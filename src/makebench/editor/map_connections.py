"""Single editor for real transitions, shared by dragging, keyboard and inspection."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QComboBox, QLabel, QCheckBox, QDialogButtonBox
from makebench.core.project import ComponentKind
from makebench.core.navigation import find_navigation_block
from .controls import reconcile_combo
from makebench.i18n import tr


class ConnectionDialog(QDialog):
    """Source, event, destination and behavior have human names and stable IDs."""

    def __init__(self, panel, source=None, target=None, edge=None):
        """Every destination can be represented by the runtime, with no illustrative links."""
        super().__init__(panel)
        self.panel = panel
        self.project = panel.window.project
        self.edge = edge
        self.setWindowTitle(tr("Edit transition") if edge else tr("Connect interfaces"))
        self.resize(570, 270)
        self.setMinimumWidth(500)
        form = QFormLayout(self)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)
        self.source = QComboBox()
        self.source.setObjectName("transition_source")
        self.event = QComboBox()
        self.event.setObjectName("transition_event")
        self.target = QComboBox()
        self.target.setObjectName("transition_target")
        self.closing = QCheckBox(tr("Close the source window when opening the destination"))
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        entries = []
        for root in self.project.roots:
            for state in [
                {"id": "@default", "name": tr("Default")},
                *self.project.states.get(root.id, []),
            ]:
                entries.append(
                    (
                        root.properties.get("title", tr("Interface")) + " › " + state["name"],
                        root.id + "|" + state["id"],
                    )
                )
        for label, key in entries:
            self.source.addItem(label, key)
        self.source.setCurrentIndex(
            max(0, self.source.findData(source or self.project.root.id + "|@default"))
        )
        form.addRow(tr("Source interface"), self.source)
        form.addRow(tr("When this happens"), self.event)
        form.addRow(tr("Destination"), self.target)
        form.addRow(tr("Behavior"), self.closing)
        form.addRow(self.notice)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            tr("Apply") if edge else tr("Connect")
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.source.currentIndexChanged.connect(self.sync)
        self.target.currentIndexChanged.connect(self.describe)
        self.event.currentIndexChanged.connect(self.describe)
        self.sync()
        if target:
            self.target.setCurrentIndex(max(0, self.target.findData(target)))
        if edge:
            flow, block = find_navigation_block(self.project, edge["flow"], edge["block"])
            if flow:
                self.event.setCurrentIndex(max(0, self.event.findData(flow["event"]["component"])))
            if block:
                self.closing.setChecked(block.get("parameters", block).get("close_current", False))
        self.describe()

    def sync(self):
        """States of another window are not offered as if they were navigable pages."""
        owner = self.source.currentData().split("|")[0]
        root = self.project.find(owner)
        selected = self.panel.window.selected_id
        if self.project.find(selected).kind != ComponentKind.BUTTON:
            selected = None
        events = [
            (tr("Click on {name}").format(name=n.properties.get("text") or n.display_name), n.id)
            for n in root.walk()
            if n.kind == ComponentKind.BUTTON
        ]
        events.append(
            (
                tr("Window {title} opens").format(
                    title=root.properties.get("title", tr("Interface"))
                ),
                root.id,
            )
        )
        current = self.event.currentData()
        reconcile_combo(
            self.event,
            events,
            current
            if current in [value for _, value in events]
            else selected
            if selected in [value for _, value in events]
            else events[0][1],
        )
        targets = []
        for destination in self.project.roots:
            states = [
                {"id": "@default", "name": tr("Default")},
                *self.project.states.get(destination.id, []),
            ]
            for state in states:
                if destination.id == owner or state["id"] == destination.properties.get(
                    "initial_state", "@default"
                ):
                    targets.append(
                        (
                            destination.properties.get("title", tr("Interface"))
                            + " › "
                            + state["name"],
                            destination.id + "|" + state["id"],
                        )
                    )
        current = self.target.currentData()
        reconcile_combo(
            self.target,
            targets,
            current if current in [value for _, value in targets] else targets[0][1],
        )
        self.describe()

    def describe(self):
        """The text describes the operation that will really be added to the event."""
        same = (
            bool(self.target.currentData())
            and self.source.currentData().split("|")[0] == self.target.currentData().split("|")[0]
        )
        self.closing.setEnabled(not same)
        self.notice.setText(
            tr("Change the state of the same window, keeping its structure.")
            if same
            else tr("Open another real system window in its initial state.")
        )

        flow = next(
            iter(
                sorted(
                    (
                        f
                        for f in self.project.editable_flows
                        if f["event"]["component"] == self.event.currentData()
                        and (
                            not f.get("states")
                            or self.source.currentData().split("|")[1] in f["states"]
                        )
                    ),
                    key=lambda f: not bool(f.get("states")),
                )
            ),
            None,
        )
        if flow and not flow.get("states"):
            self.notice.setText(
                self.notice.text() + " " + tr("The existing event runs in any state.")
            )
        elif flow and len(flow.get("states", [])) > 1:
            self.notice.setText(
                self.notice.text()
                + " "
                + tr("The action shares the existing event's state filter.")
            )
