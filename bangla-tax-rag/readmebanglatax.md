# Bangla Legal Tax Bot Checklist

## Goal
- [x] Focus the app on Bangla income-tax legal documents.
- [x] Support `Income-tax_Paripatra_2025-2026-1.pdf` as the first target corpus.
- [x] Allow any Bangla PDF to be uploaded, parsed, structured, indexed, and queried.
- [x] Reuse the existing legal RAG flow: parser -> structure builder -> metadata tagger -> parent-child linker -> chunks -> BM25/vector indexes -> agentic query runtime.
- [x] Disable inventory routes and inventory frontend by default.

## Current API Surface
- [x] `GET /bangla-tax/status` checks whether the legal tax runtime is ready.
- [x] `POST /bangla-tax/upload` uploads a PDF with multipart form data.
- [x] `POST /bangla-tax/ingest` ingests a local PDF path, useful for the repo-root Paripatra PDF.
- [x] `POST /bangla-tax/query` asks the loaded Bangla tax corpus.
- [x] `POST /bangla-tax/query` accepts `prompt_strategy`: `zero_shot`, `one_shot`, `few_shot`, or `evidence_only`.
- [x] `POST /bangla-tax/query` accepts `reasoning_trace_mode`: `off`, `summary`, or `trace`.
- [x] Legacy `/agentic/*`, `/ingest`, `/build-index`, and `/query` remain available for compatibility.
- [x] `/inventory/*` is off unless `INVENTORY_ENABLED=true`.
- [x] `/frontend/*` is off unless `FRONTEND_ENABLED=true`.
- [x] Bangla tax runtime is isolated under `data/agentic_store/bangla_tax` so old demo/inventory/legal corpora do not pollute answers.

## First Corpus: Paripatra 2025-2026
- [ ] Confirm the PDF exists at `../Income-tax_Paripatra_2025-2026-1.pdf` from the `bangla-tax-rag` directory.
- [ ] Start the API:
  ```bash
  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4893
  ```
- [ ] Ingest the local Paripatra:
  ```bash
  curl -X POST http://127.0.0.1:4893/bangla-tax/ingest \
    -H 'Content-Type: application/json' \
    -d '{
      "source_path": "../Income-tax_Paripatra_2025-2026-1.pdf",
      "document_id": "income-tax-paripatra-2025-2026",
      "act_title": "আয়কর পরিপত্র ২০২৫-২০২৬",
      "ocr_enabled": false
    }'
  ```
- [ ] Check runtime readiness:
  ```bash
  curl http://127.0.0.1:4893/bangla-tax/status
  ```
- [ ] Ask a grounded Bangla tax question:
  ```bash
  curl -X POST http://127.0.0.1:4893/bangla-tax/query \
    -H 'Content-Type: application/json' \
    -d '{
      "question": "২০২৫-২০২৬ করবর্ষে স্বাভাবিক ব্যক্তির করহার কী?",
      "prompt_strategy": "few_shot",
      "reasoning_trace_mode": "trace"
    }'
  ```

## Upload Flow
- [ ] Upload a Bangla PDF:
  ```bash
  curl -X POST http://127.0.0.1:4893/bangla-tax/upload \
    -F file=@../Income-tax_Paripatra_2025-2026-1.pdf \
    -F document_id=income-tax-paripatra-2025-2026 \
    -F act_title='আয়কর পরিপত্র ২০২৫-২০২৬' \
    -F ocr_enabled=false
  ```
- [ ] For scanned PDFs, retry with `ocr_enabled=true` after installing system OCR dependencies:
  ```bash
  sudo apt-get install ocrmypdf tesseract-ocr-ben tesseract-ocr-eng
  ```

## Configuration
- [x] `BANGLA_TAX_UPLOAD_DIR=data/raw/bangla_tax_uploads`
- [x] `BANGLA_TAX_DEFAULT_DOCUMENT_ID=income-tax-paripatra-2025-2026`
- [x] `BANGLA_TAX_DEFAULT_TITLE=আয়কর পরিপত্র ২০২৫-২০২৬`
- [x] `BANGLA_TAX_OCR_ENABLED=false`
- [x] `PARSER_USE_PYMUPDF4LLM=false`
- [x] `INVENTORY_ENABLED=false`
- [x] `FRONTEND_ENABLED=false`

## Quality Gates
- [x] Bangla headings like `১।` and `১.২` are treated as legal-tax sections.
- [x] Bangla numbered list items like `১. মহিলা করদাতা...` are not split into fake sections.
- [x] Parser avoids slow `pymupdf4llm` extraction by default.
- [x] Zero-shot answer mode uses the existing grounded legal RAG path.
- [x] One-shot and few-shot modes apply structured Bangla legal-tax answer formats.
- [x] Chain-of-thought is implemented as a safe reasoning trace, not raw private reasoning text.
- [x] Year-sensitive rate retrieval prefers the requested tax year, e.g. `২০২৫-২০২৬` does not drift to `২০২৬-২০২৭`.
- [x] Live Paripatra smoke test passed after OCR ingest: `1114` retrieval chunks, `310` reasoning chunks, `880` legal nodes.
- [ ] Run focused tests before demo:
  ```bash
  .venv/bin/pytest tests/test_parser.py tests/test_structure_builder.py tests/test_api_endpoints.py tests/test_agentic_api.py
  ```
- [ ] Run one real Paripatra ingestion smoke test and inspect chunk counts.

## Strategic Next Steps
- [ ] Add a small Bangla legal-tax evaluation set for rate lookup, surcharge, amendment, deadline, and definition questions.
- [ ] Add answer policy text that clearly says this is grounded legal information, not final professional tax advice.
- [ ] Add a lightweight tax-chat frontend after API behavior is stable.
- [ ] Decide whether old inventory modules should be archived, moved to a plugin, or kept behind the feature flag.
