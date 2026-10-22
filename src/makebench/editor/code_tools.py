"""Ferramentas leves de edição: substituição literal e delimitadores sem execução."""
import io
import tokenize
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor,QTextDocument,QTextFormat
from PySide6.QtWidgets import QInputDialog,QTextEdit


class CodeTools:
    """Operações locais no documento, com histórico de texto e realce derivado."""
    def open_replace(self):
        """Abre substituição apenas no arquivo editável, preservando a seleção atual."""
        if self.isReadOnly():return
        self.replace_row.show();self.open_find()

    def replace_one(self):
        """Substitui uma ocorrência literal; texto de substituição nunca é interpretado."""
        if self.isReadOnly() or not self.find_text.text():return
        cursor=self.textCursor()
        if cursor.selectedText().casefold()!=self.find_text.text().casefold():self.find_next();cursor=self.textCursor()
        if cursor.hasSelection():cursor.insertText(self.replace_text.text());self.setTextCursor(cursor);self.find_next()

    def replace_all(self):
        """Confirma todas as ocorrências em um único passo de desfazer, sem laço em texto novo."""
        text=self.find_text.text()
        if self.isReadOnly() or not text:return
        matches=[];position=0
        while True:
            found=self.document().find(text,position)
            if found.isNull():break
            matches.append((found.selectionStart(),found.selectionEnd()));position=found.selectionEnd()
        cursor=self.textCursor();cursor.beginEditBlock()
        for start,end in reversed(matches):
            cursor.setPosition(start);cursor.setPosition(end,QTextCursor.MoveMode.KeepAnchor);cursor.insertText(self.replace_text.text())
        cursor.endEditBlock();self.find_status.setText(f'{len(matches)} substituição(ões)')

    def go_to_line(self):
        """Localiza uma linha válida sem alterar o documento."""
        line,ok=QInputDialog.getInt(self,'Ir para linha','Linha',self.textCursor().blockNumber()+1,1,self.blockCount())
        if ok:self.show_line(line);self.setFocus()

    def delimiters(self):
        """Tokeniza Python para ignorar delimitadores de strings/comentários, inclusive unicode."""
        text=self.toPlainText()
        if getattr(self,'_bracket_text',None)==text:return self._brackets
        self._bracket_text=text;self._brackets={}
        if len(text)>300000:return self._brackets
        lines=text.splitlines(keepends=True);offsets=[];offset=0
        for line in lines:offsets.append(offset);offset+=len(line.encode('utf-16-le'))//2
        stack=[];closing={')':'(',']':'[','}':'{'}
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type!=tokenize.OP or token.string not in '()[]{}':continue
                row,column=token.start;position=offsets[row-1]+len(lines[row-1][:column].encode('utf-16-le'))//2
                if token.string in '([{':stack.append((token.string,position))
                elif stack and stack[-1][0]==closing[token.string]:
                    _,start=stack.pop();self._brackets[start]=position;self._brackets[position]=start
        except (tokenize.TokenError,IndentationError,SyntaxError):pass
        return self._brackets

    def highlight_cursor(self):
        """Combina linha, diagnóstico e par de delimitadores sem apagar os outros realces."""
        if not hasattr(self,'_error_selections'):return
        selections=list(self._error_selections);cursor=self.textCursor()
        current=QTextEdit.ExtraSelection();current.cursor=QTextCursor(cursor);current.cursor.clearSelection();current.format.setBackground(self.palette().alternateBase());current.format.setProperty(QTextFormat.Property.FullWidthSelection,True);selections.append(current)
        pairs={} if getattr(self.highlighter,'language','python')=='plain' else self.delimiters();position=cursor.position();position=position if position in pairs else position-1
        if position in pairs:
            for index in (position,pairs[position]):
                selection=QTextEdit.ExtraSelection();selection.cursor=QTextCursor(self.document());selection.cursor.setPosition(index);selection.cursor.movePosition(QTextCursor.MoveOperation.Right,QTextCursor.MoveMode.KeepAnchor);selection.format.setBackground(self.palette().highlight());selection.format.setForeground(self.palette().highlightedText());selections.append(selection)
        self.setExtraSelections(selections)

    def contextMenuEvent(self,event):
        """O código gerado oferece navegação explícita à origem em blocos."""
        menu=self.createStandardContextMenu()
        if self.isReadOnly() and getattr(self,'origin_enabled',True):
            menu.addSeparator();menu.addAction('Ir ao bloco de origem · F4',lambda:self.origin_requested.emit(self.textCursor().blockNumber()+1))
        elif not self.isReadOnly():menu.addSeparator();menu.addAction('Substituir… · Ctrl+H',self.open_replace)
        menu.addAction('Ir para linha… · Ctrl+G',self.go_to_line);menu.exec(event.globalPos())

    def indent_selection(self,reverse=False):
        """Recua linhas selecionadas sem substituir seu texto, com um único undo."""
        cursor=self.textCursor();start=cursor.selectionStart();end=cursor.selectionEnd()
        if cursor.hasSelection() and self.document().findBlock(end).position()==end:end-=1
        first=self.document().findBlock(start).blockNumber();last=self.document().findBlock(end).blockNumber();cursor.beginEditBlock()
        for number in range(last,first-1,-1):
            block=self.document().findBlockByNumber(number);edit=QTextCursor(block)
            if reverse:
                count=min(4,len(block.text())-len(block.text().lstrip(' ')))
                edit.movePosition(QTextCursor.MoveOperation.Right,QTextCursor.MoveMode.KeepAnchor,count);edit.removeSelectedText()
            else:edit.insertText('    ')
        cursor.endEditBlock()
