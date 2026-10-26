# SPDX-License-Identifier: GPL-3.0-or-later
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from makebench.core.project import Project
from makebench.core.style import gtk_css, is_default, qt_stylesheet, valid_color, window_style
from makebench.runtime.view import RuntimeView


class StyleModelTests(unittest.TestCase):
    def test_old_windows_have_no_style(self):
        self.assertTrue(is_default(window_style({"title": "x"})))
        self.assertEqual(qt_stylesheet(window_style({}), "w"), "")
        self.assertEqual(gtk_css(window_style({}), "w"), "")

    def test_invalid_values_cannot_inject_css(self):
        style = window_style({"theme": "pink", "accent": "red; } * { x", "background": "#12"})
        self.assertTrue(is_default(style))
        self.assertFalse(valid_color("#123456; }"))

    def test_dark_theme_and_accent_reach_both_toolkits(self):
        style = window_style({"theme": "dark", "accent": "#ff8800"})
        self.assertIn("#242424", qt_stylesheet(style, "w"))
        self.assertIn("#ff8800", qt_stylesheet(style, "w"))
        self.assertIn(".w button", gtk_css(style, "w"))
        self.assertIn("#ff8800", gtk_css(style, "w"))

    def test_style_round_trips_through_the_project_file(self):
        project = Project.empty("x")
        project.root.properties.update(theme="dark", background="#101010")
        again = Project.from_dict(project.to_dict())
        self.assertEqual(again.root.properties["theme"], "dark")
        self.assertEqual(again.root.properties["background"], "#101010")


class RuntimeStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_runtime_window_is_styled_and_ctx_changes_it(self):
        project = Project.empty("x")
        project.root.properties["theme"] = "dark"
        view = RuntimeView(project, lambda key: b"")
        self.assertIn("#242424", view.styleSheet())
        view.change_style(background="#336699")
        self.assertIn("#336699", view.styleSheet())
        view.reset()
        self.assertIn("#242424", view.styleSheet())
        self.assertNotIn("#336699", view.styleSheet())
        self.assertIsNotNone(project.root)


if __name__ == "__main__":
    unittest.main()


class GtkStyleTests(unittest.TestCase):
    def test_gtk_window_gets_a_scoped_provider(self):
        try:
            import gi

            gi.require_version("Gtk", "4.0")
            from gi.repository import Gdk, Gtk
        except (ImportError, ValueError):
            self.skipTest("GTK 4 is not available")
        if Gdk.Display.get_default() is None or not Gtk.init_check():
            self.skipTest("no display for GTK")
        from makebench.gtk_runtime.renderer import GtkView

        project = Project.empty("x")
        project.root.properties.update(theme="dark")
        view = GtkView(project.root, lambda key: b"", lambda _id: None)
        self.assertIsNotNone(view.provider)
        view.change_style(theme="system", background="")
        self.assertIsNone(view.provider)
