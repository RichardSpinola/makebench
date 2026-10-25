# SPDX-License-Identifier: GPL-3.0-or-later
"""Native free-graph editor, with separate execution and value ports."""

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
from makebench.i18n import tr


PORT_LABELS = {
    "value": tr("Value"),
    "count": tr("Count"),
    "condition": tr("Condition"),
    "left": tr("Left"),
    "right": tr("Right"),
    "program": tr("Program"),
    "arguments": tr("Arguments"),
    "source": tr("Script"),
    "prompt": tr("Question"),
    "options": tr("Options"),
}


def wire_path(first, last):
    """Curve with horizontal controls; allows loops without ordering the graph by position."""
    distance = max(70, abs(last.x() - first.x()) * 0.5)
    path = QPainterPath(first)
    path.cubicTo(first + QPointF(distance, 0), last - QPointF(distance, 0), last)
    return path


class Port(QGraphicsEllipseItem):
    """Draggable port; type and direction are contracts, not just decoration."""

    def __init__(self, card, name, direction, kind, y):
        """Bind a connector to the stable identity of the node and input/output."""
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
            (tr("Value") if kind == "value" else tr("Execution"))
            + " · "
            + PORT_LABELS.get(name, name)
            + " · "
            + tr("drag to connect; right-click disconnects")
        )

    def mousePressEvent(self, event):
        """Start a temporary wire without changing the document during the gesture."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.card.panel.view.begin_wire(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Update only the temporary curve while dragging."""
        self.card.panel.view.move_wire(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        """Confirm a valid connection when dropped on a compatible port."""
        self.card.panel.view.finish_wire(event.scenePos())
        event.accept()

    def contextMenuEvent(self, event):
        """Disconnect without deleting the node; undo restores previous wires and values."""
        menu = QMenu()
        menu.addAction(tr("Disconnect"), lambda: self.card.panel.disconnect(self))
        menu.exec(event.screenPos())
        event.accept()


class GraphWire(QGraphicsPathItem):
    """Wire with a hit area larger than the stroke, with no selection box over the field."""

    def shape(self):
        """Make thin curves easy to select even at low zoom."""
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        """Highlight the curve itself when selected."""
        pen = QPen(self.pen())
        if self.isSelected():
            pen = QPen(QApplication.palette().highlight(), 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())


class NodeCard(QGraphicsObject):
    """Native card with named ports, multi-selection and an execution mark."""

    width = 250

    def __init__(self, panel, node):
        """Build a node's representation; properties stay in the document."""
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
            entries.append(("exec", "in", "exec", tr("Input")))
        for name in VALUE_INPUTS[node["op"]]:
            entries.append((name, "in", "value", PORT_LABELS.get(name, name)))
        outputs = [
            (
                name,
                "out",
                "exec",
                {
                    "true": tr("Yes"),
                    "false": tr("No"),
                    "body": tr("Repeat"),
                    "done": tr("Finish"),
                    "next": tr("Next"),
                }.get(name, name),
            )
            for name in execution_outputs(node)
        ]
        if output_type(node) is not None:
            outputs.append(("value", "out", "value", tr("Value")))
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
                target.properties.get("title", tr("Window")) if target else parameters["window"]
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
            node.get("comment") or tr("Double-click configures · drag connectors to create wires")
        )

    def label(self, text, x, y, muted=False):
        """Text in the desktop palette, with no theme of our own layered over Qt."""
        item = QGraphicsSimpleTextItem(text, self)
        palette = QApplication.palette()
        item.setBrush(palette.placeholderText() if muted else palette.text())
        item.setPos(x, y)
        return item

    def boundingRect(self):
        """Include the border and connectors in the repainted area."""
        return QRectF(-7, -2, self.width + 14, self.height + 4)

    def paint(self, painter, option, widget=None):
        """Tell selection, breakpoint and active node apart with small marks."""
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
        """Wires follow the card without committing history on every pixel."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.panel.update_wires()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """A multi-selection drag becomes a single undo operation."""
        super().mouseReleaseEvent(event)
        self.panel.schedule_layout()

    def mouseDoubleClickEvent(self, event):
        """Open configuration without running the node's content."""
        QTimer.singleShot(0, lambda: self.panel.configure(self.node["id"]))
        event.accept()

    def contextMenuEvent(self, event):
        """Local actions keep the selection and the debug origin by ID."""
        identifier = self.node["id"]
        menu = QMenu()
        menu.addAction(
            tr("Configure…"), lambda: QTimer.singleShot(0, lambda: self.panel.configure(identifier))
        )
        menu.addAction(
            tr("Breakpoint"),
            lambda: self.panel.breakpoint_requested.emit(self.panel.flow["id"], identifier),
        )
        if self.node["op"] != "event":
            menu.addAction(tr("Delete node"), lambda: self.panel.delete_ids({identifier}))
        menu.exec(event.screenPos())
        event.accept()


