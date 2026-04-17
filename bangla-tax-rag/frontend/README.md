# Inventory RAG Frontend Demo

This is a static demo frontend for testing the inventory chatbot without adding another backend.

It uses:

- `frontend/data/products.json` as the sample ecommerce catalog.
- `POST /inventory/items/upsert` to sync products into the RAG mirror.
- `POST /inventory/business/signals/upsert` to sync operational business signals.
- `POST /inventory/ask` for normal chatbot answers.
- `POST /inventory/agentic/ask` for business/restock reasoning.
- `GET /inventory/chat/trace/{trace_id}` to inspect why an answer behaved the way it did.

## Run

From the `bangla-tax-rag` repo root:

```bash
python3 -m http.server 5173 --directory frontend
```

Open:

```text
http://localhost:5173
```

Do not test from a browser-saved `Inventory RAG Chat Demo.html` file. That is only a snapshot and can keep old JavaScript and old chat messages. Use the local server URL above and hard refresh after code changes.

Use the RAG API base URL:

```text
http://localhost:4893
```

or the live one:

```text
http://marshalmind.codemarshal.com:4893
```

If API key protection is enabled, paste the key into the page. The key is only stored in browser `sessionStorage`.

## Optional Local Config

For faster local testing, create:

```text
frontend/config.local.json
```

using this shape:

```json
{
  "apiBaseUrl": "http://marshalmind.codemarshal.com:4893",
  "apiKey": "your-api-key"
}
```

That file is ignored by git. Keep real API keys out of tracked frontend code.

## Direct Smoke Test

After creating `frontend/config.local.json`, run:

```bash
node frontend/smoke-test.mjs
```

It checks API status, syncs the sample JSON, asks one normal chat question, and asks one agentic business question.
If the deployed API does not expose newer helper endpoints such as business signals or sync status yet, the smoke test skips those steps and still validates catalog chat.

## Best Chat Settings

For product recommendations like "which one should I buy?", use:

```text
Mode: Sales
Reply: Detailed
Path: Agentic
Engine: Auto
```

Use `Engine: Natural` only when the RAG server has a working LLM generation provider. If the response badge still says `deterministic`, the server is falling back to rule-based answers.

The page now keeps recent product context and sends `focused_product_ids` plus `filters.product_ids` when it detects pasted SKUs/product names, so follow-ups like "which one should I buy?" stay scoped to the products currently being discussed.

## Data Format

The product JSON is intentionally shaped for the current RAG API:

```json
{
  "items": [
    {
      "product_id": "watch-trailmark-pro",
      "sku": "WAT-TRM-001",
      "name": "TrailMark Pro Smart Watch",
      "category": "Wearables",
      "brand": "TrailMark",
      "short_description": "Premium smart watch...",
      "full_description": "Best for fitness-focused buyers...",
      "price": 219,
      "currency": "USD",
      "stock": 6,
      "status": "Low Stock",
      "tags": ["watch", "smartwatch"],
      "attributes": {},
      "metadata": {},
      "include_in_rag": true,
      "updated_at": "2026-04-17T09:00:00Z"
    }
  ],
  "business_signals": [
    {
      "product_id": "watch-trailmark-pro",
      "units_sold": 38,
      "order_count": 31,
      "gross_margin_rate": 0.35,
      "inventory_on_hand": 6,
      "supplier_lead_time_days": 18,
      "demand_score": 0.82
    }
  ],
  "test_questions": []
}
```

## Important

This is a direct-to-RAG demo. It is useful for local testing and quick visual QA, but production should still use:

```text
Next.js frontend -> Express backend -> RAG sidecar
```

Do not expose a production RAG API key in a public browser app.
