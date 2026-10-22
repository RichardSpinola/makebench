"""Painel nativo de eventos com Blockly offline e ponte limitada a dados."""
from __future__ import annotations

import json
import ast
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot, QUrl, QEventLoop, QTimer, Qt
from PySide6.QtGui import QKeySequence, QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QDialog, QDialogButtonBox, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

from makebench.core.codegen import generate
from makebench.core.logic import editable, function_names
from makebench.core.project import ComponentKind
from .code import CodeEditor


class LogicBridge(QObject):
    """Transporta JSON; não expõe arquivos, shell, importação ou execução ao HTML."""
    documentChanged = Signal(str)
    update_received = Signal(str)
    block_selected = Signal(str, str)
    became_ready = Signal()
    failed = Signal(str)
    pending_received = Signal(str)
    command_received = Signal(str)

    @Slot()
    def ready(self):
        """Informa que Blockly e o canal local terminaram de carregar."""
        self.became_ready.emit()

    @Slot(str)
    def changed(self, payload):
        """Entrega dados de blocos ao validador nativo."""
        self.update_received.emit(payload)

    @Slot(str, str)
    def selected(self, flow, block):
        """Relaciona a seleção de um bloco à origem no código gerado."""
        self.block_selected.emit(flow, block)

    @Slot(str)
    def pending(self, token):
        """Sinaliza gesto pendente antes do debounce de serialização."""
        self.pending_received.emit(token)

    @Slot(str)
    def command(self, name):
        """Encaminha apenas salvar/desfazer/refazer originados por teclado."""
        if name in {'save', 'undo', 'redo', 'find_block', 'python', 'function'}:
            # Sair do callback WebChannel antes de avaliar JS durante flush.
            QTimer.singleShot(0,lambda:self.command_received.emit(name))

    @Slot(str)
    def problem(self, message):
        """Apresenta erro de carga sem interpretar mensagens como instruções."""
        self.failed.emit(message)


