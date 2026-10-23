"""PTY e emulação VT compartilhados, sem dependência de interface gráfica.

A emulação usa pyte 0.8.2 (LGPL-3.0-or-later); consulte THIRD_PARTY.md.
Somente start cria um processo. A leitura é não bloqueante e cabe ao toolkit
chamar poll; o histórico nunca ultrapassa 10 mil linhas.
"""
from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import struct
import termios

import pyte
from copy import deepcopy


class TerminalScreen(pyte.HistoryScreen):
    """Acrescenta tela alternativa xterm sem acumular seu conteúdo no histórico."""
    def __init__(self, *args, **kwargs):
        """Guarda a tela principal quando um programa de tela cheia solicita outra."""
        self.alternate=None
        super().__init__(*args,**kwargs)

    def set_mode(self, *modes, **kwargs):
        """Entra em 47/1047/1049, preservando conteúdo e cursor da tela principal."""
        if kwargs.get('private') and set(modes)&{47,1047,1049} and self.alternate is None:
            self.alternate=(deepcopy(self.buffer),deepcopy(self.cursor),deepcopy(self.history))
            self.erase_in_display(2);self.cursor_position();self.history.top.clear();self.history.bottom.clear()
        super().set_mode(*modes,**kwargs)

    def reset_mode(self, *modes, **kwargs):
        """Restaura a tela principal quando o programa deixa a tela alternativa."""
        super().reset_mode(*modes,**kwargs)
        if kwargs.get('private') and set(modes)&{47,1047,1049} and self.alternate is not None:
            self.buffer,self.cursor,self.history=self.alternate;self.alternate=None
            self.cursor.x=min(self.cursor.x,self.columns-1);self.cursor.y=min(self.cursor.y,self.lines-1)
            self.dirty.update(range(self.lines))

    def reset(self):
        """Limpa também uma tela alternativa ao iniciar outra sessão."""
        self.alternate=None
        super().reset()


class TerminalSession:
    """Possui uma sessão Linux e sua tela; não oferece elevação administrativa."""

    def __init__(self, columns=80, rows=24, root=None):
        """Prepara emulação inerte e diretório inicial, sem abrir shell."""
        self.screen = TerminalScreen(columns, rows, history=10_000)
        self.screen.write_process_input = self.send
        self.stream = pyte.ByteStream(self.screen)
        self.root = Path(root or Path.home()).resolve()
        self.pid = None
        self.master = None
        self.exit_code = None
        self.process = None
        self.pending = bytearray()
        self.revision = 0

    @property
    def running(self):
        """Indica se há filho ainda pertencente ao terminal."""
        return self.pid is not None

    def start(self, program=None, arguments=None):
        """Abre PTY controladora e executa argv sem shell intermediário.

        Sem programa explícito, usa o shell do usuário, ou /bin/sh. Cada início
        possui sessão própria; abrir o documento ou construir este objeto é inerte.
        """
        if self.running:
            raise ValueError('O terminal já está em execução.')
        if not program:
            shell=os.environ.get('SHELL')
            program=shell if shell and shutil.which(shell) else '/bin/sh'
        arguments = [] if arguments is None else arguments
        if not isinstance(program, str) or not program or '\0' in program:
            raise ValueError('Programa de terminal inválido.')
        if not isinstance(arguments, list) or any(not isinstance(a, str) or '\0' in a for a in arguments):
            raise ValueError('Argumentos precisam ser uma lista de textos.')
        import pty
        master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',self.screen.lines,self.screen.columns,0,0))
            environment=dict(os.environ,TERM='xterm-256color',COLORTERM='truecolor')
            self.process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('child.py')),program,*arguments],
                stdin=slave,stdout=slave,stderr=slave,cwd=self.root,env=environment,start_new_session=True)
        except BaseException:
            os.close(master);raise
        finally:
            os.close(slave)
        self.pid,self.master=self.process.pid,master
        self.exit_code = None
        self.pending.clear()
        self.screen.reset()
        os.set_blocking(master, False)
        self.resize(self.screen.columns, self.screen.lines)
        self.revision += 1
        return self.pid

    def resize(self, columns, rows):
        """Atualiza tela e PTY, provocando SIGWINCH no grupo em primeiro plano."""
        columns, rows = max(2, min(1000, int(columns))), max(2, min(500, int(rows)))
        if (columns, rows) != (self.screen.columns, self.screen.lines):
            self.screen.resize(lines=rows, columns=columns)
            self.revision += 1
        if self.master is not None:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))

    def send(self, value):
        """Enfileira entrada UTF-8/bytes, incluindo sequências de controle."""
        if self.master is None:
            return False
        data = value.encode('utf-8') if isinstance(value, str) else bytes(value)
        if len(self.pending) + len(data) > 1_000_000:
            raise ValueError('A entrada do terminal excedeu o limite de 1 MB.')
        self.pending.extend(data)
        self._flush()
        return True

    def _flush(self):
        """Escreve somente bytes aceitos pela PTY, sem bloquear a interface."""
        if self.master is None or not self.pending:
            return
        try:
            count = os.write(self.master, self.pending)
            del self.pending[:count]
        except BlockingIOError:
            pass
        except OSError as exc:
            if exc.errno not in (errno.EIO, errno.EBADF):
                raise

    def poll(self):
        """Consome até 256 KiB por turno e recolhe o filho sem espera bloqueante."""
        self._flush()
        if self.master is not None:
            for _ in range(16):
                try:
                    data = os.read(self.master, 16384)
                    if not data:
                        break
                    self.stream.feed(data)
                    self.revision += 1
                except BlockingIOError:
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EIO, errno.EBADF):
                        raise
                    break
        if self.pid is not None:
            # WNOWAIT mantém o PID reservado durante a limpeza dos grupos.
            result=os.waitid(os.P_PID,self.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if result is not None:
                self._cleanup()
                self.exit_code=self.process.wait()
                self.process=None
                self.revision += 1
        return self.revision

    def _signal_session(self, sig):
        """Encerra grupos da sessão, inclusive jobs em segundo plano do shell."""
        if self.pid is None:
            return
        groups = {self.pid}
        for entry in Path('/proc').iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[3]) == self.pid:
                    groups.add(int(fields[2]))
            except (OSError, ValueError, IndexError):
                continue
        for group in groups:
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                pass

    def _cleanup(self):
        """Elimina jobs restantes antes de abandonar o identificador da sessão."""
        self._signal_session(signal.SIGKILL)
        if self.master is not None:
            os.close(self.master)
        self.master = self.pid = None
        self.pending.clear()

    def stop(self):
        """Fecha toda a sessão e recolhe o filho; operação idempotente."""
        pid = self.pid
        self._cleanup()
        if pid is not None:
            try:
                self.exit_code = self.process.wait()
                self.process=None
            except ChildProcessError:
                pass
        self.revision += 1

    def lines(self):
        """Retorna histórico e tela como células ANSI, sem interpretar HTML."""
        screen = self.screen
        return [*([] if screen.alternate is not None else screen.history.top), *(screen.buffer[y] for y in range(screen.lines))]


