"""Aceitação real Qt/GTK: prévia inerte, terminal, pilha, teclas e encerramento."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    """Executa o exemplo versionado em display real; salva evidências e resultados."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("qt", "gtk"), required=True)
    parser.add_argument("--theme", choices=("light", "dark"), default="dark")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from makebench.core.storage import load_project
    from makebench.core.source import SourceBuffer

    path = (
        Path(__file__).resolve().parents[1]
        / "examples/terminal-debug"
        / f"{args.backend}.makebench.json"
    )
    project = load_project(path)
    source = SourceBuffer.load(path).text
    button = next(n for n in project.walk() if n.kind.value == "button")
    results = []
    pauses = []
    errors = []
    config = {"enabled": True, "breakpoints": [{"file": "source", "line": 10}]}

    def observe(message, send):
        """A primeira parada entra na função e a segunda alcança a linha própria."""
        if message.get("type") == "error":
            errors.append(message)
        if message.get("type") == "debug" and message.get("state") == "paused":
            pauses.append(message)
            if len(pauses) == 1:
                send("step_in")
            else:
                send("continue")

    with tempfile.TemporaryDirectory(prefix="makebench-terminal-acceptance-") as directory:
        root = Path(directory)
        if args.backend == "qt":
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication
            from native_palette import kde_palette
            from makebench.ui.renderer import create_control
            from makebench.runtime.window import RuntimeWindow

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            app.setPalette(kde_palette(args.theme))
            component = next(n for n in project.walk() if n.kind.value == "terminal")
            preview = create_control(component, lambda _: b"", editing=True)
            preview.show()
            QTest.qWait(30)
            assert not preview.terminal.running
            assert preview.start_terminal() is None
            preview.close()
            results.append("Prévia sem processos")
            window = RuntimeWindow(
                project,
                source,
                lambda _: b"",
                root,
                path.with_suffix(".actions.py"),
                supervision=False,
            )
            window.session.snapshot["debug"] = config

            def wait(predicate, seconds=10):
                """Aguarda observação real processando eventos nativos."""
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    QTest.qWait(20)
                    if errors:
                        raise AssertionError(errors)
                    if predicate():
                        return
                raise AssertionError("Prazo excedido")

            done = []
            window.session.event_done.connect(done.append)
            window.session.error.connect(errors.append)
            window.session.debug_changed.connect(lambda m: observe(m, window.session.debug_command))
            window.show()
            window.start()
            wait(lambda: window.session.active)
            window.view.widgets[button.id].click()
            wait(lambda: bool(done))
            terminal = window.widget_for("terminal")[1]
            wait(
                lambda: (
                    "TERMINAL PRONTO" in [line.strip() for line in terminal.terminal.screen.display]
                )
            )
            terminal.setFocus()
            QTest.keyClicks(terminal, "print('ENTRADA_REAL')")
            QTest.keyClick(terminal, Qt.Key.Key_Return)
            wait(
                lambda: (
                    "ENTRADA_REAL" in [line.strip() for line in terminal.terminal.screen.display]
                )
            )
            actual_scale = window.devicePixelRatioF()
            window.grab().save(str(args.output / "runtime.png"))
            results.extend(["Python interativo Qt", "Teclado real Qt"])
            window.stop()
            wait(lambda: window.session.closed)
            assert not terminal.terminal.running
            window.close()
        else:
            import gi

            for name, version in [("Gtk", "4.0"), ("Graphene", "1.0"), ("Adw", "1")]:
                gi.require_version(name, version)
            from gi.repository import Gtk, GLib, Graphene, Adw, Gdk
            from makebench.gtk_runtime.renderer import GtkView
            from makebench.gtk_runtime.application import GtkRuntime

            Adw.init()
            Adw.StyleManager.get_default().set_color_scheme(
                Adw.ColorScheme.FORCE_DARK if args.theme == "dark" else Adw.ColorScheme.FORCE_LIGHT
            )
            preview = GtkView(project.root, lambda _: b"", lambda _: None)
            assert not next(
                w for w in preview.widgets.values() if hasattr(w, "terminal")
            ).terminal.running
            results.append("Prévia sem processos")
            runtime = None
            deadline = time.monotonic() + 20
            phase = {"clicked": False, "done": False, "typed": False, "capture": False}

            def observer(message):
                """Observa os mesmos comandos e estados entregues à ponte do editor."""
                observe(message, lambda action: runtime.send({"type": "debug", "action": action}))
                if message["type"] == "done":
                    phase["done"] = True

            runtime = GtkRuntime(
                project, source, lambda _: b"", root, path.with_suffix(".actions.py"), observer
            )
            runtime.debug_config = config

            def poll():
                """Interage com terminal GTK e captura a janela real após o evento."""
                try:
                    if errors:
                        raise AssertionError(errors)
                    if time.monotonic() > deadline:
                        raise AssertionError("Prazo GTK excedido")
                    if runtime.active and not phase["clicked"]:
                        phase["clicked"] = True
                        runtime.queue_event(button.id)
                    if phase["done"]:
                        terminal = next(
                            w
                            for view in runtime.views.values()
                            for w in view.widgets.values()
                            if hasattr(w, "terminal")
                        )
                        text = [line.strip() for line in terminal.terminal.screen.display]
                        if "TERMINAL PRONTO" in text and not phase["typed"]:
                            phase["typed"] = True
                            terminal.send_terminal("print('ENTRADA_REAL')\n")
                        if phase["typed"] and "ENTRADA_REAL" in text:
                            window = runtime.windows[runtime.current]
                            width, height = window.get_width(), window.get_height()
                            paintable = Gtk.WidgetPaintable.new(window)
                            snapshot = Gtk.Snapshot.new()
                            paintable.snapshot(snapshot, width, height)
                            texture = window.get_renderer().render_texture(
                                snapshot.to_node(), Graphene.Rect().init(0, 0, width, height)
                            )
                            assert texture.save_to_png(str(args.output / "runtime.png"))
                            phase["actual_scale"] = window.get_surface().get_scale()
                            runtime.stop()
                            results.extend(["Python interativo GTK", "Entrada e saída GTK"])
                            assert not terminal.terminal.running
                            return False
                except BaseException as exc:
                    errors.append(str(exc))
                    runtime.stop()
                    return False
                return True

            GLib.timeout_add(40, poll)
            runtime.run()
        assert not errors, errors
        assert len(pauses) >= 3, pauses
        assert pauses[0].get("block") == "call_demo"
        assert pauses[1].get("source_line") == 6
        assert pauses[-1].get("source_line") == 10
        assert pauses[-1]["stack"][0]["variables"]["resultado"] == "TERMINAL PRONTO"
        results.extend(
            [
                "Ponto em bloco",
                "Entrar na função Python",
                "Ponto em linha própria",
                "Pilha e valores somente leitura",
                "Fechamento recolhe processos",
            ]
        )
        (args.output / "results.json").write_text(
            json.dumps(
                {
                    "backend": args.backend,
                    "theme": args.theme,
                    "requested_qt_scale": os.environ.get("QT_SCALE_FACTOR", "1"),
                    "actual_scale": actual_scale
                    if args.backend == "qt"
                    else phase.get("actual_scale"),
                    "results": results,
                    "pauses": pauses,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("OK", args.backend, len(results), "cenários")


if __name__ == "__main__":
    main()
