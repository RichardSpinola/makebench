# SPDX-License-Identifier: GPL-3.0-or-later
"""Asset storage with no graphical toolkit dependency."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
import xml.etree.ElementTree as ET
from .storage import StorageError
from makebench.i18n import tr


class AssetStore:
    """Portable image cache with confined paths and exclusive publication."""

    def __init__(self, root=None):
        """Bind an optional folder; imports stay in memory until saved."""
        self.root = Path(root).resolve() if root else None
        self._cache = {}

    @staticmethod
    def inside(root, name):
        """Reject traversal, absolute paths and links that escape the folder."""
        parts = PurePosixPath(name)
        root = Path(root).resolve()
        if (
            parts.is_absolute()
            or ".." in parts.parts
            or "\\" in name
            or len(parts.parts) < 2
            or parts.parts[0] != "assets"
        ):
            raise StorageError(tr("The asset must be inside the assets folder."))
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise StorageError(tr("The asset points outside the project."))
        return path

    def import_image(self, path):
        """Identify static images by signature; the frontend validates decoding."""
        path = Path(path)
        data = path.read_bytes()
        if len(data) > 50 * 1024 * 1024:
            raise StorageError(tr("The image is larger than 50 MB."))
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        elif data.startswith(b"\xff\xd8\xff"):
            extension = "jpg"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            extension = "webp"
        else:
            try:
                if ET.fromstring(data).tag.split("}")[-1] != "svg":
                    raise ValueError()
                extension = "svg"
            except (ET.ParseError, ValueError):
                raise StorageError(tr("Choose a valid PNG, JPEG, WebP or SVG file."))
        name = f"assets/{hashlib.sha256(data).hexdigest()}.{extension}"
        self._cache[name] = data
        return name

    def read(self, name):
        """Resolve only assets from the project folder or explicitly imported."""
        if name not in self._cache:
            if self.root is None:
                raise StorageError(tr("Asset not found: {name}").format(name=name))
            self._cache[name] = self.inside(self.root, name).read_bytes()
        return self._cache[name]

    def write_referenced(self, root, names):
        """Copy assets without overwriting other content; keep the cache for undo."""
        for name in sorted(names):
            data = self.read(name)
            target = self.inside(root, name)
            if target.exists():
                if target.read_bytes() != data:
                    raise StorageError(
                        tr("The destination contains a different asset: {name}").format(name=name)
                    )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                temporary = Path(stream.name)
            try:
                os.link(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
