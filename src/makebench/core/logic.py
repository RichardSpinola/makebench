# SPDX-License-Identifier: MIT
"""Portable logic: events and operations independent of Blockly and Qt."""

from __future__ import annotations

import ast
from copy import deepcopy
import keyword
import math
from typing import TYPE_CHECKING

from .datamodel import find_collection, find_field
from .menus import menu_items
from .project import ComponentKind, ProjectError, new_id
from makebench.i18n import tr

if TYPE_CHECKING:
    from .project import Project

LOGIC_VERSION = 1
DATA_OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "contains"}
TEXT_KINDS = {
    ComponentKind.LABEL,
    ComponentKind.BUTTON,
    ComponentKind.TEXT_INPUT,
    ComponentKind.TEXT_AREA,
    ComponentKind.CHOICE,
    ComponentKind.DATE,
    ComponentKind.CHECKBOX,
    ComponentKind.OUTPUT,
}
VALUE_KINDS = {ComponentKind.PROGRESS, ComponentKind.NUMBER, ComponentKind.SLIDER}


EVENT_TARGETS = {
    "start": {ComponentKind.WINDOW},
    "close": {ComponentKind.WINDOW},
    "timer": {ComponentKind.WINDOW},
    "menu": {ComponentKind.WINDOW},
    "click": {ComponentKind.BUTTON},
    "change": {
        ComponentKind.TEXT_INPUT,
        ComponentKind.TEXT_AREA,
        ComponentKind.CHOICE,
        ComponentKind.DATE,
        ComponentKind.CHECKBOX,
        ComponentKind.NUMBER,
        ComponentKind.SLIDER,
        ComponentKind.TABLE,
    },
}
EVENT_SUFFIX = {
    "start": "start",
    "close": "close",
    "timer": "timer",
    "menu": "menu",
    "click": "click",
    "change": "change",
}


def event_family(kind: str) -> str:
    """`menu:save` belongs to the menu family; other events are their own."""
    return kind.split(":")[0]


def event_choices(project: Project) -> list[tuple[str, str, str]]:
    """Every (label, component id, event kind) a flow can be bound to, in document order."""
    labels = {
        "start": tr("On start:"),
        "close": tr("On close:"),
        "timer": tr("On timer:"),
        "click": tr("On click:"),
        "change": tr("On change:"),
    }
    choices = []
    for node in project.walk():
        for kind, kinds in EVENT_TARGETS.items():
            if kind == "menu":
                for menu, item in menu_items(node.properties):
                    prefix = (
                        project.window_of(node.id).properties.get("title", tr("Interface")) + " › "
                        if len(project.roots) > 1
                        else ""
                    )
                    label = tr("On menu:") + " " + prefix + menu["text"] + " › " + item["text"]
                    choices.append((label, node.id, "menu:" + item["id"]))
            elif node.kind in kinds:
                prefix = (
                    project.window_of(node.id).properties.get("title", tr("Interface")) + " › "
                    if len(project.roots) > 1
                    else ""
                )
                choices.append((labels[kind] + " " + prefix + node.display_name, node.id, kind))
    return choices


def default_event_kind(node) -> str | None:
    """The event a component fires when none is named: start, click or change."""
    return next(
        (kind for kind in ("start", "click", "change") if node.kind in EVENT_TARGETS[kind]), None
    )


def editable(project: Project) -> bool:
    """Recognize logic of this version without reinterpreting older extensions."""
    return not project.workflows or project.metadata.get("logic_version") == LOGIC_VERSION


def create_flow(
    project: Project, component_id: str, states: list[str] | None = None, kind: str | None = None
) -> dict:
    """Bind an event of a window or component; reuse an existing binding."""
    if not editable(project):
        raise ProjectError(
            tr(
                "This project contains flows from another version. They were kept; editing requires migration."
            )
        )
    node = project.find(component_id)
    kind = kind or (node and default_event_kind(node))
    family = event_family(kind or "")
    if (
        node is None
        or family not in EVENT_TARGETS
        or node.kind not in EVENT_TARGETS[family]
        or (family == "menu" and kind[5:] not in {i["id"] for _, i in menu_items(node.properties)})
    ):
        raise ProjectError(tr("Select the window or a control that can fire this event."))
    event = {"kind": kind, "component": node.id}
    for flow in project.workflows:
        if flow["event"] == event and sorted(flow.get("states", [])) == sorted(states or []):
            return flow
    project.metadata["logic_version"] = LOGIC_VERSION
    flow = {
        "id": new_id("flow"),
        "name": event_name(event["kind"], node),
        "event": event,
        "body": [],
        "workspace": {},
    }
    if states:
        flow["states"] = list(states)
    project.workflows.append(flow)
    return flow


