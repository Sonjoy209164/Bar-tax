# Theory Of The Inventory RAG Pipeline

This document is for learning the theory behind the current inventory chatbot pipeline.

The goal is to understand why each layer exists, not just where the code lives.

## Pipeline Flowchart

![Inventory RAG pipeline flow](docs/assets/rag_pipeline_flow.svg)

This diagram shows the full loop: product data ingestion, normalization, embedding, vector storage, customer question understanding, retrieval, reranking, evidence contract, answer generation, verification, and feedback.

## The Big Idea

A normal chatbot answers from what the model has learned during training.

An inventory chatbot cannot do that safely.

Why?

Because inventory facts change:

- stock changes
- price changes
- color availability changes
- size availability changes
- delivery policy changes
- refund policy changes
- product catalog changes

So the bot must not answer from memory. It must answer from current business data.

That is the reason we use RAG.

```text
RAG = Retrieval-Augmented Generation
```

In simple words:

```text
First retrieve facts.
Then generate the answer.
```

The model should not be the source of truth. The catalog should be the source of truth.

## The Core Theory

The inventory bot has three jobs:

1. Understand what the customer wants.
2. Find the correct evidence from inventory and policy data.
3. Write a helpful answer without inventing anything.

This gives us the theoretical pipeline:

```text
Question understanding
  -> Evidence retrieval
  -> Evidence ranking
  -> Decision planning
  -> Safe answer generation
  -> Verification
```

If any layer fails, the final answer can fail.

## Why Prompting Alone Is Not Enough

This is the most important lesson.

If the catalog retrieval is wrong, a better prompt will only make a wrong answer sound more confident.

Example:

```text
Customer: office er jonno bag dekhan
Bad retrieval: sarees and clutches
Good prompt: "Be warm and helpful"
Final result: a warm, helpful, wrong answer
```

Prompt quality matters, but evidence quality matters more.

Correct order of work:

1. Structure the catalog.
2. Retrieve the right products.
3. Rank the right products.
4. Generate a nice answer.
5. Verify the answer.

Do not reverse this order.

## Mental Model

Think of the bot like a trained shop assistant.

The assistant has:

- shelves: product catalog
- labels: structured product fields
- memory: current conversation
- rules: delivery/payment/refund policy
- search skill: retrieval
- judgment: reranking and retail reasoning
- speech: answer generation
- supervisor: verification and critic

The assistant should speak beautifully, but only after checking the shelf.

## Full Theoretical Flow

```text
Product data
  -> cleaned and structured
  -> converted into searchable text
  -> converted into vectors
  -> stored in vector/search index

Customer question
  -> language detection
  -> intent detection
  -> slot extraction
  -> structured filters
  -> vector/lexical retrieval
  -> candidate merging
  -> reranking
  -> evidence contract
  -> answer plan
  -> prompt-based answer
  -> grounding verification
  -> final customer response
```

## Technology Used In Each Stage

This is how the theory maps to the actual technology in this project.

| Stage | What happens | Technology used now |
| --- | --- | --- |
| Product data | Stores catalog items, price, stock, category, attributes | JSONL: `data/inventory/catalog.jsonl` |
| Policy data | Stores delivery, payment, refund, exchange rules | JSON: `data/inventory/policies.json` |
| POS/input sync | Imports inventory updates | FastAPI endpoints, CSV-style import, webhook sync in `app/inventory/pos_sync.py` |
| API layer | Receives chat/search/order requests | Python, FastAPI, Pydantic schemas |
| Frontend | Customer chat and catalog panel | HTML, CSS, JavaScript |
| Data validation | Checks request and product shape | Pydantic models in `app/core/schemas.py` |
| Search text creation | Converts product JSON into searchable text | Python service logic: `InventoryService._build_search_text()` |
| Bangla/Banglish normalization | Converts customer wording into usable signals | Python rule/dictionary layer: `app/inventory/banglish_normalizer.py` |
| Intent detection | Understands question type | Python rules + optional Ollama LLM classifier using `qwen3:8b` |
| Slot extraction | Extracts category, size, color, budget, occasion, gender | Python regex/rules + optional Ollama JSON classifier |
| Embedding | Converts text into vectors | Transformers/OpenAI-compatible/deterministic/multilingual embedders in `app/retrieval/embedder.py` |
| Default embedding config | Local semantic embedding option | `BAAI/bge-m3` in `config/config.dev.yaml` |
| Dev/test embedding | Fast local wiring check | Deterministic hash embeddings |
| Vector storage | Stores product vectors | Local JSONL vector store or Elasticsearch 8.x |
| Local vector store | Small catalog/dev search | `data/agentic_store/local_vectors.jsonl`, `app/retrieval/local_store.py` |
| Elasticsearch vector store | Scalable vector + lexical retrieval | `app/retrieval/elasticsearch_store.py` |
| Lexical search | Exact words, SKU, product name matching | Python lexical scoring + optional Elasticsearch lexical query |
| Metadata filters | Enforces category, brand, stock, price filters | Python filters + vector store filters: `$eq`, `$in`, `$gte`, `$lte` |
| Fashion retail reasoning | Handles saree/bag/size/design/accessory/styling logic | `app/inventory/fashion_retail.py` |
| Candidate reranking | Sorts retrieved products by usefulness | Custom Python ecommerce reranker and decisioning logic |
| Evidence contract | Defines what facts the answer can use | Pydantic/Python layer: `app/inventory/evidence_contract.py` |
| Answer plan | Decides primary product, alternatives, caveats, next question | `app/inventory/planner.py` |
| Natural answer writing | Makes response warm and human | Deterministic templates + optional Ollama prompt in `app/inventory/natural_answer.py` |
| Strict answer writer | Writes final grounded JSON answer from evidence package | Prompt builder in `InventoryService._build_inventory_answer_messages()` |
| Verification | Checks unsupported claims and answer safety | Python verifier + optional Ollama critic in `app/inventory/answer_critic.py` |
| Conversation memory | Resolves follow-up references safely | Conversation state, profile store, memory resolver |
| Orders | Draft, update, confirm, track orders | FastAPI order routes + JSONL order store |
| Feedback | Stores thumbs up/down for improvement | FastAPI feedback route + JSONL feedback store |
| Testing | Checks regressions and behavior | Pytest |

