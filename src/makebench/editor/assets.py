# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable images: explicit import and project-relative assets."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader

from makebench.core.storage import StorageError
from makebench.i18n import tr


class AssetStore:
    """Keep images in memory until saved and resolve only local paths.

    The cache survives Save As, so deleting an image can be undone even after
    the document's folder changes. Never reads URLs or external paths named by a
    project; only an explicit import accepts an external file.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Bind the document to the folder where its assets are found."""
        self.root = root.resolve() if root else None
        self._cache: dict[str, bytes] = {}

    @staticmethod
    def _inside(root: Path, source: str) -> Path:
        """Reject absolute paths, traversal and links that escape the project."""
        parts = PurePosixPath(source)
        if (
            parts.is_absolute()
            or ".." in parts.parts
            or "\\" in source
            or not parts.parts
            or parts.parts[0] != "assets"
        ):
            raise StorageError(tr("The asset must be inside the project's assets folder."))
        path = (root / source).resolve()
        if not path.is_relative_to(root.resolve()):
            raise StorageError(tr("The image path points outside the project."))
        return path

    def import_image(self, path: Path) -> str:
        """Validate PNG/JPEG/WebP/SVG and reserve a copy identified by its content."""
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise StorageError(tr("Could not read the image: {error}").format(error=exc)) from exc
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        format_name = bytes(reader.format()).decode("ascii", errors="replace").lower()
        if format_name not in {"png", "jpeg", "jpg", "webp", "svg"} or reader.read().isNull():
            raise StorageError(tr("Choose a valid PNG, JPEG, WebP or SVG image."))
        extension = "jpg" if format_name == "jpeg" else format_name
        relative = f"assets/{hashlib.sha256(data).hexdigest()}.{extension}"
        self._cache[relative] = data
        return relative

    def read(self, source: str) -> bytes:
        """Read an image confined to the project or already imported in this session."""
        if source in self._cache:
            return self._cache[source]
        if self.root is None:
            raise StorageError(tr("Save the project or select the image again."))
        try:
            data = self._inside(self.root, source).read_bytes()
        except OSError as exc:
            raise StorageError(tr("Image not found: {source}").format(source=source)) from exc
        self._cache[source] = data
        return data

    def write_referenced(self, root: Path, sources: set[str]) -> None:
        """Copy assets before the JSON, never replacing files with different content."""
        root = root.resolve()
        for source in sorted(sources):
            data = self.read(source)
            destination = self._inside(root, source)
            temporary = None
            try:
                if destination.exists():
                    if destination.read_bytes() != data:
                        raise StorageError(
                            tr(
                                "Another image already exists at {source}; choose another destination folder."
                            ).format(source=source)
                        )
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # An atomic link never replaces a file created by another process.
                os.link(temporary, destination)
            except OSError as exc:
                raise StorageError(
                    tr("Could not copy the image {source}: {error}").format(
                        source=source, error=exc
                    )
                ) from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
