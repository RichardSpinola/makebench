# SPDX-License-Identifier: MIT
"""Controls and layouts shared by editing and running Qt applications."""

from PySide6.QtCore import QDate, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QFrame,
    QWidget,
)
from makebench.core.project import RANGE_DEFAULTS, ComponentKind, LayoutKind
from makebench.core.storage import StorageError
from makebench.core.style import component_qss
from makebench.i18n import tr
from .chart import ChartWidget
from .table import RecordTable


def range_properties(node):
    """The limits and value of a number or slider, with the defaults filled in."""
    return {**RANGE_DEFAULTS, **node.properties}


def fill_choice(widget, options, text, ids=None):
    """Set the options of a choice list and select `text` (the first one when it is absent).

    `ids` hides a record id behind each option."""
    blocked = widget.blockSignals(True)
    try:
        widget.clear()
        for index, option in enumerate(options):
            widget.addItem(option, ids[index] if ids else None)
        widget.setCurrentIndex(max(widget.findText(text), 0) if widget.count() else -1)
    finally:
        widget.blockSignals(blocked)


def configure_table(widget, columns):
    """Show the columns of a table; rows are added later by the application."""
    widget.rows_model.set_headers(columns)


def append_table_row(widget, row, record=None):
    """Add a row of texts; `record` hides a record id in the row."""
    widget.rows_model.append(row, record)


def set_table_rows(widget, rows, ids=None):
    """Replace every row without telling the application the person did it."""
    blocked = widget.blockSignals(True)
    try:
        widget.rows_model.set_rows(rows, ids)
    finally:
        widget.blockSignals(blocked)


def selected_table_record(widget):
    """The record id hidden in the selected row, or None."""
    row = widget.selected_row()
    return widget.rows_model.records[row] if row >= 0 else None


def selected_table_row(widget):
    row = widget.selected_row()
    return [] if row < 0 else [widget.text(row, c) for c in range(widget.columnCount())]


def table_contents(widget):
    """Headers and every row of a table, as texts (what a CSV export writes)."""
    model = widget.rows_model
    width = len(model.headers)
    rows = [(row + [""] * width)[:width] for row in model.rows]
    return {"headers": list(model.headers), "rows": rows}


def set_date(widget, iso):
    """Show a YYYY-MM-DD date without telling the application the person did it."""
    blocked = widget.blockSignals(True)
    try:
        widget.setDate(QDate.fromString(iso, "yyyy-MM-dd"))
    finally:
        widget.blockSignals(blocked)


def date_text(widget):
    return widget.date().toString("yyyy-MM-dd")


def set_range_value(widget, value):
    """Move a number or slider without telling the application the person did it."""
    blocked = widget.blockSignals(True)
    try:
        widget.setValue(value if isinstance(widget, QDoubleSpinBox) else int(value))
    finally:
        widget.blockSignals(blocked)


def configure_range(widget, node):
    """Apply minimum, maximum, step, decimals and value of a number or slider."""
    p = range_properties(node)
    widget.blockSignals(True)
    if isinstance(widget, QDoubleSpinBox):
        widget.setDecimals(p["decimals"])
        widget.setRange(p["minimum"], p["maximum"])
        widget.setSingleStep(p["step"])
        widget.setKeyboardTracking(False)
    else:
        widget.setRange(int(p["minimum"]), int(p["maximum"]))
        widget.setSingleStep(int(p["step"]))
        widget.setPageStep(max(int(p["step"]), 1))
    widget.blockSignals(False)
    set_range_value(widget, p["value"])


def range_value(widget):
    """Read a number or slider as int when it has no decimals."""
    value = widget.value()
    if isinstance(widget, QDoubleSpinBox) and widget.decimals():
        return value
    return int(round(value))


class TextArea(QPlainTextEdit):
    """Multi-line input that reports only what the person types, never ctx edits."""

    edited = Signal()

    def __init__(self, text=""):
        """Start with the initial text without reporting it."""
        super().__init__()
        self._silent = True
        self.setPlainText(text)
        self._silent = False
        self.textChanged.connect(lambda: None if self._silent else self.edited.emit())

    def setPlainText(self, text):
        """Replace the text as the application, not as the person."""
        previous, self._silent = self._silent, True
        try:
            super().setPlainText(text)
        finally:
            self._silent = previous


