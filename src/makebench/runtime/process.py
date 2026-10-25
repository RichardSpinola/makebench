# SPDX-License-Identifier: GPL-3.0-or-later
"""QProcess tasks with explicit argv, incremental output and Polkit authentication."""

from __future__ import annotations
import codecs
import os
from pathlib import Path
import shutil
import signal

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from makebench.i18n import tr


def signal_group(identifier, number):
    """Signal only the group of a task created in its own session."""
    if identifier:
        try:
            os.killpg(identifier, number)
        except ProcessLookupError:
            pass


class TaskProcess(QObject):
    """Run a task and report its end exactly once, including start failures."""

    output = Signal(str, str)
    completed = Signal(dict)

    def __init__(self, program, arguments, root: Path, admin=False, parent=None):
        """Validate argv with no implicit shell; pkexec is reserved for declared tasks."""
        super().__init__(parent)
        if not isinstance(program, str) or not program.strip() or "\0" in program:
            raise ValueError(tr("Enter a valid program."))
        if (
            not isinstance(arguments, list)
            or len(arguments) > 256
            or any(not isinstance(arg, str) or "\0" in arg for arg in arguments)
        ):
            raise ValueError(tr("Arguments must be a list of up to 256 texts."))
        if type(admin) is not bool:
            raise ValueError(tr("Invalid administrative permission."))
        executable = str((root / program).resolve()) if "/" in program else shutil.which(program)
        if not executable:
            raise ValueError(tr("Program not found: {program}.").format(program=program))
        self.admin = admin
        self.pgid = 0
        self.finished = False
        if admin:
            pkexec = shutil.which("pkexec")
            if not pkexec:
                raise ValueError(
                    tr(
                        "pkexec is not available. Install Polkit support on the target distribution."
                    )
                )
            arguments = ["--disable-internal-agent", executable, *arguments]
            executable = pkexec
        self.process = QProcess(self)
        self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        self.process.setWorkingDirectory(str(root))
        from makebench.terminal.environment import external_environment

        environment = QProcessEnvironment()
        for key, value in external_environment(executable).items():
            environment.insert(key, value)
        self.process.setProcessEnvironment(environment)
        self.process.setProgram(executable)
        self.process.setArguments(arguments)
        self.process.setInputChannelMode(QProcess.InputChannelMode.ManagedInputChannel)
        self.decoders = {
            channel: codecs.getincrementaldecoder("utf-8")("replace")
            for channel in ("stdout", "stderr")
        }
        self.process.started.connect(self._started)
        self.process.readyReadStandardOutput.connect(lambda: self._read("stdout"))
        self.process.readyReadStandardError.connect(lambda: self._read("stderr"))
        self.process.finished.connect(self._finish)
        self.process.errorOccurred.connect(self._error)

    def start(self):
        """Start asynchronously; stdin is closed because interaction uses dialogs."""
        self.process.start()
        self.process.closeWriteChannel()

    def _started(self):
        """Keep the group for cancelling ordinary children."""
        self.pgid = int(self.process.processId())

    def _read(self, channel, final=False):
        """Decode UTF-8 even when a character arrives in several chunks."""
        data = (
            self.process.readAllStandardOutput()
            if channel == "stdout"
            else self.process.readAllStandardError()
        )
        text = self.decoders[channel].decode(bytes(data), final=final)
        if text:
            self.output.emit(channel, text)

    def _error(self, error):
        """A start failure gets no finished signal in Qt."""
        if error == QProcess.ProcessError.FailedToStart and not self.finished:
            self.finished = True
            self.completed.emit({"ok": False, "error": self.process.errorString()})

    def _finish(self, code, status):
        """Use exit status/code; writing to stderr does not mean failure."""
        if self.finished:
            return
        self.finished = True
        self._read("stdout", True)
        self._read("stderr", True)
        if self.admin and code in (126, 127):
            self.completed.emit(
                {
                    "ok": False,
                    "cancelled": code == 126,
                    "error": tr(
                        "Administrative task not completed (code {code}). Authentication may have been cancelled or refused; check the output."
                    ).format(code=code),
                }
            )
        else:
            self.completed.emit(
                {
                    "ok": True,
                    "value": {"code": code, "crashed": status == QProcess.ExitStatus.CrashExit},
                }
            )

    def terminate(self, force=False):
        """Cancel an ordinary user group; never forces an administrative task."""
        if self.admin:
            return False
        signal_group(self.pgid, signal.SIGKILL if force else signal.SIGTERM)
        if not self.pgid:
            self.process.kill() if force else self.process.terminate()
        return True
