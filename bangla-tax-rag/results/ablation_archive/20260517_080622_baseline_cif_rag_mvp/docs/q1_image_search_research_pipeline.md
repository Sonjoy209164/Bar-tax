# Q1 Image Search Research Pipeline

This document defines the first-pass research pipeline for turning the boutique image-search chatbot into a publishable experiment.

The core idea is not "CLIP can find similar images." That is too weak for a Q1 paper.

The stronger research claim is:

```text
Customer screenshot search becomes safer and more commercially useful when visual retrieval is combined with
catalog identity, variant grouping, stock/size facts, reference-image guardrails, and grounded answer policy.
```

For the next architectural-novelty version, use:

- [CIF-RAG Architecture Plan](cif_rag_architecture_plan.md)

CIF-RAG reframes the work as **counterfactual product-identity retrieval**: hold the product design from a screenshot, intervene on requested factors such as color or size, verify catalog/stock evidence, and only then generate a commerce-safe answer.

## What The Pipeline Tests

The evaluation separates the actual retail decisions customers care about:

- Exact product confirmation
- Same-design/different-color variant search
- Available color listing
- Requested color missing
- Size/stock availability
- Reference-image exact-claim prevention
- Cross-category confusion prevention
- Similar-item recommendation

This matters because a model can look good on generic image similarity while still failing as a salesperson.

## Dataset Contract

Research dataset:

```text
evaluation/q1_image_search_research_set.jsonl
```

Each case contains:

- `case_id`: stable case identifier.
- `task_type`: the business/research task.
- `language`: English, Bangla, or Banglish.
- `difficulty`: why this case is hard.
- `image_path`: local screenshot/product image path.
- `query_text`: customer text sent with the image.
- `expected_decision_label`: expected business-safe decision when known.
- `forbidden_decision_label`: labels that must not be produced.
- `expected_primary_product_id`: product that should appear in primary or top-3.
- `expected_target_product_ids`: target products for recall measurement.
- `expected_same_design_variant_ids`: required same-design sibling products.
- `expected_available_colors`: color availability expected from catalog facts.
- `forbidden_product_ids`: products that must not appear because they indicate category confusion.
- `metric_tags`: metrics groups such as `reference_guard`, `same_design`, `cross_category_guard`.
- `research_question`: what this case tests.

## Methods Compared

The runner compares multiple paths:

```text
full_system
  -> current system path
  -> retrieval + owner corrections + reference guard + variant/design resolver + answer policy

metadata_baseline
  -> deterministic text/category/color fallback
  -> useful when CLIP is unavailable

no_identity_ablation
  -> removes variant_group_id/design_id before decision
  -> tests how much catalog identity helps

policy_oracle
  -> injects the known image product as a high-score raw visual candidate
  -> tests decision policy independent of retrieval quality

naive_oracle_top1
  -> calls top-1 high-score candidate "exact"
  -> unsafe baseline showing why guardrails are needed
```

## Metrics

The generated report calculates:

- Strict pass rate
- Decision-label accuracy
- Primary/top-3 accuracy
- Target top-3 recall
- Same-design variant recall
- Available-color recall
- Forbidden-product violation rate
- False-exact rate on reference-image cases
- Average latency

For a paper, the most important metrics are not generic top-1 accuracy. They are:

- False exact rate
- Same-design recall
- Cross-category violation rate
- Grounded availability correctness

Those metrics map directly to customer trust and business risk.

## Command

Fast local pass:

```bash
.venv/bin/python scripts/run_q1_image_research_pass.py --engine metadata
```

CLIP pass, if model dependencies are available:

```bash
.venv/bin/python scripts/run_q1_image_research_pass.py --engine auto
```

Output files are saved in:

```text
results/q1_image_research_pass_*.json
results/q1_image_research_pass_*.md
```

## Current Limitation

This pipeline is Q1-shaped, but the current dataset is not yet enough for a Q1 paper.

The current catalog includes:

- Some shop-owned/demo product photos such as the ribbed polo group.
- Many reference/demo images from public fashion datasets.

For a strong Q1 submission, the next step is a real shop-owned dataset:

```text
30-100 real products
2-4 images per product
variant groups for same design across color/size
messy customer-style screenshots
owner-confirmed exact/same-design/similar/no-match labels
```

## Publishable Hypothesis

A credible paper can test:

```text
Adding catalog identity and answer-grounding policy to visual product retrieval
reduces false exact matches while preserving same-design recall for boutique e-commerce search.
```

The ablation table should show:

- CLIP-only has better broad visual retrieval but unsafe exact claims.
- Metadata-only is safer but weaker on visual discovery.
- Full system improves same-design answers and reduces false exact claims.
- Removing `variant_group_id` / `design_id` damages same-design/color availability behavior.

That is the path from engineering demo to research contribution.