class ImageLabel(QLabel):
    """Show an image scaled to the available space, with an accessible description."""

    def __init__(self, image: QPixmap, description: str) -> None:
        """Keep the original image so quality is not lost on every resize."""
        super().__init__()
        self.image = image
        self.setMinimumSize(80, 64)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setAccessibleName(description)

    def paintEvent(self, event) -> None:
        """Center the image without distorting or cropping its content."""
        if self.image.isNull():
            super().paintEvent(event)
            return
        size = self.image.size().scaled(
            self.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        rect = QRect(QPoint(), size)
        rect.moveCenter(self.contentsRect().center())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(rect, self.image)


def create_control(node, read_asset, editing=False):
    """Create a native control; editing disables typing and receives external selection."""
    text = node.properties.get("text", "")
    match node.kind:
        case ComponentKind.SEPARATOR:
            widget = QFrame()
            widget.setFrameShape(QFrame.Shape.HLine)
        case ComponentKind.SPACER:
            widget = QWidget()
            widget.setMinimumSize(24, 24)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        case ComponentKind.LABEL:
            widget = QLabel(text)
            widget.setWordWrap(True)
        case ComponentKind.BUTTON:
            widget = QPushButton(text)
            widget.setMinimumHeight(34)
        case ComponentKind.TEXT_INPUT:
            widget = QLineEdit(text)
            widget.setPlaceholderText(node.properties.get("placeholder", ""))
            widget.setReadOnly(editing)
        case ComponentKind.TEXT_AREA:
            widget = TextArea(text)
            widget.setPlaceholderText(node.properties.get("placeholder", ""))
            widget.setReadOnly(editing)
            widget.setMinimumHeight(70)
        case ComponentKind.CHECKBOX:
            widget = QCheckBox(text)
            widget.setChecked(node.properties.get("checked", False))
        case ComponentKind.PROGRESS:
            widget = QProgressBar()
            widget.setValue(node.properties.get("value", 0))
        case ComponentKind.CHART:
            widget = ChartWidget(
                node.properties.get("chart_type", "bar"), node.properties.get("title", ""), editing
            )
        case ComponentKind.CHOICE:
            widget = QComboBox()
            fill_choice(widget, node.properties.get("options", []), node.properties.get("text", ""))
        case ComponentKind.TABLE:
            widget = RecordTable()
            configure_table(widget, node.properties.get("headers", []))
            widget.setMinimumHeight(70)
        case ComponentKind.DATE:
            widget = QDateEdit()
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.setCalendarPopup(True)
            set_date(widget, node.properties.get("text", ""))
        case ComponentKind.NUMBER:
            widget = QDoubleSpinBox()
            configure_range(widget, node)
        case ComponentKind.SLIDER:
            widget = QSlider(Qt.Orientation.Horizontal)
            configure_range(widget, node)
        case ComponentKind.TERMINAL:
            from makebench.terminal.qt import TerminalWidget

            widget = TerminalWidget(editing=editing)
        case ComponentKind.OUTPUT:
            # A running app keeps the text as a hint, so output never lands after it.
            widget = QPlainTextEdit(text if editing else "")
            if not editing:
                widget.setPlaceholderText(text)
            widget.setReadOnly(True)
            widget.setMinimumHeight(110)
            widget.setMaximumHeight(220)
        case ComponentKind.IMAGE:
            source = node.properties.get("source", "")
            pixmap = QPixmap()
            try:
                if source:
                    pixmap.loadFromData(read_asset(source))
            except StorageError:
                pass
            widget = ImageLabel(pixmap, node.properties.get("alt_text", tr("Image")))
            if pixmap.isNull():
                widget.setText(
                    tr("Image unavailable") if source else tr("Select an image in the properties")
                )
                widget.setWordWrap(True)
                widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        case _:
            raise ValueError(tr("Component without a renderer: {kind}").format(kind=node.kind))
    if isinstance(widget, QLabel):
        widget.setTextFormat(Qt.TextFormat.PlainText)
    if node.kind == ComponentKind.BUTTON and node.properties.get("icon"):
        image = QPixmap()
        try:
            image.loadFromData(read_asset(node.properties["icon"]))
        except (OSError, StorageError):
            pass
        widget.setIcon(QIcon(image))
    widget.setToolTip(node.properties.get("tooltip", ""))
    widget.setObjectName(node.id)
    widget.setEnabled(node.properties.get("enabled", True))
    apply_component_style(widget, node)
    return widget


def apply_component_style(widget, node, container=False):
    """Give one control or container its own color, font and corners."""
    sheet = component_qss(node.properties, container)
    if sheet:
        widget.setProperty("mbOwn", True)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setStyleSheet(sheet)


class BackgroundImage(QWidget):
    """A window background picture that covers its parent, under every control."""

    def __init__(self, data: bytes, parent: QWidget) -> None:
        super().__init__(parent)
        self.image = QPixmap()
        self.image.loadFromData(data)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setObjectName("mbBackgroundImage")
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.lower()
        self.show()

    def eventFilter(self, watched, event) -> bool:
        """Follow the parent's size and stay below the controls added later."""
        if watched is self.parent() and event.type() in (event.Type.Resize, event.Type.Show):
            self.setGeometry(watched.rect())
            self.lower()
        return False

    def paintEvent(self, event) -> None:
        """Fill the area keeping proportions; the overflow is cropped at the center."""
        if self.image.isNull():
            return
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        rect = QRect(QPoint(), size)
        rect.moveCenter(self.rect().center())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(rect, self.image)


def set_background_image(surface, node, read_asset):
    """Add or replace the background picture of a window surface."""
    old = surface.findChild(BackgroundImage, "mbBackgroundImage")
    if old is not None:
        old.setParent(None)
        old.deleteLater()
    source = node.properties.get("background_image", "")
    if not source:
        return None
    try:
        data = read_asset(source)
    except (OSError, StorageError):
        return None
    return BackgroundImage(data, surface)


def place_children(frame, node, render):
    """Apply the same geometry/layout to children in the editor and in the application."""
    if node.layout == LayoutKind.FREE:
        for child in node.children:
            rendered = render(child)
            rendered.setParent(frame)
            rendered.setGeometry(*(child.geometry[key] for key in ("x", "y", "width", "height")))
            rendered.setVisible(child.properties.get("visible", True))
        # Exactly the children's extent: a control at the edge must not widen the window.
        width = max((c.geometry["x"] + c.geometry["width"] for c in node.children), default=300)
        height = max((c.geometry["y"] + c.geometry["height"] for c in node.children), default=200)
        frame.setMinimumSize(width, height)
        return
    if node.layout == LayoutKind.HORIZONTAL:
        layout = QHBoxLayout(frame)
    elif node.layout == LayoutKind.GRID:
        layout = QGridLayout(frame)
    else:
        layout = QVBoxLayout(frame)
    padding = node.properties.get("padding", 8)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(node.properties.get("spacing", 6))
    distribute = node.properties.get("distribute", "start")
    explicit = "distribute" in node.properties
    if not isinstance(layout, QGridLayout) and distribute in {"center", "end"}:
        layout.addStretch(1)
    for index, child in enumerate(node.children):
        rendered = render(child)
        modes = child.properties.get("size_mode", {})
        for axis in ("width", "height"):
            if modes.get(axis) == "fixed":
                getattr(rendered, "setFixed" + axis.title())(child.geometry[axis])
            elif modes.get(axis) == "fill":
                policy = rendered.sizePolicy()
                if axis == "width":
                    policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
                else:
                    policy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
                rendered.setSizePolicy(policy)
        alignment = {
            "start": Qt.AlignmentFlag.AlignLeft
            if node.layout == LayoutKind.VERTICAL
            else Qt.AlignmentFlag.AlignTop,
            "center": Qt.AlignmentFlag.AlignHCenter
            if node.layout == LayoutKind.VERTICAL
            else Qt.AlignmentFlag.AlignVCenter,
            "end": Qt.AlignmentFlag.AlignRight
            if node.layout == LayoutKind.VERTICAL
            else Qt.AlignmentFlag.AlignBottom,
        }.get(node.properties.get("align"))
        if alignment:
            layout.setAlignment(rendered, alignment)
        if isinstance(layout, QGridLayout):
            columns = node.properties.get("columns", 2)
            layout.addWidget(rendered, index // columns, index % columns)
        else:
            axis = "height" if node.layout == LayoutKind.VERTICAL else "width"
            layout.addWidget(rendered, 1 if modes.get(axis) == "fill" else 0)
            if alignment:
                layout.setAlignment(rendered, alignment)
            if distribute == "space-between" and index < len(node.children) - 1:
                layout.addStretch(1)
    if isinstance(layout, QGridLayout) and node.properties.get("alignment_preset"):
        vertical, horizontal = node.properties["alignment_preset"].split("-")
        layout.setAlignment(
            {
                "top": Qt.AlignmentFlag.AlignTop,
                "center": Qt.AlignmentFlag.AlignVCenter,
                "bottom": Qt.AlignmentFlag.AlignBottom,
            }[vertical]
            | {
                "left": Qt.AlignmentFlag.AlignLeft,
                "center": Qt.AlignmentFlag.AlignHCenter,
                "right": Qt.AlignmentFlag.AlignRight,
            }[horizontal]
        )
    if not isinstance(layout, QGridLayout) and distribute == "center":
        layout.addStretch(1)
    elif isinstance(layout, QVBoxLayout) and distribute == "start":
        layout.addStretch(1)
    elif explicit and not isinstance(layout, QGridLayout) and distribute == "start":
        layout.addStretch(1)
    elif not node.children:
        frame.setMinimumSize(220, 100)
