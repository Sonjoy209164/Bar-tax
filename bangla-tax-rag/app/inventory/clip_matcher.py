from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import httpx

from app.inventory.image_matcher import ImageMatchResult, ImageMatcher, primary_image_url

logger = logging.getLogger(__name__)

_clip_model = None
_clip_processor = None
_MODEL_NAME = "openai/clip-vit-base-patch32"
_HTTP_HEADERS = {"User-Agent": "bangla-tax-rag-image-search/1.0"}

# In-memory cache: product_id → embedding vector
_catalog_embeddings: dict[str, list[float]] = {}
_catalog_image_urls: dict[str, str] = {}
_catalog_embedding_mtime: float = 0.0
_catalog_embedding_signature: tuple[tuple[str, str], ...] = ()


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
        return _feature_to_vector(feat)
    except Exception as exc:
        logger.warning("CLIP image encode failed: %s", exc)
        return None


def _encode_image_bytes(raw: bytes) -> list[float] | None:
    model, processor = _load_clip()
    if model is None:
        return None
    try:
        import torch
        from PIL import Image  # type: ignore[import]

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        inputs = processor(images=img, return_tensors="pt")
        with torch.no_grad():
            feat = model.get_image_features(**inputs)
        return _feature_to_vector(feat)
    except Exception as exc:
        logger.warning("CLIP catalog image encode failed: %s", exc)
        return None


def _encode_image_source(source: str) -> list[float] | None:
    try:
        if source.startswith(("http://", "https://")):
            resp = httpx.get(source, timeout=8.0, follow_redirects=True, headers=_HTTP_HEADERS)
            resp.raise_for_status()
            return _encode_image_bytes(resp.content)
        path = Path(source)
        if path.exists():
            return _encode_image_bytes(path.read_bytes())
    except Exception as exc:
        logger.warning("CLIP image source load failed for %s: %s", source, exc)
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
        return _feature_to_vector(feat)
    except Exception as exc:
        logger.warning("CLIP text encode failed: %s", exc)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))  # vectors are already normalized


def _feature_to_vector(feature: Any) -> list[float] | None:
    if hasattr(feature, "pooler_output"):
        feature = feature.pooler_output
    elif hasattr(feature, "last_hidden_state"):
        feature = feature.last_hidden_state[:, 0]
    elif isinstance(feature, tuple):
        feature = feature[0]
    if feature is None:
        return None
    feature = feature / feature.norm(dim=-1, keepdim=True)
    return feature[0].tolist()


def precompute_catalog_embeddings(
    catalog: dict[str, Any],
    force: bool = False,
) -> int:
    """
    Encode each catalog product's name+description as a CLIP text embedding.
    Stores results in the in-memory cache.  Returns number of items encoded.
    Only runs if CLIP is available.
    """
    global _catalog_embeddings, _catalog_image_urls, _catalog_embedding_signature
    signature = _catalog_signature(catalog)
    if not force and _catalog_embeddings and _catalog_embedding_signature == signature:
        return len(_catalog_embeddings)
    model, _ = _load_clip()
    if model is None:
        return 0

    items = list(catalog.values())
    texts = []
    ids = []
    image_vectors: dict[str, list[float]] = {}
    image_urls: dict[str, str] = {}
    for item in items:
        if hasattr(item, "name"):
            image_url = primary_image_url(item)
            if image_url:
                vec = _encode_image_source(image_url)
                if vec is not None:
                    pid = item.product_id
                    image_vectors[pid] = vec
                    image_urls[pid] = image_url
                    continue
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
    new_cache: dict[str, list[float]] = dict(image_vectors)
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        try:
            inputs = processor(text=batch_texts, return_tensors="pt", padding=True, truncation=True, max_length=77)
            with torch.no_grad():
                feats = _clip_model.get_text_features(**inputs)
                if hasattr(feats, "pooler_output"):
                    feats = feats.pooler_output
                elif hasattr(feats, "last_hidden_state"):
                    feats = feats.last_hidden_state[:, 0]
                elif isinstance(feats, tuple):
                    feats = feats[0]
                feats = feats / feats.norm(dim=-1, keepdim=True)
            for pid, vec in zip(batch_ids, feats.tolist()):
                if pid:
                    new_cache[pid] = vec
        except Exception as exc:
            logger.warning("CLIP batch encode failed at index %d: %s", i, exc)

    _catalog_embeddings = new_cache
    _catalog_image_urls = image_urls
    _catalog_embedding_signature = signature
    logger.info("CLIP: precomputed %d catalog embeddings", len(_catalog_embeddings))
    return len(_catalog_embeddings)


def _catalog_signature(catalog: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    signature: list[tuple[str, str]] = []
    for product_id, item in sorted(catalog.items()):
        image_source = primary_image_url(item) or ""
        updated_at = getattr(item, "updated_at", "") if hasattr(item, "updated_at") else str(item.get("updated_at", ""))
        name = getattr(item, "name", "") if hasattr(item, "name") else str(item.get("name", ""))
        signature.append((str(product_id), f"{image_source}|{updated_at}|{name}"))
    return tuple(signature)


class CLIPImageMatcher:
    """
    Visual similarity search using CLIP embeddings.
    Falls back gracefully to metadata-based ImageMatcher if CLIP unavailable.
    """

    def __init__(self) -> None:
        pass

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
        if catalog:
            # Fast no-op when the catalog signature is unchanged; rebuilds when images/products change.
            precompute_catalog_embeddings(catalog)

        query_vec: list[float] | None = None
        if image_b64:
            query_vec = _encode_image_b64(image_b64)
        if query_vec is None and query_text:
            query_vec = _encode_text(query_text)

        if query_vec is None or not _catalog_embeddings:
            # Fall back to metadata matcher
            return ImageMatcher(catalog or {}).search(
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
                    image_url=_catalog_image_urls.get(pid) or primary_image_url(item),
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
