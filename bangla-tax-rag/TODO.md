# TODO

GitHub-style checklist for `bangla-tax-rag`.

Use this file as the working project board for engineering, benchmarking, experiments, and publication preparation.

## Immediate

- [ ] Run the English pipeline end to end and confirm the current clean baseline.
- [ ] Run the Bangla OCR pipeline end to end and confirm the current OCR baseline.
- [ ] Decide the primary research corpus for the next phase:
  - [ ] English Act first
  - [ ] Bangla OCR circular first
- [ ] Save one stable baseline result set under `results/`.
- [ ] Verify the current API, UI, and CLI all point to the intended index files.

## Chunking

- [ ] Audit bad chunk pages manually in the Streamlit chunk browser.
- [ ] Create a list of recurring chunking failure patterns.
- [ ] Improve Bangla subsection boundary detection.
- [ ] Improve English clause-level splitting.
- [ ] Improve heading recovery on OCRed Bangla pages.
- [ ] Reduce noisy metadata assignment for corrupted pages.
- [ ] Add chunk quality scoring fields to chunk records.
- [ ] Add tests for new chunk boundary failure cases.

## OCR

- [ ] Compare Bangla extraction quality with and without OCR.
- [ ] Measure how OCR changes chunk count and chunk quality.
- [ ] Identify pages where OCR still fails badly.
- [ ] Add chunk-level OCR or text-quality confidence estimation.
- [ ] Propagate OCR confidence into chunk metadata.

## Retrieval

- [ ] Freeze the sparse retrieval baseline.
- [ ] Replace the dense placeholder retriever with a real multilingual embedding retriever.
- [ ] Rebuild dense index artifacts after dense retriever implementation.
- [ ] Compare sparse vs dense vs hybrid on the same query set.
- [ ] Improve support filtering for legal evidence.
- [ ] Improve multi-passage evidence selection.
- [ ] Add stronger legal conflict resolution logic.
- [ ] Add more retrieval tests for English Act queries.
- [ ] Add more retrieval tests for Bangla OCRed queries.

## Authority and Time Awareness

- [ ] Formalize authority-aware reranking beyond heuristic boosts.
- [ ] Improve tax-year-aware evidence validity checks.
- [ ] Add conflict cases where authority differs.
- [ ] Add conflict cases where tax year differs.
- [ ] Evaluate authority-aware retrieval on a labeled benchmark.
- [ ] Evaluate tax-year-aware retrieval on a labeled benchmark.

## Generation

- [ ] Add explicit logging of which backend answered each query:
  - [ ] DeepSeek via Ollama
  - [ ] deterministic fallback
- [ ] Improve answer rendering for mention/existence queries.
- [ ] Improve answer rendering for rate table queries.
- [ ] Improve answer rendering for section summary queries.
- [ ] Add more tests for abstention correctness.
- [ ] Add more tests for citation faithfulness.
- [ ] Add more tests for unsupported answer rejection.
- [ ] Add UI visibility for generation backend used.

## Benchmark Dataset

- [ ] Generate annotation candidates from the English corpus.
- [ ] Generate annotation candidates from the Bangla OCR corpus.
- [ ] Define the benchmark schema version.
- [ ] Create a first gold dataset subset.
- [ ] Add human-annotated evidence labels.
- [ ] Add abstention-required examples.
- [ ] Add authority-conflict examples.
- [ ] Add tax-year-sensitive examples.
- [ ] Add train/dev/test splits.
- [ ] Document benchmark statistics.

## Evaluation

- [ ] Expand retrieval metrics:
  - [ ] Recall@k
  - [ ] MRR
  - [ ] nDCG
  - [ ] evidence precision
- [ ] Expand generation metrics:
  - [ ] citation support rate
  - [ ] unsupported claim rate
  - [ ] abstention precision
  - [ ] abstention recall
- [ ] Add OCR robustness evaluation.
- [ ] Add chunk quality evaluation.
- [ ] Add legal correctness-oriented evaluation where possible.
- [ ] Save all evaluation outputs under structured result directories.

