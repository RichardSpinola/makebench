"""Arquivos Python próprios: edição, índice estático e integração com o documento."""
import hashlib
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QHBoxLayout,QInputDialog,QLabel,QMessageBox,QToolButton,QTreeWidget,QTreeWidgetItem,QWidget,QSizePolicy)
from makebench.core.code_index import CodeIndex
from makebench.core.source import ENTRY_FILE,SourceBuffer,source_signature
from makebench.core.project import ProjectError
from .code import CodeEditor
from .code_assist import CodeAssist
from .theme import icon


class CodeWorkspaceMixin:
    """Mantém buffers por arquivo e reutiliza as APIs antigas de fonte principal."""
    def install_code_workspace(self):
        """Acrescenta árvore de arquivos e assistência à área Código existente."""
        self.code_index=CodeIndex();self.module_editors={};self._workspace_buffer=None
        pane=self.function_outline.parentWidget();layout=pane.layout()
        self.code_tree=QTreeWidget();self.code_tree.setHeaderHidden(True);self.code_tree.setAccessibleName('Arquivos Python do projeto');self.code_tree.itemActivated.connect(self.code_tree_open);self.code_tree.itemClicked.connect(self.code_tree_open)
        controls=QWidget();row=QHBoxLayout(controls);row.setContentsMargins(0,0,0,0);row.addWidget(QLabel('Arquivos'),1)
        for symbol,label,callback in [('add','Novo módulo',self.new_module_dialog),('edit','Renomear módulo',self.rename_module_dialog),('remove','Excluir módulo',self.delete_module_dialog)]:
            button=QToolButton();button.setIcon(icon(symbol));button.setAccessibleName(label);button.setToolTip(label);button.clicked.connect(callback);row.addWidget(button)
        layout.insertWidget(0,controls);layout.insertWidget(1,self.code_tree,1)
        self.code_splitter.insertWidget(0,pane);self.code_splitter.setSizes([260,900])
        self.code_signature=QLabel();self.code_signature.setAccessibleName('Assinatura da chamada');self.code_signature.setTextFormat(Qt.TextFormat.PlainText);self.code_signature.setMinimumWidth(0);self.code_signature.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.tabs.widget(2).layout().addWidget(self.code_signature)
        self._entry_assist=CodeAssist(self,self.source_editor,ENTRY_FILE)
        self.code_index_timer=QTimer(self);self.code_index_timer.setSingleShot(True);self.code_index_timer.setInterval(250);self.code_index_timer.timeout.connect(self.refresh_code_index)
        self.source_editor.textChanged.connect(self.code_index_timer.start)
        self.code_files.currentChanged.connect(self.code_file_changed)
        self.sync_code_workspace()

    def sync_code_workspace(self):
        """Reconcilia apenas arquivos adicionados/removidos, sem recriar editores ativos."""
        if not hasattr(self,'code_tree'):return
        self.project.python_files=sorted(self.source.modules)
        if self._workspace_buffer is not self.source:
            for editor in self.module_editors.values():self.code_files.removeTab(self.code_files.indexOf(editor));editor.deleteLater()
            self.module_editors={};self._workspace_buffer=self.source
        for name in list(self.module_editors):
            if name not in self.source.modules or getattr(self.module_editors[name],'_source_buffer',None) is not self.source.modules[name]:
                editor=self.module_editors.pop(name);self.code_files.removeTab(self.code_files.indexOf(editor));editor.deleteLater()
        for name,buffer in self.source.modules.items():
            if name in self.module_editors:continue
            editor=CodeEditor(parent=self.code_files);editor.setPlainText(buffer.text);editor.setAccessibleName('Código '+name);editor.breakpoints_enabled=True
            editor._assist=CodeAssist(self,editor,name);editor._source_buffer=buffer;self.module_editors[name]=editor
            self.code_files.addTab(editor,Path(name).name);editor.textChanged.connect(lambda name=name,editor=editor:self.module_changed(name,editor))
            editor.cursorPositionChanged.connect(self.update_code_position);editor.breakpoint_requested.connect(lambda line,name=name:self.toggle_source_breakpoint(line,name))
            editor.undoAvailable.connect(lambda _:self._update_actions());editor.redoAvailable.connect(lambda _:self._update_actions())
            editor.setFont(self.source_editor.font());editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(' ')*4);editor.setLineWrapMode(self.source_editor.lineWrapMode())
        signature=(id(self.source),self.source.path,tuple(sorted(self.source.modules)))
        if signature!=getattr(self,'_code_tree_signature',None):
            self._code_tree_signature=signature;self.code_tree.clear();folders={}
            for label,key in [('gerado.py · leitura','@generated'),(self.source.path.name if self.source.path else 'project.actions.py',ENTRY_FILE),*[(name,name) for name in sorted(self.source.modules)]]:
                parent=None
                if key in self.source.modules:
                    path=Path(key)
                    for depth in range(1,len(path.parts)):
                        folder='/'.join(path.parts[:depth])
                        if folder not in folders:
                            item=QTreeWidgetItem([path.parts[depth-1]]);item.setData(0,Qt.ItemDataRole.UserRole,'@folder:'+folder)
                            (parent.addChild if parent else self.code_tree.addTopLevelItem)(item);folders[folder]=item;item.setExpanded(True)
                        parent=folders[folder]
                    label=path.name
                item=QTreeWidgetItem([label]);item.setData(0,Qt.ItemDataRole.UserRole,key);item.setToolTip(0,key)
                (parent.addChild if parent else self.code_tree.addTopLevelItem)(item)
        for name,editor in self.module_editors.items():self.code_files.setTabText(self.code_files.indexOf(editor),Path(name).name+(' •' if self.source.modules[name].dirty else ''))
        self.sync_code_tree_selection();self.watch_source();self.refresh_code_index()

    def current_code_file(self):
        """Identifica o arquivo ativo, conservando os índices das duas abas legadas."""
        widget=self.code_files.currentWidget()
        return next((name for name,editor in self.module_editors.items() if editor is widget),'@generated' if self.code_files.currentIndex()==0 else ENTRY_FILE)

    def active_code_editor(self):
        """Entrega o editor ativo para posição, outline e desfazer/refazer."""
        if not hasattr(self,'code_files'):return self.source_editor
        if self.code_files.currentIndex()==0:return self.generated_editor
        return self.module_editors.get(self.current_code_file(),self.source_editor)

    def open_code_file(self,name,line=1,column=1):
        """Abre arquivo do documento e traz sua localização para a área visível."""
        if name not in {ENTRY_FILE,'@generated',*self.source.modules}:return
        self.set_mode('Código')
        if name in self.source.modules:
            self.sync_code_workspace();editor=self.module_editors[name];self.code_files.setCurrentWidget(editor)
        else:
            self.code_files.setCurrentIndex(0 if name=='@generated' else 1);editor=self.active_code_editor()
        editor.show_line(line);editor.setFocus()
        if column>1:
            cursor=editor.textCursor();cursor.movePosition(cursor.MoveOperation.Right,cursor.MoveMode.MoveAnchor,column-1);editor.setTextCursor(cursor)

    def code_tree_open(self,item,*_):
        """Seleção de arquivo é navegação, não altera o projeto."""
        self.open_code_file(item.data(0,Qt.ItemDataRole.UserRole))

    def code_file_changed(self,*_):
        """Atualiza outline e posição mantendo texto e histórico por arquivo."""
        if not hasattr(self,'code_tree'):return
        self.sync_code_tree_selection()
        self._outline_signature=None;self.sync_outline();self.update_code_position();self._update_actions()

    def sync_code_tree_selection(self):
        """Marca o arquivo ativo sem mover a rolagem nem disparar navegação recursiva."""
        key=self.current_code_file()
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        iterator=QTreeWidgetItemIterator(self.code_tree);blocked=self.code_tree.blockSignals(True)
        while iterator.value():
            item=iterator.value()
            if item.data(0,Qt.ItemDataRole.UserRole)==key:self.code_tree.setCurrentItem(item);break
            iterator+=1
        self.code_tree.blockSignals(blocked)

    def module_changed(self,name,editor):
        """Confirma texto no buffer e adia análise para não percorrer a UI por tecla."""
        if name not in self.source.modules:return
        self.source.modules[name].text=editor.toPlainText();self.code_index_timer.start();self.source_timer.start()
        self.setWindowModified(True);self.code_files.setTabText(self.code_files.indexOf(editor),Path(name).name+' •')

    def refresh_code_index(self):
        """Reconstrói índice só quando o conteúdo muda; erros não apagam o último AST."""
        if not hasattr(self,'code_index'):return
        signature=(source_signature(self.source.text),tuple((n.id,n.display_name) for n in self.project.walk()))
        if signature==getattr(self,'_code_index_signature',None):return
        self._code_index_signature=signature;self.code_index.update(self.source.text,self.project.walk())
        for name,editor in [(ENTRY_FILE,self.source_editor),*self.module_editors.items()]:
            error=next((e for e in self.code_index.errors if e['file']==name),None);editor.mark_syntax_error(error['line'] if error else None,error['message'] if error else '')

    def update_module_manifest(self):
        """Declara só arquivos reais do documento; formatos antigos não mudam ao abrir."""
        self.project.python_files=sorted(self.source.modules);self.sync_code_workspace();self._update_code();self._update_actions()

    def add_code_module(self,name,text=''):
        """API compartilhada pelo diálogo e testes; criação é editável antes de salvar."""
        self.source.add_module(name,text);self.update_module_manifest();self.open_code_file(name)

    def new_module_dialog(self):
        """Cria nome validado dentro do pacote reservado, sem tocar no disco."""
        name,ok=QInputDialog.getText(self,'Novo módulo','Arquivo dentro de makebench_user',text='helpers.py')
        if ok:
            try:self.add_code_module(name if name.startswith('makebench_user/') else 'makebench_user/'+name)
            except ProjectError as exc:self._show_error(str(exc))

    def rename_module_dialog(self):
        """Conserva textos; imports antigos são diagnosticados, sem reescrita implícita."""
        old=self.current_code_file()
        if old not in self.source.modules:return
        name,ok=QInputDialog.getText(self,'Renomear módulo','Novo caminho (imports não são reescritos)',text=old)
        if ok and name!=old:
            try:
                self.source.rename_module(old,name)
                for point in self.breakpoints():
                    if point.get('file')=='source' and point.get('path')==old:point['path']=name
                self.update_module_manifest();self.open_code_file(name)
            except ProjectError as exc:self._show_error(str(exc))

    def delete_module_dialog(self):
        """Solicita confirmação concreta e mantém exclusão pendente até salvar."""
        name=self.current_code_file()
        if name not in self.source.modules:return
        changed=' Há alterações não salvas neste arquivo.' if self.source.modules[name].dirty else ''
        if QMessageBox.question(self,'Excluir módulo?',name+' será removido ao salvar o projeto.'+changed,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        try:self.source.remove_module(name);self.update_module_manifest()
        except ProjectError as exc:self._show_error(str(exc))

    def fingerprint(self):
        """Confiança inclui os módulos que efetivamente serão executados."""
        return hashlib.sha256((json.dumps(self.project.to_dict(),sort_keys=True)+repr(source_signature(self.source.text))).encode()).hexdigest()

    def watch_source(self):
        """Observa todos os arquivos próprios, sem carregá-los automaticamente."""
        if not hasattr(self,'source_watcher'):return
        old=self.source_watcher.files()
        paths=[str(b.path) for b in [self.source,*self.source.modules.values()] if b.path and b.path.exists()]
        if set(old)==set(paths):return
        if old:self.source_watcher.removePaths(old)
        if paths:self.source_watcher.addPaths(paths)

    def source_changed_externally(self,path):
        """Sinaliza conflito no arquivo afetado; os buffers continuam preservados."""
        for buffer in [self.source,*self.source.modules.values()]:
            if buffer.path and str(buffer.path)==path:
                try:changed=buffer.path.is_symlink() or (buffer.path.read_bytes() if buffer.path.exists() else None)!=buffer.original
                except OSError:changed=True
                if changed:self.external_change_row.show();self.statusBar().showMessage('Python alterado fora do Makebench: '+path,15000)
        self.watch_source()

    def reload_source(self):
        """Recarregamento explícito conserva avisos de erro e atualiza abas dos módulos."""
        if self.source.dirty and QMessageBox.question(self,'Recarregar arquivos Python?','Descartar as edições Python não salvas e reler os arquivos do projeto?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        super().reload_source();self.sync_code_workspace()

    def keep_source(self):
        """Aceita sobrescrita somente por ação explícita, para todos os buffers atuais."""
        try:
            from makebench.core.source import _read,module_path
            for name,buffer in [(ENTRY_FILE,self.source),*self.source.modules.items()]:
                if buffer.path:
                    if name!=ENTRY_FILE:module_path(buffer.path.parents[len(Path(name).parts)-1],name)
                    buffer.original=_read(buffer.path)
        except (OSError,ProjectError) as exc:self._show_error(str(exc));return
        self.external_change_row.hide();self.watch_source();self.refresh_trust_banner()
