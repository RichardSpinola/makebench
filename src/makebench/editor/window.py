# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: visual interface, blocks and Python functions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QMainWindow,
    QFileDialog,  # noqa: F401  (tests patch it through this module)
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

from makebench.core.logic import (
    editable,
)
from makebench.core.source import ENTRY_FILE, SourceBuffer
from makebench.editor.code import CodeEditor
from makebench.editor.logic import LogicPanel
from makebench.core.history import History
from makebench.core.project import (
    Component,
    ComponentKind,
    LayoutKind,
    Project,
)
from makebench.editor.assets import AssetStore
from makebench.editor.canvas import PreviewCanvas
from makebench.editor.drag import ComponentPalette, ComponentTree
from makebench.editor.inspector import Inspector
from makebench import __version__


from .design_edit import DesignEditMixin, undo_labels  # noqa: F401  (kept importable here)
from .logic_edit import LogicEditMixin
from .project_files import ProjectFilesMixin
from .running import RunMixin
from .studio import StudioMixin
from makebench.i18n import ntr, tr


def application_icon():
    """The Makebench application icon, or None when the file is missing."""
    path = Path(__file__).with_name("makebench.svg")
    return QIcon(str(path)) if path.is_file() else None


class MainWindow(
    DesignEditMixin, ProjectFilesMixin, LogicEditMixin, RunMixin, StudioMixin, QMainWindow
):
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
        self.logic.function_edit_requested.connect(self.save_block_function)
        self.logic.module_requested.connect(self.move_to_module)
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
