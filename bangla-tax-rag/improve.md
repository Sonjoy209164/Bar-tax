# Improve TODO: CIF-RAG Image Search After 10k Ablation

## Strategic Goal

Make the image-search system useful enough for commerce and strong enough for research.

The 10k ablation already proves the main problem:

```text
Visual similarity alone is not safe enough to make product promises.
```

But the current full CIF-RAG policy is too conservative. It protects the business, but it rejects too many exact claims.

The next target is not simply "increase accuracy." The target is:

```text
Increase accepted exact coverage while keeping false exact claims low.
```

## Current 10k Baseline

Source report:

- `results/lereve_clip10000_comparison_20260519_164406.md`
- `results/lereve_clip10000_clip_baseline_20260519_151528.md`

### Main Numbers

| Method | Top-1 Exact | Top-5 Recall | Wrong Category Top-1 | Accepted Exact Rate | Accepted Exact Precision | Accepted Wrong Exact / All |
|---|---:|---:|---:|---:|---:|---:|
| CLIP only | 22.7% | 32.7% | 53.9% | 100.0% | 22.4% | 77.6% |
| CLIP + metadata rerank | 37.8% | 56.5% | 7.0% | 100.0% | 37.4% | 62.6% |
| CIF-RAG without claim contracts | 14.8% | 56.5% | 7.0% | 20.9% | 70.6% | 6.2% |
| CIF-RAG without risk policy | 35.7% | 56.5% | 7.0% | 93.0% | 38.4% | 57.3% |
| Full CIF-RAG guarded | 14.0% | 56.5% | 7.0% | 18.7% | 74.9% | 4.7% |

## 20k Follow-Up Pass

Source reports:

- `results/lereve_clip20000_clip_baseline_20260519_190206.md`
- `results/lereve_clip20000_comparison_20260519_194304.md`
- `results/lereve_clip20000_clip_baseline_20260519_194652.md`
- `results/lereve_clip20000_comparison_20260519_202619.md`
- `results/lereve_clip20000_comparison_20260519_203838.md`

### 20k Primary-Image Index

| Method | Top-1 Exact | Top-5 Recall | Wrong Category Top-1 | Accepted Exact Rate | Accepted Exact Precision | Accepted Wrong Exact / All |
|---|---:|---:|---:|---:|---:|---:|
| CLIP only | 18.8% | 27.0% | 43.5% | 100.0% | 18.4% | 81.6% |
| CLIP + metadata rerank | 28.5% | 42.6% | 0.0% | 100.0% | 28.1% | 71.9% |
| Full CIF-RAG guarded | 9.8% | 42.6% | 0.0% | 15.9% | 61.8% | 6.1% |

### 20k Naive All-Gallery Index

The all-gallery pass indexed `46,159` product images for `20,000` products.

| Method | Top-1 Exact | Top-5 Recall | Wrong Category Top-1 | Accepted Exact Rate | Accepted Exact Precision | Accepted Wrong Exact / All |
|---|---:|---:|---:|---:|---:|---:|
| CLIP only | 17.9% | 24.4% | 34.9% | 100.0% | 17.5% | 82.5% |
| CLIP + metadata rerank | 23.8% | 33.6% | 0.0% | 100.0% | 23.4% | 76.6% |
| Full CIF-RAG guarded | 10.0% | 33.6% | 0.0% | 19.4% | 51.4% | 9.4% |

### 20k Gallery Index With Alternate-Image Penalty

The best gallery penalty tested so far is:

```text
--gallery-penalty 0.15
```

This means primary images keep their raw CLIP score, while non-primary gallery images are demoted by `0.15` before product-level max aggregation.

| Method | Top-1 Exact | Top-5 Recall | Wrong Category Top-1 | Accepted Exact Rate | Accepted Exact Precision | Accepted Wrong Exact / All |
|---|---:|---:|---:|---:|---:|---:|
| CLIP only | 18.9% | 27.3% | 43.3% | 100.0% | 18.6% | 81.4% |
| CLIP + metadata rerank | 28.7% | 42.9% | 0.0% | 100.0% | 28.3% | 71.7% |
| Full CIF-RAG guarded | 10.0% | 42.9% | 0.0% | 16.2% | 61.7% | 6.2% |

### 20k Interpretation