Short version:

```text
FastAPI + Pydantic
+ JSONL/JSON catalog and policy stores
+ Python retail reasoning
+ Transformers/deterministic embeddings
+ Local vector store or Elasticsearch
+ Ollama qwen3:8b for optional reasoning and natural wording
+ Pytest for verification
```

## Logic And Code Map For Each Stage

This table connects the theory to the exact implementation points. Use it when you want to understand or modify a stage.

| Stage | Logic being done | Main code files/functions | Prompt used? |
| --- | --- | --- | --- |
| Frontend chat | Collects user question, API key, session id, history, focused products, and sends request to backend | `frontend/chat.js`; chat submit payload around `assistant_mode`, `reply_style`, `conversation_history`, `focused_product_ids` | No prompt |
| API validation | Validates request body and returns typed response | `app/api/routes_inventory.py` -> `ask_inventory()`; `app/core/schemas.py` -> `InventoryAskRequest`, `InventoryAskResponse` | No prompt |
| Service orchestration | Chooses whether to answer by small talk, policy, fashion retail path, or generic RAG search | `app/services/inventory_service.py` -> `InventoryService.ask()` | No direct prompt |
| Small talk | Detects greetings, thanks, help, goodbye, simple identity questions | `InventoryService._build_conversational_reply()` | No prompt; deterministic text |
| Policy QA | Detects delivery/payment/refund/exchange questions and answers from policy data | `InventoryService._try_policy_qa()`; `app/inventory/policy_qa.py` | No LLM prompt in normal path; policy templates/rules |
| Memory/context | Resolves follow-ups like `eta`, `same design`, `first one`; avoids old context for new category queries | `app/inventory/memory.py`; `app/inventory/conversation_state.py`; `app/inventory/coreference_resolver.py`; `InventoryService._try_fashion_retail_ask()` | No main prompt; optional planner can use LLM |
| Intent planner | For deeper multi-turn questions, reads conversation/profile/state and decides if clarification is needed | `app/inventory/intent_planner.py`; called inside `InventoryService._try_fashion_retail_ask()` | Yes, if Ollama planner is available |
| Banglish normalization | Expands words like `biye`, `eid`, `dekhan`, `katan`, `ache` into searchable retail meaning | `app/inventory/banglish_normalizer.py`; used by `app/inventory/fashion_retail.py` | No prompt; dictionary/rule logic |
| LLM intent + slot extraction | Classifies intent and extracts category, color, fabric, size, brand, budget, occasion, language | `app/inventory/llm_intent_classifier.py` -> `classify_intent_llm()`; called by `FashionRetailAssistant._merge_llm_classification()` | Yes: `_PROMPT` in `llm_intent_classifier.py` |
| Regex/rule slot extraction | Fallback extraction when LLM is unavailable or uncertain | `app/inventory/fashion_retail.py` -> `_extract_slots()`, `_classify_intent()`, `_extract_size()`, `_extract_gender()` | No prompt |
| Fashion retail routing | Dispatches to exact retail handlers: search, variant color, size, accessory, compare, styling | `app/inventory/fashion_retail.py` -> `FashionRetailAssistant.answer()` | No direct prompt; structured logic |
| Same-design color | Uses `design_id` / variant group to find other colors in same design family | `FashionRetailAssistant._answer_variant_color()` | No prompt |
| Size availability | Checks exact size and stock before wording answer | `FashionRetailAssistant._answer_size_availability()` | No prompt |
| Accessory matching | Matches bags/jewelry/shoes using compatible design/color/category metadata | `FashionRetailAssistant._answer_accessory_match()` | No prompt |
| Styling advice | Builds outfit/styling recommendation from catalog-backed products | `FashionRetailAssistant._answer_styling_advice()` | Mostly deterministic; can later be prompt-enhanced |
| Compare | Compares product/fabric options by price, fabric, occasion, stock | `FashionRetailAssistant._answer_fashion_compare()`, `_compare_by_fabric()` | No prompt |
| Catalog load | Reads product records from JSONL or mirror store | `InventoryService._load_catalog()`; `data/inventory/catalog.jsonl` | No prompt |
| Catalog upsert/delete | Saves catalog changes and updates/deletes vector records | `InventoryService.upsert_items()`, `InventoryService.delete_items()` | No prompt |
| Sync rebuild | Rebuilds vector index from all `include_in_rag=true` catalog products | `InventoryService.sync_rebuild()` | No prompt |
| Search text creation | Converts product facts into rich text for embedding/search | `InventoryService._build_search_text()`, `_build_curated_vector_metadata()`, `_build_curated_search_text()` | No prompt |
| Embedding | Converts product text/query text into vector numbers | `app/retrieval/embedder.py` -> `build_embedder()`, `TextEmbedder.embed_text()` | No prompt; model call depending on provider |
| Vector record creation | Builds `VectorRecord` with vector, text, namespace, metadata | `InventoryService._build_vector_record()` | No prompt |
| Local vector storage | Stores vectors in JSONL and does cosine/dot-product search | `app/retrieval/local_store.py` -> `LocalVectorStore.upsert()`, `query()`, `delete()` | No prompt |
| Elasticsearch vector storage | Stores vectors in dense vector index, supports `knn`, lexical query, filters | `app/retrieval/elasticsearch_store.py` -> `ElasticsearchVectorStore.upsert()`, `query()`, `lexical_query()` | No prompt |
| Dense retrieval | Embeds the query and retrieves similar vector records | `InventoryService._dense_candidate_scores()` | No prompt |
| Lexical retrieval | Scores exact term/name/SKU/category matches; optionally calls Elasticsearch lexical query | `InventoryService._lexical_candidate_scores()`, `_external_lexical_candidate_scores()`; `ElasticsearchVectorStore.lexical_query()` | No prompt |
| Product preference extraction | Extracts product type, specs, budget, quality, stock need for generic inventory search | `app/inventory/preferences.py`; called inside `InventoryService._semantic_search()` | No prompt |
| Candidate merging | Merges dense and lexical candidate ids into one candidate pool | `InventoryService._semantic_search()` | No prompt |
| Candidate gates | Rejects wrong specs, wrong product type, wrong category, weak exact lookup, weak lexical anchor | `InventoryService._semantic_search()` spec/type/category/exact/lexical gates | No prompt |
| Reranking | Scores candidates by ecommerce relevance, stock, price, specs, lexical/vector fit | `app/inventory/reranker.py`; `app/inventory/decisioning.py`; `InventoryService._semantic_search()` | No prompt |
| LLM candidate reasoner | For broad fashion search, picks best 1-3 candidates from already retrieved candidates | `app/inventory/llm_reasoner.py` -> `reason_over_candidates()`; called in `_try_fashion_retail_ask()` | Yes: `_PROMPT` in `llm_reasoner.py` |
| Search hit creation | Converts catalog product to response/search hit shape | `InventoryService._build_search_hit()`, `_fashion_retail_hits()` | No prompt |
| No-match/abstain | Decides when there is no safe catalog-backed answer | `InventoryService._build_no_match_or_abstain_reply()`; `FashionRetailAssistant` abstention outcomes | No prompt; deterministic safety logic |
| Evidence contract | Converts selected/rejected products into allowed facts, missing facts, contradictions, caveats | `app/inventory/evidence_contract.py` -> `InventoryEvidenceContractBuilder.build()` | No prompt |
| Answer planning | Decides primary product, alternatives, cross-sells, tradeoffs, risks, next question | `app/inventory/planner.py` -> `InventoryAnswerPlanner.enrich_plan()`; service `_build_inventory_answer_plan()`, `_enrich_answer_plan()` | No prompt |
| Deterministic answer | Builds a safe template answer without LLM wording | `FashionRetailAssistant._build_outcome()` and service `_build_answer()` family | No prompt |
| Lightweight natural answer | Rewrites product-backed answer warmly in Bangla/Banglish/English | `app/inventory/natural_answer.py` -> `generate_ollama_answer()`, `build_natural_answer_prompt()` | Yes: `_SYSTEM_PROMPT`, `_PRODUCT_CONTEXT_TEMPLATE`, few-shot examples |
| Heavy grounded writer | Builds strict evidence package and asks model to output final JSON answer | `InventoryService._build_inventory_answer_messages()`, `_run_inventory_answer_model()`, `_parse_inventory_answer_model_output()` | Yes: system prompt inside `_build_inventory_answer_messages()` |
| Writer guidance | Compresses answer-plan rules into response mode, mention sequence, caveats, forbidden moves | `InventoryService._build_inventory_writer_guidance()` | No separate prompt; becomes part of writer prompt payload |
| Answer verification | Verifies answer plan product roles and final answer safety | `InventoryService._verify_answer_plan()`, `_finalize_inventory_reply()` | No prompt for deterministic verification |
| LLM answer critic | Checks natural answer for hallucinated facts, wrong stock, ignored constraints, wrong language | `app/inventory/answer_critic.py` -> `critique_answer()` | Yes: `_PROMPT` in `answer_critic.py` |
| Soft confirmation | Adds a small confirmation tail for medium-confidence answers | `app/inventory/soft_confirm.py` | No main prompt; rule/template text |
| Escalation | Creates human handoff message after repeated failures or explicit request | `app/inventory/escalation.py` | No main prompt; rule/template text |
| Proactive cross-sell | Adds compatible add-on suggestion when safe | `app/inventory/proactive.py`; called in `_try_fashion_retail_ask()` | No prompt |
| Order workflow | Drafts, updates, confirms, cancels, tracks orders | `app/api/routes_orders.py`; `app/inventory/order_workflow.py`; `data/orders/orders_store.jsonl` | No prompt in API path |
| Image matching | Finds visually similar products or same-design variants | `app/inventory/image_matcher.py`; `app/inventory/clip_matcher.py` | No prompt; optional CLIP model |
| Feedback storage | Stores thumbs up/down and recent feedback report | `app/api/routes_feedback.py`; `data/feedback/feedback.jsonl` | No prompt |
| Trace logging | Saves execution path, selected/rejected hits, answer plan, fallback reason | `InventoryService._save_inventory_chat_trace()` | No prompt |
| Tests | Verifies regressions and adapter behavior | `tests/test_boutique_retail_catalog.py`, `tests/test_elasticsearch_store.py`, wider `tests/` suite | No prompt |

