# Future Work for `bangla-tax-rag`

This document separates the current state of the system from the work that still needs to be done.

It is meant to answer two questions clearly:

1. What is already implemented now?
2. What still needs to be implemented for stronger research, stronger evaluation, and stronger publication potential?

## 1. Current System Status

The repository already contains a substantial working pipeline.

## 2. What The System Has Now

### A. Ingestion

Implemented now:

- PDF ingestion pipeline
- page-by-page parsing
- support for:
  - `pdfplumber`
  - `PyMuPDF`
  - `pymupdf4llm`
- OCR-first ingestion path using:
  - `ocrmypdf`
  - `Tesseract`
- Bangla and English document support

Current strengths:

- can ingest English legal acts
- can ingest Bangla PDFs, especially after OCR
- supports local experimentation on real documents

Current weakness:

- difficult Bangla legal PDFs can still produce noisy structure

### B. Normalization

Implemented now:

- Bangla digit normalization
- whitespace normalization
- tax-year extraction
- section reference extraction
- appendix reference extraction
- SRO extraction
- OCR noise cleaning for generation-time evidence

Current strengths:

- useful metadata is extracted and reused across retrieval and generation

Current weakness:

- metadata extraction is still heuristic and sometimes imperfect

### C. Chunking

Implemented now:

- `section_aware` chunking
- `naive` chunking
- `example_aware` chunking
- `table_aware` chunking
- special handling for examples and table-like pages
- row-level handling for some structured appendix pages
- header and noise cleanup for many page types

Current strengths:

- much better than raw fixed-size chunking
- supports section-based legal retrieval
- works meaningfully on English statutes
- improved a lot for OCRed Bangla PDFs

Current weakness:

- chunking is still heuristic
- clause boundaries are not always perfect
- adjacent legal subsections can still merge
- noisy Bangla OCR pages still need stronger structure recovery

### D. Retrieval

Implemented now:

- sparse BM25 retrieval
- dense placeholder retrieval
- hybrid retrieval with reciprocal rank fusion
- metadata-aware filtering
- authority-aware boosts
- tax-year-aware boosts
- section/subsection-aware reranking
- query rewriting for some English and Bangla queries
- support filtering and evidence selection

Current strengths:

- sparse baseline is solid
- hybrid retrieval is usable
- retrieval is much stronger than the initial scaffold

Current weakness:

- dense retrieval is still a placeholder, not a real embedding retriever
- hybrid performance is still constrained by chunk quality

### E. Generation

Implemented now:

- grounded answer generation
- OpenAI-compatible client abstraction
- local deterministic fallback generation
- sentence-level citations
- verification of citation markers
- abstention logic
- conflict note support

Current strengths:

- supports answer generation with evidence only
- avoids unsupported answers better than naive generation
- works with local DeepSeek/Ollama config

Current weakness:

- some queries use deterministic fallback instead of full LLM generation
- generation quality still depends heavily on retrieval and chunk quality

### F. API

Implemented now:

- `/health`
- `/config`
- `/ingest`
- `/build-index`
- `/query`
- `/evaluate`

Current strengths:

- end-to-end usable API
- supports local experimentation and UI integration

Current weakness:

- still optimized for research workflow rather than production-scale deployment

### G. Streamlit UI

Implemented now:

- API connection panel
- PDF ingestion panel
- index building panel
- query panel
- result panel
- chunk browser
- intermediate hit inspection

Current strengths:

- very useful for debugging chunking and retrieval
- supports both English and Bangla experimentation

Current weakness:

- still more of a research tool than a polished end-user product

### H. Dataset Tooling

Implemented now:

- annotation candidate generation
- annotation merge tooling
- dataset validation
- sample chunk dataset
- sample evaluation dataset
- annotation template

Current strengths:

- the benchmark workflow has a working scaffold

Current weakness:

- no large human-annotated gold benchmark yet

### I. Evaluation

Implemented now:

- lightweight evaluation script
- sample evaluation output
- sample benchmark artifacts
- test suite for major components

Current strengths:

- the repo is testable and reproducible
- evaluation workflow exists

Current weakness:

- metrics are still lightweight
- benchmarking is not yet paper-grade

## 3. What Is Only Partially Implemented

These areas exist in early or heuristic form, but are not yet fully realized research contributions.

