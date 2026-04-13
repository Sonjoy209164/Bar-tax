# Agentic Legal RAG TODO

Working checklist for the future `agentic legal RAG` version of this project.

This file is meant to be used as our implementation board:

- you pick one task
- I implement it
- we test it
- we move to the next one

## Build Strategy

- [ ] Build `document-specialized v1` for the `Bangladesh Income Tax Act 2023` first.
- [ ] Keep the architecture `generic-capable`, but do not optimize for all legal documents yet.
- [ ] Preserve `legal hierarchy first`, `chunking second`.
- [ ] Use `retrieval child chunks` and `reasoning parent context`.
- [ ] Use `hybrid retrieval + reranking + evidence packs` before reasoning.
- [ ] Use `bounded agentic reasoning`, not unrestricted loops.
- [ ] Enforce `grounded answers only`.
- [ ] Enforce `granular citations`.
- [ ] Enforce `unsupported fact refusal`.

## Phase 0: Freeze The Target Architecture

- [ ] Finalize the canonical target architecture for this repo.
- [ ] Finalize the list of supported question families.
- [ ] Finalize the bounded reasoning policy.
- [ ] Finalize the answer format policy.
- [ ] Finalize the refusal policy.
- [ ] Finalize the trace and observability requirements.

## Phase 1: Domain Model

- [ ] Create `app/domain/legal_types.py`
- [ ] Create `app/domain/models.py`
- [ ] Create `app/domain/schemas.py`
- [ ] Create `app/domain/citations.py`
- [ ] Define `LegalNodeType` enum:
- [ ] `act`
- [ ] `part`
- [ ] `chapter`
- [ ] `section`
- [ ] `subsection`
- [ ] `clause`
- [ ] `proviso`
- [ ] `explanation`
- [ ] `table`
- [ ] `illustration`
- [ ] `definition`
- [ ] Define `LegalNode` model.
- [ ] Define `Citation` model.
- [ ] Define `EvidenceItem` model.
- [ ] Define `EvidencePack` model.
- [ ] Define `QueryPlan` model.
- [ ] Define `ReasoningTrace` model.
- [ ] Define `AnswerPayload` model.
- [ ] Add tests for domain models.

## Phase 2: Query Taxonomy

- [ ] Finalize the query taxonomy for legal-tax questions.
- [ ] Add `section_lookup`
- [ ] Add `definition`
- [ ] Add `table_lookup`
- [ ] Add `rate_lookup`
- [ ] Add `amount_lookup`
- [ ] Add `date_lookup`
- [ ] Add `duration_lookup`
- [ ] Add `count_lookup`
- [ ] Add `comparison`
- [ ] Add `scenario_reasoning`
- [ ] Add `cross_section_reasoning`
- [ ] Add `eligibility`
- [ ] Add `unsupported_or_underspecified`
- [ ] Define query-routing heuristics.
- [ ] Define when a question should skip the agent loop.
- [ ] Add tests for query classification.

## Phase 3: LangGraph State Design

- [ ] Create `app/reasoning/state.py`
- [ ] Define the `AgentState` model.
- [ ] Track `question`.
- [ ] Track `query_type`.
- [ ] Track `facts_from_user`.
- [ ] Track `facts_found`.
- [ ] Track `missing_facts`.
- [ ] Track `rules_found`.
- [ ] Track `exceptions_found`.
- [ ] Track `open_issues`.
- [ ] Track `retrieval_attempts`.
- [ ] Track `verification_failures`.
- [ ] Track `needs_more_retrieval`.
- [ ] Track `draft_answer`.
- [ ] Track `final_answer`.
- [ ] Track `trace_id`.
- [ ] Add tests for state transitions.

## Phase 4: Parser Abstraction

- [ ] Create `app/ingestion/parser_base.py`
- [ ] Create `app/ingestion/llamaparse_parser.py`
- [ ] Create `app/ingestion/fallback_parser.py`
- [ ] Add `PARSER_PROVIDER=llamaparse|fallback`
- [ ] Define a clean parser interface.
- [ ] Preserve structured headings.
- [ ] Preserve section boundaries.
- [ ] Preserve tables.
- [ ] Preserve provisos and explanations.
- [ ] Add parser output validation.
- [ ] Add parser tests.

