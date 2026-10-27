# SPDX-License-Identifier: GPL-3.0-or-later
"""Native component dragging and tree reordering, without moving Qt data."""

from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import QMimeData, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QTreeWidget,
)

from makebench.core.project import KIND_LABELS, ComponentKind, Project
from makebench.i18n import tr

MIME_TYPE = "application/x-makebench-component"


def mime_for(payload: dict) -> QMimeData:
    """Encode only insert/move descriptions, never files or code."""
    data = QMimeData()
    data.setData(MIME_TYPE, json.dumps(payload).encode("utf-8"))
    return data


def read_payload(mime: QMimeData) -> dict | None:
    """Reject external formats and incomplete drag descriptions."""
    if not mime.hasFormat(MIME_TYPE):
        return None
    try:
        value = json.loads(bytes(mime.data(MIME_TYPE)))
        if not isinstance(value, dict):
            return None
        if value.get("mode") == "new":
            kind = ComponentKind(value["kind"])
            return value if kind != ComponentKind.WINDOW else None
        if value.get("mode") == "move" and all(
            isinstance(value.get(key), str) for key in ("id", "project")
        ):
            if any(
                type(value.get(key, 0)) is not int or not 0 <= value.get(key, 0) <= 20000
                for key in ("offset_x", "offset_y")
            ):
                return None
            return value
    except (ValueError, KeyError, TypeError, UnicodeError):
        return None
    return None


GROUP_ROLE = Qt.ItemDataRole.UserRole + 1
ROW = 22
GROUP = 20


class GroupedDelegate(QStyledItemDelegate):
    """Compact rows; the first visible row of each category carries its group heading."""

    def _first_of_group(self, index):
        view = self.parent()
        group = index.data(GROUP_ROLE)
        for row in range(index.row() - 1, -1, -1):
            if not view.item(row).isHidden():
                return view.item(row).data(GROUP_ROLE) != group
        return True

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW + (GROUP if self._first_of_group(index) else 0))

    def paint(self, painter, option, index):
        from makebench.ui.theme import blend, manager

        from .catalog import CATEGORIES

        if self._first_of_group(index):
            t = manager().tokens
            band = QRect(option.rect.left(), option.rect.top(), option.rect.width(), GROUP)
            painter.save()
            painter.fillRect(band, QColor(blend(t["panel"], t["text"], 0.05)))
            font = QFont(option.font)
            font.setWeight(QFont.Weight.DemiBold)
            font.setPointSizeF(font.pointSizeF() * 0.85)
            font.setCapitalization(QFont.Capitalization.AllUppercase)
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
            painter.setFont(font)
            painter.setPen(QColor(t["muted"]))
            painter.drawText(
                band.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                CATEGORIES.get(index.data(GROUP_ROLE), ""),
            )
            painter.restore()
            option.rect = option.rect.adjusted(0, GROUP, 0, 0)
        super().paint(painter, option, index)


class ComponentPalette(QListWidget):
    """Visual library: click to choose, drag or double-click to insert."""

    add_requested = Signal()

    def __init__(self, parent=None) -> None:
        """Fill in the available types and enable copy dragging."""
        super().__init__(parent)
        from .catalog import CATEGORIES, COMPONENTS

        order = list(CATEGORIES)
        kinds = [k for k in KIND_LABELS if k != ComponentKind.WINDOW]
        kinds.sort(key=lambda k: order.index(COMPONENTS.get(k.value, (order[-1],))[0]))
        for kind in kinds:
            item = QListWidgetItem(KIND_LABELS[kind])
            item.setData(Qt.ItemDataRole.UserRole, kind.value)
            item.setData(GROUP_ROLE, COMPONENTS.get(kind.value, (order[-1],))[0])
            self.addItem(item)
        self.setItemDelegate(GroupedDelegate(self))
        self.setIconSize(QSize(16, 16))
        self.setCurrentRow(0)
        self.setDragEnabled(True)
        self.setMaximumHeight(195)
        self.itemDoubleClicked.connect(lambda _: self.add_requested.emit())
        self.setToolTip(tr("Drag a component onto the interface or double-click to add it."))

    def currentData(self) -> str:
        """Return the type chosen for the insert button."""
        return self.currentItem().data(Qt.ItemDataRole.UserRole)

    def findData(self, value: str) -> int:
        """Find a type by its identifier, never relying on the translated text."""
        return next(
            (
                i
                for i in range(self.count())
                if self.item(i).data(Qt.ItemDataRole.UserRole) == value
            ),
            -1,
        )

    def startDrag(self, _supported_actions) -> None:
        """Start inserting with a preview of the palette item."""
        drag = QDrag(self)
        drag.setMimeData(mime_for({"mode": "new", "kind": self.currentData()}))
        drag.setPixmap(self.viewport().grab(self.visualItemRect(self.currentItem())))
        drag.exec(Qt.DropAction.CopyAction)


