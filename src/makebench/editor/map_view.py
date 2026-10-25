"""Map gestures: selection, panning, ports, zoom and keyboard."""

from PySide6.QtCore import Qt, QPointF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QLabel, QPushButton, QMenu
from .map_items import MapNode, MapEdge, CARD_WIDTH
from .theme import manager, icon
from makebench.i18n import tr


class NavigationView(QGraphicsView):
    """Map canvas with zoom, pan and drag connections between ports."""

    zoom_changed = Signal(float)

    def __init__(self, panel):
        """Set up interaction without replacing the model with graphics items."""
        super().__init__(panel)
        self.graph_scene = QGraphicsScene(self)
        self.setScene(self.graph_scene)
        self.panel = panel
        self.connection = None
        self.connection_item = None
        self._press_positions = {}
        self.dragging_card = None
        self.empty_hint = QLabel(
            tr("No interface yet") + "\n" + tr("Create a screen to get started."), self.viewport()
        )
        self.empty_action = QPushButton(icon("add"), tr("New interface…"), self.viewport())
        self.empty_action.setFixedSize(164, 32)
        self.empty_action.clicked.connect(panel.window.new_window_dialog)
        self.empty_action.hide()
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_hint.hide()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def node_at(self, point):
        """Resolve the node even when the text or port receives the click."""
        item = self.itemAt(point)
        while item and not isinstance(item, MapNode):
            item = item.parentItem()
        return item

    def mousePressEvent(self, event):
        """Start a link only on the port, keeping the node body draggable."""
        self._press_positions = {
            key: [node.pos().x(), node.pos().y()] for key, node in self.panel.nodes.items()
        }
        node = self.node_at(event.position().toPoint())
        if node:
            local = node.mapFromScene(self.mapToScene(event.position().toPoint()))
            if local.x() > CARD_WIDTH - 12 and abs(local.y() - 126) < 16:
                self.connection = node.key
                event.accept()
                return
        self.dragging_card = (
            node.key if node and event.button() == Qt.MouseButton.LeftButton else None
        )
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Confirm a link or position; one edit corresponds to one Undo."""
        if self.connection:
            source = self.connection
            self.connection = None
            if self.connection_item:
                self.graph_scene.removeItem(self.connection_item)
                self.connection_item = None
            target = self.node_at(event.position().toPoint())
            if target and target.key != source:
                key = target.key
                QTimer.singleShot(0, lambda: self.panel.connect_nodes(source, key))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.dragging_card = None
        positions = {
            node.key: [node.pos().x(), node.pos().y()] for node in self.panel.nodes.values()
        }
        moved = {
            key: value
            for key, value in positions.items()
            if key in self._press_positions and self._press_positions[key] != value
        }
        self._press_positions = {}
        if moved:
            project = self.panel.window.project

            def commit():
                """The scene can only be rebuilt after Qt finishes the items' event."""
                if self.panel.window.project is project:
                    self.panel.window._edit(lambda: project.map_layout.update(moved), refresh=False)
                    self.panel.sync()

            QTimer.singleShot(0, commit)
        else:
            QTimer.singleShot(0, self.panel.selection_changed)

    def mouseMoveEvent(self, event):
        """The link follows the cursor before confirmation, without creating blocks yet."""
        if self.connection:
            source = self.panel.nodes.get(self.connection)
            if source:
                start = source.scenePos() + QPointF(CARD_WIDTH, 126)
                end = self.mapToScene(event.position().toPoint())
                path = QPainterPath(start)
                path.cubicTo(start + QPointF(80, 0), end - QPointF(80, 0), end)
                if self.connection_item is None:
                    self.connection_item = self.graph_scene.addPath(
                        path, QPen(QColor(manager().tokens["accent"]), 2, Qt.PenStyle.DashLine)
                    )
                else:
                    self.connection_item.setPath(path)
            event.accept()
            return
        super().mouseMoveEvent(event)
        if self._press_positions and event.buttons() & Qt.MouseButton.LeftButton:
            self.panel.refresh_edges()

    def resizeEvent(self, event):
        """Orientation belongs to the viewport and neither grows nor disappears with zoom."""
        super().resizeEvent(event)
        self.position_hint()

    def position_hint(self):
        """Center the empty state without creating editable objects on the map."""
        width = min(360, max(0, self.viewport().width() - 32))
        height = 110
        self.empty_hint.setGeometry(
            (self.viewport().width() - width) // 2,
            (self.viewport().height() - height) // 2 - 24,
            width,
            height,
        )
        self.empty_action.move(
            (self.viewport().width() - self.empty_action.width()) // 2,
            self.viewport().height() // 2 + 32,
        )

    def contextMenuEvent(self, event):
        """The interface area creates windows with the right button, even when empty."""
        node = self.node_at(event.pos())
        menu = QMenu(self)
        point = self.mapToScene(event.pos())

        def create():
            """After the dialog, place the new interface at the chosen point."""
            empty = bool(self.panel.window.project.metadata.get("empty_map"))
            before = set() if empty else {r.id for r in self.panel.window.project.roots}
            self.panel.window.new_window_dialog()
            root = next((r for r in self.panel.window.project.roots if r.id not in before), None)
            if root:
                self.panel.window._edit(
                    lambda: self.panel.window.project.map_layout.update(
                        {root.id + "|@default": [point.x(), point.y()]}
                    )
                )
                self.panel.sync()

        menu.addAction(tr("Create interface here…"), create)
        if node:
            self.panel.populate_context(menu, node.key)
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        """Allow removing a selected connection without requiring precise gestures."""
        if event.key() == Qt.Key.Key_Escape and self.connection:
            self.connection = None
            if self.connection_item:
                self.graph_scene.removeItem(self.connection_item)
                self.connection_item = None
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            selected = self.scene().selectedItems()
            edge = next(
                (item.data(0) for item in selected if isinstance(item, MapEdge) and item.data(0)),
                None,
            )
            if edge:
                self.panel.remove_edge(edge)
                event.accept()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Ctrl+wheel zooms the map; the plain wheel keeps scrolling the area."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            scale = self.transform().m11() * factor
            if 0.25 <= scale <= 4:
                self.scale(factor, factor)
                self.zoom_changed.emit(self.transform().m11())
            event.accept()
        else:
            super().wheelEvent(event)
