# SPDX-License-Identifier: MIT
"""Inert Python sources, local modules, conflicts and atomic per-file writes."""

from __future__ import annotations
import json
import keyword
import os
from pathlib import Path, PurePosixPath
import tempfile
from makebench.i18n import language, tr
from .project import ProjectError

DEFAULT_SOURCES = {
    "en": '''"""Your project's own functions. Opening Makebench never runs this file.

Each function receives ctx (the application context) and value (the block input).
Press F5 to test these functions in the application process.
"""


def greet(ctx, value):
    """Example function that a block can call."""
    return f"Hello, {value or 'Linux'}!"
''',
    "pt_BR": '''"""Funções próprias do projeto. Abrir o Makebench não executa este arquivo.

Cada função recebe ctx (contexto do aplicativo) e valor (entrada do bloco).
Use F5 para testar estas funções no processo do aplicativo.
"""


def saudacao(ctx, valor):
    """Exemplo de função que pode ser chamada por um bloco."""
    return f"Olá, {valor or 'Linux'}!"
''',
}
DEFAULT_NAMES = {
    "en": {"function": "greet", "variable": "value", "answer": "answer"},
    "pt_BR": {"function": "saudacao", "variable": "valor", "answer": "resposta"},
}


def default_source():
    """Starter functions file in the active language; it is data, never run here."""
    return DEFAULT_SOURCES.get(language(), DEFAULT_SOURCES["en"])


def default_names():
    """Identifiers used by new blocks so they match `default_source()`."""
    return DEFAULT_NAMES.get(language(), DEFAULT_NAMES["en"])


# Kept for callers that only need the English starter text.
DEFAULT_SOURCE = DEFAULT_SOURCES["en"]
ENTRY_FILE = "@actions"
MAX_FILES = 256
MAX_BYTES = 8 * 1024 * 1024


def validate_module_name(name):
    """Accept only Python modules inside the reserved package, with no traversal."""
    if not isinstance(name, str) or len(name) > 240 or "\\" in name:
        raise ProjectError(tr("Invalid module path."))
    path = PurePosixPath(name)
    if (
        len(path.parts) < 2
        or path.parts[0] != "makebench_user"
        or path.as_posix() != name
        or path.suffix != ".py"
    ):
        raise ProjectError(tr("Modules must be inside makebench_user and end in .py."))
    if any(not p.isidentifier() or keyword.iskeyword(p) for p in (*path.parts[1:-1], path.stem)):
        raise ProjectError(tr("Use valid Python names for modules and folders."))
    return name


