# SPDX-License-Identifier: MIT
"""Application menus of a window: `[{"text", "items": [{"id", "text", "shortcut"}]}]`."""

from __future__ import annotations

import re
import unicodedata

from makebench.i18n import tr

MAX_MENUS = 8
MAX_ITEMS = 32
ITEM_ID = re.compile(r"[a-z0-9_]{1,40}")


def menu_items(properties: dict) -> list[tuple[dict, dict]]:
    """Every (menu, item) pair of a window, in order."""
    return [(menu, item) for menu in properties.get("menus", []) for item in menu["items"]]


def validate_menus(menus, window_id: str) -> None:
    """Raise ValueError when the menus of a window are malformed."""
    problem = ValueError(tr("The menus of {id} are invalid.").format(id=window_id))
    if not isinstance(menus, list) or len(menus) > MAX_MENUS:
        raise problem
    seen = set()
    for menu in menus:
        if (
            not isinstance(menu, dict)
            or set(menu) != {"text", "items"}
            or not isinstance(menu["text"], str)
            or not 1 <= len(menu["text"]) <= 60
            or not isinstance(menu["items"], list)
            or not 1 <= len(menu["items"]) <= MAX_ITEMS
        ):
            raise problem
        for item in menu["items"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"id", "text", "shortcut"}
                or not all(isinstance(item[key], str) for key in item)
                or not ITEM_ID.fullmatch(item["id"])
                or item["id"] in seen
                or not 1 <= len(item["text"]) <= 60
                or len(item["shortcut"]) > 30
            ):
                raise problem
            seen.add(item["id"])


def format_menus(menus: list[dict]) -> str:
    """The editable form: a menu title per line, its items indented as `text | shortcut`."""
    lines = []
    for menu in menus:
        lines.append(menu["text"])
        for item in menu["items"]:
            lines.append(
                "  " + item["text"] + (" | " + item["shortcut"] if item["shortcut"] else "")
            )
    return "\n".join(lines)


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:40] or "item"


def parse_menus(text: str, previous: list[dict] | None = None) -> list[dict]:
    """Read the editable form; items keep the id of an earlier item with the same text."""
    known = {}
    for menu, item in menu_items({"menus": previous or []}):
        known.setdefault((menu["text"], item["text"]), item["id"])
    menus, used = [], set()
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if not raw[0].isspace():
            menus.append({"text": raw.strip(), "items": []})
            continue
        if not menus:
            continue
        label, _, shortcut = raw.strip().partition("|")
        label = label.strip()
        if not label:
            continue
        menu = menus[-1]
        base = known.get((menu["text"], label)) or _slug(label)
        identifier, number = base, 2
        while identifier in used:
            identifier, number = f"{base}_{number}"[:40], number + 1
        used.add(identifier)
        menu["items"].append({"id": identifier, "text": label, "shortcut": shortcut.strip()})
    return [menu for menu in menus if menu["items"]]
