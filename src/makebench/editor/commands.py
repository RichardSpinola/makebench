# SPDX-License-Identifier: GPL-3.0-or-later
"""Single QAction registry and keyboard-accessible command search."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)

from makebench.i18n import tr

from .theme import icon

SHORTCUT_ROLE = Qt.ItemDataRole.UserRole + 1


class _ShortcutDelegate(QStyledItemDelegate):
    """Draw the command name on the left and its shortcut, dimmed, on the right."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        shortcut = index.data(SHORTCUT_ROLE)
        if not shortcut:
            return
        selected = option.state & QStyle.StateFlag.State_Selected
        role = (
            QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.PlaceholderText
        )
        painter.save()
        painter.setPen(option.palette.color(role))
        rect = option.rect.adjusted(0, 0, -10, 0)
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, shortcut
        )
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), option.fontMetrics.height() + 12))
        return size


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
        self.items.setItemDelegate(_ShortcutDelegate(self.items))
        self.items.setUniformItemSizes(True)
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
            item = QListWidgetItem(action.icon(), label)
            item.setData(Qt.ItemDataRole.UserRole, action)
            shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            item.setData(SHORTCUT_ROLE, shortcut)
            item.setToolTip(label + (" · " + shortcut if shortcut else ""))
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


def tidy_menus(window):
    """Put the menus in the usual Linux order and keep Quit last in File."""
    bar = window.menuBar()
    order = [
        tr("&File"),
        tr("&Edit"),
        tr("&View"),
        tr("&Project"),
        tr("&Run"),
        tr("&Plugins"),
        tr("&Help"),
    ]
    order = [name.replace("&", "") for name in order]
    menus = {action.text().replace("&", ""): action for action in bar.actions() if action.menu()}
    known = [menus[name] for name in order if name in menus]
    rest = [action for action in bar.actions() if action not in known]
    for action in known + rest:
        bar.removeAction(action)
        bar.addAction(action)
    file_menu = menus.get(order[0])
    if file_menu is None:
        return
    menu = file_menu.menu()
    entries = [action for action in menu.actions() if not action.isSeparator()]
    first = [
        getattr(window, name, None) for name in ("new_action", "open_action", "example_action")
    ]
    saving = [window.save_action] + [a for a in entries if a.text() == tr("Save as…")]
    quitting = [a for a in entries if a.text() == tr("Quit")]
    groups = [
        [a for a in first if a in entries],
        [a for a in saving if a in entries],
        [a for a in entries if a not in first + saving + quitting],
        quitting,
    ]
    # removeAction keeps actions the menu owns alive; clear() would delete them.
    for action in menu.actions():
        menu.removeAction(action)
    for group in filter(None, groups):
        if menu.actions():
            menu.addSeparator()
        menu.addActions(group)


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
                None,
            )
            # A generic icon on every row is noise; only real symbols are shown.
            name = action.property("makebenchIcon") or name
            if name:
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
