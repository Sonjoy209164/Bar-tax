# TODO: Image Search Improvements With Current Demo Data

## Goal

Use the current 100-image demo/reference catalog to improve and test the image-search system without waiting for real shop product photos.

This file is intentionally **not** about proving production exact matching. With the current data, many images are `reference_photo`, so the bot should behave like this:

```text
Good: "closest match", "similar style", "same design only when catalog identity proves it"
Bad:  "exact same product ache" from reference/demo image similarity
```

The purpose now is to harden the pipeline, decision policy, UI, memory, evaluation, and debugging tools. Real product photos can come later.

## Current Data Can Prove

- [ ] Image upload flow works end to end.
- [ ] CLIP/image retrieval returns plausible visual candidates.
- [ ] Wrong-category matches are filtered or downgraded.
- [ ] Reference images do not create exact product claims.
- [ ] Product cards render image, name, price, stock, color, and confidence.
- [ ] Same-design logic works where `variant_group_id` / `design_id` exists.
- [ ] Follow-up memory works after an image search.
- [ ] The trace/debug UI shows each image-search stage.
- [ ] Evaluation tests catch regressions like pearl image matching a shirt.

## Current Data Cannot Prove

- [ ] Real Facebook screenshot accuracy.
- [ ] Real shop SKU exact matching.
- [ ] Actual stock/POS truth.
- [ ] Production pattern matching across messy customer photos.
- [ ] Perfect same-design detection without catalog identity.

## Phase 1: Catalog Identity Cleanup

- [ ] Audit every product for `design_id`.
  - Purpose: gives the bot a stable design identity beyond CLIP score.

- [ ] Audit every product for `variant_group_id` where same-design variants exist.
  - Purpose: lets the bot answer "same design onno color ache?"

- [ ] Add `color` and `color_family` to every visual product.
  - Purpose: allows color filtering and "available colors" answers.

- [ ] Add `category_key` consistently.
  - Purpose: prevents jewelry images from being answered as shirts, sarees, etc.

- [ ] Add `size_options` where relevant.
  - Purpose: supports follow-ups like "M size ache?"

- [ ] Keep `kind: "reference_photo"` and `is_reference: true` for demo images.
  - Purpose: prevents false exact-match claims.

## Phase 2: Decision Policy Hardening

- [ ] Keep exact-match claims blocked for reference images.
  - Purpose: current demo images are not proof of real SKU ownership.

- [ ] Prefer strongest visual match before expanding variant groups.
  - Purpose: prevents a weaker shirt hit from expanding into all shirt colors over a stronger pearl/jewelry hit.

- [ ] Add category outlier filtering.
  - Purpose: if top hit is jewelry, weak shirt/saree hits should not appear as useful recommendations.

- [ ] Require strong confidence before `same_design` expansion.
  - Purpose: weak visual similarity should not become "same design colors: black, grey, olive, white."

- [ ] Separate labels clearly:
  - `confirmed_exact`
  - `confirmed_same_design_variant`
  - `likely_same_design`
  - `similar_style`
  - `no_confident_match`

- [ ] Make customer wording match the label.
  - Purpose: confidence language must be honest.

## Phase 3: Test Cases With Current Catalog

- [ ] Upload `jewelry-pearl-necklace-white`.
  - Expected: primary is `jewelry-pearl-necklace-white`.
  - Expected: no ribbed polo family.
  - Expected: answer says similar/closest, not exact.

- [ ] Upload `jewelry-pearl-earring-white`.
  - Expected: primary is `jewelry-pearl-earring-white`.
  - Expected: no shirt same-design colors.

- [ ] Upload `shirt-ribbed-polo-black`.
  - Expected: black polo primary.
  - Expected: available colors include black, grey, olive, white.

- [ ] Upload black ribbed polo and ask `white color ache?`.
  - Expected: white ribbed polo returned as same-design variant.

- [ ] Upload white ribbed polo and ask `blue ache?`.
  - Expected: blue not available; show available colors.

- [ ] Upload a bag image.
  - Expected: bag category results.
  - Expected: no exact claim if image is reference/demo.

- [ ] Upload a lipstick/cosmetics image.
  - Expected: cosmetics category results.
  - Expected: no fashion clothing results unless score is very high.

- [ ] Upload an unrelated image.
  - Expected: `no_confident_match` or cautious similar-style answer.

## Phase 4: Evaluation Dataset

- [ ] Expand `evaluation/image_search_gold_set.jsonl`.
  - Purpose: make regression testing repeatable.

- [ ] Add at least 30 image cases from current demo catalog.
  - Suggested groups:
    - jewelry
    - saree
    - shirt
    - bag
    - shoes
    - cosmetics
    - watches
    - perfume

- [ ] Add expected fields per case:
  ```json
  {
    "case_id": "pearl_necklace_no_shirt",
    "image_path": "frontend/assets/demo_catalog/jewelry-pearl-necklace-white/primary.jpg",
    "query_text": "do you have this?",
    "expected_primary_product_id": "jewelry-pearl-necklace-white",
    "forbidden_product_ids": ["shirt-ribbed-polo-white"],
    "forbidden_decision_label": "confirmed_exact"
  }
  ```

- [ ] Add no-match cases.
  - Purpose: bot should abstain or be cautious when evidence is weak.

- [ ] Add same-design cases.
  - Purpose: protect the variant-group behavior.

- [ ] Add cross-category confusion cases.
  - Purpose: catch pearl-to-shirt, bag-to-saree, cosmetics-to-jewelry mistakes.

