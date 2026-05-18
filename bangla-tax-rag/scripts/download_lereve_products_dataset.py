from __future__ import annotations

import argparse
import atexit
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image


DEFAULT_OUTPUT_DIR = Path("/mnt/nvme0n1p3/sonjoy/lereve_products_dataset")
BASE_URL = "https://www.lerevecraze.com"
API_URL = f"{BASE_URL}/wp-json/wp/v2/product"
DEFAULT_PER_PAGE = 100

API_FIELDS = ",".join(
    [
        "id",
        "date",
        "date_gmt",
        "modified",
        "modified_gmt",
        "slug",
        "status",
        "link",
        "title",
        "excerpt",
        "content",
        "featured_media",
        "yoast_head_json",
    ]
)

COLOR_KEYWORDS = {
    "black": "black",
    "white": "white",
    "red": "red",
    "maroon": "red",
    "wine": "red",
    "blue": "blue",
    "navy": "blue",
    "sky": "blue",
    "green": "green",
    "olive": "green",
    "mint": "green",
    "teal": "green",
    "yellow": "yellow",
    "mustard": "yellow",
    "purple": "purple",
    "violet": "purple",
    "lavender": "purple",
    "pink": "pink",
    "peach": "pink",
    "orange": "orange",
    "rust": "orange",
    "gold": "gold",
    "golden": "gold",
    "silver": "silver",
    "grey": "grey",
    "gray": "grey",
    "cream": "cream",
    "beige": "beige",
    "brown": "brown",
    "coffee": "brown",
    "multi": "multicolor",
    "multicolor": "multicolor",
}

GARMENT_KEYWORDS = {
    "saree": "saree",
    "sari": "saree",
    "salwar kameez": "salwar_kameez",
    "kameez": "kameez",
    "kurti": "kurti",
    "tunic": "tunic",
    "top": "top",
    "shirt": "shirt",
    "polo": "polo",
    "t-shirt": "t_shirt",
    "tee": "t_shirt",
    "panjabi": "panjabi",
    "punjabi": "panjabi",
    "fatua": "fatua",
    "waistcoat": "waistcoat",
    "dress": "dress",
    "gown": "gown",
    "maxi": "maxi",
    "abaya": "abaya",
    "skirt": "skirt",
    "palazzo": "palazzo",
    "trouser": "trouser",
    "pant": "pant",
    "jeans": "jeans",
    "jacket": "jacket",
    "shoe": "shoe",
    "sandal": "sandal",
    "bag": "bag",
    "scarf": "scarf",
    "dupatta": "dupatta",
}

FABRIC_KEYWORDS = {
    "cotton": "cotton",
    "viscose": "viscose",
    "silk": "silk",
    "georgette": "georgette",
    "linen": "linen",
    "denim": "denim",
    "chiffon": "chiffon",
    "muslin": "muslin",
    "rayon": "rayon",
    "polyester": "polyester",
    "knit": "knit",
    "velvet": "velvet",
    "jacquard": "jacquard",
}

