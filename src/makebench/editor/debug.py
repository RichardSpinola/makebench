"""Controles de depuração e inspeção somente leitura do snapshot iniciado."""

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DebugPanel(QWidget):
    """Mostra contexto, pilha e valores sem console de avaliação arbitrária."""

    command = Signal(str)
    locate = Signal(dict)

    def __init__(self, parent=None):
        """Monta comandos que enviam mensagens ao worker, sem executar Python local."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.buttons = {}
        for label, action, shortcut in [
            ("Continuar", "continue", "F8"),
            ("Pausar", "pause", ""),
            ("Próximo", "step_over", "F10"),
            ("Entrar", "step_in", "F11"),
            ("Sair", "step_out", "Shift+F11"),
            ("Parar", "stop", "Shift+F5"),
        ]:
            button = QPushButton(label)
            button.setToolTip(label + (" · " + shortcut if shortcut else ""))
            button.clicked.connect(lambda _, action=action: self.command.emit(action))
            row.addWidget(button)
            self.buttons[action] = button
        row.addStretch()
        layout.addLayout(row)
        self.status = QLabel(
            "F6 inicia a depuração. Clique na margem do código ou use o menu de um bloco para marcar uma parada."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter()
        self.stack = QTreeWidget()
        self.stack.setHeaderLabels(["Pilha", "Arquivo", "Linha"])
        self.values = QTreeWidget()
        self.values.setHeaderLabels(["Variável", "Valor"])
        split.addWidget(self.stack)
        split.addWidget(self.values)
        layout.addWidget(split, 1)
        self.stack.itemActivated.connect(
            lambda item, _: self.locate.emit(item.data(0, Qt.ItemDataRole.UserRole))
        )
        self.changed({"state": "stopped"})

    def changed(self, message):
        """Apresenta cópia JSON limitada enviada pelo depurador do projeto."""
        state = message.get("state", "stopped")
        paused = state == "paused"
        for action, button in self.buttons.items():
            button.setEnabled(
                paused
                if action in {"continue", "step_over", "step_in", "step_out"}
                else state in {"running", "paused"}
            )
        if state == "stopped":
            self.status.setText("Depurador parado · F6 para iniciar")
            return
        if not paused:
            self.status.setText("Depuração em execução")
            return
        self.status.setText(
            "Pausado · "
            + str(message.get("component_label") or message.get("component") or "")
            + " · "
            + str(message.get("flow_label") or message.get("flow") or "")
            + " · "
            + message.get("reason", "")
        )
        self.stack.clear()
        self.values.clear()
        for frame in message.get("stack", []):
            item = QTreeWidgetItem(
                [
                    frame["name"],
                    frame.get("source_file", "gerado.py"),
                    str(frame.get("source_line") or frame.get("line") or ""),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, frame)
            self.stack.addTopLevelItem(item)
        values = [
            ("Projeto", message.get("variables", {})),
            ("Janela", message.get("window_variables", {})),
        ]
        for index, frame in enumerate(message.get("stack", [])):
            values.append((frame["name"] + f" [{index}]", frame.get("variables", {})))

        def add(parent, name, value):
            """Expande somente dados serializados, sem acessar objetos do processo remoto."""
            compound = isinstance(value, (dict, list))
            item = QTreeWidgetItem(
                [str(name), "" if compound else json.dumps(value, ensure_ascii=False)]
            )
            (parent.addChild if parent else self.values.addTopLevelItem)(item)
            if compound:
                for key, child in value.items() if isinstance(value, dict) else enumerate(value):
                    add(item, key, child)
            return item

        for name, value in values:
            add(None, name, value).setExpanded(True)
