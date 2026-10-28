# SPDX-License-Identifier: GPL-3.0-or-later
"""First-release acceptance: palette, templates, GTK and inert packages."""

import support  # noqa: F401  (first: isolates settings and data)
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication
from makebench.ui.theme import derive_tokens, contrast, ThemeManager


class PaletteTests(unittest.TestCase):
    """The accent follows its origin and stays visible in both schemes."""

    @classmethod
    def setUpClass(cls):
        """Share the test application without touching the author's settings."""
        cls.app = QApplication.instance() or QApplication([])

    def test_simulated_accents_and_contrast(self):
        """Different palettes change the selection; texts/controls keep a minimum ratio."""
        accents = []
        for color in ("#3584e4", "#26a269"):
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Accent, QColor(color))
            for dark in (False, True):
                t = derive_tokens(palette, dark, system_surfaces=False)
                accents.append(t["accent"])
                for key in ("text", "muted", "success", "warning", "error", "info"):
                    for bg in ("panel", "raised"):
                        self.assertGreaterEqual(contrast(t[key], t[bg]), 4.5, (key, bg, t))
                for bg in ("panel", "raised"):
                    self.assertGreaterEqual(contrast(t["accent"], t[bg]), 3)
                    self.assertGreaterEqual(contrast(t["control"], t[bg]), 3)
                self.assertGreaterEqual(contrast(t["on_accent"], t["fill"]), 4.5)
        self.assertNotEqual(accents[0], accents[2])

    def test_theme_does_not_replace_system_palette(self):
        """With desktop colors, preferences never call setPalette on the application."""
        from unittest.mock import patch

        theme = getattr(self.app, "makebench_theme", None) or ThemeManager(self.app)
        look = theme.look
        theme.look = "native"
        theme.apply()
        self.addCleanup(lambda: (setattr(theme, "look", look), theme.apply()))
        with patch.object(self.app, "setPalette") as setter:
            theme.set_mode("dark")
            theme.set_accent("green")
            theme.set_mode("light")
            setter.assert_not_called()
        theme.set_accent("system")
        theme.set_mode("system")


class TemplateTests(unittest.TestCase):
    """Templates are independent documents and keep the chosen backend."""

    def test_five_models_and_backend_roundtrip(self):
        """Every template validates without running code and legacy ones stay Qt."""
        from makebench.core.templates import MODELS, make_template
        from makebench.core.project import Project
        from makebench.core.codegen import generate

        self.assertEqual(len(MODELS), 5)
        for key, _, _ in MODELS:
            if key == "tasks":
                continue
            p = make_template(key, "Testing")
            self.assertEqual(generate(p, "").diagnostics, [])
            self.assertEqual(Project.from_dict(p.to_dict()).application.get("backend", "qt"), "qt")
            for backend in ("gtk", "qt"):
                p.application["backend"] = backend
                q = Project.from_dict(p.to_dict())
                self.assertEqual(q.application["backend"], backend)
                self.assertEqual(q.to_dict(), p.to_dict())
