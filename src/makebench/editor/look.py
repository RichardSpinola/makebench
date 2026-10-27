# SPDX-License-Identifier: GPL-3.0-or-later
"""Small layout helpers shared by dialogs: titles, secondary text, button rows, empty lists.

Colors come from palette roles, never fixed values, so they follow theme changes.
"""

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

DETAIL_ROLE = Qt.ItemDataRole.UserRole + 2


def make_title(label: QLabel, scale: float = 1.25) -> QLabel:
    """Bold and a little larger than the text around it."""
    font = label.font()
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * scale)
    font.setBold(True)
    label.setFont(font)
    return label


def make_muted(label: QLabel) -> QLabel:
    """Secondary text in the palette's placeholder color, wrapped."""
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    label.setWordWrap(True)
    return label


def wash(palette: QPalette, amount: float = 0.13) -> QColor:
    """The window color tinted toward the accent, as in the start page's banner."""
    base, accent = (
        palette.color(QPalette.ColorRole.Window),
        palette.color(QPalette.ColorRole.Highlight),
    )
    return QColor(
        *(round(a + (b - a) * amount) for a, b in zip(base.getRgb()[:3], accent.getRgb()[:3]))
    )


class Banner(QWidget):
    """A dialog or page header: accent-tinted band, an accent edge, title and one phrase."""

    def __init__(self, title: str, help_text: str = "", icon: QIcon | None = None):
        super().__init__()
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(16, 10, 12, 10)
        self.row.setSpacing(12)
        if icon is not None and not icon.isNull():
            self.icon = QLabel()
            self.icon.setPixmap(icon.pixmap(QSize(24, 24), self.devicePixelRatioF()))
            self.row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = make_title(QLabel(title))
        text.addWidget(self.title)
        self.help = make_muted(QLabel(help_text))
        self.help.setWordWrap(True)
        self.help.setVisible(bool(help_text))
        text.addWidget(self.help)
        self.row.addLayout(text, 1)

    def add_widget(self, widget):
        """Put a control (a search field, a button) on the banner's right side."""
        self.row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(palette.color(QPalette.ColorRole.Mid))
        painter.setBrush(wash(palette))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.color(QPalette.ColorRole.Highlight))
        painter.drawRoundedRect(QRectF(0, 0, 4, self.height()), 2, 2)
        painter.end()


def header(title: str, help_text: str = "", icon: QIcon | None = None) -> Banner:
    """An area or dialog header: a title and, below it, one phrase of help."""
    return Banner(title, help_text, icon)


def button_row(*buttons, trailing=()) -> QHBoxLayout:
    """Buttons at their natural width on the left, optional ones pushed to the right."""
    row = QHBoxLayout()
    row.setSpacing(6)
    for button in buttons:
        row.addWidget(button)
    row.addStretch(1)
    for button in trailing:
        row.addWidget(button)
    return row


class _EmptyHint(QObject):
    """Keep a centered hint over a list's viewport while the list has no rows."""

    def __init__(self, view, text):
        super().__init__(view)
        self.view = view
        self.label = make_muted(QLabel(text, view.viewport()))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        view.viewport().installEventFilter(self)
        model = view.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(self.refresh)
        self.refresh()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.label.setGeometry(watched.rect().adjusted(16, 16, -16, -16))
        return False

    def refresh(self, *_):
        # The model clears its rows while the list is being destroyed.
        if not isValid(self.view) or not isValid(self.label):
            return
        self.label.setGeometry(self.view.viewport().rect().adjusted(16, 16, -16, -16))
        self.label.setVisible(self.view.model().rowCount() == 0)


def empty_hint(view, text: str) -> QLabel:
    """Show `text` in the middle of an item view whenever it is empty."""
    return _EmptyHint(view, text).label


class TwoLineDelegate(QStyledItemDelegate):
    """List rows with a bold name and, below it, a dimmed line from DETAIL_ROLE."""

    PAD = 8

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        name, opt.text = opt.text, ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        selected = opt.state & QStyle.StateFlag.State_Selected
        rect = opt.rect.adjusted(self.PAD, self.PAD // 2, -self.PAD, -self.PAD // 2)
        bold = opt.font
        bold.setBold(True)
        line = opt.fontMetrics.height()
        painter.save()
        painter.setFont(bold)
        text_role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        painter.setPen(opt.palette.color(text_role))
        painter.drawText(rect.adjusted(0, 0, 0, -line), Qt.AlignmentFlag.AlignLeft, name)
        detail = index.data(DETAIL_ROLE)
        if detail:
            painter.setFont(option.font)
            dim = text_role if selected else QPalette.ColorRole.PlaceholderText
            painter.setPen(opt.palette.color(dim))
            painter.drawText(rect.adjusted(0, line, 0, 0), Qt.AlignmentFlag.AlignLeft, detail)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(option.fontMetrics.height() * 2 + self.PAD + 4)
        return size
