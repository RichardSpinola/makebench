"""Adaptador Qt do teste GTK: somente supervisão, sem controles Qt no aplicativo."""
import json
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QObject,QProcess,QProcessEnvironment,Signal
from makebench.core.project import Project,ProjectError
from makebench.core.codegen import generate
from makebench.core.environment import gtk_support,GTK_HELP


class GtkSession(QObject):
    """Sinais compatíveis com a gaveta de testes existente da bancada."""
    output=Signal(str,str);busy_changed=Signal(bool);error=Signal(dict);task_changed=Signal(dict)
    debug_changed=Signal(dict)
    inspection=Signal(dict)
    admin_changed=Signal(bool);stopped=Signal();ready=Signal();event_done=Signal(dict)
    def __init__(self,parent):
        """Somente armazena o estado observado do processo GTK."""
        super().__init__(parent);self.closed=True;self.active=False;self.busy=False;self.admin_active=False


    def debug_command(self, action, **values):
        """Encaminha comandos ao worker neutro através da ponte GTK."""
        self.parent().command({'command':'debug','action':action,**values})


class GtkRuntimeBridge(QObject):
    """Lança GTK somente em start/F5 e mantém referências até o término real."""
    locate_requested=Signal(dict);shutdown_finished=Signal();status_changed=Signal(str)
    def __init__(self,project,source,read_asset,root=None,source_filename=None,parent=None,supervision=False):
        """Valida e copia snapshot para staging sem executar conteúdo do projeto."""
        super().__init__(parent)
        if not gtk_support()['gtk4']:raise ProjectError(GTK_HELP)
        diagnostics=generate(project,source).diagnostics
        if diagnostics:raise ProjectError('\n'.join(diagnostics))
        self.project=Project.from_dict(project.to_dict());self.source=source;self.session=GtkSession(self)
        self.temp=tempfile.TemporaryDirectory(prefix='makebench-gtk-');directory=Path(self.temp.name)
        self.path=directory/'project.makebench.json';self.path.write_text(json.dumps(project.to_dict(),ensure_ascii=False),encoding='utf-8')
        (directory/'project.actions.py').write_text(source,encoding='utf-8')
        for name in project.asset_paths():
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_asset(name))
        self.process=QProcess(self);env=QProcessEnvironment.systemEnvironment();env.insert('PYTHONPATH',str(Path(__file__).resolve().parents[2])+':'+env.value('PYTHONPATH'));self.process.setProcessEnvironment(env)
        self.process.setProgram(sys.executable);self.process.setArguments(['-u','-m','makebench.gtk_runtime.launcher',str(self.path),'--supervised','--working-directory',str(Path(root).resolve() if root else directory),'--source-filename',str(source_filename or directory/'project.actions.py')]);self.buffer=b'';self._stderr=b''
        self.debug_config=None
        self.process.readyReadStandardOutput.connect(self.read);self.process.readyReadStandardError.connect(self.read_error)
        self.process.finished.connect(self.finished);self.process.errorOccurred.connect(self.process_error)

    def start(self):
        """Inicia o processo GTK explícito, mantendo o editor livre para responder."""
        if self.debug_config:
            (self.path.parent/'debug.json').write_text(json.dumps(self.debug_config),encoding='utf-8')
        self.session.closed=False;self.session.busy=True;self.session.busy_changed.emit(True);self.process.start()

    def command(self,value):
        """Envia comandos de supervisão para o processo GTK independente."""
        self.process.write((json.dumps(value)+'\n').encode())

    def show(self):
        """Reapresenta janelas GTK já abertas sem criar outra instância."""
        if self.process.state()==QProcess.ProcessState.Running:self.command({'command':'raise'})

    def raise_(self):
        """Compatibilidade com os comandos de foco do editor."""
        self.show()

    def activateWindow(self):
        """Solicita apresentação ao toolkit e compositor da aplicação GTK."""
        self.show()

    def read(self):
        """Remonta protocolo JSON; código do projeto nunca é avaliado no editor."""
        self.buffer+=bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>2_000_000:self.session.error.emit({'message':'Resposta GTK excedeu o limite.'});self.stop();return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:self.message(json.loads(line))
            except (ValueError,KeyError,TypeError) as exc:self.session.error.emit({'message':'Protocolo GTK inválido: '+str(exc)})

    def message(self,value):
        """Converte observação do GTK nos mesmos sinais usados pelo runtime Qt."""
        kind=value['type'];session=self.session
        if kind=='log':session.output.emit(value['channel'],value['text'])
        elif kind=='status':self.status_changed.emit(value['text'])
        elif kind=='error':session.error.emit(value)
        elif kind=='ready':session.active=True;session.ready.emit()
        elif kind=='busy':session.busy=value['value'];session.busy_changed.emit(session.busy)
        elif kind=='admin':session.admin_active=value['value'];session.admin_changed.emit(session.admin_active)
        elif kind=='task':session.task_changed.emit(value)
        elif kind=='debug':session.debug_changed.emit(value)
        elif kind=='inspection':session.inspection.emit(value)
        elif kind=='done':session.event_done.emit(value)

    def read_error(self):
        """Encaminha mensagens nativas do GTK como stderr de diagnóstico."""
        text=bytes(self.process.readAllStandardError()).decode('utf-8',errors='replace')
        if text:self.session.output.emit('stderr',text)

    def stop(self):
        """Não força GTK nem tarefa administrativa; aguarda limpeza dos grupos comuns."""
        if self.session.admin_active:return False
        if not self.session.closed:self.command({'command':'stop'})
        return True

    def close(self):
        """Fecha por protocolo sem abandonar processos de teste."""
        return self.stop()

    def setEnabled(self,_enabled):
        """Compatibilidade de ciclo de vida; sensibilidade pertence ao GTK."""

    def process_error(self,error):
        """Falha de inicialização não recebe finished no QProcess."""
        if error==QProcess.ProcessError.FailedToStart:
            self.session.error.emit({'message':self.process.errorString()});self.finished()

    def finished(self,*_args):
        """Libera o snapshot somente após o processo GTK ter terminado."""
        self.read();self.read_error();self.session.closed=True;self.session.busy=False;self.session.active=False
        self.session.busy_changed.emit(False);self.session.stopped.emit();self.shutdown_finished.emit();self.temp.cleanup()
