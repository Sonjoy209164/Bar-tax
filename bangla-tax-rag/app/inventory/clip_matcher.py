from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.inventory.image_matcher import ImageMatchResult, ImageMatcher, primary_image_url

logger = logging.getLogger(__name__)

_clip_model = None
_clip_processor = None
_MODEL_NAME = "openai/clip-vit-base-patch32"
_MODEL_VERSION = "clip-vit-base-patch32-v1"
# Bump when the channel layout / preprocessing changes so stale vectors are rebuilt.
EMBEDDING_VERSION = "image-embedding-v2"
_HTTP_HEADERS = {"User-Agent": "bangla-tax-rag-image-search/1.0"}

# Channel suffixes appended to the embedding key.
#   {pid}::{image_id}             -> full_visual   (color + shape + category)
#   {pid}::{image_id}::pattern    -> pattern_visual (grayscale, color-invariant design)
#   {pid}::text                   -> text_visual_tags (name/attribute fallback)
_PATTERN_SUFFIX = "::pattern"

# Persisted cache so cold start does not re-encode the whole catalog.
_CACHE_PATH = Path(os.environ.get("IMAGE_SEARCH_CLIP_CACHE_PATH", "data/inventory/clip_embeddings_cache.json"))
_MAX_SYNC_PRECOMPUTE_ITEMS = int(os.environ.get("IMAGE_SEARCH_MAX_SYNC_PRECOMPUTE_ITEMS", "300"))
_ALLOW_SYNC_PRECOMPUTE = os.environ.get("IMAGE_SEARCH_ALLOW_SYNC_PRECOMPUTE", "").casefold() in {
    "1",
    "true",
    "yes",
}
_LOCAL_FILES_ONLY = os.environ.get("IMAGE_SEARCH_CLIP_LOCAL_ONLY", "1").casefold() not in {
    "0",
    "false",
    "no",
}

# A channel counts as "matched" for the agreement gate when its cosine clears
# this floor. Low enough that genuine fashion neighbours register, high enough
# that random noise does not.
_CHANNEL_AGREEMENT_FLOOR = 0.5

# How much of the query is image vs text when the customer sends both.
_HYBRID_IMAGE_WEIGHT = 0.7

# In-memory cache: embedding_key → embedding vector
_catalog_embeddings: dict[str, list[float]] = {}
_catalog_image_urls: dict[str, str] = {}
_catalog_embedding_product_ids: dict[str, str] = {}
_catalog_embedding_mtime: float = 0.0
_catalog_embedding_signature: tuple[tuple[str, str], ...] = ()


def embedding_metadata() -> dict[str, str]:
    """Version stamp every embedding so a model/preprocess change forces a rebuild."""
    try:
        from app.inventory.image_preprocessing import PREPROCESS_VERSION
    except Exception:  # pragma: no cover - defensive only
        PREPROCESS_VERSION = "unknown"
    return {
        "model_name": _MODEL_NAME,
        "model_version": _MODEL_VERSION,
        "preprocess_version": PREPROCESS_VERSION,
        "embedding_version": EMBEDDING_VERSION,
        "embedding_created_at": datetime.now(UTC).isoformat(),
    }


def _embedding_type_for_key(embedding_key: str) -> str:
    if embedding_key.endswith(_PATTERN_SUFFIX):
        return "pattern_visual"
    if embedding_key.endswith("::text"):
        return "text_visual_tags"
    return "full_visual"


def _load_clip():
    global _clip_model, _clip_processor
    if _clip_model is not None:
        return _clip_model, _clip_processor
    try:
        if _LOCAL_FILES_ONLY:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from transformers import CLIPModel, CLIPProcessor  # type: ignore[import]
        logger.info("Loading CLIP model: %s local_files_only=%s", _MODEL_NAME, _LOCAL_FILES_ONLY)
        _clip_processor = CLIPProcessor.from_pretrained(_MODEL_NAME, local_files_only=_LOCAL_FILES_ONLY)
        _clip_model = CLIPModel.from_pretrained(_MODEL_NAME, local_files_only=_LOCAL_FILES_ONLY)
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
        payload = image_b64.split(",", 1)[1] if image_b64.startswith("data:image/") and "," in image_b64 else image_b64
        raw = base64.b64decode(payload + "==")
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


def _encode_image_bytes_grayscale(raw: bytes) -> list[float] | None:
    """Encode the grayscale version of an image.

    CLIP overweights color and category; a grayscale embedding isolates the
    design/pattern so the same design in a different color still matches.
    """
    model, processor = _load_clip()
    if model is None:
        return None
    try:
        import torch
        from PIL import Image, ImageOps  # type: ignore[import]

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img = ImageOps.grayscale(img).convert("RGB")
        inputs = processor(images=img, return_tensors="pt")
        with torch.no_grad():
            feat = model.get_image_features(**inputs)
        return _feature_to_vector(feat)
    except Exception as exc:
        logger.warning("CLIP grayscale image encode failed: %s", exc)
        return None


