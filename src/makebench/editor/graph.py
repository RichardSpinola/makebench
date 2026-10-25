"""Editor nativo de grafos livres, com portas de execução e valores distintas."""

from __future__ import annotations
from copy import deepcopy
import json
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from makebench.core.graph import (
    LABELS,
    VALUE_INPUTS,
    VALUE_OPS,
    execution_outputs,
    output_type,
    default_node,
    validate_graph,
)
from makebench.core.project import ProjectError, new_id


PORT_LABELS = {
    "value": "Valor",
    "count": "Quantidade",
    "condition": "Condição",
    "left": "Esquerda",
    "right": "Direita",
    "program": "Programa",
    "arguments": "Argumentos",
    "source": "Script",
    "prompt": "Pergunta",
    "options": "Opções",
}


def wire_path(first, last):
    """Curva com controles horizontais; permite retornos sem ordenar o grafo por posição."""
    distance = max(70, abs(last.x() - first.x()) * 0.5)
    path = QPainterPath(first)
    path.cubicTo(first + QPointF(distance, 0), last - QPointF(distance, 0), last)
    return path


class Port(QGraphicsEllipseItem):
    """Porta arrastável; tipo e direção são contratos, não apenas decoração."""

    def __init__(self, card, name, direction, kind, y):
        """Associa um conector à identidade estável do nó e da entrada/saída."""
        super().__init__(-6, -6, 12, 12, card)
        self.card = card
        self.name = name
        self.direction = direction
        self.kind = kind
        self.setPos(0 if direction == "in" else card.width, y)
        self.setZValue(4)
        palette = QApplication.palette()
        self.setBrush(palette.highlight() if kind == "value" else palette.windowText())
        self.setPen(QPen(palette.base(), 1))
        self.setToolTip(
            ("Valor" if kind == "value" else "Execução")
            + " · "
            + PORT_LABELS.get(name, name)
            + " · arraste para conectar; botão direito desconecta"
        )

    def mousePressEvent(self, event):
        """Inicia fio temporário sem alterar o documento durante o gesto."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.card.panel.view.begin_wire(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Atualiza somente a curva temporária durante o arraste."""
        self.card.panel.view.move_wire(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        """Confirma uma conexão válida ao soltar sobre uma porta compatível."""
        self.card.panel.view.finish_wire(event.scenePos())
        event.accept()

    def contextMenuEvent(self, event):
        """Desconecta sem apagar o nó; desfazer recupera fios e valores anteriores."""
        menu = QMenu()
        menu.addAction("Desconectar", lambda: self.card.panel.disconnect(self))
        menu.exec(event.screenPos())
        event.accept()


class GraphWire(QGraphicsPathItem):
    """Fio com área de toque maior que o traço, sem caixa de seleção sobre o campo."""

    def shape(self):
        """Facilita selecionar curvas finas mesmo com zoom reduzido."""
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        """Destaca a própria curva quando selecionada."""
        pen = QPen(self.pen())
        if self.isSelected():
            pen = QPen(QApplication.palette().highlight(), 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())


class NodeCard(QGraphicsObject):
    """Cartão nativo com portas nomeadas, seleção múltipla e marca de execução."""

    width = 250

    def __init__(self, panel, node):
        """Constrói a representação de um nó; propriedades continuam no documento."""
        super().__init__()
        self.panel = panel
        self.node = node
        self.ports = {}
        self.active = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setData(0, "node")
        self.setData(1, node["id"])
        self.setZValue(1)
        entries = []
        if node["op"] not in VALUE_OPS and node["op"] != "event":
            entries.append(("exec", "in", "exec", "Entrada"))
        for name in VALUE_INPUTS[node["op"]]:
            entries.append((name, "in", "value", PORT_LABELS.get(name, name)))
        outputs = [
            (
                name,
                "out",
                "exec",
                {
                    "true": "Sim",
                    "false": "Não",
                    "body": "Repetir",
                    "done": "Concluir",
                    "next": "Próximo",
                }.get(name, name),
            )
            for name in execution_outputs(node)
        ]
        if output_type(node) is not None:
            outputs.append(("value", "out", "value", "Valor"))
        self.height = max(112, 66 + max(len(entries), len(outputs)) * 24)
        self.title = self.label(LABELS[node["op"]], 10, 8)
        parameters = node.get("parameters", {})
        description = (
            parameters.get("function")
            or parameters.get("name")
            or parameters.get("state")
            or parameters.get("operator")
        )
        if "window" in parameters:
            target = panel.project.find(parameters["window"])
            description = (
                target.properties.get("title", "Janela") if target else parameters["window"]
            )
        if "component" in parameters:
            target = panel.project.find(parameters["component"])
            description = target.display_name if target else parameters["component"]
        if node["op"] == "constant":
            description = json.dumps(parameters.get("value"), ensure_ascii=False)
        self.label(
            str(description or node.get("comment", "")).split("\n")[0][:33], 10, 30, muted=True
        )
        for column in (entries, outputs):
            for index, (name, direction, kind, label) in enumerate(column):
                y = 65 + index * 24
                port = Port(self, name, direction, kind, y)
                self.ports[(direction, kind, name)] = port
                binding = node.get("inputs", {}).get(name, {})
                if direction == "in" and kind == "value" and "value" in binding:
                    label += " = " + json.dumps(binding["value"], ensure_ascii=False)[:15]
                text = self.label(
                    label, 12 if direction == "in" else 0, y - 9, muted=kind == "value"
                )
                if direction == "out":
                    text.setX(self.width - text.boundingRect().width() - 12)
        self.setToolTip(
            node.get("comment") or "Duplo clique configura · arraste conectores para criar fios"
        )

    def label(self, text, x, y, muted=False):
        """Texto com a paleta do desktop, sem tema próprio sobreposto ao Qt."""
        item = QGraphicsSimpleTextItem(text, self)
        palette = QApplication.palette()
        item.setBrush(palette.placeholderText() if muted else palette.text())
        item.setPos(x, y)
        return item

    def boundingRect(self):
        """Inclui borda e conectores na área repintada."""
        return QRectF(-7, -2, self.width + 14, self.height + 4)

    def paint(self, painter, option, widget=None):
        """Distingue seleção, ponto de parada e nó ativo com indicações pequenas."""
        palette = QApplication.palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(palette.button())
        painter.setPen(
            QPen(
                palette.highlight() if self.active or self.isSelected() else palette.mid(),
                3 if self.active else 2 if self.isSelected() else 1,
            )
        )
        painter.drawRoundedRect(QRectF(0, 0, self.width, self.height), 3, 3)
        painter.setPen(QPen(palette.mid(), 1))
        painter.drawLine(0, 52, self.width, 52)
        if self.node["id"] in self.panel.breakpoints:
            painter.setBrush(QBrush(Qt.GlobalColor.red))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.width - 17, 10, 8, 8)

    def itemChange(self, change, value):
        """Fios acompanham o cartão sem confirmar um histórico a cada pixel."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.panel.update_wires()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Um arraste de seleção múltipla vira uma única operação de desfazer."""
        super().mouseReleaseEvent(event)
        self.panel.schedule_layout()

    def mouseDoubleClickEvent(self, event):
        """Abre configuração sem executar o conteúdo do nó."""
        QTimer.singleShot(0, lambda: self.panel.configure(self.node["id"]))
        event.accept()

    def contextMenuEvent(self, event):
        """Ações locais preservam a seleção e a origem de depuração por ID."""
        identifier = self.node["id"]
        menu = QMenu()
        menu.addAction(
            "Configurar…", lambda: QTimer.singleShot(0, lambda: self.panel.configure(identifier))
        )
        menu.addAction(
            "Ponto de parada",
            lambda: self.panel.breakpoint_requested.emit(self.panel.flow["id"], identifier),
        )
        if self.node["op"] != "event":
            menu.addAction("Excluir nó", lambda: self.panel.delete_ids({identifier}))
        menu.exec(event.screenPos())
        event.accept()


