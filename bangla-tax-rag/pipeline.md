# Inventory RAG Pipeline

This document explains the current inventory RAG pipeline in technical detail: what each layer does, what technology is used, how ingest becomes retrieval, where embeddings and vector stores fit, and which prompts control the final reply style.

The important idea: this is not only a chatbot. It is a catalog-grounded retail answer system. The model can make the reply sound human, but product facts must come from catalog, policy, order, or POS evidence.

## Pipeline Diagram

![Inventory RAG pipeline flow](docs/assets/rag_pipeline_flow.svg)

## What RAG Means In This Bot

RAG means Retrieval-Augmented Generation.

For this inventory bot, it means:

1. Product and policy data are stored as structured evidence.
2. The user asks a natural question in Bangla, English, or Banglish.
3. The system retrieves the most relevant products or policy facts.
4. The answer layer writes a customer-friendly reply using only that retrieved evidence.
5. Verification and critic layers try to prevent hallucinated stock, price, size, product, delivery, or refund claims.

This is different from a normal LLM chatbot. A normal chatbot may answer from model memory. This bot should answer from the shop's actual inventory.

## Current Pipeline In One Line

```text
catalog/POS/policy data
  -> normalize
  -> searchable text
  -> embeddings
  -> vector store
  -> customer query
  -> Banglish + intent + slots
  -> structured filters + retrieval
  -> reranking
  -> evidence contract
  -> answer plan
  -> prompt-based reply writing
  -> grounding check
  -> final UI answer
  -> feedback + traces
```

## Two Pipelines Run Together

There are two related pipelines in the current codebase.

| Pipeline | Purpose | Main path |
| --- | --- | --- |
| Inventory RAG pipeline | General inventory search, vector retrieval, evidence packing, answer planning | `InventoryService.ask()` -> `_search_with_trace_diagnostics()` -> `_semantic_search()` -> `_build_answer()` -> `_finalize_inventory_reply()` |
| Fashion retail structured pipeline | Fast boutique logic for saree, bag, shoes, cosmetics, size, same-design, styling, accessory matching | `InventoryService.ask()` -> `_try_fashion_retail_ask()` -> `FashionRetailAssistant.answer()` |

Strategic point: for fashion retail, structured fields are more important than embeddings. Size, gender, category, stock, and design family must be exact. Embeddings help recall, but they should not override hard inventory facts.

## Layer-By-Layer Breakdown

| Layer | What it does | Main files |
| --- | --- | --- |
| Frontend chat | Sends user question, history, session id, focused products, API key; renders answer and catalog panel | `frontend/chat.html`, `frontend/chat.js`, `frontend/chat.css` |
| API routing | Validates request and routes to service | `app/api/routes_inventory.py`, `app/api/routes_orders.py`, `app/api/routes_feedback.py` |
| Service orchestration | Controls small talk, policy shortcut, memory, search, fashion path, answer finalization, traces | `app/services/inventory_service.py` |
| Catalog storage | Stores product records | `data/inventory/catalog.jsonl` |
| Policy storage | Stores delivery/payment/refund/exchange facts | `data/inventory/policies.json` |
| POS sync | Imports CSV/webhook inventory updates and writes audit records | `app/inventory/pos_sync.py`, `data/inventory/sync_audit.jsonl` |
| Search text builder | Converts product fields into text for embedding/search | `InventoryService._build_search_text()` |
| Embedder | Converts search text and query text into vectors | `app/retrieval/embedder.py` |
| Vector store | Stores and queries vectors | `app/retrieval/local_store.py`, `app/retrieval/elasticsearch_store.py` |
| Fashion retail brain | Extracts retail slots and handles variants, sizes, accessories, comparison, styling | `app/inventory/fashion_retail.py` |
| Banglish normalization | Expands romanized Bangla into usable search signals | `app/inventory/banglish_normalizer.py` |
| Reranking | Scores candidates based on product fit, price, stock, specs, exact terms | `app/inventory/reranker.py`, service reranking logic |
| Evidence contract | Converts selected products into allowed facts and risk notes | `app/inventory/evidence_contract.py` |
| Answer planner | Decides primary, alternative, cross-sell, caveats, follow-up | `app/inventory/planner.py` |
| Prompt writer | Writes the final customer-facing text | `app/inventory/natural_answer.py`, `InventoryService._build_inventory_answer_messages()` |
| Critic/verification | Checks if the answer ignored facts or invented claims | `app/inventory/answer_critic.py`, `InventoryService._verify_answer_plan()` |
| Feedback/traces | Stores bad/good feedback and trace logs for improvement | `app/api/routes_feedback.py`, `results/traces/` |

