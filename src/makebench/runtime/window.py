"""Janela para testar aplicativos, coletar entradas e acompanhar tarefas."""
from __future__ import annotations
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QMainWindow,QMessageBox,
    QPlainTextEdit,QPushButton,QScrollArea,QSplitter,QVBoxLayout,QWidget,
)
from makebench.core.codegen import generate
from makebench.core.project import Project, ProjectError
from .session import RuntimeSession
from .view import RuntimeView


def append_output(editor, text, color=None):
    """Acrescenta chunks sem inventar quebras de linha e limita o texto retido."""
    bar=editor.verticalScrollBar();position=bar.value();follow=position>=bar.maximum()-2
    cursor=editor.textCursor();cursor.movePosition(QTextCursor.MoveOperation.End)
    style=QTextCharFormat()
    style.setForeground(QColor(color) if color else editor.palette().text().color())
    cursor.insertText(text,style)
    if editor.document().characterCount()>500_000:
        trim=QTextCursor(editor.document());trim.setPosition(0);trim.setPosition(editor.document().characterCount()-400_000,QTextCursor.MoveMode.KeepAnchor);trim.removeSelectedText()
    if follow:editor.setTextCursor(cursor);editor.ensureCursorVisible()
    else:bar.setValue(position)


from .navigation import RuntimeNavigation


