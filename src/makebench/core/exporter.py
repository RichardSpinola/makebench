"""Exportação real de fonte Python portátil, sem executar funções do projeto."""

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


class BuildCancelled(ProjectError):
    """Construção interrompida antes de publicar qualquer resultado parcial."""


def effects(project):
    """Inspeciona programas e privilégios declarados; não executa blocos ou imports."""
    programs = set()
    admin = False

    def visit(value):
        """Percorre dados estruturados sem executar conteúdo do projeto."""
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
        if flow.get("editor") == "nodes":
            for node in flow["graph"]["nodes"]:
                if node["op"] in {"run", "script"}:
                    admin = admin or node.get("parameters", {}).get("admin", False)
                    key = "program" if node["op"] == "run" else "source"
                    binding = node.get("inputs", {}).get(key, {})
                    if node["op"] == "script":
                        programs.add("/bin/bash")
                    elif isinstance(binding.get("value"), str):
                        programs.add(binding["value"])
        else:
            visit(flow.get("body"))
    return sorted(programs), admin


def verify(project, source, read_asset):
    """Retorna impedimentos e avisos de exportação; abrir/salvar não chama execução."""
    app = project.application
    issues = []

    def add(level, message, field):
        """Registra um diagnóstico com severidade e campo de origem."""
        issues.append({"level": level, "message": message, "field": field})

    if project.metadata.get("empty_map"):
        add("error", "Crie a primeira interface no mapa antes de exportar.", "windows")
    if not str(app.get("name", "")).strip():
        add("error", "Informe o nome público do aplicativo.", "name")
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*){2,}", app.get("id", "")):
        add("error", "Use um identificador como br.exemplo.meuapp.", "id")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", app.get("version", "")):
        add("error", "Informe a versão, por exemplo 0.1.0.", "version")
    icon = app.get("icon", "")
    if not icon:
        add("error", "Escolha o ícone do aplicativo.", "icon")
    else:
        try:
            data = read_asset(icon)
            if icon.lower().endswith(".png"):
                if (
                    data[:8] != b"\x89PNG\r\n\x1a\n"
                    or len(data) < 24
                    or min(struct.unpack(">II", data[16:24])) < 256
                ):
                    raise ValueError("Use PNG de pelo menos 256 × 256 pixels.")
            elif icon.lower().endswith(".svg"):
                if ET.fromstring(data).tag.split("}")[-1] != "svg":
                    raise ValueError("O arquivo não é SVG.")
            else:
                raise ValueError("Use um ícone PNG ou SVG.")
        except (OSError, ValueError, ProjectError, ET.ParseError) as exc:
            add("error", "Ícone inválido: " + str(exc), "icon")
    from .source import source_files, ENTRY_FILE

    if set(source_files(source)) - {ENTRY_FILE} != set(project.python_files):
        add(
            "error",
            "O manifesto e os módulos não correspondem. Reabra o projeto para revisar os arquivos.",
            "python",
        )
    for message in generate(project, source).diagnostics:
        add("error", message, "logic")
    for name in project.asset_paths():
        try:
            read_asset(name)
        except (OSError, ProjectError) as exc:
            add("error", "Recurso ausente: " + name, "assets")
    for dependency in app.get("packages", []):
        if not isinstance(dependency, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!_-]+(?:,[<>=!~]=?[A-Za-z0-9.*+!_-]+)*)?",
            dependency,
        ):
            add("error", "Dependência Python inválida: " + str(dependency), "packages")
    from .build_environment import flatpak_requirements

    try:
        flatpak_requirements(project)
    except ProjectError as exc:
        add("error", str(exc), "packages")
    programs, admin = effects(project)
    for program in programs:
        add("warning", "O destino precisa do programa " + program + ".", "dependencies")
    if admin:
        add(
            "warning",
            "Ações administrativas exigem Polkit/pkexec e agente de autenticação no sistema de destino.",
            "permissions",
        )
    if not any(i["level"] == "error" for i in issues):
        add("success", "Projeto pronto para exportar em fonte Python.", "")
    return issues


