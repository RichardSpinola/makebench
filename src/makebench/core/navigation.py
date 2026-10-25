# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows, states and transitions as data, independent of the toolkit."""

from copy import deepcopy
import math
from .project import (
    Component,
    ComponentKind,
    LayoutKind,
    Project,
    ProjectError,
    create_component,
    new_id,
)
from makebench.i18n import tr

OVERRIDES = {
    "text",
    "title",
    "source",
    "alt_text",
    "image_name",
    "visible",
    "enabled",
    "checked",
    "value",
    "initial_page",
}


def validate_navigation(project):
    """Validate scopes, targets and overrides before any rendering."""
    roots = {r.id: r for r in project.roots}
    if project.entry_window is not None and project.entry_window not in roots:
        raise ProjectError(tr("The start window does not belong to the project."))
    if (
        not isinstance(project.states, dict)
        or not isinstance(project.variables, list)
        or not isinstance(project.map_layout, dict)
    ):
        raise ProjectError(tr("Invalid states, variables or map positions."))
    for window_id, states in project.states.items():
        if window_id not in roots or not isinstance(states, list) or len(states) > 128:
            raise ProjectError(tr("States must belong to an existing window (at most 128)."))
        ids = set()
        components = {n.id: n for n in roots[window_id].walk()}
        for state in states:
            if (
                not isinstance(state, dict)
                or not isinstance(state.get("id"), str)
                or not state["id"]
                or state["id"] == "@default"
                or state["id"] in ids
                or not isinstance(state.get("name"), str)
                or not state["name"].strip()
            ):
                raise ProjectError(tr("State without a name or unique identifier."))
            ids.add(state["id"])
            overrides = state.get("overrides", {})
            if not isinstance(overrides, dict):
                raise ProjectError(tr("Invalid state overrides."))
            for identifier, values in overrides.items():
                if (
                    identifier not in components
                    or not isinstance(values, dict)
                    or values.keys() - OVERRIDES
                ):
                    raise ProjectError(
                        tr("A state only changes properties of components in its own window.")
                    )
                node = deepcopy(components[identifier])
                node.properties.update(values)
                Component.from_dict(node.to_dict())
                for key in ("visible", "enabled"):
                    if key in values and type(values[key]) is not bool:
                        raise ProjectError(tr("Visibility and enabled must be booleans."))
        initial = roots[window_id].properties.get("initial_state", "@default")
        if initial != "@default" and initial not in ids:
            raise ProjectError(tr("The initial state does not exist."))
    seen = set()
    for variable in project.variables:
        if (
            not isinstance(variable, dict)
            or not isinstance(variable.get("name"), str)
            or not variable["name"].strip()
        ):
            raise ProjectError(tr("Variable without a name."))
        scope = variable.get("scope", "project")
        window = variable.get("window")
        if scope not in {"project", "window"} or scope == "window" and window not in roots:
            raise ProjectError(tr("Invalid variable scope."))
        key = (scope, window if scope == "window" else None, variable["name"])
        if key in seen:
            raise ProjectError(tr("Repeated variable in the same scope."))
        seen.add(key)
        value = variable.get("initial")
        if (
            type(value) not in {type(None), str, bool, int, float}
            or type(value) is float
            and not math.isfinite(value)
        ):
            raise ProjectError(tr("The initial value must be text, a number, a boolean or null."))
    for key, point in project.map_layout.items():
        if (
            not isinstance(key, str)
            or not isinstance(point, list)
            or len(point) != 2
            or any(
                type(n) not in {int, float} or not math.isfinite(n) or abs(n) > 100000
                for n in point
            )
        ):
            raise ProjectError(tr("Invalid map position."))
    code_names = set()
    for root in project.roots:
        valid_states = {"@default", *[s["id"] for s in project.states.get(root.id, [])]}
        if root.properties.get("initial_state", "@default") not in valid_states:
            raise ProjectError(tr("The initial state does not exist."))
    application = project.application
    if not isinstance(application, dict):
        raise ProjectError(tr("Invalid application settings."))
    if application.get("backend", "qt") not in {"qt", "gtk"}:
        raise ProjectError(tr("The backend must be GTK or Qt."))
    for key in ("name", "id", "version", "description", "author", "license", "category", "icon"):
        if key in application and not isinstance(application[key], str):
            raise ProjectError(tr("Application metadata must be text: {key}").format(key=key))
    if not isinstance(application.get("packages", []), list) or any(
        not isinstance(v, str) for v in application.get("packages", [])
    ):
        raise ProjectError(tr("Dependencies must be a list of texts."))
    if application.get("icon"):
        from pathlib import PurePosixPath

        path = PurePosixPath(application["icon"])
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in application["icon"]
            or len(path.parts) < 2
            or path.parts[0] != "assets"
        ):
            raise ProjectError(tr("The icon must be in assets."))
    for node in project.walk():
        p = node.properties
        if p.get("icon"):
            from pathlib import PurePosixPath

            icon = PurePosixPath(p["icon"]) if isinstance(p["icon"], str) else None
            if (
                icon is None
                or icon.is_absolute()
                or ".." in icon.parts
                or len(icon.parts) < 2
                or icon.parts[0] != "assets"
                or "\\" in p["icon"]
            ):
                raise ProjectError(tr("The window icon must be in assets."))
        if not isinstance(p.get("tooltip", ""), str):
            raise ProjectError(tr("The component tooltip must be text."))
        for key in ("visible", "enabled", "resizable"):
            if key in p and type(p[key]) is not bool:
                raise ProjectError(tr("Invalid boolean property: {key}").format(key=key))
        for key in ("width", "height"):
            if key in p and (type(p[key]) is not int or not 1 <= p[key] <= 20000):
                raise ProjectError(tr("Invalid initial size."))
        code_name = p.get("code_name", "")
        import keyword

        if (
            not isinstance(code_name, str)
            or code_name
            and (
                not code_name.isidentifier()
                or keyword.iskeyword(code_name)
                or code_name in code_names
            )
        ):
            raise ProjectError(tr("Invalid or repeated code name."))
        if code_name:
            code_names.add(code_name)
        if not isinstance(p.get("size_mode", {}), dict):
            raise ProjectError(tr("Invalid size mode."))
        for key in ("spacing", "padding"):
            if key in p and (type(p[key]) is not int or not 0 <= p[key] <= 2000):
                raise ProjectError(tr("Spacing and margins must be between 0 and 2000."))
        if "alignment_preset" in p and p["alignment_preset"] not in {
            y + "-" + x for y in ("top", "center", "bottom") for x in ("left", "center", "right")
        }:
            raise ProjectError(tr("Invalid alignment."))
        if p.get("align", "start") not in {"start", "center", "end", "stretch"}:
            raise ProjectError(tr("Invalid alignment."))
        if p.get("distribute", "start") not in {"start", "center", "end", "space-between"}:
            raise ProjectError(tr("Invalid distribution."))
        for axis, mode in p.get("size_mode", {}).items():
            if axis not in {"width", "height"} or mode not in {"content", "fill", "fixed"}:
                raise ProjectError(tr("Invalid sizing."))
        if "free_geometry" in p:
            candidate = node.to_dict()
            candidate["geometry"] = p["free_geometry"]
            Component.from_dict(candidate)


