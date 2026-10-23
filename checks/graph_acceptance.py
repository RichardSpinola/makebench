"""Jornada real: fios, histórico, arquivo, depuração, duas janelas e exportação Qt/GTK."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import time
import zipfile


def main():
    """Usa a bancada nativa e um aplicativo independente em diretórios descartáveis."""
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=('qt','gtk'),required=True);parser.add_argument('--theme',choices=('light','dark'),default='dark');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='makebench-graph-qa-') as directory:
        root=Path(directory);os.environ['XDG_CONFIG_HOME']=str(root/'config');os.environ['XDG_STATE_HOME']=str(root/'state')
        from PySide6.QtCore import Qt,QPoint,QPointF,QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from native_palette import kde_palette
        from makebench.core.project import Project
        from makebench.core.graph import default_node
        from makebench.core.storage import load_project,save_project
        from makebench.core.source import SourceBuffer
        from makebench.core.logic import create_flow
        from makebench.core.exporter import export_source
        from makebench.editor.window import MainWindow
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts);app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setPalette(kde_palette(args.theme))
        fixture=Path(__file__).resolve().parents[1]/'examples/free-graph'/f'{args.backend}.makebench.json';project=load_project(fixture);source=SourceBuffer.load(fixture).text
        marker=root/'module-executed';source='from pathlib import Path\nPath('+repr(str(marker))+').write_text("explícito")\n'+source
        shutil.copytree(fixture.parent/'assets',root/'assets')
        path=root/'project.makebench.json';save_project(project,path);path.with_name('project.actions.py').write_text(source)
        window=MainWindow(project,path);window.recovery_timer.stop();window.logic.ensure_loaded();window.show();window.set_mode('Lógica');window.logic.sync(project.workflows[0]['id']);panel=window.logic.graph_panel
        results=[];errors=[];pauses=[]
        def wait(predicate,seconds=15):
            """Aguarda estado verificável processando os eventos gráficos nativos."""
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                QTest.qWait(20)
                if errors:raise AssertionError(errors)
                if predicate():return
            raise AssertionError(('Prazo excedido',window.debug_panel.status.text(),pauses))
        def capture(name):
            """Captura a janela real do editor, sem montagem de interface."""
            QTest.qWait(80);window.grab().save(str(args.output/(name+'.png')))
        wait(lambda:window.logic.ready);panel.fit();QTest.qWait(100);assert not marker.exists();capture('01-nos')
        panel.disconnect(panel.cards['repeat'].ports[('in','value','count')]);panel.flush()
        # Arraste real de uma porta de valor; o destino recupera a ligação com o produtor.
        first=panel.view.mapFromScene(panel.cards['three'].ports[('out','value','value')].scenePos());last=panel.view.mapFromScene(panel.cards['repeat'].ports[('in','value','count')].scenePos())
        QTest.mousePress(panel.view.viewport(),Qt.MouseButton.LeftButton,pos=first);QTest.mouseMove(panel.view.viewport(),last,40);QTest.mouseRelease(panel.view.viewport(),Qt.MouseButton.LeftButton,pos=last)
        def binding():return next(n for n in window.project.workflows[0]['graph']['nodes'] if n['id']=='repeat')['inputs']['count']
        wait(lambda:binding()=={'node':'three','port':'value'});results.append('Conexão por arraste real')
        window.undo();assert 'value' in binding();window.redo();assert binding()['node']=='three';results.append('Desfazer/refazer fio')
        before=deepcopy(window.project.to_dict());own=window.source.text
        nodes=[default_node('constant',window.project,window.project.workflows[0]) for _ in range(200)]
        window._edit(lambda:window.project.workflows[0]['graph']['nodes'].extend(nodes));assert len(panel.cards)==213;window.undo();assert window.project.to_dict()==before;assert window.source.text==own;results.append('Projeto maior com 213 nós e undo')
        assert window.save_to(path);loaded=load_project(path);assert loaded.workflows[0]['graph']==window.project.workflows[0]['graph'];assert loaded.workflows[0]['graph_comments']==window.project.workflows[0]['graph_comments'];assert not marker.exists();results.append('Salvar/reabrir preserva grafo e comentários sem executar')
        sourceline=next(index for index,line in enumerate(source.splitlines(),1) if 'ctx.variables' in line);window.toggle_source_breakpoint(sourceline)
        window.confirm_trust=lambda:True;window.debug_project();runtime=window.runtime_window;runtime.session.error.connect(errors.append);runtime.session.debug_changed.connect(lambda m:pauses.append(m) if m.get('state')=='paused' else None)
        wait(lambda:runtime.session.active);event=window.project.workflows[0]['event']['component']
        if args.backend=='qt':runtime.view.widgets[event].click()
        else:runtime.command({'command':'click','component':event})
        wait(lambda:len(pauses)>=1);assert marker.exists();window.debug_command('step_over');wait(lambda:len(pauses)>=2)
        window.debug_command('continue')
        for target in range(3,6):
            wait(lambda:len(pauses)>=target);assert pauses[-1].get('block')=='send';assert panel.cards['send'].active
            if target==3:capture('02-no-ativo')
            window.debug_command('continue')
        wait(lambda:any(m.get('source_line')==sourceline for m in pauses));capture('03-funcao-propria')
        assert pauses[-1]['stack'][0]['variables']['resultado'] is True
        window.debug_command('continue');wait(lambda:not runtime.session.busy)
        if args.backend=='qt':
            terminal=runtime.widget_for('terminal')[1];wait(lambda:sum(line.strip()=='PASSO' for line in terminal.terminal.screen.display)==3);assert len(runtime.open_windows)==2
        else:
            observations=[];runtime.session.inspection.connect(observations.append)
            def inspect():runtime.command({'command':'inspect'});QTest.qWait(60);return bool(observations and sum(line.strip()=='PASSO' for terminal in observations[-1]['terminals'].values() for line in terminal['screen'])==3)
            wait(inspect);assert len(observations[-1]['windows'])==2
        results.extend(['Repetição e condição no runtime','Terminal recebeu três resultados','Duas janelas reais','Pontos em nós e linha Python','Pilha/variáveis e destaque do nó'])
        window.stop_test();wait(lambda:runtime.session.closed);actual_scale=window.devicePixelRatioF();window.history.mark_saved();window.source.mark_saved();window.close()
        if hasattr(window.logic,'page'):window.logic.page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        # Aplicativo fonte fora do editor: início explícito, encerra sozinho após a segunda janela.
        exported=Project.from_dict(loaded.to_dict());flow=exported.workflows[0];flow['event']={'component':exported.root.id,'kind':'start'}
        next(n for n in flow['graph']['nodes'] if n['id']=='open')['parameters']['close_current']=True
        create_flow(exported,exported.windows[0].id)['body']=[{'id':'close-exported','op':'close_window'}]
        marker.unlink()
        export_source(exported,SourceBuffer.load(path).text,lambda name:(root/name).read_bytes(),root/'source.zip');assert not marker.exists()
        with zipfile.ZipFile(root/'source.zip') as archive:archive.extractall(root/'app')
        environment=dict(os.environ);environment.pop('PYTHONPATH',None)
        result=subprocess.run([sys.executable,'run.py'],cwd=root/'app',env=environment,capture_output=True,text=True,timeout=20)
        assert result.returncode==0,(result.stdout,result.stderr);assert marker.exists();assert 'PASSOS=3' in result.stdout,result.stdout;results.append('Aplicativo exportado executa fora do editor e encerra')
        (args.output/'results.json').write_text(json.dumps({'backend':args.backend,'theme':args.theme,'actual_scale':actual_scale,'results':results,'pauses':pauses},ensure_ascii=False,indent=2));print('OK',args.backend,len(results),'cenários')


if __name__=='__main__':main()
