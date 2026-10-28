# SPDX-License-Identifier: MIT
"""Data collections of a project: `[{"id", "name", "fields": [{"id", "name", "type", "target"?}]}]`.

A field of type `ref` points to another collection (or its own) by id. Records keep an
automatic integer `id`; the first text field is the name shown wherever a record is cited.
"""

from __future__ import annotations

import keyword
import re
from typing import Any

from makebench.i18n import tr

MAX_COLLECTIONS = 64
MAX_FIELDS = 64
FIELD_TYPES = ("text", "number", "date", "bool", "ref")
ITEM_ID = re.compile(r"[a-z0-9_]{1,40}")


def collections_of(metadata: dict) -> list[dict]:
    """The declared collections, in order."""
    return metadata.get("collections", [])


def find_collection(metadata: dict, collection_id: str) -> dict | None:
    """The collection with this id or this name."""
    return next(
        (c for c in collections_of(metadata) if collection_id in {c["id"], c["name"]}), None
    )


def find_field(collection: dict, field_id: str) -> dict | None:
    """The field with this id or this name."""
    return next((f for f in collection["fields"] if field_id in {f["id"], f["name"]}), None)


def display_field(collection: dict) -> dict | None:
    """The field that names a record: the first text field, if any."""
    return next((f for f in collection["fields"] if f["type"] == "text"), None)


def valid_name(name: Any) -> bool:
    """Names become Python keywords arguments, so they must be plain identifiers."""
    return (
        isinstance(name, str)
        and 1 <= len(name) <= 40
        and name.isidentifier()
        and not keyword.iskeyword(name)
        and name != "id"
    )


def validate_collections(collections: Any) -> None:
    """Raise ValueError when the collections are malformed or point nowhere."""
    problem = ValueError(tr("The data collections are invalid."))
    if not isinstance(collections, list) or len(collections) > MAX_COLLECTIONS:
        raise problem
    ids, names = set(), set()
    for collection in collections:
        if (
            not isinstance(collection, dict)
            or set(collection) != {"id", "name", "fields"}
            or not isinstance(collection["id"], str)
            or not ITEM_ID.fullmatch(collection["id"])
            or collection["id"] in ids
            or not valid_name(collection["name"])
            or collection["name"] in names
            or not isinstance(collection["fields"], list)
            or not 1 <= len(collection["fields"]) <= MAX_FIELDS
        ):
            raise problem
        ids.add(collection["id"])
        names.add(collection["name"])
    for collection in collections:
        field_ids, field_names = set(), set()
        for field in collection["fields"]:
            if (
                not isinstance(field, dict)
                or not {"id", "name", "type"} <= set(field)
                or set(field) - {"id", "name", "type", "target"}
                or not isinstance(field["id"], str)
                or not ITEM_ID.fullmatch(field["id"])
                or field["id"] in field_ids
                or not valid_name(field["name"])
                or field["name"] in field_names
                or field["type"] not in FIELD_TYPES
                or ("target" in field) != (field["type"] == "ref")
                or (field["type"] == "ref" and field["target"] not in ids)
            ):
                raise problem
            field_ids.add(field["id"])
            field_names.add(field["name"])