def _encode_image_b64_grayscale(image_b64: str) -> list[float] | None:
    try:
        payload = (
            image_b64.split(",", 1)[1]
            if image_b64.startswith("data:image/") and "," in image_b64
            else image_b64
        )
        return _encode_image_bytes_grayscale(base64.b64decode(payload + "=="))
    except Exception as exc:
        logger.warning("CLIP grayscale b64 decode failed: %s", exc)
        return None


def _encode_image_source(source: str, *, grayscale: bool = False) -> list[float] | None:
    encoder = _encode_image_bytes_grayscale if grayscale else _encode_image_bytes
    try:
        if source.startswith(("http://", "https://")):
            resp = httpx.get(source, timeout=8.0, follow_redirects=True, headers=_HTTP_HEADERS)
            resp.raise_for_status()
            return encoder(resp.content)
        path = Path(source)
        if path.exists():
            return encoder(path.read_bytes())
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


def _normalize_vec(values: list[float]) -> list[float]:
    norm = sum(v * v for v in values) ** 0.5
    if norm == 0:
        return values
    return [v / norm for v in values]


def _blend_vectors(a: list[float], b: list[float], weight: float) -> list[float]:
    """Weighted blend (a * weight + b * (1 - weight)) then renormalize."""
    if a is None or b is None or len(a) != len(b):
        return a if a is not None else b
    blended = [weight * x + (1.0 - weight) * y for x, y in zip(a, b)]
    return _normalize_vec(blended)