## Phase 5: Screenshot Robustness Without Real Shop Photos

- [ ] Create artificial screenshot variants from current images.
  - Purpose: simulate Facebook/WhatsApp screenshots.

- [ ] Generate test variants:
  - cropped product
  - product with white border
  - screenshot with text overlay
  - lower resolution
  - compressed JPG
  - multiple products in one image
  - dark product on dark background
  - white product on white background

- [ ] Save these under:
  ```text
  evaluation/image_queries/
  ```

- [ ] Add expected behavior for each screenshot variant.
  - Purpose: measure robustness before real customer images arrive.

## Phase 6: Preprocessing Improvements

- [ ] Add crop preview output.
  - Purpose: see what image area the matcher is actually using.

- [ ] Add simple border/UI trimming.
  - Purpose: Facebook screenshots include whitespace and UI.

- [ ] Add contrast normalization for very dark/white products.
  - Purpose: ribbed black and white clothing lose texture easily.

- [ ] Add detail/pattern crop support.
  - Purpose: pattern/design matching needs more than full-product shape.

- [ ] Store preprocessing artifacts:
  ```text
  data/inventory/image_cache/{image_id}/full.jpg
  data/inventory/image_cache/{image_id}/crop.jpg
  data/inventory/image_cache/{image_id}/gray.jpg
  data/inventory/image_cache/{image_id}/meta.json
  ```

## Phase 7: Visual Retrieval Improvements

- [ ] Keep CLIP baseline.
  - Purpose: broad visual similarity.

- [ ] Use grayscale/pattern channel for same-design detection.
  - Purpose: same design in different color should still match.

- [ ] Add color as a separate signal.
  - Purpose: do not let color dominate design identity.

- [ ] Compare top results from:
  - full visual embedding
  - grayscale/pattern embedding
  - text visual tags
  - category metadata

- [ ] Add score breakdown to every result.
  - Purpose: explain why a product was shown.

## Phase 8: UI Improvements

- [ ] Show match label badge clearly.
  - Examples:
    - Exact
    - Same design
    - Similar
    - Not confident

- [ ] Show why exact is not claimed.
  - Example:
    ```text
    Demo/reference image, so exact SKU cannot be confirmed.
    ```

- [ ] Add product cards with:
  - image
  - name
  - price
  - stock
  - color
  - size options
  - match label

- [ ] Add quick action chips:
  - `Other colors?`
  - `M size ache?`
  - `Price koto?`
  - `Show similar`
  - `Order this`

- [ ] Add a debug toggle for score breakdown.
  - Purpose: customer view stays clean; engineer view stays explainable.

## Phase 9: Memory Tests

- [ ] Upload black ribbed polo, then ask `white ache?`.
  - Expected: use previous image result and return white variant.

- [ ] Upload pearl necklace, then ask `price koto?`.
  - Expected: answer price for pearl necklace, not a new random product.

- [ ] Upload bag, then ask `aro color ache?`.
  - Expected: check same variant group if available; otherwise say no confirmed same-design colors.

- [ ] Ask a fresh product after image memory.
  - Example: `red saree ache?`
  - Expected: old image memory must not hijack the new query.

## Phase 10: Feedback And Correction Loop

- [ ] Save low-confidence image searches.
  - Purpose: find where the system is weak.

- [ ] Save wrong-result feedback.
  - Purpose: owner can correct mistakes.

- [ ] Add correction schema:
  ```json
  {
    "query_image_id": "upload_123",
    "wrong_product_id": "shirt-ribbed-polo-white",
    "correct_product_id": "jewelry-pearl-necklace-white",
    "correction_type": "similar",
    "notes": "pearl necklace was confused with white shirt"
  }
  ```

- [ ] Apply owner corrections during reranking.
  - Purpose: correction beats model score.

- [ ] Add correction tests.
  - Purpose: once fixed by owner, same image should not fail again.

## Phase 11: Commands To Run

- [ ] Syntax check:
  ```bash
  .venv/bin/python -m py_compile app/inventory/image_matcher.py app/inventory/clip_matcher.py app/services/inventory_service.py app/api/routes_inventory.py app/core/schemas.py
  node --check frontend/chat.js
  node --check frontend/trace.js
  ```

- [ ] Rebuild image index:
  ```bash
  .venv/bin/python scripts/reindex_image_embeddings.py --skip-embeddings --force
  ```

- [ ] Focused image tests:
  ```bash
  .venv/bin/python -m pytest tests/test_image_matching.py tests/test_image_search_ask.py -q
  ```

- [ ] Full test suite:
  ```bash
  .venv/bin/python -m pytest -q
  ```

- [ ] Run server:
  ```bash
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 4837
  ```

## Definition Of Done For Current Demo Data

- [ ] Pearl images never return ribbed polo as primary.
- [ ] Shirt images still return shirt variant colors correctly.
- [ ] Reference images never say `confirmed_exact`.
- [ ] Same-design claims only happen from strong identity evidence.
- [ ] Wrong-category weak hits are filtered from customer-facing results.
- [ ] Image index status returns `ready: true`.
- [ ] UI shows product cards and match labels clearly.
- [ ] Follow-up memory works after image upload.
- [ ] Evaluation dataset catches known bad cases.
- [ ] Full tests pass before demo.

## Strategic Rule

With current demo/reference data, the win is not "perfect exact image matching."

The win is:

```text
Clean pipeline
  -> honest confidence
  -> no absurd wrong-category claims
  -> strong same-design behavior where catalog identity exists
  -> repeatable tests
  -> ready for real shop photos later
```

