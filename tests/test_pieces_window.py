# SPDX-License-Identifier: GPL-3.0-or-later
"""The Insert piece menu in the main window, headless."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from makebench.core import pieces
from makebench.core.project import ComponentKind
from makebench.editor import pieces as ui
from makebench.editor.window import MainWindow


class PiecesWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {"XDG_DATA_HOME": str(Path(self.directory.name) / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.window = MainWindow()
        self.addCleanup(self._close)

    def _close(self):
        self.window._finish_field_edit()
        self.window.history.mark_saved()
        self.window.close()
        self.window.deleteLater()

    def test_insert_builtin_piece_is_one_undo_step(self):
        before = len(list(self.window.project.root.walk()))
        ui.insert(self.window, pieces.builtin_pieces()[0])
        self.assertGreater(len(list(self.window.project.root.walk())), before)
        self.window.undo()
        self.assertEqual(len(list(self.window.project.root.walk())), before)

    def test_save_selection_then_menu_lists_it(self):
        box = self.window.project.add(self.window.project.root.id, ComponentKind.CONTAINER)
        self.window.selected_id = box.id
        with patch.object(ui.QInputDialog, "getText", return_value=("Box", True)):
            ui.save_selection_as_piece(self.window)
        names = [action.text() for action in self.window.pieces_menu.actions()]
        self.assertIn("Box", names)


if __name__ == "__main__":
    unittest.main()
