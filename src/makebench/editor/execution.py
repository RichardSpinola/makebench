"""Supervisão do teste na gaveta do editor, utilizando sinais do runtime real."""
from datetime import datetime
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QComboBox,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QTreeWidget,QTreeWidgetItem,QVBoxLayout,QWidget)
from makebench.runtime.window import append_output
from .theme import manager


class ExecutionMixin:
    """Apresenta logs, tarefas e origem sem executar código no processo do editor."""
    def install_execution(self):
        """Acrescenta filtros e comandos sobre o mesmo log compartilhado."""
        self.log_entries=[];self.task_items={};self.test_started=None
        output=QWidget();layout=QVBoxLayout(output);layout.setContentsMargins(4,4,4,4)
        row=QHBoxLayout();self.output_filter=QComboBox();self.output_filter.addItems(['Tudo','Erros'])
        self.output_filter.currentIndexChanged.connect(self.rebuild_output);row.addWidget(self.output_filter);row.addStretch()
        for label,callback in [('Copiar',lambda:__import__('PySide6.QtWidgets',fromlist=['QApplication']).QApplication.clipboard().setText(self.output_log.toPlainText())),('Limpar',self.clear_output)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row);layout.addWidget(self.output_log)
        self.drawer.removeTab(0);self.drawer.insertTab(0,output,'Saída')
        tasks=QWidget();tl=QVBoxLayout(tasks)
        self.task_tree=QTreeWidget();self.task_tree.setHeaderLabels(['Tarefa','Tipo','Estado','Duração']);tl.addWidget(self.task_tree)
        self.cancel_task_button=QPushButton('Cancelar tarefa comum e encerrar teste');self.cancel_task_button.clicked.connect(self.stop_test);tl.addWidget(self.cancel_task_button)
        self.drawer.addTab(tasks,'Tarefas')
        error=QWidget();er=QVBoxLayout(error);self.run_error_label=QLabel();self.run_error_label.setWordWrap(True);er.addWidget(self.run_error_label)
        locate=QPushButton('Ir à origem');locate.clicked.connect(self.locate_test_error);er.addWidget(locate,0,Qt.AlignmentFlag.AlignLeft)
        details=QPushButton('Detalhes técnicos');details.setCheckable(True);er.addWidget(details,0,Qt.AlignmentFlag.AlignLeft)
        self.run_trace=QPlainTextEdit();self.run_trace.setReadOnly(True);self.run_trace.hide();details.toggled.connect(self.run_trace.setVisible);er.addWidget(self.run_trace)
        self.drawer.addTab(error,'Erro')
        self.clock=QTimer(self);self.clock.setInterval(1000);self.clock.timeout.connect(self.update_test_time);self.clock.start()
        self._runtime_project_fingerprint=None

    def monitor_runtime(self,window):
        """Conecta um processo real antes de seu início explícito."""
        from .settings import preference
        if preference('test/clear'):self.clear_output()
        self.run_number+=1;self.test_started=time.monotonic();self._runtime_project_fingerprint=self.fingerprint()
        self.add_output('status',f'\n──────── Execução {self.run_number} · {datetime.now():%H:%M:%S} ────────\n')
        window.session.output.connect(self.add_output)
        window.session.busy_changed.connect(lambda _:self._update_actions())
        window.session.error.connect(self.show_test_error)
        window.status_changed.connect(self.set_test_status)
        window.session.task_changed.connect(self.update_task)
        window.session.admin_changed.connect(lambda active:self.stop_action.setEnabled(not active))
        window.session.stopped.connect(lambda:self.test_status.setText('Interrompido'))
        self.drawer.show();self.drawer.setCurrentIndex(0)

    def add_output(self,channel,text):
        """Mantém canais separados; stderr é aviso, falha explícita é erro."""
        self.log_entries.append((channel,text))
        if sum(len(t) for _,t in self.log_entries)>500000:self.log_entries=self.log_entries[-1000:]
        if self.output_filter.currentIndex()==0 or channel=='error':
            tokens=manager().tokens;color=tokens['warning'] if channel=='stderr' else tokens['error'] if channel=='error' else tokens['muted'] if channel=='status' else None
            append_output(self.output_log,text,color)

    def rebuild_output(self):
        """Filtra a apresentação, preservando o histórico recebido."""
        entries=list(self.log_entries);self.output_log.clear();self.log_entries=[]
        for channel,text in entries:self.add_output(channel,text)

    def clear_output(self):
        """Limpa somente a observação da execução, sem apagar arquivos ou lógica."""
        self.log_entries=[];self.output_log.clear()

    def update_task(self,data):
        """Mostra duração e resultado de tarefas comuns ou administrativas."""
        key=f"{self.run_number}:{data['id']}";item=self.task_items.get(key)
        if item is None:
            item=QTreeWidgetItem();self.task_tree.addTopLevelItem(item);self.task_items[key]=item
        item.setText(0,data['program']);item.setText(1,'Administrativa' if data['admin'] else 'Comum')
        item.setText(2,data['state']);item.setText(3,f"{data.get('duration',0):.1f} s")
        self.cancel_task_button.setEnabled(not data['admin'] and data['state']=='Executando')
        if data['admin']:self.cancel_task_button.setToolTip('Aguarde o término da tarefa autorizada pelo sistema; não há interrupção forçada administrativa.')

    def show_test_error(self,error):
        """Exibe causa e origem, mantendo traceback recolhido por padrão."""
        self._test_error=error;self.run_error_label.setText(error['message'])
        self.run_trace.setPlainText(error.get('traceback',''));self.run_trace.hide()
        self.add_output('error','[Erro] '+error['message']+'\n')
        self.drawer.show();self.drawer.setCurrentIndex(4);self.test_status.setText('Erro')

    def locate_test_error(self):
        """Reutiliza o mapa bloco/linha do snapshot, sem adivinhar a origem."""
        if self.runtime_window and hasattr(self,'_test_error'):self._locate_runtime_error(self._test_error,self.runtime_window)

    def update_test_time(self):
        """Avisa quando a edição se distancia do snapshot que está em execução."""
        window=self.runtime_window
        from .settings import preference
        if window and not window.session.closed and self.test_started and preference('test/duration'):
            self.statusBar().showMessage(f'Teste em execução · {time.monotonic()-self.test_started:.0f} s')
        if window and not window.session.closed and self._runtime_project_fingerprint!=self.fingerprint():
            self.set_test_status('Projeto alterado · F5 para reiniciar')

    def set_test_status(self,text):
        """Mantém o cabeçalho compacto e o texto completo disponível no tooltip."""
        compact=text
        for phrase,label in [('administrativa','Autorização do sistema'),('Aguardando resposta','Aguardando resposta'),('Iniciando','Iniciando'),('Fluxo concluído','Concluído'),('Fluxo cancelado','Interrompido'),('Erro','Erro'),('erro','Erro'),('Executando fluxo','Executando'),('Aplicativo em execução','Em execução'),('Encerrando','Encerrando'),('encerrada','Parado'),('Projeto alterado','Alterações · F5 para reiniciar')]:
            if phrase in text:compact=label;break
        self.test_status.setText(compact);self.test_status.setToolTip(text)
