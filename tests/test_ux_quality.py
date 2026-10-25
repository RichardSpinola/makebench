"""Usability guarantees: unique shortcuts, named controls and readable errors."""

import errno
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton, QApplication

from makebench.core.navigation import welcome_template
from makebench.core.project import ProjectError
from makebench.editor.errors import describe
from makebench.editor.window import MainWindow


class UxQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(welcome_template())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_every_shortcut_belongs_to_a_single_action(self):
        """Two actions on the same key make Qt fire neither of them."""
        owners = {}
        for action in self.window.findChildren(QAction):
            for sequence in action.shortcuts():
                key = sequence.toString()
                if key:
                    owners.setdefault(key, set()).add(action.text().replace("&", ""))
        clashes = {key: names for key, names in owners.items() if len(names) > 1}
        self.assertEqual(clashes, {})
        self.assertEqual(self.window.debug_action.shortcut().toString(), "F9")

    def test_buttons_have_a_visible_or_accessible_name(self):
        """Icon-only buttons must still be announced by screen readers."""
        from makebench.editor.settings import ApplicationSettings, EditorPreferences

        for mode in ("map", "design", "code"):
            self.window.set_mode(mode)
        dialogs = [EditorPreferences(self.window), ApplicationSettings(self.window)]
        for dialog in dialogs:
            dialog.show()
        self.app.processEvents()
        unnamed = []
        for root in [self.window, *dialogs]:
            for button in root.findChildren(QAbstractButton):
                if not (button.text().strip("…+ ") or button.accessibleName() or button.toolTip()):
                    unnamed.append(f"{type(root).__name__}: {type(button.parent()).__name__}")
        for dialog in dialogs:
            dialog.close()
        self.assertEqual(unnamed, [])

    def test_undo_names_the_change_it_reverts(self):
        from makebench.core.project import ComponentKind

        self.window.set_mode("design")
        self.window.palette.setCurrentRow(self.window.palette.findData(ComponentKind.BUTTON.value))
        self.window.add_component()
        self.app.processEvents()
        self.assertEqual(self.window.undo_action.text(), "Undo: Add component")
        self.window.undo()
        self.app.processEvents()
        self.assertEqual(self.window.redo_action.text(), "Redo: Add component")

    def test_project_search_finds_every_file_and_opens_the_line(self):
        """Ctrl+Shift+F searches the in-memory entry file and modules, then navigates."""
        from makebench.editor.project_search import search_sources

        self.window.add_code_module(
            "makebench_user/tools.py", "def helper():\n    return 'needle'\n"
        )
        self.window.source_editor.setPlainText("# needle in the entry file\nprint('NEEDLE')\n")
        found = search_sources(self.window.source.text, "needle")
        self.assertEqual(
            sorted((name, line) for name, line, _, _ in found),
            [("@actions", 1), ("@actions", 2), ("makebench_user/tools.py", 2)],
        )
        self.assertEqual(len(search_sources(self.window.source.text, "needle", True)), 2)
        self.window.project_search_action.trigger()
        panel = self.window.project_search
        panel.query.setText("helper")
        panel.run()
        self.assertEqual(panel.results.count(), 1)
        panel.open_first()
        self.app.processEvents()
        self.assertEqual(self.window.current_code_file(), "makebench_user/tools.py")

    def test_system_errors_are_explained_with_details_kept(self):
        summary, details = describe(PermissionError(errno.EACCES, "Permission denied", "/x/a.json"))
        self.assertEqual(summary, "You do not have permission to use /x/a.json.")
        self.assertIn("Errno 13", details)
        summary, details = describe(OSError(errno.ENOSPC, "No space left on device"))
        self.assertEqual(summary, "There is no free space left on the disk.")
        self.assertEqual(describe(ProjectError("Already clear.")), ("Already clear.", ""))
        summary, details = describe(KeyError("surprise"))
        self.assertTrue(summary.startswith("Unexpected error"))
        self.assertIn("KeyError", details)


if __name__ == "__main__":
    unittest.main()
