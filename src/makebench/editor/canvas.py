"""Prévia Qt editável com arraste, alças e páginas, sem executar ações do aplicativo."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRubberBand,
    QSizePolicy,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
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
        cursor = (
            Qt.CursorShape.SizeFDiagCursor
            if edge in {"nw", "se"}
            else (
                Qt.CursorShape.SizeBDiagCursor
                if edge in {"ne", "sw"}
                else (
                    Qt.CursorShape.SizeVerCursor
                    if edge in {"n", "s"}
                    else Qt.CursorShape.SizeHorCursor
                )
            )
        )
        self.setCursor(cursor)
        self.setToolTip("Arraste para redimensionar. Esc cancela o gesto.")

    def paintEvent(self, _event) -> None:
        """Mantém as alças visíveis nos temas claro e escuro."""
        painter = QPainter(self)
        painter.setPen(QPen(self.palette().highlight().color(), 1))
        painter.setBrush(self.palette().base())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class LayoutHandle(QWidget):
    """Alça de espaçamento/margem que simula durante o gesto e confirma uma vez."""

    def __init__(self, canvas, parent, node_id, key, vertical=False):
        """Usa o layout renderizado como prévia, preservando o modelo até soltar."""
        super().__init__(parent)
        self.canvas = canvas
        self.node_id = node_id
        self.key = key
        self.vertical = vertical
        self.setFixedSize(28, 48) if vertical else self.setFixedSize(48, 28)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor if vertical else Qt.CursorShape.SizeVerCursor)
        self.setAccessibleName(
            "Ajustar " + ("espaçamento" if key == "spacing" else "margens internas")
        )
        self.origin = None
        self.value = 0

    def paintEvent(self, event):
        """Desenha a alça sobre a composição com a cor de seleção do tema."""
        painter = QPainter(self)
        painter.setPen(QPen(self.palette().highlight().color(), 3))
        if self.vertical:
            painter.drawLine(self.width() // 2, 6, self.width() // 2, self.height() - 6)
        else:
            painter.drawLine(6, self.height() // 2, self.width() - 6, self.height() // 2)

    def mousePressEvent(self, event):
        """Inicia uma edição que pode ser cancelada por Escape."""
        self.setFocus()
        self.origin = self.mapTo(self.canvas, event.position().toPoint())
        node = self.canvas._project.find(self.node_id)
        self.original = node.properties.get(self.key, 6 if self.key == "spacing" else 8)
        self.value = self.original
        event.accept()

    def mouseMoveEvent(self, event):
        """Atualiza o layout somente na representação visual do gesto."""
        if self.origin is None:
            return
        delta = self.mapTo(self.canvas, event.position().toPoint()) - self.origin
        self.value = max(
            0, min(2000, round(self.original + (delta.x() if self.vertical else delta.y())))
        )
        self.apply_preview(self.value)
        QToolTip.showText(event.globalPosition().toPoint(), str(self.value) + " px", self)

    def apply_preview(self, value):
        """Altera apenas o layout Qt temporário; salvar não observa esse estado."""
        layout = self.parentWidget().layout()
        if self.key == "spacing":
            layout.setSpacing(value)
        else:
            layout.setContentsMargins(value, value, value, value)

    def mouseReleaseEvent(self, event):
        """Confirma uma alteração de documento mesmo após vários movimentos."""
        if self.origin is None:
            return
        self.origin = None
        QToolTip.hideText()
        if self.value != self.original:
            self.canvas.layout_requested.emit(self.node_id, self.key, self.value)

    def keyPressEvent(self, event):
        """Cancela o gesto sem gerar histórico ou aplica passo fino por teclado."""
        if event.key() == Qt.Key.Key_Escape and self.origin is not None:
            self.apply_preview(self.original)
            self.origin = None
            QToolTip.hideText()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_Right, Qt.Key.Key_Up}:
            node = self.canvas._project.find(self.node_id)
            value = node.properties.get(self.key, 6 if self.key == "spacing" else 8)
            value = max(
                0,
                min(2000, value + (-1 if event.key() in {Qt.Key.Key_Left, Qt.Key.Key_Down} else 1)),
            )
            self.canvas.layout_requested.emit(self.node_id, self.key, value)
            event.accept()
            return
        super().keyPressEvent(event)


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
    inline_edit_requested = Signal()
    components_selected = Signal(object)
    layout_requested = Signal(str, str, object)
    tool_changed = Signal(str)
    image_dropped = Signal(str, str, int, object)
    context_requested = Signal(str, object)
    native_preview_ready = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Prepara seleção, estado efêmero das páginas e controle dos gestos."""
        super().__init__(parent)
        self._frames: dict[str, ComponentFrame] = {}
        self._tabs: dict[str, QTabWidget] = {}
        self._visible_pages: dict[str, str] = {}
        self._project: Project | None = None
        self._selected_id = ""
        self._gesture = None
        self._rubber = None
        self.insert_tool = None
        self._tool_ghost = None
        self._layout_handles = []
        self._guides = []
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
        # Controles Qt usam o próprio estilo instalado. GTK é desenhado em
        # processo separado pelo toolkit real, sem QSS para imitá-lo.
        self.setStyleSheet(
            'QFrame[previewNode="true"] { border:1px solid transparent; }'
            'QFrame[previewNode="true"][selectedNode="true"] { border:1px solid palette(highlight); }'
            'QFrame[previewNode="true"][dropTarget="true"] { border:2px dashed palette(highlight); }'
        )
        self._layout_handles = []
        self._guides = []
        self._layout_selection = None
        self._gesture = None
        self._frames = {}
        self._tabs = {}
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        from .window_chrome import QtWindowChrome

        self.title_bar = QtWindowChrome(project.root)
        self._watch(self.title_bar, project.root.id)
        self._layout.addWidget(self.title_bar)
        surface = self._render(project.root)
        surface.setMinimumSize(surface.minimumSize().expandedTo(QSize(360, 320)))
        surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._layout.addWidget(surface, 1)
        if project.application.get("backend", "qt") == "gtk":
            if not hasattr(self, "gtk_surface"):
                from .native_preview import GtkDesignSurface

                self.gtk_surface = GtkDesignSurface(self)
            self.gtk_surface.request()
        else:
            self.native_size = None
            if hasattr(self, "gtk_surface"):
                self.gtk_surface.hide()

    def resizeEvent(self, event):
        """Mantém a superfície GTK sobre a área de desenho ao ajustar zoom e tamanho."""
        super().resizeEvent(event)
        if hasattr(self, "gtk_surface"):
            self.gtk_surface.setGeometry(self.rect())

    def refresh_native_preview(self, force=False):
        """Atualiza a aparência visual após editar propriedades, sem eventos de execução."""
        if hasattr(self, "title_bar"):
            self.title_bar.update()
        if hasattr(self, "gtk_surface") and self._project.application.get("backend", "qt") == "gtk":
            self.gtk_surface.request(force)

    def close_native_preview(self):
        """A limpeza da janela encerra também o renderizador descartável GTK."""
        return self.gtk_surface.shutdown() if hasattr(self, "gtk_surface") else True

    def visible_page(self, node: Component) -> Component:
        """Retorna a página em edição sem alterar a página inicial do aplicativo."""
        node_id = self._visible_pages.get(node.id, node.properties.get("initial_page"))
        return next((child for child in node.children if child.id == node_id), node.children[0])

    def select(self, component_id: str) -> None:
        """Destaca a seleção e revela páginas ancestrais sem sujar o documento."""
        self._selected_id = component_id
        previous_pages = dict(self._visible_pages)
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
            if frame.property("selectedNode") != selected:
                frame.setProperty("selectedNode", selected)
                frame.style().unpolish(frame)
                frame.style().polish(frame)
            parent = self._project.parent_of(node_id)
            free = (
                parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE
            )
            frame.show_handles(bool(selected and free))
            frame.update()
        self.show_layout_handles(component_id)
        if hasattr(self, "gtk_surface"):
            self.gtk_surface.update()
        if previous_pages != self._visible_pages and hasattr(self, "gtk_surface"):
            self.gtk_surface.request()

    def show_layout_handles(self, identifier):
        """Revela alças apenas no contêiner automático selecionado."""
        parent = self._frames.get(identifier)
        signature = (identifier, id(parent))
        if signature == getattr(self, "_layout_selection", None):
            return
        self._layout_selection = signature
        for handle in self._layout_handles:
            handle.hide()
            handle.deleteLater()
        self._layout_handles = []
        node = self._project.find(identifier)
        if (
            not node
            or not node.can_have_children
            or node.kind == ComponentKind.PAGES
            or node.layout == LayoutKind.FREE
        ):
            return
        parent = self._frames[identifier]
        margin = LayoutHandle(self, parent, identifier, "padding")
        self._layout_handles.append(margin)
        if len(node.children) > 1:
            vertical = (
                node.layout == LayoutKind.HORIZONTAL
                or node.layout == LayoutKind.GRID
                and node.properties.get("columns", 2) > 1
            )
            spacing = LayoutHandle(self, parent, identifier, "spacing", vertical)
            self._layout_handles.append(spacing)

        def position():
            """Posiciona alças depois que o layout Qt calculou suas geometrias."""
            if self._frames.get(identifier) is not parent:
                return
            for handle in self._layout_handles:
                if handle.key == "padding":
                    handle.move(max(0, parent.width() // 2 - 24), 0)
                else:
                    first = self._frames[node.children[0].id].geometry()
                    second = self._frames[node.children[1].id].geometry()
                    if handle.vertical:
                        handle.move(
                            round((first.right() + second.left()) / 2) - 14,
                            max(0, first.center().y() - 24),
                        )
                    else:
                        handle.move(
                            max(0, first.center().x() - 24),
                            round((first.bottom() + second.top()) / 2) - 14,
                        )
                handle.show()
                handle.raise_()

        QTimer.singleShot(0, position)

    def select_many(self, identifiers):
        """Destaca a seleção compartilhada sem duplicar seu estado no documento."""
        self.native_selection = set(identifiers)
        if hasattr(self, "gtk_surface"):
            self.gtk_surface.update()
        for identifier, frame in self._frames.items():
            selected = identifier in identifiers
            if frame.property("selectedNode") != selected:
                frame.setProperty("selectedNode", selected)
                frame.style().unpolish(frame)
                frame.style().polish(frame)
                frame.update()

    def _watch(self, widget: QWidget, component_id: str) -> None:
        """Associa controles ao nó de edição e preserva a navegação das abas."""
        widget.setProperty("componentId", component_id)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Seleciona, movimenta ou inicia arraste sem disparar ações do aplicativo."""
        node_id = watched.property("componentId")
        if not node_id:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.ContextMenu:
            self.context_requested.emit(node_id, event.globalPos())
            return True
        if event.type() == QEvent.Type.MouseMove and self.insert_tool:
            self.tool_preview(watched, event)
            return True
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
            and self.insert_tool
        ):
            frame = self._frames[node_id]
            point = watched.mapTo(frame, event.position().toPoint())
            payload = {"mode": "new", "kind": self.insert_tool}
            location = self._drop_location(frame, point, payload)
            if location and self.can_drop(payload, location[0]):
                self.set_insert_tool(None)
                self.drop_requested.emit(payload, *location)
            return True
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self.component_selected.emit(node_id)
            self.inline_edit_requested.emit()
            return True
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.setFocus()
            self.component_selected.emit(node_id)
            node = self._project.find(node_id)
            parent = self._project.parent_of(node_id)
            free = (
                parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE
            )
            if (
                isinstance(watched, ComponentFrame)
                and node.can_have_children
                and node.layout == LayoutKind.FREE
                and not watched.property("resizeEdge")
            ):
                self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, watched)
                self._rubber_origin = event.position().toPoint()
                self._rubber_parent = node_id
                self._rubber.setGeometry(QRect(self._rubber_origin, QSize()))
                self._rubber.show()
                return True
            self._gesture = {
                "id": node_id,
                "start": watched.mapTo(self, event.position().toPoint()),
                "geometry": dict(node.geometry),
                "free": bool(free),
                "edge": watched.property("resizeEdge") or "",
                "transfer": bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier),
                "parent_minimum": self._frames[parent.id].minimumSize() if parent else QSize(),
                "changed": False,
            }
            return True
        if event.type() == QEvent.Type.MouseMove and self._rubber:
            point = watched.mapTo(self._rubber.parentWidget(), event.position().toPoint())
            self._rubber.setGeometry(QRect(self._rubber_origin, point).normalized())
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and self._rubber:
            rect = self._rubber.geometry()
            node = self._project.find(self._rubber_parent)
            identifiers = [
                child.id
                for child in node.children
                if rect.intersects(self._frames[child.id].geometry())
            ]
            self._rubber.hide()
            self._rubber.deleteLater()
            self._rubber = None
            if identifiers:
                self.components_selected.emit(identifiers)
            return True
        if event.type() == QEvent.Type.MouseMove and self._gesture:
            gesture = self._gesture
            # Qt já converteu o evento do viewport para o widget embutido.
            # Coordenadas globais (e outra divisão pelo zoom) são incorretas
            # no Wayland e podem variar quando o próprio componente se move.
            delta = watched.mapTo(self, event.position().toPoint()) - gesture["start"]
            if (
                not gesture["changed"]
                and delta.manhattanLength() < QApplication.startDragDistance()
            ):
                return True
            if gesture["free"] and not gesture["transfer"]:
                self._update_gesture(delta)
            elif gesture["id"] != self._project.root.id:
                self._gesture = None
                drag = QDrag(self)
                frame = self._frames[gesture["id"]]
                offset = frame.mapFrom(self, gesture["start"])
                drag.setMimeData(
                    mime_for(
                        {
                            "mode": "move",
                            "id": gesture["id"],
                            "project": self._project.id,
                            "offset_x": max(0, offset.x()),
                            "offset_y": max(0, offset.y()),
                        }
                    )
                )
                drag.setPixmap(frame.grab())
                drag.setHotSpot(offset)
                drag.exec(Qt.DropAction.MoveAction)
            return True
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._gesture
        ):
            gesture, self._gesture = self._gesture, None
            self.clear_guides()
            if gesture["changed"]:
                rect = self._frames[gesture["id"]].geometry()
                self.geometry_committed.emit(
                    gesture["id"],
                    {
                        "x": rect.x(),
                        "y": rect.y(),
                        "width": rect.width(),
                        "height": rect.height(),
                    },
                )
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
            minimum = (
                frame.minimumSizeHint().expandedTo(frame.minimumSize()).expandedTo(QSize(24, 24))
            )
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
        self.clear_guides()
        if not edge and not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier):
            parent = self._project.parent_of(gesture["id"])
            if parent:
                peers = [child.geometry for child in parent.children if child.id != gesture["id"]]
                for axis, length in [("x", width), ("y", height)]:
                    position = x if axis == "x" else y
                    size = "width" if axis == "x" else "height"
                    candidates = [
                        (
                            g[axis] + g[size] * anchor - position - length * own,
                            g[axis] + g[size] * anchor,
                        )
                        for g in peers
                        for anchor in (0, 0.5, 1)
                        for own in (0, 0.5, 1)
                    ]
                    if candidates:
                        delta, target = min(candidates, key=lambda pair: abs(pair[0]))
                        if abs(delta) <= 5:
                            if axis == "x":
                                x = round(x + delta)
                            else:
                                y = round(y + delta)
                            line = QFrame(frame.parentWidget())
                            line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                            line.setStyleSheet("background: palette(highlight); border: 0;")
                            if axis == "x":
                                line.setGeometry(round(target), 0, 1, frame.parentWidget().height())
                            else:
                                line.setGeometry(0, round(target), frame.parentWidget().width(), 1)
                            line.show()
                            line.raise_()
                            self._guides.append(line)
        rect = QRect(
            max(0, min(20000, x)), max(0, min(20000, y)), min(20000, width), min(20000, height)
        )
        frame.setGeometry(rect)
        frame.parentWidget().setMinimumSize(
            max(frame.parentWidget().minimumWidth(), rect.right() + 17),
            max(frame.parentWidget().minimumHeight(), rect.bottom() + 17),
        )
        gesture["changed"] = True

    def keyPressEvent(self, event) -> None:
        """Permite ajuste fino por setas e cancela um gesto com Esc."""
        native = getattr(self, "gtk_surface", None)
        if event.key() == Qt.Key.Key_Escape and native and (native.drag or native.rubber):
            native.cancel_gesture()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self.insert_tool:
            self.set_insert_tool(None)
            event.accept()
            return
        tools = {
            Qt.Key.Key_C: "container",
            Qt.Key.Key_T: "label",
            Qt.Key.Key_B: "button",
            Qt.Key.Key_I: "image",
        }
        if not (
            event.modifiers()
            & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        ):
            if event.key() in tools:
                self.set_insert_tool(tools[event.key()])
                event.accept()
                return
            if event.key() == Qt.Key.Key_V:
                self.set_insert_tool(None)
                event.accept()
                return
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                node = self._project.find(self._selected_id)
                parent = self._project.parent_of(self._selected_id)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and parent:
                    self.component_selected.emit(parent.id)
                elif node.children:
                    self.component_selected.emit(node.children[0].id)
                else:
                    self.inline_edit_requested.emit()
                event.accept()
                return
            if event.key() in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab}:
                parent = self._project.parent_of(self._selected_id)
                if parent:
                    index = next(
                        i for i, n in enumerate(parent.children) if n.id == self._selected_id
                    )
                    step = -1 if event.key() == Qt.Key.Key_Backtab else 1
                    self.component_selected.emit(
                        parent.children[(index + step) % len(parent.children)].id
                    )
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape and self._rubber:
            self._rubber.hide()
            self._rubber.deleteLater()
            self._rubber = None
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._gesture:
            gesture, self._gesture = self._gesture, None
            self.clear_guides()
            frame = self._frames[gesture["id"]]
            frame.setGeometry(*(gesture["geometry"][key] for key in ("x", "y", "width", "height")))
            frame.parentWidget().setMinimumSize(gesture["parent_minimum"])
            event.accept()
            return
        vectors = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if event.key() in vectors:
            step = self.snap * (10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
            dx, dy = vectors[event.key()]
            self.nudge_requested.emit(dx * step, dy * step)
            event.accept()
        elif event.key() == Qt.Key.Key_Delete:
            self.remove_requested.emit()
        else:
            super().keyPressEvent(event)

    def clear_guides(self):
        """Remove apenas guias temporárias de alinhamento do gesto atual."""
        for guide in self._guides:
            guide.hide()
            guide.deleteLater()
        self._guides = []

    def external_image(self, mime):
        """Reconhece a escolha explícita de um arquivo local por drag-and-drop."""
        if not mime.hasUrls() or len(mime.urls()) != 1:
            return None
        url = mime.urls()[0]
        if not url.isLocalFile():
            return None
        from pathlib import Path

        path = Path(url.toLocalFile())
        return (
            str(path) if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"} else None
        )

    def set_insert_tool(self, kind):
        """Arma inserção por clique; Esc ou Selecionar cancelam sem editar o projeto."""
        self.insert_tool = kind
        if self._tool_ghost:
            self._tool_ghost.hide()
        self.setCursor(Qt.CursorShape.CrossCursor if kind else Qt.CursorShape.ArrowCursor)
        self.tool_changed.emit(kind or "")
        self.setFocus()

    def tool_preview(self, watched, event):
        """Mostra fantasma em Livre ou linha no ponto de inserção automático."""
        frame = self._frames[watched.property("componentId")]
        point = watched.mapTo(frame, event.position().toPoint())
        payload = {"mode": "new", "kind": self.insert_tool}
        location = self._drop_location(frame, point, payload)
        if not location or not self.can_drop(payload, location[0]):
            if self._tool_ghost:
                self._tool_ghost.hide()
            return
        parent_id, index, geometry = location
        parent = self._frames[parent_id]
        node = self._project.find(parent_id)
        if self._tool_ghost is None:
            self._tool_ghost = QFrame(self)
            self._tool_ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._tool_ghost.setStyleSheet(
                "border: 2px dashed palette(highlight); background: palette(alternate-base);"
            )
        origin = parent.mapTo(self, QPoint())
        if geometry:
            rect = QRect(origin + QPoint(geometry["x"], geometry["y"]), QSize(140, 36))
        elif node.children:
            child = self._frames[node.children[min(index, len(node.children) - 1)].id]
            edge = child.geometry()
            if node.layout == LayoutKind.HORIZONTAL:
                x = edge.left() if index < len(node.children) else edge.right()
                rect = QRect(origin + QPoint(x, 8), QSize(2, max(24, parent.height() - 16)))
            else:
                y = edge.top() if index < len(node.children) else edge.bottom()
                rect = QRect(origin + QPoint(8, y), QSize(max(24, parent.width() - 16), 2))
        else:
            rect = QRect(origin + QPoint(8, 8), QSize(max(24, parent.width() - 16), 2))
        self._tool_ghost.setGeometry(rect)
        self._tool_ghost.show()
        self._tool_ghost.raise_()

    def _drop_location(self, frame: ComponentFrame, point: QPoint, payload: dict):
        """Escolhe um contêiner/página e uma posição apropriada ao layout."""
        node = self._project.find(frame.node_id)
        kind = (
            ComponentKind(payload["kind"])
            if payload["mode"] == "new"
            else self._project.find(payload["id"]).kind
        )
        if node.kind == ComponentKind.PAGES and kind != ComponentKind.PAGE:
            node = self.visible_page(node)
        elif not node.accepts(kind):
            node = self._project.parent_of(node.id)
        if node is None:
            return None
        target = self._frames[node.id]
        position = frame.mapTo(target, point)
        index = len(node.children)
        if node.layout != LayoutKind.FREE and node.kind != ComponentKind.PAGES:
            for i, child in enumerate(node.children):
                rect = self._frames[child.id].geometry()
                if (
                    (node.layout == LayoutKind.HORIZONTAL and position.x() < rect.center().x())
                    or (node.layout == LayoutKind.VERTICAL and position.y() < rect.center().y())
                    or (
                        node.layout == LayoutKind.GRID
                        and (
                            position.y() < rect.top()
                            or (position.y() <= rect.bottom() and position.x() < rect.center().x())
                        )
                    )
                ):
                    index = i
                    break
        geometry = (
            {
                "x": max(0, min(20000, position.x() - payload.get("offset_x", 0))),
                "y": max(0, min(20000, position.y() - payload.get("offset_y", 0))),
            }
            if node.layout == LayoutKind.FREE
            else None
        )
        return node.id, index, geometry

    def drag_on(self, frame: ComponentFrame, event) -> None:
        """Mostra aceitação apenas para destinos válidos deste documento."""
        payload = read_payload(event.mimeData())
        image = self.external_image(event.mimeData())
        if image:
            payload = {"mode": "new", "kind": "image"}
        if payload and (
            payload["mode"] == "new"
            or (
                payload.get("project") == self._project.id and self._project.find(payload.get("id"))
            )
        ):
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
        image = self.external_image(event.mimeData())
        if image:
            payload = {"mode": "new", "kind": "image"}
        if payload and (
            payload["mode"] == "new"
            or (
                payload.get("project") == self._project.id and self._project.find(payload.get("id"))
            )
        ):
            location = self._drop_location(frame, event.position().toPoint(), payload)
            if location and self.can_drop(payload, location[0]):
                if image:
                    self.image_dropped.emit(image, *location)
                else:
                    self.drop_requested.emit(payload, *location)
                event.acceptProposedAction()
                return
        event.ignore()

    def _render(self, node: Component) -> ComponentFrame:
        """Cria componentes Qt e seus recursos sem executar lógica do aplicativo."""
        frame = ComponentFrame(self, node.id)
        if not node.properties.get("visible", True):
            frame.hide()
        if node.can_have_children:
            frame.setEnabled(node.properties.get("enabled", True))
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
