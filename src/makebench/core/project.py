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

FORMAT_VERSION = 8
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
    TERMINAL = "terminal"
    SEPARATOR = "separator"
    SPACER = "spacer"


class LayoutKind(StrEnum):
    """Organização dos filhos de uma janela ou contêiner."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GRID = "grid"
    FREE = "free"


CONTAINER_KINDS = {
    ComponentKind.WINDOW,
    ComponentKind.CONTAINER,
    ComponentKind.PAGES,
    ComponentKind.PAGE,
}
KIND_LABELS = {
    ComponentKind.SEPARATOR: "Separador",
    ComponentKind.SPACER: "Espaçador",
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
    ComponentKind.TERMINAL: "Terminal",
}
LAYOUT_LABELS = {
    LayoutKind.VERTICAL: "Coluna",
    LayoutKind.HORIZONTAL: "Linha",
    LayoutKind.GRID: "Grade",
    LayoutKind.FREE: "Livre",
}


def has_graph(flow):
    """Detecta grafo ativo ou recuperável sem pressupor dados já validados."""
    backups = flow.get("behavior_backups", [])
    return (
        flow.get("editor") == "nodes"
        or isinstance(backups, list)
        and any(isinstance(item, dict) and item.get("editor") == "nodes" for item in backups)
    )


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
        if (
            kind == ComponentKind.IMAGE
            and "source" in properties
            and not isinstance(properties["source"], str)
        ):
            raise ProjectError("O caminho da imagem precisa ser texto.")
        if kind == ComponentKind.IMAGE and properties.get("source"):
            source = properties["source"]
            if not isinstance(source, str):
                raise ProjectError("O caminho da imagem precisa ser texto.")
            path = PurePosixPath(source)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in source
                or len(path.parts) < 2
                or path.parts[0] != "assets"
            ):
                raise ProjectError("A imagem precisa estar na pasta assets do projeto.")
        for key in ("alt_text", "image_name"):
            if key in properties and not isinstance(properties[key], str):
                raise ProjectError("A descrição e o nome da imagem precisam ser texto.")
        if "columns" in properties and (
            type(properties["columns"]) is not int or not 1 <= properties["columns"] <= 12
        ):
            raise ProjectError("A grade precisa ter entre 1 e 12 colunas.")
        if kind == ComponentKind.TERMINAL:
            if not isinstance(
                properties.get("terminal_program", ""), str
            ) or "\0" in properties.get("terminal_program", ""):
                raise ProjectError("Programa de terminal inválido.")
            arguments = properties.get("terminal_arguments", [])
            if (
                not isinstance(arguments, list)
                or len(arguments) > 256
                or any(not isinstance(a, str) or "\0" in a for a in arguments)
            ):
                raise ProjectError("Argumentos do terminal precisam ser uma lista de textos.")
            if type(properties.get("terminal_autostart", False)) is not bool:
                raise ProjectError("Início automático do terminal inválido.")
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
        ComponentKind.SEPARATOR: {},
        ComponentKind.SPACER: {"size_mode": {"width": "fill", "height": "fill"}},
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
        ComponentKind.TERMINAL: {
            "terminal_program": "",
            "terminal_arguments": [],
            "terminal_autostart": False,
        },
    }
    node = Component(id=new_id(kind.value), kind=kind, properties=defaults[kind].copy())
    if node.can_have_children:
        node.geometry.update(width=360, height=240)
    elif kind == ComponentKind.IMAGE:
        node.geometry.update(width=240, height=160)
    elif kind in {ComponentKind.OUTPUT, ComponentKind.TERMINAL}:
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
    windows: list[Component] = field(default_factory=list)
    states: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    entry_window: str | None = None
    variables: list[dict[str, Any]] = field(default_factory=list)
    map_layout: dict[str, list[float]] = field(default_factory=dict)
    format_version: int = 4
    application: dict[str, Any] = field(default_factory=dict)
    python_files: list[str] = field(default_factory=list)

    @property
    def editable_flows(self) -> list[dict[str, Any]]:
        """Retorna somente lógica reconhecida; extensões antigas continuam opacas."""
        from .logic import editable

        return self.workflows if editable(self) else []

    @property
    def roots(self) -> list[Component]:
        """Retorna janelas reais; a raiz legada continua sendo a primeira janela."""
        return [self.root, *self.windows]

    def walk(self) -> Iterator[Component]:
        """Percorre todas as janelas, com identificadores únicos no projeto."""
        for root in self.roots:
            yield from root.walk()

    def window_of(self, component_id: str) -> Component | None:
        """Resolve o escopo de janela de um componente, inclusive a própria janela."""
        return next(
            (root for root in self.roots if any(n.id == component_id for n in root.walk())), None
        )

    def effective_root(self, window_id: str, state_id: str = "@default") -> Component:
        """Aplica sobrescritas a uma cópia; nunca modifica a composição padrão."""
        root = next((r for r in self.roots if r.id == window_id), None)
        if root is None:
            raise ProjectError("A janela não existe.")
        clone = deepcopy(root)
        if state_id == "@default":
            return clone
        state = next(
            (item for item in self.states.get(window_id, []) if item["id"] == state_id), None
        )
        if state is None:
            raise ProjectError("O estado não pertence a esta janela.")
        for node in clone.walk():
            node.properties.update(deepcopy(state.get("overrides", {}).get(node.id, {})))
        return clone

    def uses_v5(self) -> bool:
        """Mantém escrita v4 até uma mudança que exige o contrato novo."""

        def new_logic(value):
            """Detecta semântica v5 em lógica completa ou em blocos ainda incompletos."""
            if isinstance(value, dict):
                if value.get("op") in {"go_state", "open_window", "close_window"} or value.get(
                    "scope"
                ) in {"window", "local"}:
                    return True
                if value.get("type") in {"mb_go_state", "mb_open_window", "mb_close_window"}:
                    return True
                fields = value.get("fields", {})
                if isinstance(fields, dict) and fields.get("SCOPE") in {"window", "local"}:
                    return True
                return any(new_logic(item) for item in value.values())
            if isinstance(value, list):
                return any(new_logic(item) for item in value)
            return False

        fields = {
            "spacing",
            "padding",
            "align",
            "distribute",
            "size_mode",
            "free_geometry",
            "icon",
            "tooltip",
        }
        return bool(
            self.format_version >= 5
            or self.application
            or self.windows
            or self.states
            or self.variables
            or self.map_layout
            or any(
                n.kind in {ComponentKind.SEPARATOR, ComponentKind.SPACER}
                or fields & n.properties.keys()
                for n in self.walk()
            )
            or any(f.get("states") for f in self.editable_flows)
            or new_logic(self.editable_flows)
        )

    @classmethod
    def empty(cls, name: str = "Novo aplicativo") -> Project:
        """Cria uma janela vazia para começar um projeto."""
        root = create_component(ComponentKind.WINDOW)
        root.properties["title"] = name
        return cls(name=name, root=root)

    def find(self, component_id: str) -> Component | None:
        """Localiza um componente por seu identificador estável."""
        return next((node for node in self.walk() if node.id == component_id), None)

    def parent_of(self, component_id: str) -> Component | None:
        """Localiza o contêiner pai; a raiz não tem pai."""
        return next(
            (node for node in self.walk() if any(c.id == component_id for c in node.children)),
            None,
        )

    def add(self, parent_id: str, kind: ComponentKind) -> Component:
        """Insere um novo componente; não permite inserir janelas internas."""
        parent = self.find(parent_id)
        if parent is None or not parent.can_have_children:
            raise ProjectError("Selecione uma janela ou um contêiner para inserir o componente.")
        if not parent.accepts(ComponentKind(kind)):
            raise ProjectError(
                "Adicione páginas a um conjunto de páginas e controles a uma página ou contêiner."
            )
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
        for states in self.states.values():
            for state in states:
                overrides = state.get("overrides", {})
                for identifier in list(overrides):
                    if identifier in subtree:
                        del overrides[identifier]
                    elif overrides[identifier].get("initial_page") in subtree:
                        overrides[identifier].pop("initial_page", None)
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
        while self.parent_of(ancestor.id) is not None:
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
        original_window = self.window_of(node.id)
        target_window = self.window_of(parent.id)
        if original_window.id != target_window.id:
            subtree = {child.id for child in node.walk()}
            if any(
                subtree & set(state.get("overrides", {}))
                for state in self.states.get(original_window.id, [])
            ) or any(flow["event"]["component"] in subtree for flow in self.editable_flows):
                raise ProjectError(
                    "Revise estados e eventos antes de mover este componente para outra janela."
                )
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
            if item.properties.get("code_name"):
                item.properties["code_name"] += "_" + item.id.rsplit("_", 1)[-1][:4]
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
        owner = self.window_of(component_id)
        for state in self.states.get(owner.id, []):
            overrides = state.setdefault("overrides", {})
            for old, new in identifiers.items():
                if old in overrides:
                    copied = deepcopy(overrides[old])
                    if copied.get("initial_page") in identifiers:
                        copied["initial_page"] = identifiers[copied["initial_page"]]
                    overrides[new] = copied
        parent.children.insert(parent.children.index(node) + 1, clone)
        return clone

    def set_geometry(self, component_id: str, geometry: dict[str, int]) -> bool:
        """Confirma posição/tamanho de um gesto livre, em uma única alteração."""
        node = self.find(component_id)
        parent = self.parent_of(component_id)
        if (
            node is None
            or parent is None
            or parent.layout != LayoutKind.FREE
            or parent.kind == ComponentKind.PAGES
        ):
            raise ProjectError(
                "Posição e tamanho manuais exigem um contêiner de organização livre."
            )
        candidate = node.to_dict()
        candidate["geometry"].update(geometry)
        validated = Component.from_dict(candidate)
        if node.geometry == validated.geometry:
            return False
        node.geometry = validated.geometry
        return True

    def asset_paths(self) -> set[str]:
        """Retorna imagens referenciadas para preservar os recursos no Salvar como."""
        paths = {
            node.properties["source"]
            for node in self.walk()
            if node.kind == ComponentKind.IMAGE and node.properties.get("source")
        }
        for states in self.states.values():
            for state in states:
                for override in state.get("overrides", {}).values():
                    if override.get("source"):
                        paths.add(override["source"])
        for node in self.walk():
            if node.properties.get("icon"):
                paths.add(node.properties["icon"])
        icon = self.application.get("icon")
        if icon:
            paths.add(icon)
        return paths

    def to_dict(self) -> dict[str, Any]:
        """Serializa um retrato independente do documento, mantendo extensões."""
        result = {
            "format": FORMAT_NAME,
            "format_version": max(
                8 if self.python_files else 4,
                7 if any(has_graph(f) for f in self.workflows) else 4,
                6 if any(n.kind == ComponentKind.TERMINAL for n in self.walk()) else 4,
                self.format_version,
                5 if self.uses_v5() else 4,
            ),
            "id": self.id,
            "name": self.name,
            "ui": self.root.to_dict(),
            "workflows": deepcopy(self.workflows),
            "metadata": deepcopy(self.metadata),
        }
        if result["format_version"] >= 5:
            result.update(
                windows=[r.to_dict() for r in self.windows],
                states=deepcopy(self.states),
                entry_window=self.entry_window or self.root.id,
                variables=deepcopy(self.variables),
                map_layout=deepcopy(self.map_layout),
                application=deepcopy(self.application),
            )
        if self.python_files:
            result["python_files"] = list(self.python_files)
        return result

    @classmethod
    def from_dict(cls, value: Any) -> Project:
        """Valida o formato, a versão e a unicidade de identificadores."""
        if not isinstance(value, dict) or value.get("format") != FORMAT_NAME:
            raise ProjectError("Este arquivo não é um projeto Makebench.")
        version = value.get("format_version")
        if type(version) is not int or version not in (1, 2, 3, 4, 5, 6, 7, FORMAT_VERSION):
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
        raw_windows = value.get("windows", []) if version >= 5 else []
        if not isinstance(raw_windows, list) or len(raw_windows) > 128:
            raise ProjectError("Lista de janelas inválida (máximo 128).")
        windows = [Component.from_dict(item) for item in raw_windows]
        if any(item.kind != ComponentKind.WINDOW for item in windows):
            raise ProjectError("Cada interface adicional precisa ser uma janela.")
        ids = [node.id for item in [root, *windows] for node in item.walk()]
        if len(set(ids)) != len(ids):
            raise ProjectError("O projeto contém identificadores de componentes repetidos.")
        workflows = value.get("workflows", [])
        metadata = value.get("metadata", {})
        if not isinstance(workflows, list) or any(not isinstance(w, dict) for w in workflows):
            raise ProjectError("A lista de fluxos de lógica é inválida.")
        if not isinstance(metadata, dict):
            raise ProjectError("Os metadados do projeto precisam ser um objeto.")
        points = metadata.get("debug_breakpoints", [])
        if (
            not isinstance(points, list)
            or len(points) > 10000
            or any(
                not isinstance(point, dict)
                or (
                    point.get("file") == "source"
                    and (type(point.get("line")) is not int or not 1 <= point["line"] <= 1000000)
                )
                or (
                    point.get("file") == "block"
                    and (
                        not isinstance(point.get("block"), str)
                        or not isinstance(point.get("flow"), str)
                    )
                )
                or point.get("file") not in {"block", "source"}
                for point in points
            )
        ):
            raise ProjectError("Lista de pontos de parada inválida.")
        from .source import validate_manifest, validate_module_name

        files = validate_manifest(value.get("python_files", []))
        if files and version < 8:
            raise ProjectError("Módulos Python requerem formato 8 ou posterior.")
        for point in points:
            if point.get("path", "@actions") != "@actions":
                validate_module_name(point["path"])
        project = cls(
            name=value["name"],
            id=value["id"],
            root=root,
            python_files=list(files),
            workflows=deepcopy(workflows),
            metadata=deepcopy(metadata),
            windows=windows,
            states=deepcopy(value.get("states", {})) if version >= 5 else {},
            entry_window=value.get("entry_window") if version >= 5 else None,
            variables=deepcopy(value.get("variables", [])) if version >= 5 else [],
            map_layout=deepcopy(value.get("map_layout", {})) if version >= 5 else {},
            format_version=version if version >= 5 else 4,
            application=deepcopy(value.get("application", {})) if version >= 5 else {},
        )
        if version < 6 and any(n.kind == ComponentKind.TERMINAL for n in project.walk()):
            raise ProjectError("O componente Terminal requer formato 6 ou posterior.")
        if version < 7 and any(has_graph(f) for f in project.workflows):
            raise ProjectError("Grafos livres requerem formato 7 ou posterior.")
        from .navigation import validate_navigation

        validate_navigation(project)
        from .logic import validate

        validate(project)
        return project
