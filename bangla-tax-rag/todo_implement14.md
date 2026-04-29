# TODO Implement14: 14-Document Pilot Execution Plan

## Goal

Use the first 14 official Bangladesh tax documents to build a serious research pilot:

> BTaxBench-Pilot: evidence-faithful Bangla legal-tax QA over 14 official government documents, with structured metadata, gold evidence spans, retrieval baselines, and early TaxTrail-RAG experiments.

This is not the final A* dataset yet. It is the proof base for deciding whether the benchmark and method are strong enough to scale.

## Success Criteria

The 14-document pilot is successful only if it produces:

- [ ] 14 official source documents in a clean raw folder.
- [ ] A complete corpus manifest with source URL, year, authority type, and PDF quality.
- [ ] Parsed/chunked JSONL with section/page/table metadata.
- [ ] A pilot benchmark with 150-250 QA pairs.
- [ ] Gold evidence spans for every answerable question.
- [ ] At least 30 unanswerable, ambiguous, or conflict questions.
- [ ] BM25, dense, hybrid, and graph-expansion baseline results.
- [ ] Early TaxTrail-RAG results and ablations.
- [ ] Error analysis showing where parsing, retrieval, and citation support fail.

## Folder Target

Create this structure:

```text
data/
  raw/
    btax14/
      pdfs/
      source_notes/
  metadata/
    corpus_manifest_btax14.csv
  processed/
    btax14/
      chunks.jsonl
      tables.jsonl
      pages.jsonl
      legal_graph.jsonl
      extraction_report.json
  btaxbench/
    pilot14/
      questions.jsonl
      gold_evidence.jsonl
      train.jsonl
      dev.jsonl
      test.jsonl
      README.md
  annotations/
    pilot14/
      annotation_guidelines.md
      annotator_a.jsonl
      annotator_b_sample.jsonl
      adjudicated.jsonl
  results/
    pilot14/
      retrieval_baselines.json
      generation_baselines.json
      citation_faithfulness.json
      error_analysis.md
```

## Phase 1: Corpus Intake

Purpose: make the 14 PDFs auditable.

- [ ] Place all 14 PDFs under `data/raw/btax14/pdfs/`.
- [ ] Rename files with stable ids:
  - [ ] `btax14_001_income_tax_act_2023.pdf`
  - [ ] `btax14_002_paripatra_2025_2026.pdf`
  - [ ] continue through `btax14_014_*.pdf`
- [ ] For each PDF, save source notes:
  - [ ] official download URL
  - [ ] access date
  - [ ] document title
  - [ ] issuing authority
  - [ ] publication date if known
  - [ ] tax year / assessment year if known
- [ ] Create `data/metadata/corpus_manifest_btax14.csv`.

Manifest columns:

```csv
doc_id,file_name,title,title_bn,source_url,issuing_authority,authority_type,publication_date,tax_year,income_year,assessment_year,language,pdf_quality,page_count,has_tables,has_scanned_pages,notes
```

Authority types:

- [ ] `act`
- [ ] `paripatra`
- [ ] `sro`
- [ ] `rule`
- [ ] `form`
- [ ] `guideline`
- [ ] `other`

PDF quality labels:

- [ ] `embedded_text`
- [ ] `scanned`
- [ ] `mixed`
- [ ] `unknown`

Pass condition:

- [ ] all 14 rows have `doc_id`, `file_name`, `title`, `source_url`, `authority_type`, `tax_year` or `assessment_year`, and `pdf_quality`.

## Phase 2: Ingestion And Extraction

Purpose: convert PDFs into evidence-grade text, not loose chunks.

Relevant current scripts/modules:

- `scripts/ingest_pdf.py`
- `app/ingest/parser.py`
- `app/ingest/chunker.py`
- `app/ingestion/structure_builder.py`
- `app/ingestion/metadata_tagger.py`
- `app/ingestion/parent_child_linker.py`

Tasks:

- [ ] Run ingestion for each PDF.
- [ ] Store one normalized combined chunk file:
  - [ ] `data/processed/btax14/chunks.jsonl`
