"""Contrato inicial do projeto, compartilhado pelo editor e futuros geradores.

O documento visual é a fonte de verdade. Código Python personalizado continuará
em arquivos próprios, sem ser reescrito ao regenerar a interface.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Iterator
from uuid import uuid4

FORMAT_VERSION = 4
FORMAT_NAME = "makebench.project"


class ProjectError(ValueError):
    """Documento ou alteração incompatível com as regras do projeto."""


class ComponentKind(StrEnum):
    """Componentes reconhecidos pelo primeiro editor de interface."""

    WINDOW = "window"
    CONTAINER = "container"
    PAGES = "pages"
    PAGE = "page"
    IMAGE = "image"
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


CONTAINER_KINDS = {
    ComponentKind.WINDOW, ComponentKind.CONTAINER, ComponentKind.PAGES, ComponentKind.PAGE,
}
KIND_LABELS = {
    ComponentKind.WINDOW: "Janela",
    ComponentKind.CONTAINER: "Contêiner",
    ComponentKind.PAGES: "Páginas com abas",
    ComponentKind.PAGE: "Página",
    ComponentKind.IMAGE: "Imagem",
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

    def accepts(self, kind: ComponentKind) -> bool:
        """Respeita a estrutura de páginas e impede janelas dentro da interface."""
        if self.kind == ComponentKind.PAGES:
            return kind == ComponentKind.PAGE
        return self.can_have_children and kind not in {ComponentKind.WINDOW, ComponentKind.PAGE}

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
        if kind == ComponentKind.IMAGE and "source" in properties and not isinstance(properties["source"], str):
            raise ProjectError("O caminho da imagem precisa ser texto.")
        if kind == ComponentKind.IMAGE and properties.get("source"):
            source = properties["source"]
            if not isinstance(source, str):
                raise ProjectError("O caminho da imagem precisa ser texto.")
            path = PurePosixPath(source)
            if (
                path.is_absolute() or ".." in path.parts or "\\" in source
                or len(path.parts) < 2 or path.parts[0] != "assets"
            ):
                raise ProjectError("A imagem precisa estar na pasta assets do projeto.")
        for key in ("alt_text", "image_name"):
            if key in properties and not isinstance(properties[key], str):
                raise ProjectError("A descrição e o nome da imagem precisam ser texto.")
        if "columns" in properties and (
            type(properties["columns"]) is not int or not 1 <= properties["columns"] <= 12
        ):
            raise ProjectError("A grade precisa ter entre 1 e 12 colunas.")
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
        if any(not node.accepts(child.kind) for child in node.children):
            raise ProjectError("Páginas devem ficar dentro de um conjunto de páginas.")
        if kind == ComponentKind.PAGES:
            if not node.children:
                raise ProjectError("Um conjunto de páginas precisa de pelo menos uma página.")
            initial = properties.get("initial_page", node.children[0].id)
            if not isinstance(initial, str) or initial not in {child.id for child in node.children}:
                raise ProjectError("A página inicial não pertence a este conjunto de páginas.")
            node.properties["initial_page"] = initial
        if depth and node.kind == ComponentKind.WINDOW:
            raise ProjectError("Uma janela não pode ficar dentro de outro componente.")
        return node


def create_component(kind: ComponentKind) -> Component:
    """Cria um componente com propriedades iniciais apropriadas ao tipo."""
    kind = ComponentKind(kind)
    defaults = {
        ComponentKind.WINDOW: {"title": "Meu aplicativo"},
        ComponentKind.CONTAINER: {},
        ComponentKind.PAGES: {},
        ComponentKind.PAGE: {"title": "Nova página"},
        ComponentKind.IMAGE: {"source": "", "alt_text": "Imagem do aplicativo"},
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
    elif kind == ComponentKind.IMAGE:
        node.geometry.update(width=240, height=160)
    elif kind == ComponentKind.OUTPUT:
        node.geometry.update(width=360, height=140)
    if kind == ComponentKind.PAGES:
        page = create_component(ComponentKind.PAGE)
        page.properties["title"] = "Página 1"
        node.children.append(page)
        node.properties["initial_page"] = page.id
    return node


@dataclass
class Project:
    """Documento visual com lógica portátil e extensões preservadas.

    Workflows e metadados são somente dados. Abrir um projeto nunca
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
        if not parent.accepts(ComponentKind(kind)):
            raise ProjectError("Adicione páginas a um conjunto de páginas e controles a uma página ou contêiner.")
        child = create_component(kind)
        self._check_depth(parent, child)
        if child.kind == ComponentKind.PAGE:
            child.properties["title"] = f"Página {len(parent.children) + 1}"
        child.geometry.update(
            x=min(20000, 16 + len(parent.children) * 16),
            y=min(20000, 16 + len(parent.children) * 16),
        )
        parent.children.append(child)
        return child

    def remove(self, component_id: str) -> str:
        """Remove um componente e seus filhos e retorna o identificador do pai."""
        parent = self.parent_of(component_id)
        if parent is None:
            raise ProjectError("A janela principal não pode ser excluída.")
        subtree = {node.id for node in self.find(component_id).walk()}
        from .logic import guard_removal
        guard_removal(self, subtree)
        self._check_last_page(parent)
        parent.children = [child for child in parent.children if child.id not in subtree]
        self._repair_initial_page(parent)
        return parent.id

    def _check_last_page(self, parent: Component) -> None:
        """Impede esvaziar um conjunto de páginas ao excluir ou transferir a última."""
        if parent.kind == ComponentKind.PAGES and len(parent.children) == 1:
            raise ProjectError("Mantenha pelo menos uma página neste conjunto.")

    def _repair_initial_page(self, parent: Component) -> None:
        """Seleciona a primeira página restante se a inicial foi removida."""
        if parent.kind == ComponentKind.PAGES:
            if parent.properties.get("initial_page") not in {node.id for node in parent.children}:
                parent.properties["initial_page"] = parent.children[0].id

    def _check_depth(self, parent: Component, child: Component) -> None:
        """Valida o limite estrutural antes de inserir ou mover uma subárvore."""
        depth = 0
        ancestor = parent
        while ancestor.id != self.root.id:
            ancestor = self.parent_of(ancestor.id)
            depth += 1

        def height(node: Component) -> int:
            """Conta a profundidade máxima da subárvore antes da inserção."""
            return max((height(item) + 1 for item in node.children), default=0)

        if depth + 1 + height(child) > 64:
            raise ProjectError("A interface excede o limite de 64 níveis de contêineres.")

    def move(self, component_id: str, parent_id: str, index: int | None = None) -> bool:
        """Move uma subárvore sem alterar IDs, recusando ciclos e hierarquia inválida.

        O índice é uma posição de inserção na lista de destino antes da remoção.
        Isso representa os espaços antes/depois dos itens no arraste. Retorna
        falso quando a posição não muda e não modifica nada em caso de erro.
        """
        node, parent = self.find(component_id), self.find(parent_id)
        previous = self.parent_of(component_id)
        if node is None or parent is None or previous is None:
            raise ProjectError("A janela principal não pode ser movida.")
        if parent.id in {child.id for child in node.walk()}:
            raise ProjectError("Um componente não pode ficar dentro de si mesmo ou de seus filhos.")
        if not parent.accepts(node.kind):
            raise ProjectError("Este destino não aceita esse tipo de componente.")
        self._check_depth(parent, node)
        if previous.id != parent.id:
            self._check_last_page(previous)
        index = len(parent.children) if index is None else max(0, min(index, len(parent.children)))
        previous_index = previous.children.index(node)
        if previous is parent and previous_index < index:
            index -= 1
        if previous is parent and previous_index == index:
            return False
        previous.children.remove(node)
        parent.children.insert(index, node)
        self._repair_initial_page(previous)
        return True

    def duplicate(self, component_id: str) -> Component:
        """Duplica uma subárvore com novos IDs e referências internas remapeadas."""
        parent, node = self.parent_of(component_id), self.find(component_id)
        if parent is None or node is None:
            raise ProjectError("A janela principal não pode ser duplicada.")
        from .logic import editable, duplicate_flows
        if not editable(self):
            raise ProjectError("Fluxos reservados impedem duplicação sem migração.")
        clone = deepcopy(node)
        identifiers = {}
        for item in clone.walk():
            old_id = item.id
            item.id = new_id(item.kind.value)
            identifiers[old_id] = item.id
        for item in clone.walk():
            if item.kind == ComponentKind.PAGES:
                item.properties["initial_page"] = identifiers[item.properties["initial_page"]]
        for key in ("title", "text"):
            if clone.properties.get(key):
                clone.properties[key] += " (cópia)"
                break
        clone.geometry["x"] = min(20000, clone.geometry["x"] + 16)
        clone.geometry["y"] = min(20000, clone.geometry["y"] + 16)
        duplicate_flows(self, identifiers)
        parent.children.insert(parent.children.index(node) + 1, clone)
        return clone

    def set_geometry(self, component_id: str, geometry: dict[str, int]) -> bool:
        """Confirma posição/tamanho de um gesto livre, em uma única alteração."""
        node = self.find(component_id)
        parent = self.parent_of(component_id)
        if node is None or parent is None or parent.layout != LayoutKind.FREE or parent.kind == ComponentKind.PAGES:
            raise ProjectError("Posição e tamanho manuais exigem um contêiner de organização livre.")
        candidate = node.to_dict()
        candidate["geometry"].update(geometry)
        validated = Component.from_dict(candidate)
        if node.geometry == validated.geometry:
            return False
        node.geometry = validated.geometry
        return True

    def asset_paths(self) -> set[str]:
        """Retorna imagens referenciadas para preservar os recursos no Salvar como."""
        return {
            node.properties["source"] for node in self.root.walk()
            if node.kind == ComponentKind.IMAGE and node.properties.get("source")
        }

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
        if type(version) is not int or version not in (1, 2, 3, FORMAT_VERSION):
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
        project = cls(
            name=value["name"], id=value["id"], root=root,
            workflows=deepcopy(workflows), metadata=deepcopy(metadata),
        )
        from .logic import validate
        validate(project)
        return project
