# SPDX-License-Identifier: GPL-3.0-or-later
"""Window shell: area bar, "where you are" strip, project corner and status items."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest


class ShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from makebench.editor.window import MainWindow

        self.window = MainWindow()
        self.window.recovery_timer.stop()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_area_bar_holds_modes_and_tools_beside_the_pages(self):
        w = self.window
        bar = w.mode_switcher
        self.assertTrue(bar.isVisible())
        self.assertIs(bar.parentWidget(), w.pages.parentWidget())
        for button in w.mode_buttons.values():
            self.assertIs(button.parentWidget(), bar)
        tips = [b.accessibleName() for b in bar.findChildren(type(w.mode_buttons["map"]))]
        self.assertIn("Version history", tips)
        self.assertIn("Preferences", tips)
        self.assertIs(w.menuBar().cornerWidget(), w.project_corner)

    def test_strip_follows_the_area_and_the_selection(self):
        w = self.window
        w.set_mode("design")
        self.app.processEvents()
        self.assertEqual(w.area_strip.badge.text(), "DESIGN")
        self.assertIn(w.project.root.properties.get("title", ""), w.area_strip.path.text())
        w.set_mode("map")
        self.assertEqual(w.area_strip.badge.text(), "MAP")
        self.assertIn(w.project.name, w.area_strip.path.text())

    def test_status_items_show_saved_state_and_problems(self):
        w = self.window
        self.assertTrue(w.save_status.isVisible())
        self.assertIn("component", w.save_status.text())
        w.problems_status.click()
        self.assertTrue(w.drawer.isVisible())
        self.assertEqual(w.drawer.currentIndex(), 1)


if __name__ == "__main__":
    unittest.main()
