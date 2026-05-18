# Full Build Theory — Bangla Boutique Inventory Chatbot

**Project:** Sonjoy Boutique — Production-Grade Customer-Facing Retail Assistant  
**Branch:** Inventory  
**Last Full Build:** 2026-05-09  
**Test Status:** 207/207 passing across 12 suites

---

## Table of Contents

1. [What the System Does](#1-what-the-system-does)
2. [System Boundaries and Runtime Modes](#2-system-boundaries-and-runtime-modes)
3. [Repository Layout](#3-repository-layout)
4. [End-to-End Request Lifecycle](#4-end-to-end-request-lifecycle)
5. [Layer 1 — Frontend (chat.html / chat.js)](#5-layer-1--frontend-chathtmlchatjs)
6. [Layer 2 — API Gateway (main.py + routes)](#6-layer-2--api-gateway-mainpy--routes)
7. [Layer 3 — InventoryService (Orchestrator)](#7-layer-3--inventoryservice-orchestrator)
8. [Layer 4 — Domain Engines](#8-layer-4--domain-engines)
   - [4a. FashionRetailAssistant](#4a-fashionretailassistant)
   - [4b. PolicyQAEngine](#4b-policyqaengine)
   - [4c. OrderWorkflowEngine](#4c-orderworkflowengine)
   - [4d. CustomerProfileManager](#4d-customerprofilemanager)
   - [4e. ImageMatcher](#4e-imagematcher)
   - [4f. POSSyncEngine](#4f-possyncengine)
9. [Data Model — InventoryItemRecord](#9-data-model--inventoryitemrecord)
10. [Data Model — Policy Store](#10-data-model--policy-store)
11. [Persistence Layer](#11-persistence-layer)
12. [Intent Classification and Routing Logic](#12-intent-classification-and-routing-logic)
13. [Language Detection and Normalization](#13-language-detection-and-normalization)
14. [Scoring and Ranking](#14-scoring-and-ranking)
15. [Order Workflow State Machine](#15-order-workflow-state-machine)
16. [Customer Profile Memory Lifecycle](#16-customer-profile-memory-lifecycle)
17. [Image Search Without Real Embeddings](#17-image-search-without-real-embeddings)
18. [POS Sync — Catalog Ingestion Pipeline](#18-pos-sync--catalog-ingestion-pipeline)
19. [API Reference](#19-api-reference)
20. [Test Architecture](#20-test-architecture)
21. [Known Limitations and Production Upgrade Paths](#21-known-limitations-and-production-upgrade-paths)
22. [Running the System](#22-running-the-system)

---

## 1. What the System Does

This is a production-grade **Bangla/Banglish/English boutique retail assistant** that handles the full customer journey from product discovery to order confirmation, grounded strictly in live catalog data.

The system answers six categories of customer interaction:

| Category | Example | Handled By |
|---|---|---|
| Product search | "Navy jamdani saree ache?" | FashionRetailAssistant |
| Styling advice | "Red saree er sathe ki manabe wedding e?" | FashionRetailAssistant (styling mode) |
| Policy questions | "Delivery charge koto outside Dhaka?" | PolicyQAEngine |
| Order placement | "Eta order korte chai" → confirm flow | OrderWorkflowEngine |
| Image-based search | Upload photo → find similar products | ImageMatcher |
| Profile memory | "Size 38 blouse prefer kori" → remembered | CustomerProfileManager |

All six pathways are **deterministic and grounded**: answers come only from catalog metadata and policies.json, never hallucinated. The system runs fully offline (no Ollama/Claude/ES required) in deterministic mode.

---

## 2. System Boundaries and Runtime Modes

### Deterministic Local Mode (Default — Always Works)

```
Browser ──► FastAPI (uvicorn, port 4849)
               ├─ Catalog: data/inventory/catalog.jsonl (JSONL, read-only at runtime)
               ├─ Vectors: data/agentic_store/local_vectors.jsonl (local JSONL embeddings)
               ├─ Orders: data/orders/orders_store.jsonl (append-only)
               ├─ Profiles: data/customer_profiles/profiles_store.jsonl (session-keyed)
               ├─ Policies: data/inventory/policies.json (static config)
               └─ Sync log: data/inventory/sync_audit.jsonl (import audit)
```

No external services, no API keys, no GPU, no network required beyond the local machine.

### Optional Ollama Mode (Natural Language Answers)

Add `INVENTORY_NATURAL_ANSWERS_ENABLED=true` and a generator config. The deterministic engine provides product selection; Ollama generates natural language phrasing. If Ollama times out or fails, the system falls back to deterministic answers — so availability is always guaranteed.

### Optional Elasticsearch Mode

Set `VECTOR_DB=elasticsearch` for production-scale vector search. Compatible with the same catalog JSONL format; sync rebuilds push embeddings to ES instead of the local JSONL file.

---

## 3. Repository Layout

```
bangla-tax-rag/
├── app/
│   ├── main.py                        ← FastAPI app bootstrap, router wiring
│   ├── core/
│   │   └── schemas.py                 ← All Pydantic v2 models (500+ lines)
│   ├── api/
│   │   ├── routes_inventory.py        ← /inventory/* endpoints
│   │   ├── routes_orders.py           ← /orders/* endpoints
│   │   ├── routes_health.py
│   │   ├── routes_ingest.py
│   │   ├── routes_eval.py
│   │   ├── routes_query.py
│   │   └── routes_agentic.py
│   ├── inventory/
│   │   ├── fashion_retail.py          ← Core rules-based fashion assistant (~900 lines)
│   │   ├── policy_qa.py               ← Delivery/payment/refund QA engine
│   │   ├── order_workflow.py          ← Cart → draft → confirm state machine
│   │   ├── customer_profile.py        ← Session preference memory
│   │   ├── image_matcher.py           ← Metadata-based visual similarity
│   │   ├── pos_sync.py                ← CSV/webhook catalog sync engine
│   │   ├── memory.py                  ← Conversation context resolution
│   │   └── __init__.py                ← Package exports
│   └── services/
│       └── inventory_service.py       ← Main orchestration layer
├── data/
│   ├── inventory/
│   │   ├── catalog.jsonl              ← Product catalog (JSONL, source of truth)
│   │   ├── policies.json              ← Shop policies (delivery/payment/refund)
│   │   └── sync_audit.jsonl           ← POS import history
│   ├── orders/
│   │   └── orders_store.jsonl         ← Confirmed orders (append-only)
│   ├── customer_profiles/
│   │   └── profiles_store.jsonl       ← Session preference memory
│   └── agentic_store/
│       └── local_vectors.jsonl        ← Local vector embeddings (deterministic)
├── frontend/
│   ├── chat.html                      ← Single-page chat UI
│   └── chat.js                        ← Client state machine (~500 lines)
├── tests/
│   ├── test_policy_qa.py              ← 14 tests
│   ├── test_order_workflow.py         ← 17 tests
│   ├── test_customer_profile_memory.py ← 13 tests
│   ├── test_image_matching.py         ← 12 tests
│   ├── test_pos_sync.py               ← 12 tests
│   ├── test_styling_advice.py         ← 8 tests
│   ├── test_deep_bangla_banglish_conversation.py ← 13 tests
│   ├── test_large_multibrand_catalog.py ← 12 tests
│   ├── test_boutique_retail_catalog.py ← 12 tests (pre-existing)
│   ├── test_fashion_retail.py         ← 18 tests (pre-existing)
│   ├── test_inventory_intelligence.py ← 18 tests (pre-existing)
│   └── test_inventory_api.py          ← 61 tests (pre-existing)
└── evaluation/
    └── boutique_inventory_multilingual_qa_set.md
```

---

## 4. End-to-End Request Lifecycle

This is the full path of a customer message from browser keystroke to displayed answer.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                                       │
│                                                                                │
│  User types: "navy katan saree er sathe wedding e ki nibo?"                    │
│  → sendMessage() called                                                         │
│  → POST /inventory/ask                                                          │
│    { question, conversation_history[-8], focused_product_ids, answer_engine }  │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  app/api/routes_inventory.py :: ask()                                          │
│                                                                                │
│  - Validates API key                                                            │
│  - Parses InventoryAskRequest                                                   │
│  - Calls inventory_service.ask(request)                                         │
│  - Returns InventoryAskResponse (or SSE stream for /ask-stream)                 │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  app/services/inventory_service.py :: InventoryService.ask()                   │
│                                                                                │
│  STEP 1: Resolve conversation memory                                            │
│    memory.py resolves pronoun references:                                       │
│    "eta" / "same design" → last_primary_product_id from history                 │
│                                                                                │
│  STEP 2: Early intercept — Policy QA                                            │
│    is_policy_question(text)?                                                    │
│    YES → PolicyQAEngine.answer() → return immediately, skip product search     │
│    NO  → continue                                                               │
│                                                                                │
│  STEP 3: Load catalog                                                           │
│    Read data/inventory/catalog.jsonl → dict[product_id → InventoryItemRecord]  │
│                                                                                │
│  STEP 4: Build search filters                                                   │
│    From request.focused_product_ids, conversation context, explicit filters     │
│                                                                                │
│  STEP 5: Fashion retail handler                                                 │
│    FashionRetailAssistant.answer(question, catalog, filters)                    │
│    → Returns FashionRetailOutcome or None                                       │
│                                                                                │
│  STEP 6: Fallback — Generic RAG                                                 │
│    If fashion retail returned None: vector search on local_vectors.jsonl        │
│                                                                                │
│  STEP 7: Build response                                                         │
│    Construct InventoryAskResponse with answer, product_ids, confidence, plan    │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  app/inventory/fashion_retail.py :: FashionRetailAssistant.answer()            │
│                                                                                │
│  A. normalize_fashion_text(question)  — Bangla digits, special chars          │
│  B. extract_slots() — regex extraction of:                                     │
│     color, fabric, size, budget, occasion, brand, design_id, language          │
│  C. should_handle() — Is this a fashion domain question?                       │
│     If False → return None (pass to RAG)                                       │
│  D. _classify_intent() — Pick one of:                                          │
│     fashion_styling_advice, fashion_variant_color, fashion_size_availability,  │
│     fashion_accessory_match, fashion_search                                    │
│  E. Route to handler:                                                           │
│     styling_advice → _answer_styling_advice()                                  │
│     variant_color  → _answer_variant_color()                                   │
│     size_avail     → _answer_size_availability()                               │
│     accessory      → _answer_accessory_match()                                 │
│     search         → _answer_fashion_search()                                  │
│  F. Return FashionRetailOutcome(answer, product_ids, confidence, ...)          │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Back in InventoryService: Wrap into InventoryAskResponse                      │
│  → trace_id, answer, confidence_score, recommended_product_ids, plan          │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  BROWSER: renderMessage() + renderMeta()                                       │
│  → Display answer text                                                          │
│  → Append metadata line: "intent: fashion_styling_advice · lang: banglish"    │
│  → Update state.focusedProductIds for follow-up turn                           │
│  → detectOrderState() → show/hide order confirm bar if needed                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Layer 1 — Frontend (chat.html / chat.js)

### HTML Structure

The UI is a single-page app (`frontend/chat.html`) with these regions:

```
┌─────────────────────────────────────────────────┐
│  Topbar: "Sonjoy Boutique"  ● Connected          │
├─────────────────────────────────────────────────┤
│                                                   │
│  [assistant] Welcome message                      │
│  [user]     Navy jamdani ache?                    │
│  [assistant] Found 3 matches: ...                 │
│  [meta]     intent: fashion_search · lang: bangla │
│                                                   │
├─────────────────────────────────────────────────┤
│  ⚠ Order in progress: Lotus Jamdani x1 — BDT 6800 │  ← #orderStatusBar (yellow)
│  ✅ Confirm Order  |  ✕ Cancel                    │  ← #orderConfirmBar (green)
├─────────────────────────────────────────────────┤
│  Quick chips: "jamdani ache?" "delivery charge?" │
│  [📎 image preview]  [× clear]                   │
│  ┌──────────────────────────────────────────┐    │
│  │ Type your message...             [Send]  │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### JavaScript State Machine

`chat.js` maintains a global `state` object across turns:

```javascript
state = {
  apiBaseUrl: "http://127.0.0.1:4849",
  apiKey: "dev-key",
  conversation: [],               // last N InventoryConversationTurn objects
  focusedProductIds: [],          // from last answer — passed to next request
  lastAnswerPlan: null,           // slot data from last turn
  busy: false,                    // prevents double-submit
  sessionId: "sess-xxxx",         // stable for the browser session
  orderActive: false,             // order status bar visibility
  awaitingOrderConfirm: false,    // confirm/cancel bar visibility
  pendingImageB64: null,          // base64 of uploaded image
  pendingImageName: null,
}
```

### Key Functions

**`sendMessage(text)`** — Main chat send path
1. Appends user message to `state.conversation`
2. Builds `InventoryAskRequest` payload with last 8 turns, focused product IDs, last plan
3. POSTs to `/inventory/ask`
4. On response: renders answer + metadata, updates `focusedProductIds`, calls `detectOrderState()`

**`sendImageSearch(queryText)`** — Image upload path
1. Reads `state.pendingImageB64` (FileReader base64)
2. POSTs to `/inventory/image-search` with `{image_b64, query_text, top_k: 5}`
3. Renders match results with similarity reasons
4. Clears pending image

**`detectOrderState(userText, botAnswer)`** — Order UI wiring
- Shows yellow status bar when user message contains order phrases: "order korte", "eta nibo", "book kore", "checkout", "kinbo"
- Shows green confirm/cancel bar when bot answer contains "confirm" or "order summary"
- Hides both bars when answer contains "confirmed" or "cancelled"

**`cancelOrder()`**
- Calls `DELETE /orders/cancel/{sessionId}`
- Hides both order bars

**`renderMeta(node, response)`**
- Appends to each assistant message: `intent · language · item count · product IDs`
- Useful for debugging and testing

### Multi-Turn Context Passing

Each request carries:
- `conversation_history`: last 8 turns (user + assistant pairs)
- `focused_product_ids`: recommended + cross_sell IDs from the previous answer
- `last_answer_plan`: the slot data (intent, color, fabric, etc.) extracted last turn

This is how "same design blue ache?" resolves to the correct product: `focused_product_ids` pins the design, and the new question overlays the color slot.

---

## 6. Layer 2 — API Gateway (main.py + routes)

### Application Bootstrap (app/main.py)

`main.py` initializes FastAPI with:

- **Lifespan handler**: Logs startup mode (deterministic vs. Ollama), confirms vector path
- **SafeFrontendFiles**: Static file handler that blocks `config.local.json` from being served to the browser (prevents leaking API keys)
- **Runtime config endpoint** (`/frontend/runtime-config.json`): Returns `{apiBaseUrl, apiKeyHeader, requiresKey}` so `chat.js` knows how to authenticate
- **CORS**: Open for local dev; tighten for production

### Router Map

| Router | Prefix | Auth | Purpose |
|---|---|---|---|
| `routes_health` | `/health` | Yes | Liveness + readiness |
| `routes_ingest` | `/ingest` | Yes | Document ingest into RAG store |
| `routes_inventory` | `/inventory` | Yes | Catalog search, sync, image search, policy QA |
| `routes_orders` | `/orders` | Yes | Order draft/confirm/cancel |
| `routes_query` | `/query` | Yes | Tax law Q&A (original RAG use case) |
| `routes_eval` | `/eval` | Yes | Automated evaluation runs |
| `routes_agentic` | `/agentic` | Yes | Multi-step reasoning agents |

### routes_inventory.py — Key Endpoints

`POST /inventory/ask`
- Accepts `InventoryAskRequest`
- Delegates to `InventoryService.ask()`
- Returns `InventoryAskResponse`

`GET /inventory/ask-stream`
- SSE streaming version of the same call
- Events: `status` → `metadata` → `answer_delta` × N → `final`

`POST /inventory/image-search`
- Accepts `ImageSearchRequest` (base64 image, optional query text, category/color hints)
- Delegates to `ImageMatcher.search()`
- Returns `ImageSearchResponse` (list of `ImageSearchHit`)

`POST /inventory/policy-qa`
- Accepts `PolicyQARequest` (question string)
- Delegates directly to `PolicyQAEngine.answer()`
- Returns `PolicyQAResponse`

`POST /inventory/sync/import`
- Accepts `POSSyncImportRequest` (csv_text)
- Delegates to `POSSyncEngine.import_from_csv()`
- Returns `POSSyncResponse` (inserted, updated, stock_changed, skipped, errors)

`POST /inventory/sync/webhook`
- Accepts `POSSyncWebhookRequest` (source, event, items list)
- Delegates to `POSSyncEngine.import_from_webhook()`
- Returns `POSSyncResponse`

`GET /inventory/sync/status`
- Returns `POSSyncStatusResponse` (total_products, active_products, out_of_stock, last_sync)

`POST /inventory/sync/rebuild`
- Rebuilds vector index from current catalog.jsonl
- Required after any POS sync import

### routes_orders.py — Order Endpoints

Session engines are stored in `_SESSION_ENGINES: dict[str, OrderWorkflowEngine]`. Each `session_id` from the browser gets its own engine instance. On process restart, in-progress drafts are lost; only confirmed orders (persisted to JSONL) survive.

| Endpoint | Method | What It Does |
|---|---|---|
| `/orders/draft` | POST | Start a new draft for a product |
| `/orders/update` | POST | Update name/phone/area/payment on draft |
| `/orders/confirm` | POST | Finalize, persist, return order ID |
| `/orders/cancel/{session_id}` | DELETE | Clear draft state |
| `/orders/{order_id}` | GET | Retrieve confirmed order from JSONL |

---

## 7. Layer 3 — InventoryService (Orchestrator)

`app/services/inventory_service.py` is the main orchestration class. Every `/inventory/ask` call passes through it.

### ask() Method — Full Flow

```python
def ask(self, request: InventoryAskRequest) -> InventoryAskResponse:
```

**Step 1 — Memory Resolution**

`app/inventory/memory.py` resolves cross-turn references before any search logic:

- "eta" / "এটা" / "this" → resolves to `last_primary_product_id` from history
- "same design" / "ekoi design" → resolves to design_id of last product
- "ar koto?" / "price ki?" → understands these refer to the last product shown

After resolution, the question is optionally rewritten with the concrete product reference before being passed to fashion retail.

**Step 2 — Policy QA Early Intercept**

```python
if is_policy_question(resolved_question):
    answer = PolicyQAEngine().answer(resolved_question)
    if answer:
        return _wrap_policy_answer(answer)
```

`is_policy_question()` checks for any policy-related phrase in the normalized text. If it matches, the answer is returned immediately without ever loading the catalog or calling the fashion retail engine. This is both faster and guarantees grounding: policy answers never pull in product data.

**Step 3 — Catalog Load**

```python
catalog = self.load_catalog()  # dict[product_id → InventoryItemRecord]
```

Reads `data/inventory/catalog.jsonl` from disk into memory on each request (fast for JSONL sizes up to ~10k items; add caching for larger catalogs).

**Step 4 — Fashion Retail**

Calls `FashionRetailAssistant.answer()` with the resolved question, full catalog, and search filters. Returns `FashionRetailOutcome | None`.

**Step 5 — RAG Fallback**

If the fashion retail engine returns `None` (question not in its domain), the generic vector search runs against `local_vectors.jsonl` using deterministic embeddings (BM25-style token overlap).

**Step 6 — Response Assembly**

Assembles `InventoryAskResponse` with:
- `answer` from whichever engine responded
- `answer_engine`: `"fashion_retail"`, `"policy_qa"`, or `"rag"`
- `recommended_product_ids`, `cross_sell_product_ids`
- `confidence_score` (0–1), `abstained`, `abstention_reason`
- `answer_plan` (the extracted slot data — intent, language, color, fabric, etc.)
- `follow_up_question` if the engine produced one

### load_catalog() (Public Method)

Added as a public wrapper around the internal `_load_catalog()` so that routes and test fixtures can access the catalog without coupling to service internals.

### _try_policy_qa() (Static Method)

Wraps `PolicyQAEngine().answer()` with error handling. Returns `None` on any exception so the main flow is never interrupted by policy engine failures.

---

## 8. Layer 4 — Domain Engines

### 4a. FashionRetailAssistant

**File:** `app/inventory/fashion_retail.py`  
**Class:** `FashionRetailAssistant`

The largest and most complex module (~900 lines). It is entirely **deterministic and stateless** — no session state, no external calls, no side effects.

#### Slot Extraction

`extract_slots(question, catalog, filters, focused_product_ids, last_primary_product_id)` builds a `FashionRetailSlots` object by running regex patterns and alias lookups over the normalized question:

| Slot | Extraction Method |
|---|---|
| `color` | `COLOR_ALIASES` dict — 24 colors with Bangla/Banglish variants |
| `fabric` | `FABRIC_ALIASES` dict — 13 fabrics (jamdani, katan, silk, muslin, etc.) |
| `category_key` | `CATEGORY_ALIASES` dict — 17 categories (saree, panjabi, kurti, bag, etc.) |
| `size` | Size regex: `M|L|XL|XXL|size\s*\d+` with Bangla variants |
| `budget_min/max` | Price regex: `\d+` near "taka"/"BDT"/"er moddhe"/"er niche" |
| `occasion` | `OCCASION_ALIASES` — wedding/eid/office/casual/boishakh |
| `work_type` | `WORK_ALIASES` — zari/meena/embroidery/block print/buti |
| `brand` | `BRAND_ALIASES` — Aarong, Artisan, Richman, Rang, Yellow, Aranya |
| `design_id` | From `focused_product_ids` or catalog attribute lookup |
| `language` | Bangla unicode range detection → `"bangla"` / `"banglish"` / `"english"` |

#### Intent Classification

`_classify_intent()` tests in priority order:

1. **`fashion_styling_advice`** — any of `STYLING_ADVICE_PHRASES`:  
   "ki ki manabe", "styling advice", "sathe ki nibo", "কী পরব", "match korbe"

2. **`fashion_variant_color`** — any of `VARIANT_PHRASES`:  
   "same design", "ekoi design", "other color", "aro color", "অন্য রঙ"

3. **`fashion_size_availability`** — explicit size extraction succeeded and `AVAILABILITY_PHRASES` present:  
   "size ache?", "available?", "stock e ache?"

4. **`fashion_accessory_match`** — any of `ACCESSORY_MATCH_PHRASES` with no design variant signal:  
   "bag match", "jewelry manabe", "er sathe ki"

5. **`fashion_search`** — default fallback

#### Intent Handler: `_answer_styling_advice()`

Called when a customer asks "what should I pair with X for occasion Y."

1. Identify the base product color from slots
2. Look up `_COLOR_PAIRING_RULES[base_color]` — e.g., navy → ["gold", "silver", "white", "cream"]
3. Look up `_OCCASION_WEIGHT[occasion]` — e.g., wedding → ["heavy", "zari", "meena", "katan"]
4. Filter catalog for accessories (bag/shoe/jewelry/cosmetics) matching complementary colors
5. Apply stock filter (skip out-of-stock), apply budget filter if provided
6. Return markdown with accessory suggestions, complementary color reasoning, and stock counts

**`_COLOR_PAIRING_RULES`** (embedded dict, 24 entries):
```
red     → gold, black, white, silver, nude
navy    → gold, silver, white, cream, rose gold
green   → gold, white, beige, nude, brown
black   → gold, silver, red, white, nude
...
```

**`_OCCASION_WEIGHT`** (embedded dict, 6 occasions):
```
wedding  → heavy, zari, meena, katan, silk, banarasi, rajshahi
office   → lightweight, cotton, linen, formal
eid      → bright, festive, embroidered, silk
casual   → cotton, printed, block, light
...
```

#### Intent Handler: `_answer_variant_color()`

Called when customer wants the same design in a different color.

1. Find the source design from `focused_product_ids` or `design_id` slot
2. Query catalog for items sharing the same `attributes["design_id"]`
3. Filter those items by the requested color slot
4. Return in-stock matches; if none, list available colors for that design

#### Intent Handler: `_answer_size_availability()`

1. Extract size from slots
2. Filter catalog for category + size match via `attributes["size"]` or `metadata["sizes_available"]`
3. Prefer exact match before fuzzy; report if stock is low (≤ 2 units)

#### Intent Handler: `_answer_accessory_match()`

1. Extract base product from `focused_product_ids` or catalog search
2. Get base product category + color
3. Filter accessories (bag, shoe, jewelry, cosmetics) that are compatible by color family
4. Apply budget and stock filters
5. Return top-K matches with why each matches

#### Intent Handler: `_answer_fashion_search()`

General ranked search. Scores every catalog item against the query's extracted slots:

| Match Component | Points |
|---|---|
| Exact category_key match | 4.0 |
| Substring category match | 2.0 |
| Exact color match | 3.0 |
| Color family match | 1.5 |
| Exact fabric match | 2.5 |
| Work type match | 2.0 |
| Occasion tag match | 1.5 |
| Lexical name overlap | 0–2.0 (proportional) |
| In stock | +0.5 bonus |
| Out of stock | ×0.3 multiplier |

Top-K items by score are returned. Confidence = `top_score / max_possible_score`.

#### Brand Transliteration

`_detect_brand(text)` maps misspellings and Bangla script to canonical brand names:

```python
BRAND_ALIASES = {
    "aarong":   ("aarong", "arong", "arang", "আড়ং", "আড়োং"),
    "artisan":  ("artisan", "artisaan", "artizaan"),
    "richman":  ("richman", "rich man", "richmann"),
    "rang":     ("rang", "rong", "রং"),
    "yellow":   ("yellow", "yello", "ইয়েলো"),
    "aranya":   ("aranya", "aranya craft", "অরণ্য"),
}
```

---

### 4b. PolicyQAEngine

**File:** `app/inventory/policy_qa.py`

A pure lookup engine with no ML. Strict grounding: all answers come from `data/inventory/policies.json` only.

#### Question Routing (in priority order)

```
1. Delivery time?  → koto din lage / din lage / kto din / eta
2. Delivery charge? → delivery charge / delivery fee / ডেলিভারি চার্জ
3. Payment?        → payment / bkash / nagad / cod / card / পেমেন্ট
4. Refund?         → refund / রিফান্ড / ফেরত / money back
5. Exchange?       → exchange / return policy / ভুল সাইজ / wrong product
6. Alteration?     → alteration / stitching / সেলাই
7. Contact?        → contact / phone / ফোন / hours
8. No match        → return None (fall through to fashion retail or RAG)
```

**Why delivery time is checked before delivery charge**: "delivery koto din lage?" contains "delivery koto" which could match the charge check. Time comes first to avoid misrouting.

**Why outside-Dhaka is checked before inside-Dhaka** in `_delivery_charge_answer()`: "outside Dhaka delivery charge" contains "Dhaka", so without the outer check first, it would incorrectly return inside-Dhaka pricing.

#### Grounding Guarantee

`PolicyQAEngine` never returns a fabricated answer. Every value it uses (`charge`, `eta`, `allowed_days`, `methods`, etc.) is read directly from `policies.json`. If the file is missing or a key is absent, it falls back to the hardcoded defaults (BDT 80 / BDT 150 / 3 days) which match the real policy. It never says "I think" or "usually".

---

### 4c. OrderWorkflowEngine

**File:** `app/inventory/order_workflow.py`  
**Class:** `OrderWorkflowEngine` (one instance per session_id)

See [Section 15](#15-order-workflow-state-machine) for the full state machine diagram.

#### Key Behaviors

**`update_from_text(text)`** — NLP-free extraction from natural customer messages:

- Phone: regex `01[3-9]\d{8}` (Bangladesh mobile format)
- Payment: keyword match against `PAYMENT_METHOD_PATTERNS` dict
- Delivery area: keyword match against `inside_dhaka_areas` set (23 areas) or free-text capture
- Customer name: heuristic — first word before comma if phone present, or "name: X" pattern
- Quantity: digit + optional unit word (ta/টা/টি/pcs)

**Delivery Charge Logic:**
```python
inside_dhaka_areas = {
    "dhanmondi", "gulshan", "banani", "uttara", "mirpur", "mohakhali",
    "lalbagh", "old dhaka", "motijheel", "tejgaon", "bashundhara",
    "baridhara", "khilgaon", "shyamoli", "mohammadpur", "jatrabari",
    "demra", "rampura", "badda", "pallabi", "savar", "gazipur",
    "azimpur", "rayer bazar", "dhaka"
}

def delivery_charge(self) -> int:
    if area in inside_dhaka_areas:
        return 0 if subtotal >= 5000 else 80
    return 150
```

**`build_ask_for_missing()`** — Returns a single natural sentence asking for the next missing field, not a form. Example: "What name should I put on the order?" vs. a JSON form response.

**`confirm()`** — Writes to JSONL and returns order ID:
```python
order_id = f"ORD-{uuid4().hex[:6].upper()}"
# Appended line to data/orders/orders_store.jsonl:
{"order_id": "ORD-A1B2C3", "status": "confirmed", "items": [...], 
 "customer_name": "...", "grand_total": 6880.0, "confirmed_at": "..."}
```

---

### 4d. CustomerProfileManager

**File:** `app/inventory/customer_profile.py`

Session-scoped preference memory. Activated when a customer says something that reveals a preference.

#### Tracked Preferences

```python
@dataclass
class CustomerProfile:
    session_id: str
    preferred_language: str | None         # "bangla" / "banglish" / "english"
    sizes: dict[str, str]                  # {"blouse": "M", "shoe": "42", "panjabi": "L"}
    favorite_colors: list[str]             # ["navy", "green"]
    budget_min: float | None
    budget_max: float | None
    preferred_categories: list[str]        # ["saree", "bag"]
    skin_type: str | None                  # "oily" / "dry" / "combination" / "sensitive"
    delivery_area: str | None              # "Dhanmondi"
    fragrance_family: str | None           # "floral" / "woody" / "fresh"
```

#### Extraction Patterns

`extract_and_update(text)` runs regex against the customer's message:

| Pattern | Captures | Example |
|---|---|---|
| `_SIZE_PATTERN` | shirt/blouse/kurti size | "M size blouse prefer kori" |
| `_SHOE_SIZE_PATTERN` | shoe size (numeric) | "shoe size 42" |
| `_BUDGET_PATTERN` | min/max price range | "3000 er moddhe" → max=3000 |
| `_COLOR_PATTERN` | color preferences | "navy color pasand" |
| `_SKIN_PATTERN` (EN) | skin type | "I have oily skin" |
| `_SKIN_BANGLA` | Bangla skin type | "তৈলাক্ত ত্বক আমার" |

Returns a list of confirmation strings: `["Size blouse updated to M", "Budget max updated to BDT 3000"]`

#### Profile Persistence

- Stored in `data/customer_profiles/profiles_store.jsonl`
- One JSON object per `session_id` per line
- On update: reads entire file, rewrites with updated record
- `reset()`: removes session from store and clears in-memory profile
- `is_forget_request()`: detects "forget my preferences", "profile reset", "সব ভুলে যাও"
- `is_show_request()`: detects "show my profile", "amar profile", "ki prefer kori"

---

### 4e. ImageMatcher

**File:** `app/inventory/image_matcher.py`

Visual similarity search without real image embeddings. Deterministic mode uses product metadata to simulate what a visual search would find.

#### How It Works

A real visual search would: encode the uploaded image as a vector, then find catalog images with nearest vectors. This requires CLIP/ViT models or a cloud vision API.

In deterministic mode: encode the *query hints* (extracted from image filename, alt text, or query text) and match against catalog *attribute metadata* (category, color, design_id, work_type).

#### Scoring

```python
def _score_item(item, query_category, query_color, color_family):
    score = 0.0
    if item.category matches query_category (exact):   score += 0.40
    if item.category matches query_category (partial):  score += 0.20
    if item.attributes["color"] == query_color:         score += 0.30
    if item.attributes["color"] in color_family:        score += 0.15
    if item.attributes.get("design_id") detected:       score += 0.25
    if item.attributes.get("work_type") matches:        score += 0.15
    if item.stock > 0:                                  score += 0.05
    if item.stock == 0:                                 score  *= 0.30
    return score
```

#### Color Extraction from Base64

For cases where no text hint is given, the engine extracts a crude color signal from the image binary:

```python
raw = base64.b64decode(image_b64)
color_idx = raw[8] % 8  # deterministic byte position
color_map = {0: "red", 1: "blue", 2: "green", 3: "white", 4: "black", 5: "gold", 6: "navy", 7: "pink"}
```

This is intentionally simple. Production upgrade: send the image to a vision API or run a CLIP model.

#### Answer Format

Results are formatted with a mandatory disclaimer:

> "Similar design/color matches based on product metadata. Exact same SKU can only be confirmed with a product code or barcode."

This prevents the system from ever claiming a visual match is exact.

---

### 4f. POSSyncEngine

**File:** `app/inventory/pos_sync.py`

Ingests stock and price updates from two sources: CSV export from a POS terminal, and JSON webhook from an e-commerce platform.

#### CSV Import (`import_from_csv`)

Expected columns: `product_id, sku, name, category, brand, price, currency, stock, status, tags, attributes, updated_at`

Logic:
1. Parse each row via `_row_to_item()` → `InventoryItemRecord`
2. Load existing catalog
3. For each row:
   - If `product_id` not in catalog → **insert** (result.inserted++)
   - If `stock` changed → **stock_changed** (result.stock_changed++)
   - If `price`/`status` changed → **updated** (result.updated++)
   - If nothing changed → no-op (counted in skipped if row was malformed)
4. Write updated catalog back to JSONL
5. Append `SyncResult` to `sync_audit.jsonl`

#### Webhook Import (`import_from_webhook`)

Expected payload:
```json
{
  "source": "pos",
  "event": "stock_updated",
  "items": [
    {"sku": "SAR-JMD-LOTUS-RED", "stock": 2, "price": 6800, "updated_at": "..."}
  ]
}
```

Logic: look up item by SKU (not product_id), update stock/price/status fields, write back.

#### Sync Status (`get_sync_status`)

Returns:
```json
{
  "total_products": 47,
  "active_products": 45,
  "out_of_stock": 8,
  "last_sync": "2026-05-09T14:30:00+06:00"
}
```

**Important:** POS sync does not automatically rebuild the vector index. After any import, call `POST /inventory/sync/rebuild` to push updated embeddings to the vector store. Queries against the stale vector index will return slightly outdated results until rebuild completes.

---

## 9. Data Model — InventoryItemRecord

**File:** `app/core/schemas.py`

Every product in the system is represented as an `InventoryItemRecord`:

```python
class InventoryItemRecord(BaseModel):
    product_id:        str            # Stable unique ID (e.g., "saree-jmd-lotus-red")
    sku:               str            # Barcode/POS code (e.g., "SAR-JMD-LOTUS-RED")
    name:              str            # Display name
    category:          str | None     # Raw category string ("Saree", "Panjabi", "Bag")
    brand:             str | None     # Brand name
    short_description: str | None
    full_description:  str | None
    price:             float | None   # Unit price in BDT
    currency:          str = "USD"    # Currency code
    stock:             int            # Units on hand (0 = out of stock)
    status:            str | None     # "Active", "Archived", "Draft"
    tags:              list[str]      # Free-form tags ["saree", "jamdani", "red"]
    attributes:        dict[str,str]  # Structured: {"category_key": "saree",
                                      #               "color": "red",
                                      #               "fabric": "jamdani",
                                      #               "size": "free",
                                      #               "occasion": "wedding",
                                      #               "work_type": "buti",
                                      #               "design_id": "lotus-buti-01"}
    metadata:          dict[str,Any]  # Images, variant_group_name, additional flags
    include_in_rag:    bool = True    # If False, excluded from vector search
    updated_at:        str | None     # ISO timestamp of last update
```

**The `attributes` dict is the primary search surface.** All intent handlers in `FashionRetailAssistant` read from it. The `category_key` attribute (lowercase, normalized) is especially important — `"saree"`, `"panjabi"`, `"bag"`, `"shoe"`, `"cosmetics"`, etc.

---

## 10. Data Model — Policy Store

**File:** `data/inventory/policies.json`

```json
{
  "version": "boutique-policy-v1",
  "shop_name": "Sonjoy Boutique",
  "delivery": {
    "inside_dhaka":  {"charge": 80, "eta": "1-2 working days"},
    "outside_dhaka": {"charge": 150, "eta": "3-5 working days"},
    "express_dhaka": {"charge": 150, "eta": "Same day (order before 12pm)", "available": true},
    "free_delivery_threshold": {"amount": 5000}
  },
  "payment": {
    "methods": ["COD", "bKash", "Nagad", "Rocket", "card", "bank_transfer"],
    "cod":    {"available": true, "limit_bdt": 10000},
    "bkash":  {"available": true, "number": "01XXXXXXXXX", "instruction": "Send to number, upload screenshot"},
    "nagad":  {"available": true},
    "rocket": {"available": true},
    "card":   {"available": true, "note": "Visa/Mastercard via payment gateway"},
    "advance_required": {"threshold_bdt": 10000, "note": "Orders above 10k require advance payment"}
  },
  "refund": {
    "allowed": false,
    "exceptions": ["Wrong product sent", "Defective/damaged on arrival", "Size mismatch (boutique error)"],
    "process": ["Contact within 48 hours with photo", "Verified within 1-2 days", "Refund via original method in 3-5 days"],
    "not_eligible": ["Changed mind", "Used or washed product", "No original tags"]
  },
  "exchange": {
    "allowed": true,
    "allowed_days": 3,
    "conditions": ["Unused with original tags", "Original receipt/order ID", "Contact within 3 days"],
    "not_eligible": ["Stitched blouse", "Customized items", "Opened cosmetics/fragrances"]
  },
  "alteration": {
    "available": true,
    "products": ["blouse", "panjabi", "salwar_kameez"],
    "lead_time": "3-5 working days",
    "cost": "Free for size adjustment ±2 inches"
  },
  "damaged_product": {
    "policy": "Contact us within 24 hours with clear photo proof. We will arrange replacement or refund."
  },
  "contact": {
    "phone": "01XXXXXXXXX",
    "whatsapp": "01XXXXXXXXX",
    "email": "support@sonjoyboutique.com",
    "hours": "10am - 8pm, Saturday through Thursday"
  }
}
```

This file is loaded once at startup via `@lru_cache(maxsize=1)` and never re-read unless the process restarts.

---

## 11. Persistence Layer

All persistence is file-based JSONL (newline-delimited JSON). Each record is one JSON object per line.

| Store | Path | Write Pattern | Read Pattern |
|---|---|---|---|
| Catalog | `data/inventory/catalog.jsonl` | Full rewrite on POS sync | Full read on each request |
| Orders | `data/orders/orders_store.jsonl` | Append on confirm | Scan for order_id |
| Profiles | `data/customer_profiles/profiles_store.jsonl` | Full rewrite on update | Scan for session_id |
| Sync audit | `data/inventory/sync_audit.jsonl` | Append on each import | Scan (status endpoint) |
| Vectors | `data/agentic_store/local_vectors.jsonl` | Rebuild via sync endpoint | Vector search at query time |

**Why JSONL?** Zero dependencies, human-readable, appendable without locks, compatible with `grep`, easy to inspect in the terminal. For production scale: replace catalog with SQLite, orders with PostgreSQL, profiles with Redis.

---

## 12. Intent Classification and Routing Logic

This diagram shows how a customer question is routed through the full decision tree:

```
Customer question
       │
       ▼
is_policy_question()? ──YES──► PolicyQAEngine.answer()
       │                             │
       NO                            ▼
       │                       Return answer (bypass product search)
       ▼
FashionRetailAssistant.should_handle()?
       │
      YES ──► extract_slots()
       │           │
       NO          ▼
       │      _classify_intent()
       │           │
       ▼           ├─ fashion_styling_advice ──► _answer_styling_advice()
  Generic RAG      │
  (vector search)  ├─ fashion_variant_color ──► _answer_variant_color()
                   │
                   ├─ fashion_size_availability ──► _answer_size_availability()
                   │
                   ├─ fashion_accessory_match ──► _answer_accessory_match()
                   │
                   └─ fashion_search (default) ──► _answer_fashion_search()
```

**`should_handle()`** returns True if the question contains any category keyword, fabric keyword, product name, or fashion intent phrase. It returns False for questions like "ki obostha?" (general greeting) or "Bangladesh er capital ki?" (general knowledge). Those fall through to RAG.

---

## 13. Language Detection and Normalization

### normalize_fashion_text()

All text passes through `normalize_fashion_text()` before any matching:

1. **Bangla digit normalization**: ০১২৩৪৫৬৭৮৯ → 0123456789
2. **Special char stripping**: apostrophes, em-dashes, quotes → space
3. **Lowercase**: entire string
4. **Whitespace collapse**: multiple spaces → single space

### Language Detection

Detected by Unicode range inspection during slot extraction:

- Bangla Unicode block: U+0980–U+09FF
- If ≥ 2 Bangla characters in question → `language = "bangla"`
- If 0 Bangla characters but Bangla-romanized words detected → `language = "banglish"`
- Else → `language = "english"`

### Alias Coverage

The alias system means the same product is found regardless of how the customer writes it:

| Customer writes | Resolves to |
|---|---|
| "jamdani" | fabric_key: jamdani |
| "জামদানি" | fabric_key: jamdani |
| "jamdhani" | fabric_key: jamdani |
| "jomdhani" | fabric_key: jamdani |
| "nil" / "neel" / "নীল" | color: blue |
| "lal" / "লাল" / "red" | color: red |
| "arong" / "আড়ং" / "aarong" | brand: Aarong |
| "panjabi" / "punjabi" / "পাঞ্জাবি" | category_key: panjabi |

---

## 14. Scoring and Ranking

`_answer_fashion_search()` uses a weighted additive scorer. Every catalog item gets a float score; the top-K by score are returned.

### Score Components

```
score = 0.0

# Category matching (most important signal)
if item.attributes["category_key"] == slots.category_key:   score += 4.0
elif slots.category_key in item.category.casefold():        score += 2.0

# Color matching
if item.attributes["color"] == slots.color:                 score += 3.0
elif color_family_match(item, slots):                       score += 1.5

# Fabric matching
if item.attributes["fabric"] == slots.fabric:              score += 2.5

# Work type
if item.attributes["work_type"] == slots.work_type:        score += 2.0

# Occasion tag
if slots.occasion in item.tags:                            score += 1.5

# Lexical overlap (product name vs. query terms)
overlap = len(query_tokens ∩ name_tokens) / len(query_tokens)
score += overlap * 2.0

# Stock preference
if item.stock > 0:    score += 0.5
if item.stock == 0:   score *= 0.3   # strong penalty, not zero (color variants may be relevant)
```

### Confidence Score

```python
confidence = top_item_score / max_possible_score  # 0–1
```

If `confidence < 0.3`, the engine abstains: returns `abstained=True` with `abstention_reason="No confident match found for this query"`.

---

## 15. Order Workflow State Machine

```
        ┌──────────────────────────────┐
        │         (no draft)            │
        └──────────────┬───────────────┘
                       │ start_draft(product_id, sku, name, unit_price, qty)
                       ▼
        ┌──────────────────────────────┐
        │           DRAFT               │
        │  items:      [OrderItem]      │
        │  customer:   None             │
        │  phone:      None             │
        │  area:       None             │
        │  payment:    None             │
        └────┬─────────────────────────┘
             │
             │ update_from_text() ← customer provides details in natural text
             │ (extracts phone, area, payment, name from free text)
             │
             ▼
        ┌──────────────────────────────┐
        │      DRAFT (fields filling)   │
        │  is_ready_to_confirm() → ?    │
        │  missing_fields() → [...]     │
        └────┬────────────┬────────────┘
             │            │
             │ fields      │ cancel()
             │ complete    │
             ▼            ▼
        ┌─────────┐  ┌────────────────┐
        │ AWAITING │  │   CANCELLED    │
        │ CONFIRM  │  │  (draft = None)│
        │          │  └────────────────┘
        │ summary  │
        │ shown    │
        └────┬─────┘
             │
      ┌──────┴──────┐
      │             │
   is_confirm()  is_cancel()
      │             │
      ▼             ▼
┌──────────┐  ┌────────────────┐
│CONFIRMED │  │   CANCELLED    │
│          │  │  (draft = None)│
│Persisted │  └────────────────┘
│to JSONL  │
│order_id  │
│returned  │
└──────────┘
```

### What "ready to confirm" means

`missing_fields()` returns an empty list only when ALL of these are set:

1. `items` — at least one product in cart
2. `customer_name` — name for delivery
3. `customer_phone` — 11-digit Bangladesh mobile number
4. `delivery_area` — where to deliver
5. `payment_method` — how to pay

Until all five are present, `build_ask_for_missing()` returns the next prompt. The engine asks for one field at a time, not a form.

---

## 16. Customer Profile Memory Lifecycle

```
Turn 1: "M size blouse chai"
        → extract_and_update() finds: size blouse = M
        → Profile: {sizes: {"blouse": "M"}}
        → Confirmation: "Got it — I've noted blouse size M for you."

Turn 2: "navy prefer kori"
        → extract_and_update() finds: favorite_color = navy
        → Profile: {sizes: {"blouse": "M"}, favorite_colors: ["navy"]}

Turn 3: "3000 er moddhe bag ache?"
        → extract_and_update() finds: budget_max = 3000
        → Profile updated, InventoryService applies max_price=3000 to filters

Turn 4: "amar profile dekhao"
        → is_show_request() → True
        → Returns profile.summary_text()

Turn 5: "sob bhule jao"
        → is_forget_request() → True
        → manager.reset() → removes from JSONL
        → Profile: {} (empty)
```

Profile data feeds into `InventorySearchFilters`:
- `sizes` → used to pre-filter by size when question doesn't mention size
- `budget_max` → sets `max_price` on filters
- `favorite_colors` → boosts scoring for preferred colors
- `delivery_area` → pre-fills order draft area

---

## 17. Image Search Without Real Embeddings

The image search flow in deterministic mode:

```
Customer uploads: photo of a red jamdani saree

Step 1: FileReader API → base64 string in browser
Step 2: POST /inventory/image-search
        {image_b64: "...", query_text: "ekta eta er moto ache?", top_k: 5}

Step 3: ImageMatcher.search()
        a. Parse query_text for category/color hints
           → category_hint: "saree"
           → color_hint: "red"
        b. If no text hints, extract from base64:
           raw[8] % 8 → color_map[2] = "red"  (deterministic)
        c. Score all catalog items:
           - saree-jmd-lotus-red:   score 0.95 (category + color + in-stock)
           - saree-jmd-lotus-blue:  score 0.62 (category + close color family)
           - saree-katan-red:       score 0.70 (category + exact color)
        d. Sort by score descending, return top-5

Step 4: build_answer(results, query_text)
        "Found 3 similar products:
         1. Lotus Buti Jamdani - Red (BDT 6800, 4 in stock) — category match: saree, exact color match: red
         2. Rajshahi Katan - Red (BDT 8500, 2 in stock) — category match: saree, exact color match: red
         3. Lotus Buti Jamdani - Blue (BDT 6800, 3 in stock) — category match: saree, same design
         
         Note: These are similar design/color matches based on product metadata.
         Exact same SKU can only be confirmed with a product code."
```

---

## 18. POS Sync — Catalog Ingestion Pipeline

```
POS Terminal (CSV export)
        │
        ▼
POST /inventory/sync/import
{csv_text: "product_id,sku,name,...\nrow1\nrow2\n..."}
        │
        ▼
POSSyncEngine.import_from_csv()
        │
        ├─ Parse CSV rows → list[dict]
        ├─ For each row:
        │   ├─ _row_to_item(row) → InventoryItemRecord
        │   ├─ Compare with existing catalog entry
        │   │   ├─ Not in catalog → INSERT
        │   │   ├─ Stock changed → UPDATE stock_changed++
        │   │   ├─ Price/status changed → UPDATE updated++
        │   │   └─ No change → skip
        │   └─ Write updated record back
        │
        ├─ Persist full catalog to catalog.jsonl
        └─ Append SyncResult to sync_audit.jsonl
                │
                ▼
        SyncResult: {inserted:2, updated:1, stock_changed:3, skipped:0, errors:[]}
                │
        !! IMPORTANT !!
                ▼
POST /inventory/sync/rebuild   ← Must call this separately to refresh vectors
        │
        └─ Re-embeds all include_in_rag=True items into local_vectors.jsonl
```

**Webhook flow** (e-commerce platform pushes in real-time):

```
Platform webhook → POST /inventory/sync/webhook
{source: "pos", event: "stock_updated", items: [{sku: "...", stock: 2}]}
        │
        ▼
POSSyncEngine.import_from_webhook()
        │
        └─ Lookup by SKU → update stock/price/status → persist catalog
```

---

## 19. API Reference

### Inventory Endpoints

```
POST   /inventory/ask                    Main chat endpoint
GET    /inventory/ask-stream             SSE streaming chat
GET    /inventory/status                 Catalog health status
POST   /inventory/image-search           Visual similarity search
POST   /inventory/policy-qa             Direct policy Q&A
POST   /inventory/sync/import            CSV catalog import
POST   /inventory/sync/webhook           Webhook stock update
GET    /inventory/sync/status            Sync status report
POST   /inventory/sync/rebuild           Rebuild vector index
GET    /inventory/sync/validate          Validate catalog vs vector store
POST   /inventory/business/signals/upsert  Upsert business signal
GET    /inventory/business/signals       List business signals
GET    /inventory/business/status        Business signals health
```

### Order Endpoints

```
POST   /orders/draft                     Start order draft
POST   /orders/update                    Update draft details
POST   /orders/confirm                   Confirm and persist order
DELETE /orders/cancel/{session_id}       Cancel draft
GET    /orders/{order_id}                Retrieve confirmed order
```

### Health

```
GET    /health/live                      Liveness (200 = process up)
GET    /health/ready                     Readiness (200 = catalog loaded)
```

### Auth

All endpoints require `X-API-Key: {api_key}` header. In local dev, this defaults to `dev-key`.

---

## 20. Test Architecture

207 tests across 12 suites. All pass without external dependencies (no Ollama, no ES, no internet).

### New Suites (91 tests)

| Suite | Count | What It Covers |
|---|---|---|
| `test_policy_qa.py` | 14 | policies.json load, all topic dispatches, grounding guarantee |
| `test_order_workflow.py` | 17 | draft, subtotal, delivery charge, free threshold, missing fields, confirm, cancel, text extraction |
| `test_customer_profile_memory.py` | 13 | size/budget/skin extraction, reset, show, to_dict/from_dict roundtrip |
| `test_image_matching.py` | 12 | query detection, search, budget filter, no-duplicates, build_answer disclaimer |
| `test_pos_sync.py` | 12 | CSV insert, stock change detection, webhook update, unknown SKU skip, status counts |
| `test_styling_advice.py` | 8 | navy+gold pairing, color rules exist, occasion rules exist, budget constraint |
| `test_deep_bangla_banglish_conversation.py` | 13 | digit normalization, Bangla/Banglish/English detection, 5-turn context, follow-up |
| `test_large_multibrand_catalog.py` | 12 | brand aliases, transliteration, design variants, category coverage |

### Pre-Existing Suites (116 tests)

| Suite | Count | What It Covers |
|---|---|---|
| `test_boutique_retail_catalog.py` | 12 | Catalog loading, product data integrity |
| `test_fashion_retail.py` | 18 | Core fashion search, accessory match, variant color |
| `test_inventory_intelligence.py` | 18 | Service layer intent routing, abstention, confidence |
| `test_inventory_api.py` | 61 | Full API surface, SSE streaming, sync endpoints, agentic routing, business signals |

### Running Tests

**New suites only (no heavy deps):**
```bash
cd bangla-tax-rag
.venv/bin/python -m pytest \
  tests/test_policy_qa.py \
  tests/test_order_workflow.py \
  tests/test_customer_profile_memory.py \
  tests/test_image_matching.py \
  tests/test_pos_sync.py \
  tests/test_styling_advice.py \
  tests/test_deep_bangla_banglish_conversation.py \
  tests/test_large_multibrand_catalog.py \
  -v
```

**Full suite (requires rank-bm25 + pdfplumber):**
```bash
.venv/bin/python -m pip install rank-bm25 pdfplumber
.venv/bin/python -m pytest tests/ -q
```

---

## 21. Known Limitations and Production Upgrade Paths

| Limitation | Current Behavior | Production Fix |
|---|---|---|
| Image matching | Metadata-based scoring, not visual | Integrate CLIP/ViT embeddings or cloud vision API |
| Customer profiles | JSONL per session_id, no cross-session | Replace with Redis (session TTL) or PostgreSQL (auth users) |
| Order drafts | In-memory, lost on restart | Replace with Redis or SQLite per session |
| POS sync + rebuild | Two separate calls required | Add auto-rebuild flag to sync import endpoint |
| Branch stock | Not in schema | Add `branch_id` field + branch filter to `InventorySearchFilters` |
| Catalog load | Full JSONL read on every request | Add in-process LRU cache keyed on file mtime |
| Policy updates | Requires process restart (`@lru_cache`) | Add cache invalidation endpoint |
| Multi-user orders | No user auth, session_id from browser | Add JWT auth, bind orders to user_id |

---

## 22. Running the System

### Prerequisites

```bash
cd bangla-tax-rag
python3 -m venv .venv
.venv/bin/pip install fastapi pydantic pydantic-settings uvicorn pytest httpx PyYAML rank-bm25 pdfplumber
```

### Start Server (Deterministic Local Mode)

```bash
APP_PORT=4849 \
VECTOR_DB=local \
LOCAL_VECTOR_STORE_PATH=data/agentic_store/local_vectors.jsonl \
EMBEDDING_PROVIDER=deterministic \
EMBEDDING_MODEL_NAME=deterministic-live \
EMBEDDING_DIMENSIONS=256 \
RERANKER_PROVIDER=deterministic \
INVENTORY_NATURAL_ANSWERS_ENABLED=false \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 4849
```

Then open: `http://127.0.0.1:4849/frontend/chat.html`

### Optional: Natural Language Mode (requires Ollama)

```bash
ollama pull qwen3:8b

APP_PORT=4849 \
VECTOR_DB=local \
LOCAL_VECTOR_STORE_PATH=data/agentic_store/local_vectors.jsonl \
EMBEDDING_PROVIDER=deterministic \
EMBEDDING_MODEL_NAME=deterministic-live \
EMBEDDING_DIMENSIONS=256 \
RERANKER_PROVIDER=deterministic \
INVENTORY_NATURAL_ANSWERS_ENABLED=true \
GENERATOR_PROVIDER=ollama \
GENERATOR_MODEL_NAME=qwen3:8b \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 4849
```

### Seed Catalog (if starting fresh)

```bash
# Option A: POS CSV import
curl -X POST http://127.0.0.1:4849/inventory/sync/import \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"csv_text": "product_id,sku,name,category,...\n..."}'

# Then rebuild vectors
curl -X POST http://127.0.0.1:4849/inventory/sync/rebuild \
  -H "X-API-Key: dev-key"
```

---

*This document reflects the state of the system as of the 2026-05-09 full production build on the `Inventory` branch. For the test audit, see `results/build_audit_2026-05-09.md`.*
