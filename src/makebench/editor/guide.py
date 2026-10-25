"""Getting-started guide and keyboard reference, both reachable from the Help menu."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from makebench.i18n import tr

GUIDE_SEEN = "v1/help/guide_seen"


def guide_steps():
    """The four areas in the order a new application is usually built."""
    return [
        (
            "map",
            tr("1 · Map"),
            tr(
                "See every window and state of your application and how they connect. Create windows here and drag a port to link them."
            ),
        ),
        (
            "design",
            tr("2 · Design"),
            tr(
                "Build each window with native Qt or GTK controls. Drag components from Insert, then adjust them in Properties."
            ),
        ),
        (
            "logic",
            tr("3 · Logic"),
            tr(
                "Say what happens on start or on a click, with blocks or nodes. The generated Python is always visible."
            ),
        ),
        (
            "code",
            tr("4 · Code"),
            tr(
                "Write your own Python functions and call them from blocks. Press F5 to test the application and F9 to debug it."
            ),
        ),
    ]


class GettingStarted(QDialog):
    """Short, dismissible guide; each step opens its area of the workbench."""

    def __init__(self, window):
        """Build the steps and remember whether the guide should open on its own again."""
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Getting started"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        intro = QLabel(
            tr(
                "Makebench builds Linux applications in four areas. Nothing in your project runs until you press F5."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for mode, title, text in guide_steps():
            row = QHBoxLayout()
            label = QLabel(f"<b>{title}</b><br>{text}")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(label, 1)
            button = QPushButton(tr("Open"))
            button.setAccessibleName(tr("Open {area}").format(area=title))
            button.clicked.connect(lambda _, mode=mode: self.open_area(mode))
            row.addWidget(button)
            layout.addLayout(row)
        self.again = QCheckBox(tr("Show this guide when I open a project"))
        self.again.setChecked(not window.settings.value(GUIDE_SEEN, False, type=bool))
        self.again.toggled.connect(
            lambda checked: window.settings.setValue(GUIDE_SEEN, not checked)
        )
        layout.addWidget(self.again)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def open_area(self, mode):
        """Switch the workbench to the chosen area and close the guide."""
        self.window.set_mode(mode)
        self.accept()


def show_guide(window, automatic=False):
    """Open the guide; automatic openings happen once, until the user asks again."""
    if automatic and window.settings.value(GUIDE_SEEN, False, type=bool):
        return None
    window.settings.setValue(GUIDE_SEEN, True)
    dialog = GettingStarted(window)
    dialog.setModal(False)
    dialog.show()
    window.guide_dialog = dialog
    return dialog


class ShortcutReference(QDialog):
    """Searchable list of every action that has a keyboard shortcut."""

    def __init__(self, window):
        """Read the real QActions, so the list never drifts from the menus."""
        super().__init__(window)
        self.setWindowTitle(tr("Keyboard shortcuts"))
        self.resize(520, 560)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search shortcuts…"))
        self.search.setAccessibleName(tr("Search shortcuts"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        rows = {}
        for action in window.findChildren(QAction):
            keys = ", ".join(s.toString() for s in action.shortcuts() if not s.isEmpty())
            name = action.text().replace("&", "").strip()
            if keys and name:
                rows[name] = keys
        self.table = QTableWidget(len(rows), 2)
        self.table.setHorizontalHeaderLabels([tr("Command"), tr("Shortcut")])
        self.table.setAccessibleName(tr("Keyboard shortcuts"))
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (name, keys) in enumerate(
            sorted(rows.items(), key=lambda item: item[0].casefold())
        ):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(keys))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self.filter)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def filter(self, text):
        """Hide rows whose command or keys do not contain the search text."""
        query = text.casefold()
        for row in range(self.table.rowCount()):
            values = " ".join(self.table.item(row, column).text() for column in (0, 1))
            self.table.setRowHidden(row, query not in values.casefold())
