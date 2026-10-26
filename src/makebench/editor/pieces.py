# SPDX-License-Identifier: GPL-3.0-or-later
"""Menu and dialogs for reusable pieces: save a subtree once, insert copies anywhere."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from makebench.core import pieces
from makebench.core.project import ProjectError
from makebench.i18n import tr

from .errors import show_error


def save_selection_as_piece(window) -> None:
    """Ask for a name and store the selected component as a piece."""
    node = window.project.find(window.selected_id)
    default = node.properties.get("title") or node.properties.get("text") or ""
    name, ok = QInputDialog.getText(
        window, tr("Save as reusable piece"), tr("Name of the piece"), text=str(default)[:40]
    )
    if not ok:
        return
    try:
        piece = pieces.make_piece(window.project, window.selected_id, name, window.assets)
        pieces.save_piece(piece)
    except (ProjectError, OSError) as exc:
        show_error(window, exc, tr("Could not save the piece"))
        return
    window.statusBar().showMessage(tr("Piece saved: {name}").format(name=piece["name"]), 5000)
    rebuild_menu(window)


def insert(window, piece: dict) -> None:
    """Insert a copy of the piece under the selection as one undoable change."""
    created = []

    def change():
        created.append(
            pieces.insert_piece(window.project, window.selected_id, piece, window.assets)
        )

    try:
        window._edit(change, label=tr("Insert piece"))
    except ProjectError as exc:
        show_error(window, exc, tr("Could not insert the piece"))
        return
    if created and window.project.find(created[0].id):
        window._select(created[0].id)


def import_piece(window) -> None:
    """Copy a piece file shared by someone into the library."""
    filename, _ = QFileDialog.getOpenFileName(
        window, tr("Import a piece"), "", tr("Makebench pieces (*.json)")
    )
    if not filename:
        return
    try:
        pieces.save_piece(pieces.read_piece(Path(filename)))
    except (ProjectError, OSError) as exc:
        show_error(window, exc, tr("Could not import the piece"))
        return
    rebuild_menu(window)


class PiecesDialog(QDialog):
    """Rename-free manager: insert, export or delete the saved pieces."""

    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self.setWindowTitle(tr("My pieces"))
        self.resize(420, 380)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                tr(
                    "Pieces are copies: changing a piece does not change copies you already inserted."
                )
            )
        )
        self.list = QListWidget()
        layout.addWidget(self.list)
        for text, slot in (
            (tr("Insert in the selected container"), self._insert),
            (tr("Export…"), self._export),
            (tr("Delete…"), self._delete),
            (tr("Import…"), self._import),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            layout.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fill()

    def _fill(self):
        self.list.clear()
        for name, path in pieces.list_pieces():
            item = QListWidgetItem(name)
            item.setData(256, str(path))
            self.list.addItem(item)

    def _current(self):
        item = self.list.currentItem()
        return Path(item.data(256)) if item else None

    def _insert(self):
        path = self._current()
        if path:
            insert(self.window_ref, pieces.read_piece(path))

    def _export(self):
        path = self._current()
        if not path:
            return
        target, _ = QFileDialog.getSaveFileName(self, tr("Export a piece"), path.name)
        if target:
            Path(target).write_bytes(path.read_bytes())

    def _delete(self):
        path = self._current()
        if path and (
            QMessageBox.question(self, tr("Delete piece"), tr("Delete this piece?"))
            == QMessageBox.StandardButton.Yes
        ):
            pieces.delete_piece(path)
            self._fill()
            rebuild_menu(self.window_ref)

    def _import(self):
        import_piece(self.window_ref)
        self._fill()


def rebuild_menu(window) -> None:
    """Refresh the Insert piece submenu: built-in pieces first, then the person's own."""
    menu = window.pieces_menu
    menu.clear()
    for piece in pieces.builtin_pieces():
        menu.addAction(piece["name"], lambda p=piece: insert(window, p))
    saved = pieces.list_pieces()
    if saved:
        menu.addSeparator()
    for name, path in saved:
        menu.addAction(name, lambda p=path: insert(window, pieces.read_piece(p)))
    menu.addSeparator()
    menu.addAction(tr("Manage pieces…"), lambda: PiecesDialog(window).exec())


def install_pieces(window, edit_menu) -> None:
    """Add Edit › Insert piece ▸ and Save as piece… to the window."""
    save = QAction(tr("Save as reusable piece…"), window)
    save.triggered.connect(lambda: save_selection_as_piece(window))
    window.pieces_menu = edit_menu.addMenu(tr("Insert piece"))
    edit_menu.addAction(save)
    window.save_piece_action = save
    rebuild_menu(window)
