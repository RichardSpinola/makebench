# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep translation catalogs in sync with the source.

Usage:
    python checks/i18n.py            # report missing/unused entries, exit 1 if any are missing
    python checks/i18n.py --update   # append missing msgids (empty msgstr) to every catalog

English is the source language: every `tr("...")` / `ntr("...", "...", n)` literal in
`src/makebench` is a msgid. Catalogs live in `src/makebench/locale/<code>/makebench.po`
and are read directly by `makebench.i18n`; no compile step is needed.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "makebench"
LOCALES = SOURCE / "locale"
JS = SOURCE / "web" / "logic.js"


def source_msgids() -> dict[str, set[str]]:
    """Map each msgid used in Python sources to the files that use it."""
    found: dict[str, set[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                count = {"tr": 1, "ntr": 2}.get(node.func.id, 0)
                for arg in node.args[:count]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.setdefault(arg.value, set()).add(str(path.relative_to(ROOT)))
    return found


def js_msgids() -> set[str]:
    """English texts passed to T('...') in the Blockly page."""
    raw = re.findall(r"T\('((?:[^'\\]|\\.)*)'\)", JS.read_text(encoding="utf-8"))
    return {ast.literal_eval("'" + text + "'") for text in raw}


def js_catalog() -> dict[str, str]:
    """The Portuguese dictionary embedded in logic.js."""
    import json

    text = JS.read_text(encoding="utf-8")
    match = re.search(r"const PT_BR = (\{.*?\});\n", text, re.S)
    return json.loads(match.group(1)) if match else {}


def quote(text: str) -> str:
    """Quote a msgid/msgstr the way makebench.i18n.read_po reads it back."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    return '"' + escaped.replace("\n", "\\n") + '"'


def block_msgid(block: str) -> str | None:
    """Read the msgid of one catalog entry, joining continuation lines."""
    parts, reading = [], False
    for line in block.splitlines():
        if line.startswith("msgid "):
            reading = True
            parts.append(line[6:])
        elif reading and line.startswith('"'):
            parts.append(line)
        elif reading:
            break
    return "".join(ast.literal_eval(part) for part in parts) if parts else None


def prune(po: Path, unused: set[str]) -> int:
    """Drop entries whose msgid is no longer used; keeps the header and order."""
    blocks = po.read_text(encoding="utf-8").split("\n\n")
    kept = [b for b in blocks if not block_msgid(b) or block_msgid(b) not in unused]
    po.write_text("\n\n".join(kept), encoding="utf-8")
    return len(blocks) - len(kept)


def main() -> int:
    """Report catalog coverage and optionally append missing entries."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="append missing msgids")
    parser.add_argument("--prune", action="store_true", help="remove unused msgids")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    from makebench.i18n import read_po

    used = source_msgids()
    status = 0
    for po in sorted(LOCALES.glob("*/makebench.po")):
        catalog = read_po(po)
        missing = sorted(set(used) - set(catalog))
        unused = sorted(set(catalog) - set(used))
        print(
            f"{po.relative_to(ROOT)}: {len(catalog)} entries, {len(missing)} missing, {len(unused)} unused"
        )
        if unused and args.prune:
            print("  removed", prune(po, set(unused)), "unused entries")
        for msgid in missing[:50]:
            print("  missing:", repr(msgid))
        if missing and args.update:
            with po.open("a", encoding="utf-8") as stream:
                for msgid in missing:
                    refs = " ".join(sorted(used[msgid]))
                    stream.write(f'\n#: {refs}\nmsgid {quote(msgid)}\nmsgstr ""\n')
            print("  appended", len(missing), "empty entries; translate them before committing")
        elif missing:
            status = 1
    js_missing = sorted(js_msgids() - set(js_catalog()))
    print(f"{JS.relative_to(ROOT)}: {len(js_missing)} T() texts without Portuguese")
    for text in js_missing:
        print("  missing:", repr(text))
    return 1 if js_missing else status


if __name__ == "__main__":
    raise SystemExit(main())
