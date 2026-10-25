"""Janelas, estados e transições como dados, independentes do toolkit."""

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
    """Valida escopos, alvos e sobrescritas antes de qualquer renderização."""
    roots = {r.id: r for r in project.roots}
    if project.entry_window is not None and project.entry_window not in roots:
        raise ProjectError("A janela inicial não pertence ao projeto.")
    if (
        not isinstance(project.states, dict)
        or not isinstance(project.variables, list)
        or not isinstance(project.map_layout, dict)
    ):
        raise ProjectError("Estados, variáveis ou posições do mapa inválidos.")
    for window_id, states in project.states.items():
        if window_id not in roots or not isinstance(states, list) or len(states) > 128:
            raise ProjectError("Estados devem pertencer a uma janela existente (máximo 128).")
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
                raise ProjectError("Estado sem nome ou identificador único.")
            ids.add(state["id"])
            overrides = state.get("overrides", {})
            if not isinstance(overrides, dict):
                raise ProjectError("Sobrescritas de estado inválidas.")
            for identifier, values in overrides.items():
                if (
                    identifier not in components
                    or not isinstance(values, dict)
                    or values.keys() - OVERRIDES
                ):
                    raise ProjectError(
                        "O estado só altera propriedades de componentes da sua janela."
                    )
                node = deepcopy(components[identifier])
                node.properties.update(values)
                Component.from_dict(node.to_dict())
                for key in ("visible", "enabled"):
                    if key in values and type(values[key]) is not bool:
                        raise ProjectError("Visibilidade e habilitação precisam ser booleanas.")
        initial = roots[window_id].properties.get("initial_state", "@default")
        if initial != "@default" and initial not in ids:
            raise ProjectError("Estado inicial inexistente.")
    seen = set()
    for variable in project.variables:
        if (
            not isinstance(variable, dict)
            or not isinstance(variable.get("name"), str)
            or not variable["name"].strip()
        ):
            raise ProjectError("Variável sem nome.")
        scope = variable.get("scope", "project")
        window = variable.get("window")
        if scope not in {"project", "window"} or scope == "window" and window not in roots:
            raise ProjectError("Escopo da variável inválido.")
        key = (scope, window if scope == "window" else None, variable["name"])
        if key in seen:
            raise ProjectError("Variável repetida no mesmo escopo.")
        seen.add(key)
        value = variable.get("initial")
        if (
            type(value) not in {type(None), str, bool, int, float}
            or type(value) is float
            and not math.isfinite(value)
        ):
            raise ProjectError("Valor inicial precisa ser texto, número, booleano ou nulo.")
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
            raise ProjectError("Posição do mapa inválida.")
    code_names = set()
    for root in project.roots:
        valid_states = {"@default", *[s["id"] for s in project.states.get(root.id, [])]}
        if root.properties.get("initial_state", "@default") not in valid_states:
            raise ProjectError("Estado inicial inexistente.")
    application = project.application
    if not isinstance(application, dict):
        raise ProjectError("Configuração do aplicativo inválida.")
    if application.get("backend", "qt") not in {"qt", "gtk"}:
        raise ProjectError("Backend precisa ser GTK ou Qt.")
    for key in ("name", "id", "version", "description", "author", "license", "category", "icon"):
        if key in application and not isinstance(application[key], str):
            raise ProjectError("Metadado do aplicativo precisa ser texto: " + key)
    if not isinstance(application.get("packages", []), list) or any(
        not isinstance(v, str) for v in application.get("packages", [])
    ):
        raise ProjectError("Dependências precisam ser uma lista de textos.")
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
            raise ProjectError("O ícone precisa ficar em assets.")
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
                raise ProjectError("Ícone da janela precisa ficar em assets.")
        if not isinstance(p.get("tooltip", ""), str):
            raise ProjectError("Dica do componente precisa ser texto.")
        for key in ("visible", "enabled", "resizable"):
            if key in p and type(p[key]) is not bool:
                raise ProjectError("Propriedade booleana inválida: " + key)
        for key in ("width", "height"):
            if key in p and (type(p[key]) is not int or not 1 <= p[key] <= 20000):
                raise ProjectError("Tamanho inicial inválido.")
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
            raise ProjectError("Nome no código inválido ou repetido.")
        if code_name:
            code_names.add(code_name)
        if not isinstance(p.get("size_mode", {}), dict):
            raise ProjectError("Modo de tamanho inválido.")
        for key in ("spacing", "padding"):
            if key in p and (type(p[key]) is not int or not 0 <= p[key] <= 2000):
                raise ProjectError("Espaçamento e margens devem estar entre 0 e 2000.")
        if "alignment_preset" in p and p["alignment_preset"] not in {
            y + "-" + x for y in ("top", "center", "bottom") for x in ("left", "center", "right")
        }:
            raise ProjectError("Alinhamento inválido.")
        if p.get("align", "start") not in {"start", "center", "end", "stretch"}:
            raise ProjectError("Alinhamento inválido.")
        if p.get("distribute", "start") not in {"start", "center", "end", "space-between"}:
            raise ProjectError("Distribuição inválida.")
        for axis, mode in p.get("size_mode", {}).items():
            if axis not in {"width", "height"} or mode not in {"content", "fill", "fixed"}:
                raise ProjectError("Dimensionamento inválido.")
        if "free_geometry" in p:
            candidate = node.to_dict()
            candidate["geometry"] = p["free_geometry"]
            Component.from_dict(candidate)


