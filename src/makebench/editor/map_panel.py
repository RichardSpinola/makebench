# SPDX-License-Identifier: GPL-3.0-or-later
"""Map of real interfaces and inspection of transitions derived from the same blocks."""

import json
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QToolButton,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QFormLayout,
    QPushButton,
    QMenu,
    QDialog,
    QMessageBox,
)
from makebench.core.logic import block_functions, called_functions, is_draft
from makebench.core.navigation import (
    navigation_edges,
    find_navigation_block,
    connect_navigation,
    remove_navigation_block,
    effective_edge_states,
)
from .map_items import MapNode, MapEdge, GroupHeader, CARD_WIDTH, CARD_HEIGHT
from .map_view import NavigationView
from .map_preview import ThumbnailCache
from .map_connections import ConnectionDialog
from .theme import manager, icon
from makebench.i18n import ntr, tr


def edge_path(source, target):
    """Route an arrow between two cards' top-left corners without crossing either card."""
    top = QPointF(CARD_WIDTH / 2, 0)
    bottom = QPointF(CARD_WIDTH / 2, CARD_HEIGHT)
    if abs(target.y() - source.y()) >= CARD_HEIGHT:
        # Another row: leave from the facing edge and enter the other card's facing edge.
        down = target.y() > source.y()
        start = source + (bottom if down else top)
        end = target + (top if down else bottom)
        bend = max(35, abs(end.y() - start.y()) / 2) * (1 if down else -1)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(0, bend), end - QPointF(0, bend), end)
        return path
    if target.x() > source.x():
        start = source + QPointF(CARD_WIDTH, 126)
        end = target + QPointF(0, 126)
        bend = max(35, (end.x() - start.x()) / 2)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(bend, 0), end - QPointF(bend, 0), end)
        return path
    # Same row, going back (or to itself): an arc over the row.
    start = source + top
    end = target + top
    lane = min(start.y(), end.y()) - 65
    path = QPainterPath(start)
    path.cubicTo(QPointF(start.x() + 35, lane), QPointF(end.x() - 35, lane), end)
    return path


LOGIC_ROLE = Qt.ItemDataRole.UserRole + 1


