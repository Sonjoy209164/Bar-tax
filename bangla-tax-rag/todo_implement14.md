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

## Command Workflow Checklist

Run these commands from the repo root:

```bash
cd "/home/sonjoy/Bar tax/bangla-tax-rag"
```

This section is intentionally operational. Tick each checkbox only after the command runs and the output looks sane.

### 0. Environment Check

- [ ] Confirm you are in the project root.

```bash
pwd
```

Expected:

```text
/home/sonjoy/Bar tax/bangla-tax-rag
```

- [ ] Create or activate the Python environment.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

- [ ] Run a smoke test before touching the 14-document workflow.

```bash
.venv/bin/python -m pytest tests/test_repo_smoke.py tests/test_parser.py tests/test_chunker.py -q
```

Pass condition:

- [ ] smoke tests pass, or failures are recorded in `results/pilot14/setup_notes.md`.

### 1. Create Pilot14 Folders

```bash
mkdir -p data/raw/btax14/pdfs \
  data/raw/btax14/source_notes \
  data/metadata \
  data/processed/btax14 \
  data/btaxbench/pilot14 \
  data/annotations/pilot14 \
  indexes/pilot14/sparse \
  indexes/pilot14/dense \
  results/pilot14
```

- [x] Confirm folders exist.

```bash
find data/raw/btax14 data/metadata data/processed/btax14 data/btaxbench/pilot14 data/annotations/pilot14 results/pilot14 -maxdepth 2 -type d | sort
```

### 2. Put The 14 PDFs In One Place

- [x] Check where your PDFs currently are.

```bash
find .. dataset data -iname '*.pdf' -print 2>/dev/null | sort
```

- [x] Copy or move the 14 official PDFs into `data/raw/btax14/pdfs/`.

Use this if the PDFs are currently under `../dataset/`:

```bash
find ../dataset -maxdepth 2 -type f -iname '*.pdf' -exec cp -n {} data/raw/btax14/pdfs/ \;
```

Use this if the PDFs are currently under repo-local `dataset/`:

```bash
find dataset -maxdepth 2 -type f -iname '*.pdf' -exec cp -n {} data/raw/btax14/pdfs/ \;
```

- [x] Confirm exactly 14 PDFs are visible.

```bash
find data/raw/btax14/pdfs -maxdepth 1 -type f -iname '*.pdf' | sort | tee results/pilot14/pdf_list.txt
wc -l results/pilot14/pdf_list.txt
```

Pass condition:

- [x] output count is `14`.

### 3. Rename PDFs To Stable IDs

Do not skip this. Stable ids prevent broken citations later.

- [x] Preview current filenames.

```bash
nl -w2 -s'. ' results/pilot14/pdf_list.txt
```

- [x] Rename manually into this pattern.

```text
data/raw/btax14/pdfs/btax14_001_<short_name>.pdf
data/raw/btax14/pdfs/btax14_002_<short_name>.pdf
...
data/raw/btax14/pdfs/btax14_014_<short_name>.pdf
```

Example:

```bash
mv "data/raw/btax14/pdfs/Income_tax_act_2023.pdf" \
  "data/raw/btax14/pdfs/btax14_001_income_tax_act_2023.pdf"
```

- [x] Confirm final stable filenames.

```bash
find data/raw/btax14/pdfs -maxdepth 1 -type f -iname 'btax14_*.pdf' | sort | tee results/pilot14/pdf_list_stable.txt
wc -l results/pilot14/pdf_list_stable.txt
```

Pass condition:

- [x] output count is `14`.

### 4. Create Draft Corpus Manifest

- [x] Generate a draft manifest from the 14 filenames.

```bash
.venv/bin/python - <<'PY'
import csv
from pathlib import Path

pdf_dir = Path("data/raw/btax14/pdfs")
out = Path("data/metadata/corpus_manifest_btax14.csv")
out.parent.mkdir(parents=True, exist_ok=True)

fields = [
    "doc_id",
    "file_name",
    "title",
    "title_bn",
    "source_url",
    "issuing_authority",
    "authority_type",
    "publication_date",
    "tax_year",
    "income_year",
    "assessment_year",
    "language",
    "pdf_quality",
    "page_count",
    "has_tables",
    "has_scanned_pages",
    "notes",
]

rows = []
for pdf in sorted(pdf_dir.glob("btax14_*.pdf")):
    doc_id = "_".join(pdf.stem.split("_")[:2])
    guessed_title = pdf.stem.replace(doc_id + "_", "").replace("_", " ").strip().title()
    rows.append({
        "doc_id": doc_id,
        "file_name": pdf.name,
        "title": guessed_title,
        "title_bn": "",
        "source_url": "",
        "issuing_authority": "National Board of Revenue",
        "authority_type": "",
        "publication_date": "",
        "tax_year": "",
        "income_year": "",
        "assessment_year": "",
        "language": "bn/en",
        "pdf_quality": "unknown",
        "page_count": "",
        "has_tables": "",
        "has_scanned_pages": "",
        "notes": "",
    })

with out.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} rows to {out}")
PY
```

- [x] Confirm the manifest has 14 data rows.

```bash
.venv/bin/python - <<'PY'
import csv
from pathlib import Path
path = Path("data/metadata/corpus_manifest_btax14.csv")
rows = list(csv.DictReader(path.open(encoding="utf-8")))
print("rows:", len(rows))
for row in rows:
    print(row["doc_id"], row["file_name"], row["authority_type"] or "MISSING_AUTHORITY", row["tax_year"] or row["assessment_year"] or "MISSING_YEAR")
PY
```

- [x] Manually fill missing manifest fields.

Required fields before ingestion:

- [ ] `title`
- [x] `source_url`
- [x] `authority_type`
- [x] `tax_year` or `assessment_year`
- [x] `pdf_quality`

