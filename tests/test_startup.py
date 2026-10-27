# SPDX-License-Identifier: GPL-3.0-or-later
"""The start window in the C layout, the emblem watermark and Download from Git."""

import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
import unittest.mock

from makebench.core import vcs
from makebench.core.project import Project
from makebench.core.storage import save_project

HOME_ENV = {"HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings

        from makebench.editor.window import MainWindow

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.window = MainWindow()
        self.window.recovery_timer.stop()
        self.window.settings = QSettings(
            str(self.root / "settings.ini"), QSettings.Format.IniFormat
        )
        self.window.recoveries = []

    def tearDown(self):
        dialog = getattr(self.window, "startup_dialog", None)
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def launcher(self):
        from makebench.editor.startup import StartupDialog

        dialog = StartupDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_launcher_has_the_four_commands_and_every_template(self):
        from makebench.core.templates import MODELS
        from makebench.editor.startup import DETAIL_ROLE

        dialog = self.launcher()
        self.assertEqual(dialog.width(), 760)
        self.assertEqual(dialog.git_button.text(), "Download from Git…")
        self.assertTrue(dialog.open_button.isDefault())
        self.assertEqual(dialog.models.count(), len(MODELS))
        self.assertTrue(dialog.models.item(0).data(DETAIL_ROLE))
        self.assertTrue(dialog.recovery_row.isHidden())

    def test_recents_show_folder_and_day_and_can_be_filtered(self):
        from makebench.editor.startup import DETAIL_ROLE

        paths = []
        for name in ("tasks", "calculator"):
            path = self.root / name / "project.makebench.json"
            path.parent.mkdir()
            save_project(Project.empty(name), path)
            paths.append(str(path))
        self.window.settings.setValue("projects/recent", paths)
        dialog = self.launcher()
        self.assertEqual(dialog.recents.count(), 2)
        self.assertTrue(dialog.recents.item(0).data(DETAIL_ROLE).endswith("today"))
        dialog.filter.setText("calc")
        self.assertTrue(dialog.recents.item(0).isHidden())
        self.assertFalse(dialog.recents.item(1).isHidden())

    def test_recovery_row_names_the_session(self):
        import json

        snapshot = self.root / "recovery" / "one"
        snapshot.mkdir(parents=True)
        (snapshot / "session.json").write_text(
            json.dumps({"name": "Workshop", "time": time.time()}), encoding="utf-8"
        )
        self.window.recoveries = [snapshot]
        dialog = self.launcher()
        self.assertFalse(dialog.recovery_row.isHidden())
        self.assertIn("Workshop, today at", dialog.recovery_label.text())

    def test_next_tip_cycles_and_is_remembered(self):
        dialog = self.launcher()
        first = dialog.tip.text()
        dialog.next_tip_button.click()
        self.assertNotEqual(dialog.tip.text(), first)
        self.assertEqual(self.window.settings.value("v1/projects/tip", type=int), 1)

    def test_emblems_load_and_watermark_can_be_turned_off(self):
        from PySide6.QtCore import QSize
        from PySide6.QtSvg import QSvgRenderer

        from makebench.editor.startup import LOGO, RETRO_LOGO, paint_watermark, watermark_image

        for path in (LOGO, RETRO_LOGO):
            self.assertTrue(QSvgRenderer(str(path)).isValid())
        image = watermark_image(True, QSize(68, 40))
        self.assertTrue(image.pixelColor(30, 20).alpha() > 0)
        self.window.settings.setValue("v1/appearance/watermark", False)
        with unittest.mock.patch("makebench.editor.startup.watermark_image") as draw:
            paint_watermark(self.window.home_page, self.window.settings)
        draw.assert_not_called()

    def test_start_page_reopens_the_launcher(self):
        from makebench.editor.startup import StartupDialog

        self.window.show()
        self.window.show_home()
        self.window.show_startup_button.click()
        self.app.processEvents()
        self.assertIsInstance(self.window.startup_dialog, StartupDialog)
        self.assertTrue(self.window.startup_dialog.isVisible())
        self.window.startup_dialog.banner.close_button.click()
        self.assertTrue(self.window.isVisible())


@unittest.skipUnless(vcs.available(), "git is not installed")
class CloneDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.saved_env = {k: os.environ.get(k) for k in HOME_ENV}
        os.environ["HOME"] = str(base / "home")
        os.environ["GIT_CONFIG_GLOBAL"] = str(base / "gitconfig")
        os.environ["GIT_CONFIG_SYSTEM"] = os.devnull
        (base / "home").mkdir()
        self.addCleanup(self.restore_env)
        self.base = base

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def server(self, with_project=True):
        work = self.base / "work"
        work.mkdir()
        if with_project:
            save_project(Project.empty("Shared"), work / "project.makebench.json")
        else:
            (work / "README").write_text("hello\n")
        vcs.init(work)
        vcs.commit_all(work, "first")
        server = self.base / "shared.git"
        vcs._run(self.base, ["init", "--bare", str(server)])
        vcs.set_remote(work, str(server))
        vcs.push(work)
        return server

    def run_dialog(self, url):
        from makebench.editor.clone import CloneDialog

        dialog = CloneDialog()
        self.addCleanup(dialog.deleteLater)
        dialog.url.setText(url)
        dialog.folder.setText(str(self.base / "downloads"))
        dialog.start()
        deadline = time.monotonic() + 60
        while dialog.poll.isActive() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        return dialog

    def test_download_finds_the_project(self):
        dialog = self.run_dialog(str(self.server()))
        self.assertEqual(dialog.name.text(), "shared")
        self.assertEqual(
            dialog.project_path, self.base / "downloads" / "shared" / "project.makebench.json"
        )
        self.assertTrue(dialog.url.isEnabled())

    def test_repository_without_a_project_is_reported(self):
        dialog = self.run_dialog(str(self.server(with_project=False)))
        self.assertIsNone(dialog.project_path)
        self.assertIn("no Makebench project", dialog.status.text())

    def test_failed_download_shows_the_error(self):
        dialog = self.run_dialog(str(self.base / "nothing.git"))
        self.assertIsNone(dialog.project_path)
        self.assertTrue(dialog.status.text())
        self.assertFalse((self.base / "downloads" / "nothing").exists())


if __name__ == "__main__":
    unittest.main()