STYLE_KEYWORDS = {
    "printed": "printed",
    "print": "printed",
    "embroidered": "embroidered",
    "embroidery": "embroidered",
    "solid": "solid",
    "striped": "striped",
    "stripe": "striped",
    "check": "checked",
    "checked": "checked",
    "floral": "floral",
    "ribbed": "ribbed",
    "a-line": "a_line",
    "regular": "regular_fit",
    "slim": "slim_fit",
    "relaxed": "relaxed_fit",
    "lapel": "lapel_collar",
    "bishop sleeve": "bishop_sleeve",
    "half sleeve": "half_sleeve",
    "full sleeve": "full_sleeve",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local Le Reve product-image dataset from public product metadata. "
            "Default mode downloads every public product row and the primary image. "
            "Use --enrich-pages for slower product-page details and --gallery-images for all gallery images."
        )
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-products", type=int)
    parser.add_argument("--page-delay", type=float, default=0.15)
    parser.add_argument("--image-delay", type=float, default=0.08)
    parser.add_argument("--product-page-delay", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--resume", action="store_true", help="Skip rows/images already saved.")
    parser.add_argument("--force", action="store_true", help="Redownload existing images and refetch raw pages.")
    parser.add_argument("--metadata-only", action="store_true", help="Do not download image files.")
    parser.add_argument("--download-images", action="store_true", help="Download image files.")
    parser.add_argument("--enrich-pages", action="store_true", help="Fetch product pages for price/categories/variants.")
    parser.add_argument("--gallery-images", action="store_true", help="Download all gallery images found on product pages.")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--force-lock", action="store_true", help="Remove a stale dataset lock before starting.")
    args = parser.parse_args()

    if not args.metadata_only:
        args.download_images = True

    out_dir = Path(args.output_dir)
    paths = make_dirs(out_dir)
    acquire_lock(paths["lock"], force=args.force_lock)
    session = build_session()
    started_at = datetime.now(UTC)

    seen_product_ids = load_seen_jsonl(paths["catalog"], "dataset_product_id") if args.resume else set()
    seen_image_ids = load_seen_jsonl(paths["image_manifest"], "image_id") if args.resume else set()

    manifest = {
        "dataset_name": "lereve_products_public_api",
        "source_site": BASE_URL,
        "source_product_api": API_URL,
        "robots_txt_checked": f"{BASE_URL}/robots.txt",
        "output_dir": str(out_dir),
        "created_or_resumed_at": started_at.isoformat(),
        "mode": {
            "download_images": bool(args.download_images),
            "metadata_only": bool(args.metadata_only),
            "enrich_pages": bool(args.enrich_pages),
            "gallery_images": bool(args.gallery_images),
            "resume": bool(args.resume),
        },
        "license_and_usage_note": (
            "This dataset is assembled from public Le Reve product pages/API for local research and prototyping. "
            "Images and product text likely remain copyrighted by Le Reve or its suppliers. Do not redistribute, "
            "publish the raw images, or use commercially without permission from the rights owner."
        ),
    }
    write_json(paths["manifest"], manifest)
    ensure_readme(out_dir, manifest)

    catalog_handle = paths["catalog"].open("a", encoding="utf-8")
    image_handle = paths["image_manifest"].open("a", encoding="utf-8")
    failure_handle = paths["failures"].open("a", encoding="utf-8")
    label_csv_exists = paths["labels"].exists() and paths["labels"].stat().st_size > 0
    label_handle = paths["labels"].open("a", encoding="utf-8", newline="")
    label_writer = make_label_writer(label_handle)
    if not label_csv_exists:
        label_writer.writeheader()

    collected = 0
    new_rows = 0
    new_images = 0
    failures = 0

    try:
        page = args.start_page
        total_pages: int | None = None
        while True:
            if args.max_pages and page >= args.start_page + args.max_pages:
                break
            if total_pages and page > total_pages:
                break
            if args.max_products and collected >= args.max_products:
                break

            try:
                page_payload, headers = fetch_product_page(
                    session=session,
                    page=page,
                    per_page=args.per_page,
                    timeout=args.timeout,
                    raw_dir=paths["raw_api"],
                    force=args.force,
                )
                if total_pages is None:
                    total_pages = parse_int(headers.get("x-wp-totalpages")) or page
                    total_products = parse_int(headers.get("x-wp-total"))
                    print(f"Le Reve public API reports {total_products} products across {total_pages} pages.")
                if not page_payload:
                    break
            except Exception as exc:  # noqa: BLE001 - scrape failures must be auditable.
                failures += 1
                write_jsonl_row(failure_handle, {"stage": "api_page", "page": page, "error": str(exc)})
                if args.stop_on_error:
                    raise
                page += 1
                time.sleep(args.page_delay)
                continue

            for api_item in page_payload:
                if args.max_products and collected >= args.max_products:
                    break
                collected += 1
                product_id = make_product_id(api_item)
                if args.resume and product_id in seen_product_ids:
                    continue

                rich = {}
                if args.enrich_pages:
                    try:
                        rich = fetch_and_parse_product_page(
                            session=session,
                            api_item=api_item,
                            raw_dir=paths["raw_products"],
                            timeout=args.timeout,
                            force=args.force,
                        )
                    except Exception as exc:  # noqa: BLE001 - keep going and log the broken product.
                        failures += 1
                        write_jsonl_row(
                            failure_handle,
                            {
                                "stage": "product_page_enrichment",
                                "dataset_product_id": product_id,
                                "source_product_url": api_item.get("link"),
                                "error": str(exc),
                            },
                        )
                        if args.stop_on_error:
                            raise
                    time.sleep(args.product_page_delay)

                catalog_row = normalize_product(api_item, rich)
                image_urls = discover_image_urls(api_item, rich, include_gallery=args.gallery_images)
                image_rows: list[dict[str, Any]] = []
                if args.download_images:
                    for image_index, image_url in enumerate(image_urls, start=1):
                        image_id = make_image_id(product_id, image_index, image_url)
                        if args.resume and image_id in seen_image_ids:
                            known_path = local_image_path(paths["images"], product_id, image_id, image_url)
                            if known_path.exists():
                                image_rows.append(
                                    {
                                        "image_id": image_id,
                                        "product_id": product_id,
                                        "role": "primary" if image_index == 1 else f"gallery_{image_index}",
                                        "source_url": image_url,
                                        "local_path": str(known_path),
                                        "relative_path": str(known_path.relative_to(out_dir)),
                                        "image_kind": "source_site_product_photo",
                                        "already_present": True,
                                    }
                                )
                                continue
                        try:
                            image_row = download_image(
                                session=session,
                                product_id=product_id,
                                image_id=image_id,
                                image_url=image_url,
                                image_index=image_index,
                                out_dir=out_dir,
                                images_root=paths["images"],
                                timeout=args.timeout,
                                force=args.force,
                            )
                            image_rows.append(image_row)
                            write_jsonl_row(image_handle, image_row)
                            new_images += 1
                        except Exception as exc:  # noqa: BLE001
                            failures += 1
                            write_jsonl_row(
                                failure_handle,
                                {
                                    "stage": "image_download",
                                    "dataset_product_id": product_id,
                                    "image_url": image_url,
                                    "error": str(exc),
                                },
                            )
                            if args.stop_on_error:
                                raise
                        time.sleep(args.image_delay)

                catalog_row["images"] = image_rows
                catalog_row["image_count"] = len(image_rows)
                catalog_row["source_image_count"] = len(image_urls)
                write_jsonl_row(catalog_handle, catalog_row)
                label_writer.writerow(flatten_label_row(catalog_row))
                new_rows += 1
                seen_product_ids.add(product_id)

                if new_rows % 25 == 0:
                    flush_all(catalog_handle, image_handle, failure_handle, label_handle)
                    write_state(
                        paths["state"],
                        page=page,
                        collected=collected,
                        new_rows=new_rows,
                        new_images=new_images,
                        failures=failures,
                        total_pages=total_pages,
                    )
                    print(
                        f"page={page} collected={collected} new_products={new_rows} "
                        f"new_images={new_images} failures={failures}"
                    )

            page += 1
            time.sleep(args.page_delay)

    finally:
        flush_all(catalog_handle, image_handle, failure_handle, label_handle)
        catalog_handle.close()
        image_handle.close()
        failure_handle.close()
        label_handle.close()

    finished_at = datetime.now(UTC)
    final_state = {
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "products_seen_this_run": collected,
        "new_products_written_this_run": new_rows,
        "new_images_downloaded_this_run": new_images,
        "failures_this_run": failures,
        "catalog_rows_total": count_lines(paths["catalog"]),
        "image_rows_total": count_lines(paths["image_manifest"]),
        "failure_rows_total": count_lines(paths["failures"]),
        "output_dir": str(out_dir),
    }
    write_state(paths["state"], **final_state)
    update_manifest(paths["manifest"], final_state)
    ensure_readme(out_dir, {**manifest, **final_state})
    print(json.dumps(final_state, indent=2, ensure_ascii=False))
    return 0


def make_dirs(out_dir: Path) -> dict[str, Path]:
    paths = {
        "root": out_dir,
        "images": out_dir / "images",
        "raw": out_dir / "raw",
        "raw_api": out_dir / "raw" / "wp_product_pages",
        "raw_products": out_dir / "raw" / "product_pages",
        "logs": out_dir / "logs",
        "catalog": out_dir / "catalog.jsonl",
        "image_manifest": out_dir / "image_manifest.jsonl",
        "labels": out_dir / "labels.csv",
        "failures": out_dir / "failures.jsonl",
        "manifest": out_dir / "manifest.json",
        "state": out_dir / "state.json",
        "lock": out_dir / "download.lock",
    }
    for key, path in paths.items():
        if key in {"catalog", "image_manifest", "labels", "failures", "manifest", "state", "lock"}:
            continue
        path.mkdir(parents=True, exist_ok=True)
    return paths


def acquire_lock(lock_path: Path, force: bool) -> None:
    if lock_path.exists():
        raw = lock_path.read_text(encoding="utf-8", errors="ignore").strip()
        pid = parse_int(raw)
        if pid and Path(f"/proc/{pid}").exists() and not force:
            raise SystemExit(
                f"Dataset lock is active at {lock_path} for PID {pid}. "
                "Stop that process or use --force-lock only if the lock is stale."
            )
        lock_path.unlink(missing_ok=True)

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SystemExit(f"Dataset lock already exists: {lock_path}") from exc

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n{datetime.now(UTC).isoformat()}\n")
    atexit.register(release_lock, lock_path, os.getpid())


def release_lock(lock_path: Path, pid: int) -> None:
    try:
        raw = lock_path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return
    if raw.startswith(str(pid)):
        lock_path.unlink(missing_ok=True)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; BanglaTaxRAGDatasetBuilder/1.0; "
                "local research dataset; respectful rate limited)"
            ),
            "Accept": "application/json,text/html,image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": BASE_URL,
        }
    )
    return session


