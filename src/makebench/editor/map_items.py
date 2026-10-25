# SPDX-License-Identifier: GPL-3.0-or-later
"""Map graphics items: real composition, ports and easy-to-select lines."""

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QFontMetricsF,
    QPixmap,
    QPainterPathStroker,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
)
from .theme import manager, icon
from makebench.i18n import ntr, tr

CARD_WIDTH = 300
CARD_HEIGHT = 252


class MapNode(QGraphicsRectItem):
    """A card is a view of the document: it holds a thumbnail, name, state and diagnostic."""

    def __init__(self, key, label, position, view, initial=False, issue="", count=0):
        """No thumbnail control receives the application's run events."""
        super().__init__(0, 0, CARD_WIDTH, CARD_HEIGHT)
        self.key = key
        self.label = label
        self.map_view = view
        self.initial = initial
        self.issue = issue
        self.count = count
        self.thumbnail = QPixmap()
        self.preview_error = ""
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setPos(*position)
        self.setToolTip(
            label
            + "\n"
            + tr("Double-click opens the Designer. Drag the port to connect.")
            + ("\n" + issue if issue else "")
        )

    def boundingRect(self):
        """Include the port in the scene's update and hit-testing rectangle."""
        return self.rect().adjusted(-1, -1, 8, 1)

    def shape(self):
        """The port can also receive a drag on its outer half."""
        path = QPainterPath()
        path.addRect(self.rect())
        path.addEllipse(QPointF(CARD_WIDTH, 126), 8, 8)
        return path

    def paint(self, painter, option, widget=None):
        """Only the card is graphics; its content is rendered by the real toolkit."""
        t = manager().tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(t["raised"]))
        painter.setPen(
            QPen(
                QColor(t["accent"] if self.isSelected() else t["border"]),
                2 if self.isSelected() else 1,
            )
        )
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setFont(QApplication.font())
        metrics = QFontMetricsF(painter.font())
        lines = self.label.split("\n", 1)
        painter.setPen(QColor(t["text"]))
        painter.drawText(
            QRectF(12, 8, 264, 22), metrics.elidedText(lines[0], Qt.TextElideMode.ElideRight, 264)
        )
        painter.setPen(QColor(t["muted"]))
        painter.drawText(
            QRectF(12, 30, 264, 18),
            metrics.elidedText(
                lines[1] if len(lines) > 1 else tr("Window"), Qt.TextElideMode.ElideRight, 264
            ),
        )
        area = QRectF(12, 54, 276, 174)
        painter.fillRect(area, QColor(t["canvas"]))
        if not self.thumbnail.isNull():
            painter.drawPixmap(
                round(area.center().x() - self.thumbnail.width() / 2),
                round(area.center().y() - self.thumbnail.height() / 2),
                self.thumbnail,
            )
        else:
            painter.drawText(
                area,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                tr("Preview unavailable") if self.preview_error else tr("Preparing preview…"),
            )
        painter.setPen(QColor(t["text"]))
        footer = (
            "▶ " + tr("Initial")
            if self.initial
            else ntr("{count} element", "{count} elements", self.count).format(count=self.count)
        )
        if self.issue or self.preview_error:
            footer += "  ·  !"
        painter.drawText(QRectF(12, 230, 250, 20), footer)
        painter.setBrush(QColor(t["raised"]))
        painter.setPen(QPen(QColor(t["accent"]), 2))
        painter.drawEllipse(QPointF(CARD_WIDTH, 126), 6, 6)

    def mouseDoubleClickEvent(self, event):
        """Defer navigation until Qt finishes the graphics event."""
        key = self.key
        QTimer.singleShot(0, lambda: self.map_view.panel.activate(key))
        event.accept()

    def keyPressEvent(self, event):
        """Enter offers the same navigation as a double-click."""
        if event.key() in {Qt.Key.Key_Enter, Qt.Key.Key_Return}:
            self.map_view.panel.activate(self.key)
            event.accept()
        else:
            super().keyPressEvent(event)


class MapEdge(QGraphicsPathItem):
    """Line with a larger click area without adding visual weight."""

    def __init__(self, path, edge):
        """Keep only the IDs of the block and flow behind this navigation."""
        super().__init__(path)
        self.edge = edge
        self.setData(0, edge)
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setToolTip(
            edge["event"] + "\n" + tr("Click to inspect; Delete removes the transition.")
        )

    def shape(self):
        """A thin line stays reachable by the mouse at low zoom."""
        stroke = QPainterPathStroker()
        stroke.setWidth(14)
        return stroke.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        """Selection uses the native highlight and the arrow follows the curve's final tangent."""
        t = manager().tokens
        color = QColor(t["accent"] if self.isSelected() else t["muted"])
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 2 if self.isSelected() else 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
        end = self.path().pointAtPercent(1)
        before = self.path().pointAtPercent(0.96)
        delta = end - before
        length = max(1, (delta.x() ** 2 + delta.y() ** 2) ** 0.5)
        unit = delta / length
        normal = QPointF(-unit.y(), unit.x())
        head = QPainterPath(end)
        head.lineTo(end - unit * 11 + normal * 4)
        head.lineTo(end - unit * 11 - normal * 4)
        head.closeSubpath()
        painter.fillPath(head, color)


class GroupHeader(QGraphicsSimpleTextItem):
    """Collapsible title of a window and its states; does not change the document."""

    def __init__(self, label, identifier, panel):
        """The native tree offers the same command by keyboard."""
        super().__init__(label)
        self.identifier = identifier
        self.panel = panel
        self.setFont(QApplication.font())
        self.setBrush(QColor(manager().tokens["text"]))
        self.setToolTip(tr("Click to expand or collapse this window's states."))

    def mousePressEvent(self, event):
        """Never start a card drag when clicking the group header."""
        identifier = self.identifier
        QTimer.singleShot(0, lambda: self.panel.toggle_group(identifier))
        event.accept()
