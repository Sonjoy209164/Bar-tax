# Run And Test Guide

This file is the practical command sheet for checking what changed in the image-search and CIF-RAG pipeline.

The baseline archive to compare against is:

```text
results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/
```

## 1. Go To The Project

```bash
cd "/home/sonjoy/Bar tax/bangla-tax-rag"
```

## 2. Run Fast Safety Tests

Use this first after code changes.

```bash
.venv/bin/python -m pytest tests/test_cif_rag.py tests/test_image_search_ask.py tests/test_image_matching.py
```

What this checks:

- CIF-RAG planner behavior
- image-search API wiring
- image matching safety rules
- same-design and product-card behavior

## 3. Run Full Image-Search Ablation Benchmark

```bash
.venv/bin/python scripts/run_q1_image_research_pass.py --engine auto --methods full_system metadata_baseline no_identity_ablation policy_oracle naive_oracle_top1
```

This creates new files like:

```text
results/q1_image_research_pass_YYYYMMDD_HHMMSS.json
results/q1_image_research_pass_YYYYMMDD_HHMMSS.md
```

Compare the newest report against:

```text
results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064205.md
```

Key metrics to watch:

- `full_system.strict_pass_rate` should go up.
- `same_design_variant_recall` should go up.
- `available_color_recall` should go up.
- `forbidden_violation_rate` should stay `0`.
- `false_exact_on_reference_rate` should stay `0`.

## 4. Run CIF-RAG Architecture Benchmark

```bash
.venv/bin/python scripts/run_cif_rag_research_eval.py
```

This creates new files like:

```text
results/cif_rag_research_pass_YYYYMMDD_HHMMSS.json
results/cif_rag_research_pass_YYYYMMDD_HHMMSS.md
```

Compare the newest report against:

```text
results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/cif_rag_research_pass_20260517_080150.md
```

Key metrics to watch:

- `planner_pass_rate`
- `claim_contract_pass_rate`
- `risk_policy_pass_rate`
- `pass_rate`

These should stay high. If they drop, the architecture is becoming less safe or less consistent.

## 5. Save A New Ablation Checkpoint

After running benchmarks, archive the new results.

```bash
.venv/bin/python scripts/archive_ablation_results.py --label after_my_change
```

Use a meaningful label:

```bash
.venv/bin/python scripts/archive_ablation_results.py --label after_color_threshold_tuning
.venv/bin/python scripts/archive_ablation_results.py --label after_variant_graph_fix
.venv/bin/python scripts/archive_ablation_results.py --label after_clip_threshold_change
```

The archive index is:

```text
results/ablation_archive/README.md
```

## 6. Decision Rule

A change is good only if it improves usefulness without increasing unsafe commercial claims.

Good change:

```text
same-design recall improves
available-color recall improves
false exact claims stay zero
forbidden claim violations stay zero
```

Bad change:

```text
accuracy improves
but false exact claims increase
```

For this product, commercial safety matters more than raw retrieval confidence.

