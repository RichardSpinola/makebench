"""Editores de código com linhas numeradas e realce de sintaxe Python."""
import keyword
import re

from PySide6.QtCore import QRect, QSize, Qt, Slot, QEvent
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QKeySequence, QShortcut
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget, QLineEdit, QToolButton, QLabel, QHBoxLayout


class PythonHighlight(QSyntaxHighlighter):
    """Realça palavras, strings e comentários sem interpretar código."""
    def highlightBlock(self, text):
        """Aplica cores leves a uma linha; não substitui análise sintática."""
        from .theme import manager
        t=manager().tokens
        rules = [(r'\b(?:'+'|'.join(keyword.kwlist)+r')\b',t['info']),
                 (r'\b\d+(?:\.\d+)?\b',t['warning']),
                 (r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''',t['success']),
                 (r'#.*',t['muted'])]
        if getattr(self,'language','python')=='bash':rules=[(r'\b(?:if|then|fi|for|do|done|echo|printf|exit|read)\b',t['info']),(r'\$[a-zA-Z0-9_{}]+',t['accent']),(r'#.*',t['muted'])]
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
        painter.fillRect(event.rect(),editor.palette().alternateBase());painter.setPen(editor.palette().placeholderText().color())
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
        self.find_bar=QWidget(self);find_layout=QHBoxLayout(self.find_bar);find_layout.setContentsMargins(4,2,4,2)
        self.find_text=QLineEdit();self.find_text.setPlaceholderText('Buscar no código…');self.find_text.setAccessibleName('Buscar no código');self.find_text.setClearButtonEnabled(True);self.find_text.installEventFilter(self);find_layout.addWidget(self.find_text,1)
        self.find_status=QLabel();find_layout.addWidget(self.find_status)
        for label,callback in [('↑',lambda:self.find_next(True)),('↓',self.find_next),('×',self.close_find)]:
            button=QToolButton();button.setText(label);button.setAccessibleName({'↑':'Resultado anterior','↓':'Próximo resultado','×':'Fechar busca'}[label]);button.clicked.connect(callback);find_layout.addWidget(button)
        self.find_bar.hide();self.find_text.textEdited.connect(lambda _:self.find_next(restart=True));self.find_text.returnPressed.connect(self.find_next)
        for sequence,callback in [('Ctrl+F',self.open_find),('F3',self.find_next),('Shift+F3',lambda:self.find_next(True)),('Esc',self.close_find)]:
            shortcut=QShortcut(QKeySequence(sequence),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.activated.connect(callback)
        self.numbers=LineNumbers(self)
        self.highlighter=PythonHighlight(self.document())
        self._error_selections=[]
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_numbers)
        self._update_margin()
        from .theme import manager
        manager().changed.connect(self.theme_changed)

    def number_width(self):
        """Calcula largura suficiente sem reservar uma coluna fixa enorme."""
        return 16+self.fontMetrics().horizontalAdvance('9')*len(str(max(1,self.blockCount())))

    def _update_margin(self):
        """Ajusta a margem quando o documento ganha ou perde linhas."""
        height=self.find_bar.sizeHint().height() if not self.find_bar.isHidden() else 0
        self.setViewportMargins(self.number_width(),height,0,0)
        rect=self.contentsRect();self.find_bar.setGeometry(rect.left(),rect.top(),rect.width(),height)
        self.numbers.setGeometry(rect.left(),rect.top()+height,self.number_width(),rect.height()-height)

    def _update_numbers(self, rect, dy):
        """Sincroniza a margem com rolagem e repintura do texto."""
        if dy:self.numbers.scroll(0,dy)
        else:self.numbers.update(0,rect.y(),self.numbers.width(),rect.height())
        if rect.contains(self.viewport().rect()):self._update_margin()

    def resizeEvent(self, event):
        """Reposiciona a margem junto da área útil do editor."""
        super().resizeEvent(event)
        self._update_margin()

    def show_line(self, line: int) -> None:
        """Destaca uma linha de origem e a traz para a área visível."""
        block = self.document().findBlockByNumber(line - 1)
        if not block.isValid():return
        cursor = QTextCursor(block);self.setTextCursor(cursor)
        selection = QTextEdit.ExtraSelection();selection.cursor = cursor
        selection.format.setBackground(self.palette().alternateBase())
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self.setExtraSelections([*self._error_selections,selection]);self.centerCursor()

    def eventFilter(self,watched,event):
        """Escape também funciona enquanto a busca tem o foco de digitação."""
        if watched is getattr(self,'find_text',None) and event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Escape:
            self.close_find();return True
        return super().eventFilter(watched,event)

    def open_find(self):
        """Busca local não modal, preservando o código e o contexto selecionado."""
        selected=self.textCursor().selectedText()
        if selected and '\u2029' not in selected:self.find_text.setText(selected)
        self.find_bar.show();self._update_margin();self.find_text.setFocus();self.find_text.selectAll()

    def close_find(self):
        """Escape devolve o foco ao código sem perder a seleção encontrada."""
        if self.find_bar.isHidden():return
        self.find_bar.hide();self._update_margin();self.setFocus()

    def find_next(self,backward=False,restart=False):
        """Percorre ocorrências com retorno ao início/fim e informa ausência de resultados."""
        text=self.find_text.text()
        if not text:self.find_status.clear();return
        cursor=self.textCursor();position=cursor.selectionStart() if restart or backward else cursor.selectionEnd()
        flags=QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found=self.document().find(text,position,flags)
        if found.isNull():found=self.document().find(text,self.document().characterCount()-1 if backward else 0,flags)
        if found.isNull():self.find_status.setText('Nenhum resultado')
        else:self.find_status.clear();self.setTextCursor(found);self.ensureCursorVisible()

    def keyPressEvent(self,event):
        """Oferece busca, comentários e recuo Python sem executar o conteúdo."""
        if self.isReadOnly():super().keyPressEvent(event);return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key()==Qt.Key.Key_Slash:
            cursor=self.textCursor();start=min(cursor.anchor(),cursor.position());end=max(cursor.anchor(),cursor.position())
            first=self.document().findBlock(start).blockNumber();last=self.document().findBlock(end).blockNumber()
            cursor.beginEditBlock()
            for number in range(last,first-1,-1):
                block=self.document().findBlockByNumber(number);line=block.text();edit=QTextCursor(block)
                if line.lstrip().startswith('#'):
                    offset=len(line)-len(line.lstrip());edit.setPosition(block.position()+offset);edit.deleteChar()
                    if self.document().findBlockByNumber(number).text()[offset:offset+1]==' ':edit.deleteChar()
                else:edit.insertText('# ')
            cursor.endEditBlock();return
        if event.key()==Qt.Key.Key_Tab:
            self.textCursor().insertText('    ');return
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter}:
            line=self.textCursor().block().text();indent=line[:len(line)-len(line.lstrip())]
            if line.rstrip().endswith(':'):indent+='    '
            super().keyPressEvent(event);self.textCursor().insertText(indent);return
        if event.key()==Qt.Key.Key_Backtab:
            cursor=self.textCursor();cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            if cursor.block().text().startswith('    '):
                cursor.movePosition(QTextCursor.MoveOperation.Right,QTextCursor.MoveMode.KeepAnchor,4);cursor.removeSelectedText()
            return
        super().keyPressEvent(event)

    def mark_syntax_error(self,line=None,message=''):
        """Sublinha um diagnóstico estático sem alterar texto, foco ou possibilidade de salvar."""
        self._error_selections=[]
        if line:
            block=self.document().findBlockByNumber(line-1)
            if block.isValid():
                cursor=QTextCursor(block);cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                selection=QTextEdit.ExtraSelection();selection.cursor=cursor
                selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                from .theme import manager
                selection.format.setUnderlineColor(QColor(manager().tokens['error']));selection.format.setToolTip(message)
                self._error_selections=[selection]
        self.setExtraSelections(self._error_selections)

    @Slot(dict)
    def theme_changed(self,_tokens):
        """Repinta código e números; a conexão acompanha a vida do widget Qt."""
        font=QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        from .theme import manager
        font.setPointSizeF(max(8,font.pointSizeF())*manager().scale/100);self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ')*4)
        self._update_margin();self.highlighter.rehighlight();self.numbers.update()
