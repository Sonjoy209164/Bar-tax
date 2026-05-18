# Learning Path To Own This Codebase

This guide is for one goal:

```text
Move from "I can run the project" to "I understand how it thinks, where to change it, and how to improve it safely."
```

It is intentionally practical and opinionated. This repo is large enough that if you try to read it file-by-file from the top, you will waste time and still not feel ownership.

The right move is to learn the system in layers.

## 1. First Orientation: What This Repo Actually Is

This repo contains **two related but different systems**:

1. **Older legal/tax RAG research system**
2. **Current inventory/fashion retail chatbot system**

If your goal is ownership of the **current product**, focus on the inventory system first.

### Focus First

- `app/services/inventory_service.py`
- `app/inventory/`
- `app/api/routes_inventory.py`
- `app/api/routes_orders.py`
- `frontend/chat.html`
- `frontend/chat.js`
- `data/inventory/catalog.jsonl`
- `config/config.dev.yaml`
- `tests/test_boutique_retail_catalog.py`

### Park For Later

- `app/reasoning/`
- `app/generation/`
- `app/ingest/`
- `app/ingestion/`
- legal-tax PDFs and related evaluation artifacts

Those older parts matter architecturally, but they are not the fastest route to controlling the inventory chatbot.

## 2. The Core Mental Model

Do not think of this as "an LLM chat app."

That is too shallow.

Think of it as:

```text
Structured retail data system
    -> retrieval system
    -> decision system
    -> controlled answer writer
    -> verification system
```

The LLM is only one layer.

If catalog structure is bad, retrieval will be bad.
If retrieval is bad, the answer will sound fluent and still be wrong.
If evidence control is weak, the bot will hallucinate stock, price, or product claims.

That means the ownership hierarchy is:

1. **Catalog truth**
2. **Query understanding**
3. **Retrieval**
4. **Decisioning**
5. **Answer writing**
6. **Verification**
7. **UI polish**

Most people reverse this and obsess over prompts. That is a mistake.

## 3. What The System Does End To End

At runtime, the main path is:

```text
Customer message
  -> frontend payload
  -> FastAPI route
  -> InventoryService.ask()
  -> query understanding
  -> structured retail path and/or generic retrieval path
  -> retrieval candidates
  -> reranking and evidence control
  -> answer plan
  -> answer writing
  -> verification
  -> response JSON
  -> frontend rendering
```

At index time, the main path is:

```text
catalog.jsonl
  -> product validation
  -> search text building
  -> embedding
  -> vector record
  -> local store or Elasticsearch
  -> searchable product index
```

If you understand both flows, you own the system.

## 4. Your Learning Strategy

Here is the strategy I want you to follow:

### Phase A: Learn The Product Surface

Goal:

- know what the bot claims to do
- know what the customer can ask
- know what inputs exist

### Phase B: Learn The Runtime Path

Goal:

- trace one question through the backend
- identify where routing decisions happen
- identify where product facts are enforced

### Phase C: Learn The Data Path

Goal:

- understand how catalog data becomes searchable
- understand where embeddings and vector stores matter
- understand when structured filters beat semantic search

### Phase D: Learn The Safety Path

Goal:

- understand why the bot does not simply answer from model memory
- learn evidence contract, reranking, and verification

### Phase E: Learn The Change Workflow

Goal:

- make one safe change
- test it
- understand the blast radius

That is how ownership forms in real engineering.

## 5. Start Here: Repo Map

Use this as your first map.

