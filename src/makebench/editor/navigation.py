# SPDX-License-Identifier: GPL-3.0-or-later
"""Editing windows/states and the map derived from the neutral logic."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLabel,
)
from makebench.core.navigation import add_state, add_window, navigation_edges


from .map_panel import MapPanel
from makebench.i18n import tr


class NavigationMixin:
    """Keep the selected context without writing it to the application file."""

    def install_navigation_editor(self):
        """Add selectors, commands and the real navigation map."""
        self.active_window = self.project.root.id
        self.active_state = "@default"
        self.tree.active_root = lambda: self.active_window
        self.window_selector = QComboBox()
        self.window_selector.setAccessibleName(tr("Window being edited"))
        self.window_selector.setMaximumWidth(210)
        self.state_selector = QComboBox()
        self.state_selector.setAccessibleName(tr("State being edited"))
        self.state_selector.setMaximumWidth(170)
        self.context_bar.insertWidget(self.context_bar.actions()[0], self.window_selector)
        self.context_bar.insertWidget(self.context_bar.actions()[-1], self.state_selector)
        self.window_selector.currentIndexChanged.connect(self.window_selected)
        self.state_selector.currentIndexChanged.connect(self.state_selected)
        menu = self.menuBar().addMenu(tr("&Project"))
        for label, callback in [
            (tr("New window…"), self.new_window_dialog),
            (tr("New state…"), self.new_state_dialog),
            (tr("Set window as initial"), self.make_entry_window),
            (tr("Set state as initial"), self.make_initial_state),
            (tr("Rename state…"), self.rename_state_dialog),
            (tr("Restore selection from Default"), self.restore_default_properties),
            (tr("Remove state"), self.remove_state),
            (tr("Remove window"), self.remove_window),
        ]:
            action = menu.addAction(label)
            action.triggered.connect(callback)
        self.map_panel = MapPanel(self)
        self.tabs.addTab(self.map_panel, tr("Map"))
        self.sync_navigation()

    def sync_navigation(self):
        """Reconcile the selection with undo, loading and window removal."""
        if not hasattr(self, "window_selector"):
            return
        if self.active_window not in {r.id for r in self.project.roots}:
            self.active_window = self.project.root.id
            self.active_state = "@default"
        owner = self.project.window_of(self.selected_id)
        if owner and owner.id != self.active_window:
            self.active_window = owner.id
            self.active_state = "@default"
        from .controls import reconcile_combo

        empty = bool(self.project.metadata.get("empty_map"))
        self.window_selector.setEnabled(not empty)
        self.state_selector.setEnabled(not empty)
        if empty:
            reconcile_combo(self.window_selector, [(tr("No interface"), None)], None)
            reconcile_combo(self.state_selector, [], None)
            return
        reconcile_combo(
            self.window_selector,
            [(root.properties.get("title", tr("Window")), root.id) for root in self.project.roots],
            self.active_window,
        )
        states = self.project.states.get(self.active_window, [])
        if self.active_state not in {"@default", *[s["id"] for s in states]}:
            self.active_state = "@default"
        reconcile_combo(
            self.state_selector,
            [
                (
                    self.project.find(self.active_window).properties.get(
                        "default_state_name", tr("Default")
                    ),
                    "@default",
                ),
                *[(state["name"], state["id"]) for state in states],
            ],
            self.active_state,
        )

    def activate_window(self, window_id, state="@default"):
        """Change context after confirming block and field changes."""
        if not self._finish_field_edit():
            return
        self.active_window = window_id
        self.active_state = state
        self.selected_id = window_id
        self._refresh()

    def window_selected(self):
        """Receive an explicit choice of a real window."""
        if self.window_selector.currentData():
            self.activate_window(self.window_selector.currentData())

    def state_selected(self):
        """Reveal a variation, keeping the same window's selection valid."""
        if self.state_selector.currentData() is not None:
            if not self._finish_field_edit():
                return
            self.active_state = self.state_selector.currentData()
            self._refresh()

    def new_window_dialog(self):
        """Create an empty window or a copy of the current composition with new IDs."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("New interface"))
        form = QFormLayout(dialog)
        from PySide6.QtWidgets import QLineEdit

        empty = bool(self.project.metadata.get("empty_map"))
        name = QLineEdit(tr("Main screen") if empty else tr("New interface"))
        name.setObjectName("new_interface_name")
        base = QComboBox()
        base.addItem(tr("Blank"), None)
        if not empty:
            for root in self.project.roots:
                base.addItem(
                    tr("Duplicate {title}").format(
                        title=root.properties.get("title", tr("Window"))
                    ),
                    root.id,
                )
        form.addRow(tr("Name"), name)
        form.addRow(tr("Base"), base)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Create interface"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not name.text().strip():
            return

        def create():
            """Create the requested item with the dialog's validated values."""
            if self.project.metadata.pop("empty_map", False):
                root = self.project.root
                root.properties["title"] = name.text().strip()
            else:
                root = add_window(self.project, name.text(), base.currentData())
            self.active_window = root.id
            self.active_state = "@default"
            self.selected_id = root.id

        self._edit(create)

    def new_state_dialog(self):
        """Create an independent variation over the default structure."""
        from PySide6.QtWidgets import QLineEdit

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("New state"))
        form = QFormLayout(dialog)
        name = QLineEdit()
        base = QComboBox()
        base.addItem(tr("Default"), "@default")
        for state in self.project.states.get(self.active_window, []):
            base.addItem(state["name"], state["id"])
        base.setCurrentIndex(base.findData(self.active_state))
        form.addRow(tr("Name"), name)
        form.addRow(tr("Start from"), base)
        note = QLabel(
            tr("Copies the differences of the chosen step. The structure still comes from Default.")
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Create state"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def create():
            """Create the requested item with the dialog's validated values."""
            state = add_state(self.project, self.active_window, name.text(), base.currentData())
            self.active_state = state["id"]

        self._edit(create)

    def make_entry_window(self):
        """Explicitly set which window opens when the application starts."""
        self._edit(lambda: setattr(self.project, "entry_window", self.active_window))

    def make_initial_state(self):
        """Set the variation applied before the window's start event."""
        self._edit(
            lambda: self.project.find(self.active_window).properties.update(
                initial_state=self.active_state
            )
        )

    def rename_state_dialog(self):
        """Rename the variation, keeping IDs and every transition."""
        if self.active_state == "@default":
            root = self.project.find(self.active_window)
            name, ok = QInputDialog.getText(
                self,
                tr("Default composition name"),
                tr("Name of the initial step"),
                text=root.properties.get("default_state_name", tr("Default")),
            )
            if ok and name.strip():
                self._edit(lambda: root.properties.update(default_state_name=name.strip()))
            return
        state = next(
            s for s in self.project.states[self.active_window] if s["id"] == self.active_state
        )
        name, ok = QInputDialog.getText(self, tr("Rename state"), tr("Name"), text=state["name"])
        if ok and name.strip():
            self._edit(lambda: state.update(name=name.strip()))

    def restore_default_properties(self):
        """Remove only the selection's overrides in the active state."""
        if self.active_state == "@default":
            return

        def restore():
            """Remove the chosen differences, keeping the remaining data."""
            state = next(
                s for s in self.project.states[self.active_window] if s["id"] == self.active_state
            )
            state.get("overrides", {}).pop(self.selected_id, None)

        self._edit(restore)

    def remove_state(self):
        """Refuse to delete a state still referenced by the logic."""
        if self.active_state == "@default":
            return
        state_id = self.active_state
        for flow in self.project.workflows:
            if state_id in flow.get("states", []) or any(
                e["target"] == state_id for e in navigation_edges(self.project)
            ):
                self._show_error(tr("Review the flows that use this state before removing it."))
                return

        def remove():
            """Remove the selected data as a reversible operation."""
            self.project.states[self.active_window] = [
                s for s in self.project.states[self.active_window] if s["id"] != state_id
            ]
            if self.project.find(self.active_window).properties.get("initial_state") == state_id:
                self.project.find(self.active_window).properties["initial_state"] = "@default"
            self.active_state = "@default"

        self._edit(remove)

    def remove_window(self):
        """Protect the root and referenced windows; removal is reversible through history."""
        if len(self.project.roots) == 1:
            self._show_error(tr("Keep at least one window in the application."))
            return
        identifier = self.active_window
        ids = {n.id for n in self.project.find(identifier).walk()}
        if any(e["target"] == identifier for e in navigation_edges(self.project)) or any(
            f["event"]["component"] in ids for f in self.project.workflows
        ):
            self._show_error(tr("Review this window's flows and connections before removing it."))
            return

        def remove():
            """Remove the selected data as a reversible operation."""
            if identifier == self.project.root.id:
                self.project.root = self.project.windows.pop(0)
            else:
                self.project.windows = [r for r in self.project.windows if r.id != identifier]
            self.project.states.pop(identifier, None)
            self.project.variables = [
                v for v in self.project.variables if v.get("window") != identifier
            ]
            if self.project.entry_window == identifier:
                self.project.entry_window = self.project.root.id
            self.active_window = self.project.root.id
            self.active_state = "@default"
            self.selected_id = self.project.root.id

        self._edit(remove)
