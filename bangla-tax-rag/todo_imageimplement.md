# TODO: Image Search Implementation Architecture

## Product Goal

Design an image-aware inventory chatbot for a real boutique/fashion shop.

The business use case is simple:

```text
A customer sees a product on Facebook, Instagram, WhatsApp, or another page.
They take a screenshot.
They send that screenshot to the shop chatbot.
The bot checks the shop's own catalog and replies like a trained salesperson.
```

The bot must answer questions such as:

- [ ] "Ei same design ta ache?"
- [ ] "Same design blue/black/white color e ache?"
- [ ] "Eta available?"
- [ ] "M/L/XL size ache?"
- [ ] "Exact eta na thakle similar dekhan."
- [ ] "Price koto?"
- [ ] "Eta diye ki styling hobe?"
- [ ] "Order korte parbo?"

The system is being designed first for one shop with real product photos and real stock data. Later, the same architecture can scale to many small online shops.

## Core Outcome

Make the bot handle customer screenshots like a real shop salesperson:

```text
Customer uploads screenshot
  -> bot finds exact same product if available
  -> if exact product is not available, bot finds same design in other colors
  -> if same design is not available, bot recommends nearest alternatives
  -> bot always grounds final answer in shop catalog, stock, price, and product facts
```

This is not only a CLIP/image-search feature. It is a product-identity system. The visual model is the eye; the catalog is the truth.

## Strategic Design Rule

- [ ] Never say "same product" only because CLIP score is high.
  - Purpose: CLIP can confuse similar textures, colors, poses, and categories.
  - Correct rule: exact/same-design claims require `product_id`, `variant_group_id`, `design_id`, or owner-confirmed mapping.

- [ ] Separate these four decisions:
  - `exact_product_match`: same SKU/product.
  - `same_design_variant`: same design/pattern, different color or size.
  - `similar_style`: visually close but not confirmed same design.
  - `no_confident_match`: not enough evidence.
  - Purpose: prevents false confidence and makes the bot trustworthy.

- [ ] Use shop-owned images for production.
  - Purpose: internet/reference/Kaggle images can test the pipeline, but cannot confirm the shop has the product.
  - Current warning: existing catalog images are demo/reference images, not actual SKU photos.

## Target Architecture

```text
Shop Product Data
  -> Catalog JSONL / POS Sync
  -> Product Normalizer
  -> Image Asset Store
  -> Image Preprocessor
  -> Visual Feature Extractors
  -> Image Vector Index
  -> Screenshot Query Processor
  -> Candidate Retrieval
  -> Variant/Design Resolver
  -> Business Fact Check
  -> Decision Policy
  -> Natural Answer + Product Cards
  -> Feedback / Owner Correction
```

## Phase 1: Catalog Identity Foundation

- [ ] Add `variant_group_id` to products.
  - Purpose: groups the same design across colors/sizes.
  - Example: black, olive, white, and grey ribbed polo all share `variant_group_id = "ribbed-open-collar-knit-polo"`.
  - Target file: `data/inventory/catalog.jsonl`.
  - Schema target: `app/core/schemas.py`.

- [ ] Add `design_id` as a required or strongly recommended attribute.
  - Purpose: identifies the pattern/design independent of color.
  - Example: `attributes.design_id = "vertical-ribbed-open-collar-knit"`.

- [ ] Add `color` and `color_family` for every visual product.
  - Purpose: allows the bot to answer "same design in blue/black/white ache?"
  - Example: `color = "olive"`, `color_family = "green"`.

- [ ] Add `size_options` or variant-level size stock.
  - Purpose: screenshot matching often leads to follow-up: "M size ache?"
  - Better design: each variant has its own stock by size.

- [ ] Add `pattern_type`, `neckline`, `sleeve`, `fabric`, and `fit` where relevant.
  - Purpose: gives the decision layer structured clues beyond the visual model.
  - Example for shirt:
    - `pattern_type = "vertical ribbed"`
    - `neckline = "open collar"`
    - `sleeve = "half sleeve"`
    - `fabric = "knit"`
    - `fit = "regular"`

- [ ] Add `image_truth_level` or derive it from `images[].kind`.
  - Purpose: distinguish real shop photo from reference/demo photo.
  - Production-safe levels:
    - `product_photo`: shop-owned exact item photo.
    - `supplier_photo`: authorized supplier photo.
    - `reference_photo`: not exact SKU, only demo/reference.
    - `generated`: synthetic visual, never exact proof.