| Area | Purpose | Main files |
| --- | --- | --- |
| App entry | FastAPI app boot | `app/main.py` |
| Inventory API | Inventory endpoints | `app/api/routes_inventory.py` |
| Orders API | Order endpoints | `app/api/routes_orders.py` |
| Main service | System orchestration brain | `app/services/inventory_service.py` |
| Retail reasoning | Boutique-specific deterministic logic | `app/inventory/fashion_retail.py` |
| Intent planning | Multi-turn reasoning/clarification | `app/inventory/intent_planner.py` |
| LLM intent | Optional classifier for intent/slots | `app/inventory/llm_intent_classifier.py` |
| Slot extraction | Optional JSON extraction | `app/inventory/llm_slot_extractor.py` |
| Retrieval | Embedding + vector search | `app/retrieval/embedder.py`, `app/retrieval/vector_store_base.py`, `app/retrieval/elasticsearch_store.py` |
| Reranking | Candidate scoring and selection | `app/inventory/reranker.py`, `app/inventory/decisioning.py` |
| Evidence | Allowed fact packaging | `app/inventory/evidence_contract.py` |
| Planner | Primary/alternative/cross-sell plan | `app/inventory/planner.py` |
| Verification | Safety checks | `app/inventory/verifier.py`, `app/inventory/answer_critic.py` |
| Memory | Follow-up context | `app/inventory/memory.py`, `app/inventory/conversation_state.py`, `app/inventory/coreference_resolver.py` |
| Catalog data | Ground-truth product data | `data/inventory/catalog.jsonl` |
| Business signals | Operational metrics | `data/inventory/business_signals.jsonl` |
| Orders data | Order state store | `data/orders/orders_store.jsonl` |
| Feedback data | Feedback store | `data/feedback/feedback.jsonl` |
| Frontend | Customer chat UI | `frontend/chat.html`, `frontend/chat.js`, `frontend/chat.css` |
| Config | Runtime choices | `config/config.dev.yaml` |
| Tests | Regression safety net | `tests/` |

## 6. Read Order: The Shortest Path To Ownership

This is the most important section in the whole guide.

Read in this order.

### Step 1: Read The Product From The Outside

Read:

- `frontend/chat.html`
- `frontend/chat.js`

Questions to answer:

- What does the UI send to the backend?
- How is session state stored?
- How is the catalog shown?
- How is API auth passed?
- What user actions exist beyond plain chat?

You are learning the product contract.

### Step 2: Read The App Entry

Read:

- `app/main.py`

Questions:

- What routes are mounted?
- Where is the frontend served from?
- Is docs UI public or protected?
- How is API key enforcement applied?

You are learning the server shell.

### Step 3: Read The Inventory Route Layer

Read:

- `app/api/routes_inventory.py`

Questions:

- Which endpoints are pure CRUD?
- Which endpoints are chat?
- Which endpoints are sync/rebuild/status?
- What request/response models are used?

You are learning the public backend API.

### Step 4: Read The Schemas

Read:

- `app/core/schemas.py`

Do not read the entire file blindly. Search for:

- `InventoryAskRequest`
- `InventoryAskResponse`
- `InventoryItemRecord`
- `VectorRecord`
- business signal models

Questions:

- What is the exact shape of product truth?
- What can the service return?
- What fields are required for safe answers?

You are learning the typed contract of the system.

### Step 5: Read `InventoryService.ask()`

Read:

- `app/services/inventory_service.py`

Search first for:

- `class InventoryService`
- `def ask(`

Do **not** read this file top-to-bottom at first. It is too large. That is a trap.

Instead, read it as a call graph:

1. `ask()`
2. the helper methods it calls directly
3. the helper methods those call

Questions:

- Where does routing happen?
- When does the fashion-specific path run?
- When does the generic retrieval path run?
- Where are traces saved?
- Where are final answers shaped?

This is the real ownership step.

### Step 6: Read The Retail Brain

Read:

- `app/inventory/fashion_retail.py`

This file matters more than most prompt files.

Why?

Because this is where hard retail logic lives:

- same design / other color
- size availability
- category detection
- accessory matching
- compare logic
- styling advice
- Bangla/Banglish retail phrasing

Questions:

- Which intents are handled deterministically?
- What product attributes does it rely on?
- Where will it fail if catalog data is weak?
- Which answers are rules, and which are model-assisted?

If you master this file, you will understand the commercial core of the chatbot.

### Step 7: Read The Retrieval Stack

Read:

- `app/retrieval/embedder.py`
- `app/retrieval/vector_store_base.py`
- `app/retrieval/elasticsearch_store.py`

Then find inside `inventory_service.py`:

- search text builder
- vector record builder
- semantic search
- lexical search

Questions:

- What text becomes the embedding input?
- What metadata becomes filterable?
- Are we using local store or Elasticsearch right now?
- How are dense and lexical signals merged?

This is how you stop treating retrieval as magic.

### Step 8: Read Decisioning And Evidence

Read:

- `app/inventory/reranker.py`
- `app/inventory/decisioning.py`
- `app/inventory/evidence_contract.py`
- `app/inventory/planner.py`
- `app/inventory/verifier.py`

Questions:

- How does the system choose primary vs alternative?
- What facts are allowed into the answer?
- Where are unsupported claims blocked?
- When does the system abstain?

