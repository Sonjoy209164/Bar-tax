from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/mnt/nvme0n1p3/sonjoy/horitoki_saree_dataset")
BASE_URL = "https://horitoki.com"
SEARCH_URL = f"{BASE_URL}/search2"
CATEGORY_URL = f"{BASE_URL}/category/women-saree"
CATEGORY_ID = 3


COLOR_KEYWORDS = {
    "black": "black",
    "white": "white",
    "red": "red",
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "purple": "purple",
    "pink": "pink",
    "orange": "orange",
    "gold": "gold",
    "golden": "gold",
    "silver": "silver",
    "grey": "grey",
    "gray": "grey",
    "maroon": "red",
    "navy": "blue",
    "cream": "cream",
    "beige": "beige",
    "brown": "brown",
    "multi": "multicolor",
    "colorful": "multicolor",
}

FABRIC_KEYWORDS = {
    "silk": "silk",
    "art silk": "art silk",
    "cotton": "cotton",
    "half silk": "half silk",
    "georgette": "georgette",
    "muslin": "muslin",
    "jamdani": "jamdani",
    "katan": "katan",
    "khadi": "khadi cotton",
}

MOTIF_KEYWORDS = {
    "rickshaw": "rickshaw paint",
    "paint": "painting",
    "painting": "painting",
    "alpona": "alpona",
    "nakshikantha": "nakshikantha",
    "moyur": "moyur",
    "peacock": "peacock",
    "pankhi": "bird",
    "flamingo": "bird",
    "flemingo": "bird",
    "jamini": "jamini roy art",
    "van gogh": "van gogh art",
    "starry": "starry night",
    "sunflower": "sunflower",
    "typography": "typography",
    "batik": "batik",
    "kalamkari": "kalamkari",
    "mughal": "mughal",
    "gamcha": "gamcha",
    "boishakhi": "boishakhi",
    "lal par": "lal par",
}


