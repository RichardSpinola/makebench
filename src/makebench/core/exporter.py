# SPDX-License-Identifier: MIT
"""Real export of portable Python source, never running project functions."""

import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from .codegen import generate
from .project import ProjectError
from makebench.i18n import tr


class BuildCancelled(ProjectError):
    """Build interrupted before publishing any partial result."""


def effects(project):
    """Inspect declared programs and privileges; never runs blocks or imports."""
    programs = set()
    admin = False

    def visit(value):
        """Walk structured data without running project content."""
        nonlocal admin
        if isinstance(value, dict):
            if value.get("op") in {"run", "script"}:
                admin = admin or value.get("admin", False)
                program = value.get("program", {})
                if value["op"] == "script":
                    programs.add("/bin/bash")
                elif program.get("op") == "literal" and isinstance(program.get("value"), str):
                    programs.add(program["value"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for flow in project.editable_flows:
        visit(flow.get("body"))
    return sorted(programs), admin


def verify(project, source, read_asset):
    """Return export blockers and warnings; opening/saving never triggers execution."""
    app = project.application
    issues = []

    def add(level, message, field):
        """Record a diagnostic with severity and source field."""
        issues.append({"level": level, "message": message, "field": field})

    if project.metadata.get("empty_map"):
        add("error", tr("Create the first interface in the map before exporting."), "windows")
    if not str(app.get("name", "")).strip():
        add("error", tr("Enter the application's public name."), "name")
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*){2,}", app.get("id", "")):
        add("error", tr("Use an identifier such as com.example.myapp."), "id")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", app.get("version", "")):
        add("error", tr("Enter the version, for example 0.1.0."), "version")
    icon = app.get("icon", "")
    if not icon:
        add("error", tr("Choose the application icon."), "icon")
    else:
        try:
            data = read_asset(icon)
            if icon.lower().endswith(".png"):
                if (
                    data[:8] != b"\x89PNG\r\n\x1a\n"
                    or len(data) < 24
                    or min(struct.unpack(">II", data[16:24])) < 256
                ):
                    raise ValueError(tr("Use a PNG of at least 256 × 256 pixels."))
            elif icon.lower().endswith(".svg"):
                if ET.fromstring(data).tag.split("}")[-1] != "svg":
                    raise ValueError(tr("The file is not an SVG."))
            else:
                raise ValueError(tr("Use a PNG or SVG icon."))
        except (OSError, ValueError, ProjectError, ET.ParseError) as exc:
            add("error", tr("Invalid icon: {error}").format(error=exc), "icon")
    from .source import source_files, ENTRY_FILE

    if set(source_files(source)) - {ENTRY_FILE} != set(project.python_files):
        add(
            "error",
            tr(
                "The manifest and the modules do not match. Reopen the project to review the files."
            ),
            "python",
        )
    for message in generate(project, source).diagnostics:
        add("error", message, "logic")
    for name in project.asset_paths():
        try:
            read_asset(name)
        except (OSError, ProjectError) as exc:
            add("error", tr("Missing asset: {name}").format(name=name), "assets")
    for dependency in app.get("packages", []):
        if not isinstance(dependency, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!_-]+(?:,[<>=!~]=?[A-Za-z0-9.*+!_-]+)*)?",
            dependency,
        ):
            add(
                "error", tr("Invalid Python dependency: {name}").format(name=dependency), "packages"
            )
    from .build_environment import flatpak_requirements

    try:
        flatpak_requirements(project)
    except ProjectError as exc:
        add("error", str(exc), "packages")
    programs, admin = effects(project)
    for program in programs:
        add(
            "warning",
            tr("The target needs the program {program}.").format(program=program),
            "dependencies",
        )
    if admin:
        add(
            "warning",
            tr(
                "Administrative actions require Polkit/pkexec and an authentication agent on the target system."
            ),
            "permissions",
        )
    if not any(i["level"] == "error" for i in issues):
        add("success", tr("Project ready to export as Python source."), "")
    return issues


QT_RUNNER = '''"""Application exported by Makebench. Starting it runs the project's code."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from makebench.core.storage import load_project
from makebench.i18n import set_language
from makebench.core.source import SourceBuffer
from makebench.runtime.window import RuntimeWindow
from makebench.ui.dialogs import install_translation


def main():
    """Start Qt and run the exported project only when the application opens."""
    root=Path(__file__).resolve().parent
    from PySide6.QtCore import Qt
    # Web view windows use Qt WebEngine, which needs shared contexts set before the app.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication(sys.argv)
    install_translation(app)
    path=root/'project.makebench.json'
    project=load_project(path)
    set_language(project.application.get('language'))
    app.setApplicationName(project.application['name'])
    source=SourceBuffer.load(path)
    window=RuntimeWindow(project,source.text,lambda name:(root/name).read_bytes(),root,source.path,supervision=False)
    window.shutdown_finished.connect(app.quit)
    window.show()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0,window.start)
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
'''


