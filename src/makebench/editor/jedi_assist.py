# SPDX-License-Identifier: GPL-3.0-or-later
"""Python help from Jedi: suggestions, signatures, definitions and renaming.

Jedi reads the code statically; it never runs the project's own modules. When Jedi is
missing every function returns an empty answer and the built-in index keeps working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    import jedi
    from jedi.api.environment import InterpreterEnvironment
except ImportError:  # the editor still works with the built-in index
    jedi = None

STUBS = Path(__file__).with_name("stubs")
PREAMBLE = "from makebench_ctx import Context as _MakebenchContext\n"
CTX_PARAMETER = re.compile(r"(\bdef\s+\w+\s*\(\s*)ctx(\s*[,)])")

SNIPPETS = {
    "on_click": 'def on_click(ctx, value):\n    ctx.message("Clicked")\n',
    "read_file": 'with open("file.txt", encoding="utf-8") as handle:\n    text = handle.read()\n',
    "run_task": 'ctx.run("echo", ["hello"])\n',
    "show_dialog": 'if ctx.confirm("Continue?"):\n    ctx.message("Done")\n',
}


@dataclass
class Suggestion:
    name: str
    kind: str
    detail: str
    doc: str = ""


@dataclass
class Target:
    path: Path | None
    line: int
    column: int


def available() -> bool:
    """Whether Jedi can be imported in this editor."""
    return jedi is not None


def _prepare(source: str, line: int):
    """Type `ctx` for Jedi without moving the caret: only other lines change."""
    lines = source.split("\n")
    for index, text in enumerate(lines):
        if index != line - 1:
            lines[index] = CTX_PARAMETER.sub(r"\1ctx: _MakebenchContext\2", text)
    return PREAMBLE + "\n".join(lines)


def _script(source: str, root: Path, path: Path | None, line: int):
    jedi.settings.auto_import_modules = []
    project = jedi.Project(str(root), added_sys_path=[str(root), str(STUBS)], smart_sys_path=False)
    return jedi.Script(
        _prepare(source, line),
        path=str(path) if path else None,
        project=project,
        environment=InterpreterEnvironment(),
    )


def completions(source, root, path, line, column, limit=60) -> list[Suggestion]:
    """Suggestions at a 1-based line and 0-based column."""
    if jedi is None:
        return []
    try:
        found = _script(source, Path(root), path, line).complete(line + 1, column)
    except Exception:  # Jedi may fail on odd code; never break typing
        return []
    result = []
    for item in found[:limit]:
        try:
            detail = item.description or item.type
        except Exception:
            detail = item.type
        result.append(Suggestion(item.name, item.type, detail))
    return result


def documentation(source, root, path, line, column) -> str:
    """Docstring and signature of the name under the caret."""
    if jedi is None:
        return ""
    try:
        names = _script(source, Path(root), path, line).help(line + 1, column)
        return names[0].docstring() if names else ""
    except Exception:
        return ""


def signature(source, root, path, line, column) -> str:
    """Call signature while typing arguments, or an empty text."""
    if jedi is None:
        return ""
    try:
        found = _script(source, Path(root), path, line).get_signatures(line + 1, column)
    except Exception:
        return ""
    return found[0].to_string() if found else ""


def definition(source, root, path, line, column) -> Target | None:
    """Where the name under the caret is defined, inside or outside the file."""
    if jedi is None:
        return None
    try:
        found = _script(source, Path(root), path, line).goto(line + 1, column, follow_imports=True)
    except Exception:
        return None
    for item in found:
        if item.module_path and item.line:
            return Target(Path(item.module_path), item.line - 1, item.column or 0)
    return None


def rename(source, root, path, line, column, new_name) -> str | None:
    """The same file with the symbol renamed everywhere in it, or None when impossible."""
    if jedi is None or not new_name.isidentifier():
        return None
    try:
        script = _script(source, Path(root), path, line)
        refactoring = script.rename(line + 1, column, new_name=new_name)
        for changed_path, diff in refactoring.get_changed_files().items():
            if path is not None and Path(changed_path) == Path(path):
                result = diff.get_new_code()
                return result[len(PREAMBLE) :] if result.startswith(PREAMBLE) else result
    except Exception:
        return None
    return None


def snippets(prefix: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Ready-made pieces of code (plus the plugins') whose name starts with what was typed."""
    if not prefix:
        return {}
    every = {**SNIPPETS, **(extra or {})}
    return {name: text for name, text in every.items() if name.startswith(prefix)}


class Workspace:
    """A scratch copy of the project's Python files, so Jedi can follow imports.

    Modules live in memory until saved; Jedi needs real files, so they are mirrored here.
    """

    ENTRY = "actions.py"

    def __init__(self):
        import tempfile

        self._folder = tempfile.TemporaryDirectory(prefix="makebench-jedi-")
        self.root = Path(self._folder.name)
        self.names: dict[Path, str] = {}

    def sync(self, entry_name: str, texts: dict[str, str]) -> None:
        """Mirror {name: text}; `entry_name` is shown as actions.py."""
        self.names = {}
        for name, text in texts.items():
            relative = self.ENTRY if name == entry_name else name
            target = (self.root / relative).resolve()
            if self.root.resolve() not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                target.write_text(text, encoding="utf-8")
            self.names[target] = name

    def path_of(self, name: str, entry_name: str) -> Path:
        return self.root / (self.ENTRY if name == entry_name else name)

    def name_of(self, path: Path) -> str | None:
        return self.names.get(Path(path).resolve())
