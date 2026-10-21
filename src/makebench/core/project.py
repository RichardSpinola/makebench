"""Contrato inicial do projeto, compartilhado pelo editor e futuros geradores.

O documento visual é a fonte de verdade. Código Python personalizado continuará
em arquivos próprios, sem ser reescrito ao regenerar a interface.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterator
from uuid import uuid4

FORMAT_VERSION = 1
FORMAT_NAME = "makebench.project"


class ProjectError(ValueError):
    """Documento ou alteração incompatível com as regras do projeto."""


class ComponentKind(StrEnum):
    """Componentes reconhecidos pelo primeiro editor de interface."""

    WINDOW = "window"
    CONTAINER = "container"
    LABEL = "label"
    BUTTON = "button"
    TEXT_INPUT = "text_input"
    CHECKBOX = "checkbox"
    PROGRESS = "progress"
    OUTPUT = "output"


class LayoutKind(StrEnum):
    """Organização dos filhos de uma janela ou contêiner."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GRID = "grid"
    FREE = "free"


CONTAINER_KINDS = {ComponentKind.WINDOW, ComponentKind.CONTAINER}
KIND_LABELS = {
    ComponentKind.WINDOW: "Janela",
    ComponentKind.CONTAINER: "Contêiner",
    ComponentKind.LABEL: "Texto",
    ComponentKind.BUTTON: "Botão",
    ComponentKind.TEXT_INPUT: "Campo de texto",
    ComponentKind.CHECKBOX: "Caixa de seleção",
    ComponentKind.PROGRESS: "Progresso",
    ComponentKind.OUTPUT: "Painel de saída",
}
LAYOUT_LABELS = {
    LayoutKind.VERTICAL: "Coluna",
    LayoutKind.HORIZONTAL: "Linha",
    LayoutKind.GRID: "Grade",
    LayoutKind.FREE: "Livre",
}