- [ ] More indexed images did **not** automatically improve retrieval.
  - Primary-only metadata top-5: `42.6%`.
  - Naive all-gallery metadata top-5: `33.6%`.
  - Meaning: raw gallery max-score aggregation introduces distractor images.

- [ ] Category canonicalization helped safety.
  - Metadata rerank wrong-category top-1 became `0.0%` in the 20k comparison.
  - Meaning: the taxonomy guard is now doing real work.

- [ ] CIF-RAG remains safer but still too conservative and underpowered.
  - Primary-only full CIF accepted exact precision: `61.8%`.
  - Naive all-gallery full CIF accepted exact precision: `51.4%`.
  - Meaning: the current CLIP score/margin policy is not enough at 20k scale.

- [ ] Naive all-gallery indexing is **not** the final answer.
  - Next version must rank gallery images by image role/quality and aggregate more intelligently.
  - Do not use raw max-score over all gallery images as the production strategy.

- [ ] Penalized gallery indexing is slightly better than primary-only, but not a breakthrough.
  - Primary-only metadata top-5: `42.6%`.
  - Penalized-gallery metadata top-5: `42.9%`.
  - Meaning: gallery helps only when demoted; it does not solve exact identity by itself.

## What The Result Means

- [ ] CLIP-only is not commerce-safe.
  - Evidence: wrong-category top-1 is `53.9%`.
  - Meaning: raw image similarity often retrieves visually close but commercially wrong products.

- [ ] Metadata rerank helps retrieval but does not make exact claims safe.
  - Evidence: top-5 recall improves to `56.5%`, wrong-category drops to `7.0%`.
  - Problem: accepted wrong exact is still `62.6%` because every top-1 is treated as exact.

- [ ] Risk policy is necessary.
  - Evidence: without risk policy, accepted exact rate becomes `93.0%`, but accepted precision is only `38.4%`.
  - Meaning: category evidence alone is not enough.

- [ ] Claim contracts are necessary.
  - Evidence: full CIF-RAG has `0.0%` accepted wrong-category among accepted exact claims.
  - Meaning: typed evidence protects the business.

- [ ] Full CIF-RAG is currently too conservative.
  - Evidence: accepted exact rate is only `18.7%`.
  - Meaning: the system avoids many bad claims, but it also refuses many useful matches.

## Research Target

Do not optimize only Top-1. That is the wrong target for a commerce bot.

Optimize this tradeoff:

| Metric | Current Full CIF-RAG | Target |
|---|---:|---:|
| Accepted exact rate | 18.7% | 40-60% |
| Accepted exact precision | 74.9% | 80%+ |
| Accepted wrong exact / all | 4.7% | under 5-8% |
| Accepted wrong category / accepted | 0.0% | near 0% |
| Top-5 retrieval recall | 56.5% | 70%+ |
| Abstain or non-exact | 81.3% | under 50-60% |

## Phase 1: Fix Category Contracts First

### Why

Some blocked examples look suspicious:

```text
Expected: Frock
Top-1 candidate: Frock
Decision: category guard blocked exact product claim
```

That means the contract is probably comparing inconsistent labels:

```text
frock vs girls_frock vs kids_frock vs Frock
```

If the category contract is noisy, the risk policy becomes too conservative for the wrong reason.

### Tasks

- [ ] Add canonical category normalization.
  - File: `scripts/run_lereve_image_search_comparison.py`
  - Better future location: `app/inventory/catalog_taxonomy.py`
  - Example mappings:
    - `frock`, `girls frock`, `kid frock`, `kids frock` -> `frock`
    - `t-shirt`, `tee`, `short sleeve t-shirt`, `polo-shirt` -> proper parent/child category
    - `panjabi`, `punjabi`, `kids panjabi` -> `panjabi`
    - `salwar kameez`, `kameez set`, `three piece` -> `salwar_kameez`

- [ ] Add category hierarchy, not only flat equality.
  - Example:
    ```text
    short_sleeve_polo -> polo -> shirt -> tops
    girls_frock -> frock -> dresses
    ```
  - Exact claims can require sibling or same leaf depending risk.

- [ ] Add tests for category normalization.
  - Test file: `tests/test_catalog_taxonomy.py`
  - Must cover:
    - same label with casing/punctuation
    - parent-child compatible categories
    - incompatible category pairs

- [ ] Re-run the 10k ablation after category normalization.
  - Expected:
    - accepted exact rate should increase
    - accepted wrong category should remain near 0

### Command

