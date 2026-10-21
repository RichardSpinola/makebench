"""Janela principal: interface visual, blocos e funções Python."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QToolBar,
    QTreeWidgetItem, QVBoxLayout, QWidget, QTabWidget,
)

from copy import deepcopy
from makebench.core.logic import create_flow, editable, validate
from makebench.core.source import SourceBuffer
from makebench.editor.code import CodeEditor
from makebench.editor.logic import LogicPanel
from makebench.core.history import History
from makebench.core.project import (
    Component, ComponentKind, LayoutKind, Project, ProjectError,
)
from makebench.core.storage import load_project, save_project
from makebench.editor.assets import AssetStore
from makebench.editor.canvas import PreviewCanvas
from makebench.editor.drag import ComponentPalette, ComponentTree
from makebench.editor.inspector import Inspector
from makebench import __version__


class MainWindow(QMainWindow):
    """Coordena documento, histórico, seleção e comandos de arquivo.

    O documento é a fonte de verdade; árvore, prévia e propriedades são vistas.
    Interface e blocos geram dados/Python; executar exige uma ação explícita.
    """

    def __init__(self, project: Project | None = None, path: Path | None = None) -> None:
        """Abre um projeto fornecido ou inicia uma nova interface vazia."""
        super().__init__()
        self.project = project or Project.empty()
        self.path = path.resolve() if path else None
        self.source = SourceBuffer.load(self.path)
        self.history = History(self.project)
        self.assets = AssetStore(path.parent if path else None)
        self.selected_id = self.project.root.id
        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._refreshing = False
        self.runtime_window = None
        self._closing_after_runtime = False
        self.resize(1280, 800)
        self.setMinimumSize(980, 600)
        self.setWindowModified(False)
        self._create_actions()
        self._create_workspace()
        self._refresh()

    def _create_actions(self) -> None:
        """Registra menus e atalhos que têm comportamento implementado."""
        file_menu = self.menuBar().addMenu("&Arquivo")
        edit_menu = self.menuBar().addMenu("&Editar")
        run_menu = self.menuBar().addMenu("E&xecutar")
        self.run_action = QAction("Testar aplicativo", self)
        self.run_action.setShortcut(QKeySequence("F5"))
        self.run_action.triggered.connect(self.run_project)
        run_menu.addAction(self.run_action)
        help_menu = self.menuBar().addMenu("Aj&uda")
        self.new_action = QAction("Novo projeto", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_project)
        self.open_action = QAction("Abrir…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_project)
        self.save_action = QAction("Salvar", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save)
        save_as_action = QAction("Salvar como…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        quit_action = QAction("Sair", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addActions([self.new_action, self.open_action, self.save_action, save_as_action])
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        self.undo_action = QAction("Desfazer", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction("Refazer", self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        self.redo_action.triggered.connect(self.redo)
        self.remove_action = QAction("Remover componente", self)
        self.remove_action.triggered.connect(self.remove_component)
        edit_menu.addActions([self.undo_action, self.redo_action, self.remove_action])
        self.duplicate_action = QAction("Duplicar", self)
        self.duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        self.duplicate_action.triggered.connect(self.duplicate_component)
        self.up_action = QAction("Mover para antes", self)
        self.up_action.setShortcut(QKeySequence("Alt+Up"))
        self.up_action.triggered.connect(lambda: self.reorder_component(-1))
        self.down_action = QAction("Mover para depois", self)
        self.down_action.setShortcut(QKeySequence("Alt+Down"))
        self.down_action.triggered.connect(lambda: self.reorder_component(1))
        self.page_action = QAction("Adicionar página", self)
        self.page_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.page_action.triggered.connect(self.add_page)
        edit_menu.addActions([self.duplicate_action, self.up_action, self.down_action, self.page_action])
        align_menu = edit_menu.addMenu("Alinhar na área livre")
        self.align_actions = []
        for mode, label in (
            ("left", "À esquerda"), ("center_x", "Centralizar horizontalmente"),
            ("right", "À direita"), ("top", "No topo"),
            ("center_y", "Centralizar verticalmente"), ("bottom", "Na base"),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _, mode=mode: self.align_component(mode))
            align_menu.addAction(action)
            self.align_actions.append(action)
        about_action = QAction("Sobre o Makebench", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        toolbar = QToolBar("Projeto", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        toolbar.addActions([self.duplicate_action, self.page_action])
        toolbar.addSeparator()
        toolbar.addAction(self.run_action)
        toolbar.addSeparator()
        self.snap_check = QCheckBox("Encaixar na grade")
        self.snap_check.setChecked(True)
        self.snap_check.setToolTip("Ajustar arraste e redimensionamento a intervalos de 8 pixels.")
        self.snap_check.toggled.connect(lambda enabled: setattr(self.canvas, "snap", 8 if enabled else 1))
        toolbar.addWidget(self.snap_check)
        self.addToolBar(toolbar)

    def _create_workspace(self) -> None:
        """Monta os três painéis: componentes, prévia e propriedades."""
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        brand = QLabel("Makebench")
        font = brand.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        brand.setFont(font)
        left_layout.addWidget(brand)
        subtitle = QLabel("Dê forma ao seu aplicativo.")
        subtitle.setWordWrap(True)
        left_layout.addWidget(subtitle)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel("Adicionar componente"))
        self.palette = ComponentPalette()
        self.palette.add_requested.connect(self.add_component)
        left_layout.addWidget(self.palette)
        add_button = QPushButton("Adicionar à interface")
        add_button.clicked.connect(self.add_component)
        left_layout.addWidget(add_button)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel("Componentes"))
        self.tree = ComponentTree(lambda: self.project, self._can_drop)
        self.tree.drop_requested.connect(self._on_drop)
        self.tree.remove_requested.connect(self.remove_component)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        left_layout.addWidget(self.tree, 1)
        remove_button = QPushButton("Remover selecionado")
        remove_button.clicked.connect(self.remove_component)
        self.remove_action.changed.connect(
            lambda: remove_button.setEnabled(self.remove_action.isEnabled())
        )
        left_layout.addWidget(remove_button)
        splitter.addWidget(left)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        heading = QLabel("Interface")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        middle_layout.addWidget(heading)
        hint = QLabel("Arraste componentes para a tela. Em áreas livres, mova e redimensione pela seleção.")
        hint.setWordWrap(True)
        middle_layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.canvas = PreviewCanvas()
        self.canvas.can_drop = self._can_drop
        self.canvas.component_selected.connect(self._select)
        self.canvas.geometry_committed.connect(self._commit_geometry)
        self.canvas.drop_requested.connect(self._on_drop)
        self.canvas.nudge_requested.connect(self.nudge_component)
        self.canvas.remove_requested.connect(self.remove_component)
        scroll.setWidget(self.canvas)
        middle_layout.addWidget(scroll, 1)
        preview_note = QLabel("Prévia de edição · Ctrl+arraste transfere componentes livres para outro contêiner.")
        preview_note.setWordWrap(True)
        middle_layout.addWidget(preview_note)
        splitter.addWidget(middle)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        properties_heading = QLabel("Propriedades")
        properties_heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(properties_heading)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        self.inspector = Inspector()
        self.inspector.property_changed.connect(self._change_property)
        self.inspector.image_requested.connect(self.choose_image)
        self.inspector.image_cleared.connect(self.clear_image)
        self.inspector.logic_requested.connect(self.edit_logic)
        inspector_scroll.setWidget(self.inspector)
        right_layout.addWidget(inspector_scroll)
        splitter.addWidget(right)
        splitter.setSizes([250, 700, 300])
        splitter.setStretchFactor(1, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Interface")
        self.logic = LogicPanel(lambda: self.project, lambda: self.source.text)
        self.logic.add_requested.connect(self.edit_logic)
        self.logic.remove_requested.connect(self.remove_flow)
        self.logic.rename_requested.connect(self.rename_flow)
        self.logic.flow_changed.connect(self._receive_flow)
        self.logic.error.connect(self._show_error)
        self.logic.save_requested.connect(self.save)
        self.logic.undo_requested.connect(self.undo)
        self.logic.redo_requested.connect(self.redo)
        self.logic.pending_changed.connect(self._update_actions)
        self.tabs.addTab(self.logic, "Lógica")
        code_page = QWidget()
        code_layout = QVBoxLayout(code_page)
        hint = QLabel("Edite suas funções à direita. O Python à esquerda acompanha os blocos e não substitui suas funções. Use F5 para testar o aplicativo em uma janela separada.")
        hint.setWordWrap(True)
        code_layout.addWidget(hint)
        code_splitter = QSplitter()
        generated_box = QWidget()
        generated_layout = QVBoxLayout(generated_box)
        generated_layout.addWidget(QLabel("Python gerado · somente leitura"))
        self.generated_editor = CodeEditor(True)
        generated_layout.addWidget(self.generated_editor)
        code_splitter.addWidget(generated_box)
        own_box = QWidget()
        own_layout = QVBoxLayout(own_box)
        self.source_label = QLabel("Funções próprias · salvas em arquivo .actions.py")
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        own_layout.addWidget(self.source_label)
        self.source_editor = CodeEditor()
        self.source_editor.setPlainText(self.source.text)
        own_layout.addWidget(self.source_editor)
        code_splitter.addWidget(own_box)
        code_layout.addWidget(code_splitter, 1)
        self.code_diagnostics = QLabel()
        self.code_diagnostics.setWordWrap(True)
        self.code_diagnostics.setTextFormat(Qt.TextFormat.PlainText)
        code_layout.addWidget(self.code_diagnostics)
        self.tabs.addTab(code_page, "Código")
        self.source_timer = QTimer(self)
        self.source_timer.setSingleShot(True)
        self.source_timer.setInterval(250)
        self.source_timer.timeout.connect(self._update_code)
        self.source_editor.textChanged.connect(self._source_changed)
        self.source_editor.undoAvailable.connect(lambda _: self._update_actions())
        self.source_editor.redoAvailable.connect(lambda _: self._update_actions())
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

    def _refresh(self) -> None:
        """Atualiza as vistas a partir do documento e preserva a seleção válida."""
        self._refreshing = True
        self._tree_items = {}
        self.tree.clear()
        self.tree._hint = None

        def append(node: Component, parent: QTreeWidgetItem | None = None) -> None:
            """Projeta um nó e seus filhos na árvore de navegação."""
            item = QTreeWidgetItem([node.display_name])
            item.setData(0, Qt.ItemDataRole.UserRole, node.id)
            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            self._tree_items[node.id] = item
            for child in node.children:
                append(child, item)

        append(self.project.root)
        self.tree.expandAll()
        self.canvas.read_asset = self.assets.read
        self.canvas.set_project(self.project)
        if self.project.find(self.selected_id) is None:
            self.selected_id = self.project.root.id
        self._refreshing = False
        self._select(self.selected_id)
        self.logic.sync()
        self._update_code()
        self._update_actions()

    def _select(self, component_id: str) -> None:
        """Sincroniza seleção da árvore, prévia e formulário de propriedades."""
        if self._refreshing:
            return
        node = self.project.find(component_id)
        if node is None:
            return
        self.selected_id = component_id
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(self._tree_items[component_id])
        self.tree.blockSignals(False)
        self.canvas.select(component_id)
        self.inspector.set_component(self.project, node)
        self._update_actions()

    def _tree_selection_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        """Recebe seleção por mouse ou teclado na árvore."""
        if current and not self._refreshing:
            self._select(current.data(0, Qt.ItemDataRole.UserRole))

    def _update_actions(self) -> None:
        """Atualiza comandos, título e indicador de alterações não salvas."""
        source_active = self.tabs.currentIndex() == 2
        interface_active = self.tabs.currentIndex() == 0
        self.snap_check.setEnabled(interface_active)
        self.undo_action.setEnabled(self.source_editor.document().isUndoAvailable() if source_active else self.history.can_undo or self.logic.pending)
        self.redo_action.setEnabled(self.source_editor.document().isRedoAvailable() if source_active else self.history.can_redo)
        self.remove_action.setEnabled(interface_active and self.selected_id != self.project.root.id)
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(self.selected_id)
        self.duplicate_action.setEnabled(interface_active and parent is not None and editable(self.project))
        self.up_action.setEnabled(interface_active and parent is not None and parent.children[0] is not node)
        self.down_action.setEnabled(interface_active and parent is not None and parent.children[-1] is not node)
        self.page_action.setEnabled(interface_active and self._page_group(node) is not None)
        free = parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE
        for action in self.align_actions:
            action.setEnabled(interface_active and bool(free))
        self.setWindowTitle(f"{self.project.name}[*] — Makebench")
        self.setWindowModified(self.history.dirty or self.source.dirty or self.logic.pending)
        count = len(list(self.project.root.walk())) - 1
        state = "Alterações não salvas" if self.history.dirty or self.source.dirty or self.logic.pending else "Pronto"
        self.statusBar().showMessage(f"{state} · {count} componente(s)")

    def _change_property(self, component_id: str, key: str, value: object) -> None:
        """Aplica uma propriedade válida e registra uma única alteração no histórico."""
        if self._refreshing:
            return
        if component_id == "@project":
            cleaned = str(value).strip()
            if not cleaned:
                self._refresh()
                self.statusBar().showMessage("O nome do projeto não pode ficar vazio.", 5000)
                return
            if self.project.name == cleaned:
                return
            self.project.name = cleaned
        else:
            node = self.project.find(component_id)
            if node is None:
                return
            if key == "layout":
                if node.layout == LayoutKind(value):
                    return
                node.layout = LayoutKind(value)
            elif key.startswith("geometry."):
                name = key.partition(".")[2]
                if node.geometry[name] == value:
                    return
                node.geometry[name] = int(value)
            else:
                if node.properties.get(key) == value:
                    return
                node.properties[key] = value
        self.history.push(self.project)
        self._refresh()

    def _finish_field_edit(self) -> bool:
        """Confirma texto ainda em edição antes de salvar ou substituir o projeto."""
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
        return self.logic.flush()

    def add_component(self) -> None:
        """Insere no contêiner ou página adequada à seleção atual."""
        kind = ComponentKind(self.palette.currentData())
        def insert():
            """Insere o tipo escolhido no destino resolvido pela seleção."""
            parent = self._insertion_parent(kind)
            self.selected_id = self.project.add(parent.id, kind).id
        self._edit(insert)

    def _insertion_parent(self, kind: ComponentKind) -> Component:
        """Resolve inserções por botão, inclusive dentro de páginas selecionadas."""
        node = self.project.find(self.selected_id)
        if node.kind == ComponentKind.PAGES and kind != ComponentKind.PAGE:
            return self.canvas.visible_page(node)
        while node:
            if node.accepts(kind):
                return node
            node = self.project.parent_of(node.id)
        raise ProjectError("Selecione um conjunto de páginas para adicionar uma página.")

    def _page_group(self, node: Component) -> Component | None:
        """Encontra o conjunto de páginas mais próximo da seleção."""
        while node:
            if node.kind == ComponentKind.PAGES:
                return node
            node = self.project.parent_of(node.id)
        return None

    def _edit(self, change: Callable[[], None]) -> None:
        """Agrupa um comando em uma alteração e restaura o documento se falhar."""
        if not self._finish_field_edit():
            return
        before = self.project.to_dict()
        selection = self.selected_id
        try:
            change()
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project = Project.from_dict(before)
            self.selected_id = selection
            self._refresh()
            self._show_error(str(exc))
            return
        self.history.push(self.project)
        self._refresh()

    def _can_drop(self, payload: dict, parent_id: str) -> bool:
        """Valida arraste sem alterar o documento durante a passagem do mouse."""
        parent = self.project.find(parent_id)
        if parent is None:
            return False
        if payload.get("mode") == "new":
            try:
                return parent.accepts(ComponentKind(payload["kind"]))
            except (KeyError, ValueError):
                return False
        node = self.project.find(payload.get("id"))
        if payload.get("project") != self.project.id or node is None:
            return False
        previous = self.project.parent_of(node.id)
        return bool(
            previous and parent.accepts(node.kind)
            and parent.id not in {child.id for child in node.walk()}
            and not (previous is not parent and previous.kind == ComponentKind.PAGES and len(previous.children) == 1)
        )

    def _on_drop(self, payload: dict, parent_id: str, index: int, geometry: dict | None) -> None:
        """Transforma um drop de árvore ou tela em uma edição do modelo."""
        if not self._can_drop(payload, parent_id):
            return
        def apply():
            """Aplica criação/transferência e geometria do drop de uma vez."""
            if payload["mode"] == "new":
                node = self.project.add(parent_id, ComponentKind(payload["kind"]))
            else:
                node = self.project.find(payload["id"])
            self.project.move(node.id, parent_id, index)
            parent = self.project.find(parent_id)
            if geometry and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
                snapped = {key: max(0, min(20000, round(value / self.canvas.snap) * self.canvas.snap)) for key, value in geometry.items()}
                self.project.set_geometry(node.id, snapped)
            self.selected_id = node.id
        self._edit(apply)

    def _commit_geometry(self, node_id: str, geometry: dict) -> None:
        """Registra um movimento/redimensionamento completo sem fragmentar o histórico."""
        self._edit(lambda: self.project.set_geometry(node_id, geometry))

    def duplicate_component(self) -> None:
        """Duplica a seleção com identificadores próprios e mantém a cópia selecionada."""
        def duplicate():
            """Seleciona a cópia recém-criada, preservando o original."""
            self.selected_id = self.project.duplicate(self.selected_id).id
        self._edit(duplicate)

    def reorder_component(self, direction: int) -> None:
        """Oferece reorganização por teclado, com a mesma semântica do arraste."""
        def reorder():
            """Converte a direção do comando em uma posição de inserção."""
            node = self.project.find(self.selected_id)
            parent = self.project.parent_of(node.id)
            if parent:
                old_index = parent.children.index(node)
                self.project.move(node.id, parent.id, old_index + (2 if direction > 0 else -1))
        self._edit(reorder)

    def add_page(self) -> None:
        """Acrescenta uma página ao conjunto selecionado ou ancestral."""
        def add():
            """Insere uma página no conjunto ancestral da seleção."""
            group = self._page_group(self.project.find(self.selected_id))
            if group is not None:
                self.selected_id = self.project.add(group.id, ComponentKind.PAGE).id
        self._edit(add)

    def nudge_component(self, dx: int, dy: int) -> None:
        """Ajusta um componente livre em passos finos sem afetar outros layouts."""
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(node.id)
        if parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
            self._commit_geometry(node.id, {
                "x": max(0, min(20000, node.geometry["x"] + dx)),
                "y": max(0, min(20000, node.geometry["y"] + dy)),
            })

    def align_component(self, mode: str) -> None:
        """Alinha a seleção aos limites visíveis de seu contêiner livre."""
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(node.id)
        if not parent or parent.layout != LayoutKind.FREE or parent.kind == ComponentKind.PAGES:
            return
        area = self.canvas._frames[parent.id].contentsRect()
        x, y = node.geometry["x"], node.geometry["y"]
        if mode in {"left", "center_x", "right"}:
            remaining = area.width() - node.geometry["width"]
            x = 8 if mode == "left" else remaining // 2 if mode == "center_x" else remaining - 8
        else:
            remaining = area.height() - node.geometry["height"]
            y = 8 if mode == "top" else remaining // 2 if mode == "center_y" else remaining - 8
        self._commit_geometry(node.id, {"x": max(0, min(20000, x)), "y": max(0, min(20000, y))})

    def choose_image(self, node_id: str) -> None:
        """Importa uma imagem escolhida explicitamente, copiando-a ao salvar."""
        filename, _ = QFileDialog.getOpenFileName(self, "Escolher imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
        if not filename:
            return
        def choose():
            """Reserva o recurso importado e atualiza a referência visual."""
            source = self.assets.import_image(Path(filename))
            node = self.project.find(node_id)
            node.properties.update(source=source, image_name=Path(filename).name)
        self._edit(choose)

    def clear_image(self, node_id: str) -> None:
        """Remove a referência visual, mantendo o recurso disponível para desfazer."""
        def clear():
            """Limpa a imagem sem remover o recurso do histórico da sessão."""
            node = self.project.find(node_id)
            node.properties.update(source="", image_name="")
        self._edit(clear)

    def remove_component(self) -> None:
        """Remove a seleção, mantendo a exclusão disponível para desfazer."""
        if not self._finish_field_edit():
            return
        if self.selected_id == self.project.root.id:
            return
        try:
            self.selected_id = self.project.remove(self.selected_id)
        except ProjectError as exc:
            self._show_error(str(exc))
            return
        self.history.push(self.project)
        self._refresh()

    def undo(self) -> None:
        """Restaura o documento anterior, incluindo propriedades e ordem dos nós."""
        if self.tabs.currentIndex() == 2:
            self.source_editor.undo()
            return
        if not self._finish_field_edit():
            return
        self.project = self.history.undo()
        self._refresh()

    def redo(self) -> None:
        """Reaplica uma alteração previamente desfeita."""
        if self.tabs.currentIndex() == 2:
            self.source_editor.redo()
            return
        if not self._finish_field_edit():
            return
        self.project = self.history.redo()
        self._refresh()

    def new_project(self) -> None:
        """Cria um documento após resolver alterações não salvas."""
        if not self._confirm_discard():
            return
        self._replace_project(Project.empty(), None)

    def open_project(self) -> None:
        """Abre um documento validado; falhas não substituem o projeto atual."""
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Abrir projeto Makebench", str(self.path.parent) if self.path else "",
            "Projetos Makebench (*.makebench.json);;JSON (*.json)",
        )
        if not filename:
            return
        try:
            project = load_project(filename)
        except ProjectError as exc:
            self._show_error(str(exc))
            return
        try:
            self._replace_project(project, Path(filename))
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))

    def _replace_project(self, project: Project, path: Path | None) -> None:
        """Troca o documento e inicia um histórico independente."""
        path = path.resolve() if path else None
        source = SourceBuffer.load(path)
        self.project = project
        self.path = path
        self.source = source
        self.source_editor.blockSignals(True)
        self.source_editor.setPlainText(source.text)
        self.source_editor.blockSignals(False)
        self.logic.flow_id = None
        self.assets = AssetStore(path.parent if path else None)
        self.history = History(project)
        self.selected_id = project.root.id
        self._refresh()

    def save(self) -> bool:
        """Salva o projeto ou solicita um destino quando ainda não tem caminho."""
        if not self._finish_field_edit():
            return False
        if self.path is None:
            return self.save_as()
        return self.save_to(self.path)

    def save_as(self) -> bool:
        """Solicita um destino, sem mudar o caminho atual em caso de falha."""
        if not self._finish_field_edit():
            return False
        filename, _ = QFileDialog.getSaveFileName(
            self, "Salvar projeto Makebench",
            str(self.path) if self.path else "projeto.makebench.json",
            "Projetos Makebench (*.makebench.json)",
        )
        if not filename:
            return False
        if not filename.endswith(".makebench.json"):
            filename += ".makebench.json"
        return self.save_to(Path(filename))

    def save_to(self, path: Path) -> bool:
        """Persiste o documento e marca como salvo somente depois do sucesso."""
        if not self._finish_field_edit():
            return False
        path = path.resolve()
        try:
            Project.from_dict(self.project.to_dict())
            self.assets.write_referenced(path.parent, self.project.asset_paths())
            self.source.write(path)
            save_project(self.project, path)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return False
        self.path = path
        self.assets.root = path.parent.resolve()
        self.history.mark_saved()
        self.source.mark_saved()
        self._update_code()
        self._update_actions()
        return True

    def _confirm_discard(self) -> bool:
        """Oferece salvar alterações antes de fechar, abrir ou criar um projeto."""
        if not self._finish_field_edit():
            choice = QMessageBox.warning(
                self, "Blocos não confirmados", "O editor de blocos não respondeu. Descartar pode perder as alterações mais recentes. Deseja descartar e continuar?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            return choice == QMessageBox.StandardButton.Discard
        if not self.history.dirty and not self.source.dirty:
            return True
        choice = QMessageBox.warning(
            self, "Salvar alterações?", "O projeto tem alterações que ainda não foram salvas.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def _tab_changed(self, index):
        """Confirma blocos ao sair e inicia WebEngine apenas quando necessário."""
        if index != 1 and not self.logic.flush():
            self.tabs.setCurrentIndex(1)
            return
        if index == 1:
            self.logic.ensure_loaded()
            self.logic.sync()
        self._update_actions()

    def _source_changed(self):
        """Mantém fonte própria independente da geração e do histórico visual."""
        self.source.text = self.source_editor.toPlainText()
        self.source_timer.start()
        self._update_actions()

    def _update_code(self):
        """Mostra código e diagnósticos sem importar o arquivo de funções."""
        self.logic.update_code()
        generated = self.logic.generated
        if self.generated_editor.toPlainText() != generated.text:
            self.generated_editor.setPlainText(generated.text)
        self.code_diagnostics.setText('\n'.join(generated.diagnostics) or 'Funções recebem ctx e valor. Use o nome no bloco “chamar função”.')
        label = self.source.path.name if self.source.path else 'arquivo .actions.py criado ao salvar'
        self.source_label.setText(f'Funções próprias · {label}')

    def edit_logic(self, component_id):
        """Cria ou abre o fluxo do evento selecionado na interface."""
        if not self._finish_field_edit():
            return
        try:
            flow = create_flow(self.project, component_id)
        except ProjectError as exc:
            self._show_error(str(exc))
            return
        self.history.push(self.project)
        self.logic.sync(flow['id'])
        self.tabs.setCurrentIndex(1)
        self._update_code()
        self._update_actions()

    def remove_flow(self, flow_id):
        """Remove só o vínculo de lógica; desfazer recupera blocos e comentários."""
        self._edit(lambda: setattr(self.project, 'workflows', [f for f in self.project.workflows if f['id'] != flow_id]))

    def rename_flow(self, flow_id, name):
        """Altera o rótulo do fluxo sem reidentificar seus blocos."""
        flow = next((f for f in self.project.workflows if f['id'] == flow_id), None)
        if flow and name.strip() and flow['name'] != name.strip():
            flow['name'] = name.strip()
            self.history.push(self.project)
            self.logic.sync()
            self._update_code()
            self._update_actions()

    def _receive_flow(self, data):
        """Valida o modelo neutro recebido; blocos incompletos ficam como rascunho."""
        flow = next((f for f in self.project.workflows if f['id'] == data.get('flow')), None)
        if flow is None or not isinstance(data.get('workspace'), dict):
            return
        if data.get('body') == flow.get('body') and data['workspace'] == flow.get('workspace', {}) and data.get('errors', []) == flow.get('errors', []):
            return
        previous = deepcopy(flow)
        flow.update(body=data.get('body'), workspace=data['workspace'], errors=data.get('errors', []))
        try:
            validate(self.project)
        except ProjectError as exc:
            flow.update(body=None, errors=[str(exc)])
            try:
                validate(self.project)
            except ProjectError:
                flow.clear(); flow.update(previous)
                return
        self.history.push(self.project)
        self._update_code()
        self._update_actions()

    def run_project(self):
        """Testa snapshot explícito; edição e abertura continuam sem executar código."""
        if self.runtime_window is not None and not self.runtime_window.session.closed:
            self.runtime_window.show();self.runtime_window.raise_();self.runtime_window.activateWindow()
            return
        if not self._finish_field_edit():
            return
        from makebench.runtime.window import RuntimeWindow
        try:
            window = RuntimeWindow(self.project, self.source.text, self.assets.read,
                self.path.parent if self.path else None, self.source.path, self)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc));return
        if self.runtime_window is not None:
            self.runtime_window.close()
        self.runtime_window = window
        window.locate_requested.connect(lambda error: self._locate_runtime_error(error, window))
        window.shutdown_finished.connect(self._runtime_stopped)
        window.destroyed.connect(lambda: self._runtime_destroyed(window))
        window.show();window.start()

    def _runtime_destroyed(self, window):
        """Remove apenas a referência da janela que foi efetivamente destruída."""
        if self.runtime_window is window:
            self.runtime_window = None

    def _runtime_stopped(self):
        """Retoma fechamento após o supervisor terminar a limpeza dos processos."""
        if self._closing_after_runtime:
            QTimer.singleShot(0, self.close)

    def _locate_runtime_error(self, error, window):
        """Localiza o bloco atual; linhas próprias só valem se o texto não mudou."""
        if self.project.id != window.project.id:
            self.statusBar().showMessage("O erro pertence a outro projeto aberto na execução.", 7000);return
        if error.get('source_line') and self.source.text == window.source:
            self.tabs.setCurrentIndex(2)
            self.source_editor.show_line(error['source_line'])
        elif error.get('block'):
            flow = next((f for f in self.project.workflows if f['id'] == error.get('flow')), None)
            if flow:
                self.logic.sync(flow['id']);self.tabs.setCurrentIndex(1)
                self.logic.focus_block(flow['id'], error['block'])
        self.raise_();self.activateWindow()

    def _show_error(self, message: str) -> None:
        """Apresenta falhas recuperáveis sem fechar o editor."""
        QMessageBox.critical(self, "Makebench", message)

    def show_about(self) -> None:
        """Informa a versão e o limite funcional da entrega atual."""
        QMessageBox.about(
            self, "Sobre o Makebench",
            "<h2>Makebench</h2><p>Aplicativos Linux, construídos por você.</p>"
            f"<p>Versão {__version__} — interface, blocos e funções Python.</p>"
            "<p>Teste aplicativos e tarefas com F5. Exportadores serão adicionados na próxima etapa.</p>",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Protege alterações não salvas ao encerrar a janela."""
        window = self.runtime_window
        if window is not None and window.session.admin_active:
            window.show();window.raise_()
            self.statusBar().showMessage("Aguarde a tarefa administrativa terminar antes de fechar o editor.", 7000)
            event.ignore();return
        if not self._closing_after_runtime and not self._confirm_discard():
            event.ignore();return
        if window is not None and not window.session.closed:
            self._closing_after_runtime = True
            self.setEnabled(False)
            window.close()
            event.ignore();return
        event.accept()
