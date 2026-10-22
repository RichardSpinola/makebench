"""Lógica portátil: eventos e operações independentes de Blockly e Qt."""

from __future__ import annotations

import ast
from copy import deepcopy
import keyword
import math
from typing import TYPE_CHECKING

from .project import ComponentKind, ProjectError, new_id

if TYPE_CHECKING:
    from .project import Project

LOGIC_VERSION = 1
TEXT_KINDS = {ComponentKind.LABEL, ComponentKind.BUTTON, ComponentKind.TEXT_INPUT,
              ComponentKind.CHECKBOX, ComponentKind.OUTPUT}


def editable(project: Project) -> bool:
    """Reconhece lógica desta versão sem reinterpretar extensões antigas."""
    return not project.workflows or project.metadata.get("logic_version") == LOGIC_VERSION


def create_flow(project: Project, component_id: str, states: list[str] | None = None) -> dict:
    """Vincula início de janela ou clique de botão; reutiliza vínculo existente."""
    if not editable(project):
        raise ProjectError("Este projeto contém fluxos de outra versão. Eles foram preservados; a edição exige migração.")
    node = project.find(component_id)
    if node is None or node.kind not in {ComponentKind.WINDOW, ComponentKind.BUTTON}:
        raise ProjectError("Selecione a janela ou um botão para criar um evento.")
    event = {"kind": "start" if node.kind == ComponentKind.WINDOW else "click", "component": node.id}
    for flow in project.workflows:
        if flow["event"] == event and sorted(flow.get("states", [])) == sorted(states or []):
            return flow
    project.metadata["logic_version"] = LOGIC_VERSION
    flow = {"id": new_id("flow"), "name": "Ao iniciar" if event["kind"] == "start" else f"Clique: {node.properties.get('text', 'Botão')}",
            "event": event, "body": [], "workspace": {}}
    if states:
        flow["states"] = list(states)
    project.workflows.append(flow)
    return flow


