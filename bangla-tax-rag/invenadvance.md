# Inventory Advanced Chatbot

This document explains how the current advanced inventory chatbot works, what each layer does, what question types it can answer, and where the next engineering work should focus.

The system is designed for a boutique or fashion retail shop with sarees, bags, cosmetics, beauty products, watches, three pieces, shoes, men's panjabi, shirts, pants, perfumes, accessories, and similar catalog items. The goal is simple: a customer should be able to ask normal Bangla, English, or Banglish questions, and the bot should answer from the real catalog instead of guessing.

## Full Flow Chart

![Advanced inventory chatbot flow](docs/assets/inventory_advanced_flow.svg)

## RAG Pipeline Flow Chart

![Inventory RAG pipeline flow](docs/assets/rag_pipeline_flow.svg)

This is the real retrieval-augmented generation loop in the current system:

1. Product data is normalized into searchable catalog evidence.
2. Search text is embedded and stored in either the local vector store or Elasticsearch.
3. A customer question is normalized, classified, and converted into structured filters.
4. The system retrieves candidate products using structured catalog filtering, vector search, and semantic fallback.
5. Candidates are reranked and converted into an evidence contract.
6. The retail decision layer chooses a primary match, variants, accessories, or abstains.
7. The answer writer responds in the customer's language style.
8. The grounding check prevents unsupported stock, price, size, color, policy, or product claims.
9. Feedback and traces become future eval cases and tuning work.

## Current Live Surfaces

| Surface | URL or endpoint | What it does |
| --- | --- | --- |
| Chat UI | `http://127.0.0.1:4850/chat.html` | Customer chat, catalog side panel, product actions, feedback, order helpers |
| Backend | `http://127.0.0.1:4849` | FastAPI application |
| Chat answer | `POST /inventory/ask` | Main customer question answering endpoint |
| Catalog list | `GET /inventory/items` | Powers the side catalog panel |
| Catalog search | `POST /inventory/search` | Direct structured inventory search |
| Image search | `POST /inventory/image-search` | Finds visually similar or same-design products |
| Policy QA | `POST /inventory/policy-qa` | Delivery, payment, refund, exchange, support policy answers |
| Order draft | `POST /orders/draft` | Starts a cart or order session |
| Order update | `POST /orders/update` | Changes item, quantity, customer, or delivery fields |
| Order confirm | `POST /orders/confirm` | Confirms an order and stores it |
| Order tracking | `GET /orders/track/{phone}` | Finds customer orders by phone |
| POS rebuild | `POST /inventory/sync/rebuild` | Rebuilds catalog mirror and vector index |
| POS import | `POST /inventory/sync/import` | Imports inventory from CSV-style payloads |
| POS webhook | `POST /inventory/sync/webhook` | Accepts external inventory updates |
| Feedback | `POST /feedback` | Stores thumbs up/down feedback from UI |

## Data Stores

| File or store | Purpose |
| --- | --- |
| `data/inventory/catalog.jsonl` | Main product catalog. Current test catalog has 47 boutique retail items. |
| `data/inventory/policies.json` | Delivery, payment, refund, exchange, and support rules. |
| `data/orders/orders_store.jsonl` | Confirmed and draft order records. |
| `data/inventory/sync_audit.jsonl` | Import, webhook, and rebuild audit history. |
| `data/customer_profiles/profiles_store.jsonl` | Customer preference/profile memory when enabled. |
| `data/agentic_store/local_vectors.jsonl` | Local vector store used by the current live backend. |
| Elasticsearch index | Optional vector backend when the app is started with `VECTOR_DB=elasticsearch`. |

Important: Elasticsearch support exists and adapter tests pass, but the live backend normally uses the local vector store unless it is restarted with Elasticsearch environment variables.

## Request Flow

1. The customer types a question in `frontend/chat.html`.
2. `frontend/chat.js` sends the question to `POST /inventory/ask` with the API key, conversation history, focused product ids, and previous answer plan when available.
3. FastAPI routes in `app/api/routes_inventory.py` validate the request and pass it to `InventoryService`.
4. `app/services/inventory_service.py` orchestrates the answer:
   - Loads catalog data.
   - Checks policy and small-talk paths.
   - Loads conversation state and profile memory when available.
   - Calls the fashion retail reasoning layer.
   - Builds traces, metadata, recommendations, and final answer structure.
5. `app/inventory/fashion_retail.py` acts as the structured retail brain:
   - Normalizes Bangla, English, and Banglish.
   - Extracts category, color, size, gender, budget, occasion, brand, fabric, design id, and stock intent.
   - Chooses the right retail intent.
   - Applies hard filters before semantic fallback.
   - Refuses to answer when no catalog-backed match exists.
6. The selected answer returns to the UI with:
   - answer text
   - intent
   - language
   - products shown
   - trace id
   - answer plan
   - feedback controls
7. The UI renders the chat response and keeps the catalog side panel available for inspection.

## Layer Responsibilities

