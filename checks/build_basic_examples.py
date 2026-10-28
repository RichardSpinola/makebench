# SPDX-License-Identifier: MIT
"""Rebuild the four basic examples twice: with block functions and as Python.

Each example keeps its folder (now fully in blocks) and gains a `<name>-python`
folder produced by "Convert to Python". Run from the repository root:
PYTHONPATH=src .venv/bin/python checks/build_basic_examples.py
"""

import shutil
import sys
from copy import deepcopy
from pathlib import Path

from build_full_examples import Ids, block_stmt

from makebench.core.assets import AssetStore
from makebench.core.codegen import convert_to_python
from makebench.core.source import SourceBuffer, SourceText
from makebench.core.storage import load_project, save_workspace

ROOT = Path(__file__).resolve().parents[1]


def lit(value):
    return ("lit", value)


def local(name):
    return ("local", name)


def join(*parts):
    result = parts[0]
    for part in parts[1:]:
        result = ("join", result, part)
    return result


NOTHING = ("list", [])

# Per language: old Python function name -> (new block function, parameter, steps).
# Every flow that called the Python function now calls the block function.
SPECS = {
    "pt": {
        "welcome/project": {
            "apresentar": (
                "apresentar",
                ["valor"],
                [
                    (
                        "if",
                        ("bin", "==", local("valor"), lit("")),
                        [
                            (
                                "log",
                                join(
                                    lit("Olá, "), lit("visitante"), lit("! Bem-vindo ao seu Linux.")
                                ),
                            )
                        ],
                        [
                            (
                                "log",
                                join(
                                    lit("Olá, "), local("valor"), lit("! Bem-vindo ao seu Linux.")
                                ),
                            )
                        ],
                    )
                ],
            )
        },
        "script-center/app": {
            "simular_instalacao": (
                "simular_instalacao",
                ["pacote"],
                [
                    ("log", join(lit("Simulando instalação: "), local("pacote"))),
                    ("set_value", "progress_task", lit(0)),
                    *[
                        step
                        for progress in (20, 40, 60, 80, 100)
                        for step in (
                            ("script", lit("sleep 0.15"), NOTHING),
                            ("set_value", "progress_task", lit(progress)),
                            ("log", lit(f"Progresso: {progress}%")),
                        )
                    ],
                    (
                        "script",
                        lit('printf "Aviso de exemplo; a tarefa termina com sucesso.\\n" >&2'),
                        NOTHING,
                    ),
                    ("log", lit("Simulação concluída. Nenhum aplicativo foi instalado.")),
                ],
            ),
            "tarefa_longa": (
                "tarefa_longa",
                ["valor"],
                [
                    (
                        "script",
                        lit('for i in $(seq 1 60); do echo "Etapa $i/60"; sleep 1; done'),
                        NOTHING,
                    )
                ],
            ),
        },
        "terminal-debug/qt": {
            "iniciar": (
                "iniciar",
                ["valor"],
                [
                    (
                        "terminal_start",
                        "terminal_7b1f01c015ec",
                        lit("python3"),
                        ("list", [lit("-u"), lit("-i"), lit("-q")]),
                    ),
                    (
                        "terminal_send",
                        "terminal_7b1f01c015ec",
                        join(lit("print('"), local("valor"), lit("'.upper())\n")),
                    ),
                    ("log", local("valor")),
                ],
            )
        },
    },
    "en": {
        "welcome/project": {
            "introduce": (
                "introduce",
                ["value"],
                [
                    (
                        "if",
                        ("bin", "==", local("value"), lit("")),
                        [
                            (
                                "log",
                                join(
                                    lit("Hello, "), lit("visitor"), lit("! Welcome to your Linux.")
                                ),
                            )
                        ],
                        [
                            (
                                "log",
                                join(
                                    lit("Hello, "), local("value"), lit("! Welcome to your Linux.")
                                ),
                            )
                        ],
                    )
                ],
            )
        },
        "script-center/app": {
            "simulate_installation": (
                "simulate_installation",
                ["package"],
                [
                    ("log", join(lit("Simulating installation: "), local("package"))),
                    ("set_value", "progress_task", lit(0)),
                    *[
                        step
                        for progress in (20, 40, 60, 80, 100)
                        for step in (
                            ("script", lit("sleep 0.15"), NOTHING),
                            ("set_value", "progress_task", lit(progress)),
                            ("log", lit(f"Progress: {progress}%")),
                        )
                    ],
                    (
                        "script",
                        lit('printf "Example warning; the task still succeeds.\\n" >&2'),
                        NOTHING,
                    ),
                    ("log", lit("Simulation complete. No application was installed.")),
                ],
            ),
            "long_task": (
                "long_task",
                ["value"],
                [
                    (
                        "script",
                        lit('for i in $(seq 1 60); do echo "Step $i/60"; sleep 1; done'),
                        NOTHING,
                    )
                ],
            ),
        },
        "terminal-debug/qt": {
            "start_python": (
                "start_python",
                ["value"],
                [
                    (
                        "terminal_start",
                        "terminal_7b1f01c015ec",
                        lit("python3"),
                        ("list", [lit("-u"), lit("-i"), lit("-q")]),
                    ),
                    (
                        "terminal_send",
                        "terminal_7b1f01c015ec",
                        join(lit("print('"), local("value"), lit("'.upper())\n")),
                    ),
                    ("log", local("value")),
                ],
            )
        },
    },
}
# Examples that have no Python function: only their (unused) actions file is emptied.
PLAIN = {"welcome-states/project"}


