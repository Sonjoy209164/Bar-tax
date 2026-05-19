from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryImageAsset, InventoryItemRecord  # noqa: E402
from app.inventory.clip_matcher import (  # noqa: E402
    EMBEDDING_VERSION,
    CLIPImageMatcher,
    _cosine,
    _encode_image_source,
    embedding_metadata,
)


DEFAULT_DATASET_ROOT = Path("/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich")
DEFAULT_CATALOG_OUT = ROOT / "data" / "inventory" / "lereve_clip_pilot_catalog.jsonl"
DEFAULT_EVAL_OUT = ROOT / "evaluation" / "lereve_clip_pilot_exact_eval.jsonl"
DEFAULT_CACHE_PATH = ROOT / "data" / "inventory" / "lereve_clip_pilot_vectors.json"
DEFAULT_OUT_DIR = ROOT / "results"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a 100-query Le Reve pilot and run a raw CLIP-only exact-product retrieval baseline. "
            "The query image is held out from the searchable catalog image to avoid a fake same-file score."
        )
    )
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--catalog-out", default=str(DEFAULT_CATALOG_OUT))
    parser.add_argument("--eval-out", default=str(DEFAULT_EVAL_OUT))
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--force-cache", action="store_true")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    catalog_source = dataset_root / "catalog.jsonl"
    if not catalog_source.exists():
        raise SystemExit(f"Missing Le Reve catalog: {catalog_source}")

    selected = select_pilot_products(catalog_source, limit=args.limit)
    if len(selected) < args.limit:
        raise SystemExit(f"Only found {len(selected)} usable products with 2+ local images; wanted {args.limit}.")

    catalog = build_bot_catalog(selected)
    cases = build_eval_cases(selected)
    write_jsonl(Path(args.catalog_out), [item.model_dump() for item in catalog.values()])
    write_jsonl(Path(args.eval_out), cases)

    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    started = perf_counter()
    baseline = run_clip_baseline(
        catalog=catalog,
        cases=cases,
        cache_path=Path(args.cache_path),
        force_cache=args.force_cache,
    )
    latency_ms = (perf_counter() - started) * 1000

    payload = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_root": str(dataset_root),
        "catalog_out": relative_or_abs(Path(args.catalog_out)),
        "eval_out": relative_or_abs(Path(args.eval_out)),
        "cache_path": relative_or_abs(Path(args.cache_path)),
        "method": "clip_only_rgb_cosine",
        "model": embedding_metadata(),
        "selection": {
            "products": len(catalog),
            "query_images": len(cases),
            "policy": "round-robin by garment_type; catalog image != query image",
        },
        "latency_ms": round(latency_ms, 2),
        **baseline,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"lereve_clip{len(cases)}_clip_baseline_{run_id}.json"
    md_path = out_dir / f"lereve_clip{len(cases)}_clip_baseline_{run_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    metrics = payload["metrics"]
    print("Le Reve CLIP-only baseline complete")
    print(f"  Catalog: {relative_or_abs(Path(args.catalog_out))}")
    print(f"  Eval:    {relative_or_abs(Path(args.eval_out))}")
    print(f"  JSON:    {json_path}")
    print(f"  MD:      {md_path}")
    print(
        "  Metrics: "
        f"top1={metrics['top1_accuracy']:.1%}, "
        f"top3={metrics['top3_recall']:.1%}, "
        f"top5={metrics['top5_recall']:.1%}, "
        f"mrr={metrics['mean_reciprocal_rank']:.3f}, "
        f"wrong_category_top1={metrics['wrong_category_top1_rate']:.1%}"
    )
    return 0


