"""Behavior templates: real neutral data, with no execution or Qt dependency."""

from .project import ComponentKind, ProjectError, new_id
from .logic_defaults import default_block, literal
from makebench.i18n import tr

TEMPLATES = [
    ("open_window", tr("Open window")),
    ("go_state", tr("Change state")),
    ("message", tr("Show message")),
    ("read_field", tr("Read field")),
    ("set_text", tr("Change text")),
    ("save_value", tr("Store value in variable")),
    ("validate_input", tr("Validate input")),
    ("run", tr("Run task")),
    ("confirm", tr("Ask for confirmation")),
]


def behavior_template(kind, project, window):
    """Return valid blocks for the given window or explain the missing precondition.

    References are real components. Storing a value keeps it in run-time memory and
    does not write files. Creating this data never starts code or processes.
    """
    root = project.find(window)
    if root is None or root.kind != ComponentKind.WINDOW:
        raise ProjectError(tr("Select an interface."))
    fields = [n for n in root.walk() if n.kind == ComponentKind.TEXT_INPUT]

    def read():
        """Build a read of the first field in this interface."""
        if not fields:
            raise ProjectError(tr("Add a text field to this interface first."))
        return {"id": new_id("value"), "op": "read", "component": fields[0].id, "attribute": "text"}

    if kind == "open_window" and len(project.roots) < 2:
        raise ProjectError(tr("Create another interface in the Map before opening a window."))
    if kind == "go_state" and not project.states.get(window):
        raise ProjectError(tr("Create a state in the Map before using this template."))
    if kind in {"open_window", "go_state", "message", "set_text", "run"}:
        try:
            return [default_block(kind, project, window)]
        except ValueError as exc:
            raise ProjectError(str(exc)) from exc
    if kind in {"read_field", "save_value"}:
        node = default_block("assign", project, window)
        node["value"] = read() if kind == "read_field" else literal(tr("New value"))
        return [node]
    if kind == "validate_input":
        node = default_block("if", project, window)
        node["condition"] = {
            "id": new_id("value"),
            "op": "binary",
            "operator": "!=",
            "left": read(),
            "right": literal(""),
        }
        success = default_block("message", project, window)
        success["value"] = literal(tr("Input filled in."))
        failure = default_block("message", project, window)
        failure["value"] = literal(tr("Fill in the field before continuing."))
        node.update(then=[success], **{"else": [failure]})
        return [node]
    if kind == "confirm":
        confirm = default_block("confirm", project, window)
        return [confirm]
    raise ProjectError(tr("Unknown behavior template."))


def append_behavior(flow, blocks):
    """Append actions keeping earlier IDs/comments; only the derived view is invalidated."""
    if flow.get("body") is None:
        raise ProjectError(tr("Complete the loose blocks before inserting a template."))
    from copy import deepcopy

    flow["body"].extend(deepcopy(blocks))
    flow["workspace"] = {
        "workspaceComments": deepcopy(flow.get("workspace", {}).get("workspaceComments", []))
    }