class GraphComment(QGraphicsTextItem):
    """Movable, editable note that never takes part in the runnable flow."""

    def __init__(self, panel, index, comment):
        """Keep the note's index to commit its text and position to the document."""
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
        """Edit the full comment, keeping line breaks."""

        def edit():
            """Open the dialog outside the callback of the item that will be rebuilt."""
            if not self.panel.flow or self.index >= len(self.panel.flow.get("graph_comments", [])):
                return
            text, ok = QInputDialog.getMultiLineText(
                self.panel,
                tr("Comment"),
                tr("Text"),
                self.panel.flow["graph_comments"][self.index]["text"],
            )
            if ok:
                self.panel.commit(lambda flow: flow["graph_comments"][self.index].update(text=text))

        QTimer.singleShot(0, edit)
        event.accept()


class GraphView(QGraphicsView):
    """Free area with wires, zoom, framing, selection and a creation menu."""

    def __init__(self, panel):
        """Keep only visual geometry; the panel commits the document."""
        super().__init__(QGraphicsScene(panel))
        self.panel = panel
        self.wire = None
        self.source = None
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QApplication.palette().base())
        self.setAccessibleName(tr("Behavior graph"))

    def begin_wire(self, port):
        """Show a temporary link and allow starting from either end."""
        self.source = port
        self.wire = QGraphicsPathItem()
        self.wire.setPen(QPen(QApplication.palette().highlight(), 2))
        self.wire.setZValue(5)
        self.scene().addItem(self.wire)

    def move_wire(self, point):
        """Never change or validate the project while the pointer moves."""
        if self.wire:
            self.wire.setPath(wire_path(self.source.scenePos(), point))

    def finish_wire(self, point):
        """Confirm only input/output pairs of the same port type."""
        if self.wire:
            self.scene().removeItem(self.wire)
        self.wire = None
        source = self.source
        self.source = None
        target = next((item for item in self.scene().items(point) if isinstance(item, Port)), None)
        if source and target and source is not target:
            self.panel.connect_ports(source, target)

    def contextMenuEvent(self, event):
        """Offer creation and comments at the clicked point of the empty field."""
        item = self.itemAt(event.pos())
        if item is not None:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        point = self.mapToScene(event.pos())
        menu.addAction(tr("Add node…"), lambda: self.panel.add_dialog(point))
        menu.addAction(tr("Comment…"), lambda: self.panel.add_comment(point))
        menu.addAction(tr("Fit"), self.panel.fit)
        menu.exec(event.globalPos())

    def wheelEvent(self, event):
        """Zoom under the pointer within limits, without moving document positions."""
        scale = self.transform().m11()
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if 0.15 <= scale * factor <= 3:
            self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        """The middle button pans the field without dragging the selected nodes."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Panning uses the scroll bars; connections stay in scene coordinates."""
        if event.buttons() & Qt.MouseButton.MiddleButton and hasattr(self, "_pan"):
            delta = event.position() - self._pan
            self._pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Also confirm the position of free comments."""
        super().mouseReleaseEvent(event)
        self.panel.schedule_layout()

    def keyPressEvent(self, event):
        """Delete acts on the selection; search opens the catalog without running actions."""
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
    """Transient representation of a behavior whose model belongs to the project."""

    changed = Signal(dict)
    breakpoint_requested = Signal(str, str)
    error = Signal(str)

    def __init__(self, get_source, parent=None):
        """Create local tools; callbacks send data to the IDE's validation and history."""
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
        button = QPushButton(tr("+ Node…"))
        button.clicked.connect(lambda: self.add_dialog())
        row.addWidget(button)
        comment = QPushButton(tr("Comment"))
        comment.clicked.connect(lambda: self.add_comment())
        row.addWidget(comment)
        for label, accessible, callback in [
            ("−", tr("Zoom out"), lambda: self.view.scale(0.8, 0.8)),
            ("+", tr("Zoom in"), lambda: self.view.scale(1.25, 1.25)),
            (tr("Fit"), tr("Fit"), self.fit),
        ]:
            button = QPushButton(label)
            button.setAccessibleName(accessible)
            button.setToolTip(accessible)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        self.hint = QLabel(
            tr("Drag connectors · double-click configures · middle button moves the field")
        )
        row.addWidget(self.hint)
        layout.addLayout(row)
        self.view = GraphView(self)
        layout.addWidget(self.view, 1)
        # Empty state: an event with no action yet gets a direct way to add the first node.
        self.empty_state = QPushButton(tr("+ Add the first node…"), self.view.viewport())
        self.empty_state.setToolTip(tr("Or right-click the empty area to add nodes and comments"))
        self.empty_state.clicked.connect(lambda: self.add_dialog())
        self.empty_state.hide()
        self.pending_payload = None
        self.commit_timer = QTimer(self)
        self.commit_timer.setSingleShot(True)
        self.commit_timer.timeout.connect(self.flush)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.commit_layout)

    def sync(self, project, flow):
        """Reconcile only when the graph changes, keeping zoom and selection when code refreshes."""
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
        empty = bool(flow) and len(flow["graph"]["nodes"]) <= 1
        self.empty_state.setVisible(empty)
        if empty:
            self.empty_state.adjustSize()
            self.empty_state.move(24, 24)

    def commit(self, mutate):
        """Validate a copy before handing over a transaction, never saving an invalid document."""
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
        """Confirm pending gestures before saving/switching/undoing, with no lost debounce."""
        self.commit_timer.stop()
        payload = self.pending_payload
        self.pending_payload = None
        if payload:
            self.changed.emit(payload)
        return True

    def rebuild_wires(self):
        """Draw real ports and bind each wire to the link that will be removed."""
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
        """Store ends by visual object; link data stays in the model."""
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
        """Reposition curves during the gesture without touching the project history."""
        for wire in self.wires:
            wire.setPath(wire_path(wire.source.scenePos(), wire.target.scenePos()))

    def connect_ports(self, first, last):
        """Reject types and value cycles; accept loops between execution ports."""
        if first.direction == "in":
            first, last = last, first
        if first.direction != "out" or last.direction != "in" or first.kind != last.kind:
            self.error.emit(tr("Connect an output to an input of the same type."))
            return
        source, target, port = first.card.node["id"], last.card.node["id"], last.name

        def change(flow):
            """Replace an input or output link without producing duplicates."""
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
        """Disconnect ports; value inputs get back an editable, valid literal."""
        identifier = port.card.node["id"]

        def change(flow):
            """Keep the document valid after removing input or output wires."""
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
        """A compatible literal when removing a link; undo restores the previous value."""
        return False if kind == "bool" else 1 if kind == "number" else [] if kind == "list" else ""

    def add_dialog(self, point=None):
        """Search every type and create the node at the requested location."""
        if not self.flow:
            return
        names = sorted((label, op) for op, label in LABELS.items() if op != "event")
        choice, ok = QInputDialog.getItem(
            self, tr("Add node"), tr("Search type"), [label for label, _ in names], 0, True
        )
        if not ok:
            return
        matches = [(label, op) for label, op in names if choice.casefold() in label.casefold()]
        exact = next((op for label, op in names if label == choice), None)
        if exact is None and len(matches) != 1:
            self.error.emit(tr("Choose a type from the list or refine the search."))
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
        """Add a free note that never takes part in the compiled program."""
        text, ok = QInputDialog.getMultiLineText(self, tr("Comment"), tr("Text"))
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
        """Defer confirmation until the gesture ends, avoiding deleting items in their callback."""
        if not self._loading:
            self.layout_timer.start(0)

    def commit_layout(self):
        """Group card and comment positions into one history operation."""
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
        """Remove nodes and incident wires, keeping the event node and remaining values."""

        def change(flow):
            """Replace removed references with compatible literals, leaving no orphans."""
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
        """Delete handles a multi-selection of nodes, wires and comments without losing the rest."""
        selected = self.view.scene().selectedItems()
        identifiers = {item.data(1) for item in selected if item.data(0) == "node"}
        if identifiers:
            self.delete_ids(identifiers)
            return
        wires = [item.key for item in selected if item.data(0) == "wire"]
        comments = {item.data(1) for item in selected if item.data(0) == "comment"}

        def change(flow):
            """Remove only the selected links or notes."""
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
        """Edit parameters by component name and JSON literals, with no typed IDs."""
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
                options = [
                    (r.properties.get("title", tr("Window")), r.id) for r in self.project.roots
                ]
            elif key == "state":
                options = [
                    (tr("Default"), "@default"),
                    *[(s["name"], s["id"]) for s in self.project.states.get(owner.id, [])],
                ]
            elif key == "scope":
                options = [
                    (tr("Project"), "project"),
                    (tr("Window"), "window"),
                    (tr("Local"), "local"),
                ]
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
                options = [
                    (tr("Text"), "text"),
                    (tr("Selection"), "checked"),
                    (tr("Progress"), "value"),
                ]
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
                    "component": tr("Component"),
                    "window": tr("Window"),
                    "state": tr("State"),
                    "scope": tr("Scope"),
                    "function": tr("Function"),
                    "operator": tr("Operator"),
                    "attribute": tr("Property"),
                    "kind": tr("Question"),
                    "name": tr("Name"),
                    "value": tr("JSON constant"),
                    "count": tr("Outputs"),
                    "admin": tr("Administrative"),
                    "close_current": tr("Close current window"),
                }.get(key, key),
                field,
            )
        for port, binding in node.get("inputs", {}).items():
            field = QLineEdit(
                json.dumps(binding["value"], ensure_ascii=False)
                if "value" in binding
                else tr("Connected to node {node}").format(node=binding["node"])
            )
            field.setReadOnly("node" in binding)
            inputs[port] = field
            form.addRow(PORT_LABELS.get(port, port) + " (JSON)", field)
        comment = QPlainTextEdit(node.get("comment", ""))
        comment.setMaximumHeight(80)
        form.addRow(tr("Comment"), comment)
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
            self.error.emit(tr("Invalid JSON value: {error}").format(error=exc))
            return
        self.commit(
            lambda flow: flow["graph"]["nodes"].__setitem__(
                next(i for i, n in enumerate(flow["graph"]["nodes"]) if n["id"] == identifier), node
            )
        )

    def focus_node(self, identifier, active=True):
        """Highlight the origin of an error/stop and keep the scene's current scale."""
        for key, card in self.cards.items():
            card.active = active and key == identifier
            card.update()
        card = self.cards.get(identifier)
        if card:
            self.view.ensureVisible(card, 60, 60)
            self.view.scene().clearSelection()
            card.setSelected(True)

    def fit(self):
        """Frame the real content without writing new coordinates to the project."""
        if self.view.scene().items():
            self.view.fitInView(
                self.view.scene().itemsBoundingRect().adjusted(-30, -30, 30, 30),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
