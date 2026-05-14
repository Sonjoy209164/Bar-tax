from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "inventory" / "catalog.jsonl"
SOURCE_MANIFEST_PATH = ROOT / "data" / "inventory" / "catalog_image_sources.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "bangla-tax-rag-image-enricher/1.0 (demo catalog image attribution)"


def main() -> int:
    items = [json.loads(line) for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    cache: dict[str, dict[str, Any] | None] = {}
    source_manifest: list[dict[str, Any]] = []

    for index, item in enumerate(items, start=1):
        query = build_query(item)
        image = cache.get(query)
        if query not in cache:
            image = search_commons_image(query)
            cache[query] = image
            time.sleep(0.8)
        if image is None:
            fallback = build_fallback_query(item)
            image = cache.get(fallback)
            if fallback not in cache:
                image = search_commons_image(fallback)
                cache[fallback] = image
                time.sleep(0.8)
        if image is None:
            continue

        tags = visual_tags(item)
        image_id = f"{item['product_id']}-reference-1"
        item["images"] = [
            {
                "image_id": image_id,
                "url": image.get("thumburl") or image.get("url"),
                "source_url": image.get("descriptionurl"),
                "source_name": "Wikimedia Commons",
                "license": image.get("license"),
                "license_url": image.get("license_url"),
                "attribution": image.get("attribution"),
                "role": "primary",
                "kind": "reference_photo",
                "is_reference": True,
                "visual_tags": tags,
                "width": image.get("width"),
                "height": image.get("height"),
            }
        ]
        metadata = dict(item.get("metadata") or {})
        metadata["image_schema_version"] = "inventory-image-v1"
        metadata["image_source_policy"] = "demo_reference_external_not_actual_sku_photo"
        item["metadata"] = metadata
        source_manifest.append(
            {
                "product_id": item["product_id"],
                "name": item.get("name"),
                "query": query,
                "image_id": image_id,
                "source_url": image.get("descriptionurl"),
                "license": image.get("license"),
                "license_url": image.get("license_url"),
                "attribution": image.get("attribution"),
                "is_reference": True,
            }
        )
        print(f"[{index:02d}/{len(items)}] {item['product_id']} <- {query}", file=sys.stderr)

    CATALOG_PATH.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in items) + "\n",
        encoding="utf-8",
    )
    SOURCE_MANIFEST_PATH.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {CATALOG_PATH} with {len(source_manifest)} image reference(s).")
    print(f"Wrote source manifest to {SOURCE_MANIFEST_PATH}.")
    return 0


def build_query(item: dict[str, Any]) -> str:
    attrs = item.get("attributes") or {}
    category = str(attrs.get("category_key") or item.get("category") or "").casefold()
    color = str(attrs.get("color") or attrs.get("color_family") or "").strip()
    fabric = str(attrs.get("fabric") or "").strip()
    work = str(attrs.get("work_type") or "").strip()
    name = str(item.get("name") or "")

    if category == "saree":
        if fabric in {"jamdani", "katan", "muslin", "cotton"}:
            return f"{color} {fabric} sari"
        return f"{color} sari"
    if category == "three_piece":
        return f"{color} salwar kameez"
    if category == "bag":
        bag_type = attrs.get("bag_type") or "handbag"
        return f"{color} {bag_type}"
    if category == "jewelry":
        jewelry_type = attrs.get("jewelry_type") or "jewelry"
        return f"{color} {jewelry_type}"
    if category == "cosmetics":
        return first_matching(name, ("lipstick", "foundation", "kajal", "makeup")) or "cosmetics product"
    if category == "beauty":
        return first_matching(name, ("sunscreen", "face wash", "serum", "cream")) or "beauty product"
    if category == "watch":
        return f"{color} wristwatch"
    if category == "shoes":
        shoe_type = attrs.get("shoe_type") or "shoes"
        return f"{color} {shoe_type}"
    if category == "panjabi":
        return f"{color} kurta"
    if category == "shirt":
        return f"{color} shirt"
    if category == "pant":
        return f"{color} trousers"
    if category == "perfume":
        return "perfume bottle"
    return f"{color} {category}".strip() or "fashion product"


def build_fallback_query(item: dict[str, Any]) -> str:
    attrs = item.get("attributes") or {}
    category = str(attrs.get("category_key") or item.get("category") or "").casefold()
    return {
        "saree": "sari",
        "three_piece": "salwar kameez",
        "bag": "handbag",
        "jewelry": "jewelry",
        "cosmetics": "cosmetics",
        "beauty": "skin care product",
        "watch": "wristwatch",
        "shoes": "shoes",
        "panjabi": "kurta",
        "shirt": "shirt",
        "pant": "trousers",
        "perfume": "perfume bottle",
    }.get(category, "fashion product")


def first_matching(text: str, terms: tuple[str, ...]) -> str | None:
    normalized = text.casefold()
    for term in terms:
        if term in normalized:
            return term
    return None


def visual_tags(item: dict[str, Any]) -> list[str]:
    attrs = item.get("attributes") or {}
    tags = list(item.get("tags") or [])
    for key in (
        "category_key",
        "color",
        "color_family",
        "fabric",
        "work_type",
        "style",
        "occasion",
        "bag_type",
        "jewelry_type",
        "shoe_type",
        "fragrance_family",
    ):
        value = attrs.get(key)
        if value:
            tags.extend(split_tags(str(value)))
    return sorted({tag.strip().casefold() for tag in tags if tag and tag.strip()})[:24]


def split_tags(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,/|]", value) if part.strip()]


def search_commons_image(query: str) -> dict[str, Any] | None:
    params = {
        "action": "query",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrsearch": query,
        "gsrlimit": "8",
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "900",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            time.sleep(8.0)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except HTTPError:
                return None
        else:
            return None
    pages = payload.get("query", {}).get("pages", [])
    for page in pages:
        imageinfo = (page.get("imageinfo") or [{}])[0]
        mime = str(imageinfo.get("mime") or "")
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        ext = imageinfo.get("extmetadata") or {}
        return {
            "url": imageinfo.get("url"),
            "thumburl": imageinfo.get("thumburl") or imageinfo.get("url"),
            "descriptionurl": imageinfo.get("descriptionurl"),
            "width": imageinfo.get("width"),
            "height": imageinfo.get("height"),
            "license": metadata_value(ext, "LicenseShortName") or metadata_value(ext, "License"),
            "license_url": metadata_value(ext, "LicenseUrl"),
            "attribution": clean_html(metadata_value(ext, "Artist") or metadata_value(ext, "Credit")),
        }
    return None


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


if __name__ == "__main__":
    raise SystemExit(main())
