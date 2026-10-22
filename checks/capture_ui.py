"""Capturas reais do editor para QA; nunca executa scripts do projeto."""
import argparse
import os
from pathlib import Path
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS','--disable-gpu')


def main():
    """Gera matriz de modos/tamanhos/temas usando um projeto conhecido em memória."""
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--sizes',nargs='+',default=['1280x800','1920x1080'])
    parser.add_argument('--themes',nargs='+',default=['light','dark'])
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='makebench-captures-') as temporary:
        os.environ['XDG_CONFIG_HOME']=str(Path(temporary)/'config');os.environ['XDG_STATE_HOME']=str(Path(temporary)/'state')
        from PySide6.QtCore import Qt,QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        app=QApplication([]);app.setQuitOnLastWindowClosed(False)
        from makebench.core.navigation import welcome_template
        from makebench.editor.window import MainWindow
        from makebench.editor.theme import manager
        window=MainWindow(welcome_template());window.recovery_timer.stop();window.show()
        window.set_mode('Lógica')
        deadline=time.monotonic()+15
        while not window.logic.ready and time.monotonic()<deadline:QTest.qWait(25)
        if not window.logic.ready:raise RuntimeError(window.logic.diagnostics.text())
        for theme in args.themes:
            manager().set_mode(theme)
            for size in args.sizes:
                width,height=map(int,size.split('x'));window.resize(width,height)
                window.activate_window(window.project.root.id,'@default')
                QTest.qWait(100)
                for mode in ['Início','Design','Lógica','Código','Mapa','Publicar']:
                    if mode=='Início':window.show_home()
                    else:
                        if mode=='Lógica':
                            button=next(node for node in window.project.root.walk() if node.properties.get('text')=='Próximo')
                            window._select(button.id)
                        window.set_mode(mode)
                    app.processEvents()
                    if mode=='Mapa':window.map_panel.fit()
                    QTest.qWait(100)
                    filename=args.output/f'{theme}-{size}-{ {"Início":"inicio","Design":"design","Lógica":"logica","Código":"codigo","Mapa":"mapa","Publicar":"publicar"}[mode] }.png'
                    if not window.grab().save(str(filename)):raise RuntimeError('Falha ao gravar '+str(filename))
                # O diálogo é real; somente capturado e cancelado, sem criar pasta.
                def capture_dialog():
                    dialog=app.activeModalWidget()
                    if dialog:
                        dialog.grab().save(str(args.output/f'{theme}-{size}-novo-projeto.png'));dialog.reject()
                QTimer.singleShot(100,capture_dialog);window.new_project_dialog('blank')
        window.history.mark_saved();window.source.mark_saved();window.close()
        if window.logic.view:
            window.logic.page.deleteLater()
            from PySide6.QtCore import QCoreApplication,QEvent
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        window.deleteLater();app.processEvents()
    print('Capturas gravadas em',args.output)


if __name__=='__main__':main()
