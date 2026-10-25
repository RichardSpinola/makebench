"""Text editing over the component, with explicit confirmation and cancellation."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit


class InlineText(QLineEdit):
    """Single-line field; the composition stays intact until confirmed."""

    finished = Signal(str, bool)

    def __init__(self, text, parent):
        """Keep a session so losing focus does not confirm twice."""
        super().__init__(text, parent)
        self.done = False
        self.selectAll()

    def finish(self, accept):
        """Finish before emitting, preventing re-entry when focus leaves."""
        if self.done:
            return
        self.done = True
        self.finished.emit(self.text(), accept)

    def keyPressEvent(self, event):
        """Enter confirms; Escape cancels and keeps the previous text."""
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.finish(True)
        elif event.key() == Qt.Key.Key_Escape:
            self.finish(False)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        """Confirm when moving to another control, without destroying the field during the event."""
        self.finish(True)
        super().focusOutEvent(event)


class InlineParagraph(QPlainTextEdit):
    """Multi-line text; Ctrl+Enter confirms and Escape cancels."""

    finished = Signal(str, bool)

    def __init__(self, text, parent):
        """Keep multi-line content as text, with no evaluation at all."""
        super().__init__(text, parent)
        self.done = False
        self.selectAll()

    def finish(self, accept):
        """Finish a single edit for the document history."""
        if self.done:
            return
        self.done = True
        self.finished.emit(self.toPlainText(), accept)

    def keyPressEvent(self, event):
        """Keep Enter as a new line, with explicit confirmation by Ctrl+Enter."""
        if event.key() == Qt.Key.Key_Escape:
            self.finish(False)
        elif (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.finish(True)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        """Confirm the current text when the user moves to another control."""
        self.finish(True)
        super().focusOutEvent(event)