| Layer | Main files | Responsibility |
| --- | --- | --- |
| Browser UI | `frontend/chat.html`, `frontend/chat.css`, `frontend/chat.js` | Smooth chat interface, hidden catalog panel, API calls, product buttons, image upload, feedback, order controls |
| API routes | `app/api/routes_inventory.py`, `app/api/routes_orders.py`, `app/api/routes_feedback.py` | HTTP request validation, endpoint routing, response schemas |
| Service orchestrator | `app/services/inventory_service.py` | Overall chat workflow, policy shortcut, memory, traces, answer synthesis, final response contract |
| Retail reasoning | `app/inventory/fashion_retail.py` | Intent detection, slot extraction, category/gender/size filters, variants, styling, compare, accessory match |
| Banglish support | `app/inventory/banglish_normalizer.py` | Adds Bangla and English equivalents for Banglish words like `katan`, `biye`, `eid`, `bag`, `saree` |
| Policy engine | `app/inventory/policy_qa.py` | Delivery charge, COD, refund, return, exchange, damaged item policy |
| Order workflow | `app/inventory/order_workflow.py` | Cart, draft order, quantity update, confirmation, order storage |
| Image matching | `app/inventory/image_matcher.py`, `app/inventory/clip_matcher.py` | Image similarity, same-design variant matching, CLIP fallback when available |
| POS sync | `app/inventory/pos_sync.py` | CSV import, webhook updates, audit trail |
| Vector store | `app/retrieval/vector_store_base.py`, `app/retrieval/elasticsearch_store.py` | Local or Elasticsearch vector retrieval |

## Intent Routing

| Intent | Example question | What the bot should do |
| --- | --- | --- |
| `small_talk` | `hello`, `apni ki korte paren?` | Greet and explain inventory help briefly. |
| `fashion_search` | `eid er jonno 5000 er moddhe elegant saree dekhan` | Filter by category, occasion, budget, style, stock, then show matching products. |
| `fashion_variant_color` | `same design ta blue color e ache?` | Resolve design family and list available color variants. |
| `fashion_size_availability` | `black heel size 39 ache?` | Check exact size and stock. |
| `fashion_accessory_match` | `maroon bridal saree er sathe bag ar jewelry ki match korbe?` | Recommend compatible accessories from catalog. |
| `fashion_compare` | `jamdani vs katan konta wedding er jonno better?` | Compare options using catalog attributes and use case. |
| `fashion_styling_advice` | `office er jonno sober look chai` | Suggest full outfit direction using catalog-backed products. |
| `policy_qa` | `Dhaka delivery charge koto?`, `COD available?` | Answer from `policies.json`. |
| `order_intent` | `eta order korte chai` | Use order draft/update/confirm flow. |
| `image_search` | Customer uploads a product photo | Return visually similar catalog items or same-design variants. |
| `unknown` | `phone cover ache?` when no phone cover exists | Say no catalog-backed match and ask a useful narrowing question. |

## Question Types The Bot Is Ready For

| Customer need | Example |
| --- | --- |
| Product availability | `red matte lipstick ache? price koto?` |
| Budget search | `3000 takar moddhe men perfume ache?` |
| Occasion search | `biye te porar moto premium saree dekhan` |
| Eid shopping | `eid er jonno 5000 er moddhe elegant saree` |
| Office use | `amar office ache amake kichu bag dekhan` |
| Size check | `ladies black heel size 39 available?` |
| Same design different color | `ei lotus jamdani same design blue ache?` |
| Accessory matching | `maroon katan saree er sathe clutch match korbe?` |
| Beauty/skincare | `toilakto skin er jonno sunscreen ache?` |
| Men section | `men panjabi white color ache?` |
| Gender-safe filtering | `men watch ba perfume 3000 er moddhe ache?` |
| Compare | `cotton saree ar silk saree konta daily use er jonno better?` |
| Policy | `wrong size hole exchange korte parbo?` |
| Delivery and payment | `Dhaka delivery koto? COD hobe?` |
| Order flow | `eta cart e add korun`, `order confirm korte chai` |
| Out-of-catalog rejection | `mobile cover ache?` |

## What Was Fixed In This Advanced Version

| Problem before | Current behavior |
| --- | --- |
| Old saree context could hijack a new bag query | Safer context logic now avoids using old context when the new query has a fresh category, budget, occasion, or gender. |
| Bag query returned saree-style no-match text | Category routing is stricter, and bag queries search bags. |
| Men's query could return women's products | Gender is now a hard filter where the user clearly says men/women. |
| Accessory questions sometimes became compare questions | Accessory routing runs before compare routing. |
| No-match answers showed random cross-sells | Abstained/no-match answers no longer attach unrelated cross-sell products. |
| `katan` Banglish could normalize incorrectly | Banglish normalization now preserves the intended fashion meaning. |
| Catalog was invisible in chat | UI now has a hideable catalog side panel powered by `/inventory/items`. |

## Current Answer Contract

The bot should follow these rules:

