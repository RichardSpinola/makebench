# SPDX-License-Identifier: MIT
"""Project contract shared by the editor and the generators.

The visual document is the source of truth. The user's own Python code lives in
separate files and is never rewritten when the interface is regenerated.
"""

from __future__ import annotations

import datetime
import math
import re
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Iterator
from uuid import uuid4
from makebench.i18n import tr
from .chart import CHART_TYPES
from .datamodel import validate_collections
from .menus import validate_menus
from .style import component_style, style_error

FORMAT_VERSION = 12
FORMAT_NAME = "makebench.project"


class ProjectError(ValueError):
    """Document or change incompatible with the project rules."""


class ComponentKind(StrEnum):
    """Components recognized by the interface editor."""

    WINDOW = "window"
    CONTAINER = "container"
    PAGES = "pages"
    PAGE = "page"
    IMAGE = "image"
    LABEL = "label"
    BUTTON = "button"
    TEXT_INPUT = "text_input"
    TEXT_AREA = "text_area"
    CHOICE = "choice"
    DATE = "date"
    TABLE = "table"
    CHART = "chart"
    CHECKBOX = "checkbox"
    PROGRESS = "progress"
    NUMBER = "number"
    SLIDER = "slider"
    OUTPUT = "output"
    TERMINAL = "terminal"
    SEPARATOR = "separator"
    SPACER = "spacer"


V10_EVENTS = {"change", "close", "timer", "menu"}
WINDOW_FRAMES = ("normal", "no_buttons", "none")
V10_KINDS = {
    ComponentKind.NUMBER,
    ComponentKind.SLIDER,
    ComponentKind.TEXT_AREA,
    ComponentKind.CHOICE,
    ComponentKind.DATE,
    ComponentKind.TABLE,
}  # grows with each new 1.0 component
RANGE_KINDS = {ComponentKind.NUMBER, ComponentKind.SLIDER}
RANGE_DEFAULTS = {"value": 0, "minimum": 0, "maximum": 100, "step": 1, "decimals": 0}


