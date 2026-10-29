# SPDX-License-Identifier: GPL-3.0-or-later
"""Size and speed limits: editor opening, exported apps, a large table and export size.

Each measurement runs in its own Python process so memory is not shared between them.
Limits live in footprint_limits.json with about twice the size and three times the time
measured on a desktop: slower CI machines pass, while a real regression (a heavy import at
startup, a widget per table cell, Qt WebEngine pulled in by default) still fails.

    python checks/footprint.py                 # measure and compare with the limits
    python checks/footprint.py --write-limits  # measure and store new limits
"""

import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMITS = Path(__file__).with_name("footprint_limits.json")
EXAMPLE = ROOT / "examples/full-blocks/project.makebench.json"


def rss_mb(pid="self"):
    """Resident memory of a process in MB, or 0 when it already ended."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def icon_png(size=256):
    """A plain square PNG, enough for the export's icon checks."""
    row = b"\x00" + b"\x33\x66\xaa\xff" * size
    data = zlib.compress(row * size)

    def chunk(kind, body):
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", data) + chunk(b"IEND", b"")
    )


def export(backend, target):
    """Export the full example as source for one backend; returns the zip path."""
    from makebench.core.exporter import export_source
    from makebench.core.source import SourceBuffer
    from makebench.core.storage import load_project

    project = load_project(EXAMPLE)
    project.application.update(
        backend=backend, name="Footprint", id="org.example.footprint", version="0.1.0"
    )
    project.application["icon"] = "assets/footprint-icon.png"
    icon = icon_png()

    def read(name):
        return icon if name == "assets/footprint-icon.png" else (EXAMPLE.parent / name).read_bytes()

    path = Path(target) / f"{backend}.zip"
    export_source(project, SourceBuffer.load(EXAMPLE).text, read, path)
    return path


def wait(condition, seconds=30):
    from PySide6.QtTest import QTest

    end = time.monotonic() + seconds
    while not condition() and time.monotonic() < end:
        QTest.qWait(5)
    return condition()


def probe_editor():
    start = time.perf_counter()
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from makebench.editor.window import MainWindow

    window = MainWindow()
    window.show()
    app.processEvents()
    return {"editor_open_s": time.perf_counter() - start, "editor_rss_mb": rss_mb()}


def probe_table():
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from makebench.ui.renderer import configure_table, set_table_rows
    from makebench.ui.table import RecordTable

    table = RecordTable()
    configure_table(table, ["Name", "Number", "Date", "Notes"])
    table.show()
    app.processEvents()
    rows = [[f"name {i}", i, "2026-10-29", "x" * 20] for i in range(50_000)]
    before = rss_mb()
    start = time.perf_counter()
    set_table_rows(table, rows)
    app.processEvents()
    return {"table_50k_s": time.perf_counter() - start, "table_50k_mb": rss_mb() - before}


def probe_qt_app(folder):
    """Open the exported Qt app from its own files until its worker is ready."""
    sys.path.insert(0, folder)
    start = time.perf_counter()
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    import makebench

    assert Path(makebench.__file__).is_relative_to(folder), "not the exported runtime"
    from makebench.core.source import SourceBuffer
    from makebench.core.storage import load_project
    from makebench.runtime.window import RuntimeWindow

    root = Path(folder)
    path = root / "project.makebench.json"
    source = SourceBuffer.load(path)
    window = RuntimeWindow(
        load_project(path),
        source.text,
        lambda name: (root / name).read_bytes(),
        root,
        source.path,
        supervision=False,
    )
    window.show()
    window.start()
    if not wait(lambda: window.session.active and not window.session.busy):
        raise RuntimeError("the exported Qt app did not get ready")
    seconds = time.perf_counter() - start
    memory = rss_mb() + rss_mb(int(window.session.process.processId()))
    window.stop()
    wait(lambda: window.session.closed, 10)
    app.processEvents()
    return {"qt_app_open_s": seconds, "qt_app_rss_mb": memory}