- [ ] Store page-level text:
  - [ ] `data/processed/btax14/pages.jsonl`
- [ ] Store table candidates:
  - [ ] `data/processed/btax14/tables.jsonl`
- [ ] Store graph nodes and links:
  - [ ] `data/processed/btax14/legal_graph.jsonl`
- [ ] Store extraction report:
  - [ ] `data/processed/btax14/extraction_report.json`

Required chunk fields:

- [ ] `chunk_id`
- [ ] `doc_id`
- [ ] `page_start`
- [ ] `page_end`
- [ ] `section_id`
- [ ] `subsection_id`
- [ ] `clause_id`
- [ ] `table_id`
- [ ] `row_id`
- [ ] `tax_year`
- [ ] `assessment_year`
- [ ] `taxpayer_class`
- [ ] `authority_type`
- [ ] `text`
- [ ] `text_normalized`
- [ ] `extraction_method`
- [ ] `extraction_confidence`
- [ ] `structure_confidence`
- [ ] `metadata_confidence`
- [ ] `parent_ids`
- [ ] `sibling_ids`
- [ ] `source_file`

Pass condition:

- [ ] every chunk has `doc_id`, page metadata, source file, and non-empty text.
- [ ] at least 80% of chunks have usable page numbers.
- [ ] section/table metadata is present where the source visibly contains it.

## Phase 3: BTaxBench-Pilot14 Schema

Purpose: define the benchmark before annotation drifts.

Create:

- [ ] `data/btaxbench/pilot14/questions.jsonl`
- [ ] `data/btaxbench/pilot14/gold_evidence.jsonl`
- [ ] `data/btaxbench/pilot14/README.md`

Question row schema:

```json
{
  "question_id": "btax14_q0001",
  "question_bn": "",
  "question_en": "",
  "question_type": "rate_lookup",
  "answerability": "answerable",
  "gold_answer_bn": "",
  "tax_year": "2025-2026",
  "income_year": "",
  "assessment_year": "",
  "taxpayer_class": "individual",
  "expected_authority_type": "paripatra",
  "gold_evidence_ids": ["btax14_ev0001"],
  "difficulty": "easy",
  "notes": ""
}
```

Evidence row schema:

```json
{
  "evidence_id": "btax14_ev0001",
  "question_id": "btax14_q0001",
  "doc_id": "btax14_002",
  "page": 12,
  "section_id": "",
  "table_id": "",
  "row_id": "",
  "span_text": "",
  "span_start": null,
  "span_end": null,
  "support_type": "direct",
  "notes": ""
}
```

Answerability labels:

- [ ] `answerable`
- [ ] `unanswerable`
- [ ] `ambiguous`
- [ ] `conflicting`

Question types:

- [ ] `rate_lookup`
- [ ] `definition`
- [ ] `procedure`
- [ ] `deadline`
- [ ] `deduction`
- [ ] `exemption`
- [ ] `taxpayer_class`
- [ ] `tax_year_specific`
- [ ] `table_lookup`
- [ ] `calculation`
- [ ] `authority_conflict`
- [ ] `unanswerable`

## Phase 4: Annotation Plan

Purpose: produce 150-250 high-quality QA pairs from the 14 documents.

Target distribution:

- [ ] 40-50 rate/table/slab lookup questions.
- [ ] 25-35 definition questions.
- [ ] 25-35 procedure/deadline questions.
- [ ] 20-30 deduction/exemption questions.
- [ ] 20-30 taxpayer-class-specific questions.
- [ ] 20-30 tax-year-specific questions.
- [ ] 10-20 amendment/conflict questions.
- [ ] 30-50 unanswerable/ambiguous questions.

Annotation rules:

- [ ] Every answerable question must have at least one gold evidence span.
- [ ] Complex legal answers should have 2-3 evidence spans.
- [ ] Table answers must cite table id or row id when possible.
- [ ] Tax-year-specific questions must include the expected tax year.
- [ ] If a question lacks enough evidence, mark it `unanswerable`; do not invent an answer.
- [ ] If two official sources conflict, mark it `conflicting` and cite both sources.

