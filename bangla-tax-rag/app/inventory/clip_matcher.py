from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.inventory.image_matcher import ImageMatchResult, ImageMatcher

logger = logging.getLogger(__name__)

_clip_model = None
_clip_processor = None
_MODEL_NAME = "openai/clip-vit-base-patch32"

# In-memory cache: product_id → embedding vector
_catalog_embeddings: dict[str, list[float]] = {}
_catalog_embedding_mtime: float = 0.0


def _load_clip():
    global _clip_model, _clip_processor
    if _clip_model is not None:
        return _clip_model, _clip_processor
    try:
        from transformers import CLIPModel, CLIPProcessor  # type: ignore[import]
        logger.info("Loading CLIP model: %s", _MODEL_NAME)
        _clip_processor = CLIPProcessor.from_pretrained(_MODEL_NAME)
        _clip_model = CLIPModel.from_pretrained(_MODEL_NAME)
        _clip_model.eval()
        logger.info("CLIP model loaded successfully")
    except ImportError:
        logger.warning(
            "transformers not installed. "
            "Run: pip install transformers Pillow torch  "
            "Falling back to metadata-based image matching."
        )
        _clip_model = None
        _clip_processor = None
    except Exception as exc:
        logger.warning("Failed to load CLIP model: %s. Falling back to metadata matching.", exc)
        _clip_model = None
        _clip_processor = None
    return _clip_model, _clip_processor


def _encode_image_b64(image_b64: str) -> list[float] | None:
    model, processor = _load_clip()
    if model is None:
        return None
    try:
        import torch
        from PIL import Image  # type: ignore[import]
        raw = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        inputs = processor(images=img, return_tensors="pt")
        with torch.no_grad():
            feat = model.get_image_features(**inputs)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat[0].tolist()
    except Exception as exc:
        logger.warning("CLIP image encode failed: %s", exc)
        return None


def _encode_text(text: str) -> list[float] | None:
    model, processor = _load_clip()
    if model is None:
        return None
    try:
        import torch
        inputs = processor(text=[text], return_tensors="pt", padding=True, truncation=True, max_length=77)
        with torch.no_grad():
            feat = model.get_text_features(**inputs)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat[0].tolist()
    except Exception as exc:
        logger.warning("CLIP text encode failed: %s", exc)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))  # vectors are already normalized


def precompute_catalog_embeddings(
    catalog: dict[str, Any],
    force: bool = False,
) -> int:
    """
    Encode each catalog product's name+description as a CLIP text embedding.
    Stores results in the in-memory cache.  Returns number of items encoded.
    Only runs if CLIP is available.
    """
    global _catalog_embeddings
    if not force and _catalog_embeddings:
        return len(_catalog_embeddings)
    model, _ = _load_clip()
    if model is None:
        return 0

    items = list(catalog.values())
    texts = []
    ids = []
    for item in items:
        if hasattr(item, "name"):
            desc = (item.name or "") + " " + (getattr(item, "short_description", "") or "")
            attrs = item.attributes or {}
            for k in ("color", "fabric", "work_type", "occasion"):
                if attrs.get(k):
                    desc += " " + attrs[k]
        else:
            desc = str(item.get("name", "")) + " " + str(item.get("short_description", ""))
        texts.append(desc.strip()[:200])
        ids.append(item.product_id if hasattr(item, "product_id") else item.get("product_id", ""))

    # Encode in batches of 32
    import torch
    from transformers import CLIPProcessor, CLIPModel  # already loaded
    processor = _clip_processor
    new_cache: dict[str, list[float]] = {}
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        try:
            inputs = processor(text=batch_texts, return_tensors="pt", padding=True, truncation=True, max_length=77)
            with torch.no_grad():
                feats = _clip_model.get_text_features(**inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            for pid, vec in zip(batch_ids, feats.tolist()):
                if pid:
                    new_cache[pid] = vec
        except Exception as exc:
            logger.warning("CLIP batch encode failed at index %d: %s", i, exc)

    _catalog_embeddings = new_cache
    logger.info("CLIP: precomputed %d catalog embeddings", len(_catalog_embeddings))
    return len(_catalog_embeddings)


class CLIPImageMatcher:
    """
    Visual similarity search using CLIP embeddings.
    Falls back gracefully to metadata-based ImageMatcher if CLIP unavailable.
    """

    def __init__(self) -> None:
        self._fallback = ImageMatcher()

    def search(
        self,
        query_text: str = "",
        image_b64: str | None = None,
        catalog: dict[str, Any] | None = None,
        category_hint: str | None = None,
        color_hint: str | None = None,
        budget_max: float | None = None,
        top_k: int = 5,
    ) -> list[ImageMatchResult]:
        if catalog and _catalog_embeddings:
            # Precompute if not done yet
            if len(_catalog_embeddings) < len(catalog) // 2:
                precompute_catalog_embeddings(catalog)

        query_vec: list[float] | None = None
        if image_b64:
            query_vec = _encode_image_b64(image_b64)
        if query_vec is None and query_text:
            query_vec = _encode_text(query_text)

        if query_vec is None or not _catalog_embeddings:
            # Fall back to metadata matcher
            return self._fallback.search(
                query_text=query_text,
                image_b64=image_b64 or "",
                category_hint=category_hint,
                color_hint=color_hint,
                budget_max=budget_max,
                top_k=top_k,
            )

        results: list[ImageMatchResult] = []
        for pid, item_vec in _catalog_embeddings.items():
            if catalog and pid not in catalog:
                continue
            score = _cosine(query_vec, item_vec)
            if catalog:
                item = catalog[pid]
                if budget_max and item.price and item.price > budget_max:
                    continue
                if item.stock == 0:
                    score *= 0.3
                results.append(ImageMatchResult(
                    product_id=pid,
                    name=item.name,
                    score=round(score, 4),
                    match_type="visual_similar",
                    reasons=("CLIP visual embedding match",),
                    price=item.price,
                    currency=item.currency,
                    stock=item.stock,
                ))
            else:
                results.append(ImageMatchResult(
                    product_id=pid,
                    name=pid,
                    score=round(score, 4),
                    match_type="visual_similar",
                    reasons=("CLIP visual embedding match",),
                ))

        results.sort(key=lambda r: -r.score)
        return results[:top_k]

    def build_answer(self, results: list[ImageMatchResult], query_text: str = "") -> str:
        if not results:
            return "No visually similar products found in the catalog."
        in_stock = [r for r in results if r.stock > 0]
        out_stock = [r for r in results if r.stock == 0]
        parts: list[str] = []
        if in_stock:
            parts.append(f"Found {len(in_stock)} visually similar in-stock item(s):")
            for r in in_stock[:3]:
                price_str = f"BDT {r.price:,.0f}" if r.price else ""
                method = "CLIP visual match" if "CLIP" in (r.reasons[0] if r.reasons else "") else "metadata match"
                parts.append(f"  • {r.name}" + (f" — {price_str}" if price_str else "") + f" ({r.stock} in stock) [{method}]")
        if out_stock:
            parts.append(f"\n{len(out_stock)} similar item(s) currently out of stock.")
        parts.append("\nNote: Visual similarity match — exact same SKU can only be confirmed with a product code.")
        return "\n".join(parts)

    @staticmethod
    def is_available() -> bool:
        return _load_clip()[0] is not None
