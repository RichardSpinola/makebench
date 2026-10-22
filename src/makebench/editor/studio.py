"""Bancada de trabalho: modos, contexto persistente e diagnóstico navegável."""
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTabWidget, QToolBar,
    QToolButton, QVBoxLayout, QWidget, QComboBox)
from .commands import CommandPalette, register
from .theme import icon, manager


from .projects import ProjectMixin
from .navigation import NavigationMixin
from .designer import DesignerMixin
from .development import DevelopmentMixin
from .execution import ExecutionMixin
from .resources import ResourceMixin


class StudioMixin(ProjectMixin, NavigationMixin, DesignerMixin, DevelopmentMixin, ExecutionMixin, ResourceMixin):
    """Adapta as vistas existentes sem duplicar documento, geração ou execução."""

    def install_studio(self):
        """Substitui a navegação antiga; preserva os widgets e APIs de edição."""
        self.settings=QSettings('Makebench','Makebench')
        self._mode='Design';self._problem_targets=[]
        for toolbar in self.findChildren(QToolBar):toolbar.hide()
        self.tabs.tabBar().hide()
        self.design_splitter=self.tabs.widget(0)
        # Remonta as vistas existentes em painéis com responsabilidades explícitas.
        old_left=self.design_splitter.widget(0)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0)
        self.left_tabs=QTabWidget()
        structure=QWidget();sl=QVBoxLayout(structure)
        self.tree_search=QLineEdit();self.tree_search.setPlaceholderText('Buscar componente…')
        self.tree_search.setAccessibleName('Buscar componente');sl.addWidget(self.tree_search)
        sl.addWidget(self.tree)
        self.tree_search.textChanged.connect(self.filter_tree)
        insert=QWidget();il=QVBoxLayout(insert);il.addWidget(QLabel('Arraste para a interface ou dê dois cliques.'))
        il.addWidget(self.palette)

        add=QPushButton('Inserir selecionado');add.clicked.connect(self.add_component);il.addWidget(add)
        self.data_list=QListWidget();self.data_list.setAccessibleName('Recursos e funções do projeto')
        self.left_tabs.addTab(structure,'Estrutura');self.left_tabs.addTab(insert,'Inserir');self.left_tabs.addTab(self.data_list,'Dados')
        ll.addWidget(self.left_tabs)
        # O botão antigo será destruído; seu callback visual não deve sobreviver.
        self.remove_action.changed.disconnect()
        self.design_splitter.replaceWidget(0,left);old_left.hide();old_left.deleteLater()
        self.left_panel=left
        middle=self.design_splitter.widget(1)
        ml=middle.layout()
        # Remove títulos e instruções que competiam com a área de criação.
        for n in reversed(range(ml.count())):
            widget=ml.itemAt(n).widget()
            if isinstance(widget,QLabel):ml.removeWidget(widget);widget.deleteLater()
        middle.setObjectName('pasteboard')
        tools=QToolBar('Ferramentas de criação');tools.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        from makebench.core.project import ComponentKind
        from PySide6.QtGui import QActionGroup
        tool_group=QActionGroup(self);tool_group.setExclusive(True)
        select=tools.addAction(icon('select'),'Selecionar');select.setCheckable(True);select.setChecked(True);tool_group.addAction(select)
        select.triggered.connect(lambda:self.canvas.set_insert_tool(None))
        self.canvas.tool_changed.connect(lambda kind:select.setChecked(True) if not kind else None)
        for kind,label in [(ComponentKind.CONTAINER,'Contêiner'),(ComponentKind.LABEL,'Texto'),(ComponentKind.BUTTON,'Botão'),(ComponentKind.IMAGE,'Imagem')]:
            action=tools.addAction(icon('add'),label)
            action.setCheckable(True);tool_group.addAction(action)
            action.triggered.connect(lambda _,k=kind:self.canvas.set_insert_tool(k.value))
        ml.addWidget(tools,0,Qt.AlignmentFlag.AlignHCenter)
        self.right_panel=self.design_splitter.widget(2)
        self.design_splitter.setChildrenCollapsible(True)
        self.tree.setMinimumWidth(160);self.inspector.setMinimumWidth(220)
        self.design_splitter.setSizes([230,740,280])
        self.design_splitter.setObjectName('design_panels')
        saved=self.settings.value('workspace/design_panels')
        if saved:self.design_splitter.restoreState(saved)
        self.design_splitter.splitterMoved.connect(lambda *_:self.settings.setValue('workspace/design_panels',self.design_splitter.saveState()))
        # Uma gaveta compartilhada em todos os modos, fora do documento.
        self.drawer=QTabWidget();self.drawer.setMinimumHeight(80);self.drawer.setMaximumHeight(350)
        from .code import CodeEditor
        self.output_log=CodeEditor(True);self.output_log.setPlaceholderText('A saída aparece aqui ao testar o aplicativo.')
        self.problems=QListWidget();self.problems.itemActivated.connect(self.go_to_problem)
        self.problems.itemClicked.connect(self.go_to_problem)
        self.script_editor=CodeEditor();self.script_editor.setPlaceholderText('Selecione um bloco Bash e escolha Editar texto ou script.')
        self.script_apply=QPushButton('Aplicar ao bloco · Ctrl+Enter');self.script_apply.setEnabled(False)
        script=QWidget();sc=QVBoxLayout(script);sc.addWidget(self.script_editor);sc.addWidget(self.script_apply)
        self.drawer.addTab(self.output_log,'Saída');self.drawer.addTab(self.problems,'Problemas');self.drawer.addTab(script,'Script')
        self.drawer.hide()
        self.workspace_splitter=QSplitter(Qt.Orientation.Vertical);self.workspace_splitter.addWidget(self.tabs);self.workspace_splitter.addWidget(self.drawer)
        self.workspace_splitter.setStretchFactor(0,1);self.workspace_splitter.setSizes([650,180])
        editor=QWidget();el=QVBoxLayout(editor);el.setContentsMargins(0,0,0,0);el.setSpacing(0)
        self.context_bar=QToolBar('Contexte de création');self.context_bar.setObjectName('context_bar')
        self.context_label=QLabel();self.context_label.setTextFormat(Qt.TextFormat.PlainText)
        self.context_bar.addWidget(self.context_label)
        el.addWidget(self.context_bar);el.addWidget(self.workspace_splitter,1)
        self.drawer_toggle=QPushButton('Saída e problemas · Ctrl+J');self.drawer_toggle.clicked.connect(self.toggle_drawer)
        el.addWidget(self.drawer_toggle)
        self.pages=QStackedWidget();self.editor_page=editor;self.pages.addWidget(editor)
        self.setCentralWidget(self.pages)
        bar=QToolBar('Bancada');bar.setObjectName('workspace_toolbar');bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.home_action=QAction(icon('home'),'Início',self);self.home_action.triggered.connect(self.show_home)
        bar.addAction(self.home_action);bar.addActions([self.save_action,self.undo_action,self.redo_action]);bar.addSeparator()
        self.project_heading=QLabel();self.project_heading.setTextFormat(Qt.TextFormat.PlainText);self.project_heading.setMinimumWidth(120);bar.addWidget(self.project_heading)
        self.mode_group=QButtonGroup(self);self.mode_group.setExclusive(True);self.mode_buttons={}
        for number,name in enumerate(['Mapa','Design','Lógica','Código','Publicar'],1):
            button=QToolButton();button.setText(name);button.setCheckable(True);button.setAccessibleName('Modo '+name)
            button.clicked.connect(lambda _,m=name:self.set_mode(m));self.mode_group.addButton(button);bar.addWidget(button)
            self.mode_buttons[name]=button
            action=QAction('Modo '+name,self);action.setShortcut(QKeySequence(f'Ctrl+{number}'))
            action.triggered.connect(lambda _,m=name:self.set_mode(m));self.addAction(action)
        spacer=QWidget();from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);bar.addWidget(spacer)
        self.test_status=QLabel('Parado');self.test_status.setMaximumWidth(190);bar.addWidget(self.test_status)
        bar.addAction(self.run_action)
        self.stop_action=QAction(icon('stop'),'Parar teste',self);self.stop_action.setShortcut(QKeySequence('Shift+F5'))
        self.stop_action.triggered.connect(self.stop_test);bar.addAction(self.stop_action)
        self.workspace_toolbar=bar
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea,bar)
        view=self.menuBar().addMenu('E&xibir')
        for label,shortcut,callback in [('Painel esquerdo','Ctrl+B',lambda:self.toggle_side('left')),('Inspetor','Ctrl+Alt+B',lambda:self.toggle_side('right')),('Saída e problemas','Ctrl+J',self.toggle_drawer),('Paleta de comandos…','Ctrl+K',self.show_commands),('Preferências…','',self.preferences),('Alternar região de foco','F6',self.cycle_focus)]:
            action=QAction(label,self);action.setShortcut(QKeySequence(shortcut));action.triggered.connect(callback);view.addAction(action)
        view.addAction(self.home_action)
        grid=view.addAction('Encaixar na grade');grid.setCheckable(True);grid.setChecked(self.snap_check.isChecked())
        grid.toggled.connect(self.snap_check.setChecked);self.snap_check.hide()
        self.command_palette_action=next(a for a in view.actions() if a.text().startswith('Paleta'))
        register(self)
        manager().changed.connect(self.theme_changed)
        self.mode_buttons['Design'].setChecked(True)
        self.tabs.currentChanged.connect(self.sync_mode_button)
        self.logic.script_requested.connect(self.edit_script_inline)
        self.script_apply.clicked.connect(self.apply_script_inline)
        self.script_editor.textChanged.connect(self.script_text_changed)
        self.logic.before_switch=self.prepare_script_change
        script_action=QAction('Aplicar script',self);script_action.setShortcut(QKeySequence('Ctrl+Return'));script_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        script_action.triggered.connect(self.apply_script_inline);self.script_editor.addAction(script_action)
        self.recovery_timer=QTimer(self);self.recovery_timer.setInterval(30000)
        self.recovery_timer.timeout.connect(self.snapshot_recovery);self.recovery_timer.start()
        self.run_number=0
        self.install_projects()
        self.install_navigation_editor()
        self.install_designer()
        self.install_development()
        self.install_execution()
        from .publish import PublishPanel
        self.publish_panel=PublishPanel(self);self.tabs.addTab(self.publish_panel,"Publicar")

    def insert_kind(self, kind):
        """Insere uma ferramenta usando o mesmo histórico da paleta por arraste."""
        self.palette.setCurrentRow(self.palette.findData(kind.value));self.add_component()

    def set_mode(self, mode):
        """Troca a tarefa preservando seleção e confirmação dos blocos."""
        indexes={'Design':0,'Lógica':1,'Código':2,'Mapa':3,'Publicar':4}
        index=indexes[mode]
        if index>=self.tabs.count():return
        self.pages.setCurrentWidget(self.editor_page)
        self.workspace_toolbar.show()
        if mode=='Lógica' and self.tabs.currentIndex()!=1:
            self.logic.select_component_event(self.selected_id,self.active_state)
        self.tabs.setCurrentIndex(index);self.sync_mode_button(self.tabs.currentIndex())

    def sync_mode_button(self,index):
        """Acompanha atalhos e navegação automática para a origem dos erros."""
        modes=['Design','Lógica','Código','Mapa','Publicar']
        if 0<=index<len(modes):
            self._mode=modes[index];self.mode_buttons[self._mode].setChecked(True)
        if hasattr(self,'zoom_actions'):
            for action in self.zoom_actions:action.setVisible(self._mode in {'Design','Mapa'})
        self.sync_studio()

    def sync_studio(self):
        """Atualiza somente dados derivados; nunca executa código do projeto."""
        if not hasattr(self,'project_heading'):return
        dirty=self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty()
        self.project_heading.setText(self.project.name+(' •' if dirty else ''))
        node=self.project.find(self.selected_id)
        self.context_label.setText('  '+self.project.root.properties.get('title',self.project.name)+'  ›  '+(node.display_name if node else 'Janela'))
        data_signature=(id(self.project),self.project.id,self.history._index,self.source.text)
        if getattr(self,'_data_signature',None)!=data_signature:
            self._data_signature=data_signature;self.data_list.clear();self.list_resources()
            from makebench.core.logic import function_names
            for name in function_names(self.source.text)[0]:self.data_list.addItem('Função · '+name+'(ctx, valor)')
            self.sync_variables()
        self.sync_navigation()
        self.sync_problems()
        self.sync_outline()
        if hasattr(self,'publish_panel') and self.tabs.currentIndex()==4:self.publish_panel.sync()
        if hasattr(self,'map_panel') and self.tabs.currentIndex()==3:self.map_panel.sync()

    def sync_problems(self):
        """Concentra diagnósticos estáticos com vínculo ao fluxo ou à linha."""
        self.problems.clear();self._problem_targets=[]
        import ast
        self.source_editor.mark_syntax_error()
        try:ast.parse(self.source.text)
        except (SyntaxError,ValueError) as exc:
            self.source_editor.mark_syntax_error(getattr(exc,"lineno",1),str(exc))
            self._add_problem('Funções Python: '+str(exc),{'source_line':getattr(exc,'lineno',1)})
        from makebench.core.logic import function_names
        names=set(function_names(self.source.text)[0])
        def visit(value,flow):
            """Percorre dados estruturados sem executar conteúdo do projeto."""
            if isinstance(value,dict):
                if value.get('op')=='call' and value.get('function') not in names:
                    self._add_problem('Função ausente: '+value.get('function',''),{'flow':flow['id'],'block':value['id']})
                for child in value.values():visit(child,flow)
            elif isinstance(value,list):
                for child in value:visit(child,flow)
        from makebench.core.logic import editable
        if not editable(self.project):self._add_problem("Fluxos reservados foram preservados. A execução exige uma versão compatível.",{})
        for flow in self.project.editable_flows:
            if flow.get('body') is None:
                self._add_problem(flow.get('name','Fluxo')+': '+('; '.join(flow.get('errors',[])) or 'Complete os blocos.'),{'flow':flow['id']})
            visit(flow.get('body'),flow)
        if not self.problems.count():
            item=QListWidgetItem('Nenhum problema encontrado.');item.setFlags(Qt.ItemFlag.NoItemFlags);self.problems.addItem(item)
        count=len(self._problem_targets);self.drawer.setTabText(1,f'Problemas ({count})' if count else 'Problemas')
        self.mode_buttons['Lógica'].setText('Lógica'+(f' · {count}' if count else ''))

    def _add_problem(self,label,target):
        """Acrescenta uma linha navegável sem interpretar texto como instrução."""
        item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,target)
        self.problems.addItem(item);self._problem_targets.append(target)

    def go_to_problem(self,item):
        """Seleciona o arquivo ou o fluxo de origem do diagnóstico."""
        target=item.data(Qt.ItemDataRole.UserRole)
        if not target:return
        if target.get('source_line'):
            self.set_mode('Código');self.source_editor.show_line(target['source_line'])
        elif target.get('flow'):
            self.logic.sync(target['flow']);self.set_mode('Lógica')
            if target.get('block'):self.logic.focus_block(target['flow'],target['block'])

    def toggle_drawer(self):
        """Recolhe a gaveta sem perder logs ou o texto de um script em edição."""
        self.drawer.setVisible(not self.drawer.isVisible())

    def show_commands(self):
        """Abre a busca sobre as mesmas QAction utilizadas pelos menus."""
        import ast
        from PySide6.QtGui import QAction
        palette=CommandPalette(register(self),self)
        dynamic=[]
        def add(label,callback):
            """Liga uma entrada temporária ao item real do documento atual."""
            action=QAction(label,palette);action.triggered.connect(callback);dynamic.append(action)
        for node in self.project.walk():
            owner=self.project.window_of(node.id)
            add('Ir para componente · '+owner.properties.get('title','Janela')+' › '+(node.properties.get('code_name') or node.display_name),lambda _,identifier=node.id:self.navigate_to_item('component',identifier))
        for owner,states in self.project.states.items():
            for state in states:add('Ir para estado · '+self.project.find(owner).properties.get('title','Janela')+' › '+state['name'],lambda _,identifier=state['id'],owner=owner:self.navigate_to_item('state',identifier,owner))
        for flow in self.project.editable_flows:add('Ir para fluxo · '+flow['name'],lambda _,identifier=flow['id']:self.navigate_to_item('flow',identifier))
        try:
            for node in ast.parse(self.source.text).body:
                if isinstance(node,ast.FunctionDef):add('Ir para função · '+node.name,lambda _,name=node.name:self.find_function_name(name))
        except (SyntaxError,ValueError):pass
        palette.actions.extend(dynamic);palette.filter('');palette.exec();palette.deleteLater()

    def filter_tree(self,query):
        """Mantém ancestrais visíveis quando um descendente combina com a busca."""
        def match(item):
            """Mantém ancestrais visíveis quando um descendente corresponde à busca."""
            visible=query.casefold() in item.text(0).casefold()
            for n in range(item.childCount()):visible=match(item.child(n)) or visible
            item.setHidden(not visible);return visible
        for n in range(self.tree.topLevelItemCount()):match(self.tree.topLevelItem(n))

    def preferences(self):
        """Oferece tema e escala sem escrever preferências dentro do projeto."""
        dialog=QDialog(self);dialog.setWindowTitle('Preferências');form=QFormLayout(dialog)
        theme=QComboBox()
        for label,value in [('Sistema','system'),('Claro','light'),('Escuro','dark')]:theme.addItem(label,value)
        theme.setCurrentIndex(theme.findData(manager().mode))
        theme.currentIndexChanged.connect(lambda _:manager().set_mode(theme.currentData()))
        form.addRow('Aparência',theme)
        scale=QComboBox()
        for value in (90,100,115,130):scale.addItem(f'{value}%',value)
        scale.setCurrentIndex(scale.findData(manager().scale))
        def change_scale():
            """Aplica escala de fonte ao editor, sem modificar o aplicativo criado."""
            manager().scale=scale.currentData();manager().settings.setValue('appearance/scale',manager().scale);manager().apply()
        scale.currentIndexChanged.connect(change_scale);form.addRow('Tamanho do texto',scale)
        from PySide6.QtWidgets import QCheckBox
        motion=QCheckBox('Reduzir movimento');motion.setChecked(manager().reduce_motion)
        def change_motion(value):
            """Persiste preferência e atualiza efeitos visuais do Qt."""
            manager().reduce_motion=value;manager().settings.setValue('appearance/reduce_motion',value);manager().apply()
        motion.toggled.connect(change_motion);form.addRow(motion)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        dialog.exec()

    def edit_script_inline(self,data):
        """Edita literal no painel inferior, mantendo token e identificador Blockly."""
        target=(self.logic.token,data['id'])
        if getattr(self,'_script_target',None)==target and self.script_dirty():
            self.drawer.show();self.drawer.setCurrentIndex(2);self.script_editor.setFocus();return
        if not self.prepare_script_change():return
        self._script_target=target;self._script_original=data['text']
        self.script_editor.setPlainText(data['text']);self.script_apply.setEnabled(False)
        self.drawer.show();self.drawer.setCurrentIndex(2);self.script_editor.setFocus()

    def apply_script_inline(self):
        """Aplica texto apenas ao workspace que originou a edição."""
        import json
        target=getattr(self,'_script_target',None)
        if not target or target[0]!=self.logic.token:
            self.script_apply.setEnabled(False);return
        text=self.script_editor.toPlainText()
        code='window.makebench.setTextValue('+json.dumps(target[1])+','+json.dumps(text)+')'
        def applied(result):
            """Confirma o buffer somente quando Blockly aceitou o texto no alvo certo."""
            if result and getattr(self,'_script_target',None)==target:
                self._script_original=text;self.script_apply.setEnabled(self.script_dirty());self._update_actions()
        self.logic.page.runJavaScript(code,applied)

    def script_dirty(self):
        """Inclui texto ainda não aplicado no aviso de alterações e na recuperação."""
        return bool(getattr(self,'_script_target',None) and self.script_editor.toPlainText()!=getattr(self,'_script_original',''))

    def script_text_changed(self):
        """Mantém aplicação e indicador de alterações disponíveis durante a digitação."""
        self.script_apply.setEnabled(self.script_dirty())
        if hasattr(self,'project_heading'):self._update_actions()

    def prepare_script_change(self):
        """Confirma script pendente antes de salvar, trocar fluxo, desfazer ou fechar."""
        if not self.script_dirty():return True
        target=getattr(self,'_script_target',None)
        if not self.logic.ready or target[0]!=self.logic.token or self.logic._flushing:
            self.statusBar().showMessage('O script continua na gaveta. Copie o texto ou retorne ao bloco antes de continuar.',8000);return False
        self.apply_script_inline()
        return self.logic.flush() and not self.script_dirty()

    def stop_test(self):
        """Solicita cancelamento real, respeitando tarefas administrativas ativas."""
        if self.runtime_window:self.runtime_window.stop()

    def cycle_focus(self):
        """Percorre regiões da bancada por teclado, incluindo uma saída do canvas."""
        regions=[self.tree,self.canvas,self.inspector,self.drawer] if self._mode=='Design' else [self.logic.events,self.logic.view,self.logic.code,self.drawer] if self._mode=='Lógica' else [self.code_files,self.source_editor,self.function_outline,self.drawer]
        regions=[region for region in regions if region is not None and region.isVisible()]
        current=QApplication.focusWidget()
        index=next((i for i,region in enumerate(regions) if region is current or region.isAncestorOf(current)), -1) if current else -1
        if regions:regions[(index+1)%len(regions)].setFocus(Qt.FocusReason.ShortcutFocusReason)

    def theme_changed(self,_tokens):
        """Atualiza ícones e mantém a seleção/campos intactos ao alternar aparência."""
        register(self)
        for identifier,item in self._tree_items.items():
            node=self.project.find(identifier)
            if node:item.setIcon(0,icon(node.kind.value))

    def toggle_side(self,side):
        """Alterna apenas o painel pertencente ao modo em uso."""
        target=None
        if self._mode=='Design':target=self.left_panel if side=='left' else self.right_panel
        elif self._mode=='Lógica' and side=='right':target=self.logic.splitter.widget(1)
        elif self._mode=='Código' and side=='right':target=self.function_outline.parentWidget()
        elif self._mode=='Publicar' and side=='left':target=self.publish_panel.sections
        if target:target.setVisible(not target.isVisible())

    def navigate_to_item(self,kind,identifier,owner=None):
        """Localiza componentes, estados e fluxos preservando texto pendente e contexto."""
        if not self._finish_field_edit():return
        if kind=='state':self.activate_window(owner,identifier);self.set_mode('Design');return
        if kind=='flow':
            flow=next(f for f in self.project.editable_flows if f['id']==identifier)
            window=self.project.window_of(flow['event']['component'])
            self.activate_window(window.id,(flow.get('states') or ['@default'])[0]);self._select(flow['event']['component'])
            self.set_mode('Lógica');self.logic.sync(identifier);return
        node=self.project.find(identifier)
        if node:
            window=self.project.window_of(identifier)
            self.activate_window(window.id,self.active_state if window.id==self.active_window else '@default')
            self._select(identifier);self.set_mode('Design')
