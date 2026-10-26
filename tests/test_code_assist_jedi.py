# SPDX-License-Identifier: GPL-3.0-or-later
"""Jedi suggestions and F12 through the real code editor, headless."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from makebench.editor import jedi_assist
from makebench.editor.window import MainWindow


@unittest.skipUnless(jedi_assist.available(), "jedi is not installed")
class CodeAssistJediTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.addCleanup(self._close)

    def _close(self):
        self.window._finish_field_edit()
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()

    def test_ctx_suggestions_have_details_and_snippets(self):
        w = self.window
        editor = w.source_editor
        editor.setPlainText("def action(ctx, value):\n    ctx.set_")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        popup = w._entry_assist.popup
        labels = [popup.item(i).text() for i in range(popup.count())]
        self.assertTrue(any(label.startswith("set_text") for label in labels))
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertIn("ctx.set_", editor.toPlainText())
        self.assertNotIn("ctx.ctx", editor.toPlainText())

    def test_f12_follows_a_module_function(self):
        w = self.window
        w.add_code_module(
            "makebench_user/helpers.py", "def calculate(value):\n    return value + 1\n"
        )
        editor = w.source_editor
        editor.setPlainText("from makebench_user import helpers\nhelpers.calculate(1)\n")
        cursor = editor.textCursor()
        cursor.setPosition(len("from makebench_user import helpers\nhelpers.calc"))
        editor.setTextCursor(cursor)
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_F12)
        self.assertIs(w.active_code_editor(), w.module_editors["makebench_user/helpers.py"])


if __name__ == "__main__":
    unittest.main()
