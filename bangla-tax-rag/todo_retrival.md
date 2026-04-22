# TODO Retrieval And Complex Reasoning

Working implementation board for improving retrieval quality and chat responses on complex reasoning questions.

This file is meant to turn strategy into build steps:

- pick one task
- implement it
- test it
- measure whether it actually improved answers

## Goal

Build an industry-grade retrieval and reasoning stack that:

- classifies the question correctly before retrieval
- retrieves evidence in multiple stages, not just vector similarity
- decomposes complex questions into smaller evidence needs
- reasons over structured evidence instead of raw hits
- uses deterministic decision logic where possible
- verifies claims before returning the answer
- measures failure modes, not just "good sounding" responses

## Operating Principle

Do not rely on a stronger model to hide weak retrieval.

The target pipeline is:

```text
question
-> classify
-> route
-> decompose
-> retrieve candidates
-> filter and rerank
-> pack evidence
-> reason deterministically where possible
-> verify
-> generate final response
```

## Phase 0: Freeze The Retrieval Architecture

- [ ] Finalize the supported question families for inventory chat.
- [ ] Finalize which question types stay deterministic.
- [ ] Finalize which question types require agentic decomposition.
- [ ] Finalize when the system must abstain.
- [ ] Finalize the evidence contract schema used by the answer layer.
- [ ] Finalize the evaluation questions for complex reasoning.

Success criteria:

```text
Every incoming question has a defined execution path instead of falling through one generic retrieval flow.
```

## Phase 1: Question Classification And Routing

Question families to support:

- [ ] `exact_lookup`
- [ ] `comparison`
- [ ] `recommendation`
- [ ] `diagnosis_root_cause`
- [ ] `planning_agentic_workflow`
- [ ] `no_match_or_abstain`

Implementation tasks:

- [x] Add deterministic routing rules for question family classification.
- [x] Detect exact product reference vs category intent vs planning intent.
- [x] Detect compare language such as `compare`, `vs`, `difference`, `better`.
- [x] Detect recommendation language such as `best`, `recommend`, `which should I buy`.
- [x] Detect diagnosis language such as `why`, `root cause`, `what went wrong`.
- [x] Detect workflow/planning language such as `restock`, `bundle`, `what should we do next`.
- [x] Detect when the request is underspecified and should move to abstain or follow-up.
- [x] Return route confidence.
- [x] Persist route decision in trace metadata.
- [x] Add tests for route classification.

Success criteria:

```text
The system chooses different retrieval and reasoning paths for lookup, comparison, recommendation, diagnosis, workflow, and abstain cases.
```

## Phase 2: Multi-Stage Retrieval Stack

Target retrieval stages:

- [ ] lexical retrieval
- [ ] dense retrieval
- [ ] metadata filtering
- [ ] entity / SKU / exact alias lookup
- [ ] reranking
- [ ] evidence packing

Implementation tasks:

- [x] Add lexical-first recovery for exact and near-exact product lookups.
- [ ] Combine lexical and dense candidate pools before reranking.
- [ ] Use normalized vector metadata for hard filters on specs and constraints.
- [x] Add product alias handling for name variants, SKU variants, and spec aliases like `1TB` vs `1024GB`.
- [ ] Add exact-match boosting for product names and SKU hits.
- [ ] Add category and product-type gating before final ranking.
- [ ] Add metadata-aware reranking for spec-heavy queries.
- [ ] Add business-signal-aware reranking for operational queries.
- [ ] Record per-stage candidate counts in traces.
- [ ] Add evals for lexical miss recovery and alias recovery.

Success criteria:

```text
The retriever returns the right candidate set for exact, spec-heavy, and comparison-heavy questions before the answer layer starts speaking.
```

## Phase 3: Retrieve Facts, Not Just Documents

Evidence required for complex reasoning:

- [ ] normalized specs
- [ ] availability
- [ ] pricing
- [ ] business signals
- [ ] lead time
- [ ] demand
- [ ] margin
- [ ] comparable alternatives
- [ ] contradictions
- [ ] missing facts

Implementation tasks:

- [ ] Define a normalized fact model for retrieved product evidence.
- [ ] Pull structured specs from `attributes` and curated vector metadata.
- [ ] Pull business metrics from the business signal store.
- [ ] Mark fields as present, missing, conflicting, or inferred.
- [ ] Attach evidence provenance for each fact.
- [ ] Detect stale or contradictory catalog vs business values.
- [ ] Expose `missing_facts` explicitly to the answer planner.
- [ ] Add tests for fact extraction and contradiction detection.

Success criteria:

```text
The answer layer works from structured facts and evidence gaps, not from vague text snippets alone.
```

## Phase 4: Complex Query Decomposition

Complex questions should be decomposed into sub-queries.

Examples:

- [ ] restock priority
- [ ] bundle recommendation
- [ ] compare two or more products
- [ ] root cause analysis
- [ ] operational planning

Implementation tasks:

- [ ] Add a retrieval planner for multi-step inventory questions.
- [ ] Split a complex question into sub-goals.
- [ ] Create a retrieval request per sub-goal.
- [ ] Support plan steps like `find candidates`, `rank`, `check constraints`, `find complements`, `compose`.
- [ ] Merge sub-query outputs into one evidence bundle.
- [ ] Keep decomposition bounded and traceable.
- [ ] Add tests for AC-restock-and-bundle style questions.

