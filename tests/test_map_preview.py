# SPDX-License-Identifier: GPL-3.0-or-later
"""Map thumbnails follow the desktop palette; arrows go around the cards."""

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


class EdgeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def crosses_a_card(self, source, target):
        from PySide6.QtCore import QRectF

        from makebench.editor.map_items import CARD_HEIGHT, CARD_WIDTH
        from makebench.editor.map_panel import edge_path

        path = edge_path(source, target)
        cards = [
            QRectF(point, point + type(point)(CARD_WIDTH, CARD_HEIGHT))
            for point in (source, target)
        ]
        for step in range(1, 20):
            point = path.pointAtPercent(step / 20)
            if any(card.adjusted(2, 2, -2, -2).contains(point) for card in cards):
                return True
        return False

    def test_arrows_to_another_row_go_around_the_cards(self):
        from PySide6.QtCore import QPointF

        origin = QPointF(0, 0)
        for target in (QPointF(-370, 387), QPointF(0, 387), QPointF(370, 387), QPointF(0, -387)):
            self.assertFalse(self.crosses_a_card(origin, target), target)

    def test_arrows_in_the_same_row_stay_outside_the_cards(self):
        from PySide6.QtCore import QPointF

        origin = QPointF(0, 0)
        for target in (QPointF(370, 0), QPointF(-370, 0)):
            self.assertFalse(self.crosses_a_card(origin, target), target)