QT_RUNNER = '''"""Aplicativo exportado pelo Makebench. Iniciar executa o código do projeto."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from makebench.core.storage import load_project
from makebench.core.source import SourceBuffer
from makebench.runtime.window import RuntimeWindow
from makebench.ui.dialogs import install_translation


def main():
    """Inicia Qt e executa o projeto exportado somente ao abrir o aplicativo."""
    root=Path(__file__).resolve().parent
    app=QApplication(sys.argv)
    install_translation(app)
    path=root/'project.makebench.json'
    project=load_project(path)
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


GTK_RUNNER = r'''"""Aplicativo GTK exportado. Iniciar executa o código do projeto."""
from pathlib import Path
from makebench.core.storage import load_project
from makebench.core.source import SourceBuffer
from makebench.gtk_runtime.application import GtkRuntime


def main():
    """Inicia controles GTK reais, sem editor nem dependência de Qt."""
    root=Path(__file__).resolve().parent;path=root/'project.makebench.json'
    return GtkRuntime(load_project(path),SourceBuffer.load(path).text,lambda name:(root/name).read_bytes(),root,root/'project.actions.py',lambda message:print(message.get('text',message.get('message','')),end='' if message.get('type')=='log' else '\n') if message.get('type') in {'log','error'} else None).run()


if __name__=='__main__':raise SystemExit(main())
'''
RUNNER = QT_RUNNER


def export_source(project, source, read_asset, destination, progress=None, cancelled=None):
    """Constrói ZIP em staging, inclui runtime mínimo e só move após sucesso.

    destination não é sobrescrito. Retorna caminho, tamanho e SHA-256. O runtime
    usa apenas Qt Widgets; Blockly e as ferramentas do editor ficam de fora.
    """
    destination = Path(destination)
    if destination.exists():
        raise ProjectError("O destino já existe. Escolha outro nome para preservar esse arquivo.")
    issues = verify(project, source, read_asset)
    errors = [i["message"] for i in issues if i["level"] == "error"]
    if errors:
        raise ProjectError("\n".join(errors))

    def step(number, text):
        """Notifica progresso e atende cancelamento antes da próxima operação."""
        if cancelled and cancelled():
            raise BuildCancelled("Construção cancelada.")
        if progress:
            progress(number, text)

    package_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix=".makebench-build-", dir=destination.parent
    ) as directory:
        stage = Path(directory) / "app"
        stage.mkdir()
        step(5, "Preparar arquivos")
        (stage / "project.makebench.json").write_text(
            json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (stage / "project.actions.py").write_text(source, encoding="utf-8")
        from .source import source_files, ENTRY_FILE

        files = source_files(source)
        if set(files) - {ENTRY_FILE} != set(project.python_files):
            raise ProjectError("O manifesto e os módulos não correspondem.")
        for name, text in files.items():
            if name != ENTRY_FILE:
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        (stage / "gerado.py").write_text(generate(project, source).text, encoding="utf-8")
        for name in sorted(project.asset_paths()):
            step(20, "Copiar recurso " + name)
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read_asset(name))
        step(40, "Incluir runtime do aplicativo")
        target = stage / "makebench"
        target.mkdir()
        shutil.copy2(package_root / "__init__.py", target / "__init__.py")
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
        (stage / "LEIA-ME.txt").write_text(
            f"Aplicativo exportado pelo Makebench.\nRequer Linux, Python 3.{python_minor}+ e as dependências de requirements.txt. GTK exige também GTK4 e PyGObject do sistema; libadwaita é opcional.\nCrie um ambiente Python, instale requirements.txt e execute python3 run.py.\nIniciar executa as funções e scripts do projeto com suas permissões.\nO runtime acompanha o aplicativo; a supervisão do editor não aparece.\nProgramas externos e Polkit devem estar disponíveis no sistema de destino.\nDefina a licença do seu aplicativo antes de distribuí-lo publicamente.\n",
            encoding="utf-8",
        )
        step(75, "Verificar fontes sem executá-las")
        for path in stage.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        zip_path = Path(directory) / "result.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                step(85, "Compactar " + str(path.relative_to(stage)))
                if path.is_file():
                    archive.write(path, path.relative_to(stage))
        step(95, "Finalizar resultado")
        # Link exclusivo evita corrida de sobrescrita; staging usa o mesmo volume.
        import os

        try:
            os.link(zip_path, destination)
        except FileExistsError:
            raise ProjectError("O destino foi criado por outro processo; escolha outro nome.")
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    if progress:
        progress(100, "Fonte Python exportada")
    return {"path": str(destination), "size": destination.stat().st_size, "sha256": digest}
