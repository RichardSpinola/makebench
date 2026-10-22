"""Aceitação Qt: tema nativo, navegação, início, campos e preferências."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from makebench.core.project import Project,ComponentKind,LayoutKind
from makebench.core.storage import save_project


class NativeQtInterfaceTests(unittest.TestCase):
    """Regressões visuais funcionais do editor Qt e da tela inicial."""
    @classmethod
    def setUpClass(cls):
        """Aplicação offscreen mantém estilo Qt padrão para não depender do KDE real."""
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        """Isola arquivos e preferências dos testes de ações da tela inicial."""
        from makebench.editor.window import MainWindow
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.window=MainWindow();self.window.recovery_timer.stop();self.window.show();self.app.processEvents()

    def tearDown(self):
        """Não deixa diálogos abertos nem ativa confirmação de descarte no fim do teste."""
        self.window.history.mark_saved();self.window.source.mark_saved();self.window.close();self.window.deleteLater();self.app.processEvents()

    def test_native_theme_and_stable_navigation_without_global_qss(self):
        """A barra não some no mapa, publicar ou início; não há stylesheet global."""
        w=self.window
        for mode in ('Design','Mapa','Publicar','Código','Lógica'):
            if mode=='Lógica':continue  # WebEngine é exercitado na integração separada.
            w.set_mode(mode);self.app.processEvents()
            self.assertTrue(w.workspace_toolbar.isVisible());self.assertTrue(all(b.isVisible() for b in w.mode_buttons.values()))
        w.show_home();self.assertTrue(w.workspace_toolbar.isVisible());self.assertEqual(self.app.styleSheet(),'')

    def test_insert_library_uses_vertical_space_and_has_search(self):
        """Biblioteca não mantém limite de 195 px nem rótulo expandido acima da lista."""
        w=self.window;w.left_tabs.setCurrentIndex(1);self.app.processEvents()
        self.assertGreater(w.palette.maximumHeight(),195);self.assertGreater(w.palette.height(),250)
        w.insert_search.setText('Separador');self.app.processEvents()
        visible=[w.palette.item(i).text() for i in range(w.palette.count()) if not w.palette.item(i).isHidden()]
        self.assertEqual(visible,['Separador'])

    def test_preferences_search_apply_and_project_settings_undo(self):
        """Globais não sujam o projeto; metadados pertencem ao histórico reversível."""
        from makebench.editor.settings import EditorPreferences,ApplicationSettings,preference
        w=self.window;dialog=EditorPreferences(w);dialog.show();self.app.processEvents();dialog.search.setText('Recuperação');self.app.processEvents();self.assertEqual(dialog.sections.currentRow(),2)
        before=w.history.dirty;original=preference('editor/recovery');dialog.changed('editor/recovery',15);self.assertEqual(w.recovery_timer.interval(),15000);self.assertEqual(w.history.dirty,before);dialog.changed('editor/recovery',original);dialog.close()
        settings=ApplicationSettings(w);settings.change('name','Novo nome público');self.assertEqual(w.project.application['name'],'Novo nome público');self.assertTrue(w.history.dirty);w.undo();self.assertNotIn('name',w.project.application);settings.close()

    def test_recent_project_delete_uses_trash_and_keeps_shared_assets(self):
        """Ação de excluir só move arquivos declarados por padrão, nunca usa rmtree."""
        path=self.root/'project.makebench.json';save_project(Project.empty(),path);own=self.root/'project.actions.py';own.write_text('# preservar na lixeira\n');assets=self.root/'assets';assets.mkdir();image=assets/'shared.png';image.write_bytes(b'preservar')
        targets=[]
        with patch('PySide6.QtCore.QFile.moveToTrash',side_effect=lambda name:targets.append(name) or (True,'lixeira')):
            self.assertTrue(self.window.move_project_to_trash(path))
        self.assertEqual(set(targets),{str(path),str(own)});self.assertTrue(image.exists())

    def test_switch_document_has_no_callback_exception(self):
        """O contexto antigo não é consultado depois que outra raiz foi carregada."""
        import sys
        errors=[]
        with patch.object(sys,'excepthook',side_effect=lambda *value:errors.append(value)):
            self.window._replace_project(Project.empty('Outra raiz'),None);self.app.processEvents()
        self.assertEqual(errors,[])

    def test_image_properties_keep_widgets_and_focus_stable(self):
        """Editar imagem não destrói o inspetor, o frame nem campos a cada valor."""
        from PySide6.QtWidgets import QLineEdit,QSpinBox
        w=self.window;p=Project.empty();p.root.layout=LayoutKind.FREE;image=p.add(p.root.id,ComponentKind.IMAGE);w._replace_project(p,None);w._select(image.id)
        frame=w.canvas._frames[image.id];field=w.inspector.findChild(QLineEdit,'property_alt_text');width=w.inspector.findChild(QSpinBox,'property_geometry.width')
        w._change_property(image.id,'alt_text','Descrição atualizada');w._change_property(image.id,'geometry.width',300)
        self.assertIs(w.canvas._frames[image.id],frame);self.assertIs(w.inspector.findChild(QLineEdit,'property_alt_text'),field);self.assertIs(w.inspector.findChild(QSpinBox,'property_geometry.width'),width)
        self.assertEqual(w.project.find(image.id).geometry['width'],300)

    def test_startup_is_fixed_internal_close_cancel_and_open_same_workspace(self):
        """Iniciador não redimensiona, cancelar não abre bancada e recente não executa fonte."""
        from PySide6.QtCore import QSettings, Qt, QTimer
        from PySide6.QtWidgets import QApplication
        from makebench.editor.startup import StartupDialog
        w=self.window;w.hide();w.settings=QSettings(str(self.root/'settings.ini'),QSettings.Format.IniFormat)
        path=self.root/'project.makebench.json';save_project(Project.empty('Teste inicial'),path)
        marker=self.root/'executado';(self.root/'project.actions.py').write_text(f'open({str(marker)!r}, "w").write("erro")\n')
        w.settings.setValue('projects/recent',[str(path)]);w.startup_dialog=dialog=StartupDialog(w);dialog.show();self.app.processEvents()
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(dialog.minimumSize(),dialog.maximumSize())
        original=dialog.size();dialog.resize(1000,900);self.assertEqual(dialog.size(),original)
        self.assertTrue(dialog.banner.close_button.isVisible());self.assertFalse(w.isVisible())
        dialog.show_at_startup.setChecked(False);self.assertFalse(w.settings.value('v1/projects/startup',True,type=bool))
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName',return_value=('','')):
            dialog.open_button.click()
        self.assertTrue(dialog.isVisible());self.assertFalse(w.isVisible())
        parents=[]
        def cancel_new():
            child=QApplication.activeModalWidget();parents.append(child.parentWidget());child.reject()
        QTimer.singleShot(20,cancel_new);dialog.new_project('blank')
        self.assertEqual(parents,[dialog]);self.assertTrue(dialog.isVisible())
        dialog.open_recent(dialog.recents.item(0));self.app.processEvents()
        self.assertFalse(dialog.isVisible());self.assertTrue(w.isVisible());self.assertEqual(w.path,path)
        self.assertFalse(marker.exists());dialog.deleteLater();del w.startup_dialog

    def test_startup_close_does_not_show_workspace(self):
        """X interno fecha apenas o iniciador; não abre documento ou bancada por efeito colateral."""
        from makebench.editor.startup import StartupDialog
        w=self.window;w.hide();dialog=StartupDialog(w);dialog.show();self.app.processEvents()
        dialog.banner.close_button.click();self.app.processEvents()
        self.assertFalse(dialog.isVisible());self.assertFalse(w.isVisible());dialog.deleteLater()

