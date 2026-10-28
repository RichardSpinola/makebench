# SPDX-License-Identifier: GPL-3.0-or-later
"""Code and data tools: static inspection, never importing the user's functions."""

import ast
from copy import deepcopy
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QMenu,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from makebench.core.project import ProjectError
from makebench.i18n import ntr, tr
from makebench.core.source import default_names


class DevelopmentMixin:
    """Bind Logic and Code to static data and the selection's context."""

    def install_development(self):
        """Rearrange existing files into tabs and add a navigable outline."""
        self.logic.design_requested.connect(self.design_event_origin)
        self.generated_editor.origin_requested.connect(self.generated_origin)
        self.logic.duplicate_requested.connect(self.duplicate_flow_dialog)
        self.logic.search_requested.connect(self.search_block)
        self.logic.function_requested.connect(self.find_function_name)
        self.logic.filter_requested.connect(self.change_flow_filter)
        self.logic.full_code_requested.connect(self.show_generated_line)
        code_page = self.tabs.widget(2)
        layout = code_page.layout()
        old = code_page.findChild(QSplitter)
        generated = old.widget(0)
        own = old.widget(1)
        self.code_files = QTabWidget()
        self.code_files.addTab(generated, "generated.py · " + tr("read-only"))
        self.code_files.addTab(own, tr("Your functions"))
        self.code_files.setDocumentMode(True)
        self.code_files.setTabPosition(QTabWidget.TabPosition.South)
        for page in (code_page, generated, own):
            page.layout().setContentsMargins(4, 4, 4, 4)
            page.layout().setSpacing(4)
        self.code_files.setCurrentIndex(1)
        self.code_files.currentChanged.connect(lambda _: self._update_actions())
        self.function_outline = QListWidget()
        self.function_outline.setAccessibleName(tr("File functions and uses in blocks"))
        self.function_outline.itemActivated.connect(self.open_function)
        self.function_outline.itemClicked.connect(self.open_function)
        pane = QWidget()
        pl = QVBoxLayout(pane)
        pl.setContentsMargins(4, 4, 4, 4)
        pl.addWidget(QLabel(tr("File symbols")))
        self.function_search = QLineEdit()
        self.function_search.setPlaceholderText(tr("Filter functions…"))
        self.function_search.setClearButtonEnabled(True)
        self.function_search.textChanged.connect(self.filter_outline)
        pl.addWidget(self.function_search)
        pl.addWidget(self.function_outline)
        add = QPushButton(tr("+ New function"))
        add.clicked.connect(self.new_function)
        pl.addWidget(add)
        splitter = QSplitter()
        splitter.setHandleWidth(4)
        splitter.addWidget(self.code_files)
        splitter.addWidget(pane)
        splitter.setSizes([900, 260])
        index = layout.indexOf(old)
        layout.removeWidget(old)
        old.deleteLater()
        layout.insertWidget(index, splitter, 1)
        self.code_splitter = splitter
        for panel, key in [(self.logic.splitter, "logic"), (splitter, "code")]:
            stored = self.settings.value("workspace/" + key + "_panels")
            if stored:
                panel.restoreState(stored)
            panel.splitterMoved.connect(
                lambda *_, panel=panel, key=key: self.settings.setValue(
                    "workspace/" + key + "_panels", panel.saveState()
                )
            )
        self.code_position = QLabel()
        self.code_position.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.code_position)
        self.source_editor.cursorPositionChanged.connect(self.update_code_position)
        self.generated_editor.cursorPositionChanged.connect(self.update_code_position)
        self.code_files.currentChanged.connect(self.update_code_position)
        self.update_code_position()
        self.code_diagnostics.hide()
        for n in range(layout.count()):
            widget = layout.itemAt(n).widget()
            if isinstance(widget, QLabel) and widget not in (
                self.code_diagnostics,
                self.code_position,
            ):
                widget.hide()
        self.source_editor.textChanged.connect(self.sync_outline)
        data_page = QWidget()
        dl = QVBoxLayout(data_page)
        dl.setContentsMargins(4, 4, 4, 4)
        dl.setSpacing(4)
        dl.addWidget(self.data_list)
        actions = QHBoxLayout()
        for label, callback in [
            (tr("+ Variable"), self.variable_dialog),
            (tr("Edit"), self.edit_data_item),
            (tr("Remove"), self.remove_variable),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        dl.addLayout(actions)
        self.panel_docks["data"].setWidget(data_page)
        self.data_list.itemActivated.connect(lambda _: self.edit_data_item())
        self.sync_outline()
        from PySide6.QtWidgets import QToolBar
        from PySide6.QtCore import QSize
        from .theme import icon

        commands = QToolBar(tr("Blocks"))
        commands.setIconSize(QSize(16, 16))
        commands.setMovable(False)
        commands.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        commands.addAction(icon("search"), tr("Search block…"), self.search_block)
        templates = QToolButton()
        templates.setText(tr("Behavior"))
        templates.setToolTip(tr("Insert a behavior template with real blocks"))
        templates.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        templates.setIcon(icon("add"))
        templates.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(templates)
        from makebench.core.behaviors import TEMPLATES

        for kind, label in TEMPLATES:
            menu.addAction(label, lambda kind=kind: self.insert_behavior(kind))
        templates.setMenu(menu)
        self.behavior_templates = templates
        commands.addWidget(templates)
        self.python_action = commands.addAction(icon("code"), "Python")
        self.python_action.setCheckable(True)
        self.python_action.setToolTip(tr("Show or hide the Python generated by the blocks"))
        self.python_action.toggled.connect(self.toggle_logic_python)
        self.python_action.setChecked(
            str(self.settings.value("workspace/logic_python", False)).lower() == "true"
        )
        self.toggle_logic_python(self.python_action.isChecked())
        self.logic.edit_text_action = commands.addWidget(self.logic.edit_text)
        self.logic._sync_edit_text()
        # One bar: the event on the left, these tools in the middle, the editor on the right.
        commands.setStyleSheet("QToolBar { border: 0; background: transparent; }")
        self.logic.top_row.insertWidget(self.logic.tools_index, commands)
        # Bash highlighting in the drawer editor; applying it stays explicit.
        self.script_editor.highlighter.language = "bash"
        self.script_editor.highlighter.rehighlight()
        self.install_code_workspace()

    def change_flow_filter(self, flow_id, states):
        """Change only the filter, with overlap validation and history."""

        def change():
            """Update the requested field inside the edit transaction."""
            flow = next(f for f in self.project.workflows if f["id"] == flow_id)
            if states:
                flow["states"] = states
            else:
                flow.pop("states", None)

        self._edit(change)

    def show_generated_line(self, line):
        """Open the complete file keeping the handler's line in focus."""
        self.set_mode("code")
        self.code_files.setCurrentIndex(0)
        self.generated_editor.show_line(line)

    def sync_outline(self):
        """Read signatures and docstrings with AST; invalid files stay editable."""
        if not hasattr(self, "function_outline"):
            return
        editor = (
            self.active_code_editor() if hasattr(self, "module_editors") else self.source_editor
        )
        signature = (
            id(editor),
            editor.toPlainText(),
            json.dumps(self.project.workflows, sort_keys=True),
        )
        if signature == getattr(self, "_outline_signature", None):
            return
        self._outline_signature = signature
        self.function_outline.clear()
        try:
            tree = ast.parse(editor.toPlainText())
        except (SyntaxError, ValueError):
            return

        def uses(value, name):
            """Count static references without importing Python functions."""
            if isinstance(value, dict):
                return int(
                    value.get("op") == "call"
                    and value.get("parameters", value).get("function") == name
                ) + sum(uses(v, name) for v in value.values())
            if isinstance(value, list):
                return sum(uses(v, name) for v in value)
            return 0

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                count = sum(uses(f.get("body"), node.name) for f in self.project.workflows)
                signature = (
                    tr("class") + " " + node.name
                    if isinstance(node, ast.ClassDef)
                    else node.name + "(" + ", ".join(a.arg for a in node.args.args) + ")"
                )
                item = QListWidgetItem(
                    signature
                    + (
                        " · " + ntr("{count} block", "{count} blocks", count).format(count=count)
                        if editor is self.source_editor
                        else ""
                    )
                )
                item.setData(Qt.ItemDataRole.UserRole, node.lineno)
                item.setToolTip(ast.get_docstring(node) or tr("No description."))
                self.function_outline.addItem(item)
        self.filter_outline()

    def update_code_position(self, _index=None):
        """Show the line and column in the active file without stealing focus or changing text."""
        editor = (
            self.active_code_editor()
            if hasattr(self, "module_editors")
            else self.generated_editor
            if self.code_files.currentIndex() == 0
            else self.source_editor
        )
        cursor = editor.textCursor()
        self.code_position.setText(
            tr("Line {line} · Column {column}").format(
                line=cursor.blockNumber() + 1, column=cursor.positionInBlock() + 1
            )
        )

    def filter_outline(self, _text=None):
        """Filter functions locally, keeping the file and the text selection intact."""
        if not hasattr(self, "function_search"):
            return
        text = self.function_search.text().casefold()
        for index in range(self.function_outline.count()):
            item = self.function_outline.item(index)
            item.setHidden(text not in item.text().casefold())

    def open_function(self, item):
        """Find the definition without running the file."""
        self.active_code_editor().show_line(item.data(Qt.ItemDataRole.UserRole))

    def new_function(self):
        """Insert an independent definition, keeping all of your own text."""
        name, ok = QInputDialog.getText(self, tr("New function"), tr("Python name"))
        if not ok:
            return
        import keyword

        if not name.isidentifier() or keyword.iskeyword(name) or name.startswith("_"):
            self._show_error(
                tr("Use a valid Python name, with no spaces and not starting with an underscore.")
            )
            return
        editor = self.active_code_editor()
        if editor.isReadOnly():
            self.code_files.setCurrentIndex(1)
            editor = self.source_editor
        try:
            names = [
                n.name
                for n in ast.parse(editor.toPlainText()).body
                if isinstance(n, ast.FunctionDef)
            ]
        except SyntaxError:
            self._show_error(tr("Fix the syntax before inserting a function with the assistant."))
            return
        if name in names:
            self._show_error(tr("A function with that name already exists."))
            return
        editor.appendPlainText(
            "\n\ndef "
            + name
            + "(ctx, "
            + default_names()["variable"]
            + '):\n    """'
            + tr("Describe the behavior, input and result of this function.")
            + '"""\n    pass\n'
        )
        editor.show_line(editor.blockCount() - 2)

    def sync_variables(self):
        """Add data by scope without turning names into Python code."""
        if not hasattr(self, "data_list"):
            return
        for index, variable in enumerate(self.project.variables):
            scope = (
                tr("Project")
                if variable.get("scope", "project") == "project"
                else self.project.find(variable["window"]).properties.get("title", tr("Window"))
            )
            item = QListWidgetItem(
                tr("Variable") + f" · {variable['name']} = {variable.get('initial')!r}\n{scope}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.data_list.insertItem(0, item)

    def variable_dialog(self, _checked=False, index=None):
        """Declare or rename a variable, updating references and workspaces."""
        original = self.project.variables[index] if index is not None else None
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Application variable"))
        form = QFormLayout(dialog)
        name = QLineEdit(original["name"] if original else tr("counter"))
        scope = QComboBox()
        scope.addItem(tr("Project-wide"), "project")
        scope.addItem(tr("This window"), "window")
        scope.setCurrentIndex(
            scope.findData(original.get("scope", "project") if original else "project")
        )
        initial = QLineEdit(
            json.dumps(original.get("initial") if original else 0, ensure_ascii=False)
        )
        form.addRow(tr("Name"), name)
        form.addRow(tr("Scope"), scope)
        form.addRow(tr("Initial value (JSON)"), initial)
        error = QLabel()
        form.addRow(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def save():
            """Validate the fields and confirm only after saving successfully."""
            try:
                value = json.loads(initial.text())
            except ValueError:
                error.setText(tr("Use quoted text, a number, true, false or null."))
                return
            variable = {"name": name.text().strip(), "scope": scope.currentData(), "initial": value}
            if scope.currentData() == "window":
                variable["window"] = self.active_window

            def edit():
                """Update the declaration and references without running code."""
                if original:
                    self.rename_variable_references(original, variable)
                    self.project.variables[index] = variable
                else:
                    self.project.variables.append(variable)

            self._edit(edit)
            from makebench.core.navigation import validate_navigation

            try:
                validate_navigation(self.project)
            except ProjectError as exc:
                error.setText(str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(save)
        dialog.exec()

    def rename_variable_references(self, old, new):
        """Update the neutral model and the Blockly view, without losing drafts/comments."""

        def visit(value, workspace=False):
            """Walk structured data without running project content."""
            if isinstance(value, dict):
                if (
                    value.get("op") in {"variable", "assign", "ask"}
                    and value.get("name") == old["name"]
                    and value.get("scope", "project") == old.get("scope", "project")
                ):
                    value.update(name=new["name"], scope=new["scope"])
                if value.get("type") in {"mb_variable", "mb_assign", "mb_ask"}:
                    fields = value.get("fields", {})
                    if fields.get("NAME") == old["name"] and fields.get(
                        "SCOPE", "project"
                    ) == old.get("scope", "project"):
                        fields.update(NAME=new["name"], SCOPE=new["scope"], VARIABLE_PICKER="@none")
                for child in value.values():
                    visit(child, workspace)
            elif isinstance(value, list):
                for child in value:
                    visit(child, workspace)

        for flow in self.project.workflows:
            if (
                old.get("scope") == "window"
                and self.project.window_of(flow["event"]["component"]).id != old["window"]
            ):
                continue
            visit(flow.get("body"))
            visit(flow.get("workspace"))

    def edit_data_item(self):
        """Edit the selected variable; functions open the Code mode."""
        item = self.data_list.currentItem()
        if not item:
            return
        value = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(value, int):
            self.variable_dialog(index=value)
        elif isinstance(value, dict) and value.get("kind") == "resource":
            self.edit_resource(value["path"])
        elif item.text().startswith(tr("Function") + " ·"):
            self.find_function_name(item.text().split("·", 1)[-1].strip().split("(")[0])

    def remove_variable(self):
        """Remove the declaration without deleting values or blocks; references stay visible."""
        item = self.data_list.currentItem()
        if item and isinstance(item.data(Qt.ItemDataRole.UserRole), dict):
            self.remove_resource(item.data(Qt.ItemDataRole.UserRole)["path"])
            return
        if item and isinstance(item.data(Qt.ItemDataRole.UserRole), int):
            index = item.data(Qt.ItemDataRole.UserRole)
            self._edit(lambda: self.project.variables.pop(index))

    def search_block(self):
        """Search the available types and insert a real draft into Blockly."""
        if not self.logic.ready:
            return
        entries = {
            tr("Start terminal"): "mb_terminal_start",
            tr("Send to terminal"): "mb_terminal_send",
            tr("Stop terminal"): "mb_terminal_stop",
            tr("Show message"): "mb_message",
            tr("Write to output"): "mb_log",
            tr("If/else condition"): "mb_if",
            tr("Repeat"): "mb_repeat",
            tr("Run program"): "mb_run",
            tr("Run Bash"): "mb_script",
            tr("Ask"): "mb_ask",
            tr("Confirm"): "mb_confirm",
            tr("Call function"): "mb_call",
            tr("Go to state"): "mb_go_state",
            tr("Open window"): "mb_open_window",
            tr("Close window"): "mb_close_window",
            tr("Set variable"): "mb_assign",
            tr("Variable value"): "mb_variable",
        }
        entries.update(
            {
                tr("Text"): "text",
                tr("Number"): "math_number",
                tr("True or false"): "logic_boolean",
                tr("List of values"): "lists_create_with",
                tr("Multi-line text"): "mb_multiline",
                tr("Change component text"): "mb_set_text",
                tr("Enable component"): "mb_set_enabled",
                tr("Change progress"): "mb_set_value",
                tr("Show page"): "mb_show_page",
                tr("Read component text"): "mb_read_text",
                tr("Read checkbox selection"): "mb_read_checked",
                tr("Read progress"): "mb_read_value",
                tr("Join texts"): "mb_join",
                tr("Compare or calculate"): "mb_binary",
            }
        )
        choice, ok = QInputDialog.getItem(
            self, tr("Search block"), tr("Type to search"), list(entries), 0, True
        )
        if not ok:
            return
        if choice not in entries:
            matches = [name for name in entries if choice.casefold() in name.casefold()]
            if not matches:
                self.statusBar().showMessage(tr("No block matches the search."), 5000)
                return
            if len(matches) == 1:
                choice = matches[0]
            else:
                choice, ok = QInputDialog.getItem(
                    self, tr("Blocks found"), tr("Choose a block"), matches, 0, False
                )
                if not ok:
                    return
        self.logic.page.runJavaScript(
            "window.makebench.addBlock(" + json.dumps(entries[choice]) + ")"
        )

    def find_function_name(self, name):
        """Open a function requested by a block, after static syntax analysis."""
        try:
            node = next(
                (
                    n
                    for n in ast.parse(self.source.text).body
                    if isinstance(n, ast.FunctionDef) and n.name == name
                ),
                None,
            )
        except (SyntaxError, ValueError):
            return
        if node:
            self.set_mode("code")
            self.code_files.setCurrentIndex(1)
            self.source_editor.show_line(node.lineno)

    def duplicate_flow_dialog(self, identifier):
        """Copy a behavior to another event/state with new IDs and comments."""
        from makebench.core.logic import create_flow
        from makebench.core.project import ComponentKind, new_id

        flow = next(f for f in self.project.workflows if f["id"] == identifier)
        if flow.get("body") is None:
            self._show_error(tr("Complete the draft before duplicating the flow."))
            return
        targets = [
            node
            for node in self.project.walk()
            if node.kind in {ComponentKind.WINDOW, ComponentKind.BUTTON}
        ]
        labels = [
            node.display_name
            + " · "
            + self.project.window_of(node.id).properties.get("title", tr("Window"))
            for node in targets
        ]
        choice, ok = QInputDialog.getItem(
            self, tr("Duplicate flow"), tr("Destination event"), labels, 0, False
        )
        if not ok:
            return
        target = targets[labels.index(choice)]
        owner = self.project.window_of(target.id)
        states = [
            {"id": None, "name": tr("In any state")},
            {"id": "@default", "name": tr("Default")},
            *self.project.states.get(owner.id, []),
        ]
        chosen, ok = QInputDialog.getItem(
            self,
            tr("Duplicate flow"),
            tr("State filter"),
            [state["name"] for state in states],
            0,
            False,
        )
        if not ok:
            return
        selected = states[[state["name"] for state in states].index(chosen)]["id"]
        filters = [selected] if selected else []
        if any(
            f["event"]["component"] == target.id and f.get("states", []) == filters
            for f in self.project.workflows
        ):
            self._show_error(
                tr("A flow already exists for that event and filter. Choose another destination.")
            )
            return

        def copy():
            """Duplicate data and references, keeping the original."""
            clone = create_flow(self.project, target.id, states=filters)
            clone["body"] = deepcopy(flow["body"])
            clone["workspace"] = {
                "workspaceComments": deepcopy(
                    flow.get("workspace", {}).get("workspaceComments", [])
                )
            }

            def reidentify(value):
                """Create independent identifiers for the copied blocks."""
                if isinstance(value, dict):
                    if "op" in value:
                        value["id"] = new_id("block")
                    for child in value.values():
                        reidentify(child)
                elif isinstance(value, list):
                    for child in value:
                        reidentify(child)

            reidentify(clone["body"])
            self.logic.flow_id = clone["id"]
            self.logic._target_component = None

        self._edit(copy)

    def toggle_logic_python(self, enabled):
        """Persist the visibility without destroying the editor or the Blockly workspace."""
        self.logic.splitter.widget(1).setVisible(enabled)
        self.settings.setValue("workspace/logic_python", enabled)

    def design_event_origin(self, identifier):
        """Keep the selected state when returning to the event's origin."""
        if not self.logic.flush():
            return
        self.navigate_to_item("component", identifier)

    def insert_behavior(self, kind):
        """Insert neutral actions in the current event with history and their own IDs."""
        if not self.logic.flush():
            return
        flow = next((f for f in self.project.editable_flows if f["id"] == self.logic.flow_id), None)
        if flow is None:
            self.logic.new_event_dialog()
            flow = next(
                (f for f in self.project.editable_flows if f["id"] == self.logic.flow_id), None
            )
        if flow is None:
            return
        from makebench.core.behaviors import behavior_template, append_behavior

        try:
            blocks = behavior_template(
                kind, self.project, self.project.window_of(flow["event"]["component"]).id
            )
        except ProjectError as exc:
            self._show_error(exc, tr("Could not insert the behavior"))
            return
        self._edit(lambda: append_behavior(flow, blocks))

    def generated_origin(self, line):
        """Find the generated statement in the same origin map used by the diagnostics."""
        generated = self.logic.generated
        functions = [
            node
            for node in ast.parse(generated.text).body
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("on_event_")
            and node.lineno <= line <= node.end_lineno
        ]
        start = functions[0].lineno if functions else line + 1
        candidates = [
            (number, key) for key, number in generated.lines.items() if start <= number <= line
        ]
        if candidates:
            _, (flow, block) = max(candidates, key=lambda item: item[0])
            self.navigate_to_item("flow", flow)
            self.logic.focus_block(flow, block)
        else:
            self.statusBar().showMessage(
                tr("This line is generated infrastructure, with no source block."), 5000
            )