This is the difference between a flashy demo and a production-worthy assistant.

### Step 9: Read Prompt-Bearing Files

Read:

- `app/inventory/llm_intent_classifier.py`
- `app/inventory/llm_reasoner.py`
- `app/inventory/natural_answer.py`
- `app/inventory/answer_critic.py`
- writer prompt logic inside `inventory_service.py`

Questions:

- What is the LLM responsible for?
- What is it explicitly not allowed to decide?
- Which prompts are optional enhancers versus core logic?

Important:

If you start here, you will misunderstand the codebase.

Prompts explain surface behavior.
They do not explain the system.

### Step 10: Read The Tests That Define Expected Behavior

Start with:

- `tests/test_boutique_retail_catalog.py`
- `tests/test_deep_bangla_banglish_conversation.py`
- `tests/test_llm_intent_classifier.py`
- `tests/test_hybrid_retrieval.py`
- `tests/test_reranker.py`
- `tests/test_feedback_api.py`
- `tests/test_api_endpoints.py`

Questions:

- What behavior is expected to stay stable?
- Which features are already covered?
- Which parts are fragile or under-tested?

Tests reveal the real product promises.

## 7. The Runtime Call Flow You Should Memorize

This is the path that matters most:

```text
frontend/chat.js
  -> POST /inventory/ask
  -> app/api/routes_inventory.py
  -> get_inventory_service().ask(request)
  -> InventoryService.ask()
  -> route/query-understanding logic
  -> fashion_retail path and/or generic retrieval path
  -> answer planning
  -> verification
  -> InventoryAskResponse
  -> frontend rendering
```

If I were onboarding you live, I would make you trace this once with a real example:

```text
"eid er jonno 5000 er moddhe elegant saree ache?"
```

Then I would ask you to write down:

1. what the UI sent
2. what request object was created
3. how intent was determined
4. what retrieval filters were built
5. what products were considered
6. what final answer logic won

Do that exercise and you will feel the codebase click.

## 8. The Data Model You Must Understand

The product catalog is the source of truth.

Current main file:

- `data/inventory/catalog.jsonl`

One line = one product JSON object.

At a minimum, learn these product fields:

- `product_id`
- `sku`
- `name`
- `category`
- `brand`
- `price`
- `stock`
- `status`
- `tags`
- `attributes.color`
- `attributes.size`
- `attributes.fabric`
- `attributes.occasion`
- `attributes.gender`
- `attributes.design_id`
- `include_in_rag`

### Why These Fields Matter

| Field | Why it matters |
| --- | --- |
| `product_id` | stable identity across sync, retrieval, ordering |
| `price` | hard fact; cannot be guessed |
| `stock` | hard fact; high hallucination risk |
| `category` | controls search and answer type |
| `attributes.color` | needed for same-design and matching |
| `attributes.size` | needed for exact availability |
| `attributes.fabric` | needed for compare and styling |
| `attributes.design_id` | needed for same-design different color |
| `include_in_rag` | determines whether it becomes searchable |

If these fields are weak, no prompt can save the system.

## 9. The Two Brains Inside The Bot

There are really two answering modes:

### Brain 1: Structured Retail Brain

Main file:

- `app/inventory/fashion_retail.py`

Use this for:

- size availability
- same design, different color
- accessory matching
- compare
- styling suggestions grounded in catalog

This brain is deterministic and business-aware.

### Brain 2: Generic Retrieval Brain

Main driver:

- `app/services/inventory_service.py`

Use this for:

- broader product search
- semantic matching
- policy-backed answers
- evidence packaging
- grounded writing

If you do not understand which brain answered a query, you will misdiagnose bugs.

## 10. Retrieval: What It Is And What It Is Not

Retrieval is not the final answer.

Retrieval is:

```text
Find the best candidate products or evidence.
```

In this repo, retrieval uses a blend of:

- structured field logic
- lexical matching
- vector similarity
- reranking

### Retrieval Inputs

- customer text
- normalized Banglish/Bangla/English cues
- extracted category/size/color/budget/etc.
- catalog metadata
- embeddings

### Retrieval Outputs

- candidate products
- scores
- matched metadata
- evidence ready for decisioning

### Key Design Truth

For fashion retail, **exact fields often matter more than embeddings**.

Example:

```text
"Do you have size 42?"
```

This is not fundamentally a semantic search problem.
It is a structured stock lookup problem.

