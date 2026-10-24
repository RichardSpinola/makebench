"""Processo Python de execução. Só é iniciado por uma ação explícita do usuário.

O protocolo JSON usa um descritor próprio; stdout/stderr do código são saída de
usuário. Isto separa travamentos do editor, mas não é sandbox de código não confiável.
"""
from __future__ import annotations

import io
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import traceback
from .debugger import Debugger, DebugStopped, WorkerTransport

from makebench.core.codegen import generate
from makebench.core.project import Project


class Cancelled(Exception):
    """Interrompe o fluxo quando um diálogo é cancelado ou uma confirmação recusada."""


class TaskError(Exception):
    """Falha de tarefa externa; ações posteriores não são executadas."""


class Context:
    """API síncrona do aplicativo, com requisições atendidas pelo processo Qt."""
    def __init__(self, send, receive):
        """Recebe transporte JSON; todas as interações Qt ficam no outro processo."""
        self.send, self.receive = send, receive
        self.variables = {}
        self.actions = {}
        self.window_scopes = {}
        self.window_defaults = {}
        self.current_window = None
        self.sequence = 0
        self.receive_response = None
        self.debugger = None
        self.graph_node = None

    def request(self, method, **values):
        """Espera a resposta correspondente, abortando em cancelamento/falha."""
        self.sequence += 1
        identifier = self.sequence
        self.send({'type':'request','id':identifier,'method':method,**values})
        reply = self.receive_response(identifier) if self.receive_response else self.receive()
        if reply.get('type') != 'response' or reply.get('id') != identifier:
            raise RuntimeError('Resposta inesperada do aplicativo.')
        if reply.get('cancelled'):
            raise Cancelled(reply.get('error', 'Operação cancelada.'))
        if not reply.get('ok'):
            raise TaskError(reply.get('error', 'A tarefa falhou.'))
        return reply.get('value')

    def graph_checkpoint(self, flow, node, steps):
        """Limita cada evento a 100 mil passos e cede CPU em ciclos de execução."""
        self.graph_node=node
        if self.debugger:self.debugger.checkpoint()
        if steps>100000:raise RuntimeError('Grafo interrompido após 100 mil passos no evento '+str(flow)+'.')
        if steps%128==0:
            import time
            time.sleep(.001)

    def graph_result(self, values, node):
        """Exige execução prévia do produtor; fio de valor não dispara ações sozinho."""
        if node not in values:raise RuntimeError('Execute o nó produtor antes de ler seu resultado: '+str(node))
        return values[node]

    def terminal_start(self, component, program=None, arguments=None):
        """Inicia PTY de um componente Terminal durante a execução explícita."""
        return self.request('terminal_start',component=component,program=program,arguments=arguments or [])

    def terminal_send(self, component, value):
        """Envia entrada ao terminal; texto não é interpolado em outro comando."""
        return self.request('terminal_send',component=component,value=str(value))

    def terminal_stop(self, component):
        """Encerra processos pertencentes ao terminal selecionado."""
        return self.request('terminal_stop',component=component)

    def read(self, component, attribute):
        """Lê texto/seleção/progresso atuais, incluindo entradas alteradas pelo usuário."""
        return self.request('read',component=component,attribute=attribute)

    def set_text(self, component, value):
        """Atualiza texto de um controle sem substituir o documento no editor."""
        return self.request('set_text',component=component,value=str(value))

    def set_enabled(self, component, value):
        """Habilita/desabilita um controle da instância em execução."""
        return self.request('set_enabled',component=component,value=bool(value))

    def set_value(self, component, value):
        """Atualiza progresso inteiro no intervalo 0–100."""
        return self.request('set_value',component=component,value=int(value))

    @property
    def window_variables(self):
        """Dados da janela atual, preservados entre seus eventos."""
        return self.window_scopes.setdefault(self.current_window, {})

    def go_state(self, state):
        """Aplica uma variação da janela atual sem copiar sua estrutura."""
        return self.request('go_state', state=state)

    def open_window(self, window, close_current=False):
        """Abre outra janela real, opcionalmente fechando a interface atual."""
        result=self.request('open_window',window=window,close_current=close_current)
        if result and result.get('reset'):self.window_scopes[window]=deepcopy(self.window_defaults.get(window,{}))

    def close_window(self):
        """Fecha a janela do evento; a última janela encerra o aplicativo."""
        return self.request('close_window')

    def show_page(self, component):
        """Revela uma página e seus ancestrais na janela do aplicativo."""
        return self.request('show_page',component=component)

    def log(self, value):
        """Envia saída textual imediatamente, sem bloquear o editor."""
        self.send({'type':'log','channel':'stdout','text':str(value)+'\n'})

    def message(self, value):
        """Apresenta mensagem e aguarda o fechamento para continuar o fluxo."""
        return self.request('message',prompt=str(value))

    def ask(self, kind, prompt, options=None):
        """Obtém entrada declarada; Cancelar encerra o fluxo antes da próxima ação."""
        return self.request('ask',kind=kind,prompt=str(prompt),options=options or [])

    def confirm(self, prompt):
        """Continua apenas se o usuário responder Sim."""
        return self.request('confirm',prompt=str(prompt))

    def run(self, program, arguments=None, *, admin=False, check=True):
        """Executa argv separado, com saída ao vivo; código não zero falha por padrão.

        stderr não determina sucesso. admin solicita pkexec via aplicativo; o
        editor nunca recebe senhas. check=False permite tratar explicitamente
        um código não zero em funções próprias.
        """
        if arguments is None:arguments=[]
        if not isinstance(arguments,list) or any(not isinstance(arg,str) for arg in arguments):
            raise TypeError('Argumentos precisam ser uma lista de textos.')
        result = self.request('run',program=program,arguments=arguments,admin=admin)
        code = result['code']
        if result.get('crashed') or (check and code != 0):
            raise TaskError(f'Tarefa terminou com código {code}.')
        return code

    def run_script(self, source, arguments=None, *, admin=False, check=True):
        """Executa Bash explícito; argumentos viram $1… e não são concatenados ao script."""
        if not isinstance(source,str):
            raise TypeError('O script precisa ser texto.')
        if arguments is None:arguments=[]
        if not isinstance(arguments,list) or any(not isinstance(arg,str) for arg in arguments):
            raise TypeError('Argumentos precisam ser uma lista de textos.')
        return self.run('/bin/bash',['-c',source,'makebench-script',*arguments],admin=admin,check=check)

    def call_action(self, name, value):
        """Resolve função própria somente nesta execução explícita."""
        function = self.actions.get(name)
        if not callable(function):
            raise RuntimeError(f'Função não encontrada: {name}.')
        return function(self,value)


