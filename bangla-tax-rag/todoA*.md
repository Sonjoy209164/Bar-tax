# TODO A*: Research Roadmap For Bangla Legal-Tax RAG

## North Star

Build an A*-credible research contribution, not a chatbot.

Working thesis:

> Legal-tax RAG fails mainly because evidence selection is unconstrained: systems retrieve semantically similar text without enforcing tax-year validity, taxpayer scope, legal hierarchy, source authority, table/page structure, or citation support. This project introduces BTaxBench and TaxTrail-RAG to evaluate and improve evidence-faithful Bangla legal-tax QA over noisy Bangladesh government PDFs.

Primary contribution package:

- [ ] **BTaxBench**: Bangla legal-tax QA benchmark with gold answers, gold evidence spans, tax-year labels, taxpayer-class labels, source authority, and answerability.
- [ ] **TaxTrail-RAG**: temporal-hierarchical constrained evidence retrieval over legal document structure.
- [ ] **Citation faithfulness evaluation**: atomic legal-claim support against cited evidence, not just final answer accuracy.
- [ ] **OCR/layout robustness study**: quantify how PDF extraction quality affects retrieval and QA.

## Submission Standard

Treat the project as A*-plausible only when these are true:

- [ ] Dataset has enough scale: target 500-1,000 QA pairs, minimum credible pilot 150-250.
- [ ] Dataset has hard cases: wrong-year traps, taxpayer-class traps, table lookups, circular/act conflicts, unanswerable questions.
- [ ] Evidence labels are explicit: document id, page, section, table/row when applicable, exact supporting span.
- [ ] Evaluation has strong baselines: BM25, dense, hybrid, reranker, flat RAG, graph expansion, long-context LLM.
- [ ] Metrics include evidence and safety: Evidence Hit@k, Tax-Year Accuracy, Citation Support F1, Unsupported Claim Rate, Abstention Accuracy, Wrong-Year Answer Rate.
- [ ] Results show ablations: remove tax-year constraint, remove hierarchy expansion, remove table parsing, remove authority weighting, remove citation verifier.
- [ ] Paper claim is generalizable beyond one bot: constrained evidence selection for temporal legal-administrative QA.

## Phase 0: Stop Product Drift

Purpose: remove anything that does not help the paper.

- [ ] Freeze new chatbot/product features.
- [ ] Keep only research-useful code paths:
  - [ ] ingestion and parsing
  - [ ] structure-aware chunking
  - [ ] retrieval baselines
  - [ ] evidence graph / graph expansion
  - [ ] citation validation
  - [ ] evaluation runner
- [ ] Move ecommerce/inventory-specific docs and experiments out of the main paper path or mark them as unrelated legacy work.
- [ ] Create one canonical research README:
  - [ ] problem
  - [ ] benchmark
  - [ ] method
  - [ ] baselines
  - [ ] metrics
  - [ ] reproduction commands

Deliverable:

- [ ] `docs/research_plan.md` with the final thesis and contribution boundaries.

## Phase 1: Define BTaxBench Precisely

Purpose: make the benchmark defensible.

### Dataset Scope

- [ ] Decide source corpus:
  - [ ] Income Tax Act
  - [ ] annual income-tax paripatra/circulars
  - [ ] SROs
  - [ ] official NBR forms/guidelines if useful
- [ ] Create corpus manifest:
  - [ ] document id
  - [ ] title
  - [ ] source URL
  - [ ] publication date
  - [ ] tax year / assessment year
  - [ ] authority level
  - [ ] language
  - [ ] PDF quality type: embedded text, scanned, mixed

Suggested file:

- [ ] `data/metadata/corpus_manifest.csv`

### QA Schema

Each QA row should include:

- [ ] `question_id`
- [ ] `question_bn`
- [ ] `question_en_optional`
- [ ] `question_type`
- [ ] `answer_bn`
- [ ] `answerability`: `answerable`, `unanswerable`, `ambiguous`, `conflicting`
- [ ] `gold_doc_ids`
- [ ] `gold_pages`
- [ ] `gold_sections`
- [ ] `gold_table_ids`
- [ ] `gold_row_ids`
- [ ] `gold_evidence_spans`
- [ ] `tax_year`
- [ ] `income_year`
- [ ] `assessment_year`
- [ ] `taxpayer_class`
- [ ] `authority_level`
- [ ] `legal_status`: `active`, `amended`, `repealed`, `unknown`
- [ ] `notes_for_annotator`