class GraphComment(QGraphicsTextItem):
    """Anotação móvel e editável sem participar do fluxo executável."""

    def __init__(self, panel, index, comment):
        """Mantém índice da anotação para confirmar texto e posição no documento."""
        super().__init__(comment["text"])
        self.panel = panel
        self.index = index
        self.setTextWidth(260)
        self.setDefaultTextColor(QApplication.palette().placeholderText().color())
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setData(0, "comment")
        self.setData(1, index)

    def mouseDoubleClickEvent(self, event):
        """Edita comentário completo, preservando quebras de linha."""

        def edit():
            """Abre diálogo fora do callback do item que será reconstruído."""
            if not self.panel.flow or self.index >= len(self.panel.flow.get("graph_comments", [])):
                return
            text, ok = QInputDialog.getMultiLineText(
                self.panel,
                "Comentário",
                "Texto",
                self.panel.flow["graph_comments"][self.index]["text"],
            )
            if ok:
                self.panel.commit(lambda flow: flow["graph_comments"][self.index].update(text=text))

        QTimer.singleShot(0, edit)
        event.accept()


class GraphView(QGraphicsView):
    """Área livre com fios, zoom, enquadramento, seleção e menu de criação."""

    def __init__(self, panel):
        """Mantém apenas geometria visual; o documento é confirmado pelo painel."""
        super().__init__(QGraphicsScene(panel))
        self.panel = panel
        self.wire = None
        self.source = None
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QApplication.palette().base())
        self.setAccessibleName("Grafo de comportamento")

    def begin_wire(self, port):
        """Mostra ligação temporária e permite iniciar por qualquer extremidade."""
        self.source = port
        self.wire = QGraphicsPathItem()
        self.wire.setPen(QPen(QApplication.palette().highlight(), 2))
        self.wire.setZValue(5)
        self.scene().addItem(self.wire)

    def move_wire(self, point):
        """Não altera nem valida o projeto enquanto o ponteiro se move."""
        if self.wire:
            self.wire.setPath(wire_path(self.source.scenePos(), point))

    def finish_wire(self, point):
        """Confirma somente pares entrada/saída de mesmo tipo de porta."""
        if self.wire:
            self.scene().removeItem(self.wire)
        self.wire = None
        source = self.source
        self.source = None
        target = next((item for item in self.scene().items(point) if isinstance(item, Port)), None)
        if source and target and source is not target:
            self.panel.connect_ports(source, target)

    def contextMenuEvent(self, event):
        """Oferece criação e comentários no ponto clicado do campo vazio."""
        item = self.itemAt(event.pos())
        if item is not None:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        point = self.mapToScene(event.pos())
        menu.addAction("Adicionar nó…", lambda: self.panel.add_dialog(point))
        menu.addAction("Comentário…", lambda: self.panel.add_comment(point))
        menu.addAction("Enquadrar", self.panel.fit)
        menu.exec(event.globalPos())

    def wheelEvent(self, event):
        """Amplia sob o ponteiro com limites, sem mover posições do documento."""
        scale = self.transform().m11()
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if 0.15 <= scale * factor <= 3:
            self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        """Botão central desloca o campo sem arrastar os nós selecionados."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Pan usa barras de rolagem; conexões permanecem em coordenadas da cena."""
        if event.buttons() & Qt.MouseButton.MiddleButton and hasattr(self, "_pan"):
            delta = event.position() - self._pan
            self._pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Confirma também a posição de comentários livres."""
        super().mouseReleaseEvent(event)
        self.panel.schedule_layout()

    def keyPressEvent(self, event):
        """Excluir opera sobre seleção; buscar abre o catálogo sem executar ações."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.panel.delete_selected()
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.panel.add_dialog()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self.wire:
            self.finish_wire(QPointF(-100000, -100000))
            event.accept()
            return
        super().keyPressEvent(event)


