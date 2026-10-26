# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from makebench.core.project import ComponentKind, Project, ProjectError, create_component
from makebench.editor.plugins import PluginManager

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "plugins" / "word-count"


def write_plugin(folder, plugin_id, code, api=1):
    target = folder / plugin_id
    target.mkdir(parents=True)
    (target / "plugin.json").write_text(
        json.dumps({"id": plugin_id, "name": plugin_id, "api": api})
    )
    (target / "plugin.py").write_text(code)


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "plugins"
        self.marker = Path(self.tmp.name) / "ran"
        self.project = Project("Demo", create_component(ComponentKind.WINDOW))

    def test_nothing_runs_until_enabled(self):
        write_plugin(
            self.folder,
            "loud",
            f"__import__('pathlib').Path({str(self.marker)!r}).write_text('x')\ndef register(api): pass\n",
        )
        manager = PluginManager(self.folder)
        manager.load_enabled()
        self.assertFalse(self.marker.exists())
        self.assertTrue(manager.enable("loud"))
        self.assertTrue(self.marker.exists())

    def test_enabled_state_is_remembered(self):
        shutil.copytree(EXAMPLE, self.folder / "word-count")
        manager = PluginManager(self.folder)
        self.assertTrue(manager.enable("word-count"))
        again = PluginManager(self.folder)
        again.load_enabled()
        self.assertTrue(again.plugins["word-count"].enabled)
        self.assertIn("greet_user", again.snippets())

    def test_wrong_api_does_not_load(self):
        write_plugin(self.folder, "old", "def register(api): pass\n", api=2)
        manager = PluginManager(self.folder)
        self.assertFalse(manager.enable("old"))
        self.assertTrue(manager.plugins["old"].error)

    def test_broken_plugin_is_turned_off_and_isolated(self):
        write_plugin(self.folder, "bad", "raise RuntimeError('boom')\n")
        write_plugin(
            self.folder,
            "good",
            "def register(api):\n    api.add_command('x', lambda p: 1/0)\n",
        )
        manager = PluginManager(self.folder)
        self.assertFalse(manager.enable("bad"))
        self.assertIn("boom", manager.plugins["bad"].error)
        self.assertTrue(manager.enable("good"))
        with self.assertRaises(ProjectError):
            manager.run_command("good", 0, self.project)
        self.assertFalse(manager.plugins["good"].enabled)

    def test_command_changes_a_copy(self):
        shutil.copytree(EXAMPLE, self.folder / "word-count")
        manager = PluginManager(self.folder)
        manager.enable("word-count")
        result = manager.run_command("word-count", 0, self.project)
        self.assertIn("words", result.root.properties["title"])
        self.assertNotIn("words", self.project.root.properties.get("title", ""))

    def test_install_from_folder(self):
        manager = PluginManager(self.folder)
        self.assertEqual(manager.install_from(EXAMPLE), "word-count")
        self.assertFalse(manager.plugins["word-count"].enabled)
        with self.assertRaises(ProjectError):
            manager.install_from(EXAMPLE)


class PluginWindowTests(unittest.TestCase):
    def test_command_is_one_undo_step(self):
        from PySide6.QtWidgets import QApplication

        from makebench.editor.plugins_ui import run_command
        from makebench.editor.window import MainWindow

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as data:
            shutil.copytree(EXAMPLE, Path(data) / "makebench" / "plugins" / "word-count")
            with patch.dict(os.environ, {"XDG_DATA_HOME": data}):
                window = MainWindow()
                window.plugin_manager.enable("word-count")
                before = window.project.root.properties.get("title")
                run_command(window, "word-count", 0)
                self.assertNotEqual(window.project.root.properties.get("title"), before)
                window.undo()
                self.assertEqual(window.project.root.properties.get("title"), before)
                window.history.mark_saved()
                window.source.mark_saved()
                window.close()
                app.processEvents()


if __name__ == "__main__":
    unittest.main()