class LayoutKind(StrEnum):
    """How the children of a window or container are arranged."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GRID = "grid"
    FREE = "free"


CONTAINER_KINDS = {
    ComponentKind.WINDOW,
    ComponentKind.CONTAINER,
    ComponentKind.PAGES,
    ComponentKind.PAGE,
}
KIND_LABELS = {
    ComponentKind.SEPARATOR: tr("Separator"),
    ComponentKind.SPACER: tr("Spacer"),
    ComponentKind.WINDOW: tr("Window"),
    ComponentKind.CONTAINER: tr("Container"),
    ComponentKind.PAGES: tr("Tabbed pages"),
    ComponentKind.PAGE: tr("Page"),
    ComponentKind.IMAGE: tr("Image"),
    ComponentKind.LABEL: tr("Text"),
    ComponentKind.BUTTON: tr("Button"),
    ComponentKind.TEXT_INPUT: tr("Text field"),
    ComponentKind.CHECKBOX: tr("Checkbox"),
    ComponentKind.PROGRESS: tr("Progress"),
    ComponentKind.TEXT_AREA: tr("Long text"),
    ComponentKind.CHOICE: tr("Choice list"),
    ComponentKind.DATE: tr("Date"),
    ComponentKind.TABLE: tr("Table"),
    ComponentKind.CHART: tr("Chart"),
    ComponentKind.NUMBER: tr("Number"),
    ComponentKind.SLIDER: tr("Slider"),
    ComponentKind.OUTPUT: tr("Output panel"),
    ComponentKind.TERMINAL: tr("Terminal"),
}
LAYOUT_LABELS = {
    LayoutKind.VERTICAL: tr("Column"),
    LayoutKind.HORIZONTAL: tr("Row"),
    LayoutKind.GRID: tr("Grid"),
    LayoutKind.FREE: tr("Free"),
}


def has_graph(flow):
    """Detect logic from the removed node editor without assuming validated data."""
    backups = flow.get("behavior_backups", [])
    return (
        flow.get("editor") == "nodes"
        or isinstance(backups, list)
        and any(isinstance(item, dict) and item.get("editor") == "nodes" for item in backups)
    )


PROGRAMMING = ("blocks", "python")


def infer_programming(project, source="") -> str | None:
    """Pick blocks or Python for a project saved before the choice existed.

    Flows mean blocks; Python modules or an edited functions file mean Python.
    Returns None for an empty project so the editor can ask.
    """
    if project.metadata.get("programming") in PROGRAMMING:
        return project.metadata["programming"]
    if project.workflows:
        return "blocks"
    from .source import DEFAULT_SOURCES

    text = str(source).strip()
    if project.python_files or getattr(source, "modules", None):
        return "python"
    if text and text not in {item.strip() for item in DEFAULT_SOURCES.values()}:
        return "python"
    return None


def new_id(prefix: str) -> str:
    """Create an identifier that stays stable across save and reopen."""
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class Component:
    """Interface node, its properties and its ordered children.

    Geometry is used by the parent in free layout. In other layouts the toolkit
    arranges the children automatically. Values are logical pixels.
    """

    id: str
    kind: ComponentKind
    properties: dict[str, Any] = field(default_factory=dict)
    layout: LayoutKind = LayoutKind.VERTICAL
    children: list[Component] = field(default_factory=list)
    geometry: dict[str, int] = field(
        default_factory=lambda: {"x": 16, "y": 16, "width": 220, "height": 44}
    )

    @property
    def can_have_children(self) -> bool:
        """Whether the editor can insert components inside this node."""
        return self.kind in CONTAINER_KINDS

    def accepts(self, kind: ComponentKind) -> bool:
        """Respect the page structure and forbid windows inside the interface."""
        if self.kind == ComponentKind.PAGES:
            return kind == ComponentKind.PAGE
        if self.kind == ComponentKind.WINDOW and isinstance(self.properties.get("web_page"), str):
            return False  # A Web view window shows only its page.
        return self.can_have_children and kind not in {ComponentKind.WINDOW, ComponentKind.PAGE}

    @property
    def display_name(self) -> str:
        """Short description for the component tree."""
        text = self.properties.get("title") or self.properties.get("text")
        return f"{KIND_LABELS[self.kind]} · {str(text)[:40]}" if text else KIND_LABELS[self.kind]

    def walk(self) -> Iterator[Component]:
        """Walk the tree in presentation order, including this node."""
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        """Produce JSON data independent of in-memory instances."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "layout": self.layout.value,
            "properties": deepcopy(self.properties),
            "geometry": dict(self.geometry),
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, value: Any, depth: int = 0) -> Component:
        """Read a node without running project content; reject invalid shapes."""
        if depth > 64:
            raise ProjectError(tr("The interface exceeds the limit of 64 container levels."))
        if not isinstance(value, dict):
            raise ProjectError(tr("Each component must be an object."))
        try:
            component_id = value["id"]
            kind = ComponentKind(value["kind"])
            layout = LayoutKind(value.get("layout", "vertical"))
        except (KeyError, ValueError, TypeError) as exc:
            raise ProjectError(tr("Component without a valid identifier, type or layout.")) from exc
        if not isinstance(component_id, str) or not component_id.strip():
            raise ProjectError(tr("The component identifier must be non-empty text."))
        properties = value.get("properties", {})
        children = value.get("children", [])
        geometry = value.get("geometry", {"x": 16, "y": 16, "width": 220, "height": 44})
        if not isinstance(properties, dict) or not isinstance(children, list):
            raise ProjectError(
                tr("Invalid properties or children in {id}.").format(id=component_id)
            )
        if not isinstance(geometry, dict) or set(geometry) != {"x", "y", "width", "height"}:
            raise ProjectError(tr("Invalid geometry in {id}.").format(id=component_id))
        for key, number in geometry.items():
            if (
                type(number) is not int
                or number < (1 if key in {"width", "height"} else 0)
                or number > 20000
            ):
                raise ProjectError(
                    tr("Invalid geometry in {id}: {key}.").format(id=component_id, key=key)
                )
        for key in ("title", "text", "placeholder"):
            if key in properties and not isinstance(properties[key], str):
                raise ProjectError(
                    tr("Property {key} of {id} must be text.").format(key=key, id=component_id)
                )
        if "checked" in properties and type(properties["checked"]) is not bool:
            raise ProjectError(
                tr("The selection of {id} must be true or false.").format(id=component_id)
            )
        if kind == ComponentKind.CHOICE:
            options = properties.get("options", [])
            if (
                not isinstance(options, list)
                or len(options) > 256
                or any(not isinstance(item, str) or len(item) > 200 for item in options)
            ):
                raise ProjectError(
                    tr("The options of {id} must be up to 256 short texts.").format(id=component_id)
                )
            if properties.get("text", "") not in {"", *options}:
                raise ProjectError(
                    tr("The selected option of {id} is not in its list.").format(id=component_id)
                )
        if "menus" in properties:
            if kind != ComponentKind.WINDOW:
                raise ProjectError(tr("Only a window can have menus."))
            try:
                validate_menus(properties["menus"], component_id)
            except ValueError as exc:
                raise ProjectError(str(exc)) from None
        if kind == ComponentKind.TABLE:
            columns = properties.get("headers", [])
            if (
                not isinstance(columns, list)
                or not 1 <= len(columns) <= 64
                or any(not isinstance(item, str) or len(item) > 200 for item in columns)
            ):
                raise ProjectError(
                    tr("The columns of {id} must be 1 to 64 short texts.").format(id=component_id)
                )
        if kind == ComponentKind.CHART and (
            properties.get("chart_type", "bar") not in CHART_TYPES
            or not isinstance(properties.get("title", ""), str)
            or len(properties.get("title", "")) > 200
        ):
            raise ProjectError(
                tr("The chart {id} needs a type (bar, line or pie) and a short title.").format(
                    id=component_id
                )
            )
        if kind == ComponentKind.DATE and not valid_date(properties.get("text", "")):
            raise ProjectError(
                tr("The date of {id} must be written as YYYY-MM-DD.").format(id=component_id)
            )
        if kind in RANGE_KINDS:
            validate_range(kind, properties, component_id)
        elif "value" in properties and (
            type(properties["value"]) is not int or not 0 <= properties["value"] <= 100
        ):
            raise ProjectError(
                tr("The progress of {id} must be between 0 and 100.").format(id=component_id)
            )
        if (
            kind == ComponentKind.IMAGE
            and "source" in properties
            and not isinstance(properties["source"], str)
        ):
            raise ProjectError(tr("The image path must be text."))
        if kind == ComponentKind.IMAGE and properties.get("source"):
            if not valid_asset(properties["source"]):
                raise ProjectError(tr("The image must be in the project's assets folder."))
        if properties.get("background_image") and (
            kind != ComponentKind.WINDOW or not valid_asset(properties["background_image"])
        ):
            raise ProjectError(
                tr("The background image of {id} must be in the project's assets folder.").format(
                    id=component_id
                )
            )
        if style_error(properties):
            raise ProjectError(
                tr("The style of {id} is invalid: {key}.").format(
                    id=component_id, key=style_error(properties)
                )
            )
        for key in ("alt_text", "image_name"):
            if key in properties and not isinstance(properties[key], str):
                raise ProjectError(tr("The image description and name must be text."))
        if "columns" in properties and (
            type(properties["columns"]) is not int or not 1 <= properties["columns"] <= 12
        ):
            raise ProjectError(tr("The grid must have between 1 and 12 columns."))
        if "web_page" in properties and (
            kind != ComponentKind.WINDOW
            or not isinstance(properties["web_page"], str)
            or len(properties["web_page"]) > 2_000_000
        ):
            raise ProjectError(tr("Only a window can show a web page, as text up to 2 MB."))
        if kind == ComponentKind.TERMINAL:
            if not isinstance(
                properties.get("terminal_program", ""), str
            ) or "\0" in properties.get("terminal_program", ""):
                raise ProjectError(tr("Invalid terminal program."))
            arguments = properties.get("terminal_arguments", [])
            if (
                not isinstance(arguments, list)
                or len(arguments) > 256
                or any(not isinstance(a, str) or "\0" in a for a in arguments)
            ):
                raise ProjectError(tr("Terminal arguments must be a list of texts."))
            if type(properties.get("terminal_autostart", False)) is not bool:
                raise ProjectError(tr("Invalid terminal autostart."))
        node = cls(
            id=component_id,
            kind=kind,
            properties=deepcopy(properties),
            layout=layout,
            geometry=dict(geometry),
            children=[cls.from_dict(child, depth + 1) for child in children],
        )
        if node.children and not node.can_have_children:
            raise ProjectError(
                tr("{kind} cannot contain other components.").format(kind=KIND_LABELS[node.kind])
            )
        if node.children and "web_page" in node.properties:
            raise ProjectError(tr("A Web view window shows only its page, without components."))
        if any(not node.accepts(child.kind) for child in node.children):
            raise ProjectError(tr("Pages must be inside a set of pages."))
        if kind == ComponentKind.PAGES:
            if not node.children:
                raise ProjectError(tr("A set of pages needs at least one page."))
            initial = properties.get("initial_page", node.children[0].id)
            if not isinstance(initial, str) or initial not in {child.id for child in node.children}:
                raise ProjectError(tr("The initial page does not belong to this set of pages."))
            node.properties["initial_page"] = initial
        if depth and node.kind == ComponentKind.WINDOW:
            raise ProjectError(tr("A window cannot be inside another component."))
        return node