- [ ] Create a catalog audit that fails products missing image identity fields.
  - Purpose: no visual search system can be reliable if catalog identity is weak.
  - Target file: `app/inventory/catalog_audit.py`.
  - Test target: `tests/test_catalog_audit.py`.

## Phase 2: Image Asset Storage

- [ ] Store real product images inside a controlled folder.
  - Purpose: avoid broken URLs and slow remote image fetching.
  - Suggested path:
    - `data/inventory/images/{product_id}/primary.jpg`
    - `data/inventory/images/{product_id}/detail_1.jpg`
    - `data/inventory/images/{product_id}/variant_side.jpg`

- [ ] Keep `images[].local_path` for shop-owned images.
  - Purpose: local images are stable and fast for embedding.
  - Target schema already exists: `InventoryImageAsset.local_path`.

- [ ] Use `images[].role` correctly.
  - Purpose: different images help different matching tasks.
  - Recommended roles:
    - `primary`: full product view.
    - `alternate`: side/angle/model photo.
    - `detail`: close crop of pattern, embroidery, rib, print, border, texture.
    - `reference`: non-SKU reference only.

- [ ] Add at least 2 images per important product.
  - Purpose: one image is fragile; different screenshots may crop, rotate, or compress the product.
  - Minimum:
    - 1 full product photo.
    - 1 detail/pattern photo.

- [ ] Add an image manifest.
  - Purpose: make image source, ownership, and license auditable.
  - Existing file to extend: `data/inventory/catalog_image_sources.json`.

- [ ] Reject production "exact match" if image is `is_reference = true`.
  - Purpose: reference images are not the actual product.
  - Target logic: image match decision policy.

## Phase 3: Product Image Ingestion Pipeline

- [ ] Build a command to import product photos.
  - Purpose: daily new product update should be simple.
  - Suggested command:
    - `.venv/bin/python scripts/import_product_images.py --catalog data/inventory/catalog.jsonl --image-root data/inventory/images`

- [ ] Validate image files on import.
  - Purpose: catch missing, corrupt, tiny, or unsupported files early.
  - Checks:
    - file exists
    - readable by Pillow
    - width/height above minimum
    - product_id exists in catalog
    - image role is valid

- [ ] Generate stable `image_id`.
  - Purpose: allows embeddings and corrections to reference exact image assets.
  - Example: `shirt-ribbed-polo-black-primary-1`.

- [ ] Save image dimensions.
  - Purpose: helps debug bad screenshots and image quality.
  - Schema fields already exist: `width`, `height`.

- [ ] Add dry-run mode.
  - Purpose: safe import before modifying catalog.
  - Example:
    - `.venv/bin/python scripts/import_product_images.py --dry-run`

- [ ] Add backup before catalog rewrite.
  - Purpose: catalog mistakes are expensive.
  - Suggested path:
    - `data/inventory/backups/catalog_YYYYMMDD_HHMMSS.jsonl`.

## Phase 4: Image Preprocessing

- [ ] Normalize all product images before embedding.
  - Purpose: embeddings should not change because of huge image size or color mode.
  - Steps:
    - convert to RGB
    - resize with aspect ratio
    - remove EXIF rotation
    - save normalized copy or cache

- [ ] Add product/background crop.
  - Purpose: screenshots often include Facebook UI, borders, text, and background.
  - MVP approach: center crop + simple background trimming.
  - Better approach: object detection/segmentation.

- [ ] Create both full-image and detail-image embeddings.
  - Purpose:
    - full image helps category/shape.
    - detail crop helps pattern/design.

- [ ] Create color-invariant version.
  - Purpose: same design in different color should still match.
  - MVP: grayscale image embedding or texture descriptor.
  - Better: DINOv2/SigLIP embedding on grayscale/detail crop.

- [ ] Extract dominant color separately.
  - Purpose: color should be a separate signal, not mixed into design identity.
  - Important: if user asks "same design in blue", the system should first match design, then filter variants by color.

- [ ] Save preprocessing outputs.
  - Purpose: debugging and repeatable indexing.
  - Suggested path:
    - `data/inventory/image_cache/{image_id}/full.jpg`
    - `data/inventory/image_cache/{image_id}/crop.jpg`
    - `data/inventory/image_cache/{image_id}/gray.jpg`
    - `data/inventory/image_cache/{image_id}/meta.json`

