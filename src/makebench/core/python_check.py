# SPDX-License-Identifier: MIT
"""Static checks for your own Python files, with a short explanation for each problem.

Nothing here runs or imports the project's code: syntax comes from Python's own parser
(the first error, with its precise message) and parso (the ones after it), names from
``symtable``, and the ``ctx`` API from the runtime's source.
"""

import ast
import builtins
import difflib
from functools import lru_cache
from pathlib import Path
import re
import symtable

import parso

from makebench.i18n import tr

LIMIT = 50
# ctx methods whose first argument is a component (or window) id.
COMPONENT_METHODS = {
    "read",
    "set_text",
    "set_enabled",
    "set_value",
    "set_rows",
    "add_row",
    "set_options",
    "set_chart",
    "show_records",
    "show_page",
    "open_window",
}
MODULE_NAMES = {"__name__", "__file__", "__doc__", "__builtins__", "__spec__", "__loader__"}


def _hints():
    """English messages from Python and parso, and what to do about them."""
    return [
        (r"expected ':'", tr("Lines that open a block (if, for, while, def…) end with a colon.")),
        (
            r"was never closed",
            tr("A parenthesis, bracket or brace opened here is never closed."),
        ),
        (r"^unmatched", tr("This closing symbol has no matching opening one.")),
        (
            r"unterminated (triple-quoted )?string|EOL while scanning|EOF while scanning",
            tr("The text in quotes is not closed: add the closing quote."),
        ),
        (
            r"expected an indented block",
            tr("After a line ending in ':' the next line must be indented (4 spaces)."),
        ),
        (r"unexpected indent", tr("This line starts with more spaces than the code around it.")),
        (
            r"unindent does not match|unexpected unindent",
            tr("The spaces at the start of this line do not match any block above."),
        ),
        (r"inconsistent use of tabs", tr("Tabs and spaces are mixed: indent with spaces only.")),
        (r"outside function", tr("return can only be used inside a function (def).")),
        (r"outside loop", tr("break and continue only work inside a for or while loop.")),
        (r"forgot a comma", tr("A comma may be missing between two items.")),
        (r"cannot assign to|cannot be assigned", tr("The left side of = must be a name.")),
        (
            r"positional argument follows keyword",
            tr("Put arguments without a name before the ones written as name=value."),
        ),
        (
            r"invalid syntax",
            tr("Python cannot read this line: look for a missing or extra symbol."),
        ),
    ]


def explain(message):
    """A short explanation for a syntax message, or an empty text."""
    for pattern, hint in _hints():
        if re.search(pattern, message):
            return hint
    return ""


@lru_cache(maxsize=1)
def ctx_api():
    """Public names of ctx and ctx.data, read from the runtime without importing it."""
    path = Path(__file__).resolve().parents[1] / "runtime/worker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def names(node):
        found = set()
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                found.add(item.name)
                if item.name == "__init__":
                    for child in ast.walk(item):
                        if (
                            isinstance(child, ast.Attribute)
                            and isinstance(child.value, ast.Name)
                            and child.value.id == "self"
                            and isinstance(child.ctx, ast.Store)
                        ):
                            found.add(child.attr)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                found.add(item.target.id)
        return frozenset(name for name in found if not name.startswith("_"))

    return names(classes["Context"]), names(classes["Data"]) | {"last_id"}


def _entry(line, column, message, hint="", severity="warning"):
    return {
        "line": max(1, line),
        "column": max(1, column),
        "message": message,
        "hint": hint,
        "severity": severity,
    }


def _suggest(name, options):
    match = difflib.get_close_matches(name, list(options), n=1, cutoff=0.75)
    return tr("Did you mean {name}?").format(name=match[0]) if match else ""


def syntax_errors(text):
    """Every syntax error: Python's first one, then parso's on the lines after it."""
    try:
        compile(text, "<file>", "exec", ast.PyCF_ONLY_AST)
        return []
    except SyntaxError as exc:
        message = exc.msg or str(exc)
        first = _entry(exc.lineno or 1, exc.offset or 1, message, explain(message), "error")
    except ValueError as exc:  # null bytes
        return [_entry(1, 1, str(exc), "", "error")]
    found = [first]
    grammar = parso.load_grammar()
    lines = {first["line"]}
    for error in grammar.iter_errors(grammar.parse(text, error_recovery=True)):
        line, column = error.start_pos
        message = error.message.split(": ", 1)[-1]
        # The line right after a broken one usually only repeats the same mistake.
        if line <= first["line"] + 1 or line in lines or line - 1 in lines:
            lines.add(line)
            continue
        lines.add(line)
        found.append(_entry(line, column + 1, message, explain(message), "error"))
    return found[:LIMIT]


def _undefined(text, tree):
    """Names read somewhere that nothing defines, imports or provides as a builtin."""
    if any(
        isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names)
        for node in ast.walk(tree)
    ):
        return set()
    try:
        top = symtable.symtable(text, "<file>", "exec")
    except SyntaxError:
        return set()
    defined = set(dir(builtins)) | MODULE_NAMES
    candidates = set()

    def visit(table):
        for symbol in table.get_symbols():
            name = symbol.get_name()
            if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace():
                if table is top or symbol.is_declared_global():
                    defined.add(name)
                continue
            if symbol.is_referenced() and symbol.is_global():
                candidates.add(name)
        for child in table.get_children():
            visit(child)

    visit(top)
    return candidates - defined


def diagnose(text, component_ids=()):
    """Problems in one Python file, sorted by line; an empty list when all is well."""
    found = syntax_errors(text)
    if found:
        return found
    tree = ast.parse(text)
    missing = _undefined(text, tree)
    context, data = ctx_api()
    components = set(component_ids)
    known = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            known.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            known.add(node.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in missing:
            found.append(
                _entry(
                    node.lineno,
                    node.col_offset + 1,
                    tr("Name not defined: {name}").format(name=node.id),
                    _suggest(node.id, known - missing)
                    or tr("Define it before using it, import it, or check the spelling."),
                )
            )
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "ctx" and node.attr not in context:
                found.append(
                    _entry(
                        node.lineno,
                        node.end_col_offset - len(node.attr) + 1,
                        tr("ctx has no {name}").format(name=node.attr),
                        _suggest(node.attr, context) or tr("See “What can I use” for the list."),
                    )
                )
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "ctx"
            and node.value.attr == "data"
            and node.attr not in data
        ):
            found.append(
                _entry(
                    node.lineno,
                    node.end_col_offset - len(node.attr) + 1,
                    tr("ctx.data has no {name}").format(name=node.attr),
                    _suggest(node.attr, data) or tr("See “What can I use” for the list."),
                )
            )
        if (
            components
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ctx"
            and node.func.attr in COMPONENT_METHODS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value not in components
        ):
            argument = node.args[0]
            found.append(
                _entry(
                    argument.lineno,
                    argument.col_offset + 1,
                    tr("No component with the id {id}").format(id=argument.value),
                    _suggest(argument.value, components)
                    or tr("Check the id in the Design properties."),
                )
            )
    found.sort(key=lambda item: (item["line"], item["column"]))
    return found[:LIMIT]
