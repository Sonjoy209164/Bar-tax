from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from app.core.schemas import InventoryImageAsset, InventoryItemRecord
from app.inventory.image_preprocessing import preprocess_image_source


IMAGE_INDEX_VERSION = "image-index-v1"
IMAGE_INDEX_PATH = Path("data/inventory/image_index.jsonl")


@dataclass(frozen=True)
class ImageIndexRecord:
    product_id: str
    image_id: str
    image_source: str
    image_role: str
    image_kind: str
    is_reference: bool
    category: str | None
    color: str | None
    color_family: str | None
    design_id: str | None
    variant_group_id: str | None
    stock: int
    price: float | None
    preprocess: dict[str, Any]
    embedding_status: str
    embedding_model: str | None = None
    vector_dimensions: int | None = None
    vector_checksum: str | None = None
    error: str | None = None
    index_version: str = IMAGE_INDEX_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class ImageIndexStatus:
    status: str
    index_path: str
    catalog_count: int
    image_asset_count: int
    indexed_count: int
    ready: bool
    missing_product_ids: list[str]
    stale_product_ids: list[str]
    model_available: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_image_index(
    catalog: dict[str, InventoryItemRecord],
    *,
    index_path: str | Path = IMAGE_INDEX_PATH,
    force: bool = False,
    include_embeddings: bool = True,
) -> list[ImageIndexRecord]:
    """Preprocess catalog images and persist image-index records.

    This is intentionally a local persistent index manifest. It makes the
    visual index observable and reusable; a later step can push the same
    records into Elasticsearch as image-vector documents.
    """

    path = Path(index_path)
    existing = {_record_key(record.product_id, record.image_id): record for record in read_image_index(path)}
    records: list[ImageIndexRecord] = []

    encoder = None
    model_available: bool | None = None
    if include_embeddings:
        try:
            from app.inventory import clip_matcher

            encoder = clip_matcher._encode_image_source  # type: ignore[attr-defined]
            model_available = clip_matcher.CLIPImageMatcher.is_available()
        except Exception:
            encoder = None
            model_available = False

    for item in catalog.values():
        for image, image_source in _iter_image_sources(item):
            existing_record = existing.get(_record_key(item.product_id, image.image_id))
            signature = _source_signature(item, image, image_source)
            if not force and existing_record and existing_record.vector_checksum == signature:
                records.append(existing_record)
                continue

            error: str | None = None
            embedding_status = "not_requested"
            vector_dimensions: int | None = None
            try:
                preprocess = preprocess_image_source(
                    source=image_source,
                    image_id=f"{item.product_id}-{image.image_id}",
                ).to_dict()
            except Exception as exc:
                preprocess = {}
                error = f"preprocess_failed: {exc}"

            if encoder and not error:
                try:
                    vector = encoder(preprocess.get("crop_path") or image_source)
                    if vector:
                        vector_dimensions = len(vector)
                        embedding_status = "ready"
                    else:
                        embedding_status = "unavailable"
                except Exception as exc:
                    embedding_status = "failed"
                    error = f"embedding_failed: {exc}"
            elif include_embeddings:
                embedding_status = "model_unavailable" if model_available is False else "unavailable"

            attrs = item.attributes or {}
            records.append(
                ImageIndexRecord(
                    product_id=item.product_id,
                    image_id=image.image_id,
                    image_source=image_source,
                    image_role=image.role,
                    image_kind=image.kind,
                    is_reference=image.is_reference,
                    category=item.category or attrs.get("category_key"),
                    color=attrs.get("color"),
                    color_family=attrs.get("color_family"),
                    design_id=attrs.get("design_id"),
                    variant_group_id=attrs.get("variant_group_id") or attrs.get("variant_group_name") or attrs.get("design_id"),
                    stock=item.stock,
                    price=item.price,
                    preprocess=preprocess,
                    embedding_status=embedding_status,
                    embedding_model="openai/clip-vit-base-patch32" if include_embeddings else None,
                    vector_dimensions=vector_dimensions,
                    vector_checksum=signature,
                    error=error,
                )
            )

    write_image_index(records, path)
    return records


def image_index_status(
    catalog: dict[str, InventoryItemRecord],
    *,
    index_path: str | Path = IMAGE_INDEX_PATH,
) -> ImageIndexStatus:
    path = Path(index_path)
    records = read_image_index(path)
    indexed_by_asset = {_record_key(record.product_id, record.image_id): record for record in records}
    image_assets: dict[str, tuple[InventoryItemRecord, InventoryImageAsset, str]] = {}
    for item in catalog.values():
        for image, source in _iter_image_sources(item):
            image_assets[_record_key(item.product_id, image.image_id)] = (item, image, source)
    missing = sorted(set(image_assets) - set(indexed_by_asset))
    stale: list[str] = []
    for key, (item, image, source) in image_assets.items():
        record = indexed_by_asset.get(key)
        if not record:
            continue
        if record.vector_checksum != _source_signature(item, image, source):
            stale.append(key)
    ready = bool(image_assets) and not missing and not stale
    return ImageIndexStatus(
        status="success",
        index_path=path.as_posix(),
        catalog_count=len(catalog),
        image_asset_count=len(image_assets),
        indexed_count=len(records),
        ready=ready,
        missing_product_ids=missing,
        stale_product_ids=sorted(stale),
        model_available=_clip_available(),
    )


def read_image_index(path: str | Path = IMAGE_INDEX_PATH) -> list[ImageIndexRecord]:
    index_path = Path(path)
    if not index_path.exists():
        return []
    records: list[ImageIndexRecord] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(ImageIndexRecord(**json.loads(stripped)))
        except (json.JSONDecodeError, TypeError):
            continue
    return records


def write_image_index(records: Iterable[ImageIndexRecord], path: str | Path = IMAGE_INDEX_PATH) -> None:
    index_path = Path(path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = index_path.with_suffix(index_path.suffix + ".tmp")
    temp_path.write_text(
        "\n".join(json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":")) for record in records) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(index_path)


def _record_key(product_id: str, image_id: str) -> str:
    return f"{product_id}::{image_id}"


def _iter_image_sources(item: InventoryItemRecord) -> Iterable[tuple[InventoryImageAsset, str]]:
    for image in item.images:
        source = _image_source(image)
        if source:
            yield image, source


def _image_source(image: InventoryImageAsset) -> str | None:
    return image.local_path or image.url


def _source_signature(item: InventoryItemRecord, image: InventoryImageAsset, image_source: str) -> str:
    path = Path(image_source)
    parts = [
        item.product_id,
        image.image_id,
        image.role,
        image.kind,
        str(image.is_reference),
        item.updated_at or "",
        image_source,
    ]
    if path.exists():
        stat = path.stat()
        parts.extend([str(stat.st_size), str(int(stat.st_mtime))])
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _clip_available() -> bool | None:
    try:
        from app.inventory.clip_matcher import CLIPImageMatcher

        return CLIPImageMatcher.is_available()
    except Exception:
        return None
