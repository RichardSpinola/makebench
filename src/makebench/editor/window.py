# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: visual interface, blocks and Python functions."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolBar,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QTabWidget,
)

from copy import deepcopy
from makebench.core.logic import create_flow, create_python_event, editable, validate
from makebench.core.source import ENTRY_FILE, SourceBuffer
from makebench.editor.code import CodeEditor
from makebench.editor.logic import LogicPanel
from makebench.core.history import History
from makebench.core.project import (
    Component,
    ComponentKind,
    LayoutKind,
    Project,
    ProjectError,
)
from makebench.core.storage import load_project, save_workspace
from makebench.editor.assets import AssetStore
from makebench.editor.canvas import PreviewCanvas
from makebench.editor.drag import ComponentPalette, ComponentTree
from makebench.editor.inspector import Inspector
from makebench import __version__


from .studio import StudioMixin
from makebench.i18n import ntr, tr


def application_icon():
    """The Makebench application icon, or None when the file is missing."""
    path = Path(__file__).with_name("makebench.svg")
    return QIcon(str(path)) if path.is_file() else None


def undo_labels():
    """Names shown by Undo/Redo, keyed by the editor command that made the change."""
    return {
        "edit_resource": tr("Replace image"),
        "mouseReleaseEvent": tr("Move in the map"),
        "contextMenuEvent": tr("Create interface"),
        "new_window_dialog": tr("Create interface"),
        "new_state_dialog": tr("Create state"),
        "make_entry_window": tr("Set start window"),
        "make_initial_state": tr("Set initial state"),
        "rename_state_dialog": tr("Rename state"),
        "restore_default_properties": tr("Restore from Default"),
        "remove_state": tr("Remove state"),
        "remove_window": tr("Remove window"),
        "duplicate_interface": tr("Duplicate interface"),
        "set_initial": tr("Set as initial"),
        "connect_nodes": tr("Connect interfaces"),
        "edit_edge": tr("Edit transition"),
        "remove_edge": tr("Remove transition"),
        "organize": tr("Arrange map"),
        "selection_command": tr("Align selection"),
        "restore_state_property": tr("Restore property"),
        "import_image_drop": tr("Insert image"),
        "add_component": tr("Add component"),
        "_on_drop": tr("Drop component"),
        "_commit_geometry": tr("Move or resize"),
        "duplicate_component": tr("Duplicate"),
        "reorder_component": tr("Reorder"),
        "add_page": tr("Add page"),
        "choose_image": tr("Choose image"),
        "clear_image": tr("Remove image"),
        "remove_component": tr("Remove component"),
        "remove_flow": tr("Remove flow"),
        "change_flow_filter": tr("Change state filter"),
        "variable_dialog": tr("Edit variable"),
        "remove_variable": tr("Remove variable"),
        "duplicate_flow_dialog": tr("Duplicate flow"),
        "insert_behavior": tr("Insert behavior"),
        "_toggle_breakpoint": tr("Toggle breakpoint"),
        "choose_window_icon": tr("Choose window icon"),
    }