@dataclass
class ProductCard:
    position: int
    name: str
    product_url: str
    product_slug: str
    source_card_id: str | None
    current_price_bdt: float | None
    original_price_bdt: float | None
    discount_percent: int | None
    card_image_urls: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and label Horitoki women saree product images for local research."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--target-count", type=int, default=145)
    parser.add_argument("--delay", type=float, default=0.45, help="Delay between page/image requests.")
    parser.add_argument("--image-delay", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--force", action="store_true", help="Redownload images even if files exist.")
    parser.add_argument("--skip-detail-pages", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    dirs = {
        "images": out_dir / "images",
        "raw": out_dir / "raw",
        "raw_products": out_dir / "raw" / "product_pages",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; BanglaTaxRAGDatasetBuilder/1.0; "
                "research dataset; respectful rate limited)"
            ),
            "Accept": "text/html,application/json,image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": CATEGORY_URL,
        }
    )

    started_at = datetime.now(UTC)
    cards = collect_product_cards(session, args.target_count, args.delay, args.timeout, dirs["raw"])
    print(f"Collected {len(cards)} product cards.")

    catalog_rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, card in enumerate(cards[: args.target_count], start=1):
        product_id = f"horitoki_saree_{index:03d}_{slugify(card.name)[:60]}"
        product_dir = dirs["images"] / product_id
        product_dir.mkdir(parents=True, exist_ok=True)

        detail = {}
        detail_html = ""
        raw_product_path = dirs["raw_products"] / f"{product_id}.html"
        if not args.skip_detail_pages:
            try:
                if raw_product_path.exists() and not args.force:
                    detail_html = raw_product_path.read_text(encoding="utf-8")
                else:
                    detail_html = fetch_text(session, card.product_url, args.timeout)
                    raw_product_path.write_text(detail_html, encoding="utf-8")
                detail = parse_detail_page(detail_html)
            except Exception as exc:  # noqa: BLE001 - keep scrape failure data for audit.
                failures.append({"product_url": card.product_url, "stage": "detail_page", "error": str(exc)})
            time.sleep(args.delay)

        image_urls = unique_urls((detail.get("gallery_image_urls") or []) + card.card_image_urls)
        if not image_urls:
            failures.append({"product_url": card.product_url, "stage": "image_discovery", "error": "no images found"})

        downloaded_images = []
        for image_index, image_url in enumerate(image_urls, start=1):
            role = "primary" if image_index == 1 else f"gallery_{image_index}"
            try:
                image_record = download_image(
                    session=session,
                    image_url=image_url,
                    product_dir=product_dir,
                    product_id=product_id,
                    image_index=image_index,
                    role=role,
                    timeout=args.timeout,
                    force=args.force,
                )
                downloaded_images.append(image_record)
                image_rows.append(image_record)
            except Exception as exc:  # noqa: BLE001 - keep scrape failure data for audit.
                failures.append(
                    {
                        "product_url": card.product_url,
                        "image_url": image_url,
                        "stage": "image_download",
                        "error": str(exc),
                    }
                )
            time.sleep(args.image_delay)

        labels = derive_labels(card.name, detail.get("description_text", ""))
        current_price = detail.get("current_price_bdt") or card.current_price_bdt
        original_price = detail.get("original_price_bdt") or card.original_price_bdt

        row = {
            "dataset_product_id": product_id,
            "source": "horitoki.com",
            "source_category_url": CATEGORY_URL,
            "source_product_url": card.product_url,
            "source_product_slug": card.product_slug,
            "source_card_id": card.source_card_id,
            "name": card.name,
            "brand": detail.get("brand") or "Horitoki",
            "category": "women_saree",
            "department": "women",
            "garment_type": "saree",
            "currency": "BDT",
            "current_price_bdt": current_price,
            "original_price_bdt": original_price,
            "discount_percent": card.discount_percent,
            "availability": detail.get("availability") or "unknown",
            "sku": detail.get("sku"),
            "rating": detail.get("rating"),
            "review_count": detail.get("review_count"),
            "description": detail.get("description_text"),
            "labels": labels,
            "images": downloaded_images,
            "image_count": len(downloaded_images),
            "source_image_count": len(image_urls),
            "source_rights_note": (
                "Images and product text are sourced from horitoki.com for local research/prototyping. "
                "Do not redistribute or use commercially without permission from the rights owner."
            ),
            "created_at": datetime.now(UTC).isoformat(),
        }
        catalog_rows.append(row)
        print(f"[{index:03d}/{min(args.target_count, len(cards)):03d}] {card.name} -> {len(downloaded_images)} images")

    write_jsonl(out_dir / "catalog.jsonl", catalog_rows)
    write_jsonl(out_dir / "image_manifest.jsonl", image_rows)
    write_labels_csv(out_dir / "labels.csv", catalog_rows)
    write_failures(out_dir / "failures.jsonl", failures)

    manifest = {
        "dataset_name": "horitoki_women_saree_145",
        "created_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "source_site": BASE_URL,
        "source_category_url": CATEGORY_URL,
        "source_search_endpoint": SEARCH_URL,
        "robots_txt_checked": f"{BASE_URL}/robots.txt",
        "target_product_count": args.target_count,
        "products_collected": len(catalog_rows),
        "images_downloaded": len(image_rows),
        "products_without_images": [row["dataset_product_id"] for row in catalog_rows if not row["images"]],
        "failures": len(failures),
        "files": {
            "catalog_jsonl": str(out_dir / "catalog.jsonl"),
            "labels_csv": str(out_dir / "labels.csv"),
            "image_manifest_jsonl": str(out_dir / "image_manifest.jsonl"),
            "failures_jsonl": str(out_dir / "failures.jsonl"),
            "images_dir": str(dirs["images"]),
            "raw_dir": str(dirs["raw"]),
        },
        "license_and_usage_note": (
            "This is a local research/prototyping dataset assembled from public product pages. "
            "The images likely remain copyrighted by Horitoki or its suppliers. Use internally for testing, "
            "and obtain permission before redistribution, publication with images, or commercial reuse."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "README.md").write_text(render_readme(manifest), encoding="utf-8")
    print()
    print(f"Dataset saved to: {out_dir}")
    print(f"Products: {len(catalog_rows)}")
    print(f"Images:   {len(image_rows)}")
    print(f"Failures: {len(failures)}")
    return 0 if len(catalog_rows) >= min(args.target_count, 145) else 1


def collect_product_cards(
    session: requests.Session, target_count: int, delay: float, timeout: float, raw_dir: Path
) -> list[ProductCard]:
    cards: list[ProductCard] = []
    seen_urls: set[str] = set()
    page = 1
    max_pages = 30
    total_count = None
    while page <= max_pages and len(cards) < target_count:
        response = session.get(
            SEARCH_URL,
            params={"categories[]": CATEGORY_ID, "page": page},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        (raw_dir / f"search_page_{page:02d}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        total_count = int(payload.get("total_product_count") or total_count or 0)
        page_cards = parse_product_cards(payload.get("product_html") or "", start_position=len(cards) + 1)
        if not page_cards:
            break
        for card in page_cards:
            if card.product_url in seen_urls:
                continue
            seen_urls.add(card.product_url)
            cards.append(card)
            if len(cards) >= target_count:
                break
        print(f"Search page {page}: {len(page_cards)} cards, total collected {len(cards)}/{target_count}")
        if total_count and len(cards) >= min(total_count, target_count):
            break
        page += 1
        time.sleep(delay)
    return cards


def parse_product_cards(product_html: str, start_position: int) -> list[ProductCard]:
    soup = BeautifulSoup(product_html, "html.parser")
    cards: list[ProductCard] = []
    product_boxes = soup.select("div.aiz-card-box")
    for offset, box in enumerate(product_boxes):
        title_link = box.select_one("h3 a[href]")
        image_link = box.select_one("a.image-hover-effect[href]")
        product_url = normalize_url((title_link or image_link).get("href") if (title_link or image_link) else "")
        if not product_url or "/product/" not in product_url:
            continue
        name = clean_text((title_link.get("title") if title_link else None) or title_link.get_text(" ", strip=True))
        image_urls = []
        for img in box.select("img.product-main-image, img.product-hover-image"):
            src = img.get("data-src") or img.get("src")
            if src and "placeholder" not in src:
                image_urls.append(normalize_url(src))
        discount_percent = None
        discount_el = box.find(string=re.compile(r"^-\d+%$"))
        if discount_el:
            discount_percent = parse_int(str(discount_el))
        price_values = [parse_price(el.get_text(" ", strip=True)) for el in box.select(".fs-14 del, .fs-14 span")]
        price_values = [value for value in price_values if value is not None]
        original_price = price_values[0] if len(price_values) > 1 else None
        current_price = price_values[-1] if price_values else None
        source_card_id = parse_card_id(str(box))
        cards.append(
            ProductCard(
                position=start_position + offset,
                name=name,
                product_url=product_url,
                product_slug=Path(urlparse(product_url).path).name,
                source_card_id=source_card_id,
                current_price_bdt=current_price,
                original_price_bdt=original_price,
                discount_percent=discount_percent,
                card_image_urls=unique_urls(image_urls),
            )
        )
    return cards


def parse_detail_page(page_html: str) -> dict[str, Any]:
    soup = BeautifulSoup(page_html, "html.parser")
    data: dict[str, Any] = {}
    name_el = soup.select_one("h1")
    if name_el:
        data["detail_name"] = clean_text(name_el.get_text(" ", strip=True))
    brand_anchor = soup.select_one('a[href*="/brand/"]')
    if brand_anchor:
        data["brand"] = clean_text(brand_anchor.get_text(" ", strip=True))
    sku_el = soup.select_one("#variant_sku")
    if sku_el:
        data["sku"] = clean_text(sku_el.get_text(" ", strip=True))
    data["availability"] = "out_of_stock" if "Out of Stock" in page_html else "in_stock"

    rating_match = re.search(r'<span class="fs-14 text-dark fw-bold">([^<]+)</span>', page_html)
    if rating_match:
        data["rating"] = parse_float(rating_match.group(1))
    review_match = re.search(r"\((\d+)\s+reviews?\)", page_html, flags=re.IGNORECASE)
    if review_match:
        data["review_count"] = int(review_match.group(1))

    current_price_el = soup.select_one("h6")
    if current_price_el:
        data["current_price_bdt"] = parse_price(current_price_el.get_text(" ", strip=True))
    del_el = soup.select_one("h6 del")
    if del_el:
        data["original_price_bdt"] = parse_price(del_el.get_text(" ", strip=True))

    description_el = soup.select_one("#description")
    if description_el:
        data["description_text"] = clean_text(description_el.get_text(" ", strip=True))

    gallery_segment = page_html
    if "THUMBNAILS SLIDER" in page_html and "<!--RIGHT SIDE-->" in page_html:
        gallery_segment = page_html.split("THUMBNAILS SLIDER", 1)[1].split("<!--RIGHT SIDE-->", 1)[0]
    image_urls = re.findall(r'https?://horitoki\.com/public/uploads/all/[^"\']+', html.unescape(gallery_segment))
    data["gallery_image_urls"] = unique_urls(image_urls)
    return data


def download_image(
    session: requests.Session,
    image_url: str,
    product_dir: Path,
    product_id: str,
    image_index: int,
    role: str,
    timeout: float,
    force: bool,
) -> dict[str, Any]:
    dataset_root = product_dir.parents[1]
    ext = Path(urlparse(image_url).path).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        ext = ".jpg"
    image_id = f"{product_id}_image_{image_index:02d}"
    filename = f"{image_id}{ext}"
    local_path = product_dir / filename
    if force or not local_path.exists():
        response = session.get(image_url, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type.lower():
            raise ValueError(f"not an image content-type: {content_type}")
        local_path.write_bytes(response.content)
    width, height = image_dimensions(local_path)
    digest = sha256_file(local_path)
    return {
        "image_id": image_id,
        "product_id": product_id,
        "role": role,
        "source_url": image_url,
        "local_path": str(local_path),
        "relative_path": str(local_path.relative_to(dataset_root))
        if local_path.is_relative_to(dataset_root)
        else str(local_path),
        "width": width,
        "height": height,
        "file_size_bytes": local_path.stat().st_size,
        "sha256": digest,
        "image_kind": "source_site_product_photo",
    }


def derive_labels(name: str, description: str) -> dict[str, Any]:
    text = f"{name} {description}".lower()
    colors = []
    for keyword, label in COLOR_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text):
            colors.append(label)
    fabrics = []
    for keyword, label in FABRIC_KEYWORDS.items():
        if keyword in text:
            fabrics.append(label)
    motifs = []
    for keyword, label in MOTIF_KEYWORDS.items():
        if keyword in text:
            motifs.append(label)
    return {
        "color_families": sorted(set(colors)),
        "fabric_keywords": sorted(set(fabrics)),
        "motif_keywords": sorted(set(motifs)),
        "occasion": infer_occasion(text),
        "visual_style": infer_visual_style(text),
        "label_source": "heuristic_from_name_and_description",
    }


def infer_occasion(text: str) -> list[str]:
    values = []
    if any(token in text for token in ["boishakh", "puja", "eid", "festival", "festive", "celebration"]):
        values.append("festival")
    if any(token in text for token in ["party", "wedding", "bridal"]):
        values.append("party")
    if any(token in text for token in ["casual", "lightweight", "daily"]):
        values.append("casual")
    return values


def infer_visual_style(text: str) -> list[str]:
    values = []
    if any(token in text for token in ["digital", "print", "printed"]):
        values.append("printed")
    if any(token in text for token in ["paint", "painting", "art", "motif"]):
        values.append("art_motif")
    if any(token in text for token in ["traditional", "heritage", "ethnic"]):
        values.append("traditional")
    if any(token in text for token in ["minimal", "plain"]):
        values.append("minimal")
    return values


def fetch_text(session: requests.Session, url: str, timeout: float) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def normalize_url(value: str | None) -> str:
    if not value:
        return ""
    return urljoin(BASE_URL, html.unescape(value.strip().replace("\\/", "/")))


def unique_urls(urls: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for url in urls:
        normalized = normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def parse_card_id(html_text: str) -> str | None:
    match = re.search(r"(?:addToWishList|addToCompare|addToCartSingleProduct|showAddToCartModal)\((\d+)\)", html_text)
    return match.group(1) if match else None


def parse_price(text: str | None) -> float | None:
    if not text:
        return None
    normalized = (
        text.replace("৳", "")
        .replace(",", "")
        .replace("\u09f3", "")
        .replace("\xa0", " ")
        .strip()
    )
    normalized = translate_bengali_digits(normalized)
    match = re.search(r"(\d+(?:\.\d+)?)", normalized)
    return float(match.group(1)) if match else None


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    normalized = translate_bengali_digits(text)
    match = re.search(r"-?(\d+)", normalized)
    return int(match.group(1)) if match else None


def parse_float(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", translate_bengali_digits(text))
    return float(match.group(1)) if match else None


def translate_bengali_digits(text: str) -> str:
    table = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
    return text.translate(table)


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "product"


def image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        return img.size


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_failures(path: Path, rows: list[dict[str, Any]]) -> None:
    write_jsonl(path, rows)


def write_labels_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "dataset_product_id",
        "name",
        "source_product_url",
        "sku",
        "brand",
        "category",
        "current_price_bdt",
        "original_price_bdt",
        "availability",
        "image_count",
        "color_families",
        "fabric_keywords",
        "motif_keywords",
        "occasion",
        "visual_style",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            labels = row.get("labels", {})
            writer.writerow(
                {
                    "dataset_product_id": row.get("dataset_product_id"),
                    "name": row.get("name"),
                    "source_product_url": row.get("source_product_url"),
                    "sku": row.get("sku"),
                    "brand": row.get("brand"),
                    "category": row.get("category"),
                    "current_price_bdt": row.get("current_price_bdt"),
                    "original_price_bdt": row.get("original_price_bdt"),
                    "availability": row.get("availability"),
                    "image_count": row.get("image_count"),
                    "color_families": ";".join(labels.get("color_families") or []),
                    "fabric_keywords": ";".join(labels.get("fabric_keywords") or []),
                    "motif_keywords": ";".join(labels.get("motif_keywords") or []),
                    "occasion": ";".join(labels.get("occasion") or []),
                    "visual_style": ";".join(labels.get("visual_style") or []),
                }
            )


def render_readme(manifest: dict[str, Any]) -> str:
    return f"""# Horitoki Women Saree Dataset

Local dataset built from public Horitoki women saree product pages.

## Summary

- Products collected: `{manifest['products_collected']}`
- Images downloaded: `{manifest['images_downloaded']}`
- Failures recorded: `{manifest['failures']}`
- Source category: `{manifest['source_category_url']}`

## Files

- `catalog.jsonl`: one product per line with labels and image records.
- `labels.csv`: flat spreadsheet-friendly label view.
- `image_manifest.jsonl`: one image per line with dimensions, hashes, and local paths.
- `failures.jsonl`: failed product/image requests, if any.
- `manifest.json`: dataset build metadata.
- `images/`: downloaded product images grouped by product ID.
- `raw/`: raw search JSON and product HTML snapshots for audit/debugging.

## Important Usage Note

{manifest['license_and_usage_note']}

For your bot: use this as a prototype/evaluation dataset. For production commerce, use shop-owned or authorized supplier photos.
"""


if __name__ == "__main__":
    raise SystemExit(main())