class Output(io.TextIOBase):
    """Transforma print em mensagens de saída, preservando o canal JSON."""
    def __init__(self, send, channel):
        """Associa escrita textual a stdout ou stderr do aplicativo."""
        self.send,self.channel=send,channel

    def write(self, value):
        """Divide saída grande em mensagens limitadas para o editor continuar responsivo."""
        for offset in range(0,len(value),8192):
            self.send({'type':'log','channel':self.channel,'text':value[offset:offset+8192]})
        return len(value)

    def flush(self):
        """O transporte já grava imediatamente; não há buffer a descarregar."""



def main():
    """Inicializa um snapshot e atende eventos em sequência, fora do processo Qt."""
    protocol = os.fdopen(os.dup(sys.stdout.fileno()),'w',encoding='utf-8',buffering=1)
    os.dup2(sys.stderr.fileno(),sys.stdout.fileno())
    def send(value):
        """Serializa exclusivamente mensagens do protocolo em uma linha UTF-8."""
        protocol.write(json.dumps(value,ensure_ascii=True,allow_nan=False)+'\n'); protocol.flush()
    def receive():
        """Lê uma mensagem; EOF encerra a instância para não deixar worker órfão."""
        line=sys.stdin.readline()
        if not line:raise EOFError('O aplicativo foi encerrado.')
        return json.loads(line)
    sys.stdout=Output(send,'stdout');sys.stderr=Output(send,'stderr')
    context=Context(send,receive)
    debugger=Debugger(send)
    generated=None; source_filename='<makebench-actions>'; flow_id=None; file_names={}
    def failure(exc):
        """Localiza erro em bloco gerado e/ou linha da função própria."""
        line=source_line=None;source_file=None
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename=='<makebench-generated>':line=frame.lineno
            if frame.filename in file_names or frame.filename==source_filename:source_line=frame.lineno;source_file=file_names.get(frame.filename,'@actions')
        block=next((block for (flow,block),number in (generated.lines.items() if generated else []) if flow==flow_id and number==line),None)
        if block is None:block=context.graph_node
        send({'type':'error','message':f'{type(exc).__name__}: {exc}', 'flow':flow_id,'block':block,'line':line,'source_line':source_line,'source_file':source_file,'traceback':traceback.format_exc()})
    try:
        snapshot=receive()
        project=Project.from_dict(snapshot['project'])
        for variable in project.variables:
            scope=context.variables if variable.get('scope','project')=='project' else context.window_scopes.setdefault(variable['window'],{})
            scope[variable['name']]=variable.get('initial')
        context.window_defaults=deepcopy(context.window_scopes)
        source=snapshot['source'];source_filename=snapshot.get('source_filename',source_filename)
        from makebench.core.source import SourceText
        from makebench.core.source_runtime import SnapshotImporter
        modules={name:text for name,text in snapshot.get('source_files',{}).items() if name!='@actions'}
        if set(modules)!=set(project.python_files):raise ValueError('O snapshot não contém todos os módulos declarados.')
        importer=SnapshotImporter(modules,Path(snapshot['root']).resolve());importer.install()
        file_names={source_filename:'@actions',**importer.filenames}
        source=SourceText(source,modules)
        generated=generate(project,source)
        if generated.diagnostics:raise ValueError('\n'.join(generated.diagnostics))
        context.debugger=debugger
        debugger.configure(snapshot.get('debug',{}),source_filename,generated,context,file_names)
        transport=WorkerTransport(receive,debugger)
        context.receive_response=lambda identifier:transport.receive(response=identifier)
        root=Path(snapshot['root']).resolve();os.chdir(root);sys.path.insert(0,str(root))
        namespace={'__name__':'makebench_project_actions','__file__':source_filename}
        exec(compile(source,source_filename,'exec'),namespace)
        context.actions=namespace
        handlers={}
        compiled={};exec(compile(generated.text,'<makebench-generated>','exec'),compiled)
        for index,flow in enumerate(project.workflows,1):
            handlers[flow['id']]=compiled[f'on_event_{index}']
        send({'type':'ready'})
        while True:
            message=transport.receive()
            if message.get('type')=='shutdown':break
            if message.get('type')!='event' or message.get('flow') not in handlers:continue
            context.current_window=message.get('window',project.root.id)
            flow_id=message['flow'];debugger.flow=flow_id
            debugger.component=next(f['event']['component'] for f in project.workflows if f['id']==flow_id)
            send({'type':'busy','flow':flow_id})
            outcome='success';context.graph_node=None
            try:
                if debugger.enabled:sys.settrace(debugger.trace)
                handlers[flow_id](context)
            except Cancelled as exc:
                outcome='cancelled';send({'type':'log','channel':'status','text':str(exc)+'\n'})
            except Exception as exc:
                outcome='error';failure(exc)
            finally:
                sys.settrace(None);debugger.last_frame=None
            send({'type':'done','flow':flow_id,'outcome':outcome})
    except (EOFError, DebugStopped):
        pass
    except BaseException as exc:
        failure(exc)
    finally:
        protocol.close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
