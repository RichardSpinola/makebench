# SPDX-License-Identifier: MIT
"""Static Python index: suggestions, signatures and targets without running imports."""

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from .python_check import diagnose
from .source import ENTRY_FILE, source_files
from makebench.i18n import tr


@dataclass(frozen=True)
class Definition:
    """Location and signature of a symbol taken from the project text."""

    name: str
    file: str
    line: int
    column: int
    signature: str = ""
    description: str = ""


def module_name(filename):
    """Turn a reserved path into an importable name, including initializers."""
    value = filename[:-3].replace("/", ".")
    return value[:-9] if value.endswith(".__init__") else value


class CodeIndex:
    """Keep the last valid AST per file while typing incomplete code."""

    def __init__(self):
        """Prepare local caches; no extra language server is started."""
        self.trees = {}
        self.texts = {}
        self.errors = []
        self.checks = {}
        self.outlines = {}
        self.definitions = {}
        self.imports = {}
        self.components = []
        self.ctx = {}
        path = Path(__file__).resolve().parents[1] / "runtime/worker.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        context = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Context")
        for node in context.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                args = ast.unparse(node.args)
                args = args.removeprefix("self, ").removeprefix("self")
                self.ctx["ctx." + node.name] = Definition(
                    "ctx." + node.name,
                    "",
                    node.lineno,
                    1,
                    "ctx." + node.name + "(" + args + ")",
                    ast.get_docstring(node) or "",
                )
        for name in ("variables", "window_variables"):
            self.ctx.setdefault("ctx." + name, Definition("ctx." + name, "", 1, 1, "ctx." + name))

    def update(self, source, components=()):
        """Update changed files and diagnose local imports without touching the disk."""
        files = source_files(source)
        self.components = list(components)
        self.errors = []
        for name in set(self.trees) - set(files):
            self.trees.pop(name, None)
            self.texts.pop(name, None)
        ids = frozenset(getattr(node, "id", node) for node in self.components)
        for name in set(self.checks) - set(files):
            self.checks.pop(name)
        for name, text in files.items():
            try:
                if self.texts.get(name) != text:
                    self.trees[name] = ast.parse(text)
                    self.texts[name] = text
            except (SyntaxError, ValueError):
                pass
            if self.checks.get(name, (None,))[0] != (text, ids):
                # The last valid tree only matches when this exact text parsed.
                tree = self.trees.get(name) if self.texts.get(name) == text else None
                self.checks[name] = ((text, ids), diagnose(text, ids, tree))
            self.errors.extend({"file": name, **item} for item in self.checks[name][1])
        for name in set(self.outlines) - set(self.trees):
            self.outlines.pop(name)
        self.definitions = {}
        self.imports = {}
        known = {module_name(name): name for name in files if name != ENTRY_FILE}
        for name, tree in self.trees.items():
            _, definitions, imports, references, _ = self._outline_of(name)
            self.definitions[name] = definitions
            self.imports[name] = imports
            for node, base, alias in references:
                if alias is None:
                    if base not in known:
                        self._missing(name, node, base)
                elif base not in known:
                    self._missing(name, node, base)
                elif base + "." + alias not in known:
                    target = self._outline_of(known[base])
                    names, star = target[4] if target else (set(), False)
                    if alias not in names and alias != "*" and not star:
                        self._missing(name, node, base + "." + alias)
        self.known = known

    def _outline_of(self, name):
        """The cached outline of a file's current tree, or None when it never parsed."""
        tree = self.trees.get(name)
        if tree is None:
            return None
        if self.outlines.get(name, (None,))[0] is not tree:
            self.outlines[name] = (tree, *self._outline(name, tree))
        return self.outlines[name]

    def _outline(self, name, tree):
        """What one file defines, imports and exports; kept until its tree changes."""
        definitions = {}
        imports = {}
        references = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                signature = (
                    node.name + "(" + ast.unparse(node.args) + ")"
                    if hasattr(node, "args")
                    else "class " + node.name
                )
                definitions[node.name] = Definition(
                    node.name,
                    name,
                    node.lineno,
                    node.col_offset + 1,
                    signature,
                    ast.get_docstring(node) or "",
                )
        assigned = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                assigned.add(node.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0],
                        None,
                    )
                    if alias.name.startswith("makebench_user"):
                        references.append((node, alias.name, None))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level and name != ENTRY_FILE:
                    package = module_name(name).split(".")
                    if not name.endswith("/__init__.py"):
                        package = package[:-1]
                    base = ".".join(
                        package[: len(package) - node.level + 1] + ([base] if base else [])
                    )
                for alias in node.names:
                    imports[alias.asname or alias.name] = (base, alias.name)
                    if base.startswith("makebench_user"):
                        references.append((node, base, alias.name))
        # A module that imports anything may re-export names, so it is never reported.
        star = any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body)
        return definitions, imports, references, (set(definitions) | assigned, star)

    def _missing(self, name, node, module):
        """Record a broken local reference, common after renaming a module."""
        self.errors.append(
            {
                "file": name,
                "line": node.lineno,
                "column": node.col_offset + 1,
                "message": tr("Local reference not found: {module}").format(module=module),
                "hint": tr("Rename the import to match the module, or create the module."),
                "severity": "error",
            }
        )

    def resolve(self, file, token):
        """Resolve a local definition or explicit import; never infers dynamic types."""
        if token in self.ctx:
            return self.ctx[token]
        first, _, rest = token.partition(".")
        if first in self.definitions.get(file, {}):
            return self.definitions[file][first]
        if first in self.imports.get(file, {}):
            base, symbol = self.imports[file][first]
            full = base + ("." + symbol if symbol else "")
            if rest:
                full += "." + rest
            if full in self.known:
                return Definition(token, self.known[full], 1, 1, token)
            module, _, name = full.rpartition(".")
            return self.definitions.get(self.known.get(module), {}).get(name)
        return None

    def complete(self, file, prefix):
        """Suggest known APIs, the project's own symbols and imported names."""
        candidates = dict(self.definitions.get(file, {}))
        candidates.update(self.ctx)
        for name in self.imports.get(file, {}):
            candidates.setdefault(name, Definition(name, file, 1, 1, name))
        if "." in prefix and not prefix.startswith("ctx."):
            base = prefix.rsplit(".", 1)[0]
            resolved = self.resolve(file, base)
            if resolved and resolved.file in self.definitions:
                for name, definition in self.definitions[resolved.file].items():
                    candidates[base + "." + name] = definition
        return [
            (name, value)
            for name, value in sorted(candidates.items())
            if name.casefold().startswith(prefix.casefold())
        ]

    def call_signature(self, file, before):
        """Show the signature of the nearest local call that is still open."""
        match = re.search(r"([\w.]+)\([^()]*$", before)
        target = self.resolve(file, match.group(1)) if match else None
        return target.signature if target else ""
