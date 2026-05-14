from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryImageAsset, InventoryItemRecord


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local product photos into the inventory catalog.")
    parser.add_argument("--catalog", default="data/inventory/catalog.jsonl")
    parser.add_argument("--image-root", default="data/inventory/images")
    parser.add_argument("--output", default=None, help="Defaults to rewriting --catalog.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a catalog backup before rewriting.")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    image_root = Path(args.image_root)
    output_path = Path(args.output) if args.output else catalog_path

    items = load_catalog(catalog_path)
    updated = 0
    skipped: list[str] = []
    errors: list[str] = []

    for item in items:
        product_dir = image_root / item.product_id
        if not product_dir.exists():
            skipped.append(item.product_id)
            continue
        try:
            images = build_image_assets(item=item, product_dir=product_dir)
        except Exception as exc:
            errors.append(f"{item.product_id}: {exc}")
            continue
        if images:
            item.images = images
            metadata = dict(item.metadata or {})
            metadata["image_schema_version"] = "inventory-image-v1"
            metadata["image_source_policy"] = "shop_local_product_images"
            item.metadata = metadata
            updated += 1

    print(f"products: {len(items)}")
    print(f"updated_with_images: {updated}")
    print(f"skipped_no_folder: {len(skipped)}")
    print(f"errors: {len(errors)}")
    for error in errors[:20]:
        print(f"ERROR {error}", file=sys.stderr)

    if args.dry_run:
        return 0 if not errors else 1

    if not args.no_backup and catalog_path.exists() and output_path == catalog_path:
        backup_dir = catalog_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        shutil.copy2(catalog_path, backup_dir / f"{catalog_path.stem}_before_image_import_{stamp}{catalog_path.suffix}")

    write_catalog(items, output_path)
    return 0 if not errors else 1


def load_catalog(path: Path) -> list[InventoryItemRecord]:
    return [
        InventoryItemRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_catalog(items: list[InventoryItemRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        "\n".join(item.model_dump_json(exclude_none=True) for item in items) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def build_image_assets(*, item: InventoryItemRecord, product_dir: Path) -> list[InventoryImageAsset]:
    files = sorted(
        path for path in product_dir.iterdir()
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
    )
    if not files:
        return []

    assets: list[InventoryImageAsset] = []
    for index, image_path in enumerate(files, start=1):
        role = infer_role(image_path, index)
        width, height = validate_image(image_path)
        image_id = f"{item.product_id}-{role}-{index}"
        assets.append(
            InventoryImageAsset(
                image_id=image_id,
                local_path=image_path.as_posix(),
                source_name="Local product photo import",
                role=role,
                kind="product_photo",
                is_reference=False,
                visual_tags=visual_tags(item),
                width=width,
                height=height,
            )
        )
    assets.sort(key=lambda image: {"primary": 0, "alternate": 1, "detail": 2, "reference": 3}.get(image.role, 9))
    return assets


def validate_image(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.width < 120 or image.height < 120:
            raise ValueError(f"image too small: {path} {image.width}x{image.height}")
        return image.width, image.height


def infer_role(path: Path, index: int) -> str:
    name = path.stem.casefold()
    if "detail" in name or "pattern" in name or "close" in name:
        return "detail"
    if "side" in name or "alt" in name or "back" in name or "model" in name:
        return "alternate"
    if "primary" in name or "main" in name or index == 1:
        return "primary"
    return "alternate"


def visual_tags(item: InventoryItemRecord) -> list[str]:
    values = [item.category or "", item.brand or "", *item.tags, *[str(v) for v in item.attributes.values() if v]]
    tags: set[str] = set()
    for value in values:
        for part in str(value).replace("/", ",").replace("|", ",").split(","):
            normalized = part.strip().casefold()
            if normalized:
                tags.add(normalized)
    return sorted(tags)[:28]


if __name__ == "__main__":
    raise SystemExit(main())
