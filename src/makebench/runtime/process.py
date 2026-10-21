"""Tarefas QProcess com argv explícito, saída incremental e autenticação Polkit."""
from __future__ import annotations
import codecs
import os
from pathlib import Path
import shutil
import signal

from PySide6.QtCore import QObject, QProcess, Signal


def signal_group(identifier, number):
    """Sinaliza apenas o grupo de uma tarefa criada em sessão própria."""
    if identifier:
        try:os.killpg(identifier,number)
        except ProcessLookupError:pass


class TaskProcess(QObject):
    """Executa uma tarefa e informa término uma única vez, inclusive falha de início."""
    output=Signal(str,str)
    completed=Signal(dict)

    def __init__(self, program, arguments, root: Path, admin=False, parent=None):
        """Valida argv sem shell implícito; pkexec é reservado às tarefas declaradas."""
        super().__init__(parent)
        if not isinstance(program,str) or not program.strip() or '\0' in program:
            raise ValueError('Informe um programa válido.')
        if not isinstance(arguments,list) or len(arguments)>256 or any(not isinstance(arg,str) or '\0' in arg for arg in arguments):
            raise ValueError('Argumentos precisam ser uma lista com até 256 textos.')
        if type(admin) is not bool:raise ValueError('Permissão administrativa inválida.')
        executable=str((root/program).resolve()) if '/' in program else shutil.which(program)
        if not executable:raise ValueError(f'Programa não encontrado: {program}.')
        self.admin=admin;self.pgid=0;self.finished=False
        if admin:
            pkexec=shutil.which('pkexec')
            if not pkexec:raise ValueError('pkexec não está disponível. Instale o suporte Polkit na distribuição de destino.')
            arguments=['--disable-internal-agent',executable,*arguments];executable=pkexec
        self.process=QProcess(self)
        self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        self.process.setWorkingDirectory(str(root))
        self.process.setProgram(executable);self.process.setArguments(arguments)
        self.process.setInputChannelMode(QProcess.InputChannelMode.ManagedInputChannel)
        self.decoders={channel:codecs.getincrementaldecoder('utf-8')('replace') for channel in ('stdout','stderr')}
        self.process.started.connect(self._started)
        self.process.readyReadStandardOutput.connect(lambda:self._read('stdout'))
        self.process.readyReadStandardError.connect(lambda:self._read('stderr'))
        self.process.finished.connect(self._finish)
        self.process.errorOccurred.connect(self._error)

    def start(self):
        """Inicia assincronamente; stdin é fechado porque a interação usa diálogos."""
        self.process.start()
        self.process.closeWriteChannel()

    def _started(self):
        """Guarda o grupo para cancelamento de filhos comuns."""
        self.pgid=int(self.process.processId())

    def _read(self, channel, final=False):
        """Decodifica UTF-8 mesmo quando um caractere chega em vários chunks."""
        data=self.process.readAllStandardOutput() if channel=='stdout' else self.process.readAllStandardError()
        text=self.decoders[channel].decode(bytes(data),final=final)
        if text:self.output.emit(channel,text)

    def _error(self, error):
        """Falha de inicialização não recebe sinal finished no Qt."""
        if error==QProcess.ProcessError.FailedToStart and not self.finished:
            self.finished=True
            self.completed.emit({'ok':False,'error':self.process.errorString()})

    def _finish(self, code, status):
        """Usa status/código de saída; escrever em stderr não implica falha."""
        if self.finished:return
        self.finished=True
        self._read('stdout',True);self._read('stderr',True)
        if self.admin and code in (126,127):
            self.completed.emit({'ok':False,'cancelled':code==126,
                'error':f'Tarefa administrativa não concluída (código {code}). A autenticação pode ter sido cancelada ou recusada; confira a saída.'})
        else:
            self.completed.emit({'ok':True,'value':{'code':code,'crashed':status==QProcess.ExitStatus.CrashExit}})

    def terminate(self, force=False):
        """Cancela grupo de usuário comum; nunca força uma tarefa administrativa."""
        if self.admin:return False
        signal_group(self.pgid,signal.SIGKILL if force else signal.SIGTERM)
        if not self.pgid:
            self.process.kill() if force else self.process.terminate()
        return True