def select_pilot_products(catalog_path: Path, *, limit: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        images = usable_images(row)
        if len(images) < 2:
            continue
        labels = row.get("labels") or {}
        garment_type = str(labels.get("garment_type") or primary_category(row) or "unknown").casefold()
        row["_catalog_image"] = choose_catalog_image(images)
        row["_query_image"] = choose_query_image(images, row["_catalog_image"])
        if not row["_query_image"]:
            continue
        buckets[garment_type].append(row)

    for key in buckets:
        buckets[key].sort(key=lambda r: str(r.get("dataset_product_id") or ""))

    selected: list[dict[str, Any]] = []
    keys = sorted(buckets, key=lambda k: (-len(buckets[k]), k))
    index = 0
    while len(selected) < limit and keys:
        progressed = False
        for key in keys:
            rows = buckets[key]
            if index < len(rows):
                selected.append(rows[index])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        index += 1
    return selected[:limit]


def usable_images(row: dict[str, Any]) -> list[dict[str, Any]]:
    images = []
    for image in row.get("images") or []:
        local_path = image.get("local_path")
        if not local_path:
            continue
        path = Path(local_path)
        if not path.exists() or path.stat().st_size <= 0:
            continue
        images.append(image)
    images.sort(key=lambda image: (0 if image.get("role") == "primary" else 1, str(image.get("role") or "")))
    return images


def choose_catalog_image(images: list[dict[str, Any]]) -> dict[str, Any]:
    return next((image for image in images if image.get("role") == "primary"), images[0])


def choose_query_image(images: list[dict[str, Any]], catalog_image: dict[str, Any]) -> dict[str, Any] | None:
    catalog_path = catalog_image.get("local_path")
    for image in images:
        if image.get("local_path") != catalog_path:
            return image
    return None


def build_bot_catalog(rows: list[dict[str, Any]]) -> dict[str, InventoryItemRecord]:
    catalog: dict[str, InventoryItemRecord] = {}
    for row in rows:
        labels = row.get("labels") or {}
        attrs = row.get("attributes") or {}
        category = primary_category(row)
        catalog_image = row["_catalog_image"]
        sizes = labels.get("size_values") or as_list(attrs.get("size"))
        size_stock = {}
        for size, status in (row.get("size_stock") or {}).items():
            size_stock[str(size)] = 1 if str(status).casefold() == "instock" else 0
        if not size_stock:
            size_stock = {str(size): 1 for size in sizes}
        visual_tags = unique_clean(
            [
                category,
                labels.get("department"),
                labels.get("garment_type"),
                *as_list(labels.get("color_values")),
                *as_list(labels.get("color_families")),
                *as_list(labels.get("fabric_values")),
                *as_list(labels.get("style_keywords")),
            ]
        )
        item = InventoryItemRecord(
            product_id=str(row["dataset_product_id"]),
            sku=str(row.get("sku") or row["dataset_product_id"]),
            name=str(row.get("name") or row.get("slug") or row["dataset_product_id"]),
            category=category,
            brand=str(row.get("brand") or "Le Reve"),
            short_description=clean_text(row.get("description"))[:280] or None,
            full_description=clean_text(row.get("description") or row.get("content")) or None,
            price=float(row["price_bdt"]) if row.get("price_bdt") is not None else None,
            currency="BDT",
            stock=1 if str(row.get("stock_status") or "").casefold() == "instock" else 0,
            status=str(row.get("stock_status") or row.get("status") or ""),
            tags=visual_tags,
            attributes={
                "source": "lerevecraze.com",
                "source_product_url": str(row.get("source_product_url") or ""),
                "category_key": str(labels.get("garment_type") or category or ""),
                "department": str(labels.get("department") or ""),
                "garment_type": str(labels.get("garment_type") or ""),
                "color": "|".join(as_list(labels.get("color_values")) or as_list(attrs.get("color"))),
                "color_family": "|".join(as_list(labels.get("color_families"))),
                "fabric": "|".join(as_list(labels.get("fabric_values")) or as_list(attrs.get("fabric"))),
                "sizes": "|".join(str(size) for size in sizes),
                "styles": "|".join(as_list(labels.get("style_keywords"))),
            },
            size_stock=size_stock,
            images=[
                InventoryImageAsset(
                    image_id=str(catalog_image.get("image_id") or f"{row['dataset_product_id']}_primary"),
                    local_path=str(catalog_image["local_path"]),
                    source_url=str(row.get("source_product_url") or ""),
                    source_name="lerevecraze.com",
                    license="internal-company-research",
                    role="primary",
                    kind="product_photo",
                    is_reference=False,
                    visual_tags=visual_tags,
                    width=maybe_int(catalog_image.get("width")),
                    height=maybe_int(catalog_image.get("height")),
                )
            ],
            metadata={
                "wordpress_id": row.get("wordpress_id"),
                "source_product_url": row.get("source_product_url"),
                "query_image_local_path": row["_query_image"].get("local_path"),
                "query_image_id": row["_query_image"].get("image_id"),
                "source_rights_note": row.get("source_rights_note"),
            },
            include_in_rag=True,
            updated_at=str(row.get("source_modified_at") or row.get("retrieved_at") or ""),
        )
        catalog[item.product_id] = item
    return catalog


def build_eval_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = []
    for index, row in enumerate(rows, start=1):
        labels = row.get("labels") or {}
        query_image = row["_query_image"]
        product_id = str(row["dataset_product_id"])
        category = primary_category(row)
        cases.append(
            {
                "case_id": f"lereve_clip{len(rows)}_exact_{index:04d}",
                "task_type": "exact_product_cross_gallery",
                "language": "visual_only",
                "difficulty": "heldout_gallery",
                "image_path": str(query_image["local_path"]),
                "query_image_id": query_image.get("image_id"),
                "indexed_image_id": row["_catalog_image"].get("image_id"),
                "query_text": "",
                "expected_primary_product_id": product_id,
                "expected_target_product_ids": [product_id],
                "expected_category": category,
                "category_hint": labels.get("garment_type") or category,
                "color_hint": first_or_none(labels.get("color_families")) or first_or_none(labels.get("color_values")),
                "source_product_url": row.get("source_product_url"),
                "sku": row.get("sku"),
                "name": row.get("name"),
            }
        )
    return cases


def run_clip_baseline(
    *,
    catalog: dict[str, InventoryItemRecord],
    cases: list[dict[str, Any]],
    cache_path: Path,
    force_cache: bool,
) -> dict[str, Any]:
    if not CLIPImageMatcher.is_available():
        raise SystemExit("CLIP is unavailable. Install transformers, torch, and Pillow, then rerun.")

    cache = {} if force_cache else load_cache(cache_path)
    catalog_vectors: dict[str, list[float]] = {}
    for product_id, item in catalog.items():
        image_path = item.images[0].local_path if item.images else None
        if not image_path:
            continue
        vector = cached_encode(image_path, cache)
        if vector:
            catalog_vectors[product_id] = vector

    if len(catalog_vectors) != len(catalog):
        missing = sorted(set(catalog) - set(catalog_vectors))
        raise SystemExit(f"CLIP failed to encode {len(missing)} catalog images; first missing: {missing[:5]}")

    rows: list[dict[str, Any]] = []
    for case in cases:
        expected = case["expected_primary_product_id"]
        query_vector = cached_encode(case["image_path"], cache)
        if not query_vector:
            rows.append({"case": case, "error": "query_encode_failed", "rank": None, "hits": []})
            continue
        hits = []
        for product_id, vector in catalog_vectors.items():
            item = catalog[product_id]
            score = _cosine(query_vector, vector)
            hits.append(
                {
                    "product_id": product_id,
                    "score": round(score, 6),
                    "sku": item.sku,
                    "name": item.name,
                    "category": item.category,
                    "price": item.price,
                    "source_product_url": item.metadata.get("source_product_url"),
                }
            )
        hits.sort(key=lambda hit: -float(hit["score"]))
        rank = next((i for i, hit in enumerate(hits, start=1) if hit["product_id"] == expected), None)
        top1 = hits[0] if hits else None
        rows.append(
            {
                "case": case,
                "expected_product_id": expected,
                "rank": rank,
                "top1_product_id": top1.get("product_id") if top1 else None,
                "top1_score": top1.get("score") if top1 else None,
                "top1_same_category": bool(top1 and same_category(case.get("expected_category"), top1.get("category"))),
                "hits": hits[:10],
            }
        )

    save_cache(cache_path, cache)
    return {
        "metrics": compute_clip_metrics(rows),
        "rows": rows,
    }


def compute_clip_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("rank")]
    total = len(rows)
    ranks = [int(row["rank"]) for row in valid]
    return {
        "cases": total,
        "encoded_cases": len(valid),
        "top1_accuracy": ratio(sum(1 for rank in ranks if rank == 1), total),
        "top3_recall": ratio(sum(1 for rank in ranks if rank <= 3), total),
        "top5_recall": ratio(sum(1 for rank in ranks if rank <= 5), total),
        "top10_recall": ratio(sum(1 for rank in ranks if rank <= 10), total),
        "mean_reciprocal_rank": round(sum(1.0 / rank for rank in ranks) / total, 6) if total else 0.0,
        "mean_rank": round(sum(ranks) / len(ranks), 3) if ranks else None,
        "median_rank": percentile(ranks, 50),
        "p90_rank": percentile(ranks, 90),
        "wrong_category_top1_rate": ratio(
            sum(1 for row in rows if row.get("hits") and not row.get("top1_same_category")),
            total,
        ),
        "query_encode_failures": total - len(valid),
    }


