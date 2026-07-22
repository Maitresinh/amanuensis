from hashlib import sha256
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest import TestCase

from qdrant_client import QdrantClient

from amanuensis.adapters.qdrant import QdrantHybridPassageIndex
from amanuensis.hybrid import BGEM3Encoder, HybridEmbedding
from amanuensis.search import PassageQuery, SearchScope
from amanuensis.search_engine import PassageSearchEngine
from amanuensis.search_store import SQLiteSearchStore

from test_extraction import _write_epub


class _DeterministicHybridEncoder:
    dense_size = 16

    def encode_documents(self, texts):
        return [self._encode(text) for text in texts]

    def encode_query(self, text):
        return self._encode(text)

    def _encode(self, text):
        dense = [0.0] * self.dense_size
        sparse: dict[int, float] = {}
        for token in re.findall(r"\w+", text.casefold()):
            index = int.from_bytes(sha256(token.encode("utf-8")).digest()[:4], "big") % 4096
            dense[index % self.dense_size] += 1.0
            sparse[index] = sparse.get(index, 0.0) + 1.0
        indices = tuple(sorted(sparse))
        return HybridEmbedding(
            dense=tuple(dense),
            sparse_indices=indices,
            sparse_values=tuple(sparse[index] for index in indices),
        )


class _FakeBGEM3Model:
    def __init__(self):
        self.calls = []

    def encode(self, texts, **options):
        self.calls.append("encode")
        self.options = options
        return {
            "dense_vecs": [[1.0, 2.0] for _ in texts],
            "lexical_weights": [{"9": 0.5, "2": 1.25} for _ in texts],
        }


class _CurrentBGEM3Model(_FakeBGEM3Model):
    def encode_queries(self, texts, **options):
        self.calls.append("queries")
        return super().encode(texts, **options)

    def encode_corpus(self, texts, **options):
        self.calls.append("corpus")
        return super().encode(texts, **options)


class HybridSearchTests(TestCase):
    def test_bge_adapter_preserves_dense_and_sparse_outputs(self):
        model = _FakeBGEM3Model()
        encoder = BGEM3Encoder(model=model, batch_size=3, max_length=700)

        embedding = encoder.encode_query("energie solaire")

        self.assertEqual((1.0, 2.0), embedding.dense)
        self.assertEqual((2, 9), embedding.sparse_indices)
        self.assertEqual((1.25, 0.5), embedding.sparse_values)
        self.assertTrue(model.options["return_dense"])
        self.assertTrue(model.options["return_sparse"])
        self.assertFalse(model.options["return_colbert_vecs"])

    def test_bge_adapter_uses_current_query_and_corpus_entry_points(self):
        model = _CurrentBGEM3Model()
        encoder = BGEM3Encoder(model=model)

        encoder.encode_query("question")
        encoder.encode_documents(["passage"])

        self.assertEqual(["queries", "encode", "corpus", "encode"], model.calls)

    def test_epub_to_qdrant_to_exact_scoped_excerpt(self):
        with TemporaryDirectory() as directory:
            store = SQLiteSearchStore(Path(directory, "search.db"))
            index = QdrantHybridPassageIndex(
                QdrantClient(":memory:"),
                _DeterministicHybridEncoder(),
            )
            engine = PassageSearchEngine(store, index)
            first_path = Path(directory, "first.epub")
            second_path = Path(directory, "second.txt")
            _write_epub(first_path)
            second_path.write_text(
                "Ce document externe parle lui aussi d'energie solaire.",
                encoding="utf-8",
            )
            engine.index_file(
                "book-1",
                first_path,
                title="Villes flottantes",
                corpus_ids=frozenset({"corpus-fr"}),
            )
            engine.index_file(
                "book-2",
                second_path,
                title="Livre exclu",
                corpus_ids=frozenset({"autre-corpus"}),
            )
            query = PassageQuery(
                "comment les villes produisent-elles leur energie ?",
                SearchScope(frozenset({"book-1"}), corpus_id="corpus-fr"),
            )

            excerpts = engine.search(query)

        self.assertTrue(excerpts)
        self.assertEqual({"book-1"}, {item.book_id for item in excerpts})
        self.assertTrue(any("energie solaire" in item.text for item in excerpts))
        self.assertTrue(all("dense" in item.channels for item in excerpts))

    def test_qdrant_scope_filter_rejects_an_unselected_book(self):
        client = QdrantClient(":memory:")
        index = QdrantHybridPassageIndex(client, _DeterministicHybridEncoder())
        with TemporaryDirectory() as directory:
            store = SQLiteSearchStore(Path(directory, "search.db"))
            engine = PassageSearchEngine(store, index)
            for book_id in ("selected", "forbidden"):
                path = Path(directory, f"{book_id}.txt")
                path.write_text("Le meme passage remarquable sur Mars.", encoding="utf-8")
                engine.index_file(book_id, path, corpus_ids=frozenset({"all"}))
            query = PassageQuery("passage remarquable", SearchScope(frozenset({"selected"})))

            excerpts = engine.search(query)

        self.assertEqual({"selected"}, {item.book_id for item in excerpts})