## Phase 5: Structure Builder

- [ ] Create `app/ingestion/structure_builder.py`
- [ ] Build a canonical legal tree from parsed text.
- [ ] Preserve:
- [ ] Act
- [ ] Part
- [ ] Chapter
- [ ] Section
- [ ] Subsection
- [ ] Clause
- [ ] Proviso
- [ ] Explanation
- [ ] Table
- [ ] Build `node_id`, `parent_id`, `child_ids`.
- [ ] Build section-aware path metadata.
- [ ] Preserve page ranges.
- [ ] Add tests for hierarchy preservation.

## Phase 6: Metadata Tagging

- [ ] Create `app/ingestion/metadata_tagger.py`
- [ ] Attach:
- [ ] `document_id`
- [ ] `act_title`
- [ ] `part_number`
- [ ] `part_title`
- [ ] `chapter_number`
- [ ] `chapter_title`
- [ ] `section_number`
- [ ] `subsection_number`
- [ ] `clause_number`
- [ ] `page_number`
- [ ] `chunk_type`
- [ ] `parent_id`
- [ ] `child_ids`
- [ ] Add citability labels.
- [ ] Add metadata validation tests.

## Phase 7: Parent-Child Linking

- [ ] Create `app/ingestion/parent_child_linker.py`
- [ ] Link child retrieval units to parent reasoning units.
- [ ] Attach provisos to their governing rule.
- [ ] Attach explanations to their governing rule.
- [ ] Attach tables to their governing section.
- [ ] Preserve sibling links for clause expansion.
- [ ] Add graph-linking tests.

## Phase 8: Document Store

- [ ] Create `app/ingestion/document_store.py`
- [ ] Persist canonical legal structure to disk.
- [ ] Support reload without reparsing PDF.
- [ ] Store normalized legal graph as JSON.
- [ ] Store parent nodes and child chunks separately.
- [ ] Add document-store tests.

## Phase 9: Chunking

- [ ] Create `app/ingestion/chunker.py` for the new architecture.
- [ ] Build child retrieval chunks of about `150-250 tokens`.
- [ ] Build parent reasoning chunks of about `1200-2200 tokens`.
- [ ] Keep legal-unit boundaries intact.
- [ ] Do not split inside important clause lists unless unavoidable.
- [ ] Preserve table rows as structured artifacts.
- [ ] Tag chunks by legal role:
- [ ] `definition`
- [ ] `rule`
- [ ] `exception`
- [ ] `proviso`
- [ ] `explanation`
- [ ] `table`
- [ ] Add chunking tests.

## Phase 10: Embedding Layer

- [ ] Create `app/retrieval/embedder.py`
- [ ] Add `text-embedding-3-large` integration.
- [ ] Make embedding dimensions configurable.
- [ ] Add provider abstraction for future embedding swaps.
- [ ] Add embedding tests and smoke checks.

## Phase 11: Vector Store Layer

- [ ] Create `app/retrieval/vector_store_base.py`
- [ ] Create `app/retrieval/pinecone_store.py`
- [ ] Create `app/retrieval/milvus_store.py`
- [ ] Add `VECTOR_DB=pinecone|milvus`
- [ ] Support metadata filtering.
- [ ] Support top-k dense retrieval.
- [ ] Add vector store tests.

## Phase 12: BM25 Layer

- [x] Create `app/retrieval/bm25_index.py`
- [x] Build BM25 over child chunks.
- [x] Support field-aware lexical retrieval.
- [x] Preserve section-aware weighting.
- [x] Add BM25 tests.

## Phase 13: Query Transformation

- [x] Create `app/retrieval/query_transformer.py`
- [x] Transform one legal query into `3-5` focused sub-queries.
- [x] Expand legal terminology.
- [x] Expand definitional ambiguity.
- [x] Expand scenario decomposition.
- [x] Expand section reference disambiguation.
- [x] Return a typed `QueryPlan`.
- [x] Add query-transformer tests.

## Phase 14: Hybrid Retrieval

