"""Editores de código com linhas numeradas e realce de sintaxe Python."""
import keyword
import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class PythonHighlight(QSyntaxHighlighter):
    """Realça palavras, strings e comentários sem interpretar código."""
    def highlightBlock(self, text):
        """Aplica cores leves a uma linha; não substitui análise sintática."""
        rules = [(r'\b(?:'+'|'.join(keyword.kwlist)+r')\b','#8e44ad'),
                 (r'\b\d+(?:\.\d+)?\b','#ad5b00'),
                 (r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''','#16724a'),
                 (r'#.*','#727a8c')]
        for pattern, color in rules:
            style = QTextCharFormat(); style.setForeground(QColor(color))
            for match in re.finditer(pattern,text):
                self.setFormat(match.start(),match.end()-match.start(),style)


class LineNumbers(QWidget):
    """Margem que acompanha apenas as linhas visíveis do editor."""
    def __init__(self, editor):
        """Associa a margem ao documento exibido."""
        super().__init__(editor); self.editor=editor

    def sizeHint(self):
        """Reserva espaço conforme o número de dígitos das linhas."""
        return QSize(self.editor.number_width(),0)

    def paintEvent(self, event):
        """Pinta números alinhados às posições reais dos blocos de texto."""
        editor=self.editor; painter=QPainter(self)
        painter.fillRect(event.rect(),QColor('#f0f1f5'));painter.setPen(QColor('#778094'))
        block=editor.firstVisibleBlock(); number=block.blockNumber()
        top=round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height=round(editor.blockBoundingRect(block).height())
            if block.isVisible() and top+height>=event.rect().top():
                painter.drawText(0,top,self.width()-8,editor.fontMetrics().height(),Qt.AlignmentFlag.AlignRight,str(number+1))
            top+=height;number+=1;block=block.next()


class CodeEditor(QPlainTextEdit):
    """Apresenta Python e destaca a linha correspondente a um bloco."""
    def __init__(self, readonly=False, parent=None):
        """Configura fonte, recuo, margem e sintaxe sem habilitar execução."""
        super().__init__(parent)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setReadOnly(readonly)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self.setPlaceholderText('Escreva suas funções Python aqui.')
        self.numbers=LineNumbers(self)
        self.highlighter=PythonHighlight(self.document())
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_numbers)
        self._update_margin()

    def number_width(self):
        """Calcula largura suficiente sem reservar uma coluna fixa enorme."""
        return 16+self.fontMetrics().horizontalAdvance('9')*len(str(max(1,self.blockCount())))

    def _update_margin(self):
        """Ajusta a margem quando o documento ganha ou perde linhas."""
        self.setViewportMargins(self.number_width(),0,0,0)

    def _update_numbers(self, rect, dy):
        """Sincroniza a margem com rolagem e repintura do texto."""
        if dy:self.numbers.scroll(0,dy)
        else:self.numbers.update(0,rect.y(),self.numbers.width(),rect.height())
        if rect.contains(self.viewport().rect()):self._update_margin()

    def resizeEvent(self, event):
        """Reposiciona a margem junto da área útil do editor."""
        super().resizeEvent(event)
        rect=self.contentsRect()
        self.numbers.setGeometry(QRect(rect.left(),rect.top(),self.number_width(),rect.height()))

    def show_line(self, line: int) -> None:
        """Destaca uma linha de origem e a traz para a área visível."""
        block = self.document().findBlockByNumber(line - 1)
        if not block.isValid():return
        cursor = QTextCursor(block);self.setTextCursor(cursor)
        selection = QTextEdit.ExtraSelection();selection.cursor = cursor
        selection.format.setBackground(QColor('#e5d9ff'))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self.setExtraSelections([selection]);self.centerCursor()