## Prompt Locations And Their Purpose

These are the exact prompt-bearing files in the current advanced inventory system.

| Prompt file/function | Prompt variable/function | Purpose | Safe things to edit |
| --- | --- | --- | --- |
| `app/inventory/llm_intent_classifier.py` | `_PROMPT` | Classify customer intent and extract slots as JSON | Add Bangla/Banglish examples, new categories, new occasions, confidence rules |
| `app/inventory/llm_reasoner.py` | `_PROMPT` | Pick best products from a candidate list | Add retail taste rules, occasion rules, office/wedding/gift preference rules |
| `app/inventory/natural_answer.py` | `_SYSTEM_PROMPT` | Make answer sound warm and human | Tone, length, language style, follow-up style |
| `app/inventory/natural_answer.py` | `_PRODUCT_CONTEXT_TEMPLATE` | Shows product facts to the natural answer model | Format product evidence more clearly |
| `app/inventory/natural_answer.py` | `_BANGLA_EXAMPLES` | Few-shot style examples | Add real Bangla/Banglish examples from your shop |
| `app/services/inventory_service.py` | `_build_inventory_answer_messages()` | Strict grounded writer prompt with answer plan and evidence package | Add wording rules without weakening factual constraints |
| `app/services/inventory_service.py` | `_build_inventory_few_shot_messages()` | Few-shot examples for heavy writer path | Add examples for no-match, comparison, budget, cross-sell, policy style |
| `app/inventory/answer_critic.py` | `_PROMPT` | Critiques answer for hallucination and ignored constraints | Make stricter on stock, gender, size, budget, unavailable variants |
| `app/inventory/intent_planner.py` | planner prompt logic | Multi-turn planning and clarification | Add examples for when to ask clarification vs search |

