# SPDX-License-Identifier: GPL-3.0-or-later
"""Workbench: modes, persistent context and navigable diagnostics."""

from PySide6.QtCore import Qt, QSettings, QTimer, QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
)
from .commands import CommandPalette, register, tidy_menus
from .theme import icon, manager


from .code_workspace import CodeWorkspaceMixin
from .projects import ProjectMixin
from .navigation import NavigationMixin
from .designer import DesignerMixin
from .development import DevelopmentMixin
from .execution import ExecutionMixin
from .resources import ResourceMixin
from .collections_ui import CollectionMixin
from makebench.i18n import tr
from makebench.i18n import ntr

# Internal mode keys are stable identifiers; only the labels are translated.
MODE_LABELS = {"map": tr("Map"), "design": tr("Design"), "logic": tr("Logic"), "code": tr("Code")}
MODE_ICONS = {
    "map": "map",
    "design": "select",
    "logic": "logic",
    "code": "code",
    "publish": "export",
}


class StudioMixin(
    CodeWorkspaceMixin,
    ProjectMixin,
    NavigationMixin,
    DesignerMixin,
    DevelopmentMixin,
    ExecutionMixin,
    ResourceMixin,
    CollectionMixin,
):
    """Adapt the existing views without duplicating the document, generation or execution."""

    def install_studio(self):
        """Replace the old navigation; keep the editing widgets and APIs."""
        self.settings = QSettings("Makebench", "Makebench")
        self._mode = "design"
        self._problem_targets = []
        for toolbar in self.findChildren(QToolBar):
            toolbar.hide()
        self.tabs.tabBar().hide()
        self.design_splitter = self.tabs.widget(0)
        # Rebuild the existing views into panels with explicit responsibilities.
        old_left = self.design_splitter.widget(0)
        structure = QWidget()
        sl = QVBoxLayout(structure)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(4)
        self.tree_search = QLineEdit()
        self.tree_search.setPlaceholderText(tr("Search components…"))
        self.tree_search.setAccessibleName(tr("Search components"))
        sl.addWidget(self.tree_search)
        sl.addWidget(self.tree)
        self.tree_search.textChanged.connect(self.filter_tree)
        insert = QWidget()
        il = QVBoxLayout(insert)
        il.setContentsMargins(6, 6, 6, 6)
        self.insert_search = QLineEdit()
        self.insert_search.setPlaceholderText(tr("Search elements…"))
        self.insert_search.setClearButtonEnabled(True)
        il.addWidget(self.insert_search)
        self.palette.setMaximumHeight(16777215)
        from PySide6.QtWidgets import QSizePolicy

        self.palette.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for index in range(self.palette.count()):
            item = self.palette.item(index)
            item.setIcon(icon(item.data(Qt.ItemDataRole.UserRole)))
        from .catalog import CATEGORIES, filter_library

        self.insert_category = QComboBox()
        self.insert_category.setAccessibleName(tr("Component category"))
        self.insert_category.addItem(tr("All components"), None)
        for key, label in CATEGORIES.items():
            self.insert_category.addItem(label, key)
        il.addWidget(self.insert_category)
        self.insert_search.textChanged.connect(lambda _: filter_library(self))
        self.insert_category.currentIndexChanged.connect(lambda _: filter_library(self))
        filter_library(self)
        il.addWidget(self.palette, 1)

        add = QPushButton(icon("add"), tr("Insert"))
        add.setToolTip(tr("Insert the selected element"))
        add.clicked.connect(self.add_component)
        il.addWidget(add)
        self.data_list = QListWidget()
        self.data_list.setAccessibleName(tr("Project assets and functions"))
        # The old button will be destroyed; its visual callback must not survive.
        self.remove_action.changed.disconnect()
        old_left.hide()
        old_left.deleteLater()
        middle = self.design_splitter.widget(1)
        ml = middle.layout()
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        # Remove titles and instructions that competed with the creation area.
        for n in reversed(range(ml.count())):
            widget = ml.itemAt(n).widget()
            if isinstance(widget, QLabel):
                ml.removeWidget(widget)
                widget.deleteLater()
        middle.setObjectName("pasteboard")
        tools = QToolBar(tr("Creation tools"))
        tools.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        tools.setIconSize(QSize(16, 16))
        tools.setMovable(False)
        select = tools.addAction(icon("select"), tr("Select"))
        select.setCheckable(True)
        select.setChecked(True)
        pan = tools.addAction(icon("pan"), tr("Pan the view"))
        pan.setCheckable(True)
        select.setProperty("makebenchIcon", "select")
        pan.setProperty("makebenchIcon", "pan")
        from PySide6.QtGui import QActionGroup

        self.pointer_tools = QActionGroup(self)
        self.pointer_tools.addAction(select)
        self.pointer_tools.addAction(pan)
        select.triggered.connect(lambda: self.canvas.set_insert_tool(None))
        self.pointer_tools.triggered.connect(
            lambda action: self.zoom_view.setDragMode(
                self.zoom_view.DragMode.ScrollHandDrag
                if action is pan
                else self.zoom_view.DragMode.NoDrag
            )
        )
        ml.addWidget(tools)
        old_right = self.design_splitter.widget(2)
        old_right.layout().setContentsMargins(0, 0, 0, 0)
        old_right.layout().setSpacing(0)
        for heading in old_right.findChildren(
            QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            heading.hide()
        from PySide6.QtWidgets import QFrame

        old_right.findChild(QScrollArea).setFrameShape(QFrame.Shape.NoFrame)
        self.tree.setMinimumWidth(160)
        self.tree.setAlternatingRowColors(True)
        self.inspector.setMinimumWidth(220)
        from .panels import DesignHost

        self.pasteboard = middle
        self.design_host = DesignHost(
            middle,
            {
                "layers": structure,
                "components": insert,
                "data": self.data_list,
                "properties": old_right,
            },
        )
        self.panel_docks = self.design_host.docks
        label = self.tabs.tabText(0)
        self.tabs.removeTab(0)
        self.tabs.insertTab(0, self.design_host, label)
        self.tabs.setCurrentIndex(0)
        self.design_splitter.deleteLater()
        del self.design_splitter
        # One drawer shared by every mode, outside the document.
        self.drawer = QTabWidget()
        self.drawer.setDocumentMode(True)
        self.drawer.setTabPosition(QTabWidget.TabPosition.South)
        self.drawer.setMinimumHeight(80)
        self.drawer.setMaximumHeight(350)
        from .code import CodeEditor

        self.output_log = CodeEditor(True)
        self.output_log.highlighter.language = "plain"
        self.output_log.highlighter.rehighlight()
        self.output_log.origin_enabled = False
        self.output_log.setAccessibleName(tr("Run output"))
        self.output_log.setPlaceholderText(tr("Output appears here when you test the application."))
        self.problems = QListWidget()
        self.problems.itemActivated.connect(self.go_to_problem)
        self.problems.itemClicked.connect(self.go_to_problem)
        self.script_editor = CodeEditor()
        self.script_editor.setPlaceholderText(
            tr("Select a Bash block and choose Edit text or script.")
        )
        self.script_apply = QPushButton(tr("Apply to block · Ctrl+Enter"))
        self.script_apply.setEnabled(False)
        script = QWidget()
        sc = QVBoxLayout(script)
        self.script_context = QLabel(
            tr("Select a text or Bash block in Logic and use Edit text or script.")
        )
        self.script_context.setWordWrap(True)
        sc.addWidget(self.script_context)
        sc.addWidget(self.script_editor)
        sc.addWidget(self.script_apply)
        self.drawer.addTab(self.output_log, tr("Output"))
        self.drawer.addTab(self.problems, tr("Problems"))
        self.drawer.addTab(script, tr("Script"))
        self.drawer.hide()
        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.workspace_splitter.setHandleWidth(4)
        self.workspace_splitter.addWidget(self.tabs)
        self.workspace_splitter.addWidget(self.drawer)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setSizes([650, 180])
        editor = QWidget()
        el = QVBoxLayout(editor)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(0)
        self.context_bar = QToolBar(tr("Creation context"))
        self.context_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.context_bar.setIconSize(QSize(16, 16))
        self.context_bar.setMovable(False)
        self.context_bar.setObjectName("context_bar")
        self.context_label = QLabel()
        self.context_label.setTextFormat(Qt.TextFormat.PlainText)
        self.context_label.setFixedWidth(190)
        self.overview_action = self.context_bar.addAction(
            icon("map"), tr("Map"), lambda: self.set_mode("map")
        )
        self.overview_action.setProperty("makebenchIcon", "map")
        self.context_bar.addWidget(self.context_label)
        el.addWidget(self.context_bar)
        el.addWidget(self.workspace_splitter, 1)
        self.drawer_toggle = QToolButton()
        self.drawer_toggle.setIcon(icon("output"))
        self.drawer_toggle.setAutoRaise(True)
        self.drawer_toggle.setFixedSize(26, 24)
        self.drawer_toggle.setToolTip(tr("Output and problems · Ctrl+J"))
        self.drawer_toggle.setAccessibleName(tr("Output and problems"))
        self.drawer_toggle.clicked.connect(self.toggle_drawer)
        self.drawer_toggle.setProperty("makebenchIcon", "output")
        self.statusBar().addPermanentWidget(self.drawer_toggle)
        self.pages = QStackedWidget()
        self.editor_page = editor
        self.pages.addWidget(editor)
        self.setCentralWidget(self.pages)
        bar = QToolBar(tr("Workbench"))
        bar.setObjectName("workspace_toolbar")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        bar.setIconSize(QSize(16, 16))
        self.home_action = QAction(icon("home"), tr("Start page"), self)
        self.home_action.setProperty("makebenchIcon", "home")
        self.home_action.triggered.connect(self.show_home)
        bar.addAction(self.home_action)
        bar.addActions([self.new_action, self.open_action, self.save_action])
        bar.addSeparator()
        bar.addActions([self.undo_action, self.redo_action])
        for action in (self.new_action, self.open_action, self.save_action):
            bar.widgetForAction(action).setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
        self.project_heading = QLabel(self)
        self.project_heading.setTextFormat(Qt.TextFormat.PlainText)
        self.project_heading.hide()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        from .shell import AreaBar, AreaButton

        self.mode_switcher = AreaBar(self)
        self.mode_switcher.hide()
        # Code is no longer an area: Logic shows blocks or Python, by project.
        for number, mode in enumerate(("map", "design", "logic"), 1):
            name = MODE_LABELS[mode]
            button = AreaButton()
            button.setIcon(icon(MODE_ICONS[mode]))
            button.setText(name)
            button.setToolTip(name + f" · Ctrl+{number}")
            button.setProperty("mode", True)
            button.setCheckable(True)
            button.setAccessibleName(tr("{mode} mode").format(mode=name))
            button.clicked.connect(lambda _, m=mode: self.set_mode(m))
            self.mode_group.addButton(button)
            self.mode_switcher.add_area(button)
            self.mode_buttons[mode] = button
            action = QAction(tr("{mode} mode").format(mode=name), self)
            action.setShortcut(QKeySequence(f"Ctrl+{number}"))
            action.triggered.connect(lambda _, m=mode: self.set_mode(m))
            self.addAction(action)
        bar.addSeparator()
        self.run_action.setIcon(icon("run"))
        self.run_action.setProperty("makebenchIcon", "run")
        self.run_action.setIconText(tr("Run"))
        bar.addAction(self.run_action)
        run_button = bar.widgetForAction(self.run_action)
        run_button.setProperty("primary", True)
        run_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.stop_action = QAction(icon("stop"), tr("Stop test"), self)
        self.stop_action.setShortcut(QKeySequence("Shift+F5"))
        self.stop_action.setProperty("makebenchIcon", "stop")
        self.stop_action.triggered.connect(self.stop_test)
        bar.addAction(self.stop_action)
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy

        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar_spacer = bar.addWidget(spacer)
        search = QToolButton()
        search.setIcon(icon("search"))
        search.setProperty("makebenchIcon", "search")
        search.setText(tr("Search commands…") + "   Ctrl+K")
        search.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        search.setToolTip(tr("Command palette…"))
        search.setAccessibleName(tr("Command palette…"))
        search.setMinimumWidth(220)
        search.clicked.connect(self.show_commands)
        bar.addWidget(search)
        # The test state lives in the status bar; the toolbar keeps the commands.
        self.test_status = QLabel(tr("Stopped"))
        self.test_status.setMaximumWidth(190)
        self.workspace_toolbar = bar
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        view = self.menuBar().addMenu(tr("&View"))
        for label, shortcut, callback in [
            (tr("Left panel"), "Ctrl+B", lambda: self.toggle_side("left")),
            (tr("Inspector"), "Ctrl+Alt+B", lambda: self.toggle_side("right")),
            (tr("Output and problems"), "Ctrl+J", self.toggle_drawer),
            (tr("Command palette…"), "Ctrl+K", self.show_commands),
            (tr("Preferences…"), "Ctrl+,", self.preferences),
            (tr("Cycle focus region"), "F6", self.cycle_focus),
        ]:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            view.addAction(action)
        from .panels import add_panel_menu

        add_panel_menu(self, view)
        view.addAction(self.home_action)
        grid = view.addAction(tr("Snap to grid"))
        grid.setCheckable(True)
        grid.setChecked(self.snap_check.isChecked())
        grid.toggled.connect(self.snap_check.setChecked)
        self.snap_check.hide()
        self.command_palette_action = next(
            a for a in view.actions() if a.text().startswith(tr("Command palette"))
        )
        register(self)
        manager().changed.connect(self.theme_changed)
        self.mode_buttons["design"].setChecked(True)
        self.tabs.currentChanged.connect(self.sync_mode_button)
        self.logic.script_requested.connect(self.edit_script_inline)
        self.script_apply.clicked.connect(self.apply_script_inline)
        self.script_editor.textChanged.connect(self.script_text_changed)
        self.logic.before_switch = self.prepare_script_change
        script_action = QAction(tr("Apply script"), self)
        script_action.setShortcut(QKeySequence("Ctrl+Return"))
        script_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        script_action.triggered.connect(self.apply_script_inline)
        self.script_editor.addAction(script_action)
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setInterval(30000)
        self.recovery_timer.timeout.connect(self.snapshot_recovery)
        self.recovery_timer.start()
        self.run_number = 0
        self.install_projects()
        self.install_navigation_editor()
        self.install_designer()
        self.install_development()
        self.install_execution()
        from .publish import ExportDialog

        self.publish_dialog = ExportDialog(self)
        self.publish_panel = self.publish_dialog.panel
        self.export_action = QAction(icon("export"), tr("Export application…"), self)
        self.export_action.setProperty("makebenchIcon", "export")
        self.export_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.export_action.triggered.connect(self.export_application)
        self.export_action.setIconText(tr("Publish…"))
        self.workspace_toolbar.insertAction(self.toolbar_spacer, self.export_action)
        self.workspace_toolbar.widgetForAction(self.export_action).setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        project_menu = next(
            (
                a.menu()
                for a in self.menuBar().actions()
                if a.text().replace("&", "") == tr("Project")
            ),
            None,
        ) or self.menuBar().addMenu(tr("&Project"))
        project_menu.addAction(tr("Application settings…"), self.application_settings)
        self.convert_python_action = project_menu.addAction(
            tr("Convert to Python…"), self.convert_to_python
        )
        project_menu.addAction(self.export_action)
        from .settings import show_diagnostic, open_checklist, apply_preferences

        help_menu = next(
            a.menu() for a in self.menuBar().actions() if a.text().replace("&", "") == tr("Help")
        )
        from .guide import ShortcutReference, show_guide

        guide = help_menu.addAction(tr("Getting started"), lambda: show_guide(self))
        guide.setShortcut(QKeySequence("F1"))
        help_menu.addAction(tr("Keyboard shortcuts"), lambda: ShortcutReference(self).exec())
        help_menu.addAction(tr("Environment diagnostics…"), lambda: show_diagnostic(self))
        help_menu.addAction(tr("User guide"), lambda: open_checklist(self))
        gear = QToolButton()
        gear.setIcon(icon("settings"))
        gear.setToolTip(tr("Application settings"))
        gear.clicked.connect(self.application_settings)
        sl.insertWidget(0, gear, 0, Qt.AlignmentFlag.AlignRight)
        gear.setProperty("makebenchIcon", "settings")
        apply_preferences(self)
        tidy_menus(self)
        register(self)

    def export_application(self):
        """Open an export window without replacing or tearing down the workspace."""
        if not self._finish_field_edit():
            return
        self.publish_panel.sync()
        self.publish_dialog.show()
        self.publish_dialog.raise_()
        self.publish_dialog.activateWindow()

    def insert_kind(self, kind):
        """Insert a tool using the same history as the drag palette."""
        self.palette.setCurrentRow(self.palette.findData(kind.value))
        self.add_component()

    def set_mode(self, mode):
        """Switch tasks keeping the selection and the blocks' confirmation."""
        if mode == "publish":
            self.export_application()
            return
        if getattr(self, "_compact_home", False):
            self._compact_home = False
            self.setMinimumSize(980, 600)
            self.resize(1280, 800)
        if mode == "logic" and self.project.programming == "python":
            mode = "code"
        if self.project.metadata.get("empty_map") and mode in {"design", "logic", "code"}:
            mode = "map"
            self.statusBar().showMessage(
                tr("Create the first interface in the map to get started."), 6000
            )
        indexes = {"design": 0, "logic": 1, "code": 2, "map": 3}
        index = indexes[mode]
        if index >= self.tabs.count():
            return
        self.pages.setCurrentWidget(self.editor_page)
        self.workspace_toolbar.show()
        if (
            mode == "design"
            and hasattr(self, "zoom_view")
            and getattr(self, "_fitted_interface", None) != (self.project.id, self.active_window)
        ):
            self._fitted_interface = (self.project.id, self.active_window)
            QTimer.singleShot(0, self.zoom_view.fit)
        if mode == "logic" and self.tabs.currentIndex() != 1:
            self.logic.select_component_event(self.selected_id, self.active_state)
        self.tabs.setCurrentIndex(index)
        self.sync_mode_button(self.tabs.currentIndex())
        from .controls import name_unlabeled_buttons

        name_unlabeled_buttons(self)

    def sync_mode_button(self, index):
        """Follow shortcuts and automatic navigation to the origin of errors."""
        modes = ["design", "logic", "code", "map"]
        if 0 <= index < len(modes):
            self._mode = modes[index]
            self.mode_buttons["logic" if self._mode == "code" else self._mode].setChecked(True)
        if hasattr(self, "zoom_actions"):
            for action in self.zoom_actions:
                action.setVisible(True)
                action.setEnabled(self._mode in {"design", "map"})
        if hasattr(self, "overview_action"):
            self.overview_action.setVisible(True)
        for name, button in self.mode_buttons.items():
            button.setVisible(True)
            button.setEnabled(
                not self.project.metadata.get("empty_map") or name in {"map", "publish"}
            )
        self.sync_studio()
        if hasattr(self, "zoom_reset_button"):
            self.update_zoom_label()

    def sync_studio(self):
        """Update only derived data; never runs project code."""
        if not hasattr(self, "project_heading"):
            return
        empty = bool(self.project.metadata.get("empty_map"))
        for name, button in self.mode_buttons.items():
            button.setEnabled(not empty or name in {"map", "publish"})
        dirty = self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty()
        self.project_heading.setText(self.project.name + (" •" if dirty else ""))
        node = self.project.find(self.selected_id)
        context = (
            ""
            if self._mode in {"map", "publish"} or node is None or node.kind.value == "window"
            else node.display_name
        )
        self.context_label.setText(
            self.context_label.fontMetrics().elidedText(context, Qt.TextElideMode.ElideRight, 185)
        )
        self.context_label.setToolTip(context)
        data_signature = (id(self.project), self.project.id, self.history._index, self.source.text)
        if getattr(self, "_data_signature", None) != data_signature:
            self._data_signature = data_signature
            self.data_list.clear()
            self.list_resources()
            from makebench.core.logic import function_names

            for name in function_names(self.source.text)[0]:
                self.data_list.addItem(tr("Function") + " · " + name + tr("(ctx, value)"))
            self.sync_variables()
            self.sync_collections()
        self.sync_navigation()
        self.sync_problems()
        self.sync_outline()
        if hasattr(self, "publish_dialog") and self.publish_dialog.isVisible():
            self.publish_panel.sync()
        if hasattr(self, "map_panel") and self.tabs.currentIndex() == 3:
            self.map_panel.sync()
        from .shell import sync_shell

        sync_shell(self)

    def sync_problems(self):
        """Gather static diagnostics, linked to their flow or line."""
        if not hasattr(self, "code_index"):
            return
        import json
        from makebench.core.source import source_signature

        signature = (
            source_signature(self.source.text),
            json.dumps(self.project.workflows, sort_keys=True),
            tuple((r.id, r.properties.get("title")) for r in self.project.roots),
            self.project.entry_window,
            self.project.programming,
            json.dumps(self.project.metadata.get("collections", []), sort_keys=True),
        )
        if signature == getattr(self, "_problems_signature", None):
            return
        self._problems_signature = signature
        self.problems.clear()
        self._problem_targets = []
        import ast

        self.refresh_code_index()
        for error in self.code_index.errors:
            self._add_problem(
                f"{error['file']}:{error['line']}:{error['column']} · {error['message']}",
                {
                    "source_file": error["file"],
                    "source_line": error["line"],
                    "column": error["column"],
                },
            )
        from makebench.core.logic import function_names

        names = set(function_names(self.source.text)[0])
        blocks = self.project.programming == "blocks"

        def visit(value, flow):
            """Walk structured data without running project content."""
            if isinstance(value, dict):
                if value.get("op") == "call" and blocks:
                    self._add_problem(
                        tr(
                            "{flow}: this block calls Python. Convert the project to Python or use a block function."
                        ).format(flow=flow.get("name", tr("Flow"))),
                        {"flow": flow["id"], "block": value["id"]},
                    )
                elif value.get("op") == "call" and value.get("function") not in names:
                    self._add_problem(
                        tr("Missing function: {name}").format(name=value.get("function", "")),
                        {"flow": flow["id"], "block": value["id"]},
                    )
                self._check_collection_use(value, flow)
                for child in value.values():
                    visit(child, flow)
            elif isinstance(value, list):
                for child in value:
                    visit(child, flow)

        from makebench.core.logic import editable

        if not editable(self.project):
            self._add_problem(
                tr("Reserved flows were kept. Running them requires a compatible version."), {}
            )
        from makebench.core.logic import is_draft

        for flow in self.project.editable_flows:
            if "function" in flow and flow["function"] not in names:
                self._add_problem(
                    tr("{flow}: function {name}() not found in the actions file.").format(
                        flow=flow.get("name", tr("Flow")), name=flow["function"]
                    ),
                    {"flow": flow["id"]},
                )
            if is_draft(flow):
                self._add_problem(
                    flow.get("name", tr("Flow"))
                    + ": "
                    + ("; ".join(flow.get("errors", [])) or tr("Complete the blocks.")),
                    {"flow": flow["id"]},
                )
            visit(flow.get("body"), flow)
        from makebench.core.navigation import navigation_edges

        incoming = {
            edge["target"] for edge in navigation_edges(self.project) if edge["op"] == "open_window"
        }
        if not self.project.metadata.get("empty_map"):
            for root in self.project.roots:
                if (
                    root.id != (self.project.entry_window or self.project.root.id)
                    and root.id not in incoming
                ):
                    self._add_problem(
                        tr(
                            "Warning · {window}: no incoming transition from blocks. Python functions can open it."
                        ).format(window=root.properties.get("title", tr("Window"))),
                        {"component": root.id},
                    )
        if not self.problems.count():
            item = QListWidgetItem(tr("No problems found."))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.problems.addItem(item)
        count = len(self._problem_targets)
        self.drawer.setTabText(
            1, tr("Problems ({count})").format(count=count) if count else tr("Problems")
        )
        self.mode_buttons["logic"].setToolTip(
            MODE_LABELS["logic"]
            + " · Ctrl+3"
            + (
                " · " + ntr("{count} problem", "{count} problems", count).format(count=count)
                if count
                else ""
            )
        )

    def _check_collection_use(self, block, flow):
        """Warn when a block cites a collection or a field the project does not declare."""
        from makebench.core.datamodel import find_collection, find_field

        name = block.get("collection")
        if name is None:
            return
        target = {"flow": flow["id"], "block": block.get("id")}
        found = find_collection(self.project.metadata, name)
        if found is None:
            self._add_problem(
                tr("{flow}: collection {name} not found.").format(
                    flow=flow.get("name", tr("Flow")), name=name
                ),
                target,
            )
            return
        cited = [block.get(key) for key in ("field", "order", "sum")]
        cited += [e.get("field") for e in block.get("values", []) if isinstance(e, dict)]
        for field in cited:
            if isinstance(field, str) and not field.startswith("@") and field != "id":
                if find_field(found, field) is None:
                    self._add_problem(
                        tr("{flow}: field {field} not found in {collection}.").format(
                            flow=flow.get("name", tr("Flow")), field=field, collection=found["name"]
                        ),
                        target,
                    )

    def _add_problem(self, label, target):
        """Add a navigable row without interpreting text as an instruction."""
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, target)
        self.problems.addItem(item)
        self._problem_targets.append(target)

    def go_to_problem(self, item):
        """Select the diagnostic's source file or flow."""
        target = item.data(Qt.ItemDataRole.UserRole)
        if not target:
            return
        if target.get("component"):
            self.navigate_to_item("component", target["component"])
        elif target.get("source_line"):
            self.open_code_file(
                target.get("source_file", "@actions"),
                target["source_line"],
                target.get("column", 1),
            )
        elif target.get("flow"):
            self.navigate_to_item("flow", target["flow"])
            if target.get("block"):
                self.logic.focus_block(target["flow"], target["block"])

    def toggle_drawer(self):
        """Collapse the drawer without losing logs or a script being edited."""
        self.drawer.setVisible(not self.drawer.isVisible())

    def show_commands(self):
        """Open the search over the same QActions used by the menus."""
        import ast
        from PySide6.QtGui import QAction

        palette = CommandPalette(register(self), self)
        dynamic = []

        def add(label, callback):
            """Bind a temporary entry to the real item of the current document."""
            action = QAction(label, palette)
            action.triggered.connect(callback)
            dynamic.append(action)

        for node in self.project.walk():
            owner = self.project.window_of(node.id)
            add(
                tr("Go to component")
                + " · "
                + owner.properties.get("title", tr("Window"))
                + " › "
                + (node.properties.get("code_name") or node.display_name),
                lambda _, identifier=node.id: self.navigate_to_item("component", identifier),
            )
        for owner, states in self.project.states.items():
            for state in states:
                add(
                    tr("Go to state")
                    + " · "
                    + self.project.find(owner).properties.get("title", tr("Window"))
                    + " › "
                    + state["name"],
                    lambda _, identifier=state["id"], owner=owner: self.navigate_to_item(
                        "state", identifier, owner
                    ),
                )
        for flow in self.project.editable_flows:
            add(
                tr("Go to flow") + " · " + flow["name"],
                lambda _, identifier=flow["id"]: self.navigate_to_item("flow", identifier),
            )
        try:
            for node in ast.parse(self.source.text).body:
                if isinstance(node, ast.FunctionDef):
                    add(
                        tr("Go to function") + " · " + node.name,
                        lambda _, name=node.name: self.find_function_name(name),
                    )
        except (SyntaxError, ValueError):
            pass
        palette.actions.extend(dynamic)
        palette.filter("")
        palette.exec()
        palette.deleteLater()

    def filter_tree(self, query):
        """Keep ancestors visible when a descendant matches the search."""

        def match(item):
            """Keep ancestors visible when a descendant matches the search."""
            visible = query.casefold() in item.text(0).casefold()
            for n in range(item.childCount()):
                visible = match(item.child(n)) or visible
            item.setHidden(not visible)
            return visible

        for n in range(self.tree.topLevelItemCount()):
            match(self.tree.topLevelItem(n))

    def preferences(self):
        """Open Qt preferences, applied immediately and searchable across all pages."""
        from .settings import EditorPreferences

        self.preferences_dialog = EditorPreferences(self)
        self.preferences_dialog.show()

    def convert_to_python(self, confirm=True):
        """Turn every block event into a Python function, keeping a .bak-blocks copy."""
        import json
        from pathlib import Path
        from PySide6.QtWidgets import QMessageBox
        from makebench.core.codegen import convert_to_python
        from makebench.core.project import ProjectError

        if not self._finish_field_edit():
            return False
        if self.project.programming == "python":
            self._show_error(tr("This project is already written in Python."))
            return False
        if confirm and (
            QMessageBox.question(
                self,
                tr("Convert to Python"),
                tr(
                    "Each event becomes a Python function in the actions file, and the project "
                    "is programmed in Python from now on. A copy of the blocks is kept next to "
                    "the project as .bak-blocks. Continue?"
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return False
        before = self.project.to_dict()
        try:
            source = convert_to_python(self.project, self.source_editor.toPlainText())
        except ProjectError as exc:
            self._show_error(exc, tr("Could not convert to Python"))
            return False
        try:
            if self.path:
                backup = Path(str(self.path) + ".bak-blocks")
                backup.write_text(json.dumps(before, ensure_ascii=False, indent=2), "utf-8")
            if self.source.path:
                Path(str(self.source.path) + ".bak-blocks").write_text(self.source.text, "utf-8")
        except OSError as exc:
            self.project = type(self.project).from_dict(before)
            self._show_error(exc, tr("Could not keep a copy of the blocks"))
            return False
        cursor = self.source_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.insertText(source)
        self.history.push(self.project, tr("Convert to Python"))
        self._refresh()
        if self.path:
            self.save_to(self.path)
        self.set_mode("logic")
        return True

    def application_settings(self, field=None):
        """Open the single settings center of the application being built."""
        if not self._finish_field_edit():
            return
        from .settings import ApplicationSettings

        self.app_settings_dialog = ApplicationSettings(self)
        mapping = {"icon": 1, "packages": 3, "dependencies": 3, "permissions": 4, "destinations": 7}
        self.app_settings_dialog.sections.setCurrentRow(mapping.get(field, 0))
        if field in self.app_settings_dialog.fields:
            self.app_settings_dialog.fields[field].setFocus()
        self.app_settings_dialog.show()

    def edit_script_inline(self, data):
        """Edit a literal in the bottom panel, keeping the Blockly token and identifier."""
        target = (self.logic.token, data["id"])
        if getattr(self, "_script_target", None) == target and self.script_dirty():
            self.drawer.show()
            self.drawer.setCurrentIndex(2)
            self.script_editor.setFocus()
            return
        if not self.prepare_script_change():
            return
        self._script_target = target
        self._script_original = data["text"]
        flow = next((f for f in self.project.editable_flows if f["id"] == self.logic.flow_id), None)
        self.script_context.setText(
            (
                tr("Event:")
                + " "
                + flow["name"]
                + " · "
                + self.project.window_of(flow["event"]["component"]).properties.get(
                    "title", tr("Window")
                )
            )
            if flow
            else tr("Text of the selected block")
        )
        self.script_editor.setPlainText(data["text"])
        self.script_apply.setEnabled(False)
        self.drawer.show()
        self.drawer.setCurrentIndex(2)
        self.script_editor.setFocus()

    def apply_script_inline(self):
        """Apply text only to the workspace the edit came from."""
        import json

        target = getattr(self, "_script_target", None)
        if not target or target[0] != self.logic.token:
            self.script_apply.setEnabled(False)
            return
        text = self.script_editor.toPlainText()
        code = (
            "window.makebench.setTextValue(" + json.dumps(target[1]) + "," + json.dumps(text) + ")"
        )

        def applied(result):
            """Commit the buffer only when Blockly accepted the text at the right target."""
            if result and getattr(self, "_script_target", None) == target:
                self._script_original = text
                self.script_apply.setEnabled(self.script_dirty())
                self._update_actions()

        self.logic.page.runJavaScript(code, applied)

    def script_dirty(self):
        """Include text not applied yet in the changes notice and in recovery."""
        return bool(
            getattr(self, "_script_target", None)
            and self.script_editor.toPlainText() != getattr(self, "_script_original", "")
        )

    def script_text_changed(self):
        """Keep applying and the changes indicator available while typing."""
        self.script_apply.setEnabled(self.script_dirty())
        if hasattr(self, "project_heading"):
            self._update_actions()

    def prepare_script_change(self):
        """Confirm a pending script before saving, switching flows, undoing or closing."""
        if not self.script_dirty():
            return True
        target = getattr(self, "_script_target", None)
        if not self.logic.ready or target[0] != self.logic.token or self.logic._flushing:
            self.statusBar().showMessage(
                tr(
                    "The script is still in the drawer. Copy the text or go back to the block before continuing."
                ),
                8000,
            )
            return False
        self.apply_script_inline()
        return self.logic.flush() and not self.script_dirty()

    def stop_test(self):
        """Request a real cancellation, respecting active administrative tasks."""
        if self.runtime_window:
            self.runtime_window.stop()

    def cycle_focus(self):
        """Cycle through the workbench regions by keyboard, including a way out of the canvas."""
        regions = (
            [self.tree, self.canvas, self.inspector, self.drawer]
            if self._mode == "design"
            else [self.logic.events, self.logic.view, self.logic.code, self.drawer]
            if self._mode == "logic"
            else [self.code_files, self.source_editor, self.function_outline, self.drawer]
        )
        regions = [region for region in regions if region is not None and region.isVisible()]
        current = QApplication.focusWidget()
        index = (
            next(
                (
                    i
                    for i, region in enumerate(regions)
                    if region is current or region.isAncestorOf(current)
                ),
                -1,
            )
            if current
            else -1
        )
        if regions:
            regions[(index + 1) % len(regions)].setFocus(Qt.FocusReason.ShortcutFocusReason)

    def theme_changed(self, _tokens):
        """Update icons and keep the selection/fields intact when switching appearance."""
        register(self)
        QTimer.singleShot(0, self, self._sync_native_bars)
        if getattr(self, "project", None) is not None and _tokens.get("look") != getattr(
            self, "_preview_look", None
        ):
            self._preview_look = _tokens.get("look")
            self.canvas.set_project(self.project)
        from PySide6.QtWidgets import QAbstractButton

        for button in self.findChildren(QAbstractButton):
            symbol = button.property("makebenchIcon")
            if symbol:
                button.setIcon(icon(symbol))
        for index in range(self.palette.count()):
            item = self.palette.item(index)
            item.setIcon(icon(item.data(Qt.ItemDataRole.UserRole)))
        for mode, button in self.mode_buttons.items():
            button.setIcon(icon(MODE_ICONS[mode]))
        for identifier, item in self._tree_items.items():
            node = self.project.find(identifier)
            if node:
                item.setIcon(0, icon(node.kind.value))
        from .shell import sync_shell

        sync_shell(self)

    def toggle_side(self, side):
        """Toggle only the panel that belongs to the current mode."""
        target = None
        if self._mode == "design":
            self.design_host.toggle_side(side)
        elif self._mode == "logic" and side == "right":
            target = self.logic.splitter.widget(1)
        elif self._mode == "map":
            target = self.map_panel.outline_panel if side == "left" else self.map_panel.details
        elif self._mode == "code" and side == "right":
            target = self.function_outline.parentWidget()
        elif self._mode == "publish" and side == "left":
            target = self.publish_panel.checks
        if target:
            target.setVisible(not target.isVisible())

    def navigate_to_item(self, kind, identifier, owner=None):
        """Find components, states and flows, keeping pending text and context."""
        if not self._finish_field_edit():
            return
        if kind == "state":
            self.activate_window(owner, identifier)
            self.set_mode("design")
            return
        if kind == "flow":
            flow = next((f for f in self.project.editable_flows if f["id"] == identifier), None)
            if flow is None:
                # Block functions have no event: they open in Logic as they are.
                self.set_mode("logic")
                self.logic.sync(identifier)
                return
            window = self.project.window_of(flow["event"]["component"])
            self.activate_window(window.id, (flow.get("states") or ["@default"])[0])
            self._select(flow["event"]["component"])
            if "function" in flow:
                self.open_event_function(identifier)
                return
            self.set_mode("logic")
            self.logic.sync(identifier)
            return
        node = self.project.find(identifier)
        if node:
            window = self.project.window_of(identifier)
            self.activate_window(
                window.id, self.active_state if window.id == self.active_window else "@default"
            )
            self._select(identifier)
            self.set_mode("design")
