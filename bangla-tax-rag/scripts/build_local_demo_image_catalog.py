from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryItemRecord

CATALOG_PATH = ROOT / "data" / "inventory" / "catalog.jsonl"
SOURCE_MANIFEST_PATH = ROOT / "data" / "inventory" / "catalog_image_sources.json"
BACKUP_DIR = ROOT / "data" / "inventory" / "backups"
FRONTEND_IMAGE_ROOT = ROOT / "frontend" / "assets" / "demo_catalog"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "bangla-tax-rag-demo-catalog-builder/1.0 (local image demo catalog)"
CATALOG_VERSION = "local-demo-image-catalog-2026-05-14"
DEFAULT_CURRENCY = "BDT"


@dataclass(frozen=True)
class ProductSpec:
    product_id: str
    sku: str
    name: str
    category: str
    brand: str
    price: float
    stock: int
    tags: tuple[str, ...]
    attributes: dict[str, str]
    query: str
    fallback_queries: tuple[str, ...] = ()
    source_local_path: str | None = None
    image_kind: str = "reference_photo"
    is_reference: bool = True
    status: str | None = None
    short_description: str | None = None
    full_description: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a 100-product local image demo catalog.")
    parser.add_argument("--count", type=int, default=100, help="Number of catalog items to build.")
    parser.add_argument("--delay", type=float, default=0.15, help="Polite delay between source downloads.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not write catalog/images.")
    args = parser.parse_args()

    specs = build_specs()
    if len(specs) < args.count:
        raise SystemExit(f"Only {len(specs)} specs available; requested {args.count}.")

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    used_source_urls: set[str] = set()
    source_manifest: list[dict[str, Any]] = []
    items: list[InventoryItemRecord] = []

    if args.dry_run:
        print(f"Would build {args.count} items from {len(specs)} specs.")
        return 0

    FRONTEND_IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_existing(timestamp)

    for spec in specs:
        if len(items) >= args.count:
            break
        try:
            image_payload = prepare_product_image(spec, used_source_urls=used_source_urls, delay=args.delay)
        except Exception as exc:
            print(f"SKIP {spec.product_id}: {exc}")
            continue

        item = build_item(spec, image_payload)
        InventoryItemRecord.model_validate(item)
        items.append(InventoryItemRecord.model_validate(item))
        source_manifest.append(image_payload["manifest"])
        print(f"[{len(items):03d}/{args.count}] {spec.product_id} <- {image_payload['display_source']}")

    if len(items) < args.count:
        raise SystemExit(f"Could only build {len(items)} valid items; requested {args.count}.")

    write_catalog(items)
    write_manifest(source_manifest)
    print(f"Wrote {len(items)} products to {CATALOG_PATH}")
    print(f"Wrote {len(source_manifest)} image source records to {SOURCE_MANIFEST_PATH}")
    print(f"Images saved under {FRONTEND_IMAGE_ROOT.relative_to(ROOT)}")
    return 0


def backup_existing(timestamp: str) -> None:
    if CATALOG_PATH.exists():
        shutil.copy2(CATALOG_PATH, BACKUP_DIR / f"catalog_before_demo_images_{timestamp}.jsonl")
    if SOURCE_MANIFEST_PATH.exists():
        shutil.copy2(SOURCE_MANIFEST_PATH, BACKUP_DIR / f"catalog_image_sources_before_demo_images_{timestamp}.json")