Do not use prompts to fix broken product data. If a product lacks `stock`, `price`, `size`, `gender`, or `design_id`, fix the catalog first.

## How A Customer Query Moves Through Code

Example query:

```text
office er jonno bag dekhan
```

Code flow:

```text
frontend/chat.js
  -> POST /inventory/ask
  -> app/api/routes_inventory.py::ask_inventory()
  -> InventoryService.ask()
  -> _build_conversational_reply()        # skipped unless small talk
  -> _try_policy_qa()                     # skipped unless policy question
  -> memory_resolver.resolve()
  -> _try_fashion_retail_ask()
  -> FashionRetailAssistant.answer()
  -> _extract_slots() / optional classify_intent_llm()
  -> _classify_intent()
  -> _answer_fashion_search()
  -> _rank_search_items()
  -> _build_outcome()
  -> _fashion_retail_hits()
  -> InventoryAnswerPlan(...)
  -> optional generate_ollama_answer()
  -> optional critique_answer()
  -> build_proactive_message() if safe
  -> decorate_with_soft_confirm()
  -> InventoryAskResponse
  -> frontend renders answer
```

Generic RAG query flow if fashion retail does not handle it:

```text
InventoryService.ask()
  -> _build_route_signals()
  -> _search_with_trace_diagnostics()
  -> _semantic_search()
  -> preference_extractor.extract()
  -> _dense_candidate_scores()
  -> vector_store.query()
  -> _lexical_candidate_scores()
  -> optional vector_store.lexical_query()
  -> merge lexical + dense candidates
  -> spec/type/category/exact/lexical gates
  -> ecommerce_reranker.score_product()
  -> returned hits
  -> _build_answer()
  -> _enrich_answer_plan()
  -> evidence_contract_builder.build()
  -> answer_planner.enrich_plan()
  -> _finalize_inventory_reply()
  -> optional heavy writer prompt
  -> _verify_answer_plan()
  -> response + trace
```

