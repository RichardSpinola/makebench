"""Aceitação Qt: tema nativo, navegação, início, campos e preferências."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from makebench.core.project import Project, ComponentKind, LayoutKind
from makebench.core.storage import save_project


class NativeQtInterfaceTests(unittest.TestCase):
    """Regressões visuais funcionais do editor Qt e da tela inicial."""

    @classmethod
    def setUpClass(cls):
        """Aplicação offscreen mantém estilo Qt padrão para não depender do KDE real."""
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        """Isola arquivos e preferências dos testes de ações da tela inicial."""
        from makebench.editor.window import MainWindow

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.window = MainWindow()
        self.window.recovery_timer.stop()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        """Não deixa diálogos abertos nem ativa confirmação de descarte no fim do teste."""
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_native_theme_and_stable_navigation_without_global_qss(self):
        """A barra não some no mapa, publicar ou início; não há stylesheet global."""
        w = self.window
        for mode in ("Design", "Mapa", "Publicar", "Código", "Lógica"):
            if mode == "Lógica":
                continue  # WebEngine é exercitado na integração separada.
            w.set_mode(mode)
            self.app.processEvents()
            self.assertTrue(w.workspace_toolbar.isVisible())
            self.assertTrue(all(b.isVisible() for b in w.mode_buttons.values()))
        w.show_home()
        self.assertTrue(w.workspace_toolbar.isVisible())
        self.assertEqual(self.app.styleSheet(), "")

    def test_insert_library_uses_vertical_space_and_has_search(self):
        """Biblioteca não mantém limite de 195 px nem rótulo expandido acima da lista."""
        w = self.window
        w.left_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertGreater(w.palette.maximumHeight(), 195)
        self.assertGreater(w.palette.height(), 250)
        w.insert_search.setText("Separador")
        self.app.processEvents()
        visible = [
            w.palette.item(i).text()
            for i in range(w.palette.count())
            if not w.palette.item(i).isHidden()
        ]
        self.assertEqual(visible, ["Separador"])

    def test_preferences_search_apply_and_project_settings_undo(self):
        """Globais não sujam o projeto; metadados pertencem ao histórico reversível."""
        from makebench.editor.settings import EditorPreferences, ApplicationSettings, preference

        w = self.window
        dialog = EditorPreferences(w)
        dialog.show()
        self.app.processEvents()
        dialog.search.setText("Recuperação")
        self.app.processEvents()
        self.assertEqual(dialog.sections.currentRow(), 2)
        before = w.history.dirty
        original = preference("editor/recovery")
        dialog.changed("editor/recovery", 15)
        self.assertEqual(w.recovery_timer.interval(), 15000)
        self.assertEqual(w.history.dirty, before)
        dialog.changed("editor/recovery", original)
        dialog.close()
        settings = ApplicationSettings(w)
        settings.change("name", "Novo nome público")
        self.assertEqual(w.project.application["name"], "Novo nome público")
        self.assertTrue(w.history.dirty)
        w.undo()
        self.assertNotIn("name", w.project.application)
        settings.close()

    def test_recent_project_delete_uses_trash_and_keeps_shared_assets(self):
        """Ação de excluir só move arquivos declarados por padrão, nunca usa rmtree."""
        path = self.root / "project.makebench.json"
        save_project(Project.empty(), path)
        own = self.root / "project.actions.py"
        own.write_text("# preservar na lixeira\n")
        assets = self.root / "assets"
        assets.mkdir()
        image = assets / "shared.png"
        image.write_bytes(b"preservar")
        targets = []
        with patch(
            "PySide6.QtCore.QFile.moveToTrash",
            side_effect=lambda name: targets.append(name) or (True, "lixeira"),
        ):
            self.assertTrue(self.window.move_project_to_trash(path))
        self.assertEqual(set(targets), {str(path), str(own)})
        self.assertTrue(image.exists())

    def test_switch_document_has_no_callback_exception(self):
        """O contexto antigo não é consultado depois que outra raiz foi carregada."""
        import sys

        errors = []
        with patch.object(sys, "excepthook", side_effect=lambda *value: errors.append(value)):
            self.window._replace_project(Project.empty("Outra raiz"), None)
            self.app.processEvents()
        self.assertEqual(errors, [])

    def test_image_properties_keep_widgets_and_focus_stable(self):
        """Editar imagem não destrói o inspetor, o frame nem campos a cada valor."""
        from PySide6.QtWidgets import QLineEdit, QSpinBox

        w = self.window
        p = Project.empty()
        p.root.layout = LayoutKind.FREE
        image = p.add(p.root.id, ComponentKind.IMAGE)
        w._replace_project(p, None)
        w._select(image.id)
        frame = w.canvas._frames[image.id]
        field = w.inspector.findChild(QLineEdit, "property_alt_text")
        width = w.inspector.findChild(QSpinBox, "property_geometry.width")
        w._change_property(image.id, "alt_text", "Descrição atualizada")
        w._change_property(image.id, "geometry.width", 300)
        self.assertIs(w.canvas._frames[image.id], frame)
        self.assertIs(w.inspector.findChild(QLineEdit, "property_alt_text"), field)
        self.assertIs(w.inspector.findChild(QSpinBox, "property_geometry.width"), width)
        self.assertEqual(w.project.find(image.id).geometry["width"], 300)

    def test_startup_is_fixed_internal_close_cancel_and_open_same_workspace(self):
        """Iniciador não redimensiona, cancelar não abre bancada e recente não executa fonte."""
        from PySide6.QtCore import QSettings, Qt, QTimer
        from PySide6.QtWidgets import QApplication
        from makebench.editor.startup import StartupDialog

        w = self.window
        w.hide()
        w.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        path = self.root / "project.makebench.json"
        save_project(Project.empty("Teste inicial"), path)
        marker = self.root / "executado"
        (self.root / "project.actions.py").write_text(f'open({str(marker)!r}, "w").write("erro")\n')
        w.settings.setValue("projects/recent", [str(path)])
        w.startup_dialog = dialog = StartupDialog(w)
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        original = dialog.size()
        dialog.resize(1000, 900)
        self.assertEqual(dialog.size(), original)
        self.assertTrue(dialog.banner.close_button.isVisible())
        self.assertFalse(w.isVisible())
        dialog.show_at_startup.setChecked(False)
        self.assertFalse(w.settings.value("v1/projects/startup", True, type=bool))
        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")):
            dialog.open_button.click()
        self.assertTrue(dialog.isVisible())
        self.assertFalse(w.isVisible())
        parents = []

        def cancel_new():
            child = QApplication.activeModalWidget()
            parents.append(child.parentWidget())
            child.reject()

        QTimer.singleShot(20, cancel_new)
        dialog.new_project("blank")
        self.assertEqual(parents, [dialog])
        self.assertTrue(dialog.isVisible())
        dialog.open_recent(dialog.recents.item(0))
        self.app.processEvents()
        self.assertFalse(dialog.isVisible())
        self.assertTrue(w.isVisible())
        self.assertEqual(w.path, path)
        self.assertFalse(marker.exists())
        dialog.deleteLater()
        del w.startup_dialog

    def test_startup_close_does_not_show_workspace(self):
        """X interno fecha apenas o iniciador; não abre documento ou bancada por efeito colateral."""
        from makebench.editor.startup import StartupDialog

        w = self.window
        w.hide()
        dialog = StartupDialog(w)
        dialog.show()
        self.app.processEvents()
        dialog.banner.close_button.click()
        self.app.processEvents()
        self.assertFalse(dialog.isVisible())
        self.assertFalse(w.isVisible())
        dialog.deleteLater()

    def test_reselect_preserves_inspector_canvas_and_diagnostic_items(self):
        """Cliques repetidos não reconstroem os campos, os frames nem a lista de problemas."""
        from PySide6.QtWidgets import QLineEdit

        w = self.window
        p = Project.empty()
        text = p.add(p.root.id, ComponentKind.LABEL)
        w._replace_project(p, None)
        w._select(text.id)
        field = w.inspector.findChild(QLineEdit, "property_text")
        frame = w.canvas._frames[text.id]
        problem = w.problems.item(0)
        with patch.object(w.inspector, "clear", wraps=w.inspector.clear) as clear:
            w._select(text.id)
            w.select_multiple([text.id])
            self.app.processEvents()
            clear.assert_not_called()
        self.assertIs(w.inspector.findChild(QLineEdit, "property_text"), field)
        self.assertIs(w.canvas._frames[text.id], frame)
        self.assertIs(w.problems.item(0), problem)

    def test_insert_repaints_only_after_complete_refresh_and_keeps_native_window(self):
        """Qt não recebe uma bancada parcialmente vazia durante a reconstrução."""
        w = self.window
        native = w.winId()
        states = []
        original = w.canvas.set_project

        def rebuild(project):
            original(project)
            self.app.processEvents()
            states.append((w.updatesEnabled(), w.canvas.updatesEnabled()))

        with patch.object(w.canvas, "set_project", side_effect=rebuild):
            w.palette.setCurrentRow(w.palette.findData("label"))
            w.add_component()
        self.assertEqual(states, [(False, False)])
        self.assertTrue(w.updatesEnabled())
        self.assertTrue(w.canvas.updatesEnabled())
        self.assertEqual(w.winId(), native)
        self.assertEqual(w.project.find(w.selected_id).kind, ComponentKind.LABEL)

    def test_map_empty_hint_survives_click_zoom_and_node_click_is_not_edit(self):
        """Orientação não é um item arrastável; selecionar nó não salva posições por engano."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        w = self.window
        p = Project.empty()
        p.metadata["empty_map"] = True
        w._replace_project(p, None)
        w.set_mode("Mapa")
        self.app.processEvents()
        panel = w.map_panel
        hint = panel.view.empty_hint
        history = w.history._index
        size = hint.size()
        QTest.mouseClick(
            panel.view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=panel.view.viewport().rect().center(),
        )
        QTest.qWait(10)
        panel.view.scale(2, 2)
        self.app.processEvents()
        self.assertTrue(hint.isVisible())
        self.assertEqual(hint.size(), size)
        self.assertEqual(w.history._index, history)
        w._replace_project(Project.empty(), None)
        w.set_mode("Mapa")
        self.app.processEvents()
        panel.fit()
        node = next(iter(panel.nodes.values()))
        history = w.history._index
        point = panel.view.mapFromScene(node.mapToScene(node.rect().center()))
        QTest.mouseClick(panel.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(10)
        self.assertEqual(w.history._index, history)
        self.assertIs(next(iter(panel.nodes.values())), node)

    def test_application_settings_and_nonvisual_preferences_keep_preview_widgets(self):
        """Metadados e preferências sem efeito visual não refazem o canvas nem o tema."""
        from PySide6.QtTest import QSignalSpy
        from makebench.editor.settings import ApplicationSettings, EditorPreferences, preference
        from makebench.editor.theme import manager

        w = self.window
        frame = w.canvas._frames[w.project.root.id]
        settings = ApplicationSettings(w)
        with patch.object(w.canvas, "set_project", wraps=w.canvas.set_project) as rebuild:
            settings.change("description", "Configuração sem piscada")
            settings.close()
            self.app.processEvents()
            rebuild.assert_not_called()
        self.assertIs(w.canvas._frames[w.project.root.id], frame)
        prefs = EditorPreferences(w)
        signals = QSignalSpy(manager().changed)
        original = preference("editor/recovery")
        prefs.changed("editor/recovery", 15 if original != 15 else 30)
        prefs.changed("editor/recovery", original)
        self.assertEqual(signals.count(), 0)
        prefs.close()

    def test_visibility_and_enabled_properties_survive_rebuild(self):
        """Os controles reais refletem os valores agora e depois de reconstruir a prévia."""
        from PySide6.QtWidgets import QCheckBox

        w = self.window
        p = Project.empty()
        button = p.add(p.root.id, ComponentKind.BUTTON)
        w._replace_project(p, None)
        w._select(button.id)
        visible = next(
            field
            for field in w.inspector.findChildren(QCheckBox)
            if field.accessibleName() == "Visível"
        )
        visible.click()
        self.assertTrue(w.canvas._frames[button.id].isHidden())
        w._refresh()
        self.assertTrue(w.canvas._frames[button.id].isHidden())
        w._change_property(button.id, "visible", True)
        w._change_property(button.id, "enabled", False)
        widget = w.canvas._frames[button.id].layout().itemAt(0).widget()
        self.assertFalse(widget.isEnabled())
        w._refresh()
        widget = w.canvas._frames[button.id].layout().itemAt(0).widget()
        self.assertFalse(widget.isEnabled())

    def test_new_project_starts_empty_and_opens_first_interface_by_double_click(self):
        """Criação configura identidade, mapa vazio e entrada explícita no Designer."""
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtWidgets import QApplication, QLineEdit, QComboBox, QDialogButtonBox
        from PySide6.QtTest import QTest
        from makebench.core.exporter import verify

        w = self.window

        def create_project():
            dialog = QApplication.activeModalWidget()
            for key, value in [
                ("new_application_name", "Aplicativo QA"),
                ("new_project_folder", str(self.root / "novo")),
                ("new_application_id", "br.exemplo.qa"),
                ("new_application_version", "0.2.0"),
            ]:
                dialog.findChild(QLineEdit, key).setText(value)
            backend = dialog.findChild(QComboBox, "new_application_backend")
            backend.setCurrentIndex(backend.findData("qt"))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()

        QTimer.singleShot(30, create_project)
        w.new_project_dialog("blank")
        self.app.processEvents()
        self.assertTrue(w.project.metadata["empty_map"])
        self.assertEqual(w.project.application["id"], "br.exemplo.qa")
        self.assertEqual(w.project.application["version"], "0.2.0")
        self.assertEqual(w.map_panel.nodes, {})
        self.assertFalse(w.mode_buttons["Design"].isEnabled())
        w.set_mode("Código")
        self.assertTrue(w.map_panel.isVisible())
        self.assertTrue(
            any(
                i["field"] == "windows" and i["level"] == "error"
                for i in verify(w.project, "", lambda _: b"")
            )
        )

        def create_interface():
            dialog = QApplication.activeModalWidget()
            dialog.findChild(QLineEdit, "new_interface_name").setText("Tela principal")
            dialog.accept()

        QTimer.singleShot(30, create_interface)
        w.new_window_dialog()
        self.app.processEvents()
        self.assertFalse(w.project.metadata.get("empty_map"))
        self.assertEqual(len(w.project.roots), 1)
        self.assertTrue(w.mode_buttons["Design"].isEnabled())
        node = next(iter(w.map_panel.nodes.values()))
        point = w.map_panel.view.mapFromScene(node.sceneBoundingRect().center())
        QTest.mouseDClick(w.map_panel.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(20)
        self.assertEqual(w.active_window, w.project.root.id)
        self.assertTrue(w.zoom_view.isVisible())

    def test_code_find_is_local_wraps_and_keeps_source_unchanged(self):
        """Busca não modal funciona em código próprio e gerado, com ida/volta e Escape."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        from makebench.editor.code import CodeEditor

        editor = CodeEditor()
        editor.setPlainText("alpha = 1\nbeta = alpha + 1\n")
        editor.resize(600, 300)
        editor.show()
        editor.moveCursor(QTextCursor.MoveOperation.Start)
        original = editor.toPlainText()
        editor.open_find()
        editor.find_text.setText("alpha")
        editor.find_next()
        first = editor.textCursor().selectionStart()
        editor.find_next()
        second = editor.textCursor().selectionStart()
        self.assertGreater(second, first)
        editor.find_next()
        self.assertEqual(editor.textCursor().selectionStart(), first)
        editor.find_next(True)
        self.assertEqual(editor.textCursor().selectionStart(), second)
        editor.find_text.setText("ausente")
        editor.find_next()
        self.assertEqual(editor.find_status.text(), "Nenhum resultado")
        QTest.keyClick(editor.find_text, Qt.Key.Key_Escape)
        self.assertTrue(editor.find_bar.isHidden())
        self.assertEqual(editor.toPlainText(), original)
        editor.close()

    def test_native_header_keeps_system_text_legible(self):
        """Paleta de cabeçalho errada não deixa o menu invisível no tema do desktop."""
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QMenuBar
        from makebench.ui.theme import manager, contrast

        manager()
        bar = QMenuBar()
        palette = QPalette(self.app.palette())
        palette.setColor(QPalette.ColorRole.Window, self.app.palette().window().color())
        palette.setColor(QPalette.ColorRole.WindowText, self.app.palette().window().color())
        bar.setPalette(palette)
        manager().repair_bar_palette(bar)
        self.app.processEvents()
        self.assertGreaterEqual(
            contrast(
                bar.palette().windowText().color().name(), bar.palette().window().color().name()
            ),
            4.5,
        )
        bar.deleteLater()

    def test_export_opens_separate_fixed_dialog_and_preserves_editor(self):
        """Exportar abre uma única janela compacta e mantém seleção, modo e canvas."""
        w = self.window
        w.set_mode("Design")
        selected = w.selected_id
        native = w.winId()
        canvas = w.canvas
        mode = w.tabs.currentIndex()
        self.assertEqual(w.tabs.count(), 4)
        self.assertNotIn("Publicar", w.mode_buttons)
        w.export_action.trigger()
        self.app.processEvents()
        dialog = w.publish_dialog
        self.assertTrue(dialog.isVisible())
        self.assertIs(w.publish_panel.parentWidget(), dialog)
        self.assertEqual(w.tabs.currentIndex(), mode)
        self.assertIs(w.canvas, canvas)
        self.assertEqual(w.selected_id, selected)
        self.assertEqual(w.winId(), native)
        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        dialog.close()
        self.app.processEvents()
        self.assertFalse(dialog.isVisible())
        self.assertTrue(w.isVisible())
        w.export_action.trigger()
        self.app.processEvents()
        self.assertIs(w.publish_dialog, dialog)
        dialog.hide()