## Index-Time Pipeline

Index-time is when inventory data becomes searchable.

### 1. Source Data

Current inventory sources:

| Source | File/API |
| --- | --- |
| Manual/sample catalog | `data/inventory/catalog.jsonl` |
| Product upsert API | `POST /inventory/items/upsert` |
| POS CSV-style import | `POST /inventory/sync/import` |
| POS webhook | `POST /inventory/sync/webhook` |
| Full rebuild | `POST /inventory/sync/rebuild` |

The product schema should include structured fields like:

- `product_id`
- `name`
- `sku`
- `category`
- `brand`
- `price`
- `stock`
- `status`
- `attributes.color`
- `attributes.color_family`
- `attributes.size`
- `attributes.available_sizes`
- `attributes.gender`
- `attributes.fabric`
- `attributes.occasion`
- `attributes.design_id`
- `metadata.variant_group_name`
- `include_in_rag`

If these fields are missing, the bot becomes weaker because it has to guess from free text.

### 2. Catalog Validation

The service validates whether products are usable for RAG and sync:

| Check | Why |
| --- | --- |
| Product exists in catalog | Prevents stale vector records |
| `include_in_rag` is true | Only searchable products are indexed |
| Product id is stable | Needed for deterministic document/vector ids |
| Required product facts exist | Prevents unsupported answers |
| Vector index is synced | Ensures search matches current catalog |

Relevant code:

- `InventoryService.sync_status()`
- `InventoryService.sync_validate()`
- `InventoryService.sync_rebuild()`

### 3. Search Text Construction

Each product is converted into one rich searchable string.

Code:

```text
InventoryService._build_search_text()
```

It combines:

- product name
- SKU
- category
- brand
- short description
- full description
- status
- tags
- attributes
- metadata
- curated numeric/text metadata
- alias text

Example shape:

```text
Maroon Bridal Katan Saree SKU123 saree Sonjoy Boutique in_stock
color maroon fabric katan occasion wedding work_type zari
variant group bridal katan design...
```

This rich text is what the embedder sees.

### 4. Embedding

The embedder converts search text into vectors.

Code:

```text
app/retrieval/embedder.py
```

Supported embedding providers:

| Provider | Env value | Use |
| --- | --- | --- |
| OpenAI-compatible | `EMBEDDING_PROVIDER=openai` | External embedding API |
| Transformers | `EMBEDDING_PROVIDER=transformers` | Local model such as `BAAI/bge-m3` |
| Deterministic | `EMBEDDING_PROVIDER=deterministic` | Fast local hash embeddings for tests/dev |
| Multilingual | `EMBEDDING_PROVIDER=multilingual` | Sentence-transformers multilingual fallback path |

Current config file default:

```yaml
embeddings:
  provider: transformers
  model_name: BAAI/bge-m3
```

Local demo runs may override this to deterministic embeddings for speed:

```bash
EMBEDDING_PROVIDER=deterministic
EMBEDDING_MODEL_NAME=deterministic-live
EMBEDDING_DIMENSIONS=256
```

Blunt truth: deterministic embeddings are good for tests and wiring checks, but not real semantic quality. For stronger Bangla/Banglish retrieval, use a real multilingual embedding model.

### 5. Vector Record Creation

Each searchable product becomes a `VectorRecord`.

