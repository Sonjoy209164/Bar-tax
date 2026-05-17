# Q1 Image Search Research Pass

- Run ID: `20260517_064205`
- Created: `2026-05-17T06:42:19.828440+00:00`
- Dataset: `evaluation/q1_image_search_research_set.jsonl`
- Catalog: `data/inventory/catalog.jsonl`
- Retrieval engine requested for full system: `auto`

## Research Question

Can a boutique inventory chatbot combine visual retrieval, catalog identity, reference-image safety, and structured business facts to answer customer screenshot queries reliably?

## Methods

- `full_system`: Current production-style path: visual retrieval when available, owner corrections, reference guard, variant/design resolver, and answer policy.
- `metadata_baseline`: Deterministic metadata fallback: text/category/color cues plus the same decision policy.
- `no_identity_ablation`: Same retrieval candidates as the full path, but variant_group_id/design_id removed before the decision layer.
- `policy_oracle`: Decision-policy ceiling test: injects the known image product as a high-score raw visual hit.
- `naive_oracle_top1`: Unsafe baseline: high-score top-1 is called exact without reference-image or business-rule gating.

## Summary Metrics

| Method | Cases | Strict Pass | Label Acc | Primary/Top-3 | Target Top-3 | Same-Design Recall | Color Recall | Forbidden Viol. | Ref False Exact | Avg Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `full_system` | 20 | 100.0% | 100.0% | 100.0% | 97.2% | 100.0% | 100.0% | 0.0% | 0.0% | 0.6 ms |
| `metadata_baseline` | 20 | 40.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 1.1 ms |
| `naive_oracle_top1` | 20 | 0.0% | 71.4% | 90.0% | 80.6% | 16.7% | 0.0% | 100.0% | 100.0% | 0.0 ms |
| `no_identity_ablation` | 20 | 65.0% | 0.0% | 100.0% | 97.2% | 100.0% | 0.0% | 0.0% | 0.0% | 6.0 ms |
| `policy_oracle` | 20 | 100.0% | 100.0% | 100.0% | 97.2% | 100.0% | 100.0% | 0.0% | 0.0% | 0.3 ms |

## Full-System Breakdown By Task

| Task | Cases | Strict Pass | Label Acc | Target Top-3 | Forbidden Viol. | Avg Latency |
|---|---:|---:|---:|---:|---:|---:|
| `cross_category_guard` | 6 | 100.0% | 100.0% | 100.0% | 0.0% | 0.5 ms |
| `exact_product` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 0.8 ms |
| `missing_fact_safety` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 1.2 ms |
| `reference_guard` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 0.8 ms |
| `requested_color_missing` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 0.9 ms |
| `same_design_variant` | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 0.8 ms |
| `similar_category_search` | 5 | 100.0% | 100.0% | 100.0% | 0.0% | 0.4 ms |
| `size_availability` | 3 | 100.0% | 100.0% | 100.0% | 0.0% | 0.8 ms |
| `variant_listing` | 1 | 100.0% | 100.0% | 75.0% | 0.0% | 0.8 ms |

## Failure Notes