```bash
.venv/bin/python scripts/run_lereve_image_search_comparison.py \
  --catalog data/inventory/lereve_clip10000_catalog.jsonl \
  --eval evaluation/lereve_clip10000_exact_eval.jsonl \
  --cache-path data/inventory/lereve_clip10000_clip_vectors.json
```

## Phase 2: Add Per-Category Breakdown

### Why

Global metrics hide the real failure modes. Saree, panjabi, frock, t-shirt, and scarf will not fail the same way.

### Tasks

- [ ] Add per-category metrics to the ablation report.
  - File: `scripts/run_lereve_image_search_comparison.py`
  - Metrics:
    - cases
    - top-1 exact
    - top-5 recall
    - accepted exact rate
    - accepted exact precision
    - accepted wrong exact / all
    - wrong-category top-1
    - median rank

- [ ] Add worst-category section.
  - Purpose: show where the next engineering effort should go.

- [ ] Add confusion pairs.
  - Example:
    ```text
    tunic -> frock
    saree -> kameez
    panjabi -> kurta
    ```

### Definition Of Done

- [ ] Report clearly says which 5 categories are hurting exact recall most.
- [ ] Report clearly says which 5 category confusions are causing unsafe matches.

## Phase 3: Index All Gallery Images

### Why

Right now the index is mostly:

```text
one catalog primary image per product
```

But customers send screenshots that may match any product angle:

```text
front image
side image
model image
detail crop
catalog gallery image
```

Exact retrieval will stay weak if only one product image is searchable.

### 20k Finding

Naive all-gallery indexing was tested and it hurt retrieval:

```text
primary-only metadata top-5: 42.6%
all-gallery metadata top-5: 33.6%
```

This means the next gallery version must be smarter:

```text
do not blindly max-pool every gallery image
```

Role-aware demotion was also tested:

```text
gallery penalty 0.03 -> metadata top-5 36.4%
gallery penalty 0.06 -> metadata top-5 38.7%
gallery penalty 0.10 -> metadata top-5 41.3%
gallery penalty 0.15 -> metadata top-5 42.9%
primary-only        -> metadata top-5 42.6%
```

The best tested setting is `0.15`, but the gain is tiny.

### Tasks

- [x] Build multi-image catalog index.
  - Each image becomes one searchable vector.
  - Product score is aggregated from image hits.

- [x] Store image-level metadata:
  - `product_id`
  - `image_id`
  - `image_role`
  - `gallery_index`
  - `local_path`
  - `category`
  - `color`
  - `source_url`

- [ ] Replace naive aggregation with role-aware aggregation.
  - `max_score`: product score is best image hit.
  - `top_k_mean`: product score is mean of best 2-3 image hits.
  - `primary_boost`: primary image gets small boost, but gallery can still win.
  - `query_role_match`: model/detail/query-like image gets more weight when relevant.
  - `low_quality_demotion`: tiny/cropped/noisy images get lower weight.
  - Current implemented baseline: `--gallery-penalty`, best tested value `0.15`.

- [x] Run ablation:
  - primary-only index
  - all-gallery index
  - all-gallery + metadata rerank
  - all-gallery + full CIF-RAG

### Expected Impact

- Initial expected impact was wrong for naive max aggregation.
- Next expected impact applies only after role-aware/quality-aware aggregation:
  - Top-5 recall should increase.
  - Median rank should improve.
  - Accepted exact rate should increase because correct product appears closer.

## Phase 4: Calibrate Risk Policy Instead Of Hardcoding It

### Why

Current policy is hardcoded:

```text
clip_score >= 0.84
and margin >= fixed threshold
```

That is too blunt. Different categories have different score distributions.

### Tasks

- [ ] Add threshold sweep script.
  - Suggested file: `scripts/tune_cif_thresholds.py`

- [ ] Sweep these variables:
  - `min_clip_score`
  - `min_final_margin`
  - `min_clip_margin`
  - `category_required`
  - `color_required`

- [ ] Optimize for multiple operating points:
  - high-safety mode
  - balanced mode
  - high-coverage mode

- [ ] Report precision-coverage curve.
  - X-axis: accepted exact rate
  - Y-axis: accepted exact precision
  - Mark current CIF-RAG point.

- [ ] Add per-category thresholds.
  - Example:
    - saree may need different threshold than t-shirt
    - scarf/accessory may need stricter exact threshold

### Definition Of Done