def new_id(prefix: str) -> str:
    """Cria um identificador que permanece estável ao salvar e reabrir."""
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class Component:
    """Nó da interface, suas propriedades e seus filhos ordenados.

    A geometria é usada pelo pai em modo livre. Nos demais layouts, o toolkit
    distribui os filhos automaticamente. Valores são expressos em pixels lógicos.
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
        """Indica se o editor pode inserir componentes dentro deste nó."""
        return self.kind in CONTAINER_KINDS

    @property
    def display_name(self) -> str:
        """Descrição curta para a árvore de componentes."""
        text = self.properties.get("title") or self.properties.get("text")
        return f"{KIND_LABELS[self.kind]} · {str(text)[:40]}" if text else KIND_LABELS[self.kind]

    def walk(self) -> Iterator[Component]:
        """Percorre a árvore em ordem de apresentação, incluindo este nó."""
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        """Produz dados JSON independentes das instâncias em memória."""
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
        """Lê um nó sem executar conteúdo do projeto; rejeita forma inválida."""
        if depth > 64:
            raise ProjectError("A interface excede o limite de 64 níveis de contêineres.")
        if not isinstance(value, dict):
            raise ProjectError("Cada componente precisa ser um objeto.")
        try:
            component_id = value["id"]
            kind = ComponentKind(value["kind"])
            layout = LayoutKind(value.get("layout", "vertical"))
        except (KeyError, ValueError, TypeError) as exc:
            raise ProjectError("Componente sem identificador, tipo ou layout válido.") from exc
        if not isinstance(component_id, str) or not component_id.strip():
            raise ProjectError("O identificador do componente precisa ser um texto não vazio.")
        properties = value.get("properties", {})
        children = value.get("children", [])
        geometry = value.get("geometry", {"x": 16, "y": 16, "width": 220, "height": 44})
        if not isinstance(properties, dict) or not isinstance(children, list):
            raise ProjectError(f"Propriedades ou filhos inválidos em {component_id}.")
        if not isinstance(geometry, dict) or set(geometry) != {"x", "y", "width", "height"}:
            raise ProjectError(f"Geometria inválida em {component_id}.")
        for key, number in geometry.items():
            if (
                type(number) is not int
                or number < (1 if key in {"width", "height"} else 0)
                or number > 20000
            ):
                raise ProjectError(f"Geometria inválida em {component_id}: {key}.")
        for key in ("title", "text", "placeholder"):
            if key in properties and not isinstance(properties[key], str):
                raise ProjectError(f"A propriedade {key} de {component_id} precisa ser texto.")
        if "checked" in properties and type(properties["checked"]) is not bool:
            raise ProjectError(f"A seleção de {component_id} precisa ser verdadeira ou falsa.")
        if "value" in properties and (
            type(properties["value"]) is not int or not 0 <= properties["value"] <= 100
        ):
            raise ProjectError(f"O progresso de {component_id} precisa estar entre 0 e 100.")
        node = cls(
            id=component_id,
            kind=kind,
            properties=deepcopy(properties),
            layout=layout,
            geometry=dict(geometry),
            children=[cls.from_dict(child, depth + 1) for child in children],
        )
        if node.children and not node.can_have_children:
            raise ProjectError(f"{KIND_LABELS[node.kind]} não pode conter outros componentes.")
        if depth and node.kind == ComponentKind.WINDOW:
            raise ProjectError("Uma janela não pode ficar dentro de outro componente.")
        return node


def create_component(kind: ComponentKind) -> Component:
    """Cria um componente com propriedades iniciais apropriadas ao tipo."""
    kind = ComponentKind(kind)
    defaults = {
        ComponentKind.WINDOW: {"title": "Meu aplicativo"},
        ComponentKind.CONTAINER: {},
        ComponentKind.LABEL: {"text": "Novo texto"},
        ComponentKind.BUTTON: {"text": "Novo botão"},
        ComponentKind.TEXT_INPUT: {"text": "", "placeholder": "Digite aqui"},
        ComponentKind.CHECKBOX: {"text": "Nova opção", "checked": False},
        ComponentKind.PROGRESS: {"value": 0},
        ComponentKind.OUTPUT: {"text": "A saída das tarefas aparecerá aqui."},
    }
    node = Component(id=new_id(kind.value), kind=kind, properties=defaults[kind].copy())
    if node.can_have_children:
        node.geometry.update(width=360, height=240)
    elif kind == ComponentKind.OUTPUT:
        node.geometry.update(width=360, height=140)
    return node


@dataclass
class Project:
    """Documento visual e extensões preservadas para as próximas etapas.

    Workflows e metadados são somente dados nesta etapa. Abrir um projeto nunca
    importa funções Python nem dispara comandos ou scripts.
    """

    name: str
    root: Component
    id: str = field(default_factory=lambda: new_id("project"))
    workflows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, name: str = "Novo aplicativo") -> Project:
        """Cria uma janela vazia para começar um projeto."""
        root = create_component(ComponentKind.WINDOW)
        root.properties["title"] = name
        return cls(name=name, root=root)

    def find(self, component_id: str) -> Component | None:
        """Localiza um componente por seu identificador estável."""
        return next((node for node in self.root.walk() if node.id == component_id), None)

    def parent_of(self, component_id: str) -> Component | None:
        """Localiza o contêiner pai; a raiz não tem pai."""
        return next(
            (node for node in self.root.walk() if any(c.id == component_id for c in node.children)),
            None,
        )

    def add(self, parent_id: str, kind: ComponentKind) -> Component:
        """Insere um novo componente; não permite inserir janelas internas."""
        parent = self.find(parent_id)
        if parent is None or not parent.can_have_children:
            raise ProjectError("Selecione uma janela ou um contêiner para inserir o componente.")
        if ComponentKind(kind) == ComponentKind.WINDOW:
            raise ProjectError("Use um contêiner para agrupar componentes dentro da janela.")
        child = create_component(kind)
        child.geometry.update(x=16 + len(parent.children) * 16, y=16 + len(parent.children) * 16)
        parent.children.append(child)
        return child

    def remove(self, component_id: str) -> str:
        """Remove um componente e seus filhos e retorna o identificador do pai."""
        parent = self.parent_of(component_id)
        if parent is None:
            raise ProjectError("A janela principal não pode ser excluída.")
        subtree = {node.id for node in self.find(component_id).walk()}
        if self.workflows:
            raise ProjectError(
                "Este projeto contém lógica. A exclusão depende da validação de referências, "
                "prevista para a etapa de blocos."
            )
        parent.children = [child for child in parent.children if child.id not in subtree]
        return parent.id

    def to_dict(self) -> dict[str, Any]:
        """Serializa um retrato independente do documento, mantendo extensões."""
        return {
            "format": FORMAT_NAME,
            "format_version": FORMAT_VERSION,
            "id": self.id,
            "name": self.name,
            "ui": self.root.to_dict(),
            "workflows": deepcopy(self.workflows),
            "metadata": deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Any) -> Project:
        """Valida o formato, a versão e a unicidade de identificadores."""
        if not isinstance(value, dict) or value.get("format") != FORMAT_NAME:
            raise ProjectError("Este arquivo não é um projeto Makebench.")
        version = value.get("format_version")
        if type(version) is not int or version != FORMAT_VERSION:
            raise ProjectError(
                f"Versão de projeto não suportada: {version}. "
                "Abra-o com uma versão compatível do Makebench."
            )
        for key in ("name", "id"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ProjectError(f"O projeto precisa de {key} não vazio.")
        root = Component.from_dict(value.get("ui"))
        if root.kind != ComponentKind.WINDOW:
            raise ProjectError("A interface precisa começar com uma janela.")
        ids = [node.id for node in root.walk()]
        if len(set(ids)) != len(ids):
            raise ProjectError("O projeto contém identificadores de componentes repetidos.")
        workflows = value.get("workflows", [])
        metadata = value.get("metadata", {})
        if not isinstance(workflows, list) or any(not isinstance(w, dict) for w in workflows):
            raise ProjectError("A lista de fluxos de lógica é inválida.")
        if not isinstance(metadata, dict):
            raise ProjectError("Os metadados do projeto precisam ser um objeto.")
        return cls(
            name=value["name"], id=value["id"], root=root,
            workflows=deepcopy(workflows), metadata=deepcopy(metadata),
        )
