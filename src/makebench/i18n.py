# SPDX-License-Identifier: MIT
"""Interface language: English source strings with optional catalogs.

The editor, the shared runtime and generated applications call `tr()` for every
user-visible text. English is the default; other languages live in gettext `.po`
files under `makebench/locale/<code>/makebench.po`, read directly (no compiled
`.mo` step). This module never imports Qt, so `core` can use it.
"""

from __future__ import annotations

import ast
from pathlib import Path

DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "pt_BR": "Português (Brasil)"}
LOCALE_DIR = Path(__file__).resolve().parent / "locale"

_catalog: dict[str, str] = {}
_language = DEFAULT_LANGUAGE


def _unquote(text: str) -> str:
    """Decode one quoted `.po` string segment using Python string escapes."""
    return ast.literal_eval(text)


def read_po(path: str | Path) -> dict[str, str]:
    """Parse a `.po` file into {msgid: msgstr}, skipping empty and fuzzy entries.

    Supports the subset Makebench writes: comments, `#, fuzzy` flags, multi-line
    `msgid`/`msgstr` continuations and an optional `msgctxt` joined to the id with
    the gettext separator (`\\x04`).
    """
    catalog: dict[str, str] = {}
    entry: dict[str, str] = {}
    field = None
    fuzzy = False

    def flush():
        """Store the finished entry unless it is the header, empty or fuzzy."""
        msgid = entry.get("msgid", "")
        if msgid and entry.get("msgstr") and not fuzzy:
            key = entry["msgctxt"] + "\x04" + msgid if "msgctxt" in entry else msgid
            catalog[key] = entry["msgstr"]

    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if field == "msgstr":
                flush()
                entry, field, fuzzy = {}, None, False
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            continue
        keyword, _, rest = line.partition(" ")
        if keyword in ("msgctxt", "msgid", "msgstr"):
            if keyword in ("msgctxt", "msgid") and field == "msgstr":
                flush()
                entry, fuzzy = {}, False
            field = keyword
            entry[field] = _unquote(rest)
        elif line.startswith('"') and field:
            entry[field] += _unquote(line)
    if field == "msgstr":
        flush()
    return catalog


def set_language(code: str | None) -> str:
    """Activate a language for later `tr()` calls; unknown codes fall back to English.

    Returns the code actually active. Call before importing modules that build
    translated module-level constants.
    """
    global _catalog, _language
    code = code if code in LANGUAGES else DEFAULT_LANGUAGE
    path = LOCALE_DIR / code / "makebench.po"
    _catalog = read_po(path) if code != DEFAULT_LANGUAGE and path.is_file() else {}
    _language = code
    return code


def language() -> str:
    """Return the active language code (for example `en` or `pt_BR`)."""
    return _language


def tr(message: str, context: str | None = None) -> str:
    """Translate an English source string; untranslated text stays in English."""
    if context is not None:
        return _catalog.get(context + "\x04" + message, message)
    return _catalog.get(message, message)


def ntr(singular: str, plural: str, count: int) -> str:
    """Choose singular/plural English source by count, then translate it."""
    return tr(singular if count == 1 else plural)
