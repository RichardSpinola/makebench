# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Qt editor flows in a headless environment, with no interface mocks."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from makebench.core.project import ComponentKind, LayoutKind, Project
from makebench.core.storage import load_project, save_project
from makebench.editor.window import MainWindow


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "interface.makebench.json"
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._finish_field_edit()
        self.window.history.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def add(self, kind):
        self.window.palette.setCurrentRow(self.window.palette.findData(kind.value))
        self.window.add_component()
        self.app.processEvents()
        return self.window.project.find(self.window.selected_id)

    def test_create_edit_save_reopen_and_undo(self):
        button = self.add(ComponentKind.BUTTON)
        field = self.window.inspector.findChild(QLineEdit, "property_text")
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "Run task")
        QTest.keyClick(field, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.project.find(button.id).properties["text"], "Run task")
        self.assertTrue(self.window.save_to(self.path))
        self.assertFalse(self.window.history.dirty)

        self.window.new_project()
        self.assertEqual(len(self.window.project.root.children), 0)
        with patch(
            "makebench.editor.window.QFileDialog.getOpenFileName", return_value=(str(self.path), "")
        ):
            self.window.open_project()
        self.assertEqual(self.window.project.find(button.id).properties["text"], "Run task")
        self.window._select(button.id)
        self.window.remove_component()
        self.assertIsNone(self.window.project.find(button.id))
        self.window.undo()
        self.assertIsNotNone(self.window.project.find(button.id))
        self.assertFalse(self.window.history.dirty)

    def test_saving_commits_text_still_being_edited(self):
        button = self.add(ComponentKind.BUTTON)
        field = self.window.inspector.findChild(QLineEdit, "property_text")
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "Texto nao confirmado")
        self.assertTrue(self.window.save_to(self.path))
        self.assertEqual(
            load_project(self.path).find(button.id).properties["text"], "Texto nao confirmado"
        )

    def test_canceling_unsaved_changes_keeps_the_document(self):
        button = self.add(ComponentKind.BUTTON)
        with patch(
            "makebench.editor.window.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Cancel,
        ):
            self.window.new_project()
        self.assertIsNotNone(self.window.project.find(button.id))
        self.assertTrue(self.window.history.dirty)

    def test_failed_save_retains_dirty_state_and_original_path(self):
        self.add(ComponentKind.BUTTON)
        with patch.object(self.window, "_show_error") as show_error:
            self.assertFalse(self.window.save_to(self.path / "missing" / "new.makebench.json"))
        show_error.assert_called_once()
        self.assertIsNone(self.window.path)
        self.assertTrue(self.window.history.dirty)

    def test_corrupt_open_does_not_replace_current_document(self):
        original_id = self.window.project.id
        self.path.write_text("broken", encoding="utf-8")
        with patch(
            "makebench.editor.window.QFileDialog.getOpenFileName", return_value=(str(self.path), "")
        ):
            with patch.object(self.window, "_show_error") as show_error:
                self.window.open_project()
        show_error.assert_called_once()
        self.assertEqual(self.window.project.id, original_id)

    def test_all_components_and_layout_modes_render_after_reload(self):
        project = Project.empty("Galeria")
        for mode in LayoutKind:
            group = project.add(project.root.id, ComponentKind.CONTAINER)
            group.layout = mode
            for kind in ComponentKind:
                if kind not in (ComponentKind.WINDOW, ComponentKind.CONTAINER, ComponentKind.PAGE):
                    project.add(group.id, kind)
        save_project(project, self.path)
        self.window._replace_project(load_project(self.path), self.path)
        self.app.processEvents()
        self.assertEqual(len(self.window.canvas._frames), len(list(project.root.walk())))

    def test_free_layout_keeps_offscreen_components_reachable_by_scrolling(self):
        project = Project.empty()
        project.root.layout = LayoutKind.FREE
        button = project.add(project.root.id, ComponentKind.BUTTON)
        button.geometry.update(x=1200, y=900)
        self.window._replace_project(project, None)
        self.app.processEvents()
        surface = self.window.canvas._frames[project.root.id]
        self.assertGreaterEqual(surface.minimumWidth(), 1200 + button.geometry["width"])
        self.assertGreaterEqual(surface.minimumHeight(), 900 + button.geometry["height"])

    def test_format_upgrade_message_names_the_real_backup(self):
        """Saving a format 1 project reports the new format and the .bak-v1 copy created."""
        example = (
            Path(__file__).resolve().parents[1] / "examples/script-center/project.makebench.json"
        )
        self.path.write_bytes(example.read_bytes())
        self.window._replace_project(load_project(self.path), self.path)
        self.window.project.application["name"] = "Atualizado"
        self.assertTrue(self.window.save_to(self.path))
        message = self.window.statusBar().currentMessage()
        self.assertIn("format 5", message)
        self.assertIn(self.path.name + ".bak-v1", message)

    def test_editor_save_keeps_untouched_json_and_commits_modules_last(self):
        """Saving from the window uses the shared path: JSON untouched without edits and modules in the manifest."""
        example = (
            Path(__file__).resolve().parents[1] / "examples/script-center/project.makebench.json"
        )
        self.path.write_bytes(example.read_bytes())
        self.window._replace_project(load_project(self.path), self.path)
        self.window.source_editor.setPlainText("def ola(ctx):\n    return 1\n")
        self.assertTrue(self.window.save())
        self.assertEqual(self.path.read_bytes(), example.read_bytes())
        actions = self.path.with_name("interface.actions.py")
        self.assertEqual(actions.read_text(encoding="utf-8"), "def ola(ctx):\n    return 1\n")
        self.window.source.add_module("makebench_user/ajuda.py", "VALOR = 1\n")
        self.assertTrue(self.window.save())
        module = self.path.parent / "makebench_user/ajuda.py"
        self.assertEqual(module.read_text(encoding="utf-8"), "VALOR = 1\n")
        self.assertIn("makebench_user/ajuda.py", load_project(self.path).python_files)
        self.window.source.remove_module("makebench_user/ajuda.py")
        self.assertTrue(module.exists())
        self.assertTrue(self.window.save())
        self.assertFalse(module.exists())
        self.assertNotIn("makebench_user/ajuda.py", load_project(self.path).python_files)
        self.assertFalse(self.window.source.dirty or self.window.history.dirty)

    def test_blank_project_name_is_reverted_before_saving(self):
        original_name = self.window.project.name
        field = self.window.inspector.findChild(QLineEdit, "property_name")
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "   ")
        self.assertTrue(self.window.save_to(self.path))
        self.assertEqual(load_project(self.path).name, original_name)
        self.assertEqual(
            self.window.inspector.findChild(QLineEdit, "property_name").text(),
            original_name,
        )


if __name__ == "__main__":
    unittest.main()