## Where To Edit For Common Problems

| Problem | First file to check | Why |
| --- | --- | --- |
| Wrong category returned | `app/inventory/fashion_retail.py` | Category extraction and hard filters live here |
| Banglish misunderstood | `app/inventory/banglish_normalizer.py`, `app/inventory/llm_intent_classifier.py` | Normalize words first; add classifier examples second |
| Wrong size answer | `FashionRetailAssistant._answer_size_availability()` | Size must be exact structured logic |
| Same design color fails | `FashionRetailAssistant._answer_variant_color()` and catalog `design_id` | Variant logic depends on structured design ids |
| Good candidates retrieved but bad one shown first | `app/inventory/llm_reasoner.py`, `app/inventory/reranker.py` | Selection/ranking problem |
| Answer sounds robotic | `app/inventory/natural_answer.py` | Tone prompt/template problem |
| Answer invents facts | `app/inventory/answer_critic.py`, `InventoryService._build_inventory_answer_messages()` | Critic and writer contract must be stricter |
| Random recommendation after no match | `InventoryService._build_no_match_or_abstain_reply()`, fashion abstention logic | Abstention policy problem |
| Search is weak for large catalog | `app/retrieval/elasticsearch_store.py`, embedding config | Retrieval infrastructure/model problem |
| Stock/price stale | POS sync and catalog source | Data freshness problem, not prompt problem |

## Stage 1: Product Data As Ground Truth

The catalog is the truth source.

For inventory RAG, a product record is not just text. It is a set of facts.

Example:

```json
{
  "product_id": "saree_001",
  "name": "Maroon Bridal Katan Saree",
  "category": "saree",
  "price": 7800,
  "stock": 3,
  "attributes": {
    "color": "maroon",
    "fabric": "katan",
    "occasion": "wedding",
    "design_id": "bridal_katan_01"
  }
}
```

The bot can safely say:

- it is a saree
- it is maroon
- it is katan
- it is for wedding
- price is BDT 7,800
- stock is 3

The bot cannot safely say:

- it has a discount
- it is available in blue
- it has size M
- delivery is free

unless those facts exist in evidence.

## Stage 2: Structured Fields

Inventory RAG needs structured fields because some questions require exact logic.

Examples:

| Customer asks | Required exact field |
| --- | --- |
| `size 39 ache?` | `attributes.size` or `available_sizes` |
| `same design blue ache?` | `attributes.design_id` and color |
| `men panjabi ache?` | `attributes.gender` and category |
| `5000 er moddhe` | price |
| `stock ache?` | stock |

Embeddings are not enough for these.

Why?

Because embeddings are fuzzy. Size and stock are not fuzzy.

```text
Semantic similarity can suggest.
Structured fields must decide.
```

## Stage 3: Search Text

A vector model cannot directly understand JSON fields. So we convert the product into searchable text.

Example product:

```text
name: Maroon Bridal Katan Saree
category: saree
color: maroon
fabric: katan
occasion: wedding
work_type: zari
```

