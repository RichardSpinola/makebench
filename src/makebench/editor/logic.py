"""Painel nativo de eventos com Blockly offline e ponte limitada a dados."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot, QUrl, QEventLoop, QTimer, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter,
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
        if name in {'save', 'undo', 'redo'}:
            self.command_received.emit(name)

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

    def __init__(self, project_getter, source_getter, parent=None):
        """Cria controles nativos; WebEngine só inicia ao entrar na aba Lógica."""
        super().__init__(parent)
        self.get_project, self.get_source = project_getter, source_getter
        self.flow_id = None
        self.view = None
        self.ready = False
        self.pending = False
        self._had_ready = False
        self.token = ''
        self._payload = None
        self._flushing = False
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Evento'))
        self.events = QComboBox()
        self.events.setMinimumWidth(210)
        self.events.currentIndexChanged.connect(self._switch_flow)
        row.addWidget(self.events, 1)
        self.name = QLineEdit()
        self.name.setPlaceholderText('Nome do fluxo')
        self.name.editingFinished.connect(self._rename)
        row.addWidget(QLabel('Nome'))
        row.addWidget(self.name, 1)
        self.remove = QPushButton('Remover fluxo')
        self.remove.clicked.connect(lambda: self.remove_requested.emit(self.flow_id) if self.flow_id else None)
        row.addWidget(self.remove)
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
        layout.addWidget(hint)
        self.splitter = QSplitter()
        self.placeholder = QLabel('O editor de blocos será carregado ao abrir esta aba.')
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splitter.addWidget(self.placeholder)
        code_box = QWidget()
        code_layout = QVBoxLayout(code_box)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.addWidget(QLabel('Python gerado · somente leitura'))
        self.code = CodeEditor(True)
        code_layout.addWidget(self.code)
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

    def _switch_flow(self):
        """Confirma o fluxo anterior antes de trocar a área de blocos."""
        requested = self.events.currentData()
        if requested == self.flow_id:
            return
        if not self.flush():
            self.events.blockSignals(True)
            self.events.setCurrentIndex(self.events.findData(self.flow_id))
            self.events.blockSignals(False)
            return
        self.flow_id = requested
        self.sync()

    def _rename(self):
        """Confirma nome do fluxo sem alterar o evento ao qual está ligado."""
        if self.flow_id and self.flush():
            self.rename_requested.emit(self.flow_id, self.name.text())

    def sync(self, flow_id=None):
        """Atualiza eventos/componentes sem recarregar a página web inteira."""
        project = self.get_project()
        if flow_id is not None:
            self.flow_id = flow_id
        flows = project.workflows if editable(project) else []
        if self.flow_id not in {f['id'] for f in flows}:
            self.flow_id = flows[0]['id'] if flows else None
        flow = next((f for f in flows if f['id'] == self.flow_id), None)
        self.events.blockSignals(True)
        self.events.clear()
        for item in flows:
            self.events.addItem(item['name'], item['id'])
        self.events.setCurrentIndex(self.events.findData(self.flow_id))
        self.events.blockSignals(False)
        self.name.setText(flow['name'] if flow else '')
        self.name.setEnabled(flow is not None)
        self.remove.setEnabled(flow is not None)
        target = self.targets.currentData()
        self.targets.clear()
        for node in project.root.walk():
            if node.kind in {ComponentKind.WINDOW, ComponentKind.BUTTON}:
                self.targets.addItem(('Ao iniciar: ' if node.kind == ComponentKind.WINDOW else 'Ao clicar: ') + node.display_name, node.id)
        if self.targets.findData(target) >= 0:
            self.targets.setCurrentIndex(self.targets.findData(target))
        components = [{'id': n.id, 'kind': n.kind.value, 'name': n.display_name} for n in project.root.walk()]
        payload = {'project':project.id, 'flow':flow, 'components':components, 'functions':function_names(self.get_source())[0]}
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
        if self.code.toPlainText() != self.generated.text:
            self.code.setPlainText(self.generated.text)
        self.diagnostics.setText('\n'.join(self.generated.diagnostics) or 'Blocos salvos como dados. Execução e diálogos serão conectados na etapa M4.')

    def _select_block(self, flow, block):
        """Mostra a linha gerada correspondente à seleção de Blockly."""
        line = self.generated.lines.get((flow, block))
        if line:
            self.code.show_line(line)

    def _mark_pending(self, token):
        """Mantém desfazer e aviso de alterações disponíveis antes do debounce."""
        if token == self.token:
            self.pending = True
            self.pending_changed.emit()

    def _command(self, name):
        """Entrega atalhos capturados no DOM ao documento nativo."""
        {'save': self.save_requested, 'undo': self.undo_requested, 'redo': self.redo_requested}[name].emit()

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