Code:

```text
InventoryService._build_vector_record()
```

Stored fields:

- `record_id`: product id
- `vector`: embedded search text
- `text`: search text
- `namespace`: inventory namespace
- `metadata.product_id`
- `metadata.sku`
- `metadata.name`
- `metadata.category`
- `metadata.category_key`
- `metadata.brand`
- `metadata.brand_key`
- `metadata.status`
- `metadata.status_key`
- `metadata.stock`
- `metadata.price`
- `metadata.currency`
- `metadata.include_in_rag`
- `metadata.updated_at`
- curated metadata

### 6. Vector Store

Vector store providers:

| Provider | Env | File |
| --- | --- | --- |
| Local JSONL vector store | `VECTOR_DB=local` | `app/retrieval/local_store.py` |
| Elasticsearch | `VECTOR_DB=elasticsearch` | `app/retrieval/elasticsearch_store.py` |
| Pinecone | `VECTOR_DB=pinecone` | `app/retrieval/pinecone_store.py` |
| Milvus | `VECTOR_DB=milvus` | `app/retrieval/milvus_store.py` |

Current local store path:

```text
data/agentic_store/local_vectors.jsonl
```

Elasticsearch config:

```bash
VECTOR_DB=elasticsearch
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX_NAME=inventory-rag
```

Elasticsearch stores dense vectors with metadata and supports:

- `knn` vector search
- lexical search through `lexical_query()`
- namespace filtering
- deterministic document ids: `namespace::record_id`
- filter operators: `$eq`, `$in`, `$gte`, `$lte`

## Query-Time Pipeline

Query-time is when a customer asks something.

### 1. Frontend Request

The current chat UI sends:

```json
{
  "question": "eid er jonno 5000 er moddhe elegant saree dekhan",
  "top_k": 5,
  "assistant_mode": "support",
  "reply_style": "short",
  "answer_engine": "auto",
  "conversation_history": [],
  "focused_product_ids": [],
  "last_answer_plan": null,
  "session_id": "browser-session"
}
```

Valid values:

| Field | Values |
| --- | --- |
| `assistant_mode` | `support`, `sales` |
| `reply_style` | `short`, `detailed` |
| `answer_engine` | `auto`, `deterministic`, `natural` |

Frontend default:

```text
assistant_mode = support
reply_style = short
```

### 2. FastAPI Route

Endpoint:

```text
POST /inventory/ask
```

Main route file:

```text
app/api/routes_inventory.py
```

The route validates schema and calls:

```text
get_inventory_service().ask(request)
```

### 3. Small Talk And Policy Shortcut

Before expensive retrieval, the service checks:

| Shortcut | Example | Outcome |
| --- | --- | --- |
| Small talk | `hello`, `thanks` | deterministic conversational answer |
| Policy QA | `Dhaka delivery charge koto?`, `COD hobe?` | answer from `policies.json` |

Relevant code:

- `InventoryService._build_conversational_reply()`
- `InventoryService._try_policy_qa()`
- `app/inventory/policy_qa.py`

### 4. Memory And Context Resolution

The service receives:

- `conversation_history`
- `focused_product_ids`
- `last_answer_plan`
- `active_filters`
- `session_id`

It uses them only when the current question is a safe follow-up.

Example:

```text
Customer: eta blue color e ache?
```

If the last answer showed a specific saree, the system may resolve `eta` to that product. But if the new query says `office bag dekhan`, old saree context should not hijack it.

Relevant files:

- `app/inventory/memory.py`
- `app/inventory/conversation_state.py`
- `app/inventory/coreference_resolver.py`

### 5. Fashion Retail Structured Path

This is the main path for boutique questions.

Entry:

```text
InventoryService._try_fashion_retail_ask()
```

Core:

```text
FashionRetailAssistant.answer()
```

This path handles:

- fashion search
- size availability
- same-design color variants
- accessory matching
- styling advice
- product comparison
- multi-brand clarification
- no-match abstention

