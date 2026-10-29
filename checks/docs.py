# SPDX-License-Identifier: MIT
"""Check the documentation site for errors.

Usage:
    python checks/docs.py              # every check, including `mkdocs build --strict`
    python checks/docs.py --no-build   # skip the site build (no MkDocs needed)

Checks that every English page has a Portuguese twin (`page.md` + `page.pt-BR.md`) and
the other way round, that images exist, that Python blocks in the hand-written pages
compile, that `plugin.json` and `.mbtheme` examples pass the real validators and that the
generated reference is up to date. The site build itself catches broken links and anchors.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PT = ".pt-BR.md"
FENCE = re.compile(r"^([ \t]*)```(\w*)[^\n]*\n(.*?)^\1```", re.M | re.S)
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def pages() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


def missing_twins() -> list[str]:
    names = {path.relative_to(DOCS).as_posix() for path in pages()}
    problems = []
    for name in sorted(names):
        if name.endswith(PT):
            if name[: -len(PT)] + ".md" not in names:
                problems.append(f"{name}: no English page")
        elif name[:-3] + PT not in names:
            problems.append(f"{name}: no Portuguese page ({name[:-3]}{PT})")
    return problems


def blocks(path: Path):
    """Yield (language, code, line) for each fenced block, dedented."""
    text = path.read_text(encoding="utf-8")
    for match in FENCE.finditer(text):
        indent = len(match.group(1))
        code = "".join(line[indent:] for line in match.group(3).splitlines(keepends=True))
        yield match.group(2), code, text.count("\n", 0, match.start()) + 1


def missing_images() -> list[str]:
    problems = []
    for path in pages():
        for target in IMAGE.findall(path.read_text(encoding="utf-8")):
            if "://" not in target and not (path.parent / target).is_file():
                problems.append(f"{path.relative_to(DOCS)}: missing image {target}")
    return problems


def broken_examples() -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from makebench.editor.plugins import PluginManager
    from makebench.ui import themes

    problems = []
    for path in pages():
        if path.relative_to(DOCS).parts[0] == "reference":
            continue  # generated signatures, not code
        for language, code, line in blocks(path):
            where = f"{path.relative_to(DOCS)}:{line}"
            if language == "python":
                try:
                    compile(code, where, "exec")
                except SyntaxError as exc:
                    problems.append(f"{where}: {exc.msg}")
            elif language == "json":
                try:
                    data = json.loads(code)
                except ValueError as exc:
                    problems.append(f"{where}: invalid JSON ({exc})")
                    continue
                if data.get("format") == "mbtheme":
                    try:
                        themes.validate(data)
                    except themes.ThemeError as exc:
                        problems.append(f"{where}: {exc}")
                elif "api" in data and "id" in data:
                    with tempfile.TemporaryDirectory() as folder:
                        plugin = Path(folder) / str(data["id"])
                        plugin.mkdir()
                        (plugin / "plugin.json").write_text(code, encoding="utf-8")
                        (plugin / "plugin.py").write_text("", encoding="utf-8")
                        found = PluginManager(folder, official=None).plugins[plugin.name]
                        if found.incompatible or found.error:
                            problems.append(f"{where}: {found.error}")
    return problems


def run(command: list[str]) -> list[str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), NO_MKDOCS_2_WARNING="1")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        return []
    return [f"{' '.join(command[1:3])} failed:\n{result.stdout}{result.stderr}".strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-build", action="store_true", help="skip mkdocs build --strict")
    args = parser.parse_args()
    problems = missing_twins() + missing_images() + broken_examples()
    problems += run([sys.executable, "checks/build_reference.py", "--check"])
    if not args.no_build:
        with tempfile.TemporaryDirectory() as site:
            problems += run(
                [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", site]
            )
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(problems)} problem(s)" if problems else "docs ok", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