class RuntimeWindow(RuntimeNavigation, QMainWindow):
    """Supervisiona uma execução explícita e nunca altera o projeto do editor."""
    locate_requested=Signal(dict)
    shutdown_finished=Signal()
    status_changed=Signal(str)

    def __init__(self, project, source, read_asset, root=None, source_filename=None, parent=None, supervision=True):
        """Valida snapshot; construção não importa nem executa funções do usuário."""
        super().__init__(parent,Qt.WindowType.Window)
        project=Project.from_dict(project.to_dict())
        generated=generate(project,source)
        if generated.diagnostics:raise ProjectError('\n'.join(generated.diagnostics))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.supervision=supervision
        self.project=project;self.source=source;self.dialogs=set();self.last_error={};self.close_pending=False
        self.temporary=tempfile.TemporaryDirectory(prefix='makebench-run-') if root is None else None
        root=Path(root or self.temporary.name).resolve()
        self.session=RuntimeSession(project,source,root,source_filename or str(root/'project.actions.py'),self)
        self.root_window_id=project.entry_window or project.root.id
        initial=project.find(self.root_window_id)
        self.setWindowTitle(('[Teste] ' if supervision else '')+initial.properties.get('title',project.name))
        width=initial.properties.get('width',640);height=initial.properties.get('height',480)+(220 if supervision else 0)
        icon_path=initial.properties.get('icon') or project.application.get('icon')
        if icon_path:
            from PySide6.QtGui import QIcon,QPixmap
            try:
                pixmap=QPixmap();pixmap.loadFromData(read_asset(icon_path));self.setWindowIcon(QIcon(pixmap))
            except (OSError,ProjectError):pass
        self.resize(width,height)
        if not initial.properties.get('resizable',True):self.setFixedSize(width,height)
        central=QWidget();layout=QVBoxLayout(central)
        controls=QHBoxLayout();self.state=QLabel('Pronto para iniciar.')
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.state,1)
        self.stop_button=QPushButton('Parar execução');self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button);layout.addLayout(controls)
        split=QSplitter(Qt.Orientation.Vertical)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        self.view=RuntimeView(project,read_asset,window_root=initial);scroll.setWidget(self.view);split.addWidget(scroll)
        output_box=QWidget();output_layout=QVBoxLayout(output_box);output_layout.setContentsMargins(0,0,0,0)
        output_layout.addWidget(QLabel('Supervisão do Makebench · não faz parte do seu aplicativo'))
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumBlockCount(3000)
        output_layout.addWidget(self.output)
        error_row=QHBoxLayout();self.error_label=QLabel();self.error_label.setTextFormat(Qt.TextFormat.PlainText);self.error_label.setWordWrap(True)
        error_row.addWidget(self.error_label,1)
        self.locate=QPushButton('Ir ao erro');self.locate.setEnabled(False);self.locate.clicked.connect(lambda:self.locate_requested.emit(self.last_error))
        error_row.addWidget(self.locate);output_layout.addLayout(error_row)
        self.details_button=QPushButton('Detalhes do erro')
        self.details_button.setCheckable(True);self.details_button.setEnabled(False)
        output_layout.addWidget(self.details_button,0,Qt.AlignmentFlag.AlignLeft)
        self.error_details=QPlainTextEdit();self.error_details.setReadOnly(True)
        self.error_details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.error_details.setMaximumHeight(180);self.error_details.hide()
        self.details_button.toggled.connect(self.error_details.setVisible)
        output_layout.addWidget(self.error_details)
        split.addWidget(output_box);split.setSizes([480,220]);layout.addWidget(split)
        self.setCentralWidget(central)
        self.supervision_box=output_box
        if not supervision:
            output_box.hide();self.stop_button.hide();self.state.hide()
        self.install_navigation(read_asset)
        self.view.clicked.connect(self._clicked)
        self.session.ready.connect(self._ready)
        self.session.request.connect(self._request)
        self.session.output.connect(self._output)
        self.session.error.connect(self._error)
        self.session.event_done.connect(self._done)
        self.session.busy_changed.connect(self._busy)
        self.session.admin_changed.connect(self._admin_changed)
        self.session.stopped.connect(self._stopped)

    def set_status(self,text):
        """Atualiza supervisão local e editor sem acoplar o runtime à bancada."""
        self.state.setText(text);self.status_changed.emit(text)

    def start(self):
        """Executa fonte própria e prepara os eventos somente por solicitação explícita."""
        self.set_status('Iniciando aplicativo…');self.session.start()

    def _ready(self):
        """Dispara início da janela uma vez, após carregar as funções no worker."""
        self.set_status('Aplicativo em execução.')
        self.queue_event(self.root_window_id,'start')

    def _clicked(self, identifier):
        """Dispara fluxo do botão; tarefas concorrentes não são enfileiradas."""
        if not self.session.busy:self.queue_event(identifier,'click')

    def _busy(self, busy):
        """Atualiza bloqueio de cliques enquanto o editor continua responsivo."""
        for view in self.views.values():view.set_busy(busy)
        if busy and self.session.active:
            for node in self.project.walk():
                if node.kind.value=='progress':
                    _,progress=self.widget_for(node.id)
                    if progress:progress.setValue(0)

            self.set_status('Executando fluxo…')
            self.last_error={};self.error_label.clear();self.locate.setEnabled(False)
            self.details_button.setChecked(False);self.details_button.setEnabled(False);self.error_details.clear()

    def _output(self, channel, text):
        """Mostra stdout/stderr ao vivo na janela e nos painéis do aplicativo."""
        from makebench.ui.theme import PALETTES
        tokens=PALETTES['dark' if self.palette().window().color().lightness()<128 else 'light']
        color=tokens['warning'] if channel=='stderr' else tokens['error'] if channel=='error' else tokens['muted'] if channel=='status' else None
        append_output(self.output,text,color)
        if not self.supervision and self.parent() is None and channel!='status':
            import sys
            stream=sys.stderr if channel in {'stderr','error'} else sys.stdout
            if stream:
                try:stream.write(text);stream.flush()
                except (OSError,ValueError):pass

    def _error(self, error):
        """Guarda origem e detalhes sem fechar o editor nem repetir o fluxo."""
        self.last_error=error
        message=error['message'].removeprefix('TaskError: ')
        self.error_label.setText(message)
        self.locate.setEnabled(bool(error.get('block') or error.get('source_line')))
        self.error_details.setPlainText(error.get('traceback',''))
        self.details_button.setEnabled(bool(error.get('traceback')))
        self._output('error','[Erro] '+message+'\n')
        self.set_status('Erro na execução. Consulte a saída.')
        if not self.supervision and self.parent() is None:
            dialog=QMessageBox(self);dialog.setWindowTitle('Não foi possível concluir a operação')
            dialog.setTextFormat(Qt.TextFormat.PlainText);dialog.setText(message)
            dialog.setDetailedText(error.get('traceback',''));dialog.setStandardButtons(QMessageBox.StandardButton.Close)
            from makebench.ui.dialogs import translate_buttons
            translate_buttons(dialog);dialog.show();self._error_dialog=dialog

    def _done(self, message):
        """Distingue sucesso, cancelamento e falha, usando resultado real do fluxo."""
        labels={'success':'Fluxo concluído.','cancelled':'Fluxo cancelado.','error':'O fluxo terminou com erro.'}
        self.set_status(labels[message['outcome']])
        self._output('status',labels[message['outcome']]+'\n')
        if message['outcome']!='success':self._queued_flows.clear()
        QTimer.singleShot(0,self.dispatch_next)

    def _admin_changed(self, active):
        """Mantém a tarefa elevada supervisionada sem oferecer interrupção forçada."""
        self.stop_button.setEnabled(not active)
        if active:self.set_status('Tarefa administrativa: conclua ou cancele a autenticação no diálogo do sistema. Aguarde o término para fechar.')

    def _request(self, request):
        """Atende somente operações declaradas no contrato de contexto."""
        identifier=request['id'];method=request['method']
        try:
            component=request.get('component');view,widget=self.widget_for(component)
            if method=='read':
                if widget is None:raise ValueError('O componente não existe.')
                attribute=request['attribute']
                if attribute=='text':value=widget.toPlainText() if isinstance(widget,QPlainTextEdit) else widget.text()
                elif attribute=='checked':value=widget.isChecked()
                elif attribute=='value':value=widget.value()
                else:raise ValueError('Propriedade desconhecida.')
                self.session.reply(identifier,value)
            elif method=='set_text':
                if widget is None:raise ValueError('O componente não existe.')
                widget.setPlainText(request['value']) if isinstance(widget,QPlainTextEdit) else widget.setText(request['value'])
                self.session.reply(identifier)
            elif method=='set_enabled':
                if widget is None:raise ValueError('O componente não existe.')
                view.set_enabled(component,request['value']);self.session.reply(identifier)
            elif method=='set_value':
                if widget is None or not 0<=request['value']<=100:raise ValueError('Progresso deve estar entre 0 e 100.')
                widget.setValue(request['value']);self.session.reply(identifier)
            elif method=='show_page':
                if view is None:raise ValueError('A janela desta página não está aberta.')
                view.show_page(component);self.session.reply(identifier)
            elif method=='go_state':self.apply_state(self.current_window,request['state']);self.session.reply(identifier)
            elif method=='open_window':
                reset=self.open_app_window(request['window'],request.get('close_current',False));self.session.reply(identifier,{'reset':reset})
            elif method=='close_window':self.close_app_window(self.current_window);self.session.reply(identifier)
            elif method in {'message','confirm','ask'}:self._dialog(request)
            else:raise ValueError('Operação de contexto desconhecida.')
        except (ValueError,TypeError,AttributeError,KeyError) as exc:
            self.session.reply(identifier,ok=False,error=str(exc))

    def _dialog(self, request):
        """Abre entrada declarada sem bloquear o ciclo de eventos do editor."""
        method=request['method'];prompt=str(request.get('prompt',''))
        kind=request.get('kind')
        parent=self.app_windows.get(self.current_window,self)
        if method in {'message','confirm'}:
            dialog=QMessageBox(parent);dialog.setWindowTitle('Confirmação' if method=='confirm' else self.project.name)
            dialog.setTextFormat(Qt.TextFormat.PlainText);dialog.setText(prompt)
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No if method=='confirm' else QMessageBox.StandardButton.Ok)
            if method=='confirm':dialog.setDefaultButton(QMessageBox.StandardButton.No)
        elif kind in {'text','choice'}:
            dialog=QInputDialog(parent);dialog.setWindowTitle(self.project.name);dialog.setLabelText(prompt)
            dialog.setOkButtonText('Continuar');dialog.setCancelButtonText('Cancelar')
            if kind=='choice':
                options=request.get('options',[])
                if not isinstance(options,list) or not options or any(not isinstance(v,str) for v in options):raise ValueError('Forneça uma lista não vazia de opções de texto.')
                dialog.setComboBoxItems(options);dialog.setComboBoxEditable(False)
        elif kind in {'file','directory'}:
            dialog=QFileDialog(parent,prompt,str(self.session.root))
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog,True)
            dialog.setFileMode(QFileDialog.FileMode.Directory if kind=='directory' else QFileDialog.FileMode.ExistingFile)
        else:raise ValueError('Tipo de diálogo desconhecido.')
        self.set_status('Aguardando resposta…')
        from makebench.ui.dialogs import translate_buttons
        translate_buttons(dialog)
        self.dialogs.add(dialog)
        def finished(result):
            """Devolve entrada ou cancelamento explícito antes de liberar o diálogo."""
            self.dialogs.discard(dialog)
            self._output("status","Pergunta respondida ou cancelada.\n")
            value=None
            if method=='confirm':accepted=result==QMessageBox.StandardButton.Yes;value=accepted
            elif method=='message':accepted=result==QMessageBox.StandardButton.Ok
            else:
                accepted=bool(result)
                if accepted:value=dialog.selectedFiles()[0] if isinstance(dialog,QFileDialog) else dialog.textValue()
            self.session.reply(request['id'],value,ok=accepted,cancelled=not accepted,error='Operação cancelada pelo usuário.' if not accepted else '')
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.setWindowModality(Qt.WindowModality.WindowModal);dialog.show()

    def stop(self):
        """Interrompe instância e tarefas comuns sem tocar em tarefa administrativa."""
        if not self.session.stop():
            self.set_status('Aguarde a tarefa administrativa terminar para parar.');return False
        self.set_status('Encerrando execução…');self.stop_button.setEnabled(False)
        for dialog in list(self.dialogs):dialog.reject()
        return True

    def _stopped(self):
        """Permite fechar somente depois que os processos comuns foram encerrados."""
        for window_id,window in self.app_windows.items():
            if window is not self:window.close()
        for view in self.views.values():view.set_busy(True)
        self.set_status('Execução encerrada.')
        self.stop_button.setEnabled(False);self.shutdown_finished.emit()
        if self.close_pending:self.close()

    def closeEvent(self, event):
        """Não abandona processos nem fecha durante uma tarefa elevada ativa."""
        if not self.session.closed:
            if len(self.open_windows)>1 and self.root_window_id in self.open_windows:
                self.close_app_window(self.root_window_id);event.ignore();return
            if self.stop():self.close_pending=True
            event.ignore();return
        if self.temporary:self.temporary.cleanup()
        event.accept()
