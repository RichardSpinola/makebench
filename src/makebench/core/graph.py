# SPDX-License-Identifier: MIT
"""Free graph independent of Blockly: ports, validation and state-machine compiler."""

from __future__ import annotations
from copy import deepcopy
import json
import keyword
import math
from .project import ComponentKind, ProjectError, new_id
from .source import default_names
from makebench.i18n import tr

# Value inputs are separate from execution outputs; positions live in the flow.
VALUE_INPUTS = {
    "event": {},
    "constant": {},
    "variable": {},
    "read": {},
    "binary": {"left": "any", "right": "any"},
    "join": {"left": "any", "right": "any"},
    "log": {"value": "any"},
    "message": {"value": "any"},
    "assign": {"value": "any"},
    "set_text": {"value": "any"},
    "set_enabled": {"value": "bool"},
    "set_value": {"value": "number"},
    "if": {"condition": "bool"},
    "repeat": {"count": "number"},
    "sequence": {},
    "return": {},
    "call": {"value": "any"},
    "run": {"program": "text", "arguments": "list"},
    "script": {"source": "text", "arguments": "list"},
    "terminal_start": {"program": "text", "arguments": "list"},
    "terminal_send": {"value": "any"},
    "terminal_stop": {},
    "go_state": {},
    "open_window": {},
    "close_window": {},
    "show_page": {},
    "ask": {"prompt": "text", "options": "list"},
    "confirm": {"prompt": "text"},
}
VALUE_OPS = {"constant", "variable", "read", "binary", "join"}
RESULT_OPS = {"call", "run", "script", "terminal_start", "ask", "assign"}
LABELS = {
    "event": tr("Event"),
    "constant": tr("Constant"),
    "variable": tr("Variable value"),
    "read": tr("Read component"),
    "binary": tr("Operation"),
    "join": tr("Join texts"),
    "if": tr("Condition"),
    "repeat": tr("Repeat"),
    "sequence": tr("Sequence"),
    "return": tr("Return"),
    "log": tr("Write to output"),
    "message": tr("Message"),
    "assign": tr("Set variable"),
    "set_text": tr("Change text"),
    "set_enabled": tr("Enable component"),
    "set_value": tr("Change progress"),
    "call": tr("Own function"),
    "run": tr("Run program"),
    "script": tr("Run Bash"),
    "terminal_start": tr("Start terminal"),
    "terminal_send": tr("Send to terminal"),
    "terminal_stop": tr("Stop terminal"),
    "go_state": tr("Go to state"),
    "open_window": tr("Open window"),
    "close_window": tr("Close window"),
    "show_page": tr("Show page"),
    "ask": tr("Ask"),
    "confirm": tr("Confirm"),
}
OPERATORS = {"+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or"}


def execution_outputs(node):
    """Define execution ports without inferring order from the node's visual position."""
    op = node["op"]
    if op in VALUE_OPS or op == "return":
        return []
    if op == "if":
        return ["true", "false"]
    if op == "repeat":
        return ["body", "done"]
    if op == "sequence":
        return [str(i) for i in range(node.get("parameters", {}).get("count", 2))]
    return ["next"]


def value_type(value):
    """Classify JSON values; a boolean is never mistaken for a number."""
    return (
        "bool"
        if type(value) is bool
        else "number"
        if type(value) in (int, float)
        else "text"
        if type(value) is str
        else "list"
        if type(value) is list
        else "any"
    )


def output_type(node):
    """Static type of a value port; variables and results are dynamic."""
    op = node["op"]
    p = node.get("parameters", {})
    if op == "constant":
        return value_type(p.get("value"))
    if op == "join":
        return "text"
    if op == "binary":
        return (
            "bool"
            if p.get("operator") in {"==", "!=", "<", "<=", ">", ">=", "and", "or"}
            else "any"
        )
    if op == "read":
        return {"text": "text", "checked": "bool", "value": "number"}.get(p.get("attribute"), "any")
    if op in VALUE_OPS | RESULT_OPS:
        return "any"
    return None


