# SPDX-License-Identifier: MIT
"""Controls and layouts shared by editing and running Qt applications."""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
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
from makebench.i18n import tr


def range_properties(node):
    """The limits and value of a number or slider, with the defaults filled in."""
    return {**RANGE_DEFAULTS, **node.properties}


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
        case ComponentKind.CHECKBOX:
            widget = QCheckBox(text)
            widget.setChecked(node.properties.get("checked", False))
        case ComponentKind.PROGRESS:
            widget = QProgressBar()
            widget.setValue(node.properties.get("value", 0))
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
    return widget


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