def fetch_product_page(
    session: requests.Session,
    page: int,
    per_page: int,
    timeout: float,
    raw_dir: Path,
    force: bool,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    raw_path = raw_dir / f"page_{page:04d}.json"
    header_path = raw_dir / f"page_{page:04d}.headers.json"
    if raw_path.exists() and header_path.exists() and not force:
        return json.loads(raw_path.read_text(encoding="utf-8")), json.loads(header_path.read_text(encoding="utf-8"))

    response = session.get(
        API_URL,
        params={"per_page": per_page, "page": page, "_fields": API_FIELDS},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    headers = {key.lower(): value for key, value in response.headers.items()}
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    header_path.write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload, headers


def fetch_and_parse_product_page(
    session: requests.Session,
    api_item: dict[str, Any],
    raw_dir: Path,
    timeout: float,
    force: bool,
) -> dict[str, Any]:
    product_id = make_product_id(api_item)
    raw_path = raw_dir / f"{product_id}.html"
    if raw_path.exists() and not force:
        page_html = raw_path.read_text(encoding="utf-8")
    else:
        response = session.get(api_item["link"], timeout=timeout)
        response.raise_for_status()
        page_html = response.text
        raw_path.write_text(page_html, encoding="utf-8")
    return parse_rich_product_page(page_html)


def parse_rich_product_page(page_html: str) -> dict[str, Any]:
    soup = BeautifulSoup(page_html, "html.parser")
    table_attributes = parse_details_table(soup)
    product_obj, variations = extract_next_product_payload(page_html)

    rich: dict[str, Any] = {
        "details_table": table_attributes,
        "attributes": normalize_attribute_list(product_obj.get("attributes", [])) if product_obj else table_attributes,
        "variations": variations,
    }
    if product_obj:
        rich.update(
            {
                "sku": product_obj.get("sku"),
                "regular_price_bdt": parse_price(product_obj.get("regular_price")),
                "sale_price_bdt": parse_price(product_obj.get("sale_price")),
                "categories": product_obj.get("categories") or [],
                "gallery_image_urls": [img.get("src") for img in product_obj.get("images", []) if img.get("src")],
                "raw_product_type": product_obj.get("type"),
            }
        )
    price_el = soup.select_one(".product-details-area .price .amount")
    if price_el and rich.get("sale_price_bdt") is None:
        rich["sale_price_bdt"] = parse_price(price_el.get_text(" ", strip=True))
    return rich


def parse_details_table(soup: BeautifulSoup) -> dict[str, list[str]]:
    attributes: dict[str, list[str]] = {}
    for row in soup.select(".details-table .d-flex"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("span")]
        if len(cells) >= 2 and cells[0]:
            attributes[normalize_key(cells[0])] = [item.strip() for item in cells[1].split(",") if item.strip()]
    return attributes


def extract_next_product_payload(page_html: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    decoded = decode_next_flight(page_html)
    product_obj = extract_json_after_key(decoded, '"p":')
    variations = extract_json_after_key(decoded, '"v":')
    return product_obj if isinstance(product_obj, dict) else {}, variations if isinstance(variations, list) else []


def decode_next_flight(page_html: str) -> str:
    chunks: list[str] = []
    for match in re.finditer(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)</script>", page_html, flags=re.DOTALL):
        raw = match.group(1)
        try:
            chunks.append(json.loads(f'"{raw}"'))
        except json.JSONDecodeError:
            chunks.append(raw.encode("utf-8", errors="ignore").decode("unicode_escape", errors="ignore"))
    return "\n".join(chunks)


def extract_json_after_key(text: str, key: str) -> Any:
    search_start = 0
    while True:
        start = text.find(key, search_start)
        if start < 0:
            return None
        value_start = start + len(key)
        while value_start < len(text) and text[value_start].isspace():
            value_start += 1
        search_start = value_start + 1
        if value_start >= len(text) or text[value_start] not in "[{":
            continue
        end = find_balanced_json_end(text, value_start)
        if end <= value_start:
            continue
        try:
            return json.loads(text[value_start:end])
        except json.JSONDecodeError:
            continue


def find_balanced_json_end(text: str, start: int) -> int:
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    stack = [closer]
    in_string = False
    escape = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or char != stack[-1]:
                return -1
            stack.pop()
            if not stack:
                return index + 1
    return -1


def normalize_product(api_item: dict[str, Any], rich: dict[str, Any]) -> dict[str, Any]:
    product_id = make_product_id(api_item)
    name = clean_text(nested_rendered(api_item.get("title")))
    excerpt = clean_html(nested_rendered(api_item.get("excerpt")))
    content = clean_html(nested_rendered(api_item.get("content")))
    yoast = api_item.get("yoast_head_json") or {}
    description = clean_text(yoast.get("description") or excerpt or content)
    labels = derive_labels(name=name, description=description, rich=rich)
    primary_image_url = first_primary_image_url(api_item)
    categories = rich.get("categories") or []
    category_names = [clean_text(item.get("name")) for item in categories if isinstance(item, dict) and item.get("name")]
    attributes = rich.get("attributes") or {}
    variations = normalize_variations(rich.get("variations") or [])
    size_stock = extract_size_stock(variations)

    return {
        "dataset_product_id": product_id,
        "source": "lerevecraze.com",
        "source_product_url": api_item.get("link"),
        "wordpress_id": api_item.get("id"),
        "source_featured_media_id": api_item.get("featured_media"),
        "slug": api_item.get("slug"),
        "sku": rich.get("sku") or (api_item.get("slug") or "").upper(),
        "name": name,
        "brand": "Le Reve",
        "currency": "BDT",
        "price_bdt": rich.get("sale_price_bdt") or rich.get("regular_price_bdt"),
        "regular_price_bdt": rich.get("regular_price_bdt"),
        "sale_price_bdt": rich.get("sale_price_bdt"),
        "status": api_item.get("status"),
        "stock_status": infer_stock_status(variations),
        "description": description,
        "content": content,
        "categories": categories,
        "category_names": category_names,
        "attributes": attributes,
        "variations": variations,
        "size_stock": size_stock,
        "labels": labels,
        "primary_image_url": primary_image_url,
        "source_created_at": api_item.get("date_gmt") or api_item.get("date"),
        "source_modified_at": api_item.get("modified_gmt") or api_item.get("modified"),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "data_quality": {
            "has_primary_image_url": bool(primary_image_url),
            "has_price": bool(rich.get("sale_price_bdt") or rich.get("regular_price_bdt")),
            "has_categories": bool(category_names),
            "has_attributes": bool(attributes),
            "has_variations": bool(variations),
            "metadata_source": "wp_api_plus_product_page" if rich else "wp_api_yoast_primary",
        },
        "source_rights_note": (
            "Images and product text are sourced from lerevecraze.com for local research/prototyping. "
            "Do not redistribute or use commercially without permission from the rights owner."
        ),
    }


def discover_image_urls(api_item: dict[str, Any], rich: dict[str, Any], include_gallery: bool) -> list[str]:
    urls = []
    primary = first_primary_image_url(api_item)
    if primary:
        urls.append(primary)
    if include_gallery:
        urls.extend(rich.get("gallery_image_urls") or [])
    return unique_urls(urls)


def first_primary_image_url(api_item: dict[str, Any]) -> str | None:
    yoast = api_item.get("yoast_head_json") or {}
    images = yoast.get("og_image") or []
    if images and isinstance(images[0], dict):
        return normalize_url(images[0].get("url"))
    return None


def download_image(
    session: requests.Session,
    product_id: str,
    image_id: str,
    image_url: str,
    image_index: int,
    out_dir: Path,
    images_root: Path,
    timeout: float,
    force: bool,
) -> dict[str, Any]:
    local_path = local_image_path(images_root, product_id, image_id, image_url)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if force or not local_path.exists():
        response = session.get(image_url, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type.lower():
            raise ValueError(f"not image content-type: {content_type}")
        local_path.write_bytes(response.content)
    width, height = image_dimensions(local_path)
    return {
        "image_id": image_id,
        "product_id": product_id,
        "role": "primary" if image_index == 1 else f"gallery_{image_index}",
        "source_url": image_url,
        "local_path": str(local_path),
        "relative_path": str(local_path.relative_to(out_dir)),
        "width": width,
        "height": height,
        "file_size_bytes": local_path.stat().st_size,
        "sha256": sha256_file(local_path),
        "image_kind": "source_site_product_photo",
        "downloaded_at": datetime.now(UTC).isoformat(),
    }


def local_image_path(images_root: Path, product_id: str, image_id: str, image_url: str) -> Path:
    ext = Path(urlparse(image_url).path).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        ext = ".jpg"
    return images_root / product_id / f"{image_id}{ext}"


def make_product_id(api_item: dict[str, Any]) -> str:
    slug = slugify(str(api_item.get("slug") or nested_rendered(api_item.get("title")) or "product"))
    return f"lereve_{api_item.get('id')}_{slug}"


def make_image_id(product_id: str, image_index: int, image_url: str) -> str:
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:10]
    role = "primary" if image_index == 1 else f"gallery_{image_index:02d}"
    return f"{product_id}_{role}_{digest}"


def derive_labels(name: str, description: str, rich: dict[str, Any]) -> dict[str, Any]:
    attributes = rich.get("attributes") or {}
    categories = rich.get("categories") or []
    category_names = " ".join(item.get("name", "") for item in categories if isinstance(item, dict))
    text = f"{name} {description} {category_names} {json.dumps(attributes, ensure_ascii=False)}".lower()
    garment_type = first_keyword_label(text, GARMENT_KEYWORDS) or "unknown"
    colors = values_from_attributes(attributes, "color") or keyword_labels(text, COLOR_KEYWORDS)
    fabrics = values_from_attributes(attributes, "fabric") or keyword_labels(text, FABRIC_KEYWORDS)
    sizes = values_from_attributes(attributes, "size")
    styles = keyword_labels(text, STYLE_KEYWORDS)
    department = infer_department(text, garment_type)
    return {
        "department": department,
        "garment_type": garment_type,
        "color_values": colors,
        "color_families": sorted({COLOR_KEYWORDS.get(value.lower(), value.lower()) for value in colors}),
        "fabric_values": fabrics,
        "size_values": sizes,
        "style_keywords": styles,
        "label_source": "source_attributes_plus_heuristics" if rich else "heuristic_from_api_title_excerpt",
    }


def normalize_attribute_list(attributes: list[dict[str, Any]]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for attribute in attributes:
        name = normalize_key(attribute.get("name"))
        options = attribute.get("options") or []
        if name:
            output[name] = [clean_text(str(option)) for option in options if clean_text(str(option))]
    return output


def normalize_variations(variations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for variation in variations:
        attrs = {}
        for attribute in variation.get("attributes") or []:
            attrs[normalize_key(attribute.get("name"))] = clean_text(attribute.get("option"))
        output.append(
            {
                "source_variation_id": variation.get("id"),
                "sku": variation.get("sku"),
                "price_bdt": parse_price(variation.get("price")),
                "regular_price_bdt": parse_price(variation.get("regular_price")),
                "sale_price_bdt": parse_price(variation.get("sale_price")),
                "stock_status": variation.get("stock_status"),
                "attributes": attrs,
            }
        )
    return output


def extract_size_stock(variations: list[dict[str, Any]]) -> dict[str, str]:
    size_stock = {}
    for variation in variations:
        size = (variation.get("attributes") or {}).get("size")
        if size:
            size_stock[size] = variation.get("stock_status") or "unknown"
    return size_stock


def infer_stock_status(variations: list[dict[str, Any]]) -> str | None:
    if not variations:
        return None
    statuses = {variation.get("stock_status") for variation in variations}
    if "instock" in statuses:
        return "instock"
    if "outofstock" in statuses:
        return "outofstock"
    return sorted(status for status in statuses if status)[0] if statuses else None


def values_from_attributes(attributes: dict[str, list[str]], key: str) -> list[str]:
    return [clean_text(value) for value in attributes.get(key, []) if clean_text(value)]


def keyword_labels(text: str, mapping: dict[str, str]) -> list[str]:
    labels = []
    for keyword, label in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", text):
            labels.append(label)
    return sorted(set(labels))


def first_keyword_label(text: str, mapping: dict[str, str]) -> str | None:
    for keyword, label in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", text):
            return label
    return None


def infer_department(text: str, garment_type: str) -> str:
    if "women" in text or garment_type in {"saree", "salwar_kameez", "kameez", "kurti", "tunic", "dress", "gown"}:
        return "women"
    if "men" in text or garment_type in {"shirt", "polo", "panjabi", "fatua", "waistcoat"}:
        return "men"
    if "kid" in text or "boys" in text or "girls" in text:
        return "kids"
    return "unknown"


def flatten_label_row(row: dict[str, Any]) -> dict[str, Any]:
    labels = row.get("labels", {})
    return {
        "dataset_product_id": row.get("dataset_product_id"),
        "wordpress_id": row.get("wordpress_id"),
        "sku": row.get("sku"),
        "name": row.get("name"),
        "brand": row.get("brand"),
        "source_product_url": row.get("source_product_url"),
        "price_bdt": row.get("price_bdt"),
        "stock_status": row.get("stock_status"),
        "department": labels.get("department"),
        "garment_type": labels.get("garment_type"),
        "colors": "|".join(labels.get("color_values") or []),
        "color_families": "|".join(labels.get("color_families") or []),
        "fabrics": "|".join(labels.get("fabric_values") or []),
        "sizes": "|".join(labels.get("size_values") or []),
        "styles": "|".join(labels.get("style_keywords") or []),
        "categories": "|".join(row.get("category_names") or []),
        "image_count": row.get("image_count"),
        "primary_image_url": row.get("primary_image_url"),
        "data_quality": json.dumps(row.get("data_quality") or {}, ensure_ascii=False),
    }


def make_label_writer(handle: Any) -> csv.DictWriter:
    fieldnames = [
        "dataset_product_id",
        "wordpress_id",
        "sku",
        "name",
        "brand",
        "source_product_url",
        "price_bdt",
        "stock_status",
        "department",
        "garment_type",
        "colors",
        "color_families",
        "fabrics",
        "sizes",
        "styles",
        "categories",
        "image_count",
        "primary_image_url",
        "data_quality",
    ]
    return csv.DictWriter(handle, fieldnames=fieldnames)


def load_seen_jsonl(path: Path, id_field: str) -> set[str]:
    seen = set()
    if not path.exists():
        return seen
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get(id_field):
                seen.add(str(item[id_field]))
    return seen


def write_jsonl_row(handle: Any, row: dict[str, Any]) -> None:
    handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_state(path: Path, **state: Any) -> None:
    state["updated_at"] = datetime.now(UTC).isoformat()
    write_json(path, state)


def update_manifest(path: Path, update: dict[str, Any]) -> None:
    manifest = {}
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(update)
    write_json(path, manifest)


def flush_all(*handles: Any) -> None:
    for handle in handles:
        handle.flush()


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def ensure_readme(out_dir: Path, manifest: dict[str, Any]) -> None:
    readme = f"""# Le Reve Product Dataset

This dataset was built from public Le Reve product metadata and images for local image-search research.

## Contents

- `catalog.jsonl`: normalized product records.
- `image_manifest.jsonl`: one row per downloaded image.
- `labels.csv`: quick spreadsheet-friendly labels.
- `failures.jsonl`: failed page/image requests for audit.
- `state.json`: latest run progress.
- `manifest.json`: dataset build metadata.
- `raw/wp_product_pages/`: cached public API pages.
- `raw/product_pages/`: cached product pages when `--enrich-pages` is used.
- `images/`: downloaded product images grouped by product id.

## Current Mode

```json
{json.dumps(manifest.get("mode", {}), indent=2)}
```

## Usage Warning

{manifest.get("license_and_usage_note", "")}

## Recommended Next Step

For production-quality research labels, manually verify a subset of:

- exact product identity
- same-design variants
- category
- color
- stock/size status
- whether the image is a product photo or only a reference/supplier photo
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def nested_rendered(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("rendered") or "")
    return str(value or "")


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean_text(value).lower()).strip("_")


def normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    return urljoin(BASE_URL, html.unescape(value).replace("\\/", "/").strip())


def unique_urls(urls: list[str | None]) -> list[str]:
    seen = set()
    output = []
    for url in urls:
        normalized = normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "product"


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def parse_price(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    normalized = translate_bengali_digits(str(value)).replace("৳", "").replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", normalized)
    return float(match.group(0)) if match else None


def translate_bengali_digits(text: str) -> str:
    return text.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))


def image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        return image.size


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
