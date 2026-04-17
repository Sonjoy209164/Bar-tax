# TODO Intelligent Ecommerce Bot

## Goal

Build a natural, logical, and trustworthy ecommerce selling/support bot that understands user intent, reasons over product facts, recommends coherently, abstains when evidence is weak, and answers naturally from verified product data.

Target behavior:

```text
User: Need premium wireless headphones under 300 for office calls.

Bot: I would lead with Auralite Flex ANC Headphones. They match the request directly: wireless headphones, under USD 300, in stock, Bluetooth 5.3, and 35-hour battery life. They are also positioned for travel, calls, and focused office work. If the customer pushes back on price, EchoWave Studio Earbuds are a cheaper fallback, but I would position them as earbuds, not equivalent over-ear headphones. Do they care more about call quality or battery life?
```

## Current Baseline

Already implemented:

- [x] Swagger API for inventory RAG on port `4893`.
- [x] API key protection for protected endpoints.
- [x] Product upsert/delete/search/ask endpoints.
- [x] Normal `/inventory/ask` flow.
- [x] Agentic `/inventory/agentic/ask` flow.
- [x] Natural-answer option using local Ollama/Qwen.
- [x] Answer plan metadata.
- [x] Plan verifier.
- [x] Metadata-aware answer prompt.
- [x] Same-category alternative filtering improvements.
- [x] Safer cross-sell behavior.
- [x] Express remains the source-of-truth backend boundary.

Important boundary:

```text
PostgreSQL through Express is the operational source of truth.
The RAG service is a mirrored intelligence layer, not the inventory database.
```

## Definition Of An Intelligent Answer

An answer is intelligent only if it is:

- [ ] Relevant to the exact user request.
- [ ] Grounded in available product facts.
- [ ] Honest about missing data.
- [ ] Category-aware.
- [ ] Price-aware.
- [ ] Stock-aware.
- [ ] Metadata-aware.
- [ ] Useful for the buyer or staff member.
- [ ] Natural in tone.
- [ ] Verifiably safe before returning.

Not intelligent:

- [ ] Recommending watches when the user asks for bikes.
- [ ] Recommending headphones because the word "premium" matched.
- [ ] Treating cross-sell items as substitutes.
- [ ] Inventing features, stock, discounts, warranty, or delivery claims.
- [ ] Giving a confident answer when the catalog has no evidence.

## Strategic Principle

Do not make the model think randomly.

The system should:

```text
understand intent
-> extract preferences
-> retrieve facts
-> rerank logically
-> create answer plan
-> verify plan and final answer
-> generate natural response
-> ask next-best question when needed
```

## Do Not Do First

These look attractive but will not solve the core intelligence problem yet:

- [ ] Do not chase bigger models before fixing ranking and verification.
- [ ] Do not make every query agentic.
- [ ] Do not let the LLM choose products directly from raw retrieval hits.
- [ ] Do not make the browser call the RAG API directly.
- [ ] Do not treat the RAG mirror as the inventory database.
- [ ] Do not expose internal debug traces to normal customers.
- [ ] Do not add sales persuasion before factual correctness is strong.

## Phase 1: Measurement First

- [ ] Create `evaluation/commerce_questions.jsonl`.
- [ ] Add 100 seed questions across key categories.
- [ ] Add expected primary product IDs.
- [ ] Add acceptable alternative product IDs.
- [ ] Add forbidden product IDs.
- [ ] Add `must_abstain` labels.
- [ ] Add required metadata fields.
- [ ] Create `evaluation/run_inventory_eval.py`.
- [ ] Create `evaluation/metrics.py`.
- [ ] Track wrong-category recommendation rate.
- [ ] Track exact no-match accuracy.
- [ ] Track recommendation accuracy.
- [ ] Track hallucinated feature rate.
- [ ] Track price correctness.
- [ ] Track stock correctness.
- [ ] Track answer latency.
- [ ] Track natural-to-deterministic fallback rate.

Success criteria:

```text
We can run one command and compare current bot quality before and after changes.
```

## Phase 2: Modularize Inventory Intelligence

Current issue:

```text
app/services/inventory_service.py is doing too much.
```

Split into:

- [ ] `app/inventory/catalog_store.py`
- [ ] `app/inventory/search_service.py`
- [ ] `app/inventory/intent.py`
- [ ] `app/inventory/preferences.py`
- [ ] `app/inventory/ontology.py`
- [ ] `app/inventory/reranker.py`
- [ ] `app/inventory/planner.py`
- [ ] `app/inventory/verifier.py`
- [ ] `app/inventory/generator.py`
- [ ] `app/inventory/agentic.py`
- [ ] Keep route behavior backward-compatible.
- [ ] Keep all current tests passing after each extraction.

Success criteria:

```text
Each intelligence layer can be tested independently.
```

## Phase 3: Intent Classifier

Implement `InventoryIntent`.

Intent labels:

- [ ] `small_talk`
- [ ] `exact_lookup`
- [ ] `product_search`
- [ ] `product_detail`
- [ ] `recommendation`
- [ ] `comparison`
- [ ] `price_objection`
- [ ] `availability_objection`
- [ ] `quality_objection`
- [ ] `cross_sell`
- [ ] `restock`
- [ ] `business_analysis`
- [ ] `unknown`

Implementation tasks:

- [ ] Add deterministic intent classifier first.
- [ ] Use phrase rules, product references, filters, and question shape.
- [ ] Return confidence score.
- [ ] Expose intent in `answer_plan.intent`.
- [ ] Add tests for each intent.

Example:

```json
{
  "question": "The customer says this is too expensive. What should I say?",
  "intent": "price_objection",
  "confidence": 0.92
}
```

Success criteria:

```text
The bot chooses different strategies for lookup, recommendation, objection, comparison, and restock questions.
```

## Phase 4: Preference Extractor

Implement `InventoryPreferenceProfile`.

Fields:

- [ ] `product_type`
- [ ] `category`
- [ ] `brand`
- [ ] `budget_min`
- [ ] `budget_max`
- [ ] `quality_level`
- [ ] `needs_in_stock`
- [ ] `use_case`
- [ ] `feature_requirements`
- [ ] `avoid_product_types`
- [ ] `selected_product_ids`

Implementation tasks:

- [ ] Extract budget from text.
- [ ] Extract product type from text.
- [ ] Extract category and brand hints.
- [ ] Extract premium/budget/value/availability hints.
- [ ] Extract use case like office calls, gaming, travel, podcasting.
- [ ] Extract feature hints like battery life, Bluetooth, ANC, USB-C.
- [ ] Merge explicit filters with extracted preferences.
- [ ] Add extracted preferences to `answer_plan`.
- [ ] Add tests for common ecommerce prompts.

Success criteria:

```text
The bot understands what the buyer cares about before ranking products.
```

## Phase 5: Product Ontology

Create `app/inventory/ontology.py`.

Initial ontology:

- [ ] `headphones -> audio_listening`
- [ ] `earbuds -> audio_listening`
- [ ] `speaker -> audio_speaker`
- [ ] `microphone -> audio_capture`
- [ ] `monitor -> display`
- [ ] `keyboard -> computing_input`
- [ ] `mouse -> computing_input`
- [ ] `watch -> wearable`
- [ ] `chair -> furniture`
- [ ] `desk -> furniture`
- [ ] `bag -> accessories`

Ontology functions:

- [ ] `detect_product_type(text, product)`
- [ ] `product_family(product)`
- [ ] `same_product_family(a, b)`
- [ ] `valid_alternative(primary, candidate)`
- [ ] `valid_cross_sell(primary, candidate, intent)`
- [ ] `explain_relationship(primary, candidate)`

Rules:

- [ ] A keyboard is not a headphone fallback.
- [ ] Earbuds may be a cheaper audio fallback, but not equivalent over-ear headphones.
- [ ] Mouse can be a laptop cross-sell only when user asks for add-ons/bundle/setup.
- [ ] Out-of-stock products can be mentioned, but should not be primary recommendations unless user asks about restock or unavailable items.

Success criteria:

```text
The bot stops relying on generic shared words like "wireless" to decide product relationships.
```

## Phase 6: Ecommerce Reranker

Create `ProductEvidenceScore`.

Fields:

- [x] `semantic_score`
- [x] `lexical_score`
- [x] `category_match`
- [x] `brand_match`
- [x] `product_type_match`
- [x] `family_match`
- [x] `price_fit`
- [x] `stock_fit`
- [x] `metadata_match`
- [x] `premium_fit`
- [x] `budget_fit`
- [x] `unrelated_category_penalty`
- [x] `out_of_stock_penalty`
- [x] `final_score`