class GraphPanel(QWidget):
    """Representação transitória de um comportamento cujo modelo pertence ao projeto."""

    changed = Signal(dict)
    breakpoint_requested = Signal(str, str)
    error = Signal(str)

    def __init__(self, get_source, parent=None):
        """Cria ferramentas locais; callbacks enviam dados para validação e histórico da IDE."""
        super().__init__(parent)
        self.get_source = get_source
        self.project = None
        self.flow = None
        self.cards = {}
        self.wires = []
        self.breakpoints = set()
        self._loading = False
        self._signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        button = QPushButton("+ Nó…")
        button.clicked.connect(lambda: self.add_dialog())
        row.addWidget(button)
        comment = QPushButton("Comentário")
        comment.clicked.connect(lambda: self.add_comment())
        row.addWidget(comment)
        for label, callback in [
            ("−", lambda: self.view.scale(0.8, 0.8)),
            ("+", lambda: self.view.scale(1.25, 1.25)),
            ("Enquadrar", self.fit),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        self.hint = QLabel(
            "Arraste conectores · duplo clique configura · botão central move o campo"
        )
        row.addWidget(self.hint)
        layout.addLayout(row)
        self.view = GraphView(self)
        layout.addWidget(self.view, 1)
        self.pending_payload = None
        self.commit_timer = QTimer(self)
        self.commit_timer.setSingleShot(True)
        self.commit_timer.timeout.connect(self.flush)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.commit_layout)

    def sync(self, project, flow):
        """Reconcilia apenas quando o grafo muda, preservando zoom e seleção ao atualizar código."""
        self.project = project
        self.flow = deepcopy(flow) if flow else None
        signature = (
            json.dumps(
                {key: flow.get(key) for key in ("id", "graph", "graph_layout", "graph_comments")},
                sort_keys=True,
            )
            if flow
            else None
        )
        if signature == self._signature:
            return
        selected = {item.data(1) for item in self.view.scene().selectedItems()}
        self._signature = signature
        self._loading = True
        self.view.scene().clear()
        self.cards = {}
        self.wires = []
        if flow:
            for index, node in enumerate(flow["graph"]["nodes"]):
                card = NodeCard(self, node)
                self.cards[node["id"]] = card
                self.view.scene().addItem(card)
                card.setPos(
                    *flow.get("graph_layout", {}).get(
                        node["id"], [40 + (index % 4) * 310, 60 + (index // 4) * 240]
                    )
                )
                card.setSelected(node["id"] in selected)
            for index, comment in enumerate(flow.get("graph_comments", [])):
                item = GraphComment(self, index, comment)
                self.view.scene().addItem(item)
                item.setPos(*comment["position"])
            self.rebuild_wires()
        self._loading = False
        bounds = self.view.scene().itemsBoundingRect()
        self.view.scene().setSceneRect(bounds.adjusted(-600, -400, 600, 400))

    def commit(self, mutate):
        """Valida uma cópia antes de entregar uma transação, sem salvar documento inválido."""
        if not self.flow:
            return
        candidate = deepcopy(self.flow)
        try:
            mutate(candidate)
            validate_graph(self.project, candidate)
        except (ProjectError, ValueError, TypeError, KeyError) as exc:
            self.error.emit(str(exc))
            return
        payload = {
            "flow": candidate["id"],
            **{
                key: candidate.get(key, []) if key == "graph_comments" else candidate.get(key, {})
                for key in ("graph", "graph_layout", "graph_comments")
            },
        }
        self.flow = deepcopy(candidate)
        self.pending_payload = payload
        self.commit_timer.start(0)

    def flush(self):
        """Confirma gestos pendentes antes de salvar/trocar/desfazer, sem debounce perdido."""
        self.commit_timer.stop()
        payload = self.pending_payload
        self.pending_payload = None
        if payload:
            self.changed.emit(payload)
        return True

    def rebuild_wires(self):
        """Desenha portas reais e associa cada fio à ligação que será removida."""
        for item in self.wires:
            self.view.scene().removeItem(item)
        self.wires = []
        if not self.flow:
            return
        for edge in self.flow["graph"]["edges"]:
            source = self.cards[edge["from"]].ports[("out", "exec", edge["out"])]
            target = self.cards[edge["to"]].ports[("in", "exec", "exec")]
            self.add_wire(source, target, ("exec", edge))
        for node in self.flow["graph"]["nodes"]:
            for port, binding in node.get("inputs", {}).items():
                if "node" in binding:
                    self.add_wire(
                        self.cards[binding["node"]].ports[("out", "value", "value")],
                        self.cards[node["id"]].ports[("in", "value", port)],
                        ("value", node["id"], port),
                    )

    def add_wire(self, source, target, key):
        """Armazena extremidades por objeto visual; dados da ligação continuam no modelo."""
        wire = GraphWire()
        wire.source = source
        wire.target = target
        wire.key = key
        wire.setZValue(-1)
        wire.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        wire.setData(0, "wire")
        wire.setPen(
            QPen(
                QApplication.palette().highlight()
                if source.kind == "value"
                else QApplication.palette().windowText(),
                2,
            )
        )
        self.view.scene().addItem(wire)
        self.wires.append(wire)
        wire.setPath(wire_path(source.scenePos(), target.scenePos()))

    def update_wires(self):
        """Reposiciona curvas durante o gesto sem tocar no histórico do projeto."""
        for wire in self.wires:
            wire.setPath(wire_path(wire.source.scenePos(), wire.target.scenePos()))

    def connect_ports(self, first, last):
        """Rejeita tipos e ciclos de valor; aceita retornos entre portas de execução."""
        if first.direction == "in":
            first, last = last, first
        if first.direction != "out" or last.direction != "in" or first.kind != last.kind:
            self.error.emit("Conecte uma saída a uma entrada do mesmo tipo.")
            return
        source, target, port = first.card.node["id"], last.card.node["id"], last.name

        def change(flow):
            """Substitui uma ligação de entrada ou saída sem produzir duplicatas."""
            if first.kind == "exec":
                flow["graph"]["edges"] = [
                    e
                    for e in flow["graph"]["edges"]
                    if (e["from"], e["out"]) != (source, first.name)
                ]
                flow["graph"]["edges"].append({"from": source, "out": first.name, "to": target})
            else:
                next(n for n in flow["graph"]["nodes"] if n["id"] == target)["inputs"][port] = {
                    "node": source,
                    "port": "value",
                }

        self.commit(change)

    def disconnect(self, port):
        """Desliga portas; entradas de valor recuperam um literal editável e válido."""
        identifier = port.card.node["id"]

        def change(flow):
            """Mantém o documento válido após remover fios de entrada ou saída."""
            if port.kind == "exec":
                flow["graph"]["edges"] = [
                    e
                    for e in flow["graph"]["edges"]
                    if not (
                        (
                            port.direction == "out"
                            and e["from"] == identifier
                            and e["out"] == port.name
                        )
                        or (port.direction == "in" and e["to"] == identifier)
                    )
                ]
            else:
                for node in flow["graph"]["nodes"]:
                    for name, binding in node.get("inputs", {}).items():
                        if (
                            port.direction == "in"
                            and node["id"] == identifier
                            and name == port.name
                        ) or (port.direction == "out" and binding.get("node") == identifier):
                            node["inputs"][name] = {
                                "value": self.default_input(VALUE_INPUTS[node["op"]][name])
                            }

        self.commit(change)

    def default_input(self, kind):
        """Literal compatível ao remover uma ligação; desfazer recupera o valor anterior."""
        return False if kind == "bool" else 1 if kind == "number" else [] if kind == "list" else ""

    def add_dialog(self, point=None):
        """Pesquisa todos os tipos e cria o nó no local solicitado."""
        if not self.flow:
            return
        names = sorted((label, op) for op, label in LABELS.items() if op != "event")
        choice, ok = QInputDialog.getItem(
            self, "Adicionar nó", "Pesquisar tipo", [label for label, _ in names], 0, True
        )
        if not ok:
            return
        matches = [(label, op) for label, op in names if choice.casefold() in label.casefold()]
        exact = next((op for label, op in names if label == choice), None)
        if exact is None and len(matches) != 1:
            self.error.emit("Escolha um tipo da lista ou refine a pesquisa.")
            return
        try:
            node = default_node(exact or matches[0][1], self.project, self.flow)
        except ProjectError as exc:
            self.error.emit(str(exc))
            return
        position = point or self.view.mapToScene(self.view.viewport().rect().center())
        self.commit(
            lambda flow: (
                flow["graph"]["nodes"].append(node),
                flow.setdefault("graph_layout", {}).update(
                    {node["id"]: [position.x(), position.y()]}
                ),
            )
        )

    def add_comment(self, point=None):
        """Adiciona uma anotação livre que nunca participa do programa compilado."""
        text, ok = QInputDialog.getMultiLineText(self, "Comentário", "Texto")
        if ok and text.strip():
            position = point or self.view.mapToScene(self.view.viewport().rect().center())
            self.commit(
                lambda flow: flow.setdefault("graph_comments", []).append(
                    {
                        "id": new_id("comment"),
                        "text": text,
                        "position": [position.x(), position.y()],
                    }
                )
            )

    def schedule_layout(self):
        """Adia confirmação até o gesto terminar, evitando apagar itens em seu callback."""
        if not self._loading:
            self.layout_timer.start(0)

    def commit_layout(self):
        """Agrupa posições de cartões e comentários em uma operação de histórico."""
        if not self.flow:
            return
        layout = {
            identifier: [card.pos().x(), card.pos().y()] for identifier, card in self.cards.items()
        }
        comments = deepcopy(self.flow.get("graph_comments", []))
        for item in self.view.scene().items():
            if item.data(0) == "comment":
                comments[item.data(1)]["position"] = [item.pos().x(), item.pos().y()]
        if layout == self.flow.get("graph_layout", {}) and comments == self.flow.get(
            "graph_comments", []
        ):
            return
        self.commit(lambda flow: flow.update(graph_layout=layout, graph_comments=comments))

    def delete_ids(self, identifiers):
        """Remove nós e fios incidentes, preservando o nó do evento e valores restantes."""

        def change(flow):
            """Substitui referências removidas por literais compatíveis, sem órfãos."""
            identifiers.discard(flow["graph"]["entry"])
            flow["graph"]["nodes"] = [
                n for n in flow["graph"]["nodes"] if n["id"] not in identifiers
            ]
            flow["graph"]["edges"] = [
                e
                for e in flow["graph"]["edges"]
                if e["from"] not in identifiers and e["to"] not in identifiers
            ]
            for identifier in identifiers:
                flow.get("graph_layout", {}).pop(identifier, None)
            for node in flow["graph"]["nodes"]:
                for name, binding in node.get("inputs", {}).items():
                    if binding.get("node") in identifiers:
                        node["inputs"][name] = {
                            "value": self.default_input(VALUE_INPUTS[node["op"]][name])
                        }

        self.commit(change)

    def delete_selected(self):
        """Excluir trata seleção múltipla de nós, fios e comentários sem perder os demais."""
        selected = self.view.scene().selectedItems()
        identifiers = {item.data(1) for item in selected if item.data(0) == "node"}
        if identifiers:
            self.delete_ids(identifiers)
            return
        wires = [item.key for item in selected if item.data(0) == "wire"]
        comments = {item.data(1) for item in selected if item.data(0) == "comment"}

        def change(flow):
            """Remove somente as ligações ou anotações selecionadas."""
            flow["graph_comments"] = [
                c for index, c in enumerate(flow.get("graph_comments", [])) if index not in comments
            ]
            for key in wires:
                if key[0] == "exec":
                    flow["graph"]["edges"].remove(key[1])
                else:
                    node = next(n for n in flow["graph"]["nodes"] if n["id"] == key[1])
                    node["inputs"][key[2]] = {
                        "value": self.default_input(VALUE_INPUTS[node["op"]][key[2]])
                    }

        self.commit(change)

    def configure(self, identifier):
        """Edita parâmetros por nomes de componentes e literais JSON, sem IDs digitados."""
        if not self.flow:
            return
        original = next((n for n in self.flow["graph"]["nodes"] if n["id"] == identifier), None)
        if original is None:
            return
        node = deepcopy(original)
        dialog = QDialog(self)
        dialog.setWindowTitle(LABELS[node["op"]])
        form = QFormLayout(dialog)
        fields = {}
        inputs = {}
        from makebench.core.logic import function_names

        owner = self.project.window_of(self.flow["event"]["component"])
        for key, value in node.get("parameters", {}).items():
            options = None
            editable = False
            if key == "component":
                options = [(n.display_name, n.id) for n in self.project.walk()]
            elif key == "window":
                options = [(r.properties.get("title", "Janela"), r.id) for r in self.project.roots]
            elif key == "state":
                options = [
                    ("Padrão", "@default"),
                    *[(s["name"], s["id"]) for s in self.project.states.get(owner.id, [])],
                ]
            elif key == "scope":
                options = [("Projeto", "project"), ("Janela", "window"), ("Local", "local")]
            elif key == "function":
                options = [(name, name) for name in function_names(self.get_source())[0]]
                editable = True
            elif key == "operator":
                options = [
                    (op, op)
                    for op in sorted(
                        __import__("makebench.core.graph", fromlist=["OPERATORS"]).OPERATORS
                    )
                ]
            elif key == "attribute":
                options = [("Texto", "text"), ("Seleção", "checked"), ("Progresso", "value")]
            elif key == "kind":
                options = [(v, v) for v in ("text", "choice", "file", "directory")]
            if options is not None:
                field = QComboBox()
                field.setEditable(editable)
                for label, data in options:
                    field.addItem(label, data)
                index = field.findData(value)
                if index >= 0:
                    field.setCurrentIndex(index)
                elif editable:
                    field.setEditText(str(value))
            elif type(value) is bool:
                field = QCheckBox()
                field.setChecked(value)
            else:
                field = QLineEdit(
                    json.dumps(value, ensure_ascii=False)
                    if key in {"value", "count"}
                    else str(value)
                )
            fields[key] = field
            form.addRow(
                {
                    "component": "Componente",
                    "window": "Janela",
                    "state": "Estado",
                    "scope": "Escopo",
                    "function": "Função",
                    "operator": "Operador",
                    "attribute": "Propriedade",
                    "kind": "Pergunta",
                    "name": "Nome",
                    "value": "Constante JSON",
                    "count": "Saídas",
                    "admin": "Administrativa",
                    "close_current": "Fechar janela atual",
                }.get(key, key),
                field,
            )
        for port, binding in node.get("inputs", {}).items():
            field = QLineEdit(
                json.dumps(binding["value"], ensure_ascii=False)
                if "value" in binding
                else "Conectado ao nó " + binding["node"]
            )
            field.setReadOnly("node" in binding)
            inputs[port] = field
            form.addRow(PORT_LABELS.get(port, port) + " (JSON)", field)
        comment = QPlainTextEdit(node.get("comment", ""))
        comment.setMaximumHeight(80)
        form.addRow("Comentário", comment)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            for key, field in fields.items():
                if isinstance(field, QComboBox):
                    node["parameters"][key] = (
                        field.currentText() if field.isEditable() else field.currentData()
                    )
                elif isinstance(field, QCheckBox):
                    node["parameters"][key] = field.isChecked()
                else:
                    node["parameters"][key] = (
                        json.loads(field.text()) if key in {"value", "count"} else field.text()
                    )
            for port, field in inputs.items():
                if not field.isReadOnly():
                    node["inputs"][port] = {"value": json.loads(field.text())}
            node["comment"] = comment.toPlainText()
        except (ValueError, TypeError) as exc:
            self.error.emit("Valor JSON inválido: " + str(exc))
            return
        self.commit(
            lambda flow: flow["graph"]["nodes"].__setitem__(
                next(i for i, n in enumerate(flow["graph"]["nodes"]) if n["id"] == identifier), node
            )
        )

    def focus_node(self, identifier, active=True):
        """Destaca origem de erro/parada e preserva a escala atual da cena."""
        for key, card in self.cards.items():
            card.active = active and key == identifier
            card.update()
        card = self.cards.get(identifier)
        if card:
            self.view.ensureVisible(card, 60, 60)
            self.view.scene().clearSelection()
            card.setSelected(True)

    def fit(self):
        """Enquadra o conteúdo real sem escrever coordenadas novas no projeto."""
        if self.view.scene().items():
            self.view.fitInView(
                self.view.scene().itemsBoundingRect().adjusted(-30, -30, 30, 30),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
