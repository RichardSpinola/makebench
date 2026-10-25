"""Search across every Python file of the project, using the in-memory buffers only."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from makebench.core.source import ENTRY_FILE, source_files
from makebench.i18n import ntr, tr

MAX_RESULTS = 500


def search_sources(source, query, case_sensitive=False):
    """Return [(file, line, column, text)] for every occurrence of a literal query.

    `source` is the SourceText snapshot of the project (entry file and modules).
    Nothing is read from disk and nothing is imported or run.
    """
    if not query:
        return []
    needle = query if case_sensitive else query.casefold()
    results = []
    for name, text in source_files(source).items():
        for number, line in enumerate(str(text).splitlines(), 1):
            haystack = line if case_sensitive else line.casefold()
            start = haystack.find(needle)
            while start >= 0:
                results.append((name, number, start + 1, line.strip()))
                if len(results) >= MAX_RESULTS:
                    return results
                start = haystack.find(needle, start + max(1, len(needle)))
    return results


class ProjectSearchPanel(QWidget):
    """Drawer tab: a query field, a case option and navigable results."""

    def __init__(self, window):
        """Build the controls; searching waits briefly after typing stops."""
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Search in every Python file of the project…"))
        self.query.setAccessibleName(tr("Search in project"))
        self.query.setClearButtonEnabled(True)
        row.addWidget(self.query, 1)
        self.case = QCheckBox(tr("Match case"))
        row.addWidget(self.case)
        layout.addLayout(row)
        self.summary = QLabel(tr("Type to search your own functions and modules."))
        layout.addWidget(self.summary)
        self.results = QListWidget()
        self.results.setAccessibleName(tr("Search results"))
        layout.addWidget(self.results, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.run)
        self.query.textChanged.connect(lambda _: self.timer.start())
        self.case.toggled.connect(lambda _: self.run())
        self.query.returnPressed.connect(self.open_first)
        self.results.itemActivated.connect(self.open_item)

    def run(self):
        """Search the current buffers and list one row per occurrence."""
        query = self.query.text()
        found = search_sources(self.window.source.text, query, self.case.isChecked())
        self.results.clear()
        for name, line, column, text in found:
            label = self._file_label(name)
            item = QListWidgetItem(f"{label}:{line}  {text[:160]}")
            item.setData(Qt.ItemDataRole.UserRole, (name, line, column))
            self.results.addItem(item)
        if not query:
            self.summary.setText(tr("Type to search your own functions and modules."))
        elif not found:
            self.summary.setText(tr("No results for “{query}”.").format(query=query))
        else:
            self.summary.setText(
                ntr("{count} result", "{count} results", len(found)).format(count=len(found))
            )

    def _file_label(self, name):
        """Readable name of a project file, matching the Code tabs."""
        if name == ENTRY_FILE:
            path = self.window.source.path
            return path.name if path else "project.actions.py"
        return name

    def open_item(self, item):
        """Open the file at the matching line in the Code area."""
        name, line, column = item.data(Qt.ItemDataRole.UserRole)
        self.window.open_code_file(name, line, column)

    def open_first(self):
        """Enter in the query jumps to the first result."""
        if self.results.count():
            self.results.setCurrentRow(0)
            self.open_item(self.results.item(0))


def install_project_search(window):
    """Add the drawer tab and the Ctrl+Shift+F command to the workbench."""
    window.project_search = ProjectSearchPanel(window)
    window.drawer.addTab(window.project_search, tr("Search"))
    action = QAction(tr("Search in project…"), window)
    action.setShortcut(QKeySequence("Ctrl+Shift+F"))

    def show():
        """Reveal the drawer on the search tab and focus the query."""
        window.drawer.show()
        window.drawer.setCurrentWidget(window.project_search)
        window.project_search.query.setFocus()
        window.project_search.query.selectAll()
        window.project_search.run()

    action.triggered.connect(show)
    window.addAction(action)
    window.project_search_action = action
    return action
