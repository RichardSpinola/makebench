"""Ferramentas de código e dados: inspeção estática, sem importar funções do usuário."""
import ast
from copy import deepcopy
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox,QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,
    QInputDialog,QLabel,QLineEdit,QListWidget,QListWidgetItem,QPushButton,QSplitter,QTabWidget,QVBoxLayout,QWidget)
from makebench.core.project import ProjectError


class DevelopmentMixin:
    """Liga Lógica e Código a dados estáticos e ao contexto da seleção."""
    def install_development(self):
        """Reorganiza arquivos existentes em abas e acrescenta outline navegável."""
        self.logic.duplicate_requested.connect(self.duplicate_flow_dialog)
        self.logic.search_requested.connect(self.search_block)
        self.logic.function_requested.connect(self.find_function_name)
        self.logic.filter_requested.connect(self.change_flow_filter)
        self.logic.full_code_requested.connect(self.show_generated_line)
        code_page=self.tabs.widget(2);layout=code_page.layout()
        old=code_page.findChild(QSplitter)
        generated=old.widget(0);own=old.widget(1)
        self.code_files=QTabWidget();self.code_files.addTab(generated,'gerado.py · somente leitura');self.code_files.addTab(own,'Funções próprias')
        self.code_files.setDocumentMode(True);self.code_files.setTabPosition(QTabWidget.TabPosition.South)
        for page in (code_page,generated,own):page.layout().setContentsMargins(4,4,4,4);page.layout().setSpacing(4)
        self.code_files.setCurrentIndex(1)
        self.code_files.currentChanged.connect(lambda _:self._update_actions())
        self.function_outline=QListWidget();self.function_outline.setAccessibleName('Funções do arquivo e usos nos blocos')
        self.function_outline.itemActivated.connect(self.open_function)
        self.function_outline.itemClicked.connect(self.open_function)
        pane=QWidget();pl=QVBoxLayout(pane);pl.setContentsMargins(4,4,4,4);pl.addWidget(QLabel('Funções do projeto'));self.function_search=QLineEdit();self.function_search.setPlaceholderText('Filtrar funções…');self.function_search.setClearButtonEnabled(True);self.function_search.textChanged.connect(self.filter_outline);pl.addWidget(self.function_search);pl.addWidget(self.function_outline)
        add=QPushButton('+ Nova função');add.clicked.connect(self.new_function);pl.addWidget(add)
        splitter=QSplitter();splitter.setHandleWidth(4);splitter.addWidget(self.code_files);splitter.addWidget(pane);splitter.setSizes([900,260])
        index=layout.indexOf(old);layout.removeWidget(old);old.deleteLater();layout.insertWidget(index,splitter,1)
        self.code_splitter=splitter
        for panel,key in [(self.logic.splitter,'logic'),(splitter,'code')]:
            stored=self.settings.value('workspace/'+key+'_panels')
            if stored:panel.restoreState(stored)
            panel.splitterMoved.connect(lambda *_,panel=panel,key=key:self.settings.setValue('workspace/'+key+'_panels',panel.saveState()))
        self.code_position=QLabel();self.code_position.setAlignment(Qt.AlignmentFlag.AlignRight);layout.addWidget(self.code_position)
        self.source_editor.cursorPositionChanged.connect(self.update_code_position);self.generated_editor.cursorPositionChanged.connect(self.update_code_position);self.code_files.currentChanged.connect(self.update_code_position);self.update_code_position()
        self.code_diagnostics.hide()
        for n in range(layout.count()):
            widget=layout.itemAt(n).widget()
            if isinstance(widget,QLabel) and widget not in (self.code_diagnostics,self.code_position):widget.hide()
        self.source_editor.textChanged.connect(self.sync_outline)
        data_page=QWidget();dl=QVBoxLayout(data_page);dl.setContentsMargins(4,4,4,4);dl.setSpacing(4);dl.addWidget(self.data_list)
        actions=QHBoxLayout()
        for label,callback in [('+ Variável',self.variable_dialog),('Editar',self.edit_data_item),('Remover',self.remove_variable)]:
            button=QPushButton(label);button.clicked.connect(callback);actions.addWidget(button)
        dl.addLayout(actions);self.left_tabs.removeTab(2);self.left_tabs.addTab(data_page,'Dados')
        self.data_list.itemActivated.connect(lambda _:self.edit_data_item())
        self.sync_outline()
        from PySide6.QtWidgets import QToolBar
        from PySide6.QtCore import QSize
        from .theme import icon
        commands=QToolBar('Blocos');commands.setIconSize(QSize(16,16));commands.setMovable(False)
        commands.addAction(icon('search'),'Buscar bloco…',self.search_block)
        self.logic.layout().removeWidget(self.logic.edit_text);commands.addWidget(self.logic.edit_text)
        self.logic.layout().insertWidget(1,commands)
        # Realce Bash no editor da gaveta; sua aplicação continua explícita.
        self.script_editor.highlighter.language='bash';self.script_editor.highlighter.rehighlight()

    def change_flow_filter(self,flow_id,states):
        """Altera somente o filtro, com validação de sobreposição e histórico."""
        def change():
            """Atualiza o campo solicitado dentro da transação de edição."""
            flow=next(f for f in self.project.workflows if f['id']==flow_id)
            if states:flow['states']=states
            else:flow.pop('states',None)
        self._edit(change)

    def show_generated_line(self,line):
        """Abre o arquivo completo mantendo a linha do handler em foco."""
        self.set_mode('Código');self.code_files.setCurrentIndex(0);self.generated_editor.show_line(line)

    def sync_outline(self):
        """Lê assinaturas e docstrings com AST; arquivos inválidos continuam editáveis."""
        if not hasattr(self,'function_outline'):return
        signature=(self.source_editor.toPlainText(),json.dumps(self.project.workflows,sort_keys=True))
        if signature==getattr(self,'_outline_signature',None):return
        self._outline_signature=signature
        self.function_outline.clear()
        try:tree=ast.parse(self.source_editor.toPlainText())
        except (SyntaxError,ValueError):return
        def uses(value,name):
            """Conta referências estáticas sem importar funções Python."""
            if isinstance(value,dict):return int(value.get('op')=='call' and value.get('function')==name)+sum(uses(v,name) for v in value.values())
            if isinstance(value,list):return sum(uses(v,name) for v in value)
            return 0
        for node in tree.body:
            if isinstance(node,ast.FunctionDef):
                count=sum(uses(f.get('body'),node.name) for f in self.project.workflows)
                item=QListWidgetItem(node.name+'('+', '.join(a.arg for a in node.args.args)+f') · {count} uso(s)')
                item.setData(Qt.ItemDataRole.UserRole,node.lineno);item.setToolTip(ast.get_docstring(node) or 'Sem descrição.')
                self.function_outline.addItem(item)
        self.filter_outline()

    def update_code_position(self,_index=None):
        """Informa linha e coluna no arquivo ativo sem roubar foco nem alterar o texto."""
        editor=self.generated_editor if self.code_files.currentIndex()==0 else self.source_editor;cursor=editor.textCursor()
        self.code_position.setText(f'Linha {cursor.blockNumber()+1} · Coluna {cursor.positionInBlock()+1}')

    def filter_outline(self,_text=None):
        """Filtra funções localmente, mantendo o arquivo e a seleção de texto intactos."""
        if not hasattr(self,'function_search'):return
        text=self.function_search.text().casefold()
        for index in range(self.function_outline.count()):
            item=self.function_outline.item(index);item.setHidden(text not in item.text().casefold())

    def open_function(self,item):
        """Localiza a definição sem executar o arquivo."""
        self.code_files.setCurrentIndex(1);self.source_editor.show_line(item.data(Qt.ItemDataRole.UserRole))

    def new_function(self):
        """Insere uma definição independente, preservando todo o texto próprio."""
        name,ok=QInputDialog.getText(self,'Nova função','Nome Python')
        if not ok:return
        import keyword
        if not name.isidentifier() or keyword.iskeyword(name) or name.startswith('_'):
            self._show_error('Use um nome Python válido, sem espaços e sem iniciar por sublinhado.');return
        try:names=[n.name for n in ast.parse(self.source.text).body if isinstance(n,ast.FunctionDef)]
        except SyntaxError:self._show_error('Corrija a sintaxe antes de inserir uma função pelo assistente.');return
        if name in names:self._show_error('Já existe uma função com esse nome.');return
        self.code_files.setCurrentIndex(1)
        self.source_editor.appendPlainText('\n\ndef '+name+'(ctx, valor):\n    """Descreva o comportamento, a entrada e o resultado desta função."""\n    pass\n')
        self.source_editor.show_line(self.source_editor.blockCount()-2)

    def sync_variables(self):
        """Acrescenta dados por escopo sem converter nomes em código Python."""
        if not hasattr(self,'data_list'):return
        for index,variable in enumerate(self.project.variables):
            scope='Projeto' if variable.get('scope','project')=='project' else self.project.find(variable['window']).properties.get('title','Janela')
            item=QListWidgetItem(f"Variável · {variable['name']} = {variable.get('initial')!r}\n{scope}")
            item.setData(Qt.ItemDataRole.UserRole,index);self.data_list.insertItem(0,item)

    def variable_dialog(self,_checked=False,index=None):
        """Declara ou renomeia uma variável, atualizando referências e workspaces."""
        original=self.project.variables[index] if index is not None else None
        dialog=QDialog(self);dialog.setWindowTitle('Variável do aplicativo');form=QFormLayout(dialog)
        name=QLineEdit(original['name'] if original else 'contador')
        scope=QComboBox();scope.addItem('Do projeto','project');scope.addItem('Desta janela','window')
        scope.setCurrentIndex(scope.findData(original.get('scope','project') if original else 'project'))
        initial=QLineEdit(json.dumps(original.get('initial') if original else 0,ensure_ascii=False))
        form.addRow('Nome',name);form.addRow('Escopo',scope);form.addRow('Valor inicial (JSON)',initial)
        error=QLabel();form.addRow(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def save():
            """Valida os campos e só confirma depois de salvar com sucesso."""
            try:value=json.loads(initial.text())
            except ValueError:error.setText('Use texto entre aspas, número, true, false ou null.');return
            variable={'name':name.text().strip(),'scope':scope.currentData(),'initial':value}
            if scope.currentData()=='window':variable['window']=self.active_window
            def edit():
                """Atualiza a declaração e referências sem executar código."""
                if original:
                    self.rename_variable_references(original,variable)
                    self.project.variables[index]=variable
                else:self.project.variables.append(variable)
            self._edit(edit)
            from makebench.core.navigation import validate_navigation
            try:validate_navigation(self.project)
            except ProjectError as exc:error.setText(str(exc));return
            dialog.accept()
        buttons.accepted.connect(save);dialog.exec()

    def rename_variable_references(self,old,new):
        """Atualiza o modelo neutro e a vista Blockly, sem perder rascunhos/comentários."""
        def visit(value,workspace=False):
            """Percorre dados estruturados sem executar conteúdo do projeto."""
            if isinstance(value,dict):
                if value.get('op') in {'variable','assign','ask'} and value.get('name')==old['name'] and value.get('scope','project')==old.get('scope','project'):
                    value.update(name=new['name'],scope=new['scope'])
                if value.get('type') in {'mb_variable','mb_assign','mb_ask'}:
                    fields=value.get('fields',{})
                    if fields.get('NAME')==old['name'] and fields.get('SCOPE','project')==old.get('scope','project'):fields.update(NAME=new['name'],SCOPE=new['scope'],VARIABLE_PICKER='@none')
                for child in value.values():visit(child,workspace)
            elif isinstance(value,list):
                for child in value:visit(child,workspace)
        for flow in self.project.workflows:
            if old.get('scope')=='window' and self.project.window_of(flow['event']['component']).id!=old['window']:continue
            visit(flow.get('body'));visit(flow.get('workspace'))

    def edit_data_item(self):
        """Edita variável selecionada; funções abrem o modo Código."""
        item=self.data_list.currentItem()
        if not item:return
        value=item.data(Qt.ItemDataRole.UserRole)
        if isinstance(value,int):self.variable_dialog(index=value)
        elif isinstance(value,dict) and value.get('kind')=='resource':self.edit_resource(value['path'])
        elif item.text().startswith('Função'):self.find_function_name(item.text().split('·',1)[-1].strip().split('(')[0])

    def remove_variable(self):
        """Remove declaração sem apagar valores ou blocos; referências continuam visíveis."""
        item=self.data_list.currentItem()
        if item and isinstance(item.data(Qt.ItemDataRole.UserRole),dict):
            self.remove_resource(item.data(Qt.ItemDataRole.UserRole)['path']);return
        if item and isinstance(item.data(Qt.ItemDataRole.UserRole),int):
            index=item.data(Qt.ItemDataRole.UserRole);self._edit(lambda:self.project.variables.pop(index))

    def search_block(self):
        """Pesquisa tipos disponíveis e insere um rascunho real no Blockly."""
        if not self.logic.ready:return
        entries={'Mostrar mensagem':'mb_message','Registrar na saída':'mb_log','Condição se/senão':'mb_if','Repetir':'mb_repeat','Executar programa':'mb_run','Executar Bash':'mb_script','Perguntar':'mb_ask','Confirmar':'mb_confirm','Chamar função':'mb_call','Ir para estado':'mb_go_state','Abrir janela':'mb_open_window','Fechar janela':'mb_close_window','Definir variável':'mb_assign','Valor de variável':'mb_variable'}
        entries.update({'Texto':'text','Número':'math_number','Verdadeiro ou falso':'logic_boolean','Lista de valores':'lists_create_with','Texto de várias linhas':'mb_multiline','Alterar texto de componente':'mb_set_text','Habilitar componente':'mb_set_enabled','Alterar progresso':'mb_set_value','Mostrar página':'mb_show_page','Ler texto do componente':'mb_read_text','Ler seleção da caixa':'mb_read_checked','Ler progresso':'mb_read_value','Juntar textos':'mb_join','Comparar ou calcular':'mb_binary'})
        choice,ok=QInputDialog.getItem(self,'Buscar bloco','Digite para buscar',list(entries),0,True)
        if not ok:return
        if choice not in entries:
            matches=[name for name in entries if choice.casefold() in name.casefold()]
            if not matches:self.statusBar().showMessage('Nenhum bloco corresponde à busca.',5000);return
            if len(matches)==1:choice=matches[0]
            else:
                choice,ok=QInputDialog.getItem(self,'Blocos encontrados','Escolha um bloco',matches,0,False)
                if not ok:return
        self.logic.page.runJavaScript('window.makebench.addBlock('+json.dumps(entries[choice])+')')

    def find_function_name(self,name):
        """Abre uma função solicitada pelo bloco, após análise sintática estática."""
        try:node=next((n for n in ast.parse(self.source.text).body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        except (SyntaxError,ValueError):return
        if node:self.set_mode('Código');self.code_files.setCurrentIndex(1);self.source_editor.show_line(node.lineno)

    def duplicate_flow_dialog(self,identifier):
        """Copia comportamento para outro evento/estado com IDs novos e comentários."""
        from makebench.core.logic import create_flow
        from makebench.core.project import ComponentKind,new_id
        flow=next(f for f in self.project.workflows if f['id']==identifier)
        if flow.get('body') is None:self._show_error('Complete o rascunho antes de duplicar o fluxo.');return
        targets=[node for node in self.project.walk() if node.kind in {ComponentKind.WINDOW,ComponentKind.BUTTON}]
        labels=[node.display_name+' · '+self.project.window_of(node.id).properties.get('title','Janela') for node in targets]
        choice,ok=QInputDialog.getItem(self,'Duplicar fluxo','Evento de destino',labels,0,False)
        if not ok:return
        target=targets[labels.index(choice)];owner=self.project.window_of(target.id)
        states=[{'id':None,'name':'Em qualquer estado'},{'id':'@default','name':'Padrão'},*self.project.states.get(owner.id,[])]
        chosen,ok=QInputDialog.getItem(self,'Duplicar fluxo','Filtro de estado',[state['name'] for state in states],0,False)
        if not ok:return
        selected=states[[state['name'] for state in states].index(chosen)]['id'];filters=[selected] if selected else []
        if any(f['event']['component']==target.id and f.get('states',[])==filters for f in self.project.workflows):self._show_error('Já existe um fluxo nesse evento e filtro. Escolha outro destino.');return
        def copy():
            """Duplica dados e referências, preservando o original."""
            clone=create_flow(self.project,target.id,states=filters);clone['body']=deepcopy(flow['body']);clone['workspace']={'workspaceComments':deepcopy(flow.get('workspace',{}).get('workspaceComments',[]))}
            def reidentify(value):
                """Cria identificadores independentes para os blocos copiados."""
                if isinstance(value,dict):
                    if 'op' in value:value['id']=new_id('block')
                    for child in value.values():reidentify(child)
                elif isinstance(value,list):
                    for child in value:reidentify(child)
            reidentify(clone['body']);self.logic.flow_id=clone['id'];self.logic._target_component=None
        self._edit(copy)