Search text:

```text
Maroon Bridal Katan Saree saree maroon katan wedding zari premium bridal festive
```

This text is used for embeddings and semantic search.

Theory:

```text
The better the search text, the better the retrieval.
```

Bad search text:

```text
product 001
```

Good search text:

```text
Maroon Bridal Katan Saree saree katan fabric maroon color wedding bridal zari work festive occasion
```

## Stage 4: Embeddings

An embedding is a list of numbers that represents meaning.

Example:

```text
"wedding saree" -> [0.12, -0.44, 0.91, ...]
"bridal katan" -> [0.10, -0.40, 0.88, ...]
```

If two texts mean similar things, their vectors should be close.

This allows the bot to match:

```text
biye er jonno saree
```

with:

```text
wedding bridal katan saree
```

even if the exact words are different.

## Stage 5: Vector Search

Vector search means:

1. Embed the customer question.
2. Compare it with product vectors.
3. Return the closest products.

Example:

```text
Customer: eid er jonno elegant saree
```

Vector search may retrieve:

- soft silk saree
- festive jamdani saree
- bridal katan saree

This is useful because customers do not always use exact catalog words.

## Stage 6: Lexical Search

Lexical search means exact or near-exact word matching.

Example:

```text
Customer: lotus jamdani ache?
```

The word `lotus` is important. A vector search may find other jamdani products, but lexical search keeps the exact product name anchored.

Inventory systems need both:

| Search type | Strength | Weakness |
| --- | --- | --- |
| Vector search | Understands meaning | Can be too fuzzy |
| Lexical search | Exact terms, SKU, product names | Misses synonyms |
| Hybrid search | Combines both | More complex |

For inventory, hybrid search is usually better than vector-only search.

## Stage 7: Metadata Filters

Metadata filters are hard rules applied during retrieval.

Examples:

```text
category = bag
price <= 5000
stock >= 1
gender = men
```

Why filters matter:

If the customer asks for a bag, the bot should not return a saree just because both are used for weddings.

If the customer asks for men's perfume, the bot should not return women's cosmetics.

If the customer asks for size 39, the bot should not return size 38 as available.

Theory:

```text
Filters protect correctness.
Embeddings improve recall.
Reranking improves order.
```

## Stage 8: Candidate Retrieval

The first retrieval result is not the final answer.

It is only a candidate list.

Example:

```text
Customer: office er jonno bag dekhan
```

Candidates may include:

- Everyday Black Tote Bag
- Tan Shoulder Bag
- Gold Party Clutch
- Small Potli Bag

All are bags, but not all are equally good for office.

So we need ranking.

## Stage 9: Reranking

Reranking means sorting candidates by actual usefulness.

For inventory, ranking should consider:

- category match
- stock
- price
- budget fit
- occasion fit
- color match
- size match
- gender match
- exact product name match
- semantic similarity
- product quality
- business rules

Example:

```text
Customer: office er jonno bag dekhan
```

Better ranking:

1. Everyday Black Tote Bag
2. Tan Structured Shoulder Bag
3. Gold Party Clutch

Why?

The tote and shoulder bag are practical for office. The party clutch may be a bag, but it is not the best office recommendation.

## Stage 10: Retail Intent

Inventory questions are not all the same.

These two questions need different logic:

```text
red saree ache?
same design blue ache?
```

The first is a search question.

The second is a variant question.

Important retail intents:

| Intent | Meaning |
| --- | --- |
| `fashion_search` | Find products matching category, occasion, budget, etc. |
| `fashion_variant_color` | Find same design in another color |
| `fashion_size_availability` | Check a specific size |
| `fashion_accessory_match` | Find matching bag/jewelry/shoes |
| `fashion_compare` | Compare two product types or products |
| `fashion_styling_advice` | Suggest outfit or look |
| `policy_qa` | Answer delivery/payment/refund/exchange |
| `order_intent` | Start or continue order flow |

Each intent needs different rules.

## Stage 11: Slot Extraction

Slots are structured meaning extracted from the question.

Example:

```text
Customer: eid er jonno 5000 er moddhe elegant saree dekhan
```

Slots:

```json
{
  "category": "saree",
  "occasion": "eid",
  "budget_max": 5000,
  "style": "elegant",
  "language": "banglish"
}
```

The bot uses these slots to filter and rank products.

Without slots, everything becomes vague semantic search.

## Stage 12: Bangla And Banglish Understanding

Banglish means romanized Bangla.

Examples:

```text
biye = wedding
eid = Eid
dekhan = show me
ache = available
rong = color
koto = how much
```

Banglish support matters because real customers write like this:

```text
amar biye kichu saree dekhan
eid er jonno 5000 er moddhe elegant saree
office er jonno bag ache?
```

