# SPDX-License-Identifier: GPL-3.0-or-later
"""Observable contracts for PTY, migration and debugging without arbitrary evaluation."""

import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from makebench.core.project import Project, ComponentKind, ProjectError
from makebench.core.logic import create_flow
from makebench.core.logic_defaults import literal, default_block
from makebench.core.storage import load_project, save_project
from makebench.runtime.debugger import inspect_value
from makebench.terminal.session import TerminalSession, key_input


class TerminalTests(unittest.TestCase):
    """Um processo real precisa perceber TTY, tamanho, entrada e sinais."""

    def wait(self, terminal, predicate, timeout=5):
        """Drain the PTY until the result is observed, with a time limit per scenario."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            terminal.poll()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Terminal não atingiu o resultado esperado: " + repr(terminal.screen.display))

    def test_tty_unicode_ansi_input_resize_and_exit(self):
        """ANSI keeps cells and UTF-8, and the child sees a resized PTY."""
        terminal = TerminalSession(80, 24)
        self.addCleanup(terminal.stop)
        self.assertFalse(terminal.running)
        terminal.start(
            sys.executable,
            [
                "-u",
                "-c",
                "import os; print(os.isatty(0),flush=True); print('\\033[31mOlá\\033[0m',flush=True); input(); print(os.get_terminal_size().columns,flush=True)",
            ],
        )
        self.wait(terminal, lambda: "Olá" in "\n".join(terminal.screen.display))
        self.assertIn("True", "\n".join(terminal.screen.display))
        self.assertEqual(terminal.screen.buffer[1][0].fg, "red")
        terminal.resize(101, 30)
        terminal.send("teste\r")
        self.wait(terminal, lambda: not terminal.running)
        self.assertIn("101", "\n".join(terminal.screen.display))
        self.assertEqual(terminal.exit_code, 0)

    def test_ctrl_c_interrupts_foreground_and_close_kills_background(self):
        """Ctrl+C reaches the process and stopping leaves no shell or job running."""
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "job.pid"
            terminal = TerminalSession(root=directory)
            self.addCleanup(terminal.stop)
            terminal.start("/bin/bash", ["--noprofile", "--norc", "-i"])
            terminal.send(f"sleep 60 & echo $! > {file.name}\rsleep 60\r")
            self.wait(terminal, lambda: file.exists() and file.stat().st_size > 0)
            child = int(file.read_text())
            terminal.send("\x03")
            time.sleep(0.05)
            terminal.poll()
            self.assertTrue(terminal.running)
            terminal.stop()
            # A freshly adopted child may briefly exist as a zombie, but never runs.
            status = Path(f"/proc/{child}/stat")
            for _ in range(100):
                try:
                    if not status.exists() or ") Z " in status.read_text():
                        break
                except (FileNotFoundError, ProcessLookupError):
                    break
                time.sleep(0.01)
            try:
                self.assertTrue(not status.exists() or ") Z " in status.read_text())
            except (FileNotFoundError, ProcessLookupError):
                pass

    def test_history_bounded_and_cursor_addressing(self):
        """Long output stays bounded and programs can move/erase the cursor."""
        terminal = TerminalSession(20, 4)
        terminal.stream.feed(b"abc\x1b[1;1HZ\x1b[K")
        self.assertEqual(terminal.screen.display[0].strip(), "Z")
        terminal.stream.feed(b"line\r\n" * 11000)
        self.assertLessEqual(len(terminal.screen.history.top), 10000)
        self.assertEqual(key_input("c", "c", control=True), "\x03")

    def test_alternate_screen_restores_main_buffer(self):
        """Full-screen applications restore the previous content on exit."""
        terminal = TerminalSession(20, 4)
        terminal.stream.feed(b"main\x1b[?1049hfull\x1b[?1049l")
        self.assertTrue(terminal.screen.display[0].startswith("main"))
        self.assertNotIn("full", "\n".join(terminal.screen.display))

    def test_format_upgrade_backup_and_old_file_untouched_on_open(self):
        """Terminal requires format 6; opening v4 is inert and saving keeps the original."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.makebench.json"
            project = Project.empty()
            save_project(project, path)
            old = path.read_bytes()
            reopened = load_project(path)
            self.assertEqual(path.read_bytes(), old)
            terminal = reopened.add(reopened.root.id, ComponentKind.TERMINAL)
            self.assertEqual(reopened.to_dict()["format_version"], 6)
            save_project(reopened, path)
            self.assertEqual(path.with_name(path.name + ".bak-v4").read_bytes(), old)
            self.assertEqual(load_project(path).find(terminal.id).kind, ComponentKind.TERMINAL)
            terminal.properties["terminal_arguments"] = "not argv"
            with self.assertRaises(ProjectError):
                Project.from_dict(reopened.to_dict())


