# TODO Next: Image Product Search + Reply Quality Development

## Mission

```text
Customer uploads a product screenshot
-> bot finds exact / same-design / similar catalog products
-> bot replies like a careful shop salesperson
```

The visual model is only the eye. The catalog is the truth.

## Status Legend

- [x] = already implemented in this branch
- [ ] = open work item

---

## Out Of Scope (still enforced)

- [x] Do not scrape Alibaba / commercial sites.
- [x] Do not search for more Kaggle datasets.
- [x] Do not replace the whole app architecture.
- [x] Do not do full model fine-tuning now.
- [x] Do not run full final eval here; testing happens on the main machine.
- [x] Do not mark reference/demo images as real product photos.

## Development Constraints

- [x] Changes scoped to image product search and reply quality.
- [x] APIs preserved; only backward-compatible additions to schemas.
- [x] exact / same-design / similar / no-match labels are explicit.
- [x] Prefer small helpers over rewrites.
- [x] Reference images cannot produce `confirmed_exact` (locked by tests).

---

## Phase 1: Catalog Identity Helpers

- [ ] New module `app/inventory/catalog_identity.py` consolidating identity reads.
- [ ] Helper `image_can_confirm_exact(image_or_product) -> bool`
- [ ] Helper `product_variant_group(product) -> str | None`
- [ ] Helper `product_design_id(product) -> str | None`
- [ ] Helper `product_size_stock(product) -> dict[str, int]`
- [x] Reference vs product-photo check is enforced (currently inside `_hit_decision_label` — needs extraction).
- [x] Variant group / design lookup logic exists ad-hoc — needs consolidation.

Definition of done:
```text
Image matcher reads identity from one helper module, not scattered attrs.get() calls.
```

---

## Phase 2: Multi-Signal Scoring

