# SPDX-License-Identifier: GPL-3.0-or-later
"""The .mbtheme format: strict validation and safe import."""

import support  # noqa: F401  (first: isolates settings and data)
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from makebench.ui import themes


class ThemeFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.folder = self.base / "themes"

    def write(self, data, name="a.mbtheme"):
        path = self.base / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def theme(self, **changes):
        data = copy.deepcopy(themes.BUILTIN)
        data["name"] = "Forest"
        data.update(changes)
        return data

    def test_builtin_is_valid_and_listed_first(self):
        self.assertEqual(themes.installed(self.folder)[0]["name"], "Makebench")

    def test_rejects_bad_files(self):
        bad = [
            "not json",
            [],
            self.theme(format="other"),
            self.theme(version=99),
            self.theme(name=" "),
            self.theme(accent="blue"),
            self.theme(dark={"win": "#000000"}),
            self.theme(light=None),
        ]
        for index, data in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(themes.ThemeError):
                themes.load(self.write(data, f"b{index}.mbtheme"))

    def test_rejects_huge_and_missing_files(self):
        with self.assertRaises(themes.ThemeError):
            themes.load(self.write(" " * (themes.MAX_SIZE + 1)))
        with self.assertRaises(themes.ThemeError):
            themes.load(self.base / "missing.mbtheme")

    def test_import_copies_without_overwriting_and_drops_extra_keys(self):
        data = self.theme(script="rm -rf /")
        source = self.write(data)
        themes.import_theme(source, self.folder)
        themes.import_theme(source, self.folder)
        files = sorted(p.name for p in self.folder.glob("*.mbtheme"))
        self.assertEqual(files, ["forest-2.mbtheme", "forest.mbtheme"])
        self.assertNotIn("script", json.loads((self.folder / files[0]).read_text()))

    def test_installed_skips_invalid_user_files(self):
        self.folder.mkdir()
        (self.folder / "broken.mbtheme").write_text("{")
        themes.import_theme(self.write(self.theme()), self.folder)
        self.assertEqual(
            [t["name"] for t in themes.installed(self.folder)], ["Makebench", "Forest"]
        )


class MakebenchLookTests(unittest.TestCase):
    """The default look supplies a palette; desktop colors bring the system's back."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from makebench.ui.theme import manager

        self.theme = manager()
        saved = (self.theme.look, self.theme.mode)
        self.addCleanup(self.restore, saved)

    def restore(self, saved):
        self.theme.look, self.theme.mode = saved
        self.theme.apply()

    def test_tokens_are_legible_in_both_modes(self):
        from makebench.ui.theme import contrast, look_tokens

        theme = themes.validate(themes.BUILTIN)
        for dark in (False, True):
            t = look_tokens(theme, dark)
            for key in ("text", "muted", "success", "warning", "error", "info"):
                for bg in ("panel", "raised", "sidebar"):
                    with self.subTest(dark=dark, key=key, bg=bg):
                        self.assertGreaterEqual(contrast(t[key], t[bg]), 4.5)
            self.assertGreaterEqual(contrast(t["accent"], t["panel"]), 3)
            self.assertGreaterEqual(contrast(t["on_accent"], t["fill"]), 4.5)

    def test_switching_looks_sets_and_restores_the_palette(self):
        from PySide6.QtGui import QPalette

        window = QPalette.ColorRole.Window
        self.theme.look, self.theme.mode = "native", "system"
        self.theme.apply()
        native = self.app.palette().color(window).name()
        self.theme.look, self.theme.mode = "makebench", "dark"
        self.theme.apply()
        self.assertEqual(self.app.palette().color(window).name(), "#2b2e32")
        self.assertEqual(self.theme.tokens["look"], "makebench")
        self.assertEqual(self.app.styleSheet(), "")
        self.theme.mode = "light"
        self.theme.apply()
        self.assertEqual(self.app.palette().color(window).name(), "#eceef0")
        self.theme.look = "native"
        self.theme.apply()
        self.assertEqual(self.app.palette().color(window).name(), native)
        self.assertEqual(self.app.palette().resolveMask(), 0)


class ThemesDialogTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])
        from PySide6.QtCore import QSettings

        from makebench.ui.theme import manager

        self.manager = manager()
        self.folder = Path(tempfile.mkdtemp())
        # Never write the person's real settings.
        self.saved = (self.manager.settings, self.manager.look, self.manager.color_theme)
        self.manager.settings = QSettings(
            str(self.folder / "settings.ini"), QSettings.Format.IniFormat
        )

    def tearDown(self):
        self.manager.settings, look, self.manager.color_theme = self.saved
        self.manager.look = look
        self.manager.apply()
        shutil.rmtree(self.folder)

    def test_lists_builtin_user_and_desktop_and_applies(self):
        from makebench.editor.themes_ui import DESKTOP, ThemesDialog

        mine = {**themes.validate(themes.BUILTIN), "name": "Ocean", "accent": "#118899"}
        themes.add(mine, self.folder)
        dialog = ThemesDialog(folder=self.folder)
        names = [dialog.list.item(i).data(256) for i in range(dialog.list.count())]
        self.assertEqual(names, ["Makebench", "Ocean", DESKTOP])
        dialog.list.setCurrentRow(1)
        self.assertTrue(dialog.swatches["fg"].isEnabled())
        dialog._change_color("accent", "#aa3355")
        self.assertEqual(themes.load(self.folder / "ocean.mbtheme")["accent"], "#aa3355")
        dialog.list.setCurrentRow(2)
        dialog._apply()
        self.assertEqual(self.manager.look, "native")
        dialog.list.setCurrentRow(0)
        self.assertFalse(dialog.swatches["fg"].isEnabled())
        dialog._apply()
        self.assertEqual((self.manager.look, self.manager.color_theme), ("makebench", "Makebench"))
        self.assertFalse(dialog.apply_button.isEnabled())