That is why `fashion_retail.py` matters so much.

## 11. Why Elasticsearch Exists

Elasticsearch is the scalable retrieval backend.

It stores:

- product text
- structured metadata
- dense vectors

It supports:

- semantic kNN search
- lexical search
- metadata filters

Main file:

- `app/retrieval/elasticsearch_store.py`

Use it when you need:

- larger catalogs
- better combined search
- scalable filtering
- stronger retrieval than a tiny local store

But do not confuse "implemented" with "active."

The actual active provider is controlled by:

- `config/config.dev.yaml`

So one of your first ownership checks should always be:

```text
What provider is configured now?
```

## 12. Decisioning And Evidence: The Real Safety Layer

This is where the system stops being a fuzzy chatbot and becomes an operational assistant.

Key files:

- `app/inventory/reranker.py`
- `app/inventory/decisioning.py`
- `app/inventory/evidence_contract.py`
- `app/inventory/planner.py`
- `app/inventory/verifier.py`

### What This Layer Decides

- Which product is primary?
- Which ones are alternatives?
- Which ones are only cross-sells?
- Which facts are safe to say?
- When should the bot clarify?
- When should it abstain?

This is the layer that prevents:

- wrong stock claims
- wrong price claims
- random product mentions
- unsupported delivery/refund promises

If you want production quality, this layer is not optional.

## 13. Prompt Layers: Important But Overrated

Prompt-bearing files:

- `app/inventory/llm_intent_classifier.py`
- `app/inventory/llm_reasoner.py`
- `app/inventory/natural_answer.py`
- `app/inventory/answer_critic.py`
- writer prompt logic in `app/services/inventory_service.py`

### What Prompts Should Do

- classify intent better
- parse messy Banglish better
- make replies warmer
- critique answer quality

### What Prompts Should Not Be Used To Hide

- bad catalog structure
- bad retrieval
- weak business logic
- missing sizes/colors/design ids
- broken filtering

That is the strategic discipline this codebase needs.

## 14. Memory, Orders, And Feedback

Ownership is not only about search.

You also need to understand the stateful layers.

### Memory

Files:

- `app/inventory/memory.py`
- `app/inventory/conversation_state.py`
- `app/inventory/coreference_resolver.py`

Use cases:

- "same design ta blue e ache?"
- "first one ta koto?"
- "eta office e jabe?"

### Orders

Files:

- `app/api/routes_orders.py`
- `app/inventory/order_workflow.py`
- `data/orders/orders_store.jsonl`

Use cases:

- place order
- confirm order
- update order
- track order

### Feedback

Files:

- `app/api/routes_feedback.py`
- `data/feedback/feedback.jsonl`

Use cases:

- thumbs up / thumbs down
- later evaluation and tuning

These parts matter because the product is not only a retriever. It is a commerce assistant.

## 15. The Fastest Way To Learn The Code: Use Real Questions

Use real customer-style questions, not only technical probes.

Examples:

- `do you have White Pearl Earrings?`
- `ei same design ta blue color e ache?`
- `eid er jonno 5000 er moddhe elegant saree dekhan`
- `amar office ache amake kichu bag dekhan`
- `jamdani vs katan — konta nibo?`
- `oily skin er jonno sunscreen ache?`
- `navy katan sareer shathe kon bag manabe?`

For each query, ask:

1. Which module understood this query?
2. Was this structured logic or retrieval logic?
3. Which products were candidates?
4. Which evidence won?
5. Was the final answer safe?

That is a much better learning loop than passive reading.

## 16. Your First Two Weeks Of Learning

Here is the plan I would actually recommend.

### Week 1: Understand The Product And Runtime

Day 1:

- read `frontend/chat.js`
- read `app/main.py`
- read `app/api/routes_inventory.py`

Day 2:

- read inventory request/response schemas in `app/core/schemas.py`
- inspect `data/inventory/catalog.jsonl`
- inspect `config/config.dev.yaml`

Day 3:

- trace `InventoryService.ask()`
- note every major branch

Day 4:

- read `fashion_retail.py`
- list all retail intents handled

Day 5:

- run example questions
- manually trace 3 answers end to end

### Week 2: Understand Retrieval And Safety

Day 6:

- read `embedder.py`
- read `vector_store_base.py`
- read active vector store implementation

Day 7:

- read search text builder and vector record builder in `inventory_service.py`
- map index-time flow

