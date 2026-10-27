# SPDX-License-Identifier: GPL-3.0-or-later
"""Menu order, the command palette, empty lists and the example chooser."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from makebench.core.navigation import welcome_template
from makebench.editor.commands import SHORTCUT_ROLE, CommandPalette
from makebench.editor.guide import ExampleChooser
from makebench.editor.look import DETAIL_ROLE, empty_hint
from makebench.editor.window import MainWindow
from makebench.i18n import tr


class LookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(welcome_template())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def menu_titles(self):
        return [action.text().replace("&", "") for action in self.window.menuBar().actions()]

    def test_banner_tints_toward_the_accent_and_carries_the_search(self):
        from PySide6.QtGui import QPalette

        from makebench.editor.look import header, wash

        banner = header("Title", "Help")
        palette = banner.palette()
        tint = wash(palette)
        self.assertNotEqual(tint, palette.color(QPalette.ColorRole.Window))
        banner.resize(300, 60)
        image = banner.grab().toImage()
        self.assertEqual(image.pixelColor(150, 30), tint)
        self.assertEqual(image.pixelColor(1, 30), palette.color(QPalette.ColorRole.Highlight))
        self.window.preferences()
        dialog = self.window.preferences_dialog
        self.assertIs(dialog.search.parent(), dialog.banner)
        dialog.close()

    def test_menus_follow_the_usual_order_and_quit_is_last(self):
        titles = self.menu_titles()
        expected = [tr(name).replace("&", "") for name in ("&File", "&Edit", "&View", "&Help")]
        self.assertEqual(sorted(expected, key=titles.index), expected)
        self.assertEqual(titles[0], expected[0])
        file_menu = self.window.menuBar().actions()[0].menu()
        actions = [action for action in file_menu.actions() if not action.isSeparator()]
        self.assertEqual(actions[-1].text().replace("&", ""), tr("Quit"))

    def test_palette_keeps_the_shortcut_apart_from_the_name(self):
        palette = CommandPalette(self.window.findChildren(type(self.window.menuBar().actions()[0])))
        rows = [palette.items.item(row) for row in range(palette.items.count())]
        with_shortcut = [item for item in rows if item.data(SHORTCUT_ROLE)]
        self.assertTrue(with_shortcut)
        for item in with_shortcut:
            self.assertNotIn(item.data(SHORTCUT_ROLE), item.text())
        palette.deleteLater()

    def test_empty_hint_shows_only_while_the_list_is_empty(self):
        view = QListWidget()
        hint = empty_hint(view, "Nothing here")
        view.show()
        self.app.processEvents()
        self.assertTrue(hint.isVisible())
        view.addItem(QListWidgetItem("one"))
        self.assertFalse(hint.isVisible())
        view.clear()
        self.assertTrue(hint.isVisible())
        view.deleteLater()

    def test_example_chooser_lists_every_example_with_its_description(self):
        titles = [title for title, _, _ in self.window.available_examples()]
        self.assertTrue(
            any("full" in str(folder) for _, folder, _ in self.window.available_examples())
        )
        chooser = ExampleChooser(titles)
        self.assertEqual(chooser.list.count(), len(titles))
        for row in range(chooser.list.count()):
            self.assertTrue(chooser.list.item(row).data(DETAIL_ROLE))
        chooser.list.setCurrentRow(2)
        self.assertEqual(chooser.choice(), 2)
        chooser.deleteLater()


if __name__ == "__main__":
    unittest.main()