Suggested file:

- [ ] `data/btaxbench/btaxbench_v0.jsonl`

### Question Type Distribution

Target distribution:

- [ ] 20% rate/slab/table lookup
- [ ] 15% definition
- [ ] 15% procedure/compliance
- [ ] 10% deduction/exemption
- [ ] 10% taxpayer-class-specific
- [ ] 10% tax-year-specific
- [ ] 10% amendment/circular conflict
- [ ] 10% unanswerable/ambiguous

Blind spot:

- [ ] Do not let the dataset become mostly easy lookup questions. That will make reviewers say the benchmark is shallow.

### Annotation Quality

- [ ] Write annotation guidelines before labeling.
- [ ] Use at least two annotators for a subset.
- [ ] Report inter-annotator agreement:
  - [ ] answerability agreement
  - [ ] evidence span overlap
  - [ ] section/page agreement
- [ ] Create adjudication workflow for conflicts.

Suggested files:

- [ ] `docs/annotation_guidelines.md`
- [ ] `data/btaxbench/annotator_a.jsonl`
- [ ] `data/btaxbench/annotator_b.jsonl`
- [ ] `data/btaxbench/adjudicated.jsonl`

## Phase 2: Make Ingestion Evidence-Grade

Purpose: every chunk must carry legal provenance.

Relevant current modules:

- `app/ingest/parser.py`
- `app/ingest/chunker.py`
- `app/ingestion/structure_builder.py`
- `app/ingestion/metadata_tagger.py`
- `app/ingestion/parent_child_linker.py`

### Required Chunk Fields

- [ ] `chunk_id`
- [ ] `doc_id`
- [ ] `source_url`
- [ ] `page_start`
- [ ] `page_end`
- [ ] `section_id`
- [ ] `subsection_id`
- [ ] `clause_id`
- [ ] `table_id`
- [ ] `row_id`
- [ ] `tax_year`
- [ ] `income_year`
- [ ] `assessment_year`
- [ ] `taxpayer_class`
- [ ] `authority_level`
- [ ] `legal_status`
- [ ] `text`
- [ ] `extraction_method`: `embedded`, `ocr`, `layout`, `manual`
- [ ] `extraction_confidence`
- [ ] `structure_confidence`
- [ ] `metadata_confidence`
- [ ] `parent_ids`
- [ ] `sibling_ids`
- [ ] `cites_ids`

### Parser Tasks

- [ ] Detect Bangla and English numerals.
- [ ] Normalize tax years such as `২০২৫-২০২৬`, `2025-26`, `২০২৫-২৬`.
- [ ] Extract page numbers from PDF position, not only printed text.
- [ ] Detect section/subsection/clause headings.
- [ ] Detect table boundaries and preserve rows.
- [ ] Mark extraction uncertainty when structure is unclear.
- [ ] Store raw extracted text alongside normalized text.

### Validation Tasks

- [ ] Add a chunk schema validator.
- [ ] Add tests for Bangla numeral normalization.
- [ ] Add tests for table-row preservation.
- [ ] Add tests for section hierarchy linking.
- [ ] Add tests for wrong/missing tax-year metadata.

Suggested files:

- [ ] `app/domain/legal_types.py`
- [ ] `app/ingestion/metadata_tagger.py`
- [ ] `app/ingestion/structure_builder.py`
- [ ] `tests/test_btaxbench_schema.py`
- [ ] `tests/test_tax_year_normalization.py`
- [ ] `tests/test_table_structure.py`

## Phase 3: Formalize The Algorithm

Purpose: make the method more than graph search with rules.

### Problem Formulation

Define each evidence node:

```text
e = (text, source, section, page, table, tax_year_range, taxpayer_scope, authority, status, confidence)
```

Define query:

```text
q = (natural_language_question, tax_year, taxpayer_class, task_type)
```

Retrieval objective:

