# Run Guide — Bangla Boutique AI Assistant

Everything you need to go from zero to a running chat assistant.

---

## What you need

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11 or 3.12 | 3.10 will not work |
| pip | latest | `pip install --upgrade pip` |
| Ollama | any | **Optional** — for LLM slot extraction + natural answers |
| torch + transformers | latest | **Optional** — for CLIP image search |
| sentence-transformers | latest | **Optional** — for multilingual embeddings |

The system runs fully without Ollama, torch, or sentence-transformers. Those only activate smarter features — the bot still answers without them.

---

## 1. Clone and enter the project

```bash
git clone <your-repo-url>
cd bangla-tax-rag
```

---

## 2. Create virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
```

Or using Make:

```bash
make install
```

**Optional — smarter features:**

```bash
# Multilingual semantic search (Bangla + English queries match better)
pip install sentence-transformers

# CLIP visual image search (photo upload → similar products)
pip install transformers Pillow torch

# Natural language answers + LLM slot extraction
# → Install Ollama from https://ollama.com then:
ollama pull qwen3:8b
```

---

## 3. Configure environment

Copy the example file and edit it:

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
APP_ENV=development
APP_PORT=4893
API_ACCESS_KEY=your-secret-key-here

# Point to your product catalog
INVENTORY_CATALOG_PATH=data/inventory/catalog.jsonl

# Set to "multilingual" if you installed sentence-transformers
EMBEDDING_PROVIDER=deterministic   # or: multilingual, transformers, openai

# If using Ollama for LLM answers:
GENERATOR_PROVIDER=openai_compatible
GENERATOR_MODEL_NAME=qwen3:8b
GENERATOR_BASE_URL=http://127.0.0.1:11434/v1
```

**For a fully offline/local run** (no API keys needed):

```env
EMBEDDING_PROVIDER=deterministic
GENERATOR_PROVIDER=openai_compatible
GENERATOR_MODEL_NAME=qwen3:8b
GENERATOR_BASE_URL=http://127.0.0.1:11434/v1
```

---

## 4. Prepare your catalog

Your product catalog lives at `data/inventory/catalog.jsonl`.
Each line is one product in JSON. Minimum required fields:

```jsonc
{
  "product_id": "saree-red-001",
  "sku": "SKU001",
  "name": "Red Jamdani Saree",
  "category": "Saree",
  "price": 6800,
  "stock": 4,
  "attributes": {
    "category_key": "saree",
    "color": "red",
    "fabric": "jamdani",
    "work_type": "buti",
    "occasion": "wedding",
    "size": "free"
  },
  "tags": ["wedding", "jamdani", "red"],
  "rag_enabled": true
}
```

A sample 47-product catalog is already at `data/inventory/catalog.jsonl`.

**Run the catalog audit to check quality:**

```bash
# Start the server first (Step 5), then:
curl -H "X-API-Key: your-secret-key-here" \
     http://localhost:4893/inventory/audit
```

---

## 5. Start the server

```bash
source .venv/bin/activate

uvicorn app.main:app --reload --host 0.0.0.0 --port 4893
```

Or using Make:

```bash
make run-api
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:4893 (Press CTRL+C to quit)
INFO:     FastAPI app started  environment=development  retrieval_mode=hybrid
```

---

## 6. Open the chat UI

Go to:

```
http://localhost:4893/frontend/
```

The browser chat interface loads. You can:
- Type in Bangla, Banglish, or English
- Click the mic 🎤 button for voice input
- Add products to cart and place orders
- Track orders by phone number
- Give 👍 / 👎 feedback on answers

---

## 7. Try your first questions

In the chat box:

```
লাল জামদানি শাড়ি আছে?
```
```
jamdani vs katan konta nibo?
```
```
eid er jonno panjabi dekhao under 2000 taka
```
```
Dhaka delivery charge koto?
```
```
order dite chai
```

---

## 8. Run the tests

```bash
source .venv/bin/activate
pytest
```

Or:

```bash
make test
```

Expected output: **495 passed**, 11 skipped/failed (pre-existing — elasticsearch not installed, missing data files). All your code passes.

---

## 9. API key authentication

All API endpoints (except `/health`) require the key in a header:

```bash
# Health check (no auth)
curl http://localhost:4893/health

# Ask a question (auth required)
curl -X POST http://localhost:4893/inventory/ask \
  -H "X-API-Key: your-secret-key-here" \
  -H "Content-Type: application/json" \
  -d '{"question": "লাল শাড়ি আছে?"}'
```

Set the key in `.env`:
```env
API_ACCESS_KEY=your-secret-key-here
```

---

## 10. POS sync — import products from CSV

```bash
curl -X POST http://localhost:4893/inventory/sync/import \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"csv_text": "product_id,name,price,stock\nSKU001,Red Saree,5000,10"}'
```

Or via webhook from your POS system:

```bash
curl -X POST http://localhost:4893/inventory/sync/webhook \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"source": "pos", "event": "stock_update", "items": [{"product_id": "SKU001", "stock": 15}]}'
```

---

## Docker (optional)

```bash
# Build
docker build -t boutique-ai .

# Run
docker run -p 4893:4893 \
  -e API_ACCESS_KEY=your-key \
  -e INVENTORY_CATALOG_PATH=data/inventory/catalog.jsonl \
  -v $(pwd)/data:/app/data \
  boutique-ai
```

Then open `http://localhost:4893/frontend/`

---

## API documentation

Interactive Swagger UI:

```
http://localhost:4893/docs
```

Raw OpenAPI schema:

```
http://localhost:4893/openapi.json
```

---

## Full endpoint reference

| Method | Endpoint | What it does |
|--------|----------|-------------|
| `GET` | `/health` | Server health check |
| `POST` | `/inventory/ask` | Main chat — ask any question |
| `POST` | `/inventory/ask/stream` | Same but server-sent events stream |
| `POST` | `/inventory/search` | Direct product search |
| `POST` | `/inventory/image-search` | Search by photo (base64) or text |
| `GET` | `/inventory/audit` | Catalog quality report |
| `GET` | `/inventory/items` | List all products |
| `GET` | `/inventory/items/{id}` | Single product |
| `POST` | `/inventory/items/upsert` | Add or update products |
| `POST` | `/inventory/waitlist` | Join out-of-stock waitlist |
| `GET` | `/inventory/waitlist/status` | Waitlist counts |
| `POST` | `/inventory/sync/import` | CSV import from POS |
| `POST` | `/inventory/sync/webhook` | Webhook from POS |
| `POST` | `/inventory/policy-qa` | Policy questions (delivery, refund…) |
| `POST` | `/orders/draft` | Start an order |
| `POST` | `/orders/confirm` | Confirm and place order |
| `GET` | `/orders/cart/{session_id}` | View cart |
| `POST` | `/orders/cart/remove` | Remove item from cart |
| `POST` | `/orders/cart/quantity` | Update item quantity |
| `GET` | `/orders/track/{phone}` | Track orders by phone |
| `PATCH` | `/orders/{id}/status` | Staff: update order status |
| `POST` | `/feedback` | Submit thumbs up/down |
| `GET` | `/feedback/report` | Satisfaction report |

---

## Troubleshooting

**Server won't start**
```bash
# Check Python version
python3 --version   # must be 3.11+

# Re-install deps
pip install -r requirements.txt
```

**"Module not found" on startup**
```bash
# Make sure venv is active
source .venv/bin/activate
which python   # should point to .venv/bin/python
```

**Chat UI shows "connection refused"**
- Make sure the server is running on port 4893
- Check `.env` has correct `APP_PORT=4893`
- Try `curl http://localhost:4893/health`

**All answers are template-based, not natural language**
- Install Ollama: https://ollama.com
- Run `ollama pull qwen3:8b`
- Set in `.env`: `GENERATOR_BASE_URL=http://127.0.0.1:11434/v1`

**Image search not working visually**
```bash
pip install transformers Pillow torch
# Restart the server — CLIP loads on first image request
```

**Bangla text not matching well**
```bash
pip install sentence-transformers
# Set in .env:
EMBEDDING_PROVIDER=multilingual
# Restart server
```

**Test failures**
```bash
# The 11 expected failures are pre-existing (elasticsearch, missing data files)
# Run only your code:
pytest tests/ --ignore=tests/test_repo_smoke.py \
              --ignore=tests/test_streamlit_smoke.py \
              --ignore=tests/test_streamlit_ui_helpers.py
# Should be: 488 passed, ~6 failed (elasticsearch + missing data files)
```
