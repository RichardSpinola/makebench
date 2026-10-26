# SPDX-License-Identifier: GPL-3.0-or-later
"""The complete workshop examples open, validate, generate Python and run."""

import os
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from makebench.core.codegen import generate
from makebench.core.project import ComponentKind
from makebench.core.source import SourceBuffer
from makebench.core.storage import load_project
from makebench.runtime.window import RuntimeWindow

ROOT = Path(__file__).resolve().parents[1] / "examples"
PATHS = [
    ROOT / name / folder / "project.makebench.json"
    for name in ("", "en")
    for folder in ("full-nodes", "full-blocks")
]


class FullExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_component_kind_is_used(self):
        for path in PATHS:
            with self.subTest(path=str(path)):
                project = load_project(path)
                used = {node.kind for node in project.walk()}
                self.assertFalse(set(ComponentKind) - used - {ComponentKind.WINDOW})

    def test_generated_python_compiles_without_diagnostics(self):
        for path in PATHS:
            with self.subTest(path=str(path)):
                project = load_project(path)
                code = generate(project, SourceBuffer.load(path).text)
                self.assertEqual(code.diagnostics, [])
                compile(code.text, str(path), "exec")

    def test_windows_have_their_own_look_and_a_state(self):
        project = load_project(PATHS[0])
        self.assertGreaterEqual(len(project.windows), 2)
        looks = {
            w.properties.get("theme") or w.properties.get("background") for w in project.windows
        }
        self.assertGreaterEqual(len(looks), 2)
        self.assertTrue(project.states)

    def test_greeting_runs_in_every_example(self):
        for path in PATHS:
            with self.subTest(path=str(path)):
                project = load_project(path)
                source = SourceBuffer.load(path).text
                window = RuntimeWindow(
                    project, source, lambda p: b"", path.parent, path.parent / "x.py"
                )
                window.show()
                try:
                    window.start()
                    self.wait(lambda: window.session.active and not window.session.busy)
                    button = next(
                        n for n in project.walk() if n.properties.get("code_name") == "greet_button"
                    )
                    window.view.widgets[button.id].click()
                    self.wait(lambda: not window.session.busy)
                    self.assertFalse(window.last_error)
                finally:
                    window.stop()
                    self.wait(lambda: window.session.closed)
                    window.close()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def wait(self, predicate, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline and not predicate():
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())


if __name__ == "__main__":
    unittest.main()
