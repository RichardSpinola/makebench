# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Bookshop" example records a sale, lowers the stock and marks the sale delivered."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import shutil
import sys
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

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(ROOT / "checks"))
from build_bookshop_example import TEXT as BOOKSHOP_TEXT  # noqa: E402


class BookshopExampleTests(unittest.TestCase):
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

    def test_sale_lowers_stock_fills_cash_and_can_be_delivered(self):
        for base, language in ((EXAMPLES, "pt"), (EXAMPLES / "en", "en")):
            words = BOOKSHOP_TEXT[language]
            with self.subTest(str(base)), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "bookshop"
                shutil.copytree(base / "bookshop", folder)
                path = folder / "project.makebench.json"
                project = load_project(path)
                project.application["id"] = "org.makebench.test." + base.name + "bookshop"
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
                    w = {code: window.view.widgets[node] for code, node in ids.items() if code}

                    def click(name):
                        self.settle()  # the worker learns typed values through events
                        w[name].click()
                        self.settle()
                        self.wait(lambda: not window.session.busy)
                        self.assertFalse(window.last_error, window.last_error)

                    w["title_input"].setText("Dom Casmurro")
                    w["price_input"].setValue(12.5)
                    w["stock_input"].setValue(3)
                    click("add_book_button")
                    w["name_input"].setText("Ana")
                    click("add_client_button")
                    self.assertEqual(w["books_table"].rowCount(), 1)
                    w["client_choice"].setCurrentIndex(0)
                    w["book_choice"].setCurrentIndex(0)
                    w["quantity_input"].setValue(2)
                    click("sell_button")
                    self.assertEqual(w["sales_table"].rowCount(), 1)
                    self.assertEqual(w["books_table"].text(0, 2), "1")
                    self.assertIn("25", w["cash_label"].text())
                    click("sell_button")  # only one book left
                    self.assertEqual(w["sales_table"].rowCount(), 1)
                    self.assertEqual(w["status"].text(), words["no_stock"])
                    undelivered = w["sales_table"].text(0, 4)
                    click("deliver_button")  # nothing selected yet
                    self.assertEqual(w["status"].text(), words["need_sale"])
                    w["sales_table"].selectRow(0)
                    click("deliver_button")
                    self.assertEqual(w["status"].text(), words["delivered"])
                    self.assertNotEqual(w["sales_table"].text(0, 4), undelivered)
                finally:
                    window.stop()
                    self.wait(lambda: window.session.closed)
                    window.close()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