def function_names(source: str) -> tuple[list[str], str | None]:
    """Inspeciona assinaturas sem importar nem executar o arquivo Python."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return [], f"Funções Python: {exc}"
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)
             and not node.name.startswith("_")]
    return names, None


def validate(project: Project) -> None:
    """Rejeita eventos/referências inválidos e limita profundidade e volume da lógica.

    body=None representa um rascunho incompleto; seu workspace é preservado,
    mas não recebe código executável. Fluxos reservados antigos não são alterados.
    """
    version = project.metadata.get("logic_version")
    if version is None:
        return
    if type(version) is not int or version != LOGIC_VERSION:
        raise ProjectError("Versão de lógica não suportada; use um Makebench compatível.")
    seen_flows, seen_events = set(), set()
    for flow in project.workflows:
        if not isinstance(flow.get("id"), str) or not flow["id"] or flow["id"] in seen_flows:
            raise ProjectError("Identificador de fluxo ausente ou repetido.")
        seen_flows.add(flow["id"])
        if not isinstance(flow.get("name"), str):
            raise ProjectError("O nome do fluxo precisa ser texto.")
        event = flow.get("event", {})
        if not isinstance(event, dict):
            raise ProjectError("Evento inválido.")
        node = project.find(event.get("component"))
        expected = ComponentKind.WINDOW if event.get("kind") == "start" else ComponentKind.BUTTON
        if event.get("kind") not in {"start", "click"} or node is None or node.kind != expected:
            raise ProjectError("O evento precisa apontar para a janela ou um botão existente.")
        states = flow.get('states', [])
        owner = project.window_of(node.id)
        state_ids = {'@default', *[item['id'] for item in project.states.get(owner.id, [])]}
        if not isinstance(states, list) or any(not isinstance(item,str) or item not in state_ids for item in states) or len(states) != len(set(states)):
            raise ProjectError('Filtro de estado inválido.')
        key = (event["kind"], node.id, tuple(sorted(states)))
        if key in seen_events:
            raise ProjectError("Há mais de um fluxo para o mesmo evento.")
        seen_events.add(key)
        if not isinstance(flow.get("workspace", {}), dict):
            raise ProjectError("O estado visual dos blocos precisa ser um objeto.")
        if not isinstance(flow.get("errors", []), list) or any(not isinstance(e, str) for e in flow.get("errors", [])):
            raise ProjectError("Diagnósticos dos blocos inválidos.")
        ids: set[str] = set()

        def target(value, kinds=None):
            """Valida referência sem depender do toolkit de interface."""
            found = project.find(value)
            if found is None or (kinds and found.kind not in kinds):
                raise ProjectError("Um bloco aponta para componente inexistente ou incompatível.")

        def visit(value, expression=False, depth=0):
            """Valida os nós de uma árvore sem aceitar Python arbitrário como expressão."""
            if depth > 48 or len(ids) >= 5000:
                raise ProjectError("Lógica excede 48 níveis ou 5000 blocos por evento.")
            if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"] or value["id"] in ids:
                raise ProjectError("Bloco sem identificador único.")
            ids.add(value["id"])
            if "comment" in value and not isinstance(value["comment"], str):
                raise ProjectError("Comentário de bloco precisa ser texto.")
            op = value.get("op")
            def expr(key):
                """Valida uma entrada de valor obrigatória."""
                visit(value.get(key), True, depth + 1)
            def body(key):
                """Valida uma sequência ordenada de instruções."""
                sequence(value.get(key), depth + 1)
            def text(key, identifier=False):
                """Valida campos textuais e nomes de funções Python."""
                item = value.get(key)
                if not isinstance(item, str) or not item.strip() or (identifier and (not item.isidentifier() or keyword.iskeyword(item) or item.startswith("_"))):
                    raise ProjectError(f"Campo inválido no bloco: {key}.")
            if expression:
                if op == "literal":
                    item = value.get("value")
                    if type(item) not in {str, bool, int, float} or (type(item) is float and not math.isfinite(item)):
                        raise ProjectError("Valor literal inválido.")
                elif op == "list":
                    items = value.get("items")
                    if not isinstance(items, list) or len(items) > 256:
                        raise ProjectError("Uma lista de valores aceita até 256 itens.")
                    for item in items:
                        visit(item, True, depth + 1)
                elif op == "variable":
                    text("name")
                    if value.get("scope", "project") not in {"project", "window", "local"}:raise ProjectError("Escopo inválido.")
                elif op == "read":
                    attribute = value.get("attribute")
                    kinds = TEXT_KINDS if attribute == "text" else {ComponentKind.CHECKBOX} if attribute == "checked" else {ComponentKind.PROGRESS} if attribute == "value" else set()
                    if not kinds:
                        raise ProjectError("Propriedade de leitura desconhecida.")
                    target(value.get("component"), kinds)
                elif op == "binary":
                    if value.get("operator") not in {"+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or"}:
                        raise ProjectError("Operador desconhecido.")
                    expr("left"); expr("right")
                elif op == "join":
                    expr("left"); expr("right")
                else:
                    raise ProjectError(f"Expressão desconhecida: {op}.")
            elif op in {"log", "message"}:
                expr("value")
            elif op in {"set_text", "set_enabled", "set_value"}:
                target(value.get("component"), TEXT_KINDS if op == "set_text" else {ComponentKind.PROGRESS} if op == "set_value" else None)
                expr("value")
            elif op == "show_page":
                target(value.get("component"), {ComponentKind.PAGE})
            elif op in {'go_state', 'open_window', 'close_window'}:
                if op == 'go_state' and value.get('state') not in state_ids:
                    raise ProjectError('A transição aponta para estado inexistente.')
                if op == 'open_window':
                    target(value.get('window'), {ComponentKind.WINDOW})
                    if type(value.get('close_current', False)) is not bool:raise ProjectError('Opção de fechar janela inválida.')
            elif op == "assign":
                text("name"); expr("value")
                if value.get('scope', 'project') not in {'project', 'window', 'local'}:raise ProjectError('Escopo inválido.')
            elif op == "if":
                expr("condition"); body("then"); body("else")
            elif op == "repeat":
                expr("count"); body("body")
            elif op == "call":
                text("function", True); expr("value")
            elif op in {"run", "script"}:
                expr("program" if op == "run" else "source"); expr("arguments")
                if type(value.get("admin")) is not bool:
                    raise ProjectError("A permissão administrativa precisa ser declarada no bloco.")
            elif op == "ask":
                if value.get("kind") not in {"text", "choice", "file", "directory"}:
                    raise ProjectError("Tipo de pergunta desconhecido.")
                text("name"); expr("prompt"); expr("options")
                if value.get("scope","project") not in {"project","window","local"}:raise ProjectError("Escopo inválido na pergunta.")
            elif op == "confirm":
                expr("prompt")
            else:
                raise ProjectError(f"Operação desconhecida: {op}.")

        def sequence(items, depth=0):
            """Valida uma lista de instruções sem interpretar seus efeitos."""
            if not isinstance(items, list):
                raise ProjectError("A sequência de blocos precisa ser uma lista.")
            for item in items:
                visit(item, False, depth)

        if flow.get("body") is not None:
            sequence(flow["body"])
        elif not flow.get("workspace"):
            raise ProjectError("Um fluxo incompleto precisa preservar seus blocos.")


def referenced_components(flow: dict) -> set[str]:
    """Coleta referências de componentes sem confundir textos com identificadores."""
    result = {flow["event"]["component"]}
    def walk(item):
        """Percorre somente a representação de lógica, ignorando a vista Blockly."""
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
    """Impede apagar alvos usados pela lógica, indicando como resolver o vínculo."""
    if not editable(project) and project.workflows:
        raise ProjectError("Fluxos reservados exigem validação de referências antes da exclusão.")
    for flow in project.workflows:
        if flow.get("body") is None or ids & referenced_components(flow):
            raise ProjectError(f"Revise ou remova o fluxo ‘{flow['name']}’ na aba Lógica antes de excluir este componente.")


def duplicate_flows(project: Project, identifiers: dict[str, str]) -> None:
    """Copia eventos da subárvore duplicada e remapeia apenas referências internas."""
    copies = []
    for flow in project.workflows:
        if flow["event"]["component"] not in identifiers:
            continue
        if flow.get("body") is None:
            raise ProjectError("Complete os blocos deste componente antes de duplicá-lo.")
        clone = deepcopy(flow)
        clone.update(id=new_id("flow"), name=flow["name"] + " (cópia)", workspace={"workspaceComments": deepcopy(flow.get("workspace", {}).get("workspaceComments", []))})
        def remap(item):
            """Regenera IDs de nós e remapeia alvos preservando referências externas."""
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
        remap(clone["event"]); remap(clone["body"])
        copies.append(clone)
    project.workflows.extend(copies)