class MainWindow(StudioMixin, QMainWindow):
    """Coordinate the document, history, selection and file commands.

    The document is the source of truth; tree, preview and properties are views.
    The interface and blocks produce data/Python; running needs an explicit action.
    """

    def __init__(self, project: Project | None = None, path: Path | None = None) -> None:
        """Open a given project or start a new empty interface."""
        super().__init__()
        from .theme import manager
        from .dialogs import install_translation

        manager()
        from .theme import icon

        self.setWindowIcon(application_icon() or icon("window"))
        if not hasattr(QApplication.instance(), "_makebench_dialog_filter"):
            install_translation(QApplication.instance())
        self.project = project or Project.empty()
        self.path = path.resolve() if path else None
        self.source = SourceBuffer.load(self.path)
        self.history = History(self.project)
        self._saved_document = self.project.to_dict() if self.path else None
        self.assets = AssetStore(path.parent if path else None)
        self.selected_id = self.project.root.id
        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._refreshing = False
        self.runtime_window = None
        self._closing_after_runtime = False
        self.resize(1280, 800)
        self.setMinimumSize(980, 600)
        self.setWindowModified(False)
        self._create_actions()
        self._create_workspace()
        self.install_studio()
        from .project_search import install_project_search

        search = install_project_search(self)
        edit_menu = next(
            (a.menu() for a in self.menuBar().actions() if a.text() == tr("&Edit")), None
        )
        if edit_menu is not None:
            edit_menu.addSeparator()
            edit_menu.addAction(search)
            from .pieces import install_pieces

            install_pieces(self, edit_menu)
        from .plugins_ui import install_plugins

        help_entry = next((a for a in self.menuBar().actions() if a.text() == tr("&Help")), None)
        install_plugins(self, help_entry)
        if hasattr(self, "pieces_menu"):
            from .pieces import rebuild_menu as rebuild_pieces

            rebuild_pieces(self)
        from .history_panel import install_history

        history_action = install_history(self)
        file_menu = next(
            (a.menu() for a in self.menuBar().actions() if a.text() == tr("&File")), None
        )
        if file_menu is not None:
            file_menu.insertAction(file_menu.actions()[-2], history_action)
        from .shell import install_shell

        install_shell(self, application_icon())
        from .commands import menu_icons

        menu_icons(self)
        self._refresh()
        self.remember_project()

    def showEvent(self, event):
        """Wait for the style to polish the bars before checking the native palette."""
        super().showEvent(event)
        QTimer.singleShot(0, self, self._sync_native_bars)
        from .controls import name_unlabeled_buttons

        name_unlabeled_buttons(self)

    def changeEvent(self, event):
        """Theme and activation can change the special colors of KDE headers."""
        super().changeEvent(event)
        if event.type() in {
            QEvent.Type.ActivationChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        } and hasattr(self, "workspace_toolbar"):
            QTimer.singleShot(0, self, self._sync_native_bars)

    def _sync_native_bars(self):
        """Fix only illegible text in already built bars, outside style events."""
        from .theme import manager

        for bar in (self.menuBar(), self.workspace_toolbar):
            manager().repair_bar_palette(bar)

    def _create_actions(self) -> None:
        """Register the menus and shortcuts that have implemented behavior."""
        file_menu = self.menuBar().addMenu(tr("&File"))
        edit_menu = self.menuBar().addMenu(tr("&Edit"))
        run_menu = self.menuBar().addMenu(tr("&Run"))
        self.run_action = QAction(tr("Test application"), self)
        self.run_action.setShortcut(QKeySequence("F5"))
        self.run_action.triggered.connect(self.run_project)
        run_menu.addAction(self.run_action)
        self.debug_action = QAction(tr("Debug application"), self)
        self.debug_action.setShortcut(QKeySequence("F9"))
        self.debug_action.triggered.connect(self.debug_project)
        run_menu.addAction(self.debug_action)
        for title, shortcut, action in [
            (tr("Continue"), "F8", "continue"),
            (tr("Next step"), "F10", "step_over"),
            (tr("Step into function"), "F11", "step_in"),
            (tr("Step out of function"), "Shift+F11", "step_out"),
        ]:
            command = QAction(title, self)
            command.setShortcut(QKeySequence(shortcut))
            command.triggered.connect(lambda _, action=action: self.debug_command(action))
            run_menu.addAction(command)

        help_menu = self.menuBar().addMenu(tr("&Help"))
        self.new_action = QAction(tr("New project"), self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_project)
        self.open_action = QAction(tr("Open…"), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_project)
        self.save_action = QAction(tr("Save"), self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save)
        save_as_action = QAction(tr("Save as…"), self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        quit_action = QAction(tr("Quit"), self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        self.example_action = QAction(tr("Open example…"), self)
        self.example_action.triggered.connect(self.open_example_dialog)
        file_menu.addActions(
            [
                self.new_action,
                self.open_action,
                self.example_action,
                self.save_action,
                save_as_action,
            ]
        )
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        self.undo_action = QAction(tr("Undo"), self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction(tr("Redo"), self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        self.redo_action.triggered.connect(self.redo)
        self.remove_action = QAction(tr("Remove component"), self)
        self.remove_action.triggered.connect(self.remove_component)
        edit_menu.addActions([self.undo_action, self.redo_action, self.remove_action])
        self.duplicate_action = QAction(tr("Duplicate"), self)
        self.duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        self.duplicate_action.triggered.connect(self.duplicate_component)
        self.up_action = QAction(tr("Move before"), self)
        self.up_action.setShortcut(QKeySequence("Alt+Up"))
        self.up_action.triggered.connect(lambda: self.reorder_component(-1))
        self.down_action = QAction(tr("Move after"), self)
        self.down_action.setShortcut(QKeySequence("Alt+Down"))
        self.down_action.triggered.connect(lambda: self.reorder_component(1))
        self.page_action = QAction(tr("Add page"), self)
        self.page_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.page_action.triggered.connect(self.add_page)
        edit_menu.addActions(
            [self.duplicate_action, self.up_action, self.down_action, self.page_action]
        )
        align_menu = edit_menu.addMenu(tr("Align in the free area"))
        self.align_actions = []
        for mode, label in (
            ("left", tr("Left")),
            ("center_x", tr("Center horizontally")),
            ("right", tr("Right")),
            ("top", tr("Top")),
            ("center_y", tr("Center vertically")),
            ("bottom", tr("Bottom")),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _, mode=mode: self.align_component(mode))
            align_menu.addAction(action)
            self.align_actions.append(action)
        about_action = QAction(tr("About Makebench"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        toolbar = QToolBar(tr("Project"), self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        toolbar.addActions([self.duplicate_action, self.page_action])
        toolbar.addSeparator()
        toolbar.addAction(self.run_action)
        toolbar.addSeparator()
        self.snap_check = QCheckBox(tr("Snap to grid"))
        self.snap_check.setChecked(True)
        self.snap_check.setToolTip(tr("Snap dragging and resizing to 8-pixel steps."))
        self.snap_check.toggled.connect(
            lambda enabled: setattr(self.canvas, "snap", 8 if enabled else 1)
        )
        toolbar.addWidget(self.snap_check)
        self.addToolBar(toolbar)

    def _create_workspace(self) -> None:
        """Build the three panels: components, preview and properties."""
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        brand = QLabel("Makebench")
        font = brand.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        brand.setFont(font)
        left_layout.addWidget(brand)
        subtitle = QLabel(tr("Shape your application."))
        subtitle.setWordWrap(True)
        left_layout.addWidget(subtitle)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel(tr("Add component")))
        self.palette = ComponentPalette()
        self.palette.add_requested.connect(self.add_component)
        left_layout.addWidget(self.palette)
        add_button = QPushButton(tr("Add to interface"))
        add_button.clicked.connect(self.add_component)
        left_layout.addWidget(add_button)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel(tr("Components")))
        self.tree = ComponentTree(lambda: self.project, self._can_drop)
        self.tree.drop_requested.connect(self._on_drop)
        self.tree.remove_requested.connect(self.remove_component)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        left_layout.addWidget(self.tree, 1)
        remove_button = QPushButton(tr("Remove selected"))
        remove_button.clicked.connect(self.remove_component)
        self.remove_action.changed.connect(
            lambda: remove_button.setEnabled(self.remove_action.isEnabled())
        )
        left_layout.addWidget(remove_button)
        splitter.addWidget(left)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        heading = QLabel(tr("Interface"))
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        middle_layout.addWidget(heading)
        hint = QLabel(
            tr(
                "Drag components onto the screen. In free areas, move and resize through the selection."
            )
        )
        hint.setWordWrap(True)
        middle_layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.canvas = PreviewCanvas()
        self.canvas.can_drop = self._can_drop
        self.canvas.component_selected.connect(self._select)
        self.canvas.geometry_committed.connect(self._commit_geometry)
        self.canvas.window_resize_requested.connect(self._resize_window)
        self.canvas.drop_requested.connect(self._on_drop)
        self.canvas.nudge_requested.connect(self.nudge_component)
        self.canvas.remove_requested.connect(self.remove_component)
        scroll.setWidget(self.canvas)
        middle_layout.addWidget(scroll, 1)
        preview_note = QLabel(
            tr("Editing preview · Ctrl+drag moves free components to another container.")
        )
        preview_note.setWordWrap(True)
        middle_layout.addWidget(preview_note)
        splitter.addWidget(middle)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        properties_heading = QLabel(tr("Properties"))
        properties_heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(properties_heading)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        self.inspector = Inspector()
        self.inspector.property_changed.connect(self._change_property)
        self.inspector.image_requested.connect(self.choose_image)
        self.inspector.image_cleared.connect(self.clear_image)
        self.inspector.logic_requested.connect(self.edit_logic)
        self.inspector.icon_requested.connect(self.choose_component_icon)
        self.inspector.navigation_requested.connect(self.reveal_navigation)
        inspector_scroll.setWidget(self.inspector)
        right_layout.addWidget(inspector_scroll)
        splitter.addWidget(right)
        splitter.setSizes([250, 700, 300])
        splitter.setStretchFactor(1, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, tr("Interface"))
        self.logic = LogicPanel(lambda: self.project, lambda: self.source.text)
        self.logic.add_requested.connect(self.edit_logic)
        self.logic.remove_requested.connect(self.remove_flow)
        self.logic.rename_requested.connect(self.rename_flow)
        self.logic.flow_changed.connect(self._receive_flow)
        self.logic.error.connect(self._show_error)
        self.logic.save_requested.connect(self.save)
        self.logic.undo_requested.connect(self.undo)
        self.logic.redo_requested.connect(self.redo)
        self.logic.pending_changed.connect(self._update_actions)
        self.tabs.addTab(self.logic, tr("Logic"))
        code_page = QWidget()
        code_layout = QVBoxLayout(code_page)
        hint = QLabel(
            tr(
                "Edit your functions on the right. The Python on the left follows the blocks and never replaces your functions. Press F5 to test the application in a separate window."
            )
        )
        hint.setWordWrap(True)
        code_layout.addWidget(hint)
        code_splitter = QSplitter()
        generated_box = QWidget()
        generated_layout = QVBoxLayout(generated_box)
        generated_layout.addWidget(QLabel(tr("Generated Python · read-only")))
        self.generated_editor = CodeEditor(True)
        generated_layout.addWidget(self.generated_editor)
        code_splitter.addWidget(generated_box)
        own_box = QWidget()
        own_layout = QVBoxLayout(own_box)
        self.source_label = QLabel(tr("Your functions · saved in the .actions.py file"))
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        own_layout.addWidget(self.source_label)
        self.source_editor = CodeEditor()
        self.source_editor.setPlainText(self.source.text)
        own_layout.addWidget(self.source_editor)
        code_splitter.addWidget(own_box)
        code_layout.addWidget(code_splitter, 1)
        self.code_diagnostics = QLabel()
        self.code_diagnostics.setWordWrap(True)
        self.code_diagnostics.setTextFormat(Qt.TextFormat.PlainText)
        code_layout.addWidget(self.code_diagnostics)
        self.tabs.addTab(code_page, tr("Code"))
        self.source_timer = QTimer(self)
        self.source_timer.setSingleShot(True)
        self.source_timer.setInterval(250)
        self.source_timer.timeout.connect(self._source_analysis_ready)
        self.source_editor.textChanged.connect(self._source_changed)
        self.source_editor.undoAvailable.connect(lambda _: self._update_actions())
        self.source_editor.redoAvailable.connect(lambda _: self._update_actions())
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

    def presentation_signature(self):
        """Identify only composition/context, without rebuilding widgets on logic changes."""
        import json

        return json.dumps(
            {
                "project": self.project.id,
                "assets": id(self.assets),
                "roots": [r.to_dict() for r in self.project.roots],
                "states": self.project.states,
                "window": getattr(self, "active_window", self.project.root.id),
                "state": getattr(self, "active_state", "@default"),
                "backend": self.project.application.get("backend", "qt"),
                "icon": self.project.application.get("icon"),
                "empty": self.project.metadata.get("empty_map", False),
            },
            sort_keys=True,
        )

    def _refresh(self) -> None:
        """Reuse the composition if only logic/metadata changed; structure repaints atomically."""
        from .updates import hold_updates

        if hasattr(self, "refresh_programming_banner"):
            self.refresh_programming_banner()
        signature = self.presentation_signature()
        if signature == getattr(self, "_presentation_signature", None):
            for identifier, item in self._tree_items.items():
                node = self.project.find(identifier)
                count = sum(
                    f["event"]["component"] == identifier for f in self.project.editable_flows
                )
                item.setText(
                    0,
                    ("◌ " if not node.properties.get("visible", True) else "")
                    + (node.properties.get("code_name") or node.display_name)
                    + (
                        " · " + ntr("{count} event", "{count} events", count).format(count=count)
                        if count
                        else ""
                    ),
                )
            self.sync_navigation()
            self._select(self.selected_id)
            self.logic.sync()
            self._update_code()
            self._update_actions()
            return
        # The graphics proxy is not a QWidget child of the main window.
        with hold_updates(self), hold_updates(self.canvas):
            self._rebuild_views()
        self._presentation_signature = self.presentation_signature()

    def _rebuild_views(self) -> None:
        """Update the views from the document and keep a valid selection."""
        self._refreshing = True
        expanded = {
            key: item.isExpanded() for key, item in getattr(self, "_tree_items", {}).items()
        }
        tree_scroll = self.tree.verticalScrollBar().value()
        self._tree_items = {}
        self.tree.clear()
        self.tree._hint = None

        def append(node: Component, parent: QTreeWidgetItem | None = None) -> None:
            """Project a node and its children into the navigation tree."""
            count = sum(
                1
                for flow in self.project.editable_flows
                if flow.get("event", {}).get("component") == node.id
            )
            label = node.properties.get("code_name") or node.display_name
            if not node.properties.get("visible", True):
                label = "◌ " + label
            if count:
                label += " · " + ntr("{count} event", "{count} events", count).format(count=count)
            item = QTreeWidgetItem([label])
            from .theme import icon

            item.setIcon(0, icon(node.kind.value))
            item.setToolTip(
                0,
                node.display_name
                + (
                    " · " + tr("hidden in the application")
                    if not node.properties.get("visible", True)
                    else ""
                )
                + (" · " + tr("container") if node.can_have_children else ""),
            )
            item.setData(0, Qt.ItemDataRole.UserRole, node.id)
            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            self._tree_items[node.id] = item
            if node.kind == ComponentKind.WINDOW and self.project.states.get(node.id):
                group = QTreeWidgetItem([tr("States")])
                item.addChild(group)
                for state in [
                    {
                        "id": "@default",
                        "name": node.properties.get("default_state_name", tr("Default")),
                    },
                    *self.project.states[node.id],
                ]:
                    state_item = QTreeWidgetItem([state["name"]])
                    state_item.setData(
                        0, Qt.ItemDataRole.UserRole, "@state|" + node.id + "|" + state["id"]
                    )
                    group.addChild(state_item)
            for child in node.children:
                append(child, item)

        for root in self.project.roots:
            append(root)
        self.tree.expandAll()
        for key, item in self._tree_items.items():
            if key in expanded:
                item.setExpanded(expanded[key])
        self.tree.verticalScrollBar().setValue(tree_scroll)
        self.canvas.read_asset = self.assets.read
        self.sync_navigation()
        from dataclasses import replace

        root = self.project.effective_root(self.active_window, self.active_state)
        canvas_project = replace(self.project, root=root, windows=[])
        self.canvas.set_project(canvas_project)
        from makebench.core.web import is_web

        # A Web view window holds only its page, so the component library rests.
        self.palette.setEnabled(not is_web(root))
        self.palette.setToolTip(
            tr("This window is a Web view: its content is the page.") if is_web(root) else ""
        )
        if self.project.find(self.selected_id) is None:
            self.selected_id = self.project.root.id
        self._refreshing = False
        # A rebuild also restores entries rejected by validation.
        # The cache only avoids redoing fields on selection clicks with no change.
        self.inspector._binding_signature = None
        if self.selected_id not in getattr(self, "selected_ids", set()):
            self.selected_ids = {self.selected_id}
        self._preserve_multi = True
        self._select(self.selected_id)
        self._preserve_multi = False
        if hasattr(self, "selected_ids"):
            self.selected_ids = {
                identifier for identifier in self.selected_ids if self.project.find(identifier)
            } or {self.selected_id}
            if len(self.selected_ids) > 1:
                self.select_multiple(self.selected_ids)
        self.logic.sync()
        self._update_code()
        self._update_actions()
        if hasattr(self, "zoom_view"):
            self.zoom_view.update_bounds()

    def _select(self, component_id: str) -> None:
        """Group the selection and field swap into a single repaint."""
        from .updates import hold_updates

        with hold_updates(self.inspector):
            self._select_component(component_id)

    def _select_component(self, component_id: str) -> None:
        """Sync the tree selection, preview and properties form."""
        if self._refreshing:
            return
        node = self.project.find(component_id)
        if node is None:
            return
        if not getattr(self, "_preserve_multi", False) and not getattr(self, "_from_tree", False):
            modifiers = QApplication.keyboardModifiers()
            if modifiers & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            ):
                self.selected_ids = getattr(self, "selected_ids", set()) | {component_id}
            elif component_id not in getattr(self, "selected_ids", set()):
                self.selected_ids = {component_id}
        self.selected_id = component_id
        owner = self.project.window_of(component_id)
        if owner and owner.id != self.active_window:
            self.active_window = owner.id
            self.active_state = "@default"
            self._refresh()
            return
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(self._tree_items[component_id])
        self.tree.blockSignals(False)
        self.canvas.select(component_id)
        shown = self.canvas._project.find(component_id) or node
        overrides = {}
        if self.active_state != "@default":
            state = next(
                item
                for item in self.project.states[self.active_window]
                if item["id"] == self.active_state
            )
            overrides = state.get("overrides", {}).get(node.id, {})
        self.inspector.set_component(
            self.project, shown, overrides, self.active_state != "@default"
        )
        if hasattr(self, "selected_ids"):
            self.canvas.select_many(self.selected_ids)
        if len(getattr(self, "selected_ids", [])) > 1:
            self.select_multiple(self.selected_ids)
        self._update_actions()

    def _tree_selection_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        """Receive a mouse or keyboard selection in the tree."""
        if current and not self._refreshing:
            identifier = current.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(identifier, str) and identifier.startswith("@state|"):
                _, window, state = identifier.split("|", 2)
                self.activate_window(window, state)
            elif identifier:
                self._from_tree = True
                self._select(identifier)
                self._from_tree = False

    def _update_actions(self) -> None:
        """Update commands, title and the unsaved-changes indicator."""
        source_active = self.tabs.currentIndex() == 2 and (
            not hasattr(self, "code_files") or self.code_files.currentIndex() > 0
        )
        interface_active = self.tabs.currentIndex() == 0
        home = hasattr(self, "home_page") and self.pages.currentWidget() is self.home_page
        active = self.runtime_window is not None and not self.runtime_window.session.closed
        self.debug_action.setEnabled(not home and not self.project.metadata.get("empty_map"))
        self.sync_breakpoints()
        self.run_action.setEnabled(not home and not self.project.metadata.get("empty_map"))
        self.run_action.setText(tr("Restart test") if active else tr("Test application"))
        self.run_action.setToolTip(self.run_action.text() + " · F5")
        if hasattr(self, "stop_action"):
            self.stop_action.setEnabled(active and not self.runtime_window.session.admin_active)
        self.save_action.setEnabled(not home)
        self.snap_check.setEnabled(interface_active and not home)
        self.undo_action.setEnabled(
            self.active_code_editor().document().isUndoAvailable()
            if source_active
            else self.history.can_undo or self.logic.pending
        )
        self.redo_action.setEnabled(
            self.active_code_editor().document().isRedoAvailable()
            if source_active
            else self.history.can_redo
        )
        # Say what Undo/Redo will act on: the open code file or a named project change.
        if source_active:
            current = self.current_code_file() if hasattr(self, "code_files") else ENTRY_FILE
            name = (
                (self.source.path.name if self.source.path else "project.actions.py")
                if current == ENTRY_FILE
                else Path(current).name
            )
            self.undo_action.setText(tr("Undo in {file}").format(file=name))
            self.redo_action.setText(tr("Redo in {file}").format(file=name))
        else:
            undo, redo = self.history.undo_label, self.history.redo_label
            self.undo_action.setText(
                tr("Undo: {action}").format(action=undo) if undo else tr("Undo")
            )
            self.redo_action.setText(
                tr("Redo: {action}").format(action=redo) if redo else tr("Redo")
            )
        for action in (self.undo_action, self.redo_action):
            action.setToolTip(action.text() + " · " + action.shortcut().toString())
        self.remove_action.setEnabled(
            interface_active
            and (self.selected_id != self.project.root.id or len(self.project.roots) > 1)
        )
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(self.selected_id)
        self.duplicate_action.setEnabled(
            interface_active and parent is not None and editable(self.project)
        )
        self.up_action.setEnabled(
            interface_active and parent is not None and parent.children[0] is not node
        )
        self.down_action.setEnabled(
            interface_active and parent is not None and parent.children[-1] is not node
        )
        self.page_action.setEnabled(interface_active and self._page_group(node) is not None)
        free = parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE
        for action in self.align_actions:
            action.setEnabled(interface_active and bool(free))
        self.setWindowTitle(f"{self.project.name}[*] — Makebench")
        if hasattr(self, "code_files"):
            self.code_files.setTabText(
                1, tr("Your functions") + (" •" if self.source.dirty else "")
            )
        self.setWindowModified(
            self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty()
        )
        self.sync_studio()

    def _change_property(self, component_id: str, key: str, value: object) -> None:
        """Apply a valid property and record a single history change."""
        if self._refreshing:
            return
        before = self.project.to_dict()
        if component_id != "@project" and getattr(self, "active_state", "@default") != "@default":
            from makebench.core.navigation import OVERRIDES

            if key not in OVERRIDES:
                self.statusBar().showMessage(
                    tr("Edit structure and layout in the Default state."), 6000
                )
                self._refresh()
                return
            state = next(
                item
                for item in self.project.states[self.active_window]
                if item["id"] == self.active_state
            )
            state.setdefault("overrides", {}).setdefault(component_id, {})[key] = value
            try:
                Project.from_dict(self.project.to_dict())
            except ProjectError as exc:
                self.project = Project.from_dict(before)
                self._refresh()
                self.statusBar().showMessage(str(exc), 7000)
                return
            self.history.push(self.project, tr("Change property"))
            self._refresh_property(component_id, key)
            return
        if component_id == "@project":
            cleaned = str(value).strip()
            if not cleaned:
                field = self.inspector.findChild(
                    __import__("PySide6.QtWidgets", fromlist=["QLineEdit"]).QLineEdit,
                    "property_name",
                )
                if field:
                    field.setText(self.project.name)
                    field.setModified(False)
                self.statusBar().showMessage(tr("The project name cannot be empty."), 5000)
                return
            if self.project.name == cleaned:
                return
            self.project.name = cleaned
        else:
            node = self.project.find(component_id)
            if node is None:
                return
            if key == "layout":
                if node.layout == LayoutKind(value):
                    return
                try:
                    self.convert_layout(node, value)
                except ProjectError as exc:
                    self._show_error(exc, tr("Could not change the property"))
                    self._refresh()
                    return
            elif key == "alignment_preset":
                if node.properties.get(key) == value:
                    return
                vertical, horizontal = str(value).split("-")
                horizontal = {"left": "start", "center": "center", "right": "end"}[horizontal]
                vertical = {"top": "start", "center": "center", "bottom": "end"}[vertical]
                node.properties.update(
                    alignment_preset=value,
                    align=horizontal if node.layout == LayoutKind.VERTICAL else vertical,
                    distribute=vertical if node.layout == LayoutKind.VERTICAL else horizontal,
                )
            elif key.startswith("geometry."):
                name = key.partition(".")[2]
                if node.geometry[name] == value:
                    return
                node.geometry[name] = int(value)
            else:
                if node.properties.get(key) == value:
                    return
                node.properties[key] = value
        try:
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project = Project.from_dict(before)
            self._refresh()
            self.statusBar().showMessage(str(exc), 7000)
            return
        self.history.push(self.project, tr("Change property"))
        self._refresh_property(component_id, key)

    def _refresh_property(self, identifier, key, finish=True):
        """Update values without destroying the field being edited or the widget tree."""
        structural = {
            "layout",
            "size_mode",
            "align",
            "distribute",
            "alignment_preset",
            "initial_page",
        }
        if (
            key in structural
            or key in {"width", "height", "resizable", "theme", "accent", "background"}
            or key == "icon"
            and self.project.find(identifier).kind == ComponentKind.WINDOW
        ):
            self.setUpdatesEnabled(False)
            try:
                self._refresh()
            finally:
                self.setUpdatesEnabled(True)
            return
        if identifier == "@project":
            self.canvas._project.name = self.project.name
            self._presentation_signature = self.presentation_signature()
            self._update_actions()
            return
        node = self.project.find(identifier)
        if node is None:
            return
        effective = next(
            (
                n
                for n in self.project.effective_root(self.active_window, self.active_state).walk()
                if n.id == identifier
            ),
            None,
        )
        shown = self.canvas._project.find(identifier)
        if effective is None or shown is None:
            return
        shown.properties = deepcopy(effective.properties)
        shown.geometry = dict(effective.geometry)
        self.canvas.refresh_native_preview()
        frame = self.canvas._frames.get(identifier)
        widget = (
            frame.layout().itemAt(0).widget()
            if frame and frame.layout() and frame.layout().count()
            else None
        )
        if widget and not node.can_have_children:
            if key == "text":
                widget.setPlainText(str(effective.properties.get("text", ""))) if hasattr(
                    widget, "setPlainText"
                ) else widget.setText(str(effective.properties.get("text", "")))
            elif key == "placeholder" and hasattr(widget, "setPlaceholderText"):
                widget.setPlaceholderText(str(effective.properties.get("placeholder", "")))
            elif key == "tooltip":
                widget.setToolTip(effective.properties.get("tooltip", ""))
            elif key == "icon" and hasattr(widget, "setIcon"):
                from PySide6.QtGui import QPixmap, QIcon

                image = QPixmap()
                if effective.properties.get("icon"):
                    image.loadFromData(self.assets.read(effective.properties["icon"]))
                widget.setIcon(QIcon(image))
            elif key == "checked" and hasattr(widget, "setChecked"):
                widget.setChecked(effective.properties["checked"])
            elif key == "value" and hasattr(widget, "setValue"):
                widget.setValue(effective.properties["value"])
            elif key in {"source", "alt_text", "image_name"} and hasattr(widget, "image"):
                from PySide6.QtGui import QPixmap

                image = QPixmap()
                if effective.properties.get("source"):
                    image.loadFromData(self.assets.read(effective.properties["source"]))
                widget.image = image
                widget.setAccessibleName(effective.properties.get("alt_text", tr("Image")))
                widget.update()
        if frame:
            if key == "visible":
                frame.setVisible(effective.properties.get("visible", True))
            if key == "enabled":
                target = frame if node.can_have_children else widget
                if target:
                    target.setEnabled(effective.properties.get("enabled", True))
            if key == "spacing" and frame.layout():
                frame.layout().setSpacing(effective.properties.get("spacing", 6))
            if key == "padding" and frame.layout():
                value = effective.properties.get("padding", 8)
                frame.layout().setContentsMargins(value, value, value, value)
            if key.startswith("geometry."):
                parent = self.project.parent_of(identifier)
                if parent and parent.layout == LayoutKind.FREE:
                    frame.setGeometry(
                        *(effective.geometry[k] for k in ("x", "y", "width", "height"))
                    )
                else:
                    axis = key.partition(".")[2]
                    if axis in {"width", "height"}:
                        getattr(frame, "setFixed" + axis.title())(effective.geometry[axis])
        if key == "title" and node.kind == ComponentKind.WINDOW:
            for label in self.canvas.findChildren(QLabel):
                if (
                    label.property("componentId") == identifier
                    and label.parentWidget().objectName() == "app_window_titlebar"
                ):
                    label.setText(str(effective.properties.get("title", tr("Interface"))))
        item = self._tree_items.get(identifier)
        if item:
            count = sum(
                f.get("event", {}).get("component") == identifier
                for f in self.project.editable_flows
            )
            item.setText(
                0,
                ("◌ " if not node.properties.get("visible", True) else "")
                + (node.properties.get("code_name") or node.display_name)
                + (
                    " · " + ntr("{count} event", "{count} events", count).format(count=count)
                    if count
                    else ""
                ),
            )
        if self.active_state != "@default":
            state = next(
                s for s in self.project.states[self.active_window] if s["id"] == self.active_state
            )
            self.inspector._overrides = state.get("overrides", {}).get(identifier, {})
        if identifier == self.selected_id:
            if key == "icon":
                self.inspector._binding_signature = None
                self._select(identifier)
            elif not key.startswith("geometry."):
                self.inspector.patch_value(key, effective.properties.get(key, ""))
        self._presentation_signature = self.presentation_signature()
        if not finish:
            return
        self.logic.sync()
        self._update_code()
        self._update_actions()
        if hasattr(self, "zoom_view"):
            self.zoom_view.update_bounds()

    def choose_component_icon(self, identifier):
        """Import a portable icon into the document, never linking external paths."""
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Button icon"), "", tr("Icons (*.png *.svg)")
        )
        if filename:
            try:
                self._change_property(identifier, "icon", self.assets.import_image(Path(filename)))
            except (OSError, ProjectError) as exc:
                self._show_error(exc, tr("Could not use this icon"))

    def reveal_navigation(self, edge):
        """The Designer's inspector opens the exact connection in the Map."""
        self.set_mode("map")
        line = next(
            (
                line
                for line in self.map_panel.edges
                if line.edge["flow"] == edge["flow"] and line.edge["block"] == edge["block"]
            ),
            None,
        )
        if line:
            self.map_panel.view.scene().clearSelection()
            line.setSelected(True)
            self.map_panel.view.ensureVisible(line)

    def _finish_field_edit(self) -> bool:
        """Commit text still being edited before saving or replacing the project."""
        # Also commits edits made through accessibility/tests without an active window.
        from PySide6.QtWidgets import QLineEdit

        for field in self.inspector.findChildren(QLineEdit):
            if field.isModified():
                field.setModified(False)
                field.editingFinished.emit()
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
        if not self.prepare_script_change():
            return False
        return self.logic.flush()

    def add_component(self) -> None:
        """Insert into the container or page that fits the current selection."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Add components in the Default state."), 6000)
            return
        kind = ComponentKind(self.palette.currentData())

        def insert():
            """Insert the chosen type into the destination resolved from the selection."""
            parent = self._insertion_parent(kind)
            self.selected_id = self.project.add(parent.id, kind).id

        self._edit(insert)

    def _insertion_parent(self, kind: ComponentKind) -> Component:
        """Resolve insertions from the button, including inside selected pages."""
        node = self.project.find(self.selected_id)
        if node.kind == ComponentKind.PAGES and kind != ComponentKind.PAGE:
            return self.canvas.visible_page(node)
        while node:
            if node.accepts(kind):
                return node
            node = self.project.parent_of(node.id)
        raise ProjectError(tr("Select a set of pages to add a page."))

    def _page_group(self, node: Component) -> Component | None:
        """Find the set of pages closest to the selection."""
        while node:
            if node.kind == ComponentKind.PAGES:
                return node
            node = self.project.parent_of(node.id)
        return None

    def _edit(self, change: Callable[[], None], refresh=True, label: str | None = None) -> None:
        """Group a command into one change and restore the document if it fails.

        `label` names the change for Undo/Redo; when omitted it comes from
        UNDO_LABELS, keyed by the name of the command that called this method.
        """
        if label is None:
            import sys

            label = undo_labels().get(sys._getframe(1).f_code.co_name, tr("Edit"))
        if not self._finish_field_edit():
            return
        before = self.project.to_dict()
        selection = self.selected_id
        try:
            change()
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project = Project.from_dict(before)
            self.selected_id = selection
            self._refresh()
            self._show_error(exc, tr("Could not apply the change"))
            return
        self.history.push(self.project, label)
        if refresh:
            self._refresh()
        else:
            self._update_actions()

    def change_application(self, key, value):
        """App metadata does not need to destroy the widgets of the interface being edited."""
        if self.project.application.get(key) == value or not self._finish_field_edit():
            return
        before = deepcopy(self.project.application)
        self.project.application[key] = value
        try:
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project.application = before
            self._show_error(exc, tr("Could not change the application settings"))
            return
        self.history.push(self.project, tr("Change application settings"))
        if key == "backend":
            self._refresh()
        else:
            self.canvas._project.application = deepcopy(self.project.application)
            self._update_actions()

    def _can_drop(self, payload: dict, parent_id: str) -> bool:
        """Validate a drag without changing the document while the mouse passes over."""
        if self.active_state != "@default":
            return False
        parent = self.project.find(parent_id)
        if parent is None:
            return False
        if payload.get("mode") == "new":
            try:
                return parent.accepts(ComponentKind(payload["kind"]))
            except (KeyError, ValueError):
                return False
        node = self.project.find(payload.get("id"))
        if payload.get("project") != self.project.id or node is None:
            return False
        previous = self.project.parent_of(node.id)
        return bool(
            previous
            and parent.accepts(node.kind)
            and parent.id not in {child.id for child in node.walk()}
            and not (
                previous is not parent
                and previous.kind == ComponentKind.PAGES
                and len(previous.children) == 1
            )
        )

    def _on_drop(self, payload: dict, parent_id: str, index: int, geometry: dict | None) -> None:
        """Turn a tree or screen drop into a model edit."""
        if not self._can_drop(payload, parent_id):
            return

        def apply():
            """Apply the creation/move and the drop geometry at once."""
            if payload["mode"] == "new":
                node = self.project.add(parent_id, ComponentKind(payload["kind"]))
            else:
                node = self.project.find(payload["id"])
            self.project.move(node.id, parent_id, index)
            parent = self.project.find(parent_id)
            if geometry and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
                snapped = {
                    key: max(0, min(20000, round(value / self.canvas.snap) * self.canvas.snap))
                    for key, value in geometry.items()
                }
                self.project.set_geometry(node.id, snapped)
            self.selected_id = node.id

        self._edit(apply)

    def _resize_window(self, width: int, height: int) -> None:
        """Store the size the window opens with, as one step in the history."""
        identifier = self.project.root.id
        self._edit(
            lambda: self.project.find(identifier).properties.update(width=width, height=height)
        )

    def _commit_geometry(self, node_id: str, geometry: dict) -> None:
        """Record a complete move/resize without fragmenting the history."""
        if self.active_state != "@default":
            self._refresh()
            return
        node = self.project.find(node_id)
        ids = getattr(self, "selected_ids", {node_id})
        if (
            len(ids) > 1
            and node_id in ids
            and geometry.get("width", node.geometry["width"]) == node.geometry["width"]
            and geometry.get("height", node.geometry["height"]) == node.geometry["height"]
        ):
            dx = geometry.get("x", node.geometry["x"]) - node.geometry["x"]
            dy = geometry.get("y", node.geometry["y"]) - node.geometry["y"]
            siblings = [
                self.project.find(identifier)
                for identifier in ids
                if self.project.parent_of(identifier) is self.project.parent_of(node_id)
            ]
            dx = max(
                -min(item.geometry["x"] for item in siblings),
                min(dx, 20000 - max(item.geometry["x"] for item in siblings)),
            )
            dy = max(
                -min(item.geometry["y"] for item in siblings),
                min(dy, 20000 - max(item.geometry["y"] for item in siblings)),
            )

            def move_group():
                """Move the group keeping relative positions and valid bounds."""
                for identifier in ids:
                    item = self.project.find(identifier)
                    if self.project.parent_of(identifier) is self.project.parent_of(node_id):
                        self.project.set_geometry(
                            identifier,
                            {
                                "x": max(0, min(20000, item.geometry["x"] + dx)),
                                "y": max(0, min(20000, item.geometry["y"] + dy)),
                            },
                        )

            self._edit(move_group, refresh=False)
            self.patch_geometries(ids)
        else:
            self._edit(lambda: self.project.set_geometry(node_id, geometry), refresh=False)
            self.patch_geometries([node_id])

    def duplicate_component(self) -> None:
        """Duplicate the selection with its own identifiers and keep the copy selected."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Edit the structure in the Default state."), 6000)
            return

        def duplicate():
            """Duplicate the selection's top nodes and keep the copied group selected."""
            identifiers = self.top_level_selection()
            copies = [self.project.duplicate(identifier).id for identifier in identifiers]
            self.selected_ids = set(copies)
            self.selected_id = copies[-1]

        self._edit(duplicate)

    def reorder_component(self, direction: int) -> None:
        """Offer keyboard reordering, with the same semantics as dragging."""

        def reorder():
            """Turn the command's direction into an insertion position."""
            node = self.project.find(self.selected_id)
            parent = self.project.parent_of(node.id)
            if parent:
                old_index = parent.children.index(node)
                self.project.move(node.id, parent.id, old_index + (2 if direction > 0 else -1))

        self._edit(reorder)

    def add_page(self) -> None:
        """Add a page to the selected set or an ancestor."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Edit the structure in the Default state."), 6000)
            return

        def add():
            """Insert a page into the selection's ancestor set."""
            group = self._page_group(self.project.find(self.selected_id))
            if group is not None:
                self.selected_id = self.project.add(group.id, ComponentKind.PAGE).id

        self._edit(add)

    def nudge_component(self, dx: int, dy: int) -> None:
        """Nudge a free component in fine steps without affecting other layouts."""
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(node.id)
        if parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
            self._commit_geometry(
                node.id,
                {
                    "x": max(0, min(20000, node.geometry["x"] + dx)),
                    "y": max(0, min(20000, node.geometry["y"] + dy)),
                },
            )

    def align_component(self, mode: str) -> None:
        """Align the selection to the visible bounds of its free container."""
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(node.id)
        if not parent or parent.layout != LayoutKind.FREE or parent.kind == ComponentKind.PAGES:
            return
        area = self.canvas._frames[parent.id].contentsRect()
        x, y = node.geometry["x"], node.geometry["y"]
        if mode in {"left", "center_x", "right"}:
            remaining = area.width() - node.geometry["width"]
            x = 8 if mode == "left" else remaining // 2 if mode == "center_x" else remaining - 8
        else:
            remaining = area.height() - node.geometry["height"]
            y = 8 if mode == "top" else remaining // 2 if mode == "center_y" else remaining - 8
        self._commit_geometry(node.id, {"x": max(0, min(20000, x)), "y": max(0, min(20000, y))})

    def choose_image(self, node_id: str) -> None:
        """Import an explicitly chosen image, copying it when saving."""
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Choose image"), "", tr("Images (*.png *.jpg *.jpeg *.webp)")
        )
        if not filename:
            return

        def choose():
            """Reserve the imported asset and update the visual reference."""
            source = self.assets.import_image(Path(filename))
            node = self.project.find(node_id)
            node.properties.update(source=source, image_name=Path(filename).name)

        self._edit(choose)

    def clear_image(self, node_id: str) -> None:
        """Remove the visual reference, keeping the asset available for undo."""

        def clear():
            """Clear the image without removing the asset from the session history."""
            node = self.project.find(node_id)
            node.properties.update(source="", image_name="")

        self._edit(clear)

    def remove_component(self) -> None:
        """Remove the selection, keeping the deletion available for undo."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Edit the structure in the Default state."), 6000)
            return
        if not self._finish_field_edit():
            return
        node = self.project.find(self.selected_id)
        if node and node.kind == ComponentKind.WINDOW:
            if len(self.project.roots) > 1:
                self.remove_window()
            return
        if len(getattr(self, "selected_ids", set())) > 1:

            def remove_group():
                """Group sibling/container removals into a single reversible change."""
                identifiers = self.top_level_selection()
                parent = self.project.parent_of(identifiers[0])
                for identifier in identifiers:
                    self.project.remove(identifier)
                self.selected_id = (
                    parent.id if parent and self.project.find(parent.id) else self.active_window
                )
                self.selected_ids = {self.selected_id}

            self._edit(remove_group)
            return
        try:
            self.selected_id = self.project.remove(self.selected_id)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not remove the component"))
            return
        self.history.push(self.project, tr("Remove component"))
        self._refresh()

    def undo(self) -> None:
        """Restore the previous document, including properties and node order."""
        if self.tabs.currentIndex() == 2 and (
            not hasattr(self, "code_files") or self.code_files.currentIndex() > 0
        ):
            self.active_code_editor().undo()
            return
        if not self._finish_field_edit():
            return
        self.project = self.history.undo()
        self._refresh()

    def redo(self) -> None:
        """Reapply a change that was undone."""
        if self.tabs.currentIndex() == 2 and (
            not hasattr(self, "code_files") or self.code_files.currentIndex() > 0
        ):
            self.active_code_editor().redo()
            return
        if not self._finish_field_edit():
            return
        self.project = self.history.redo()
        self._refresh()

    def new_project(self) -> None:
        """Create a document after resolving unsaved changes."""
        if not self._confirm_discard():
            return
        self._replace_project(Project.empty(), None)

    def open_project(self) -> None:
        """Open a validated document; failures never replace the current project."""
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.project_dialog_parent(),
            tr("Open Makebench project"),
            str(self.path.parent) if self.path else "",
            tr("Makebench projects (*.makebench.json *.zip);;JSON (*.json)"),
        )
        if not filename:
            return
        if filename.lower().endswith(".zip"):
            destination = QFileDialog.getExistingDirectory(
                self.project_dialog_parent(), tr("Extract into an empty folder"), ""
            )
            if not destination:
                return
            from makebench.core.bundle import read_bundle

            try:
                filename = str(read_bundle(filename, Path(destination)))
            except (ProjectError, OSError) as exc:
                self._show_error(exc, tr("Could not open the project"))
                return
        try:
            project = load_project(filename)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not open the project"))
            return
        try:
            self._replace_project(project, Path(filename))
        except (ProjectError, OSError) as exc:
            self._show_error(exc, tr("Could not open the project"))

    def _replace_project(self, project: Project, path: Path | None) -> None:
        """Swap the document and start an independent history."""
        path = path.resolve() if path else None
        source = SourceBuffer.load(path)
        if path and project.programming is None:
            from makebench.core.project import infer_programming

            choice = infer_programming(project, source.text)
            if choice:
                project.metadata["programming"] = choice
        self._trusted_session = False
        self._created_here = False
        self.project = project
        self.path = path
        self.source = source
        self.source_editor.blockSignals(True)
        self.source_editor.setPlainText(source.text)
        self.source_editor.blockSignals(False)
        self._script_target = None
        self._script_original = ""
        self.script_editor.clear()
        self.script_apply.setEnabled(False)
        self.logic.flow_id = None
        self.logic._target_component = None
        self.assets = AssetStore(path.parent if path else None)
        self.history = History(project)
        self._saved_document = project.to_dict() if path else None
        self.selected_id = project.root.id
        self._refresh()
        self.remember_project()
        self.pages.setCurrentWidget(self.editor_page)

    def save(self) -> bool:
        """Save the project or ask for a destination when it has no path yet."""
        if not self._finish_field_edit():
            return False
        if self.path is None:
            return self.save_as()
        return self.save_to(self.path)

    def save_as(self) -> bool:
        """Ask for a destination, keeping the current path on failure."""
        return self.save_as_dialog()

    def save_to(self, path: Path) -> bool:
        """Persist the document and mark it as saved only after success."""
        if not self._finish_field_edit():
            return False
        path = path.resolve()
        try:
            saved = self._saved_document if path == self.path else None
            self._saved_document, backup = save_workspace(
                self.project, self.source, self.assets, path, saved
            )
        except (ProjectError, OSError) as exc:
            self._show_error(exc, tr("Could not save the project"))
            return False
        self.path = path
        self.history.mark_saved()
        self._update_code()
        self._update_actions()
        self.remember_project()
        self.canvas.close_native_preview()
        self.clear_recovery()
        from .history_panel import record_version

        record_version(self)
        if backup:
            self.statusBar().showMessage(
                tr(
                    "Project upgraded to format {version}. The copy {backup} keeps the previous version; older editors cannot open the new features."
                ).format(version=self.project.to_dict()["format_version"], backup=backup.name),
                12000,
            )
        return True

    def _confirm_discard(self) -> bool:
        """Offer to save changes before closing, opening or creating a project."""
        if not self._finish_field_edit():
            choice = QMessageBox.warning(
                self,
                tr("Unconfirmed blocks"),
                tr(
                    "There are logic changes not confirmed yet. Discarding may lose blocks or the script being edited. Discard and continue?"
                ),
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Discard:
                self.clear_recovery()
                return True
            return False
        if not self.history.dirty and not self.source.dirty:
            return True
        choice = QMessageBox.warning(
            self,
            tr("Save changes?"),
            tr("The project has changes that have not been saved yet."),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        if choice == QMessageBox.StandardButton.Discard:
            self.clear_recovery()
            return True
        return False

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

    def edit_logic(self, component_id):
        """Create or open the flow of the event selected in the interface."""
        if not self._finish_field_edit():
            return
        try:
            states = [self.active_state] if self.project.states.get(self.active_window) else None
            existing = [
                f
                for f in self.project.workflows
                if f.get("event", {}).get("component") == component_id
            ]
            flow = next(
                (f for f in existing if self.active_state in f.get("states", [])), None
            ) or next((f for f in existing if not f.get("states")), None)
            python = self.project.programming == "python"
            if flow is None and python:
                before = self.source_editor.toPlainText()
                flow, after = create_python_event(self.project, component_id, before, states)
                if after != before:
                    stub = after[len(before.rstrip("\n")) :].strip("\n")
                    if before.strip():
                        self.source_editor.appendPlainText("\n\n" + stub)
                    else:
                        self.source_editor.setPlainText(stub + "\n")
            elif flow is None:
                flow = create_flow(self.project, component_id, states=states)
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

    def remove_flow(self, flow_id):
        """Remove only the logic binding; undo restores blocks and comments."""
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
        flow = next((f for f in self.project.workflows if f["id"] == data.get("flow")), None)
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

    def run_project(self):
        """Test an explicit snapshot; editing and opening still never run code."""
        if self.runtime_window is not None and not self.runtime_window.session.closed:
            if self.runtime_window.session.admin_active:
                self.statusBar().showMessage(
                    tr("Wait for the administrative task to finish before restarting."), 7000
                )
                return
            from .settings import preference

            if self.runtime_window.session.busy and preference("test/confirm_restart"):
                choice = QMessageBox.warning(
                    self,
                    tr("Restart test?"),
                    tr(
                        "A task is in progress. Restarting ends the test and the ordinary processes."
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    return
            if not self.runtime_window.stop():
                self.statusBar().showMessage(
                    tr("Wait for the administrative task to finish before restarting."), 7000
                )
                return
            self._restart_pending = True
            return
        if not self._finish_field_edit():
            return
        if not self.confirm_trust():
            return
        from makebench.runtime.window import RuntimeWindow

        if self.project.application.get("backend", "qt") == "gtk":
            from makebench.runtime.gtk_bridge import GtkRuntimeBridge as RuntimeWindow
        try:
            window = RuntimeWindow(
                self.project,
                self.source.text,
                self.assets.read,
                self.path.parent if self.path else None,
                self.source.path,
                self,
                supervision=False,
            )
        except (ProjectError, OSError) as exc:
            if self.project.application.get("backend", "qt") == "gtk":
                self._show_error(exc, tr("Could not start the test"))
            self.sync_problems()
            self.drawer.show()
            self.drawer.setCurrentIndex(1)
            self.statusBar().showMessage(tr("Test blocked: resolve the items in Problems."), 7000)
            return
        if self.runtime_window is not None:
            self.runtime_window.close()
        self.runtime_window = window
        window.locate_requested.connect(lambda error: self._locate_runtime_error(error, window))
        window.shutdown_finished.connect(self._runtime_stopped)
        window.destroyed.connect(lambda: self._runtime_destroyed(window))
        self._debug_active = getattr(self, "_next_debug", False)
        self._next_debug = False
        config = {"enabled": self._debug_active, "breakpoints": self.breakpoints()}
        if hasattr(window.session, "snapshot"):
            window.session.snapshot["debug"] = config
        else:
            window.debug_config = config
        self.monitor_runtime(window)
        window.show()
        window.start()

    def _runtime_destroyed(self, window):
        """Remove only the reference of the window that was actually destroyed."""
        if self.runtime_window is window:
            self.runtime_window = None

    def _runtime_stopped(self):
        """Resume closing after the supervisor finishes cleaning up the processes."""
        self._update_actions()
        if self._closing_after_runtime:
            QTimer.singleShot(0, self.close)
        elif getattr(self, "_restart_pending", False):
            self._restart_pending = False
            QTimer.singleShot(0, self.run_project)

    def _locate_runtime_error(self, error, window):
        """Find the current block; own lines only count if the text did not change."""
        if self.project.id != window.project.id:
            self.statusBar().showMessage(
                tr("The error belongs to another project open in the run."), 7000
            )
            return
        from makebench.core.source import source_signature

        if error.get("source_line") and source_signature(self.source.text) == source_signature(
            window.source
        ):
            self.open_code_file(error.get("source_file", "@actions"), error["source_line"])
        elif error.get("block"):
            flow = next((f for f in self.project.workflows if f["id"] == error.get("flow")), None)
            if flow:
                self.logic.sync(flow["id"])
                self.tabs.setCurrentIndex(1)
                self.logic.focus_block(flow["id"], error["block"])
        self.raise_()
        self.activateWindow()

    def _show_error(self, error, action: str | None = None) -> None:
        """Show recoverable failures without closing the editor.

        `error` is a message or an exception; `action` names what failed and becomes
        the title, while technical details stay collapsed.
        """
        from .errors import show_error

        show_error(self.project_dialog_parent(), error, action)

    def show_about(self) -> None:
        """Show the version and what this release does."""
        QMessageBox.about(
            self,
            tr("About Makebench"),
            "<h2>Makebench</h2><p>"
            + tr("Linux applications, built by you.")
            + "</p>"
            + "<p>"
            + tr("Version {version}").format(version=__version__)
            + "</p>"
            + "<p>"
            + tr(
                "Design Qt or GTK4 interfaces, connect blocks or nodes, write your own Python and export as Python source, DEB, RPM, AppImage or Flatpak."
            )
            + "</p>"
            + "<p>"
            + tr(
                "Free software: editor under the GNU GPL 3 or later, runtime under the MIT license."
            )
            + "</p>",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Protect unsaved changes when the window closes."""
        window = self.runtime_window
        if window is not None and window.session.admin_active:
            window.show()
            window.raise_()
            self.statusBar().showMessage(
                tr("Wait for the administrative task to finish before closing the editor."), 7000
            )
            event.ignore()
            return
        if (
            not self._closing_after_runtime
            and not getattr(self, "_closing_after_build", False)
            and not getattr(self, "_closing_after_preview", False)
            and not self._confirm_discard()
        ):
            event.ignore()
            return
        if window is not None and not window.session.closed:
            if not window.stop():
                self.statusBar().showMessage(
                    tr("Wait for the administrative task to finish before closing."), 7000
                )
                event.ignore()
                return
            self._closing_after_runtime = True
            self.setEnabled(False)
            window.close_pending = True
            event.ignore()
            return
        if (
            hasattr(self, "publish_panel")
            and self.publish_panel.job
            and self.publish_panel.job.isRunning()
        ):
            self._closing_after_build = True
            self.publish_panel.cancel_build()
            self.statusBar().showMessage(tr("Cancelling build before closing…"), 5000)
            QTimer.singleShot(100, self.close)
            event.ignore()
            return
        canvas_ready = self.canvas.close_native_preview()
        thumbnails_ready = (
            self.map_panel.previews.shutdown() if hasattr(self, "map_panel") else True
        )
        if not canvas_ready or not thumbnails_ready:
            self._closing_after_preview = True
            self.setEnabled(False)
            self.statusBar().showMessage(tr("Closing previews…"), 3000)
            QTimer.singleShot(100, self.close)
            event.ignore()
            return
        if hasattr(self, "terminal_panel"):
            self.terminal_panel.surface.stop_terminal()
        self.clear_recovery()
        event.accept()