```text
S* = argmax F(S | q)

subject to:
  |S| <= k
  temporal_validity(S, q)
  taxpayer_scope_consistency(S, q)
  authority_consistency(S)
  extraction_confidence(S) >= tau
```

Scoring function:

```text
F(S | q) =
  relevance(q, S)
+ lambda_1 * legal_factor_coverage(q, S)
+ lambda_2 * hierarchy_coherence(S)
+ lambda_3 * source_authority(S)
+ lambda_4 * table_row_alignment(q, S)
- lambda_5 * temporal_mismatch(q, S)
- lambda_6 * taxpayer_scope_mismatch(q, S)
- lambda_7 * conflict_score(S)
- lambda_8 * extraction_uncertainty(S)
```

### TaxTrail-RAG Algorithm

- [ ] Stage 1: query analysis
  - [ ] detect question type
  - [ ] detect tax year
  - [ ] detect taxpayer class
  - [ ] detect whether table lookup/calculation is needed
- [ ] Stage 2: candidate retrieval
  - [ ] BM25 candidates
  - [ ] dense candidates
  - [ ] hybrid merged candidates
  - [ ] optional reranker candidates
- [ ] Stage 3: legal constraint scoring
  - [ ] temporal validity
  - [ ] taxpayer scope
  - [ ] authority level
  - [ ] legal status
  - [ ] extraction confidence
- [ ] Stage 4: graph expansion
  - [ ] parent section
  - [ ] child clauses
  - [ ] sibling clauses
  - [ ] table rows
  - [ ] amendment/circular references
- [ ] Stage 5: evidence set optimization
  - [ ] greedy submodular selection or A* path search
  - [ ] compare both if feasible
- [ ] Stage 6: evidence sufficiency gate
  - [ ] answer
  - [ ] clarify
  - [ ] abstain

### Theory Angle

- [ ] Show that legal evidence selection is a constrained set-selection problem.
- [ ] If using greedy selection, define conditions under which `F` is monotone submodular and use `(1 - 1/e)` approximation as the theoretical justification.
- [ ] If using A* search, define:
  - [ ] state
  - [ ] transition
  - [ ] path cost
  - [ ] admissible heuristic
  - [ ] termination condition
- [ ] Be honest: only claim optimality if the heuristic is actually admissible.

Blind spot:

- [ ] Do not fake theorem weight. One clean formulation plus one honest proposition is stronger than decorative math.

Suggested files:

- [ ] `app/retrieval/taxtrail.py`
- [ ] `app/retrieval/legal_constraints.py`
- [ ] `app/retrieval/evidence_optimizer.py`
- [ ] `tests/test_taxtrail_retrieval.py`
- [ ] `docs/method_taxtrail.md`

## Phase 4: Build Citation Faithfulness Evaluation

Purpose: evaluate legal support at claim level.

Relevant current modules:

- `app/generation/citations.py`
- `app/domain/citations.py`
- `app/services/citation_service.py`
- `app/eval/metrics.py`

### Atomic Claim Extraction

- [ ] Split generated answers into atomic legal claims.
- [ ] Each claim should contain one legal proposition only.
- [ ] Tag claim type:
  - [ ] rate/slab
  - [ ] eligibility
  - [ ] definition
  - [ ] procedure
  - [ ] deadline
  - [ ] exception
  - [ ] calculation

### Claim-Evidence Matching

Define:

```text
support(a_i, e_j) in [0, 1]
```

Decision:

```text
claim_supported(a_i) = 1 if max_j support(a_i, e_j) >= tau
```

Metrics:

- [ ] Citation Support Precision
- [ ] Citation Support Recall
- [ ] Citation Support F1
- [ ] Unsupported Claim Rate
- [ ] Uncited Claim Rate
- [ ] Wrong Citation Rate

### Human Audit

- [ ] Manually audit at least 100 generated answers.
- [ ] Compare automatic citation scoring with human labels.
- [ ] Report disagreement categories.

Suggested files:

- [ ] `app/eval/citation_faithfulness.py`
- [ ] `data/btaxbench/citation_audit.jsonl`
- [ ] `scripts/run_citation_audit.py`
- [ ] `tests/test_citation_faithfulness.py`

