# Execution Guide for `bangla-tax-rag`

This document is the practical execution manual for running, testing, benchmarking, and extending `bangla-tax-rag`.

It is designed to answer:

- what to run first
- how to run the full pipeline
- what to benchmark
- what to test
- what experiments to conduct
- what `codex` commands can be used to extend the system

## 1. Quick Start

From the project root:

```bash
cd "/home/sonjoy/Bar tax/bangla-tax-rag"
```

Create the environment and install dependencies:

```bash
make install
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Run tests:

```bash
make test
```

Run the API:

```bash
make run-api
```

Run the UI:

```bash
make run-ui
```

## 2. Full System Flow

The normal flow is:

1. install dependencies
2. ingest PDF
3. inspect chunk JSONL
4. build sparse index
5. optionally build dense index
6. run retrieval queries
7. inspect evidence and generation
8. build dataset candidates
9. validate benchmark dataset
10. run evaluation
11. iterate on chunking, retrieval, and generation

## 3. Primary Execution Flows

### Flow A: English PDF Workflow

Use this first when debugging or running clean experiments.

#### Ingest the English Act

```bash
.venv/bin/python scripts/ingest_pdf.py \
  --input "/home/sonjoy/Bar tax/Income_tax_act_2023.pdf" \
  --doc-id income-tax-act-2023 \
  --doc-title "Income Tax Act 2023" \
  --doc-type statute \
  --authority-level national \
  --chunking-mode section_aware \
  --output data/processed/income-tax-act-2023.jsonl
```

#### Build sparse index

```bash
.venv/bin/python scripts/build_sparse_index.py \
  --input data/processed/income-tax-act-2023.jsonl \
  --output indexes/sparse-english
```

#### Build dense placeholder index

```bash
.venv/bin/python scripts/build_dense_index.py \
  --input data/processed/income-tax-act-2023.jsonl \
  --output indexes/dense-english
```

#### Query from CLI

```bash
.venv/bin/python scripts/demo_query.py \
  --mode hybrid \
  --index-dir indexes/sparse-english \
  --query "What are the income tax authorities under section 4?" \
  --top-k 5
```

### Flow B: Bangla OCR Workflow

Use this for OCR-aware Bangla experiments.

#### OCR the PDF first

```bash
ocrmypdf -l ben+eng --force-ocr --deskew --optimize 0 --output-type pdf \
  "/home/sonjoy/Bar tax/Income-tax_Paripatra_2025-2026-1.pdf" \
  "data/processed/income-tax-paripatra-2025-2026.ocr.pdf"
```

#### Ingest the OCRed PDF

```bash
.venv/bin/python scripts/ingest_pdf.py \
  --input data/processed/income-tax-paripatra-2025-2026.ocr.pdf \
  --doc-id income-tax-paripatra-2025-2026 \
  --doc-title "Income Tax Paripatra 2025-2026" \
  --doc-type circular \
  --authority-level national \
  --chunking-mode section_aware \
  --output data/processed/income-tax-paripatra-2025-2026.jsonl
```

#### Build sparse index

```bash
.venv/bin/python scripts/build_sparse_index.py \
  --input data/processed/income-tax-paripatra-2025-2026.jsonl \
  --output indexes/sparse-bangla
```

#### Query from CLI

```bash
.venv/bin/python scripts/demo_query.py \
  --mode hybrid \
  --index-dir indexes/sparse-bangla \
  --query "ধারা ৩.১ এ কী বলা হয়েছে?" \
  --top-k 5
```

## 4. API and UI Flow

### Start API

```bash
.venv/bin/uvicorn app.main:app --reload
```

### Start Streamlit

```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```

### Typical UI sequence

1. Check API health
2. Ingest PDF
3. Build index
4. Open chunk browser
5. Run query
6. Inspect:
   - analyzed query
   - rewritten query
   - answer or abstention
   - citations
   - final hits
   - intermediate sparse/dense/fused hits

## 5. Benchmarking Flow

This repository currently supports benchmark preparation and lightweight evaluation. The strongest practical benchmarking flow is:

1. create chunk JSONL from source documents
2. generate annotation candidates
3. manually annotate gold answers and supporting evidence
4. validate the benchmark
5. run evaluation
6. compare settings across chunking, retrieval, and generation

### Generate annotation candidates

```bash
.venv/bin/python scripts/build_annotation_candidates.py \
  --chunks data/processed/sample_chunks.jsonl \
  --output results/annotation_candidates.jsonl
