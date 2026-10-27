# SPDX-License-Identifier: GPL-3.0-or-later
"""Detachable Design panels: docking, floating, hiding and restoring the layout."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        # Keep layout changes out of the real configuration.
        cls.config = tempfile.TemporaryDirectory()
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, cls.config.name)

    @classmethod
    def tearDownClass(cls):
        from PySide6.QtCore import QSettings

        QSettings.setPath(
            QSettings.Format.NativeFormat,
            QSettings.Scope.UserScope,
            str(Path.home() / ".config"),
        )
        cls.config.cleanup()

    def setUp(self):
        from PySide6.QtCore import QSettings

        from makebench.editor.panels import LAYOUT_KEY
        from makebench.editor.window import MainWindow

        QSettings("Makebench", "Makebench").remove(LAYOUT_KEY)

        self.window = MainWindow()
        self.window.recovery_timer.stop()
        self.window.show()
        self.window.set_mode("design")
        self.app.processEvents()

    def tearDown(self):
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_panels_dock_around_the_creation_area(self):
        from PySide6.QtCore import Qt

        host = self.window.design_host
        self.assertIs(self.window.tabs.widget(0), host)
        self.assertIs(host.centralWidget(), self.window.pasteboard)
        self.assertEqual(set(host.docks), {"layers", "components", "data", "properties"})
        left = Qt.DockWidgetArea.LeftDockWidgetArea
        self.assertEqual(host.dockWidgetArea(host.docks["layers"]), left)
        self.assertEqual(
            host.dockWidgetArea(host.docks["properties"]), Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.assertTrue(self.window.tree.isVisible())
        self.assertTrue(self.window.inspector.isVisible())
        self.assertIs(self.window.data_list.window(), self.window)

    def test_floating_and_restoring_the_layout(self):
        host = self.window.design_host
        properties = host.docks["properties"]
        properties.setFloating(True)
        host.docks["layers"].hide()
        self.app.processEvents()
        self.assertTrue(properties.isFloating())
        self.window.restore_layout_action.trigger()
        self.app.processEvents()
        self.assertFalse(properties.isFloating())
        self.assertTrue(host.docks["layers"].isVisible())

    def test_layout_is_kept_for_the_next_window(self):
        from makebench.editor.window import MainWindow

        self.window.design_host.docks["properties"].hide()
        self.window.design_host.save_layout()
        other = MainWindow()
        other.recovery_timer.stop()
        other.show()
        other.set_mode("design")
        self.app.processEvents()
        try:
            self.assertFalse(other.design_host.docks["properties"].isVisible())
            other.design_host.restore_layout()
        finally:
            other.history.mark_saved()
            other.source.mark_saved()
            other.close()
            other.deleteLater()

    def test_side_shortcuts_toggle_the_panels(self):
        host = self.window.design_host
        self.window.toggle_side("right")
        self.assertFalse(host.docks["properties"].isVisible())
        self.window.toggle_side("right")
        self.assertTrue(host.docks["properties"].isVisible())
        self.window.toggle_side("left")
        self.assertFalse(host.docks["layers"].isVisible())
        self.assertFalse(host.docks["components"].isVisible())

    def test_view_menu_lists_every_panel(self):
        texts = [
            a.text() for a in self.window.findChildren(type(self.window.restore_layout_action))
        ]
        for title in ("Layers", "Components", "Data", "Properties", "Restore layout"):
            self.assertIn(title, texts)


if __name__ == "__main__":
    unittest.main()
