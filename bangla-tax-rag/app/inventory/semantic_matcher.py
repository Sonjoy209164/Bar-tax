"""
Embedding-based catalog matcher.

Replaces alias-dictionary filtering with semantic similarity so the bot
understands new variants without code changes:

  "biye-r jonno saree"       → matches catalog entries tagged "wedding"
  "haldi-r holud saree"      → matches "ceremonial / pre-wedding" sarees
  "ayer ma jonno gift"       → matches gift-style items
  "matha gorom kora rong"    → matches bright/festive colors

How it works:
  1. On catalog load, embed each product's "rich text" (name + category +
     fabric + color + occasion + work type + brand + description) once
     and cache the vector matrix.
  2. At query time, embed the customer question and compute cosine
     similarity against the cached matrix.
  3. Return the top-K product_ids with similarity scores.

Failure mode: if the embedding model isn't available, the whole module
returns None and the caller falls back to the existing regex filter path.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Iterable

from app.core.schemas import InventoryItemRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SemanticMatch:
    product_id: str
    score: float
    matched_text: str  # the rich-text representation that produced the embedding


class SemanticCatalogMatcher:
    """
    Holds an embedding index over a catalog. Rebuilt when catalog changes.

    The index is computed lazily — first call to `retrieve` triggers the
    build. After that, retrieves reuse the cached matrix.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._catalog_signature: str | None = None
        self._product_ids: list[str] = []
        self._matrix = None  # numpy array, lazy
        self._rich_texts: list[str] = []
        self._embedder = None
        self._available: bool | None = None  # tri-state: unknown / yes / no

    # ── Public API ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        *,
        question: str,
        catalog: dict[str, InventoryItemRecord],
        top_k: int = 8,
        min_score: float = 0.20,
    ) -> list[SemanticMatch] | None:
        """
        Return the top-K most semantically similar products.
        Returns None if the embedder is unavailable — caller should fall back.
        """
        if not question.strip() or not catalog:
            return []
        try:
            self._ensure_index(catalog)
        except Exception as exc:
            logger.debug("Semantic index build failed: %s", exc)
            return None
        if self._matrix is None or self._available is False:
            return None
        try:
            import numpy as np
            query_vec = self._embed_query(question)
            if query_vec is None:
                return None
            sims = self._matrix @ np.asarray(query_vec, dtype="float32")
            order = np.argsort(-sims)
            results: list[SemanticMatch] = []
            for idx in order[:top_k]:
                score = float(sims[idx])
                if score < min_score:
                    break
                results.append(SemanticMatch(
                    product_id=self._product_ids[idx],
                    score=score,
                    matched_text=self._rich_texts[idx],
                ))
            return results
        except Exception as exc:
            logger.debug("Semantic retrieve failed: %s", exc)
            return None

    def is_available(self) -> bool:
        """True if the embedding model loaded successfully at least once."""
        return self._available is True

    # ── Internals ──────────────────────────────────────────────────────────

    def _ensure_index(self, catalog: dict[str, InventoryItemRecord]) -> None:
        signature = self._catalog_signature_for(catalog)
        with self._lock:
            if self._catalog_signature == signature and self._matrix is not None:
                return
            self._build_index(catalog)
            self._catalog_signature = signature

    def _build_index(self, catalog: dict[str, InventoryItemRecord]) -> None:
        import numpy as np

        product_ids: list[str] = []
        rich_texts: list[str] = []
        for product_id, item in catalog.items():
            rich_texts.append(_render_product_text(item))
            product_ids.append(product_id)

        embedder = self._get_embedder()
        if embedder is None:
            self._available = False
            return

        batch = embedder.embed_texts(rich_texts)
        if not batch.vectors:
            self._available = False
            return

        # If we got the deterministic fallback, mark unavailable so caller
        # can choose to skip semantic matching entirely (deterministic
        # vectors don't carry semantic signal worth using).
        model_name = (batch.model_name or "").lower()
        if "deterministic" in model_name or "hash" in model_name:
            self._available = False
            return

        matrix = np.asarray(batch.vectors, dtype="float32")
        # Normalize rows for cosine via dot product
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms

        self._matrix = matrix
        self._product_ids = product_ids
        self._rich_texts = rich_texts
        self._available = True

    def _embed_query(self, question: str):
        import numpy as np
        embedder = self._get_embedder()
        if embedder is None:
            return None
        batch = embedder.embed_texts([question])
        if not batch.vectors:
            return None
        vec = np.asarray(batch.vectors[0], dtype="float32")
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from app.retrieval.embedder import (
                EmbedderConfig,
                EmbeddingProvider,
                build_embedder,
            )
            cfg = EmbedderConfig(provider=EmbeddingProvider.MULTILINGUAL, normalize=True)
            self._embedder = build_embedder(cfg)
            return self._embedder
        except Exception as exc:
            logger.debug("Embedder construction failed: %s", exc)
            return None

    @staticmethod
    def _catalog_signature_for(catalog: dict[str, InventoryItemRecord]) -> str:
        """A cheap fingerprint that changes when the catalog content changes."""
        parts: list[str] = []
        for pid, item in catalog.items():
            parts.append(f"{pid}:{item.name}:{item.price}:{item.stock}")
        return "|".join(sorted(parts))


def _render_product_text(item: InventoryItemRecord) -> str:
    """
    Build a single sentence-ish representation of the product covering all
    attributes that a customer might mention. Embedding models work best on
    natural-language-style text, not key:value bags.
    """
    attrs = item.attributes or {}
    parts = [item.name or "", item.category or ""]

    for key in (
        "color", "color_family", "fabric", "occasion", "work_type",
        "style", "brand", "design_id", "size",
    ):
        v = attrs.get(key)
        if v:
            parts.append(str(v))

    desc = (item.full_description or item.short_description or "").strip()
    if desc:
        parts.append(desc)

    # Tag-like fields
    for key in ("tags", "compatible_design_ids", "occasions"):
        v = attrs.get(key)
        if isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))

    text = " ".join(p.strip() for p in parts if p)
    return text or (item.name or item.product_id)


# Module-level singleton — one matcher per process is plenty.
_matcher: SemanticCatalogMatcher | None = None


def get_semantic_matcher() -> SemanticCatalogMatcher:
    global _matcher
    if _matcher is None:
        _matcher = SemanticCatalogMatcher()
    return _matcher
