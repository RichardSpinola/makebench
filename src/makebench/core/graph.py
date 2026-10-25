"""Grafo livre independente de Blockly: portas, validação e compilador de estados."""

from __future__ import annotations
from copy import deepcopy
import json
import keyword
import math
from .project import ComponentKind, ProjectError, new_id

# Entradas de valor são distintas das saídas de execução; posições ficam no fluxo.
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
    "event": "Evento",
    "constant": "Constante",
    "variable": "Valor de variável",
    "read": "Ler componente",
    "binary": "Operação",
    "join": "Juntar textos",
    "if": "Condição",
    "repeat": "Repetir",
    "sequence": "Sequência",
    "return": "Retornar",
    "log": "Registrar na saída",
    "message": "Mensagem",
    "assign": "Definir variável",
    "set_text": "Alterar texto",
    "set_enabled": "Habilitar componente",
    "set_value": "Alterar progresso",
    "call": "Função própria",
    "run": "Executar programa",
    "script": "Executar Bash",
    "terminal_start": "Iniciar terminal",
    "terminal_send": "Enviar ao terminal",
    "terminal_stop": "Encerrar terminal",
    "go_state": "Ir para estado",
    "open_window": "Abrir janela",
    "close_window": "Fechar janela",
    "show_page": "Mostrar página",
    "ask": "Perguntar",
    "confirm": "Confirmar",
}
OPERATORS = {"+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or"}


def execution_outputs(node):
    """Define portas de execução sem inferir ordem pela posição visual do nó."""
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
    """Classifica valores JSON; booleano não é confundido com número."""
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
    """Tipo estático de uma porta de valor; variáveis e resultados são dinâmicos."""
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
    """Prepara um novo grafo de evento; a substituição exige confirmação na IDE."""
    entry = new_id("node")
    return {
        "graph_version": 1,
        "entry": entry,
        "nodes": [{"id": entry, "op": "event", "parameters": {}, "inputs": {}}],
        "edges": [],
    }


def replace_editor(flow, editor):
    """Troca explicitamente a fonte de verdade e guarda a representação anterior inteira."""
    if editor not in {"blocks", "nodes"}:
        raise ProjectError("Editor de comportamento desconhecido.")
    current = flow.get("editor", "blocks")
    if current == editor:
        return
    previous = {
        key: deepcopy(value) for key, value in flow.items() if key not in {"behavior_backups"}
    }
    if len(flow.get("behavior_backups", [])) >= 1000:
        raise ProjectError("Limite de 1000 versões recuperáveis atingido.")
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
    """Restaura uma cópia recuperável e conserva a versão atual na mesma lista."""
    backups = flow.get("behavior_backups", [])
    if not backups:
        raise ProjectError("Não há comportamento anterior para restaurar.")
    restored = deepcopy(backups[index])
    current = {k: deepcopy(v) for k, v in flow.items() if k != "behavior_backups"}
    history = [deepcopy(item) for i, item in enumerate(backups) if i != index % len(backups)]
    history.append(current)
    flow.clear()
    flow.update(restored, behavior_backups=history)


def json_value(value, depth=0):
    """Valida constantes limitadas, sem Python arbitrário e sem números não finitos."""
    if depth > 12:
        raise ProjectError("Constante excede 12 níveis.")
    if type(value) in (str, int, float, bool, type(None)):
        if type(value) is str and len(value) > 100000:
            raise ProjectError("Constante textual muito extensa.")
        if type(value) is float and not math.isfinite(value):
            raise ProjectError("Constante numérica não finita.")
        return
    if type(value) is list and len(value) <= 256:
        for item in value:
            json_value(item, depth + 1)
        return
    if type(value) is dict and len(value) <= 256 and all(isinstance(k, str) for k in value):
        for item in value.values():
            json_value(item, depth + 1)
        return
    raise ProjectError("Use uma constante JSON válida e limitada.")


