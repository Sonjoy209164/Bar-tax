# Inventory Image Schema

This project now treats product images as first-class catalog data instead of hiding them inside `metadata`.

## Why

Image search needs trustworthy visual ground truth:

```text
customer screenshot
→ image encoder
→ catalog image vectors
→ product metadata filters
→ ranked similar products
→ grounded answer and product cards
```

If a product has no image, the system can still fall back to text/metadata matching, but visual search is weaker.

## Product Image Field

Each `InventoryItemRecord` can include:

```json
"images": [
  {
    "image_id": "saree-jmd-lotus-red-reference-1",
    "url": "https://...",
    "local_path": null,
    "source_url": "https://commons.wikimedia.org/wiki/File:...",
    "source_name": "Wikimedia Commons",
    "license": "CC BY-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/3.0",
    "attribution": "Creator name",
    "role": "primary",
    "kind": "reference_photo",
    "is_reference": true,
    "visual_tags": ["saree", "red", "jamdani", "wedding"],
    "width": 2592,
    "height": 1944
  }
]
```

## Field Meaning

- `image_id`: stable ID for this image.
- `url`: direct internet image URL.
- `local_path`: local product photo path, used when the shop owns the photo.
- `source_url`: attribution/review page.
- `source_name`: source system/site.
- `license` and `license_url`: rights information for external images.
- `attribution`: creator/owner credit.
- `role`: `primary`, `alternate`, `detail`, or `reference`.
- `kind`: `product_photo`, `supplier_photo`, `reference_photo`, or `generated`.
- `is_reference`: `true` means this is demo/reference imagery, not the actual SKU photo.
- `visual_tags`: color/category/fabric/pattern hints used as fallback when visual embeddings are unavailable.

## Current Data Policy

The catalog currently uses internet images from Wikimedia Commons as `reference_photo` demo assets.

Important: these are not actual SKU photos. They are acceptable for testing the visual pipeline shape, but production should replace them with:

- shop-owned product photos,
- supplier-authorized images,
- POS/e-commerce image URLs,
- or internally generated product mockups clearly marked as generated.

## Source Manifest

Attribution and license data is saved in:

```text
data/inventory/catalog_image_sources.json
```

## Enrichment Script

Run:

```bash
.venv/bin/python scripts/enrich_catalog_with_internet_images.py
```

The script searches Wikimedia Commons, adds one primary `reference_photo` per product when found, and writes the source manifest.