Day 8:

- read `reranker.py`
- read `decisioning.py`

Day 9:

- read `evidence_contract.py`
- read `planner.py`
- read `verifier.py`

Day 10:

- read prompt-bearing files
- compare prompt logic with deterministic logic

If you do these ten days properly, you will stop feeling like a guest in the codebase.

## 17. Exercises That Build Real Ownership

Do these in order.

### Exercise 1: Trace One Query

Pick one query and write:

- request payload
- intent
- slots
- retrieval candidates
- selected product
- final answer path

### Exercise 2: Add One New Retail Alias

Example:

- add a new Banglish term for a category or occasion

Goal:

- learn how language normalization affects retrieval and retail routing

### Exercise 3: Add One New Product Attribute

Example:

- sleeve type
- heel type
- skin type

Goal:

- learn how catalog structure propagates through search and answers

### Exercise 4: Improve One Test

Pick a brittle area and add a regression test.

Goal:

- ownership means locking in behavior, not only editing code

### Exercise 5: Rebuild Index And Explain What Changed

Goal:

- understand index-time versus runtime

### Exercise 6: Debug A Bad Answer

Take a real failure and classify it:

- catalog problem
- normalization problem
- retrieval problem
- ranking problem
- answer-writing problem
- verification gap

This is an elite engineering habit.

## 18. Common Blind Spots In This Repo

These are the traps I want you to avoid.

### Blind Spot 1: Reading `inventory_service.py` As A Novel

It is too large. Read it by call path, not by linearly scrolling.

### Blind Spot 2: Over-crediting The LLM

If the answer is good, it is often because catalog structure and decisioning were good.

### Blind Spot 3: Treating Retrieval As Pure Semantics

Retail retrieval often depends on exact structured constraints.

### Blind Spot 4: Ignoring Data Quality

Bad `design_id`, weak `color`, missing `size`, and noisy categories will quietly ruin the bot.

### Blind Spot 5: Confusing Old Legal-Tax Code With Current Product Logic

Both systems share RAG ideas, but they solve different problems.

### Blind Spot 6: Thinking UI Polish Equals Product Maturity

Nice chat bubbles do not make grounded retrieval safe.

## 19. What "Ownership" Really Means Here

You own this codebase when you can do these things without guessing:

1. Explain the end-to-end runtime flow from UI to answer.
2. Explain the index-time flow from catalog to searchable vectors.
3. Tell whether a bad answer came from data, retrieval, ranking, or prompting.
4. Add a feature without breaking the grounded answer rules.
5. Add a test for the feature.
6. Explain which files matter for a given bug report.
7. Tell when the system should use deterministic retail logic versus LLM assistance.

That is the bar.

## 20. Your First Ownership Checklist

- [ ] I can explain what the product does in one minute.
- [ ] I know the difference between the legal-tax path and the inventory path.
- [ ] I know where the frontend sends chat requests.
- [ ] I know where `InventoryService.ask()` routes requests.
- [ ] I know what `fashion_retail.py` is responsible for.
- [ ] I know how catalog data is stored.
- [ ] I know how product text becomes embeddings.
- [ ] I know whether the active vector store is local or Elasticsearch.
- [ ] I know what evidence contract means in this project.
- [ ] I know where answer verification happens.
- [ ] I know where orders are stored.
- [ ] I know where feedback is stored.
- [ ] I have traced at least three real user questions end to end.
- [ ] I have added or modified at least one test.

## 21. Recommended Companion Docs In This Repo

Read these after this guide:

- `pipeline.md`
- `theorypipeline.md`
- `invenadvance.md`
- `expert_pipeline_presentation.md`

Use them as secondary material.

This `learning.md` should be your primary onboarding path because it is optimized for ownership, not just explanation.

## 22. Final Advice

If you want real control over this system, do not ask:

```text
"Which prompt should I improve?"
```

Ask:

```text
"What exact product truth is missing?"
"Which layer made the wrong decision?"
"What evidence should have been available but was not?"
"Was this a routing bug, retrieval bug, or answer-writing bug?"
```

That mindset is what turns you from user of the codebase into owner of the codebase.

## 23. What We Should Do Next

The best next step is not more reading.

The best next step is:

1. pick one real customer query
2. trace it through the full runtime path
3. write down the exact functions involved
4. identify where the answer quality is won or lost

That exercise will teach you more than another 50 pages of theory.