```

### Validate a benchmark dataset

```bash
.venv/bin/python scripts/validate_dataset.py \
  --dataset data/templates/annotation_template.jsonl \
  --chunks data/processed/sample_chunks.jsonl
```

### Merge annotation files

```bash
.venv/bin/python scripts/merge_annotations.py \
  --inputs data/templates/annotation_template.jsonl \
  --output results/merged_dataset.jsonl
```

### Run evaluation

```bash
.venv/bin/python scripts/run_eval.py \
  --dataset data/processed/sample_eval.jsonl \
  --output-dir results/eval_sample
```

## 6. What To Benchmark

### A. Ingestion and OCR Benchmarking

Record:

- OCR on vs OCR off
- number of pages parsed
- number of chunks created
- percentage of corrupted chunks
- heading recovery quality
- section marker quality

### B. Chunking Benchmarking

Compare:

- `section_aware`
- `naive`
- `example_aware`
- `table_aware`

Record:

- number of chunks
- average chunk length
- number of tiny fragments
- number of header-only chunks
- section/subsection correctness
- example/table preservation quality

### C. Retrieval Benchmarking

Compare:

- `sparse`
- `dense`
- `hybrid`
- hybrid with authority/time-aware reranking

Record:

- Recall@k
- MRR
- nDCG
- correct section retrieval
- correct evidence chunk retrieval

### D. Generation Benchmarking

Compare:

- retrieval only
- grounded generation enabled
- deterministic grounded fallback
- local LLM generation through Ollama

Record:

- citation coverage
- support verification success
- unsupported claim rate
- abstention rate
- abstention correctness

### E. OCR-Uncertainty Benchmarking

If you implement OCR-uncertainty-aware retrieval later, compare:

- direct extraction
- OCR-first extraction
- OCR-first + uncertainty-aware chunking
- OCR-first + uncertainty-aware retrieval

## 7. What To Test

### Full test suite

```bash
.venv/bin/pytest -q
```

### Important targeted tests

Parser and chunker:

```bash
.venv/bin/pytest tests/test_parser.py tests/test_chunker.py -q
```

Sparse and hybrid retrieval:

```bash
.venv/bin/pytest tests/test_sparse_retrieval.py tests/test_hybrid_retrieval.py -q
```

Generation and citations:

```bash
.venv/bin/pytest tests/test_generation.py tests/test_citations.py -q
```

API:

```bash
.venv/bin/pytest tests/test_api_endpoints.py tests/test_health.py -q
```

Dataset tooling:

```bash
.venv/bin/pytest tests/test_dataset_builder.py tests/test_dataset_validation.py -q
```

UI smoke:

```bash
.venv/bin/pytest tests/test_streamlit_smoke.py -q
```

Repo smoke:

```bash
.venv/bin/pytest tests/test_repo_smoke.py -q
```

## 8. Experiment Tracks

### Track 1: English Statute Baseline

Goal:

- validate the full pipeline on cleaner English legal text

Run:

1. ingest English PDF
2. build sparse index
3. test section queries
4. test definition queries
5. test mention/existence queries

### Track 2: Bangla OCR Baseline

Goal:

- measure whether OCR-first ingestion improves chunking and retrieval

Run:

1. ingest Bangla PDF without OCR
2. ingest Bangla PDF with OCR
3. compare chunk quality
4. compare retrieval quality

### Track 3: Chunking Ablation

Goal:

- identify which chunking mode produces the best downstream retrieval

Run:

1. ingest the same document with different chunking settings
2. build indexes for each
3. run the same question set
4. compare evidence quality

### Track 4: Retrieval Ablation

Goal:

- compare sparse, dense, and hybrid retrieval

Run:

1. build sparse and dense indexes
2. run the same benchmark questions
3. compare final evidence hits
4. compare generation outcomes

### Track 5: Generation and Abstention

Goal:

- measure when the system should answer vs abstain

Run:

1. test strong-support questions
2. test weak-support questions
3. test conflict cases
4. test citation correctness

## 9. Recommended Evaluation Matrix

For serious experiments, track runs in a table with:

- corpus
- language
- OCR on or off
- chunking mode
- retrieval mode
- top_k
- final_evidence_k
- generation on or off
- generator backend
- verification on or off
- abstention threshold

## 10. Manual Inspection Checklist

Before trusting any experiment result, inspect:

1. the chunk JSONL
2. heading paths
3. section ids
4. final evidence hits
5. citation snippets
6. abstention reason

If chunking is bad, retrieval and generation metrics are misleading.

## 11. Save Results

### Save evaluation output

The evaluation script writes to:

- `results/eval_sample/evaluation_summary.json`

### Save query results as PDF

```bash
.venv/bin/python scripts/save_query_pdf.py \
  --index-dir indexes/sparse \
  --query "২০২৫-২০২৬ করবর্ষে কোম্পানির করহার কী?" \
  --top-k 3 \
  --output results/demo_query_response.pdf
