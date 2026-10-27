# SPDX-License-Identifier: GPL-3.0-or-later
"""Color themes for the editor, stored as small `.mbtheme` JSON files."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from makebench.i18n import tr

FORMAT = "mbtheme"
VERSION = 1
MAX_SIZE = 64 * 1024
SURFACE_KEYS = ("win", "side", "base", "line", "btn", "btnLine", "fg", "mut")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

BUILTIN = {
    "format": FORMAT,
    "version": VERSION,
    "name": "Makebench",
    "accent": "#3a83c9",
    "dark": dict(
        win="#2b2e32",
        side="#25282b",
        base="#1f2124",
        line="#3e4247",
        btn="#363a3f",
        btnLine="#4a4f55",
        fg="#dfe1e4",
        mut="#959ba2",
    ),
    "light": dict(
        win="#eceef0",
        side="#e2e5e8",
        base="#ffffff",
        line="#c9ced3",
        btn="#f6f7f8",
        btnLine="#b8bec4",
        fg="#23272b",
        mut="#586068",
    ),
}


class ThemeError(ValueError):
    """The file is not a usable theme."""


def user_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "makebench" / "themes"


def _colors(data, where: str) -> dict:
    if not isinstance(data, dict):
        raise ThemeError(tr("The theme is missing its {where} colors.").format(where=where))
    colors = {}
    for key in SURFACE_KEYS:
        value = data.get(key)
        if not isinstance(value, str) or not COLOR.match(value):
            raise ThemeError(tr("Invalid color for {key} in {where}.").format(key=key, where=where))
        colors[key] = value.lower()
    return colors


def validate(data) -> dict:
    """Return a clean copy of a theme or raise ThemeError; nothing else is kept."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ThemeError(tr("This is not a Makebench theme."))
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version > VERSION:
        raise ThemeError(tr("This theme needs a newer Makebench."))
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 60:
        raise ThemeError(tr("The theme needs a name of up to 60 characters."))
    accent = data.get("accent")
    if not isinstance(accent, str) or not COLOR.match(accent):
        raise ThemeError(tr("The theme needs an accent color like #3a83c9."))
    return {
        "format": FORMAT,
        "version": VERSION,
        "name": name.strip(),
        "accent": accent.lower(),
        "dark": _colors(data.get("dark"), tr("dark")),
        "light": _colors(data.get("light"), tr("light")),
    }


def load(path) -> dict:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_SIZE:
            raise ThemeError(tr("The theme file is too large."))
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ThemeError(tr("The theme file cannot be read.")) from exc
    return validate(data)


def save(path, theme: dict) -> None:
    Path(path).write_text(
        json.dumps(validate(theme), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "theme"


def installed(folder: Path | None = None) -> list[dict]:
    """The built-in theme first, then the valid user themes by name; bad files are skipped."""
    found = []
    folder = Path(folder) if folder else user_dir()
    for path in sorted(folder.glob("*.mbtheme")) if folder.is_dir() else []:
        try:
            found.append(load(path))
        except ThemeError:
            continue
    found.sort(key=lambda theme: theme["name"].lower())
    return [validate(BUILTIN), *[t for t in found if t["name"] != BUILTIN["name"]]]


def import_theme(source, folder: Path | None = None) -> dict:
    """Validate a file and copy it, rewritten, into the themes folder without overwriting."""
    theme = load(source)
    folder = Path(folder) if folder else user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{slug(theme['name'])}.mbtheme"
    number = 2
    while target.exists():
        target = folder / f"{slug(theme['name'])}-{number}.mbtheme"
        number += 1
    save(target, theme)
    return theme
