# SPDX-License-Identifier: GPL-3.0-or-later
"""Code editors with line numbers and Python syntax highlighting."""

import keyword
import re

from PySide6.QtCore import QRect, QSize, Qt, Slot, QEvent, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QTextEdit,
    QWidget,
    QLineEdit,
    QToolButton,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
)
from makebench.i18n import tr


class PythonHighlight(QSyntaxHighlighter):
    """Highlight keywords, strings and comments without interpreting code."""

    def highlightBlock(self, text):
        """Apply light colors to a line; does not replace syntax analysis."""
        from .theme import manager

        t = manager().tokens
        rules = [
            (r"\b(?:" + "|".join(keyword.kwlist) + r")\b", t["info"]),
            (r"\b\d+(?:\.\d+)?\b", t["warning"]),
            (r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""", t["success"]),
            (r"#.*", t["muted"]),
        ]
        if getattr(self, "language", "python") == "bash":
            rules = [
                (r"\b(?:if|then|fi|for|do|done|echo|printf|exit|read)\b", t["info"]),
                (r"\$[a-zA-Z0-9_{}]+", t["accent"]),
                (r"#.*", t["muted"]),
            ]
        if getattr(self, "language", "python") == "plain":
            rules = []
        for pattern, color in rules:
            style = QTextCharFormat()
            style.setForeground(QColor(color))
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), style)


class LineNumbers(QWidget):
    """Margin that follows only the editor's visible lines."""

    def __init__(self, editor):
        """Bind the margin to the displayed document."""
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        """Reserve space according to the number of line digits."""
        return QSize(self.editor.number_width(), 0)

    def mousePressEvent(self, event):
        """Toggle a breakpoint on the real line, never changing the document text."""
        if getattr(self.editor, "breakpoints_enabled", False):
            block = self.editor.firstVisibleBlock()
            top = (
                self.editor.blockBoundingGeometry(block)
                .translated(self.editor.contentOffset())
                .top()
            )
            while block.isValid():
                height = self.editor.blockBoundingRect(block).height()
                if top <= event.position().y() < top + height:
                    self.editor.breakpoint_requested.emit(block.blockNumber() + 1)
                    return
                top += height
                block = block.next()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Paint numbers aligned with the real positions of the text blocks."""
        editor = self.editor
        painter = QPainter(self)
        painter.fillRect(event.rect(), editor.palette().alternateBase())
        painter.setPen(editor.palette().placeholderText().color())
        block = editor.firstVisibleBlock()
        number = block.blockNumber()
        top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(editor.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                if number + 1 in getattr(editor, "breakpoints", set()):
                    painter.setBrush(QColor("#d34b4b"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(2, top + 3, 9, 9)
                painter.setPen(editor.palette().placeholderText().color())
                painter.drawText(
                    0,
                    top,
                    self.width() - 8,
                    editor.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(number + 1),
                )
            top += height
            number += 1
            block = block.next()


from .code_tools import CodeTools


class CodeEditor(CodeTools, QPlainTextEdit):
    """Present Python and highlight the line that corresponds to a block."""

    origin_requested = Signal(int)
    breakpoint_requested = Signal(int)

    def __init__(self, readonly=False, parent=None):
        """Set font, indentation, margin and syntax without enabling execution."""
        super().__init__(parent)
        self.breakpoints = set()
        self.breakpoints_enabled = False
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setReadOnly(readonly)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setPlaceholderText(tr("Write your Python functions here."))
        self.find_bar = QWidget(self)
        bar_layout = QVBoxLayout(self.find_bar)
        bar_layout.setContentsMargins(4, 2, 4, 2)
        bar_layout.setSpacing(2)
        find_layout = QHBoxLayout()
        bar_layout.addLayout(find_layout)
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText(tr("Search in code…"))
        self.find_text.setAccessibleName(tr("Search in code"))
        self.find_text.setClearButtonEnabled(True)
        self.find_text.installEventFilter(self)
        find_layout.addWidget(self.find_text, 1)
        self.find_status = QLabel()
        find_layout.addWidget(self.find_status)
        for label, callback in [
            ("↑", lambda: self.find_next(True)),
            ("↓", self.find_next),
            ("×", self.close_find),
        ]:
            button = QToolButton()
            button.setText(label)
            button.setAccessibleName(
                {"↑": tr("Previous result"), "↓": tr("Next result"), "×": tr("Close search")}[label]
            )
            button.clicked.connect(callback)
            find_layout.addWidget(button)
        self.replace_row = QWidget()
        replacement = QHBoxLayout(self.replace_row)
        replacement.setContentsMargins(0, 0, 0, 0)
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText(tr("Replace with…"))
        self.replace_text.setAccessibleName(tr("Replacement text"))
        replacement.addWidget(self.replace_text, 1)
        for label, callback in [(tr("Replace"), self.replace_one), (tr("All"), self.replace_all)]:
            button = QToolButton()
            button.setText(label)
            button.clicked.connect(callback)
            replacement.addWidget(button)
        self.replace_row.hide()
        bar_layout.addWidget(self.replace_row)
        self.find_bar.hide()
        self.find_text.textEdited.connect(lambda _: self.find_next(restart=True))
        self.find_text.returnPressed.connect(self.find_next)
        for sequence, callback in [
            ("Ctrl+H", self.open_replace),
            ("Ctrl+G", self.go_to_line),
            (
                "F4",
                lambda: (
                    self.origin_requested.emit(self.textCursor().blockNumber() + 1)
                    if self.isReadOnly() and getattr(self, "origin_enabled", True)
                    else None
                ),
            ),
            ("Ctrl+F", self.open_find),
            ("F3", self.find_next),
            ("Shift+F3", lambda: self.find_next(True)),
            ("Esc", self.close_find),
        ]:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        self.numbers = LineNumbers(self)
        self.highlighter = PythonHighlight(self.document())
        self._error_selections = []
        self.cursorPositionChanged.connect(self.highlight_cursor)
        self.textChanged.connect(self.highlight_cursor)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_numbers)
        self._update_margin()
        from .theme import manager

        manager().changed.connect(self.theme_changed)

    def number_width(self):
        """Compute a sufficient width without reserving a huge fixed column."""
        return 16 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))

    def _update_margin(self):
        """Adjust the margin when the document gains or loses lines."""
        height = self.find_bar.sizeHint().height() if not self.find_bar.isHidden() else 0
        self.setViewportMargins(self.number_width(), height, 0, 0)
        rect = self.contentsRect()
        self.find_bar.setGeometry(rect.left(), rect.top(), rect.width(), height)
        self.numbers.setGeometry(
            rect.left(), rect.top() + height, self.number_width(), rect.height() - height
        )

    def _update_numbers(self, rect, dy):
        """Sync the margin with scrolling and text repaints."""
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event):
        """Reposition the margin along with the editor's useful area."""
        super().resizeEvent(event)
        self._update_margin()

    def show_line(self, line: int) -> None:
        """Highlight a source line and bring it into view."""
        block = self.document().findBlockByNumber(line - 1)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(self.palette().alternateBase())
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self.highlight_cursor()
        self.centerCursor()

    def eventFilter(self, watched, event):
        """Escape also works while the search field has typing focus."""
        if (
            watched is getattr(self, "find_text", None)
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.close_find()
            return True
        return super().eventFilter(watched, event)

    def open_find(self):
        """Non-modal local search, keeping the code and the selected context."""
        selected = self.textCursor().selectedText()
        if selected and "\u2029" not in selected:
            self.find_text.setText(selected)
        self.find_bar.show()
        self._update_margin()
        self.find_text.setFocus()
        self.find_text.selectAll()

    def close_find(self):
        """Escape returns focus to the code without losing the found selection."""
        if self.find_bar.isHidden():
            return
        self.find_bar.hide()
        self.replace_row.hide()
        self._update_margin()
        self.setFocus()

    def find_next(self, backward=False, restart=False):
        """Step through occurrences, wrapping around and reporting when there are none."""
        text = self.find_text.text()
        if not text:
            self.find_status.clear()
            return
        cursor = self.textCursor()
        position = cursor.selectionStart() if restart or backward else cursor.selectionEnd()
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = self.document().find(text, position, flags)
        if found.isNull():
            found = self.document().find(
                text, self.document().characterCount() - 1 if backward else 0, flags
            )
        if found.isNull():
            self.find_status.setText(tr("No results"))
        else:
            self.find_status.clear()
            self.setTextCursor(found)
            self.ensureCursorVisible()

    def keyPressEvent(self, event):
        """Offer search, comments and Python indentation without running the content."""
        if self.isReadOnly():
            super().keyPressEvent(event)
            return
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Slash
        ):
            cursor = self.textCursor()
            start = min(cursor.anchor(), cursor.position())
            end = max(cursor.anchor(), cursor.position())
            end = (
                end - 1
                if cursor.hasSelection() and self.document().findBlock(end).position() == end
                else end
            )
            first = self.document().findBlock(start).blockNumber()
            last = self.document().findBlock(end).blockNumber()
            cursor.beginEditBlock()
            for number in range(last, first - 1, -1):
                block = self.document().findBlockByNumber(number)
                line = block.text()
                edit = QTextCursor(block)
                if line.lstrip().startswith("#"):
                    offset = len(line) - len(line.lstrip())
                    edit.setPosition(block.position() + offset)
                    edit.deleteChar()
                    if self.document().findBlockByNumber(number).text()[offset : offset + 1] == " ":
                        edit.deleteChar()
                else:
                    edit.insertText("# ")
            cursor.endEditBlock()
            return
        if event.key() == Qt.Key.Key_Tab:
            if self.textCursor().hasSelection():
                self.indent_selection()
            else:
                self.textCursor().insertText("    ")
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            line = self.textCursor().block().text()[: self.textCursor().positionInBlock()]
            indent = line[: len(line) - len(line.lstrip())]
            if line.rstrip().endswith(":"):
                indent += "    "
            super().keyPressEvent(event)
            self.textCursor().insertText(indent)
            return
        if event.key() == Qt.Key.Key_Backtab:
            self.indent_selection(True)
            return
        super().keyPressEvent(event)

    def mark_syntax_error(self, line=None, message=""):
        """Underline a static diagnostic without changing text, focus or the ability to save."""
        self._error_selections = []
        if line:
            block = self.document().findBlockByNumber(line - 1)
            if block.isValid():
                cursor = QTextCursor(block)
                cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                from .theme import manager

                selection.format.setUnderlineColor(QColor(manager().tokens["error"]))
                selection.format.setToolTip(message)
                self._error_selections = [selection]
        self.highlight_cursor()

    @Slot(dict)
    def theme_changed(self, _tokens):
        """Repaint code and numbers; the connection follows the Qt widget's lifetime."""
        font = QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        from .theme import manager

        font.setPointSizeF(max(8, font.pointSizeF()) * manager().scale / 100)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self._update_margin()
        self.highlighter.rehighlight()
        self.numbers.update()
        self.highlight_cursor()