## Phase 5: Visual Feature Extractors

- [ ] Keep CLIP as the baseline visual model.
  - Purpose: strong zero-shot image similarity, already partly implemented.
  - Existing file: `app/inventory/clip_matcher.py`.

- [ ] Add a design/pattern embedding channel.
  - Purpose: CLIP often overweights object category and color; pattern matching needs texture/design sensitivity.
  - MVP options:
    - grayscale CLIP embedding
    - edge/texture descriptor
  - Better options:
    - DINOv2 image embedding
    - FashionCLIP/SigLIP for fashion-specific similarity

- [ ] Add a color feature channel.
  - Purpose: answer color availability independently.
  - Output example:
    - `dominant_color = "black"`
    - `color_family = "black"`
    - `color_confidence = 0.91`

- [ ] Add optional text embedding from visual tags.
  - Purpose: hybrid search should still work if image model fails.
  - Text example:
    - `"men shirt ribbed knit open collar half sleeve black"`

- [ ] Version every embedding.
  - Purpose: if model changes, old vectors must be rebuilt.
  - Required fields:
    - `model_name`
    - `model_version`
    - `preprocess_version`
    - `embedding_created_at`

- [ ] Do not fetch remote images during customer query.
  - Purpose: query latency becomes slow and unstable.
  - Correct design: precompute embeddings in background when catalog changes.

## Phase 6: Vector Index Design

- [ ] Store image embeddings in a vector index.
  - Purpose: fast nearest-neighbor image search.
  - Current repo has Elasticsearch vector support.
  - Existing file: `app/retrieval/elasticsearch_store.py`.

- [ ] Index by image asset, not only product.
  - Purpose: one product can have primary/detail/alternate images.
  - Recommended document ID:
    - `{namespace}::{product_id}::{image_id}::{embedding_type}`

- [ ] Use namespaces.
  - Purpose: future multi-shop product must isolate each shop.
  - Current one-shop namespace can be:
    - `default_shop`.

- [ ] Store structured metadata with each vector.
  - Purpose: filter and rerank after vector search.
  - Required metadata:
    - `product_id`
    - `sku`
    - `variant_group_id`
    - `design_id`
    - `category`
    - `color`
    - `color_family`
    - `stock`
    - `price`
    - `image_id`
    - `image_role`
    - `image_kind`
    - `is_reference`
    - `embedding_type`

- [ ] Use separate embedding types.
  - Purpose: combine broad and detailed visual signals.
  - Recommended values:
    - `full_visual`
    - `pattern_visual`
    - `text_visual_tags`
    - `color_feature`

- [ ] Add reindex command.
  - Purpose: after catalog/image/model change, rebuild cleanly.
  - Suggested command:
    - `.venv/bin/python scripts/reindex_image_embeddings.py --provider elasticsearch --force`

- [ ] Add index status endpoint.
  - Purpose: prove whether image search index is ready.
  - Suggested endpoint:
    - `GET /inventory/image-index/status`

## Phase 7: Customer Screenshot Query Flow

- [ ] Accept image upload in chat API.
  - Purpose: customer sends screenshot from Facebook.
  - Existing likely route: image search route in `app/api/routes_inventory.py`.

- [ ] Accept optional text with image.
  - Purpose: user can say "ei same design ta blue color e ache?"
  - Query input includes:
    - image
    - text
    - session_id
    - language
    - desired color/size/budget if mentioned

- [ ] Preprocess query image.
  - Purpose: remove Facebook UI, crop product area, normalize image.
  - Same pipeline as catalog preprocessing.

- [ ] Extract query slots.
  - Purpose: text controls the search goal.
  - Examples:
    - "same design blue" -> design match + color filter blue.
    - "eta ache?" -> exact/similar availability.
    - "similar dekhan" -> similar style search.
    - "M size ache?" -> resolve previous product + size check.

- [ ] Run visual retrieval.
  - Purpose: get candidate images/products.
  - Retrieval channels:
    - full visual vector search
    - pattern/detail vector search
    - text tag search
    - optional color filter

- [ ] Resolve product candidates.
  - Purpose: multiple image hits may map to the same product.
  - Output should aggregate scores by `product_id`.