def prepare_product_image(
    spec: ProductSpec,
    *,
    used_source_urls: set[str],
    delay: float,
) -> dict[str, Any]:
    product_dir = FRONTEND_IMAGE_ROOT / spec.product_id
    product_dir.mkdir(parents=True, exist_ok=True)
    target = product_dir / "primary.jpg"
    local_path_for_catalog = target.relative_to(ROOT).as_posix()

    if spec.source_local_path:
        source_path = Path(spec.source_local_path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        normalize_image(source_path.read_bytes(), target)
        return {
            "image": {
                "image_id": f"{spec.product_id}-primary-1",
                "local_path": local_path_for_catalog,
                "source_name": "Local product photo",
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
                "source_name": "Local product photo",
                "source_path": str(source_path),
                "local_path": local_path_for_catalog,
                "kind": spec.image_kind,
                "is_reference": spec.is_reference,
            },
            "display_source": str(source_path),
        }

    image_info = find_commons_image((spec.query, *spec.fallback_queries), used_source_urls=used_source_urls)
    if image_info is None:
        raise RuntimeError(f"no image found for query '{spec.query}'")

    raw = download_bytes(image_info["download_url"])
    normalize_image(raw, target)
    if delay:
        time.sleep(delay)

    return {
        "image": {
            "image_id": f"{spec.product_id}-primary-1",
            "local_path": local_path_for_catalog,
            "source_url": image_info.get("source_url"),
            "source_name": "Wikimedia Commons",
            "license": image_info.get("license"),
            "license_url": image_info.get("license_url"),
            "attribution": image_info.get("attribution"),
            "role": "primary",
            "kind": spec.image_kind,
            "is_reference": spec.is_reference,
            "visual_tags": visual_tags(spec),
            **image_dimensions(target),
        },
        "manifest": {
            "product_id": spec.product_id,
            "name": spec.name,
            "query": spec.query,
            "image_id": f"{spec.product_id}-primary-1",
            "source_url": image_info.get("source_url"),
            "downloaded_from": image_info.get("download_url"),
            "source_name": "Wikimedia Commons",
            "license": image_info.get("license"),
            "license_url": image_info.get("license_url"),
            "attribution": image_info.get("attribution"),
            "local_path": local_path_for_catalog,
            "kind": spec.image_kind,
            "is_reference": spec.is_reference,
        },
        "display_source": image_info.get("source_url") or image_info.get("download_url"),
    }


def normalize_image(raw: bytes, target: Path) -> None:
    from io import BytesIO

    with Image.open(BytesIO(raw)) as image:
        image = image.convert("RGB")
        image.thumbnail((900, 900), Image.Resampling.LANCZOS)
        if image.width < 120 or image.height < 120:
            raise ValueError(f"image too small after normalization: {image.width}x{image.height}")
        image.save(target, format="JPEG", quality=88, optimize=True)


def image_dimensions(path: Path) -> dict[str, int]:
    with Image.open(path) as image:
        return {"width": image.width, "height": image.height}


def find_commons_image(queries: tuple[str, ...], *, used_source_urls: set[str]) -> dict[str, Any] | None:
    for query in queries:
        for candidate in search_commons(query):
            source_url = candidate.get("source_url") or candidate.get("download_url")
            if not source_url or source_url in used_source_urls:
                continue
            used_source_urls.add(source_url)
            return candidate
    return None


def search_commons(query: str) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrsearch": query,
        "gsrlimit": "14",
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "900",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    payload = json.loads(download_bytes(url).decode("utf-8"))
    pages = payload.get("query", {}).get("pages", [])
    candidates: list[dict[str, Any]] = []
    for page in pages:
        image_info = (page.get("imageinfo") or [{}])[0]
        mime = str(image_info.get("mime") or "")
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        ext = image_info.get("extmetadata") or {}
        download_url = image_info.get("thumburl") or image_info.get("url")
        if not download_url:
            continue
        candidates.append(
            {
                "download_url": download_url,
                "source_url": image_info.get("descriptionurl"),
                "license": metadata_value(ext, "LicenseShortName") or metadata_value(ext, "License"),
                "license_url": metadata_value(ext, "LicenseUrl"),
                "attribution": clean_html(metadata_value(ext, "Artist") or metadata_value(ext, "Credit")),
            }
        )
    return candidates


def download_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def metadata_value(extmetadata: dict[str, Any], key: str) -> str | None:
    value = extmetadata.get(key)
    if isinstance(value, dict):
        raw = value.get("value")
        return str(raw) if raw else None
    return None


def clean_html(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"<[^>]+>", "", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def build_item(spec: ProductSpec, image_payload: dict[str, Any]) -> dict[str, Any]:
    status = spec.status or ("Out of Stock" if spec.stock <= 0 else "Low Stock" if spec.stock <= 2 else "Active")
    short_description = spec.short_description or default_short_description(spec)
    full_description = spec.full_description or default_full_description(spec)
    metadata = {
        "source": "local-downloaded-demo-catalog",
        "catalog_version": CATALOG_VERSION,
        "image_schema_version": "inventory-image-v1",
        "image_source_policy": "local_downloaded_demo_images_not_real_shop_inventory",
        "catalog_purpose": "image_search_corner_case_testing",
    }
    return {
        "product_id": spec.product_id,
        "sku": spec.sku,
        "name": spec.name,
        "category": spec.category,
        "brand": spec.brand,
        "short_description": short_description,
        "full_description": full_description,
        "price": spec.price,
        "currency": DEFAULT_CURRENCY,
        "stock": spec.stock,
        "status": status,
        "tags": sorted(set(spec.tags)),
        "attributes": spec.attributes,
        "images": [image_payload["image"]],
        "metadata": metadata,
        "include_in_rag": True,
        "updated_at": "2026-05-14T00:00:00Z",
    }


def default_short_description(spec: ProductSpec) -> str:
    color = spec.attributes.get("color")
    category = spec.category.lower()
    purpose = spec.attributes.get("occasion") or spec.attributes.get("style") or "daily use"
    bits = [color, category, f"for {purpose}"]
    return " ".join(bit for bit in bits if bit).capitalize() + "."


def default_full_description(spec: ProductSpec) -> str:
    design = spec.attributes.get("design_id") or spec.attributes.get("variant_group_name") or spec.name
    color = spec.attributes.get("color") or "available color"
    size = spec.attributes.get("size") or spec.attributes.get("size_options") or ""
    return (
        f"{spec.name} from the {design} design family. "
        f"Color: {color}. "
        f"{'Size: ' + size + '. ' if size else ''}"
        "Included in the local demo image catalog for screenshot search, color/variant checks, and similar-item recommendations."
    )


def visual_tags(spec: ProductSpec) -> list[str]:
    values: list[str] = [*spec.tags, spec.category, spec.brand]
    values.extend(spec.attributes.values())
    tags: set[str] = set()
    for value in values:
        for part in re.split(r"[,/|]", str(value)):
            normalized = part.strip().casefold()
            if normalized:
                tags.add(normalized)
    return sorted(tags)[:28]


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


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "item"


def spec(
    *,
    pid: str,
    name: str,
    category: str,
    section: str,
    gender: str,
    color: str,
    color_family: str,
    price: float,
    stock: int,
    query: str,
    brand: str = "Demo Boutique",
    size: str | None = None,
    design_id: str | None = None,
    variant_group: str | None = None,
    style: str = "classic",
    occasion: str = "daily wear",
    fabric: str | None = None,
    work_type: str | None = None,
    product_type: str | None = None,
    local_path: str | None = None,
    image_kind: str = "reference_photo",
    is_reference: bool = True,
    fallback_queries: tuple[str, ...] = (),
    extra_attrs: dict[str, str] | None = None,
    tags: tuple[str, ...] = (),
) -> ProductSpec:
    attrs = {
        "section": section,
        "gender": gender,
        "category_key": slug(category).replace("-", "_"),
        "color": color,
        "color_family": color_family,
        "occasion": occasion,
        "style": style,
    }
    if size:
        attrs["size"] = size
    if fabric:
        attrs["fabric"] = fabric
    if work_type:
        attrs["work_type"] = work_type
    if design_id:
        attrs["design_id"] = design_id
    if variant_group:
        attrs["variant_group_id"] = slug(variant_group)
        attrs["variant_group_name"] = variant_group
    if product_type:
        attrs[f"{slug(category).replace('-', '_')}_type"] = product_type
        attrs["product_type"] = product_type
    if extra_attrs:
        attrs.update(extra_attrs)

    base_tags = (
        section,
        gender,
        category,
        color,
        color_family,
        style,
        occasion,
        *(fabric, work_type, product_type, size, design_id or "", variant_group or ""),
        *tags,
    )
    return ProductSpec(
        product_id=pid,
        sku=pid.upper().replace("-", "_")[:48],
        name=name,
        category=category,
        brand=brand,
        price=price,
        stock=stock,
        tags=tuple(tag for tag in base_tags if tag),
        attributes=attrs,
        query=query,
        fallback_queries=fallback_queries or fallback_for_category(category, color),
        source_local_path=local_path,
        image_kind=image_kind,
        is_reference=is_reference,
    )


def fallback_for_category(category: str, color: str) -> tuple[str, ...]:
    category_key = slug(category)
    generic = {
        "saree": ("sari", "traditional sari", "silk sari"),
        "three-piece": ("salwar kameez", "kurta set", "traditional dress"),
        "bag": ("handbag", "clutch bag", "fashion bag"),
        "jewelry": ("jewelry", "earrings", "necklace"),
        "cosmetics": ("cosmetics", "makeup product", "lipstick"),
        "beauty": ("skin care product", "cosmetic bottle", "sunscreen"),
        "watch": ("wristwatch", "watch"),
        "shoes": ("shoes", "sandal", "sneaker"),
        "panjabi": ("kurta", "traditional kurta"),
        "shirt": ("shirt", "polo shirt", "mens shirt"),
        "pant": ("trousers", "pants"),
        "perfume": ("perfume bottle", "fragrance bottle"),
    }.get(category_key, ("fashion product",))
    return tuple(f"{color} {entry}".strip() for entry in generic) + generic


def build_specs() -> list[ProductSpec]:
    specs: list[ProductSpec] = []

    sarees = [
        ("saree-jmd-lotus-red", "Lotus Buti Dhakai Jamdani Saree - Red", "red", "red", "jamdani", "buti", 6800, 3, "red jamdani sari"),
        ("saree-jmd-lotus-blue", "Lotus Buti Dhakai Jamdani Saree - Royal Blue", "royal blue", "blue", "jamdani", "buti", 6800, 2, "blue jamdani sari"),
        ("saree-jmd-lotus-green", "Lotus Buti Dhakai Jamdani Saree - Bottle Green", "bottle green", "green", "jamdani", "buti", 6800, 0, "green jamdani sari"),
        ("saree-ktn-meena-maroon", "Meena Border Bridal Katan Saree - Maroon", "maroon", "red", "katan", "zari border", 12500, 1, "maroon silk sari"),
        ("saree-ktn-meena-navy", "Meena Border Bridal Katan Saree - Navy Blue", "navy blue", "blue", "katan", "zari border", 12500, 2, "blue silk sari"),
        ("saree-ktn-meena-gold", "Meena Border Bridal Katan Saree - Antique Gold", "antique gold", "gold", "katan", "zari border", 13200, 1, "gold silk sari"),
        ("saree-msn-pastel-peach", "Pastel Soft Muslin Saree - Peach", "peach", "pink", "muslin", "plain border", 3600, 5, "peach sari"),
        ("saree-msn-pastel-mint", "Pastel Soft Muslin Saree - Mint Green", "mint green", "green", "muslin", "plain border", 3600, 4, "green sari"),
        ("saree-msn-pastel-lavender", "Pastel Soft Muslin Saree - Lavender", "lavender", "purple", "muslin", "plain border", 3600, 2, "purple sari"),
        ("saree-cot-block-indigo", "Cotton Block Print Saree - Indigo", "indigo", "blue", "cotton", "block print", 2850, 6, "blue printed sari"),
        ("saree-cot-block-mustard", "Cotton Block Print Saree - Mustard", "mustard", "yellow", "cotton", "block print", 2850, 5, "yellow printed sari"),
        ("saree-cot-block-black", "Cotton Block Print Saree - Black", "black", "black", "cotton", "block print", 2850, 2, "black printed sari"),
        ("saree-silk-floral-pink", "Floral Silk Saree - Rose Pink", "rose pink", "pink", "silk", "floral print", 5400, 3, "pink floral sari"),
        ("saree-silk-floral-cream", "Floral Silk Saree - Cream", "cream", "white", "silk", "floral print", 5400, 4, "cream floral sari"),
        ("saree-party-sequin-black", "Sequin Party Saree - Black", "black", "black", "georgette", "sequin", 7200, 2, "black sequin sari"),
        ("saree-party-sequin-silver", "Sequin Party Saree - Silver", "silver", "silver", "georgette", "sequin", 7200, 1, "silver sequin sari"),
    ]
    for pid, name, color, family, fabric, work, price, stock, query in sarees:
        design = "lotus-buti-jamdani" if "jmd-lotus" in pid else "meena-border-bridal-katan" if "ktn-meena" in pid else "pastel-soft-muslin" if "msn-pastel" in pid else "cotton-block-print" if "cot-block" in pid else "floral-silk-saree" if "silk-floral" in pid else "sequin-party-saree"
        specs.append(spec(pid=pid, name=name, category="Saree", section="ladies", gender="women", color=color, color_family=family, fabric=fabric, work_type=work, price=price, stock=stock, query=query, design_id=design, variant_group=design.replace("-", " ").title(), occasion="wedding, party, eid" if price > 5000 else "office, daily wear, summer", style="premium" if price > 5000 else "lightweight", brand="Sonjoy Boutique"))

    three_pieces = [
        ("three-piece-lawn-blue", "Printed Lawn Three Piece - Sky Blue", "sky blue", "blue", "lawn", "printed", 3200, 5, "blue salwar kameez"),
        ("three-piece-lawn-pink", "Printed Lawn Three Piece - Pink", "pink", "pink", "lawn", "printed", 3200, 4, "pink salwar kameez"),
        ("three-piece-lawn-green", "Printed Lawn Three Piece - Green", "green", "green", "lawn", "printed", 3200, 3, "green salwar kameez"),
        ("three-piece-embroidered-black", "Embroidered Party Three Piece - Black", "black", "black", "georgette", "embroidery", 5800, 2, "black salwar kameez embroidery"),
        ("three-piece-embroidered-maroon", "Embroidered Party Three Piece - Maroon", "maroon", "red", "georgette", "embroidery", 5800, 1, "maroon salwar kameez embroidery"),
        ("three-piece-cotton-white", "Cotton Everyday Three Piece - White", "white", "white", "cotton", "plain", 2500, 6, "white salwar kameez"),
        ("three-piece-cotton-yellow", "Cotton Everyday Three Piece - Yellow", "yellow", "yellow", "cotton", "plain", 2500, 5, "yellow salwar kameez"),
        ("three-piece-party-gold", "Golden Party Three Piece", "gold", "gold", "net", "zari", 6400, 1, "gold salwar kameez"),
        ("three-piece-office-navy", "Office Wear Three Piece - Navy", "navy blue", "blue", "cotton blend", "minimal print", 2900, 4, "blue kurta set"),
        ("three-piece-office-grey", "Office Wear Three Piece - Grey", "grey", "grey", "cotton blend", "minimal print", 2900, 3, "grey kurta set"),
    ]
    for pid, name, color, family, fabric, work, price, stock, query in three_pieces:
        group = "printed-lawn-three-piece" if "lawn" in pid else "embroidered-party-three-piece" if "embroidered" in pid else "cotton-everyday-three-piece" if "cotton" in pid else "office-three-piece" if "office" in pid else pid
        specs.append(spec(pid=pid, name=name, category="Three Piece", section="ladies", gender="women", color=color, color_family=family, fabric=fabric, work_type=work, price=price, stock=stock, query=query, design_id=group, variant_group=group.replace("-", " ").title(), occasion="party, eid" if price > 5000 else "office, daily wear", style="elegant" if price > 5000 else "comfortable"))

    bags = [
        ("bag-tote-black-everyday", "Everyday Black Tote Bag", "black", "black", "tote", 1650, 8, "black tote bag"),
        ("bag-tote-tan-everyday", "Everyday Tan Tote Bag", "tan", "brown", "tote", 1650, 6, "tan tote bag"),
        ("bag-clutch-antique-gold", "Antique Gold Party Clutch", "antique gold", "gold", "clutch", 1850, 4, "gold clutch bag"),
        ("bag-clutch-silver-party", "Silver Party Clutch", "silver", "silver", "clutch", 1850, 3, "silver clutch bag"),
        ("bag-potli-gold-beaded", "Gold Beaded Potli Bag", "gold", "gold", "potli", 1450, 5, "gold drawstring bag"),
        ("bag-handbag-red-small", "Small Red Handbag", "red", "red", "handbag", 2100, 2, "red handbag"),
        ("bag-handbag-blue-small", "Small Blue Handbag", "blue", "blue", "handbag", 2100, 2, "blue handbag"),
        ("bag-crossbody-cream", "Cream Crossbody Bag", "cream", "white", "crossbody", 1750, 5, "cream crossbody bag"),
        ("bag-backpack-black-mini", "Mini Black Backpack", "black", "black", "backpack", 2200, 3, "black mini backpack"),
        ("bag-party-velvet-maroon", "Maroon Velvet Party Bag", "maroon", "red", "party bag", 2400, 1, "maroon evening bag"),
    ]
    for pid, name, color, family, bag_type, price, stock, query in bags:
        group = f"{bag_type}-bag".replace(" ", "-")
        specs.append(spec(pid=pid, name=name, category="Bag", section="ladies", gender="women", color=color, color_family=family, product_type=bag_type, price=price, stock=stock, query=query, design_id=group, variant_group=group.title(), occasion="office, party, daily wear", style="functional", extra_attrs={"bag_type": bag_type}))

    jewelry = [
        ("jewelry-pearl-earring-white", "White Pearl Earrings", "white", "white", "earrings", 750, 8, "pearl earrings"),
        ("jewelry-pearl-necklace-white", "White Pearl Necklace", "white", "white", "necklace", 1250, 4, "pearl necklace"),
        ("jewelry-gold-bangle-set", "Gold Tone Bangle Set", "gold", "gold", "bangle", 950, 6, "gold bangle"),
        ("jewelry-silver-bangle-set", "Silver Tone Bangle Set", "silver", "silver", "bangle", 950, 6, "silver bangle"),
        ("jewelry-kundan-necklace-red", "Red Kundan Necklace Set", "red", "red", "necklace set", 2200, 2, "kundan necklace"),
        ("jewelry-kundan-necklace-green", "Green Kundan Necklace Set", "green", "green", "necklace set", 2200, 1, "green necklace"),
        ("jewelry-nosepin-gold", "Gold Nose Pin", "gold", "gold", "nose pin", 450, 10, "gold nose pin"),
        ("jewelry-anklet-silver", "Silver Anklet Pair", "silver", "silver", "anklet", 680, 7, "silver anklet"),
        ("jewelry-ring-rose-gold", "Rose Gold Adjustable Ring", "rose gold", "gold", "ring", 620, 5, "rose gold ring"),
        ("jewelry-jhumka-gold-red", "Gold Red Jhumka Earrings", "gold red", "gold", "jhumka", 890, 4, "jhumka earrings"),
    ]
    for pid, name, color, family, jewelry_type, price, stock, query in jewelry:
        specs.append(spec(pid=pid, name=name, category="Jewelry", section="ladies", gender="women", color=color, color_family=family, product_type=jewelry_type, price=price, stock=stock, query=query, design_id=slug(jewelry_type), occasion="wedding, party, daily wear", style="ornamental", extra_attrs={"jewelry_type": jewelry_type}))

    cosmetics = [
        ("cosmetic-lipstick-red-matte", "Matte Red Lipstick", "red", "red", "lipstick", 650, 12, "red lipstick"),
        ("cosmetic-lipstick-nude-matte", "Matte Nude Lipstick", "nude", "brown", "lipstick", 650, 10, "nude lipstick"),
        ("cosmetic-foundation-natural", "Natural Beige Foundation", "beige", "brown", "foundation", 1450, 5, "foundation bottle"),
        ("cosmetic-foundation-warm", "Warm Honey Foundation", "honey", "brown", "foundation", 1450, 4, "makeup foundation"),
        ("cosmetic-kajal-black", "Black Kajal Pencil", "black", "black", "kajal", 350, 14, "black eyeliner pencil"),
        ("cosmetic-compact-ivory", "Ivory Compact Powder", "ivory", "white", "compact powder", 850, 7, "compact powder makeup"),
        ("cosmetic-blush-pink", "Soft Pink Blush", "pink", "pink", "blush", 780, 6, "pink blush makeup"),
        ("cosmetic-mascara-black", "Black Volume Mascara", "black", "black", "mascara", 720, 8, "black mascara"),
    ]
    for pid, name, color, family, product_type, price, stock, query in cosmetics:
        specs.append(spec(pid=pid, name=name, category="Cosmetics", section="ladies", gender="women", color=color, color_family=family, product_type=product_type, price=price, stock=stock, query=query, occasion="makeup, party, daily wear", style="beauty", extra_attrs={"cosmetic_type": product_type}))

    beauty = [
        ("beauty-sunscreen-oily-spf50", "SPF 50 Sunscreen for Oily Skin", "white", "white", "sunscreen", 980, 9, "sunscreen tube"),
        ("beauty-sunscreen-dry-spf50", "SPF 50 Sunscreen for Dry Skin", "white", "white", "sunscreen", 980, 5, "sunscreen lotion"),
        ("beauty-facewash-neem", "Neem Face Wash", "green", "green", "face wash", 420, 11, "face wash tube"),
        ("beauty-serum-vitamin-c", "Vitamin C Face Serum", "orange", "orange", "serum", 1250, 4, "face serum bottle"),
        ("beauty-moisturizer-aloe", "Aloe Moisturizer", "green", "green", "moisturizer", 650, 7, "aloe moisturizer"),
        ("beauty-cream-night", "Hydrating Night Cream", "white", "white", "cream", 890, 6, "skin cream jar"),
        ("beauty-toner-rose", "Rose Water Toner", "pink", "pink", "toner", 520, 8, "rose water bottle"),
        ("beauty-sheetmask-bright", "Brightening Sheet Mask", "white", "white", "sheet mask", 180, 20, "sheet mask skincare"),
    ]
    for pid, name, color, family, product_type, price, stock, query in beauty:
        specs.append(spec(pid=pid, name=name, category="Beauty", section="ladies", gender="women", color=color, color_family=family, product_type=product_type, price=price, stock=stock, query=query, occasion="skin care, daily wear", style="care", extra_attrs={"skin_type": "oily, dry, normal" if "sunscreen" in product_type else "all skin"}))

    watches = [
        ("watch-men-black-leather", "Men's Black Leather Watch", "black", "black", "watch", 2850, 4, "black wristwatch"),
        ("watch-men-brown-leather", "Men's Brown Leather Watch", "brown", "brown", "watch", 2850, 3, "brown wristwatch"),
        ("watch-men-silver-chain", "Men's Silver Chain Watch", "silver", "silver", "watch", 3400, 2, "silver wristwatch"),
        ("watch-women-gold-chain", "Women's Gold Chain Watch", "gold", "gold", "watch", 3200, 3, "gold wristwatch"),
        ("watch-women-rose-gold", "Women's Rose Gold Watch", "rose gold", "gold", "watch", 3350, 2, "rose gold watch"),
        ("watch-women-white-strap", "Women's White Strap Watch", "white", "white", "watch", 2400, 5, "white wristwatch"),
        ("watch-unisex-smart-black", "Black Smart Watch", "black", "black", "smart watch", 4200, 4, "black smartwatch"),
        ("watch-unisex-sport-blue", "Blue Sport Watch", "blue", "blue", "sport watch", 2200, 5, "blue sport watch"),
    ]
    for pid, name, color, family, product_type, price, stock, query in watches:
        gender = "men" if "-men-" in pid else "women" if "-women-" in pid else "unisex"
        specs.append(spec(pid=pid, name=name, category="Watch", section=gender if gender != "women" else "ladies", gender=gender, color=color, color_family=family, product_type=product_type, price=price, stock=stock, query=query, occasion="gift, office, daily wear", style="accessory"))

    shoes = [
        ("shoe-women-heel-black-38", "Women's Black Block Heel - Size 38", "black", "black", "heel", 2350, 3, "black high heel shoe"),
        ("shoe-women-heel-gold-38", "Women's Gold Party Heel - Size 38", "gold", "gold", "heel", 2600, 2, "gold high heel shoe"),
        ("shoe-women-sandal-red-37", "Women's Red Sandal - Size 37", "red", "red", "sandal", 1550, 5, "red sandal"),
        ("shoe-women-sandal-white-39", "Women's White Sandal - Size 39", "white", "white", "sandal", 1550, 4, "white sandal"),
        ("shoe-men-loafer-brown-42", "Men's Brown Loafer - Size 42", "brown", "brown", "loafer", 2850, 3, "brown loafer"),
        ("shoe-men-sneaker-white-43", "Men's White Casual Sneaker - Size 43", "white", "white", "sneaker", 2600, 5, "white sneaker"),
        ("shoe-men-sneaker-black-42", "Men's Black Casual Sneaker - Size 42", "black", "black", "sneaker", 2600, 4, "black sneaker"),
        ("shoe-men-sandal-black-41", "Men's Black Sandal - Size 41", "black", "black", "sandal", 1750, 3, "black sandal"),
    ]
    for pid, name, color, family, shoe_type, price, stock, query in shoes:
        gender = "men" if "-men-" in pid else "women"
        size = re.search(r"-(\d{2})$", pid).group(1) if re.search(r"-(\d{2})$", pid) else ""
        specs.append(spec(pid=pid, name=name, category="Shoes", section=gender if gender == "men" else "ladies", gender=gender, color=color, color_family=family, product_type=shoe_type, price=price, stock=stock, query=query, size=size, occasion="office, party, daily wear", style="comfortable", extra_attrs={"shoe_type": shoe_type}))

    panjabis = [
        ("panjabi-cotton-white-m", "Men's White Cotton Panjabi - Size M", "white", "white", "M", "cotton", 2600, 4, "white kurta"),
        ("panjabi-cotton-white-l", "Men's White Cotton Panjabi - Size L", "white", "white", "L", "cotton", 2600, 3, "white kurta"),
        ("panjabi-silk-navy-xl", "Men's Navy Silk Panjabi - Size XL", "navy blue", "blue", "XL", "silk", 4200, 2, "blue kurta"),
        ("panjabi-silk-maroon-l", "Men's Maroon Silk Panjabi - Size L", "maroon", "red", "L", "silk", 4200, 2, "maroon kurta"),
        ("panjabi-embroidered-black-m", "Men's Black Embroidered Panjabi - Size M", "black", "black", "M", "cotton silk", 3600, 2, "black kurta embroidery"),
        ("panjabi-embroidered-cream-xl", "Men's Cream Embroidered Panjabi - Size XL", "cream", "white", "XL", "cotton silk", 3600, 1, "cream kurta embroidery"),
    ]
    for pid, name, color, family, size, fabric, price, stock, query in panjabis:
        group = "classic-cotton-panjabi" if "cotton" in pid else "silk-panjabi" if "silk" in pid else "embroidered-panjabi"
        specs.append(spec(pid=pid, name=name, category="Panjabi", section="men", gender="men", color=color, color_family=family, fabric=fabric, work_type="embroidery" if "embroidered" in pid else "plain", size=size, price=price, stock=stock, query=query, design_id=group, variant_group=group.title(), occasion="eid, jummah, wedding", style="traditional"))

    shirt_sources = {
        "black": "/home/sonjoy/Bar tax/shirt/black.jpg",
        "grey": "/home/sonjoy/Bar tax/shirt/grey.jpg",
        "olive": "/home/sonjoy/Bar tax/shirt/olive.jpg",
        "white": "/home/sonjoy/Bar tax/shirt/white.jpg",
    }
    for color, path in shirt_sources.items():
        family = "green" if color == "olive" else "white" if color in {"white", "grey"} else color
        specs.append(spec(pid=f"shirt-ribbed-polo-{color}", name=f"Ribbed Open-Collar Knit Polo - {color.title()}", category="Shirt", section="men", gender="men", color=color, color_family=family, fabric="knit", work_type="vertical ribbed", product_type="polo shirt", price=1750, stock=5 if color != "grey" else 2, query=f"{color} ribbed polo shirt", size="M, L, XL", design_id="vertical-ribbed-open-collar-knit", variant_group="Ribbed Open Collar Knit Polo", occasion="casual, summer, travel", style="minimal casual", local_path=path, image_kind="product_photo", is_reference=False, extra_attrs={"neckline": "open collar", "sleeve": "half sleeve", "fit": "regular"}))

    shirts = [
        ("shirt-oxford-blue-m", "Men's Blue Oxford Shirt - Size M", "blue", "blue", "M", "cotton oxford", "regular", 1800, 5, "blue oxford shirt"),
        ("shirt-formal-white-l", "Men's White Formal Shirt - Size L", "white", "white", "L", "cotton blend", "regular", 1950, 4, "white formal shirt"),
        ("shirt-check-red-l", "Men's Red Check Shirt - Size L", "red check", "red", "L", "cotton", "regular", 1850, 3, "red plaid shirt"),
        ("shirt-denim-blue-xl", "Men's Blue Denim Shirt - Size XL", "denim blue", "blue", "XL", "denim", "regular", 2450, 2, "blue denim shirt"),
    ]
    for pid, name, color, family, size, fabric, fit, price, stock, query in shirts:
        specs.append(spec(pid=pid, name=name, category="Shirt", section="men", gender="men", color=color, color_family=family, fabric=fabric, size=size, price=price, stock=stock, query=query, design_id=slug(name.rsplit(" - ", 1)[0]), variant_group=name.rsplit(" - ", 1)[0], occasion="office, casual", style="formal casual", extra_attrs={"fit": fit, "sleeve": "full sleeve"}))

    pants = [
        ("pant-chino-navy-32", "Men's Navy Chino Pant - Waist 32", "navy blue", "blue", "32", "cotton twill", 2250, 3, "navy trousers"),
        ("pant-formal-black-34", "Men's Black Formal Pant - Waist 34", "black", "black", "34", "poly viscose", 2450, 2, "black trousers"),
        ("pant-jeans-blue-32", "Men's Blue Denim Jeans - Waist 32", "blue", "blue", "32", "denim", 2600, 4, "blue jeans"),
        ("pant-cargo-olive-34", "Men's Olive Cargo Pant - Waist 34", "olive", "green", "34", "cotton cargo", 2850, 3, "olive cargo pants"),
    ]
    for pid, name, color, family, waist, fabric, price, stock, query in pants:
        specs.append(spec(pid=pid, name=name, category="Pant", section="men", gender="men", color=color, color_family=family, fabric=fabric, size=waist, price=price, stock=stock, query=query, design_id=slug(name.rsplit(" - ", 1)[0]), variant_group=name.rsplit(" - ", 1)[0], occasion="office, casual", style="smart casual", extra_attrs={"waist": waist, "fit": "regular"}))

    perfumes = [
        ("perfume-men-oud-100ml", "Men's Oud Noir Perfume 100ml", "black", "black", "oud, woody, amber", 3200, 5, "black perfume bottle"),
        ("perfume-women-floral-50ml", "Women's Floral Bloom Perfume 50ml", "pink", "pink", "floral, fresh", 2400, 6, "pink perfume bottle"),
        ("perfume-unisex-citrus-50ml", "Unisex Citrus Fresh Perfume 50ml", "yellow", "yellow", "citrus, fresh", 1800, 4, "yellow perfume bottle"),
        ("perfume-women-vanilla-100ml", "Women's Vanilla Musk Perfume 100ml", "cream", "white", "vanilla, musk", 2900, 3, "cream perfume bottle"),
    ]
    for pid, name, color, family, scent, price, stock, query in perfumes:
        gender = "men" if "-men-" in pid else "women" if "-women-" in pid else "unisex"
        specs.append(spec(pid=pid, name=name, category="Perfume", section=gender if gender == "men" else "ladies" if gender == "women" else "unisex", gender=gender, color=color, color_family=family, product_type="perfume", price=price, stock=stock, query=query, occasion="gift, eid, party", style="fragrance", extra_attrs={"fragrance_family": scent, "size": "100ml" if "100ml" in pid else "50ml"}))

    return specs


if __name__ == "__main__":
    raise SystemExit(main())