GTK_RUNNER = r'''"""Exported GTK application. Starting it runs the project's code."""
from pathlib import Path
from makebench.core.storage import load_project
from makebench.i18n import set_language
from makebench.core.source import SourceBuffer
from makebench.gtk_runtime.application import GtkRuntime


def main():
    """Start real GTK controls, with no editor and no Qt dependency."""
    root=Path(__file__).resolve().parent;path=root/'project.makebench.json'
    project=load_project(path);set_language(project.application.get('language'))
    return GtkRuntime(project,SourceBuffer.load(path).text,lambda name:(root/name).read_bytes(),root,root/'project.actions.py',lambda message:print(message.get('text',message.get('message','')),end='' if message.get('type')=='log' else '\n') if message.get('type') in {'log','error'} else None).run()


if __name__=='__main__':raise SystemExit(main())
'''
RUNNER = QT_RUNNER


def export_source(project, source, read_asset, destination, progress=None, cancelled=None):
    """Build a ZIP in staging, include the minimal runtime and move it only on success.

    destination is never overwritten. Returns path, size and SHA-256. The runtime
    uses only Qt Widgets; Blockly and the editor tools are left out.
    """
    destination = Path(destination)
    if destination.exists():
        raise ProjectError(
            tr("The destination already exists. Choose another name to keep that file.")
        )
    issues = verify(project, source, read_asset)
    errors = [i["message"] for i in issues if i["level"] == "error"]
    if errors:
        raise ProjectError("\n".join(errors))

    def step(number, text):
        """Report progress and honor cancellation before the next operation."""
        if cancelled and cancelled():
            raise BuildCancelled(tr("Build cancelled."))
        if progress:
            progress(number, text)

    package_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix=".makebench-build-", dir=destination.parent
    ) as directory:
        stage = Path(directory) / "app"
        stage.mkdir()
        step(5, tr("Prepare files"))
        (stage / "project.makebench.json").write_text(
            json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (stage / "project.actions.py").write_text(source, encoding="utf-8")
        from .source import source_files, ENTRY_FILE

        files = source_files(source)
        if set(files) - {ENTRY_FILE} != set(project.python_files):
            raise ProjectError(tr("The manifest and the modules do not match."))
        for name, text in files.items():
            if name != ENTRY_FILE:
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        (stage / "generated.py").write_text(generate(project, source).text, encoding="utf-8")
        for name in sorted(project.asset_paths()):
            step(20, tr("Copy asset {name}").format(name=name))
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read_asset(name))
        step(40, tr("Include the application runtime"))
        target = stage / "makebench"
        target.mkdir()
        shutil.copy2(package_root / "__init__.py", target / "__init__.py")
        shutil.copy2(package_root / "i18n.py", target / "i18n.py")
        shutil.copytree(package_root / "locale", target / "locale")
        backend = project.application.get("backend", "qt")
        for module in (
            ("core", "gtk_runtime", "terminal", "portable")
            if backend == "gtk"
            else ("core", "runtime", "ui", "terminal", "portable")
        ):
            (target / module).mkdir()
            for path in sorted((package_root / module).glob("*.py")):
                shutil.copy2(path, target / module / path.name)
        if backend == "gtk":
            (target / "runtime").mkdir()
            shutil.copy2(
                package_root / "runtime" / "__init__.py", target / "runtime" / "__init__.py"
            )
            shutil.copy2(package_root / "runtime" / "worker.py", target / "runtime" / "worker.py")
            shutil.copy2(
                package_root / "runtime" / "debugger.py", target / "runtime" / "debugger.py"
            )
        shutil.copytree(package_root / "notices", target / "notices")
        (stage / "run.py").write_text(
            GTK_RUNNER if backend == "gtk" else QT_RUNNER, encoding="utf-8"
        )
        dependencies = [
            "pyte==0.8.2",
            *(["PyGObject>=3.48"] if backend == "gtk" else ["PySide6==6.11.2"]),
            *project.application.get("packages", []),
        ]
        from .compatibility import minimum_minor

        python_minor = minimum_minor(source) or 14
        (stage / "runtime-requirements.json").write_text(
            json.dumps(
                {"python": f">=3.{python_minor}", "backend": backend, "dependencies": dependencies},
                indent=2,
            ),
            encoding="utf-8",
        )
        (stage / "requirements.txt").write_text("\n".join(dependencies) + "\n", encoding="utf-8")
        (stage / "README.txt").write_text(
            tr(
                "Application exported by Makebench.\nRequires Linux, Python 3.{minor}+ and the dependencies in requirements.txt. GTK also requires the system's GTK4 and PyGObject; libadwaita is optional.\nCreate a Python environment, install requirements.txt and run python3 run.py.\nStarting it runs the project's functions and scripts with your permissions.\nThe runtime ships with the application; the editor's supervision does not appear.\nExternal programs and Polkit must be available on the target system.\nThe bundled Makebench runtime is under the MIT license (see makebench/notices), so you may choose the license of your application. Choose it before distributing the application publicly.\n"
            ).format(minor=python_minor),
            encoding="utf-8",
        )
        step(75, tr("Check sources without running them"))
        for path in stage.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        zip_path = Path(directory) / "result.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                step(85, tr("Compress {path}").format(path=path.relative_to(stage)))
                if path.is_file():
                    archive.write(path, path.relative_to(stage))
        step(95, tr("Finish result"))
        # An exclusive link avoids an overwrite race; staging uses the same volume.
        import os

        try:
            os.link(zip_path, destination)
        except FileExistsError:
            raise ProjectError(
                tr("The destination was created by another process; choose another name.")
            )
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    if progress:
        progress(100, tr("Python source exported"))
    return {"path": str(destination), "size": destination.stat().st_size, "sha256": digest}