def add_window(project, name, duplicate=None):
    """Add a real window; duplication remaps components and pages."""
    if not name.strip():
        raise ProjectError(tr("Give the window a name."))
    root = (
        create_component(ComponentKind.WINDOW)
        if duplicate is None
        else deepcopy(project.find(duplicate))
    )
    if root is None or root.kind != ComponentKind.WINDOW:
        raise ProjectError(tr("Select a window to duplicate."))
    if duplicate:
        from .logic import duplicate_flows

        mapping = {n.id: new_id(n.kind.value) for n in root.walk()}
        state_mapping = {s["id"]: new_id("state") for s in project.states.get(duplicate, [])}
        original_count = len(project.workflows)
        duplicate_flows(project, mapping)
        for node in root.walk():
            node.id = mapping[node.id]
            if node.kind == ComponentKind.PAGES:
                node.properties["initial_page"] = mapping[node.properties["initial_page"]]
            if node.properties.get("code_name"):
                node.properties["code_name"] += "_" + node.id.rsplit("_", 1)[-1][:4]
        initial = root.properties.get("initial_state")
        if initial in state_mapping:
            root.properties["initial_state"] = state_mapping[initial]
        if state_mapping:
            copies = deepcopy(project.states[duplicate])
            for state in copies:
                state["id"] = state_mapping[state["id"]]
                state["overrides"] = {
                    mapping[key]: value for key, value in state.get("overrides", {}).items()
                }
                for values in state["overrides"].values():
                    if values.get("initial_page") in mapping:
                        values["initial_page"] = mapping[values["initial_page"]]
            project.states[root.id] = copies

        def remap(value):
            """Update references without rewriting text or the user's own code."""
            if isinstance(value, dict):
                if value.get("state") in state_mapping:
                    value["state"] = state_mapping[value["state"]]
                if value.get("window") in mapping:
                    value["window"] = mapping[value["window"]]
                for child in value.values():
                    remap(child)
            elif isinstance(value, list):
                for child in value:
                    remap(child)

        for variable in list(project.variables):
            if variable.get("scope") == "window" and variable.get("window") == duplicate:
                clone = deepcopy(variable)
                clone["window"] = root.id
                project.variables.append(clone)
        for flow in project.workflows[original_count:]:
            if flow.get("states"):
                flow["states"] = [state_mapping.get(state, state) for state in flow["states"]]
            remap(flow.get("body"))
            if flow.get("editor") == "nodes":
                for node in flow["graph"]["nodes"]:
                    if node["op"] == "go_state":
                        node["parameters"]["state"] = state_mapping.get(
                            node["parameters"]["state"], node["parameters"]["state"]
                        )
    root.properties["title"] = name.strip()
    project.windows.append(root)
    return root