def validate_graph(project, flow):
    """Rejeita referências e portas inválidas e ciclos de valores; execução pode retornar."""
    graph = flow.get("graph")
    if (
        not isinstance(graph, dict)
        or type(graph.get("graph_version")) is not int
        or graph.get("graph_version") != 1
    ):
        raise ProjectError("Versão de grafo inválida.")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if (
        not isinstance(nodes, list)
        or not 1 <= len(nodes) <= 5000
        or not isinstance(edges, list)
        or len(edges) > 40000
    ):
        raise ProjectError("O grafo aceita até 5000 nós e 40000 conexões.")
    by_id = {}
    owner = project.window_of(flow["event"]["component"])
    states = {"@default", *[s["id"] for s in project.states.get(owner.id, [])]}

    def name(value):
        """Valida nome de função própria, sem usá-lo como trecho de código."""
        return (
            isinstance(value, str)
            and value.isidentifier()
            and not keyword.iskeyword(value)
            and not value.startswith("_")
        )

    def target(value, kinds=None):
        """Confere alvos contra o documento, mantendo referências por ID."""
        node = project.find(value)
        if node is None or (kinds and node.kind not in kinds):
            raise ProjectError("Nó aponta para componente inexistente ou incompatível.")

    for node in nodes:
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("id"), str)
            or not node["id"]
            or node["id"] in by_id
            or not isinstance(node.get("op"), str)
            or node.get("op") not in VALUE_INPUTS
        ):
            raise ProjectError("Nó sem ID único ou operação reconhecida.")
        by_id[node["id"]] = node
        op = node["op"]
        p = node.get("parameters", {})
        inputs = node.get("inputs", {})
        if (
            not isinstance(p, dict)
            or not isinstance(inputs, dict)
            or inputs.keys() - VALUE_INPUTS[op].keys()
        ):
            raise ProjectError("Porta de entrada desconhecida.")
        if not isinstance(node.get("comment", ""), str):
            raise ProjectError("Comentário de nó precisa ser texto.")
        if op == "constant":
            json_value(p.get("value"))
        if op in {"variable", "assign", "ask"}:
            if (
                not isinstance(p.get("name"), str)
                or not p["name"].strip()
                or p.get("scope", "project") not in ("project", "window", "local")
            ):
                raise ProjectError("Variável de nó inválida.")
        if op == "call" and not name(p.get("function")):
            raise ProjectError("Função própria de nó inválida.")
        if op == "binary" and (
            not isinstance(p.get("operator"), str) or p.get("operator") not in OPERATORS
        ):
            raise ProjectError("Operador de nó desconhecido.")
        if op == "sequence" and (
            type(p.get("count", 2)) is not int or not 2 <= p.get("count", 2) <= 8
        ):
            raise ProjectError("Sequência aceita entre 2 e 8 saídas.")
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
                raise ProjectError("Propriedade de leitura inválida.")
        if op == "go_state" and (
            not isinstance(p.get("state"), str) or p.get("state") not in states
        ):
            raise ProjectError("Estado de nó inexistente.")
        if op == "open_window":
            target(p.get("window"), {ComponentKind.WINDOW})
            if type(p.get("close_current", False)) is not bool:
                raise ProjectError("Opção de fechar janela inválida.")
        if op in {"run", "script"} and type(p.get("admin", False)) is not bool:
            raise ProjectError("Permissão de tarefa inválida.")
        if op == "ask" and p.get("kind", "text") not in ("text", "choice", "file", "directory"):
            raise ProjectError("Pergunta de nó inválida.")
    if (
        not isinstance(graph.get("entry"), str)
        or graph.get("entry") not in by_id
        or by_id[graph["entry"]]["op"] != "event"
        or sum(n["op"] == "event" for n in nodes) != 1
    ):
        raise ProjectError("Mantenha um único nó de evento como entrada.")
    for node in nodes:
        for port, expected in VALUE_INPUTS[node["op"]].items():
            binding = node.get("inputs", {}).get(port)
            if not isinstance(binding, dict) or set(binding) not in ({"value"}, {"node", "port"}):
                raise ProjectError("Preencha todas as entradas de valor do nó.")
            if "value" in binding:
                json_value(binding["value"])
                actual = value_type(binding["value"])
            else:
                if not isinstance(binding["node"], str) or not isinstance(binding["port"], str):
                    raise ProjectError("Identificador de porta de valor inválido.")
                producer = by_id.get(binding["node"])
                if producer is None or binding["port"] != "value" or output_type(producer) is None:
                    raise ProjectError("Conexão de valor aponta para porta inexistente.")
                actual = output_type(producer)
            if expected != "any" and actual not in {"any", expected}:
                raise ProjectError(f"Tipos incompatíveis na entrada {port}: {expected} esperado.")
    used = set()
    for edge in edges:
        if (
            not isinstance(edge, dict)
            or set(edge) != {"from", "out", "to"}
            or any(not isinstance(edge[k], str) for k in ("from", "out", "to"))
            or edge["from"] not in by_id
            or edge["to"] not in by_id
        ):
            raise ProjectError("Conexão de execução inválida.")
        source, destination = by_id[edge["from"]], by_id[edge["to"]]
        if (
            edge["out"] not in execution_outputs(source)
            or destination["op"] in VALUE_OPS
            or destination["op"] == "event"
        ):
            raise ProjectError("Portas de execução incompatíveis.")
        key = (edge["from"], edge["out"])
        if key in used:
            raise ProjectError(
                "Cada saída de execução aceita uma conexão. Use Sequência para ramificar."
            )
        used.add(key)
    # DFS iterativa evita recursão Python em arquivos grandes ou malformados.
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
                raise ProjectError(
                    "Ciclo entre valores. Use uma variável para representar memória."
                )
            visiting.add(current)
            if len(visiting) > 100:
                raise ProjectError("Dependência de valores excede 100 níveis.")
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
        raise ProjectError("Posição visual de nó inválida.")
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
        raise ProjectError("Comentários livres do grafo inválidos.")


