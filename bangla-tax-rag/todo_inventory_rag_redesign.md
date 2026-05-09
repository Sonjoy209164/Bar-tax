# Inventory RAG Redesign Todo

Generated from `results/inventory_eval/human_friendly_qa_run_20260507_114542_audit.md`.

## Goal

Make the system reliable for human shopping and inventory conversations, not just technically searchable.

## Priority Checklist

- [x] Add hard constraint gating before final recommendation: product type, wired/wireless, USB/XLR, budget, in-stock, category, and explicit 'do not recommend' rules must filter or heavily demote candidates.
- [x] Redesign abstention logic so valid candidates are not rejected because secondary inferred specs are missing. A product that satisfies catalog-level constraints should not be blocked by unrelated required specs.
- [x] Create a bundle/planner answer mode that intentionally selects multiple complementary products, computes total price, and explains each item's role.
- [x] Create a ranking answer mode for 'top N' questions that always returns the requested number when enough candidates exist.
- [ ] Add requested-field coverage checks: if the user asks for price, stock, specs, total cost, or why-fit, the final answer must include those fields.
- [x] Fix verifier/spec mapping so metadata-derived fields like `anc_support`, `gps_support`, RAM, storage, and water resistance are read consistently from catalog attributes and metadata.
- [x] Rework reranking weights: exact product type and structured spec fit should outrank generic semantic similarity and low price.
- [ ] Add per-intent scoring profiles: audio calls, creator/podcast, outdoor wearables, office productivity, storage, networking, mobile accessories, restock planning, and abstention.
- [x] Separate retrieval recall from recommendation eligibility: keep broad Elasticsearch recall, then run a deterministic eligibility/rerank layer before answer generation.
- [x] Make alternatives policy-aware: alternatives can be shown only when they respect the user's hard constraints or are clearly labeled as tradeoffs.
- [ ] Add answer-plan validation against the human-friendly QA set and fail builds when hard constraints regress.

## Evaluation Harness

- [ ] Convert `evaluation/inventory_human_friendly_qa_set.md` into machine-readable JSONL with fields for endpoint, expected products, forbidden products, required facts, and abstention expectation.
- [ ] Add a repeatable eval runner command that records raw responses, case verdicts, and trace IDs.
- [ ] Add UI smoke coverage for the same cases, especially bundles and top-N business questions.
- [ ] Track pass/partial/fail over time in `results/inventory_eval/`.

## Fashion Retail Generalization

- [x] Stop designing around a fixed question list; use retail primitives instead: category, design family, color, size, price, stock, occasion, fabric, work type, and compatibility.
- [x] Add a generalized fashion-retail structured layer before generic RAG.
- [x] Support same-design color variant checks via `design_id`.
- [x] Support exact size availability checks before semantic ranking.
- [x] Support fashion search across sarees, blouses, panjabi/kurta, bags, jewelry, accessories, fabric, occasion, and budget.
- [x] Support accessory matching through `compatible_design_ids` and `compatible_colors`.
- [x] Keep non-fashion queries on the existing generic inventory pipeline.
- [ ] Expand sample catalog with Aarong-style bags, jewelry, panjabi, kurti, three-piece, dupatta, and mixed-size products.
- [x] Add Bangla/Banglish aliases beyond the current romanized terms.
- [x] Preserve Bangla text during fashion query normalization instead of stripping it.
- [x] Support Bangla numerals in size and budget questions.
- [x] Localize deterministic fashion answers for Bangla/Banglish customer messages.
- [ ] Add machine-readable fashion QA regression set and run it in CI.

## Current Failure Snapshot

- `fail`: 29
- `pass`: 13
- `partial`: 8
- `lead_ranking`: 20
- `false_abstention`: 20
- `verifier_flag`: 17
- `retrieval_or_ranking`: 15
- `bundle_composition`: 11
- `fact_coverage`: 8
- `abstention_guardrail`: 2
- `constraint_soft_violation`: 1
- `top_n_completeness`: 1

## Non-Passing Cases

- [ ] Q04 `Support Team Headset`: fail - Did not surface any expected product: audio-clairvoice-headset
- [ ] Q06 `XLR Creator Microphone`: partial - Lead product was audio-clairvoice-headset, expected one of: audio-streamcore-xlr
- [ ] Q07 `Meeting Room Speakerphone`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q09 `Travel Laptop Under $1000`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q10 `Manager Laptop With More Power`: partial - Lead product was laptop-aurora-13-air, expected one of: laptop-nimbus-14
- [ ] Q11 `Creator Laptop`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q12 `Gaming Monitor`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q13 `Office QHD Monitor`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q15 `Triple Display Dock`: fail - Did not surface any expected product: dock-hub-4k
- [ ] Q18 `Outdoor Smartwatch Under $250`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q19 `Premium Adventure Watch`: fail - Did not surface any expected product: watch-summit-x
- [ ] Q20 `Budget Fitness Tracker`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q22 `Midrange OLED Phone`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q23 `Premium Camera Phone`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q24 `Travel Charging Bundle`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q25 `NovaCore Protection Cross-Sell`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q27 `Midrange Ergonomic Chair`: fail - Did not surface any expected product: chair-lumbarflex-air
- [ ] Q28 `Standing Desk`: partial - Lead product was lamp-lumenleaf-task, expected one of: desk-flexispan-120
- [ ] Q29 `Secure File Storage`: fail - Did not surface any expected product: cabinet-filevault-3
- [ ] Q30 `Desk Planning Setup`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q31 `Small Home Wi-Fi`: fail - Did not surface any expected product: net-skyroute-ax1800
- [ ] Q32 `Bigger Home Coverage`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q33 `Travel Hotspot`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q35 `Desktop Backup Drive`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q36 `Camera or Tablet microSD`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q37 `Auralite Exact Lookup`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q39 `TrailMark vs PulseLine Comparison`: partial - Bundle/multi-product answer missed expected products: watch-pulseline-lite
- [ ] Q40 `Remote Meeting Kit`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q41 `Laptop Desk Bundle Around $1500`: partial - Bundle/multi-product answer missed expected products: monitor-visionedge-27, dock-hub-4k, acc-viewstand-fold
- [ ] Q42 `Creator Podcast Bundle`: fail - Did not surface any expected product: seed-audio-004, webcam-clearframe-4k, lamp-lumenleaf-task
- [ ] Q43 `Top Restock Ranking`: partial - Bundle/multi-product answer missed expected products: audio-streamcore-xlr, watch-trailmark-pro
- [ ] Q44 `Stockout Risk`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
- [ ] Q45 `High-Margin Low-Stock Review`: partial - Bundle/multi-product answer missed expected products: watch-trailmark-pro
- [ ] Q46 `No Refrigerators`: fail - Should have abstained or clearly said no reliable catalog match, but returned a product recommendation.
- [ ] Q47 `Impossible Gaming Laptop`: partial - Verifier flagged issues: Primary recommendation CarryShield 15 Laptop Sleeve is in category Accessories, not the required computing category.; Primary recommendation CarryShield 15 Laptop Sleeve is missing the required spec ram_gb.; Primary recommendation CarryShield 15 Laptop Sleeve is missing the required spec storage_gb.
- [ ] Q48 `Unknown SKU or Missing Product`: fail - Should have abstained or clearly said no reliable catalog match, but returned a product recommendation.
- [ ] Q50 `Casual Small Talk With Inventory Handoff`: fail - False abstention: the eval set has a valid catalog answer, but the system refused.
