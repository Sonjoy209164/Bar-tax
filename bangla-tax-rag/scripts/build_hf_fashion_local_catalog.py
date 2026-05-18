from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryItemRecord
from scripts.build_local_demo_image_catalog import (
    BACKUP_DIR,
    CATALOG_PATH,
    CATALOG_VERSION,
    DEFAULT_CURRENCY,
    FRONTEND_IMAGE_ROOT,
    SOURCE_MANIFEST_PATH,
    ProductSpec,
    build_item,
    build_specs,
    image_dimensions,
    visual_tags,
)


HF_REPO_ID = "ashraq/fashion-product-images-small"
HF_PARQUET = "data/train-00000-of-00002-6cff4c59f91661c3.parquet"
TARGET_TOTAL = 100
TARGET_CATEGORY_COUNTS = {
    "Saree": 12,
    "Three Piece": 10,
    "Bag": 10,
    "Jewelry": 8,
    "Cosmetics": 8,
    "Beauty": 7,
    "Watch": 8,
    "Shoes": 12,
    "Shirt": 12,
    "Pant": 7,
    "Perfume": 6,
}


def main() -> int:
    FRONTEND_IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_existing(timestamp)

    items: list[InventoryItemRecord] = []
    manifest: list[dict[str, Any]] = []

    existing_specs = {spec.product_id: spec for spec in build_specs()}
    for product_id in sorted(existing_local_product_ids()):
        if len(items) >= TARGET_TOTAL:
            break
        spec = existing_specs.get(product_id)
        if spec is None:
            continue
        target = FRONTEND_IMAGE_ROOT / product_id / "primary.jpg"
        payload = image_payload_from_existing(spec, target)
        item = InventoryItemRecord.model_validate(build_item(spec, payload))
        items.append(item)
        manifest.append(payload["manifest"])

    counts = category_counts(items)
    print(f"Seeded {len(items)} local/demo products: {counts}")

    parquet_path = hf_hub_download(repo_id=HF_REPO_ID, repo_type="dataset", filename=HF_PARQUET)
    print(f"Using HF parquet: {parquet_path}")

    for row in iter_hf_rows(Path(parquet_path)):
        if len(items) >= TARGET_TOTAL:
            break
        mapped = map_hf_row(row)
        if mapped is None:
            continue
        category = mapped["category"]
        if counts.get(category, 0) >= TARGET_CATEGORY_COUNTS.get(category, 0):
            continue
        product_id = mapped["product_id"]
        if any(item.product_id == product_id for item in items):
            continue
        target = FRONTEND_IMAGE_ROOT / product_id / "primary.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            normalize_hf_image(row["image"]["bytes"], target)
        except Exception:
            continue

        spec = hf_spec(row, mapped)
        payload = image_payload_from_hf(spec, target, row)
        item = InventoryItemRecord.model_validate(build_item(spec, payload))
        items.append(item)
        manifest.append(payload["manifest"])
        counts[category] = counts.get(category, 0) + 1
        print(f"[{len(items):03d}/{TARGET_TOTAL}] {product_id} ({category})")

    if len(items) != TARGET_TOTAL:
        raise SystemExit(f"Built {len(items)} items, expected {TARGET_TOTAL}. Counts: {category_counts(items)}")

    write_catalog(items)
    write_manifest(manifest)

    print(f"Wrote {len(items)} products to {CATALOG_PATH}")
    print(f"Wrote {len(manifest)} source records to {SOURCE_MANIFEST_PATH}")
    print(f"Final category counts: {category_counts(items)}")
    print(f"Images are local under {FRONTEND_IMAGE_ROOT.relative_to(ROOT)}")
    return 0


def backup_existing(timestamp: str) -> None:
    if CATALOG_PATH.exists():
        shutil.copy2(CATALOG_PATH, BACKUP_DIR / f"catalog_before_hf_demo_{timestamp}.jsonl")
    if SOURCE_MANIFEST_PATH.exists():
        shutil.copy2(SOURCE_MANIFEST_PATH, BACKUP_DIR / f"catalog_image_sources_before_hf_demo_{timestamp}.json")


def existing_local_product_ids() -> set[str]:
    ids: set[str] = set()
    if not FRONTEND_IMAGE_ROOT.exists():
        return ids
    for image_path in FRONTEND_IMAGE_ROOT.glob("*/primary.jpg"):
        ids.add(image_path.parent.name)
    return ids


def image_payload_from_existing(spec: ProductSpec, target: Path) -> dict[str, Any]:
    local_path = target.relative_to(ROOT).as_posix()
    return {
        "image": {
            "image_id": f"{spec.product_id}-primary-1",
            "local_path": local_path,
            "source_name": "Local demo image cache" if spec.is_reference else "Local product photo",
            "role": "primary",
            "kind": spec.image_kind,
            "is_reference": spec.is_reference,
            "visual_tags": visual_tags(spec),
            **image_dimensions(target),
        },
        "manifest": {
            "product_id": spec.product_id,
            "name": spec.name,
            "image_id": f"{spec.product_id}-primary-1",
            "source_name": "Local demo image cache" if spec.is_reference else "Local product photo",
            "local_path": local_path,
            "kind": spec.image_kind,
            "is_reference": spec.is_reference,
        },
        "display_source": local_path,
    }


