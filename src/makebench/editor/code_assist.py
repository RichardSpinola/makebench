# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit suggestions and static navigation in your own Python editors."""

import re
from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFrame, QInputDialog, QListWidget, QListWidgetItem
from makebench.core.source import ENTRY_FILE, source_files
from makebench.i18n import tr

from . import jedi_assist


class CodeAssist(QObject):
    """Adapt the project index to the editor with no evaluation and no language server."""

    def __init__(self, window, editor, filename):
        """Install local controls, keeping generated code and scripts out of the suggestions."""
        super().__init__(editor)
        self.window = window
        self.editor = editor
        self.filename = filename
        self.popup = QListWidget(editor.viewport())
        self.popup.setAccessibleName(tr("Code suggestions"))
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setFrameShape(QFrame.Shape.Box)
        self.popup.hide()
        self.popup.itemClicked.connect(lambda item: self.accept(item.text()))
        self.prefix = ""
        editor.installEventFilter(self)
        editor.setToolTip(
            tr(
                "Ctrl+Space: suggestions · Ctrl+Shift+Space: parameters · F12: definition · F2: rename"
            )
        )
        editor.cursorPositionChanged.connect(self.parameters)

    def before(self):
        """Convert Qt's UTF-16 position to Python text without splitting Unicode characters."""
        cursor = self.editor.textCursor()
        cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText().replace("\u2029", "\n")

    def _position(self):
        """Mirror the project's files for Jedi and return (source, path, line, column)."""
        window = self.window
        if not hasattr(window, "jedi_workspace"):
            window.jedi_workspace = jedi_assist.Workspace()
        texts = source_files(window.source.text)
        source = self.editor.toPlainText()
        texts[self.filename] = source
        window.jedi_workspace.sync(ENTRY_FILE, texts)
        cursor = self.editor.textCursor()
        text = cursor.block().text()
        units = cursor.positionInBlock()
        column = len(text.encode("utf-16-le")[: units * 2].decode("utf-16-le"))
        path = window.jedi_workspace.path_of(self.filename, ENTRY_FILE)
        return source, path, cursor.blockNumber() + 1, column

    def _jedi_items(self):
        """Suggestions from Jedi with the matching snippets, as {label: text to insert}."""
        if not jedi_assist.available():
            return {}
        source, path, line, column = self._position()
        found = jedi_assist.completions(source, self.window.jedi_workspace.root, path, line, column)
        items = {f"{item.name} · {item.detail}": item.name for item in found}
        for name, text in jedi_assist.snippets(
            self.prefix.split(".")[-1],
            getattr(self.window, "plugin_manager", None) and self.window.plugin_manager.snippets(),
        ).items():
            items[f"{name} · " + tr("snippet")] = text
        return items

    def complete(self):
        """Open suggestions with Ctrl+Space, including components in ctx calls."""
        self.window.refresh_code_index()
        before = self.before()
        match = re.search(r"[\w.]+$", before)
        self.prefix = match.group() if match else ""
        component = re.search(
            r"ctx\.(?:read|set_text|set_enabled|set_value|set_options|show_page|terminal_start|terminal_send|terminal_stop)\(\s*(['\"])([^'\"]*)$",
            before,
        )
        self.inserts = {}
        if component:
            self.prefix = component.group(2)
            for node in self.window.project.walk():
                label = node.properties.get("code_name") or node.display_name
                if node.id.startswith(self.prefix) or label.casefold().startswith(
                    self.prefix.casefold()
                ):
                    self.inserts[node.id + " · " + label] = node.id
            items = list(self.inserts)
        else:
            full_prefix = self.prefix
            self.prefix = full_prefix.split(".")[-1]
            self.inserts = self._jedi_items()
            if not self.inserts:
                self.prefix = full_prefix
            items = list(self.inserts) or [
                name for name, _ in self.window.code_index.complete(self.filename, self.prefix)
            ]
        self.popup.clear()
        for text in items:
            item = QListWidgetItem(text)
            target = self.window.code_index.resolve(self.filename, text)
            if target:
                item.setToolTip(target.signature + "\n" + target.description)
            self.popup.addItem(item)
        if items:
            self.popup.setCurrentRow(0)
            rect = self.editor.cursorRect()
            viewport = self.editor.viewport()
            width = min(460, max(120, viewport.width() - 12))
            height = min(
                self.popup.sizeHintForRow(0) * min(8, len(items)) + 6,
                max(32, viewport.height() - 12),
            )
            x = max(0, min(rect.left(), viewport.width() - width))
            y = rect.bottom() + 4
            if y + height > viewport.height():
                y = max(0, rect.top() - height - 4)
            self.popup.setGeometry(x, y, width, height)
            self.popup.show()
            self.popup.raise_()
        else:
            self.popup.hide()
            self.window.statusBar().showMessage(tr("No static suggestion in this context."), 3000)

    def accept(self, text):
        """Confirm a suggestion without opening another native window or losing focus."""
        self.insert(text)
        self.popup.hide()
        self.editor.setFocus()

    def insert(self, text):
        """Replace only the prefix, as a single reversible edit."""
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        for _ in range(len(self.prefix.encode("utf-16-le")) // 2):
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(getattr(self, "inserts", {}).get(text, text))
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def definition(self):
        """F12 opens a known local definition, without running its module."""
        self.window.refresh_code_index()
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        before = self.before()
        match = re.search(r"[\w.]+$", before)
        token = match.group() if match else cursor.selectedText()
        # Include the rest of the word if the cursor is in the middle of it.
        line = self.editor.textCursor().block().text()
        position = self.editor.textCursor().positionInBlock()
        suffix = re.match(r"\w*", line.encode("utf-16-le")[position * 2 :].decode("utf-16-le"))
        if suffix and token and not token.endswith(suffix.group()):
            token += suffix.group()
        target = self.window.code_index.resolve(self.filename, token)
        if target and target.file:
            self.window.open_code_file(target.file, target.line, target.column)
        elif self._jedi_definition():
            return
        else:
            self.window.statusBar().showMessage(tr("Local definition not found."), 3000)

    def _jedi_definition(self):
        """F12 through Jedi, for names the built-in index does not know."""
        if not jedi_assist.available():
            return False
        source, path, line, column = self._position()
        workspace = self.window.jedi_workspace
        found = jedi_assist.definition(source, workspace.root, path, line, column)
        name = workspace.name_of(found.path) if found else None
        if name is None:
            return False
        self.window.open_code_file(name, found.line + 1, found.column + 1)
        return True

    def rename(self):
        """F2: rename the symbol under the caret inside this file."""
        if not jedi_assist.available():
            return
        source, path, line, column = self._position()
        new_name, ok = QInputDialog.getText(self.editor, tr("Rename symbol"), tr("New name"))
        if not ok or not new_name.strip():
            return
        result = jedi_assist.rename(
            source, self.window.jedi_workspace.root, path, line, column, new_name.strip()
        )
        if result is None or result == source:
            self.window.statusBar().showMessage(tr("This symbol cannot be renamed."), 3000)
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(result)
        cursor.endEditBlock()

    def parameters(self):
        """Show the contextual signature discreetly in the Code area's footer."""
        if not self.editor.hasFocus():
            return
        signature = self.window.code_index.call_signature(self.filename, self.before())
        if not signature and jedi_assist.available():
            source, path, line, column = self._position()
            signature = jedi_assist.signature(
                source, self.window.jedi_workspace.root, path, line, column
            )
        self.window.code_signature.setText(signature)
        self.window.code_signature.setToolTip(signature)

    def eventFilter(self, watched, event):
        """Drive the editor's child list, with no native grabs that cause flicker on Wayland."""
        controls = (
            bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if event.type() in {QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride}
            else False
        )
        assisted = event.type() in {QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride} and (
            event.key() in {Qt.Key.Key_F12, Qt.Key.Key_F2}
            or controls
            and event.key() == Qt.Key.Key_Space
        )
        if assisted:
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            if event.key() == Qt.Key.Key_F12:
                self.definition()
            elif event.key() == Qt.Key.Key_F2:
                self.rename()
            elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.parameters()
            else:
                self.complete()
            return True
        if self.popup.isVisible() and event.type() == QEvent.Type.KeyPress:
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab}:
                item = self.popup.currentItem()
                if item:
                    self.accept(item.text())
                return True
            if event.key() in {Qt.Key.Key_Up, Qt.Key.Key_Down}:
                step = -1 if event.key() == Qt.Key.Key_Up else 1
                self.popup.setCurrentRow((self.popup.currentRow() + step) % self.popup.count())
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.popup.hide()
                return True
            if event.key() not in {Qt.Key.Key_Control, Qt.Key.Key_Shift}:
                self.popup.hide()
        if event.type() in {QEvent.Type.FocusOut, QEvent.Type.Resize}:
            self.popup.hide()
        return super().eventFilter(watched, event)
