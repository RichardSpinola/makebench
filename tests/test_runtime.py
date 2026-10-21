"""Execução real de fixtures locais, sem autenticação nem alterações no sistema."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QCoreApplication,QEvent,QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox,QLineEdit
from makebench.core.logic import create_flow
from makebench.core.project import ComponentKind,Project
from makebench.runtime.window import RuntimeWindow


def literal(identifier,value):
    return {'id':identifier,'op':'literal','value':value}


def log(identifier,text):
    return {'id':identifier,'op':'log','value':literal(identifier+'_value',text)}


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.project=Project.empty('Teste de execução')
        self.button=self.project.add(self.project.root.id,ComponentKind.BUTTON)
        self.label=self.project.add(self.project.root.id,ComponentKind.LABEL)
        self.flow=create_flow(self.project,self.button.id)
        self.windows=[]

    def tearDown(self):
        for window in self.windows:
            for dialog in list(window.dialogs):dialog.reject()
            if not window.session.closed:
                self.assertFalse(window.session.admin_active,'Teste não pode deixar tarefa administrativa pendente.')
                window.stop();self.wait(lambda:window.session.closed)
            window.close()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def wait(self,predicate,timeout=5):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
        self.assertTrue(predicate(),'Tempo esgotado aguardando a execução.')

    def window(self,source='',start=True):
        w=RuntimeWindow(self.project,source,lambda path:b'',self.root,self.root/'actions.py')
        self.windows.append(w);w.show()
        if start:w.start();self.wait(lambda:w.session.active and not w.session.busy)
        return w

    def click(self,w):
        w.view.widgets[self.button.id].click()
        self.wait(lambda:not w.session.busy)

    def test_construction_does_not_execute_source_and_explicit_start_does(self):
        source="from pathlib import Path\nPath('started').write_text('ok')\n"
        w=self.window(source,start=False)
        self.assertFalse((self.root/'started').exists())
        w.start();self.wait(lambda:w.session.active)
        self.assertEqual((self.root/'started').read_text(),'ok')

    def test_fields_pages_functions_and_persistent_enabled_state(self):
        pages=self.project.add(self.project.root.id,ComponentKind.PAGES)
        page=self.project.add(pages.id,ComponentKind.PAGE)
        field=self.project.add(page.id,ComponentKind.TEXT_INPUT)
        create_flow(self.project,self.project.root.id)['body']=[log('start','Início')]
        self.flow['body']=[{'id':'page','op':'show_page','component':page.id},
            {'id':'text','op':'set_text','component':self.label.id,'value':{'id':'read','op':'read','component':field.id,'attribute':'text'}},
            {'id':'call','op':'call','function':'greet','value':literal('arg','Linux')},
            {'id':'disabled','op':'set_enabled','component':self.button.id,'value':literal('false',False)}]
        w=self.window('def greet(ctx, valor):\n    print("Olá",valor)\n')
        w.view.widgets[field.id].setText('Meu nome')
        self.click(w)
        self.assertEqual(w.view.tabs[pages.id].currentIndex(),1)
        self.assertEqual(w.view.widgets[self.label.id].text(),'Meu nome')
        self.assertIn('Olá Linux',w.output.toPlainText())
        self.assertFalse(w.view.widgets[self.button.id].isEnabled())
        self.assertEqual(self.label.properties['text'],'Novo texto')
        self.assertEqual(pages.properties['initial_page'],pages.children[0].id)

    def test_argument_boundaries_and_stderr_zero_exit(self):
        value='$(touch SHOULD_NOT_EXIST); espaço "aspas"'
        self.flow['body']=[{'id':'run','op':'run','admin':False,'program':literal('program',sys.executable),
            'arguments':{'id':'args','op':'list','items':[literal('flag','-c'),literal('code','import sys; print(sys.argv[1]); print("aviso",file=sys.stderr)'),literal('arg',value)]}},log('after','CONTINUOU')]
        w=self.window();self.click(w)
        text=w.output.toPlainText()
        self.assertIn(value,text);self.assertIn('aviso',text);self.assertIn('CONTINUOU',text)
        self.assertEqual(w.state.text(),'Fluxo concluído.')
        self.assertFalse((self.root/'SHOULD_NOT_EXIST').exists())

    def test_nonzero_and_missing_executable_stop_sequence_with_origin(self):
        self.flow['body']=[{'id':'script','op':'script','admin':False,'source':literal('source','printf "Antes\\n"; printf "Erro\\n" >&2; exit 7'),
                           'arguments':{'id':'args','op':'list','items':[]}},log('after','NAO_CONTINUAR')]
        w=self.window();self.click(w)
        self.assertEqual(w.last_error['block'],'script')
        self.assertIn('código 7',w.last_error['message'])
        self.assertNotIn('NAO_CONTINUAR',w.output.toPlainText())
        self.assertTrue(w.locate.isEnabled())
        self.flow['body'][0]={'id':'missing','op':'run','admin':False,'program':literal('p','makebench-missing-executable'), 'arguments':{'id':'a','op':'list','items':[]}}
        other=self.window();self.click(other)
        self.assertEqual(other.last_error['block'],'missing')
        self.assertIn('não encontrado',other.last_error['message'])

    def test_own_function_traceback_and_worker_remains_available(self):
        self.flow['body']=[{'id':'function','op':'call','function':'fail','value':literal('arg','')}]
        w=self.window('def fail(ctx, valor):\n    raise ValueError("Falha própria")\n')
        self.click(w)
        self.assertEqual(w.last_error['block'],'function');self.assertEqual(w.last_error['source_line'],2)
        self.assertIn('Falha própria',w.output.toPlainText())
        self.assertTrue(w.session.active)

    def test_text_choice_and_cancel_do_not_run_following_actions(self):
        self.flow['body']=[{'id':'ask','op':'ask','kind':'text','name':'name','prompt':literal('prompt','Seu nome?'),'options':{'id':'opts','op':'list','items':[]}},
            {'id':'choice','op':'ask','kind':'choice','name':'choice','prompt':literal('question','Uma opção?'),'options':{'id':'options','op':'list','items':[literal('one','A'),literal('two','B')]}},
            {'id':'result','op':'log','value':{'id':'name','op':'variable','name':'name'}},log('after','NAO_APOS_CANCELAR')]
        w=self.window();w.view.widgets[self.button.id].click()
        self.wait(lambda:bool(w.dialogs));dialog=next(iter(w.dialogs));self.assertIsInstance(dialog,QInputDialog)
        dialog.setTextValue('Richard');dialog.accept()
        self.wait(lambda:bool(w.dialogs));dialog=next(iter(w.dialogs))
        self.assertEqual(dialog.comboBoxItems(),['A','B']);dialog.reject()
        self.wait(lambda:not w.session.busy)
        self.assertEqual(w.state.text(),'Fluxo cancelado.')
        self.assertNotIn('NAO_APOS_CANCELAR',w.output.toPlainText())

    def test_confirmation_no_cancels_flow(self):
        self.flow['body']=[{'id':'confirm','op':'confirm','prompt':literal('prompt','Continuar?')},log('after','NAO')]
        w=self.window();w.view.widgets[self.button.id].click();self.wait(lambda:bool(w.dialogs))
        dialog=next(iter(w.dialogs));dialog.button(QMessageBox.StandardButton.No).click()
        self.wait(lambda:not w.session.busy)
        self.assertEqual(w.state.text(),'Fluxo cancelado.')
        self.assertNotIn('NAO',w.output.toPlainText())

    def test_infinite_python_is_cancellable_and_gui_ticks(self):
        self.flow['body']=[{'id':'call','op':'call','function':'infinite','value':literal('arg','')}]
        w=self.window('def infinite(ctx, valor):\n    while True: pass\n')
        ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(10)
        w.view.widgets[self.button.id].click();QTest.qWait(120)
        self.assertTrue(w.session.busy);self.assertGreater(len(ticks),3)
        started=time.monotonic();w.stop();self.wait(lambda:w.session.closed,3)
        timer.stop();self.assertLess(time.monotonic()-started,2)

    def test_cancelling_task_kills_ordinary_descendants(self):
        code='''import os,signal,subprocess,sys,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
p=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
open('child.pid','w').write(str(p.pid))
print('Pronto',flush=True)
time.sleep(60)
'''
        self.flow['body']=[{'id':'run','op':'run','admin':False,'program':literal('p',sys.executable),'arguments':{'id':'args','op':'list','items':[literal('flag','-u'),literal('flag2','-c'),literal('code',code)]}}]
        w=self.window();w.view.widgets[self.button.id].click()
        self.wait(lambda:(self.root/'child.pid').exists())
        child=int((self.root/'child.pid').read_text());w.stop();self.wait(lambda:w.session.closed)
        def gone():
            status=Path(f'/proc/{child}/status')
            return not status.exists() or '\nState:\tZ' in status.read_text()
        self.wait(gone)

    def test_admin_protocol_with_disposable_fake_agent(self):
        # Executável descartável simula o resultado do agente; nunca chama pkexec real.
        original=shutil.which
        fake=self.root/'pkexec-test';fake.write_text('#!/bin/sh\nsleep 0.15\nexit 126\n');fake.chmod(0o700)
        self.flow['body']=[{'id':'admin','op':'run','admin':True,'program':literal('p','/usr/bin/true'),
                           'arguments':{'id':'args','op':'list','items':[]}},log('after','NAO_CONTINUAR')]
        with patch('makebench.runtime.process.shutil.which',side_effect=lambda value:str(fake) if value=='pkexec' else original(value)):
            w=self.window();w.view.widgets[self.button.id].click()
            self.wait(lambda:w.session.admin_active)
            self.assertFalse(w.stop());self.assertFalse(w.stop_button.isEnabled())
            self.wait(lambda:not w.session.busy)
        self.assertFalse(w.session.admin_active)
        self.assertEqual(w.state.text(),'Fluxo cancelado.')
        self.assertNotIn('NAO_CONTINUAR',w.output.toPlainText())

    def test_top_level_function_source_error_keeps_original_traceback(self):
        w=self.window('raise ValueError("Falha ao carregar funções")\n',start=False)
        w.start();self.wait(lambda:w.session.closed)
        self.assertIn('Falha ao carregar funções',w.last_error['message'])
        self.assertEqual(w.last_error['source_line'],1)
        self.assertTrue(w.locate.isEnabled())

    def test_choice_and_file_directory_dialogs_return_explicit_values(self):
        from PySide6.QtWidgets import QFileDialog
        chosen=self.root/'file.txt';chosen.write_text('fixture')
        self.flow['body']=[{'id':'ask','op':'ask','kind':'file','name':'file','prompt':literal('p','Arquivo?'),'options':{'id':'o','op':'list','items':[]}},
            {'id':'log','op':'log','value':{'id':'var','op':'variable','name':'file'}}]
        w=self.window();w.view.widgets[self.button.id].click();self.wait(lambda:bool(w.dialogs))
        dialog=next(iter(w.dialogs));self.assertIsInstance(dialog,QFileDialog)
        QTest.qWait(100)
        edit=dialog.findChild(QLineEdit,'fileNameEdit');edit.setFocus();edit.selectAll();QTest.keyClicks(edit,str(chosen))
        QTest.keyClick(edit,Qt.Key.Key_Return);self.wait(lambda:not w.session.busy)
        self.assertIn(str(chosen),w.output.toPlainText())
        self.flow['body'][0]['kind']='directory'
        other=self.window();other.view.widgets[self.button.id].click();self.wait(lambda:bool(other.dialogs))
        dialog=next(iter(other.dialogs));QTest.qWait(100)
        edit=dialog.findChild(QLineEdit,'fileNameEdit');edit.setFocus();edit.selectAll();QTest.keyClicks(edit,str(self.root))
        QTest.keyClick(edit,Qt.Key.Key_Return);self.wait(lambda:not other.session.busy)
        self.assertIn(str(self.root),other.output.toPlainText())

    def test_admin_success_and_denial_using_only_fake_disposable_agent(self):
        original=shutil.which;fake=self.root/'pkexec-test'
        self.flow['body']=[{'id':'admin','op':'run','admin':True,'program':literal('p','/usr/bin/true'),'arguments':{'id':'args','op':'list','items':[]}},log('after','APOS_AUTORIZAR')]
        for code in (0,127):
            with self.subTest(code=code):
                fake.write_text(f'#!/bin/sh\nexit {code}\n');fake.chmod(0o700)
                with patch('makebench.runtime.process.shutil.which',side_effect=lambda value:str(fake) if value=='pkexec' else original(value)):
                    w=self.window();self.click(w)
                if code==0:self.assertIn('APOS_AUTORIZAR',w.output.toPlainText())
                else:
                    self.assertNotIn('APOS_AUTORIZAR',w.output.toPlainText())
                    self.assertEqual(w.last_error['block'],'admin')

    def test_script_center_simulation_completes_with_stderr_and_progress(self):
        from makebench.core.storage import load_project
        from makebench.core.source import SourceBuffer
        self.project=load_project('examples/script-center/app.makebench.json')
        self.button=self.project.find('button_setup')
        w=self.window(SourceBuffer.load(Path('examples/script-center/app.makebench.json')).text)
        w.view.widgets[self.button.id].click();self.wait(lambda:bool(w.dialogs))
        dialog=next(iter(w.dialogs));dialog.setTextValue('Reprodutor de música');dialog.accept()
        self.wait(lambda:bool(w.dialogs));dialog=next(iter(w.dialogs));dialog.button(QMessageBox.StandardButton.Yes).click()
        self.wait(lambda:not w.session.busy)
        self.assertEqual(w.view.widgets['progress_task'].value(),100)
        self.assertIn('Aviso de exemplo',w.output.toPlainText())
        self.assertIn('Nenhum aplicativo foi instalado',w.output.toPlainText())
        self.assertEqual(w.state.text(),'Fluxo concluído.')

    def test_editor_does_not_abandon_admin_task_when_closing(self):
        from makebench.editor.window import MainWindow
        original=shutil.which;fake=self.root/'pkexec-test'
        fake.write_text('#!/bin/sh\nsleep 0.35\nexit 0\n');fake.chmod(0o700)
        self.flow['body']=[{'id':'admin','op':'run','admin':True,'program':literal('p','/usr/bin/true'),'arguments':{'id':'args','op':'list','items':[]}}]
        editor=MainWindow(self.project);editor.show()
        try:
            with patch('makebench.runtime.process.shutil.which',side_effect=lambda value:str(fake) if value=='pkexec' else original(value)):
                editor.run_project();runtime=editor.runtime_window
                self.wait(lambda:runtime.session.active and not runtime.session.busy)
                runtime.view.widgets[self.button.id].click();self.wait(lambda:runtime.session.admin_active)
                editor.close();self.assertTrue(editor.isVisible())
                runtime.close();self.assertFalse(runtime.close_pending)
                self.wait(lambda:not runtime.session.busy)
            editor.close();self.wait(lambda:not editor.isVisible())
            self.assertTrue(runtime.session.closed)
        finally:
            if editor.runtime_window is not None and not editor.runtime_window.session.closed:
                editor.runtime_window.stop();self.wait(lambda:editor.runtime_window is None or editor.runtime_window.session.closed)
            editor.history.mark_saved();editor.source.mark_saved();editor.close();editor.deleteLater()


if __name__=='__main__':unittest.main()
