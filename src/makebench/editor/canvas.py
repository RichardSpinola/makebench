"""Prévia Qt editável com arraste, alças e páginas, sem executar ações do aplicativo."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from makebench.core.project import Component, ComponentKind, LayoutKind, Project
from makebench.ui.renderer import ImageLabel, create_control, place_children
from makebench.editor.drag import mime_for, read_payload

EDGES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


class ResizeHandle(QWidget):
    """Alça desenhada sobre o componente sem ocupar espaço no layout."""

    def __init__(self, edge: str, parent: QWidget) -> None:
        """Configura a direção da alça e seu cursor de redimensionamento."""
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self.setProperty("resizeEdge", edge)
        cursor = Qt.CursorShape.SizeFDiagCursor if edge in {"nw", "se"} else (
            Qt.CursorShape.SizeBDiagCursor if edge in {"ne", "sw"} else (
                Qt.CursorShape.SizeVerCursor if edge in {"n", "s"} else Qt.CursorShape.SizeHorCursor
            )
        )
        self.setCursor(cursor)
        self.setToolTip("Arraste para redimensionar. Esc cancela o gesto.")

    def paintEvent(self, _event) -> None:
        """Mantém as alças visíveis nos temas claro e escuro."""
        painter = QPainter(self)
        painter.setPen(QPen(self.palette().highlight().color(), 1))
        painter.setBrush(self.palette().base())
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class ComponentFrame(QFrame):
    """Superfície de um componente, com alvo de arraste e alças de seleção."""

    def __init__(self, canvas: PreviewCanvas, node_id: str) -> None:
        """Registra um alvo que delega alterações ao documento central."""
        super().__init__()
        self.canvas = canvas
        self.node_id = node_id
        self.handles: list[ResizeHandle] = []
        self.setAcceptDrops(True)
        self.setProperty("previewNode", True)

    def show_handles(self, visible: bool) -> None:
        """Cria alças somente para componentes livres selecionados."""
        if visible and not self.handles:
            for edge in EDGES:
                handle = ResizeHandle(edge, self)
                self.canvas._watch(handle, self.node_id)
                self.handles.append(handle)
        for handle in self.handles:
            handle.setVisible(visible)
            handle.raise_()
        self._position_handles()

    def _position_handles(self) -> None:
        """Reposiciona as oito alças quando o componente muda de tamanho."""
        for handle in self.handles:
            edge = handle.property("resizeEdge")
            x = 0 if "w" in edge else self.width() - 8 if "e" in edge else (self.width() - 8) // 2
            y = 0 if "n" in edge else self.height() - 8 if "s" in edge else (self.height() - 8) // 2
            handle.move(x, y)

    def resizeEvent(self, event) -> None:
        """Mantém as alças sobre a borda do componente durante o gesto."""
        super().resizeEvent(event)
        self._position_handles()

    def dragEnterEvent(self, event) -> None:
        """Valida a entrada e destaca o alvo compatível."""
        self.canvas.drag_on(self, event)

    def dragMoveEvent(self, event) -> None:
        """Atualiza a indicação de destino ao atravessar a superfície."""
        self.canvas.drag_on(self, event)

    def dragLeaveEvent(self, event) -> None:
        """Limpa o destaque de destino ao sair do componente."""
        self.setProperty("dropTarget", False)
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event) -> None:
        """Confirma uma inserção ou reorganização por arraste."""
        self.canvas.drop_on(self, event)


class PreviewCanvas(QFrame):
    """Renderiza o documento e emite edições completas para o histórico central."""

    component_selected = Signal(str)
    geometry_committed = Signal(str, object)
    drop_requested = Signal(object, str, int, object)
    nudge_requested = Signal(int, int)
    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Prepara seleção, estado efêmero das páginas e controle dos gestos."""
        super().__init__(parent)
        self._frames: dict[str, ComponentFrame] = {}
        self._tabs: dict[str, QTabWidget] = {}
        self._visible_pages: dict[str, str] = {}
        self._project: Project | None = None
        self._selected_id = ""
        self._gesture = None
        self.snap = 8
        self.can_drop = lambda _payload, _parent: False
        self.read_asset = lambda _source: b""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(10)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            'QFrame[previewNode="true"] { border: 1px solid transparent; border-radius: 4px; }'
            'QFrame[previewNode="true"][selectedNode="true"] { border: 1px solid palette(highlight); }'
            'QFrame[previewNode="true"][dropTarget="true"] { border: 2px dashed palette(highlight); }'
        )

    def set_project(self, project: Project) -> None:
        """Reconstrói a prévia e conserva páginas visíveis do mesmo documento."""
        if self._project is None or self._project.id != project.id:
            self._visible_pages = {}
        self._project = project
        self._gesture = None
        self._frames = {}
        self._tabs = {}
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

    def visible_page(self, node: Component) -> Component:
        """Retorna a página em edição sem alterar a página inicial do aplicativo."""
        node_id = self._visible_pages.get(node.id, node.properties.get("initial_page"))
        return next((child for child in node.children if child.id == node_id), node.children[0])

    def select(self, component_id: str) -> None:
        """Destaca a seleção e revela páginas ancestrais sem sujar o documento."""
        self._selected_id = component_id
        child = self._project.find(component_id)
        parent = self._project.parent_of(component_id)
        while parent:
            if parent.kind == ComponentKind.PAGES:
                self._visible_pages[parent.id] = child.id
                tabs = self._tabs[parent.id]
                tabs.blockSignals(True)
                tabs.setCurrentIndex(parent.children.index(child))
                tabs.blockSignals(False)
            child, parent = parent, self._project.parent_of(parent.id)
        for node_id, frame in self._frames.items():
            selected = node_id == component_id
            frame.setProperty("selectedNode", selected)
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            parent = self._project.parent_of(node_id)
            free = parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE
            frame.show_handles(bool(selected and free))
            frame.update()

    def _watch(self, widget: QWidget, component_id: str) -> None:
        """Associa controles ao nó de edição e preserva a navegação das abas."""
        widget.setProperty("componentId", component_id)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Seleciona, movimenta ou inicia arraste sem disparar ações do aplicativo."""
        node_id = watched.property("componentId")
        if not node_id:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.component_selected.emit(node_id)
            node = self._project.find(node_id)
            parent = self._project.parent_of(node_id)
            free = parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE
            self._gesture = {
                "id": node_id, "start": event.globalPosition().toPoint(),
                "geometry": dict(node.geometry), "free": bool(free),
                "edge": watched.property("resizeEdge") or "",
                "transfer": bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier),
                "parent_minimum": self._frames[parent.id].minimumSize() if parent else QSize(),
                "changed": False,
            }
            return True
        if event.type() == QEvent.Type.MouseMove and self._gesture:
            gesture = self._gesture
            delta = event.globalPosition().toPoint() - gesture["start"]
            if not gesture["changed"] and delta.manhattanLength() < QApplication.startDragDistance():
                return True
            if gesture["free"] and not gesture["transfer"]:
                self._update_gesture(delta)
            elif gesture["id"] != self._project.root.id:
                self._gesture = None
                drag = QDrag(self)
                frame = self._frames[gesture["id"]]
                offset = frame.mapFromGlobal(gesture["start"])
                drag.setMimeData(mime_for({
                    "mode": "move", "id": gesture["id"], "project": self._project.id,
                    "offset_x": max(0, offset.x()), "offset_y": max(0, offset.y()),
                }))
                drag.setPixmap(frame.grab())
                drag.setHotSpot(offset)
                drag.exec(Qt.DropAction.MoveAction)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton and self._gesture:
            gesture, self._gesture = self._gesture, None
            if gesture["changed"]:
                rect = self._frames[gesture["id"]].geometry()
                self.geometry_committed.emit(gesture["id"], {
                    "x": rect.x(), "y": rect.y(), "width": rect.width(), "height": rect.height(),
                })
            return True
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self.component_selected.emit(node_id)
            return True
        return super().eventFilter(watched, event)

    def _update_gesture(self, delta: QPoint) -> None:
        """Atualiza apenas a prévia; o documento recebe uma alteração ao soltar."""
        gesture = self._gesture
        frame = self._frames[gesture["id"]]
        original = gesture["geometry"]
        x, y, width, height = (original[key] for key in ("x", "y", "width", "height"))
        snap = lambda value: round(value / self.snap) * self.snap
        edge = gesture["edge"]
        if not edge:
            x, y = snap(x + delta.x()), snap(y + delta.y())
        else:
            minimum = frame.minimumSizeHint().expandedTo(frame.minimumSize()).expandedTo(QSize(24, 24))
            right, bottom = x + width, y + height
            if "e" in edge:
                width = max(minimum.width(), snap(width + delta.x()))
            if "s" in edge:
                height = max(minimum.height(), snap(height + delta.y()))
            if "w" in edge:
                x = max(0, min(right - minimum.width(), snap(x + delta.x())))
                width = right - x
            if "n" in edge:
                y = max(0, min(bottom - minimum.height(), snap(y + delta.y())))
                height = bottom - y
        rect = QRect(max(0, min(20000, x)), max(0, min(20000, y)), min(20000, width), min(20000, height))
        frame.setGeometry(rect)
        frame.parentWidget().setMinimumSize(
            max(frame.parentWidget().minimumWidth(), rect.right() + 17),
            max(frame.parentWidget().minimumHeight(), rect.bottom() + 17),
        )
        gesture["changed"] = True

    def keyPressEvent(self, event) -> None:
        """Permite ajuste fino por setas e cancela um gesto com Esc."""
        if event.key() == Qt.Key.Key_Escape and self._gesture:
            gesture, self._gesture = self._gesture, None
            frame = self._frames[gesture["id"]]
            frame.setGeometry(*(gesture["geometry"][key] for key in ("x", "y", "width", "height")))
            frame.parentWidget().setMinimumSize(gesture["parent_minimum"])
            event.accept()
            return
        vectors = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if event.key() in vectors:
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx, dy = vectors[event.key()]
            self.nudge_requested.emit(dx * step, dy * step)
            event.accept()
        elif event.key() == Qt.Key.Key_Delete:
            self.remove_requested.emit()
        else:
            super().keyPressEvent(event)

    def _drop_location(self, frame: ComponentFrame, point: QPoint, payload: dict):
        """Escolhe um contêiner/página e uma posição apropriada ao layout."""
        node = self._project.find(frame.node_id)
        kind = ComponentKind(payload["kind"]) if payload["mode"] == "new" else self._project.find(payload["id"]).kind
        if node.kind == ComponentKind.PAGES and kind != ComponentKind.PAGE:
            node = self.visible_page(node)
        elif not node.accepts(kind):
            node = self._project.parent_of(node.id)
        if node is None:
            return None
        target = self._frames[node.id]
        position = target.mapFromGlobal(frame.mapToGlobal(point))
        index = len(node.children)
        if node.layout != LayoutKind.FREE and node.kind != ComponentKind.PAGES:
            for i, child in enumerate(node.children):
                rect = self._frames[child.id].geometry()
                if (node.layout == LayoutKind.HORIZONTAL and position.x() < rect.center().x()) or (
                    node.layout == LayoutKind.VERTICAL and position.y() < rect.center().y()
                ) or (node.layout == LayoutKind.GRID and (
                    position.y() < rect.top() or (position.y() <= rect.bottom() and position.x() < rect.center().x())
                )):
                    index = i
                    break
        geometry = {
            "x": max(0, min(20000, position.x() - payload.get("offset_x", 0))),
            "y": max(0, min(20000, position.y() - payload.get("offset_y", 0))),
        } if node.layout == LayoutKind.FREE else None
        return node.id, index, geometry

    def drag_on(self, frame: ComponentFrame, event) -> None:
        """Mostra aceitação apenas para destinos válidos deste documento."""
        payload = read_payload(event.mimeData())
        if payload and (payload["mode"] == "new" or (
            payload.get("project") == self._project.id and self._project.find(payload.get("id"))
        )):
            location = self._drop_location(frame, event.position().toPoint(), payload)
            if location and self.can_drop(payload, location[0]):
                frame.setProperty("dropTarget", True)
                frame.style().unpolish(frame)
                frame.style().polish(frame)
                event.acceptProposedAction()
                return
        event.ignore()

    def drop_on(self, frame: ComponentFrame, event) -> None:
        """Solicita uma única edição depois de validar novamente o destino."""
        frame.setProperty("dropTarget", False)
        frame.style().unpolish(frame)
        frame.style().polish(frame)
        payload = read_payload(event.mimeData())
        if payload and (payload["mode"] == "new" or (
            payload.get("project") == self._project.id and self._project.find(payload.get("id"))
        )):
            location = self._drop_location(frame, event.position().toPoint(), payload)
            if location and self.can_drop(payload, location[0]):
                self.drop_requested.emit(payload, *location)
                event.acceptProposedAction()
                return
        event.ignore()

    def _render(self, node: Component) -> ComponentFrame:
        """Cria componentes Qt e seus recursos sem executar lógica do aplicativo."""
        frame = ComponentFrame(self, node.id)
        self._frames[node.id] = frame
        self._watch(frame, node.id)
        if node.kind == ComponentKind.PAGES:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(4, 4, 4, 4)
            tabs = QTabWidget()
            tabs.setMinimumHeight(220)
            self._tabs[node.id] = tabs
            for page in node.children:
                tabs.addTab(self._render(page), page.properties.get("title", "Página"))
            tabs.setCurrentIndex(node.children.index(self.visible_page(node)))
            tabs.currentChanged.connect(lambda index, node=node: self._page_changed(node, index))
            layout.addWidget(tabs)
            return frame
        if node.can_have_children:
            self._render_children(frame, node)
            return frame
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        widget = create_control(node, self.read_asset, editing=True)
        if isinstance(widget, QPlainTextEdit):
            self._watch(widget.viewport(), node.id)
        self._watch(widget, node.id)
        layout.addWidget(widget)
        return frame

    def _page_changed(self, node: Component, index: int) -> None:
        """Troca a página em edição sem alterar a página inicial salva."""
        if index >= 0:
            self._visible_pages[node.id] = node.children[index].id
            self.component_selected.emit(node.children[index].id)

    def _render_children(self, frame: ComponentFrame, node: Component) -> None:
        """Aplica layouts nativos ou coordenadas livres a componentes selecionáveis."""
        place_children(frame, node, self._render)