class LogicPanel(QWidget):
    """Seleciona eventos, mantém a sessão Blockly e mostra Python correspondente."""
    add_requested = Signal(str)
    remove_requested = Signal(str)
    rename_requested = Signal(str, str)
    flow_changed = Signal(dict)
    error = Signal(str)
    save_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()
    pending_changed = Signal()
    script_requested = Signal(dict)
    filter_requested = Signal(str,object)
    full_code_requested = Signal(int)
    search_requested = Signal()
    function_requested = Signal(str)
    duplicate_requested = Signal(str)

    def __init__(self, project_getter, source_getter, parent=None):
        """Cria controles nativos; WebEngine só inicia ao entrar na aba Lógica."""
        super().__init__(parent)
        self.get_project, self.get_source = project_getter, source_getter
        self.flow_id = None
        self.before_switch=lambda:True
        self._target_component=None
        self.view = None
        self.ready = False
        self.pending = False
        self._had_ready = False
        self.token = ''
        self._payload = None
        self._flushing = False
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Quando'))
        self.events = QComboBox()
        self.events.setMinimumWidth(210)
        self.events.currentIndexChanged.connect(self._switch_flow)
        row.addWidget(self.events, 1)
        self.name = QLineEdit()
        self.name.setPlaceholderText('Nome do fluxo')
        self.name.editingFinished.connect(self._rename)
        self.name.hide()
        self.state_filter=QComboBox();self.state_filter.setAccessibleName('Filtro de estado do fluxo')
        self.state_filter.currentIndexChanged.connect(self._change_filter)
        row.addWidget(self.state_filter)
        self.remove = QPushButton('Remover fluxo')
        self.remove.clicked.connect(lambda: self.remove_requested.emit(self.flow_id) if self.flow_id else None)
        row.addWidget(self.remove)
        duplicate=QPushButton('Duplicar fluxo…');duplicate.clicked.connect(lambda:self.duplicate_requested.emit(self.flow_id) if self.flow_id else None);row.addWidget(duplicate)
        layout.addLayout(row)
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel('Novo vínculo'))
        self.targets = QComboBox()
        add_row.addWidget(self.targets, 1)
        add = QPushButton('Conectar evento')
        add.clicked.connect(lambda: self.add_requested.emit(self.targets.currentData()) if self.targets.currentData() else None)
        add_row.addWidget(add)
        layout.addLayout(add_row)
        hint = QLabel('Encaixe os blocos em “fazer”. Botão direito adiciona comentários. Selecione um bloco para localizar sua linha Python.')
        hint.setWordWrap(True)
        hint.hide()
        self.selected_block=''
        self.edit_text=QPushButton('Editar texto ou script…')
        self.edit_text.setToolTip('Selecione um bloco de texto ou de execução Bash para editar várias linhas.')
        self.edit_text.setEnabled(False)
        self.edit_text.clicked.connect(self._edit_text)
        layout.addWidget(self.edit_text,0,Qt.AlignmentFlag.AlignLeft)
        self.splitter = QSplitter()
        self.placeholder = QLabel('O editor de blocos será carregado ao abrir esta aba.')
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splitter.addWidget(self.placeholder)
        code_box = QWidget()
        code_layout = QVBoxLayout(code_box)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.addWidget(QLabel('Python deste fluxo · somente leitura'))
        complete=QPushButton('Ver arquivo completo');complete.clicked.connect(lambda:self.full_code_requested.emit(self.code_start+self.code.textCursor().blockNumber()));code_layout.addWidget(complete)
        self.code_start=1;self._selecting_code=False
        self.code = CodeEditor(True)
        wrap=QCheckBox('Quebrar linhas');wrap.toggled.connect(lambda enabled:self.code.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap));code_layout.addWidget(wrap)
        code_layout.addWidget(self.code)
        self.code.cursorPositionChanged.connect(self._select_line)
        self.splitter.addWidget(code_box)
        self.splitter.setSizes([850, 380])
        layout.addWidget(self.splitter, 1)
        self.diagnostics = QLabel()
        self.diagnostics.setWordWrap(True)
        self.diagnostics.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.diagnostics)
        self.sync()

    def ensure_loaded(self):
        """Abre exclusivamente recursos locais, com perfil temporário sem rede."""
        if self.view is not None:
            return
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebChannel import QWebChannel
        root = Path(__file__).resolve().parent.parent / 'web'

        class LocalRequests(QWebEngineUrlRequestInterceptor):
            """Bloqueia rede e arquivos fora dos recursos incorporados."""
            def interceptRequest(self, info):
                """Permite apenas o diretório web e o script interno do Qt."""
                url = info.requestUrl()
                allowed = url.toString() == 'qrc:///qtwebchannel/qwebchannel.js'
                if url.scheme() == 'file':
                    allowed = Path(url.toLocalFile()).resolve().is_relative_to(root)
                info.block(not allowed and url.scheme() != 'data')

        class LocalPage(QWebEnginePage):
            """Recusa navegação para fora da entrada HTML do editor."""
            def acceptNavigationRequest(self, url, navigation_type, main_frame):
                """Só a entrada incorporada pode ocupar a página principal."""
                return url == QUrl.fromLocalFile(str(root / 'index.html'))

            def javaScriptConsoleMessage(page_self, level, message, line, source):
                """Encaminha erros de inicialização ao painel nativo."""
                if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    self.diagnostics.setText(f'Blockly: {message} (linha {line})')

        class LocalView(QWebEngineView):
            """Encaminha atalhos de arquivo/histórico para o documento nativo."""
            def keyPressEvent(view_self, event):
                """Evita um segundo histórico de desfazer dentro do navegador."""
                if event.matches(QKeySequence.StandardKey.Save):
                    self.save_requested.emit()
                elif event.matches(QKeySequence.StandardKey.Undo):
                    self.undo_requested.emit()
                elif event.matches(QKeySequence.StandardKey.Redo) or event.keyCombination().toCombined() == QKeySequence('Ctrl+Shift+Z')[0].toCombined():
                    self.redo_requested.emit()
                else:
                    super().keyPressEvent(event)
                    return
                event.accept()

        self.profile = QWebEngineProfile()
        self.interceptor = LocalRequests(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.view = LocalView(self)
        self.page = LocalPage(self.profile, self.view)
        self.view.setPage(self.page)
        from .theme import manager
        self.page.setBackgroundColor(QColor(manager().tokens["canvas"]))
        # Ordem de destruição: a vista/página morre antes do perfil Chromium.
        self.profile.setParent(self)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.channel = QWebChannel(self.page)
        self.bridge = LogicBridge(self.channel)
        self.channel.registerObject('bridge', self.bridge)
        self.page.setWebChannel(self.channel)
        self.bridge.update_received.connect(self._receive)
        self.bridge.block_selected.connect(self._select_block)
        self.bridge.became_ready.connect(self._became_ready)
        self.bridge.failed.connect(self.error)
        self.bridge.pending_received.connect(self._mark_pending)
        self.bridge.command_received.connect(self._command)
        self.splitter.replaceWidget(0, self.view)
        self.placeholder.deleteLater()
        self.view.load(QUrl.fromLocalFile(str(root / 'index.html')))
        self.view.loadFinished.connect(self._load_finished)
        self.page.renderProcessTerminated.connect(lambda *_: self._load_finished(False))

    def _load_finished(self, ok):
        """Explica falha de recurso sem fingir que há editor de blocos disponível."""
        if not ok:
            self.ready = False
            self.diagnostics.setText('Não foi possível carregar Blockly. Reabra o Makebench; a interface e os arquivos salvos continuam disponíveis.')

    def _became_ready(self):
        """Envia o contexto inicial assim que o canal está pronto."""
        self.ready = True
        self._had_ready = True
        self._payload = None
        self.sync()
        from .theme import manager
        manager().changed.connect(self.apply_theme)
        self.apply_theme(manager().tokens)

    def _switch_flow(self):
        """Confirma o fluxo anterior antes de trocar a área de blocos."""
        requested = self.events.currentData()
        if requested == self.flow_id:
            return
        if not self.before_switch() or not self.flush():
            self.events.blockSignals(True)
            self.events.setCurrentIndex(self.events.findData(self.flow_id))
            self.events.blockSignals(False)
            return
        self._target_component=None
        self.flow_id = requested
        self.sync()

    def _rename(self):
        """Confirma nome do fluxo sem alterar o evento ao qual está ligado."""
        if self.flow_id and self.flush():
            self.rename_requested.emit(self.flow_id, self.name.text())

    def sync(self, flow_id=None):
        """Atualiza eventos/componentes sem recarregar a página web inteira."""
        project = self.get_project()
        if flow_id is not None and flow_id!=self.flow_id and not self.before_switch():return
        if flow_id is not None:
            self.flow_id = flow_id
        flows = project.workflows if editable(project) else []
        if self.flow_id not in {f['id'] for f in flows}:
            candidates=[f for f in flows if not self._target_component or f['event']['component']==self._target_component]
            self.flow_id=candidates[0]['id'] if candidates else None
        flow = next((f for f in flows if f['id'] == self.flow_id), None)
        self.events.blockSignals(True)
        self.events.clear()
        for item in flows:
            self.events.addItem(item['name'], item['id'])
        self.events.setCurrentIndex(self.events.findData(self.flow_id))
        self.events.blockSignals(False)
        self.name.setText(flow['name'] if flow else '')
        self.state_filter.blockSignals(True);self.state_filter.clear();self.state_filter.addItem('em qualquer estado',[])
        owner=project.window_of(flow['event']['component']) if flow else project.root
        self.state_filter.addItem('só no Padrão',['@default'])
        for state in project.states.get(owner.id,[]):self.state_filter.addItem('só em '+state['name'],[state['id']])
        self.state_filter.addItem('Escolher vários estados…','@choose')
        filters=flow.get('states',[]) if flow else []
        selected=self.state_filter.findData(filters)
        if selected<0:self.state_filter.addItem('filtro de vários estados',filters);selected=self.state_filter.count()-1
        self.state_filter.setCurrentIndex(selected);self.state_filter.setEnabled(flow is not None)
        self.state_filter.blockSignals(False)
        self.name.setEnabled(flow is not None)
        self.remove.setEnabled(flow is not None)
        target = self._target_component or self.targets.currentData()
        self.targets.clear()
        for node in project.walk():
            if node.kind in {ComponentKind.WINDOW, ComponentKind.BUTTON}:
                self.targets.addItem(('Ao iniciar: ' if node.kind == ComponentKind.WINDOW else 'Ao clicar: ') + node.display_name, node.id)
        if self.targets.findData(target) >= 0:
            self.targets.setCurrentIndex(self.targets.findData(target))
        components = [{'id':n.id,'kind':n.kind.value,'name':project.window_of(n.id).properties.get('title','Janela')+' › '+(n.properties.get('code_name') or n.display_name)} for n in project.walk()]
        try:
            function_info=[{'name':n.name,'signature':n.name+'('+', '.join(a.arg for a in n.args.args)+')','description':(ast.get_docstring(n) or '').split('\n')[0]} for n in ast.parse(self.get_source()).body if isinstance(n,ast.FunctionDef)]
        except (SyntaxError,ValueError):function_info=[]
        variables=[dict(item) for item in project.variables if item.get('scope','project')=='project' or item.get('window')==owner.id]
        def collect(value):
            """Reúne variáveis declaradas e implícitas sem avaliar expressões."""
            if isinstance(value,dict):
                if value.get('op') in {'assign','variable','ask'} and value.get('name'):
                    candidate={'name':value['name'],'scope':value.get('scope','project')}
                    if not any(item['name']==candidate['name'] and item.get('scope','project')==candidate['scope'] for item in variables):variables.append(candidate)
                for child in value.values():collect(child)
            elif isinstance(value,list):
                for child in value:collect(child)
        if flow:collect(flow.get('body'))
        payload = {'variables':variables,'function_info':function_info,'windows':[{'id':r.id,'name':r.properties.get('title','Janela')} for r in project.roots], 'states':[{'id':'@default','name':'Padrão'}, *[{'id':s['id'],'name':s['name']} for s in project.states.get(owner.id,[])]], 'project':project.id, 'flow':flow, 'components':components, 'functions':function_names(self.get_source())[0]}
        serialized = json.dumps(payload, ensure_ascii=False)
        if self.ready and serialized != self._payload:
            self._payload = serialized
            self.token = uuid4().hex
            self.pending = False
            self.pending_changed.emit()
            payload['token'] = self.token
            self.bridge.documentChanged.emit(json.dumps(payload, ensure_ascii=False))
        self.update_code()

    def update_code(self):
        """Regenera Python visível a partir do modelo, sem executar funções."""
        self.generated = generate(self.get_project(), self.get_source())
        lines=self.generated.text.splitlines()
        flow_index=next((index for index,f in enumerate(self.get_project().editable_flows,1) if f['id']==self.flow_id),None)
        start=next((i for i,line in enumerate(lines) if line.startswith(f'def on_event_{flow_index}(')),None)
        if start is not None:
            end=next((i for i in range(start+1,len(lines)) if lines[i].startswith('# Evento:')),len(lines))
            while end>start and (not lines[end-1].strip() or lines[end-1].startswith('# ')):end-=1
            text='\n'.join(lines[start:end])+'\n';self.code_start=start+1
        else:text='';self.code_start=1
        if self.code.toPlainText()!=text:self.code.setPlainText(text)
        self.diagnostics.setText('\n'.join(self.generated.diagnostics) or 'Blocos salvos. Use F5 para testar o aplicativo e acompanhar a saída.')

    def _select_block(self, flow, block):
        """Mostra a linha gerada correspondente à seleção de Blockly."""
        self.selected_block=block
        self.edit_text.setEnabled(bool(block))
        line = self.generated.lines.get((flow, block))
        if line:
            self._selecting_code=True
            try:self.code.show_line(line-self.code_start+1)
            finally:self._selecting_code=False

    def _edit_text(self):
        """Edita texto multilinha sem executar scripts nem concatenar argumentos."""
        if not self.ready or not self.selected_block:
            return
        self.page.runJavaScript("JSON.stringify(window.makebench.textValue("+json.dumps(self.selected_block)+"))", self._text_dialog)

    def _text_dialog(self, result):
        """Abre um editor nativo para um literal textual do workspace atual."""
        if not result or result=='null':
            self.diagnostics.setText('Selecione um bloco de texto ou um bloco “executar Bash” com texto conectado.')
            return
        self.script_requested.emit(json.loads(result))

    def focus_block(self, flow, block, attempt=0):
        """Revela origem de erro assim que o workspace solicitado está disponível."""
        self._select_block(flow, block)
        if attempt >= 30:
            return
        if not self.ready:
            QTimer.singleShot(100, lambda: self.focus_block(flow, block, attempt + 1))
            return
        code = "(() => {const ws=window.makebench?.workspace;const b=ws?.getBlockById(" + json.dumps(block) + ");if(!b)return false;b.select();ws.centerOnBlock(b.id);return true;})()"
        self.page.runJavaScript(code, lambda found: QTimer.singleShot(50, lambda: self.focus_block(flow, block, attempt + 1)) if not found else None)

    def _mark_pending(self, token):
        """Mantém desfazer e aviso de alterações disponíveis antes do debounce."""
        if token == self.token:
            self.pending = True
            self.pending_changed.emit()

    def _command(self, name):
        """Entrega atalhos capturados no DOM ao documento nativo."""
        if name=='find_block':self.search_requested.emit()
        elif name=='python':self.full_code_requested.emit(self.code_start+self.code.textCursor().blockNumber())
        elif name=='function':
            if self.ready:self.page.runJavaScript('window.makebench.selectedFunction()',lambda value:self.function_requested.emit(value) if value else None)
        else:{'save':self.save_requested,'undo':self.undo_requested,'redo':self.redo_requested}[name].emit()

    def _receive(self, payload):
        """Ignora mensagens de sessão antiga e entrega atualização validável."""
        try:
            data = json.loads(payload)
            if not isinstance(data, dict) or data.get('token') != self.token or data.get('flow') != self.flow_id:
                return
            self.pending = False
            self.flow_changed.emit(data)
            self.pending_changed.emit()
        except (ValueError, TypeError) as exc:
            self.error.emit(f'Dados de blocos inválidos: {exc}')

    def flush(self):
        """Obtém mudanças ainda na web antes de salvar, trocar ou desfazer.

        O retorno JavaScript evita depender do debounce do canal. Em falha não
        autoriza uma operação que poderia perder alterações não confirmadas.
        """
        if self.view is None or self._flushing:
            return True
        if not self.ready:
            if self._had_ready:
                self.error.emit('O processo Blockly foi encerrado. Reabra o Makebench para continuar; o último arquivo salvo foi preservado.')
                return False
            return True
        self._flushing = True
        loop = QEventLoop()
        results = []
        def finished(value):
            """Finaliza a espera curta quando JavaScript devolve o retrato."""
            results.append(value)
            loop.quit()
        self.page.runJavaScript('JSON.stringify(window.makebench.flush(true))', finished)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(2500)
        loop.exec()
        timer.stop()
        self._flushing = False
        if not results:
            self.error.emit('Blockly não respondeu. Aguarde e tente salvar novamente antes de fechar.')
            return False
        if results[0] and results[0] != 'null':
            self._receive(results[0])
        return True

    def _change_filter(self):
        """Confirma o workspace antes de alterar o filtro declarativo do evento."""
        if not self.flow_id or not self.flush():return
        if self.state_filter.currentData()=='@choose':
            from PySide6.QtWidgets import QListWidget,QListWidgetItem
            flow=next(f for f in self.get_project().workflows if f['id']==self.flow_id)
            owner=self.get_project().window_of(flow['event']['component'])
            dialog=QDialog(self);dialog.setWindowTitle('Executar neste(s) estado(s)');layout=QVBoxLayout(dialog)
            choices=QListWidget();choices.setSelectionMode(choices.SelectionMode.MultiSelection)
            for state in [{'id':'@default','name':'Padrão'},*self.get_project().states.get(owner.id,[])]:
                item=QListWidgetItem(state['name']);item.setData(Qt.ItemDataRole.UserRole,state['id']);choices.addItem(item);item.setSelected(state['id'] in flow.get('states',[]))
            layout.addWidget(choices);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
            if dialog.exec()==QDialog.DialogCode.Accepted:self.filter_requested.emit(self.flow_id,[item.data(Qt.ItemDataRole.UserRole) for item in choices.selectedItems()])
            else:self.sync()
        else:self.filter_requested.emit(self.flow_id,self.state_filter.currentData())

    def _select_line(self):
        """Relaciona a linha visível ao bloco, sem recarregar ou alterar a lógica."""
        if not self.ready or self._selecting_code:return
        line=self.code_start+self.code.textCursor().blockNumber()
        match=next(((flow,block) for (flow,block),number in self.generated.lines.items() if flow==self.flow_id and number==line),None)
        if match and match[1]!=self.selected_block:self.focus_block(*match)

    def apply_theme(self,tokens):
        """Entrega apenas tokens visuais à página local pelo canal JavaScript."""
        if self.ready:self.page.runJavaScript('window.makebench.applyTheme('+json.dumps(tokens)+')')

    def select_component_event(self,component,state):
        """Seleciona o comportamento da origem atual ou mostra um estado vazio honesto."""
        if not self.before_switch() or not self.flush():return
        self._target_component=component
        flows=[f for f in self.get_project().editable_flows if f['event']['component']==component]
        flow=next((f for f in flows if state in f.get('states',[])),None) or next((f for f in flows if not f.get('states')),None)
        self.flow_id=flow['id'] if flow else None;self.sync()
