# Dataset

This document describes the benchmark dataset layer used for local experiments and paper preparation.

## Dataset Schema

Each gold dataset row supports:

- `question_id`
- `question_text`
- `question_type`
- `answer_text`
- `expected_chunk_ids`
- `expected_doc_ids`
- `expected_sections`
- `expected_tax_year`
- `preferred_authority_level`
- `should_abstain`
- `answer_language`
- `notes`

## Annotation Workflow

1. Build chunk JSONL from source documents.
2. Generate annotation candidates from chunk records.
3. Review and edit the candidate JSONL manually.
4. Fill in gold answer fields and expected evidence fields.
5. Merge annotation files if multiple annotators or batches are used.
6. Validate the final dataset against the source chunk JSONL.

## Recommended Question Type Distribution

For a balanced benchmark, include a mix of:

- `rate_lookup`
- `definition`
- `amendment`
- `procedure`
- `example_based`
- `calculation`
- `comparison`
- `authority_conflict`

Start with more `rate_lookup`, `definition`, and `procedure` rows, then add conflict and abstention cases for robustness.

## Train/Dev/Test Splits

Recommended split strategy:

1. Split by document and tax year when possible to reduce leakage.
2. Keep question types distributed across all splits.
3. Reserve hard conflict and abstention examples for dev and test.
4. Track split membership in a separate manifest if the core JSONL should stay clean.

## Commands

Generate annotation candidates:

```bash
.venv/bin/python scripts/build_annotation_candidates.py \
  --chunks data/processed/sample_chunks.jsonl \
  --output results/annotation_candidates.jsonl
```

Validate an annotated dataset:

```bash
.venv/bin/python scripts/validate_dataset.py \
  --dataset data/templates/annotation_template.jsonl \
  --chunks data/processed/sample_chunks.jsonl
```
