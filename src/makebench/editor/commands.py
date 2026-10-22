"""Registro único de QAction e pesquisa de comandos acessível por teclado."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout
from .theme import icon


class CommandPalette(QDialog):
    """Lista as mesmas ações dos menus, incluindo seus estados e atalhos."""
    def __init__(self, actions, parent=None):
        """Recebe ações existentes, sem duplicar implementação ou atalhos."""
        super().__init__(parent)
        self.setWindowTitle('Paleta de comandos');self.resize(620,420)
        self.actions = list(actions)
        layout=QVBoxLayout(self)
        self.query=QLineEdit();self.query.setPlaceholderText('Buscar comando…');self.query.setAccessibleName('Buscar comando')
        self.items=QListWidget();layout.addWidget(self.query);layout.addWidget(self.items)
        self.query.textChanged.connect(self.filter)
        self.query.returnPressed.connect(self.invoke)
        self.items.itemActivated.connect(lambda _:self.invoke())
        self.filter('')

    def filter(self, query):
        """Filtra sem perder a identidade da ação nem ativar comandos desabilitados."""
        self.items.clear()
        for action in self.actions:
            label=action.text().replace('&','')
            if action.isSeparator() or not label or query.casefold() not in label.casefold():continue
            item=QListWidgetItem(action.icon(),label+'    '+action.shortcut().toString())
            item.setData(Qt.ItemDataRole.UserRole,action)
            if not action.isEnabled():item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.items.addItem(item)
        self.items.setCurrentRow(0)

    def invoke(self):
        """Fecha a pesquisa antes de acionar o comando selecionado."""
        item=self.items.currentItem()
        if item:
            action=item.data(Qt.ItemDataRole.UserRole)
            if action.isEnabled():self.accept();action.trigger()


def register(window):
    """Identifica e adorna as ações reais da janela, em um catálogo estável."""
    actions=[];candidates=[]
    def visit(menu):
        """Coleta só comandos pertencentes aos menus atuais da bancada."""
        for action in menu.actions():
            if action.menu():visit(action.menu())
            else:candidates.append(action)
    visit(window.menuBar());candidates.extend(window.actions())
    from PySide6.QtWidgets import QToolBar
    for toolbar in window.findChildren(QToolBar):candidates.extend(toolbar.actions())
    for number,action in enumerate(candidates):
        if action in actions or action.isSeparator() or not action.text() or action.menu() is not None:continue
        if action in [bar.toggleViewAction() for bar in window.findChildren(__import__('PySide6.QtWidgets',fromlist=['QToolBar']).QToolBar)]:continue
        action.setObjectName(action.objectName() or f'command_{number}')
        if action.icon().isNull() or action.property('makebenchIcon'):
            name=next((key for key,attr in [('new','new_action'),('open','open_action'),('save','save_action'),('undo','undo_action'),('redo','redo_action'),('run','run_action')] if getattr(window,attr,None) is action),'document')
            name=action.property('makebenchIcon') or name
            action.setProperty('makebenchIcon',name);action.setIcon(icon(name))
        action.setToolTip(action.text().replace('&','')+(' · '+action.shortcut().toString() if not action.shortcut().isEmpty() else ''))
        actions.append(action)
    from PySide6.QtWidgets import QToolButton
    for button in window.findChildren(QToolButton):
        action=button.defaultAction()
        if action:
            button.setAccessibleName(action.text().replace('&',''));button.setToolTip(action.toolTip())
    window.commands=actions
    return actions