- [ ] Resolve variant group.
  - Purpose: answer same-design/different-color questions.
  - If top product has `variant_group_id`, fetch all products in that group.

- [ ] Apply business facts.
  - Purpose: availability comes from catalog/POS, not visual model.
  - Check:
    - stock
    - size stock
    - price
    - status
    - policy restrictions

## Phase 8: Ranking And Decision Policy

- [ ] Build a score breakdown, not one opaque score.
  - Purpose: easier debugging and safer decisions.
  - Suggested score fields:
    - `full_visual_score`
    - `pattern_score`
    - `color_score`
    - `category_score`
    - `variant_group_score`
    - `stock_score`
    - `metadata_score`
    - `final_score`

- [ ] Prefer exact catalog identity over raw visual score.
  - Purpose: confirmed `variant_group_id` is stronger than CLIP similarity.
  - Ranking order:
    - same `product_id`
    - same `variant_group_id`
    - same `design_id`
    - high pattern score
    - high visual score
    - same category/fabric/style

- [ ] Add exact match threshold.
  - Purpose: prevent weak visual hits from becoming exact claims.
  - Rule:
    - exact product only if visual score is very high and image is `product_photo`, or owner mapping exists.

- [ ] Add same-design threshold.
  - Purpose: same design across colors must be stricter than general similarity.
  - Rule:
    - confirmed if `variant_group_id` matches.
    - likely if pattern score high, shape/category match, and color ignored.

- [ ] Add similar-style threshold.
  - Purpose: useful recommendation even if exact/same design not found.
  - Rule:
    - category + style/pattern closeness, but no exact claim.

- [ ] Add no-match threshold.
  - Purpose: honest failure is better than wrong confidence.
  - Rule:
    - if top score below threshold or evidence is reference-only, say not confident.

- [ ] Return decision labels.
  - Purpose: UI and answer can explain confidence.
  - Labels:
    - `confirmed_exact`
    - `confirmed_same_design_variant`
    - `likely_same_design`
    - `similar_style`
    - `no_confident_match`

## Phase 9: Answer Generation Rules

- [ ] Use different answer templates for each decision label.
  - Purpose: language must match confidence.

- [ ] Exact product answer template.
  - Purpose: direct seller-like answer.
  - Example:
    - "Yes, this looks like our Ribbed Open-Collar Knit Polo in black. It is available. We also have the same design in olive, white, and grey."

- [ ] Same design variant answer template.
  - Purpose: answer the common customer question: same design different color.
  - Example:
    - "Same design ta ache. Black stock e ache, olive ache, white ache. Blue color currently catalog e dekhacche na."

- [ ] Similar style answer template.
  - Purpose: recommend like a salesperson without overclaiming.
  - Example:
    - "Exact same design confirm korte parchi na, but close ribbed open-collar options ache. Ei 3 ta nearest."

- [ ] No confident match answer template.
  - Purpose: safe fallback.
  - Example:
    - "Ei screenshot er exact product catalog e confident bhabe pachchi na. Apni color/size bolle ami similar options dekhate pari."

- [ ] Always include product cards.
  - Purpose: visual commerce needs visual confirmation.
  - Product card should show:
    - image
    - name
    - price
    - stock
    - color
    - size if available
    - match label

- [ ] Do not expose raw model names to customers.
  - Purpose: customers care about product availability, not CLIP or vector scores.

- [ ] Keep debug score visible only in observer/dev UI.
  - Purpose: engineers need traceability; customers need clean answers.

## Phase 10: UI Implementation

- [ ] Improve chat upload flow.
  - Purpose: user should easily upload Facebook screenshot.
  - Existing UI file: `frontend/chat.html`, `frontend/chat.js`, `frontend/chat.css`.

- [ ] Show image preview before sending.
  - Purpose: user confirms correct screenshot.

- [ ] Allow text + image together.
  - Purpose: "same design blue ache?" needs both.

- [ ] Render product image cards.
  - Purpose: customer visually verifies the match.
  - Existing support partly added in `frontend/chat.js`.

- [ ] Add match label badge.
  - Purpose: clearly separate exact/same-design/similar.
  - Example badges:
    - `Exact`
    - `Same design`
    - `Similar`
    - `Not confident`

- [ ] Add quick action chips after image result.
  - Purpose: natural next steps.
  - Examples:
    - "Other colors?"
    - "M size ache?"
    - "Price?"
    - "Order this"
    - "Show similar"