def event_name(kind: str, node) -> str:
    """Readable default name of a new flow."""
    text = node.properties.get("text", "") or node.properties.get("placeholder", "")
    return {
        "start": lambda: tr("On start"),
        "close": lambda: tr("On close"),
        "timer": lambda: tr("On timer"),
        "menu": lambda: tr("Menu: {text}").format(text=menu_text(node, kind)),
        "click": lambda: tr("Click: {text}").format(text=text or tr("Button")),
        "change": lambda: tr("Change: {text}").format(text=text or tr("Control")),
    }[event_family(kind)]()


def menu_text(node, kind: str) -> str:
    """The text of the menu item an event `menu:<id>` names."""
    for _menu, item in menu_items(node.properties):
        if "menu:" + item["id"] == kind:
            return item["text"]
    return kind[5:]


def is_draft(flow: dict) -> bool:
    """A blocks flow whose body is null is unfinished; Python events have no body."""
    return flow.get("body") is None and "function" not in flow


def is_python_event(flow: dict) -> bool:
    """Python events call a function of the actions file by name."""
    return "function" in flow


def block_functions(project: Project) -> list[dict]:
    """Return the project's block functions, a list kept in the metadata."""
    return project.metadata.get("functions", [])


def find_unit(project: Project, unit_id: str | None) -> dict | None:
    """Find an event flow or a block function by its identifier."""
    return next(
        (item for item in [*project.workflows, *block_functions(project)] if item["id"] == unit_id),
        None,
    )


def modules(project: Project) -> list[str]:
    """Return the block module names in use, sorted, for the sidebar and menus."""
    units = [*project.workflows, *block_functions(project)]
    return sorted({unit["module"] for unit in units if unit.get("module")}, key=str.casefold)


def set_module(project: Project, unit_id: str, module: str) -> None:
    """Group an event or a function under a module; an empty name ungroups it."""
    unit = find_unit(project, unit_id)
    if unit is None:
        raise ProjectError(tr("The flow no longer exists."))
    previous = unit.get("module")
    module = " ".join(module.split())
    if module:
        unit["module"] = module
    else:
        unit.pop("module", None)
    try:
        validate(project)
    except ProjectError:
        unit.pop("module", None)
        if previous is not None:
            unit["module"] = previous
        raise


def create_block_function(project: Project, name: str, params: list[str] | None = None) -> dict:
    """Add an empty block function; the name and parameters must be Python names."""
    if not editable(project):
        raise ProjectError(
            tr(
                "This project contains flows from another version. They were kept; editing requires migration."
            )
        )
    function = {
        "id": new_id("function"),
        "name": name.strip(),
        "params": list(params or []),
        "body": [],
        "workspace": {},
    }
    project.metadata["logic_version"] = LOGIC_VERSION
    project.metadata.setdefault("functions", []).append(function)
    try:
        validate(project)
    except ProjectError:
        project.metadata["functions"].remove(function)
        if not project.metadata["functions"]:
            del project.metadata["functions"]
        raise
    return function


def function_calls(project: Project, function_id: str) -> list[str]:
    """Name the events and functions whose blocks call this function."""
    found = []

    def calls(item):
        """Look for a call by structure, never by text."""
        if isinstance(item, dict):
            return (
                item.get("op") == "call_function" and item.get("function") == function_id
            ) or any(calls(child) for child in item.values())
        if isinstance(item, list):
            return any(calls(child) for child in item)
        return False

    for unit in [*project.workflows, *block_functions(project)]:
        if unit["id"] != function_id and calls(unit.get("body")):
            found.append(unit["name"])
    return found


def called_functions(unit: dict) -> list[str]:
    """List, once each and in order, the block functions a flow or function calls."""
    found = []

    def visit(item):
        """Walk the block tree by structure, never by text."""
        if isinstance(item, dict):
            if item.get("op") == "call_function" and item.get("function") not in found:
                found.append(item.get("function"))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(unit.get("body"))
    return found


