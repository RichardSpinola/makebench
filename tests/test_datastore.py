# SPDX-License-Identifier: GPL-3.0-or-later
"""Stored records: migration, references, filters and the ctx.data wrapper."""

import support  # noqa: F401  (first: isolates settings and data)
import tempfile
import unittest
from pathlib import Path

from makebench.core.datastore import DataError, DataStore, data_path
from makebench.core.project import Project
from makebench.runtime.worker import Data, TaskError

AUTHORS = {
    "id": "authors",
    "name": "Autores",
    "fields": [
        {"id": "name", "name": "nome", "type": "text"},
        {"id": "born", "name": "nascimento", "type": "date"},
    ],
}
BOOKS = {
    "id": "books",
    "name": "Livros",
    "fields": [
        {"id": "title", "name": "titulo", "type": "text"},
        {"id": "pages", "name": "paginas", "type": "number"},
        {"id": "read", "name": "lido", "type": "bool"},
        {"id": "author", "name": "autor", "type": "ref", "target": "authors"},
    ],
}


class DataStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = DataStore(":memory:", [AUTHORS, BOOKS])
        self.addCleanup(self.store.close)
        self.machado = self.store.add("Autores", nome="Machado de Assis", nascimento="1839-06-21")
        self.dom = self.store.add(
            "Livros", titulo="Dom Casmurro", paginas=256, lido=True, autor=self.machado
        )
        self.store.add(
            "Livros", titulo="Quincas Borba", paginas=300, lido=False, autor=self.machado
        )

    def test_listing_shows_names_for_references_and_keeps_ids(self):
        listing = self.store.listing("Livros", self.store.find("Livros", "lido", "=", True))
        self.assertEqual(listing["headers"], ["titulo", "paginas", "lido", "autor"])
        self.assertEqual(listing["rows"], [["Dom Casmurro", "256", "Yes", "Machado de Assis"]])
        self.assertEqual(listing["ids"], [self.dom])
        self.assertEqual(listing["names"], ["Dom Casmurro"])
        self.assertEqual(len(self.store.listing("Livros")["rows"]), 2)
        with self.assertRaises(DataError):
            self.store.listing("Livros", [{"titulo": "x"}])

    def test_records_roundtrip_with_types(self):
        self.assertEqual(
            self.store.get("Livros", self.dom),
            {
                "id": self.dom,
                "titulo": "Dom Casmurro",
                "paginas": 256,
                "lido": True,
                "autor": self.machado,
            },
        )
        self.assertIsNone(self.store.get("Livros", 999))
        self.store.update("Livros", self.dom, paginas=260.5, lido=False)
        record = self.store.get("Livros", self.dom)
        self.assertEqual((record["paginas"], record["lido"]), (260.5, False))

    def test_find_count_sum_and_order(self):
        self.assertEqual(self.store.count("Livros"), 2)
        self.assertEqual(self.store.count("Livros", "lido", "=", True), 1)
        self.assertEqual(self.store.count("Livros", "autor", "=", self.machado), 2)
        self.assertEqual(self.store.sum("Livros", "paginas"), 556)
        self.assertEqual(self.store.sum("Livros", "paginas", "lido", "=", False), 300)
        self.assertEqual(self.store.sum("Livros", "paginas", "paginas", ">", 1000), 0)
        titles = [r["titulo"] for r in self.store.find("Livros", "titulo", "contains", "Casm")]
        self.assertEqual(titles, ["Dom Casmurro"])
        by_pages = self.store.find("Livros", order="paginas", descending=True)
        self.assertEqual([r["paginas"] for r in by_pages], [300, 256])
        self.assertEqual(len(self.store.find("Livros", "id", "=", self.dom)), 1)
        self.assertEqual(len(self.store.find("Livros", "titulo", "contains", "%")), 0)

    def test_reference_blocks_deletion_and_shows_the_name(self):
        self.assertEqual(self.store.name("Autores", self.machado), "Machado de Assis")
        self.assertEqual(self.store.name("Autores", 999), "")
        with self.assertRaisesRegex(DataError, "2 records of Livros"):
            self.store.delete("Autores", self.machado)
        for book in self.store.find("Livros"):
            self.store.delete("Livros", book["id"])
        self.store.delete("Autores", self.machado)
        self.assertEqual(self.store.count("Autores"), 0)

    def test_invalid_requests_are_refused(self):
        for call in (
            lambda: self.store.add("Nada", nome="x"),
            lambda: self.store.add("Livros", titulo=3),
            lambda: self.store.add("Livros", paginas=True),
            lambda: self.store.add("Livros", lido=1),
            lambda: self.store.add("Livros", nao_existe="x"),
            lambda: self.store.add("Autores", nascimento="31/12/2020"),
            lambda: self.store.add("Livros", autor=999),
            lambda: self.store.update("Livros", 999, titulo="x"),
            lambda: self.store.find("Livros", "titulo", "like", "x"),
            lambda: self.store.sum("Livros", "titulo"),
        ):
            with self.assertRaises(DataError):
                call()

    def test_reopening_migrates_without_losing_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep" / "data.sqlite"
            first = DataStore(path, [AUTHORS])
            author = first.add("Autores", nome="Clarice")
            first.close()
            extended = {
                **AUTHORS,
                "fields": [*AUTHORS["fields"], {"id": "city", "name": "cidade", "type": "text"}],
            }
            second = DataStore(path, [extended, BOOKS])
            self.addCleanup(second.close)
            self.assertEqual(second.get("Autores", author)["nome"], "Clarice")
            self.assertIsNone(second.get("Autores", author)["cidade"])
            second.update("Autores", author, cidade="Recife")
            second.add("Livros", titulo="A Hora da Estrela", autor=author)
            with self.assertRaises(DataError):
                second.delete("Autores", author)
            # A field dropped from the project is ignored, not erased.
            third = DataStore(path, [AUTHORS, BOOKS])
            self.addCleanup(third.close)
            self.assertNotIn("cidade", third.get("Autores", author))

    def test_worker_wrapper_turns_errors_into_task_errors(self):
        data = Data(lambda: DataStore(":memory:", [AUTHORS]))
        self.assertEqual(data.add("Autores", nome="A"), 1)
        self.assertEqual(data.find("Autores")[0]["nome"], "A")
        with self.assertRaises(TaskError):
            data.add("Nada")
        data.close()

    def test_data_path_separates_testing_from_the_app(self):
        project = Project.empty("Library")
        project.application["id"] = "org.example.Library"
        self.assertEqual(
            data_path(project, False).parts[-2:], ("org.example.Library", "data.sqlite")
        )
        testing = data_path(project, True)
        self.assertIn("test-data", testing.parts)
        self.assertTrue(testing.parts[-2].startswith("project"))


if __name__ == "__main__":
    unittest.main()