| Method | Case | Task | Decision | Primary | Issues |
|---|---|---|---|---|---|
| `metadata_baseline` | `q1_shirt_black_exact` | `exact_product` | `confirmed_same_design_variant` | `hf-53759-puma-men-grey-t-shirt` | expected decision_label=confirmed_exact, got confirmed_same_design_variant<br>expected shirt-ribbed-polo-black in primary/top-3, got hf-53759-puma-men-grey-t-shirt / ['hf-53759-puma-men-grey-t-shirt', 'hf-1855-inkfruit-mens-chain-reaction-t-shirt', 'pant-jeans-blue-32']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-black']<br>missing expected variants: ['shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive', 'shirt-ribbed-polo-white'] |
| `no_identity_ablation` | `q1_shirt_black_exact` | `exact_product` | `likely_same_design` | `shirt-ribbed-polo-black` | expected decision_label=confirmed_exact, got likely_same_design |
| `naive_oracle_top1` | `q1_shirt_black_exact` | `exact_product` | `confirmed_exact` | `shirt-ribbed-polo-black` | missing expected variants: ['shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive', 'shirt-ribbed-polo-white'] |
| `metadata_baseline` | `q1_shirt_black_white_variant` | `same_design_variant` | `similar_style` | `pant-jeans-blue-32` | expected decision_label=confirmed_same_design_variant, got similar_style<br>expected shirt-ribbed-polo-white in primary/top-3, got pant-jeans-blue-32 / ['shirt-formal-white-l', 'hf-58183-rocky-s-women-white-handbag', 'hf-3168-nike-men-s-incinerate-msl-white-blue-shoe']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-white']<br>missing expected variants: ['shirt-ribbed-polo-black', 'shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive'] |
| `no_identity_ablation` | `q1_shirt_black_white_variant` | `same_design_variant` | `likely_same_design` | `shirt-ribbed-polo-black` | expected decision_label=confirmed_same_design_variant, got likely_same_design |
| `naive_oracle_top1` | `q1_shirt_black_white_variant` | `same_design_variant` | `confirmed_exact` | `shirt-ribbed-polo-black` | expected decision_label=confirmed_same_design_variant, got confirmed_exact<br>expected shirt-ribbed-polo-white in primary/top-3, got shirt-ribbed-polo-black / ['shirt-ribbed-polo-black']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-white']<br>missing expected variants: ['shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive']<br>expected requested_color=white, got None |
| `metadata_baseline` | `q1_shirt_olive_color_listing` | `variant_listing` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected decision_label=confirmed_exact, got confirmed_same_design_variant<br>expected shirt-ribbed-polo-olive in primary/top-3, got pant-jeans-blue-32 / ['pant-jeans-blue-32', 'shirt-oxford-blue-m', 'pant-cargo-olive-34']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-black', 'shirt-ribbed-polo-grey', 'shirt-ribbed-polo-olive', 'shirt-ribbed-polo-white']<br>missing expected colors: ['black', 'grey', 'olive', 'white'] |
| `no_identity_ablation` | `q1_shirt_olive_color_listing` | `variant_listing` | `likely_same_design` | `shirt-ribbed-polo-olive` | expected decision_label=confirmed_exact, got likely_same_design<br>missing expected colors: ['black', 'grey', 'olive', 'white'] |
| `naive_oracle_top1` | `q1_shirt_olive_color_listing` | `variant_listing` | `confirmed_exact` | `shirt-ribbed-polo-olive` | missing expected colors: ['black', 'grey', 'olive', 'white'] |
| `metadata_baseline` | `q1_shirt_white_blue_missing` | `requested_color_missing` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected decision_label=similar_style, got confirmed_same_design_variant<br>missing expected colors: ['black', 'grey', 'olive', 'white']<br>color should be absent but appeared in available_colors: blue |
| `no_identity_ablation` | `q1_shirt_white_blue_missing` | `requested_color_missing` | `likely_same_design` | `shirt-ribbed-polo-white` | expected decision_label=similar_style, got likely_same_design<br>missing expected colors: ['black', 'grey', 'olive', 'white'] |
| `naive_oracle_top1` | `q1_shirt_white_blue_missing` | `requested_color_missing` | `confirmed_exact` | `shirt-ribbed-polo-white` | expected decision_label=similar_style, got confirmed_exact<br>missing expected colors: ['black', 'grey', 'olive', 'white']<br>expected requested_color=blue, got None |
| `metadata_baseline` | `q1_reference_saree_no_exact` | `reference_guard` | `confirmed_same_design_variant` | `hf-53759-puma-men-grey-t-shirt` | expected saree-jmd-lotus-red in primary/top-3, got hf-53759-puma-men-grey-t-shirt / ['hf-53759-puma-men-grey-t-shirt', 'hf-1855-inkfruit-mens-chain-reaction-t-shirt', 'pant-jeans-blue-32']<br>none of expected target ids appeared in primary/top-3: ['saree-jmd-lotus-red']<br>expected category signal Saree in hits |
| `naive_oracle_top1` | `q1_reference_saree_no_exact` | `reference_guard` | `confirmed_exact` | `saree-jmd-lotus-red` | forbidden decision_label=confirmed_exact |
| `metadata_baseline` | `q1_reference_saree_size_hedge` | `missing_fact_safety` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected saree-jmd-lotus-red in primary/top-3, got pant-jeans-blue-32 / ['pant-jeans-blue-32', 'shirt-oxford-blue-m', 'pant-cargo-olive-34']<br>expected category signal Saree in hits |
| `naive_oracle_top1` | `q1_reference_saree_size_hedge` | `missing_fact_safety` | `confirmed_exact` | `saree-jmd-lotus-red` | forbidden decision_label=confirmed_exact<br>expected requested_size=M, got None<br>expected answer to contain 'size' |
| `naive_oracle_top1` | `q1_bag_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-47957-murcia-women-blue-handbag` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_shoe_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-9204-puma-men-future-cat-remix-sf-black-casual-sh` | forbidden decision_label=confirmed_exact |
| `naive_oracle_top1` | `q1_cosmetic_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-56019-colorbar-soft-touch-show-stopper-copper-lips` | forbidden decision_label=confirmed_exact<br>expected category signal Cosmetics in hits |
| `naive_oracle_top1` | `q1_perfume_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-43967-dkny-women-red-delicious-perfume` | forbidden decision_label=confirmed_exact |
| `metadata_baseline` | `q1_three_piece_visual_category` | `similar_category_search` | `similar_style` | `hf-54924-do-u-speak-green-men-blue-shorts` | expected category signal Three Piece in hits |
| `naive_oracle_top1` | `q1_three_piece_visual_category` | `similar_category_search` | `confirmed_exact` | `hf-54588-sushilas-women-printed-green-kurta` | forbidden decision_label=confirmed_exact<br>expected category signal Three Piece in hits |
| `metadata_baseline` | `q1_pearl_necklace_no_shirt` | `cross_category_guard` | `confirmed_same_design_variant` | `hf-53759-puma-men-grey-t-shirt` | expected jewelry-pearl-necklace-white in primary/top-3, got hf-53759-puma-men-grey-t-shirt / ['hf-53759-puma-men-grey-t-shirt', 'hf-1855-inkfruit-mens-chain-reaction-t-shirt', 'pant-jeans-blue-32']<br>none of expected target ids appeared in primary/top-3: ['jewelry-pearl-necklace-white']<br>expected category signal Jewelry in hits |
| `naive_oracle_top1` | `q1_pearl_necklace_no_shirt` | `cross_category_guard` | `confirmed_exact` | `jewelry-pearl-necklace-white` | forbidden decision_label=confirmed_exact<br>expected category signal Jewelry in hits |
| `metadata_baseline` | `q1_pearl_earring_no_shirt` | `cross_category_guard` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected jewelry-pearl-earring-white in primary/top-3, got pant-jeans-blue-32 / ['pant-jeans-blue-32', 'shirt-oxford-blue-m', 'hf-54924-do-u-speak-green-men-blue-shorts']<br>none of expected target ids appeared in primary/top-3: ['jewelry-pearl-earring-white']<br>expected category signal Jewelry in hits |
| `naive_oracle_top1` | `q1_pearl_earring_no_shirt` | `cross_category_guard` | `confirmed_exact` | `jewelry-pearl-earring-white` | forbidden decision_label=confirmed_exact<br>expected category signal Jewelry in hits |
| `naive_oracle_top1` | `q1_watch_no_jewelry_confusion` | `cross_category_guard` | `confirmed_exact` | `hf-11188-carrera-men-dial-steel-finish-strap-silver-w` | forbidden decision_label=confirmed_exact |
| `metadata_baseline` | `q1_shirt_black_m_size_available` | `size_availability` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected decision_label=confirmed_exact, got confirmed_same_design_variant<br>expected shirt-ribbed-polo-black in primary/top-3, got pant-jeans-blue-32 / ['pant-jeans-blue-32', 'shirt-oxford-blue-m', 'pant-cargo-olive-34']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-black'] |
| `no_identity_ablation` | `q1_shirt_black_m_size_available` | `size_availability` | `likely_same_design` | `shirt-ribbed-polo-black` | expected decision_label=confirmed_exact, got likely_same_design |
| `naive_oracle_top1` | `q1_shirt_black_m_size_available` | `size_availability` | `confirmed_exact` | `shirt-ribbed-polo-black` | expected requested_size=M, got None |
| `metadata_baseline` | `q1_shirt_white_m_size_out_of_stock` | `size_availability` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected decision_label=confirmed_exact, got confirmed_same_design_variant<br>expected shirt-ribbed-polo-white in primary/top-3, got pant-jeans-blue-32 / ['pant-jeans-blue-32', 'shirt-oxford-blue-m', 'pant-cargo-olive-34']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-white'] |
| `no_identity_ablation` | `q1_shirt_white_m_size_out_of_stock` | `size_availability` | `likely_same_design` | `shirt-ribbed-polo-white` | expected decision_label=confirmed_exact, got likely_same_design |
| `naive_oracle_top1` | `q1_shirt_white_m_size_out_of_stock` | `size_availability` | `confirmed_exact` | `shirt-ribbed-polo-white` | expected requested_size=M, got None |
| `metadata_baseline` | `q1_shirt_olive_xxl_missing` | `size_availability` | `confirmed_same_design_variant` | `pant-jeans-blue-32` | expected decision_label=confirmed_exact, got confirmed_same_design_variant<br>expected shirt-ribbed-polo-olive in primary/top-3, got pant-jeans-blue-32 / ['pant-jeans-blue-32', 'shirt-oxford-blue-m', 'pant-cargo-olive-34']<br>none of expected target ids appeared in primary/top-3: ['shirt-ribbed-polo-olive'] |
| `no_identity_ablation` | `q1_shirt_olive_xxl_missing` | `size_availability` | `likely_same_design` | `shirt-ribbed-polo-olive` | expected decision_label=confirmed_exact, got likely_same_design |
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
.venv/bin/python scripts/run_q1_image_research_pass.py --engine auto --methods full_system metadata_baseline no_identity_ablation policy_oracle naive_oracle_top1
```