def suggest_function(project: Project, component_id: str, taken, kind: str | None = None) -> str:
    """Build a readable, unused Python name for an event's function."""
    import re
    import unicodedata

    node = project.find(component_id)
    kind = kind or default_event_kind(node)
    if node.kind == ComponentKind.WINDOW:
        base = node.properties.get("code_name") or node.properties.get("title", "")
    else:
        base = (
            node.properties.get("code_name")
            or node.properties.get("text", "")
            or node.properties.get("placeholder", "")
        )
    suffix = EVENT_SUFFIX[event_family(kind)] + (kind[4:].replace(":", "_") if ":" in kind else "")
    ascii_text = unicodedata.normalize("NFKD", str(base)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:40] or "event"
    name = f"on_{slug}_{suffix}"
    taken = set(taken) | {f.get("function") for f in project.workflows}
    candidate, number = name, 2
    while candidate in taken or keyword.iskeyword(candidate):
        candidate, number = f"{name}_{number}", number + 1
    return candidate


def create_python_event(
    project: Project,
    component_id: str,
    source: str,
    states: list[str] | None = None,
    kind: str | None = None,
) -> tuple[dict, str]:
    """Bind an event to a function, adding an empty function when it does not exist yet."""
    flow = create_flow(project, component_id, states, kind)
    if is_python_event(flow):
        return flow, source
    names, _ = function_names(source)
    name = suggest_function(project, component_id, names, flow["event"]["kind"])
    for key in ("body", "workspace", "errors"):
        flow.pop(key, None)
    flow["function"] = name
    stub = f"def {name}(ctx):\n    pass\n"
    text = source.rstrip("\n")
    return flow, (text + "\n\n\n" if text else "") + stub