ANSI_COLORS = {'black':'#1d2021','red':'#cc4444','green':'#50a050','brown':'#c0a040',
               'blue':'#5599dd','magenta':'#b060c0','cyan':'#40b0b0','white':'#dddddd',
               'brightblack':'#777777','brightred':'#ff6666','brightgreen':'#88cc66',
               'brightbrown':'#ffdd77','brightblue':'#88bbff','brightmagenta':'#dd88ee',
               'brightcyan':'#88eeee','brightwhite':'#ffffff'}


def color(value, default):
    """Resolve cores pyte indexadas ou RGB usando o padrão da paleta nativa."""
    if value == 'default':
        return default
    return ANSI_COLORS.get(value, '#' + value if len(value) == 6 else default)


def key_input(name, text='', control=False, alt=False, application=False):
    """Traduz teclas comuns dos dois toolkits em sequências de terminal."""
    keys = {'Return':'\r','Enter':'\r','BackSpace':'\x7f','Tab':'\t','ISO_Left_Tab':'\x1b[Z',
            'Escape':'\x1b','Up':'\x1b[A','Down':'\x1b[B','Right':'\x1b[C','Left':'\x1b[D',
            'Home':'\x1b[H','End':'\x1b[F','Insert':'\x1b[2~','Delete':'\x1b[3~',
            'Page_Up':'\x1b[5~','Page_Down':'\x1b[6~',
            'F1':'\x1bOP','F2':'\x1bOQ','F3':'\x1bOR','F4':'\x1bOS',
            'F5':'\x1b[15~','F6':'\x1b[17~','F7':'\x1b[18~','F8':'\x1b[19~',
            'F9':'\x1b[20~','F10':'\x1b[21~','F11':'\x1b[23~','F12':'\x1b[24~'}
    if control and len(text) == 1 and 64 <= ord(text.upper()) <= 95:
        value = chr(ord(text.upper()) - 64)
    else:
        value = keys.get(name, text)
    if application and name in {'Up','Down','Right','Left','Home','End'}:
        value = value.replace('[', 'O')
    return ('\x1b' if alt else '') + value
