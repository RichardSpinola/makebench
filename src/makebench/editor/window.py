"""Janela principal: interface visual, blocos e funções Python."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, QEvent
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


from .studio import StudioMixin


class MainWindow(StudioMixin, QMainWindow):
    """Coordena documento, histórico, seleção e comandos de arquivo.

    O documento é a fonte de verdade; árvore, prévia e propriedades são vistas.
    Interface e blocos geram dados/Python; executar exige uma ação explícita.
    """

    def __init__(self, project: Project | None = None, path: Path | None = None) -> None:
        """Abre um projeto fornecido ou inicia uma nova interface vazia."""
        super().__init__()
        from .theme import manager
        from .dialogs import install_translation
        manager()
        from .theme import icon
        self.setWindowIcon(icon('window'))
        if not hasattr(QApplication.instance(), '_makebench_dialog_filter'):
            install_translation(QApplication.instance())
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
        self.install_studio()
        self._refresh()
        self.remember_project()

    def showEvent(self,event):
        """Aguarda o estilo polir as barras antes de conferir a paleta nativa."""
        super().showEvent(event);QTimer.singleShot(0,self,self._sync_native_bars)

    def changeEvent(self,event):
        """Tema e ativação podem mudar as cores especiais dos cabeçalhos KDE."""
        super().changeEvent(event)
        if event.type() in {QEvent.Type.ActivationChange,QEvent.Type.PaletteChange,QEvent.Type.StyleChange} and hasattr(self,'workspace_toolbar'):
            QTimer.singleShot(0,self,self._sync_native_bars)

    def _sync_native_bars(self):
        """Corrige apenas texto ilegível em barras já construídas, fora dos eventos de estilo."""
        from .theme import manager
        for bar in (self.menuBar(),self.workspace_toolbar):manager().repair_bar_palette(bar)

    def _create_actions(self) -> None:
        """Registra menus e atalhos que têm comportamento implementado."""
        file_menu = self.menuBar().addMenu("&Arquivo")
        edit_menu = self.menuBar().addMenu("&Editar")
        run_menu = self.menuBar().addMenu("E&xecutar")
        self.run_action = QAction("Testar aplicativo", self)
        self.run_action.setShortcut(QKeySequence("F5"))
        self.run_action.triggered.connect(self.run_project)
        run_menu.addAction(self.run_action)
        self.debug_action=QAction('Depurar aplicativo',self);self.debug_action.setShortcut(QKeySequence('F6'));self.debug_action.triggered.connect(self.debug_project);run_menu.addAction(self.debug_action)
        for title,shortcut,action in [('Continuar','F8','continue'),('Próximo passo','F10','step_over'),('Entrar na função','F11','step_in'),('Sair da função','Shift+F11','step_out')]:
            command=QAction(title,self);command.setShortcut(QKeySequence(shortcut));command.triggered.connect(lambda _,action=action:self.debug_command(action));run_menu.addAction(command)

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
        self.inspector.icon_requested.connect(self.choose_component_icon)
        self.inspector.navigation_requested.connect(self.reveal_navigation)
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
        self.source_timer.timeout.connect(self._source_analysis_ready)
        self.source_editor.textChanged.connect(self._source_changed)
        self.source_editor.undoAvailable.connect(lambda _: self._update_actions())
        self.source_editor.redoAvailable.connect(lambda _: self._update_actions())
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

    def presentation_signature(self):
        """Identifica somente composição/contexto, sem reconstruir widgets por mudanças de lógica."""
        import json
        return json.dumps({'project':self.project.id,'assets':id(self.assets),'roots':[r.to_dict() for r in self.project.roots],
            'states':self.project.states,'window':getattr(self,'active_window',self.project.root.id),'state':getattr(self,'active_state','@default'),
            'backend':self.project.application.get('backend','qt'),'icon':self.project.application.get('icon'),'empty':self.project.metadata.get('empty_map',False)},sort_keys=True)

    def _refresh(self) -> None:
        """Reutiliza a composição se só lógica/metadados mudaram; estrutura repinta atomicamente."""
        from .updates import hold_updates
        signature=self.presentation_signature()
        if signature==getattr(self,'_presentation_signature',None):
            for identifier,item in self._tree_items.items():
                node=self.project.find(identifier);count=sum(f['event']['component']==identifier for f in self.project.editable_flows)
                item.setText(0,('◌ ' if not node.properties.get('visible',True) else '')+(node.properties.get('code_name') or node.display_name)+(f' · {count} evento(s)' if count else ''))
            self.sync_navigation();self._select(self.selected_id);self.logic.sync();self._update_code();self._update_actions();return
        # O proxy gráfico não é filho QWidget da janela principal.
        with hold_updates(self), hold_updates(self.canvas):self._rebuild_views()
        self._presentation_signature=self.presentation_signature()

    def _rebuild_views(self) -> None:
        """Atualiza as vistas a partir do documento e preserva a seleção válida."""
        self._refreshing = True
        expanded={key:item.isExpanded() for key,item in getattr(self,'_tree_items',{}).items()}
        tree_scroll=self.tree.verticalScrollBar().value()
        self._tree_items = {}
        self.tree.clear()
        self.tree._hint = None

        def append(node: Component, parent: QTreeWidgetItem | None = None) -> None:
            """Projeta um nó e seus filhos na árvore de navegação."""
            count=sum(1 for flow in self.project.editable_flows if flow.get('event',{}).get('component')==node.id)
            label=node.properties.get('code_name') or node.display_name
            if not node.properties.get('visible',True):label='◌ '+label
            if count:label+=f' · {count} evento(s)'
            item = QTreeWidgetItem([label])
            from .theme import icon
            item.setIcon(0,icon(node.kind.value));item.setToolTip(0,node.display_name+(' · oculto no aplicativo' if not node.properties.get('visible',True) else '')+(' · contêiner' if node.can_have_children else ''))
            item.setData(0, Qt.ItemDataRole.UserRole, node.id)
            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            self._tree_items[node.id] = item
            if node.kind==ComponentKind.WINDOW and self.project.states.get(node.id):
                group=QTreeWidgetItem(['Estados']);item.addChild(group)
                for state in [{'id':'@default','name':node.properties.get('default_state_name','Padrão')},*self.project.states[node.id]]:
                    state_item=QTreeWidgetItem([state['name']]);state_item.setData(0,Qt.ItemDataRole.UserRole,'@state|'+node.id+'|'+state['id']);group.addChild(state_item)
            for child in node.children:
                append(child, item)

        for root in self.project.roots:append(root)
        self.tree.expandAll()
        for key,item in self._tree_items.items():
            if key in expanded:item.setExpanded(expanded[key])
        self.tree.verticalScrollBar().setValue(tree_scroll)
        self.canvas.read_asset = self.assets.read
        self.sync_navigation()
        from dataclasses import replace
        root=self.project.effective_root(self.active_window,self.active_state)
        canvas_project=replace(self.project,root=root,windows=[])
        self.canvas.set_project(canvas_project)
        if self.project.find(self.selected_id) is None:
            self.selected_id = self.project.root.id
        self._refreshing = False
        # Uma reconstrução também restaura entradas rejeitadas pela validação.
        # O cache só evita refazer campos em cliques de seleção sem alteração.
        self.inspector._binding_signature = None
        if self.selected_id not in getattr(self,'selected_ids',set()):self.selected_ids={self.selected_id}
        self._preserve_multi=True
        self._select(self.selected_id)
        self._preserve_multi=False
        if hasattr(self,'selected_ids'):
            self.selected_ids={identifier for identifier in self.selected_ids if self.project.find(identifier)} or {self.selected_id}
            if len(self.selected_ids)>1:self.select_multiple(self.selected_ids)
        self.logic.sync()
        self._update_code()
        self._update_actions()
        if hasattr(self,"zoom_view"):self.zoom_view.update_bounds()

    def _select(self, component_id: str) -> None:
        """Agrupa a seleção e a troca de campos em uma única repintura."""
        from .updates import hold_updates
        with hold_updates(self.inspector):
            self._select_component(component_id)

    def _select_component(self, component_id: str) -> None:
        """Sincroniza seleção da árvore, prévia e formulário de propriedades."""
        if self._refreshing:
            return
        node = self.project.find(component_id)
        if node is None:
            return
        if not getattr(self,'_preserve_multi',False) and not getattr(self,'_from_tree',False):
            modifiers=QApplication.keyboardModifiers()
            if modifiers & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):
                self.selected_ids=getattr(self,'selected_ids',set())|{component_id}
            elif component_id not in getattr(self,"selected_ids",set()):self.selected_ids={component_id}
        self.selected_id = component_id
        owner=self.project.window_of(component_id)
        if owner and owner.id!=self.active_window:
            self.active_window=owner.id;self.active_state='@default'
            self._refresh();return
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(self._tree_items[component_id])
        self.tree.blockSignals(False)
        self.canvas.select(component_id)
        shown=self.canvas._project.find(component_id) or node
        overrides={}
        if self.active_state!='@default':
            state=next(item for item in self.project.states[self.active_window] if item['id']==self.active_state)
            overrides=state.get('overrides',{}).get(node.id,{})
        self.inspector.set_component(self.project, shown, overrides,self.active_state!='@default')
        if hasattr(self,"selected_ids"):self.canvas.select_many(self.selected_ids)
        if self.active_state!='@default':
            self.statusBar().showMessage('Editando estado: somente propriedades. Projeto > Restaurar seleção do Padrão remove diferenças.')
        if len(getattr(self,"selected_ids",[]))>1:self.select_multiple(self.selected_ids)
        self._update_actions()

    def _tree_selection_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        """Recebe seleção por mouse ou teclado na árvore."""
        if current and not self._refreshing:
            identifier=current.data(0,Qt.ItemDataRole.UserRole)
            if isinstance(identifier,str) and identifier.startswith('@state|'):
                _,window,state=identifier.split('|',2);self.activate_window(window,state)
            elif identifier:
                self._from_tree=True;self._select(identifier);self._from_tree=False

    def _update_actions(self) -> None:
        """Atualiza comandos, título e indicador de alterações não salvas."""
        source_active = self.tabs.currentIndex() == 2 and (not hasattr(self,"code_files") or self.code_files.currentIndex()>0)
        interface_active = self.tabs.currentIndex() == 0
        home=hasattr(self,'home_page') and self.pages.currentWidget() is self.home_page
        active=self.runtime_window is not None and not self.runtime_window.session.closed
        self.debug_action.setEnabled(not home and not self.project.metadata.get('empty_map'))
        self.sync_breakpoints()
        if hasattr(self,'behavior_templates'):self.behavior_templates.setVisible(self.logic.editor_kind.currentData()!='nodes')
        self.run_action.setEnabled(not home and not self.project.metadata.get('empty_map'))
        self.run_action.setText('Reiniciar teste' if active else 'Testar aplicativo')
        self.run_action.setToolTip(self.run_action.text()+' · F5')
        if hasattr(self,'stop_action'):self.stop_action.setEnabled(active and not self.runtime_window.session.admin_active)
        self.save_action.setEnabled(not home)
        self.snap_check.setEnabled(interface_active and not home)
        self.undo_action.setEnabled(self.active_code_editor().document().isUndoAvailable() if source_active else self.history.can_undo or self.logic.pending)
        self.redo_action.setEnabled(self.active_code_editor().document().isRedoAvailable() if source_active else self.history.can_redo)
        self.remove_action.setEnabled(interface_active and (self.selected_id != self.project.root.id or len(self.project.roots)>1))
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
        if hasattr(self,'code_files'):self.code_files.setTabText(1,'Funções próprias'+(' •' if self.source.dirty else ''))
        self.setWindowModified(self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty())
        count = len(list(self.project.root.walk())) - 1
        state = "Alterações não salvas" if self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty() else "Pronto"
        self.statusBar().showMessage(f"{state} · {count} componente(s)")
        self.sync_studio()

    def _change_property(self, component_id: str, key: str, value: object) -> None:
        """Aplica uma propriedade válida e registra uma única alteração no histórico."""
        if self._refreshing:
            return
        before=self.project.to_dict()
        if component_id != '@project' and getattr(self,'active_state','@default')!='@default':
            from makebench.core.navigation import OVERRIDES
            if key not in OVERRIDES:
                self.statusBar().showMessage('Edite a estrutura e o layout no estado Padrão.',6000);self._refresh();return
            state=next(item for item in self.project.states[self.active_window] if item['id']==self.active_state)
            state.setdefault('overrides',{}).setdefault(component_id,{})[key]=value
            try:Project.from_dict(self.project.to_dict())
            except ProjectError as exc:
                self.project=Project.from_dict(before);self._refresh();self.statusBar().showMessage(str(exc),7000);return
            self.history.push(self.project);self._refresh_property(component_id,key);return
        if component_id == "@project":
            cleaned = str(value).strip()
            if not cleaned:
                field=self.inspector.findChild(__import__('PySide6.QtWidgets',fromlist=['QLineEdit']).QLineEdit,'property_name')
                if field:field.setText(self.project.name);field.setModified(False)
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
                try:self.convert_layout(node,value)
                except ProjectError as exc:self._show_error(str(exc));self._refresh();return
            elif key=='alignment_preset':
                if node.properties.get(key)==value:return
                vertical,horizontal=str(value).split('-')
                horizontal={'left':'start','center':'center','right':'end'}[horizontal]
                vertical={'top':'start','center':'center','bottom':'end'}[vertical]
                node.properties.update(alignment_preset=value,align=horizontal if node.layout==LayoutKind.VERTICAL else vertical,distribute=vertical if node.layout==LayoutKind.VERTICAL else horizontal)
            elif key.startswith("geometry."):
                name = key.partition(".")[2]
                if node.geometry[name] == value:
                    return
                node.geometry[name] = int(value)
            else:
                if node.properties.get(key) == value:
                    return
                node.properties[key] = value
        try:Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project=Project.from_dict(before);self._refresh();self.statusBar().showMessage(str(exc),7000);return
        self.history.push(self.project)
        self._refresh_property(component_id,key)

    def _refresh_property(self,identifier,key,finish=True):
        """Atualiza valores sem destruir o campo em edição nem a árvore de widgets."""
        structural={'layout','size_mode','align','distribute','alignment_preset','initial_page'}
        if key in structural or key in {'width','height','resizable'} or key=='icon' and self.project.find(identifier).kind==ComponentKind.WINDOW:
            self.setUpdatesEnabled(False)
            try:self._refresh()
            finally:self.setUpdatesEnabled(True)
            return
        if identifier=='@project':
            self.canvas._project.name=self.project.name;self._presentation_signature=self.presentation_signature();self._update_actions();return
        node=self.project.find(identifier)
        if node is None:return
        effective=next((n for n in self.project.effective_root(self.active_window,self.active_state).walk() if n.id==identifier),None)
        shown=self.canvas._project.find(identifier)
        if effective is None or shown is None:return
        shown.properties=deepcopy(effective.properties);shown.geometry=dict(effective.geometry)
        self.canvas.refresh_native_preview()
        frame=self.canvas._frames.get(identifier)
        widget=frame.layout().itemAt(0).widget() if frame and frame.layout() and frame.layout().count() else None
        if widget and not node.can_have_children:
            if key=='text':
                widget.setPlainText(str(effective.properties.get('text',''))) if hasattr(widget,'setPlainText') else widget.setText(str(effective.properties.get('text','')))
            elif key=='placeholder' and hasattr(widget,'setPlaceholderText'):widget.setPlaceholderText(str(effective.properties.get('placeholder','')))
            elif key=='tooltip':widget.setToolTip(effective.properties.get('tooltip',''))
            elif key=='icon' and hasattr(widget,'setIcon'):
                from PySide6.QtGui import QPixmap,QIcon
                image=QPixmap()
                if effective.properties.get('icon'):image.loadFromData(self.assets.read(effective.properties['icon']))
                widget.setIcon(QIcon(image))
            elif key=='checked' and hasattr(widget,'setChecked'):widget.setChecked(effective.properties['checked'])
            elif key=='value' and hasattr(widget,'setValue'):widget.setValue(effective.properties['value'])
            elif key in {'source','alt_text','image_name'} and hasattr(widget,'image'):
                from PySide6.QtGui import QPixmap
                image=QPixmap()
                if effective.properties.get('source'):image.loadFromData(self.assets.read(effective.properties['source']))
                widget.image=image;widget.setAccessibleName(effective.properties.get('alt_text','Imagem'));widget.update()
        if frame:
            if key=='visible':frame.setVisible(effective.properties.get('visible',True))
            if key=='enabled':
                target=frame if node.can_have_children else widget
                if target:target.setEnabled(effective.properties.get('enabled',True))
            if key=='spacing' and frame.layout():frame.layout().setSpacing(effective.properties.get('spacing',6))
            if key=='padding' and frame.layout():
                value=effective.properties.get('padding',8);frame.layout().setContentsMargins(value,value,value,value)
            if key.startswith('geometry.'):
                parent=self.project.parent_of(identifier)
                if parent and parent.layout==LayoutKind.FREE:frame.setGeometry(*(effective.geometry[k] for k in ('x','y','width','height')))
                else:
                    axis=key.partition('.')[2]
                    if axis in {'width','height'}:getattr(frame,'setFixed'+axis.title())(effective.geometry[axis])
        if key=='title' and node.kind==ComponentKind.WINDOW:
            for label in self.canvas.findChildren(QLabel):
                if label.property('componentId')==identifier and label.parentWidget().objectName()=='app_window_titlebar':label.setText(str(effective.properties.get('title','Interface')))
        item=self._tree_items.get(identifier)
        if item:
            count=sum(f.get('event',{}).get('component')==identifier for f in self.project.editable_flows)
            item.setText(0,('◌ ' if not node.properties.get('visible',True) else '')+(node.properties.get('code_name') or node.display_name)+(f' · {count} evento(s)' if count else ''))
        if self.active_state!='@default':
            state=next(s for s in self.project.states[self.active_window] if s['id']==self.active_state);self.inspector._overrides=state.get('overrides',{}).get(identifier,{})
        if identifier==self.selected_id:
            if key=='icon':self.inspector._binding_signature=None;self._select(identifier)
            elif not key.startswith('geometry.'):self.inspector.patch_value(key,effective.properties.get(key,''))
        self._presentation_signature=self.presentation_signature()
        if not finish:return
        self.logic.sync();self._update_code();self._update_actions()
        if hasattr(self,'zoom_view'):self.zoom_view.update_bounds()

    def choose_component_icon(self,identifier):
        """Importa ícone portátil no documento, sem vincular caminhos externos."""
        filename,_=QFileDialog.getOpenFileName(self,'Ícone do botão','','Ícones (*.png *.svg)')
        if filename:
            try:self._change_property(identifier,'icon',self.assets.import_image(Path(filename)))
            except (OSError,ProjectError) as exc:self._show_error(str(exc))

    def reveal_navigation(self,edge):
        """O inspetor do Designer abre a conexão exata no Mapa."""
        self.set_mode('Mapa')
        line=next((line for line in self.map_panel.edges if line.edge['flow']==edge['flow'] and line.edge['block']==edge['block']),None)
        if line:self.map_panel.view.scene().clearSelection();line.setSelected(True);self.map_panel.view.ensureVisible(line)

    def _finish_field_edit(self) -> bool:
        """Confirma texto ainda em edição antes de salvar ou substituir o projeto."""
        # Também confirma edição por acessibilidade/testes sem janela ativa.
        from PySide6.QtWidgets import QLineEdit
        for field in self.inspector.findChildren(QLineEdit):
            if field.isModified():
                field.setModified(False);field.editingFinished.emit()
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
        if not self.prepare_script_change():return False
        return self.logic.flush()

    def add_component(self) -> None:
        """Insere no contêiner ou página adequada à seleção atual."""
        if self.active_state!='@default':
            self.statusBar().showMessage('Adicione componentes no estado Padrão.',6000);return
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

    def _edit(self, change: Callable[[], None], refresh=True) -> None:
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
        if refresh:self._refresh()
        else:self._update_actions()

    def change_application(self,key,value):
        """Metadados do app não precisam destruir os widgets da interface em edição."""
        if self.project.application.get(key)==value or not self._finish_field_edit():return
        before=deepcopy(self.project.application);self.project.application[key]=value
        try:Project.from_dict(self.project.to_dict())
        except ProjectError as exc:self.project.application=before;self._show_error(str(exc));return
        self.history.push(self.project)
        if key=='backend':self._refresh()
        else:
            self.canvas._project.application=deepcopy(self.project.application)
            self._update_actions()

    def _can_drop(self, payload: dict, parent_id: str) -> bool:
        """Valida arraste sem alterar o documento durante a passagem do mouse."""
        if self.active_state!='@default':return False
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
        if self.active_state!='@default':self._refresh();return
        node=self.project.find(node_id)
        ids=getattr(self,'selected_ids',{node_id})
        if len(ids)>1 and node_id in ids and geometry.get('width',node.geometry['width'])==node.geometry['width'] and geometry.get('height',node.geometry['height'])==node.geometry['height']:
            dx=geometry.get('x',node.geometry['x'])-node.geometry['x'];dy=geometry.get('y',node.geometry['y'])-node.geometry['y']
            siblings=[self.project.find(identifier) for identifier in ids if self.project.parent_of(identifier) is self.project.parent_of(node_id)]
            dx=max(-min(item.geometry['x'] for item in siblings),min(dx,20000-max(item.geometry['x'] for item in siblings)))
            dy=max(-min(item.geometry['y'] for item in siblings),min(dy,20000-max(item.geometry['y'] for item in siblings)))
            def move_group():
                """Transfere o grupo preservando posições relativas e limites válidos."""
                for identifier in ids:
                    item=self.project.find(identifier)
                    if self.project.parent_of(identifier) is self.project.parent_of(node_id):
                        self.project.set_geometry(identifier,{'x':max(0,min(20000,item.geometry['x']+dx)),'y':max(0,min(20000,item.geometry['y']+dy))})
            self._edit(move_group,refresh=False)
            self.patch_geometries(ids)
        else:
            self._edit(lambda:self.project.set_geometry(node_id,geometry),refresh=False)
            self.patch_geometries([node_id])

    def duplicate_component(self) -> None:
        """Duplica a seleção com identificadores próprios e mantém a cópia selecionada."""
        if self.active_state!='@default':
            self.statusBar().showMessage('Edite a estrutura no estado Padrão.',6000);return
        def duplicate():
            """Duplica os nós superiores da seleção e mantém o grupo copiado selecionado."""
            identifiers=self.top_level_selection()
            copies=[self.project.duplicate(identifier).id for identifier in identifiers]
            self.selected_ids=set(copies);self.selected_id=copies[-1]
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
        if self.active_state!='@default':
            self.statusBar().showMessage('Edite a estrutura no estado Padrão.',6000);return
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
        if self.active_state!='@default':
            self.statusBar().showMessage('Edite a estrutura no estado Padrão.',6000);return
        if not self._finish_field_edit():
            return
        node=self.project.find(self.selected_id)
        if node and node.kind==ComponentKind.WINDOW:
            if len(self.project.roots)>1:self.remove_window()
            return
        if len(getattr(self,'selected_ids',set()))>1:
            def remove_group():
                """Agrupa remoções de irmãos/contêineres em uma única alteração reversível."""
                identifiers=self.top_level_selection();parent=self.project.parent_of(identifiers[0])
                for identifier in identifiers:self.project.remove(identifier)
                self.selected_id=parent.id if parent and self.project.find(parent.id) else self.active_window;self.selected_ids={self.selected_id}
            self._edit(remove_group);return
        try:
            self.selected_id = self.project.remove(self.selected_id)
        except ProjectError as exc:
            self._show_error(str(exc))
            return
        self.history.push(self.project)
        self._refresh()

    def undo(self) -> None:
        """Restaura o documento anterior, incluindo propriedades e ordem dos nós."""
        if self.tabs.currentIndex() == 2 and (not hasattr(self,"code_files") or self.code_files.currentIndex()>0):
            self.active_code_editor().undo()
            return
        if not self._finish_field_edit():
            return
        self.project = self.history.undo()
        self._refresh()

    def redo(self) -> None:
        """Reaplica uma alteração previamente desfeita."""
        if self.tabs.currentIndex() == 2 and (not hasattr(self,"code_files") or self.code_files.currentIndex()>0):
            self.active_code_editor().redo()
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
            self.project_dialog_parent(), "Abrir projeto Makebench", str(self.path.parent) if self.path else "",
            "Projetos Makebench (*.makebench.json *.zip);;JSON (*.json)",
        )
        if not filename:
            return
        if filename.lower().endswith('.zip'):
            destination=QFileDialog.getExistingDirectory(self.project_dialog_parent(),'Extrair em pasta vazia','')
            if not destination:return
            from makebench.core.bundle import read_bundle
            try:filename=str(read_bundle(filename,Path(destination)))
            except (ProjectError,OSError) as exc:self._show_error(str(exc));return
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
        self._trusted_session=False;self._created_here=False
        self.project = project
        self.path = path
        self.source = source
        self.source_editor.blockSignals(True)
        self.source_editor.setPlainText(source.text)
        self.source_editor.blockSignals(False)
        self._script_target=None;self._script_original=''
        self.script_editor.clear();self.script_apply.setEnabled(False)
        self.logic.flow_id = None
        self.logic._target_component=None
        self.assets = AssetStore(path.parent if path else None)
        self.history = History(project)
        self.selected_id = project.root.id
        self._refresh()
        self.remember_project()
        self.pages.setCurrentWidget(self.editor_page)

    def save(self) -> bool:
        """Salva o projeto ou solicita um destino quando ainda não tem caminho."""
        if not self._finish_field_edit():
            return False
        if self.path is None:
            return self.save_as()
        return self.save_to(self.path)

    def save_as(self) -> bool:
        """Solicita um destino, sem mudar o caminho atual em caso de falha."""
        return self.save_as_dialog()

    def save_to(self, path: Path) -> bool:
        """Persiste o documento e marca como salvo somente depois do sucesso."""
        if not self._finish_field_edit():
            return False
        path = path.resolve()
        try:
            self.project.python_files=sorted(self.source.modules)
            Project.from_dict(self.project.to_dict())
            self.assets.write_referenced(path.parent, self.project.asset_paths())
            self.source.write(path)
            backup=save_project(self.project, path)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return False
        self.path = path
        self.assets.root = path.parent.resolve()
        self.history.mark_saved()
        self.source.mark_saved()
        self._update_code()
        self._update_actions()
        self.remember_project()
        self.canvas.close_native_preview()
        self.clear_recovery()
        if backup:self.statusBar().showMessage(f'Projeto atualizado para formato {self.project.to_dict()["format_version"]}. A cópia {backup.name} preserva a versão anterior; editores antigos não abrem os recursos novos.',12000)
        return True

    def _confirm_discard(self) -> bool:
        """Oferece salvar alterações antes de fechar, abrir ou criar um projeto."""
        if not self._finish_field_edit():
            choice = QMessageBox.warning(
                self, "Blocos não confirmados", "Há alterações de lógica ainda não confirmadas. Descartar pode perder blocos ou o script em edição. Deseja descartar e continuar?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice==QMessageBox.StandardButton.Discard:
                self.clear_recovery();return True
            return False
        if not self.history.dirty and not self.source.dirty:
            return True
        choice = QMessageBox.warning(
            self, "Salvar alterações?", "O projeto tem alterações que ainda não foram salvas.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        if choice==QMessageBox.StandardButton.Discard:
            self.clear_recovery();return True
        return False

    def _tab_changed(self, index):
        """Confirma blocos ao sair e inicia WebEngine apenas quando necessário."""
        if index != 1 and not self._finish_field_edit():
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
        self.setWindowModified(True)
        if hasattr(self,"code_files"):self.code_files.setTabText(1,"Funções próprias •")

    def _source_analysis_ready(self):
        """Analisa após uma pausa na digitação, sem atualizar todos os painéis por tecla."""
        self._update_code();self._update_actions()

    def _update_code(self):
        """Mostra código e diagnósticos sem importar o arquivo de funções."""
        self.sync_code_workspace()
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
            states=[self.active_state] if self.project.states.get(self.active_window) else None
            existing=[f for f in self.project.workflows if f.get('event',{}).get('component')==component_id]
            flow=next((f for f in existing if self.active_state in f.get('states',[])),None) or next((f for f in existing if not f.get('states')),None)
            if flow is None:flow=create_flow(self.project,component_id,states=states)
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
        if flow is None or flow.get('editor')=='nodes' or not isinstance(data.get('workspace'), dict):
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
            if self.runtime_window.session.admin_active:
                self.statusBar().showMessage('Aguarde a tarefa administrativa terminar antes de reiniciar.',7000);return
            from .settings import preference
            if self.runtime_window.session.busy and preference('test/confirm_restart'):
                choice=QMessageBox.warning(self,'Reiniciar teste?','Uma tarefa está em andamento. Reiniciar encerra o teste e os processos comuns.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
                if choice!=QMessageBox.StandardButton.Yes:return
            if not self.runtime_window.stop():
                self.statusBar().showMessage('Aguarde a tarefa administrativa terminar antes de reiniciar.',7000);return
            self._restart_pending=True;return
        if not self._finish_field_edit():
            return
        if not self.confirm_trust():return
        from makebench.runtime.window import RuntimeWindow
        if self.project.application.get('backend','qt')=='gtk':
            from makebench.runtime.gtk_bridge import GtkRuntimeBridge as RuntimeWindow
        try:
            window = RuntimeWindow(self.project, self.source.text, self.assets.read,
                self.path.parent if self.path else None, self.source.path, self, supervision=False)
        except (ProjectError, OSError) as exc:
            if self.project.application.get('backend','qt')=='gtk':self._show_error(str(exc))
            self.sync_problems();self.drawer.show();self.drawer.setCurrentIndex(1)
            self.statusBar().showMessage('Teste impedido: resolva os itens em Problemas.',7000);return
        if self.runtime_window is not None:
            self.runtime_window.close()
        self.runtime_window = window
        window.locate_requested.connect(lambda error: self._locate_runtime_error(error, window))
        window.shutdown_finished.connect(self._runtime_stopped)
        window.destroyed.connect(lambda: self._runtime_destroyed(window))
        self._debug_active=getattr(self,'_next_debug',False);self._next_debug=False
        config={'enabled':self._debug_active,'breakpoints':self.breakpoints()}
        if hasattr(window.session,'snapshot'):window.session.snapshot['debug']=config
        else:window.debug_config=config
        self.monitor_runtime(window)
        window.show();window.start()

    def _runtime_destroyed(self, window):
        """Remove apenas a referência da janela que foi efetivamente destruída."""
        if self.runtime_window is window:
            self.runtime_window = None

    def _runtime_stopped(self):
        """Retoma fechamento após o supervisor terminar a limpeza dos processos."""
        self._update_actions()
        if self._closing_after_runtime:
            QTimer.singleShot(0, self.close)
        elif getattr(self,'_restart_pending',False):
            self._restart_pending=False;QTimer.singleShot(0,self.run_project)

    def _locate_runtime_error(self, error, window):
        """Localiza o bloco atual; linhas próprias só valem se o texto não mudou."""
        if self.project.id != window.project.id:
            self.statusBar().showMessage("O erro pertence a outro projeto aberto na execução.", 7000);return
        from makebench.core.source import source_signature
        if error.get('source_line') and source_signature(self.source.text)==source_signature(window.source):
            self.open_code_file(error.get('source_file','@actions'),error['source_line'])
        elif error.get('block'):
            flow = next((f for f in self.project.workflows if f['id'] == error.get('flow')), None)
            if flow:
                self.logic.sync(flow['id']);self.tabs.setCurrentIndex(1)
                self.logic.focus_block(flow['id'], error['block'])
        self.raise_();self.activateWindow()

    def _show_error(self, message: str) -> None:
        """Apresenta falhas recuperáveis sem fechar o editor."""
        QMessageBox.critical(self.project_dialog_parent(), "Makebench", message)

    def show_about(self) -> None:
        """Informa a versão e o limite funcional da entrega atual."""
        QMessageBox.about(
            self, "Sobre o Makebench",
            "<h2>Makebench</h2><p>Aplicativos Linux, construídos por você.</p>"
            f"<p>Versão {__version__} — Bancada, janelas, estados e fonte Python.</p>"
            "<p>Crie interfaces Qt ou GTK4, conecte blocos e exporte em fonte Python. "
            "DEB, RPM, AppImage e Flatpak geram receitas; a construção exige ferramentas e SDKs de destino.</p>",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Protege alterações não salvas ao encerrar a janela."""
        window = self.runtime_window
        if window is not None and window.session.admin_active:
            window.show();window.raise_()
            self.statusBar().showMessage("Aguarde a tarefa administrativa terminar antes de fechar o editor.", 7000)
            event.ignore();return
        if not self._closing_after_runtime and not getattr(self,'_closing_after_build',False) and not getattr(self,'_closing_after_preview',False) and not self._confirm_discard():
            event.ignore();return
        if window is not None and not window.session.closed:
            if not window.stop():
                self.statusBar().showMessage('Aguarde a tarefa administrativa terminar antes de fechar.',7000);event.ignore();return
            self._closing_after_runtime = True
            self.setEnabled(False)
            window.close_pending=True
            event.ignore();return
        if hasattr(self,'publish_panel') and self.publish_panel.job and self.publish_panel.job.isRunning():
            self._closing_after_build=True
            self.publish_panel.cancel_build()
            self.statusBar().showMessage('Cancelando construção antes de fechar…',5000)
            QTimer.singleShot(100,self.close);event.ignore();return
        canvas_ready=self.canvas.close_native_preview()
        thumbnails_ready=self.map_panel.previews.shutdown() if hasattr(self,'map_panel') else True
        if not canvas_ready or not thumbnails_ready:
            self._closing_after_preview=True;self.setEnabled(False)
            self.statusBar().showMessage('Encerrando prévias…',3000)
            QTimer.singleShot(100,self.close);event.ignore();return
        if hasattr(self,'terminal_panel'):self.terminal_panel.surface.stop_terminal()
        self.clear_recovery()
        event.accept()
