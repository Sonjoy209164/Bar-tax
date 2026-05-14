# MVP: Multi-Shop Visual Commerce Bot

This is the later product direction. Do not let it distract the current build loop: right now the priority is one shop, high accuracy, and a reliable screenshot-to-product flow.

## Product Intention

Build a chatbot that small online shop owners can connect to their catalog/Facebook/POS so customers can ask:

- “Is this screenshot item available?”
- “Do you have the same design in another color?”
- “What size is available?”
- “Show me similar products.”
- “Can I order this?”

The bot must answer from the shop’s own catalog and stock, not from general model memory.

## Later Multi-Shop Architecture

```text
Shop Owner
  ↓
Catalog / POS / Facebook Product Import
  ↓
Product Normalizer
  ↓
Image Processor
  ↓
Text + Image Embedding Sync
  ↓
Per-Shop Search Index / Namespace
  ↓
Customer Chatbot
  ↓
Grounded Product Answer
```

## Core Principle

The visual model is only the eye.

```text
Visual model = finds similar-looking catalog images
Catalog/POS = decides stock, price, exact product, variants, policy
```

Never let the bot answer availability from internet/Kaggle/reference data.

## Tenant Model

Each business gets isolated data:

```json
{
  "shop_id": "shop_001",
  "product_id": "p_123",
  "name": "Gold Party Clutch",
  "price": 1850,
  "stock": 2,
  "images": [],
  "attributes": {},
  "source": "facebook|pos|manual"
}
```

Search must always filter by `shop_id`.

## Visual Search Flow

```text
Customer screenshot
  ↓
Preprocess / crop product area
  ↓
Image embedding with CLIP/FashionCLIP/SigLIP
  ↓
Search only this shop's image vectors
  ↓
Merge with text query and metadata filters
  ↓
Rank products
  ↓
Check stock/price/variants in catalog
  ↓
Answer exact/similar/no-match
```

## Match Decision Policy

```text
High score + shop-owned product photo
→ “This looks like [product]. It is available.”

Medium score
→ “I’m not fully sure, but these are the closest matches.”

Low score
→ “I don’t see the exact item. Want similar options?”
```

Reference images must never produce “exact match” language.

## What Each Shop Must Provide

Minimum:

- Product ID
- Product name
- Price
- Stock
- Category
- At least one product image

Better:

- Color
- Size
- Brand
- Variants
- Description
- Tags
- Facebook/Instagram post URL

## Daily Update Model

Do not fine-tune every day.

Daily product update should be:

```text
new product arrives
  ↓
owner/POS uploads product info + images
  ↓
system creates image/text embeddings
  ↓
embeddings are inserted into search index
  ↓
bot can answer immediately
```

Fine-tuning happens later and occasionally, using accumulated feedback.

## MVP Checklist For Later

- [ ] Add `shop_id` to catalog/product records.
- [ ] Add tenant-aware API keys.
- [ ] Add per-shop image upload/import.
- [ ] Add per-shop vector namespace/index.
- [ ] Add Facebook/Instagram product import workflow.
- [ ] Add object storage for images.
- [ ] Add image embedding background worker.
- [ ] Add screenshot upload to customer chat.
- [ ] Add exact/similar/no-match thresholds.
- [ ] Add admin correction screen.
- [ ] Add feedback export for future fine-tuning.
- [ ] Add shop-level policy settings.
- [ ] Add analytics: unmatched screenshots, common requests, conversion.

## Current One-Shop Focus

For now, focus on one shop and make the sub-problem near perfect:

```text
one shop catalog
  ↓
real product images
  ↓
image embeddings
  ↓
customer screenshot
  ↓
exact/similar/no-match
  ↓
stock-grounded answer
```

Current priority checklist:

- [ ] Replace demo/reference images with real shop product photos.
- [ ] Add 2-5 images per product when possible.
- [ ] Add Facebook screenshot examples mapped to product IDs.
- [ ] Build a small evaluation set: screenshot → expected product ID.
- [ ] Tune exact/similar/no-match thresholds.
- [ ] Improve UI product cards for image matches.
- [ ] Save failed image searches for review.
- [ ] Add owner correction: “this result should be product X.”

## Strategic Warning

The business will fail if the bot confidently says unavailable/available from weak visual evidence. For sellable quality, the product must separate:

```text
exact product match
similar product recommendation
no confident match
```

That distinction is more important than making the bot sound impressive.
