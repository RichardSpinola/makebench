# SPDX-License-Identifier: GPL-3.0-or-later
"""The version history window and the record-on-save hook, headless."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox

from makebench.core import vcs
from makebench.core.project import ComponentKind
from makebench.editor.history_panel import HistoryDialog
from makebench.editor.window import MainWindow


@unittest.skipUnless(vcs.available(), "git is not installed")
class HistoryPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.env = patch.dict(
            os.environ,
            {
                "HOME": str(base),
                "GIT_CONFIG_GLOBAL": str(base / "gc"),
                "GIT_CONFIG_SYSTEM": os.devnull,
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.path = base / "app" / "app.makebench.json"
        self.path.parent.mkdir()
        self.window = MainWindow()
        self.window.show()
        self.addCleanup(self._close)

    def _close(self):
        QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents()
        self.window._finish_field_edit()
        self.window.history.mark_saved()
        self.window.close()
        self.window.deleteLater()

    def wait_for_versions(self, count):
        deadline = time.time() + 10
        while time.time() < deadline:
            self.app.processEvents()
            if len(vcs.log(self.path.parent)) >= count:
                return
            time.sleep(0.05)
        self.fail("versions were not recorded")

    def test_history_is_off_until_asked_and_then_records_every_save(self):
        self.assertTrue(self.window.save_to(self.path))
        self.assertFalse(vcs.is_repo(self.path.parent))
        dialog = HistoryDialog(self.window)
        self.assertFalse(dialog.enable.isHidden())
        vcs.init(self.path.parent)
        vcs.set_identity(self.path.parent, "Ana", "ana@example.com")
        vcs.commit_all(self.path.parent, "History turned on")
        self.window.project.add(self.window.project.root.id, ComponentKind.BUTTON)
        self.window.history.push(self.window.project, "Add")
        self.assertTrue(self.window.save_to(self.path))
        self.wait_for_versions(2)
        dialog.refresh()
        self.assertGreaterEqual(dialog.versions.count(), 3)

    def test_restore_reloads_the_project(self):
        self.assertTrue(self.window.save_to(self.path))
        vcs.init(self.path.parent)
        vcs.set_identity(self.path.parent, "Ana", "ana@example.com")
        first = vcs.commit_all(self.path.parent, "first")
        before = len(self.window.project.root.children)
        self.window.project.add(self.window.project.root.id, ComponentKind.BUTTON)
        self.window.history.push(self.window.project, "Add")
        self.assertTrue(self.window.save_to(self.path))
        self.wait_for_versions(2)
        dialog = HistoryDialog(self.window)
        for index in range(dialog.versions.count()):
            item = dialog.versions.item(index)
            data = item.data(256)
            if data and data.rev == first:
                dialog.versions.setCurrentRow(index)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dialog.restore_version()
        self.assertEqual(len(self.window.project.root.children), before)


if __name__ == "__main__":
    unittest.main()
