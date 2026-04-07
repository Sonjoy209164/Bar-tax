# bangla-tax-rag

Local research scaffold for Bangla tax and legal retrieval-augmented generation.

## Project Overview

`bangla-tax-rag` is a practical local stack for:

- parsing Bangla tax PDFs
- chunking them into structured JSONL records
- building sparse and dense retrieval artifacts
- running sparse, dense, and hybrid retrieval
- generating grounded answers with sentence-level citations
- exposing the workflow through FastAPI and Streamlit

The project is designed for local experiments first. It works without external APIs by default and uses a safe mocked generation backend unless you later connect an OpenAI-compatible model server.

## What is implemented

- PDF parsing with `pdfplumber` and `PyMuPDF`
- metadata extraction for tax year, section ids, appendix ids, and SRO ids
- section-aware, example-aware, table-aware, and fixed chunking
- sparse BM25 retrieval
- dense overlap-based local retrieval baseline
- hybrid retrieval with reciprocal rank fusion
- grounded generation with sentence-level citations
- abstention and answer verification logic
- FastAPI endpoints for ingest, index build, query, config, health, and evaluation
- Streamlit frontend for local research use
- sample chunk and evaluation artifacts for smoke runs

## Architecture Summary

The pipeline is:

1. Ingest PDF to structured pages
2. Normalize and chunk pages into JSONL
3. Build retrieval artifacts
4. Run sparse, dense, or hybrid retrieval
5. Build a compact evidence pack
6. Generate grounded answers with citations or abstain
7. Inspect results via API or Streamlit

See:

- [docs/architecture.md](/home/sonjoy/Bar%20tax/bangla-tax-rag/docs/architecture.md)
- [docs/methodology.md](/home/sonjoy/Bar%20tax/bangla-tax-rag/docs/methodology.md)
- [docs/experiments.md](/home/sonjoy/Bar%20tax/bangla-tax-rag/docs/experiments.md)

## Setup Steps

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

## API Run Command

```bash
.venv/bin/uvicorn app.main:app --reload
```

## UI Run Command

```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```

Expected backend URL for the UI:

```text
http://127.0.0.1:8000
```

## Ingest Command

```bash
.venv/bin/python scripts/ingest_pdf.py \
  --input "/home/sonjoy/Bar tax/Income-tax_Paripatra_2025-2026-1.pdf" \
  --doc-id income-tax-paripatra-2025-2026 \
  --doc-title "Income Tax Paripatra 2025-2026" \
  --doc-type circular \
  --authority-level national \
  --chunking-mode section_aware \
  --output data/processed/income-tax-paripatra-2025-2026.jsonl
```

## Sparse Index Build Command

```bash
.venv/bin/python scripts/build_sparse_index.py \
  --input data/processed/income-tax-paripatra-2025-2026.jsonl \
  --output indexes/sparse
```

## Dense Index Build Command

```bash
.venv/bin/python scripts/build_dense_index.py \
  --input data/processed/income-tax-paripatra-2025-2026.jsonl \
  --output indexes/dense
```

## Query Example

```bash
.venv/bin/python scripts/demo_query.py \
  --mode hybrid \
  --index-dir indexes/sparse \
  --query "২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?" \
  --top-k 3
```

## Evaluation Example

```bash
.venv/bin/python scripts/run_eval.py \
  --dataset data/processed/sample_eval.jsonl \
  --output-dir results/eval
```

## Dataset Tooling

Generate annotation candidates:

```bash
.venv/bin/python scripts/build_annotation_candidates.py \
  --chunks data/processed/sample_chunks.jsonl \
  --output results/annotation_candidates.jsonl
```

Validate a dataset:

```bash
.venv/bin/python scripts/validate_dataset.py \
  --dataset data/templates/annotation_template.jsonl \
  --chunks data/processed/sample_chunks.jsonl
```

Run ablation experiments later with:

```bash
.venv/bin/python scripts/run_eval.py \
  --dataset data/processed/sample_eval.jsonl \
  --output-dir results/ablation
```

## API Examples

Health:

```bash
curl http://127.0.0.1:8000/health
```

Ingest:

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "input_pdf_path": "/home/sonjoy/Bar tax/Income-tax_Paripatra_2025-2026-1.pdf",
    "doc_id": "income-tax-paripatra-2025-2026",
    "doc_title": "Income Tax Paripatra 2025-2026",
    "doc_type": "circular",
    "authority_level": "national",
    "chunking_mode": "section_aware"
  }'
```

Build indexes:

```bash
curl -X POST http://127.0.0.1:8000/build-index \
  -H "Content-Type: application/json" \
  -d '{
    "chunk_jsonl_path": "data/processed/income-tax-paripatra-2025-2026.jsonl",
    "build_sparse": true,
    "build_dense": true
  }'
```

Query:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question_text": "২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?",
    "retrieval_mode": "hybrid",
    "top_k": 5,
    "final_evidence_k": 3,
    "include_intermediate_hits": false,
    "generate_answer": true
  }'
```

Evaluate:

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_path": "data/processed/sample_eval.jsonl",
    "retrieval_modes": ["sparse", "hybrid"],
    "generate_answers": true
  }'
```

## Sample Assets

- [data/processed/sample_chunks.jsonl](/home/sonjoy/Bar%20tax/bangla-tax-rag/data/processed/sample_chunks.jsonl)
- [data/processed/sample_eval.jsonl](/home/sonjoy/Bar%20tax/bangla-tax-rag/data/processed/sample_eval.jsonl)

These are small synthetic files intended for local smoke tests and reproducible demo runs.

## Troubleshooting

- `ModuleNotFoundError: No module named 'app'`
  Run commands from the repo root. The Streamlit app now bootstraps the project root automatically.
- `Sparse index not found`
  Build the sparse index first with `scripts/build_sparse_index.py` or `/build-index`.
- `Dense index metadata not found`
  Build the dense index first with `scripts/build_dense_index.py` or `/build-index`.
- API unreachable from Streamlit
  Start FastAPI locally and confirm the sidebar backend URL is `http://127.0.0.1:8000`.
- Weak or abstained answers
  This is expected when evidence is thin, conflicting, or below the configured confidence threshold.

## Research Notes

- Sparse retrieval is the strongest exact-match local baseline.
- Dense retrieval is currently a local overlap-based placeholder, not embeddings.
- Hybrid retrieval is fully wired and is the recommended default for experiments.
- Generation is grounded and testable, but the default provider is mocked unless you connect an external model server later.
