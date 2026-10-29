# SPDX-License-Identifier: GPL-3.0-or-later
import support  # noqa: F401  (first: isolates settings and data)
import tempfile
import unittest
from pathlib import Path

from makebench.core import catalog
from makebench.core.plugin_scan import folder_hash


def entry(**extra):
    base = {
        "id": "word-count",
        "name": "Word count",
        "version": "1.0.0",
        "api": 2,
        "license": "MIT",
        "source": "https://github.com/example/word-count",
        "download": "https://example.org/word-count.zip",
        "sha256": "a" * 64,
    }
    return {**base, **extra}


def index(*plugins):
    return {"format": catalog.INDEX_FORMAT, "version": 1, "plugins": list(plugins)}


class CatalogTests(unittest.TestCase):
    def test_reads_a_valid_index(self):
        (one,) = catalog.parse_index(index(entry(reviewed=True, permissions=["network"])))
        self.assertTrue(one.reviewed)
        self.assertEqual(one.permissions, ["network"])
        self.assertFalse(catalog.parse_index(index(entry()))[0].reviewed)

    def test_rejects_bad_indexes_whole(self):
        for bad in (
            {},
            {"format": "x", "version": 1, "plugins": []},
            index(entry(id="Bad Id")),
            index(entry(), entry()),
            index(entry(sha256="zz")),
            index(entry(download="http://example.org/a.zip")),
            index(entry(license="")),
            index(entry(permissions="network")),
            index(entry(api="2")),
        ):
            with self.subTest(bad), self.assertRaises(catalog.CatalogError):
                catalog.parse_index(bad)

    def test_check_download_compares_hash_api_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "plugin.py").write_text("import socket\n")
            good = catalog.parse_index(
                index(entry(sha256=folder_hash(folder), permissions=["network"]))
            )[0]
            catalog.check_download(good, folder, {1, 2})
            with self.assertRaises(catalog.CatalogError):
                catalog.check_download(good, folder, {1})
            good.permissions = []
            with self.assertRaises(catalog.CatalogError):
                catalog.check_download(good, folder, {2})
            good.permissions = ["network"]
            (folder / "plugin.py").write_text("import socket  # changed\n")
            with self.assertRaises(catalog.CatalogError):
                catalog.check_download(good, folder, {2})


if __name__ == "__main__":
    unittest.main()
