# SPDX-License-Identifier: GPL-3.0-or-later
"""The "What can I use" panel: ctx methods, components and collections to insert."""

import ast
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from makebench.core.project import KIND_LABELS
from makebench.i18n import tr

STUB = Path(__file__).with_name("stubs") / "makebench_ctx.pyi"


@lru_cache(maxsize=1)
def api_entries():
    """(prefix, name, call, signature, doc) for each public ctx and ctx.data member of the stub."""
    tree = ast.parse(STUB.read_text(encoding="utf-8"))
    entries = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in {"Context", "Data"}:
            continue
        prefix = "ctx." if node.name == "Context" else "ctx.data."
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name.startswith("_"):
                continue
            doc = ast.get_docstring(item) or ""
            if any(getattr(d, "id", "") == "property" for d in item.decorator_list):
                entries.append((prefix, item.name, prefix + item.name, prefix + item.name, doc))
                continue
            arguments = item.args
            names = [a.arg for a in arguments.posonlyargs + arguments.args][1:]
            required = names[: len(names) - len(arguments.defaults)]
            signature = ast.unparse(arguments).split(", ", 1)
            signature = signature[1] if len(signature) > 1 else ""
            call = f"{prefix}{item.name}({', '.join(required)})"
            entries.append((prefix, item.name, call, f"{prefix}{item.name}({signature})", doc))
    return entries


class CodeReference(QWidget):
    """Searchable list; double-click (or Enter) inserts the item at the code cursor."""

    insert_requested = Signal(str)
    example_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(QLabel(tr("What can I use")), 1)
        from .code_examples import examples
        from .theme import icon

        self.examples = QToolButton()
        self.examples.setIcon(icon("code"))
        self.examples.setText(tr("Insert example"))
        self.examples.setToolTip(tr("Insert example"))
        self.examples.setAccessibleName(tr("Insert example"))
        self.examples.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.examples)
        for title, code in examples():
            menu.addAction(title, lambda code=code: self.example_requested.emit(code))
        self.examples.setMenu(menu)
        header.addWidget(self.examples)
        layout.addLayout(header)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Filter"))
        self.search.setAccessibleName(tr("Filter what can I use"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName(tr("What can I use"))
        self.tree.setToolTip(tr("Double-click to insert at the cursor."))
        self.tree.itemActivated.connect(self._activated)
        layout.addWidget(self.tree, 1)
        self._signature = None

    def sync(self, project):
        """Rebuild only when components or collections change."""
        collections = project.metadata.get("collections", [])
        components = [(n.id, n.kind, n.display_name) for n in project.walk()]
        signature = (tuple(components), repr(collections))
        if signature == self._signature:
            return
        self._signature = signature
        expanded = {
            self.tree.topLevelItem(i).text(0)
            for i in range(self.tree.topLevelItemCount())
            if self.tree.topLevelItem(i).isExpanded()
        }
        self.tree.clear()
        groups = {}
        for prefix, name, call, signature_text, doc in api_entries():
            if prefix not in groups:
                groups[prefix] = self._group(prefix.rstrip("."), expanded)
            self._leaf(groups[prefix], name, call, signature_text + ("\n\n" + doc if doc else ""))
        group = self._group(tr("Components"), expanded)
        for component, kind, label in components:
            self._leaf(
                group,
                f"{component} · {KIND_LABELS.get(kind, kind)}",
                f'"{component}"',
                label,
            )
        group = self._group(tr("Collections"), expanded)
        for collection in collections:
            item = self._leaf(group, collection["name"], f'"{collection["name"]}"', "")
            for field in collection.get("fields", []):
                self._leaf(item, f"{field['name']} · {field['type']}", f"{field['name']}=", "")
        self.filter(self.search.text())

    def _group(self, title, expanded):
        item = QTreeWidgetItem([title])
        self.tree.addTopLevelItem(item)
        item.setExpanded(title in expanded)
        return item

    def _leaf(self, parent, text, insert, tooltip):
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, Qt.ItemDataRole.UserRole, insert)
        item.setToolTip(0, tooltip or insert)
        return item

    def filter(self, text):
        """Hide entries whose label does not contain the text; groups follow their children."""
        text = text.strip().lower()

        def visit(item):
            shown = not text or text in item.text(0).lower()
            children = [visit(item.child(i)) for i in range(item.childCount())]
            shown = shown or any(children)
            item.setHidden(not shown)
            if text and any(children):
                item.setExpanded(True)
            return shown

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))

    def _activated(self, item, _column=0):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if value:
            self.insert_requested.emit(value)