def probe_gtk_app(folder):
    """Open the exported GTK app until its worker is ready; needs GTK 4 and a display."""
    sys.path.insert(0, folder)
    start = time.perf_counter()
    from gi.repository import GLib

    from makebench.core.source import SourceBuffer
    from makebench.core.storage import load_project
    from makebench.gtk_runtime.application import GtkRuntime

    root = Path(folder)
    path = root / "project.makebench.json"
    result = {}

    def observe(message):
        if message.get("type") == "ready" and not result:
            result["gtk_app_open_s"] = time.perf_counter() - start
            result["gtk_app_rss_mb"] = rss_mb() + rss_mb(runtime.process.pid)
            GLib.idle_add(runtime.stop)

    runtime = GtkRuntime(
        load_project(path),
        SourceBuffer.load(path).text,
        lambda name: (root / name).read_bytes(),
        root,
        root / "project.actions.py",
        observe,
    )
    GLib.timeout_add_seconds(30, runtime.stop)
    runtime.run()
    if not result:
        raise RuntimeError("the exported GTK app did not get ready")
    return result


def gtk_available():
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        return False
    code = "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; assert Gtk.init_check()"
    return (
        subprocess.run([sys.executable, "-c", code], capture_output=True, check=False).returncode
        == 0
    )


def run_probe(name, *args):
    """Run one probe in a fresh process and return its numbers."""
    environment = dict(os.environ)
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    if name != "gtk_app":
        environment["PYTHONPATH"] = str(ROOT / "src")
    with tempfile.TemporaryDirectory(prefix="makebench-footprint-") as home:
        for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            environment[key] = home
        if name == "gtk_app":
            environment.pop("QT_QPA_PLATFORM")
        done = subprocess.run(
            [sys.executable, __file__, "--probe", name, *args],
            env=environment,
            cwd=args[0] if args else ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    if done.returncode:
        raise RuntimeError(f"{name} failed:\n{done.stderr[-2000:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def measure():
    sys.path.insert(0, str(ROOT / "src"))
    values = {}
    values.update(run_probe("editor"))
    values.update(run_probe("table"))
    with tempfile.TemporaryDirectory(prefix="makebench-footprint-export-") as target:
        for backend in ("qt", "gtk"):
            path = export(backend, target)
            values[f"{backend}_zip_kb"] = path.stat().st_size / 1024
            folder = Path(target) / backend
            with zipfile.ZipFile(path) as archive:
                archive.extractall(folder)
                requirements = archive.read("requirements.txt").decode().split()
            print(f"{backend} requirements: {' '.join(requirements) or '(none)'}")
            if backend == "qt" and any(
                r.startswith(("PySide6==", "PySide6-Addons")) for r in requirements
            ):
                raise SystemExit("The Qt export requires Qt WebEngine without a Web view window.")
            if backend == "qt":
                values.update(run_probe("qt_app", str(folder)))
            elif gtk_available():
                values.update(run_probe("gtk_app", str(folder)))
            else:
                print("GTK 4 or a display is missing: the GTK app is not measured.")
    return values


def main():
    if "--probe" in sys.argv:
        name = sys.argv[sys.argv.index("--probe") + 1]
        args = sys.argv[sys.argv.index("--probe") + 2 :]
        print(json.dumps(globals()["probe_" + name](*args)), flush=True)
        os._exit(0)  # skip Qt teardown; the numbers are already out
    values = measure()
    if "--write-limits" in sys.argv:
        # CI machines start Python and Qt much slower than a desktop; sizes vary less.
        limits = {
            key: round(value * (3 if key.endswith("_s") else 2) + 1, 1)
            for key, value in sorted(values.items())
        }
        LIMITS.write_text(json.dumps(limits, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {LIMITS.name}.")
    limits = json.loads(LIMITS.read_text(encoding="utf-8"))
    failed = False
    for key, value in sorted(values.items()):
        limit = limits.get(key)
        over = limit is not None and value > limit
        failed |= over
        print(f"{'OVER' if over else 'ok':4} {key:16} {value:9.2f}   limit {limit}")
    if failed:
        raise SystemExit("A size or speed limit was passed.")


if __name__ == "__main__":
    main()