## Phase 5: Baselines

Purpose: make reviewers believe the improvement is real.

Implement or configure:

- [ ] BM25 only
- [ ] dense only
- [ ] hybrid BM25 + dense
- [ ] hybrid + reranker
- [ ] flat chunk RAG
- [ ] parent-child chunk RAG
- [ ] graph expansion RAG
- [ ] long-context LLM with full/large document context
- [ ] TaxTrail-RAG without generation, retrieval only
- [ ] full TaxTrail-RAG with generation and citation gate

Baseline fairness rules:

- [ ] Same corpus.
- [ ] Same train/dev/test split.
- [ ] Same top-k budget where possible.
- [ ] Same generation model where possible.
- [ ] Same answer prompt where possible.
- [ ] Record latency and token cost.

Suggested files:

- [ ] `app/eval/baselines.py`
- [ ] `configs/baselines/*.yaml`
- [ ] `scripts/run_btaxbench_eval.py`

## Phase 6: Metrics And Leaderboard Table

Purpose: produce paper-ready results.

### Retrieval Metrics

- [ ] Evidence Hit@1
- [ ] Evidence Hit@3
- [ ] Evidence Hit@5
- [ ] MRR
- [ ] Section Accuracy
- [ ] Page Accuracy
- [ ] Table Row Accuracy

### Legal Applicability Metrics

- [ ] Tax-Year Accuracy
- [ ] Wrong-Year Answer Rate
- [ ] Taxpayer-Class Accuracy
- [ ] Authority-Level Accuracy
- [ ] Conflict Detection Accuracy

### Generation Metrics

- [ ] Answer Exactness or expert correctness
- [ ] Citation Support Precision
- [ ] Citation Support Recall
- [ ] Citation Support F1
- [ ] Unsupported Claim Rate
- [ ] Abstention Accuracy

### Robustness Metrics

- [ ] Clean-to-OCR Performance Drop
- [ ] Embedded-text vs OCR vs layout-aware parsing comparison
- [ ] Table degradation impact
- [ ] Missing-page stress test
- [ ] Wrong-tax-year distractor stress test

Main result table should include:

- [ ] BM25
- [ ] dense
- [ ] hybrid
- [ ] hybrid + reranker
- [ ] graph expansion
- [ ] long-context LLM
- [ ] TaxTrail-RAG

## Phase 7: Ablation Studies

Purpose: prove which part matters.

Run TaxTrail-RAG variants:

- [ ] full method
- [ ] no tax-year constraint
- [ ] no taxpayer-class constraint
- [ ] no legal hierarchy expansion
- [ ] no table-aware retrieval
- [ ] no authority weighting
- [ ] no extraction-confidence penalty
- [ ] no citation sufficiency gate
- [ ] no abstention

Expected strongest ablation:

- [ ] Removing tax-year constraint should increase wrong-year answers.
- [ ] Removing citation gate should increase unsupported claims.
- [ ] Removing table-aware retrieval should hurt slab/rate questions.
- [ ] Removing extraction-confidence penalty should hurt OCR cases.

## Phase 8: Error Analysis

Purpose: show reviewer-level honesty.

Analyze at least 50 failures by category:

- [ ] OCR corruption
- [ ] broken table extraction
- [ ] missing tax-year metadata
- [ ] wrong taxpayer-class inference
- [ ] ambiguous user question
- [ ] conflicting authority
- [ ] relevant evidence retrieved but answer generation failed
- [ ] correct answer but weak citation
- [ ] correct citation but incomplete answer
- [ ] benchmark annotation issue

Output:

- [ ] error taxonomy table
- [ ] 5-8 qualitative examples
- [ ] concrete future-work boundaries

Suggested file:

- [ ] `results/error_analysis.md`

## Phase 9: Paper Positioning

Purpose: avoid a weak venue mismatch.

### SIGIR Angle

Use if retrieval results are the strongest:

> Temporal-hierarchical constrained evidence retrieval improves legal-tax evidence search under noisy PDF extraction.

Needed:

- [ ] strong retrieval metrics
- [ ] strong ablations
- [ ] clear algorithm
- [ ] limited dependence on generation

### ACL / EMNLP Angle

