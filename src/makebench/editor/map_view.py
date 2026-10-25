"""Gestos do Mapa: seleção, panorama, portas, zoom e teclado."""

from PySide6.QtCore import Qt, QPointF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QLabel, QPushButton, QMenu
from .map_items import MapNode, MapEdge, CARD_WIDTH
from .theme import manager, icon


class NavigationView(QGraphicsView):
    """Canvas de mapa com zoom, pan e conexão por arraste entre portas."""

    zoom_changed = Signal(float)

    def __init__(self, panel):
        """Configura interação sem substituir o modelo por itens gráficos."""
        super().__init__(panel)
        self.graph_scene = QGraphicsScene(self)
        self.setScene(self.graph_scene)
        self.panel = panel
        self.connection = None
        self.connection_item = None
        self._press_positions = {}
        self.dragging_card = None
        self.empty_hint = QLabel("Nenhuma interface\nCrie uma tela para começar.", self.viewport())
        self.empty_action = QPushButton(icon("add"), "Nova interface…", self.viewport())
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
        """Resolve o nó mesmo quando texto ou porta recebe o clique."""
        item = self.itemAt(point)
        while item and not isinstance(item, MapNode):
            item = item.parentItem()
        return item

    def mousePressEvent(self, event):
        """Inicia ligação apenas na porta, preservando o arraste do corpo do nó."""
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
        """Confirma ligação ou posição; uma edição corresponde a um Desfazer."""
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
                """A cena só pode ser reconstruída depois que Qt termina o evento dos itens."""
                if self.panel.window.project is project:
                    self.panel.window._edit(lambda: project.map_layout.update(moved), refresh=False)
                    self.panel.sync()

            QTimer.singleShot(0, commit)
        else:
            QTimer.singleShot(0, self.panel.selection_changed)

    def mouseMoveEvent(self, event):
        """A ligação acompanha o cursor antes da confirmação, sem criar blocos ainda."""
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
        """A orientação pertence ao viewport, sem aumentar nem sumir com o zoom."""
        super().resizeEvent(event)
        self.position_hint()

    def position_hint(self):
        """Centraliza o estado vazio sem criar objetos editáveis no mapa."""
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
        """O espaço de interfaces cria janelas pelo botão direito, inclusive vazio."""
        node = self.node_at(event.pos())
        menu = QMenu(self)
        point = self.mapToScene(event.pos())

        def create():
            """Após o diálogo, posiciona a nova interface no ponto escolhido."""
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

        menu.addAction("Criar interface aqui…", create)
        if node:
            self.panel.populate_context(menu, node.key)
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        """Permite remover uma conexão selecionada sem exigir gestos precisos."""
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
        """Ctrl+roda amplia o mapa; a roda normal continua rolando a área."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            scale = self.transform().m11() * factor
            if 0.25 <= scale <= 4:
                self.scale(factor, factor)
                self.zoom_changed.emit(self.transform().m11())
            event.accept()
        else:
            super().wheelEvent(event)
