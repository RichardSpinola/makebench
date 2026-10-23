"""Semântica do grafo livre, compatibilidade e transações reais do editor nativo."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from makebench.core.project import Project,ComponentKind,ProjectError
from makebench.core.logic import create_flow
from makebench.core.graph import replace_editor,restore_behavior,default_node,validate_graph
from makebench.core.codegen import generate
from makebench.core.storage import save_project,load_project
from makebench.core.navigation import add_window,navigation_edges
from makebench.runtime.worker import Context


class GraphFixture:
    """Constrói documentos por portas explícitas, sem depender do editor gráfico."""
    def __init__(self):
        self.project=Project.empty();self.flow=create_flow(self.project,self.project.root.id);replace_editor(self.flow,'nodes')
        self.graph=self.flow['graph'];self.entry=self.graph['entry'];self.output=[]

    def node(self,op,parameters=None,**inputs):
        """Aplica configuração neutra, mantendo valores e conexões identificados."""
        node=default_node(op,self.project,self.flow);node['parameters'].update(parameters or {})
        node['inputs'].update({port:value if isinstance(value,dict) and set(value)=={'node','port'} else {'value':value} for port,value in inputs.items()})
        self.graph['nodes'].append(node);return node['id']

    def edge(self,first,last,port='next'):
        """Acrescenta aresta de controle por porta, sem ordenar nós visualmente."""
        self.graph['edges'].append({'from':first,'out':port,'to':last})

    def ref(self,identifier):
        """Fio de valor independe de qualquer ligação de execução."""
        return {'node':identifier,'port':'value'}

    def run(self):
        """Executa explicitamente somente Python gerado do fixture em contexto neutro."""
        Project.from_dict(self.project.to_dict());code=generate(self.project);namespace={};exec(compile(code.text,'<makebench-generated>','exec'),namespace)
        context=Context(lambda message:self.output.append(message),lambda:None)
        namespace['on_event_1'](context);return context,code


class GraphModelTests(unittest.TestCase):
    """Fios livres preservam significado, limites, comentários e origem do programa."""
    def test_backward_execution_edges_and_layout_do_not_change_program(self):
        """Uma condição volta a atribuir uma variável até três iterações, sem árvore."""
        f=GraphFixture();initial=f.node('assign',{'name':'counter'},value=0);read=f.node('variable',{'name':'counter'})
        plus=f.node('binary',{'operator':'+'},left=f.ref(read),right=1);assign=f.node('assign',{'name':'counter'},value=f.ref(plus))
        condition=f.node('binary',{'operator':'<'},left=f.ref(read),right=3);branch=f.node('if',condition=f.ref(condition));log=f.node('log',value=f.ref(read))
        f.edge(f.entry,initial);f.edge(initial,assign);f.edge(assign,branch);f.edge(branch,assign,'true');f.edge(branch,log,'false')
        context,code=f.run();self.assertEqual(context.variables['counter'],3);self.assertEqual(f.output[-1]['text'],'3\n')
        f.flow['graph_layout']={node['id']:[i*-300,100] for i,node in enumerate(f.graph['nodes'])}
        self.assertEqual(generate(f.project).text,code.text);self.assertIn((f.flow['id'],branch),code.lines)
        self.assertIn('while _pc is not None',code.text)

    def test_repeat_sequence_and_explicit_return_preserve_order(self):
        """Repeat retorna automaticamente; Sequence executa saídas na ordem das portas."""
        f=GraphFixture();repeat=f.node('repeat',count=3);sequence=f.node('sequence');one=f.node('log',value='A');two=f.node('log',value='B');done=f.node('log',value='fim')
        f.edge(f.entry,repeat);f.edge(repeat,sequence,'body');f.edge(repeat,done,'done');f.edge(sequence,one,'0');f.edge(sequence,two,'1')
        f.run();self.assertEqual([m['text'].strip() for m in f.output],['A','B','A','B','A','B','fim'])

    def test_repeat_explicit_back_edge_does_not_duplicate_continuations(self):
        """Retornar ao próprio Repeat não duplica a pilha de repetições."""
        f=GraphFixture();repeat=f.node('repeat',count=3);log=f.node('log',value='A');f.edge(f.entry,repeat);f.edge(repeat,log,'body');f.edge(log,repeat)
        f.run();self.assertEqual(len(f.output),3)

    def test_value_cycle_is_rejected_but_execution_cycle_is_legal(self):
        """Memória usa variáveis; laços de valores são diagnosticados antes de salvar."""
        f=GraphFixture();a=f.node('join',left='a',right='');b=f.node('join',left=f.ref(a),right='b')
        next(n for n in f.graph['nodes'] if n['id']==a)['inputs']['left']=f.ref(b)
        with self.assertRaisesRegex(ProjectError,'Ciclo entre valores'):Project.from_dict(f.project.to_dict())

    def test_step_budget_diagnoses_infinite_control_loop(self):
        """Um ciclo de controle é aceito e interrompido com diagnóstico após 100 mil passos."""
        f=GraphFixture();node=f.node('if',condition=True);f.edge(f.entry,node);f.edge(node,node,'true')
        with self.assertRaisesRegex(RuntimeError,'100 mil passos'):f.run()

    def test_shared_value_dag_is_not_expanded_exponentially(self):
        """Compartilhar produtores mantém geração linear e memoização por passo."""
        f=GraphFixture();previous=f.node('constant',{'value':1})
        for _ in range(30):previous=f.node('binary',{'operator':'+'},left=f.ref(previous),right=f.ref(previous))
        log=f.node('log',value=f.ref(previous));f.edge(f.entry,log)
        _,code=f.run();self.assertEqual(f.output[-1]['text'],str(2**30)+'\n');self.assertLess(len(code.text),20000)

    def test_result_requires_execution_before_read(self):
        """Ligar saída de uma ação não executa essa ação por inferência."""
        f=GraphFixture();call=f.node('call',{'function':'saudacao'});log=f.node('log',value=f.ref(call));f.edge(f.entry,log)
        with self.assertRaisesRegex(RuntimeError,'nó produtor'):f.run()

    def test_type_mismatch_and_invalid_files_have_project_errors(self):
        """Portas, IDs malformados e tipos incompatíveis não vazam exceções internas."""
        f=GraphFixture();node=f.node('if',condition='texto')
        with self.assertRaisesRegex(ProjectError,'Tipos incompatíveis'):Project.from_dict(f.project.to_dict())
        mutations=[lambda g:g.update(entry=[]),lambda g:g['nodes'][0].update(op=[]),lambda g:g.update(edges=[{'from':[],'out':'next','to':'x'}]),lambda g:g['nodes'][1]['inputs'].update(condition={'node':[],'port':'value'})]
        for mutate in mutations:
            document=deepcopy(f.project.to_dict());document['workflows'][0]['graph']['nodes'][1]['inputs']['condition']={'value':True};mutate(document['workflows'][0]['graph'])
            with self.assertRaises(ProjectError):Project.from_dict(document)

    def test_explicit_replacement_and_recovery_preserve_blockly_comments(self):
        """Trocar editor conserva os dados completos anteriores, sem conversão implícita."""
        project=Project.empty();flow=create_flow(project,project.root.id)
        flow.update(body=[{'id':'log','op':'log','value':{'id':'v','op':'literal','value':'oi'},'comment':'comentário'}],workspace={'workspaceComments':[{'text':'nota antiga'}]})
        old=deepcopy(flow);replace_editor(flow,'nodes');self.assertEqual(flow['behavior_backups'][0],old)
        graph=deepcopy(flow['graph']);restore_behavior(flow)
        for key,value in old.items():self.assertEqual(flow[key],value)
        self.assertEqual(flow['behavior_backups'][-1]['graph'],graph)
        Project.from_dict(project.to_dict())

    def test_format7_backup_and_no_conversion_on_open(self):
        """Projetos v6 só recebem v7 ao salvar com grafo, com cópia da versão anterior."""
        with tempfile.TemporaryDirectory() as directory:
            project=Project.empty();project.add(project.root.id,ComponentKind.TERMINAL);path=Path(directory)/'app.makebench.json';save_project(project,path);old=path.read_bytes()
            opened=load_project(path);self.assertEqual(path.read_bytes(),old)
            flow=create_flow(opened,opened.root.id);replace_editor(flow,'nodes');self.assertEqual(opened.to_dict()['format_version'],7)
            save_project(opened,path);self.assertEqual(path.with_name(path.name+'.bak-v6').read_bytes(),old)
            self.assertEqual(load_project(path).workflows[0]['graph'],flow['graph'])

    def test_worker_can_pause_and_cancel_a_free_execution_cycle(self):
        """O transporte atende Pausar/Parar durante um ciclo livre no worker real."""
        import time
        from test_terminal_debug import WorkerHarness
        f=GraphFixture();node=f.node('if',condition=True);f.edge(f.entry,node);f.edge(node,node,'true')
        with tempfile.TemporaryDirectory() as directory:
            worker=WorkerHarness(f.project,'',directory)
            try:
                worker.send({'type':'event','flow':f.flow['id'],'window':f.project.root.id})
                worker.until(lambda m:m['type']=='debug' and m['state']=='paused');worker.command('continue')
                time.sleep(.03);worker.command('pause');pause=worker.until(lambda m:m['type']=='debug' and m['state']=='paused')
                self.assertEqual(pause['block'],node);worker.command('stop');self.assertEqual(worker.process.wait(timeout=3),0)
            finally:worker.close()

    def test_map_edits_graph_navigation_in_place_and_ignores_unreachable_nodes(self):
        """O mapa não anuncia ações soltas; editar ligação conserva ID, fios e comentários."""
        from makebench.core.navigation import connect_navigation,remove_navigation_block
        f=GraphFixture();target=add_window(f.project,'Outra janela');nav=f.node('open_window',{'window':target.id})
        self.assertFalse(navigation_edges(f.project));f.edge(f.entry,nav)
        node=next(n for n in f.graph['nodes'] if n['id']==nav);node['comment']='Preservar'
        connect_navigation(f.project,f.project.root.id+'|@default',f.project.root.id,target.id+'|@default',True,(f.flow['id'],nav))
        self.assertEqual(node['id'],nav);self.assertEqual(node['comment'],'Preservar');self.assertTrue(node['parameters']['close_current'])
        remove_navigation_block(f.project,f.flow['id'],nav);self.assertFalse(navigation_edges(f.project));Project.from_dict(f.project.to_dict())

    def test_graph_navigation_and_window_duplication_keep_internal_references(self):
        """O mapa lê navegação dos nós e uma janela duplicada ganha IDs próprios."""
        f=GraphFixture();terminal=f.project.add(f.project.root.id,ComponentKind.TERMINAL)
        target=add_window(f.project,'Outra janela');nav=f.node('open_window',{'window':target.id});start=f.node('terminal_start',{'component':terminal.id},program='',arguments=[])
        f.edge(f.entry,start);f.edge(start,nav);self.assertEqual(navigation_edges(f.project)[0]['target'],target.id)
        duplicate=add_window(f.project,'Cópia',duplicate=f.project.root.id)
        cloned=f.project.workflows[-1];original_ids={n['id'] for n in f.graph['nodes']};self.assertFalse(original_ids&{n['id'] for n in cloned['graph']['nodes']})
        cloned_terminal=next(n for n in duplicate.walk() if n.kind==ComponentKind.TERMINAL)
        self.assertEqual(next(n for n in cloned['graph']['nodes'] if n['op']=='terminal_start')['parameters']['component'],cloned_terminal.id)
        Project.from_dict(f.project.to_dict())


class GraphEditorTests(unittest.TestCase):
    """Portas e transações gráficas devem sobreviver a salvar, desfazer e exclusão."""
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from makebench.editor.window import MainWindow
        self.fixture=GraphFixture();self.window=MainWindow(self.fixture.project);self.window.recovery_timer.stop();self.window.logic.sync(self.fixture.flow['id']);self.panel=self.window.logic.graph_panel
        self.addCleanup(self.close)

    def close(self):
        """Encerra widgets sem diálogo e sem mexer em arquivos do usuário."""
        self.window.history.mark_saved();self.window.source.mark_saved();self.window.close()

    def test_pending_connection_immediate_save_and_undo(self):
        """Salvar imediatamente inclui um fio recém-solto, com uma etapa de desfazer."""
        from PySide6.QtCore import QPointF
        from PySide6.QtTest import QTest
        f=self.fixture;node=default_node('log',f.project,f.flow);f.graph['nodes'].append(node);self.window.history.push(self.window.project);self.window._refresh();self.window.logic.sync(f.flow['id'])
        first=self.panel.cards[f.entry].ports[('out','exec','next')];last=self.panel.cards[node['id']].ports[('in','exec','exec')]
        self.panel.connect_ports(first,last)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'app.makebench.json';self.assertTrue(self.window.save_to(path));self.assertEqual(load_project(path).workflows[0]['graph']['edges'][0]['to'],node['id'])
        self.window.undo();self.assertFalse(self.window.project.workflows[0]['graph']['edges'])

    def test_delete_preserves_other_nodes_and_restores_value_default(self):
        """Excluir produtor remove seus fios e desfazer recupera referências e IDs."""
        f=self.fixture;a=f.node('constant',{'value':'texto'});b=f.node('log',value=f.ref(a));f.edge(f.entry,b);self.window.history.push(self.window.project);self.window._refresh();self.window.logic.sync(f.flow['id'])
        self.panel.delete_ids({a});self.panel.flush()
        flow=self.window.project.workflows[0];self.assertEqual(next(n for n in flow['graph']['nodes'] if n['id']==b)['inputs']['value'],{'value':''})
        self.window.undo();flow=self.window.project.workflows[0];self.assertEqual(next(n for n in flow['graph']['nodes'] if n['id']==b)['inputs']['value']['node'],a)

    def test_group_move_is_single_undo_and_source_is_preserved(self):
        """Mover nós conserva fonte própria e registra posições, não a ordem de execução."""
        from PySide6.QtCore import QPointF
        f=self.fixture;a=f.node('log',value='texto');self.window.history.push(self.window.project);self.window._refresh();self.window.logic.sync(f.flow['id']);source=self.window.source.text
        before=deepcopy(self.window.project.workflows[0].get('graph_layout',{}))
        for card in self.panel.cards.values():card.setPos(card.pos()+QPointF(40,20))
        self.panel.commit_layout();self.panel.flush();self.window.undo()
        self.assertEqual(self.window.project.workflows[0].get('graph_layout',{}),before);self.assertEqual(self.window.source.text,source)


if __name__=='__main__':unittest.main()