def create_graph(flow):
    """Prepare a new event graph; replacing it requires confirmation in the IDE."""
    entry = new_id("node")
    return {
        "graph_version": 1,
        "entry": entry,
        "nodes": [{"id": entry, "op": "event", "parameters": {}, "inputs": {}}],
        "edges": [],
    }


def replace_editor(flow, editor):
    """Explicitly switch the source of truth and keep the whole previous representation."""
    if editor not in {"blocks", "nodes"}:
        raise ProjectError(tr("Unknown behavior editor."))
    current = flow.get("editor", "blocks")
    if current == editor:
        return
    previous = {
        key: deepcopy(value) for key, value in flow.items() if key not in {"behavior_backups"}
    }
    if len(flow.get("behavior_backups", [])) >= 1000:
        raise ProjectError(tr("Limit of 1000 recoverable versions reached."))
    flow.setdefault("behavior_backups", []).append(previous)
    flow.update(editor=editor, body=[], workspace={})
    flow.pop("errors", None)
    if editor == "nodes":
        flow["graph"] = create_graph(flow)
        flow["graph_layout"] = {flow["graph"]["entry"]: [40, 60]}
    else:
        flow.pop("graph", None)
        flow.pop("graph_layout", None)


def restore_behavior(flow, index=-1):
    """Restore a recoverable copy and keep the current version in the same list."""
    backups = flow.get("behavior_backups", [])
    if not backups:
        raise ProjectError(tr("There is no previous behavior to restore."))
    restored = deepcopy(backups[index])
    current = {k: deepcopy(v) for k, v in flow.items() if k != "behavior_backups"}
    history = [deepcopy(item) for i, item in enumerate(backups) if i != index % len(backups)]
    history.append(current)
    flow.clear()
    flow.update(restored, behavior_backups=history)


def json_value(value, depth=0):
    """Validate bounded constants, with no arbitrary Python and no non-finite numbers."""
    if depth > 12:
        raise ProjectError(tr("Constant exceeds 12 levels."))
    if type(value) in (str, int, float, bool, type(None)):
        if type(value) is str and len(value) > 100000:
            raise ProjectError(tr("Text constant is too long."))
        if type(value) is float and not math.isfinite(value):
            raise ProjectError(tr("Non-finite numeric constant."))
        return
    if type(value) is list and len(value) <= 256:
        for item in value:
            json_value(item, depth + 1)
        return
    if type(value) is dict and len(value) <= 256 and all(isinstance(k, str) for k in value):
        for item in value.values():
            json_value(item, depth + 1)
        return
    raise ProjectError(tr("Use a valid, bounded JSON constant."))


