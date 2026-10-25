"""Asset preservation and confinement of images referenced by projects."""

import tempfile
import unittest
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from makebench.core.storage import StorageError
from makebench.editor.assets import AssetStore


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "picture.png"
        image = QImage(24, 16, QImage.Format.Format_RGB32)
        image.fill(QColor("steelblue"))
        self.assertTrue(image.save(str(self.source)))

    def test_same_image_is_deduplicated_and_original_is_not_required_after_import(self):
        assets = AssetStore()
        source = assets.import_image(self.source)
        self.assertEqual(source, assets.import_image(self.source))
        data = self.source.read_bytes()
        self.source.unlink()
        destination = self.root / "project"
        destination.mkdir()
        assets.write_referenced(destination, {source})
        self.assertEqual((destination / source).read_bytes(), data)

    def test_different_existing_asset_is_never_overwritten(self):
        assets = AssetStore()
        source = assets.import_image(self.source)
        destination = self.root / "project"
        (destination / "assets").mkdir(parents=True)
        target = destination / source
        target.write_bytes(b"different image content")
        with self.assertRaises(StorageError):
            assets.write_referenced(destination, {source})
        self.assertEqual(target.read_bytes(), b"different image content")

    def test_symlinks_and_relative_paths_cannot_read_outside_the_project(self):
        project = self.root / "project"
        (project / "assets").mkdir(parents=True)
        (project / "assets" / "link.png").symlink_to(self.source)
        assets = AssetStore(project)
        for source in ("assets/link.png", "assets/../../picture.png", str(self.source)):
            with self.subTest(source=source), self.assertRaises(StorageError):
                assets.read(source)

    def test_non_image_files_are_rejected_before_becoming_assets(self):
        self.source.write_bytes(b"not an image")
        with self.assertRaisesRegex(StorageError, "valid PNG, JPEG, WebP or SVG image"):
            AssetStore().import_image(self.source)
