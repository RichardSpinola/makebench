# SPDX-License-Identifier: MIT
"""The Qt table component: rows live in a model, so only the visible cells are drawn.

A table with tens of thousands of rows fills in milliseconds; a widget with one item per
cell took about a second and a hundred megabytes for fifty thousand rows.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTableView


class RowsModel(QAbstractTableModel):
    """Rows of texts, each with an optional hidden record id."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = []
        self.rows = []
        self.records = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            row = self.rows[index.row()]
            return row[index.column()] if index.column() < len(row) else ""
        if role == Qt.ItemDataRole.UserRole and index.column() == 0:
            return self.records[index.row()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and section < len(self.headers)
        ):
            return self.headers[section]
        return None

    def set_headers(self, headers):
        self.beginResetModel()
        self.headers = [str(header) for header in headers]
        self.endResetModel()

    def set_rows(self, rows, ids=None):
        self.beginResetModel()
        self.rows = [[str(cell) for cell in row] for row in rows]
        self.records = list(ids) if ids else [None] * len(self.rows)
        self.endResetModel()

    def append(self, row, record=None):
        index = len(self.rows)
        self.beginInsertRows(QModelIndex(), index, index)
        self.rows.append([str(cell) for cell in row])
        self.records.append(record)
        self.endInsertRows()


class RecordTable(QTableView):
    """Read-only table with whole-row single selection.

    `itemSelectionChanged` is emitted by the view itself (not by its selection model), so
    `blockSignals` on the table still hides changes the application made."""

    itemSelectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows_model = RowsModel(self)
        self.setModel(self.rows_model)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        # Fixed row heights let the view skip measuring every row.
        self.verticalHeader().setSectionResizeMode(self.verticalHeader().ResizeMode.Fixed)
        self.selectionModel().selectionChanged.connect(lambda *_: self.itemSelectionChanged.emit())

    def rowCount(self):
        return self.rows_model.rowCount()

    def columnCount(self):
        return self.rows_model.columnCount()

    def selected_row(self):
        """Index of the selected row, or -1."""
        rows = self.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def text(self, row, column):
        cells = self.rows_model.rows[row]
        return cells[column] if column < len(cells) else ""
