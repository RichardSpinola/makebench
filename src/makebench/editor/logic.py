# SPDX-License-Identifier: GPL-3.0-or-later
"""Native event panel with offline Blockly and a bridge limited to data."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEventLoop, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from makebench.core.codegen import generate
from makebench.core.logic import (
    block_functions,
    editable,
    event_choices,
    find_unit,
    function_names,
    modules,
)
from makebench.core.project import ComponentKind
from makebench.i18n import language, tr

from .code import CodeEditor
from .look import make_muted


class LogicBridge(QObject):
    """Carry JSON; never exposes files, shell, imports or execution to the HTML."""

    documentChanged = Signal(str)
    update_received = Signal(str)
    block_selected = Signal(str, str)
    breakpoint_requested = Signal(str, str)
    became_ready = Signal()
    failed = Signal(str)
    pending_received = Signal(str)
    command_received = Signal(str)

    @Slot()
    def ready(self):
        """Report that Blockly and the local channel finished loading."""
        self.became_ready.emit()

    @Slot(str)
    def changed(self, payload):
        """Deliver block data to the native validator."""
        self.update_received.emit(payload)

    @Slot(str, str)
    def selected(self, flow, block):
        """Map a block selection to its origin in the generated code."""
        self.block_selected.emit(flow, block)

    @Slot(str, str)
    def toggleBreakpoint(self, flow, block):
        """Request a debug mark by stable ID, never running the block."""
        QTimer.singleShot(0, lambda: self.breakpoint_requested.emit(flow, block))

    @Slot(str)
    def pending(self, token):
        """Signal a pending gesture before the serialization debounce."""
        self.pending_received.emit(token)

    @Slot(str)
    def command(self, name):
        """Forward only save/undo/redo triggered from the keyboard."""
        if name in {"save", "undo", "redo", "find_block", "python", "function", "new_event"}:
            # Leave the WebChannel callback before evaluating JS during a flush.
            QTimer.singleShot(0, lambda: self.command_received.emit(name))

    @Slot(str)
    def problem(self, message):
        """Show a loading error without interpreting messages as instructions."""
        self.failed.emit(message)


class LogicPanel(QWidget):
    """Select events, keep the Blockly session and show the matching Python."""

    breakpoint_requested = Signal(str, str)
    add_requested = Signal(str, str)
    remove_requested = Signal(str)
    rename_requested = Signal(str, str)
    flow_changed = Signal(dict)
    error = Signal(str)
    save_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()
    pending_changed = Signal()
    script_requested = Signal(dict)
    filter_requested = Signal(str, object)
    full_code_requested = Signal(int)
    search_requested = Signal()
    function_requested = Signal(str)
    duplicate_requested = Signal(str)
    design_requested = Signal(str)
    function_edit_requested = Signal(str, str, list)
    module_requested = Signal(str, str)

    def __init__(self, project_getter, source_getter, parent=None):
        """Create native controls; WebEngine starts only when entering the Logic tab."""
        super().__init__(parent)
        self.get_project, self.get_source = project_getter, source_getter
        self.flow_id = None
        self.before_switch = lambda: True
        self._target_component = None
        self.view = None
        self.ready = False
        self.pending = False
        self._had_ready = False
        self.token = ""
        self._payload = None
        self._flushing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        row = QHBoxLayout()
        # The sidebar shows the events; this combo stays as the selection model.
        self.events = QComboBox()
        self.events.hide()
        self.events.setMinimumWidth(210)
        self.events.setMaximumWidth(460)
        self.events.currentIndexChanged.connect(self._switch_flow)
        # The way to add an event sits next to the list it adds to.
        self.add_event = QPushButton(tr("+ Event…"))
        self.add_event.setToolTip(tr("Connect a click or a window opening to the logic."))
        self.add_event.clicked.connect(self.new_event_dialog)
        row.addWidget(self.add_event)
        from .theme import icon

        back = QToolButton()
        back.setIcon(icon("design"))
        back.setAutoRaise(True)
        back.setToolTip(tr("Select this event's origin in the Designer"))
        back.setAccessibleName(tr("Show origin in the Designer"))
        back.clicked.connect(self.show_origin)
        row.addWidget(back)
        self.show_origin_button = back
        # The window puts its block tools here (search, behaviors, Python).
        self.top_row = row
        self.tools_index = row.count()
        row.addStretch(1)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("Flow name"))
        self.name.editingFinished.connect(self._rename)
        self.name.hide()
        self.state_filter = QComboBox()
        self.state_filter.setMaximumWidth(220)
        self.state_filter.setAccessibleName(tr("Flow state filter"))
        self.state_filter.currentIndexChanged.connect(self._change_filter)
        row.addWidget(self.state_filter)
        # Less frequent flow actions wait in one menu.
        more = QToolButton()
        more.setText("⋯")
        more.setAutoRaise(True)
        more.setToolTip(tr("More flow actions"))
        more.setAccessibleName(tr("More flow actions"))
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        menu = QMenu(more)
        menu.addAction(
            icon("duplicate"),
            tr("Duplicate flow…"),
            lambda: self.duplicate_requested.emit(self.flow_id) if self.flow_id else None,
        )
        menu.addAction(icon("add"), tr("New function…"), lambda: self.function_dialog())
        self.edit_function = menu.addAction(
            icon("code"),
            tr("Function name and inputs…"),
            lambda: self.function_dialog(self.flow_id),
        )
        self.move_module = menu.addAction(
            icon("layers"), tr("Move to module…"), lambda: self.module_dialog()
        )
        menu.addSeparator()
        self.remove = menu.addAction(
            icon("remove"),
            tr("Remove flow"),
            lambda: self.remove_requested.emit(self.flow_id) if self.flow_id else None,
        )
        more.setMenu(menu)
        row.addWidget(more)
        layout.addLayout(row)
        # The sentence about the event shows as the list's tooltip, not as another row.
        self.context_label = make_muted(QLabel())
        self.targets = QComboBox(self)
        self.targets.hide()
        hint = QLabel(
            tr(
                "Snap blocks into “do”. Right-click adds comments. Select a block to find its Python line."
            )
        )
        hint.setWordWrap(True)
        hint.hide()
        self.selected_block = ""
        self.edit_text = QPushButton(tr("Edit text or script…"))
        self.edit_text.setToolTip(
            tr("Select a text block or a Bash run block to edit several lines.")
        )
        self.edit_text.setEnabled(False)
        self.edit_text.clicked.connect(self._edit_text)
        self.edit_text.hide()
        self.edit_text_action = None
        self.splitter = QSplitter()
        self.splitter.setHandleWidth(4)
        self.placeholder = QLabel(tr("The block editor loads when this tab opens."))
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.surfaces = QStackedWidget()
        self.surfaces.addWidget(self.placeholder)
        self.outline = QTreeWidget()
        self.outline.setHeaderHidden(True)
        self.outline.setAccessibleName(tr("Events, functions and modules"))
        self.outline.itemClicked.connect(self._outline_clicked)
        self.outline.itemActivated.connect(self._outline_clicked)
        self.splitter.addWidget(self.outline)
        self.splitter.addWidget(self.surfaces)
        code_box = QWidget()
        self.code_box = code_box
        code_layout = QVBoxLayout(code_box)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_header = QHBoxLayout()
        code_header.addWidget(QLabel(tr("Generated Python")), 1)
        complete = QToolButton()
        complete.setIcon(icon("code"))
        complete.setToolTip(tr("Show the complete file"))
        complete.setAccessibleName(tr("Show the complete file"))
        complete.clicked.connect(
            lambda: self.full_code_requested.emit(
                self.code_start + self.code.textCursor().blockNumber()
            )
        )
        code_header.addWidget(complete)
        self.code_start = 1
        self._selecting_code = False
        self.code = CodeEditor(True)
        self.code.origin_requested.connect(self.focus_code_origin)
        wrap = QCheckBox(tr("Wrap lines"))
        wrap.toggled.connect(
            lambda enabled: self.code.setLineWrapMode(
                QPlainTextEdit.LineWrapMode.WidgetWidth
                if enabled
                else QPlainTextEdit.LineWrapMode.NoWrap
            )
        )
        code_header.addWidget(wrap)
        code_layout.addLayout(code_header)
        code_layout.addWidget(self.code)
        self.code.cursorPositionChanged.connect(self._select_line)
        self.splitter.addWidget(code_box)
        self.splitter.setSizes([220, 850, 380])
        code_box.hide()
        self.view_python = QToolButton()
        self.view_python.setText(tr("View Python"))
        self.view_python.setCheckable(True)
        self.view_python.setToolTip(tr("Show the Python generated from these blocks (read-only)"))
        self.view_python.toggled.connect(code_box.setVisible)
        row.insertWidget(row.indexOf(self.add_event) + 1, self.view_python)
        layout.addWidget(self.splitter, 1)
        self.diagnostics = QLabel()
        self.diagnostics.setWordWrap(True)
        self.diagnostics.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.diagnostics)
        self.sync()

    def new_event_dialog(self):
        """A short action opens the origin choice, without a second permanent bar."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("New event"))
        dialog.setFixedWidth(460)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr("When this happens")))
        choices = QComboBox()
        current = self.targets.currentData()
        for label, component, kind in event_choices(self.get_project()):
            choices.addItem(label, (component, kind))
            if component == current and kind in {"start", "click", "change"}:
                choices.setCurrentIndex(choices.count() - 1)
        layout.addWidget(choices)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Connect event"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setFixedHeight(dialog.sizeHint().height())
        if dialog.exec() == QDialog.DialogCode.Accepted and choices.currentData():
            self.add_requested.emit(*choices.currentData())

    def ensure_loaded(self):
        """Open only local resources, with a temporary profile and no network."""
        if self.view is not None:
            return
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import (
            QWebEnginePage,
            QWebEngineProfile,
            QWebEngineSettings,
            QWebEngineUrlRequestInterceptor,
        )
        from PySide6.QtWebEngineWidgets import QWebEngineView

        root = Path(__file__).resolve().parent.parent / "web"
        # Each interface language has its own static entry with the matching Blockly locale.
        entry = "index.pt_BR.html" if language() == "pt_BR" else "index.html"

        class LocalRequests(QWebEngineUrlRequestInterceptor):
            """Block network and files outside the embedded resources."""

            def interceptRequest(self, info):
                """Allow only the web folder and Qt's internal script."""
                url = info.requestUrl()
                allowed = url.toString() == "qrc:///qtwebchannel/qwebchannel.js"
                if url.scheme() == "file":
                    allowed = Path(url.toLocalFile()).resolve().is_relative_to(root)
                info.block(not allowed and url.scheme() != "data")

        class LocalPage(QWebEnginePage):
            """Refuse navigation away from the editor's HTML entry point."""

            def acceptNavigationRequest(self, url, navigation_type, main_frame):
                """Only the embedded entry can occupy the main page."""
                return url == QUrl.fromLocalFile(str(root / entry))

            def javaScriptConsoleMessage(page_self, level, message, line, source):
                """Forward startup errors to the native panel."""
                if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    self.diagnostics.setText(
                        tr("Blockly: {message} (line {line})").format(message=message, line=line)
                    )

        class LocalView(QWebEngineView):
            """Forward file/history shortcuts to the native document."""

            def keyPressEvent(view_self, event):
                """Avoid a second undo history inside the browser."""
                if event.matches(QKeySequence.StandardKey.Save):
                    self.save_requested.emit()
                elif event.matches(QKeySequence.StandardKey.Undo):
                    self.undo_requested.emit()
                elif (
                    event.matches(QKeySequence.StandardKey.Redo)
                    or event.keyCombination().toCombined()
                    == QKeySequence("Ctrl+Shift+Z")[0].toCombined()
                ):
                    self.redo_requested.emit()
                else:
                    super().keyPressEvent(event)
                    return
                event.accept()

        self.profile = QWebEngineProfile()
        self.interceptor = LocalRequests(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.view = LocalView(self)
        self.page = LocalPage(self.profile, self.view)
        self.view.setPage(self.page)
        from .theme import manager

        self.page.setBackgroundColor(QColor(manager().tokens["canvas"]))
        # Destruction order: the view/page dies before the Chromium profile.
        self.profile.setParent(self)
        self.page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        self.page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False
        )
        self.page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self.channel = QWebChannel(self.page)
        self.bridge = LogicBridge(self.channel)
        self.bridge.breakpoint_requested.connect(self.breakpoint_requested)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel)
        self.bridge.update_received.connect(self._receive)
        self.bridge.block_selected.connect(self._select_block)
        self.bridge.became_ready.connect(self._became_ready)
        self.bridge.failed.connect(self.error)
        self.bridge.pending_received.connect(self._mark_pending)
        self.bridge.command_received.connect(self._command)
        self.surfaces.addWidget(self.view)
        flow = next((f for f in self.get_project().editable_flows if f["id"] == self.flow_id), None)
        if not flow or flow.get("editor", "blocks") == "blocks":
            self.surfaces.setCurrentWidget(self.view)
        self.placeholder.deleteLater()
        self.view.load(QUrl.fromLocalFile(str(root / entry)))
        self.view.loadFinished.connect(self._load_finished)
        self.page.renderProcessTerminated.connect(lambda *_: self._load_finished(False))

    def _load_finished(self, ok):
        """Explain a resource failure without pretending a block editor is available."""
        if not ok:
            self.ready = False
            self.diagnostics.setText(
                tr(
                    "Could not load Blockly. Reopen Makebench; the interface and the saved files remain available."
                )
            )

    def _became_ready(self):
        """Send the initial context as soon as the channel is ready."""
        self.ready = True
        self._had_ready = True
        self._payload = None
        self.sync()
        from .theme import manager

        manager().changed.connect(self.apply_theme)
        self.apply_theme(manager().tokens)

    def _switch_flow(self):
        """Confirm the previous flow before switching the block area."""
        requested = self.events.currentData()
        if requested == self.flow_id:
            return
        if not self.before_switch() or not self.flush():
            self.events.blockSignals(True)
            self.events.setCurrentIndex(self.events.findData(self.flow_id))
            self.events.blockSignals(False)
            return
        self._target_component = None
        self.flow_id = requested
        self.sync()

    def _rename(self):
        """Confirm the flow name without changing the event it is bound to."""
        if self.flow_id and self.flush():
            self.rename_requested.emit(self.flow_id, self.name.text())

    def sync(self, flow_id=None):
        """Update events/components without reloading the whole web page."""
        project = self.get_project()
        if flow_id is not None and flow_id != self.flow_id and not self.before_switch():
            return
        if flow_id is not None:
            self.flow_id = flow_id
        flows = project.workflows if editable(project) else []
        functions = block_functions(project) if editable(project) else []
        if self.flow_id not in {f["id"] for f in [*flows, *functions]}:
            candidates = [
                f
                for f in flows
                if not self._target_component or f["event"]["component"] == self._target_component
            ]
            self.flow_id = candidates[0]["id"] if candidates else None
        function = next((f for f in functions if f["id"] == self.flow_id), None)
        flow = function or next((f for f in flows if f["id"] == self.flow_id), None)
        from .controls import reconcile_combo

        reconcile_combo(
            self.events,
            [
                (
                    (
                        project.window_of(item["event"]["component"]).properties.get(
                            "title", tr("Interface")
                        )
                        + " › "
                        if len(project.roots) > 1
                        else ""
                    )
                    + item["name"],
                    item["id"],
                )
                for item in flows
            ]
            + [(self.signature(item), item["id"]) for item in functions],
            self.flow_id,
        )
        self.name.setText(flow["name"] if flow else "")
        self._sync_outline()
        self.surfaces.setCurrentWidget(self.view if self.view is not None else self.placeholder)
        self._sync_edit_text()

        owner = (
            project.root
            if function
            else project.window_of(flow["event"]["component"])
            if flow
            else project.window_of(self._target_component)
            if self._target_component and project.find(self._target_component)
            else project.root
        )
        filters = flow.get("states", []) if flow else []
        entries = [
            (tr("in any state"), []),
            (tr("only in Default"), ["@default"]),
            *[
                (tr("only in {state}").format(state=state["name"]), [state["id"]])
                for state in project.states.get(owner.id, [])
            ],
            (tr("Choose several states…"), "@choose"),
        ]
        if filters not in [value for _, value in entries]:
            entries.append((tr("multiple-state filter"), filters))
        reconcile_combo(self.state_filter, entries, filters)
        self.state_filter.setEnabled(flow is not None and not function)
        self.edit_function.setEnabled(function is not None)
        self.move_module.setEnabled(flow is not None)
        self.name.setEnabled(flow is not None)
        self.remove.setEnabled(flow is not None)
        target = self._target_component or self.targets.currentData()
        targets = [
            (
                (
                    tr("On start:") + " "
                    if node.kind == ComponentKind.WINDOW
                    else tr("On click:") + " "
                )
                + (
                    project.window_of(node.id).properties.get("title", tr("Interface")) + " › "
                    if len(project.roots) > 1
                    else ""
                )
                + node.display_name,
                node.id,
            )
            for node in project.walk()
            if node.kind in {ComponentKind.WINDOW, ComponentKind.BUTTON}
        ]
        reconcile_combo(
            self.targets,
            targets,
            target
            if target in [value for _, value in targets]
            else targets[0][1]
            if targets
            else None,
        )
        components = [
            {
                "id": n.id,
                "kind": n.kind.value,
                "name": project.window_of(n.id).properties.get("title", tr("Window"))
                + " › "
                + (n.properties.get("code_name") or n.display_name),
            }
            for n in project.walk()
        ]
        try:
            function_info = [
                {
                    "name": n.name,
                    "signature": n.name + "(" + ", ".join(a.arg for a in n.args.args) + ")",
                    "description": (ast.get_docstring(n) or "").split("\n")[0],
                }
                for n in ast.parse(self.get_source()).body
                if isinstance(n, ast.FunctionDef)
            ]
        except (SyntaxError, ValueError):
            function_info = []
        variables = [
            dict(item)
            for item in project.variables
            if item.get("scope", "project") == "project" or item.get("window") == owner.id
        ]

        def collect(value):
            """Gather declared and implicit variables without evaluating expressions."""
            if isinstance(value, dict):
                if value.get("op") in {"assign", "variable", "ask"} and value.get("name"):
                    candidate = {"name": value["name"], "scope": value.get("scope", "project")}
                    if not any(
                        item["name"] == candidate["name"]
                        and item.get("scope", "project") == candidate["scope"]
                        for item in variables
                    ):
                        variables.append(candidate)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        if flow:
            collect(flow.get("body"))
        if function:
            variables.extend({"name": name, "scope": "local"} for name in function["params"])
        payload = {
            "variables": variables,
            "function_info": function_info,
            "windows": [
                {"id": r.id, "name": r.properties.get("title", tr("Window"))} for r in project.roots
            ],
            "states": [
                {"id": "@default", "name": tr("Default")},
                *[{"id": s["id"], "name": s["name"]} for s in project.states.get(owner.id, [])],
            ],
            "project": project.id,
            "flow": {**function, "kind": "function", "title": self.signature(function)}
            if function
            else flow,
            "block_functions": [
                {"id": item["id"], "name": item["name"], "params": item["params"]}
                for item in functions
            ],
            "components": components,
            "functions": function_names(self.get_source())[0],
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        if self.ready and serialized != self._payload:
            self._payload = serialized
            self.token = uuid4().hex
            self.pending = False
            self.pending_changed.emit()
            payload["token"] = self.token
            self.bridge.documentChanged.emit(json.dumps(payload, ensure_ascii=False))
        self.show_origin_button.setVisible(bool(flow) and not function)
        if function:
            self.context_label.setText(
                tr("Function {signature}").format(signature=self.signature(function))
            )
        elif flow:
            component = project.find(flow["event"]["component"])
            verb = (
                tr("starting")
                if component.kind == ComponentKind.WINDOW
                else tr("clicking {name}").format(name=component.display_name)
            )
            self.context_label.setText(
                tr("When {event} · {window}").format(
                    event=verb, window=owner.properties.get("title", tr("Window"))
                )
            )
        else:
            self.context_label.setText(tr("Choose an event or connect a new one to start."))
        self.events.setToolTip(self.context_label.text())
        self.update_code()

    @staticmethod
    def signature(function):
        """Show a block function the way it is called: name(inputs)."""
        return f"{function['name']}({', '.join(function['params'])})"

    def _open_function(self, value):
        """Open a Python function, or switch to the block function a call points to."""
        if not value:
            return
        if value.startswith("@block:"):
            target = value.removeprefix("@block:")
            if any(f["id"] == target for f in block_functions(self.get_project())):
                if self.before_switch() and self.flush():
                    self.sync(target)
            return
        self.function_requested.emit(value)

    def function_dialog(self, function_id=None):
        """Ask for a function's Python name and its inputs, separated by commas."""
        if function_id is None and not self.flush():
            return
        current = next(
            (f for f in block_functions(self.get_project()) if f["id"] == function_id), None
        )
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Function") if current else tr("New function"))
        dialog.setFixedWidth(420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr("Name (a Python name, like total_price)")))
        name = QLineEdit(current["name"] if current else "")
        layout.addWidget(name)
        layout.addWidget(QLabel(tr("Inputs, separated by commas (optional)")))
        params = QLineEdit(", ".join(current["params"]) if current else "")
        params.setPlaceholderText(tr("price, amount"))
        layout.addWidget(params)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.function_edit_requested.emit(
                function_id or "",
                name.text().strip(),
                [item.strip() for item in params.text().split(",") if item.strip()],
            )

    def module_dialog(self):
        """Ask which module groups the open event or function; empty leaves the module."""
        unit = find_unit(self.get_project(), self.flow_id)
        if unit is None or not self.flush():
            return
        choices = ["", *modules(self.get_project())]
        dialog = QInputDialog(self)
        dialog.setWindowTitle(tr("Move to module"))
        dialog.setLabelText(tr("Module (leave empty for none)"))
        dialog.setComboBoxItems(choices)
        dialog.setComboBoxEditable(True)
        dialog.setTextValue(unit.get("module", ""))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.module_requested.emit(self.flow_id, dialog.textValue().strip())

    def _sync_outline(self):
        """Mirror the event list in the sidebar without emitting selection changes."""
        self.outline.blockSignals(True)
        self.outline.clear()
        events = QTreeWidgetItem([tr("Events")])
        events.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.outline.addTopLevelItem(events)
        for index in range(self.events.count()):
            item = QTreeWidgetItem([self.events.itemText(index)])
            item.setData(0, Qt.ItemDataRole.UserRole, self.events.itemData(index))
            events.addChild(item)
            if self.events.itemData(index) == self.flow_id:
                self.outline.setCurrentItem(item)
        events.setExpanded(True)
        functions = {f["id"] for f in block_functions(self.get_project())}
        if functions:
            group = QTreeWidgetItem([tr("Functions")])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.outline.addTopLevelItem(group)
            for index in reversed(range(events.childCount())):
                child = events.child(index)
                if child.data(0, Qt.ItemDataRole.UserRole) in functions:
                    events.removeChild(child)
                    group.insertChild(0, child)
            group.setExpanded(True)
            if self.flow_id in functions:
                self.outline.setCurrentItem(
                    next(
                        group.child(i)
                        for i in range(group.childCount())
                        if group.child(i).data(0, Qt.ItemDataRole.UserRole) == self.flow_id
                    )
                )
        # Modules gather events and functions in one more group; each unit stays in one place.
        project = self.get_project()
        grouped = {
            unit["id"]: unit["module"]
            for unit in [*project.workflows, *block_functions(project)]
            if unit.get("module")
        }
        if grouped:
            group = QTreeWidgetItem([tr("Modules")])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.outline.addTopLevelItem(group)
            folders = {}
            for name in modules(project):
                folders[name] = QTreeWidgetItem([name])
                folders[name].setFlags(Qt.ItemFlag.ItemIsEnabled)
                group.addChild(folders[name])
            for index in reversed(range(self.outline.topLevelItemCount() - 1)):
                parent = self.outline.topLevelItem(index)
                for child_index in reversed(range(parent.childCount())):
                    child = parent.child(child_index)
                    module = grouped.get(child.data(0, Qt.ItemDataRole.UserRole))
                    if module:
                        parent.removeChild(child)
                        folders[module].insertChild(0, child)
            group.setExpanded(True)
            for folder in folders.values():
                folder.setExpanded(True)
                for i in range(folder.childCount()):
                    if folder.child(i).data(0, Qt.ItemDataRole.UserRole) == self.flow_id:
                        self.outline.setCurrentItem(folder.child(i))
        self.outline.blockSignals(False)

    def _outline_clicked(self, item, _column=0):
        """Open the clicked event; group headings do nothing."""
        flow = item.data(0, Qt.ItemDataRole.UserRole)
        if flow:
            self.events.setCurrentIndex(self.events.findData(flow))

    def _sync_edit_text(self):
        """The multi-line editor appears only while a block is selected in Blocks."""
        visible = bool(self.selected_block)
        if self.edit_text_action is not None:
            self.edit_text_action.setVisible(visible)
        else:
            self.edit_text.setVisible(visible)

    def show_origin(self):
        """Return to the component that fires the flow without changing its behavior."""
        flow = next((f for f in self.get_project().editable_flows if f["id"] == self.flow_id), None)
        if flow:
            self.design_requested.emit(flow["event"]["component"])

    def update_code(self):
        """Regenerate visible Python from the model, without running functions."""
        self.generated = generate(self.get_project(), self.get_source())
        lines = self.generated.text.splitlines()
        flow_index = next(
            (
                index
                for index, f in enumerate(self.get_project().editable_flows, 1)
                if f["id"] == self.flow_id
            ),
            None,
        )
        function = next(
            (f for f in block_functions(self.get_project()) if f["id"] == self.flow_id), None
        )
        header = f"def fn_{function['name']}(" if function else f"def on_event_{flow_index}("
        start = next((i for i, line in enumerate(lines) if line.startswith(header)), None)
        if start is not None:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].startswith("def ")),
                len(lines),
            )
            while end > start and (not lines[end - 1].strip() or lines[end - 1].startswith("# ")):
                end -= 1
            text = "\n".join(lines[start:end]) + "\n"
            self.code_start = start + 1
        else:
            text = ""
            self.code_start = 1
        if self.code.toPlainText() != text:
            self.code.setPlainText(text)
        self.diagnostics.setText(
            "\n".join(self.generated.diagnostics)
            or tr("Blocks saved. Press F5 to test the application and follow its output.")
        )

    def _select_block(self, flow, block):
        """Show the generated line that matches the Blockly selection."""
        self.selected_block = block
        self.edit_text.setEnabled(bool(block))
        self._sync_edit_text()
        line = self.generated.lines.get((flow, block))
        if line:
            self._selecting_code = True
            try:
                self.code.show_line(line - self.code_start + 1)
            finally:
                self._selecting_code = False

    def _edit_text(self):
        """Edit multi-line text without running scripts or concatenating arguments."""
        if not self.ready or not self.selected_block:
            return
        self.page.runJavaScript(
            "JSON.stringify(window.makebench.textValue(" + json.dumps(self.selected_block) + "))",
            self._text_dialog,
        )

    def _text_dialog(self, result):
        """Open a native editor for a text literal of the current workspace."""
        if not result or result == "null":
            self.diagnostics.setText(
                tr("Select a text block or a “run Bash” block with connected text.")
            )
            return
        self.script_requested.emit(json.loads(result))

    def focus_block(self, flow, block, attempt=0):
        """Reveal an error's origin as soon as the requested workspace is available."""
        self._select_block(flow, block)
        if attempt >= 30:
            return
        if not self.ready:
            QTimer.singleShot(100, lambda: self.focus_block(flow, block, attempt + 1))
            return
        code = (
            "(() => {const ws=window.makebench?.workspace;const b=ws?.getBlockById("
            + json.dumps(block)
            + ");if(!b)return false;b.select();ws.centerOnBlock(b.id);return true;})()"
        )
        self.page.runJavaScript(
            code,
            lambda found: (
                QTimer.singleShot(50, lambda: self.focus_block(flow, block, attempt + 1))
                if not found
                else None
            ),
        )

    def _mark_pending(self, token):
        """Keep undo and the changes notice available before the debounce."""
        if token == self.token:
            self.pending = True
            self.pending_changed.emit()

    def _command(self, name):
        """Deliver shortcuts captured in the DOM to the native document."""
        if name == "find_block":
            self.search_requested.emit()
        elif name == "new_event":
            self.new_event_dialog()
        elif name == "new_function":
            self.function_dialog()
        elif name == "python":
            self.full_code_requested.emit(self.code_start + self.code.textCursor().blockNumber())
        elif name == "function":
            if self.ready:
                self.page.runJavaScript(
                    "window.makebench.selectedFunction()",
                    self._open_function,
                )
        else:
            {"save": self.save_requested, "undo": self.undo_requested, "redo": self.redo_requested}[
                name
            ].emit()

    def _receive(self, payload):
        """Ignore messages from an old session and deliver a validatable update."""
        try:
            data = json.loads(payload)
            if (
                not isinstance(data, dict)
                or data.get("token") != self.token
                or data.get("flow") != self.flow_id
            ):
                return
            self.pending = False
            self.flow_changed.emit(data)
            self.pending_changed.emit()
        except (ValueError, TypeError) as exc:
            self.error.emit(tr("Invalid block data: {error}").format(error=exc))

    def flush(self):
        """Get changes still in the web page before saving, switching or undoing.

        The JavaScript return value avoids depending on the channel's debounce. On
        failure it does not authorize an operation that could lose unconfirmed changes.
        """
        if self.view is None or self._flushing:
            return True
        if not self.ready:
            if self._had_ready:
                self.error.emit(
                    tr(
                        "The Blockly process ended. Reopen Makebench to continue; the last saved file was kept."
                    )
                )
                return False
            return True
        self._flushing = True
        loop = QEventLoop()
        results = []

        def finished(value):
            """Finish the short wait when JavaScript returns the snapshot."""
            results.append(value)
            loop.quit()

        self.page.runJavaScript("JSON.stringify(window.makebench.flush(true))", finished)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(2500)
        loop.exec()
        timer.stop()
        self._flushing = False
        if not results:
            self.error.emit(
                tr("Blockly did not respond. Wait and try saving again before closing.")
            )
            return False
        if results[0] and results[0] != "null":
            self._receive(results[0])
        return True

    def _change_filter(self):
        """Confirm the workspace before changing the event's declarative filter."""
        if not self.flow_id or not self.state_filter.isEnabled() or not self.flush():
            return
        if self.state_filter.currentData() == "@choose":
            from PySide6.QtWidgets import QListWidget, QListWidgetItem

            flow = next(f for f in self.get_project().workflows if f["id"] == self.flow_id)
            owner = self.get_project().window_of(flow["event"]["component"])
            dialog = QDialog(self)
            dialog.setWindowTitle(tr("Run in these states"))
            layout = QVBoxLayout(dialog)
            choices = QListWidget()
            choices.setSelectionMode(choices.SelectionMode.MultiSelection)
            for state in [
                {"id": "@default", "name": tr("Default")},
                *self.get_project().states.get(owner.id, []),
            ]:
                item = QListWidgetItem(state["name"])
                item.setData(Qt.ItemDataRole.UserRole, state["id"])
                choices.addItem(item)
                item.setSelected(state["id"] in flow.get("states", []))
            layout.addWidget(choices)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.filter_requested.emit(
                    self.flow_id,
                    [item.data(Qt.ItemDataRole.UserRole) for item in choices.selectedItems()],
                )
            else:
                self.sync()
        else:
            self.filter_requested.emit(self.flow_id, self.state_filter.currentData())

    def _select_line(self):
        """Map the visible line to the block, without reloading or changing the logic."""
        if not self.ready or self._selecting_code:
            return
        line = self.code_start + self.code.textCursor().blockNumber()
        match = next(
            (
                (flow, block)
                for (flow, block), number in self.generated.lines.items()
                if flow == self.flow_id and number == line
            ),
            None,
        )
        if match and match[1] != self.selected_block:
            self.focus_block(*match)

    def apply_theme(self, tokens):
        """Deliver only visual tokens to the local page through the JavaScript channel."""
        if self.ready:
            self.page.runJavaScript("window.makebench.applyTheme(" + json.dumps(tokens) + ")")

    def select_component_event(self, component, state):
        """Select the current origin's behavior or show an honest empty state."""
        if not self.before_switch() or not self.flush():
            return
        self._target_component = component
        flows = [
            f for f in self.get_project().editable_flows if f["event"]["component"] == component
        ]
        flow = next((f for f in flows if state in f.get("states", [])), None) or next(
            (f for f in flows if not f.get("states")), None
        )
        self.flow_id = flow["id"] if flow else None
        self.sync()

    def focus_code_origin(self, line):
        """The collapsible Python menu finds the block through the matching global line."""
        candidates = [
            (number, key)
            for key, number in self.generated.lines.items()
            if key[0] == self.flow_id and number <= self.code_start + line - 1
        ]
        if candidates:
            _, key = max(candidates, key=lambda item: item[0])
            self.focus_block(*key)
