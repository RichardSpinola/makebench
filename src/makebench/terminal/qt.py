"""Superfície Qt do terminal: células nativas, entrada e seleção sem WebEngine."""
from __future__ import annotations
from PySide6.QtCore import QEvent, Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFontDatabase, QFontMetrics, QPainter, QKeySequence
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget
from .session import TerminalSession, color, key_input


class TerminalWidget(QAbstractScrollArea):
    """Exibe uma sessão VT; construir ou mostrar a prévia não inicia processos."""
    status_changed = Signal(str)

    def __init__(self, parent=None, root=None, editing=False):
        """Prepara fonte fixa, seleção e relógio de leitura não bloqueante."""
        super().__init__(parent)
        self.terminal = TerminalSession(root=root)
        self.editing = editing
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if not editing else Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(160, 100)
        self.setAccessibleName('Terminal')
        self.anchor = self.selection_end = None
        self._revision = -1
        self._was_running = False
        self.timer = QTimer(self); self.timer.setInterval(20); self.timer.timeout.connect(self.refresh)
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())
        self.destroyed.connect(lambda: self.terminal.stop())
        self.metrics()

    def sizeHint(self):
        """Sugere área útil sem impor tamanho fixo ao layout do aplicativo."""
        return QSize(560, 260)

    def metrics(self):
        """Mede células em pixels lógicos respeitando escala e fonte do desktop."""
        metrics = QFontMetrics(self.font())
        self.cell_width = max(1, metrics.horizontalAdvance('M'))
        self.cell_height = metrics.height()
        self.baseline = metrics.ascent()

    def start_terminal(self, program=None, arguments=None):
        """Inicia somente por execução explícita; prévia permanece inerte."""
        if self.editing:
            return None
        pid = self.terminal.start(program, arguments)
        self._was_running = True
        self.timer.start(); self.resize_terminal(); self.setFocus()
        self.status_changed.emit(f'PID {pid}')
        return pid

    def stop_terminal(self):
        """Encerra processos da sessão, preservando a tela para consulta."""
        self.terminal.stop(); self.timer.stop(); self.status_changed.emit('Encerrado'); self.viewport().update()

    def send_terminal(self, text):
        """Fornece a mesma entrada usada pelo teclado à API ctx."""
        return self.terminal.send(text)

    def resize_terminal(self):
        """Comunica a quantidade visível de células ao processo e à emulação."""
        self.metrics()
        self.terminal.resize(max(2, self.viewport().width() // self.cell_width), max(2, self.viewport().height() // self.cell_height))

    def resizeEvent(self, event):
        """Mantém o processo informado de alterações de tamanho da área."""
        super().resizeEvent(event); self.resize_terminal(); self.refresh()

    def refresh(self):
        """Atualiza apenas após saída, mantendo a posição ao consultar histórico."""
        bar = self.verticalScrollBar(); follow = bar.value() >= bar.maximum()
        revision = self.terminal.poll()
        if revision != self._revision:
            self._revision = revision
            bar.setRange(0, max(0, len(self.terminal.lines()) - self.terminal.screen.lines))
            bar.setPageStep(self.terminal.screen.lines)
            if follow: bar.setValue(bar.maximum())
            self.viewport().update()
        if self._was_running and not self.terminal.running:
            self._was_running = False; self.timer.stop()
            self.status_changed.emit(f'Encerrado · código {self.terminal.exit_code}')

    def paintEvent(self, event):
        """Desenha células ANSI com as cores padrão herdadas da paleta nativa."""
        painter = QPainter(self.viewport()); painter.setFont(self.font())
        foreground, background = self.palette().text().color().name(), self.palette().base().color().name()
        painter.fillRect(self.viewport().rect(), QColor(background))
        screen = self.terminal.screen; lines = self.terminal.lines(); offset = self.verticalScrollBar().value()
        selection = sorted((self.anchor, self.selection_end)) if self.anchor is not None and self.selection_end is not None else None
        glyphs=[]
        for row, line in enumerate(lines[offset:offset + screen.lines]):
            for column in range(screen.columns):
                cell = line[column]; x, y = column * self.cell_width, row * self.cell_height
                fg, bg = color(cell.fg, foreground), color(cell.bg, background)
                if cell.reverse: fg, bg = bg, fg
                position = (offset + row, column)
                if selection and selection[0] <= position < selection[1]:
                    fg, bg = self.palette().highlightedText().color().name(), self.palette().highlight().color().name()
                painter.fillRect(x, y, self.cell_width, self.cell_height, QColor(bg))
                glyphs.append((x,y,cell,fg))
        # Fundos antes dos glifos: a segunda célula não apaga um caractere CJK largo.
        for x,y,cell,fg in glyphs:
            font = self.font(); font.setBold(cell.bold); font.setItalic(cell.italics); font.setUnderline(cell.underscore)
            painter.setFont(font); painter.setPen(QColor(fg)); painter.drawText(x, y + self.baseline, cell.data)
        cursor = screen.cursor
        if not cursor.hidden and self.terminal.running and offset == self.verticalScrollBar().maximum():
            painter.setPen(QColor(foreground)); painter.drawRect(cursor.x*self.cell_width, cursor.y*self.cell_height, self.cell_width-1, self.cell_height-1)
        if self.editing or (self._revision < 0 and not self.terminal.running):
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, 'Terminal · prévia inativa' if self.editing else 'Inicie o terminal para abrir uma sessão')

    def selected_text(self):
        """Extrai seleção por células, sem códigos ANSI nem conteúdo oculto."""
        if self.anchor is None or self.selection_end is None: return ''
        start, end = sorted((self.anchor, self.selection_end)); lines = self.terminal.lines(); text = []
        for row in range(start[0], min(end[0]+1, len(lines))):
            first = start[1] if row == start[0] else 0
            last = end[1] if row == end[0] else self.terminal.screen.columns
            text.append(''.join(lines[row][c].data for c in range(first, last)).rstrip())
        return '\n'.join(text)

    def position(self, point):
        """Converte coordenadas do ponteiro em índices limitados de células."""
        return (max(0, min(len(self.terminal.lines())-1, self.verticalScrollBar().value()+int(point.y())//self.cell_height)),
                max(0, min(self.terminal.screen.columns, int(point.x())//self.cell_width)))

    def mousePressEvent(self, event):
        """Inicia seleção por arraste; botão direito oferece copiar/colar."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = self.selection_end = self.position(event.position()); self.viewport().update(); self.setFocus()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Estende a seleção sem reenviar cliques como comandos do shell."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.selection_end = self.position(event.position()); self.viewport().update()

    def contextMenuEvent(self, event):
        """Disponibiliza ações usuais sem introduzir avaliação de comandos."""
        menu = QMenu(self)
        menu.addAction('Copiar', lambda: QApplication.clipboard().setText(self.selected_text())).setEnabled(bool(self.selected_text()))
        menu.addAction('Colar', lambda: self.paste()).setEnabled(self.terminal.running and not self.editing)
        menu.exec(event.globalPos())

    def paste(self):
        """Envia a área de transferência, usando bracketed paste quando solicitado."""
        value = QApplication.clipboard().text()
        if 2004 << 5 in self.terminal.screen.mode: value = '\x1b[200~' + value + '\x1b[201~'
        self.send_terminal(value)

    def event(self, event):
        """Mantém teclas de programas de terminal fora dos atalhos globais da IDE."""
        if event.type()==QEvent.Type.ShortcutOverride and not self.editing:
            event.accept();return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Encaminha teclas ao PTY, reservando Ctrl+Shift+C/V para transferência."""
        modifiers = event.modifiers(); control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if control and shift and event.key() == Qt.Key.Key_C:
            QApplication.clipboard().setText(self.selected_text()); return
        if control and shift and event.key() == Qt.Key.Key_V: self.paste(); return
        if shift and event.key() in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()+(-1 if event.key()==Qt.Key.Key_PageUp else 1)*self.terminal.screen.lines); return
        mapping = {Qt.Key.Key_Backspace:'BackSpace',Qt.Key.Key_PageUp:'Page_Up', Qt.Key.Key_PageDown:'Page_Down'}
        name = mapping.get(event.key(), QKeySequence(event.key()).toString())
        self.send_terminal(key_input(name, event.text(), control, bool(modifiers & Qt.KeyboardModifier.AltModifier), 1 << 5 in self.terminal.screen.mode))
        self.anchor = self.selection_end = None
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()); event.accept()

    def closeEvent(self, event):
        """Não deixa processos quando a superfície é fechada."""
        self.stop_terminal(); super().closeEvent(event)


class TerminalPanel(QWidget):
    """Aba da IDE com início explícito, interrupção e estado da sessão."""
    def __init__(self, parent=None, root=None):
        """Monta controles compactos sem abrir um shell na inicialização da IDE."""
        super().__init__(parent); layout = QVBoxLayout(self); layout.setContentsMargins(4,4,4,4)
        row = QHBoxLayout(); self.start_button = QPushButton('Iniciar shell'); row.addWidget(self.start_button)
        stop = QPushButton('Encerrar'); row.addWidget(stop); self.status = QLabel('Parado'); row.addWidget(self.status,1)
        layout.addLayout(row); self.surface = TerminalWidget(root=root); layout.addWidget(self.surface,1)
        self.start_button.clicked.connect(self.start); stop.clicked.connect(self.surface.stop_terminal)
        self.surface.status_changed.connect(self.status.setText)
        self.surface.status_changed.connect(lambda _: self.start_button.setEnabled(not self.surface.terminal.running))

    def start(self):
        """Inicia o shell por clique e apresenta falhas sem encerrar o editor."""
        try:
            if hasattr(self,'directory_provider'):self.surface.terminal.root=self.directory_provider()
            self.surface.start_terminal()
        except (OSError,ValueError) as exc: self.status.setText(str(exc))

    def closeEvent(self, event):
        """Fecha também o terminal ao encerrar a aba proprietária."""
        self.surface.stop_terminal(); super().closeEvent(event)
