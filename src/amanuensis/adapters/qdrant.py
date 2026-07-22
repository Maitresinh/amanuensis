"""Qdrant-backed dense+sparse passage retrieval."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..hybrid import HybridEncoder
from ..search import IndexDocument, Passage, PassageQuery, SearchHit


class QdrantHybridPassageIndex:
    def __init__(
        self,
        client: Any,
        encoder: HybridEncoder,
        *,
        collection_name: str = "amanuensis_passages",
    ) -> None:
        self.client = client
        self.encoder = encoder
        self.collection_name = collection_name
        self._ensure_collection()

    def delete_books(self, book_ids: frozenset[str]) -> None:
        if not book_ids:
            return
        models = _models()
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=_scope_filter(book_ids, None)),
            wait=True,
        )

    def index(self, passages: Iterable[IndexDocument]) -> None:
        documents = list(passages)
        if not documents:
            return
        models = _models()
        batch_size = 32
        for offset in range(0, len(documents), batch_size):
            batch = documents[offset : offset + batch_size]
            embeddings = self.encoder.encode_documents([item.text for item in batch])
            if len(embeddings) != len(batch):
                raise ValueError("encoder returned a different number of embeddings")
            points = []
            for document, embedding in zip(batch, embeddings, strict=True):
                passage = document.passage
                points.append(
                    models.PointStruct(
                        id=passage.passage_id,
                        vector={
                            "dense": list(embedding.dense),
                            "sparse": models.SparseVector(
                                indices=list(embedding.sparse_indices),
                                values=list(embedding.sparse_values),
                            ),
                        },
                        payload={
                            "passage_id": passage.passage_id,
                            "book_id": passage.book_id,
                            "unit_id": passage.unit_id,
                            "ordinal": passage.ordinal,
                            "start": passage.start,
                            "end": passage.end,
                            "corpus_ids": sorted(document.corpus_ids),
                        },
                    )
                )
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )

    def search(self, query: PassageQuery) -> list[SearchHit]:
        models = _models()
        embedding = self.encoder.encode_query(query.text)
        query_filter = _scope_filter(query.scope.book_ids, query.scope.corpus_id)
        candidate_limit = max(20, min(400, query.limit * 4))
        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=list(embedding.dense),
                    using="dense",
                    filter=query_filter,
                    limit=candidate_limit,
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=list(embedding.sparse_indices),
                        values=list(embedding.sparse_values),
                    ),
                    using="sparse",
                    filter=query_filter,
                    limit=candidate_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=query.limit,
            with_payload=True,
            with_vectors=False,
        )
        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            book_id = str(payload.get("book_id", ""))
            if book_id not in query.scope.book_ids:
                raise ValueError(f"Qdrant returned out-of-scope book {book_id!r}")
            if query.scope.corpus_id and query.scope.corpus_id not in payload.get("corpus_ids", []):
                raise ValueError(f"Qdrant returned book outside corpus {query.scope.corpus_id!r}")
            passage = Passage(
                passage_id=str(payload["passage_id"]),
                book_id=book_id,
                unit_id=str(payload["unit_id"]),
                ordinal=int(payload["ordinal"]),
                start=int(payload["start"]),
                end=int(payload["end"]),
            )
            hits.append(SearchHit(passage, float(point.score), ("dense", "sparse", "rrf")))
        return hits

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        models = _models()
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.encoder.dense_size,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )


def _scope_filter(book_ids: frozenset[str], corpus_id: str | None):
    models = _models()
    conditions = [
        models.FieldCondition(
            key="book_id",
            match=models.MatchAny(any=sorted(book_ids)),
        )
    ]
    if corpus_id:
        conditions.append(
            models.FieldCondition(
                key="corpus_ids",
                match=models.MatchValue(value=corpus_id),
            )
        )
    return models.Filter(must=conditions)


def _models():
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError(
            "Qdrant search requires qdrant-client; install the Amanuensis package first"
        ) from exc
    return models
