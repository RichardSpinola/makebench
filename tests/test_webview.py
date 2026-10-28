# SPDX-License-Identifier: GPL-3.0-or-later
"""Web view windows and the official plugin that makes them."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from makebench.core.project import ComponentKind, Project, ProjectError
from makebench.core.web import materialize, page_assets
from makebench.editor.plugins import CommandContext, PluginManager, Refusal

IMAGE = "assets/" + "a" * 64 + ".png"


def fake_page(html, read_asset, parent=None):
    """Tests never start Qt WebEngine; the label carries the HTML it was given."""
    label = QLabel(parent)
    label.setProperty("html", html)
    return label


class WebWindowTests(unittest.TestCase):
    def web_project(self, html="<p>Hi</p>"):
        project = Project.empty("Tour")
        project.root.properties["web_page"] = html
        return Project.from_dict(project.to_dict())

    def test_only_windows_hold_a_page_and_it_takes_no_components(self):
        project = self.web_project()
        self.assertFalse(project.root.accepts(ComponentKind.BUTTON))
        with self.assertRaises(ProjectError):
            project.add(project.root.id, ComponentKind.BUTTON)
        data = Project.empty("x").to_dict()
        data["ui"]["properties"]["web_page"] = 5
        with self.assertRaises(ProjectError):
            Project.from_dict(data)
        normal = Project.empty("x")
        normal.add(normal.root.id, ComponentKind.LABEL)
        data = normal.to_dict()
        data["ui"]["properties"]["web_page"] = "<p></p>"
        with self.assertRaises(ProjectError):
            Project.from_dict(data)

    def test_images_used_by_the_page_are_kept_and_written_beside_it(self):
        project = self.web_project(f'<img src="{IMAGE}">')
        self.assertIn(IMAGE, project.asset_paths())
        self.assertEqual(page_assets(project.root.properties["web_page"]), {IMAGE})
        page = materialize(project.root.properties["web_page"], lambda name: b"png")
        self.assertEqual((page.parent / IMAGE).read_bytes(), b"png")
        self.assertIn(IMAGE, page.read_text())

    def test_running_window_shows_only_the_page(self):
        from makebench.runtime.view import RuntimeView

        QApplication.instance() or QApplication([])
        project = self.web_project("<h1>Tour</h1>")
        with patch("makebench.ui.web.web_widget", fake_page):
            view = RuntimeView(project, lambda name: b"")
        page = view.widgets[project.root.id]
        self.assertEqual(page.property("html"), "<h1>Tour</h1>")
        self.assertEqual(list(view.widgets), [project.root.id])


class OfficialPluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = PluginManager(Path(self.tmp.name))
        self.addCleanup(self.manager.disable, "webview")

    def command(self, name):
        names = [label for label, _ in self.manager.plugins["webview"].commands]
        return names.index(name)

    def test_ships_off_and_marked_official(self):
        plugin = self.manager.plugins["webview"]
        self.assertTrue(plugin.official)
        self.assertFalse(plugin.enabled)
        self.manager.load_enabled()
        self.assertFalse(plugin.enabled)
        with self.assertRaises(ProjectError):
            self.manager.install_from(plugin.folder)

    def test_template_makes_a_web_view_project(self):
        self.assertTrue(self.manager.enable("webview"))
        (key, name, _), *_ = self.manager.templates()
        self.assertEqual(name, "Web view")
        project = self.manager.make_template(key, "Tour")
        self.assertIn("<script>", project.root.properties["web_page"])
        self.assertEqual(project.root.properties["title"], "Tour")

    def test_window_turns_into_a_web_view_and_back_keeping_the_page(self):
        self.manager.enable("webview")
        project = Project.empty("Tour")
        context = CommandContext(project.root.id)
        web = self.manager.run_command(
            "webview", self.command("Turn this window into a Web view"), project, context
        )
        page = web.root.properties["web_page"]
        normal = self.manager.run_command(
            "webview",
            self.command("Turn this Web view back into a normal window"),
            web,
            context,
        )
        self.assertNotIn("web_page", normal.root.properties)
        normal.add(normal.root.id, ComponentKind.LABEL)
        normal.root.children.clear()
        again = self.manager.run_command(
            "webview", self.command("Turn this window into a Web view"), normal, context
        )
        self.assertEqual(again.root.properties["web_page"], page)

    def test_refusal_is_shown_and_the_plugin_stays_on(self):
        self.manager.enable("webview")
        project = Project.empty("Busy")
        project.add(project.root.id, ComponentKind.BUTTON)
        with self.assertRaises(Refusal):
            self.manager.run_command(
                "webview",
                self.command("Turn this window into a Web view"),
                project,
                CommandContext(project.root.id),
            )
        self.assertTrue(self.manager.plugins["webview"].enabled)


class WebViewEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_design_shows_the_page_and_rests_the_library(self):
        from makebench.editor.plugins_ui import run_command
        from makebench.editor.window import MainWindow

        with patch("makebench.ui.web.web_widget", fake_page):
            window = MainWindow()
            self.addCleanup(self.close, window)
            window.plugin_manager.enable("webview")
            self.addCleanup(window.plugin_manager.disable, "webview")
            names = [label for label, _ in window.plugin_manager.plugins["webview"].commands]
            run_command(window, "webview", names.index("Turn this window into a Web view"))
            self.assertIn("web_page", window.project.root.properties)
            self.assertFalse(window.palette.isEnabled())
            labels = window.canvas.window_frame.findChildren(QLabel)
            self.assertTrue(any(label.property("html") for label in labels))
            steps = window.history._index
            editor = sys.modules["makebench_plugin_webview"].PageEditor
            with (
                patch.object(editor, "__init__", lambda self, html, context: None),
                patch.object(editor, "ask", lambda self: None),
            ):
                run_command(window, "webview", names.index("Edit Web view page…"))
            self.assertEqual(window.history._index, steps)
            window.undo()
            self.assertNotIn("web_page", window.project.root.properties)
            self.assertTrue(window.palette.isEnabled())

    @staticmethod
    def close(window):
        window.history.mark_saved()
        window.source.mark_saved()
        window.close()


if __name__ == "__main__":
    unittest.main()