Quality control:

- [ ] Second annotator reviews at least 50 questions.
- [ ] Track disagreement on answerability.
- [ ] Track disagreement on evidence page/section.
- [ ] Adjudicate disagreements into `adjudicated.jsonl`.

Pass condition:

- [ ] 150+ validated QA pairs.
- [ ] 30+ unanswerable/ambiguous/conflict cases.
- [ ] 50-question double-annotated sample.

## Phase 5: Baseline Retrieval Experiments

Purpose: establish whether the pilot has measurable retrieval difficulty.

Run these baselines:

- [ ] BM25 only.
- [ ] Dense only.
- [ ] Hybrid BM25 + dense.
- [ ] Hybrid + reranker.
- [ ] Parent-child expansion.
- [ ] Existing graph expansion.

Metrics:

- [ ] Evidence Hit@1.
- [ ] Evidence Hit@3.
- [ ] Evidence Hit@5.
- [ ] MRR.
- [ ] Section Accuracy.
- [ ] Page Accuracy.
- [ ] Table Row Accuracy.
- [ ] Tax-Year Accuracy.
- [ ] Wrong-Year Retrieval Rate.

Suggested output:

- [ ] `results/pilot14/retrieval_baselines.json`
- [ ] `results/pilot14/retrieval_baselines.md`

Pass condition:

- [ ] Baselines produce different measurable scores.
- [ ] At least one failure category is visible: wrong year, wrong table, wrong taxpayer class, weak evidence, missing evidence.

## Phase 6: TaxTrail-RAG Pilot

Purpose: test whether constrained evidence retrieval beats normal retrieval.

Implement or configure:

- [ ] Query analyzer:
  - [ ] question type
  - [ ] tax year
  - [ ] taxpayer class
  - [ ] table/calculation need
- [ ] Legal constraints:
  - [ ] temporal validity
  - [ ] taxpayer scope
  - [ ] authority type
  - [ ] legal hierarchy
  - [ ] extraction confidence
- [ ] Evidence expansion:
  - [ ] parent section
  - [ ] sibling clause
  - [ ] child clause
  - [ ] table row
  - [ ] linked circular/SRO reference
- [ ] Evidence sufficiency gate:
  - [ ] answer
  - [ ] clarify
  - [ ] abstain

Ablations:

- [ ] TaxTrail full.
- [ ] no tax-year constraint.
- [ ] no taxpayer-class constraint.
- [ ] no hierarchy expansion.
- [ ] no table-aware retrieval.
- [ ] no authority weighting.
- [ ] no extraction-confidence penalty.
- [ ] no abstention.

Pass condition:

- [ ] TaxTrail improves Evidence Hit@3 or Tax-Year Accuracy over hybrid + reranker.
- [ ] Removing tax-year constraint increases wrong-year retrieval.
- [ ] Removing table-aware retrieval hurts table/slab questions.

## Phase 7: Generation And Citation Faithfulness

Purpose: ensure answers are supported by citations.

Tasks:

- [ ] Generate answers using the same retrieved evidence budget for each method.
- [ ] Extract atomic legal claims from generated answers.
- [ ] Match each claim to cited evidence.
- [ ] Mark claims:
  - [ ] supported
  - [ ] partially supported
  - [ ] unsupported
  - [ ] contradicted
- [ ] Run manual audit on at least 50 generated answers.

Metrics:

- [ ] Citation Support Precision.
- [ ] Citation Support Recall.
- [ ] Citation Support F1.
- [ ] Unsupported Claim Rate.
- [ ] Wrong Citation Rate.
- [ ] Abstention Accuracy.

Pass condition:

- [ ] Citation gate reduces unsupported claim rate.
- [ ] Abstention catches at least some unanswerable/ambiguous cases.

## Phase 8: OCR/Layout Robustness

Purpose: turn messy government PDFs into a measured research variable.

Compare:

- [ ] embedded text extraction.
- [ ] OCR extraction.
- [ ] layout-aware parsing.
- [ ] structure-aware chunking.