def _cache_payload(signature: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return {
        "embedding_version": EMBEDDING_VERSION,
        "model_name": _MODEL_NAME,
        "signature": [list(item) for item in signature],
        "embeddings": _catalog_embeddings,
        "image_urls": _catalog_image_urls,
        "product_ids": _catalog_embedding_product_ids,
    }


def _try_load_persisted_cache(
    signature: tuple[tuple[str, str], ...],
    *,
    cache_path: Path = _CACHE_PATH,
) -> bool:
    """Populate in-memory cache from disk when the signature still matches.

    Returns True on a cache hit (caller can skip CLIP loading entirely).
    """
    global _catalog_embeddings, _catalog_image_urls, _catalog_embedding_product_ids
    global _catalog_embedding_signature
    if not cache_path.exists():
        return False
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:  # pragma: no cover - corrupt cache must not crash
        logger.debug("CLIP cache read failed: %s", exc)
        return False
    if data.get("embedding_version") != EMBEDDING_VERSION:
        return False
    if data.get("model_name") != _MODEL_NAME:
        return False
    cached_signature = tuple(tuple(item) for item in data.get("signature") or [])
    if cached_signature != signature:
        return False
    embeddings = data.get("embeddings") or {}
    if not embeddings:
        return False
    _catalog_embeddings = {key: list(vec) for key, vec in embeddings.items()}
    _catalog_image_urls = dict(data.get("image_urls") or {})
    _catalog_embedding_product_ids = dict(data.get("product_ids") or {})
    _catalog_embedding_signature = signature
    logger.info("CLIP cache hit: loaded %d embeddings from %s", len(_catalog_embeddings), cache_path)
    return True


def _try_load_source_vector_cache(
    catalog: dict[str, Any],
    signature: tuple[tuple[str, str], ...],
    *,
    cache_path: Path = _CACHE_PATH,
) -> bool:
    """Load the Le Reve/baseline vector cache format without re-encoding images.

    Research scripts save cache entries by image-source fingerprint:

        {path}|{mtime_ns}|{size}|{embedding_version} -> vector

    The online matcher needs product/image embedding keys. This adapter bridges
    those formats and avoids doing a catalog-wide CLIP encode inside chat.
    """
    global _catalog_embeddings, _catalog_image_urls, _catalog_embedding_product_ids
    global _catalog_embedding_signature

    if not cache_path.exists():
        return False
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:  # pragma: no cover - corrupt cache must not crash
        logger.debug("CLIP source-vector cache read failed: %s", exc)
        return False
    if data.get("embedding_version") != EMBEDDING_VERSION:
        return False
    vectors = data.get("vectors")
    if not isinstance(vectors, dict) or not vectors:
        return False

    embeddings: dict[str, list[float]] = {}
    image_urls: dict[str, str] = {}
    product_ids: dict[str, str] = {}
    missing = 0
    for item in catalog.values():
        pid = str(getattr(item, "product_id", "") or "")
        if not pid:
            continue
        loaded_for_product = False
        for image_id, source in _image_sources(item):
            cache_key = _source_cache_key(source)
            if not cache_key:
                continue
            vec = vectors.get(cache_key)
            if not vec:
                continue
            embedding_key = f"{pid}::{image_id}"
            embeddings[embedding_key] = list(vec)
            image_urls[embedding_key] = source
            product_ids[embedding_key] = pid
            loaded_for_product = True
        if not loaded_for_product:
            missing += 1

    if not embeddings:
        return False
    _catalog_embeddings = embeddings
    _catalog_image_urls = image_urls
    _catalog_embedding_product_ids = product_ids
    _catalog_embedding_signature = signature
    logger.info(
        "CLIP source-vector cache hit: loaded %d embeddings from %s; missing_products=%d",
        len(_catalog_embeddings),
        cache_path,
        missing,
    )
    return True


def _source_cache_key(source: str) -> str | None:
    if source.startswith(("http://", "https://")):
        return None
    try:
        path = Path(source)
        stat = path.stat()
    except Exception:
        return None
    return f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{EMBEDDING_VERSION}"


def _persist_cache(
    signature: tuple[tuple[str, str], ...],
    *,
    cache_path: Path = _CACHE_PATH,
) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(_cache_payload(signature), handle)
        tmp.replace(cache_path)
        logger.info("CLIP cache persisted (%d embeddings) -> %s", len(_catalog_embeddings), cache_path)
    except Exception as exc:  # pragma: no cover - persisting is best-effort
        logger.debug("CLIP cache persist failed: %s", exc)


def precompute_catalog_embeddings(
    catalog: dict[str, Any],
    force: bool = False,
) -> int:
    """
    Encode each catalog product's name+description as a CLIP text embedding.
    Stores results in the in-memory cache.  Returns number of items encoded.
    Only runs if CLIP is available.
    """
    global _catalog_embeddings, _catalog_image_urls, _catalog_embedding_product_ids, _catalog_embedding_signature
    signature = _catalog_signature(catalog)
    if not force and _catalog_embeddings and _catalog_embedding_signature == signature:
        return len(_catalog_embeddings)
    if not force and _try_load_persisted_cache(signature):
        return len(_catalog_embeddings)
    if not force and _try_load_source_vector_cache(catalog, signature):
        return len(_catalog_embeddings)
    if not force and not _ALLOW_SYNC_PRECOMPUTE and len(catalog) > _MAX_SYNC_PRECOMPUTE_ITEMS:
        logger.warning(
            "Skipping synchronous CLIP catalog precompute for %d items. "
            "Build a cache first or set IMAGE_SEARCH_ALLOW_SYNC_PRECOMPUTE=1.",
            len(catalog),
        )
        _catalog_embeddings = {}
        _catalog_image_urls = {}
        _catalog_embedding_product_ids = {}
        _catalog_embedding_signature = signature
        return 0
    model, _ = _load_clip()
    if model is None:
        return 0

    items = list(catalog.values())
    texts = []
    ids = []
    image_vectors: dict[str, list[float]] = {}
    image_urls: dict[str, str] = {}
    embedding_product_ids: dict[str, str] = {}
    for item in items:
        if hasattr(item, "name"):
            pid = item.product_id
            encoded_any_image = False
            for image_id, image_url in _image_sources(item):
                vec = _encode_image_source(image_url)
                if vec is not None:
                    key = f"{pid}::{image_id}"
                    image_vectors[key] = vec
                    image_urls[key] = image_url
                    embedding_product_ids[key] = pid
                    encoded_any_image = True
                    # Pattern channel: grayscale embedding for color-invariant
                    # same-design matching. Strictly additive — failure here
                    # never blocks the full-visual channel.
                    pattern_vec = _encode_image_source(image_url, grayscale=True)
                    if pattern_vec is not None:
                        pattern_key = f"{key}{_PATTERN_SUFFIX}"
                        image_vectors[pattern_key] = pattern_vec
                        image_urls[pattern_key] = image_url
                        embedding_product_ids[pattern_key] = pid
            if encoded_any_image:
                continue
            desc = (item.name or "") + " " + (getattr(item, "short_description", "") or "")
            attrs = item.attributes or {}
            for k in ("color", "fabric", "work_type", "occasion"):
                if attrs.get(k):
                    desc += " " + attrs[k]
            product_id = item.product_id
        else:
            desc = str(item.get("name", "")) + " " + str(item.get("short_description", ""))
            product_id = item.get("product_id", "")
        texts.append(desc.strip()[:200])
        text_key = f"{product_id}::text"
        ids.append(text_key)
        embedding_product_ids[text_key] = product_id

    new_cache: dict[str, list[float]] = dict(image_vectors)
    # Encode the text fallback in batches of 32 — only when there are products
    # without usable images, so a fully image-backed catalog never needs torch.
    if texts:
        import torch

        processor = _clip_processor
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
                for key, vec in zip(batch_ids, feats.tolist()):
                    if key:
                        new_cache[key] = vec
            except Exception as exc:
                logger.warning("CLIP batch encode failed at index %d: %s", i, exc)

    _catalog_embeddings = new_cache
    _catalog_image_urls = image_urls
    _catalog_embedding_product_ids = embedding_product_ids
    _catalog_embedding_signature = signature
    logger.info("CLIP: precomputed %d catalog embeddings", len(_catalog_embeddings))
    _persist_cache(signature)
    return len(_catalog_embeddings)


def _catalog_signature(catalog: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    signature: list[tuple[str, str]] = []
    for product_id, item in sorted(catalog.items()):
        image_parts = [f"{image_id}:{source}" for image_id, source in _image_sources(item)]
        image_source = "|".join(image_parts) or primary_image_url(item) or ""
        updated_at = getattr(item, "updated_at", "") if hasattr(item, "updated_at") else str(item.get("updated_at", ""))
        name = getattr(item, "name", "") if hasattr(item, "name") else str(item.get("name", ""))
        signature.append((str(product_id), f"{image_source}|{updated_at}|{name}"))
    return tuple(signature)


def _image_sources(item: Any) -> list[tuple[str, str]]:
    images = getattr(item, "images", None) or []
    sources: list[tuple[str, str]] = []
    for index, image in enumerate(images, start=1):
        image_id = getattr(image, "image_id", None) or f"image-{index}"
        source = getattr(image, "local_path", None) or getattr(image, "url", None)
        if source:
            sources.append((str(image_id), str(source)))
    return sources


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
        query_pattern_vec: list[float] | None = None
        if image_b64:
            query_vec = _encode_image_b64(image_b64)
            # Color-invariant design channel for same-design/different-color hits.
            query_pattern_vec = _encode_image_b64_grayscale(image_b64)
            # Hybrid query: when text is also provided, blend it into the image
            # vector so phrasing like "ei black polo ache?" disambiguates the
            # image's design intent without overriding the visual signal.
            if query_text and query_vec is not None:
                text_vec = _encode_text(query_text)
                if text_vec is not None:
                    query_vec = _blend_vectors(query_vec, text_vec, _HYBRID_IMAGE_WEIGHT)
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

        # Track which channels matched ("above floor") per product so the
        # downstream decision policy can demand multi-channel agreement before
        # claiming an exact match.
        channels_above_floor: dict[str, set[str]] = {}
        best_by_product: dict[str, ImageMatchResult] = {}
        for embedding_key, item_vec in _catalog_embeddings.items():
            pid = _catalog_embedding_product_ids.get(embedding_key) or embedding_key.split("::", 1)[0]
            if catalog and pid not in catalog:
                continue
            embedding_type = _embedding_type_for_key(embedding_key)
            # The pattern channel is only meaningful against a grayscale query.
            channel_query = (
                query_pattern_vec if embedding_type == "pattern_visual" else query_vec
            )
            if channel_query is None:
                continue
            score = _cosine(channel_query, item_vec)
            if score >= _CHANNEL_AGREEMENT_FLOOR:
                channels_above_floor.setdefault(pid, set()).add(embedding_type)
            if catalog:
                item = catalog[pid]
                if budget_max and item.price and item.price > budget_max:
                    continue
                if item.stock == 0:
                    score *= 0.3
                result = ImageMatchResult(
                    product_id=pid,
                    name=item.name,
                    score=round(score, 4),
                    match_type="visual_similar",
                    reasons=(f"CLIP {embedding_type} match",),
                    price=item.price,
                    currency=item.currency,
                    stock=item.stock,
                    image_url=_catalog_image_urls.get(embedding_key) or primary_image_url(item),
                    score_breakdown={
                        "embedding_key": embedding_key,
                        "embedding_type": embedding_type,
                        "embedding_version": EMBEDDING_VERSION,
                        "model_name": _MODEL_NAME,
                    },
                )
            else:
                result = ImageMatchResult(
                    product_id=pid,
                    name=pid,
                    score=round(score, 4),
                    match_type="visual_similar",
                    reasons=(f"CLIP {embedding_type} match",),
                    score_breakdown={
                        "embedding_key": embedding_key,
                        "embedding_type": embedding_type,
                    },
                )
            existing = best_by_product.get(pid)
            if existing is None or result.score > existing.score:
                best_by_product[pid] = result

        # Annotate each winning hit with the full set of channels that matched
        # for its product, so the exact-match gate can require agreement.
        for pid, hit in list(best_by_product.items()):
            channels = sorted(channels_above_floor.get(pid, set()))
            if not channels and hit.score_breakdown:
                channels = [str(hit.score_breakdown.get("embedding_type") or "full_visual")]
            updated = dict(hit.score_breakdown or {})
            updated["matched_channels"] = channels
            best_by_product[pid] = replace(hit, score_breakdown=updated)

        results = list(best_by_product.values())
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
