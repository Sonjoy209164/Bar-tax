# Retrieval Theory And Build Notes

This file is the running theory log for the retrieval stack.

The point is simple:

- record what we built
- record why it exists
- make future changes easier to judge

## Current Principle

Do not let the model speak confidently when routing and retrieval are still uncertain.

For this system, that means:

1. classify the question before retrieval
2. choose the answer path intentionally
3. clarify or abstain when the question is too vague
4. keep traces so we can inspect why the system behaved that way

## What We Have Done

### Phase 1: Question Family Routing

Implemented in:

- `app/services/inventory_service.py`
- `app/core/schemas.py`
- `tests/test_inventory_api.py`

What changed:

- added explicit question families:
  - `exact_lookup`
  - `comparison`
  - `recommendation`
  - `diagnosis_root_cause`
  - `planning_agentic_workflow`
  - `no_match_or_abstain`
- route metadata is now stored in traces
- route summaries and decision factors are now visible for debugging

Why it matters:

- one generic retrieval path is too blunt
- routing is the control plane for everything that comes after
- without route traces, it is hard to know whether a bad answer came from weak retrieval or bad execution choice

### Phase 1 Gap Closed: No-Match Or Abstain Behavior

Implemented in:

- `app/services/inventory_service.py`
- `tests/test_inventory_api.py`

What changed:

- `no_match_or_abstain` now affects the real ask flow instead of living only in route metadata
- normal ask now turns underspecified requests into clarification behavior
- normal ask now abstains for non-inventory or unsupported questions
- agentic ask now short-circuits before retrieval when the route already says clarification or abstain is the safer move
- guarded replies intentionally suppress weak hits from the user-facing response while still preserving retrieved evidence in traces

Why it matters:

- before this, the classifier could correctly say "this is underspecified" while the answer path still returned weak semantic guesses
- that is the exact failure mode that makes chatbots sound plausible while being operationally unsafe
- clarification is better than bluffing
- abstention is better than pretending an unrelated product is a valid answer

### Phase 2 Start: Lexical Recovery And Exact Alias Handling

Implemented in:

- `app/services/inventory_service.py`
- `tests/test_inventory_api.py`

What changed:

- retrieval now builds an explicit alias surface for each product
- alias sources include:
  - explicit metadata aliases such as `search_aliases`, `alternate_names`, `sku_aliases`, and model identifiers
  - generated compact SKU variants such as `CMP-LTP-901 -> cmpltp901`
  - generated compact name variants such as `smart watch -> smartwatch`
- lexical scoring now rewards exact and near-exact alias matches
- query-term coverage now counts alias tokens, not just the base name and SKU fields
- vector search text now also carries alias text so dense retrieval gets the same recovery hints

Why it matters:

- many real catalog questions are not asked with the exact stored name
- users collapse SKUs, remove punctuation, or use internal nicknames
- without alias-aware lexical recovery, the system can look smart on generic semantic search while still failing obvious exact lookup requests

What this fixes:

- compact SKU queries like `cmpltp901`
- explicit alias lookups like `cc16 pro`
- collapsed name variants like `smartwatch`

### Phase 2 Next Slice: Explicit Pool Combination And Trace Diagnostics

Implemented in:

- `app/services/inventory_service.py`
- `app/core/schemas.py`
- `tests/test_inventory_api.py`

What changed:

- dense and lexical candidates are now generated as separate pools first
- those pools are then merged explicitly before type gating and reranking
- retrieval traces now record stage counts such as:
  - `dense_pool_candidates`
  - `lexical_pool_candidates`
  - `merged_pool_candidates`
  - `type_gated_candidates`
  - `exact_lookup_candidates`
  - `lexical_anchor_candidates`
  - `reranked_candidates`
  - `returned_hits`
- agentic retrieval steps now also carry their own per-step stage counts

Why it matters:

- before this, lexical and dense evidence were effectively mixed inside one loop
- that worked, but it hid where candidate quality was being won or lost
- once retrieval starts getting more sophisticated, hidden mixing becomes a debugging tax
- explicit pool accounting makes it much easier to answer:
  - did dense retrieval miss?
  - did lexical recovery save the lookup?
  - did type gating over-prune?
  - did reranking collapse a good merged pool into a weak final shortlist?

## Design Choices We Are Following

### Clarify Before Recommending

When the question is inventory-related but underspecified, we ask for:

- product type
- category
- budget
- brand

Reason:

- the retriever may still return items
- returned items are not the same as reliable intent resolution

### Hide Weak Retrieval Guesses From The Main Response

For `no_match_or_abstain` guard cases, the API returns:

- `total_hits = 0`
- `hits = []`

while traces still keep:

- retrieved product ids
- reranked product ids

Reason:

- UI and calling services should not treat weak guesses as validated answers
- traces still preserve the evidence we need for debugging and evaluation

### Keep The System Deterministic In Guarded Cases

Guarded clarification and abstain flows are designed to stay on the deterministic path.

Reason:

- when the system is already uncertain, adding a generative layer usually increases style before it increases truth
- deterministic guardrails are the right move at this stage

### Recover Exact Candidates Before Semantic Neighbors

For exact-ish product lookup, lexical recovery should win before dense similarity gets to free-associate.

Reason:

- vector similarity is useful for relatedness
- exact lookup is about identity
- a retriever that cannot reliably recover identity will always make downstream reasoning fragile

### Make Retrieval Stages Observable

If retrieval has multiple stages, those stages need visible counts.

Reason:

- otherwise we only see the final hits and guess what happened upstream
- stage counts turn retrieval into an inspectable system instead of a black box
- this is especially important before adding heavier reranking and evaluation

## What This Means Architecturally

We are not building "just prompt engineering."

We are building a decision system with these layers:

```text
question
-> classify
-> route
-> decide whether to clarify, abstain, or retrieve
-> retrieve and rerank only when justified
-> answer with grounded evidence
```

That is the foundation we can later reuse in other domains, even though inventory is the first domain.

## What Is Next

The next high-value step is Phase 2 from `todo_retrival.md`:

- exact-match boosting for product names and SKU hits
- category and product-type gating before final ranking
- metadata-aware reranking

Reason:

- Phase 1 now decides better when to answer and when not to
- the first slices of Phase 2 now recover and expose more candidates correctly
- the next bottleneck is ranking discipline after the pools are merged