It extracts:

- language
- category
- color
- color family
- fabric
- size
- gender
- occasion
- budget
- design id
- stock intent

Important rule: hard retail facts win over semantic similarity.

For example:

- If customer asks for `men`, do not return women's products.
- If customer asks for `size 39`, do not return size 38 as available.
- If customer asks for `same design`, use `design_id`/variant group first.
- If no matching product exists, say no match.

### 6. LLM Intent Classifier

Optional LLM-first intent and slot classification.

File:

```text
app/inventory/llm_intent_classifier.py
```

Prompt variable:

```text
_PROMPT
```

Technology:

- Ollama HTTP API
- default model: `qwen3:8b`
- output: strict JSON

It classifies:

- `fashion_search`
- `fashion_compare`
- `fashion_styling_advice`
- `fashion_variant_color`
- `fashion_size_availability`
- `fashion_accessory_match`
- policy intents
- order intents
- small talk
- unknown

If Ollama fails, the code falls back to deterministic regex/slot logic.

### 7. Generic Inventory RAG Search Path

If the fashion retail layer does not handle the question, the service runs the generic inventory retrieval path.

Entry:

```text
InventoryService._search_with_trace_diagnostics()
InventoryService._semantic_search()
```

The generic RAG search combines:

1. Dense vector search
2. Local lexical matching
3. Elasticsearch lexical search if the vector backend supports it
4. Product type gating
5. Category gating
6. Exact lookup gating
7. Spec filtering
8. Deterministic ecommerce reranking

### 8. Dense Retrieval

Dense retrieval embeds the customer query and searches the vector store.

Code:

```text
InventoryService._dense_candidate_scores()
```

Steps:

1. `self.embedder.embed_text(query_text)`
2. Build vector filters from request filters.
3. Query vector store:

```text
self.vector_store.query(query_vector, top_k=candidate_limit, filters=..., namespace=...)
```

Vector filters can include:

- product ids
- categories
- brands
- statuses
- min/max stock
- min/max price

### 9. Lexical Retrieval

The service also does lexical matching because inventory questions often contain exact words:

- SKU
- product names
- color words
- size terms
- category words

Code paths:

- local lexical scoring inside `InventoryService._lexical_candidate_scores()`
- optional Elasticsearch lexical query via `ElasticsearchVectorStore.lexical_query()`

This is important because vector search alone can be too fuzzy for inventory.

### 10. Candidate Merging And Gating

The system merges lexical and vector candidates, then rejects weak matches.

Gates include:

| Gate | Purpose |
| --- | --- |
| Spec gate | Rejects products that do not satisfy explicit specs |
| Product-type gate | Keeps products in the requested product family |
| Category gate | Enforces explicitly requested category |
| Exact lookup gate | Prevents answering exact product questions with loose semantic neighbors |
| Lexical anchor gate | Keeps exact-text evidence when the query has strong named references |

This is why the bot should not answer `bag` with a `saree` just because both appear in wedding context.

### 11. Reranking

After merging and gating, the system reranks candidates by:

- final ecommerce score
- query term coverage
- product relation score
- lexical score
- vector score
- stock status
- quality score
- price sorting

Relevant files:

- `app/inventory/reranker.py`
- `app/inventory/decisioning.py`
- service-level `_semantic_search()`

### 12. Evidence Contract

The answer is not allowed to use arbitrary product facts. It gets an evidence contract.

File:

```text
app/inventory/evidence_contract.py
```

The evidence contract includes:

- candidate evidence
- primary product id
- selected facts
- inclusion reasons
- rejection reasons
- missing facts
- contradictions
- follow-up question rules

This is the safety layer between retrieval and answer writing.

### 13. Answer Plan

The answer planner decides what role each product plays.

File:

```text
app/inventory/planner.py
```

The answer plan can contain:

- primary product
- alternative products
- cross-sell products
- excluded products
- primary reason
- alternative reason
- tradeoffs
- risk notes
- next best question
- confidence breakdown
- abstention reason

