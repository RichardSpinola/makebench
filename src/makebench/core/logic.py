# SPDX-License-Identifier: MIT
"""Portable logic: events and operations independent of Blockly and Qt."""

from __future__ import annotations

import ast
from copy import deepcopy
import keyword
import math
from typing import TYPE_CHECKING

from .project import ComponentKind, ProjectError, new_id
from makebench.i18n import tr

if TYPE_CHECKING:
    from .project import Project

LOGIC_VERSION = 1
TEXT_KINDS = {
    ComponentKind.LABEL,
    ComponentKind.BUTTON,
    ComponentKind.TEXT_INPUT,
    ComponentKind.CHECKBOX,
    ComponentKind.OUTPUT,
}


def editable(project: Project) -> bool:
    """Recognize logic of this version without reinterpreting older extensions."""
    return not project.workflows or project.metadata.get("logic_version") == LOGIC_VERSION


def create_flow(project: Project, component_id: str, states: list[str] | None = None) -> dict:
    """Bind window start or button click; reuse an existing binding."""
    if not editable(project):
        raise ProjectError(
            tr(
                "This project contains flows from another version. They were kept; editing requires migration."
            )
        )
    node = project.find(component_id)
    if node is None or node.kind not in {ComponentKind.WINDOW, ComponentKind.BUTTON}:
        raise ProjectError(tr("Select the window or a button to create an event."))
    event = {
        "kind": "start" if node.kind == ComponentKind.WINDOW else "click",
        "component": node.id,
    }
    for flow in project.workflows:
        if flow["event"] == event and sorted(flow.get("states", [])) == sorted(states or []):
            return flow
    project.metadata["logic_version"] = LOGIC_VERSION
    flow = {
        "id": new_id("flow"),
        "name": tr("On start")
        if event["kind"] == "start"
        else tr("Click: {text}").format(text=node.properties.get("text", tr("Button"))),
        "event": event,
        "body": [],
        "workspace": {},
    }
    if states:
        flow["states"] = list(states)
    project.workflows.append(flow)
    return flow


def is_draft(flow: dict) -> bool:
    """A blocks flow whose body is null is unfinished; Python events have no body."""
    return flow.get("body") is None and "function" not in flow


def is_python_event(flow: dict) -> bool:
    """Python events call a function of the actions file by name."""
    return "function" in flow


def suggest_function(project: Project, component_id: str, taken) -> str:
    """Build a readable, unused Python name for an event's function."""
    import re
    import unicodedata

    node = project.find(component_id)
    if node.kind == ComponentKind.WINDOW:
        base, suffix = node.properties.get("code_name") or node.properties.get("title", ""), "start"
    else:
        base, suffix = node.properties.get("code_name") or node.properties.get("text", ""), "click"
    ascii_text = unicodedata.normalize("NFKD", str(base)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:40] or "event"
    name = f"on_{slug}_{suffix}"
    taken = set(taken) | {f.get("function") for f in project.workflows}
    candidate, number = name, 2
    while candidate in taken or keyword.iskeyword(candidate):
        candidate, number = f"{name}_{number}", number + 1
    return candidate


def create_python_event(
    project: Project, component_id: str, source: str, states: list[str] | None = None
) -> tuple[dict, str]:
    """Bind an event to a function, adding an empty function when it does not exist yet."""
    flow = create_flow(project, component_id, states)
    if is_python_event(flow):
        return flow, source
    names, _ = function_names(source)
    name = suggest_function(project, component_id, names)
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
    for flow in project.workflows:
        if not isinstance(flow.get("id"), str) or not flow["id"] or flow["id"] in seen_flows:
            raise ProjectError(tr("Missing or repeated flow identifier."))
        seen_flows.add(flow["id"])
        if not isinstance(flow.get("name"), str):
            raise ProjectError(tr("The flow name must be text."))
        event = flow.get("event", {})
        if not isinstance(event, dict):
            raise ProjectError(tr("Invalid event."))
        node = project.find(event.get("component"))
        expected = ComponentKind.WINDOW if event.get("kind") == "start" else ComponentKind.BUTTON
        if event.get("kind") not in {"start", "click"} or node is None or node.kind != expected:
            raise ProjectError(tr("The event must point to the window or an existing button."))
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
                        else {ComponentKind.PROGRESS}
                        if attribute == "value"
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
                else:
                    raise ProjectError(tr("Unknown expression: {op}.").format(op=op))
            elif op in {"log", "message"}:
                expr("value")
            elif op in {"set_text", "set_enabled", "set_value"}:
                target(
                    value.get("component"),
                    TEXT_KINDS
                    if op == "set_text"
                    else {ComponentKind.PROGRESS}
                    if op == "set_value"
                    else None,
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
            elif op == "call":
                text("function", True)
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
    result = {flow["event"]["component"]}

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
    for flow in project.workflows:
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
