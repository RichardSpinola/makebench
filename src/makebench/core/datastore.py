# SPDX-License-Identifier: MIT
"""SQLite storage for the collections of a project, used by the running app only.

One table per collection (`c_<id>`) and one column per field (`f_<id>`), so renaming a
field in the editor never moves stored data. Opening migrates by adding what is missing;
nothing is ever dropped. A reference is a foreign key that restricts deletion.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from makebench.i18n import ntr, tr
from .datamodel import collections_of, display_field, find_collection, find_field
from .project import valid_date

COLUMN_TYPES = {
    "text": "TEXT",
    "number": "NUMERIC",
    "date": "TEXT",
    "bool": "INTEGER",
    "ref": "INTEGER",
}
OPERATORS = {"=": "=", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">="}


class DataError(Exception):
    """A request the stored data cannot honour (unknown name, bad value, still referenced)."""


def data_path(project, testing: bool) -> Path:
    """Where the records live: per app when exported, apart while testing in the editor."""
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    safe = re.compile(r"[^A-Za-z0-9._-]")
    if testing:
        return base / "makebench" / "test-data" / safe.sub("_", project.id) / "data.sqlite"
    return base / safe.sub("_", project.application.get("id") or project.id) / "data.sqlite"


class DataStore:
    """Records of the project's collections, opened lazily and closed with the worker."""

    def __init__(self, path, collections: list[dict]):
        """Open (creating or migrating) the database for these collections."""
        self.metadata = {"collections": collections}
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.database = sqlite3.connect(str(path), isolation_level=None)
        self.database.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def close(self):
        """Release the file."""
        self.database.close()

    def migrate(self):
        """Create missing tables and add missing columns; never remove anything."""
        collections = collections_of(self.metadata)
        for collection in collections:
            table = self.table(collection)
            self.database.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY AUTOINCREMENT)"
            )
            have = {row[1] for row in self.database.execute(f"PRAGMA table_info({table})")}
            for field in collection["fields"]:
                if self.column(field) in have:
                    continue
                definition = f"{self.column(field)} {COLUMN_TYPES[field['type']]}"
                if field["type"] == "ref":
                    target = find_collection(self.metadata, field["target"])
                    definition += f" REFERENCES {self.table(target)}(id) ON DELETE RESTRICT"
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    @staticmethod
    def table(collection):
        """Table of a collection (identifiers are checked by the project format)."""
        return "c_" + collection["id"]

    @staticmethod
    def column(field):
        """Column of a field."""
        return "f_" + field["id"]

    def collection(self, name):
        """The declared collection, by name or id."""
        found = find_collection(self.metadata, name)
        if found is None:
            raise DataError(tr("Unknown collection: {name}.").format(name=name))
        return found

    def field(self, collection, name):
        """The declared field of a collection, by name or id."""
        found = find_field(collection, name)
        if found is None:
            raise DataError(
                tr("Unknown field {field} in {collection}.").format(
                    field=name, collection=collection["name"]
                )
            )
        return found

    def store(self, collection, field, value):
        """Check a value against its field type and return what SQLite should keep."""
        kind, bad = (
            field["type"],
            DataError(
                tr("Invalid value for {field}: {value!r}.").format(field=field["name"], value=value)
            ),
        )
        if value is None:
            return None
        if kind == "text":
            if not isinstance(value, str):
                raise bad
            return value
        if kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise bad
            return value
        if kind == "date":
            if not isinstance(value, str) or not valid_date(value):
                raise bad
            return value
        if kind == "bool":
            if not isinstance(value, bool):
                raise bad
            return int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise bad
        target = find_collection(self.metadata, field["target"])
        if self.get(target["name"], value) is None:
            raise DataError(
                tr("{collection} has no record {id}.").format(collection=target["name"], id=value)
            )
        return value

    def load(self, collection, row):
        """A record as a dict keyed by field names, with the record id."""
        record = {"id": row[0]}
        for field, value in zip(collection["fields"], row[1:]):
            record[field["name"]] = (
                bool(value) if field["type"] == "bool" and value is not None else value
            )
        return record

    def select(self, collection):
        """The SELECT list shared by every query of a collection."""
        columns = ", ".join(self.column(f) for f in collection["fields"])
        return f"SELECT id, {columns} FROM {self.table(collection)}"

    def values(self, collection, fields):
        """Validated (column, value) pairs for the given keyword fields."""
        return [
            (self.column(field), self.store(collection, field, value))
            for field, value in (
                (self.field(collection, name), value) for name, value in fields.items()
            )
        ]

    def add(self, name, **fields):
        """Insert a record and return its id."""
        collection = self.collection(name)
        pairs = self.values(collection, fields)
        table = self.table(collection)
        if not pairs:
            cursor = self.database.execute(f"INSERT INTO {table} DEFAULT VALUES")
        else:
            cursor = self.database.execute(
                f"INSERT INTO {table} ({', '.join(c for c, _ in pairs)}) "
                f"VALUES ({', '.join('?' for _ in pairs)})",
                [v for _, v in pairs],
            )
        return cursor.lastrowid

    def update(self, name, record_id, **fields):
        """Change fields of an existing record."""
        collection = self.collection(name)
        if self.get(name, record_id) is None:
            raise DataError(
                tr("{collection} has no record {id}.").format(collection=name, id=record_id)
            )
        pairs = self.values(collection, fields)
        if pairs:
            self.database.execute(
                f"UPDATE {self.table(collection)} SET {', '.join(c + ' = ?' for c, _ in pairs)} "
                "WHERE id = ?",
                [*(v for _, v in pairs), record_id],
            )

    def delete(self, name, record_id):
        """Delete a record unless other records still point to it."""
        collection = self.collection(name)
        for other in collections_of(self.metadata):
            for field in other["fields"]:
                if field["type"] != "ref" or field["target"] != collection["id"]:
                    continue
                count = self.database.execute(
                    f"SELECT COUNT(*) FROM {self.table(other)} WHERE {self.column(field)} = ?",
                    [record_id],
                ).fetchone()[0]
                if count:
                    raise DataError(
                        ntr(
                            "Cannot delete: {count} record of {collection} still points to it.",
                            "Cannot delete: {count} records of {collection} still point to it.",
                            count,
                        ).format(count=count, collection=other["name"])
                    )
        self.database.execute(f"DELETE FROM {self.table(collection)} WHERE id = ?", [record_id])

    def get(self, name, record_id):
        """One record, or None."""
        collection = self.collection(name)
        row = self.database.execute(
            f"{self.select(collection)} WHERE id = ?", [record_id]
        ).fetchone()
        return self.load(collection, row) if row else None

    def where(self, collection, field, operator, value):
        """SQL condition and parameters for a simple filter on one field."""
        if field is None:
            return "", []
        if field == "id":
            column, kind = "id", "ref"
        else:
            found = self.field(collection, field)
            column, kind = self.column(found), found["type"]
        if operator == "contains":
            escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            return f" WHERE {column} LIKE ? ESCAPE '\\'", [f"%{escaped}%"]
        if operator not in OPERATORS:
            raise DataError(tr("Unknown comparison: {operator}.").format(operator=operator))
        if kind == "bool" and isinstance(value, bool):
            value = int(value)
        return f" WHERE {column} {OPERATORS[operator]} ?", [value]

    def find(self, name, field=None, operator="=", value=None, order=None, descending=False):
        """Records matching one simple filter, by id or by a field, optionally ordered."""
        collection = self.collection(name)
        condition, parameters = self.where(collection, field, operator, value)
        column = "id"
        if order is not None and order != "id":
            column = self.column(self.field(collection, order))
        sql = f"{self.select(collection)}{condition} ORDER BY {column} {'DESC' if descending else 'ASC'}, id"
        return [self.load(collection, row) for row in self.database.execute(sql, parameters)]

    def count(self, name, field=None, operator="=", value=None):
        """How many records match."""
        collection = self.collection(name)
        condition, parameters = self.where(collection, field, operator, value)
        sql = f"SELECT COUNT(*) FROM {self.table(collection)}{condition}"
        return self.database.execute(sql, parameters).fetchone()[0]

    def sum(self, name, field, filter_field=None, operator="=", value=None):
        """Total of a number field over the matching records (0 when there are none)."""
        collection = self.collection(name)
        target = self.field(collection, field)
        if target["type"] != "number":
            raise DataError(tr("Only number fields can be summed: {field}.").format(field=field))
        condition, parameters = self.where(collection, filter_field, operator, value)
        sql = f"SELECT COALESCE(SUM({self.column(target)}), 0) FROM {self.table(collection)}{condition}"
        return self.database.execute(sql, parameters).fetchone()[0]

    def listing(self, name, records=None):
        """Headers, text rows, ids and names of records, ready for a table or a choice list."""
        collection = self.collection(name)
        if records is None:
            records = self.find(name)
        shown = display_field(collection)
        rows, ids, names = [], [], []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), int):
                raise DataError(tr("Provide records as returned by the data blocks."))
            cells = []
            for field in collection["fields"]:
                value = record.get(field["name"])
                if value is None:
                    cells.append("")
                elif field["type"] == "ref":
                    cells.append(
                        self.name(find_collection(self.metadata, field["target"])["name"], value)
                    )
                elif field["type"] == "bool":
                    cells.append(tr("Yes") if value else tr("No"))
                else:
                    cells.append(str(value))
            rows.append(cells)
            ids.append(record["id"])
            label = record.get(shown["name"]) if shown else None
            names.append(str(label) if label is not None else str(record["id"]))
        return {
            "headers": [f["name"] for f in collection["fields"]],
            "rows": rows,
            "ids": ids,
            "names": names,
        }

    def name(self, collection_name, record_id):
        """The text that names a record in references; empty when it does not exist."""
        collection = self.collection(collection_name)
        record = self.get(collection_name, record_id)
        if record is None:
            return ""
        shown = display_field(collection)
        return (
            str(record[shown["name"]])
            if shown and record[shown["name"]] is not None
            else str(record_id)
        )
