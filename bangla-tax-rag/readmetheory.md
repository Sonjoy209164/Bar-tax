# README Theory

This file explains what the project has become so far, not just what it started as.

The short version:

- it started as a Bangla legal/tax RAG system
- it now also contains a structured agentic legal reasoning runtime
- it now also contains a much larger inventory intelligence stack with deterministic reasoning, evidence contracts, and verification

If you read the repo as if it is only a PDF-to-RAG project, you will misunderstand half the codebase.

## 1. Big Picture

The repo currently has **three major execution paths**:

```text
Client
-> FastAPI app (`app/main.py`)
-> API routes (`app/api/*`)
-> one of three paths:

   A. Classic legal/tax RAG
      -> ingest PDF
      -> build sparse/dense indexes
      -> retrieve evidence
      -> generate cited answer

   B. Agentic legal reasoning
      -> ingest legal document into structured graph + chunks
      -> run planner/retrieve/reason/verify/compose loop
      -> return traceable reasoning answer

   C. Inventory intelligence
      -> route inventory question
      -> retrieve catalog/business evidence
      -> build evidence contract
      -> score deterministically
      -> verify claims
      -> answer or abstain
```

That is the correct mental model for the project today.

## 2. Architectural Truth

This repo is not organized around one single pure architecture. It has evolved in layers:

```text
Layer 1: classic legal/tax RAG
-> `app/ingest`
-> `app/retrieval`
-> `app/generation`

Layer 2: structured legal reasoning
-> `app/ingestion`
-> `app/reasoning`
-> `app/services/runtime_service.py`

Layer 3: inventory decision engine
-> `app/inventory`
-> `app/services/inventory_service.py`
-> `tests/test_inventory_*`
```

This is why some folder names look close but are not the same:

- `app/ingest` is the older, simpler ingestion path used by `/ingest`
- `app/ingestion` is the newer, richer structured legal ingestion path used by the agentic runtime

If you mix those up, the codebase will feel inconsistent when it is actually serving different generations of the system.

## 3. Request Flow Map

### 3.1 Overall Request Routing

```text
HTTP request
-> `app/main.py`
-> mounted routers:
   -> `routes_health.py`
   -> `routes_ingest.py`
   -> `routes_query.py`
   -> `routes_eval.py`
   -> `routes_agentic.py`
   -> `routes_inventory.py`
-> route-specific service/pipeline
-> Pydantic response from `app/core/schemas.py`
```

### 3.2 Classic Legal/Tax RAG Flow

```text
PDF
-> `/ingest`
-> `app.ingest.parser`
-> `app.ingest.chunker`
-> chunk JSONL
-> `/build-index`
-> sparse index + dense index

Question
-> `/query`
-> `preprocess_query(...)`
-> sparse / dense / hybrid retrieval
-> support filtering
-> `app/generation/generator.py`
-> `app/generation/citations.py`
-> cited final answer
```

### 3.3 Agentic Legal Reasoning Flow

```text
Legal source file
-> `/agentic/ingest`
-> runtime ingest
-> `app/ingestion/chunker.py`
-> retrieval child chunks + reasoning parent chunks
-> BM25 + vector records + document graph

Agentic question
-> `/agentic/query`
-> `app/reasoning/agent_graph.py`
-> router
-> planner
-> retrieve
-> reason
-> verify
-> compose
-> answer + trace
```

### 3.4 Inventory Intelligence Flow

```text
Inventory question
-> `/inventory/route` or `/inventory/ask` or `/inventory/agentic/ask`
-> `app/services/inventory_service.py`
-> intent classification
-> preference extraction
-> multi-stage retrieval
-> evidence contract build
-> deterministic scoring
-> plan enrichment
-> final answer verification
-> answer / stream / abstain
```

For complex inventory questions, the internal logic now looks closer to this:

```text
question
-> classify
-> decompose
-> retrieve candidates
-> rerank/filter
-> normalize facts
-> build evidence contract
-> score decisions
-> explain decision
-> verify claims
-> return answer
```

## 4. Folder-By-Folder Explanation

## `app/api`

This is the HTTP boundary.

- `routes_ingest.py`: simple legal/tax ingestion and index building
- `routes_query.py`: classic legal/tax retrieval and answer generation
- `routes_eval.py`: dataset-level evaluation entrypoint
- `routes_agentic.py`: structured legal runtime status, ingest, query, evaluation, traces
- `routes_inventory.py`: inventory catalog, search, routing, ask, agentic ask, business signals, sync, traces

These files should stay thin. Their job is transport, validation, and error handling, not business logic.

## `app/core`

This is the shared contract layer.

- `schemas.py`: biggest shared Pydantic contract file for both the legal/tax and inventory systems
- `settings.py`: environment-driven configuration
- `utils.py`: normalization, query cleanup, helper utilities

If you want to understand the input/output shape of the repo, start here.

## `app/ingest`

This is the older ingestion path used by the classic `/ingest` endpoint.

The mental model:

```text
raw PDF
-> parse text
-> chunk pages
-> write JSONL
-> later build sparse/dense indexes
```

This path is simpler and more document-centric than the newer agentic ingestion path.

## `app/ingestion`

This is the structured legal-document pipeline used for the agentic runtime.

Important idea:

```text
legal document
-> linked document structure
-> retrieval child chunks
-> reasoning parent chunks
-> better support for graph expansion and multi-step reasoning
```

`app/ingestion/chunker.py` is central here. It creates:

- retrieval-sized chunks for search
- larger reasoning chunks for synthesis
- anchor/context style chunk variants

This is much closer to a law-aware retrieval architecture than the older page chunker.

## `app/retrieval`

This is the retrieval engine layer.

It contains:

- sparse retrieval
- dense retrieval
- hybrid retrieval
- reranking
- BM25 indexing
- vector store abstractions
- graph expansion
- query transformation

There are effectively two retrieval styles in the repo:

```text
Classic path
-> sparse + dense + simple fusion

Structured path
-> BM25 + vector retrieval + query plan + reranking + graph expansion
```

`app/retrieval/hybrid.py` powers the classic hybrid legal/tax retrieval path.

`app/retrieval/hybrid_retriever.py` is the richer structured retriever used by the agentic legal runtime.

## `app/generation`

This is the grounded answer layer for the classic legal/tax flow.

- `generator.py`: prompt construction, abstention checks, model calling, answer parsing
- `citations.py`: marker creation and citation rendering

Mental model:

```text
retrieved hits
-> citation markers
-> grounded prompt
-> JSON-like answer structure
-> inline citation rendering
```

This layer is evidence-first. It is not supposed to hallucinate beyond the retrieved support.

## `app/reasoning`

This is the orchestration layer for the agentic legal runtime.

`agent_graph.py` shows the cleanest state machine in the repo:

```text
router
-> planner
-> retrieve
-> reason
-> verify
-> compose
```

It can run through LangGraph when available, or a Python fallback loop otherwise.

That is important: the project is designed to degrade gracefully instead of depending fully on one framework.

## `app/inventory`

This is now a full subsystem, not a side feature.

Key responsibilities are split here:

- `intent.py`: question-family classification
- `preferences.py`: budget, product type, style, and other preference extraction
- `ontology.py`: product type/family/category relationships
- `policy.py`: the frozen contract for supported families, default execution paths, abstain triggers, and canonical evals
- `reranker.py`: inventory-aware ranking features
- `evidence_contract.py`: normalized product facts and allowed-claim package
- `decisioning.py`: deterministic scoring for recommendation, comparison, restock
- `planner.py`: converts scored evidence into an explicit answer plan
- `verifier.py`: checks final text against allowed claims and evidence
- `storage.py`: mirrored inventory storage abstraction
- `memory.py`: conversation memory resolution

The inventory stack is the most advanced reasoning surface in the repo right now.

## `app/services`

This is the orchestration boundary between routes and domain logic.

Important files:

- `inventory_service.py`: main inventory orchestrator and the largest operational brain in the repo
- `runtime_service.py`: structured legal agentic runtime
- `query_service.py`: legal/tax query service boundary
- `ingest_service.py`: service-level ingestion logic
- `evaluation_service.py`: evaluation support

If you want to know where the real workflow decisions happen, this folder matters more than the route layer.

## `app/domain`

This holds shared legal domain models and taxonomy concepts.

It helps keep the structured legal reasoning side from collapsing into raw dictionaries.

## `app/eval`

Evaluation and metrics logic live here.

This part exists, but the inventory roadmap still shows evaluation depth as an unfinished area.

## `tests`

The tests tell you where the repo is strongest today.

Broadly:

- legal/tax retrieval and generation tests validate the classic stack
- agentic tests validate the structured runtime
- `test_inventory_api.py` and `test_inventory_intelligence.py` validate the newer inventory reasoning path

The inventory tests are especially important because that subsystem now depends on routing, evidence normalization, scoring, planning, and verification all staying aligned.

## 5. The Most Important Runtime Boundaries

These are the files that define the project more than any others.

### `app/main.py`

This is the app assembly point. It tells you which systems are officially exposed and supported.

### `app/core/schemas.py`

This is the shared contract backbone.

Why it matters:

```text
Weak schemas
-> hidden coupling
-> route/service drift
-> impossible debugging

Strong schemas
-> traceable execution
-> predictable responses
-> safer refactors
```

### `app/services/inventory_service.py`

This is the most strategically important file today.

It is doing more than CRUD or search. It is coordinating:

- routing
- retrieval
- reranking
- business-signal integration
- plan building
- evidence contracts
- verification
- streaming answers

If this file becomes muddy, the entire inventory system becomes impossible to reason about.

### `app/reasoning/agent_graph.py`

This is the cleanest expression of the newer agentic architecture on the legal side.

It shows the intended pattern for bounded reasoning loops.

## 6. Inventory Architecture, In Plain English

The inventory subsystem is where most of the project evolution has happened.

The correct mental model is:

```text
inventory chat is not "search and then let the LLM talk"

it is:
question understanding
-> retrieval
-> fact normalization
-> deterministic decisioning
-> explanation
-> verification
```

That is a much stronger architecture.

The important internal pipeline is roughly:

```text
User asks inventory question
-> classify intent
-> detect preferences and constraints
-> search catalog/business evidence
-> build `InventoryEvidenceContract`
-> score candidates with `InventoryDecisionScorer`
-> enrich answer with `InventoryAnswerPlanner`
-> verify final wording with `InventoryFinalAnswerVerifier`
-> return answer or abstain
```

This is why recent work in the repo focused on:

- evidence contracts
- bounded multi-step planning
- deterministic ranking
- verification rules

That is the right direction. Otherwise the system would sound smart while making unstable decisions.

## 7. What Has Been Implemented So Far

Based on `todo_retrival.md`, the project has already moved well beyond a basic retrieval chatbot.

Current status in plain language:

- Phase 0 is now done: inventory chat has an explicit policy contract for families, execution paths, abstain rules, and eval coverage
- Phase 1 is done: question classification and routing exist
- Phase 2 is done: multi-stage retrieval exists, including lexical recovery, alias handling, reranking, and metadata-aware filtering
- Phase 3 is done: the answer layer works from structured evidence contracts instead of raw hits alone
- Phase 4 is done: compare, bundle, restock, diagnosis, and operational planning all have bounded decomposition paths
- Phase 5 is done: evidence contracts feed planning and verification
- Phase 6 is done: deterministic scoring exists for recommendation, comparison, prioritization, restock, and alternatives
- Phase 7 is done: product-fit verification and hard-abstain behavior are enforced
- Phase 8 is done: the eval matrix now covers the major agentic and hard-constraint families
- Phase 9 is done: traces expose rejected candidates and score breakdowns

The important strategic point:

```text
the repo's center of gravity has shifted
from "retrieve relevant text"
to "retrieve evidence, score it, explain it, verify it"
```

That is a major architectural upgrade.

## 8. How To Read The Codebase Without Getting Lost

If you are onboarding, read in this order:

### Path A: learn the whole repo fast

```text
1. `app/main.py`
-> what is exposed

2. `app/api/routes_inventory.py`
-> biggest modern surface area

3. `app/services/inventory_service.py`
-> orchestration center

4. `app/inventory/evidence_contract.py`
-> what the system believes counts as evidence

5. `app/inventory/decisioning.py`
-> how ranking decisions are actually made

6. `app/inventory/planner.py`
-> how the system turns scores into answer structure

7. `app/inventory/verifier.py`
-> how unsupported claims are blocked

8. `app/api/routes_query.py`
-> original classic RAG entrypoint

9. `app/retrieval/hybrid.py`
-> classic hybrid retrieval

10. `app/generation/generator.py`
-> classic grounded answer generation

11. `app/api/routes_agentic.py`
-> newer legal reasoning runtime surface

12. `app/reasoning/agent_graph.py`
-> graph-style reasoning loop
```

### Path B: only learn the classic legal/tax system

```text
`routes_ingest.py`
-> `app/ingest/*`
-> `routes_query.py`
-> `app/retrieval/hybrid.py`
-> `app/generation/generator.py`
```

### Path C: only learn the inventory system

```text
`routes_inventory.py`
-> `inventory_service.py`
-> `intent.py`
-> `preferences.py`
-> `reranker.py`
-> `evidence_contract.py`
-> `decisioning.py`
-> `planner.py`
-> `verifier.py`
```

## 9. Design Strengths

The strongest ideas in the repo right now are:

- explicit schemas instead of loose payloads
- evidence-first answer generation
- bounded reasoning loops
- deterministic scoring where ranking should be stable
- verification before final output
- traceability across route, plan, evidence, and answer layers

Those are real system-design strengths, not cosmetic ones.

## 10. Design Risks

These are the main risks you should keep in mind.

### 1. The repo has multiple generations of architecture in one place

That is powerful, but it can also create drift:

```text
old path still works
-> new path gets added
-> shared contracts evolve
-> duplicated logic appears
```

This is already visible in the ingestion split and in the coexistence of classic versus agentic flows.

### 2. `inventory_service.py` can become too powerful

This file is strategically central, but it is also the highest refactor risk because it owns too many decisions.

### 3. Evaluation is behind architecture

The inventory roadmap is increasingly mature, but evaluation coverage still lags behind the sophistication of the reasoning path.

That is dangerous. Strong architecture without strong measurement eventually drifts.

## 11. Practical Extension Guide

If you want to add a new feature, use this decision rule:

### Add it to the classic legal/tax path when:

- the question is mostly direct retrieval
- evidence can be answered from a few chunks
- multi-step planning is unnecessary

### Add it to the agentic legal path when:

- the question needs decomposition
- multiple retrieval rounds are justified
- graph/context expansion matters

### Add it to the inventory stack when:

- the feature needs catalog facts plus business signals
- ranking must be stable and explainable
- the system should verify supported claims before speaking

## 12. One-Sentence Summary

The project today is best understood as a **shared FastAPI platform for three evidence-driven systems: classic Bangla legal/tax RAG, structured agentic legal reasoning, and an inventory intelligence engine that increasingly behaves like a deterministic decision-support system rather than a plain chatbot.**