def add_state(project, window_id, name, start="@default"):
    """Create differences over Default; copying does not create inheritance between states."""
    if not name.strip() or project.window_of(window_id) is None:
        raise ProjectError(tr("Enter the window and the state name."))
    states = project.states.setdefault(window_id, [])
    base = next((s for s in states if s["id"] == start), None)
    state = {
        "id": new_id("state"),
        "name": name.strip(),
        "overrides": deepcopy(base.get("overrides", {})) if base else {},
    }
    states.append(state)
    return state


def navigation_edges(project):
    """Derive connections from blocks, including navigation inside conditions."""
    edges = []

    def visit(value, flow):
        """Walk structured data without running project content."""
        if isinstance(value, dict):
            if value.get("op") in {"go_state", "open_window", "close_window", "show_page"}:
                owner = project.window_of(flow["event"]["component"])
                edges.append(
                    {
                        "flow": flow["id"],
                        "block": value["id"],
                        "source": owner.id,
                        "states": flow.get("states", []),
                        "event": flow["name"],
                        "op": value["op"],
                        "target": value.get("state")
                        or value.get("window")
                        or value.get("component"),
                    }
                )
            for child in value.values():
                visit(child, flow)
        elif isinstance(value, list):
            for child in value:
                visit(child, flow)

    for flow in project.editable_flows:
        if flow.get("editor") == "nodes":
            reachable = {flow["graph"]["entry"]}
            pending = list(reachable)
            successors = {}
            for edge in flow["graph"]["edges"]:
                successors.setdefault(edge["from"], []).append(edge["to"])
            while pending:
                for target in successors.get(pending.pop(), []):
                    if target not in reachable:
                        reachable.add(target)
                        pending.append(target)
            for node in flow["graph"]["nodes"]:
                if node["id"] not in reachable:
                    continue
                if node["op"] in {"go_state", "open_window", "close_window", "show_page"}:
                    visit({"id": node["id"], "op": node["op"], **node["parameters"]}, flow)
        else:
            visit(flow.get("body"), flow)
    return edges


