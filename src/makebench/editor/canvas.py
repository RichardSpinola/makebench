"""Prévia Qt da árvore visual, sem executar ações dos componentes."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from makebench.core.project import Component, ComponentKind, LayoutKind, Project


class PreviewCanvas(QFrame):
    """Renderiza componentes nativos e converte cliques em seleção de edição."""

    component_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Prepara a superfície e o estilo de seleção do editor."""
        super().__init__(parent)
        self._frames: dict[str, QFrame] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(10)
        self.setStyleSheet(
            'QFrame[previewNode="true"] { border: 1px solid transparent; border-radius: 4px; }'
            'QFrame[previewNode="true"][selectedNode="true"] '
            '{ border: 1px solid palette(highlight); }'
        )

    def set_project(self, project: Project) -> None:
        """Reconstrói a prévia a partir do documento, sem alterar o modelo."""
        self._frames = {}
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        title = QLabel(project.root.properties.get("title", project.name))
        font = title.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        title.setFont(font)
        self._layout.addWidget(title)
        surface = self._render(project.root)
        surface.setMinimumSize(surface.minimumSize().expandedTo(QSize(360, 320)))
        surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._layout.addWidget(surface, 1)

    def select(self, component_id: str) -> None:
        """Atualiza o destaque sem recriar widgets ou roubar o foco."""
        for node_id, frame in self._frames.items():
            selected = node_id == component_id
            if frame.property("selectedNode") != selected:
                frame.setProperty("selectedNode", selected)
                frame.style().unpolish(frame)
                frame.style().polish(frame)
                frame.update()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Intercepta cliques da prévia para evitar disparar ações de aplicativos."""
        node_id = watched.property("componentId")
        if node_id and event.type() in (
            QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
        ):
            self.component_selected.emit(node_id)
            return True
        return super().eventFilter(watched, event)

    def _watch(self, widget: QWidget, component_id: str) -> None:
        """Associa o controle ao componente que será selecionado pelo clique."""
        widget.setProperty("componentId", component_id)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        widget.installEventFilter(self)

    def _render(self, node: Component) -> QFrame:
        """Cria um controle ou contêiner correspondente ao nó do documento."""
        frame = QFrame()
        frame.setProperty("previewNode", True)
        self._frames[node.id] = frame
        self._watch(frame, node.id)
        if node.can_have_children:
            self._render_children(frame, node)
            return frame

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        text = node.properties.get("text", "")
        match node.kind:
            case ComponentKind.LABEL:
                widget = QLabel(text)
                widget.setWordWrap(True)
            case ComponentKind.BUTTON:
                widget = QPushButton(text)
                widget.setMinimumHeight(34)
            case ComponentKind.TEXT_INPUT:
                widget = QLineEdit(text)
                widget.setPlaceholderText(node.properties.get("placeholder", ""))
                widget.setReadOnly(True)
            case ComponentKind.CHECKBOX:
                widget = QCheckBox(text)
                widget.setChecked(node.properties.get("checked", False))
            case ComponentKind.PROGRESS:
                widget = QProgressBar()
                widget.setValue(node.properties.get("value", 0))
            case ComponentKind.OUTPUT:
                widget = QPlainTextEdit(text)
                widget.setReadOnly(True)
                widget.setMinimumHeight(110)
                widget.setMaximumHeight(220)
                self._watch(widget.viewport(), node.id)
            case _:
                raise ValueError(f"Componente sem renderizador: {node.kind}")
        self._watch(widget, node.id)
        layout.addWidget(widget)
        return frame

    def _render_children(self, frame: QFrame, node: Component) -> None:
        """Aplica layout nativo ou geometria livre aos componentes filhos."""
        if node.layout == LayoutKind.FREE:
            for child in node.children:
                rendered = self._render(child)
                rendered.setParent(frame)
                geometry = child.geometry
                rendered.setGeometry(*(geometry[key] for key in ("x", "y", "width", "height")))
            width = max((c.geometry["x"] + c.geometry["width"] + 16 for c in node.children), default=300)
            height = max((c.geometry["y"] + c.geometry["height"] + 16 for c in node.children), default=200)
            frame.setMinimumSize(width, height)
            return
        if node.layout == LayoutKind.HORIZONTAL:
            layout = QHBoxLayout(frame)
        elif node.layout == LayoutKind.GRID:
            layout = QGridLayout(frame)
        else:
            layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        for index, child in enumerate(node.children):
            rendered = self._render(child)
            if isinstance(layout, QGridLayout):
                layout.addWidget(rendered, index // 2, index % 2)
            else:
                layout.addWidget(rendered)
        if isinstance(layout, QVBoxLayout):
            layout.addStretch(1)
        elif not node.children:
            frame.setMinimumSize(220, 100)
