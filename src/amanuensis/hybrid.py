"""Hybrid embedding contracts and the BGE-M3 adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class HybridEmbedding:
    dense: tuple[float, ...]
    sparse_indices: tuple[int, ...]
    sparse_values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.dense:
            raise ValueError("dense embedding must not be empty")
        if len(self.sparse_indices) != len(self.sparse_values):
            raise ValueError("sparse indices and values must have the same length")


class HybridEncoder(Protocol):
    @property
    def dense_size(self) -> int: ...

    def encode_documents(self, texts: Sequence[str]) -> list[HybridEmbedding]: ...

    def encode_query(self, text: str) -> HybridEmbedding: ...


class BGEM3Encoder:
    """Lazy FlagEmbedding adapter exposing BGE-M3 dense and lexical signals."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        *,
        use_fp16: bool = True,
        batch_size: int = 8,
        max_length: int = 1_200,
        model: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self.batch_size = batch_size
        self.max_length = max_length
        self._model = model

    @property
    def dense_size(self) -> int:
        # BAAI/bge-m3 emits 1024-dimensional dense vectors.
        return 1_024

    def encode_documents(self, texts: Sequence[str]) -> list[HybridEmbedding]:
        if not texts:
            return []
        return self._encode(list(texts), query=False)

    def encode_query(self, text: str) -> HybridEmbedding:
        if not text.strip():
            raise ValueError("query text must not be empty")
        return self._encode([text], query=True)[0]

    def _encode(self, texts: list[str], *, query: bool) -> list[HybridEmbedding]:
        model = self._load_model()
        method = getattr(model, "encode_queries" if query else "encode_corpus", None)
        if method is None:
            method = model.encode
        output = method(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense_vectors = output["dense_vecs"]
        lexical_weights = output["lexical_weights"]
        embeddings: list[HybridEmbedding] = []
        for dense, weights in zip(dense_vectors, lexical_weights, strict=True):
            dense_values = dense.tolist() if hasattr(dense, "tolist") else list(dense)
            sparse = sorted((int(index), float(value)) for index, value in weights.items())
            embeddings.append(
                HybridEmbedding(
                    dense=tuple(float(value) for value in dense_values),
                    sparse_indices=tuple(item[0] for item in sparse),
                    sparse_values=tuple(item[1] for item in sparse),
                )
            )
        return embeddings

    def _load_model(self):
        if self._model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as exc:
                raise RuntimeError(
                    "BGE-M3 requires the optional dependency: pip install 'amanuensis-library[bge]'"
                ) from exc
            self._model = BGEM3FlagModel(self.model_name, use_fp16=self.use_fp16)
        return self._model
