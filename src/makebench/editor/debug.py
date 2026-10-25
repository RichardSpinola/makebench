"""Debug controls and read-only inspection of the started snapshot."""

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
from makebench.i18n import tr


class DebugPanel(QWidget):
    """Show context, stack and values with no arbitrary evaluation console."""

    command = Signal(str)
    locate = Signal(dict)

    def __init__(self, parent=None):
        """Build commands that send messages to the worker, never running Python locally."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.buttons = {}
        for label, action, shortcut in [
            (tr("Continue"), "continue", "F8"),
            (tr("Pause"), "pause", ""),
            (tr("Step over"), "step_over", "F10"),
            (tr("Step into"), "step_in", "F11"),
            (tr("Step out"), "step_out", "Shift+F11"),
            (tr("Stop"), "stop", "Shift+F5"),
        ]:
            button = QPushButton(label)
            button.setToolTip(label + (" · " + shortcut if shortcut else ""))
            button.clicked.connect(lambda _, action=action: self.command.emit(action))
            row.addWidget(button)
            self.buttons[action] = button
        row.addStretch()
        layout.addLayout(row)
        self.status = QLabel(
            tr(
                "F9 starts debugging. Click the code margin or use a block's menu to set a breakpoint."
            )
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter()
        self.stack = QTreeWidget()
        self.stack.setHeaderLabels([tr("Stack"), tr("File"), tr("Line")])
        self.values = QTreeWidget()
        self.values.setHeaderLabels([tr("Variable"), tr("Value")])
        split.addWidget(self.stack)
        split.addWidget(self.values)
        layout.addWidget(split, 1)
        self.stack.itemActivated.connect(
            lambda item, _: self.locate.emit(item.data(0, Qt.ItemDataRole.UserRole))
        )
        self.changed({"state": "stopped"})

    def changed(self, message):
        """Show the bounded JSON copy sent by the project's debugger."""
        state = message.get("state", "stopped")
        paused = state == "paused"
        for action, button in self.buttons.items():
            button.setEnabled(
                paused
                if action in {"continue", "step_over", "step_in", "step_out"}
                else state in {"running", "paused"}
            )
        if state == "stopped":
            self.status.setText(tr("Debugger stopped · F9 to start"))
            return
        if not paused:
            self.status.setText(tr("Debugging running"))
            return
        self.status.setText(
            tr("Paused")
            + " · "
            + str(message.get("component_label") or message.get("component") or "")
            + " · "
            + str(message.get("flow_label") or message.get("flow") or "")
            + " · "
            + {
                "breakpoint": tr("breakpoint"),
                "step": tr("step"),
                "entry": tr("entry"),
                "pause": tr("pause"),
            }.get(message.get("reason", ""), message.get("reason", ""))
        )
        self.stack.clear()
        self.values.clear()
        for frame in message.get("stack", []):
            item = QTreeWidgetItem(
                [
                    frame["name"],
                    frame.get("source_file", "generated.py"),
                    str(frame.get("source_line") or frame.get("line") or ""),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, frame)
            self.stack.addTopLevelItem(item)
        values = [
            (tr("Project"), message.get("variables", {})),
            (tr("Window"), message.get("window_variables", {})),
        ]
        for index, frame in enumerate(message.get("stack", [])):
            values.append((frame["name"] + f" [{index}]", frame.get("variables", {})))

        def add(parent, name, value):
            """Expand only serialized data, never touching objects of the remote process."""
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