Example target:

```text
Which AC should I restock first, and what should I bundle with it?
-> find AC candidates
-> score by stock, demand, margin, lead time
-> find cross-sell accessories
-> check operational constraints
-> compose final recommendation
```

Success criteria:

```text
Complex questions are answered through explicit sub-steps instead of one broad retrieval call.
```

## Phase 5: Evidence Contract For The Answer Layer

Do not pass raw hits directly into answer generation.

Evidence contract should contain:

- [ ] primary candidates
- [ ] rejected candidates and why
- [ ] required tradeoffs
- [ ] missing facts
- [ ] allowed claims
- [ ] follow-up question rules

Implementation tasks:

- [ ] Define an `EvidenceContract` or equivalent schema.
- [ ] Add candidate-level reasons for inclusion and rejection.
- [ ] Add tradeoff summaries like `better battery`, `weaker stock`, `higher margin`, `lower demand`.
- [ ] Add claim allowlist fields so the model only states supported facts.
- [ ] Add follow-up rules for missing constraints such as budget, availability, or preferred feature.
- [ ] Add trace output for evidence contract creation.
- [ ] Add tests for contract completeness.

Success criteria:

```text
The generation layer receives a structured decision package instead of an unbounded context dump.
```

## Phase 6: Deterministic Reasoning First

The model should explain decisions, not invent them.

Apply deterministic logic for:

- [ ] comparison
- [ ] recommendation
- [ ] prioritization
- [ ] restock ranking
- [ ] alternative suggestion

Implementation tasks:

- [ ] Define scoring rules for comparison and recommendation.
- [ ] Define weighted ranking rules for operational prioritization.
- [ ] Separate ranking logic from response wording.
- [ ] Make the answer plan authoritative over the final response.
- [ ] Keep the LLM as explainer where deterministic ranking is available.
- [ ] Add tests for score-based decisions and tradeoff ordering.

Success criteria:

```text
The system reaches the same ranking decision reliably even when the wording layer changes.
```

## Phase 7: Verification And Abstain Policy

Before returning the final answer:

- [ ] verify claims
- [ ] verify product-fit
- [ ] detect unsupported conclusions
- [ ] force abstain when evidence is weak

Implementation tasks:

- [ ] Check that recommended products satisfy the asked constraints.
- [ ] Check that price, stock, and spec claims exist in evidence.
- [ ] Reject category mismatch recommendations.
- [ ] Reject weak substitutions that are really cross-sell items.
- [ ] Detect when no exact match exists.
- [ ] Detect when the answer should ask a follow-up instead of pretending certainty.
- [ ] Add tests for abstain behavior and false-claim prevention.

Success criteria:

```text
The bot fails safely when evidence is incomplete instead of producing a polished wrong answer.
```

## Phase 8: Evaluation And Failure Tracking

Track these failure modes:

- [ ] wrong product type
- [ ] missed exact match
- [ ] bad comparison
- [ ] false in-stock claim
- [ ] false price claim
- [ ] false spec claim
- [ ] weak abstain behavior
- [ ] bad cross-sell
- [ ] hallucinated business rationale

Implementation tasks:

- [ ] Build an eval runner for complex reasoning questions.
- [ ] Add labeled cases for lookup, compare, recommend, diagnose, bundle, and restock.
- [ ] Track per-question-family quality, not only global accuracy.
- [ ] Track retrieval-stage misses separately from answer-stage misses.
- [ ] Track latency by route type.
- [ ] Track deterministic vs natural-answer fallback rates.
- [ ] Add a simple report showing what improved and what regressed.

Success criteria:

```text
Every retrieval or reasoning change can be measured against real failure categories before and after the patch.
```

## Phase 9: Observability And Debugging

- [ ] Log question family classification.
- [ ] Log route choice and confidence.
- [ ] Log candidate counts per retrieval stage.
- [ ] Log applied metadata filters.
- [ ] Log rejected candidates and rejection reasons.
- [ ] Log evidence gaps and abstain reasons.
- [ ] Log deterministic score breakdowns.
- [ ] Expose these details in traces without leaking them to end users.

Success criteria:

```text
When the system fails, we can tell whether the problem came from classification, retrieval, ranking, evidence packing, or generation.
```

## Suggested Build Order

- [ ] Phase 1: Question classification and routing
- [ ] Phase 2: Multi-stage retrieval stack
- [ ] Phase 3: Structured fact retrieval
- [ ] Phase 4: Query decomposition
- [ ] Phase 5: Evidence contract
- [ ] Phase 6: Deterministic reasoning
- [ ] Phase 7: Verification and abstain
- [ ] Phase 8: Evaluation and failure tracking
- [ ] Phase 9: Observability and debugging

## Definition Of Done

- [ ] Complex questions no longer rely on one generic retrieval path.
- [ ] Spec-heavy and alias-heavy questions retrieve the right candidates.
- [ ] Comparison and recommendation answers are driven by structured evidence.
- [ ] Unsupported claims are blocked before final answer generation.
- [ ] Failure modes are measured with repeatable evals.
- [ ] Traces show where the system succeeded or failed.