def default_node(op, project, flow):
    """Cria nó configurável com entradas literais; não executa ações ou gera fios implícitos."""
    if op not in VALUE_INPUTS or op == "event":
        raise ProjectError("Escolha um tipo de nó disponível.")
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
        p["value"] = "Olá!"
    if op in {"variable", "assign", "ask"}:
        p.update(name="valor", scope="project")
    if op == "call":
        p["function"] = "saudacao"
    if op == "binary":
        p["operator"] = "=="
    if op == "sequence":
        p["count"] = 2
    if op in {"run", "script"}:
        p["admin"] = False
    if op == "run":
        inputs["program"]["value"] = "uname"
    if op == "script":
        inputs["source"]["value"] = 'printf "Olá\\n"'
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
                "Insira um componente compatível nesta janela antes de criar este nó."
            )
        p["component"] = component.id
        if op == "read":
            p["attribute"] = "text"
    return {"id": new_id("node"), "op": op, "parameters": p, "inputs": inputs}


def compile_graph(flow, index, functions):
    """Compila fluxo livre para máquina de estados Python, sem criar árvore Blockly."""
    graph = flow["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {(e["from"], e["out"]): e["to"] for e in graph["edges"]}
    lines = [
        f"# {flow['name'].replace(chr(10), ' ').replace(chr(13), ' ')}",
        f"# Evento: {flow['event']['kind']} em {flow['event']['component']!r}",
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
        """Emite linha com indentação controlada pelo compilador."""
        lines.append("    " * indent + text)

    def expression(binding, path=()):
        """Resolve valores puros ou resultados previamente produzidos por execução."""
        if "value" in binding:
            return repr(binding["value"])
        return f"_value({binding['node']!r})"

    def node_expression(node):
        """Uma expressão por produtor; dependências são acessos em vez de expansão textual."""
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
    emit('raise RuntimeError("Produtor de valor inexistente.")', 2)
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
                    f"{flow['name']}: função ‘{p['function']}’ não encontrada em .actions.py."
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
    lines.extend(['        raise RuntimeError("Estado de execução do grafo inválido.")', ""])
    return lines, origins, diagnostics


def duplicate_graph(flow, components):
    """Regenera IDs e fios internos e remapeia componentes de uma cópia de comportamento."""
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