- [ ] We can choose a policy target:
  ```text
  accepted precision >= 80%
  accepted exact rate as high as possible
  accepted wrong category ~= 0%
  ```

## Phase 5: Improve Visual Retrieval Backbone

### Why

CLIP is general-purpose. Fashion product identity requires sensitivity to:

- fabric
- pattern
- cut
- sleeve
- neckline
- embroidery
- product-specific details

### Tasks

- [ ] Add FashionCLIP baseline.
  - Compare against current CLIP.

- [ ] Add DINOv2 baseline.
  - Useful for visual similarity and instance-level details.

- [ ] Add SigLIP baseline.
  - Strong modern alternative to CLIP.

- [ ] Add ensemble retrieval.
  - Example:
    ```text
    final_visual = 0.45 * CLIP + 0.35 * DINO + 0.20 * metadata
    ```

- [ ] Report:
  - top-1 exact
  - top-5 recall
  - wrong-category top-1
  - accepted exact precision after CIF policy

### Do Not Fine-Tune Yet

Fine-tuning before understanding the failure modes is premature.

First prove:

```text
Which frozen visual backbone gives better retrieval?
Which categories fail?
Which decision policy gives best precision/coverage?
```

Fine-tuning comes after this.

## Phase 6: Add Screenshot-Style Evaluation

### Why

The current eval is honest, but still not the real customer scenario.

Current:

```text
gallery image -> same product retrieval
```

Real use case:

```text
Facebook screenshot + Bangla/Banglish text -> exact/same-design/similar/no-match answer
```

### Tasks

- [ ] Generate screenshot-like query images from gallery images.
  - Add crops.
  - Add compression.
  - Add phone screenshot frame.
  - Add text overlay noise.
  - Add partial product crops.
  - Add multiple products in one image.

- [ ] Build real user-style query set.
  - Suggested file: `evaluation/lereve_cif_screenshot_eval.jsonl`

- [ ] Include query types:
  - exact product
  - same design different color
  - similar style
  - no match
  - size question
  - price question
  - image + Bangla text
  - image + Banglish text
  - image + English text

- [ ] Add labels:
  ```json
  {
    "query_image": "...",
    "query_text": "same design blue ache?",
    "expected_product_id": "...",
    "same_design_variant_ids": [],
    "requested_color": "blue",
    "requested_size": "M",
    "expected_decision": "confirmed_exact|same_design|similar|no_match",
    "forbidden_claims": ["exact_product_if_score_only"],
    "required_evidence": ["product_photo", "variant_group", "stock"]
  }
  ```

## Phase 7: Build Same-Design Variant Ground Truth

### Why

Your real product goal is not only exact retrieval.

The business question is:

```text
Ei same design ta onno color e ache?
```

That requires `variant_group_id` or `design_id`.

### Tasks

- [ ] Mine possible variant groups from SKU/name.
  - Products with same base SKU family.
  - Products with same name but different color.
  - Products with similar URL slug.

- [ ] Add weak variant labels.
  - Example:
    ```text
    variant_group_id = normalized_style_family
    design_id = normalized_design_signature
    ```

- [ ] Manually validate a small gold set.
  - Start with 500 products.
  - Expand to 2,000+ once the process is stable.

- [ ] Add same-design eval.
  - Query: one color image.
  - Expected: same design in other colors.

## Phase 8: Strengthen Claim Contracts

### Why

Claim contracts are the paper's architectural strength. They should be explicit and measurable.

### Tasks

- [ ] Define typed claim classes.
  - `ExactProductClaim`
  - `SameDesignVariantClaim`
  - `SimilarStyleClaim`
  - `ColorAvailabilityClaim`
  - `SizeStockClaim`
  - `PriceClaim`
  - `NoMatchClaim`

- [ ] Define required evidence per claim.
  - Exact product:
    - high visual score
    - margin evidence
    - category compatible
    - product image proof
  - Same design:
    - variant group or design ID
    - requested color checked
    - stock checked
  - Price:
    - catalog price field
  - Size:
    - size stock field

- [ ] Log claim coverage.
  - Metric:
    ```text
    claim_evidence_coverage = supported_claims / total_claims
    ```

## Phase 9: Add Owner Correction Loop

### Why

Production commerce data will never be perfect. A shop owner must be able to correct bad matches.

### Tasks

- [ ] Save low-confidence queries.
  - File: `data/feedback/image_search_failures.jsonl`