def welcome_template(name=None):
    """Runnable example: three states, Back/Next and opening another window."""
    from .logic import create_flow

    project = Project.empty(tr("Welcome") if name is None else name)
    root = project.root
    heading = project.add(root.id, ComponentKind.LABEL)
    heading.properties["text"] = tr("Welcome to your Linux")
    body = project.add(root.id, ComponentKind.LABEL)
    body.properties["text"] = tr("Discover the tools that come with your system.")
    row = project.add(root.id, ComponentKind.CONTAINER)
    row.layout = LayoutKind.HORIZONTAL
    back = project.add(row.id, ComponentKind.BUTTON)
    back.properties.update(text=tr("Back"), enabled=False)
    next_button = project.add(row.id, ComponentKind.BUTTON)
    next_button.properties["text"] = tr("Next")
    second = add_state(project, root.id, tr("Discover the system"))
    second["overrides"] = {
        heading.id: {"text": tr("Your system, your way")},
        body.id: {"text": tr("Customize tools and preferences whenever you like.")},
        back.id: {"enabled": True},
    }
    third = add_state(project, root.id, tr("All set"))
    third["overrides"] = {
        heading.id: {"text": tr("All set to start")},
        body.id: {"text": tr("Finish the wizard to open your dashboard.")},
        back.id: {"enabled": True},
        next_button.id: {"text": tr("Finish")},
    }
    panel = add_window(project, tr("Main dashboard"))
    text = project.add(panel.id, ComponentKind.LABEL)
    text.properties["text"] = tr("Welcome! Your dashboard is ready.")
    sequence = ["@default", second["id"], third["id"]]
    for index, state in enumerate(sequence):
        flow = create_flow(project, next_button.id, states=[state])
        flow["body"] = (
            [{"id": new_id("block"), "op": "go_state", "state": sequence[index + 1]}]
            if index < 2
            else [
                {
                    "id": new_id("block"),
                    "op": "open_window",
                    "window": panel.id,
                    "close_current": True,
                }
            ]
        )
        if index:
            create_flow(project, back.id, states=[state])["body"] = [
                {"id": new_id("block"), "op": "go_state", "state": sequence[index - 1]}
            ]
    return project


