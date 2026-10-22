"""Controles nativos para dependências e ícones, sem instalar nem importar pacotes."""
import importlib.metadata
import re
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QPushButton,QInputDialog,QLabel


class Dependencies(QWidget):
    """Lista requisitos declarados e versões disponíveis no Python do editor."""
    changed=Signal(list)
    def __init__(self,packages,parent=None):
        """O diagnóstico consulta metadados; importar o módulo de um pacote é proibido aqui."""
        super().__init__(parent);self.packages=list(packages);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.items=QListWidget();self.items.setAccessibleName('Requisitos Python do aplicativo');self.items.setMaximumHeight(210);self.items.itemActivated.connect(lambda _:self.edit());layout.addWidget(self.items)
        row=QHBoxLayout()
        for label,callback in [('Adicionar…',lambda:self.edit(new=True)),('Editar…',self.edit),('Remover',self.remove)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();layout.addLayout(row);hint=QLabel('Disponibilidade neste Python. A construção Flatpak usa seu próprio SDK e cache.');hint.setWordWrap(True);layout.addWidget(hint);self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice);self.refresh()

    def refresh(self):
        """Atualiza apenas a lista de requisitos, preservando a declaração original."""
        self.items.clear()
        for package in self.packages:
            name=re.split(r'[\[<>=!~]',package,1)[0]
            try:status='instalado: '+importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:status='ausente neste Python'
            self.items.addItem(package+' · '+status)

    def edit(self,_checked=False,new=False):
        """Valida um requisito sem enviá-lo ao shell ou ao gerenciador de pacotes."""
        index=self.items.currentRow()
        if index<0 and not new:return
        text,ok=QInputDialog.getText(self,'Dependência Python','Requisito, por exemplo requests>=2.32',text='' if new else self.packages[index])
        if not ok or not text.strip():return
        text=text.strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!_-]+(?:,[<>=!~]=?[A-Za-z0-9.*+!_-]+)*)?',text):self.notice.setText('Requisito inválido. Use nome e versão, por exemplo requests>=2.32.');return
        self.notice.clear()
        if new:self.packages.append(text)
        else:self.packages[index]=text
        self.changed.emit(list(self.packages));self.refresh()

    def remove(self):
        """Remove a declaração selecionada, sem desinstalar nada do computador."""
        index=self.items.currentRow()
        if index>=0:self.packages.pop(index);self.changed.emit(list(self.packages));self.refresh()