```

## 12. Shell Command Reference

### Install

```bash
make install
```

### Test

```bash
make test
```

### Run API

```bash
make run-api
```

### Run UI

```bash
make run-ui
```

## 13. Codex Command Templates

These are reusable `codex --full-auto` prompts you can use to continue the project.

### A. Improve chunking

```bash
codex --full-auto "
Improve chunking quality for bangla-tax-rag.

Goal:
Reduce noisy chunks, improve subsection boundary detection, and keep legal examples and tables intact.

Implement in:
- app/ingest/parser.py
- app/ingest/chunker.py
- tests/test_parser.py
- tests/test_chunker.py

After implementation:
- run pytest
- fix failures
- summarize chunk quality changes
"
```

### B. Add OCR-uncertainty-aware scoring

```bash
codex --full-auto "
Implement OCR-uncertainty-aware chunk scoring and retrieval for bangla-tax-rag.

Goal:
Estimate chunk reliability from OCR or text-quality signals and use it in sparse and hybrid post-ranking.

Implement in:
- app/core/schemas.py
- app/core/utils.py
- app/ingest/parser.py
- app/ingest/chunker.py
- app/retrieval/sparse.py
- app/retrieval/hybrid.py
- tests/test_sparse_retrieval.py
- tests/test_hybrid_retrieval.py

After implementation:
- run pytest
- print example chunk confidence fields and ranking effects
"
```

### C. Build a gold benchmark

```bash
codex --full-auto "
Implement a research-grade benchmark workflow for bangla-tax-rag.

Goal:
Create a gold legal/tax QA benchmark with evidence labels, abstention labels, validation, and split support.

Implement in:
- app/eval/dataset_builder.py
- app/eval/annotation.py
- app/core/schemas.py
- scripts/build_annotation_candidates.py
- scripts/merge_annotations.py
- scripts/validate_dataset.py
- docs/dataset.md
- tests/test_dataset_builder.py
- tests/test_dataset_validation.py

After implementation:
- run pytest
- print benchmark creation commands
"
```

### D. Replace dense placeholder retrieval

```bash
codex --full-auto "
Replace the placeholder dense retriever in bangla-tax-rag with a real multilingual embedding retriever.

Goal:
Support dense retrieval for Bangla-English legal/tax chunks with persistent embeddings and hybrid fusion.

Implement in:
- app/retrieval/dense.py
- app/retrieval/hybrid.py
- scripts/build_dense_index.py
- tests/test_hybrid_retrieval.py
- tests/test_sparse_retrieval.py

After implementation:
- run pytest
- print dense indexing and dense query commands
"
```

### E. Improve research docs

```bash
codex --full-auto "
Upgrade the research documentation for bangla-tax-rag.

Goal:
Make the repo paper-friendly with a stronger methodology, experiments section, related work, and benchmark instructions.

Implement in:
- README.md
- docs/methodology.md
- docs/experiments.md
- docs/dataset.md
- docs/related_work.md
- READMEA*.md

After implementation:
- summarize the new research narrative and document structure
"
```

## 14. Recommended Practical Order

If you want the most sensible order of work:

1. run tests
2. use the English PDF workflow first
3. validate chunk quality manually
4. run sparse and hybrid retrieval
5. enable generation
6. test the Bangla OCR workflow
7. build annotation candidates
8. create a gold benchmark
9. run evaluation and ablations
10. only then add new methods

## 15. Bottom Line

Use this file as your execution checklist.

If the goal is:

- debugging: run tests and inspect chunks first
- benchmarking: build annotation candidates and evaluate retrieval
- publication: freeze chunking, build a gold benchmark, add a real method, and run ablations

That is the shortest reliable path from a working system to a research contribution.