- [ ] Save owner corrections.
  - File: `data/feedback/image_search_corrections.jsonl`

- [ ] Correction schema:
  ```json
  {
    "query_image_id": "upload_123",
    "wrong_product_id": "p_old",
    "correct_product_id": "p_new",
    "correction_type": "exact_product|same_design|similar|no_match",
    "notes": "same embroidery, different color",
    "created_at": "..."
  }
  ```

- [ ] Use corrections during reranking.
  - Owner-confirmed exact mapping beats model score.

## Phase 10: Paper-Grade Reporting

### Why

The paper needs more than one table. It needs a full argument:

```text
CLIP retrieves visually similar products.
CIF-RAG controls what claims the bot is allowed to make.
This reduces unsafe commerce answers.
```

### Tasks

- [ ] Add these result tables:
  - retrieval metrics
  - commerce safety metrics
  - precision/coverage tradeoff
  - per-category breakdown
  - screenshot robustness
  - same-design variant accuracy
  - ablation table

- [ ] Add these ablations:
  - CLIP only
  - FashionCLIP only
  - DINOv2 only
  - metadata only
  - CLIP + metadata
  - no claim contracts
  - no risk policy
  - no gallery indexing
  - no category hierarchy
  - full CIF-RAG

- [ ] Add error taxonomy:
  - wrong category
  - right category wrong product
  - same style but not exact
  - color confusion
  - missing variant group
  - weak image quality
  - over-abstention

## Immediate Next 5 Engineering Tasks

Do these in order.

- [ ] 1. Add category canonicalization and hierarchy.
  - Goal: remove false category-blocks.
  - Expected metric move: accepted exact rate up, wrong-category accepted stays near 0.

- [ ] 2. Add per-category breakdown to the report.
  - Goal: know where the system fails.
  - Expected metric move: not a model improvement, but critical diagnosis.

- [ ] 3. Add all-gallery image indexing.
  - Goal: improve top-5 recall.
  - Expected metric move: top-5 recall from `56.5%` to `70%+`.

- [ ] 4. Add threshold sweep.
  - Goal: find better precision/coverage operating point.
  - Expected metric move: accepted exact rate from `18.7%` toward `40%+`.

- [ ] 5. Build screenshot-style eval.
  - Goal: make the benchmark match the real Facebook screenshot use case.
  - Expected research value: much stronger paper claim.

## Commands To Keep Using

### 10k CLIP Baseline

```bash
.venv/bin/python scripts/run_lereve_clip100_baseline.py \
  --limit 10000 \
  --catalog-out data/inventory/lereve_clip10000_catalog.jsonl \
  --eval-out evaluation/lereve_clip10000_exact_eval.jsonl \
  --cache-path data/inventory/lereve_clip10000_clip_vectors.json
```

### 10k Ablation Comparison

```bash
.venv/bin/python scripts/run_lereve_image_search_comparison.py \
  --catalog data/inventory/lereve_clip10000_catalog.jsonl \
  --eval evaluation/lereve_clip10000_exact_eval.jsonl \
  --cache-path data/inventory/lereve_clip10000_clip_vectors.json
```

### Fast Smoke Test

```bash
.venv/bin/python scripts/run_lereve_image_search_comparison.py \
  --catalog data/inventory/lereve_clip100_catalog.jsonl \
  --eval evaluation/lereve_clip100_exact_eval.jsonl \
  --cache-path data/inventory/lereve_clip100_clip_vectors.json \
  --limit 20
```

## Definition Of Done For Next Pass

- [ ] Category guard no longer blocks obvious same-category examples.
- [ ] Report includes per-category and confusion-pair metrics.
- [ ] All-gallery indexing is implemented.
- [ ] Full CIF-RAG accepted exact rate improves meaningfully.
- [ ] Full CIF-RAG accepted wrong category remains near 0.
- [ ] Accepted wrong exact / all stays under 5-8%.
- [ ] A screenshot-style eval set exists.
- [ ] The result table can support a paper argument, not only an engineering demo.

## Hard Strategic Warning

Do not sell this as "near perfect image search" yet.

The current result proves the architecture is safer than raw CLIP, but not yet strong enough as a final production product or Q1-grade research result.

The next breakthrough must come from:

```text
better catalog identity
+ gallery-level retrieval
+ threshold calibration
+ screenshot-style evaluation
```

That is the path from interesting demo to publishable system.
