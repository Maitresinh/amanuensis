import json
from pathlib import Path
from unittest import TestCase

from amanuensis.search import AssembledExcerpt, SearchScope
from amanuensis.search_store import StoredBook
from amanuensis.webapp import SearchWebApplication


class _FakeStore:
    def resolve_scope(self, *, book_ids=(), corpus_id=None):
        selected = frozenset(item for item in book_ids if item == "book-1")
        if corpus_id and corpus_id != "essais":
            selected = frozenset()
        return SearchScope(selected, corpus_id=corpus_id)


class _FakeEngine:
    def __init__(self):
        self.store = _FakeStore()
        self.last_query = None

    def books(self, *, corpus_id=None):
        return [
            StoredBook(
                book_id="book-1",
                title="Les villes flottantes",
                source_path=str(Path("library", "villes.epub")),
                format="epub",
                status="indexable",
                message="",
                unit_count=7,
                corpus_ids=("essais",),
                indexed_at=1.0,
            )
        ]

    def corpus_ids(self):
        return ["essais"]

    def search(self, query):
        self.last_query = query
        return [
            AssembledExcerpt(
                book_id="book-1",
                unit_id="chapter-2",
                unit_label="Chapitre 2",
                unit_order=2,
                start=18,
                end=53,
                text="Le passage original, sans reecriture.",
                score=0.87,
                passage_ids=("passage-1",),
                channels=("dense", "sparse", "rrf"),
            )
        ]


class SearchWebApplicationTests(TestCase):
    def setUp(self):
        self.engine = _FakeEngine()
        self.app = SearchWebApplication(self.engine)

    def test_screen_and_assets_are_served(self):
        status, content_type, body = self.app.handle("GET", "/")

        self.assertEqual(200, status)
        self.assertEqual("text/html; charset=utf-8", content_type)
        self.assertIn(b"Recherche dans les livres", body)
        self.assertIn(b'id="corpus"', body)

    def test_catalogue_exposes_books_corpora_and_indexability(self):
        status, _, body = self.app.handle("GET", "/api/catalogue")
        payload = json.loads(body)

        self.assertEqual(200, status)
        self.assertEqual(["essais"], payload["corpora"])
        self.assertEqual("book-1", payload["books"][0]["book_id"])
        self.assertEqual("indexable", payload["books"][0]["status"])

    def test_search_returns_exact_excerpts_and_resolved_scope(self):
        request = json.dumps(
            {
                "query": "Comment fonctionnent les villes ?",
                "book_ids": ["book-1", "forbidden"],
                "corpus_id": "essais",
                "order": "reading",
            }
        ).encode("utf-8")

        status, _, body = self.app.handle("POST", "/api/search", request)
        payload = json.loads(body)

        self.assertEqual(200, status)
        self.assertEqual(["book-1"], payload["scope"]["book_ids"])
        self.assertEqual("Les villes flottantes", payload["excerpts"][0]["book_title"])
        self.assertEqual(
            "Le passage original, sans reecriture.",
            payload["excerpts"][0]["text"],
        )
        self.assertEqual(SearchScope(frozenset({"book-1"}), "essais"), self.engine.last_query.scope)

    def test_empty_resolved_scope_is_rejected(self):
        request = json.dumps({"query": "secret", "book_ids": ["forbidden"]}).encode("utf-8")

        status, _, body = self.app.handle("POST", "/api/search", request)

        self.assertEqual(400, status)
        self.assertIn("scope", json.loads(body)["error"])
