# SPDX-License-Identifier: MIT
"""Model actions and starting values, with no graphical dependency."""

from .project import new_id
from .source import default_names
from makebench.i18n import tr

OPS = [
    ("terminal_start", tr("Start terminal")),
    ("terminal_send", tr("Send to terminal")),
    ("terminal_stop", tr("Stop terminal")),
    ("log", tr("Write to output")),
    ("message", tr("Show message")),
    ("set_text", tr("Change text")),
    ("set_enabled", tr("Enable component")),
    ("set_value", tr("Change value")),
    ("set_options", tr("Change options")),
    ("set_rows", tr("Change table rows")),
    ("add_row", tr("Add table row")),
    ("set_chart", tr("Change chart data")),
    ("set_theme", tr("Change window theme")),
    ("set_background", tr("Change window background")),
    ("assign", tr("Set variable")),
    ("call", tr("Call Python function")),
    ("script", tr("Run Bash")),
    ("run", tr("Run program")),
    ("ask", tr("Ask")),
    ("confirm", tr("Confirm")),
    ("go_state", tr("Go to state")),
    ("open_window", tr("Open window")),
    ("close_window", tr("Close window")),
    ("show_page", tr("Show page")),
    ("if", tr("Condition")),
    ("repeat", tr("Repeat")),
]


def literal(value=""):
    """Create a neutral expression with its own id, preservable in comments."""
    return {"id": new_id("value"), "op": "literal", "value": value}


def default_block(op, project, window):
    """Valid starting values when compatible controls exist; never runs anything."""
    node = {"id": new_id("block"), "op": op}
    components = list(project.find(window).walk())
    if op in {"log", "message", "set_text", "assign", "call"}:
        node["value"] = literal(tr("Hello!"))
    if op in {
        "set_text",
        "set_enabled",
        "set_value",
        "set_options",
        "set_rows",
        "add_row",
        "set_chart",
        "show_page",
    }:
        kinds = {
            "set_text": {
                "label",
                "button",
                "text_input",
                "text_area",
                "choice",
                "date",
                "checkbox",
                "output",
            },
            "set_options": {"choice"},
            "set_rows": {"table"},
            "add_row": {"table"},
            "set_chart": {"chart"},
            "set_value": {"progress", "number", "slider"},
            "show_page": {"page"},
        }.get(op)
        target = next((n for n in components if kinds is None or n.kind.value in kinds), None)
        if not target:
            raise ValueError(tr("Insert a compatible component before creating this action."))
        node["component"] = target.id
    if op.startswith("terminal_"):
        target = next((n for n in components if n.kind.value == "terminal"), None)
        if target is None:
            raise ValueError(tr("Insert a Terminal component in this window."))
        node["component"] = target.id
        if op == "terminal_start":
            node.update(
                program=literal(""), arguments={"id": new_id("value"), "op": "list", "items": []}
            )
        if op == "terminal_send":
            node["value"] = literal("help\n")
    if op == "set_theme":
        node.update(theme="dark", value=literal(""))
    if op == "set_background":
        node["value"] = literal("#336699")
    if op == "set_enabled":
        node["value"] = literal(True)
    if op == "set_value":
        node["value"] = literal(50)
    if op == "set_options":
        node["value"] = {
            "id": new_id("value"),
            "op": "list",
            "items": [literal(tr("Option 1")), literal(tr("Option 2"))],
        }
    if op == "set_chart":
        node["labels"] = {
            "id": new_id("value"),
            "op": "list",
            "items": [literal("A"), literal("B")],
        }
        node["value"] = {
            "id": new_id("value"),
            "op": "list",
            "items": [literal(3), literal(5)],
        }
    if op == "set_rows":
        node["value"] = {"id": new_id("value"), "op": "list", "items": []}
    if op == "add_row":
        node["value"] = {
            "id": new_id("value"),
            "op": "list",
            "items": [literal(tr("Cell 1")), literal(tr("Cell 2"))],
        }
    if op == "assign":
        node.update(name=default_names()["variable"], scope="project")
    if op == "call":
        node["function"] = default_names()["function"]
    if op in {"run", "script"}:
        node.update(arguments={"id": new_id("value"), "op": "list", "items": []}, admin=False)
        node["program" if op == "run" else "source"] = literal(
            "uname" if op == "run" else tr('printf "Hello, Linux\\n"')
        )
    if op == "ask":
        node.update(
            kind="text",
            prompt=literal(tr("What is your name?")),
            options={"id": new_id("value"), "op": "list", "items": []},
            name=default_names()["answer"],
        )
    if op == "confirm":
        node["prompt"] = literal(tr("Do you want to continue?"))
    if op == "go_state":
        node["state"] = next(iter(project.states.get(window, [])), {"id": "@default"})["id"]
    if op == "open_window":
        node.update(
            window=next((r.id for r in project.roots if r.id != window), window),
            close_current=False,
        )
    if op == "if":
        node.update(condition=literal(True), then=[], **{"else": []})
    if op == "repeat":
        node.update(count=literal(3), body=[])
    return node
