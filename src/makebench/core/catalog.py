# SPDX-License-Identifier: MIT
"""The plugin catalog index: a JSON list of plugins with their source, license and hash.

Reading and checking only; nothing here touches the network. The store downloads the index
and the files, then asks this module whether what arrived is what the index promised.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from makebench.i18n import tr

INDEX_FORMAT = "makebench-plugin-index"
INDEX_VERSION = 1
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CatalogError(ValueError):
    """The index or a download does not match what the catalog promises."""


@dataclass
class Entry:
    id: str
    name: str
    version: str
    api: int
    description: str
    author: str
    license: str
    source: str
    download: str
    sha256: str
    permissions: list[str] = field(default_factory=list)
    reviewed: bool = False


def _text(item, key, required=True):
    value = item.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        raise CatalogError(
            tr("Catalog entry {id}: invalid {key}.").format(id=item.get("id"), key=key)
        )
    return value


def parse_index(value) -> list[Entry]:
    """Validate a decoded index; any bad entry rejects the whole index."""
    if (
        not isinstance(value, dict)
        or value.get("format") != INDEX_FORMAT
        or value.get("version") != INDEX_VERSION
        or not isinstance(value.get("plugins"), list)
    ):
        raise CatalogError(tr("This is not a plugin catalog this Makebench can read."))
    entries, seen = [], set()
    for item in value["plugins"][:2000]:
        if not isinstance(item, dict) or not ID_PATTERN.match(str(item.get("id", ""))):
            raise CatalogError(tr("Catalog entry with an invalid id."))
        if item["id"] in seen:
            raise CatalogError(tr("Catalog lists {id} twice.").format(id=item["id"]))
        seen.add(item["id"])
        if type(item.get("api")) is not int or not HASH_PATTERN.match(str(item.get("sha256", ""))):
            raise CatalogError(
                tr("Catalog entry {id}: invalid api or sha256.").format(id=item["id"])
            )
        permissions = item.get("permissions", [])
        if not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions):
            raise CatalogError(tr("Catalog entry {id}: invalid permissions.").format(id=item["id"]))
        download = _text(item, "download")
        if not download.startswith("https://"):
            raise CatalogError(
                tr("Catalog entry {id}: downloads must use https.").format(id=item["id"])
            )
        entries.append(
            Entry(
                id=item["id"],
                name=_text(item, "name"),
                version=_text(item, "version"),
                api=item["api"],
                description=_text(item, "description", required=False),
                author=_text(item, "author", required=False),
                license=_text(item, "license"),
                source=_text(item, "source"),
                download=download,
                sha256=item["sha256"],
                permissions=list(permissions),
                reviewed=item.get("reviewed") is True,
            )
        )
    return entries


def check_download(entry: Entry, folder: Path, supported_apis) -> None:
    """Raise CatalogError unless the downloaded folder is what the index described."""
    from .plugin_scan import folder_hash, undeclared

    if entry.api not in supported_apis:
        raise CatalogError(tr("This plugin needs plugin API {api}.").format(api=entry.api))
    if folder_hash(Path(folder)) != entry.sha256:
        raise CatalogError(tr("The download does not match the catalog's fingerprint."))
    extra = undeclared(Path(folder), entry.permissions)
    if extra:
        raise CatalogError(
            tr("The code uses permissions the catalog does not list: {list}.").format(
                list=", ".join(extra)
            )
        )