def validate_graph(project, flow):
    """Reject invalid references and ports and value cycles; execution may loop back."""
    graph = flow.get("graph")
    if (
        not isinstance(graph, dict)
        or type(graph.get("graph_version")) is not int
        or graph.get("graph_version") != 1
    ):
        raise ProjectError(tr("Invalid graph version."))
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if (
        not isinstance(nodes, list)
        or not 1 <= len(nodes) <= 5000
        or not isinstance(edges, list)
        or len(edges) > 40000
    ):
        raise ProjectError(tr("The graph accepts up to 5000 nodes and 40000 connections."))
    by_id = {}
    owner = project.window_of(flow["event"]["component"])
    states = {"@default", *[s["id"] for s in project.states.get(owner.id, [])]}

    def name(value):
        """Validate an own-function name without using it as a code fragment."""
        return (
            isinstance(value, str)
            and value.isidentifier()
            and not keyword.iskeyword(value)
            and not value.startswith("_")
        )

    def target(value, kinds=None):
        """Check targets against the document, keeping references by ID."""
        node = project.find(value)
        if node is None or (kinds and node.kind not in kinds):
            raise ProjectError(tr("A node points to a missing or incompatible component."))

    for node in nodes:
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("id"), str)
            or not node["id"]
            or node["id"] in by_id
            or not isinstance(node.get("op"), str)
            or node.get("op") not in VALUE_INPUTS
        ):
            raise ProjectError(tr("Node without a unique ID or a recognized operation."))
        by_id[node["id"]] = node
        op = node["op"]
        p = node.get("parameters", {})
        inputs = node.get("inputs", {})
        if (
            not isinstance(p, dict)
            or not isinstance(inputs, dict)
            or inputs.keys() - VALUE_INPUTS[op].keys()
        ):
            raise ProjectError(tr("Unknown input port."))
        if not isinstance(node.get("comment", ""), str):
            raise ProjectError(tr("A node comment must be text."))
        if op == "constant":
            json_value(p.get("value"))
        if op in {"variable", "assign", "ask"}:
            if (
                not isinstance(p.get("name"), str)
                or not p["name"].strip()
                or p.get("scope", "project") not in ("project", "window", "local")
            ):
                raise ProjectError(tr("Invalid node variable."))
        if op == "call" and not name(p.get("function")):
            raise ProjectError(tr("Invalid own function in node."))
        if op == "binary" and (
            not isinstance(p.get("operator"), str) or p.get("operator") not in OPERATORS
        ):
            raise ProjectError(tr("Unknown node operator."))
        if op == "sequence" and (
            type(p.get("count", 2)) is not int or not 2 <= p.get("count", 2) <= 8
        ):
            raise ProjectError(tr("A sequence accepts between 2 and 8 outputs."))
        if op in {
            "set_text",
            "set_enabled",
            "set_value",
            "show_page",
            "read",
            "terminal_start",
            "terminal_send",
            "terminal_stop",
        }:
            from .logic import TEXT_KINDS

            kinds = (
                TEXT_KINDS
                if op == "set_text" or op == "read" and p.get("attribute") == "text"
                else {ComponentKind.PROGRESS}
                if op == "set_value" or op == "read" and p.get("attribute") == "value"
                else {ComponentKind.CHECKBOX}
                if op == "read" and p.get("attribute") == "checked"
                else {ComponentKind.PAGE}
                if op == "show_page"
                else {ComponentKind.TERMINAL}
                if op.startswith("terminal_")
                else None
            )
            target(p.get("component"), kinds)
            if op == "read" and p.get("attribute") not in ("text", "checked", "value"):
                raise ProjectError(tr("Invalid read property."))
        if op == "go_state" and (
            not isinstance(p.get("state"), str) or p.get("state") not in states
        ):
            raise ProjectError(tr("Node state does not exist."))
        if op == "open_window":
            target(p.get("window"), {ComponentKind.WINDOW})
            if type(p.get("close_current", False)) is not bool:
                raise ProjectError(tr("Invalid close-window option."))
        if op in {"run", "script"} and type(p.get("admin", False)) is not bool:
            raise ProjectError(tr("Invalid task permission."))
        if op == "ask" and p.get("kind", "text") not in ("text", "choice", "file", "directory"):
            raise ProjectError(tr("Invalid node question."))
    if (
        not isinstance(graph.get("entry"), str)
        or graph.get("entry") not in by_id
        or by_id[graph["entry"]]["op"] != "event"
        or sum(n["op"] == "event" for n in nodes) != 1
    ):
        raise ProjectError(tr("Keep a single event node as the entry."))
    for node in nodes:
        for port, expected in VALUE_INPUTS[node["op"]].items():
            binding = node.get("inputs", {}).get(port)
            if not isinstance(binding, dict) or set(binding) not in ({"value"}, {"node", "port"}):
                raise ProjectError(tr("Fill in every value input of the node."))
            if "value" in binding:
                json_value(binding["value"])
                actual = value_type(binding["value"])
            else:
                if not isinstance(binding["node"], str) or not isinstance(binding["port"], str):
                    raise ProjectError(tr("Invalid value port identifier."))
                producer = by_id.get(binding["node"])
                if producer is None or binding["port"] != "value" or output_type(producer) is None:
                    raise ProjectError(
                        tr("A value connection points to a port that does not exist.")
                    )
                actual = output_type(producer)
            if expected != "any" and actual not in {"any", expected}:
                raise ProjectError(
                    tr("Incompatible types on input {port}: {expected} expected.").format(
                        port=port, expected=expected
                    )
                )
    used = set()
    for edge in edges:
        if (
            not isinstance(edge, dict)
            or set(edge) != {"from", "out", "to"}
            or any(not isinstance(edge[k], str) for k in ("from", "out", "to"))
            or edge["from"] not in by_id
            or edge["to"] not in by_id
        ):
            raise ProjectError(tr("Invalid execution connection."))
        source, destination = by_id[edge["from"]], by_id[edge["to"]]
        if (
            edge["out"] not in execution_outputs(source)
            or destination["op"] in VALUE_OPS
            or destination["op"] == "event"
        ):
            raise ProjectError(tr("Incompatible execution ports."))
        key = (edge["from"], edge["out"])
        if key in used:
            raise ProjectError(
                tr("Each execution output accepts one connection. Use Sequence to branch.")
            )
        used.add(key)
    # Iterative DFS avoids Python recursion on large or malformed files.
    visited = set()
    for identifier in by_id:
        stack = [(identifier, False)]
        visiting = set()
        while stack:
            current, finished = stack.pop()
            if finished:
                visiting.discard(current)
                visited.add(current)
                continue
            if current in visited:
                continue
            if current in visiting:
                raise ProjectError(tr("Cycle between values. Use a variable to represent memory."))
            visiting.add(current)
            if len(visiting) > 100:
                raise ProjectError(tr("Value dependencies exceed 100 levels."))
            stack.append((current, True))
            stack.extend(
                (binding["node"], False)
                for binding in by_id[current].get("inputs", {}).values()
                if "node" in binding
            )
    layout = flow.get("graph_layout", {})
    if not isinstance(layout, dict) or any(
        key not in by_id
        or not isinstance(point, list)
        or len(point) != 2
        or any(
            type(x) not in {int, float} or not math.isfinite(x) or abs(x) > 100000 for x in point
        )
        for key, point in layout.items()
    ):
        raise ProjectError(tr("Invalid visual node position."))
    comments = flow.get("graph_comments", [])
    if (
        not isinstance(comments, list)
        or len(comments) > 1000
        or any(
            not isinstance(c, dict)
            or not isinstance(c.get("text"), str)
            or not isinstance(c.get("position"), list)
            or len(c["position"]) != 2
            or any(
                type(x) not in {int, float} or not math.isfinite(x) or abs(x) > 100000
                for x in c["position"]
            )
            for c in comments
        )
    ):
        raise ProjectError(tr("Invalid free graph comments."))