def image_payload_from_hf(spec: ProductSpec, target: Path, row: dict[str, Any]) -> dict[str, Any]:
    local_path = target.relative_to(ROOT).as_posix()
    image_id = f"{spec.product_id}-primary-1"
    source_url = f"https://huggingface.co/datasets/{HF_REPO_ID}"
    return {
        "image": {
            "image_id": image_id,
            "local_path": local_path,
            "source_url": source_url,
            "source_name": "Hugging Face / Kaggle Fashion Product Images Small",
            "license": "Dataset/demo use; verify rights before production",
            "role": "primary",
            "kind": "reference_photo",
            "is_reference": True,
            "visual_tags": visual_tags(spec),
            **image_dimensions(target),
        },
        "manifest": {
            "product_id": spec.product_id,
            "name": spec.name,
            "image_id": image_id,
            "source_url": source_url,
            "hf_dataset_id": row.get("id"),
            "hf_master_category": row.get("masterCategory"),
            "hf_sub_category": row.get("subCategory"),
            "hf_article_type": row.get("articleType"),
            "local_path": local_path,
            "kind": "reference_photo",
            "is_reference": True,
        },
        "display_source": source_url,
    }


def iter_hf_rows(parquet_path: Path):
    columns = [
        "id",
        "gender",
        "masterCategory",
        "subCategory",
        "articleType",
        "baseColour",
        "season",
        "usage",
        "productDisplayName",
        "image",
    ]
    parquet = pq.ParquetFile(parquet_path)
    for batch in parquet.iter_batches(batch_size=512, columns=columns):
        for row in batch.to_pylist():
            image = row.get("image") or {}
            if not image.get("bytes"):
                continue
            yield row