- [ ] Add debug trace panel for image search.
  - Purpose: observe every stage while testing.
  - Existing trace UI: `frontend/trace.html`, `frontend/trace.js`.

## Phase 11: API And Service Wiring

- [ ] Add a dedicated request/response schema for image search.
  - Purpose: avoid mixing visual fields into normal chat loosely.
  - Target file: `app/core/schemas.py`.
  - Suggested response fields:
    - `decision_label`
    - `query_image_id`
    - `matched_products`
    - `same_design_variants`
    - `similar_products`
    - `score_breakdown`
    - `evidence`
    - `final_answer`

- [ ] Add or strengthen `/inventory/image-search`.
  - Purpose: standalone image matching endpoint.
  - Target file: `app/api/routes_inventory.py`.

- [ ] Integrate image search into normal `/inventory/ask`.
  - Purpose: one customer chat flow.
  - Target file: `app/services/inventory_service.py`.

- [ ] Make memory work with image matches.
  - Purpose: follow-up questions need previous image result.
  - Example:
    - User: uploads black shirt.
    - Bot: shows ribbed polo.
    - User: "white ache?"
    - Bot: resolves "white" against previous `variant_group_id`.

- [ ] Store last focused product and variant group in conversation state.
  - Purpose: reliable follow-up behavior.
  - Existing files:
    - `app/inventory/memory.py`
    - `app/inventory/conversation_state.py`

## Phase 12: Feedback And Owner Correction

- [ ] Save failed image searches.
  - Purpose: improve the system from real customer misses.
  - Suggested path:
    - `data/feedback/image_search_failures.jsonl`.

- [ ] Save low-confidence searches.
  - Purpose: discover catalog/photo gaps.

- [ ] Add owner correction record.
  - Purpose: shop owner can say "this screenshot should match product X."
  - Suggested schema:
    ```json
    {
      "query_image_id": "upload_123",
      "wrong_product_id": "p_old",
      "correct_product_id": "p_new",
      "correction_type": "exact_product|same_design|similar|no_match",
      "notes": "same ribbed design, different color",
      "created_at": "..."
    }
    ```

- [ ] Use corrections during reranking.
  - Purpose: owner-confirmed mapping beats model score.

- [ ] Create correction review UI later.
  - Purpose: production shops need non-technical correction workflow.

## Phase 13: Evaluation Set

- [ ] Build a small gold dataset for one shop.
  - Purpose: know whether changes improve or break matching.
  - Suggested path:
    - `evaluation/image_search_gold_set.jsonl`.

- [ ] Include exact product cases.
  - Purpose: same screenshot/product should rank first.

- [ ] Include same-design different-color cases.
  - Purpose: the core business use case.
  - Example:
    - query image: black ribbed polo
    - expected same-design variants: grey, olive, white

- [ ] Include similar-but-not-same cases.
  - Purpose: train the bot to avoid false exact claims.

- [ ] Include no-match cases.
  - Purpose: verify abstention.

- [ ] Include difficult screenshots.
  - Purpose: Facebook screenshots are messy.
  - Cases:
    - cropped product
    - screenshot with text overlay
    - low resolution
    - dark fabric
    - white fabric on white background
    - multiple products in one image

- [ ] Define metrics.
  - Purpose: objective progress.
  - Metrics:
    - top-1 exact accuracy
    - top-3 recall
    - same-design recall
    - false exact rate
    - no-match precision
    - average latency

- [ ] Add test runner.
  - Purpose: repeatable build-test-fix loop.
  - Suggested script:
    - `scripts/run_image_search_eval.py`.

## Phase 14: Current Shirt Example Implementation

- [ ] Add the four shirt images as real product photos.
  - Purpose: create a concrete test bed for same-design different-color.
  - Source files:
    - `/home/sonjoy/Bar tax/shirt/black.jpg`
    - `/home/sonjoy/Bar tax/shirt/grey.jpg`
    - `/home/sonjoy/Bar tax/shirt/olive.jpg`
    - `/home/sonjoy/Bar tax/shirt/white.jpg`

- [ ] Create or update four product records.
  - Purpose: each color is a sellable variant.
  - Suggested product IDs:
    - `shirt-ribbed-polo-black`
    - `shirt-ribbed-polo-grey`
    - `shirt-ribbed-polo-olive`
    - `shirt-ribbed-polo-white`