def default_node(op, project, flow):
    """Create a configurable node with literal inputs; never runs actions or adds implicit wires."""
    if op not in VALUE_INPUTS or op == "event":
        raise ProjectError(tr("Choose an available node type."))
    inputs = {
        key: {
            "value": False
            if kind == "bool"
            else 1
            if kind == "number"
            else []
            if kind == "list"
            else ""
        }
        for key, kind in VALUE_INPUTS[op].items()
    }
    p = {}
    owner = project.window_of(flow["event"]["component"])
    if op == "constant":
        p["value"] = tr("Hello!")
    if op in {"variable", "assign", "ask"}:
        p.update(name=default_names()["variable"], scope="project")
    if op == "call":
        p["function"] = default_names()["function"]
    if op == "binary":
        p["operator"] = "=="
    if op == "sequence":
        p["count"] = 2
    if op in {"run", "script"}:
        p["admin"] = False
    if op == "run":
        inputs["program"]["value"] = "uname"
    if op == "script":
        inputs["source"]["value"] = tr('printf "Hello\\n"')
    if op == "ask":
        p["kind"] = "text"
    if op == "go_state":
        p["state"] = "@default"
    if op == "open_window":
        p.update(
            window=next((r.id for r in project.roots if r.id != owner.id), owner.id),
            close_current=False,
        )
    if op in {
        "set_text",
        "set_enabled",
        "set_value",
        "show_page",
        "read",
        "terminal_start",
        "terminal_send",
        "terminal_stop",
    }:
        from .logic import TEXT_KINDS

        kinds = (
            TEXT_KINDS
            if op in {"set_text", "read"}
            else {ComponentKind.PROGRESS}
            if op == "set_value"
            else {ComponentKind.PAGE}
            if op == "show_page"
            else {ComponentKind.TERMINAL}
            if op.startswith("terminal_")
            else None
        )
        component = next((n for n in owner.walk() if kinds is None or n.kind in kinds), None)
        if component is None:
            raise ProjectError(
                tr("Insert a compatible component in this window before creating this node.")
            )
        p["component"] = component.id
        if op == "read":
            p["attribute"] = "text"
    return {"id": new_id("node"), "op": op, "parameters": p, "inputs": inputs}