Stress tests:

- [ ] noisy OCR text.
- [ ] missing page.
- [ ] broken table rows.
- [ ] wrong tax-year distractor.
- [ ] document with mixed Bangla/English numerals.

Metrics:

- [ ] Clean-to-OCR Evidence Hit@3 drop.
- [ ] Clean-to-OCR Citation Support F1 drop.
- [ ] Table Row Accuracy drop.
- [ ] Wrong-Year Retrieval Rate under distractors.

Pass condition:

- [ ] Structure-aware parsing degrades less than flat text under at least one realistic noise condition.

## Phase 9: Error Analysis

Purpose: know whether the project is worth scaling.

Analyze at least 50 errors:

- [ ] OCR corruption.
- [ ] table extraction failure.
- [ ] missing section metadata.
- [ ] wrong tax-year detection.
- [ ] wrong taxpayer-class detection.
- [ ] retrieval found right doc but wrong passage.
- [ ] evidence retrieved but generation failed.
- [ ] answer correct but citation unsupported.
- [ ] benchmark label unclear.

Create:

- [ ] `results/pilot14/error_analysis.md`

Pass condition:

- [ ] The error analysis identifies 3-5 concrete fixes before scaling beyond 14 documents.

## Phase 10: Scale/Stop Decision

Purpose: avoid wasting months on a weak path.

Scale to 20-50 documents only if:

- [ ] 150+ pilot QA pairs are validated.
- [ ] TaxTrail beats strong retrieval baselines on at least two key metrics.
- [ ] Citation gate reduces unsupported claims.
- [ ] OCR/layout robustness result is non-trivial.
- [ ] Error analysis shows fixable issues, not fundamental dataset weakness.

Stop or reframe if:

- [ ] 14 documents are too homogeneous.
- [ ] Most questions are easy lookup.
- [ ] Evidence spans cannot be annotated consistently.
- [ ] Hybrid + reranker already solves most cases.
- [ ] TaxTrail only works through brittle hand rules.

## First 7-Day Sprint

### Day 1

- [ ] Put all 14 PDFs in `data/raw/btax14/pdfs/`.
- [ ] Create `corpus_manifest_btax14.csv`.
- [ ] Fill at least required metadata for all 14 documents.

### Day 2

- [ ] Run ingestion on all 14 documents.
- [ ] Produce initial `chunks.jsonl`.
- [ ] Count chunks per document.
- [ ] Identify documents with extraction failure.

### Day 3

- [ ] Inspect 20 random chunks per document.
- [ ] Mark parser issues: pages, sections, tables, tax years.
- [ ] Fix only high-impact parser issues.

### Day 4

- [ ] Create first 50 QA pairs.
- [ ] Add gold evidence spans.
- [ ] Include at least 10 unanswerable/ambiguous questions.

### Day 5

- [ ] Run BM25, dense, and hybrid retrieval on the 50 QA pilot.
- [ ] Record Evidence Hit@3 and Tax-Year Accuracy.

### Day 6

- [ ] Add 50 more QA pairs.
- [ ] Run baseline retrieval again.
- [ ] Start error analysis.

### Day 7

- [ ] Decide top parser/retrieval fixes.
- [ ] Update roadmap with evidence, not intuition.
- [ ] Freeze `BTaxBench-Pilot14 v0.1`.

## Immediate Next Commands

Create folders:

```bash
mkdir -p data/raw/btax14/pdfs \
  data/raw/btax14/source_notes \
  data/metadata \
  data/processed/btax14 \
  data/btaxbench/pilot14 \
  data/annotations/pilot14 \
  results/pilot14
```

Check current visible PDFs:

```bash
find data -iname '*.pdf' -print
```

Count current JSONL records:

```bash
wc -l data/processed/*.jsonl data/agentic_store/*/chunks/*.jsonl 2>/dev/null
```

## Strategic Warning

Do not optimize TaxTrail before the 50-question pilot exists. Without gold evidence, you will tune retrieval by vibes. That is not research; that is self-deception with extra code.

