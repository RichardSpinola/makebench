# SPDX-License-Identifier: GPL-3.0-or-later
"""Map thumbnails follow the desktop palette they are drawn with."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ThumbnailSignatureTests(unittest.TestCase):
    def test_desktop_palette_change_renders_the_card_again(self):
        """A light thumbnail is not reused after the desktop turns dark."""
        from PySide6.QtCore import QObject
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QApplication

        from makebench.core.project import Project
        from makebench.editor.map_preview import ThumbnailCache
        from makebench.editor.theme import manager

        QApplication.instance() or QApplication([])
        theme = manager()
        original = QPalette(theme.system_palette)
        owner = QObject()
        cache = ThumbnailCache(owner)
        cache.timer.stop()
        root = Project.empty().root
        try:
            cache.request("w|@default", root, "qt", lambda _name: b"")
            light = cache.wanted["w|@default"]
            dark = QPalette(original)
            dark.setColor(QPalette.ColorRole.Window, QColor("#202124"))
            theme.system_palette = dark
            cache.request("w|@default", root, "qt", lambda _name: b"")
            self.assertNotEqual(cache.wanted["w|@default"], light)
        finally:
            theme.system_palette = original
            cache.closed = True
            cache.timer.stop()


if __name__ == "__main__":
    unittest.main()
