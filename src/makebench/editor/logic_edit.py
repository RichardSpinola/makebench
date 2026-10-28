# SPDX-License-Identifier: GPL-3.0-or-later
"""Logic area: code tab, flows, block functions and modules."""

from __future__ import annotations

from copy import deepcopy

from makebench.core.logic import (
    create_block_function,
    create_flow,
    create_python_event,
    default_event_kind,
    find_unit,
    function_calls,
    set_module,
    validate,
)
from makebench.core.project import (
    ProjectError,
)
from makebench.i18n import tr


class LogicEditMixin:
    """Logic area: code tab, flows, block functions and modules. Mixed into MainWindow."""

    def _tab_changed(self, index):
        """Confirm blocks when leaving and start WebEngine only when needed."""
        if index != 1 and not self._finish_field_edit():
            self.tabs.setCurrentIndex(1)
            return
        if index == 1:
            self.logic.ensure_loaded()
            self.logic.sync()
        self._update_actions()

    def _source_changed(self):
        """Keep your own source independent of generation and the visual history."""
        self.source.text = self.source_editor.toPlainText()
        self.source_timer.start()
        self.setWindowModified(True)
        if hasattr(self, "code_files"):
            self.code_files.setTabText(1, tr("Your functions") + " •")

    def _source_analysis_ready(self):
        """Analyze after a typing pause, without refreshing every panel per key."""
        self._update_code()
        self._update_actions()

    def _update_code(self):
        """Show code and diagnostics without importing the functions file."""
        self.sync_code_workspace()
        self.logic.update_code()
        generated = self.logic.generated
        if self.generated_editor.toPlainText() != generated.text:
            self.generated_editor.setPlainText(generated.text)
        self.code_diagnostics.setText(
            "\n".join(generated.diagnostics)
            or tr("Functions receive ctx and value. Use the name in the “call function” block.")
        )
        label = (
            self.source.path.name
            if self.source.path
            else tr(".actions.py file created when saving")
        )
        self.source_label.setText(tr("Your functions · {file}").format(file=label))

    def edit_logic(self, component_id, kind=None):
        """Create or open the flow of the event selected in the interface."""
        if not self._finish_field_edit():
            return
        try:
            states = [self.active_state] if self.project.states.get(self.active_window) else None
            node = self.project.find(component_id)
            kind = kind or (node and default_event_kind(node))
            existing = [
                f
                for f in self.project.workflows
                if f.get("event", {}).get("component") == component_id
                and f["event"].get("kind") == kind
            ]
            flow = next(
                (f for f in existing if self.active_state in f.get("states", [])), None
            ) or next((f for f in existing if not f.get("states")), None)
            python = self.project.programming == "python"
            if flow is None and python:
                before = self.source_editor.toPlainText()
                flow, after = create_python_event(self.project, component_id, before, states, kind)
                if after != before:
                    stub = after[len(before.rstrip("\n")) :].strip("\n")
                    if before.strip():
                        self.source_editor.appendPlainText("\n\n" + stub)
                    else:
                        self.source_editor.setPlainText(stub + "\n")
            elif flow is None:
                flow = create_flow(self.project, component_id, states=states, kind=kind)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not open the logic"))
            return
        if python:
            if not any(f is flow for f in existing):
                self.history.push(self.project, tr("Create event"))
            self.sync_code_workspace()
            self.open_event_function(flow["id"])
            self._update_actions()
            return
        self.history.push(self.project, tr("Create event"))
        self.logic.sync(flow["id"])
        self.tabs.setCurrentIndex(1)
        self._update_code()
        self._update_actions()

    def save_block_function(self, function_id, name, params):
        """Create a block function or change its name and inputs, keeping its calls valid."""
        if not self.logic.flush():
            return
        if not function_id:
            try:
                function = create_block_function(self.project, name, params)
            except ProjectError as exc:
                self._show_error(exc, tr("Could not create the function"))
                return
            self.history.push(self.project, tr("Create function"))
            self.logic.sync(function["id"])
            self._update_code()
            self._update_actions()
            return
        function = find_unit(self.project, function_id)
        if function is None:
            return
        if len(params) != len(function["params"]) and function_calls(self.project, function_id):
            self._show_error(
                ProjectError(
                    tr("Remove the calls to this function before changing how many inputs it has.")
                ),
                tr("Could not change the function"),
            )
            return
        previous = deepcopy(function)
        function.update(name=name, params=params)
        try:
            validate(self.project)
        except ProjectError as exc:
            function.clear()
            function.update(previous)
            self._show_error(exc, tr("Could not change the function"))
            return
        self.history.push(self.project, tr("Change function"))
        self.logic.sync()
        self._update_code()
        self._update_actions()

    def move_to_module(self, unit_id, module):
        """Group an event or function under a block module (organization only)."""
        if not self.logic.flush():
            return
        try:
            set_module(self.project, unit_id, module)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not move to the module"))
            return
        self.history.push(self.project, tr("Move to module"))
        self.logic.sync()

    def remove_flow(self, flow_id):
        """Remove only the logic binding; undo restores blocks and comments."""
        functions = self.project.metadata.get("functions", [])
        if any(f["id"] == flow_id for f in functions):
            callers = function_calls(self.project, flow_id)
            if callers:
                self._show_error(
                    ProjectError(
                        tr("This function is still called by: {names}.").format(
                            names=", ".join(callers)
                        )
                    ),
                    tr("Could not remove the function"),
                )
                return

            def drop():
                """Remove the function; the list goes away with its last item."""
                remaining = [f for f in functions if f["id"] != flow_id]
                if remaining:
                    self.project.metadata["functions"] = remaining
                else:
                    self.project.metadata.pop("functions", None)

            self._edit(drop)
            return
        self._edit(
            lambda: setattr(
                self.project, "workflows", [f for f in self.project.workflows if f["id"] != flow_id]
            )
        )

    def rename_flow(self, flow_id, name):
        """Change the flow's label without re-identifying its blocks."""
        flow = next((f for f in self.project.workflows if f["id"] == flow_id), None)
        if flow and name.strip() and flow["name"] != name.strip():
            flow["name"] = name.strip()
            self.history.push(self.project, tr("Rename flow"))
            self.logic.sync()
            self._update_code()
            self._update_actions()

    def _receive_flow(self, data):
        """Validate the received neutral model; incomplete blocks stay as a draft."""
        flow = find_unit(self.project, data.get("flow"))
        if flow is None or not isinstance(data.get("workspace"), dict):
            return
        if (
            data.get("body") == flow.get("body")
            and data["workspace"] == flow.get("workspace", {})
            and data.get("errors", []) == flow.get("errors", [])
        ):
            return
        previous = deepcopy(flow)
        flow.update(
            body=data.get("body"), workspace=data["workspace"], errors=data.get("errors", [])
        )
        try:
            validate(self.project)
        except ProjectError as exc:
            flow.update(body=None, errors=[str(exc)])
            try:
                validate(self.project)
            except ProjectError:
                flow.clear()
                flow.update(previous)
                return
        self.history.push(self.project, tr("Edit blocks"))
        self._update_code()
        self._update_actions()
