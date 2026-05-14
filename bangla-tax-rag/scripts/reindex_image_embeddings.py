from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryItemRecord
from app.inventory.image_index import build_image_index, image_index_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local image-search index manifest.")
    parser.add_argument("--catalog", default="data/inventory/catalog.jsonl")
    parser.add_argument("--index-path", default="data/inventory/image_index.jsonl")
    parser.add_argument("--force", action="store_true", help="Reprocess all image assets even if unchanged.")
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Only preprocess and audit images; do not load CLIP or create embedding checksums.",
    )
    args = parser.parse_args()

    catalog = load_catalog(Path(args.catalog))
    records = build_image_index(
        catalog,
        index_path=args.index_path,
        force=args.force,
        include_embeddings=not args.skip_embeddings,
    )
    status = image_index_status(catalog, index_path=args.index_path)

    print(f"status: {status.status}")
    print(f"catalog_count: {status.catalog_count}")
    print(f"image_asset_count: {status.image_asset_count}")
    print(f"indexed_count: {status.indexed_count}")
    print(f"rebuilt_count: {len(records)}")
    print(f"ready: {status.ready}")
    print(f"index_path: {status.index_path}")
    print(f"model_available: {status.model_available}")
    if status.missing_product_ids:
        print("missing_product_ids:")
        for product_id in status.missing_product_ids[:50]:
            print(f"  - {product_id}")
    if status.stale_product_ids:
        print("stale_product_ids:")
        for product_id in status.stale_product_ids[:50]:
            print(f"  - {product_id}")
    return 0 if status.ready else 1


def load_catalog(path: Path) -> dict[str, InventoryItemRecord]:
    items: dict[str, InventoryItemRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = InventoryItemRecord.model_validate_json(stripped)
        items[item.product_id] = item
    return items


if __name__ == "__main__":
    raise SystemExit(main())
