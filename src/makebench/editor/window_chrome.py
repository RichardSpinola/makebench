# SPDX-License-Identifier: GPL-3.0-or-later
"""The window being designed: a real-looking frame with a title bar and resize grips."""

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QRubberBand, QToolTip, QVBoxLayout, QWidget

from makebench.i18n import tr

MINIMUM_WINDOW = QSize(200, 160)


def mix(first, second, amount):
    """Blend two colors; used to derive the title bar from the desktop palette."""
    return QColor(
        round(first.red() + (second.red() - first.red()) * amount),
        round(first.green() + (second.green() - first.green()) * amount),
        round(first.blue() + (second.blue() - first.blue()) * amount),
    )


class QtWindowChrome(QWidget):
    """A desktop title bar: centered title and window buttons, from the desktop palette."""

    def __init__(self, root, parent=None):
        """Window buttons are visual on the canvas; they never close the editing tool."""
        super().__init__(parent)
        self.root = root
        self.setFixedHeight(38)
        self.setAccessibleName(tr("Window title bar"))

    def buttons(self):
        """Names of the buttons shown, right to left as on most Linux desktops."""
        names = ["close"]
        if self.root.properties.get("resizable", True):
            names.append("maximize")
        names.append("minimize")
        return names

    def paintEvent(self, event):
        """Title and buttons follow the native palette and font."""
        palette = self.palette()
        window = palette.window().color()
        text = palette.windowText().color()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), mix(window, text, 0.06))
        painter.setPen(QPen(mix(window, text, 0.16), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        x = self.width() - 12
        for name in self.buttons():
            x -= 24
            circle = QRectF(x, (self.height() - 24) / 2, 24, 24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(mix(window, text, 0.12))
            painter.drawEllipse(circle)
            painter.setPen(QPen(text, 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            c = circle.center()
            if name == "close":
                painter.drawLine(c + QPointF(-4, -4), c + QPointF(4, 4))
                painter.drawLine(c + QPointF(-4, 4), c + QPointF(4, -4))
            elif name == "maximize":
                painter.drawRect(QRectF(c.x() - 4, c.y() - 4, 8, 8))
            else:
                painter.drawLine(c + QPointF(-4, 3), c + QPointF(4, 3))
            x -= 8
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text)
        title = self.root.properties.get("title", tr("Application"))
        room = self.width() - x
        area = QRect(room, 0, self.width() - 2 * room, self.height())
        if area.width() < 40:
            area = QRect(12, 0, x - 12, self.height())
        title = painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, area.width())
        painter.drawText(area, Qt.AlignmentFlag.AlignCenter, title)


class WindowFrame(QFrame):
    """The designed window: title bar over the client area, with a thin border."""

    def __init__(self, chrome, surface, parent=None):
        """The surface keeps the declared client size; content never moves it."""
        super().__init__(parent)
        self.setObjectName("mbWindowFrame")
        # A real window is opaque; the desk and its shadow never show through.
        self.setAutoFillBackground(True)
        self.chrome = chrome
        self.surface = surface
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(chrome)
        layout.addWidget(surface)

    def set_client_size(self, size):
        """Show the window at the size the application opens with."""
        size = (
            size.expandedTo(MINIMUM_WINDOW)
            .expandedTo(self.surface.minimumSize())
            .expandedTo(self.surface.minimumSizeHint())
        )
        self.surface.setFixedSize(size)
        self.chrome.setFixedWidth(size.width())
        self.setFixedSize(size.width() + 2, size.height() + self.chrome.height() + 2)

    def paintEvent(self, event):
        """A border a little darker than the window, like a desktop window edge."""
        palette = self.palette()
        painter = QPainter(self)
        painter.setPen(QPen(mix(palette.window().color(), palette.windowText().color(), 0.3), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


def paint_shadow(painter, rect):
    """A soft shadow under the designed window, so it reads as a window on a desk."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    for step in range(8):
        grow = 8 - step
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect.adjusted(-grow, -grow + 3, grow, grow + 3)), 8, 8)
        painter.setBrush(QColor(0, 0, 0, 6 + step * 2))
        painter.drawPath(path)
    painter.restore()


class WindowGrip(QWidget):
    """Drag the right edge, bottom edge or corner to set the window's opening size."""

    resized = Signal(int, int)

    def __init__(self, edge, canvas):
        """The grip lives on the canvas so it stays above the GTK preview too."""
        super().__init__(canvas)
        self.edge = edge
        self.canvas = canvas
        self.start = None
        self.outline = None
        self.setCursor(
            {
                "e": Qt.CursorShape.SizeHorCursor,
                "s": Qt.CursorShape.SizeVerCursor,
                "se": Qt.CursorShape.SizeFDiagCursor,
            }[edge]
        )
        self.setToolTip(tr("Drag to change the size the window opens with."))
        self.setAccessibleName(tr("Window size"))

    def place(self, rect):
        """Sit just outside the window's edge so it never covers its controls."""
        if self.edge == "e":
            self.setGeometry(rect.right() + 1, rect.top(), 7, rect.height() - 12)
        elif self.edge == "s":
            self.setGeometry(rect.left(), rect.bottom() + 1, rect.width() - 12, 7)
        else:
            self.setGeometry(rect.right() - 11, rect.bottom() - 11, 19, 19)
        self.show()
        self.raise_()

    def paintEvent(self, event):
        """Only the corner shows dots; the edges are found by the cursor."""
        if self.edge != "se":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().highlight())
        for x, y in ((15, 7), (15, 11), (11, 11), (15, 15), (11, 15), (7, 15)):
            painter.drawEllipse(QPointF(x, y), 1.4, 1.4)

    def mousePressEvent(self, event):
        """Remember where the gesture began and the size it began with."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        root = self.canvas._project.root
        self.start = (
            self.mapTo(self.canvas, event.position().toPoint()),
            QSize(root.properties.get("width", 640), root.properties.get("height", 480)),
        )

    def target(self, event):
        """The client size under the pointer, snapped to the grid."""
        origin, size = self.start
        delta = self.mapTo(self.canvas, event.position().toPoint()) - origin
        snap = lambda value: round(value / 8) * 8
        width = size.width() + (delta.x() if "e" in self.edge else 0)
        height = size.height() + (delta.y() if "s" in self.edge else 0)
        return QSize(snap(width), snap(height)).expandedTo(MINIMUM_WINDOW)

    def mouseMoveEvent(self, event):
        """Qt windows resize live; the GTK picture shows an outline until release."""
        if self.start is None:
            return
        size = self.target(event)
        self.canvas.preview_window_size(size, self)
        QToolTip.showText(
            event.globalPosition().toPoint(), f"{size.width()} × {size.height()}", self
        )

    def show_outline(self, rect):
        """Outline used while the window is drawn by another toolkit."""
        if self.outline is None:
            self.outline = QRubberBand(QRubberBand.Shape.Rectangle, self.canvas)
        self.outline.setGeometry(rect)
        self.outline.show()

    def mouseReleaseEvent(self, event):
        """One change in the history for the whole gesture."""
        if self.start is None:
            return
        size = self.target(event)
        changed = size != self.start[1]
        self.start = None
        if self.outline is not None:
            self.outline.hide()
        if changed:
            self.resized.emit(size.width(), size.height())