def normalize_hf_image(raw: bytes, target: Path) -> None:
    from io import BytesIO

    with Image.open(BytesIO(raw)) as image:
        image = image.convert("RGB")
        if image.width < 260 or image.height < 260:
            scale = max(260 / image.width, 260 / image.height)
            image = image.resize(
                (max(260, int(image.width * scale)), max(260, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        image.thumbnail((900, 900), Image.Resampling.LANCZOS)
        image.save(target, format="JPEG", quality=90, optimize=True)


def map_hf_row(row: dict[str, Any]) -> dict[str, str] | None:
    master = clean(row.get("masterCategory"))
    sub = clean(row.get("subCategory"))
    article = clean(row.get("articleType"))
    gender = clean(row.get("gender"))
    name = clean(row.get("productDisplayName")) or f"Fashion Product {row.get('id')}"
    color = clean(row.get("baseColour")) or "multi"

    category: str | None = None
    if sub == "Bags":
        category = "Bag"
    elif sub == "Watches":
        category = "Watch"
    elif sub in {"Jewellery", "Jewelry"}:
        category = "Jewelry"
    elif master == "Footwear":
        category = "Shoes"
    elif sub == "Fragrance" or article in {"Perfume and Body Mist", "Perfume"}:
        category = "Perfume"
    elif master == "Personal Care":
        if article in {"Lipstick", "Lip Gloss", "Kajal and Eyeliner", "Mascara", "Compact", "Foundation and Primer", "Nail Polish", "Blush"}:
            category = "Cosmetics"
        else:
            category = "Beauty"
    elif sub == "Bottomwear" and article in {"Jeans", "Trousers", "Track Pants", "Shorts"}:
        category = "Pant"
    elif sub == "Topwear" and article in {"Shirts", "Tshirts", "Tops", "Kurtas", "Kurtis", "Tunics"}:
        if gender == "Women" and article in {"Tops", "Kurtas", "Kurtis", "Tunics"}:
            category = "Three Piece"
        else:
            category = "Shirt"
    elif master == "Apparel" and article in {"Dresses", "Kurta Sets", "Salwar and Dupatta", "Sarees"}:
        category = "Three Piece"

    if category is None:
        return None

    product_id = f"hf-{row.get('id')}-{slug(name)[:44]}"
    return {
        "product_id": product_id,
        "category": category,
        "name": name,
        "gender": gender or "Unisex",
        "color": color,
        "article": article or category,
        "sub": sub or category,
        "master": master or category,
    }


def hf_spec(row: dict[str, Any], mapped: dict[str, str]) -> ProductSpec:
    category = mapped["category"]
    gender_raw = mapped["gender"]
    gender = gender_raw.casefold()
    if gender in {"women", "girls"}:
        gender = "women"
        section = "ladies"
    elif gender in {"men", "boys"}:
        gender = "men"
        section = "men"
    else:
        gender = "unisex"
        section = "unisex"

    color = mapped["color"].casefold()
    color_family = normalize_color_family(color)
    article = mapped["article"]
    usage = clean(row.get("usage")) or "daily wear"
    price = price_for(category, int(row.get("id") or 0))
    stock = 0 if int(row.get("id") or 1) % 29 == 0 else (int(row.get("id") or 1) % 8) + 1
    size = size_for(category, gender, int(row.get("id") or 0))
    design_id = slug(remove_color_words(mapped["name"], color))
    variant_group = title_from_slug(design_id)
    attrs: dict[str, str] = {
        "hf_master_category": mapped["master"],
        "hf_sub_category": mapped["sub"],
        "hf_article_type": article,
        "source_dataset": HF_REPO_ID,
    }
    if category == "Shoes":
        attrs["shoe_type"] = article
    if category == "Bag":
        attrs["bag_type"] = article
    if category == "Jewelry":
        attrs["jewelry_type"] = article
    if category in {"Cosmetics", "Beauty"}:
        attrs["skin_type"] = "all skin"
    if category == "Perfume":
        attrs["fragrance_family"] = "demo fragrance"

    return ProductSpec(
        product_id=mapped["product_id"],
        sku=mapped["product_id"].upper().replace("-", "_")[:48],
        name=mapped["name"],
        category=category,
        brand=brand_from_name(mapped["name"]),
        price=price,
        stock=stock,
        tags=tuple(
            tag
            for tag in (
                section,
                gender,
                category,
                color,
                color_family,
                article,
                usage,
                mapped["sub"],
                mapped["master"],
            )
            if tag
        ),
        attributes={
            "section": section,
            "gender": gender,
            "category_key": slug(category).replace("-", "_"),
            "color": color,
            "color_family": color_family,
            "size": size,
            "occasion": usage.casefold(),
            "style": usage.casefold(),
            "design_id": design_id,
            "variant_group_id": slug(variant_group),
            "variant_group_name": variant_group,
            "product_type": article,
            **attrs,
        },
        query=mapped["name"],
        image_kind="reference_photo",
        is_reference=True,
    )


def price_for(category: str, row_id: int) -> float:
    base = {
        "Saree": 4500,
        "Three Piece": 2800,
        "Bag": 1800,
        "Jewelry": 850,
        "Cosmetics": 650,
        "Beauty": 550,
        "Watch": 2600,
        "Shoes": 2200,
        "Shirt": 1700,
        "Pant": 2300,
        "Perfume": 2400,
    }.get(category, 1200)
    return float(base + (row_id % 9) * 150)


def size_for(category: str, gender: str, row_id: int) -> str:
    if category == "Shoes":
        return str((37 if gender == "women" else 40) + (row_id % 5))
    if category in {"Shirt", "Three Piece"}:
        return ("S", "M", "L", "XL")[row_id % 4]
    if category == "Pant":
        return str(30 + (row_id % 5) * 2)
    if category == "Perfume":
        return "50ml" if row_id % 2 else "100ml"
    return "one size"


def normalize_color_family(color: str) -> str:
    lowered = color.casefold()
    mappings = {
        "navy": "blue",
        "blue": "blue",
        "red": "red",
        "maroon": "red",
        "pink": "pink",
        "green": "green",
        "olive": "green",
        "yellow": "yellow",
        "mustard": "yellow",
        "gold": "gold",
        "silver": "silver",
        "white": "white",
        "cream": "white",
        "off white": "white",
        "black": "black",
        "grey": "grey",
        "gray": "grey",
        "brown": "brown",
        "beige": "brown",
        "tan": "brown",
        "purple": "purple",
        "violet": "purple",
        "orange": "orange",
    }
    for key, value in mappings.items():
        if key in lowered:
            return value
    return lowered.split()[0] if lowered else "multi"


def remove_color_words(name: str, color: str) -> str:
    result = name
    for word in color.split():
        result = re.sub(re.escape(word), "", result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip() or name


def brand_from_name(name: str) -> str:
    parts = name.split()
    if not parts:
        return "Demo Fashion"
    if len(parts) >= 2 and parts[0].casefold() in {"united", "peter", "levis", "urban"}:
        return " ".join(parts[:2])
    return parts[0]


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "item"


def title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in slug(value).split("-"))


def category_counts(items: list[InventoryItemRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        category = item.category or "Other"
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def write_catalog(items: list[InventoryItemRecord]) -> None:
    temp_path = CATALOG_PATH.with_suffix(".jsonl.tmp")
    temp_path.write_text(
        "\n".join(item.model_dump_json(exclude_none=True) for item in items) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(CATALOG_PATH)


def write_manifest(source_manifest: list[dict[str, Any]]) -> None:
    temp_path = SOURCE_MANIFEST_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(SOURCE_MANIFEST_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
