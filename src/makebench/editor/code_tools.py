# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight editing tools: literal replacement and delimiters, with no execution."""

import io
import tokenize
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import QInputDialog, QTextEdit
from makebench.i18n import ntr, tr


class CodeTools:
    """Local document operations, with text history and derived highlighting."""

    def open_replace(self):
        """Open replacement only in the editable file, keeping the current selection."""
        if self.isReadOnly():
            return
        self.replace_row.show()
        self.open_find()

    def replace_one(self):
        """Replace one literal occurrence; the replacement text is never interpreted."""
        if self.isReadOnly() or not self.find_text.text():
            return
        cursor = self.textCursor()
        if cursor.selectedText().casefold() != self.find_text.text().casefold():
            self.find_next()
            cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_text.text())
            self.setTextCursor(cursor)
            self.find_next()

    def replace_all(self):
        """Confirm every occurrence in a single undo step, with no loop over new text."""
        text = self.find_text.text()
        if self.isReadOnly() or not text:
            return
        matches = []
        position = 0
        while True:
            found = self.document().find(text, position)
            if found.isNull():
                break
            matches.append((found.selectionStart(), found.selectionEnd()))
            position = found.selectionEnd()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for start, end in reversed(matches):
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(self.replace_text.text())
        cursor.endEditBlock()
        self.find_status.setText(
            ntr("{count} replacement", "{count} replacements", len(matches)).format(
                count=len(matches)
            )
        )

    def go_to_line(self):
        """Find a valid line without changing the document."""
        line, ok = QInputDialog.getInt(
            self,
            tr("Go to line"),
            tr("Line"),
            self.textCursor().blockNumber() + 1,
            1,
            self.blockCount(),
        )
        if ok:
            self.show_line(line)
            self.setFocus()

    def delimiters(self):
        """Tokenize Python to skip delimiters in strings/comments, including Unicode."""
        text = self.toPlainText()
        if getattr(self, "_bracket_text", None) == text:
            return self._brackets
        self._bracket_text = text
        self._brackets = {}
        if len(text) > 300000:
            return self._brackets
        lines = text.splitlines(keepends=True)
        offsets = []
        offset = 0
        for line in lines:
            offsets.append(offset)
            offset += len(line.encode("utf-16-le")) // 2
        stack = []
        closing = {")": "(", "]": "[", "}": "{"}
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type != tokenize.OP or token.string not in "()[]{}":
                    continue
                row, column = token.start
                position = offsets[row - 1] + len(lines[row - 1][:column].encode("utf-16-le")) // 2
                if token.string in "([{":
                    stack.append((token.string, position))
                elif stack and stack[-1][0] == closing[token.string]:
                    _, start = stack.pop()
                    self._brackets[start] = position
                    self._brackets[position] = start
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        return self._brackets

    def highlight_cursor(self):
        """Combine line, diagnostic and delimiter-pair highlights without clearing the others."""
        if not hasattr(self, "_error_selections"):
            return
        selections = list(self._error_selections)
        cursor = self.textCursor()
        current = QTextEdit.ExtraSelection()
        current.cursor = QTextCursor(cursor)
        current.cursor.clearSelection()
        current.format.setBackground(self.palette().alternateBase())
        current.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selections.append(current)
        pairs = (
            {} if getattr(self.highlighter, "language", "python") == "plain" else self.delimiters()
        )
        position = cursor.position()
        position = position if position in pairs else position - 1
        if position in pairs:
            for index in (position, pairs[position]):
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(self.document())
                selection.cursor.setPosition(index)
                selection.cursor.movePosition(
                    QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor
                )
                selection.format.setBackground(self.palette().highlight())
                selection.format.setForeground(self.palette().highlightedText())
                selections.append(selection)
        self.setExtraSelections(selections)

    def contextMenuEvent(self, event):
        """Generated code offers explicit navigation to its source block."""
        menu = self.createStandardContextMenu()
        if self.isReadOnly() and getattr(self, "origin_enabled", True):
            menu.addSeparator()
            menu.addAction(
                tr("Go to source block · F4"),
                lambda: self.origin_requested.emit(self.textCursor().blockNumber() + 1),
            )
        elif not self.isReadOnly():
            menu.addSeparator()
            menu.addAction(tr("Replace… · Ctrl+H"), self.open_replace)
            self.add_examples_menu(menu)
        menu.addAction(tr("Go to line… · Ctrl+G"), self.go_to_line)
        menu.exec(event.globalPos())

    def add_examples_menu(self, menu):
        """An "Insert example" submenu whose recipes go in at the cursor."""
        from .code_examples import examples

        examples_menu = menu.addMenu(tr("Insert example"))
        for title, code in examples():
            examples_menu.addAction(title, lambda code=code: self.insert_example(code))
        return examples_menu

    def replace_all_text(self, text):
        """Replace the whole text as one undo step, keeping the cursor's line and column."""
        cursor = self.textCursor()
        line, column = cursor.blockNumber(), cursor.positionInBlock()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        block = self.document().findBlockByNumber(min(line, self.document().blockCount() - 1))
        cursor.setPosition(block.position() + min(column, block.length() - 1))
        self.setTextCursor(cursor)

    def insert_example(self, code):
        """Insert a recipe on its own lines, indented like the cursor's line, as one undo."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        line = cursor.block().text()
        before = line[: cursor.positionInBlock()]
        indent = line[: len(line) - len(line.lstrip(" "))]
        lines = code.rstrip("\n").split("\n")
        if before.strip():
            # After code on this line: the recipe starts on the next line.
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            prefix, suffix = "\n" + indent, ""
        elif line.strip():
            # Before code on this line: the recipe goes above it.
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            prefix, suffix = indent, "\n"
        else:
            # A blank line: keep the spaces typed so far as the indentation.
            indent, prefix, suffix = before, "", ""
        body = "\n".join([lines[0]] + [indent + item if item else "" for item in lines[1:]])
        cursor.insertText(prefix + body + suffix)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def indent_selection(self, reverse=False):
        """Indent selected lines without replacing their text, with a single undo."""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        if cursor.hasSelection() and self.document().findBlock(end).position() == end:
            end -= 1
        first = self.document().findBlock(start).blockNumber()
        last = self.document().findBlock(end).blockNumber()
        cursor.beginEditBlock()
        for number in range(last, first - 1, -1):
            block = self.document().findBlockByNumber(number)
            edit = QTextCursor(block)
            if reverse:
                count = min(4, len(block.text()) - len(block.text().lstrip(" ")))
                edit.movePosition(
                    QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, count
                )
                edit.removeSelectedText()
            else:
                edit.insertText("    ")
        cursor.endEditBlock()
