"""Gestos pelo viewport real do Designer; projetos descartáveis e nenhum script executado."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    """Mede ações reais e registra falhas sem usar os arquivos do proprietário."""
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=('qt','gtk'),default='qt');parser.add_argument('--output',type=Path);parser.add_argument('--large',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='makebench-designer-qa-') as directory:
        root=Path(directory);os.environ['XDG_CONFIG_HOME']=str(root/'config');os.environ['XDG_STATE_HOME']=str(root/'state')
        from PySide6.QtCore import Qt,QPoint,QPointF
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication,QLineEdit
        from makebench.core.project import Project,ComponentKind,LayoutKind
        from makebench.editor.window import MainWindow
        app=QApplication([]);app.setQuitOnLastWindowClosed(False)
        project=Project.empty('Teste do Designer — '+args.backend);project.application['backend']=args.backend;project.root.layout=LayoutKind.FREE;project.root.properties.update(width=760,height=600)
        first=project.add(project.root.id,ComponentKind.BUTTON);first.properties['text']='Selecionar e mover';first.geometry.update(x=56,y=64,width=224,height=48)
        second=project.add(project.root.id,ComponentKind.LABEL);second.properties['text']='Texto preservado';second.geometry.update(x=500,y=350,width=160,height=32)
        if args.large:
            from makebench.core.navigation import add_window
            for index in range(8):
                extra=add_window(project,'Tela '+str(index+2))
                for count in range(30):project.add(extra.id,ComponentKind.BUTTON).properties['text']='Botão '+str(count+1)
        window=MainWindow(project);window.recovery_timer.stop();window.resize(1280,850);window.show();window.set_mode('Design');window.activateWindow();QTest.qWait(250)
        native=window.winId();failures=[];results=[];surface=getattr(window.canvas,'gtk_surface',None)
        def wait(predicate,seconds=15):
            """Processa eventos normais enquanto a imagem GTK é produzida."""
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                QTest.qWait(20)
                if predicate():return
            raise AssertionError(surface.error if surface else 'Ação não terminou no prazo')
        def settle():
            """Evita medir uma imagem antiga após uma edição assíncrona."""
            if args.backend=='gtk':wait(lambda:not surface.image.isNull() and surface.job is None and not surface.timer.isActive())
            QTest.qWait(50)
        def point(identifier,edge=None):
            """Converte alocações em coordenadas do viewport, como o clique do usuário."""
            if args.backend=='gtk':
                rect=surface.rectangles[identifier];local=rect.bottomRight()-QPoint(2,2) if edge else rect.center()
            else:
                frame=window.canvas._frames[identifier]
                if edge:
                    handle=next(h for h in frame.handles if h.property('resizeEdge')=='se');local=handle.mapTo(window.canvas,handle.rect().center())
                else:local=frame.mapTo(window.canvas,frame.rect().center())
            return window.zoom_view.mapFromScene(window.zoom_view.proxy.mapToScene(QPointF(local)))
        def check(label,operation):
            """Guarda latência e resultado de cada cenário independente."""
            started=time.monotonic()
            try:operation();results.append({'scenario':label,'ok':True,'seconds':round(time.monotonic()-started,3)})
            except BaseException as exc:failures.append(label+': '+str(exc));results.append({'scenario':label,'ok':False,'error':str(exc)})
        def select():
            QTest.mouseClick(window.zoom_view.viewport(),Qt.MouseButton.LeftButton,pos=point(first.id));assert window.selected_id==first.id,(window.selected_id,first.id)
        def move():
            select();QTest.qWait(app.doubleClickInterval()+30);before=dict(window.project.find(first.id).geometry);origin=point(first.id);pixels=QPoint(round(32*window.zoom_view.zoom),round(24*window.zoom_view.zoom))
            QTest.mousePress(window.zoom_view.viewport(),Qt.MouseButton.LeftButton,pos=origin)
            for step in range(1,5):QTest.mouseMove(window.zoom_view.viewport(),origin+pixels*step/4);QTest.qWait(15)
            QTest.mouseRelease(window.zoom_view.viewport(),Qt.MouseButton.LeftButton,pos=origin+pixels);settle()
            after=window.project.find(first.id).geometry;assert after['x']==before['x']+32 and after['y']==before['y']+24,(before,after,window.zoom_view.zoom)
        def resize():
            select();QTest.qWait(app.doubleClickInterval()+30);before=dict(window.project.find(first.id).geometry);origin=point(first.id,True);pixels=QPoint(round(32*window.zoom_view.zoom),round(24*window.zoom_view.zoom))
            QTest.mousePress(window.zoom_view.viewport(),Qt.MouseButton.LeftButton,pos=origin);QTest.mouseMove(window.zoom_view.viewport(),origin+pixels);QTest.mouseRelease(window.zoom_view.viewport(),Qt.MouseButton.LeftButton,pos=origin+pixels);settle()
            after=window.project.find(first.id).geometry;assert after['width']==before['width']+32 and after['height']==before['height']+24,(before,after)
        def property_edit():
            """Digita no inspetor real e exige que campo e janela continuem vivos."""
            select();field=window.inspector.findChild(QLineEdit,'property_text');field.setFocus();field.selectAll();QTest.keyClicks(field,'Texto alterado pelo inspetor');QTest.keyClick(field,Qt.Key.Key_Tab);settle()
            assert window.project.find(first.id).properties['text']=='Texto alterado pelo inspetor'
            assert window.inspector.findChild(QLineEdit,'property_text') is field
            assert window.winId()==native and window.isVisible()
        def history():
            """Desfazer/refazer restauram o texto sem trocar a janela nativa."""
            window.undo();settle();assert window.project.find(first.id).properties['text']=='Selecionar e mover'
            window.redo();settle();assert window.project.find(first.id).properties['text']=='Texto alterado pelo inspetor';assert window.winId()==native
        def application_settings():
            """Configuração muda só metadados; GTK mantém a versão da imagem."""
            from makebench.editor.settings import ApplicationSettings
            version=surface.version if surface and args.backend=='gtk' else None
            dialog=ApplicationSettings(window);dialog.show();QTest.qWait(30);dialog.fields['description'].setText('Configuração QA');dialog.fields['description'].editingFinished.emit();dialog.close();settle()
            if version is not None:assert surface.version==version
            assert window.winId()==native
        def insertion():
            """Inserção estrutural mantém o documento e a janela disponíveis."""
            window._select(window.project.root.id);window.palette.setCurrentRow(window.palette.findData('label'));window.add_component();settle()
            assert window.project.find(window.selected_id).kind==ComponentKind.LABEL;assert window.winId()==native
        def save_reopen():
            """Roundtrip de um projeto maior preserva os elementos e as propriedades."""
            destination=root/'project.makebench.json';assert window.save_to(destination)
            from makebench.core.storage import load_project
            reopened=load_project(destination);assert reopened.find(first.id).properties['text']=='Texto alterado pelo inspetor';assert len(reopened.roots)==len(window.project.roots)
            window._replace_project(reopened,destination);window.set_mode('Design');settle();assert window.winId()==native
        try:
            settle();check('seleção pelo viewport',select);check('mover com zoom ajustado',move);check('redimensionar com zoom ajustado',resize)
            window.zoom_view.set_zoom(1);check('mover em 100%',move)
            check('editar propriedade pelo inspetor',property_edit);check('desfazer e refazer',history);check('configurar aplicativo sem refazer prévia',application_settings);check('inserir elemento',insertion);check('salvar e reabrir',save_reopen)
            if args.output:
                args.output.mkdir(parents=True,exist_ok=True);window.grab().save(str(args.output/(args.backend+'-'+app.platformName()+'.png')))
                (args.output/(args.backend+'-'+app.platformName()+'.json')).write_text(json.dumps({'platform':app.platformName(),'backend':args.backend,'large':args.large,'device_pixel_ratio':window.devicePixelRatioF(),'results':results,'failures':failures},ensure_ascii=False,indent=2))
        finally:
            window.history.mark_saved();window.source.mark_saved();window.close();window.deleteLater();app.processEvents()
        print(json.dumps({'platform':app.platformName(),'backend':args.backend,'large':args.large,'device_pixel_ratio':window.devicePixelRatioF(),'results':results,'failures':failures},ensure_ascii=False,indent=2))
        return bool(failures)


if __name__=='__main__':raise SystemExit(main())