- [ ] Assign same `variant_group_id`.
  - Purpose: lets bot confidently answer "same design in another color."
  - Suggested value:
    - `ribbed-open-collar-knit-polo`

- [ ] Assign same `design_id`.
  - Purpose: pattern/design identity.
  - Suggested value:
    - `vertical-ribbed-open-collar-knit`

- [ ] Assign different `color` values.
  - Purpose: color availability lookup.
  - Values:
    - black
    - grey
    - olive
    - white

- [ ] Add product attributes.
  - Purpose: structured reranking and answer explanation.
  - Suggested attributes:
    - `category_key = "shirt"`
    - `department = "men"`
    - `neckline = "open collar"`
    - `sleeve = "half sleeve"`
    - `pattern_type = "vertical ribbed"`
    - `fabric = "knit"`
    - `style = "minimal casual"`

- [ ] Add gold tests for this shirt group.
  - Purpose: protect the core use case.
  - Test questions:
    - upload black shirt -> should return black exact/top match.
    - upload black shirt + "white color ache?" -> should return white same-design variant.
    - upload olive shirt + "same design ar ki color ache?" -> should list black, grey, white.
    - upload white shirt + "blue ache?" -> should say blue not available, then show available colors.

## Phase 15: Tests

- [ ] Test catalog schema accepts image assets.
  - Existing file: `tests/test_image_matching.py`.

- [ ] Test products with same `variant_group_id` are grouped.
  - Purpose: same-design answer depends on this.

- [ ] Test exact product decision.
  - Purpose: high confidence exact match only when safe.

- [ ] Test reference image cannot create exact claim.
  - Purpose: production safety.

- [ ] Test image + text color query.
  - Purpose: "same design blue ache?" is the key behavior.

- [ ] Test follow-up memory.
  - Purpose: "white ache?" after image upload should use previous product/design.

- [ ] Test no-match behavior.
  - Purpose: bot should abstain instead of hallucinating.

- [ ] Test latency budget.
  - Purpose: chat should feel responsive.
  - Target:
    - warm query under 2 seconds for one-shop catalog.
    - cold indexing should not happen during customer query.

## Phase 16: Observability

- [ ] Add trace fields for image search.
  - Purpose: engineer can inspect every stage.
  - Required fields:
    - `image_preprocessing`
    - `embedding_model`
    - `vector_index`
    - `retrieved_image_ids`
    - `retrieved_product_ids`
    - `variant_group_resolution`
    - `score_breakdown`
    - `decision_label`
    - `abstention_reason`

- [ ] Show image trace in observer UI.
  - Purpose: learn and debug the system visually.
  - Existing debug UI: `http://127.0.0.1:5555/frontend/trace.html`.

- [ ] Log slow image queries.
  - Purpose: find remote fetches, model loading, or index problems.

- [ ] Log top failed categories.
  - Purpose: know where better images or schema fields are needed.

## Phase 17: Production Readiness Guardrails

- [ ] Do not run model loading per request.
  - Purpose: avoid 30-second customer waits.

- [ ] Do not build catalog embeddings per request.
  - Purpose: indexing belongs in sync/background jobs.

- [ ] Do not depend on internet image URLs at query time.
  - Purpose: external URLs break, rate-limit, and slow down.

- [ ] Do not let visual model override stock.
  - Purpose: availability is business truth.

- [ ] Do not show unavailable item as primary unless user asks for old/out-of-stock.
  - Purpose: selling flow should prioritize buyable items.

- [ ] Add confidence copy rules.
  - Purpose: wording must match evidence.
  - Bad:
    - "Yes exact same ache" from weak visual similarity.
  - Good:
    - "Exact same confirm korte parchi na, but closest design gula eta."

- [ ] Add owner-visible data quality warnings.
  - Purpose: bad product data causes bad bot answers.
  - Example:
    - "12 products missing real product images."
    - "7 products missing variant group."
    - "4 image URLs failed."

## Phase 18: Recommended Implementation Order

- [ ] Step 1: Add shirt variant group records.
  - Purpose: create a clean same-design/different-color demo.

- [ ] Step 2: Store the four local shirt photos as `product_photo`.
  - Purpose: stop relying on reference images for this test.

- [ ] Step 3: Add variant/design grouping helpers.
  - Purpose: query can move from one color to sibling colors.