Recommended values:

```text
authority_type: act | paripatra | sro | rule | form | guideline | other
pdf_quality: embedded_text | scanned | mixed | unknown
```

Pass condition:

- [x] no row has missing `source_url`, `authority_type`, and both `tax_year`/`assessment_year`.

### 5. Count PDF Pages And Update Manifest Notes

- [x] Generate page counts into a side report.

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

import fitz

rows = []
for pdf in sorted(Path("data/raw/btax14/pdfs").glob("btax14_*.pdf")):
    try:
        doc = fitz.open(pdf)
        rows.append({"file_name": pdf.name, "page_count": doc.page_count})
        doc.close()
    except Exception as exc:
        rows.append({"file_name": pdf.name, "page_count": None, "error": str(exc)})

out = Path("results/pilot14/pdf_page_counts.json")
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
for row in rows:
    print(row)
PY
```

- [x] Copy page counts into `data/metadata/corpus_manifest_btax14.csv`.

### 6. Ingest All 14 PDFs

Default path: parse existing PDF text first. Use OCR only for documents that clearly fail extraction.

- [x] Run batch ingestion from the manifest.

```bash
.venv/bin/python - <<'PY'
import csv
import subprocess
from pathlib import Path

manifest = Path("data/metadata/corpus_manifest_btax14.csv")
pdf_dir = Path("data/raw/btax14/pdfs")
out_dir = Path("data/processed/btax14/per_doc")
out_dir.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
for row in rows:
    doc_id = row["doc_id"].strip()
    file_name = row["file_name"].strip()
    title = row["title"].strip() or doc_id
    authority_type = row["authority_type"].strip() or "other"
    pdf = pdf_dir / file_name
    output = out_dir / f"{doc_id}.jsonl"
    cmd = [
        ".venv/bin/python",
        "scripts/ingest_pdf.py",
        "--input",
        str(pdf),
        "--doc-id",
        doc_id,
        "--doc-title",
        title,
        "--doc-type",
        authority_type,
        "--authority-level",
        "national",
        "--chunking-mode",
        "section_aware",
        "--output",
        str(output),
    ]
    print("RUN", " ".join(cmd))
    subprocess.run(cmd, check=True)