Implementation tasks:

- [x] Score all retrieved hits.
- [x] Use preferences and ontology.
- [x] Penalize unrelated categories.
- [x] Penalize weak metadata fit.
- [x] Prefer in-stock items for selling.
- [x] Prefer exact product type over broad semantic match.
- [x] Expose debug score in dev/admin response.
- [x] Add tests for wrong-category penalties.

Success criteria:

```text
Ranking reflects ecommerce logic, not only vector similarity.
```

## Phase 7: Rich Answer Plan

Extend `InventoryAnswerPlan`.

Add:

- [x] `preferences`
- [x] `primary_reason`
- [x] `alternative_reason`
- [x] `cross_sell_reason`
- [x] `tradeoffs`
- [x] `risk_notes`
- [x] `next_best_question`
- [x] `confidence_breakdown`

Plan should decide:

- [x] primary product
- [x] fallback product
- [x] premium step-up
- [x] cheaper alternative
- [x] cross-sell add-on
- [x] excluded products
- [x] abstention
- [x] next-best question

Success criteria:

```text
The LLM receives a decision plan, not a pile of products.
```

## Phase 8: Tradeoff Reasoning

Implement tradeoff templates:

- [x] premium vs budget
- [x] price vs feature strength
- [x] stock urgency vs best fit
- [x] exact product type vs nearby category
- [x] over-ear headphones vs earbuds
- [x] in-stock alternative vs out-of-stock premium option
- [x] direct substitute vs cross-sell add-on

Example:

```text
EchoWave Studio Earbuds are a cheaper audio fallback, but they are earbuds, not equivalent over-ear headphones.
```

Success criteria:

```text
The bot explains recommendation tradeoffs honestly.
```

## Phase 9: Final Answer Verifier

Current verifier checks the plan. Add final-answer verification.

Checks:

- [x] Answer does not recommend excluded products.
- [x] Answer does not invent product names.
- [x] Answer does not invent stock.
- [x] Answer does not invent price.
- [x] Answer does not invent features.
- [x] Answer respects abstention.
- [x] Answer does not treat cross-sell as substitute.
- [x] Answer includes required caveat for near alternatives.

Actions:

- [x] If verification passes, return answer.
- [x] If verification fails and natural mode was used, retry deterministic answer.
- [x] If deterministic also fails, return safe abstention.
- [x] Log verification issues.

Success criteria:

```text
The bot cannot confidently say unsupported things without being caught.
```

## Phase 10: Better Natural Generation Prompt

Prompt should include:

- [x] intent
- [x] preferences
- [x] answer plan
- [x] verified product facts
- [x] excluded products
- [x] tradeoffs
- [x] next-best question
- [x] output JSON schema

Rules:

- [x] Do not change product selection.
- [x] Do not add products.
- [x] Do not mention excluded products as recommendations.
- [x] Use metadata only if present.
- [x] Ask one next-best question only when useful.
- [x] Keep customer-facing language natural.
- [x] Keep staff-facing sales coaching practical.

Success criteria:

```text
Qwen writes naturally but does not make recommendation decisions by itself.
```

## Phase 11: Conversation Memory Contract

Express should own memory.

RAG sidecar should accept:

- [x] `conversation_summary`
- [x] `conversation_history`
- [x] `focused_product_ids`
- [x] `active_filters`
- [x] `last_answer_plan`

Implementation tasks:

- [x] Define request schema for memory context.
- [x] Use selected product IDs for "this", "it", "that one".
- [x] Use summary for buyer preferences.
- [x] Do not store customer session truth in RAG sidecar by default.

Success criteria:

```text
Follow-up questions work without hallucinating what "it" means.
```

## Phase 12: Agentic Business Tools

Only after normal chat is strong.

Add tools for:

- [x] sales history
- [x] order history
- [x] supplier lead time
- [x] margins
- [x] inventory snapshots
- [x] return rates
- [x] customer segments

Agentic use cases:

- [x] restock prioritization
- [x] demand reasoning
- [x] why sales dropped
- [x] supplier risk
- [x] margin-aware recommendation
- [x] stockout prevention

