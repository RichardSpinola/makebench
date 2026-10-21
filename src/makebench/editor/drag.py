"""Arraste nativo de componentes e reorganização da árvore, sem mover dados Qt."""

from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QTreeWidget

from makebench.core.project import KIND_LABELS, ComponentKind, Project

MIME_TYPE = "application/x-makebench-component"


def mime_for(payload: dict) -> QMimeData:
    """Codifica somente descrições de inserção/movimento, nunca arquivos ou código."""
    data = QMimeData()
    data.setData(MIME_TYPE, json.dumps(payload).encode("utf-8"))
    return data


def read_payload(mime: QMimeData) -> dict | None:
    """Recusa formatos externos e descrições incompletas de arraste."""
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
            if any(type(value.get(key, 0)) is not int or not 0 <= value.get(key, 0) <= 20000 for key in ("offset_x", "offset_y")):
                return None
            return value
    except (ValueError, KeyError, TypeError, UnicodeError):
        return None
    return None


class ComponentPalette(QListWidget):
    """Biblioteca visual: clique para escolher, arraste ou dê duplo clique para inserir."""

    add_requested = Signal()

    def __init__(self, parent=None) -> None:
        """Preenche os tipos disponíveis e habilita o arraste de cópia."""
        super().__init__(parent)
        for kind, label in KIND_LABELS.items():
            if kind != ComponentKind.WINDOW:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, kind.value)
                self.addItem(item)
        self.setCurrentRow(0)
        self.setDragEnabled(True)
        self.setMaximumHeight(195)
        self.itemDoubleClicked.connect(lambda _: self.add_requested.emit())
        self.setToolTip("Arraste um componente para a interface ou dê duplo clique para adicionar.")

    def currentData(self) -> str:
        """Retorna o tipo escolhido para o botão de inserção."""
        return self.currentItem().data(Qt.ItemDataRole.UserRole)

    def findData(self, value: str) -> int:
        """Localiza um tipo por seu identificador, sem depender do texto traduzido."""
        return next((i for i in range(self.count()) if self.item(i).data(Qt.ItemDataRole.UserRole) == value), -1)

    def startDrag(self, _supported_actions) -> None:
        """Inicia a inserção com uma prévia do item da paleta."""
        drag = QDrag(self)
        drag.setMimeData(mime_for({"mode": "new", "kind": self.currentData()}))
        drag.setPixmap(self.viewport().grab(self.visualItemRect(self.currentItem())))
        drag.exec(Qt.DropAction.CopyAction)


class ComponentTree(QTreeWidget):
    """Árvore que pede movimentos ao documento, sem deixar o Qt mover itens sozinho."""

    drop_requested = Signal(object, str, int, object)
    remove_requested = Signal()

    def __init__(self, project: Callable[[], Project], can_drop: Callable, parent=None) -> None:
        """Recebe acesso ao documento atual e a validação de destinos de arraste."""
        super().__init__(parent)
        self.project = project
        self.can_drop = can_drop
        self._hint = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(False)
        self.setAutoScroll(True)

    def startDrag(self, _supported_actions) -> None:
        """Arrasta uma subárvore existente, mantendo seus identificadores."""
        item = self.currentItem()
        if item is None:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        project = self.project()
        if node_id == project.root.id:
            return
        drag = QDrag(self)
        drag.setMimeData(mime_for({"mode": "move", "id": node_id, "project": project.id}))
        drag.setPixmap(self.viewport().grab(self.visualItemRect(item)))
        drag.exec(Qt.DropAction.MoveAction)

    def _location(self, point, payload):
        """Interpreta topo/centro/base de uma linha como antes/dentro/depois."""
        project = self.project()
        item = self.itemAt(point)
        if item is None:
            return project.root.id, len(project.root.children), None, "inside"
        node = project.find(item.data(0, Qt.ItemDataRole.UserRole))
        rect = self.visualItemRect(item)
        zone = "before" if point.y() < rect.top() + rect.height() / 3 else (
            "after" if point.y() > rect.bottom() - rect.height() / 3 else "inside"
        )
        if node.id == project.root.id or (zone == "inside" and node.can_have_children):
            return node.id, len(node.children), item, "inside"
        parent = project.parent_of(node.id)
        index = parent.children.index(node) + (zone != "before")
        return parent.id, index, item, "after" if zone != "before" else "before"

    def dragEnterEvent(self, event) -> None:
        """Aceita exclusivamente descrições Makebench reconhecidas."""
        if read_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Mostra a posição de inserção apenas quando a estrutura permite o movimento."""
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
        """Remove o destaque ao sair da árvore."""
        self._hint = None
        self.viewport().update()
        event.accept()

    def dropEvent(self, event) -> None:
        """Solicita uma única edição do documento, sem modificar QTreeWidgetItems."""
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
        """Desenha a indicação de inserção, sem mudar a seleção do usuário."""
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
        """Exclui a seleção por teclado sem interceptar edição de texto em outros painéis."""
        if event.key() == Qt.Key.Key_Delete:
            self.remove_requested.emit()
        else:
            super().keyPressEvent(event)