- [ ] Step 4: Add image index/reindex command.
  - Purpose: precompute embeddings once.

- [ ] Step 5: Add score breakdown and decision labels.
  - Purpose: make exact/similar/no-match explainable.

- [ ] Step 6: Wire image search into normal chat memory.
  - Purpose: follow-up questions become natural.

- [ ] Step 7: Add product cards with badges.
  - Purpose: customer can visually verify.

- [ ] Step 8: Add image eval set and runner.
  - Purpose: build-test-fix loop.

- [ ] Step 9: Tune thresholds on real shop images.
  - Purpose: maximize same-design recall while minimizing false exact claims.

- [ ] Step 10: Add owner correction loop.
  - Purpose: continuous improvement without daily model fine-tuning.

## Definition Of Done

- [ ] Customer can upload a screenshot and get product cards.
- [ ] Bot can identify an exact product when evidence is strong.
- [ ] Bot can list same-design variants in other colors.
- [ ] Bot can say requested color is unavailable and offer available colors.
- [ ] Bot can recommend nearby alternatives when same design does not exist.
- [ ] Bot does not claim exact match from reference/demo images.
- [ ] Bot uses catalog stock/price/status for final answer.
- [ ] Follow-up questions use previous image match memory.
- [ ] Engineer can see trace output for every stage.
- [ ] Evaluation set proves top-3 and same-design behavior.
- [ ] Owner correction can fix bad matches over time.

## Files To Touch

- [ ] `app/core/schemas.py`
  - Purpose: request/response schemas, image assets, variant metadata.

- [ ] `app/inventory/image_matcher.py`
  - Purpose: metadata fallback, decision labels, answer helper.

- [ ] `app/inventory/clip_matcher.py`
  - Purpose: visual embedding search.

- [ ] `app/retrieval/elasticsearch_store.py`
  - Purpose: vector index backend.

- [ ] `app/services/inventory_service.py`
  - Purpose: route image results into normal chat and memory.

- [ ] `app/api/routes_inventory.py`
  - Purpose: image-search endpoint and API wiring.

- [ ] `app/inventory/memory.py`
  - Purpose: follow-up questions after image search.

- [ ] `frontend/chat.html`
  - Purpose: image upload UI.

- [ ] `frontend/chat.js`
  - Purpose: send image+text, render result cards and badges.

- [ ] `frontend/chat.css`
  - Purpose: product cards and match labels.

- [ ] `frontend/trace.html`
  - Purpose: debug image pipeline.

- [ ] `frontend/trace.js`
  - Purpose: stage-by-stage visual trace.

- [ ] `data/inventory/catalog.jsonl`
  - Purpose: product facts, variants, image assets.

- [ ] `data/inventory/catalog_image_sources.json`
  - Purpose: image ownership/source audit.

- [ ] `tests/test_image_matching.py`
  - Purpose: image search unit tests.

- [ ] `tests/test_inventory_api.py`
  - Purpose: endpoint-level tests.

- [ ] `evaluation/image_search_gold_set.jsonl`
  - Purpose: real evaluation examples.

## Key Risk Register

- [ ] Risk: CLIP matches color more than design.
  - Fix: separate color feature from design/pattern embedding.

- [ ] Risk: dark/black product hides texture.
  - Fix: detail image crops and image enhancement.

- [ ] Risk: white product on white background loses edge.
  - Fix: background crop, contrast normalization, detail crop.

- [ ] Risk: screenshot includes Facebook UI.
  - Fix: product crop/object detection before embedding.

- [ ] Risk: similar item falsely called exact.
  - Fix: exact claims require product/variant identity or owner correction.

- [ ] Risk: daily new products make index stale.
  - Fix: reindex on product/image sync event.

- [ ] Risk: remote image URL slows query.
  - Fix: local image cache and background embedding.

- [ ] Risk: catalog lacks variant grouping.
  - Fix: admin data quality audit and required `variant_group_id`.

## The Best Possible MVP Scope

Do not try to solve every shop and every product category first. That is too broad.

Best MVP:

```text
One shop
  -> 30-100 real product photos
  -> variant groups for same-design products
  -> image embeddings precomputed
  -> exact/same-design/similar/no-match policy
  -> feedback correction loop
```

Once this works reliably for one shop, multi-shop becomes an architecture scaling problem, not a research problem.