def add_window(project, name, duplicate=None):
    """Acrescenta janela real; duplicação remapeia componentes e páginas."""
    if not name.strip():
        raise ProjectError("Dê um nome à janela.")
    root = (
        create_component(ComponentKind.WINDOW)
        if duplicate is None
        else deepcopy(project.find(duplicate))
    )
    if root is None or root.kind != ComponentKind.WINDOW:
        raise ProjectError("Selecione uma janela para duplicar.")
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
            """Atualiza referências sem reescrever texto ou código próprio."""
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
    """Cria diferenças sobre o Padrão; copiar não estabelece herança entre estados."""
    if not name.strip() or project.window_of(window_id) is None:
        raise ProjectError("Informe janela e nome do estado.")
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
    """Deriva conexões dos blocos, inclusive navegação dentro de condições."""
    edges = []

    def visit(value, flow):
        """Percorre dados estruturados sem executar conteúdo do projeto."""
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


def welcome_template(name="Boas-vindas"):
    """Exemplo executável: três estados, Voltar/Próximo e abertura de outra janela."""
    from .logic import create_flow

    project = Project.empty(name)
    root = project.root
    heading = project.add(root.id, ComponentKind.LABEL)
    heading.properties["text"] = "Bem-vindo ao seu Linux"
    body = project.add(root.id, ComponentKind.LABEL)
    body.properties["text"] = "Conheça as ferramentas que acompanham seu sistema."
    row = project.add(root.id, ComponentKind.CONTAINER)
    row.layout = LayoutKind.HORIZONTAL
    back = project.add(row.id, ComponentKind.BUTTON)
    back.properties.update(text="Voltar", enabled=False)
    next_button = project.add(row.id, ComponentKind.BUTTON)
    next_button.properties["text"] = "Próximo"
    second = add_state(project, root.id, "Conheça o sistema")
    second["overrides"] = {
        heading.id: {"text": "Seu sistema, do seu jeito"},
        body.id: {"text": "Personalize as ferramentas e preferências quando quiser."},
        back.id: {"enabled": True},
    }
    third = add_state(project, root.id, "Tudo pronto")
    third["overrides"] = {
        heading.id: {"text": "Tudo pronto para começar"},
        body.id: {"text": "Conclua o assistente para abrir seu painel."},
        back.id: {"enabled": True},
        next_button.id: {"text": "Concluir"},
    }
    panel = add_window(project, "Painel principal")
    text = project.add(panel.id, ComponentKind.LABEL)
    text.properties["text"] = "Bem-vindo! Seu painel está pronto."
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
    """Localiza uma ação por identidade, inclusive dentro de condições/repetições."""
    flow = next((f for f in project.editable_flows if f["id"] == flow_id), None)

    def visit(value):
        """IDs não são nomes exibidos e não precisam de interpretação de código."""
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
    """Remove só o bloco indicado, preservando outros efeitos e comentários do fluxo."""
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
        """A remoção funciona também em ramificações internas do evento."""
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
    """Cria/edita navegação real no fluxo; janelas abrem no estado inicial suportado."""
    from .logic import create_flow

    window_id, state = source.split("|", 1)
    target_window, target_state = target.split("|", 1)
    owner = project.window_of(event_component)
    destination = project.find(target_window)
    if owner is None or owner.id != window_id or destination not in project.roots:
        raise ProjectError("Origem ou destino da navegação não pertence à interface escolhida.")
    if target_window != window_id and target_state != destination.properties.get(
        "initial_state", "@default"
    ):
        raise ProjectError(
            "Outra janela abre em seu estado inicial. Escolha esse estado como destino."
        )
    old_flow, old_block = find_navigation_block(project, *replace) if replace else (None, None)
    comment = old_block.get("comment") if old_block else None
    identifier = old_block["id"] if old_block else new_id("block")
    if replace and not old_block:
        raise ProjectError("A transição não existe mais.")
    if state not in {
        "@default",
        *[s["id"] for s in project.states.get(window_id, [])],
    } or target_state not in {
        "@default",
        *[s["id"] for s in project.states.get(target_window, [])],
    }:
        raise ProjectError("O estado da transição não existe.")
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
        raise ProjectError("Complete o rascunho desse evento antes de adicionar uma transição.")
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
                    "Esse evento usa Nós. Adicione e conecte a navegação no editor de Nós para escolher o caminho de execução."
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
    """Deriva estados realmente alcançados, respeitando handlers específicos sobre gerais."""
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
