# SPDX-License-Identifier: GPL-3.0-or-later
"""Your own Python files: editing, static index and integration with the document."""

import hashlib
import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QSizePolicy,
)
from makebench.core.code_index import CodeIndex
from makebench.core.source import ENTRY_FILE, SourceBuffer, source_signature
from makebench.core.project import ProjectError
from .code import CodeEditor
from .code_assist import CodeAssist
from .code_reference import CodeReference
from .theme import icon
from makebench.i18n import tr


class CodeWorkspaceMixin:
    """Keep per-file buffers and reuse the older main-source APIs."""

    def install_code_workspace(self):
        """Add the file tree and assistance to the existing Code area."""
        self.code_index = CodeIndex()
        self.module_editors = {}
        self._workspace_buffer = None
        pane = self.function_outline.parentWidget()
        layout = pane.layout()
        self.code_tree = QTreeWidget()
        self.code_tree.setHeaderHidden(True)
        self.code_tree.setAccessibleName(tr("Project Python files"))
        self.code_tree.itemActivated.connect(self.code_tree_open)
        self.code_tree.itemClicked.connect(self.code_tree_open)
        controls = QWidget()
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("Modules")), 1)
        for symbol, label, callback in [
            ("add", tr("New module"), self.new_module_dialog),
            ("edit", tr("Rename module"), self.rename_module_dialog),
            ("remove", tr("Delete module"), self.delete_module_dialog),
        ]:
            button = QToolButton()
            button.setIcon(icon(symbol))
            button.setAccessibleName(label)
            button.setToolTip(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.insertWidget(0, controls)
        layout.insertWidget(1, self.code_tree, 1)
        self.code_events = QListWidget()
        self.code_events.setAccessibleName(tr("Events"))
        self.code_events.itemActivated.connect(self.code_event_open)
        self.code_events.itemClicked.connect(self.code_event_open)
        layout.insertWidget(0, QLabel(tr("Events")))
        layout.insertWidget(1, self.code_events, 1)
        self.code_splitter.insertWidget(0, pane)
        self.code_reference = CodeReference()
        self.code_reference.insert_requested.connect(self.insert_code_reference)
        self.code_reference.example_requested.connect(self.insert_code_example)
        self.code_splitter.addWidget(self.code_reference)
        self.code_splitter.setSizes([260, 900, 240])
        self.code_signature = QLabel()
        self.code_signature.setAccessibleName(tr("Call signature"))
        self.code_signature.setTextFormat(Qt.TextFormat.PlainText)
        self.code_signature.setMinimumWidth(0)
        self.code_signature.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.tabs.widget(2).layout().addWidget(self.code_signature)
        self._entry_assist = CodeAssist(self, self.source_editor, ENTRY_FILE)
        self.code_index_timer = QTimer(self)
        self.code_index_timer.setSingleShot(True)
        self.code_index_timer.setInterval(400)
        self.code_index_timer.timeout.connect(self.refresh_code_index)
        self.source_editor.textChanged.connect(self.code_index_timer.start)
        self.code_files.currentChanged.connect(self.code_file_changed)
        self.sync_code_workspace()

    def sync_code_workspace(self):
        """Reconcile only added/removed files, without re-creating active editors."""
        if not hasattr(self, "code_tree"):
            return
        self.project.python_files = sorted(self.source.modules)
        if self._workspace_buffer is not self.source:
            for editor in self.module_editors.values():
                self.code_files.removeTab(self.code_files.indexOf(editor))
                editor.deleteLater()
            self.module_editors = {}
            self._workspace_buffer = self.source
        for name in list(self.module_editors):
            if (
                name not in self.source.modules
                or getattr(self.module_editors[name], "_source_buffer", None)
                is not self.source.modules[name]
            ):
                editor = self.module_editors.pop(name)
                self.code_files.removeTab(self.code_files.indexOf(editor))
                editor.deleteLater()
        for name, buffer in self.source.modules.items():
            if name in self.module_editors:
                continue
            editor = CodeEditor(parent=self.code_files)
            editor.setPlainText(buffer.text)
            editor.setAccessibleName(tr("Code {name}").format(name=name))
            editor.breakpoints_enabled = True
            editor._assist = CodeAssist(self, editor, name)
            editor._source_buffer = buffer
            self.module_editors[name] = editor
            self.code_files.addTab(editor, Path(name).name)
            editor.textChanged.connect(
                lambda name=name, editor=editor: self.module_changed(name, editor)
            )
            editor.cursorPositionChanged.connect(self.update_code_position)
            editor.breakpoint_requested.connect(
                lambda line, name=name: self.toggle_source_breakpoint(line, name)
            )
            editor.undoAvailable.connect(lambda _: self._update_actions())
            editor.redoAvailable.connect(lambda _: self._update_actions())
            editor.setFont(self.source_editor.font())
            editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 4)
            editor.setLineWrapMode(self.source_editor.lineWrapMode())
        signature = (id(self.source), self.source.path, tuple(sorted(self.source.modules)))
        if signature != getattr(self, "_code_tree_signature", None):
            self._code_tree_signature = signature
            self.code_tree.clear()
            folders = {}
            for label, key in [
                ("generated.py · " + tr("read-only"), "@generated"),
                (self.source.path.name if self.source.path else "project.actions.py", ENTRY_FILE),
                *[(name, name) for name in sorted(self.source.modules)],
            ]:
                parent = None
                if key in self.source.modules:
                    path = Path(key)
                    for depth in range(1, len(path.parts)):
                        folder = "/".join(path.parts[:depth])
                        if folder not in folders:
                            item = QTreeWidgetItem([path.parts[depth - 1]])
                            item.setData(0, Qt.ItemDataRole.UserRole, "@folder:" + folder)
                            (parent.addChild if parent else self.code_tree.addTopLevelItem)(item)
                            folders[folder] = item
                            item.setExpanded(True)
                        parent = folders[folder]
                    label = path.name
                item = QTreeWidgetItem([label])
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                item.setToolTip(0, key)
                (parent.addChild if parent else self.code_tree.addTopLevelItem)(item)
        for name, editor in self.module_editors.items():
            self.code_files.setTabText(
                self.code_files.indexOf(editor),
                Path(name).name + (" •" if self.source.modules[name].dirty else ""),
            )
        self.sync_code_events()
        self.sync_code_tree_selection()
        self.watch_source()
        self.refresh_code_index()

    def sync_code_events(self):
        """List Python events as 'name → function()'; selecting one opens the function."""
        from makebench.core.logic import is_python_event

        flows = [f for f in self.project.editable_flows if is_python_event(f)]
        signature = tuple((f["id"], f["name"], f["function"]) for f in flows)
        if signature == getattr(self, "_code_events_signature", None):
            return
        self._code_events_signature = signature
        self.code_events.clear()
        for flow in flows:
            item = QListWidgetItem(f"{flow['name']} → {flow['function']}()")
            item.setData(Qt.ItemDataRole.UserRole, flow["id"])
            self.code_events.addItem(item)

    def code_event_open(self, item):
        """Open the function bound to the selected event."""
        self.open_event_function(item.data(Qt.ItemDataRole.UserRole))

    def open_event_function(self, flow_id):
        """Show an event's function in the actions file, at its definition when it exists."""
        import ast

        flow = next((f for f in self.project.editable_flows if f["id"] == flow_id), None)
        if flow is None:
            return
        line = 1
        try:
            tree = ast.parse(self.source_editor.toPlainText())
        except (SyntaxError, ValueError):
            tree = None
        for node in getattr(tree, "body", []):
            if isinstance(node, ast.FunctionDef) and node.name == flow["function"]:
                line = node.lineno
        self.open_code_file(ENTRY_FILE, line)

    def current_code_file(self):
        """Identify the active file, keeping the indexes of the two legacy tabs."""
        widget = self.code_files.currentWidget()
        return next(
            (name for name, editor in self.module_editors.items() if editor is widget),
            "@generated" if self.code_files.currentIndex() == 0 else ENTRY_FILE,
        )

    def insert_code_reference(self, text):
        """Insert an item of "What can I use" at the cursor of the file being edited."""
        editor = self.active_code_editor()
        if editor.isReadOnly():
            return
        editor.insertPlainText(text)
        editor.setFocus()

    def tidy_code_files(self):
        """Clean up every editable Python file before saving, when Preferences ask for it."""
        from makebench.core.python_check import tidy
        from .settings import preference

        if not preference("editor/format_on_save"):
            return
        for editor in [self.source_editor, *self.module_editors.values()]:
            text = editor.toPlainText()
            clean = tidy(text)
            if clean != text:
                editor.replace_all_text(clean)

    def insert_code_example(self, code):
        """Insert a task recipe at the cursor of the file being edited."""
        editor = self.active_code_editor()
        if editor.isReadOnly():
            return
        editor.insert_example(code)
        editor.setFocus()

    def active_code_editor(self):
        """Return the active editor for position, outline and undo/redo."""
        if not hasattr(self, "code_files"):
            return self.source_editor
        if self.code_files.currentIndex() == 0:
            return self.generated_editor
        return self.module_editors.get(self.current_code_file(), self.source_editor)

    def open_code_file(self, name, line=1, column=1):
        """Open a document file and bring its location into view."""
        if name not in {ENTRY_FILE, "@generated", *self.source.modules}:
            return
        self.set_mode("code")
        if name in self.source.modules:
            self.sync_code_workspace()
            editor = self.module_editors[name]
            self.code_files.setCurrentWidget(editor)
        else:
            self.code_files.setCurrentIndex(0 if name == "@generated" else 1)
            editor = self.active_code_editor()
        editor.show_line(line)
        editor.setFocus()
        if column > 1:
            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Right, cursor.MoveMode.MoveAnchor, column - 1)
            editor.setTextCursor(cursor)

    def code_tree_open(self, item, *_):
        """Selecting a file is navigation; it does not change the project."""
        self.open_code_file(item.data(0, Qt.ItemDataRole.UserRole))

    def code_file_changed(self, *_):
        """Update outline and position, keeping text and history per file."""
        if not hasattr(self, "code_tree"):
            return
        self.sync_code_tree_selection()
        self._outline_signature = None
        self.sync_outline()
        self.update_code_position()
        self._update_actions()

    def sync_code_tree_selection(self):
        """Mark the active file without moving the scroll or triggering recursive navigation."""
        key = self.current_code_file()
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(self.code_tree)
        blocked = self.code_tree.blockSignals(True)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                self.code_tree.setCurrentItem(item)
                break
            iterator += 1
        self.code_tree.blockSignals(blocked)

    def module_changed(self, name, editor):
        """Commit text to the buffer and defer analysis so the UI is not walked on every key."""
        if name not in self.source.modules:
            return
        self.source.modules[name].text = editor.toPlainText()
        self.code_index_timer.start()
        self.source_timer.start()
        self.setWindowModified(True)
        self.code_files.setTabText(self.code_files.indexOf(editor), Path(name).name + " •")

    def refresh_code_index(self):
        """Rebuild the index only when content changes; errors never clear the last AST."""
        if not hasattr(self, "code_index"):
            return
        signature = (
            source_signature(self.source.text),
            tuple((n.id, n.display_name) for n in self.project.walk()),
        )
        if signature == getattr(self, "_code_index_signature", None):
            return
        self._code_index_signature = signature
        self.code_index.update(self.source.text, self.project.walk())
        self.code_reference.sync(self.project)
        for name, editor in [(ENTRY_FILE, self.source_editor), *self.module_editors.items()]:
            editor.mark_diagnostics([e for e in self.code_index.errors if e["file"] == name])

    def update_module_manifest(self):
        """Declare only the document's real files; older formats do not change on open."""
        self.project.python_files = sorted(self.source.modules)
        self.sync_code_workspace()
        self._update_code()
        self._update_actions()

    def add_code_module(self, name, text=""):
        """API shared by the dialog and tests; creation stays editable before saving."""
        self.source.add_module(name, text)
        self.update_module_manifest()
        self.open_code_file(name)

    def new_module_dialog(self):
        """Create a validated name inside the reserved package, without touching the disk."""
        name, ok = QInputDialog.getText(
            self, tr("New module"), tr("File inside makebench_user"), text="helpers.py"
        )
        if ok:
            try:
                self.add_code_module(
                    name if name.startswith("makebench_user/") else "makebench_user/" + name
                )
            except ProjectError as exc:
                self._show_error(exc, tr("Could not create the module"))

    def rename_module_dialog(self):
        """Keep texts; old imports are diagnosed, never implicitly rewritten."""
        old = self.current_code_file()
        if old not in self.source.modules:
            return
        name, ok = QInputDialog.getText(
            self, tr("Rename module"), tr("New path (imports are not rewritten)"), text=old
        )
        if ok and name != old:
            try:
                self.source.rename_module(old, name)
                for point in self.breakpoints():
                    if point.get("file") == "source" and point.get("path") == old:
                        point["path"] = name
                self.update_module_manifest()
                self.open_code_file(name)
            except ProjectError as exc:
                self._show_error(exc, tr("Could not rename the module"))

    def delete_module_dialog(self):
        """Ask for concrete confirmation and keep the deletion pending until saved."""
        name = self.current_code_file()
        if name not in self.source.modules:
            return
        changed = (
            " " + tr("This file has unsaved changes.") if self.source.modules[name].dirty else ""
        )
        if (
            QMessageBox.question(
                self,
                tr("Delete module?"),
                tr("{name} will be removed when the project is saved.").format(name=name) + changed,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.source.remove_module(name)
            self.update_module_manifest()
        except ProjectError as exc:
            self._show_error(exc, tr("Could not delete the module"))

    def fingerprint(self):
        """Trust includes the modules that will actually run."""
        return hashlib.sha256(
            (
                json.dumps(self.project.to_dict(), sort_keys=True)
                + repr(source_signature(self.source.text))
            ).encode()
        ).hexdigest()

    def watch_source(self):
        """Watch every own file, without loading them automatically."""
        if not hasattr(self, "source_watcher"):
            return
        old = self.source_watcher.files()
        paths = [
            str(b.path)
            for b in [self.source, *self.source.modules.values()]
            if b.path and b.path.exists()
        ]
        if set(old) == set(paths):
            return
        if old:
            self.source_watcher.removePaths(old)
        if paths:
            self.source_watcher.addPaths(paths)

    def source_changed_externally(self, path):
        """Flag a conflict in the affected file; the buffers stay preserved."""
        for buffer in [self.source, *self.source.modules.values()]:
            if buffer.path and str(buffer.path) == path:
                try:
                    changed = (
                        buffer.path.is_symlink()
                        or (buffer.path.read_bytes() if buffer.path.exists() else None)
                        != buffer.original
                    )
                except OSError:
                    changed = True
                if changed:
                    self.external_change_row.show()
                    self.statusBar().showMessage(
                        tr("Python changed outside Makebench: {path}").format(path=path), 15000
                    )
        self.watch_source()

    def reload_source(self):
        """An explicit reload keeps error notices and updates the module tabs."""
        if (
            self.source.dirty
            and QMessageBox.question(
                self,
                tr("Reload Python files?"),
                tr("Discard unsaved Python edits and reread the project files?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        super().reload_source()
        self.sync_code_workspace()

    def keep_source(self):
        """Accept overwriting only by explicit action, for all current buffers."""
        try:
            from makebench.core.source import _read, module_path

            for name, buffer in [(ENTRY_FILE, self.source), *self.source.modules.items()]:
                if buffer.path:
                    if name != ENTRY_FILE:
                        module_path(buffer.path.parents[len(Path(name).parts) - 1], name)
                    buffer.original = _read(buffer.path)
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not keep your version"))
            return
        self.external_change_row.hide()
        self.watch_source()
        self.refresh_trust_banner()