Theory:

The bot does not need perfect translation. It needs enough normalization to recover retail meaning.

```text
Banglish -> retail slots -> catalog search
```

## Stage 13: Evidence Contract

The evidence contract is a safety boundary.

It answers:

```text
What facts are allowed in the final answer?
```

Example evidence:

```text
Product: Everyday Black Tote Bag
Price: BDT 1,650
Stock: 8
Category: bag
Occasion: office/daily
```

Allowed answer:

```text
Everyday Black Tote Bag office use er jonno bhalo option. Price BDT 1,650, stock 8.
```

Not allowed:

```text
Eta leather imported bag and lifetime warranty ache.
```

unless the evidence says that.

## Stage 14: Answer Plan

The answer plan decides the structure of the answer before the model writes it.

It may say:

```json
{
  "primary_product_id": "bag_black_tote",
  "alternative_product_ids": ["bag_tan_shoulder"],
  "cross_sell_product_ids": [],
  "next_best_question": "Apni laptop carry korben?"
}
```

The answer writer should not change this.

Theory:

```text
Decision first.
Wording second.
```

If the LLM decides products freely during answer writing, hallucination risk increases.

## Stage 15: Generation

Generation is the final writing step.

This is where the answer becomes human-friendly.

Input:

- customer question
- retrieved products
- evidence contract
- answer plan
- language style
- policy rules
- conversation context

Output:

- final customer-facing answer

Good generation:

```text
Ji, office use er jonno Everyday Black Tote Bag ta bhalo match. Price BDT 1,650, stock 8. Daily essentials carry korar jonno eta practical. Apni ki laptop carry korben?
```

Bad generation:

```text
We have many beautiful office bags with premium imported leather and discount.
```

Why bad?

It invents facts.

## Stage 16: Verification

Verification checks whether the answer is safe.

It asks:

- Did the answer mention products from evidence?
- Did it invent price?
- Did it invent stock?
- Did it ignore size/color/gender/budget?
- Did it answer in the right language?
- Did it recommend out-of-stock products as available?

Verification is necessary because LLMs are fluent, not automatically truthful.

## Stage 17: Abstention

Abstention means the bot refuses to invent an answer.

Example:

```text
Customer: phone cover ache?
Catalog: no phone cover
```

Good answer:

```text
Current catalog e phone cover match pacchi na. Apni ki bag, saree, cosmetics, shoes, na men section dekhte chan?
```

Bad answer:

```text
Yes, we have stylish phone covers.
```

Abstention is not failure. In inventory, abstention is trust protection.

## Stage 18: Memory

Memory helps with follow-up questions.

Example:

```text
Customer: red jamdani dekhan
Bot: shows product A
Customer: same design blue ache?
```

The bot can use memory to understand `same design`.

But memory must be careful.

Bad memory:

```text
Customer: red jamdani dekhan
Bot: shows saree
Customer: office er jonno bag dekhan
Bot: keeps saree context and answers about sarees
```

Good memory:

```text
New category detected: bag.
Ignore old saree context.
```

Theory:

```text
Use memory only for true follow-ups.
Do not let memory override explicit new intent.
```

## Stage 19: Policy QA

Policy questions should not go through product recommendation.

Examples:

```text
delivery charge koto?
COD ache?
wrong size hole exchange hobe?
refund policy ki?
```

These should retrieve from policy data, not product data.

Why?

Because delivery and refund rules are business commitments.

The bot must not invent them.

## Stage 20: Order Flow

Order flow is different from RAG search.

It requires collecting structured information:

- product
- quantity
- customer name
- phone
- address
- payment method
- delivery method

Theory:

```text
RAG answers questions.
Workflow state completes actions.
```

For ordering, the bot needs workflow state, not only retrieval.

## Important Theory Terms

| Term | Meaning |
| --- | --- |
| RAG | Retrieve facts before generating answer |
| Embedding | Numeric representation of meaning |
| Vector store | Database for embedding vectors |
| Vector search | Finds semantically similar records |
| Lexical search | Finds exact word/name/SKU matches |
| Hybrid search | Combines vector and lexical search |
| Metadata filter | Hard structured filter like price/category/stock |
| Candidate | Possible product retrieved before final decision |
| Reranking | Reordering candidates by usefulness |
| Intent | What kind of question the user asked |
| Slot | Extracted structured detail like color, size, budget |
| Evidence contract | Allowed facts for the final answer |
| Answer plan | Decision about what to recommend and what to say next |
| Generation | Writing the final answer |
| Verification | Checking answer against evidence |
| Abstention | Saying no safe answer exists |

## Why Inventory RAG Is Harder Than Document RAG