- [x] Create `app/retrieval/hybrid_retriever.py`
- [x] Merge dense + BM25 candidates.
- [x] Add metadata filtering before rerank.
- [x] Add parent/child graph expansion.
- [x] Return top evidence candidates plus parent context.
- [x] Add hybrid retrieval tests.

## Phase 15: Graph Expansion

- [x] Create `app/retrieval/graph_expander.py`
- [x] Expand from child hit to parent section.
- [x] Expand sibling clauses when needed.
- [x] Expand attached provisos.
- [x] Expand attached explanations.
- [x] Expand linked tables.
- [x] Add graph-expansion tests.

## Phase 16: Reranker

- [x] Create `app/retrieval/reranker.py` in the new architecture.
- [x] Add `Cohere Rerank` provider integration.
- [x] Keep reranker behind an interface.
- [x] Rerank only bounded candidate sets.
- [x] Record reranker scores in traces.
- [x] Add reranker tests.

## Phase 17: Evidence Pack Builders

- [x] Create `app/retrieval/evidence_packs.py`
- [x] Build `DefinitionEvidencePack`
- [x] Build `SectionLookupEvidencePack`
- [x] Build `RateTableEvidencePack`
- [x] Build `ScenarioEvidencePack`
- [x] Build `CrossSectionEvidencePack`
- [x] Build `ComparisonEvidencePack`
- [x] Ensure each evidence pack includes linked parent context.
- [x] Add evidence pack tests.

## Phase 18: Reasoning Graph

- [ ] Create `app/reasoning/agent_graph.py`
- [ ] Create `app/reasoning/nodes_router.py`
- [ ] Create `app/reasoning/nodes_planner.py`
- [ ] Create `app/reasoning/nodes_retrieve.py`
- [ ] Create `app/reasoning/nodes_reason.py`
- [ ] Create `app/reasoning/nodes_verify.py`
- [ ] Create `app/reasoning/nodes_compose.py`
- [ ] Create `app/reasoning/evidence_builder.py`
- [ ] Create a bounded LangGraph loop:
- [ ] Router
- [ ] Planner
- [ ] Retrieve
- [ ] Reason
- [ ] Gap-check
- [ ] Retrieve-again if needed
- [ ] Verify
- [ ] Compose
- [ ] Enforce max reasoning steps.
- [ ] Add reasoning-flow tests.

## Phase 19: Guardrails

- [ ] Create `app/reasoning/nli_guardrail.py`
- [ ] Create `app/reasoning/answer_policy.py`
- [ ] Verify every factual claim against evidence.
- [ ] Remove unsupported claims.
- [ ] Replace unsupported claims with:
- [ ] `Information not found in retrieved evidence`
- [ ] Add deterministic validators for:
- [ ] section numbers
- [ ] rates
- [ ] dates
- [ ] thresholds
- [ ] table values
- [ ] Add guardrail tests.

## Phase 20: Prompts

- [ ] Create `app/core/prompts.py`
- [ ] Add planner prompt.
- [ ] Add query-transformer prompt.
- [ ] Add reasoner prompt.
- [ ] Add verifier prompt.
- [ ] Add composer prompt.
- [ ] Keep all prompts editable and versionable.

## Phase 21: Services

- [ ] Create `app/services/ingest_service.py`
- [ ] Create `app/services/query_service.py`
- [ ] Create `app/services/citation_service.py`
- [ ] Create `app/services/evaluation_service.py`
- [ ] Move orchestration out of routes and into services.
- [ ] Add service-layer tests.

## Phase 22: API

- [ ] Create `app/api/main.py`
- [ ] Create `app/api/routes_ingest.py`
- [ ] Create `app/api/routes_query.py`
- [ ] Create `app/api/routes_health.py`
- [ ] Add `GET /trace/{trace_id}`
- [ ] Validate request schema strongly.
- [ ] Return:
- [ ] `answer`
- [ ] `citations`
- [ ] `reasoning_summary`
- [ ] `missing_facts`
- [ ] `confidence`
- [ ] `trace_id`
- [ ] Add API integration tests.

## Phase 23: Security And Robustness

