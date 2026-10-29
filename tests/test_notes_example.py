# SPDX-License-Identifier: GPL-3.0-or-later
"""The "My notes" example saves a note through its blocks and shows it in the table."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from makebench.core.codegen import generate
from makebench.core.source import SourceBuffer
from makebench.core.storage import load_project
from makebench.runtime.window import RuntimeWindow

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class NotesExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, predicate, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline and not predicate():
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def settle(self, seconds=0.3):
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.01)

    def test_adding_notes_fills_the_table_and_an_empty_title_is_refused(self):
        for base in (EXAMPLES, EXAMPLES / "en"):
            with self.subTest(str(base)), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "my-notes"
                shutil.copytree(base / "my-notes", folder)
                path = folder / "project.makebench.json"
                project = load_project(path)
                project.application["id"] = "org.makebench.test." + base.name + "notes"
                source = SourceBuffer.load(path).text
                self.assertEqual(generate(project, source).diagnostics, [])
                window = RuntimeWindow(
                    project, source, lambda p: b"", folder, folder / "x.py", supervision=False
                )
                window.show()
                try:
                    window.start()
                    self.wait(lambda: window.session.active and not window.session.busy)
                    ids = {n.properties.get("code_name"): n.id for n in project.walk()}
                    widgets = window.view.widgets
                    table = widgets[ids["notes_table"]]
                    widgets[ids["add_button"]].click()
                    self.wait(lambda: not window.session.busy)
                    self.assertEqual(table.rowCount(), 0)
                    for text in ("one", "two"):
                        widgets[ids["title_input"]].setText(text)
                        widgets[ids["text_input"]].setPlainText("body " + text)
                        self.settle()  # the worker learns typed values through events
                        widgets[ids["add_button"]].click()
                        self.wait(lambda n=table.rowCount(): table.rowCount() > n)
                        self.assertFalse(window.last_error, window.last_error)
                    self.assertEqual(table.rowCount(), 2)
                    self.assertEqual(table.text(0, 0), "one")
                    self.assertEqual(widgets[ids["title_input"]].text(), "")
                    self.assertFalse(window.last_error)
                finally:
                    window.stop()
                    self.wait(lambda: window.session.closed)
                    window.close()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