This is the main object that the prompt writer must obey.

## Prompt Layers

There is not one prompt. There are several prompts for different jobs.

| Prompt layer | File | What it controls |
| --- | --- | --- |
| Intent + slot prompt | `app/inventory/llm_intent_classifier.py` | Intent, category, color, fabric, size, budget, language |
| Candidate reasoner prompt | `app/inventory/llm_reasoner.py` | Which products to pick from an already retrieved candidate list |
| Natural answer prompt | `app/inventory/natural_answer.py` | Warm boutique-style final wording for fashion path |
| Heavy writer prompt | `InventoryService._build_inventory_answer_messages()` | Strict final answer writer using answer plan and evidence package |
| Answer critic prompt | `app/inventory/answer_critic.py` | Checks hallucination, ignored constraints, wrong language |
| Soft confirm messages | `app/inventory/soft_confirm.py` | Adds medium-confidence confirmation tails |
| Escalation messages | `app/inventory/escalation.py` | Human handoff language |

## Which Prompt Should You Adjust?

| Goal | Edit this | Do not edit this first |
| --- | --- | --- |
| Make replies warmer and more human | `app/inventory/natural_answer.py` `_SYSTEM_PROMPT` | Retrieval/reranking code |
| Make Banglish replies sound more natural | `app/inventory/natural_answer.py` examples and language rules | Vector store |
| Fix wrong intent/category detection | `app/inventory/llm_intent_classifier.py` `_PROMPT` and category vocabulary | Natural answer prompt |
| Fix wrong product choice from valid candidates | `app/inventory/llm_reasoner.py` `_PROMPT` or deterministic scoring | Final wording prompt |
| Prevent hallucinated stock/price | `app/inventory/answer_critic.py` and service writer contract | Tone examples only |
| Change short vs detailed style | `_build_inventory_writer_guidance()` and `reply_style` handling | Product data |
| Change support vs sales style | `_build_inventory_answer_messages()` sales/support system prompt suffix | Embedder |
| Fix no-match behavior | Fashion retail abstention logic and answer contract | LLM temperature |

## Reply Prompt: Lightweight Natural Answer

File:

```text
app/inventory/natural_answer.py
```

Main prompt variable:

```text
_SYSTEM_PROMPT
```

Current job:

- act like a warm boutique assistant
- answer in same language
- use only provided products
- mention price and stock
- keep simple answers short
- ask a natural follow-up question

This is the best first place to tune tone.

Example improvement:

```text
Add:
- For Banglish, use friendly Dhaka shop tone, but do not overdo slang.
- Start with the direct answer first: "Ji ache" / "Eta available" / "Ei budget e best options..."
- If multiple products match, show maximum 3.
- If no exact match, say it clearly and ask one narrowing question.
```

Keep this rule:

```text
Use ONLY the product information provided below. Never mention products not listed.
```

Do not remove that rule.

## Reply Prompt: Heavy Writer Contract

File:

```text
app/services/inventory_service.py
```

Function:

```text
InventoryService._build_inventory_answer_messages()
```

This builds the strict writer prompt with:

- question
- assistant mode
- reply style
- conversation summary
- memory resolution
- draft reply
- writer contract
- answer plan
- verification result
- reasoning summary
- missing facts
- retrieved hits

The system prompt says the writer must:

- obey `answer_plan`
- obey `writer_contract`
- not add/reorder products
- not invent facts
- not expose internal ids
- ask at most one follow-up question
- return strict JSON

Use this prompt when you need stricter grounded output.

Good edits here:

```text
For customer-facing retail answers, lead with the direct answer in the user's language.
If the query is Banglish, keep the answer Banglish unless policy text is clearer in English.
Use bullet points only when showing 2 or more product options.
Do not mention internal confidence, trace, answer_plan, evidence package, or database.
```

Bad edits here:

```text
Always recommend something.
Never say no match.
Make up alternatives.
Ignore stock if the product is attractive.
```

