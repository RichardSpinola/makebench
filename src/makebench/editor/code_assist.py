"""Sugestões explícitas e navegação estática nos editores Python próprios."""

import re
from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QFrame


class CodeAssist(QObject):
    """Adapta o índice do projeto ao editor sem avaliação nem servidor de linguagem."""

    def __init__(self, window, editor, filename):
        """Instala controles locais, mantendo geração e scripts fora das sugestões."""
        super().__init__(editor)
        self.window = window
        self.editor = editor
        self.filename = filename
        self.popup = QListWidget(editor.viewport())
        self.popup.setAccessibleName("Sugestões de código")
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setFrameShape(QFrame.Shape.Box)
        self.popup.hide()
        self.popup.itemClicked.connect(lambda item: self.accept(item.text()))
        self.prefix = ""
        editor.installEventFilter(self)
        editor.setToolTip(
            "Ctrl+Espaço: sugestões · Ctrl+Shift+Espaço: parâmetros · F12: definição local"
        )
        editor.cursorPositionChanged.connect(self.parameters)

    def before(self):
        """Converte posição UTF-16 do Qt para texto Python sem cortar caracteres Unicode."""
        cursor = self.editor.textCursor()
        cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText().replace("\u2029", "\n")

    def complete(self):
        """Abre sugestões por Ctrl+Espaço, incluindo componentes em chamadas ctx."""
        self.window.refresh_code_index()
        before = self.before()
        match = re.search(r"[\w.]+$", before)
        self.prefix = match.group() if match else ""
        component = re.search(
            r"ctx\.(?:read|set_text|set_enabled|set_value|show_page|terminal_start|terminal_send|terminal_stop)\(\s*(['\"])([^'\"]*)$",
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
            items = [
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
            self.window.statusBar().showMessage("Nenhuma sugestão estática neste contexto.", 3000)

    def accept(self, text):
        """Confirma uma sugestão sem abrir outra janela nativa ou perder foco."""
        self.insert(text)
        self.popup.hide()
        self.editor.setFocus()

    def insert(self, text):
        """Substitui somente o prefixo, como uma única edição reversível."""
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        for _ in range(len(self.prefix.encode("utf-16-le")) // 2):
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(getattr(self, "inserts", {}).get(text, text))
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def definition(self):
        """F12 abre uma definição local conhecida, sem executar seu módulo."""
        self.window.refresh_code_index()
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        before = self.before()
        match = re.search(r"[\w.]+$", before)
        token = match.group() if match else cursor.selectedText()
        # Inclui o restante da palavra se o cursor estiver no meio dela.
        line = self.editor.textCursor().block().text()
        position = self.editor.textCursor().positionInBlock()
        suffix = re.match(r"\w*", line.encode("utf-16-le")[position * 2 :].decode("utf-16-le"))
        if suffix and token and not token.endswith(suffix.group()):
            token += suffix.group()
        target = self.window.code_index.resolve(self.filename, token)
        if target and target.file:
            self.window.open_code_file(target.file, target.line, target.column)
        else:
            self.window.statusBar().showMessage("Definição local não encontrada.", 3000)

    def parameters(self):
        """Apresenta assinatura contextual discretamente no rodapé da área Código."""
        if not self.editor.hasFocus():
            return
        signature = self.window.code_index.call_signature(self.filename, self.before())
        self.window.code_signature.setText(signature)
        self.window.code_signature.setToolTip(signature)

    def eventFilter(self, watched, event):
        """Controla a lista filha do editor, sem grabs nativos que causem piscadas no Wayland."""
        controls = (
            bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if event.type() in {QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride}
            else False
        )
        assisted = event.type() in {QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride} and (
            event.key() == Qt.Key.Key_F12 or controls and event.key() == Qt.Key.Key_Space
        )
        if assisted:
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            if event.key() == Qt.Key.Key_F12:
                self.definition()
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