def function_names(source: str) -> tuple[list[str], str | None]:
    """Inspect signatures without importing or running the Python file."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return [], tr("Python functions: {error}").format(error=exc)
    names = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    return names, None


def validate(project: Project) -> None:
    """Reject invalid events/references and limit logic depth and size.

    body=None is an incomplete draft; its workspace is kept but receives no
    runnable code. Older reserved flows are not changed.
    """
    version = project.metadata.get("logic_version")
    if version is None:
        return
    if type(version) is not int or version != LOGIC_VERSION:
        raise ProjectError(tr("Unsupported logic version; use a compatible Makebench."))
    seen_flows, seen_events = set(), set()
    functions = project.metadata.get("functions", [])
    if not isinstance(functions, list) or len(functions) > 512:
        raise ProjectError(tr("Invalid function list (at most 512)."))
    signatures, names = {}, set()
    for function in functions:
        if not isinstance(function, dict) or not isinstance(function.get("id"), str):
            raise ProjectError(tr("Missing or repeated flow identifier."))
        name, params = function.get("name"), function.get("params")
        if (
            not isinstance(name, str)
            or not name.isidentifier()
            or keyword.iskeyword(name)
            or name.startswith("_")
            or name in names
        ):
            raise ProjectError(tr("Each function needs its own Python name."))
        if (
            not isinstance(params, list)
            or len(params) > 8
            or len(set(map(str, params))) != len(params)
            or any(
                not isinstance(item, str)
                or not item.isidentifier()
                or keyword.iskeyword(item)
                or item in {"ctx", "variables", "local_variables"}
                for item in params
            )
        ):
            raise ProjectError(tr("Function inputs must be up to 8 different Python names."))
        names.add(name)
        signatures[function["id"]] = len(params)
    all_states = {"@default", *[s["id"] for items in project.states.values() for s in items]}
    for flow in [*project.workflows, *functions]:
        if not isinstance(flow.get("id"), str) or not flow["id"] or flow["id"] in seen_flows:
            raise ProjectError(tr("Missing or repeated flow identifier."))
        seen_flows.add(flow["id"])
        if not isinstance(flow.get("name"), str):
            raise ProjectError(tr("The flow name must be text."))
        module = flow.get("module")
        if module is not None and (
            not isinstance(module, str) or not module.strip() or len(module) > 60
        ):
            raise ProjectError(tr("A module name must be 1 to 60 characters."))
        in_function = any(flow is item for item in functions)
        if in_function:
            state_ids = all_states
            if "function" in flow or "event" in flow:
                raise ProjectError(tr("A block function cannot have an event."))
        event = {} if in_function else flow.get("event", {})
        if not in_function:
            if not isinstance(event, dict):
                raise ProjectError(tr("Invalid event."))
            node = project.find(event.get("component"))
            family = event_family(event.get("kind") if isinstance(event.get("kind"), str) else "")
            if family not in EVENT_TARGETS or node is None:
                raise ProjectError(tr("The event must point to the window or an existing control."))
            if node.kind not in EVENT_TARGETS[family]:
                raise ProjectError(tr("This component cannot fire that event."))
            if family == "menu" and event["kind"][5:] not in {
                i["id"] for _, i in menu_items(node.properties)
            }:
                raise ProjectError(tr("The menu item of this event does not exist."))
            states = flow.get("states", [])
            owner = project.window_of(node.id)
            state_ids = {"@default", *[item["id"] for item in project.states.get(owner.id, [])]}
            if (
                not isinstance(states, list)
                or any(not isinstance(item, str) or item not in state_ids for item in states)
                or len(states) != len(set(states))
            ):
                raise ProjectError(tr("Invalid state filter."))
            key = (event["kind"], node.id, tuple(sorted(states)))
            if key in seen_events:
                raise ProjectError(tr("There is more than one flow for the same event."))
            seen_events.add(key)
            if "function" in flow:
                name = flow["function"]
                if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
                    raise ProjectError(tr("The event function must be a Python name."))
                if any(key in flow for key in ("body", "workspace")):
                    raise ProjectError(tr("A Python event cannot also have blocks."))
                continue
        if not isinstance(flow.get("workspace", {}), dict):
            raise ProjectError(tr("The visual state of the blocks must be an object."))
        if not isinstance(flow.get("errors", []), list) or any(
            not isinstance(e, str) for e in flow.get("errors", [])
        ):
            raise ProjectError(tr("Invalid block diagnostics."))
        if flow.get("editor", "blocks") != "blocks":
            raise ProjectError(tr("Unknown behavior editor."))
        ids: set[str] = set()

        def target(value, kinds=None):
            """Validate a reference without depending on the UI toolkit."""
            found = project.find(value)
            if found is None or (kinds and found.kind not in kinds):
                raise ProjectError(tr("A block points to a missing or incompatible component."))

        def visit(value, expression=False, depth=0):
            """Validate a tree's nodes without accepting arbitrary Python as an expression."""
            if depth > 48 or len(ids) >= 5000:
                raise ProjectError(tr("Logic exceeds 48 levels or 5000 blocks per event."))
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("id"), str)
                or not value["id"]
                or value["id"] in ids
            ):
                raise ProjectError(tr("Block without a unique identifier."))
            ids.add(value["id"])
            if "comment" in value and not isinstance(value["comment"], str):
                raise ProjectError(tr("A block comment must be text."))
            op = value.get("op")

            def expr(key):
                """Validate a required value input."""
                visit(value.get(key), True, depth + 1)

            def body(key):
                """Validate an ordered sequence of statements."""
                sequence(value.get(key), depth + 1)

            def text(key, identifier=False):
                """Validate text fields and Python function names."""
                item = value.get(key)
                if (
                    not isinstance(item, str)
                    or not item.strip()
                    or (
                        identifier
                        and (
                            not item.isidentifier()
                            or keyword.iskeyword(item)
                            or item.startswith("_")
                        )
                    )
                ):
                    raise ProjectError(tr("Invalid field in block: {key}.").format(key=key))

            def call():
                """Validate a call to a block function and its inputs."""
                args = value.get("args")
                if value.get("function") not in signatures:
                    raise ProjectError(tr("A block calls a function that does not exist."))
                if not isinstance(args, list) or len(args) != signatures[value["function"]]:
                    raise ProjectError(tr("A function call has the wrong number of inputs."))
                for item in args:
                    visit(item, True, depth + 1)

            def collection():
                """Validate the collection a data block points to and return it."""
                found = find_collection(project.metadata, value.get("collection"))
                if found is None:
                    raise ProjectError(tr("A block points to a collection that does not exist."))
                return found

            def data_field(key, owner, allow_id=False, optional=False, number=False):
                """Validate a field of the collection, by id."""
                name = value.get(key)
                if name is None and optional:
                    return
                if allow_id and name == "id" and not number:
                    return
                found = find_field(owner, name) if isinstance(name, str) else None
                if found is None or (number and found["type"] != "number"):
                    raise ProjectError(tr("A block points to a missing or incompatible field."))

            def data_filter(owner):
                """Validate the optional 'where field operator value' part of a query."""
                data_field("field", owner, allow_id=True, optional=True)
                if value.get("field") is not None:
                    if value.get("operator") not in DATA_OPERATORS:
                        raise ProjectError(tr("Unknown operator."))
                    expr("value")

            def data_values(owner):
                """Validate the field inputs of an add or change block."""
                entries = value.get("values")
                if not isinstance(entries, list):
                    raise ProjectError(tr("Invalid field in block: {key}.").format(key="values"))
                seen = set()
                for entry in entries:
                    name = entry.get("field") if isinstance(entry, dict) else None
                    if (
                        not isinstance(entry, dict)
                        or set(entry) != {"field", "value"}
                        or not isinstance(name, str)
                        or find_field(owner, name) is None
                        or name in seen
                    ):
                        raise ProjectError(tr("A block points to a missing or incompatible field."))
                    seen.add(name)
                    visit(entry["value"], True, depth + 1)

            if expression:
                if op == "literal":
                    item = value.get("value")
                    if type(item) not in {str, bool, int, float} or (
                        type(item) is float and not math.isfinite(item)
                    ):
                        raise ProjectError(tr("Invalid literal value."))
                elif op == "list":
                    items = value.get("items")
                    if not isinstance(items, list) or len(items) > 256:
                        raise ProjectError(tr("A value list accepts up to 256 items."))
                    for item in items:
                        visit(item, True, depth + 1)
                elif op == "variable":
                    text("name")
                    if value.get("scope", "project") not in {"project", "window", "local"}:
                        raise ProjectError(tr("Invalid scope."))
                elif op == "read":
                    attribute = value.get("attribute")
                    kinds = (
                        TEXT_KINDS
                        if attribute == "text"
                        else {ComponentKind.CHECKBOX}
                        if attribute == "checked"
                        else VALUE_KINDS
                        if attribute == "value"
                        else {ComponentKind.TABLE}
                        if attribute == "selected"
                        else set()
                    )
                    if not kinds:
                        raise ProjectError(tr("Unknown read property."))
                    target(value.get("component"), kinds)
                elif op == "binary":
                    if value.get("operator") not in {
                        "+",
                        "-",
                        "*",
                        "/",
                        "==",
                        "!=",
                        "<",
                        "<=",
                        ">",
                        ">=",
                        "and",
                        "or",
                    }:
                        raise ProjectError(tr("Unknown operator."))
                    expr("left")
                    expr("right")
                elif op == "join":
                    expr("left")
                    expr("right")
                elif op == "call_function":
                    call()
                elif op == "data_find":
                    owner = collection()
                    data_filter(owner)
                    data_field("order", owner, allow_id=True, optional=True)
                    if type(value.get("descending", False)) is not bool:
                        raise ProjectError(
                            tr("Invalid field in block: {key}.").format(key="descending")
                        )
                elif op == "data_get" or op == "data_name":
                    collection()
                    expr("record_id")
                elif op == "data_count":
                    data_filter(collection())
                elif op == "data_sum":
                    owner = collection()
                    data_field("sum", owner, number=True)
                    data_filter(owner)
                elif op == "record_field":
                    data_field("field", collection(), allow_id=True)
                    expr("record")
                elif op == "data_last_id":
                    pass
                else:
                    raise ProjectError(tr("Unknown expression: {op}.").format(op=op))
            elif op in {"log", "message"}:
                expr("value")
            elif op == "set_options":
                target(value.get("component"), {ComponentKind.CHOICE})
                expr("value")
            elif op in {"set_rows", "add_row"}:
                target(value.get("component"), {ComponentKind.TABLE})
                expr("value")
            elif op in {"set_text", "set_enabled", "set_value"}:
                target(
                    value.get("component"),
                    TEXT_KINDS if op == "set_text" else VALUE_KINDS if op == "set_value" else None,
                )
                expr("value")
            elif op in {"terminal_start", "terminal_send", "terminal_stop"}:
                target(value.get("component"), {ComponentKind.TERMINAL})
                if op == "terminal_start":
                    expr("program")
                    expr("arguments")
                if op == "terminal_send":
                    expr("value")
            elif op == "show_page":
                target(value.get("component"), {ComponentKind.PAGE})
            elif op in {"go_state", "open_window", "close_window"}:
                if op == "go_state" and value.get("state") not in state_ids:
                    raise ProjectError(tr("The transition points to a state that does not exist."))
                if op == "open_window":
                    target(value.get("window"), {ComponentKind.WINDOW})
                    if type(value.get("close_current", False)) is not bool:
                        raise ProjectError(tr("Invalid close-window option."))
            elif op == "assign":
                text("name")
                expr("value")
                if value.get("scope", "project") not in {"project", "window", "local"}:
                    raise ProjectError(tr("Invalid scope."))
            elif op == "if":
                expr("condition")
                body("then")
                body("else")
            elif op == "repeat":
                expr("count")
                body("body")
            elif op == "for_each":
                text("name")
                expr("source")
                if value.get("scope") != "local":
                    raise ProjectError(tr("Invalid scope."))
                body("body")
            elif op == "data_add":
                data_values(collection())
            elif op == "data_update":
                data_values(collection())
                expr("record_id")
            elif op == "data_delete":
                collection()
                expr("record_id")
            elif op == "call":
                text("function", True)
                expr("value")
            elif op == "call_function":
                call()
            elif op == "return":
                if not in_function:
                    raise ProjectError(tr("“Return” only works inside a function."))
                if "value" in value:
                    expr("value")
            elif op in {"run", "script"}:
                expr("program" if op == "run" else "source")
                expr("arguments")
                if type(value.get("admin")) is not bool:
                    raise ProjectError(
                        tr("Administrative permission must be declared in the block.")
                    )
            elif op == "ask":
                if value.get("kind") not in {"text", "choice", "file", "directory"}:
                    raise ProjectError(tr("Unknown question type."))
                text("name")
                expr("prompt")
                expr("options")
                if value.get("scope", "project") not in {"project", "window", "local"}:
                    raise ProjectError(tr("Invalid scope in the question."))
            elif op == "confirm":
                expr("prompt")
            else:
                raise ProjectError(tr("Unknown operation: {op}.").format(op=op))

        def sequence(items, depth=0):
            """Validate a list of statements without interpreting their effects."""
            if not isinstance(items, list):
                raise ProjectError(tr("The block sequence must be a list."))
            for item in items:
                visit(item, False, depth)

        if flow.get("body") is not None:
            sequence(flow["body"])
        elif not flow.get("workspace"):
            raise ProjectError(tr("An incomplete flow must keep its blocks."))