- [ ] Create `app/core/security.py`
- [ ] Create `app/core/exceptions.py`
- [ ] Treat retrieved text as untrusted.
- [ ] Prevent prompt injection from retrieved evidence.
- [ ] Add request validation hooks.
- [ ] Add rate-limiting hook points.
- [ ] Handle parser failures gracefully.
- [ ] Handle vector DB failures gracefully.
- [ ] Handle reranker failures gracefully.
- [ ] Handle LLM failures gracefully.

## Phase 24: Logging And Tracing

- [ ] Create `app/core/logging.py` for the new architecture.
- [ ] Add structured logs for each query step.
- [ ] Add trace IDs.
- [ ] Record:
- [ ] router decision
- [ ] query plan
- [ ] retrieval candidates
- [ ] reranked candidates
- [ ] evidence pack
- [ ] verification failures
- [ ] final answer outcome
- [ ] Add `/trace/{trace_id}` output model.

## Phase 25: Evaluation

- [ ] Create `evals/golden_set.jsonl`
- [ ] Create `evals/run_evals.py`
- [ ] Add evals for:
- [ ] direct lookup accuracy
- [ ] section citation accuracy
- [ ] scenario reasoning accuracy
- [ ] table/rate extraction accuracy
- [ ] unsupported-claim refusal accuracy
- [ ] retrieval relevance
- [ ] reranker improvement
- [ ] guardrail effectiveness
- [ ] Report evaluation outputs cleanly.

## Phase 26: Tests

- [ ] Create `tests/test_chunking.py`
- [ ] Create `tests/test_metadata.py`
- [ ] Create `tests/test_query_transformer.py`
- [ ] Create `tests/test_hybrid_retrieval.py`
- [ ] Create `tests/test_reranker.py`
- [ ] Create `tests/test_reasoning_flow.py`
- [ ] Create `tests/test_nli_guardrail.py`
- [ ] Create `tests/test_api.py`
- [ ] Keep tests fast enough for local iteration.

## Phase 27: Scripts And DevEx

- [ ] Create `scripts/ingest_pdf.py`
- [ ] Create `scripts/reindex.py`
- [ ] Create `scripts/demo_query.py`
- [ ] Create `.env.example`
- [ ] Add Dockerfile.
- [ ] Add docker-compose.
- [ ] Document provider env vars:
- [ ] `LLM_PROVIDER`
- [ ] `VECTOR_DB`
- [ ] `PARSER_PROVIDER`
- [ ] `EMBEDDING_MODEL`
- [ ] `RERANKER_MODEL`

## Phase 28: README

- [ ] Write architecture summary.
- [ ] Write setup instructions.
- [ ] Write ingestion instructions.
- [ ] Write query API usage.
- [ ] Write Docker usage.
- [ ] Write evaluation instructions.
- [ ] Write design decisions.
- [ ] Write tradeoffs.
- [ ] Write limitations.
- [ ] Write next production upgrades.

## Suggested Order To Give Me Tasks

- [ ] 1. Canonical `LegalNode` schema
- [ ] 2. Query taxonomy
- [ ] 3. LangGraph `AgentState`
- [ ] 4. Parser abstraction
- [ ] 5. Structure builder
- [ ] 6. Metadata tagger
- [ ] 7. Parent-child linker
- [ ] 8. Document store
- [ ] 9. New chunker
- [ ] 10. Embedder abstraction
- [ ] 11. Vector-store abstraction
- [ ] 12. BM25 layer
- [ ] 13. Query transformer
- [ ] 14. Hybrid retriever
- [ ] 15. Graph expander
- [ ] 16. Reranker abstraction
- [ ] 17. Evidence pack builders
- [ ] 18. LangGraph reasoning loop
- [ ] 19. Guardrails
- [ ] 20. Services
- [ ] 21. API
- [ ] 22. Evaluation
- [ ] 23. Tests
- [ ] 24. Docker + README

## Definition Of Done For The Agentic Version

- [ ] Legal hierarchy is preserved end to end.
- [ ] Parent-child linking works.
- [ ] Hybrid retrieval is working.
- [ ] Reranking is working.
- [ ] Evidence packs are query-type aware.
- [ ] Bounded reasoning loop is working.
- [ ] Unsupported claims are blocked.
- [ ] Answers include granular citations.
- [ ] Evals are runnable.
- [ ] Docker setup works.
- [ ] README is complete.
