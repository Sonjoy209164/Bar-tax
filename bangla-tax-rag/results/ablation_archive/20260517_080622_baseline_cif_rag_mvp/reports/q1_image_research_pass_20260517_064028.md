# Q1 Image Search Research Pass

- Run ID: `20260517_064028`
- Created: `2026-05-17T06:40:43.126476+00:00`
- Dataset: `evaluation/q1_image_search_research_set.jsonl`
- Catalog: `data/inventory/catalog.jsonl`
- Retrieval engine requested for full system: `auto`

## Research Question

Can a boutique inventory chatbot combine visual retrieval, catalog identity, reference-image safety, and structured business facts to answer customer screenshot queries reliably?

## Methods

- `full_system`: Current production-style path: visual retrieval when available, owner corrections, reference guard, variant/design resolver, and answer policy.
- `policy_oracle`: Decision-policy ceiling test: injects the known image product as a high-score raw visual hit.
- `naive_oracle_top1`: Unsafe baseline: high-score top-1 is called exact without reference-image or business-rule gating.

## Summary Metrics

| Method | Cases | Strict Pass | Label Acc | Primary/Top-3 | Target Top-3 | Same-Design Recall | Color Recall | Forbidden Viol. | Ref False Exact | Avg Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `full_system` | 20 | 100.0% | 100.0% | 100.0% | 97.2% | 100.0% | 100.0% | 0.0% | 0.0% | 0.7 ms |
| `naive_oracle_top1` | 20 | 0.0% | 71.4% | 90.0% | 80.6% | 16.7% | 0.0% | 100.0% | 100.0% | 0.0 ms |
| `policy_oracle` | 20 | 100.0% | 100.0% | 100.0% | 97.2% | 100.0% | 100.0% | 0.0% | 0.0% | 0.4 ms |

## Full-System Breakdown By Task

| Task | Cases | Strict Pass | Label Acc | Target Top-3 | Forbidden Viol. | Avg Latency |
|---|---:|---:|---:|---:|---:|---:|
| `cross_category_guard` | 6 | 100.0% | 100.0% | 100.0% | 0.0% | 0.5 ms |
| `exact_product` | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 0.8 ms |
| `missing_fact_safety` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 1.2 ms |
| `reference_guard` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 1.5 ms |
| `requested_color_missing` | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 0.9 ms |
| `same_design_variant` | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 0.8 ms |
| `similar_category_search` | 5 | 100.0% | 100.0% | 100.0% | 0.0% | 0.4 ms |
| `size_availability` | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 0.8 ms |
| `variant_listing` | 1 | 100.0% | 100.0% | 75.0% | 100.0% | 0.9 ms |

## Failure Notes