def referenced_components(flow: dict) -> set[str]:
    """Collect component references without confusing text with identifiers."""
    result = {flow["event"]["component"]} if "event" in flow else set()

    def walk(item):
        """Walk only the logic representation, ignoring the Blockly view."""
        if isinstance(item, dict):
            if "component" in item:
                result.add(item["component"])
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(flow.get("body"))
    return result


def guard_removal(project: Project, ids: set[str]) -> None:
    """Prevent deleting targets used by logic, explaining how to resolve the link."""
    if not editable(project) and project.workflows:
        raise ProjectError(tr("Reserved flows require reference validation before deleting."))
    for flow in [*project.workflows, *block_functions(project)]:
        if is_draft(flow) or ids & referenced_components(flow):
            raise ProjectError(
                tr(
                    "Review or remove the flow ‘{name}’ in the Logic tab before deleting this component."
                ).format(name=flow["name"])
            )


def duplicate_flows(project: Project, identifiers: dict[str, str]) -> None:
    """Copy events of the duplicated subtree and remap only internal references."""
    copies = []
    for flow in project.workflows:
        if flow["event"]["component"] not in identifiers:
            continue
        if is_draft(flow):
            raise ProjectError(tr("Complete this component's blocks before duplicating it."))
        clone = deepcopy(flow)
        if is_python_event(flow):
            clone.update(id=new_id("flow"), name=flow["name"] + " " + tr("(copy)"))
            clone["event"]["component"] = identifiers[flow["event"]["component"]]
            copies.append(clone)
            continue
        clone.update(
            id=new_id("flow"),
            name=flow["name"] + " " + tr("(copy)"),
            workspace={
                "workspaceComments": deepcopy(
                    flow.get("workspace", {}).get("workspaceComments", [])
                )
            },
        )

        def remap(item):
            """Regenerate node IDs and remap targets keeping external references."""
            if isinstance(item, dict):
                if "id" in item:
                    item["id"] = new_id("block")
                if item.get("component") in identifiers:
                    item["component"] = identifiers[item["component"]]
                for value in item.values():
                    remap(value)
            elif isinstance(item, list):
                for value in item:
                    remap(value)

        remap(clone["event"])
        remap(clone["body"])
        copies.append(clone)
    project.workflows.extend(copies)