def validate_manifest(names):
    """Validate a bounded list of declared files; never searches for or imports modules."""
    if (
        not isinstance(names, list)
        or len(names) > MAX_FILES
        or len(set(n for n in names if isinstance(n, str))) != len(names)
    ):
        raise ProjectError(tr("Invalid module list (at most 256 files, no repeats)."))
    for name in names:
        validate_module_name(name)
    if names and "makebench_user/__init__.py" not in names:
        raise ProjectError(tr("The package needs makebench_user/__init__.py."))
    seen = set()
    for name in names:
        module = name[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        if module in seen:
            raise ProjectError(tr("A module and a package have the same name."))
        seen.add(module)
        for parent in PurePosixPath(name).parents:
            if str(parent) == ".":
                break
            if (parent / "__init__.py").as_posix() not in names:
                raise ProjectError(tr("Missing package initializer: {path}").format(path=parent))
    return names


def module_path(root, name):
    """Reject links in any segment, even inside the project root."""
    validate_module_name(name)
    path = Path(root)
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise ProjectError(tr("Modules and their folders cannot be symbolic links."))
    return path


class SourceText(str):
    """Text compatible with older APIs, carrying a copy of the modules."""

    def __new__(cls, text, modules=None):
        """Freeze auxiliary contents to build/export without reading widgets."""
        value = super().__new__(cls, text)
        value.modules = dict(modules or {})
        return value


def source_files(source):
    """Return the snapshot files, keeping the entry file of older projects."""
    return {ENTRY_FILE: str(source), **getattr(source, "modules", {})}


def source_signature(source):
    """Stable signature that also detects changes in auxiliary modules."""
    return tuple(sorted(source_files(source).items()))


def source_path(project_path):
    """Derive the sibling file: project.makebench.json → project.actions.py."""
    name = project_path.name
    stem = (
        name[: -len(".makebench.json")] if name.endswith(".makebench.json") else project_path.stem
    )
    return project_path.with_name(stem + ".actions.py")


def _read(path):
    """Read only regular files, rejecting links and excessive sizes."""
    if path.is_symlink():
        raise ProjectError(tr("The Python file cannot be a symbolic link."))
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ProjectError(tr("Invalid Python file or larger than 8 MiB."))
    return path.read_bytes()


def _atomic_write(path, data):
    """Replace one file after flush/fsync; does not confirm the whole document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".actions-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


class SourceBuffer:
    """Entry text and modules with independent external-conflict detection and recovery."""

    def __init__(self, text=None, saved_text=None, path=None, original=None):
        """Keep the old constructor; no content is evaluated. Defaults to `default_source()`."""
        text = default_source() if text is None else text
        saved_text = default_source() if saved_text is None else saved_text
        self._text = str(text)
        self.saved_text = saved_text
        self.path = path
        self.original = original
        self.modules = {}
        self._saved_names = ()
        self._deleted = {}

    @property
    def text(self):
        """Return a text snapshot compatible with the run/export API."""
        return SourceText(
            self._text, {name: str(buffer.text) for name, buffer in self.modules.items()}
        )

    @text.setter
    def text(self, value):
        """Replace only the entry text; editing it never deletes modules."""
        self._text = str(value)
        if isinstance(value, SourceText):
            self.modules = {
                name: SourceBuffer(text, text + "\0") for name, text in value.modules.items()
            }

    @property
    def dirty(self):
        """Include creating, deleting, renaming and editing modules."""
        return (
            self._text != self.saved_text
            or tuple(sorted(self.modules)) != self._saved_names
            or any(b.dirty for b in self.modules.values())
        )

    @classmethod
    def load(cls, project_path):
        """Load only the files declared in the JSON, always as UTF-8."""
        if project_path is None:
            return cls()
        path = source_path(project_path)
        data = _read(path)
        try:
            text = data.decode("utf-8") if data is not None else default_source()
            buffer = cls(text, text, path, data)
            raw = (
                json.loads(Path(project_path).read_text(encoding="utf-8"))
                if Path(project_path).exists()
                else {}
            )
            names = validate_manifest(raw.get("python_files", []))
            total = len(data or b"")
            for name in names:
                target = module_path(path.parent, name)
                payload = _read(target)
                if payload is None:
                    raise ProjectError(tr("Missing module: {name}").format(name=name))
                total += len(payload)
                if total > MAX_BYTES:
                    raise ProjectError(tr("Sources exceed 8 MiB."))
                value = payload.decode("utf-8")
                buffer.modules[name] = cls(value, value, target, payload)
            buffer._saved_names = tuple(sorted(names))
            return buffer
        except UnicodeDecodeError as exc:
            raise ProjectError(tr("Python files must be UTF-8.")) from exc
        except (ValueError, TypeError) as exc:
            raise ProjectError(tr("Invalid sources manifest: {error}").format(error=exc)) from exc

    def add_module(self, name, text=""):
        """Create the package/folders explicitly without overwriting existing modules."""
        validate_module_name(name)
        if name in self.modules:
            raise ProjectError(tr("That module already exists."))
        names = [PurePosixPath(name)]
        for parent in PurePosixPath(name).parents:
            if str(parent) == ".":
                break
            init = (parent / "__init__.py").as_posix()
            if init not in self.modules and init != name:
                names.append(PurePosixPath(init))
        if len(self.modules) + len(names) > MAX_FILES:
            raise ProjectError(tr("At most 256 Python files."))
        validate_manifest([*self.modules, *(path.as_posix() for path in names)])
        for path in reversed(names):
            key = path.as_posix()
            buffer = SourceBuffer(text if key == name else "", "\0")
            target = module_path(self.path.parent, key) if self.path else None
            if target in self._deleted:
                buffer.path = target
                buffer.original = self._deleted.pop(target)
            self.modules[key] = buffer

    def rename_module(self, old, new):
        """Rename a file without rewriting imports or discarding pending edits."""
        if old.endswith("/__init__.py"):
            raise ProjectError(tr("The package initializer cannot be renamed."))
        validate_module_name(new)
        if new in self.modules:
            raise ProjectError(tr("That module already exists."))
        buffer = self.modules[old]
        self.add_module(new, str(buffer.text))
        self.remove_module(old)

    def remove_module(self, name):
        """Drop it from the manifest; the original file is removed only after saving the whole project."""
        if name.endswith("/__init__.py"):
            raise ProjectError(tr("The package initializer cannot be deleted."))
        buffer = self.modules.pop(name)
        if buffer.path:
            self._deleted[buffer.path] = buffer.original

    def write(self, project_path):
        """Check every conflict before writing; the JSON confirms the save."""
        entry = source_path(project_path)
        if not entry.parent.is_dir():
            raise OSError(tr("The destination folder does not exist."))
        targets = [(self, entry)] + [
            (buffer, module_path(entry.parent, name))
            for name, buffer in sorted(self.modules.items())
        ]
        total = 0
        for buffer, target in targets:
            current = _read(target)
            data = buffer._text.encode("utf-8")
            total += len(data)
            if target == buffer.path and current != buffer.original:
                raise ProjectError(
                    tr(
                        "The file changed outside Makebench: {path}. Save to another folder or reopen to review."
                    ).format(path=target)
                )
            if target != buffer.path and current is not None and current != data:
                raise ProjectError(
                    tr("The destination already contains a different Python file: {path}").format(
                        path=target
                    )
                )
        for target, original in self._deleted.items():
            if target.is_relative_to(entry.parent) and _read(target) != original:
                raise ProjectError(
                    tr("The deleted module changed outside Makebench: {path}").format(path=target)
                )
        if total > MAX_BYTES:
            raise ProjectError(tr("Sources exceed 8 MiB."))
        for buffer, target in targets:
            data = buffer._text.encode("utf-8")
            if _read(target) != data:
                _atomic_write(target, data)
            buffer.path, buffer.original = target, data

    def mark_saved(self):
        """Confirm after the JSON; deletions depend on the original bytes."""
        for target, original in self._deleted.items():
            if self.path and target.is_relative_to(self.path.parent) and _read(target) == original:
                target.unlink(missing_ok=True)
        self._deleted.clear()
        self.saved_text = self._text
        self._saved_names = tuple(sorted(self.modules))
        for buffer in self.modules.values():
            buffer.mark_saved()