| Method | Case | Task | Decision | Primary | Issues |
|---|---|---|---|---|---|
| `naive_oracle_top1` | `q1_shirt_black_exact` | `exact_product` | `confirmed_exact` | `shirt-ribbed-polo-black` | missing expected variants: ['shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive', 'shirt-ribbed-polo-white'] |
| `naive_oracle_top1` | `q1_shirt_black_white_variant` | `same_design_variant` | `confirmed_exact` | `shirt-ribbed-polo-black` | expected decision_label=confirmed_same_design_variant, got confirmed_exact<br>expected shirt-ribbed-polo-white in primary/top-3, got shirt-ribbed-polo-black / ['shirt-ribbed-polo-black']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-white']<br>missing expected variants: ['shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive']<br>expected requested_color=white, got None |
| `naive_oracle_top1` | `q1_shirt_olive_color_listing` | `variant_listing` | `confirmed_exact` | `shirt-ribbed-polo-olive` | missing expected colors: ['black', 'grey', 'olive', 'white'] |
| `naive_oracle_top1` | `q1_shirt_white_blue_missing` | `requested_color_missing` | `confirmed_exact` | `shirt-ribbed-polo-white` | expected decision_label=similar_style, got confirmed_exact<br>missing expected colors: ['black', 'grey', 'olive', 'white']<br>expected requested_color=blue, got None |
| `naive_oracle_top1` | `q1_reference_saree_no_exact` | `reference_guard` | `confirmed_exact` | `saree-jmd-lotus-red` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_reference_saree_size_hedge` | `missing_fact_safety` | `confirmed_exact` | `saree-jmd-lotus-red` | forbidden decision_label=confirmed_exact<br>expected requested_size=M, got None<br>expected answer to contain 'size' |
| `naive_oracle_top1` | `q1_bag_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-47957-murcia-women-blue-handbag` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_shoe_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-9204-puma-men-future-cat-remix-sf-black-casual-sh` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_cosmetic_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-56019-colorbar-soft-touch-show-stopper-copper-lips` | forbidden decision_label=confirmed_exact<br>expected category signal Cosmetics in hits |
| `naive_oracle_top1` | `q1_perfume_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-43967-dkny-women-red-delicious-perfume` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_three_piece_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-54588-sushilas-women-printed-green-kurta` | forbidden decision_label=confirmed_exact<br>expected category signal Three Piece in hits |
| `naive_oracle_top1` | `q1_pearl_necklace_no_shirt` | `cross_category_guard` | `confirmed_exact` | `jewelry-pearl-necklace-white` | forbidden decision_label=confirmed_exact<br>expected category signal Jewelry in hits |
| `naive_oracle_top1` | `q1_pearl_earring_no_shirt` | `cross_category_guard` | `confirmed_exact` | `jewelry-pearl-earring-white` | forbidden decision_label=confirmed_exact<br>expected category signal Jewelry in hits |
| `naive_oracle_top1` | `q1_watch_no_jewelry_confusion` | `cross_category_guard` | `confirmed_exact` | `hf-11188-carrera-men-dial-steel-finish-strap-silver-w` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_shirt_black_m_size_available` | `size_availability` | `confirmed_exact` | `shirt-ribbed-polo-black` | expected requested_size=M, got None |
| `naive_oracle_top1` | `q1_shirt_white_m_size_out_of_stock` | `size_availability` | `confirmed_exact` | `shirt-ribbed-polo-white` | expected requested_size=M, got None |
| `naive_oracle_top1` | `q1_shirt_olive_xxl_missing` | `size_availability` | `confirmed_exact` | `shirt-ribbed-polo-olive` | expected requested_size=XXL, got None<br>expected answer to contain 'XXL' |
| `naive_oracle_top1` | `q1_lipstick_no_perfume_confusion` | `cross_category_guard` | `confirmed_exact` | `hf-55039-lakme-absolute-matte-merlot-lipstick-45` | forbidden decision_label=confirmed_exact<br>expected category signal Cosmetics in hits |
| `naive_oracle_top1` | `q1_blue_bag_no_shoe_confusion` | `cross_category_guard` | `confirmed_exact` | `hf-31923-fabindia-women-blue-silk-sling-bag` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_black_watch_no_black_shirt_confusion` | `cross_category_guard` | `confirmed_exact` | `hf-30039-skagen-men-black-watch` | forbidden decision_label=confirmed_exact |

## Q1 Readiness Assessment

This is a first-pass research pipeline, not yet a Q1-grade empirical result. It creates the machinery a Q1 paper needs: task-labeled cases, baselines, ablations, safety metrics, and reproducible artifacts. The current catalog still mixes shop-owned product photos with reference/demo images, so production claims must stay conservative.

Strongest publishable direction:

- Evaluate how catalog identity fields (`variant_group_id`, `design_id`, stock/size facts) reduce false exact matches and improve same-design retrieval over raw visual similarity.
- Add a real shop-owned image dataset and compare against CLIP-only, metadata-only, and no-identity ablations.
- Report false-exact rate, same-design recall, top-3 retrieval, and answer-grounding violations rather than only retrieval accuracy.

## One-Pass Reproduction Command

```bash
.venv/bin/python scripts/run_q1_image_research_pass.py --engine metadata
```