def find_navigation_block(project, flow_id, block_id):
    """Find an action by identity, including inside conditions/repeats."""
    flow = next((f for f in project.editable_flows if f["id"] == flow_id), None)

    def visit(value):
        """IDs are not display names and need no code interpretation."""
        if isinstance(value, dict):
            if value.get("id") == block_id:
                return value
            for child in value.values():
                found = visit(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = visit(child)
                if found:
                    return found

    if flow and flow.get("editor") == "nodes":
        return flow, next((n for n in flow["graph"]["nodes"] if n["id"] == block_id), None)
    return (flow, visit(flow.get("body"))) if flow else (None, None)


def remove_navigation_block(project, flow_id, block_id):
    """Remove only the given block, keeping the flow's other effects and comments."""
    flow, _ = find_navigation_block(project, flow_id, block_id)
    if not flow:
        return
    if flow.get("editor") == "nodes":
        flow["graph"]["nodes"] = [n for n in flow["graph"]["nodes"] if n["id"] != block_id]
        flow["graph"]["edges"] = [
            e for e in flow["graph"]["edges"] if block_id not in (e["from"], e["to"])
        ]
        flow.get("graph_layout", {}).pop(block_id, None)
        return

    def visit(items):
        """Removal also works in the event's inner branches."""
        for item in list(items or []):
            if item.get("id") == block_id:
                items.remove(item)
                return True
            for key in ("then", "else", "body"):
                if isinstance(item.get(key), list) and visit(item[key]):
                    return True
        return False

    visit(flow.get("body"))
    flow["workspace"] = {
        "workspaceComments": flow.get("workspace", {}).get("workspaceComments", [])
    }


def connect_navigation(project, source, event_component, target, close_current=False, replace=None):
    """Create/edit real navigation in the flow; windows open in their supported initial state."""
    from .logic import create_flow

    window_id, state = source.split("|", 1)
    target_window, target_state = target.split("|", 1)
    owner = project.window_of(event_component)
    destination = project.find(target_window)
    if owner is None or owner.id != window_id or destination not in project.roots:
        raise ProjectError(
            tr("The navigation source or destination does not belong to the chosen interface.")
        )
    if target_window != window_id and target_state != destination.properties.get(
        "initial_state", "@default"
    ):
        raise ProjectError(
            tr("Another window opens in its initial state. Choose that state as the destination.")
        )
    old_flow, old_block = find_navigation_block(project, *replace) if replace else (None, None)
    comment = old_block.get("comment") if old_block else None
    identifier = old_block["id"] if old_block else new_id("block")
    if replace and not old_block:
        raise ProjectError(tr("The transition no longer exists."))
    if state not in {
        "@default",
        *[s["id"] for s in project.states.get(window_id, [])],
    } or target_state not in {
        "@default",
        *[s["id"] for s in project.states.get(target_window, [])],
    }:
        raise ProjectError(tr("The transition state does not exist."))
    flow = (
        old_flow
        if old_flow
        and old_flow["event"]["component"] == event_component
        and (not old_flow.get("states") or state in old_flow["states"])
        else next(
            iter(
                sorted(
                    (
                        f
                        for f in project.editable_flows
                        if f["event"]["component"] == event_component
                        and (not f.get("states") or state in f["states"])
                    ),
                    key=lambda f: not bool(f.get("states")),
                )
            ),
            None,
        )
    )
    if flow is None:
        flow = create_flow(project, event_component, states=[state])
    if flow.get("body") is None:
        raise ProjectError(tr("Complete this event's draft before adding a transition."))
    block = (
        {"id": identifier, "op": "go_state", "state": target_state}
        if window_id == target_window
        else {
            "id": identifier,
            "op": "open_window",
            "window": target_window,
            "close_current": bool(close_current),
        }
    )
    if comment:
        block["comment"] = comment
    if flow.get("editor") == "nodes":
        parameters = {
            key: value for key, value in block.items() if key not in {"id", "op", "comment"}
        }
        if old_block and old_flow is flow:
            old_block.update(op=block["op"], parameters=parameters, inputs={})
        else:
            entry = flow["graph"]["entry"]
            if any(e["from"] == entry and e["out"] == "next" for e in flow["graph"]["edges"]):
                raise ProjectError(
                    tr(
                        "This event uses Nodes. Add and connect the navigation in the Nodes editor to choose the execution path."
                    )
                )
            flow["graph"]["nodes"].append(
                {
                    "id": identifier,
                    "op": block["op"],
                    "parameters": parameters,
                    "inputs": {},
                    "comment": comment or "",
                }
            )
            flow["graph"]["edges"].append({"from": entry, "out": "next", "to": identifier})
        return flow
    if old_block and old_flow is flow:
        old_block.clear()
        old_block.update(block)
    else:
        if old_block:
            remove_navigation_block(project, *replace)
        flow["body"].append(block)
    flow["workspace"] = {
        "workspaceComments": flow.get("workspace", {}).get("workspaceComments", [])
    }
    return flow


def effective_edge_states(project, edge):
    """Derive the states actually reached, with specific handlers over general ones."""
    if edge["states"]:
        return edge["states"]
    flow = next(f for f in project.editable_flows if f["id"] == edge["flow"])
    states = ["@default", *[s["id"] for s in project.states.get(edge["source"], [])]]
    overridden = {
        s
        for f in project.editable_flows
        if f["id"] != flow["id"] and f["event"] == flow["event"]
        for s in f.get("states", [])
    }
    return [state for state in states if state not in overridden]