class WorkerHarness:
    """Test transport without Qt; the project's Python never runs in the test process."""

    def __init__(self, project, source, directory):
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "makebench.runtime.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.messages = queue.Queue()

        def read():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))

        threading.Thread(target=read, daemon=True).start()
        from makebench.core.source import source_files

        self.send(
            {
                "source_files": source_files(source),
                "project": project.to_dict(),
                "source": source,
                "source_filename": "project.actions.py",
                "root": directory,
                "debug": {"enabled": True},
            }
        )
        self.until(lambda m: m["type"] == "ready")

    def send(self, value):
        """Send a message immediately, without waiting for a UI reply."""
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def until(self, predicate):
        """Wait for a specific message with a deadline to detect a stuck protocol."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            message = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            if message["type"] == "error":
                raise AssertionError(message)
            if predicate(message):
                return message
        raise AssertionError("Sem resposta do worker")

    def command(self, action, **values):
        """Usa o mesmo protocolo limitado exposto pela IDE."""
        self.send({"type": "debug", "action": action, **values})

    def close(self):
        """Recolhe o worker mesmo quando um teste falha durante pausa."""
        if self.process.poll() is None:
            self.command("stop")
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


class DebugTests(unittest.TestCase):
    """Pontos, pilha, passos e pausa durante resposta precisam funcionar no processo real."""

    def make_worker(self, body, source):
        """Create a snapshot with one event; breakpoints always belong to the own file or the block."""
        project = Project.empty()
        flow = create_flow(project, project.root.id)
        flow["body"] = body
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        worker = WorkerHarness(project, source, directory.name)
        self.addCleanup(worker.close)
        worker.send({"type": "event", "flow": flow["id"], "window": project.root.id})
        return worker, flow

    def test_step_in_out_and_readonly_values(self):
        """An event calls an own function, steps into it, inspects data and returns to the block."""
        worker, flow = self.make_worker(
            [
                {"id": "call", "op": "call", "function": "action", "value": literal(4)},
                {"id": "log", "op": "log", "value": literal("fim")},
            ],
            'def action(ctx, value):\n    result=value+2\n    ctx.variables["result"]=result\n    return result\n',
        )
        pause = worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        self.assertEqual(pause["block"], "call")
        worker.command("step_in")
        pause = worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        self.assertEqual(pause["source_line"], 2)
        self.assertEqual(pause["stack"][0]["variables"]["value"], 4)
        worker.command("step_over")
        pause = worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        self.assertEqual(pause["stack"][0]["variables"]["result"], 6)
        worker.command("step_out")
        pause = worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        self.assertEqual(pause["block"], "log")
        self.assertEqual(pause["variables"]["result"], 6)
        worker.command("continue")
        self.assertEqual(worker.until(lambda m: m["type"] == "done")["outcome"], "success")

    def test_pause_while_waiting_ui_retains_response(self):
        """Pause and continue work during a dialog and do not consume its reply."""
        worker, flow = self.make_worker(
            [
                {"id": "dialog", "op": "message", "value": literal("oi")},
                {"id": "after", "op": "log", "value": literal("fim")},
            ],
            "",
        )
        worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        worker.command("continue")
        request = worker.until(lambda m: m["type"] == "request")
        worker.command("pause")
        pause = worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        self.assertEqual(pause["block"], "dialog")
        worker.send({"type": "response", "id": request["id"], "ok": True, "value": None})
        worker.command("continue")
        self.assertEqual(worker.until(lambda m: m["type"] == "done")["outcome"], "success")

    def test_breakpoints_in_own_source(self):
        """A line breakpoint is independent of steps and resolves the snapshot's function."""
        worker, flow = self.make_worker(
            [{"id": "call", "op": "call", "function": "action", "value": literal(4)}],
            "def action(ctx, value):\n    result=value+2\n    ctx.log(result)\n",
        )
        worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        worker.command("breakpoints", items=[{"file": "source", "line": 3}])
        worker.command("continue")
        pause = worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        self.assertEqual(pause["source_line"], 3)
        worker.command("continue")
        worker.until(lambda m: m["type"] == "done")

    def test_stop_while_paused_does_not_execute_next_block(self):
        """Stopping a paused session ends the worker before running the own code."""
        worker, _ = self.make_worker(
            [{"id": "call", "op": "call", "function": "action", "value": literal(4)}],
            'def action(ctx,value):\n    raise AssertionError("Não deve executar")\n',
        )
        worker.until(lambda m: m["type"] == "debug" and m["state"] == "paused")
        worker.command("stop")
        self.assertEqual(worker.process.wait(timeout=3), 0)

    def test_inspection_does_not_invoke_project_methods(self):
        """Unknown objects never get repr, iteration or property access."""

        class Dangerous:
            def __repr__(self):
                raise AssertionError("Não chamar repr")

        self.assertEqual(inspect_value({"object": Dangerous()}), {"object": "<Dangerous>"})