Those would break inventory correctness.

## Intent Prompt

File:

```text
app/inventory/llm_intent_classifier.py
```

Prompt variable:

```text
_PROMPT
```

Use this when the bot misunderstands questions like:

- `amar office ache bag dekhan`
- `same design e onno color ache?`
- `biye er jonno saree`
- `men section e perfume ache?`

Good adjustment:

```text
Add more examples for your real customer language:

Input: "amar office ache amake kichu bag dekhan"
Output: {"intent":"fashion_search","category":"bag","occasion":"office","language":"banglish",...}

Input: "amar biye kichu saree dekhan"
Output: {"intent":"fashion_search","category":"saree","occasion":"wedding","language":"banglish",...}
```

Do not overload this prompt with final answer style. Its job is classification, not customer response.

## Candidate Reasoner Prompt

File:

```text
app/inventory/llm_reasoner.py
```

Prompt variable:

```text
_PROMPT
```

This only chooses from candidates already retrieved.

Use it when:

- retrieval finds good products but the top order feels wrong
- occasion/styling nuance matters
- the customer gives soft intent like `elegant`, `simple`, `premium`, `office`, `gift`

Do not let it invent products. It must select product ids from the candidate list.

Good adjustment:

```text
Prefer products that match the customer's occasion and budget over visually similar but less suitable products.
For office use, prefer sober colors, practical size, and daily-use materials.
For wedding use, prefer festive fabric, richer work type, and premium look.
```

## Answer Critic Prompt

File:

```text
app/inventory/answer_critic.py
```

Prompt variable:

```text
_PROMPT
```

This checks:

- unsupported facts
- wrong stock claim
- wrong product name
- ignored budget/color/size/occasion
- wrong language

Use it to make the bot stricter.

Example improvement:

```text
Mark as major if the answer recommends an item outside the customer's requested gender.
Mark as major if the answer says "available" for stock <= 0.
Mark as major if the answer recommends products not present in Product facts.
```

## Runtime Controls

Important settings:

| Env var | Meaning |
| --- | --- |
| `INVENTORY_NATURAL_ANSWERS_ENABLED` | Enables/disables natural LLM answer writing |
| `INVENTORY_NATURAL_ANSWER_MODEL_NAME` | Model for natural answer |
| `INVENTORY_NATURAL_ANSWER_TEMPERATURE` | Higher = more creative, lower = safer |
| `INVENTORY_NATURAL_ANSWER_MAX_TOKENS` | Max answer length |
| `INVENTORY_NATURAL_ANSWER_MIN_CONFIDENCE` | Below this, use deterministic answer |
| `INVENTORY_NATURAL_ANSWER_TIMEOUT_SECONDS` | Timeout before fallback |
| `INVENTORY_NATURAL_ANSWER_FEW_SHOT_ENABLED` | Enables style examples |
| `BOT_ENABLE_LLM_INTENT` | Enables LLM intent/slot classifier |
| `BOT_ENABLE_LLM_REASONER` | Enables LLM candidate picker |
| `BOT_ENABLE_ANSWER_CRITIC` | Enables self-critique |
| `BOT_ENABLE_SEMANTIC_MATCHER` | Enables embedding-based catalog fallback |
| `BOT_ENABLE_NATURAL_ANSWER` | Enables natural language answer layer |
| `BOT_ENABLE_SOFT_CONFIRM` | Adds confirmation text on medium confidence |
| `BOT_ENABLE_ESCALATION` | Enables human handoff behavior |

Safer production settings:

```bash
INVENTORY_NATURAL_ANSWER_TEMPERATURE=0.1
INVENTORY_NATURAL_ANSWER_MAX_TOKENS=220
INVENTORY_NATURAL_ANSWER_MIN_CONFIDENCE=0.55
BOT_ENABLE_ANSWER_CRITIC=true
```

Faster deterministic test settings:

```bash
INVENTORY_NATURAL_ANSWERS_ENABLED=false
BOT_ENABLE_NATURAL_ANSWER=false
BOT_ENABLE_ANSWER_CRITIC=false
```

