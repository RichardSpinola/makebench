# SPDX-License-Identifier: MIT
"""Qt terminal surface: native cells, input and selection without WebEngine."""

from __future__ import annotations
from PySide6.QtCore import QEvent, Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFontDatabase, QFontMetrics, QPainter, QKeySequence
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from .session import TerminalSession, color, key_input
from makebench.i18n import tr


class TerminalWidget(QAbstractScrollArea):
    """Show a VT session; building or showing the preview never starts processes."""

    status_changed = Signal(str)

    def __init__(self, parent=None, root=None, editing=False):
        """Prepare a fixed font, selection and a non-blocking read timer."""
        super().__init__(parent)
        self.terminal = TerminalSession(root=root)
        self.editing = editing
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if not editing else Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(160, 100)
        self.setAccessibleName(tr("Terminal"))
        self.anchor = self.selection_end = None
        self._revision = -1
        self._was_running = False
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.refresh)
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())
        self.destroyed.connect(lambda: self.terminal.stop())
        self.metrics()

    def sizeHint(self):
        """Suggest a useful area without forcing a fixed size on the application layout."""
        return QSize(560, 260)

    def metrics(self):
        """Measure cells in logical pixels, respecting the desktop scale and font."""
        metrics = QFontMetrics(self.font())
        self.cell_width = max(1, metrics.horizontalAdvance("M"))
        self.cell_height = metrics.height()
        self.baseline = metrics.ascent()

    def start_terminal(self, program=None, arguments=None):
        """Start only by explicit run; the preview stays inert."""
        if self.editing:
            return None
        pid = self.terminal.start(program, arguments)
        self._was_running = True
        self.timer.start()
        self.resize_terminal()
        self.setFocus()
        self.status_changed.emit(f"PID {pid}")
        return pid

    def stop_terminal(self):
        """Stop the session's processes, keeping the screen for reference."""
        self.terminal.stop()
        self.timer.stop()
        self.status_changed.emit(tr("Ended"))
        self.viewport().update()

    def send_terminal(self, text):
        """Provide the ctx API with the same input used by the keyboard."""
        return self.terminal.send(text)

    def resize_terminal(self):
        """Report the number of visible cells to the process and the emulation."""
        self.metrics()
        self.terminal.resize(
            max(2, self.viewport().width() // self.cell_width),
            max(2, self.viewport().height() // self.cell_height),
        )

    def resizeEvent(self, event):
        """Keep the process informed about changes to the area's size."""
        super().resizeEvent(event)
        self.resize_terminal()
        self.refresh()

    def refresh(self):
        """Refresh only after output, keeping the position while browsing history."""
        bar = self.verticalScrollBar()
        follow = bar.value() >= bar.maximum()
        revision = self.terminal.poll()
        if revision != self._revision:
            self._revision = revision
            bar.setRange(0, max(0, len(self.terminal.lines()) - self.terminal.screen.lines))
            bar.setPageStep(self.terminal.screen.lines)
            if follow:
                bar.setValue(bar.maximum())
            self.viewport().update()
        if self._was_running and not self.terminal.running:
            self._was_running = False
            self.timer.stop()
            self.status_changed.emit(tr("Ended · code {code}").format(code=self.terminal.exit_code))

    def paintEvent(self, event):
        """Draw ANSI cells with the default colors inherited from the native palette."""
        painter = QPainter(self.viewport())
        painter.setFont(self.font())
        foreground, background = (
            self.palette().text().color().name(),
            self.palette().base().color().name(),
        )
        painter.fillRect(self.viewport().rect(), QColor(background))
        screen = self.terminal.screen
        lines = self.terminal.lines()
        offset = self.verticalScrollBar().value()
        selection = (
            sorted((self.anchor, self.selection_end))
            if self.anchor is not None and self.selection_end is not None
            else None
        )
        glyphs = []
        for row, line in enumerate(lines[offset : offset + screen.lines]):
            for column in range(screen.columns):
                cell = line[column]
                x, y = column * self.cell_width, row * self.cell_height
                fg, bg = color(cell.fg, foreground), color(cell.bg, background)
                if cell.reverse:
                    fg, bg = bg, fg
                position = (offset + row, column)
                if selection and selection[0] <= position < selection[1]:
                    fg, bg = (
                        self.palette().highlightedText().color().name(),
                        self.palette().highlight().color().name(),
                    )
                painter.fillRect(x, y, self.cell_width, self.cell_height, QColor(bg))
                glyphs.append((x, y, cell, fg))
        # Backgrounds before glyphs: the second cell does not erase a wide CJK character.
        for x, y, cell, fg in glyphs:
            font = self.font()
            font.setBold(cell.bold)
            font.setItalic(cell.italics)
            font.setUnderline(cell.underscore)
            painter.setFont(font)
            painter.setPen(QColor(fg))
            painter.drawText(x, y + self.baseline, cell.data)
        cursor = screen.cursor
        if (
            not cursor.hidden
            and self.terminal.running
            and offset == self.verticalScrollBar().maximum()
        ):
            painter.setPen(QColor(foreground))
            painter.drawRect(
                cursor.x * self.cell_width,
                cursor.y * self.cell_height,
                self.cell_width - 1,
                self.cell_height - 1,
            )
        if self.editing or (self._revision < 0 and not self.terminal.running):
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignmentFlag.AlignCenter,
                tr("Terminal · inactive preview")
                if self.editing
                else tr("Start the terminal to open a session"),
            )

    def selected_text(self):
        """Extract the selection by cells, without ANSI codes or hidden content."""
        if self.anchor is None or self.selection_end is None:
            return ""
        start, end = sorted((self.anchor, self.selection_end))
        lines = self.terminal.lines()
        text = []
        for row in range(start[0], min(end[0] + 1, len(lines))):
            first = start[1] if row == start[0] else 0
            last = end[1] if row == end[0] else self.terminal.screen.columns
            text.append("".join(lines[row][c].data for c in range(first, last)).rstrip())
        return "\n".join(text)

    def position(self, point):
        """Turn pointer coordinates into bounded cell indexes."""
        return (
            max(
                0,
                min(
                    len(self.terminal.lines()) - 1,
                    self.verticalScrollBar().value() + int(point.y()) // self.cell_height,
                ),
            ),
            max(0, min(self.terminal.screen.columns, int(point.x()) // self.cell_width)),
        )

    def mousePressEvent(self, event):
        """Start a drag selection; the right button offers copy/paste."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = self.selection_end = self.position(event.position())
            self.viewport().update()
            self.setFocus()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Extend the selection without forwarding clicks as shell commands."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.selection_end = self.position(event.position())
            self.viewport().update()

    def contextMenuEvent(self, event):
        """Offer the usual actions without introducing command evaluation."""
        menu = QMenu(self)
        menu.addAction(
            tr("Copy"), lambda: QApplication.clipboard().setText(self.selected_text())
        ).setEnabled(bool(self.selected_text()))
        menu.addAction(tr("Paste"), lambda: self.paste()).setEnabled(
            self.terminal.running and not self.editing
        )
        menu.exec(event.globalPos())

    def paste(self):
        """Send the clipboard, using bracketed paste when requested."""
        value = QApplication.clipboard().text()
        if 2004 << 5 in self.terminal.screen.mode:
            value = "\x1b[200~" + value + "\x1b[201~"
        self.send_terminal(value)

    def focusNextPrevChild(self, next):
        """Tab completes in the active terminal; Ctrl+Tab leaves the surface."""
        if self.terminal.running and not self.editing:
            return False
        return super().focusNextPrevChild(next)

    def event(self, event):
        """Keep terminal program keys out of the IDE's global shortcuts."""
        if event.type() == QEvent.Type.ShortcutOverride and not self.editing:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Forward keys to the PTY, reserving Ctrl+Shift+C/V for the clipboard."""
        modifiers = event.modifiers()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if control and event.key() == Qt.Key.Key_Tab:
            super().focusNextPrevChild(not shift)
            return
        if control and shift and event.key() == Qt.Key.Key_C:
            QApplication.clipboard().setText(self.selected_text())
            return
        if control and shift and event.key() == Qt.Key.Key_V:
            self.paste()
            return
        if shift and event.key() in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value()
                + (-1 if event.key() == Qt.Key.Key_PageUp else 1) * self.terminal.screen.lines
            )
            return
        mapping = {
            Qt.Key.Key_Backspace: "BackSpace",
            Qt.Key.Key_PageUp: "Page_Up",
            Qt.Key.Key_PageDown: "Page_Down",
        }
        name = mapping.get(event.key(), QKeySequence(event.key()).toString())
        self.send_terminal(
            key_input(
                name,
                event.text(),
                control,
                bool(modifiers & Qt.KeyboardModifier.AltModifier),
                1 << 5 in self.terminal.screen.mode,
            )
        )
        self.anchor = self.selection_end = None
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
        event.accept()

    def closeEvent(self, event):
        """Leave no processes behind when the surface closes."""
        self.stop_terminal()
        super().closeEvent(event)


class TerminalPanel(QWidget):
    """IDE tab with explicit start, interruption and session state."""

    def __init__(self, parent=None, root=None):
        """Build compact controls without opening a shell when the IDE starts."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.start_button = QPushButton(tr("Start shell"))
        row.addWidget(self.start_button)
        stop = QPushButton(tr("Stop"))
        row.addWidget(stop)
        self.status = QLabel(tr("Stopped"))
        row.addWidget(self.status, 1)
        layout.addLayout(row)
        self.surface = TerminalWidget(root=root)
        layout.addWidget(self.surface, 1)
        self.start_button.clicked.connect(self.start)
        stop.clicked.connect(self.surface.stop_terminal)
        self.surface.status_changed.connect(self.status.setText)
        self.surface.status_changed.connect(
            lambda _: self.start_button.setEnabled(not self.surface.terminal.running)
        )

    def start(self):
        """Start the shell on click and show failures without closing the editor."""
        try:
            if hasattr(self, "directory_provider"):
                self.surface.terminal.root = self.directory_provider()
            self.surface.start_terminal()
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))

    def closeEvent(self, event):
        """Also close the terminal when the owning tab closes."""
        self.surface.stop_terminal()
        super().closeEvent(event)
