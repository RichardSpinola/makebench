# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt chart widget, shared by the Design preview and the running application."""

import math

from PySide6.QtCore import Property, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from makebench.core.chart import SAMPLE_LABELS, SAMPLE_VALUES, layout, series_color


class ChartWidget(QWidget):
    """Draws the shapes of ``core.chart.layout`` with the window's text color and accent."""

    def __init__(self, chart_type="bar", title="", sample=False):
        super().__init__()
        self.chart_type = chart_type
        self.title = title
        self.labels = list(SAMPLE_LABELS) if sample else []
        self.values = list(SAMPLE_VALUES) if sample else []
        self._accent = ""
        self.setProperty("mbChart", True)
        self.setMinimumSize(160, 110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def get_accent(self):
        """Accent color from the window style ("" for the default blue)."""
        return self._accent

    def set_accent(self, value):
        """Set by the stylesheet (qproperty-accent)."""
        self._accent = value
        self.update()

    accent = Property(str, get_accent, set_accent)

    def set_data(self, labels, values):
        """Replace the data and repaint."""
        self.labels = [str(x) for x in labels]
        self.values = list(values)
        self.setAccessibleDescription(
            ", ".join(f"{a}: {b}" for a, b in zip(self.labels, self.values))
        )
        self.update()

    def paintEvent(self, _event):
        """Paint the shapes; text uses the widget palette so any theme stays readable."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = self.palette().windowText().color()
        faint = QColor(ink)
        faint.setAlphaF(0.45)
        font = QFont(self.font())
        small = QFont(font)
        small.setPointSizeF(max(6.0, font.pointSizeF() * 0.85))
        bold = QFont(font)
        bold.setBold(True)
        for shape in layout(
            self.chart_type, self.title, self.labels, self.values, self.width(), self.height()
        ):
            kind = shape[0]
            if kind == "text":
                _, x, y, text, align, role = shape
                painter.setFont(bold if role == "title" else small)
                painter.setPen(ink)
                metrics = painter.fontMetrics()
                width = metrics.horizontalAdvance(text)
                left = x - (width / 2 if align == "center" else width if align == "right" else 0)
                painter.drawText(
                    QPointF(left, y + (metrics.ascent() - metrics.descent()) / 2), text
                )
            elif kind == "axis":
                painter.setPen(QPen(faint, 1))
                painter.drawLine(QPointF(shape[1], shape[2]), QPointF(shape[3], shape[4]))
            elif kind == "rect":
                _, x, y, w, h, color = shape
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(series_color(color, self._accent)))
                painter.drawRect(QRectF(x, y, w, h))
            elif kind == "line":
                painter.setPen(QPen(QColor(series_color(shape[2], self._accent)), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in shape[1]]))
            elif kind == "dot":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(series_color(shape[3], self._accent)))
                painter.drawEllipse(QPointF(shape[1], shape[2]), 3.5, 3.5)
            elif kind == "slice":
                _, cx, cy, radius, start, span, color = shape
                painter.setPen(QPen(self.palette().window().color(), 1))
                painter.setBrush(QColor(series_color(color, self._accent)))
                box = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
                if math.isclose(abs(span), 360.0):
                    painter.drawEllipse(box)
                else:
                    painter.drawPie(box, round(start * 16), round(span * 16))
        painter.end()