## Experiments

### OCR Experiments

- [ ] Run OCR vs non-OCR comparison on Bangla PDFs.
- [ ] Compare chunk quality under OCR vs non-OCR.
- [ ] Compare retrieval quality under OCR vs non-OCR.

### Chunking Experiments

- [ ] Compare `section_aware` vs `naive`.
- [ ] Compare `section_aware` vs `example_aware`.
- [ ] Compare `section_aware` vs `table_aware`.
- [ ] Measure downstream retrieval quality for each chunking mode.

### Retrieval Experiments

- [ ] Compare sparse vs hybrid retrieval.
- [ ] Compare hybrid with and without authority-aware reranking.
- [ ] Compare hybrid with and without tax-year-aware reranking.
- [ ] Compare hybrid before and after real dense retrieval is implemented.

### Generation Experiments

- [ ] Compare retrieval-only vs grounded generation.
- [ ] Compare local DeepSeek generation vs deterministic fallback behavior.
- [ ] Measure citation verification pass rates.
- [ ] Measure abstention rates by question type.

### Novelty Experiments

- [ ] Implement OCR-uncertainty-aware chunk scoring.
- [ ] Inject uncertainty into retrieval ranking.
- [ ] Compare standard retrieval vs uncertainty-aware retrieval.
- [ ] Measure whether uncertainty-aware retrieval improves evidence quality.

## A*-Oriented Research Work

- [ ] Choose one primary novelty:
  - [ ] OCR-uncertainty-aware retrieval
  - [ ] LLM-assisted structure recovery
  - [ ] authority/time-aware legal evidence selection
- [ ] Choose one supporting contribution:
  - [ ] benchmark dataset
  - [ ] evaluation framework
  - [ ] error analysis taxonomy
- [ ] Write a clear problem statement.
- [ ] Write a clear hypothesis.
- [ ] Define the exact claimed contribution before adding more features.

## Error Analysis

- [ ] Define error categories:
  - [ ] OCR failure
  - [ ] parser failure
  - [ ] chunk boundary failure
  - [ ] wrong section retrieval
  - [ ] temporal mismatch
  - [ ] authority mismatch
  - [ ] unsupported generation
  - [ ] over-abstention
  - [ ] under-abstention
- [ ] Create an error analysis spreadsheet or JSON template.
- [ ] Record representative examples for each category.
- [ ] Summarize dominant failure modes after each major experiment.

## Documentation

- [ ] Keep `README.md` aligned with actual system behavior.
- [ ] Keep `readme_exec.md` aligned with actual runnable commands.
- [ ] Keep `readme_futurework.md` aligned with real project status.
- [ ] Keep `READMEA*.md` aligned with the current publication plan.
- [ ] Keep `readme_ocr_uncertainty.md` aligned with the actual novelty implementation.
- [ ] Add a docs index page if needed.

## Paper Preparation

- [ ] Draft title options.
- [ ] Draft abstract.
- [ ] Draft introduction.
- [ ] Turn `docs/related_work.md` into a formal related work section.
- [ ] Turn `readme_ocr_uncertainty.md` into a method section draft.
- [ ] Create results table templates.
- [ ] Create ablation table templates.
- [ ] Create error analysis table templates.
- [ ] Write a limitation section.
- [ ] Write a reproducibility section.

## Strongest Next 5 Tasks

- [ ] Replace dense placeholder retrieval with a real multilingual embedding retriever.
- [ ] Build the first human-annotated gold benchmark subset.
- [ ] Improve Bangla chunk boundaries on OCRed subsection pages.
- [ ] Implement chunk-level OCR or text-quality confidence scoring.
- [ ] Run the first real ablation study and store results.

## Done Criteria For A Stronger Research Version

- [ ] Stable English baseline exists.
- [ ] Stable Bangla OCR baseline exists.
- [ ] Gold benchmark exists.
- [ ] Real dense retriever exists.
- [ ] One main novelty is implemented.
- [ ] Controlled ablations are complete.
- [ ] Error analysis is complete.
- [ ] Paper outline is drafted.