def valid_asset(source) -> bool:
    """True for a relative path inside the project's assets folder."""
    if not isinstance(source, str):
        return False
    path = PurePosixPath(source)
    return not (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in source
        or len(path.parts) < 2
        or path.parts[0] != "assets"
    )


def valid_date(value) -> bool:
    """True for a real calendar date written as YYYY-MM-DD."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_range(kind, properties, component_id):
    """Check the value, limits, step and decimals of a number or slider."""
    values = {**RANGE_DEFAULTS, **properties}
    decimals = values["decimals"]
    if (
        type(decimals) is not int
        or not 0 <= decimals <= 6
        or (kind == ComponentKind.SLIDER and decimals)
    ):
        raise ProjectError(
            tr("The decimals of {id} must be a whole number from 0 to 6.").format(id=component_id)
        )
    for key in ("value", "minimum", "maximum", "step"):
        item = values[key]
        if type(item) not in {int, float} or not math.isfinite(item) or abs(item) > 1e12:
            raise ProjectError(
                tr("The number {key} of {id} is invalid.").format(key=key, id=component_id)
            )
        if not decimals and item != int(item):
            raise ProjectError(
                tr("The number {key} of {id} must be a whole number.").format(
                    key=key, id=component_id
                )
            )
    if values["minimum"] > values["maximum"] or values["step"] <= 0:
        raise ProjectError(tr("The limits or step of {id} are invalid.").format(id=component_id))
    if not values["minimum"] <= values["value"] <= values["maximum"]:
        raise ProjectError(
            tr("The value of {id} must be between its limits.").format(id=component_id)
        )


def clamp_range(node):
    """Keep a number or slider valid after one of its limits, step or decimals changed."""
    p = {**RANGE_DEFAULTS, **node.properties}
    if node.kind == ComponentKind.SLIDER:
        p["decimals"] = 0
    for key in ("value", "minimum", "maximum", "step"):
        p[key] = round(p[key]) if not p["decimals"] else round(p[key], p["decimals"])
    p["step"] = p["step"] or 10 ** -p["decimals"]
    p["maximum"] = max(p["maximum"], p["minimum"])
    p["value"] = min(max(p["value"], p["minimum"]), p["maximum"])
    p.pop("decimals") if node.kind == ComponentKind.SLIDER else None
    node.properties.update(p)


def create_component(kind: ComponentKind) -> Component:
    """Create a component with starting properties suited to its type."""
    kind = ComponentKind(kind)
    defaults = {
        ComponentKind.WINDOW: {"title": tr("My application")},
        ComponentKind.SEPARATOR: {},
        ComponentKind.SPACER: {"size_mode": {"width": "fill", "height": "fill"}},
        ComponentKind.CONTAINER: {},
        ComponentKind.PAGES: {},
        ComponentKind.PAGE: {"title": tr("New page")},
        ComponentKind.IMAGE: {"source": "", "alt_text": tr("Application image")},
        ComponentKind.LABEL: {"text": tr("New text")},
        ComponentKind.BUTTON: {"text": tr("New button")},
        ComponentKind.TEXT_INPUT: {"text": "", "placeholder": tr("Type here")},
        ComponentKind.CHECKBOX: {"text": tr("New option"), "checked": False},
        ComponentKind.PROGRESS: {"value": 0},
        ComponentKind.TEXT_AREA: {"text": "", "placeholder": tr("Type here")},
        ComponentKind.CHOICE: {"options": [tr("Option 1"), tr("Option 2")], "text": ""},
        ComponentKind.TABLE: {"headers": [tr("Column 1"), tr("Column 2")]},
        ComponentKind.CHART: {"chart_type": "bar", "title": ""},
        ComponentKind.DATE: {"text": datetime.date.today().isoformat()},
        ComponentKind.NUMBER: dict(RANGE_DEFAULTS),
        ComponentKind.SLIDER: {k: v for k, v in RANGE_DEFAULTS.items() if k != "decimals"},
        ComponentKind.OUTPUT: {"text": tr("Task output will appear here.")},
        ComponentKind.TERMINAL: {
            "terminal_program": "",
            "terminal_arguments": [],
            "terminal_autostart": False,
        },
    }
    node = Component(id=new_id(kind.value), kind=kind, properties=defaults[kind].copy())
    if node.can_have_children:
        node.geometry.update(width=360, height=240)
    elif kind == ComponentKind.IMAGE:
        node.geometry.update(width=240, height=160)
    elif kind in {
        ComponentKind.OUTPUT,
        ComponentKind.TERMINAL,
        ComponentKind.TEXT_AREA,
        ComponentKind.TABLE,
        ComponentKind.CHART,
    }:
        node.geometry.update(width=360, height=140)
    if kind == ComponentKind.PAGES:
        page = create_component(ComponentKind.PAGE)
        page.properties["title"] = tr("Page {number}").format(number=1)
        node.children.append(page)
        node.properties["initial_page"] = page.id
    return node


@dataclass
class Project:
    """Visual document with portable logic and preserved extensions.

    Workflows and metadata are data only. Opening a project never imports
    Python functions or triggers commands or scripts.
    """

    name: str
    root: Component
    id: str = field(default_factory=lambda: new_id("project"))
    workflows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    windows: list[Component] = field(default_factory=list)
    states: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    entry_window: str | None = None
    variables: list[dict[str, Any]] = field(default_factory=list)
    map_layout: dict[str, list[float]] = field(default_factory=dict)
    format_version: int = 4
    application: dict[str, Any] = field(default_factory=dict)
    python_files: list[str] = field(default_factory=list)

    @property
    def editable_flows(self) -> list[dict[str, Any]]:
        """Return only recognized logic; older extensions stay opaque."""
        from .logic import editable

        return self.workflows if editable(self) else []

    @property
    def programming(self) -> str | None:
        """Return "blocks", "python" or None when the project has not chosen yet."""
        value = self.metadata.get("programming")
        return value if value in PROGRAMMING else None

    @property
    def roots(self) -> list[Component]:
        """Return real windows; the legacy root stays the first window."""
        return [self.root, *self.windows]

    def walk(self) -> Iterator[Component]:
        """Walk every window, with identifiers unique across the project."""
        for root in self.roots:
            yield from root.walk()

    def window_of(self, component_id: str) -> Component | None:
        """Resolve a component's window scope, including the window itself."""
        return next(
            (root for root in self.roots if any(n.id == component_id for n in root.walk())), None
        )

    def effective_root(self, window_id: str, state_id: str = "@default") -> Component:
        """Apply overrides to a copy; never changes the default composition."""
        root = next((r for r in self.roots if r.id == window_id), None)
        if root is None:
            raise ProjectError(tr("The window does not exist."))
        clone = deepcopy(root)
        if state_id == "@default":
            return clone
        state = next(
            (item for item in self.states.get(window_id, []) if item["id"] == state_id), None
        )
        if state is None:
            raise ProjectError(tr("The state does not belong to this window."))
        for node in clone.walk():
            node.properties.update(deepcopy(state.get("overrides", {}).get(node.id, {})))
        return clone

    def uses_v10(self) -> bool:
        """Format 10 adds the change, close and timer events and the 1.0 components."""
        return (
            any(
                flow.get("event", {}).get("kind", "").split(":")[0] in V10_EVENTS
                for flow in self.workflows
            )
            or any(node.kind in V10_KINDS for node in self.walk())
            or any(
                root.properties.get("menus")
                or root.properties.get("frame", "normal") != "normal"
                or root.properties.get("centered")
                or root.properties.get("on_top")
                or root.properties.get("fullscreen")
                for root in self.roots
            )
        )

    def uses_v11(self) -> bool:
        """Format 11 adds data collections."""
        return "collections" in self.metadata or any(
            node.kind == ComponentKind.CHART for node in self.walk()
        )

    def uses_v12(self) -> bool:
        """Format 12 adds per-component style, window background images and theme blocks."""

        def theme_block(value):
            if isinstance(value, dict):
                return value.get("op") in {"set_theme", "set_background"} or any(
                    theme_block(item) for item in value.values()
                )
            return isinstance(value, list) and any(theme_block(item) for item in value)

        return any(
            node.properties.get("background_image") or component_style(node.properties)
            for node in self.walk()
        ) or theme_block([*self.workflows, *self.metadata.get("functions", [])])

    def uses_v5(self) -> bool:
        """Keep writing v4 until a change requires the newer contract."""

        def new_logic(value):
            """Detect v5 semantics in complete logic or in still-incomplete blocks."""
            if isinstance(value, dict):
                if value.get("op") in {"go_state", "open_window", "close_window"} or value.get(
                    "scope"
                ) in {"window", "local"}:
                    return True
                if value.get("type") in {"mb_go_state", "mb_open_window", "mb_close_window"}:
                    return True
                fields = value.get("fields", {})
                if isinstance(fields, dict) and fields.get("SCOPE") in {"window", "local"}:
                    return True
                return any(new_logic(item) for item in value.values())
            if isinstance(value, list):
                return any(new_logic(item) for item in value)
            return False

        fields = {
            "spacing",
            "padding",
            "align",
            "distribute",
            "size_mode",
            "free_geometry",
            "icon",
            "tooltip",
        }
        return bool(
            self.format_version >= 5
            or self.application
            or self.windows
            or self.states
            or self.variables
            or self.map_layout
            or any(
                n.kind in {ComponentKind.SEPARATOR, ComponentKind.SPACER}
                or fields & n.properties.keys()
                for n in self.walk()
            )
            or any(f.get("states") for f in self.editable_flows)
            or new_logic(self.editable_flows)
        )

    @classmethod
    def empty(cls, name: str | None = None) -> Project:
        """Create an empty window to start a project."""
        name = tr("New application") if name is None else name
        root = create_component(ComponentKind.WINDOW)
        root.properties["title"] = name
        return cls(name=name, root=root)

    def find(self, component_id: str) -> Component | None:
        """Find a component by its stable identifier."""
        return next((node for node in self.walk() if node.id == component_id), None)

    def parent_of(self, component_id: str) -> Component | None:
        """Find the parent container; the root has no parent."""
        return next(
            (node for node in self.walk() if any(c.id == component_id for c in node.children)),
            None,
        )

    def add(self, parent_id: str, kind: ComponentKind) -> Component:
        """Insert a new component; inner windows are not allowed."""
        parent = self.find(parent_id)
        if parent is None or not parent.can_have_children:
            raise ProjectError(tr("Select a window or a container to insert the component."))
        if not parent.accepts(ComponentKind(kind)):
            raise ProjectError(
                tr("Add pages to a set of pages and controls to a page or container.")
            )
        child = create_component(kind)
        self._check_depth(parent, child)
        if child.kind == ComponentKind.PAGE:
            child.properties["title"] = tr("Page {number}").format(number=len(parent.children) + 1)
        child.geometry.update(
            x=min(20000, 16 + len(parent.children) * 16),
            y=min(20000, 16 + len(parent.children) * 16),
        )
        parent.children.append(child)
        return child

    def remove(self, component_id: str) -> str:
        """Remove a component and its children and return the parent's identifier."""
        parent = self.parent_of(component_id)
        if parent is None:
            raise ProjectError(tr("The main window cannot be deleted."))
        subtree = {node.id for node in self.find(component_id).walk()}
        from .logic import guard_removal

        guard_removal(self, subtree)
        self._check_last_page(parent)
        parent.children = [child for child in parent.children if child.id not in subtree]
        self._repair_initial_page(parent)
        for states in self.states.values():
            for state in states:
                overrides = state.get("overrides", {})
                for identifier in list(overrides):
                    if identifier in subtree:
                        del overrides[identifier]
                    elif overrides[identifier].get("initial_page") in subtree:
                        overrides[identifier].pop("initial_page", None)
        return parent.id

    def _check_last_page(self, parent: Component) -> None:
        """Keep a set of pages from being emptied when deleting or moving the last one."""
        if parent.kind == ComponentKind.PAGES and len(parent.children) == 1:
            raise ProjectError(tr("Keep at least one page in this set."))

    def _repair_initial_page(self, parent: Component) -> None:
        """Select the first remaining page if the initial one was removed."""
        if parent.kind == ComponentKind.PAGES:
            if parent.properties.get("initial_page") not in {node.id for node in parent.children}:
                parent.properties["initial_page"] = parent.children[0].id

    def _check_depth(self, parent: Component, child: Component) -> None:
        """Validate the structural limit before inserting or moving a subtree."""
        depth = 0
        ancestor = parent
        while self.parent_of(ancestor.id) is not None:
            ancestor = self.parent_of(ancestor.id)
            depth += 1

        def height(node: Component) -> int:
            """Count the subtree's maximum depth before insertion."""
            return max((height(item) + 1 for item in node.children), default=0)

        if depth + 1 + height(child) > 64:
            raise ProjectError(tr("The interface exceeds the limit of 64 container levels."))

    def move(self, component_id: str, parent_id: str, index: int | None = None) -> bool:
        """Move a subtree without changing IDs, rejecting cycles and invalid hierarchy.

        The index is an insertion position in the target list before removal. It
        represents the gaps before/after items while dragging. Returns False when
        the position does not change and changes nothing on error.
        """
        node, parent = self.find(component_id), self.find(parent_id)
        previous = self.parent_of(component_id)
        if node is None or parent is None or previous is None:
            raise ProjectError(tr("The main window cannot be moved."))
        if parent.id in {child.id for child in node.walk()}:
            raise ProjectError(tr("A component cannot be placed inside itself or its children."))
        if not parent.accepts(node.kind):
            raise ProjectError(tr("This destination does not accept that type of component."))
        self._check_depth(parent, node)
        original_window = self.window_of(node.id)
        target_window = self.window_of(parent.id)
        if original_window.id != target_window.id:
            subtree = {child.id for child in node.walk()}
            if any(
                subtree & set(state.get("overrides", {}))
                for state in self.states.get(original_window.id, [])
            ) or any(flow["event"]["component"] in subtree for flow in self.editable_flows):
                raise ProjectError(
                    tr("Review states and events before moving this component to another window.")
                )
        if previous.id != parent.id:
            self._check_last_page(previous)
        index = len(parent.children) if index is None else max(0, min(index, len(parent.children)))
        previous_index = previous.children.index(node)
        if previous is parent and previous_index < index:
            index -= 1
        if previous is parent and previous_index == index:
            return False
        previous.children.remove(node)
        parent.children.insert(index, node)
        self._repair_initial_page(previous)
        return True

    def duplicate(self, component_id: str) -> Component:
        """Duplicate a subtree with new IDs and remapped internal references."""
        parent, node = self.parent_of(component_id), self.find(component_id)
        if parent is None or node is None:
            raise ProjectError(tr("The main window cannot be duplicated."))
        from .logic import editable, duplicate_flows

        if not editable(self):
            raise ProjectError(tr("Reserved flows prevent duplication without migration."))
        clone = deepcopy(node)
        identifiers = {}
        for item in clone.walk():
            old_id = item.id
            item.id = new_id(item.kind.value)
            identifiers[old_id] = item.id
            if item.properties.get("code_name"):
                item.properties["code_name"] += "_" + item.id.rsplit("_", 1)[-1][:4]
        for item in clone.walk():
            if item.kind == ComponentKind.PAGES:
                item.properties["initial_page"] = identifiers[item.properties["initial_page"]]
        for key in ("title", "text"):
            if clone.properties.get(key):
                clone.properties[key] += " " + tr("(copy)")
                break
        clone.geometry["x"] = min(20000, clone.geometry["x"] + 16)
        clone.geometry["y"] = min(20000, clone.geometry["y"] + 16)
        duplicate_flows(self, identifiers)
        owner = self.window_of(component_id)
        for state in self.states.get(owner.id, []):
            overrides = state.setdefault("overrides", {})
            for old, new in identifiers.items():
                if old in overrides:
                    copied = deepcopy(overrides[old])
                    if copied.get("initial_page") in identifiers:
                        copied["initial_page"] = identifiers[copied["initial_page"]]
                    overrides[new] = copied
        parent.children.insert(parent.children.index(node) + 1, clone)
        return clone

    def set_geometry(self, component_id: str, geometry: dict[str, int]) -> bool:
        """Confirm the position/size of a free gesture as a single change."""
        node = self.find(component_id)
        parent = self.parent_of(component_id)
        if (
            node is None
            or parent is None
            or parent.layout != LayoutKind.FREE
            or parent.kind == ComponentKind.PAGES
        ):
            raise ProjectError(tr("Manual position and size require a free-layout container."))
        candidate = node.to_dict()
        candidate["geometry"].update(geometry)
        validated = Component.from_dict(candidate)
        if node.geometry == validated.geometry:
            return False
        node.geometry = validated.geometry
        return True

    def asset_paths(self) -> set[str]:
        """Return referenced images so Save As keeps the assets."""
        paths = {
            node.properties["source"]
            for node in self.walk()
            if node.kind == ComponentKind.IMAGE and node.properties.get("source")
        }
        for states in self.states.values():
            for state in states:
                for override in state.get("overrides", {}).values():
                    if override.get("source"):
                        paths.add(override["source"])
        for node in self.walk():
            for key in ("icon", "background_image"):
                if node.properties.get(key):
                    paths.add(node.properties[key])
            if isinstance(node.properties.get("web_page"), str):
                from .web import page_assets

                paths |= page_assets(node.properties["web_page"])
        icon = self.application.get("icon")
        if icon:
            paths.add(icon)
        return paths

    def to_dict(self) -> dict[str, Any]:
        """Serialize an independent snapshot of the document, keeping extensions."""
        result = {
            "format": FORMAT_NAME,
            "format_version": max(
                12 if self.uses_v12() else 4,
                11 if self.uses_v11() else 4,
                10 if self.uses_v10() else 4,
                9 if self.metadata.get("programming") else 4,
                8 if self.python_files else 4,
                6 if any(n.kind == ComponentKind.TERMINAL for n in self.walk()) else 4,
                self.format_version,
                5 if self.uses_v5() else 4,
            ),
            "id": self.id,
            "name": self.name,
            "ui": self.root.to_dict(),
            "workflows": deepcopy(self.workflows),
            "metadata": deepcopy(self.metadata),
        }
        if result["format_version"] >= 5:
            result.update(
                windows=[r.to_dict() for r in self.windows],
                states=deepcopy(self.states),
                entry_window=self.entry_window or self.root.id,
                variables=deepcopy(self.variables),
                map_layout=deepcopy(self.map_layout),
                application=deepcopy(self.application),
            )
        if self.python_files:
            result["python_files"] = list(self.python_files)
        return result

    @classmethod
    def from_dict(cls, value: Any) -> Project:
        """Validate the format, version and identifier uniqueness."""
        if not isinstance(value, dict) or value.get("format") != FORMAT_NAME:
            raise ProjectError(tr("This file is not a Makebench project."))
        version = value.get("format_version")
        if type(version) is not int or not 1 <= version <= FORMAT_VERSION:
            raise ProjectError(
                tr(
                    "Unsupported project version: {version}. Open it with a compatible version of Makebench."
                ).format(version=version)
            )
        for key in ("name", "id"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ProjectError(tr("The project needs a non-empty {key}.").format(key=key))
        root = Component.from_dict(value.get("ui"))
        if root.kind != ComponentKind.WINDOW:
            raise ProjectError(tr("The interface must start with a window."))
        raw_windows = value.get("windows", []) if version >= 5 else []
        if not isinstance(raw_windows, list) or len(raw_windows) > 128:
            raise ProjectError(tr("Invalid window list (at most 128)."))
        windows = [Component.from_dict(item) for item in raw_windows]
        if any(item.kind != ComponentKind.WINDOW for item in windows):
            raise ProjectError(tr("Each additional interface must be a window."))
        ids = [node.id for item in [root, *windows] for node in item.walk()]
        if len(set(ids)) != len(ids):
            raise ProjectError(tr("The project contains repeated component identifiers."))
        workflows = value.get("workflows", [])
        metadata = value.get("metadata", {})
        if not isinstance(workflows, list) or any(not isinstance(w, dict) for w in workflows):
            raise ProjectError(tr("The list of logic flows is invalid."))
        if not isinstance(metadata, dict):
            raise ProjectError(tr("Project metadata must be an object."))
        points = metadata.get("debug_breakpoints", [])
        if (
            not isinstance(points, list)
            or len(points) > 10000
            or any(
                not isinstance(point, dict)
                or (
                    point.get("file") == "source"
                    and (type(point.get("line")) is not int or not 1 <= point["line"] <= 1000000)
                )
                or (
                    point.get("file") == "block"
                    and (
                        not isinstance(point.get("block"), str)
                        or not isinstance(point.get("flow"), str)
                    )
                )
                or point.get("file") not in {"block", "source"}
                for point in points
            )
        ):
            raise ProjectError(tr("Invalid breakpoint list."))
        if "collections" in metadata:
            if version < 11:
                raise ProjectError(tr("Data collections require format 11 or later."))
            try:
                validate_collections(metadata["collections"])
            except ValueError as exc:
                raise ProjectError(str(exc)) from exc
        programming = metadata.get("programming")
        if programming is not None and (programming not in PROGRAMMING or version < 9):
            raise ProjectError(tr("Invalid programming choice; use blocks or python (format 9)."))
        from .source import validate_manifest, validate_module_name

        files = validate_manifest(value.get("python_files", []))
        if files and version < 8:
            raise ProjectError(tr("Python modules require format 8 or later."))
        for point in points:
            if point.get("path", "@actions") != "@actions":
                validate_module_name(point["path"])
        project = cls(
            name=value["name"],
            id=value["id"],
            root=root,
            python_files=list(files),
            workflows=deepcopy(workflows),
            metadata=deepcopy(metadata),
            windows=windows,
            states=deepcopy(value.get("states", {})) if version >= 5 else {},
            entry_window=value.get("entry_window") if version >= 5 else None,
            variables=deepcopy(value.get("variables", [])) if version >= 5 else [],
            map_layout=deepcopy(value.get("map_layout", {})) if version >= 5 else {},
            format_version=version if version >= 5 else 4,
            application=deepcopy(value.get("application", {})) if version >= 5 else {},
        )
        if version < 6 and any(n.kind == ComponentKind.TERMINAL for n in project.walk()):
            raise ProjectError(tr("The Terminal component requires format 6 or later."))
        if any(has_graph(f) for f in project.workflows):
            raise ProjectError(
                tr(
                    "This project uses the node editor, which was removed in Makebench 1.0. "
                    "Open it in Makebench 0.9."
                )
            )
        from .navigation import validate_navigation

        validate_navigation(project)
        from .logic import validate

        validate(project)
        return project