def cached_encode(image_path: str, cache: dict[str, Any]) -> list[float] | None:
    path = Path(image_path)
    stat = path.stat()
    key = f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{EMBEDDING_VERSION}"
    cached = cache.get(key)
    if cached:
        return cached
    vector = _encode_image_source(str(path), grayscale=False)
    if vector:
        cache[key] = vector
    return vector


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if payload.get("embedding_version") != EMBEDDING_VERSION:
        return {}
    return dict(payload.get("vectors") or {})


def save_cache(path: Path, vectors: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "embedding_version": EMBEDDING_VERSION,
        "model": embedding_metadata(),
        "saved_at": datetime.now(UTC).isoformat(),
        "vectors": vectors,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        f"# Le Reve CLIP-Only {payload['selection']['query_images']}-Query Baseline",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Created: `{payload['created_at']}`",
        f"- Dataset: `{payload['dataset_root']}`",
        f"- Catalog: `{payload['catalog_out']}`",
        f"- Eval: `{payload['eval_out']}`",
        f"- Method: `{payload['method']}`",
        f"- Products indexed: **{payload['selection']['products']}**",
        f"- Held-out query images: **{payload['selection']['query_images']}**",
        f"- Latency: **{payload['latency_ms']:.0f} ms**",
        "",
        "## Why This Baseline Is Honest",
        "",
        "The query image is not the same file indexed in the catalog. Each case uses a held-out gallery image and asks CLIP to retrieve the same product from a sibling product image.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Top-1 exact accuracy | {metrics['top1_accuracy']:.1%} |",
        f"| Top-3 exact recall | {metrics['top3_recall']:.1%} |",
        f"| Top-5 exact recall | {metrics['top5_recall']:.1%} |",
        f"| Top-10 exact recall | {metrics['top10_recall']:.1%} |",
        f"| Mean reciprocal rank | {metrics['mean_reciprocal_rank']:.3f} |",
        f"| Mean rank | {metrics['mean_rank']} |",
        f"| Median rank | {metrics['median_rank']} |",
        f"| P90 rank | {metrics['p90_rank']} |",
        f"| Wrong-category top-1 rate | {metrics['wrong_category_top1_rate']:.1%} |",
        f"| Query encode failures | {metrics['query_encode_failures']} |",
        "",
        "## Top Failures",
        "",
    ]
    failures = [row for row in payload["rows"] if row.get("rank") != 1]
    if not failures:
        lines.append("No top-1 failures.")
    else:
        for row in failures[:20]:
            case = row["case"]
            top = row["hits"][0] if row.get("hits") else {}
            lines.extend(
                [
                    f"### {case['case_id']} rank={row.get('rank')}",
                    "",
                    f"- Expected: `{case['expected_primary_product_id']}` / {case.get('name')}",
                    f"- Top-1: `{top.get('product_id')}` / {top.get('name')} / score={top.get('score')}",
                    f"- Query image: `{case['image_path']}`",
                    f"- Product URL: {case.get('source_product_url')}",
                    "",
                ]
            )
    lines.extend(["", "## Sample Successes", ""])
    successes = [row for row in payload["rows"] if row.get("rank") == 1]
    for row in successes[:10]:
        case = row["case"]
        top = row["hits"][0]
        lines.extend(
            [
                f"- `{case['case_id']}`: {case.get('name')} → top-1 score `{top.get('score')}`",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def primary_category(row: dict[str, Any]) -> str:
    labels = row.get("labels") or {}
    if labels.get("garment_type"):
        return str(labels["garment_type"]).replace("_", " ").title()
    names = row.get("category_names") or []
    for name in names:
        if name and str(name).casefold() not in {"eid collection", "men", "women", "men collection", "women collection"}:
            return str(name)
    return str(names[0]) if names else "Fashion"


def clean_text(value: Any) -> str:
    text = str(value or "")
    return " ".join(text.replace("&amp;", "&").split())


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split("|") if part.strip()] or ([value.strip()] if value.strip() else [])
    return [str(value)]


def first_or_none(value: Any) -> str | None:
    values = as_list(value)
    return values[0] if values else None


def unique_clean(values: list[Any]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        for entry in as_list(value):
            cleaned = clean_text(entry)
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
    return out


def maybe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def same_category(expected: Any, actual: Any) -> bool:
    if not expected or not actual:
        return False
    return str(expected).casefold() == str(actual).casefold()


def ratio(num: int, denom: int) -> float:
    return round(num / denom, 6) if denom else 0.0


def percentile(values: list[int], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100) * len(ordered)) - 1))
    return float(ordered[index])


def relative_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
