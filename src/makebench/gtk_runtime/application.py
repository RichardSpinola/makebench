# SPDX-License-Identifier: MIT
"""Real GTK application, Python worker and supervised tasks with no Qt dependency."""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from makebench.core.codegen import generate
from makebench.core.project import ComponentKind, ProjectError
from makebench.i18n import language, tr
from .renderer import GtkView


def terminate_group(process, force=False):
    """Signal only groups created by the runtime; never an administrative process."""
    if process:
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass


class GtkRuntime:
    """Share the Qt runtime's ctx protocol and keep the GTK loop responsive."""

    def __init__(self, project, source, read_asset, root, source_filename, observer=None):
        """Prepare the snapshot; building the instance does not run the user's code."""
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, GLib, Gio

        if not Gtk.init_check():
            raise ProjectError(tr("Could not open GTK4: no graphical display is available."))
        self.Gtk, self.GLib = Gtk, GLib
        self.Adw = None
        try:
            gi.require_version("Adw", "1")
            from gi.repository import Adw

            self.Adw = Adw
        except (ValueError, ImportError):
            pass
        self.project = project
        self.source = source
        self.read_asset = read_asset
        self.root = Path(root).resolve()
        self.source_filename = source_filename
        diagnostics = generate(project, source).diagnostics
        if diagnostics:
            raise ProjectError("\n".join(diagnostics))
        self.debug_config = {}
        self.observer = observer or (lambda value: None)
        self.windows = {}
        self.views = {}
        self.open_windows = set()
        self.states = {}
        self.pending = []
        self.current = project.entry_window or project.root.id
        self.process = None
        self.task = None
        self.admin = False
        self.active = False
        self.busy = True
        self.stopping = False
        self.lock = threading.Lock()
        self.dialogs = set()
        self.event_buttons = {
            f["event"]["component"] for f in project.editable_flows if f["event"]["kind"] == "click"
        }
        cls = self.Adw.Application if self.Adw else Gtk.Application
        self.app = cls(
            application_id=project.application.get("id") or "org.makebench.Generated",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.app.connect("activate", self.activate)

    def emit(self, kind, **values):
        """Forward observations to the workbench or to the standalone application's console."""
        self.observer({"type": kind, **values})

    def run(self):
        """Explicit entry of the GTK run; starting is the only action that runs code."""
        return self.app.run([])

    def activate(self, _app):
        """Open the start window and start the same neutral worker used by Qt."""
        if self.process:
            for identifier in self.open_windows:
                self.windows[identifier].present()
            return
        self.app.hold()
        self.open_window(self.current, queue_start=False)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        package_root = str(Path(__file__).resolve().parents[2])
        environment["PYTHONPATH"] = package_root + os.pathsep + environment.get("PYTHONPATH", "")
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "makebench.runtime.worker"],
            cwd=self.root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            bufsize=0,
        )
        from makebench.core.source import source_files

        self.send(
            {
                "source_files": source_files(self.source),
                "project": self.project.to_dict(),
                "source": self.source,
                "root": str(self.root),
                "source_filename": str(self.source_filename or "<makebench-actions>"),
                "debug": self.debug_config,
                "language": language(),
            }
        )
        threading.Thread(target=self.read_worker, daemon=True).start()
        threading.Thread(
            target=self.read_channel, args=(self.process.stderr, "stderr"), daemon=True
        ).start()
        self.emit("status", text=tr("Starting GTK…"))

    def send(self, value):
        """Serialize replies to the worker; pipe failures are handled at shutdown."""
        if self.process and self.process.poll() is None:
            try:
                with self.lock:
                    self.process.stdin.write((json.dumps(value, ensure_ascii=True) + "\n").encode())
                    self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def reply(self, identifier, value=None, ok=True, cancelled=False, error=""):
        """Keep the reply contract identical in both toolkits."""
        self.send(
            {
                "type": "response",
                "id": identifier,
                "value": value,
                "ok": ok,
                "cancelled": cancelled,
                "error": error,
            }
        )

    def read_worker(self):
        """Read in a thread and deliver to GTK only through idle_add, without blocking drawing."""
        try:
            while True:
                line = self.process.stdout.readline(2_000_001)
                if not line:
                    break
                if len(line) > 2_000_000:
                    raise ValueError(tr("The worker reply exceeded the limit."))
                self.GLib.idle_add(self.message, json.loads(line))
        except (ValueError, OSError) as exc:
            self.GLib.idle_add(lambda message=str(exc): self.emit("error", message=message))
        finally:
            self.GLib.idle_add(self.worker_finished)

    def read_channel(self, pipe, channel):
        """Keep incremental UTF-8 and live output even without line breaks."""
        import codecs

        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            data = pipe.read(8192)
            if not data:
                break
            text = decoder.decode(data)
            if text:
                self.GLib.idle_add(self.output, channel, text)
        tail = decoder.decode(b"", final=True)
        if tail:
            self.GLib.idle_add(self.output, channel, tail)

    def output(self, channel, text):
        """Record channels without treating stderr as failure."""
        self.emit("log", channel=channel, text=text)
        if channel != "status":
            view = self.views.get(self.current)
            if view:
                for node in view.root.walk():
                    if node.kind == ComponentKind.OUTPUT:
                        buffer = view.widgets[node.id].get_buffer()
                        buffer.insert(buffer.get_end_iter(), text)
                        if buffer.get_char_count() > 500000:
                            buffer.delete(
                                buffer.get_start_iter(),
                                buffer.get_iter_at_offset(buffer.get_char_count() - 400000),
                            )

    def message(self, message):
        """Serve the worker's neutral events only on the GTK thread."""
        if self.stopping:
            return
        kind = message.get("type")
        if kind == "ready":
            self.active = True
            from makebench.terminal.components import start_components

            for view in self.views.values():
                start_components(view.root, view.widgets, self.root)
            self.set_busy(False)
            self.queue_event(self.current, "start")
            self.emit("ready")
        elif kind == "debug":
            self.observer(message)
        elif kind == "busy":
            self.set_busy(True)
        elif kind == "done":
            self.set_busy(False)
            self.emit("done", **{k: v for k, v in message.items() if k != "type"})
            self.dispatch()
        elif kind == "log":
            self.output(message["channel"], message["text"])
        elif kind == "error":
            self.output("error", tr("[Error]") + " " + message.get("message", tr("Error")) + "\n")
            self.emit("error", **{k: v for k, v in message.items() if k != "type"})
        elif kind == "request":
            self.request(message)

    def set_busy(self, busy):
        """Update event sensitivity and state observation in the workbench."""
        self.busy = busy
        for view in self.views.values():
            view.busy(busy, self.event_buttons)
        self.emit("busy", value=busy)
        self.emit("status", text=tr("Running flow…") if busy else tr("GTK application running"))

    def queue_event(self, identifier, kind="click"):
        """Pick state-specific flows before generic ones."""
        if kind == "click" and self.busy:
            return
        owner = self.project.window_of(identifier)
        if owner is None:
            return
        matches = [
            f
            for f in self.project.editable_flows
            if f["event"] == {"component": identifier, "kind": kind}
        ]
        specific = [f for f in matches if self.states[owner.id] in f.get("states", [])]
        self.pending.extend(
            f["id"] for f in (specific or [f for f in matches if not f.get("states")])
        )
        self.dispatch()

    def dispatch(self):
        """Run a single handler at a time; window variables follow the event."""
        if self.pending and self.active and not self.busy and not self.stopping:
            identifier = self.pending.pop(0)
            flow = next(f for f in self.project.editable_flows if f["id"] == identifier)
            self.current = self.project.window_of(flow["event"]["component"]).id
            self.set_busy(True)
            self.send({"type": "event", "flow": identifier, "window": self.current})

    def open_window(self, identifier, close_current=False, queue_start=True):
        """Open a real GTK window; reopening resets controls, state and scope."""
        root = next((r for r in self.project.roots if r.id == identifier), None)
        if root is None:
            raise ValueError(tr("The window does not exist."))
        reset = identifier not in self.open_windows
        if reset:
            if identifier in self.windows:
                self.windows[identifier].destroy()
            view = GtkView(root, self.read_asset, self.queue_event)
            self.views[identifier] = view
            if self.Adw:
                window = self.Adw.ApplicationWindow(application=self.app)
                box = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL)
                box.append(self.Adw.HeaderBar())
                box.append(view.widget)
                view.widget.set_vexpand(True)
                window.set_content(box)
            else:
                window = self.Gtk.ApplicationWindow(application=self.app)
                window.set_child(view.widget)
            icon = root.properties.get("icon") or self.project.application.get("icon")
            if icon:
                self.Gtk.IconTheme.get_for_display(window.get_display()).add_search_path(
                    str(self.root / Path(icon).parent)
                )
                window.set_icon_name(Path(icon).stem)
            window.set_title(root.properties.get("title", self.project.name))
            window.set_default_size(
                root.properties.get("width", 640), root.properties.get("height", 480)
            )
            window.set_resizable(root.properties.get("resizable", True))
            window.connect("close-request", lambda _window: self.window_close(identifier))
            self.windows[identifier] = window
            self.states[identifier] = root.properties.get("initial_state", "@default")
            self.apply_state(identifier, self.states[identifier])
            view.busy(self.busy, self.event_buttons)
        self.open_windows.add(identifier)
        self.windows[identifier].present()
        if close_current and self.current != identifier:
            self.close_window(self.current, check_last=False)
        if reset and queue_start:
            from makebench.terminal.components import start_components

            start_components(root, self.views[identifier].widgets, self.root)
            self.queue_event(identifier, "start")
        self.emit("navigation", windows=sorted(self.open_windows), states=dict(self.states))
        return reset

    def apply_state(self, identifier, state):
        """Apply only content differences, keeping IDs and the base structure."""
        root = self.project.effective_root(identifier, state)
        view = self.views[identifier]
        self.states[identifier] = state
        for node in root.walk():
            p = node.properties
            widget = view.widgets[node.id]
            if node.kind in {
                ComponentKind.LABEL,
                ComponentKind.BUTTON,
                ComponentKind.TEXT_INPUT,
                ComponentKind.CHECKBOX,
                ComponentKind.OUTPUT,
            }:
                view.set_text(node.id, p.get("text", ""))
            if node.kind == ComponentKind.CHECKBOX:
                widget.set_active(p.get("checked", False))
            if node.kind == ComponentKind.PROGRESS:
                widget.set_fraction(p.get("value", 0) / 100)
            if node.kind == ComponentKind.IMAGE:
                paintable = (
                    view.Gdk.Texture.new_from_bytes(
                        view.GLib.Bytes.new(self.read_asset(p["source"]))
                    )
                    if p.get("source")
                    else None
                )
                widget.set_paintable(paintable)
            view.frames[node.id].set_visible(p.get("visible", True))
            view.enabled[node.id] = p.get("enabled", True)
            widget.set_sensitive(view.enabled[node.id])
            if node.kind == ComponentKind.PAGES:
                view.show_page(self.project, p["initial_page"])
        if identifier in self.windows:
            self.windows[identifier].set_title(root.properties.get("title", self.project.name))
        self.emit("navigation", windows=sorted(self.open_windows), states=dict(self.states))

    def window_close(self, identifier):
        """Never close or interrupt an administrative action in progress."""
        if self.admin:
            self.emit("status", text=tr("Wait for the administrative task to finish."))
            return True
        self.close_window(identifier)
        return True

    def close_window(self, identifier, check_last=True):
        """Close an interface and end the application when no other remains."""
        if self.admin:
            raise ValueError(tr("Wait for the administrative task to finish."))
        from makebench.terminal.components import stop_components

        if identifier in self.views:
            stop_components(self.views[identifier].widgets)
        self.open_windows.discard(identifier)
        if identifier in self.windows:
            self.windows[identifier].set_visible(False)
        if check_last and not self.open_windows:
            self.GLib.idle_add(self.stop)
        self.emit("navigation", windows=sorted(self.open_windows), states=dict(self.states))

    def locate(self, identifier):
        """Resolve a stable ID or readable name in any open window."""
        node = self.project.find(identifier) or next(
            (n for n in self.project.walk() if n.properties.get("code_name") == identifier), None
        )
        if node is None:
            raise ValueError(tr("The component does not exist."))
        owner = self.project.window_of(node.id)
        view = self.views.get(owner.id)
        if view is None:
            raise ValueError(tr("The component's window is not open."))
        return view, node.id

    def request(self, r):
        """Translate the same ctx API to GTK, tasks and declared dialogs."""
        identifier = r["id"]
        method = r["method"]
        try:
            if method == "run":
                self.run_task(r)
                return
            if method in {"ask", "confirm", "message"}:
                self.dialog(r)
                return
            result = None
            if method.startswith("terminal_"):
                from makebench.terminal.components import terminal_request

                view, key = self.locate(r.get("component"))
                view.widgets[key].terminal.root = self.root
                result = terminal_request(view.widgets[key], method, r)
            elif method == "go_state":
                self.apply_state(self.current, r["state"])
            elif method == "open_window":
                result = {"reset": self.open_window(r["window"], r.get("close_current", False))}
            elif method == "close_window":
                self.close_window(self.current)
            elif method in {"set_theme", "set_background"}:
                from makebench.core.style import THEMES, valid_color

                view = self.views[self.current]
                if method == "set_theme":
                    if r["theme"] not in THEMES or (r["accent"] and not valid_color(r["accent"])):
                        raise ValueError(tr("Use light, dark or system and a #rrggbb accent."))
                    view.change_style(theme=r["theme"], accent=r["accent"])
                else:
                    if r["color"] and not valid_color(r["color"]):
                        raise ValueError(tr("Use a color such as #336699."))
                    view.change_style(background=r["color"])
            else:
                view, key = self.locate(r.get("component"))
                widget = view.widgets[key]
                if method == "read":
                    result = view.read(key, r["attribute"])
                elif method == "set_text":
                    view.set_text(key, r["value"])
                elif method == "set_enabled":
                    view.enabled[key] = r["value"]
                    widget.set_sensitive(r["value"])
                elif method == "set_value":
                    if not 0 <= r["value"] <= 100:
                        raise ValueError(tr("Progress must be between 0 and 100."))
                    widget.set_fraction(r["value"] / 100)
                elif method == "show_page":
                    view.show_page(self.project, key)
                else:
                    raise ValueError(tr("Unknown operation."))
            self.reply(identifier, result)
        except (ValueError, TypeError, AttributeError, KeyError, OSError) as exc:
            self.reply(identifier, ok=False, error=str(exc))

    def dialog(self, r):
        """Explicit GTK dialogs, with no password of their own and no reading of terminal prompts."""
        Gtk = self.Gtk
        parent = self.windows[self.current]
        method = r["method"]
        kind = r.get("kind")
        prompt = str(r.get("prompt", ""))
        if method == "ask" and kind in {"file", "directory"}:
            dialog = Gtk.FileChooserNative(
                title=prompt,
                transient_for=parent,
                action=Gtk.FileChooserAction.SELECT_FOLDER
                if kind == "directory"
                else Gtk.FileChooserAction.OPEN,
                accept_label=tr("Select"),
                cancel_label=tr("Cancel"),
            )

            def selected(_dialog, response):
                """Return only the chosen local file/folder or a cancellation."""
                file = dialog.get_file()
                accepted = (
                    response == Gtk.ResponseType.ACCEPT
                    and file is not None
                    and file.get_path() is not None
                )
                self.reply(
                    r["id"],
                    file.get_path() if accepted else None,
                    ok=accepted,
                    cancelled=not accepted,
                )
                self.dialogs.discard(dialog)
                dialog.destroy()

            dialog.connect("response", selected)
            self.dialogs.add(dialog)
            dialog.show()
            return
        dialog = Gtk.Dialog(title=self.project.name, transient_for=parent, modal=True)
        dialog.set_default_size(420, 180)
        box = dialog.get_content_area()
        box.set_spacing(12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, "set_margin_" + side)(18)
        box.append(Gtk.Label(label=prompt, wrap=True, xalign=0))
        field = None
        if method == "ask":
            if kind == "text":
                field = Gtk.Entry()
                box.append(field)
            elif kind == "choice":
                if not r.get("options") or any(not isinstance(v, str) for v in r["options"]):
                    raise ValueError(tr("Provide text options."))
                field = Gtk.DropDown.new_from_strings(r["options"])
                box.append(field)
            else:
                raise ValueError(tr("Unknown question type."))
        if method != "message":
            dialog.add_button(
                tr("No") if method == "confirm" else tr("Cancel"), Gtk.ResponseType.CANCEL
            )
        dialog.add_button(
            tr("Yes") if method == "confirm" else tr("Continue") if method == "ask" else tr("OK"),
            Gtk.ResponseType.OK,
        )

        def finished(_dialog, response):
            """Unblock the worker only after an explicit user answer."""
            accepted = response == Gtk.ResponseType.OK
            value = None
            if accepted and method == "ask":
                value = field.get_text() if kind == "text" else r["options"][field.get_selected()]
            elif method == "confirm":
                value = accepted
            self.reply(r["id"], value, ok=accepted, cancelled=not accepted)
            self.dialogs.discard(dialog)
            dialog.destroy()

        dialog.connect("response", finished)
        self.dialogs.add(dialog)
        dialog.present()
        self.emit("status", text=tr("Waiting for an answer…"))

    def run_task(self, r):
        """Run argv with no implicit shell, optional Polkit and incremental output."""
        if self.task:
            raise ValueError(tr("A task is already running."))
        program = r["program"]
        args = r["arguments"]
        admin = r.get("admin", False)
        if (
            not isinstance(program, str)
            or not program.strip()
            or "\0" in program
            or not isinstance(args, list)
            or len(args) > 256
            or any(not isinstance(v, str) or "\0" in v for v in args)
        ):
            raise ValueError(tr("Invalid program/arguments."))
        executable = (
            str((self.root / program).resolve()) if "/" in program else shutil.which(program)
        )
        if not executable:
            raise ValueError(tr("Program not found: {program}.").format(program=program))
        if admin:
            pkexec = shutil.which("pkexec")
            if not pkexec:
                raise ValueError(tr("pkexec is not available on the target system."))
            args = ["--disable-internal-agent", executable, *args]
            executable = pkexec
        from makebench.terminal.environment import external_environment

        task = subprocess.Popen(
            [executable, *args],
            env=external_environment(executable),
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            bufsize=0,
        )
        self.task = task
        self.admin = admin
        started = time.monotonic()
        self.emit("admin", value=admin)
        self.emit("task", id=r["id"], program=program, admin=admin, state="running", duration=0)

        def wait():
            """Wait for the task in a thread and keep both channels flowing until EOF."""
            readers = [
                threading.Thread(target=self.read_channel, args=(pipe, ch), daemon=True)
                for pipe, ch in ((task.stdout, "stdout"), (task.stderr, "stderr"))
            ]
            for reader in readers:
                reader.start()
            code = task.wait()
            for reader in readers:
                reader.join()
            self.GLib.idle_add(self.task_done, r, code, started)

        threading.Thread(target=wait, daemon=True).start()

    def task_done(self, r, code, started):
        """The exit code decides success; administrative 126/127 do not promise completion."""
        self.task = None
        self.admin = False
        self.emit("admin", value=False)
        self.emit(
            "task",
            id=r["id"],
            program=r["program"],
            admin=r.get("admin", False),
            state="completed" if code == 0 else "failed",
            duration=time.monotonic() - started,
        )
        if not self.stopping:
            if r.get("admin") and code in (126, 127):
                self.reply(
                    r["id"],
                    ok=False,
                    cancelled=code == 126,
                    error=tr("Administrative task not completed (code {code}).").format(code=code),
                )
            else:
                self.reply(r["id"], {"code": code, "crashed": code < 0})
        if self.process and self.process.poll() is not None:
            self.stop()

    def worker_finished(self):
        """Never abandon an administrative task if the worker ends unexpectedly."""
        if not self.stopping:
            self.emit("error", message=tr("The Python process ended."))
        if not self.admin:
            self.stop()

    def stop(self):
        """Cancel ordinary groups and wait for cleanup; an administrative task blocks."""
        if self.admin:
            self.emit("status", text=tr("Wait for the administrative task to finish."))
            return False
        if self.stopping:
            return False
        self.stopping = True
        self.active = False
        from makebench.terminal.components import stop_components

        for view in self.views.values():
            stop_components(view.widgets)
        for dialog in list(self.dialogs):
            dialog.destroy()
        self.dialogs.clear()
        terminate_group(self.process)
        terminate_group(self.task)
        self.GLib.timeout_add(700, self.finish_stop)
        return False

    def finish_stop(self):
        """Force only ordinary user groups and end after reaping the children."""
        terminate_group(self.process, True)
        terminate_group(self.task, True)
        if self.process:
            try:
                self.process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                return True
        if self.task and self.task.poll() is None:
            return True
        for window in self.windows.values():
            window.destroy()
        self.emit("stopped")
        self.app.release()
        self.app.quit()
        return False