PY
```

- [x] Confirm every document produced chunks.

```bash
for f in data/processed/btax14/per_doc/*.jsonl; do
  printf "%s " "$f"
  wc -l < "$f"
done | tee results/pilot14/per_doc_chunk_counts.txt
```

Pass condition:

- [x] all 14 files exist.
- [x] no official document has `0` chunks.

### 7. OCR Failed Or Weak Documents

Only run this for PDFs where chunks are empty, badly garbled, or missing Bangla text.

- [x] Create OCR output folder.

```bash
mkdir -p data/processed/btax14/ocr_pdfs
```

- [x] Generate saved OCR ingestion commands for all 14 PDFs.

```bash
.venv/bin/python scripts/run_pilot14_ocr_ingest.py
```

This writes:

```text
results/pilot14/pilot14_ocr_ingest_commands.sh
results/pilot14/pilot14_ocr_ingest_commands.jsonl
results/pilot14/pilot14_ocr_ingest_summary.json
```

- [x] Run OCR ingestion for all 14 PDFs.

```bash
.venv/bin/python scripts/run_pilot14_ocr_ingest.py --execute --overwrite
```

This writes OCR parsing results to:

```text
data/processed/btax14/ocr_pdfs/
data/processed/btax14/ocr_per_doc/
results/pilot14/ocr_ingest_stdout/
results/pilot14/ocr_ingest_stderr/
```

- [ ] Optional: OCR one weak document manually if the batch runner fails. Replace ids and filenames.

```bash
.venv/bin/python scripts/ingest_pdf.py \
  --input data/raw/btax14/pdfs/btax14_002_example.pdf \
  --doc-id btax14_002 \
  --doc-title "Replace With Real Title" \
  --doc-type paripatra \
  --authority-level national \
  --chunking-mode section_aware \
  --ocr-enabled \
  --ocr-language ben+eng \
  --ocr-output-pdf data/processed/btax14/ocr_pdfs/btax14_002_example.ocr.pdf \
  --output data/processed/btax14/per_doc/btax14_002.jsonl
```

- [x] Record every OCR rerun in `results/pilot14/ocr_rerun_notes.md`.

### 8. Structure And Publish Clean OCR Corpus

Do not use a raw `cat` merge as the final corpus. The final Pilot14 artifacts must come from the structure script because it preserves provenance, separates tables/forms, extracts row ids, merges weak short fragments, and tags OCR/section confidence.

- [x] Run the structuring script over OCR per-document chunks.

```bash
.venv/bin/python scripts/structure_pilot14_corpus.py
```

This writes and publishes:

```text
data/processed/btax14/chunks.jsonl
data/processed/btax14/chunks_enriched.jsonl
data/processed/btax14/chunks_rejected.jsonl
data/processed/btax14/pages.jsonl
data/processed/btax14/tables.jsonl
data/processed/btax14/table_rows.jsonl
data/processed/btax14/forms.jsonl
data/processed/btax14/legal_graph.jsonl
data/processed/btax14/extraction_report.json
```

- [x] Count structured artifacts.

```bash
wc -l data/processed/btax14/chunks.jsonl \
  data/processed/btax14/chunks_enriched.jsonl \
  data/processed/btax14/chunks_rejected.jsonl \
  data/processed/btax14/pages.jsonl \
  data/processed/btax14/tables.jsonl \
  data/processed/btax14/table_rows.jsonl \
  data/processed/btax14/forms.jsonl \
  data/processed/btax14/legal_graph.jsonl
```

- [x] Confirm structured chunks load through the retrieval schema.

```bash
.venv/bin/python - <<'PY'
from app.retrieval.sparse import load_chunk_records_from_jsonl

chunks = load_chunk_records_from_jsonl("data/processed/btax14/chunks.jsonl")
print("loaded", len(chunks))
print("types", sorted({chunk.chunk_type for chunk in chunks}))
PY
```

Pass condition:

- [x] canonical chunk file exists.
- [x] enriched metadata file exists.
- [x] table rows and forms files exist.
- [x] every `btax14_###` document has non-zero chunks.

### 9. Inspect Chunk Quality

- [x] Sample 20 chunks for manual inspection.

```bash
.venv/bin/python - <<'PY'
import json
import random
from pathlib import Path

path = Path("data/processed/btax14/chunks.jsonl")
rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
sample = random.Random(7).sample(rows, min(20, len(rows)))
out = Path("results/pilot14/random_20_chunks.md")
with out.open("w", encoding="utf-8") as handle:
    for i, row in enumerate(sample, 1):
        text = row.get("original_text") or row.get("text") or row.get("normalized_text") or ""
        handle.write(f"## {i}. {row.get('chunk_id')} | {row.get('doc_id')} | page {row.get('page_no')}\n\n")
        handle.write(f"section: {row.get('section_id')} | tax_year: {row.get('tax_year')} | type: {row.get('chunk_type')}\n\n")
        handle.write(text[:1200].replace('\\n', ' ') + "\n\n")
print(f"Wrote {out}")
PY
```

- [x] Read `results/pilot14/random_20_chunks.md`.
- [x] Record parser issues in `results/pilot14/parser_issues.md`.

Pass condition:

- [x] chunks are readable enough to annotate evidence.
- [x] page/section/tax-year issues are documented.

### 10. Build Retrieval Indexes

- [x] Build sparse BM25 index.

```bash
.venv/bin/python scripts/build_sparse_index.py \
  --input data/processed/btax14/structured/chunks.jsonl \
  --output indexes/pilot14/sparse
```

- [x] Build dense placeholder index.

```bash
.venv/bin/python scripts/build_dense_index.py \
  --input data/processed/btax14/structured/chunks.jsonl \
  --output indexes/pilot14/dense \
  --provider mock \
  --no-faiss
```

- [x] Run one smoke query.

```bash
.venv/bin/python scripts/demo_query.py \
  --mode hybrid \
  --index-dir indexes/pilot14/sparse \
  --dense-index-dir indexes/pilot14/dense \
  --query "ব্যক্তি করদাতার করহার কত?" \
  --top-k 5 | tee results/pilot14/demo_query_hybrid.txt
```

Pass condition:

- [x] sparse index builds.
- [x] dense placeholder index builds.
- [x] hybrid query returns hits.

### 11. Generate Annotation Candidates

- [x] Generate candidate questions from chunks.

```bash
.venv/bin/python scripts/build_annotation_candidates.py \
  --chunks data/processed/btax14/structured/gold_ready_chunks.jsonl \
  --output data/annotations/pilot14/candidates.jsonl
```

- [x] Count candidates.

```bash
wc -l data/annotations/pilot14/candidates.jsonl
```

- [x] Create the first annotation working file.

```bash
cp data/annotations/pilot14/candidates.jsonl data/annotations/pilot14/annotator_a_working.jsonl
```

Manual step:

- [x] Edit `data/annotations/pilot14/annotator_a_working.jsonl` down to the first 50 high-quality questions.
- [x] Fill gold answers.
- [x] Fill expected chunk ids.
- [x] Include at least 10 unanswerable/ambiguous/conflict questions.

Reproducible shortlist command:

```bash
.venv/bin/python scripts/create_pilot14_shortlist.py
```

### 12. Create Pilot14 Dataset Files

Current validation code expects the existing `AnnotatedQuestion` schema. For now, use that schema for executable validation, then later add the richer `questions.jsonl` plus `gold_evidence.jsonl` format.

- [x] Save the first executable dataset as:

```text
data/btaxbench/pilot14/pilot14_50.jsonl
```

Required row shape:

```json
{"question_id":"btax14_q0001","question_text":"","question_type":"rate_lookup","answer_text":"","expected_chunk_ids":[],"expected_doc_ids":[],"expected_sections":[],"expected_tax_year":"2025-2026","preferred_authority_level":"national","should_abstain":false,"answer_language":"bangla","notes":""}
```

- [x] Validate the first 50-question dataset.

```bash
.venv/bin/python scripts/validate_dataset.py \
  --dataset data/btaxbench/pilot14/pilot14_50.jsonl \
  --chunks data/processed/btax14/structured/gold_ready_chunks.jsonl | tee results/pilot14/validate_pilot14_50.json
```

Pass condition:

- [x] validator exits successfully.
- [x] `invalid_rows` is `0`.

### 12b. Add Bangla-English-Banglish Query Robustness

Purpose: users may ask in Bangla script, English, or Banglish/code-mixed form such as `kor ortho bochor ki` or `korhar koto`.

- [x] Add query-time Banglish expansion.
- [x] Detect Banglish rate, definition, section, withholding, penalty, rebate, return-filing, exemption, company, individual, and calculation terms.
- [x] Support Romanized section references such as `dhara 52`.
- [x] Wire the expansion into both `preprocess_query` and query planning.
- [x] Add regression tests.

```bash
.venv/bin/python -m pytest tests/test_sparse_retrieval.py tests/test_query_transformer.py
```

- [x] Run Banglish retrieval smoke checks.

```bash
.venv/bin/python scripts/demo_query.py \
  --mode sparse \
  --index-dir indexes/pilot14/sparse \
  --query "2025-2026 bekti korhar koto" \
  --top-k 3 | tee results/pilot14/demo_query_banglish_person_rate.txt

.venv/bin/python scripts/demo_query.py \
  --mode sparse \
  --index-dir indexes/pilot14/sparse \
  --query "dhara 52 utse kor koto" \
  --top-k 3 | tee results/pilot14/demo_query_banglish_section_withholding.txt
```

Pass condition:

- [x] `kor ortho bochor ki` becomes a definition-style query.
- [x] `2025-2026 korhar koto` becomes a rate lookup.
- [x] `dhara 52 utse kor koto` extracts section `52` and retrieves withholding-tax evidence.

### 13. Run Placeholder Evaluation

This is not the real paper metric yet. It only proves the evaluation script can run.

- [x] Create a simple prediction/reference file from the annotated dataset.

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

src = Path("data/btaxbench/pilot14/pilot14_50.jsonl")
out = Path("results/pilot14/pilot14_50_placeholder_eval.jsonl")
with src.open(encoding="utf-8") as in_handle, out.open("w", encoding="utf-8") as out_handle:
    for line in in_handle:
        if not line.strip():
            continue
        row = json.loads(line)
        out_handle.write(json.dumps({
            "question": row.get("question_text", ""),
            "prediction": "",
            "reference": row.get("answer_text", ""),
            "retrieval_mode": "not_run_yet",
        }, ensure_ascii=False) + "\n")
print(out)
PY
```

- [x] Run placeholder eval.

```bash
.venv/bin/python scripts/run_eval.py \
  --dataset results/pilot14/pilot14_50_placeholder_eval.jsonl \
  --output-dir results/pilot14/eval_placeholder
```

Pass condition:

- [x] `results/pilot14/eval_placeholder/evaluation_summary.json` exists.

### 14. Run Manual Baseline Retrieval Checks

Until a full Pilot14 retrieval evaluator is implemented, run query-level checks and record the hit quality.

- [x] Choose 10 representative questions from `pilot14_50.jsonl`.
- [x] Run sparse retrieval for each.

```bash
.venv/bin/python scripts/demo_query.py \
  --mode sparse \
  --index-dir indexes/pilot14/sparse \
  --query "REPLACE_WITH_REAL_QUESTION" \
  --top-k 5
```

- [x] Run dense retrieval for each.

```bash
.venv/bin/python scripts/demo_query.py \
  --mode dense \
  --dense-index-dir indexes/pilot14/dense \
  --query "REPLACE_WITH_REAL_QUESTION" \
  --top-k 5
```

- [x] Run hybrid retrieval for each.

```bash
.venv/bin/python scripts/demo_query.py \
  --mode hybrid \
  --index-dir indexes/pilot14/sparse \
  --dense-index-dir indexes/pilot14/dense \
  --query "REPLACE_WITH_REAL_QUESTION" \
  --top-k 5
```

- [x] Record manual results in:

```text
results/pilot14/manual_retrieval_audit.md
```

Audit columns:

```text
question_id | mode | gold_chunk_in_top_1 | gold_chunk_in_top_3 | gold_chunk_in_top_5 | wrong_year | notes
```

### 15. Implement Missing Automation

These checkboxes are code tasks required to make the workflow truly paper-ready.

- [x] Add `scripts/run_retrieval_eval.py`.
- [x] It should read `pilot14_50.jsonl`.
- [x] It should run `sparse`, `dense`, and `hybrid`.
- [x] It should compute:
  - [x] Evidence Hit@1
  - [x] Evidence Hit@3
  - [x] Evidence Hit@5
  - [x] MRR
  - [x] Tax-Year Accuracy
  - [x] Wrong-Year Retrieval Rate
- [x] It should write:
  - [x] `results/pilot14/retrieval_eval_50.json`
  - [x] `results/pilot14/retrieval_eval_50.md`

Do not pretend the current placeholder eval is enough. It is not.

### 15b. Replace Dense Placeholder And Fix Retrieval Failures

- [x] Replace dense placeholder with real transformer embeddings.
- [x] Build FAISS-backed `indexes/pilot14/dense` using `BAAI/bge-m3`.
- [x] Add document/title tax-year fallback for chunks whose `tax_year` metadata is missing.
- [x] Add query tax-year selection for multi-year questions.
- [x] Penalize early outline/table-of-contents style chunks.
- [x] Improve Bangla amount/penalty query routing.
- [x] Rerun retrieval tests.
- [x] Rerun automated retrieval evaluation.

Current Pilot14 retrieval result after Step 15b:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year Rate@1 |
|---|---:|---:|---:|---:|---:|---:|
| sparse | 0.325 | 0.500 | 0.625 | 0.4329 | 0.8649 | 0.1351 |
| dense real BGE-M3 | 0.300 | 0.575 | 0.625 | 0.4279 | 0.8649 | 0.1351 |
| hybrid | 0.500 | 0.700 | 0.750 | 0.6029 | 0.8649 | 0.1351 |

### 15c. Audit Wrong-Year Retrieval And Add Temporal Constraint Fixes

- [x] Audit wrong-year rows from `results/pilot14/retrieval_eval_50.json`.
- [x] Separate explicit query-year failures from gold-only temporal assumptions.
- [x] Fix tax-year range parsing so `2025-2026 পরিপত্রে` does not become `2026-2027`.
- [x] Fix multi-year selection so `2019-2020 থেকে ... 2022-2023 সালে` targets `2022-2023`.
- [x] Add evaluator fields:
  - [x] `query_tax_year`
  - [x] `temporal_constraint_source`
  - [x] `explicit_tax_year_accuracy_top1`
  - [x] `explicit_wrong_year_retrieval_rate_top1`
  - [x] `gold_only_wrong_year_retrieval_rate_top1`
- [x] Rerun retrieval tests.
- [x] Rerun automated retrieval evaluation.

Current Pilot14 retrieval result after Step 15c:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Explicit Wrong-Year@1 | Gold-Only Wrong-Year@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| sparse | 0.350 | 0.525 | 0.675 | 0.4629 | 0.9189 | 0.0000 | 0.4286 |
| dense real BGE-M3 | 0.350 | 0.625 | 0.675 | 0.4779 | 0.9189 | 0.0000 | 0.4286 |
| hybrid | 0.550 | 0.750 | 0.800 | 0.6529 | 0.9189 | 0.0000 | 0.4286 |

Interpretation:

- Explicit temporal retrieval is now clean on the 50-question pilot: `0.0000` explicit wrong-year rate.
- Remaining wrong-year rows are gold-only temporal cases where the question omits a year but the annotation expects one. These are benchmark-design issues, not pure retrieval failures.
- Before scaling, rewrite gold-only temporal questions to include a tax year or mark them as intentionally underspecified temporal-abstention cases.

### 15d. Fix Gold-Only Temporal Questions Before Scaling

- [x] Identify answerable questions with `expected_tax_year` but no visible query tax year.
- [x] Rewrite the affected questions so the tax year is explicit:
  - [x] `btax14_q0011`
  - [x] `btax14_q0018`
  - [x] `btax14_q0019`
  - [x] `btax14_q0020`
  - [x] `btax14_q0021`
  - [x] `btax14_q0025`
  - [x] `btax14_q0026`
  - [x] `btax14_q0042`
- [x] Update all Pilot14 working dataset files:
  - [x] `data/btaxbench/pilot14/pilot14_50.jsonl`
  - [x] `data/annotations/pilot14/shortlist_50_with_answers.jsonl`
  - [x] `data/annotations/pilot14/annotator_a_working.jsonl`
  - [x] `scripts/create_pilot14_shortlist.py`
- [x] Save rewrite audit:
  - [x] `results/pilot14/gold_only_temporal_question_fixes.md`
- [x] Validate dataset after the fix:
  - [x] `results/pilot14/validate_pilot14_50_after_temporal_fixes.json`
- [x] Confirm `answerable_gold_only_count = 0`.
- [x] Rerun retrieval tests.
- [x] Rerun automated retrieval evaluation.

Current Pilot14 retrieval result after Step 15d:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year Rate@1 | Gold-Only Temporal Questions |
|---|---:|---:|---:|---:|---:|---:|---:|
| sparse | 0.325 | 0.550 | 0.700 | 0.4617 | 1.0000 | 0.0000 | 0 |
| dense real BGE-M3 | 0.350 | 0.600 | 0.700 | 0.4779 | 1.0000 | 0.0000 | 0 |
| hybrid | 0.600 | 0.775 | 0.800 | 0.6883 | 1.0000 | 0.0000 | 0 |

Interpretation:

- The benchmark no longer hides tax-year constraints in answerable questions.
- Temporal retrieval is now clean on the 50-question pilot: `0.0000` wrong-year rate for sparse, dense, and hybrid.
- Remaining strict Hit@5 misses are passage/table/locality failures, not year-selection failures.

### 16. Expand From 50 To 150

- [x] Add questions 51-100.
- [x] Use the fixed temporal-question policy:
  - [x] no answerable question may hide `expected_tax_year` only in metadata.
  - [x] year-specific answerable questions must expose the tax year in the visible query.
  - [x] deliberately underspecified temporal questions must be marked as abstention.
- [x] Create reproducible 100-row builder:
  - [x] `scripts/create_pilot14_100.py`
- [x] Write Pilot14-100 files:
  - [x] `data/btaxbench/pilot14/pilot14_100.jsonl`
  - [x] `data/annotations/pilot14/shortlist_100_with_answers.jsonl`
  - [x] `data/annotations/pilot14/annotator_a_working_100.jsonl`
  - [x] `results/pilot14/shortlist_100_report.md`
- [x] Validate `pilot14_100.jsonl`.

```bash
.venv/bin/python scripts/validate_dataset.py \
  --dataset data/btaxbench/pilot14/pilot14_100.jsonl \
  --chunks data/processed/btax14/structured/gold_ready_chunks.jsonl | tee results/pilot14/validate_pilot14_100.json
```

Current Pilot14-100 dataset result:

| rows | answerable | abstention | valid rows | invalid rows | answerable hidden-year rows |
|---:|---:|---:|---:|---:|---:|
| 100 | 80 | 20 | 100 | 0 | 0 |

Question type distribution:

| type | count |
|---|---:|
| `rate_lookup` | 42 |
| `procedure` | 28 |
| `definition` | 13 |
| `calculation` | 10 |
| `amendment` | 4 |
| `authority_conflict` | 3 |

### 16b. Run Retrieval Evaluation On Pilot14-100 And Audit Failures

- [x] Run sparse, dense, and hybrid retrieval on `pilot14_100.jsonl`.
- [x] Write automated retrieval reports:
  - [x] `results/pilot14/retrieval_eval_100.json`
  - [x] `results/pilot14/retrieval_eval_100.md`
- [x] Write failure audit:
  - [x] `results/pilot14/retrieval_failure_audit_100.json`
  - [x] `results/pilot14/retrieval_failure_audit_100.md`
- [x] Confirm answerable temporal behavior:
  - [x] `wrong_year_retrieval_rate_top1 = 0.0000`
  - [x] `gold_only_tax_year_questions = 0`

Current Pilot14-100 retrieval result:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year Rate@1 | Doc Hit@5 | Page Hit@5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sparse | 0.2625 | 0.5000 | 0.5875 | 0.3902 | 1.0000 | 0.0000 | 0.9375 | 0.6875 |
| dense real BGE-M3 | 0.3625 | 0.5750 | 0.6500 | 0.4738 | 1.0000 | 0.0000 | 0.9625 | 0.8125 |
| hybrid | 0.5625 | 0.7625 | 0.7875 | 0.6633 | 1.0000 | 0.0000 | 0.9750 | 0.8250 |

Hybrid strict Hit@5 miss breakdown:

| category | count |
|---|---:|
| `same_doc_wrong_section` | 9 |
| `same_page_wrong_chunk` | 3 |
| `adjacent_page_near_miss` | 3 |
| `wrong_doc_top5` | 2 |
| `wrong_year_top1` | 0 |

Interpretation:

- The 100-question expansion did not break temporal behavior.
- Hybrid is still strongest and remains close to the 50-question pilot result.
- The main bottleneck is evidence locality over tables, examples, repeated appendix text, and near-duplicate legal passages.
- Before adding questions 101-150, repair or explicitly tag the 17 hybrid strict Hit@5 misses.

### 16c. Repair High-Priority Pilot14-100 Retrieval Failures

- [x] Inspect the 17 hybrid strict Hit@5 misses from Step 16b.
- [x] Fix canonical paripatra tax-year inference so example years inside a document do not override the document tax year.
- [x] Add Bangla/Banglish query handling for:
  - [x] clarification/spষ্টীকরণ questions
  - [x] surcharge questions
  - [x] international transaction penalty questions
  - [x] Bangla eligibility yes/no questions
- [x] Penalize table-of-contents/navigation chunks in final hybrid ranking.
- [x] Downweight late appendix/statute duplicate material unless the query explicitly asks for appendix/SRO/schedule evidence.
- [x] Expand same-page neighboring chunks for table/example/procedure evidence packs.
- [x] Fill hybrid evidence packs to `final_top_k` with the best remaining supportive candidates.
- [x] Add regression tests for the temporal and Bangla-query fixes.
- [x] Rerun Pilot14-100 retrieval evaluation.
- [x] Regenerate failure audit:
  - [x] `results/pilot14/retrieval_eval_100.json`
  - [x] `results/pilot14/retrieval_eval_100.md`
  - [x] `results/pilot14/retrieval_failure_audit_100.json`
  - [x] `results/pilot14/retrieval_failure_audit_100.md`

Current Pilot14-100 retrieval result after Step 16c:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year Rate@1 | Doc Hit@5 | Page Hit@5 | Adjacent Page Hit@5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sparse | 0.3375 | 0.5875 | 0.7625 | 0.4900 | 1.0000 | 0.0000 | 0.9750 | 0.7875 | 0.8125 |
| dense real BGE-M3 | 0.3875 | 0.6125 | 0.7125 | 0.5065 | 1.0000 | 0.0000 | 0.9750 | 0.7875 | 0.9000 |
| hybrid | 0.6375 | 0.7875 | 0.8875 | 0.7265 | 1.0000 | 0.0000 | 0.9875 | 0.9000 | 0.9375 |

Hybrid strict Hit@5 miss breakdown after Step 16c:

| category | count |
|---|---:|
| `same_doc_wrong_section` | 4 |
| `same_page_wrong_chunk` | 1 |
| `adjacent_page_near_miss` | 3 |
| `wrong_doc_top5` | 1 |
| `wrong_year_top1` | 0 |

Interpretation:

- Hybrid crossed the 80% gate: strict Hit@5 improved from `0.7875` to `0.8875`.
- Hybrid strict hits improved from `63/80` to `71/80`.
- Wrong-year retrieval remains `0.0000`.
- Remaining misses are mostly evidence-locality and annotation-granularity cases, so it is now reasonable to continue scaling to 150 while keeping a failure-audit loop.

### 16d. Expand Pilot14-100 To Pilot14-150 And Audit Failures

- [x] Add questions 101-150.
- [x] Use the same fixed temporal-question policy from Step 16:
  - [x] answerable year-specific questions expose the tax year in the visible query.
  - [x] deliberately underspecified/future/out-of-scope questions are marked as abstention.
- [x] Create reproducible 150-row builder:
  - [x] `scripts/create_pilot14_150.py`
- [x] Write Pilot14-150 files:
  - [x] `data/btaxbench/pilot14/pilot14_150.jsonl`
  - [x] `data/annotations/pilot14/shortlist_150_with_answers.jsonl`
  - [x] `data/annotations/pilot14/annotator_a_working_150.jsonl`
  - [x] `results/pilot14/shortlist_150_report.md`
- [x] Validate `pilot14_150.jsonl`.

```bash
.venv/bin/python scripts/validate_dataset.py \
  --dataset data/btaxbench/pilot14/pilot14_150.jsonl \
  --chunks data/processed/btax14/structured/gold_ready_chunks.jsonl | tee results/pilot14/validate_pilot14_150.json
```

Pass condition:

- [x] `pilot14_150.jsonl` has at least 150 valid rows.
- [x] at least 30 rows have `should_abstain: true` or conflict/ambiguous notes.

Current Pilot14-150 dataset result:

| rows | answerable | abstention | valid rows | invalid rows | answerable hidden-year rows |
|---:|---:|---:|---:|---:|---:|
| 150 | 120 | 30 | 150 | 0 | 0 |

Question type distribution:

| type | count |
|---|---:|
| `rate_lookup` | 59 |
| `procedure` | 51 |
| `definition` | 20 |
| `calculation` | 12 |
| `amendment` | 5 |
| `authority_conflict` | 3 |

- [x] Run sparse, dense, and hybrid retrieval on `pilot14_150.jsonl`.
- [x] Repair the new high-priority temporal failure:
  - [x] explicit chunk tax-year headings such as `2026-2027 করবর্ষের` now override the document title year when filtering.
  - [x] example-year metadata without a tax-year marker still falls back to the paripatra document year.
- [x] Add regression test for future tax-year headings inside a current-year paripatra.
- [x] Add reusable failure-audit script:
  - [x] `scripts/audit_retrieval_failures.py`
- [x] Write automated retrieval reports:
  - [x] `results/pilot14/retrieval_eval_150.json`
  - [x] `results/pilot14/retrieval_eval_150.md`
- [x] Write failure audit:
  - [x] `results/pilot14/retrieval_failure_audit_150.json`
  - [x] `results/pilot14/retrieval_failure_audit_150.md`

Current Pilot14-150 retrieval result after Step 16d:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year Rate@1 | Doc Hit@5 | Page Hit@5 | Adjacent Page Hit@5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sparse | 0.3583 | 0.6083 | 0.7333 | 0.4988 | 1.0000 | 0.0000 | 0.9833 | 0.7583 | 0.7917 |
| dense real BGE-M3 | 0.4167 | 0.6000 | 0.7000 | 0.5192 | 1.0000 | 0.0000 | 0.9833 | 0.7917 | 0.9000 |
| hybrid | 0.6333 | 0.7667 | 0.8583 | 0.7119 | 1.0000 | 0.0000 | 0.9917 | 0.8667 | 0.9083 |

Hybrid strict Hit@5 miss breakdown after Step 16d:

| category | count |
|---|---:|
| `same_doc_wrong_section` | 10 |
| `adjacent_page_near_miss` | 5 |
| `same_page_wrong_chunk` | 1 |
| `wrong_doc_top5` | 1 |
| `no_results` | 0 |
| `wrong_year_top1` | 0 |

Interpretation:

- Pilot14 now meets the 150-row pilot threshold with 30 abstention/ambiguous cases.
- Hybrid remains strongest at `0.8583` strict Evidence Hit@5 and `1.0000` Tax-Year Accuracy@1.
- Scaling from 100 to 150 lowered hybrid Hit@5 from `0.8875` to `0.8583`; this is acceptable because the added questions are harder, but it exposes the next bottleneck: exact evidence locality within long paripatras.
- The new future-year failure was real and is fixed: 2026-2027/2027-2028 chunks inside the 2025-2026 paripatra are no longer filtered out by document-title year.
- Next retrieval work should focus on parent/neighbor evidence expansion and page/section locality, not broad tax-year filtering.

### 17. Freeze Pilot14 v0.1

- [x] Copy the final validated pilot.

```bash
cp data/btaxbench/pilot14/pilot14_150.jsonl data/btaxbench/pilot14/btaxbench_pilot14_v0_1.jsonl
```

- [x] Create checksum.

```bash
sha256sum data/btaxbench/pilot14/btaxbench_pilot14_v0_1.jsonl \
  data/processed/btax14/chunks.jsonl \
  data/metadata/corpus_manifest_btax14.csv | tee results/pilot14/pilot14_v0_1_checksums.txt
```

- [x] Write a short freeze note.

```text
results/pilot14/freeze_note_v0_1.md
```

Freeze note must include:

- [x] number of documents
- [x] number of chunks
- [x] number of QA pairs
- [x] number of answerable rows
- [x] number of abstention/conflict/ambiguous rows
- [x] known parser limitations
- [x] known evaluation limitations

Frozen Pilot14 v0.1 snapshot:

| item | count |
|---|---:|
| official documents | 14 |
| indexed chunks | 7,985 |
| QA pairs | 150 |
| answerable rows | 120 |
| abstention / ambiguous / out-of-scope rows | 30 |

Frozen files:

- `data/btaxbench/pilot14/btaxbench_pilot14_v0_1.jsonl`
- `results/pilot14/pilot14_v0_1_checksums.txt`
- `results/pilot14/freeze_note_v0_1.md`

Freeze rule:

- Do not mutate `btaxbench_pilot14_v0_1.jsonl`.
- Future dataset edits should become `v0.2`.

### 18. Build and Evaluate TaxTrail v0.1

- [x] Implement guarded TaxTrail structure-aware retrieval:
  - [x] hybrid sparse+dense seed retrieval
  - [x] tax-year filtering before expansion
  - [x] same page / adjacent page expansion
  - [x] same section and same heading expansion
  - [x] document-level legal-term fallback
  - [x] guarded top-four hybrid preservation
  - [x] high-confidence structure replacement threshold
- [x] Add `taxtrail` as an evaluation retrieval mode.
- [x] Add API/schema support for `taxtrail`.
- [x] Compare sparse, dense, hybrid, and TaxTrail on frozen Pilot14 v0.1.
- [x] Refresh TaxTrail failure audit.
- [x] Add citation faithfulness scaffold.
- [x] Write TaxTrail method note.

Commands run:

```bash
.venv/bin/python scripts/run_retrieval_eval.py \
  --dataset data/btaxbench/pilot14/btaxbench_pilot14_v0_1.jsonl \
  --index-dir indexes/pilot14/sparse \
  --dense-index-dir indexes/pilot14/dense \
  --output-json results/pilot14/retrieval_eval_150_taxtrail.json \
  --output-md results/pilot14/retrieval_eval_150_taxtrail.md \
  --top-k 5 \
  --modes taxtrail

.venv/bin/python scripts/compare_retrieval_reports.py \
  --reports results/pilot14/retrieval_eval_150.json results/pilot14/retrieval_eval_150_taxtrail.json \
  --output-json results/pilot14/retrieval_eval_150_taxtrail_comparison.json \
  --output-md results/pilot14/retrieval_eval_150_taxtrail_comparison.md

.venv/bin/python scripts/audit_retrieval_failures.py \
  --input-json results/pilot14/retrieval_eval_150_taxtrail.json \
  --output-json results/pilot14/retrieval_failure_audit_150_taxtrail.json \
  --output-md results/pilot14/retrieval_failure_audit_150_taxtrail.md \
  --priority-mode taxtrail

.venv/bin/python scripts/run_citation_faithfulness_eval.py \
  --dataset data/btaxbench/pilot14/btaxbench_pilot14_v0_1.jsonl \
  --chunks data/processed/btax14/chunks.jsonl \
  --output-json results/pilot14/citation_faithfulness_v0_1.json \
  --output-md results/pilot14/citation_faithfulness_v0_1.md
```

Current Pilot14 v0.1 retrieval comparison:

| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year@1 | Page Hit@5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| sparse | 0.3583 | 0.6083 | 0.7333 | 0.4988 | 1.0000 | 0.0000 | 0.7583 |
| dense real BGE-M3 | 0.4167 | 0.6000 | 0.7000 | 0.5192 | 1.0000 | 0.0000 | 0.7917 |
| hybrid | 0.6333 | 0.7667 | 0.8583 | 0.7119 | 1.0000 | 0.0000 | 0.8667 |
| TaxTrail guarded | 0.6083 | 0.7500 | 0.8917 | 0.7037 | 1.0000 | 0.0000 | 0.9000 |

Current citation faithfulness scaffold:

| metric | value |
|---|---:|
| citation support precision | 0.8959 |
| citation support recall | 0.8417 |
| citation support F1 | 0.8679 |
| unsupported claim rate | 0.1041 |
| abstention accuracy | 0.9667 |

Important interpretation:

- TaxTrail improves strict Evidence Hit@5 over hybrid by `+0.0334`.
- TaxTrail improves evidence page locality, from Page Hit@5 `0.8667` to `0.9000`.
- TaxTrail does not improve Hit@1 or MRR yet.
- The contribution is evidence coverage under legal structure constraints, not first-rank precision.
- Runtime is currently high and should be optimized with cached query embeddings or batched dense evaluation.

Novelty and theory note:

- Current architectural novelty:
  - `TaxTrail` is guarded structure-aware legal evidence path retrieval, not a plain Bangla tax chatbot.
  - It combines hybrid lexical-semantic retrieval with legal-tax constraints: tax year, document, page, section, heading, adjacent chunks, and citation-ready evidence.
  - The key design insight is the guard: naive structure expansion can hurt retrieval, while guarded expansion preserves high-confidence hybrid evidence and only admits structure-expanded candidates above a confidence threshold.
- Current theoretical framing:
  - Model the corpus as a legal evidence graph `G = (V, E)`.
  - Nodes `V`: tax years, documents, pages, sections, headings, chunks, tables, citation/evidence units.
  - Edges `E`: `contains`, `adjacent_to`, `same_section`, `same_heading`, `mentions_reference`, `tax_year_valid`.
  - Retrieval objective:

```text
argmax EvidenceScore(q, v)
subject to:
  TaxYear(v) = TaxYear(q)
  Authority(v) >= required authority
  SupportRisk(v) <= threshold
```

- Guarded TaxTrail rule:

```text
TaxTrail(q) = Top_m(Hybrid(q)) union {v in Expand_G(Hybrid(q)) : score(q, v) >= tau}

Current pilot setting:
  m = 4
  tau = 12.0
```

- Best paper claim:
  - We introduce `TaxTrail`, a guarded evidence-path retrieval architecture for legal-tax RAG over noisy Bangla government PDFs.
  - TaxTrail treats the parsed corpus as a constrained legal evidence graph and expands retrieval through tax-year, page, section, and heading structure.
  - Unlike naive graph expansion, TaxTrail preserves top hybrid evidence and admits expanded evidence only under a confidence guard.
  - On Pilot14 v0.1, TaxTrail improves strict Evidence Hit@5 from `0.8583` to `0.8917` while keeping Wrong-Year@1 at `0.0000`.
- What is not yet proven:
  - No final theorem yet.
  - The threshold `tau = 12.0` is pilot-tuned and must be validated on a dev split.
  - The current result shows an algorithmic/architectural contribution, not a full theoretical guarantee.
- Required next experiments to make the novelty stronger:
  - [ ] dev/test split to avoid label leakage.
  - [ ] ablation: hybrid vs unguarded TaxTrail vs guarded TaxTrail.
  - [ ] ablation: with/without tax-year constraint.
  - [ ] ablation: with/without page/section/heading expansion.
  - [ ] threshold curve over `tau`.
  - [ ] prove or state prefix-preservation property: top `m` baseline evidence is unchanged by TaxTrail.
  - [ ] report precision/coverage tradeoff: TaxTrail improves Hit@5 but currently lowers Hit@1/MRR.

Artifacts:

- `app/retrieval/taxtrail.py`
- `scripts/compare_retrieval_reports.py`
- `scripts/run_citation_faithfulness_eval.py`
- `results/pilot14/retrieval_eval_150_taxtrail.json`
- `results/pilot14/retrieval_eval_150_taxtrail.md`
- `results/pilot14/retrieval_eval_150_taxtrail_comparison.json`
- `results/pilot14/retrieval_eval_150_taxtrail_comparison.md`
- `results/pilot14/retrieval_failure_audit_150_taxtrail.json`
- `results/pilot14/retrieval_failure_audit_150_taxtrail.md`
- `results/pilot14/citation_faithfulness_v0_1.json`
- `results/pilot14/citation_faithfulness_v0_1.md`
- `results/pilot14/taxtrail_v0_1_method_note.md`

### 19. Current JSONL Inventory Check

```bash
wc -l data/processed/*.jsonl data/agentic_store/*/chunks/*.jsonl 2>/dev/null
```

## Strategic Warning

Do not optimize TaxTrail before the 50-question pilot exists. Without gold evidence, you will tune retrieval by vibes. That is not research; that is self-deception with extra code.