1. Answer from catalog evidence only.
2. Never invent price, stock, size, delivery promise, or refund rule.
3. Keep user language style when possible: Bangla, English, or Banglish.
4. When the query is broad, show a few strong matches and ask one narrowing question.
5. When there is no match, clearly say no match and ask for category, color, size, budget, or occasion.
6. Do not recommend unrelated products just to avoid an empty answer.
7. For size, color, design, and gender, prefer structured product fields over semantic similarity.
8. For policy questions, answer from policy data, not from product descriptions.
9. For order placement, collect product, quantity, customer name, phone, address, and payment/delivery choices before confirmation.

## Prompt Contract For Natural Answers

When natural wording is enabled, the writer model should receive a strict contract like this:

```text
You are a grounded fashion retail assistant for a boutique inventory system.

Use only the provided catalog evidence and policy evidence.
Do not invent stock, price, color, size, material, discount, delivery time, refund rule, or product availability.
Answer in the customer's language style: Bangla, English, or Banglish.

If products are provided:
- Mention the best 1 to 3 matches.
- Include price and stock if present.
- Explain why they match the customer's need.
- Ask one useful follow-up question when narrowing is needed.

If no product matches:
- Say that the current catalog does not show an exact match.
- Do not recommend unrelated items.
- Ask for one narrowing detail such as category, color, size, budget, or occasion.

If the question is about delivery, payment, refund, exchange, or order:
- Use policy/order evidence only.
- Do not make promises outside the policy.
```

## Testing Status

Recent focused tests passed for the boutique retail behavior:

| Test area | Result |
| --- | --- |
| Boutique catalog regression tests | Passed |
| Wider inventory test suite | Passed |
| Elasticsearch adapter tests | Passed |
| Live smoke tests for Banglish examples | Passed after wiring fixes |

The exact live quality still depends on how the backend is started. Deterministic answer mode is faster and more stable. Natural LLM wording can sound nicer, but it can also add latency and must be verified.

## Known Weaknesses

Let's pressure-test the current system honestly:

1. It is not yet a perfect human salesperson. It is a structured catalog assistant with some conversation memory.
2. Local LLM calls can make responses slow, sometimes 10 to 25 seconds depending on Ollama/model state.
3. Image matching can be slow the first time if CLIP needs to load or download model assets.
4. Chat-native order placement is functional at the API level, but the conversational order flow still needs more polish.
5. The static frontend currently contains a local demo API key. That is acceptable for local testing, but it is not production-safe.
6. Large multi-brand catalogs need stronger taxonomy, brand aliases, duplicate handling, and inventory freshness guarantees.

## Recommended Next Engineering Priorities

| Priority | Work | Why it matters |
| --- | --- | --- |
| 1 | Add deterministic answer templates for common retail intents | Makes chat fast, stable, and human enough without waiting on LLM for every turn. |
| 2 | Add production auth instead of exposing API key in static JS | Prevents anyone from copying the key from the browser. |
| 3 | Strengthen product taxonomy and aliases | Makes the bot work for any future inventory, not only the current sample catalog. |
| 4 | Improve conversational order state | Lets the bot naturally collect missing order details across turns. |
| 5 | Prewarm or lazy-safe CLIP image matching | Prevents first image search from feeling broken. |
| 6 | Add real POS sync adapter | Keeps stock, price, and variants current. |
| 7 | Add owner dashboard for failed questions | Turns bad answers into a continuous improvement loop. |

## How To Run Locally

Backend:

```bash
APP_PORT=4849 \
UI_BACKEND_BASE_URL=http://127.0.0.1:4849 \
VECTOR_DB=local \
LOCAL_VECTOR_STORE_PATH=data/agentic_store/local_vectors.jsonl \
EMBEDDING_PROVIDER=deterministic \
EMBEDDING_MODEL_NAME=deterministic-live \
EMBEDDING_DIMENSIONS=256 \
RERANKER_PROVIDER=deterministic \
INVENTORY_NATURAL_ANSWERS_ENABLED=false \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 4849
```

Frontend:

```bash
python3 -m http.server 4850 --bind 127.0.0.1 --directory frontend
```

Rebuild inventory sync:

```bash
curl -X POST \
  -H "X-API-Key: <your-api-key>" \
  http://127.0.0.1:4849/inventory/sync/rebuild
```

Run with Elasticsearch instead of the local vector store:

```bash
VECTOR_DB=elasticsearch \
ELASTICSEARCH_URL=http://localhost:9200 \
ELASTICSEARCH_INDEX_NAME=inventory-rag \
APP_PORT=4849 \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 4849
```

## Practical Decision

The current architecture is compatible with a real boutique inventory chatbot, but only if the product catalog stays structured. The critical fields are:

- `product_id`
- `name`
- `category`
- `price`
- `stock`
- `attributes.color`
- `attributes.color_family`
- `attributes.size` or `attributes.available_sizes`
- `attributes.gender`
- `attributes.fabric`
- `attributes.occasion`
- `attributes.design_id`
- `metadata.variant_group_name`
- `metadata.source`

If those fields are weak or missing, the bot becomes a generic semantic search system and will make worse decisions. The strategic rule is: make the catalog machine-readable first, then let the chatbot sound human.
