# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt editing decoration drawn by the native style, with no theme of our own."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QStyle, QStyleOptionTitleBar
from makebench.i18n import tr


class QtWindowChrome(QWidget):
    """Use the same title bar primitive as the Qt installed on the desktop."""

    def __init__(self, root, parent=None):
        """Window buttons are visual on the canvas; they never close the editing tool."""
        super().__init__(parent)
        self.root = root
        self.setFixedHeight(self.style().pixelMetric(QStyle.PixelMetric.PM_TitleBarHeight))
        self.setAccessibleName(tr("Window title bar"))

    def paintEvent(self, event):
        """Title, icon and window controls follow the native QStyle and QPalette."""
        option = QStyleOptionTitleBar()
        option.initFrom(self)
        option.rect = self.rect()
        option.text = self.root.properties.get("title", tr("Application"))
        option.titleBarFlags = (
            Qt.WindowType.Window
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        if self.root.properties.get("resizable", True):
            option.titleBarFlags |= Qt.WindowType.WindowMaximizeButtonHint
        option.titleBarState = Qt.WindowState.WindowActive.value
        option.subControls = QStyle.SubControl.SC_All
        painter = QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_TitleBar, option, painter, self)