Use if benchmark and faithfulness are strongest:

> BTaxBench evaluates evidence-faithful Bangla legal-tax QA with citation support and answerability.

Needed:

- [ ] strong dataset description
- [ ] annotation quality
- [ ] faithfulness evaluation
- [ ] multilingual/low-resource framing

### AAAI / IJCAI Angle

Use if search/reasoning formulation is strongest:

> Legal-tax QA as constrained evidence-path optimization with temporal validity, authority, and abstention.

Needed:

- [ ] formal problem statement
- [ ] search algorithm
- [ ] robustness and reasoning cases
- [ ] comparison to unconstrained graph retrieval

## Phase 10: Release Package

Purpose: make the work reusable.

- [ ] Dataset card.
- [ ] Corpus source manifest.
- [ ] Annotation guidelines.
- [ ] Evaluation script.
- [ ] Baseline configs.
- [ ] Reproduction commands.
- [ ] Model/prompt details.
- [ ] Known limitations.
- [ ] License and source-document usage notes.

Suggested files:

- [ ] `DATASET_CARD.md`
- [ ] `MODEL_CARD.md`
- [ ] `REPRODUCE.md`
- [ ] `configs/eval/btaxbench_taxtrail.yaml`

## 12-Week Execution Plan

### Weeks 1-2: Benchmark Foundation

- [ ] Finalize corpus manifest.
- [ ] Finalize benchmark schema.
- [ ] Write annotation guidelines.
- [ ] Create 50-question pilot.
- [ ] Validate evidence-span annotation workflow.

### Weeks 3-4: Evidence-Grade Parsing

- [ ] Add missing chunk metadata.
- [ ] Improve tax-year normalization.
- [ ] Preserve table rows.
- [ ] Add parser confidence fields.
- [ ] Build structure validation tests.

### Weeks 5-6: Baselines

- [ ] Implement baseline runner.
- [ ] Run BM25, dense, hybrid, reranker.
- [ ] Run flat RAG and parent-child RAG.
- [ ] Save results with reproducible configs.

### Weeks 7-8: TaxTrail-RAG

- [ ] Implement legal constraints.
- [ ] Implement graph expansion.
- [ ] Implement evidence optimizer.
- [ ] Add sufficiency gate.
- [ ] Run retrieval-only evaluation.

### Weeks 9-10: Faithfulness And Robustness

- [ ] Implement claim-evidence matching.
- [ ] Run citation support evaluation.
- [ ] Run OCR/layout robustness experiments.
- [ ] Run ablations.

### Weeks 11-12: Paper Package

- [ ] Write method section.
- [ ] Write dataset section.
- [ ] Write experiment section.
- [ ] Produce final tables.
- [ ] Produce error analysis.
- [ ] Decide target venue.

## Non-Negotiables

- [ ] Do not claim "first" unless verified with a systematic related-work search.
- [ ] Do not report only answer accuracy.
- [ ] Do not use only LLM-as-judge for legal faithfulness.
- [ ] Do not let generated text hide weak evidence.
- [ ] Do not tune on the test set.
- [ ] Do not treat tax year as optional metadata.
- [ ] Do not collapse table rows into arbitrary chunks without row identifiers.
- [ ] Do not frame this as a chatbot paper.

## Kill Criteria

If these fail, downgrade venue ambition:

- [ ] Dataset cannot reach at least 150 high-quality QA pairs.
- [ ] Gold evidence spans cannot be annotated reliably.
- [ ] TaxTrail-RAG does not beat hybrid + reranker on evidence metrics.
- [ ] Citation gate does not reduce unsupported claim rate.
- [ ] OCR/layout study shows no measurable difference.
- [ ] Method depends on brittle hand rules that do not generalize beyond one PDF.

## First Three Concrete Tasks

Do these before writing more code:

- [ ] Create `data/metadata/corpus_manifest.csv` for all official PDFs.
- [ ] Create 50 gold QA examples in `data/btaxbench/btaxbench_pilot.jsonl`.
- [ ] Run BM25, dense, and hybrid retrieval on the pilot and record Evidence Hit@3, Tax-Year Accuracy, and Wrong-Year Answer Rate.

