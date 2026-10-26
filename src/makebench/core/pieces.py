# SPDX-License-Identifier: MIT
"""Reusable pieces: a component tree saved once and inserted as an independent copy."""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path

from makebench.core.project import (
    Component,
    ComponentKind,
    LayoutKind,
    Project,
    ProjectError,
    create_component,
    new_id,
)
from makebench.i18n import tr

FORMAT = "makebench.piece"
MAX_SIZE = 20 * 1024 * 1024


def pieces_dir() -> Path:
    """Where the person's pieces live (follows XDG_DATA_HOME)."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "makebench" / "components"


def _file_name(name: str) -> str:
    slug = re.sub(r"[^\w.-]+", "-", name.strip(), flags=re.UNICODE).strip("-.").lower()
    if not slug:
        raise ProjectError(tr("Enter a name for the piece."))
    return slug[:80] + ".json"


def _assets_of(node: Component) -> set[str]:
    return {
        item.properties["source"]
        for item in node.walk()
        if item.kind == ComponentKind.IMAGE and item.properties.get("source")
    }


def make_piece(project: Project, component_id: str, name: str, assets=None) -> dict:
    """Describe the subtree of a component (and its images) as a piece."""
    node = project.find(component_id)
    if node is None or node.kind in (ComponentKind.WINDOW, ComponentKind.PAGE):
        raise ProjectError(tr("Select a control or a container to save as a piece."))
    if not name.strip():
        raise ProjectError(tr("Enter a name for the piece."))
    files = {}
    for source in sorted(_assets_of(node)):
        if assets is not None:
            files[source] = base64.b64encode(assets.read(source)).decode("ascii")
    return {
        "format": FORMAT,
        "version": 1,
        "name": name.strip(),
        "component": node.to_dict(),
        "assets": files,
    }


def save_piece(piece: dict, folder: Path | None = None) -> Path:
    """Write a piece to the library, replacing one with the same name."""
    folder = folder or pieces_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _file_name(piece["name"])
    data = json.dumps(piece, ensure_ascii=False, indent=2).encode("utf-8")
    handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def read_piece(path: Path) -> dict:
    """Read and validate a piece file; anything odd is refused with a clear message."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_SIZE:
            raise ProjectError(tr("The piece file is too large."))
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("format") != FORMAT
            or not isinstance(value.get("name"), str)
            or not isinstance(value.get("assets", {}), dict)
        ):
            raise ValueError
        component = Component.from_dict(value["component"])
        if component.kind in (ComponentKind.WINDOW, ComponentKind.PAGE):
            raise ValueError
        for name, text in value.get("assets", {}).items():
            if not isinstance(text, str) or not name.startswith("assets/"):
                raise ValueError
            base64.b64decode(text, validate=True)
    except ProjectError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ProjectError(
            tr("{name} is not a valid Makebench piece.").format(name=path.name)
        ) from exc
    return value


def list_pieces(folder: Path | None = None) -> list[tuple[str, Path]]:
    """(name, path) of the readable pieces in the library, sorted by name."""
    folder = folder or pieces_dir()
    found = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            found.append((read_piece(path)["name"], path))
        except ProjectError:
            continue
    return sorted(found, key=lambda pair: pair[0].lower())


def delete_piece(path: Path) -> None:
    """Remove one piece file from the library."""
    Path(path).unlink(missing_ok=True)


def insert_piece(project: Project, parent_id: str, piece: dict, assets=None) -> Component:
    """Insert an independent copy with new identifiers; returns the new component."""
    parent = project.find(parent_id)
    while parent is not None and not parent.can_have_children:
        parent = project.parent_of(parent.id)
    if parent is None:
        raise ProjectError(tr("Select a window or a container to insert the piece."))
    clone = Component.from_dict(deepcopy(piece["component"]))
    if not parent.accepts(clone.kind):
        raise ProjectError(tr("This piece cannot go inside the selected component."))
    identifiers = {}
    for item in clone.walk():
        identifiers[item.id] = new_id(item.kind.value)
        item.id = identifiers[item.id]
        if item.properties.get("code_name"):
            item.properties["code_name"] += "_" + item.id.rsplit("_", 1)[-1][:4]
    for item in clone.walk():
        if item.kind == ComponentKind.PAGES and item.properties.get("initial_page") in identifiers:
            item.properties["initial_page"] = identifiers[item.properties["initial_page"]]
    project._check_depth(parent, clone)
    if assets is not None:
        for source, text in piece.get("assets", {}).items():
            with tempfile.TemporaryDirectory() as folder:
                holder = Path(folder) / Path(source).name
                holder.write_bytes(base64.b64decode(text))
                stored = assets.import_image(holder)
            if stored != source:
                for item in clone.walk():
                    if item.kind == ComponentKind.IMAGE and item.properties.get("source") == source:
                        item.properties["source"] = stored
    parent.children.append(clone)
    return clone


def builtin_pieces() -> list[dict]:
    """Ready-made pieces that ship with Makebench (not stored on disk)."""

    def node(kind, text=None, **extra):
        item = create_component(kind)
        if text is not None:
            item.properties["text"] = text
        item.properties.update(extra)
        return item

    def piece(name, root):
        return {
            "format": FORMAT,
            "version": 1,
            "name": name,
            "component": root.to_dict(),
            "assets": {},
        }

    buttons = node(ComponentKind.CONTAINER)
    buttons.layout = LayoutKind.HORIZONTAL
    buttons.children = [
        node(ComponentKind.SPACER),
        node(ComponentKind.BUTTON, tr("Cancel")),
        node(ComponentKind.BUTTON, tr("OK")),
    ]
    login = node(ComponentKind.CONTAINER)
    login.children = [
        node(ComponentKind.LABEL, tr("Sign in")),
        node(ComponentKind.TEXT_INPUT),
        node(ComponentKind.TEXT_INPUT),
        node(ComponentKind.BUTTON, tr("Enter")),
    ]
    login.children[1].properties["placeholder"] = tr("User")
    login.children[2].properties["placeholder"] = tr("Password")
    header = node(ComponentKind.CONTAINER)
    header.children = [
        node(ComponentKind.LABEL, tr("Title")),
        node(ComponentKind.LABEL, tr("A short line that explains this screen.")),
        node(ComponentKind.SEPARATOR),
    ]
    return [
        piece(tr("OK / Cancel bar"), buttons),
        piece(tr("Login form"), login),
        piece(tr("Screen header"), header),
    ]