## Technology Stack

| Part | Technology |
| --- | --- |
| API | Python, FastAPI |
| Runtime | Uvicorn |
| UI | HTML, CSS, JavaScript |
| Catalog | JSONL |
| Policy | JSON |
| Orders | JSONL |
| Embedding providers | Transformers, OpenAI-compatible, deterministic, multilingual |
| Default embedding model in config | `BAAI/bge-m3` |
| Local LLM | Ollama |
| Default local LLM in prompts | `qwen3:8b` |
| Vector store now | Local JSONL vector store |
| Optional vector store | Elasticsearch 8.x |
| Image matching | Metadata matcher, optional CLIP |
| Tests | Pytest |

## Local Vector Store vs Elasticsearch

| Choice | Good for | Tradeoff |
| --- | --- | --- |
| Local vector store | Small catalog, dev, simple demo | Not ideal for large multi-brand catalog |
| Elasticsearch | Larger catalog, metadata filters, lexical + vector search, production-like search | Needs ES server and index management |

For the current 47-item sample catalog, local vector store is enough. For real boutique scale with many categories, brands, colors, sizes, and POS sync, Elasticsearch is the better direction.

## Current Config Reality

The config file says:

```yaml
embeddings:
  provider: transformers
  model_name: BAAI/bge-m3
vector_store:
  provider: local
  local_store_path: data/agentic_store/local_vectors.jsonl
inventory_chat:
  natural_answers_enabled: true
  natural_answer_model_name: qwen3:8b
```

But the actual runtime can be overridden by environment variables. To know what is running right now, check:

```text
GET /health/config
GET /inventory/status
GET /inventory/sync/status
```

## Recommended Reply Tuning Plan

Do this in order:

1. Tune deterministic structured behavior first.
   - Fix category, size, gender, stock, variant, and budget logic in `fashion_retail.py`.
2. Tune intent prompt second.
   - Add real Bangla/Banglish examples in `llm_intent_classifier.py`.
3. Tune product selection third.
   - Adjust `llm_reasoner.py` only after retrieval returns valid candidates.
4. Tune final wording fourth.
   - Edit `natural_answer.py` and writer guidance.
5. Tighten the critic last.
   - Make `answer_critic.py` stricter when hallucinations appear.

Reason: if retrieval is wrong, a nicer prompt will only make wrong answers sound confident. Fix evidence first, tone second.

## Example Final Answer Style Target

For Banglish:

```text
Ji, office use er jonno 2ta bag match korche:
1. Everyday Black Tote Bag — BDT 1,650, stock 8
2. Tan Structured Shoulder Bag — BDT 2,250, stock 5

Daily office er jonno black tote ta beshi practical, karon eta neutral color and regular use er jonno suitable. Apni ki laptop carry korben, naki normal daily essentials?
```

For no match:

```text
Ei exact request er jonno current catalog e match pacchi na. Apni category ta bolben: saree, bag, shoes, cosmetics, na men section?
```

For strict policy:

```text
Dhaka city delivery charge BDT 80. BDT 5,000 er upore order hole free delivery available. Apni ki Dhaka city er moddhe delivery chan?
```

## Red Lines

Never tune prompts to do these:

- answer without catalog evidence
- hide out-of-stock status
- invent unavailable colors
- invent sizes
- invent discounts
- invent delivery promises
- recommend unrelated products after no match
- use old context when the customer starts a new category

Those are not style issues. Those are trust failures.

## Best Summary For Your Boss

The bot uses a RAG pipeline where product data is converted into searchable evidence, embedded into a vector store, retrieved with structured and semantic search, reranked, turned into an evidence contract, and then written as a human-friendly answer through controlled prompts. The key technology is FastAPI, JSONL catalog storage, local or Elasticsearch vector search, transformer/deterministic embeddings, Ollama for optional language reasoning, and strict verification to avoid hallucinated inventory claims.

