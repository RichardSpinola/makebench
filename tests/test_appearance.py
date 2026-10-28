# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-component style, window background image and Copy/Paste style."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox

from makebench.core.project import ComponentKind, Project, ProjectError
from makebench.core.style import component_qss, gtk_component_css, style_error
from makebench.runtime.view import RuntimeView
from makebench.ui.renderer import BackgroundImage


def png(color="#ff0000"):
    """A tiny real PNG, so the background goes through the same loader as an asset."""
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


class StyleModelTests(unittest.TestCase):
    def test_style_values_are_checked_and_cannot_inject_css(self):
        self.assertIsNone(style_error({}))
        self.assertIsNone(style_error({"style_color": "", "style_font_size": 0}))
        self.assertEqual(style_error({"style_color": "red; } * {"}), "style_color")
        self.assertEqual(style_error({"style_font_size": 200}), "style_font_size")
        self.assertEqual(style_error({"style_radius": -1}), "style_radius")
        self.assertEqual(style_error({"style_bold": "yes"}), "style_bold")
        self.assertEqual(component_qss({}), "")
        sheet = component_qss({"style_color": "#112233", "style_bold": True, "style_radius": 8})
        self.assertIn("color: #112233;", sheet)
        self.assertIn("font-weight: bold;", sheet)
        self.assertIn("border-radius: 8px;", sheet)
        css = gtk_component_css({"style_background": "#445566"}, "win", "mb-c0")
        self.assertIn(".win .mb-c0 { background: #445566; }", css)

    def test_project_validates_style_and_background_and_bumps_the_format(self):
        project = Project.empty("x")
        self.assertLess(project.to_dict()["format_version"], 12)
        button = project.add(project.root.id, ComponentKind.BUTTON)
        button.properties["style_color"] = "#ff0000"
        project.root.properties["background_image"] = "assets/sky.png"
        data = project.to_dict()
        self.assertEqual(data["format_version"], 12)
        again = Project.from_dict(data)
        self.assertEqual(again.find(button.id).properties["style_color"], "#ff0000")
        self.assertIn("assets/sky.png", again.asset_paths())
        for bad in ("../sky.png", "/tmp/sky.png", "sky.png"):
            project.root.properties["background_image"] = bad
            with self.assertRaises(ProjectError):
                Project.from_dict(project.to_dict())
        project.root.properties["background_image"] = ""
        button.properties["style_font_size"] = 500
        with self.assertRaises(ProjectError):
            Project.from_dict(project.to_dict())


class QtAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_running_window_shows_style_and_background_image(self):
        project = Project.empty("x")
        button = project.add(project.root.id, ComponentKind.BUTTON)
        button.properties.update(style_background="#00ff00", style_font_size=20)
        group = project.add(project.root.id, ComponentKind.CONTAINER)
        group.properties["style_color"] = "#0000ff"
        project.root.properties["background_image"] = "assets/sky.png"
        view = RuntimeView(project, lambda source: png())
        view.resize(300, 200)
        view.show()
        self.app.processEvents()
        widget = view.widgets[button.id]
        self.assertIn("#00ff00", widget.styleSheet())
        self.assertTrue(widget.property("mbOwn"))
        self.assertIn("QLabel", view.frames[group.id].styleSheet())
        background = view.findChild(BackgroundImage)
        self.assertIsNotNone(background)
        self.assertFalse(background.image.isNull())
        self.assertEqual(background.geometry(), view.rect())
        self.assertEqual(view.grab().toImage().pixelColor(2, 2).name(), "#ff0000")
        view.close()


class EditorStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from makebench.editor.window import MainWindow

        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.history.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_inspector_edits_style_and_copy_paste_style_is_one_undo(self):
        window = self.window
        project = window.project
        first = project.add(project.root.id, ComponentKind.BUTTON)
        second = project.add(project.root.id, ComponentKind.LABEL)
        window._refresh()
        window._select(first.id)
        self.app.processEvents()
        size = window.inspector.findChild(QSpinBox, "property_style_font_size")
        self.assertIsNotNone(size)
        size.setValue(18)
        window._change_property(first.id, "style_bold", True)
        self.assertEqual(window.project.find(first.id).properties["style_font_size"], 18)
        self.assertIsNotNone(window.inspector.findChild(QPushButton, "property_style_color"))
        self.assertFalse(window.paste_style_action.isEnabled())
        window.copy_style()
        window._select(second.id)
        self.assertTrue(window.paste_style_action.isEnabled())
        window.paste_style()
        pasted = window.project.find(second.id).properties
        self.assertEqual((pasted["style_font_size"], pasted["style_bold"]), (18, True))
        window.undo()
        self.assertNotIn("style_bold", window.project.find(second.id).properties)

    def test_window_look_offers_a_background_image(self):
        window = self.window
        window._select(window.project.root.id)
        self.app.processEvents()
        self.assertIsNotNone(window.inspector.findChild(QPushButton, "property_background_image"))
        self.assertIsNone(window.inspector.findChild(QSpinBox, "property_style_font_size"))
        with tempfile.TemporaryDirectory() as folder:
            picture = Path(folder) / "sky.png"
            picture.write_bytes(png("#0000ff"))
            with patch(
                "makebench.editor.design_edit.QFileDialog.getOpenFileName",
                return_value=(str(picture), ""),
            ):
                window.choose_background_image(window.project.root.id)
        self.app.processEvents()
        self.assertTrue(window.project.root.properties["background_image"].startswith("assets/"))
        self.assertIsNotNone(window.canvas.findChild(BackgroundImage))
        self.assertIsNotNone(window.inspector.findChild(QPushButton, "property_background_image"))


class GtkAppearanceTests(unittest.TestCase):
    def test_gtk_view_styles_components_and_covers_with_the_image(self):
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
        button = project.add(project.root.id, ComponentKind.BUTTON)
        button.properties["style_background"] = "#00ff00"
        project.root.properties["background_image"] = "assets/sky.png"
        view = GtkView(project.root, lambda source: png(), lambda _id: None)
        self.assertIsInstance(view.widget, Gtk.Overlay)
        self.assertTrue(view.frames[button.id].has_css_class("mb-c0"))
        self.assertIsNotNone(view.provider)
        width = view.widget.get_first_child().measure(Gtk.Orientation.HORIZONTAL, -1)
        self.assertEqual(width[1], 0)


if __name__ == "__main__":
    unittest.main()
