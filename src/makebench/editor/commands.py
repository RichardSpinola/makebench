"""Single QAction registry and keyboard-accessible command search."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout
from .theme import icon
from makebench.i18n import tr


class CommandPalette(QDialog):
    """List the same actions as the menus, including their states and shortcuts."""

    def __init__(self, actions, parent=None):
        """Receive existing actions, without duplicating implementation or shortcuts."""
        super().__init__(parent)
        self.setWindowTitle(tr("Command palette"))
        self.resize(620, 420)
        self.actions = list(actions)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Search commands…"))
        self.query.setAccessibleName(tr("Search commands"))
        self.items = QListWidget()
        layout.addWidget(self.query)
        layout.addWidget(self.items)
        self.query.textChanged.connect(self.filter)
        self.query.returnPressed.connect(self.invoke)
        self.items.itemActivated.connect(lambda _: self.invoke())
        self.filter("")

    def filter(self, query):
        """Filter without losing the action's identity or triggering disabled commands."""
        self.items.clear()
        for action in self.actions:
            label = action.text().replace("&", "")
            if action.isSeparator() or not label or query.casefold() not in label.casefold():
                continue
            item = QListWidgetItem(action.icon(), label + "    " + action.shortcut().toString())
            item.setData(Qt.ItemDataRole.UserRole, action)
            if not action.isEnabled():
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.items.addItem(item)
        self.items.setCurrentRow(0)

    def invoke(self):
        """Close the search before triggering the selected command."""
        item = self.items.currentItem()
        if item:
            action = item.data(Qt.ItemDataRole.UserRole)
            if action.isEnabled():
                self.accept()
                action.trigger()


def register(window):
    """Identify and decorate the window's real actions in a stable catalog."""
    actions = []
    candidates = []

    def visit(menu):
        """Collect only commands that belong to the workbench's current menus."""
        for action in menu.actions():
            if action.menu():
                visit(action.menu())
            else:
                candidates.append(action)

    visit(window.menuBar())
    candidates.extend(window.actions())
    from PySide6.QtWidgets import QToolBar

    for toolbar in window.findChildren(QToolBar):
        candidates.extend(toolbar.actions())
    for number, action in enumerate(candidates):
        if (
            action in actions
            or action.isSeparator()
            or not action.text()
            or action.menu() is not None
        ):
            continue
        if action in [
            bar.toggleViewAction()
            for bar in window.findChildren(
                __import__("PySide6.QtWidgets", fromlist=["QToolBar"]).QToolBar
            )
        ]:
            continue
        action.setObjectName(action.objectName() or f"command_{number}")
        if action.icon().isNull() or action.property("makebenchIcon"):
            name = next(
                (
                    key
                    for key, attr in [
                        ("new", "new_action"),
                        ("open", "open_action"),
                        ("save", "save_action"),
                        ("undo", "undo_action"),
                        ("redo", "redo_action"),
                        ("run", "run_action"),
                    ]
                    if getattr(window, attr, None) is action
                ),
                "document",
            )
            name = action.property("makebenchIcon") or name
            action.setProperty("makebenchIcon", name)
            action.setIcon(icon(name))
        action.setToolTip(
            action.text().replace("&", "")
            + (" · " + action.shortcut().toString() if not action.shortcut().isEmpty() else "")
        )
        actions.append(action)
    from PySide6.QtWidgets import QToolButton

    for button in window.findChildren(QToolButton):
        action = button.defaultAction()
        if action:
            button.setAccessibleName(action.text().replace("&", ""))
            button.setToolTip(action.toolTip())
    window.commands = actions
    return actions
