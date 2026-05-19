"""Embeddings for Topic.our_understanding and Chapter.summary.

Two providers behind one interface:
  - SentenceTransformer  (default, local, free, 384 dims)
  - OpenAI               (opt-in, 1536 dims, costs $)

The chosen provider lives in config.embedding. Vector index dimensions in
Neo4j are derived from this config, so the two stay aligned.

Embeddings are written **in memory** on the extraction result; the ingestion
phase persists them to Neo4j with everything else.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ...config import EmbeddingConfig
from ..models import Chapter, CurriculumExtractionResult, Topic

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class EmbeddingProvider(ABC):
    """Sync interface; the generator wraps calls in asyncio.to_thread."""

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerProvider(EmbeddingProvider):
    """Local embeddings via sentence-transformers (default).

    all-MiniLM-L6-v2 is the sane default — 384 dims, ~80MB, very fast on MPS.
    Loads lazily on first call so import-time stays cheap.
    """

    def __init__(self, model_name: str, device: str = "auto"):
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self._model = None
        self._dimensions: int | None = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "sentence-transformers not installed. Run: poetry install"
                ) from e
            logger.info("Loading sentence-transformer %s on %s", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._dimensions = self._model.get_sentence_embedding_dimension()
        return self._model

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            self._ensure_model()
        return int(self._dimensions or 0)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        out = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [vec.tolist() for vec in out]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text-embedding-3-small (cloud, costs $)."""

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536, api_key: str | None = None):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            input=texts, model=self._model, dimensions=self._dimensions,
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]


def create_embedding_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "sentence_transformers":
        return SentenceTransformerProvider(model_name=config.model, device=config.device)
    if config.provider == "openai":
        return OpenAIEmbeddingProvider(model=config.model, dimensions=config.dimensions)
    raise ValueError(f"Unknown embedding provider: {config.provider!r}")


# ---------------------------------------------------------------------------
# Report + Generator
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingReport:
    chapters_embedded: int = 0
    topics_embedded: int = 0
    chapters_skipped_existing: int = 0
    topics_skipped_existing: int = 0
    failures: int = 0
    elapsed_seconds: float = 0.0
    error_details: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Embeddings — {self.chapters_embedded} chapters, {self.topics_embedded} topics "
            f"({self.chapters_skipped_existing}+{self.topics_skipped_existing} reused), "
            f"{self.failures} failures, {self.elapsed_seconds:.1f}s"
        )


class EmbeddingGenerator:
    def __init__(self, provider: EmbeddingProvider, batch_size: int = 64):
        self.provider = provider
        self.batch_size = batch_size

    async def embed_extraction(
        self,
        extraction: CurriculumExtractionResult,
        existing_chapter_ids_with_embedding: set[str] | None = None,
        existing_topic_ids_with_embedding: set[str] | None = None,
    ) -> EmbeddingReport:
        report = EmbeddingReport()
        start = time.monotonic()

        existing_chapters = existing_chapter_ids_with_embedding or set()
        existing_topics = existing_topic_ids_with_embedding or set()

        chapter_items = [
            (c, self._compose_chapter_text(c))
            for c in extraction.chapters
            if c.chapter_id not in existing_chapters and self._compose_chapter_text(c).strip()
        ]
        report.chapters_skipped_existing = len(extraction.chapters) - len(chapter_items)

        topic_items = [
            (t, self._compose_topic_text(t))
            for t in extraction.topics
            if t.topic_id not in existing_topics and self._compose_topic_text(t).strip()
        ]
        report.topics_skipped_existing = len(extraction.topics) - len(topic_items)

        await self._embed_items(chapter_items, report, label="chapter")
        await self._embed_items(topic_items, report, label="topic")

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    async def _embed_items(
        self, items: list[tuple], report: EmbeddingReport, *, label: str,
    ) -> None:
        if not items:
            return
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            texts = [text for (_, text) in batch]
            try:
                vectors = await asyncio.to_thread(self.provider.embed_batch, texts)
                for (node, _), vec in zip(batch, vectors):
                    node.embedding = list(vec)
                    if isinstance(node, Chapter):
                        report.chapters_embedded += 1
                    elif isinstance(node, Topic):
                        report.topics_embedded += 1
            except Exception as e:
                report.failures += len(batch)
                report.error_details.append(f"{label} batch {i}: {e}")
                logger.error("Embedding %s batch %d failed: %s", label, i, e)

    @staticmethod
    def _compose_chapter_text(chapter: Chapter) -> str:
        return f"{chapter.title}. {chapter.summary}"

    @staticmethod
    def _compose_topic_text(topic: Topic) -> str:
        return f"{topic.topic_name}: {topic.our_understanding}"