Success criteria:

```text
Agentic mode answers business questions from real operational data, not only catalog text.
```

## Phase 13: Sync And Data Quality

Add endpoints:

- [x] `GET /inventory/sync/status`
- [x] `POST /inventory/sync/validate`
- [ ] `POST /inventory/sync/rebuild`

Validation:

- [x] catalog count
- [x] vector count
- [x] missing product IDs
- [x] stale product IDs
- [x] invalid metadata
- [x] empty descriptions
- [x] missing category
- [x] missing product type
- [x] out-of-date prices

Success criteria:

```text
The bot cannot be smarter than stale or dirty product data, so sync health must be visible.
```

## Phase 14: Observability And Tracing

Log every chat turn:

- [x] request ID
- [x] question
- [x] intent
- [x] preferences
- [x] retrieved IDs
- [x] reranked IDs
- [x] answer plan
- [x] verification
- [x] final answer
- [x] answer engine
- [x] latency
- [x] fallback reason

Add endpoint:

- [x] `GET /inventory/chat/trace/{trace_id}`

Success criteria:

```text
Every bad answer can be debugged from retrieval to final response.
```

## Phase 15: Production Hardening

- [x] Move catalog mirror away from JSONL for production.
- [x] Use Postgres mirror table or durable document store.
- [x] Use Qdrant/Milvus/Pinecone for vector retrieval.
- [ ] Add rate limiting.
- [ ] Add HTTPS.
- [ ] Add key rotation.
- [ ] Add streaming response support.
- [ ] Add model timeout fallback strategy.
- [ ] Add generated TypeScript client from OpenAPI.

Success criteria:

```text
The system is safe to run beyond a local demo.
```

## API Contract To Preserve

Existing consumers should continue using:

- [ ] `GET /inventory/status`
- [ ] `POST /inventory/items/upsert`
- [ ] `POST /inventory/items/delete`
- [ ] `POST /inventory/search`
- [ ] `POST /inventory/ask`
- [ ] `POST /inventory/agentic/ask`

Response additions should be backward-compatible:

- [ ] Keep `answer`.
- [ ] Keep `hits`.
- [ ] Keep `confidence`.
- [ ] Keep `recommended_product_ids`.
- [ ] Keep `alternative_product_ids`.
- [ ] Keep `cross_sell_product_ids`.
- [ ] Keep `follow_up_question`.
- [ ] Add intelligence fields without removing old fields.
- [ ] Put debug-only reasoning under explicit debug/admin fields.

Success criteria:

```text
Express/Next can keep calling the same endpoints while the RAG service gets smarter internally.
```

## Build Order

Recommended implementation sequence:

1. [ ] Evaluation harness
2. [x] Intent classifier
3. [x] Preference extractor
4. [x] Product ontology
5. [x] Ecommerce reranker
6. [x] Rich answer plan
7. [x] Tradeoff reasoning
8. [x] Final answer verifier
9. [x] Better natural prompt
10. [x] Conversation memory contract
11. [x] Sync validation
12. [x] Observability
13. [x] Agentic business tools
14. [x] Production storage and vector backend

## Immediate Next Task

Start with:

```text
Rate limiting and key rotation
```

Why:

```text
The storage/vector migration path now exists. The next production risk is API abuse and leaked or long-lived keys.
```

First sprint deliverables:

- [x] Create `app/inventory/intent.py`.
- [x] Create `app/inventory/preferences.py`.
- [x] Create `app/inventory/ontology.py`.
- [x] Add unit tests for intent classification.
- [x] Add unit tests for preference extraction.
- [x] Add unit tests for ontology relationships.
- [x] Wire intent and preferences into `answer_plan`.
- [x] Keep current `/inventory/ask` response shape compatible.

First sprint acceptance tests:

- [x] "Do you have any bike?" should abstain if no bike exists.
- [x] "Show me some watches" should return only watches or abstain.
- [x] "Find wireless headphones under 300" should not return keyboard/mouse/watch.
- [x] "Tell me about this product" should use focused product IDs.
- [x] "This is too expensive" should suggest same-family lower-price alternatives only.
- [ ] "What can I bundle with this laptop?" may use cross-sell logic.
- [x] Casual greetings should not trigger random product recommendations.