### Partially implemented now

- authority-aware retrieval
- tax-year-aware retrieval
- conflict detection
- OCR-aware ingestion
- chunk cleaning for noisy documents
- grounded abstention
- legal evidence filtering

### Not fully realized yet

- OCR-uncertainty-aware retrieval
- robust clause-level structure recovery
- research-grade benchmark
- real dense multilingual retrieval
- strong evaluation with human gold labels

## 4. What Still Needs To Be Implemented

## A. For Better Engineering Quality

### 1. Better Bangla chunk structure recovery

Still needed:

- cleaner subsection boundary detection
- better OCR-aware heading repair
- stronger clause splitting
- more reliable section metadata on noisy pages

### 2. Better English statute chunking

Still needed:

- cleaner clause-level splitting
- better footnote and amendment note separation
- cleaner statute section continuation across pages

### 3. Real dense retrieval

Still needed:

- multilingual embeddings
- persistent embedding index
- real dense ranking
- stronger hybrid baseline

### 4. Better query understanding

Still needed:

- better legal intent detection
- better multi-hop query handling
- more robust Bangla-English mixed query support

## B. For Better Research Quality

### 1. Gold benchmark dataset

Still needed:

- human annotation
- evidence labels
- abstention labels
- train/dev/test split
- enough examples for real evaluation

### 2. Stronger evaluation metrics

Still needed:

- retrieval metrics such as:
  - Recall@k
  - MRR
  - nDCG
- generation metrics
- citation faithfulness metrics
- abstention correctness metrics

### 3. Stronger baselines

Still needed:

- real dense retriever baseline
- reranker baseline
- generation baseline comparisons
- OCR/no-OCR comparisons

### 4. Error analysis framework

Still needed:

- failure categories
- per-category logging
- manual inspection templates
- result tables for publication

## C. For A*-Oriented Novelty

### 1. OCR-uncertainty-aware chunking and retrieval

Still needed:

- chunk-level uncertainty scores
- OCR reliability modeling
- uncertainty-aware reranking
- uncertainty-aware abstention
- benchmark proof of improvement

### 2. Benchmark contribution

Still needed:

- a serious Bangla-English legal/tax QA dataset
- documented annotation process
- benchmark statistics
- release-quality splits and schema

### 3. LLM-assisted structure recovery

Still needed:

- selective LLM refinement for ambiguous pages
- structured JSON output for repaired chunks
- comparison with heuristic-only chunking

### 4. Authority- and time-aware legal evidence model

Still needed:

- stronger formalization of legal validity
- clearer conflict resolution
- better support for temporal reasoning
- evaluation on legal correctness, not just retrieval overlap

## 5. Suggested Future Work Roadmap

### Phase 1: Strengthen the current pipeline

Focus on:

- chunking quality
- retrieval quality
- OCR consistency

Tasks:

- improve Bangla subsection recovery
- improve English clause segmentation
- reduce noisy chunk metadata
- replace dense placeholder retrieval

### Phase 2: Build the benchmark

Focus on:

- real question set
- evidence labels
- abstention labels

Tasks:

- generate annotation candidates
- annotate gold questions
- validate benchmark files
- define train/dev/test splits

### Phase 3: Add the publishable method

Focus on one main novelty:

- OCR-uncertainty-aware retrieval
or
- LLM-assisted structure recovery
or
- authority/time-aware legal retrieval

Tasks:

- implement method
- add ablations
- compare against strong baselines

### Phase 4: Prepare publication-quality evaluation

Focus on:

- metrics
- tables
- failure analysis
- reproducibility

Tasks:

- run controlled experiments
- produce ablation tables
- categorize errors
- write clear claims

## 6. Short Summary

### What the system has now

- a strong local legal/tax RAG prototype
- OCR-aware ingestion
- structure-aware chunking
- sparse and hybrid retrieval
- grounded generation with citations
- API, UI, evaluation scaffold, and dataset tooling

### What the system still needs

- cleaner chunking
- real dense retrieval
- gold benchmark dataset
- stronger metrics
- stronger baselines
- a clear method contribution

### What turns it into a publication-ready project

- one strong novelty
- one serious benchmark
- rigorous ablations
- careful failure analysis

That is the path from a useful research system to a publishable research contribution.