COMMENTS = {
    "A função está no arquivo project.actions.py, editável na aba Código.": "A função apresentar é uma função de blocos; veja Lógica › Funções.",
    "The function lives in project.actions.py, editable in the Code tab.": "The introduce function is a block function; see Logic › Functions.",
}


def replace_calls(body, names):
    """Turn each `call` of a Python function into a `call_function` of its block function."""
    for block in body:
        if block.get("op") == "call" and block["function"] in names:
            argument = block.pop("value")
            block["comment"] = COMMENTS.get(block.get("comment"), block.get("comment"))
            if block["comment"] is None:
                del block["comment"]
            block.update(
                op="call_function", function="fn_" + names[block["function"]], args=[argument]
            )
        for key in ("then", "else", "body"):
            if isinstance(block.get(key), list):
                replace_calls(block[key], names)


def to_blocks(project, specs):
    """Define the block functions and point the flows at them."""
    project.metadata["programming"] = "blocks"
    functions = project.metadata.setdefault("functions", [])
    for name, params, steps in specs.values():
        ids = Ids()
        functions.append(
            {
                "id": f"fn_{name}",
                "name": name,
                "params": params,
                "body": [block_stmt(step, ids) for step in steps],
            }
        )
    names = {old: name for old, (name, _, _) in specs.items()}
    for flow in project.workflows:
        replace_calls(flow.get("body", []), names)


def buffer(path, text):
    """A source buffer that may replace the file already beside `path`."""
    source = SourceBuffer.load(path) if path.is_file() else SourceBuffer()
    source.text = SourceText(text)
    return source


def build(language, base):
    """Rewrite one language's examples in place and write their Python twins."""
    table = {**SPECS[language], **{name: {} for name in PLAIN}}
    table["terminal-debug/gtk"] = table["terminal-debug/qt"]
    for key, specs in table.items():
        folder, stem = key.split("/")
        source_dir = base / folder
        path = source_dir / f"{stem}.makebench.json"
        project = load_project(path)
        to_blocks(project, specs)
        blocks = buffer(path, "")
        python = deepcopy(project)
        python_dir = base / f"{folder}-python"
        python_dir.mkdir(exist_ok=True)
        for child in ("graphics",):
            if (source_dir / child).is_dir():
                shutil.copytree(source_dir / child, python_dir / child, dirs_exist_ok=True)
        text = convert_to_python(python, "")
        python_source = buffer(python_dir / path.name, text)
        save_workspace(project, blocks, AssetStore(source_dir), path)
        save_workspace(python, python_source, AssetStore(source_dir), python_dir / path.name)
        print("wrote", path, "and", python_dir / path.name, file=sys.stderr)


if __name__ == "__main__":
    build("pt", ROOT / "examples")
    build("en", ROOT / "examples" / "en")