def compile_graph(flow, index, functions):
    """Compile a free flow into a Python state machine, without creating a Blockly tree."""
    graph = flow["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {(e["from"], e["out"]): e["to"] for e in graph["edges"]}
    lines = [
        f"# {flow['name'].replace(chr(10), ' ').replace(chr(13), ' ')}",
        "# "
        + tr("Event: {kind} on {component}").format(
            kind=flow["event"]["kind"], component=repr(flow["event"]["component"])
        ),
        f"def on_event_{index}(ctx):",
        "    variables = ctx.variables",
        "    local_variables = {}",
        "    _values = {}",
        "    _repeats = {}",
        "    _pending = []",
        f"    _pc = {graph['entry']!r}",
        "    _steps = 0",
        "    while _pc is not None or _pending:",
        "        if _pc is None:",
        "            _pc = _pending.pop()",
        "        _steps += 1",
    ]
    origins = {}
    diagnostics = []

    def emit(text, indent=3):
        """Emit a line with indentation controlled by the compiler."""
        lines.append("    " * indent + text)

    def expression(binding, path=()):
        """Resolve pure values or results previously produced by execution."""
        if "value" in binding:
            return repr(binding["value"])
        return f"_value({binding['node']!r})"

    def node_expression(node):
        """One expression per producer; dependencies are lookups instead of textual expansion."""
        op = node["op"]
        p = node.get("parameters", {})
        inputs = node.get("inputs", {})

        def value(port):
            return expression(inputs[port])

        if op == "constant":
            return repr(p.get("value"))
        if op == "variable":
            return f"{ {'project': 'variables', 'window': 'ctx.window_variables', 'local': 'local_variables'}[p.get('scope', 'project')] }.get({p['name']!r})"
        if op == "read":
            return f"ctx.read({p['component']!r}, {p['attribute']!r})"
        if op == "binary":
            return f"({value('left')} {p['operator']} {value('right')})"
        if op == "join":
            return f"(str({value('left')}) + str({value('right')}))"
        return f"ctx.graph_result(_values, {node['id']!r})"

    setup = lines[:10]
    loop = lines[10:]
    lines = setup
    emit("_memo = {}", 1)
    emit("def _value(identifier):", 1)
    emit("if identifier in _memo: return _memo[identifier]", 2)
    for producer in graph["nodes"]:
        if output_type(producer) is None:
            continue
        emit(f"if identifier == {producer['id']!r}:", 2)
        if producer["op"] in VALUE_OPS:
            origins[producer["id"]] = len(lines) + 1
        emit("result = " + node_expression(producer), 3)
        emit("_memo[identifier] = result", 3)
        emit("return result", 3)
    emit("raise RuntimeError(" + repr(tr("Value producer does not exist.")) + ")", 2)
    lines.extend(loop)
    emit("_memo.clear()", 2)
    for node in graph["nodes"]:
        if node["op"] in VALUE_OPS:
            continue
        op = node["op"]
        identifier = node["id"]
        p = node.get("parameters", {})
        inputs = node.get("inputs", {})
        emit(f"if _pc == {identifier!r}:", 2)
        for comment in node.get("comment", "").splitlines():
            emit("# " + comment)
        origins[identifier] = len(lines) + 1
        emit(f"ctx.graph_checkpoint({flow['id']!r}, {identifier!r}, _steps)")

        def value(port):
            return expression(inputs[port])

        def edge(port="next"):
            return repr(edges.get((identifier, port)))

        if op in {"log", "message", "confirm"}:
            emit(f"ctx.{op}({value('prompt' if op == 'confirm' else 'value')})")
        elif op in {"set_text", "set_enabled", "set_value", "terminal_send"}:
            emit(f"ctx.{op}({p['component']!r}, {value('value')})")
        elif op in {"terminal_stop", "show_page"}:
            emit(f"ctx.{op}({p['component']!r})")
        elif op == "terminal_start":
            emit(
                f"_values[{identifier!r}] = ctx.terminal_start({p['component']!r}, {value('program')}, {value('arguments')})"
            )
        elif op == "assign":
            emit(
                f"_values[{identifier!r}] = { {'project': 'variables', 'window': 'ctx.window_variables', 'local': 'local_variables'}[p.get('scope', 'project')] }[{p['name']!r}] = {value('value')}"
            )
        elif op == "call":
            if p["function"] not in functions:
                diagnostics.append(
                    tr("{flow}: function ‘{function}’ not found in .actions.py.").format(
                        flow=flow["name"], function=p["function"]
                    )
                )
            emit(f"_values[{identifier!r}] = ctx.call_action({p['function']!r}, {value('value')})")
        elif op in {"run", "script"}:
            emit(
                f"_values[{identifier!r}] = ctx.{'run' if op == 'run' else 'run_script'}({value('program' if op == 'run' else 'source')}, {value('arguments')}, admin={p.get('admin', False)!r})"
            )
        elif op == "ask":
            emit(
                f"_values[{identifier!r}] = { {'project': 'variables', 'window': 'ctx.window_variables', 'local': 'local_variables'}[p.get('scope', 'project')] }[{p['name']!r}] = ctx.ask({p.get('kind', 'text')!r}, {value('prompt')}, {value('options')})"
            )
        elif op == "go_state":
            emit(f"ctx.go_state({p['state']!r})")
        elif op == "open_window":
            emit(
                f"ctx.open_window({p['window']!r}, close_current={p.get('close_current', False)!r})"
            )
        elif op == "close_window":
            emit("ctx.close_window()")
        if op == "if":
            emit(f"_pc = {edge('true')} if {value('condition')} else {edge('false')}")
        elif op == "repeat":
            emit(f"if _pending and _pending[-1] == {identifier!r}: _pending.pop()")
            emit(
                f"if {identifier!r} not in _repeats: _repeats[{identifier!r}] = max(0,int({value('count')}))"
            )
            emit(f"if _repeats[{identifier!r}] > 0:")
            emit(f"_repeats[{identifier!r}] -= 1", 4)
            emit(f"_pending.append({identifier!r})", 4)
            emit(f"_pc = {edge('body')}", 4)
            emit("else:")
            emit(f"del _repeats[{identifier!r}]", 4)
            emit(f"_pc = {edge('done')}", 4)
        elif op == "sequence":
            targets = [
                edges[(identifier, port)]
                for port in execution_outputs(node)
                if (identifier, port) in edges
            ]
            for target in reversed(targets[1:]):
                emit(f"_pending.append({target!r})")
            emit(f"_pc = {targets[0] if targets else None!r}")
        elif op == "return":
            emit("_pc = None")
        else:
            emit(f"_pc = {edge()}")
        emit("continue")
    lines.extend(
        ["        raise RuntimeError(" + repr(tr("Invalid graph execution state.")) + ")", ""]
    )
    return lines, origins, diagnostics


def duplicate_graph(flow, components):
    """Regenerate IDs and internal wires and remap components of a behavior copy."""
    graph = flow["graph"]
    mapping = {node["id"]: new_id("node") for node in graph["nodes"]}
    graph["entry"] = mapping[graph["entry"]]
    for node in graph["nodes"]:
        node["id"] = mapping[node["id"]]
        parameters = node.get("parameters", {})
        for key in ("component", "window"):
            if parameters.get(key) in components:
                parameters[key] = components[parameters[key]]
        for binding in node.get("inputs", {}).values():
            if "node" in binding:
                binding["node"] = mapping[binding["node"]]
    for edge in graph["edges"]:
        edge.update({"from": mapping[edge["from"]], "to": mapping[edge["to"]]})
    flow["graph_layout"] = {
        mapping[key]: value for key, value in flow.get("graph_layout", {}).items()
    }
    for comment in flow.get("graph_comments", []):
        comment["id"] = new_id("comment")
