"""Controles e layouts comuns à edição e à execução de aplicativos Qt."""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QFrame,
    QWidget,
)
from makebench.core.project import ComponentKind, LayoutKind
from makebench.core.storage import StorageError


class ImageLabel(QLabel):
    """Exibe uma imagem proporcional ao espaço disponível, com descrição acessível."""

    def __init__(self, image: QPixmap, description: str) -> None:
        """Guarda a imagem original, evitando perder qualidade a cada redimensionamento."""
        super().__init__()
        self.image = image
        self.setMinimumSize(80, 64)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setAccessibleName(description)

    def paintEvent(self, event) -> None:
        """Centraliza a imagem sem deformar ou cortar seu conteúdo."""
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
    """Cria um controle nativo; edição desabilita digitação e recebe seleção externa."""
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
        case ComponentKind.TERMINAL:
            from makebench.terminal.qt import TerminalWidget

            widget = TerminalWidget(editing=editing)
        case ComponentKind.OUTPUT:
            widget = QPlainTextEdit(text)
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
            widget = ImageLabel(pixmap, node.properties.get("alt_text", "Imagem"))
            if pixmap.isNull():
                widget.setText(
                    "Imagem indisponível" if source else "Selecione uma imagem nas propriedades"
                )
                widget.setWordWrap(True)
                widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        case _:
            raise ValueError(f"Componente sem renderizador: {node.kind}")
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
    """Aplica a mesma geometria/layout aos filhos no editor e no aplicativo."""
    if node.layout == LayoutKind.FREE:
        for child in node.children:
            rendered = render(child)
            rendered.setParent(frame)
            rendered.setGeometry(*(child.geometry[key] for key in ("x", "y", "width", "height")))
            rendered.setVisible(child.properties.get("visible", True))
        width = max(
            (c.geometry["x"] + c.geometry["width"] + 16 for c in node.children), default=300
        )
        height = max(
            (c.geometry["y"] + c.geometry["height"] + 16 for c in node.children), default=200
        )
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