- [x] `score_breakdown` object on every image match candidate.
- [x] Color is a separate filter signal in `finalize_image_search`.
- [x] "Same design + requested color" first matches design then filters by color.
- [x] Category outlier pruning (`_prune_visual_outliers`).
- [x] Reference penalty (reference images can't earn `confirmed_exact`).
- [x] Raw visual score visible in trace; never claimed in customer copy.
- [ ] Add explicit named components to `score_breakdown`: `category_score`, `color_score`, `metadata_score`, `stock_score`, `final_score`.
- [ ] Compute a single rankable `final_score` and put it in trace.

Definition of done:
```text
The trace can explain why a product won via named score components, not one opaque cosine.
```

---

## Phase 3: Decision Policy

- [x] Labels: `confirmed_exact`, `confirmed_same_design_variant`, `likely_same_design`, `similar_style`, `no_confident_match`.
- [x] `confirmed_exact` requires `product_photo` + non-reference + high score (Margin gate + channel agreement also enforced).
- [x] `confirmed_same_design_variant` requires shared `variant_group_id`.
- [x] Reference photo cannot yield `confirmed_exact` (test-locked).
- [x] Customer wording matches decision label.
- [ ] Make "category must match" and "product must be active" explicit checks for `confirmed_exact` (currently implicit via pruning + filters).

---

## Phase 4: Same-Design Variant Resolver

- [x] `_same_design_items(catalog, group_key)` returns siblings.
- [x] Requested-color extraction via `infer_requested_color` (en/bn/banglish).
- [x] In-stock requested color → `confirmed_same_design_variant`.
- [x] Out-of-stock requested color → "currently nei" + available colors.
- [x] Requested color not in variant group → "ei color nai" + available colors.
- [ ] Promote `_same_design_items` to a public helper `find_variant_siblings` and re-use it in the conversation memory follow-up path.

---

## Phase 5: Business Fact Check

- [x] Final answer pulls price from product record.
- [x] Final answer pulls stock from product record.
- [x] Inactive products are not promoted as primary.
- [x] Out-of-stock not primary unless user asked availability of an exact match.
- [ ] **Add `size_stock: dict[str, int]` schema field** and prefer it when answering "M size ache?".
- [ ] Populate `size_stock` for the four ribbed-polo shirts (catalog has only `size: "M, L, XL"` strings today).
- [ ] When only total stock is known: answer carefully ("size-wise stock catalog e clear na").

---

## Phase 6: Natural Image Answer Layer

- [x] Templates per decision label in `_build_decision_answer` (en/bn/banglish).
- [x] Reference-image reason note appended when exact is withheld.
- [x] Direct seller-style answer (not "Found 5 results").
- [ ] Per-label **next_best_question** (e.g. `confirmed_same_design_variant` → "M size check korbo?"; `similar_style` → "Cheaper option dekhabo?").
- [ ] Surface `next_best_question` on `InventoryAskResponse.follow_up_question` for the image-search path.

---

## Phase 7: Product Cards

- [x] Card rendering: image, name, price, stock, color, decision badge.
- [x] Badge labels mapped from decision label.
- [x] Raw technical fields hidden by default.
- [ ] Show **size** (or size_stock summary) on the card.
- [ ] Show match-confidence % when debug mode is enabled.
- [ ] **Quick action chips** under image results: `Other colors?`, `M size ache?`, `Price koto?`, `Show similar`, `Order this`.

---

## Phase 8: Memory For Image Follow-Ups

- [x] `conversation_state.active_slots` stores `variant_group_id`, `design_id`, `color`, `category_key` after an image search.
- [x] `last_primary_product_id` + `last_shown_product_ids` recorded.
- [x] Text-only follow-ups ("white ache?", "M size ache?", "ar ki color ache?") resolve against the previous variant group via `_try_image_followup_ask`.
- [x] Naming a new product type ("red saree ache?") does NOT hijack memory.
- [ ] Record `last_image_match_decision_label` explicitly (so clarification logic can react to weak prior matches).
- [ ] When the previous image match was `no_confident_match`, ask one clarification before answering follow-ups.

---

## Phase 9: API Response Shape

- [x] `ImageSearchResponse` has: `decision_label`, `primary_product_id`, `hits`, `same_design_variant_ids`, `similar_product_ids`, `available_colors`, `requested_color`, `score_breakdown`, `query_image_id`, `trace_id`.
- [x] `/inventory/ask` answers image uploads as `answer_engine="image_search"` with the same data on a normal `InventoryAskResponse`.
- [x] Backward compatible — no field removals.
- [ ] (Optional) Mirror `same_design_variant_ids` / `similar_product_ids` on `InventoryAskResponse` so the chat UI need not branch by endpoint.

---

## Phase 10: Trace And Debug Visibility

- [x] Image-search trace stage saved in `_save_image_search_trace`.
- [x] Trace panel rendered in `frontend/trace.html` (3b. Image Search Pipeline) + `frontend/trace.js`.
- [x] Decision label, requested/available colors, same-design variants, score breakdown, per-hit reasons all in trace.
- [x] `embedding_metadata()` versions every embedding.
- [ ] Show a ranked candidate table (one row per pre-pruning hit) in the trace panel.
- [ ] Show the variant-sibling lookup result as a discrete trace stage.

---

## Phase 11: Development Evaluation Fixtures

- [x] `evaluation/image_search_gold_set.jsonl` — 11 cases now (4 shirt + 1 saree-reference + 3 HF category + 2 pearl cross-category + 1 watch).
- [x] `scripts/run_image_search_eval.py` lightweight, deterministic; supports `forbidden_decision_label`, `forbidden_product_ids`, `expected_same_design_variant_ids`, `expected_available_colors`, `expected_category`.
- [x] In-process decision-policy regression gate (`test_image_search_gold_set_decision_policy`).
- [ ] Expand to 30+ cases: more no-match / cross-category-confusion / requested-color-unavailable / cropped-screenshot cases.
- [ ] Add a few cases that explicitly target `must_not_claim_exact_if_reference`.

---

## Phase 12: Guardrail Checklist (regression target)

- [x] Reference images cannot create `confirmed_exact`.
- [x] Cross-category weak hits do not outrank strong same-category hits (pearl vs shirt locked by tests).
- [x] Same-design color answers use `variant_group_id`, not visual score alone.
- [x] Stock and price come from catalog facts.
- [x] Customer reply is natural and short.
- [x] Product cards show match label.
- [x] Follow-up questions can use the last image match.
- [x] Debug trace explains the decision.

---

## Important Files

Primary backend: `app/inventory/image_matcher.py`, `app/inventory/clip_matcher.py`, `app/services/inventory_service.py`, `app/api/routes_inventory.py`, `app/core/schemas.py`.
Identity helpers (new): `app/inventory/catalog_identity.py`.
Memory: `app/inventory/memory.py`, `app/inventory/conversation_state.py`.
Frontend: `frontend/chat.{html,js,css}`, `frontend/trace.{html,js}`.
Data + eval: `data/inventory/catalog.jsonl`, `data/inventory/image_index.jsonl`, `evaluation/image_search_gold_set.jsonl`.

## Implementation order for this round

1. Phase 1 — `catalog_identity.py` (foundation; cheap)
2. Phase 5 — `size_stock` schema field + shirt data + answer logic (real reply-quality lift for size questions)
3. Phase 6 — `next_best_question` per decision label
4. Phase 7 — quick action chips + size on card
5. Phase 11 — expand gold set toward 30 cases (low-priority; can be partial)
6. Tests + full image-search suite run.
