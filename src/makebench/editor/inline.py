"""Edição de texto sobre o componente, com confirmação e cancelamento explícitos."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QLineEdit,QPlainTextEdit


class InlineText(QLineEdit):
    """Campo de uma linha; a composição permanece intacta até confirmar."""
    finished=Signal(str,bool)
    def __init__(self,text,parent):
        """Guarda uma sessão para não confirmar duas vezes ao perder o foco."""
        super().__init__(text,parent);self.done=False;self.selectAll()

    def finish(self,accept):
        """Conclui antes de emitir, impedindo reentrada na saída de foco."""
        if self.done:return
        self.done=True;self.finished.emit(self.text(),accept)

    def keyPressEvent(self,event):
        """Enter confirma; Escape cancela e mantém o texto anterior."""
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter}:self.finish(True)
        elif event.key()==Qt.Key.Key_Escape:self.finish(False)
        else:super().keyPressEvent(event)

    def focusOutEvent(self,event):
        """Confirma ao mudar de controle, sem destruir o campo durante o evento."""
        self.finish(True);super().focusOutEvent(event)


class InlineParagraph(QPlainTextEdit):
    """Texto multilinha; Ctrl+Enter confirma e Escape cancela."""
    finished=Signal(str,bool)
    def __init__(self,text,parent):
        """Mantém conteúdo de várias linhas como texto, sem qualquer avaliação."""
        super().__init__(text,parent);self.done=False;self.selectAll()

    def finish(self,accept):
        """Finaliza uma única edição para o histórico do documento."""
        if self.done:return
        self.done=True;self.finished.emit(self.toPlainText(),accept)

    def keyPressEvent(self,event):
        """Mantém Enter como nova linha, com confirmação explícita por Ctrl+Enter."""
        if event.key()==Qt.Key.Key_Escape:self.finish(False)
        elif event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ControlModifier:self.finish(True)
        else:super().keyPressEvent(event)

    def focusOutEvent(self,event):
        """Confirma o texto atual quando a pessoa muda de controle."""
        self.finish(True);super().focusOutEvent(event)