Document RAG usually answers from paragraphs.

Inventory RAG answers from changing structured data.

Inventory has harder constraints:

- exact stock
- exact price
- exact size
- exact color
- exact gender
- variant families
- out-of-stock handling
- delivery rules
- order state
- customer preference
- real-time updates

So inventory RAG needs:

```text
structured logic + retrieval + generation
```

not just:

```text
vector search + LLM
```

## The Correct Priority Order

If you want to improve the bot, follow this order:

1. Catalog quality
2. Taxonomy and aliases
3. Slot extraction
4. Structured filters
5. Retrieval
6. Reranking
7. Evidence contract
8. Prompt writing
9. Verification
10. Feedback loop

Most people start at number 8. That is the blind spot.

## Common Failure Modes

| Failure | Root cause | Fix |
| --- | --- | --- |
| Bot recommends wrong category | Weak category extraction/filtering | Improve taxonomy and hard filters |
| Bot ignores budget | Budget slot missing or not enforced | Improve slot extraction and price filter |
| Bot invents stock | Prompt/verification too weak | Strengthen evidence contract and critic |
| Bot gives random cross-sells | No-match path too aggressive | Abstain cleanly |
| Bot forgets context | Memory not passed or state not saved | Improve conversation state |
| Bot overuses context | Memory overrides new explicit query | Add safe memory rules |
| Bot slow | Too many LLM calls | Use deterministic templates and reduce critic/reasoner calls |
| Bot bad in Banglish | Poor normalization/examples | Add Banglish aliases and prompt examples |

## The Five Rules Of A Good Inventory Bot

1. Never lie about stock.
2. Never invent unavailable variants.
3. Never ignore explicit customer constraints.
4. Never recommend unrelated products after no match.
5. Always ask one useful next question when the customer is vague.

## How To Think About Prompts

Prompts are not magic. Prompts are contracts.

A good prompt defines:

- role
- evidence boundaries
- output style
- forbidden behavior
- examples
- response format

For this bot, every answer prompt should contain:

```text
Use only provided product/policy evidence.
Do not invent stock, price, color, size, delivery, refund, or discount.
Answer in the customer's language style.
If no match exists, say no match and ask one useful question.
```

## How To Think About Embeddings

Embeddings are useful for meaning, not truth.

They can understand that:

```text
biye
```

is close to:

```text
wedding
bridal
party
festive
```

But embeddings cannot guarantee:

- exact stock
- exact size
- exact price
- exact color

So use embeddings for recall, then use structured fields for correctness.

## How To Think About Elasticsearch

Elasticsearch is not the intelligence by itself.

It is a stronger search backend.

It helps with:

- larger catalogs
- faster retrieval
- metadata filters
- lexical search
- vector search
- scalable indexing

But it still needs:

- good product schema
- good embeddings
- good filters
- good ranking
- good answer rules

Theory:

```text
Elasticsearch improves retrieval infrastructure.
It does not automatically make the bot smart.
```

## How To Think About Evaluation

You cannot improve what you do not measure.

Good evaluation questions should test:

- Bangla
- Banglish
- English
- size
- color
- same design
- stock
- budget
- occasion
- gender
- policy
- no-match
- follow-up memory
- order flow
- image search

Each test should check:

1. Did the bot understand intent?
2. Did it retrieve correct products?
3. Did it respect filters?
4. Did it answer from evidence?
5. Did it sound human?

## What "Human-Like" Really Means

Human-like does not mean long or emotional.

For a retail bot, human-like means:

- direct answer first
- warm tone
- short product explanation
- one practical follow-up
- no robotic metadata
- no hallucination
- no unnecessary lecture

Example:

```text
Ji, office er jonno black tote ta best fit. Price BDT 1,650, stock 8. Eta daily use er jonno practical and neutral color. Apni laptop carry korben?
```

That is more human than:

```text
Based on your query, I have analyzed the inventory database and found the following product candidates...
```

## Learning Path

If you want to master this system, learn in this order:

1. What RAG is and why inventory needs it.
2. Product schema and structured fields.
3. Embeddings and vector search.
4. Metadata filters and exact constraints.
5. Hybrid search and reranking.
6. Intent and slot extraction.
7. Evidence contracts and answer planning.
8. Prompt writing.
9. Verification and abstention.
10. Evaluation and feedback loops.

## Final Theory Summary

The inventory chatbot is a controlled decision system.

The LLM is not the brain by itself. The full brain is:

```text
catalog structure
+ retrieval
+ filters
+ reranking
+ evidence contract
+ answer plan
+ prompt writer
+ verification
```

The strongest version of this bot will not come from one perfect prompt. It will come from a pipeline where every layer does one job well.