class MapPanel(QWidget):
    """Thumbnail composition, keyboard navigation and contextual inspection in one space."""

    def __init__(self, window):
        """Thumbnails and group preferences never become another data source for the app."""
        super().__init__()
        self.window = window
        self.nodes = {}
        self.edges = []
        self._signature = None
        self._fit_project = None
        self.collapsed = set()
        self.selected_key = None
        self._syncing = False
        self.previews = ThumbnailCache(self)
        self.previews.ready.connect(self.thumbnail_ready)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setContentsMargins(8, 4, 8, 0)
        self.summary = QLabel()
        row.addWidget(self.summary, 1)
        self.interface_actions = []
        for symbol, label, callback in [
            ("settings", tr("Application…"), window.application_settings),
            ("add", tr("New interface…"), window.new_window_dialog),
            ("logic", tr("Connect…"), self.connect_dialog),
            ("map", tr("Arrange"), self.organize),
            ("fit", tr("Fit all"), self.fit),
        ]:
            button = QToolButton()
            button.setIcon(icon(symbol))
            button.setProperty("makebenchIcon", symbol)
            button.setText(label)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setAutoRaise(True)
            button.clicked.connect(callback)
            if symbol in {"add", "logic"}:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if symbol not in {"settings", "add", "fit"}:
                self.interface_actions.append(button)
            row.addWidget(button)
        layout.addLayout(row)
        self.splitter = QSplitter()
        self.splitter.setHandleWidth(4)
        layout.addWidget(self.splitter, 1)
        self.outline_panel = QWidget()
        left = QVBoxLayout(self.outline_panel)
        left.setContentsMargins(6, 2, 2, 4)
        left.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search interfaces…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_outline)
        left.addWidget(self.search)
        self.outline = QTreeWidget()
        self.outline.setHeaderHidden(True)
        self.outline.setAccessibleName(tr("Interfaces, states and transitions"))
        self.outline.itemSelectionChanged.connect(self.outline_selected)
        self.outline.itemActivated.connect(self.outline_open)
        self.outline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.outline.customContextMenuRequested.connect(self.outline_menu)
        left.addWidget(self.outline)
        self.outline_panel.setMinimumWidth(170)
        self.splitter.addWidget(self.outline_panel)
        self.view = NavigationView(self)
        self.view.scene().selectionChanged.connect(self.selection_changed)
        self.splitter.addWidget(self.view)
        self.details = QWidget()
        self.details.setMinimumWidth(220)
        self.details.setMaximumWidth(330)
        self.detail_layout = QVBoxLayout(self.details)
        self.detail_layout.setContentsMargins(8, 8, 8, 8)
        self.detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.splitter.addWidget(self.details)
        self.details.hide()
        self.splitter.setSizes([195, 850, 260])
        self.hint = QLabel(
            tr("Select an interface or connection to inspect it. Double-click opens the Designer.")
        )
        self.hint.hide()
        self.view.setToolTip(self.hint.text())
        self._outline_items = {}
        stored = window.settings.value("workspace/map_panels")
        if stored:
            self.splitter.restoreState(stored)
        self.splitter.splitterMoved.connect(
            lambda *_: window.settings.setValue("workspace/map_panels", self.splitter.saveState())
        )

    def sync(self):
        """Topology and thumbnails are invalidated separately; selection and zoom survive."""
        project = self.window.project
        empty = bool(project.metadata.get("empty_map"))
        self.summary.setText(
            (project.application.get("name") or project.name)
            + " · "
            + project.application.get("backend", "qt").upper()
        )
        self.summary.setToolTip(tr("Map of the application's windows and states"))
        for action in self.interface_actions:
            action.setEnabled(not empty)
        if getattr(self, "_project", None) != project.id:
            self._project = project.id
            self.collapsed = set(
                self.window.settings.value("map/collapsed/" + project.id, [], type=list)
            )
            self.selected_key = None
        edges = navigation_edges(project)
        visual = {
            "roots": [
                (
                    r.id,
                    r.properties.get("title", tr("Interface")),
                    r.properties.get("initial_state", "@default"),
                    len(list(r.walk())),
                )
                for r in project.roots
            ],
            "states": {
                r.id: [(s["id"], s["name"]) for s in project.states.get(r.id, [])]
                for r in project.roots
            },
            "positions": project.map_layout,
            "entry": project.entry_window,
            "edges": edges,
            "logic": [
                (u["id"], u["name"], u.get("function"), called_functions(u))
                for u in [*project.editable_flows, *block_functions(project)]
            ],
            "collapsed": sorted(self.collapsed),
            "empty": empty,
            "theme": manager().tokens,
            "scale": manager().scale,
        }
        signature = json.dumps(visual, sort_keys=True)
        if signature != self._signature:
            self._signature = signature
            self.rebuild(edges, empty)
        if not empty:
            for key in self.nodes:
                owner, state = key.split("|", 1)
                self.previews.request(
                    key,
                    project.effective_root(owner, state),
                    project.application.get("backend", "qt"),
                    self.window.assets.read,
                )
        self.previews.retain(set(self.nodes))

    def rebuild(self, edges, empty):
        """Rebuild only the changed topology and keep an accessible native list of the map."""
        thumbnails = {key: (node.thumbnail, node.preview_error) for key, node in self.nodes.items()}
        selected_edge = next(
            ((line.edge["flow"], line.edge["block"]) for line in self.edges if line.isSelected()),
            None,
        )
        self.details.hide()
        self._syncing = True
        self.view.connection = None
        self.view.connection_item = None
        scene = self.view.scene()
        scene.clear()
        self.nodes = {}
        self.edges = []
        self.outline.clear()
        self._outline_items = {}
        scene.setBackgroundBrush(QColor(manager().tokens["canvas"]))
        self.view.empty_hint.setVisible(empty)
        self.view.empty_action.setVisible(empty)
        self.view.position_hint()
        self.outline_panel.setVisible(not empty)
        if empty:
            self.details.hide()
            scene.setSceneRect(0, 0, 1000, 650)
            self._syncing = False
            return
        project = self.window.project
        incoming = {e["target"] for e in edges if e["op"] == "open_window"}
        for row, root in enumerate(project.roots):
            states = [{"id": "@default", "name": tr("Default")}, *project.states.get(root.id, [])]
            title = root.properties.get("title", tr("Interface"))
            tree_root = QTreeWidgetItem([title])
            tree_root.setIcon(0, icon("window"))
            tree_root.setData(
                0,
                Qt.ItemDataRole.UserRole,
                root.id + "|" + root.properties.get("initial_state", "@default"),
            )
            self.outline.addTopLevelItem(tree_root)
            representative = (
                root.properties.get("initial_state", "@default")
                if root.id in self.collapsed
                else None
            )
            for column, state in enumerate(states):
                key = root.id + "|" + state["id"]
                item = QTreeWidgetItem(
                    [
                        state["name"]
                        + (
                            " · " + tr("initial")
                            if root.id == (project.entry_window or project.root.id)
                            and state["id"] == root.properties.get("initial_state", "@default")
                            else ""
                        )
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                tree_root.addChild(item)
                self._outline_items[key] = item
                if representative is not None and state["id"] != representative:
                    continue
                initial = root.id == (project.entry_window or project.root.id) and state[
                    "id"
                ] == root.properties.get("initial_state", "@default")
                issue = (
                    tr("No incoming transition from blocks.")
                    if root.id != (project.entry_window or project.root.id)
                    and root.id not in incoming
                    else ""
                )
                if any(
                    is_draft(f)
                    for f in project.editable_flows
                    if project.window_of(f["event"]["component"]).id == root.id
                ):
                    issue = tr("There is an incomplete behavior in this interface.")
                node = MapNode(
                    key,
                    title + "\n" + tr("Window · {state}").format(state=state["name"]),
                    project.map_layout.get(
                        key, [column * (CARD_WIDTH + 70), row * (CARD_HEIGHT + 135)]
                    ),
                    self.view,
                    initial,
                    issue,
                    len(list(root.walk())) - 1,
                )
                if key in thumbnails:
                    node.thumbnail, node.preview_error = thumbnails[key]
                scene.addItem(node)
                self.nodes[key] = node
            self._add_logic_items(tree_root, root.id)
            tree_root.setExpanded(True)
            members = [node for key, node in self.nodes.items() if key.startswith(root.id + "|")]
            bounds = members[0].sceneBoundingRect()
            for node in members[1:]:
                bounds = bounds.united(node.sceneBoundingRect())
            bounds = bounds.adjusted(-18, -42, 18, 18)
            group = scene.addRect(
                bounds,
                QPen(QColor(manager().tokens["border"]), 1),
                QBrush(QColor(manager().tokens["panel"])),
            )
            group.setZValue(-4)
            header = GroupHeader(
                ("▸ " if root.id in self.collapsed else "▾ ")
                + title
                + " · "
                + ntr("{count} state", "{count} states", len(states)).format(count=len(states)),
                root.id,
                self,
            )
            scene.addItem(header)
            header.setPos(bounds.left() + 12, bounds.top() + 10)
        functions = block_functions(project)
        if functions:
            group = QTreeWidgetItem([tr("Functions")])
            group.setIcon(0, icon("code"))
            self.outline.addTopLevelItem(group)
            for function in functions:
                group.addChild(self._logic_item(function, function))
            group.setExpanded(True)
        for edge in edges:
            self.add_edge(edge)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-70, -70, 70, 70))
        self._syncing = False
        self.filter_outline()
        if self.selected_key in self.nodes:
            self.nodes[self.selected_key].setSelected(True)
        elif selected_edge:
            line = next(
                (
                    line
                    for line in self.edges
                    if (line.edge["flow"], line.edge["block"]) == selected_edge
                ),
                None,
            )
            if line:
                line.setSelected(True)

    def _logic_item(self, unit, function=None):
        """One event or block function in the list; activating it opens it in Logic."""
        label = (
            f"{function['name']}({', '.join(function['params'])})"
            if function
            else unit["name"] + (f" → {unit['function']}()" if "function" in unit else "")
        )
        item = QTreeWidgetItem([label])
        item.setIcon(0, icon("code" if function else "logic"))
        item.setData(0, LOGIC_ROLE, unit["id"])
        return item

    def _add_logic_items(self, tree_root, owner):
        """List the window's events and, under each, the block functions it calls."""
        project = self.window.project
        functions = {f["id"]: f for f in block_functions(project)}
        for flow in project.editable_flows:
            if project.window_of(flow["event"]["component"]).id != owner:
                continue
            item = self._logic_item(flow)
            for target in called_functions(flow):
                if target in functions:
                    item.addChild(self._logic_item(functions[target], functions[target]))
            tree_root.addChild(item)

    def node_for(self, owner, state):
        """Collapsed states use the representative card, keeping real IDs in the inspector."""
        return self.nodes.get(owner + "|" + state) or next(
            (n for key, n in self.nodes.items() if key.startswith(owner + "|")), None
        )

    def add_edge(self, edge):
        """The arrow comes only from a runnable navigation block."""
        project = self.window.project
        for state in effective_edge_states(project, edge):
            source = self.node_for(edge["source"], state)
            if edge["op"] == "go_state":
                target = self.node_for(edge["source"], edge["target"])
            elif edge["op"] == "open_window":
                root = project.find(edge["target"])
                target = (
                    self.node_for(root.id, root.properties.get("initial_state", "@default"))
                    if root
                    else None
                )
            elif edge["op"] == "show_page":
                root = project.window_of(edge["target"])
                target = self.node_for(root.id, state) if root else None
            else:
                target = source
            if not source or not target:
                continue
            if source is target and edge["source"] in self.collapsed:
                continue
            line = MapEdge(edge_path(source.scenePos(), target.scenePos()), edge)
            self.view.scene().addItem(line)
            self.edges.append(line)

    def thumbnail_ready(self, key, image, error):
        """Update a single card, including after editing text or swapping an image."""
        node = self.nodes.get(key)
        if node:
            if not image.isNull():
                node.thumbnail = image
            node.preview_error = error
            node.update()
            node.setToolTip(
                node.label
                + ("\n" + error if error else "\n" + tr("Double-click opens the Designer."))
            )

    def selection_changed(self):
        """A single click inspects; opening the Designer stays an explicit action."""
        if self._syncing:
            return
        selected = self.view.scene().selectedItems()
        node = next((n for n in selected if isinstance(n, MapNode)), None)
        edge = next((n for n in selected if isinstance(n, MapEdge)), None)
        if node:
            self.selected_key = node.key
            self.outline.blockSignals(True)
            self.outline.setCurrentItem(self._outline_items.get(node.key))
            self.outline.blockSignals(False)
            # Opening the inspector on mouse-down would change a drag's coordinates.
            if not self.view.dragging_card:
                self.show_details(node=node)
        elif edge:
            self.selected_key = None
            self.show_details(edge=edge.edge)
        else:
            self.details.hide()

    def clear_details(self):
        """Destroy only the side inspector; thumbnails and scene stay available."""
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_details(self, node=None, edge=None):
        """Inspection shows source/event/destination and actions tied to the document."""
        self.clear_details()
        self.details.show()
        heading = QLabel(tr("Transition") if edge else tr("Interface"))
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        self.detail_layout.addWidget(heading)

        def label(text):
            """Read-only fields accept long names without widening the panel."""
            field = QLabel(text)
            field.setWordWrap(True)
            field.setTextFormat(Qt.TextFormat.PlainText)
            self.detail_layout.addWidget(field)

        def action(text, callback):
            """Each action uses the same commands as the Designer and Logic."""
            button = QPushButton(text)
            button.clicked.connect(callback)
            self.detail_layout.addWidget(button)

        if node:
            label(node.label)
            label(node.issue) if node.issue else None
            owner, state = node.key.split("|", 1)
            root = self.window.project.find(owner)
            label(
                f"{root.properties.get('width', 640)} × {root.properties.get('height', 480)} · {self.window.project.application.get('backend', 'qt').upper()}"
            )
            action(tr("Open Designer"), lambda: self.activate(node.key))
            action(tr("Edit on start"), lambda: self.open_logic_for_node(node.key))
            action(tr("Set as initial"), lambda: self.set_initial(node.key))
        else:
            flow, block = find_navigation_block(self.window.project, edge["flow"], edge["block"])
            if not flow or not block:
                return
            owner = self.window.project.find(edge["source"])
            label(owner.properties.get("title", tr("Interface")) + " → " + edge["event"])
            target = self.window.project.find(edge["target"]) if edge["target"] else None
            if block["op"] == "go_state":
                label(
                    tr("Change to")
                    + " "
                    + next(
                        (
                            s["name"]
                            for s in self.window.project.states.get(owner.id, [])
                            if s["id"] == edge["target"]
                        ),
                        tr("Default"),
                    )
                )
            elif target:
                label(tr("Destination: {name}").format(name=target.display_name))
            else:
                label(tr("Close this window"))
            if block["op"] in {"go_state", "open_window"}:
                action(tr("Edit transition…"), lambda: self.edit_edge(edge))
            action(tr("Show in Logic"), lambda: self.window.navigate_to_item("flow", edge["flow"]))
            action(tr("Show generated Python"), lambda: self.open_edge_code(edge))
            action(tr("Remove transition"), lambda: self.remove_edge(edge))

    def filter_outline(self, _text=None):
        """Search by window/state with visible ancestors and preserved identity."""
        query = self.search.text().casefold()
        for index in range(self.outline.topLevelItemCount()):
            root = self.outline.topLevelItem(index)
            visible = query in root.text(0).casefold()
            for i in range(root.childCount()):
                child = root.child(i)
                match = query in child.text(0).casefold() or query in root.text(0).casefold()
                child.setHidden(not match)
                visible = visible or match
            root.setHidden(not visible)

    def outline_selected(self):
        """The native list also selects collapsed cards, without requiring a drag."""
        if self._syncing:
            return
        item = self.outline.currentItem()
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if key:
            owner, state = key.split("|", 1)
            node = self.node_for(owner, state)
            if node:
                self.view.scene().clearSelection()
                node.setSelected(True)
                self.view.ensureVisible(node)

    def outline_open(self, item, _column=0):
        """Enter or activation opens exactly the selected composition."""
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.activate(key)
        elif item.data(0, LOGIC_ROLE):
            self.window.navigate_to_item("flow", item.data(0, LOGIC_ROLE))

    def outline_menu(self, point):
        """Keyboard/mouse alternative to gestures in the graphics area."""
        item = self.outline.itemAt(point)
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if key:
            menu = QMenu(self)
            self.populate_context(menu, key)
            menu.exec(self.outline.viewport().mapToGlobal(point))

    def populate_context(self, menu, key):
        """Contextual actions keep the scope of the window under the cursor."""
        owner, state = key.split("|", 1)
        menu.addAction(tr("Open Designer"), lambda: self.activate(key))
        menu.addAction(tr("Edit on start"), lambda: self.open_logic_for_node(key))
        menu.addAction(tr("Set as initial"), lambda: self.set_initial(key))
        menu.addSeparator()
        menu.addAction(tr("Refresh preview"), lambda: self.refresh_thumbnail(key))
        menu.addAction(tr("Expand/collapse states"), lambda: self.toggle_group(owner))
        menu.addAction(tr("Create state…"), lambda: self.create_state(key))
        menu.addAction(tr("Duplicate interface…"), lambda: self.duplicate_interface(owner))

    def create_state(self, key):
        """Select the owner before using the editor's same creation command."""
        self.window.activate_window(*key.split("|", 1))
        self.window.new_state_dialog()

    def duplicate_interface(self, owner):
        """Duplication uses the existing remapping of components, states and flows."""
        from PySide6.QtWidgets import QInputDialog
        from makebench.core.navigation import add_window

        title, ok = QInputDialog.getText(
            self,
            tr("Duplicate interface"),
            tr("Name"),
            text=self.window.project.find(owner).properties.get("title", tr("Interface"))
            + " — "
            + tr("copy"),
        )
        if ok and title.strip():
            self.window._edit(lambda: add_window(self.window.project, title, owner))

    def set_initial(self, key):
        """The start window and state change together in a single history entry."""
        owner, state = key.split("|", 1)

        def change():
            """Persist the real start destination, with no parallel map table."""
            self.window.project.entry_window = owner
            self.window.project.find(owner).properties["initial_state"] = state

        self.window._edit(change)

    def toggle_group(self, owner):
        """Collapsing changes only this project's visual preference."""
        if owner in self.collapsed:
            self.collapsed.remove(owner)
        else:
            self.collapsed.add(owner)
        self.window.settings.setValue(
            "map/collapsed/" + self.window.project.id, sorted(self.collapsed)
        )
        self.sync()

    def activate(self, key):
        """Double-click enters the card's exact state."""
        owner, state = key.split("|", 1)
        self.window.activate_window(owner, state)
        self.window.set_mode("design")

    def open_logic_for_node(self, key):
        """The opening logic is bound to the correct window."""
        owner, state = key.split("|", 1)
        self.window.activate_window(owner, state)
        self.window.edit_logic(owner)

    def open_edge_code(self, edge):
        """The generated line points to the block that produces this connection."""
        line = self.window.logic.generated.lines.get((edge["flow"], edge["block"]), 1)
        self.window.show_generated_line(line)

    def connect_dialog(self):
        """A single dialog replaces loose source and destination choices."""
        if self.nodes:
            self.connect_nodes(self.selected_key or next(iter(self.nodes)), None)

    def connect_nodes(self, source, target):
        """Dragging and the button use the same navigation editor and semantics."""
        dialog = ConnectionDialog(self, source, target)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.window._edit(
                lambda: connect_navigation(
                    self.window.project,
                    dialog.source.currentData(),
                    dialog.event.currentData(),
                    dialog.target.currentData(),
                    dialog.closing.isChecked(),
                )
            )

    def edit_edge(self, edge):
        """Editing a link changes the original block, even inside a condition."""
        flow, block = find_navigation_block(self.window.project, edge["flow"], edge["block"])
        if not block:
            return
        block = {**block, **block.get("parameters", {})}
        state = (edge["states"] or ["@default"])[0]
        source = edge["source"] + "|" + state
        target = (
            (edge["source"] + "|" + block["state"])
            if block["op"] == "go_state"
            else block["window"]
            + "|"
            + self.window.project.find(block["window"]).properties.get("initial_state", "@default")
        )
        dialog = ConnectionDialog(self, source, target, edge)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.window._edit(
                lambda: connect_navigation(
                    self.window.project,
                    dialog.source.currentData(),
                    dialog.event.currentData(),
                    dialog.target.currentData(),
                    dialog.closing.isChecked(),
                    (edge["flow"], edge["block"]),
                )
            )

    def remove_edge(self, edge):
        """Remove only the navigation action, with undo/redo support."""
        self.window._edit(
            lambda: remove_navigation_block(self.window.project, edge["flow"], edge["block"])
        )

    def organize(self):
        """Lay cards out in rows per window, keeping every link."""
        positions = {}
        for row, root in enumerate(self.window.project.roots):
            for col, state in enumerate(
                ["@default", *[s["id"] for s in self.window.project.states.get(root.id, [])]]
            ):
                positions[root.id + "|" + state] = [
                    col * (CARD_WIDTH + 70),
                    row * (CARD_HEIGHT + 135),
                ]
        self.window._edit(lambda: self.window.project.map_layout.update(positions), refresh=False)
        self.sync()
        self.fit()

    def fit(self):
        """Fit every card without making thumbnails disproportionately large."""
        if not self.nodes:
            self.view.resetTransform()
            self.view.centerOn(self.view.sceneRect().center())
        else:
            self.view.fitInView(
                self.view.scene().itemsBoundingRect().adjusted(-24, -24, 24, 24),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            scale = self.view.transform().m11()
            if scale > 1.15:
                self.view.scale(1.15 / scale, 1.15 / scale)
        self.view.zoom_changed.emit(self.view.transform().m11())

    def showEvent(self, event):
        """The first fit waits for the panels to get real sizes."""
        super().showEvent(event)
        if self._fit_project != self.window.project.id:
            self._fit_project = self.window.project.id
            QTimer.singleShot(0, self.fit)

    def refresh_edges(self):
        """Reposition links while dragging without rebuilding the native cards."""
        for line in self.edges:
            self.view.scene().removeItem(line)
        self.edges = []
        for edge in navigation_edges(self.window.project):
            self.add_edge(edge)

    def refresh_thumbnail(self, key):
        """A manual refresh only invalidates this composition, never running the application."""
        self.previews.invalidate(key)
        self.sync()
