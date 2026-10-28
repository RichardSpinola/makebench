# SPDX-License-Identifier: GPL-3.0-or-later
"""Data collections in the Data panel: list, edit and remove, without touching stored data."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)
from makebench.core.datamodel import FIELD_TYPES, collections_of, validate_collections
from makebench.core.project import new_id
from makebench.i18n import ntr, tr

FIELD_LABELS = {
    "text": tr("Text"),
    "number": tr("Number"),
    "date": tr("Date"),
    "bool": tr("Yes/No"),
    "ref": tr("Reference"),
}


def uses_collection(value, collection_id, name) -> int:
    """Count the neutral blocks that cite a collection by id or name."""
    if isinstance(value, dict):
        own = int(value.get("collection") in {collection_id, name})
        return own + sum(uses_collection(child, collection_id, name) for child in value.values())
    if isinstance(value, list):
        return sum(uses_collection(child, collection_id, name) for child in value)
    return 0


def uses_fields(value, collection_id, name, field_ids) -> int:
    """Count the neutral blocks of a collection that cite one of these fields."""
    if isinstance(value, list):
        return sum(uses_fields(child, collection_id, name, field_ids) for child in value)
    if not isinstance(value, dict):
        return 0
    own = 0
    if value.get("collection") in {collection_id, name}:
        cited = [value.get(key) for key in ("field", "order", "sum")]
        cited += [
            entry.get("field") for entry in value.get("values", []) if isinstance(entry, dict)
        ]
        own = int(any(item in field_ids for item in cited))
    return own + sum(uses_fields(child, collection_id, name, field_ids) for child in value.values())


class CollectionMixin:
    """Declare record types; the stored records live only in the running app."""

    def sync_collections(self):
        """List the collections at the top of the Data panel."""
        for collection in reversed(collections_of(self.project.metadata)):
            count = len(collection["fields"])
            item = QListWidgetItem(
                tr("Collection")
                + f" · {collection['name']}\n"
                + ntr("{count} field", "{count} fields", count).format(count=count)
            )
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "collection", "id": collection["id"]})
            self.data_list.insertItem(0, item)

    def collection_usage(self, collection):
        """Blocks and fields of other collections that depend on this collection."""
        blocks = sum(
            uses_collection(flow.get(key), collection["id"], collection["name"])
            for flow in self.project.workflows
            for key in ("body", "workspace")
        ) + sum(
            uses_collection(function.get(key), collection["id"], collection["name"])
            for function in self.project.metadata.get("functions", [])
            for key in ("body", "workspace")
        )
        fields = sum(
            1
            for other in collections_of(self.project.metadata)
            if other["id"] != collection["id"]
            for field in other["fields"]
            if field.get("target") == collection["id"]
        )
        return blocks, fields

    def field_usage(self, collection, field_ids):
        """Blocks that still cite fields of a collection that are about to disappear."""
        units = [
            *(flow.get("body") for flow in self.project.workflows),
            *(function.get("body") for function in self.project.metadata.get("functions", [])),
        ]
        return sum(
            uses_fields(unit, collection["id"], collection["name"], field_ids) for unit in units
        )

    def collection_dialog(self, _checked=False, collection_id=None):
        """Create or change a collection: its name and its typed fields."""
        collections = collections_of(self.project.metadata)
        original = next((c for c in collections if c["id"] == collection_id), None)
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Data collection"))
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name = QLineEdit(original["name"] if original else "")
        name.setPlaceholderText(tr("Books"))
        form.addRow(tr("Name"), name)
        layout.addLayout(form)
        layout.addWidget(QLabel(tr("Fields (the first text field names each record)")))
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels([tr("Name"), tr("Type"), tr("Points to")])
        table.horizontalHeader().setStretchLastSection(True)
        table.setAccessibleName(tr("Fields"))
        layout.addWidget(table)
        targets = [(c["id"], c["name"]) for c in collections]

        def add_row(field=None):
            """Append a field row; an existing field keeps its identifier."""
            row = table.rowCount()
            table.insertRow(row)
            cell = QLineEdit(field["name"] if field else "")
            cell.setProperty("field_id", field["id"] if field else new_id("field"))
            table.setCellWidget(row, 0, cell)
            kind, target = QComboBox(), QComboBox()
            for key in FIELD_TYPES:
                kind.addItem(FIELD_LABELS[key], key)
            for target_id, target_name in targets:
                target.addItem(target_name, target_id)
            if field:
                kind.setCurrentIndex(kind.findData(field["type"]))
                target.setCurrentIndex(max(0, target.findData(field.get("target"))))
            target.setEnabled(kind.currentData() == "ref")
            kind.currentIndexChanged.connect(
                lambda _i, kind=kind, target=target: target.setEnabled(kind.currentData() == "ref")
            )
            table.setCellWidget(row, 1, kind)
            table.setCellWidget(row, 2, target)

        for field in (
            original["fields"]
            if original
            else [{"id": new_id("field"), "name": "nome", "type": "text"}]
        ):
            add_row(field)
        row_buttons = QHBoxLayout()
        add = QPushButton(tr("+ Field"))
        remove = QPushButton(tr("Remove field"))
        add.clicked.connect(lambda: add_row())
        remove.clicked.connect(
            lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None
        )
        row_buttons.addWidget(add)
        row_buttons.addWidget(remove)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)
        error = QLabel()
        error.setWordWrap(True)
        layout.addWidget(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        new_identifier = original["id"] if original else new_id("collection")

        def save():
            """Validate the whole declaration before changing the document."""
            fields = []
            for row in range(table.rowCount()):
                cell, kind, target = (table.cellWidget(row, n) for n in range(3))
                field = {
                    "id": cell.property("field_id"),
                    "name": cell.text().strip(),
                    "type": kind.currentData(),
                }
                if field["type"] == "ref":
                    field["target"] = target.currentData() or new_identifier
                fields.append(field)
            collection = {"id": new_identifier, "name": name.text().strip(), "fields": fields}
            result = [c for c in collections if c["id"] != new_identifier]
            result.insert(collections.index(original) if original else len(result), collection)
            try:
                validate_collections(result)
            except ValueError:
                error.setText(
                    tr(
                        "Use different names made of letters, digits and underscores (not “id”), "
                        "at least one field, and a collection to point to."
                    )
                )
                return

            gone = (
                {f["id"] for f in original["fields"]} - {f["id"] for f in fields}
                if original
                else set()
            )
            if gone and self.field_usage(original, gone):
                error.setText(
                    tr("Some removed fields are still used by blocks. Change the blocks first.")
                )
                return

            def edit():
                """Replace the declaration; stored records are never touched here."""
                self.project.metadata["collections"] = result

            self._edit(edit, label=tr("Edit collection"))
            dialog.accept()

        buttons.accepted.connect(save)
        dialog.exec()

    def remove_collection(self, collection_id):
        """Remove a collection nothing depends on, after confirming."""
        collection = next(
            (c for c in collections_of(self.project.metadata) if c["id"] == collection_id), None
        )
        if collection is None:
            return
        blocks, fields = self.collection_usage(collection)
        if blocks or fields:
            self.statusBar().showMessage(
                tr("This collection is still used by blocks or by fields of other collections."),
                6000,
            )
            return
        answer = QMessageBox.question(
            self,
            tr("Remove collection"),
            tr(
                "Remove the collection “{name}”? Records already stored by test runs stay on disk."
            ).format(name=collection["name"]),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def edit():
            """Drop the declaration, and the key itself when it was the last one."""
            remaining = [
                c for c in self.project.metadata["collections"] if c["id"] != collection_id
            ]
            if remaining:
                self.project.metadata["collections"] = remaining
            else:
                del self.project.metadata["collections"]

        self._edit(edit, label=tr("Remove collection"))

    def clear_test_data(self):
        """Delete the records stored by test runs of this project; the app's own data stays."""
        from makebench.core.datastore import data_path

        path = data_path(self.project, True)
        if not path.is_file():
            self.statusBar().showMessage(tr("There is no test data to delete."), 6000)
            return
        answer = QMessageBox.question(
            self,
            tr("Delete test data"),
            tr("Delete all records stored by test runs of this project?"),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for suffix in ("", "-wal", "-shm", "-journal"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        self.statusBar().showMessage(tr("Test data deleted."), 6000)