class ComponentTree(QTreeWidget):
    """Tree that asks the document for moves, never letting Qt move items by itself."""

    drop_requested = Signal(object, str, int, object)
    remove_requested = Signal()

    def __init__(self, project: Callable[[], Project], can_drop: Callable, parent=None) -> None:
        """Receive access to the current document and drop-target validation."""
        super().__init__(parent)
        self.project = project
        self.can_drop = can_drop
        self.active_root = lambda: self.project().root.id
        self._hint = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(False)
        self.setAutoScroll(True)

    def startDrag(self, _supported_actions) -> None:
        """Drag an existing subtree, keeping its identifiers."""
        item = self.currentItem()
        if item is None:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        project = self.project()
        if project.find(node_id) is None or node_id in {r.id for r in project.roots}:
            return
        drag = QDrag(self)
        drag.setMimeData(mime_for({"mode": "move", "id": node_id, "project": project.id}))
        drag.setPixmap(self.viewport().grab(self.visualItemRect(item)))
        drag.exec(Qt.DropAction.MoveAction)

    def _location(self, point, payload):
        """Read the top/middle/bottom of a row as before/inside/after."""
        project = self.project()
        item = self.itemAt(point)
        if item is None:
            root = project.find(self.active_root())
            return root.id, len(root.children), None, "inside"
        node = project.find(item.data(0, Qt.ItemDataRole.UserRole))
        rect = self.visualItemRect(item)
        zone = (
            "before"
            if point.y() < rect.top() + rect.height() / 3
            else ("after" if point.y() > rect.bottom() - rect.height() / 3 else "inside")
        )
        if node is None:
            return None, 0, None, "inside"
        if node.id in {r.id for r in project.roots} or (
            zone == "inside" and node.can_have_children
        ):
            return node.id, len(node.children), item, "inside"
        parent = project.parent_of(node.id)
        index = parent.children.index(node) + (zone != "before")
        return parent.id, index, item, "after" if zone != "before" else "before"

    def dragEnterEvent(self, event) -> None:
        """Accept only recognized Makebench descriptions."""
        if read_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Show the insertion point only when the structure allows the move."""
        payload = read_payload(event.mimeData())
        if payload:
            parent, index, item, zone = self._location(event.position().toPoint(), payload)
            if self.can_drop(payload, parent):
                self._hint = (item, zone)
                self.viewport().update()
                event.acceptProposedAction()
                return
        self._hint = None
        self.viewport().update()
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        """Remove the highlight when leaving the tree."""
        self._hint = None
        self.viewport().update()
        event.accept()

    def dropEvent(self, event) -> None:
        """Request a single document edit, never modifying QTreeWidgetItems."""
        payload = read_payload(event.mimeData())
        self._hint = None
        self.viewport().update()
        if payload:
            parent, index, _, _ = self._location(event.position().toPoint(), payload)
            if self.can_drop(payload, parent):
                self.drop_requested.emit(payload, parent, index, None)
                event.acceptProposedAction()
                return
        event.ignore()

    def paintEvent(self, event) -> None:
        """Draw the insertion hint without changing the user's selection."""
        super().paintEvent(event)
        if self._hint and self._hint[0] is not None:
            item, zone = self._hint
            rect = self.visualItemRect(item)
            painter = QPainter(self.viewport())
            painter.setPen(QPen(self.palette().highlight().color(), 2))
            if zone == "inside":
                painter.drawRect(rect.adjusted(1, 1, -2, -2))
            else:
                y = rect.top() if zone == "before" else rect.bottom()
                painter.drawLine(rect.left(), y, rect.right(), y)
            painter.end()

    def keyPressEvent(self, event) -> None:
        """Delete the selection by keyboard without intercepting text editing in other panels."""
        if event.key() == Qt.Key.Key_Delete:
            self.remove_requested.emit()
        else:
            super().keyPressEvent(event)
