"""Medição comparável do Designer com projeto grande, sem scripts de usuário."""

import argparse
import json
import os
from pathlib import Path
import resource
import statistics
import tempfile
import time


def main():
    """Mede seleção, texto e movimento; registra reconstruções, não só tempo total."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    from PySide6.QtWidgets import QApplication
    from makebench.core.project import Project, ComponentKind, LayoutKind
    from makebench.core.navigation import add_window
    from makebench.editor.window import MainWindow

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory() as directory:
        os.environ["XDG_CONFIG_HOME"] = directory
        os.environ["XDG_STATE_HOME"] = directory
        project = Project.empty("Medição")
        project.root.layout = LayoutKind.FREE
        roots = [project.root] + [add_window(project, "Janela " + str(n)) for n in range(7)]
        for root in roots:
            root.layout = LayoutKind.FREE
            for n in range(40):
                button = project.add(root.id, ComponentKind.BUTTON)
                button.geometry.update(x=(n % 4) * 140, y=(n // 4) * 40, width=120, height=32)
        start = time.perf_counter()
        window = MainWindow(project)
        window.recovery_timer.stop()
        window.show()
        window.set_mode("Design")
        app.processEvents()
        opening = time.perf_counter() - start
        rebuild = [0]
        original = window._rebuild_views

        def track():
            """Conta reconstruções sem interferir no resultado do comando original."""
            rebuild[0] += 1
            return original()

        window._rebuild_views = track
        ids = [n.id for n in project.root.children]
        records = {}
        for label, operation in [
            ("selection", lambda n: window._select(ids[n % len(ids)])),
            ("text", lambda n: window._change_property(ids[0], "text", "Texto " + str(n))),
            ("geometry", lambda n: window._commit_geometry(ids[0], {"x": 32 + (n % 2) * 8})),
        ]:
            times = []
            before = rebuild[0]
            for n in range(20):
                started = time.perf_counter()
                operation(n)
                app.processEvents()
                times.append((time.perf_counter() - started) * 1000)
            records[label] = {
                "median_ms": round(statistics.median(times), 3),
                "max_ms": round(max(times), 3),
                "view_rebuilds": rebuild[0] - before,
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "windows": 8,
                    "controls": 320,
                    "opening_seconds": round(opening, 3),
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "operations": records,
                },
                indent=2,
            )
        )
        window.history.mark_saved()
        window.source.mark_saved()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
