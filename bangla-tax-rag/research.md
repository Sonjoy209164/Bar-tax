# Research Notes — Corrective RAG for Image Search

Working notes for turning the image-aware inventory chatbot into a research
contribution. Captured 2026-05-15. This is a planning/decision document, not a
spec — revisit when ready to pursue the paper.

---

## 1. Context and goal

The product: an image-aware inventory chatbot for boutique/fashion shops. A
customer screenshots a product from Facebook/Instagram/WhatsApp and sends it; the
bot checks the shop's own catalog and replies like a trained salesperson — exact
product if available, else same design in other colors, else nearest
alternatives, always grounded in catalog stock/price/facts.

The research question: can this become a *corrective RAG for image search*, and
is that publishable?

---

## 2. Current implementation state (already built)

The screenshot-search pipeline is largely implemented and tested:

- **Retrieval**: `app/inventory/clip_matcher.py` — CLIP image/text embeddings with
  a metadata fallback (`ImageMatcher`). Now has a grayscale **pattern channel**
  for color-invariant matching plus embedding version stamping.
- **Decision policy**: `app/inventory/image_matcher.py` — `finalize_image_search`
  grades raw visual hits into business-safe labels:
  `confirmed_exact / confirmed_same_design_variant / likely_same_design /
  similar_style / no_confident_match`. Variant grouping via
  `variant_group_id` / `design_id`.
- **Service wiring**: `InventoryService.image_search()` centralizes the pipeline;
  `/inventory/ask` answers uploaded screenshots and resolves text-only follow-ups
  ("white ache?") against the previous image-search variant group.
- **Feedback loop**: `app/inventory/image_feedback.py` — owner corrections
  override weak visual similarity; failures logged to
  `data/feedback/image_search_failures.jsonl`.
- **Observability**: image-search trace stages saved and rendered in
  `frontend/trace.html`.
- **Eval seed**: `evaluation/image_search_gold_set.jsonl` (8 cases) +
  `scripts/run_image_search_eval.py`; decision policy locked by
  `tests/test_image_matching.py`.

---

## 3. Is the current system a corrective RAG?

It is **CRAG-flavored, not textbook CRAG**.

Classic CRAG = retrieve → evaluate retrieval quality → {use / refine /
discard+seek elsewhere}.

What the system already has:
- A retrieval-quality evaluator — the decision policy grading hits into
  confidence tiers.
- A discard/abstain branch — `no_confident_match` instead of hallucinating.
- Re-grounding in structured truth — variant-group resolution from catalog
  identity rather than raw visual score.
- Human-in-the-loop correction — owner corrections override visual similarity;
  failures logged for review.

What makes it *not* classic CRAG:
- The evaluator is a fixed threshold, not a learned/composite signal.
- There is no action that actually *changes* the retrieval (no re-crop,
  re-query, or alternate-source fallback) — only a label is produced.
- No explicit out-of-distribution ("not from our catalog") detection. The only
  guard is the score threshold, so an outside product that looks close to a real
  `product_photo` SKU could be over-confidently labeled `confirmed_exact`.

---

## 4. How to build a real corrective RAG for image search

Map each CRAG component to the image domain:

### 4.1 Retrieve (multi-channel — mostly done)
Full CLIP + grayscale/pattern + color + text-tags.

### 4.2 Retrieval evaluator — the heart, where threshold ≠ CRAG
Replace the single score cutoff with a composite or learned signal:
- **Top-1 vs top-2 margin** — confident retrieval has a clear winner.
- **Cross-channel agreement** — do full + pattern + color channels point at the
  same product?
- **Cross-modal consistency** — does the query image embedding agree with the
  text/attribute embedding of the retrieved product? (CLIP gives image↔text in
  one space — a free consistency check.)
- **Geometric verification** — local-feature matching (DINOv2 patch
  correspondences, LoFTR, SIFT) to confirm *same item*, not just same category.
  Biggest single upgrade for "is this actually our SKU."
- **Learned classifier** — train relevant/ambiguous/irrelevant on
  `image_search_corrections.jsonl` + `image_search_failures.jsonl`.

Output: `confident / ambiguous / out-of-distribution` — the three CRAG branches.

### 4.3 Corrective actions (the missing part)
- **Confident** → ground in catalog identity (variant group, stock, price).
- **Ambiguous** → knowledge refinement: crop/segment the product region,
  re-query with detail crops, decompose into design+color+category sub-queries
  and recombine — or ask the customer one disambiguating question. The point: the
  retrieval actually changes.
- **OOD / incorrect** → CRAG's "web search" analog. The external knowledge here
  is the **supplier/wholesale catalog** or the **owner**, not the web. Expand to
  category-level recommendations, query the supplier catalog, or abstain +
  escalate.

### 4.4 Feedback loop
Owner corrections retrain/adjust the evaluator — the corrective loop becomes a
learned component, not a rule.

**Full architecture:** multi-channel retrieve → composite/learned evaluator →
{ground | refine+re-retrieve | expand-source/abstain} → catalog fact-check →
answer → owner correction retrains evaluator.

---

## 5. New-architecture angle (a methods contribution)

A new *network* from scratch is unrealistic (compute/data). But there is a real,
feasible (LoRA / fine-tune scale) architecture worth proposing.

**The gap:** CLIP/DINOv2/SigLIP are trained for visual *similarity*. The problem
here is product *identity* — "same design, different color," "exact SKU vs
lookalike," "abstain when not ours." Nobody has cleanly unified those.

**The architecture: disentangled product-identity encoder + abstention-aware
retrieval head.**
1. **Factored embedding** — fine-tune CLIP (LoRA/adapters) to emit *separate*
   codes: design/structure, color, category — instead of one entangled vector.
2. **Loss = catalog is free supervision** — `variant_group_id` / `design_id` /
   `color` give triplets for free:
   - same `variant_group_id`, different color → design code matches, color differs
   - same color, different design → color code matches, design differs
3. **Abstention head** — a trained output producing calibrated
   `exact / same-design / similar / not-ours`, supervised by owner corrections.
   OOD/abstention as a first-class learned output, not a threshold.
4. **Feedback loop as architecture** — owner corrections retrain the abstention
   head.

Caveats: a methods paper still requires the benchmark, strong baselines
(zero-shot + fine-tuned CLIP/DINOv2/FashionCLIP), and ablations (does
disentanglement actually help same-design recall? does the abstention head beat
thresholds?). Bigger commitment — months and some GPU. Reviewer risk: if it only
marginally beats fine-tuned FashionCLIP it reads as incremental.

---

## 6. Publishability assessment

The raw framing "we applied CRAG to images" is **not enough** — multimodal RAG,
visual retrieval with geometric verification, and abstention in retrieval all
exist.

What *would* make it publishable:
- **A dataset/benchmark** — real shop catalogs + messy customer screenshots
  labeled exact / same-design / similar / no-match. Genuine gap, datasets get
  cited, the South-Asian boutique-fashion + Bangla/Banglish domain is
  distinctive. **Strongest and lowest-risk path.**
- **The same-design-vs-color disentanglement problem** — under-explored, and the
  core of the business case.
- **A deployed-system paper** — measured business metrics (false-exact rate,
  same-design recall, no-match precision, conversion) on a real multilingual
  commerce assistant.

What it is **not**: a CVPR/NeurIPS main-track methods paper (no new foundation
architecture, no SOTA on a standard benchmark).

Realistic venues: dataset/benchmark paper; applied/industry track (ECNLP@ACL,
EMNLP industry, WWW/RecSys industry); CVPR/ECCV fashion & e-commerce workshops.

**Recommended sequencing:** dataset/benchmark paper *first* (lower risk, citable
on its own, and you need it anyway to evaluate any architecture), then the
architecture paper builds directly on it. Two papers; the first de-risks the
second.

---

## 7. The Kaggle dataset verdict

`paramaggarwal/fashion-product-images-dataset` — re-hosted on HuggingFace as
`ashraq/fashion-product-images-small`, which `scripts/build_hf_fashion_local_catalog.py`
already pulls. The `hf-*` demo catalog entries come from it.

**Good for:** encoder pretraining/fine-tuning at scale (~44k products with real
`articleType`, `baseColour`, `gender`, `productDisplayName`); baseline
comparisons; the catalog side of the pipeline.

**Falls short for the actual goal:**
- **Variant-group supervision is weak.** The current `design_id` is derived by
  *stripping color words from the product name string* — noisy approximation, not
  true SKU variant grouping. Myntra never exported real variant data.
- **Zero query side.** All clean studio shots on white. The hard problem
  (Facebook/WhatsApp UI clutter, low-res, crops, glare) is absent.
- **It is reference data, not shop-owned.** Cannot prove a shop stocks the
  product — must stay `is_reference=true`.
- **Not a dataset contribution.** Well-known; using it = pretraining + baselines
  only.

Treat it as the "easy half." The contribution lives in the half it can't give:
true variant groups (from real shop SKU data) and a real query set of messy
screenshots.

---

## 8. The dataset to build

Two files: a fixed catalog (knowledge base) and a query benchmark (the
contribution).

### 8.1 Flaw to fix in the current seed
`evaluation/image_search_gold_set.jsonl` uses catalog images *as* query images —
query = retrieval target = identity leakage. Real benchmark query images must be
separate, messy screenshots never present in the catalog.

### 8.2 `catalog.jsonl` — the KB (one variant group shown)
Upgrade: per-size stock instead of a `"M, L, XL"` string.

```json
{"product_id":"shirt-ribbed-polo-black","sku":"SHIRT_RIBBED_POLO_BLACK","name":"Ribbed Open-Collar Knit Polo - Black","category":"Shirt","variant_group_id":"ribbed-open-collar-knit-polo","design_id":"vertical-ribbed-open-collar-knit","color":"black","color_family":"black","size_stock":{"M":2,"L":2,"XL":1},"price":1750,"images":[{"image_id":"shirt-ribbed-polo-black-primary-1","local_path":"catalog/shirt-ribbed-polo-black/primary.jpg","kind":"product_photo","is_reference":false}]}
{"product_id":"shirt-ribbed-polo-white","sku":"SHIRT_RIBBED_POLO_WHITE","name":"Ribbed Open-Collar Knit Polo - White","category":"Shirt","variant_group_id":"ribbed-open-collar-knit-polo","design_id":"vertical-ribbed-open-collar-knit","color":"white","color_family":"white","size_stock":{"M":0,"L":3,"XL":2},"price":1750,"images":[{"image_id":"shirt-ribbed-polo-white-primary-1","local_path":"catalog/shirt-ribbed-polo-white/primary.jpg","kind":"product_photo","is_reference":false}]}
```

The shared `variant_group_id` is the free disentanglement supervision — must be
real SKU data, not name-stripping.

### 8.3 `query_benchmark.jsonl` — the contribution
One case per real screenshot. Five label types, each with difficulty tags.

```json
{"case_id":"ribbed_polo_black_exact_fb","query_image":"queries/fb_0012.jpg","query_source":"facebook","difficulty_tags":["text_overlay","cropped"],"query_text":"eta ki ache?","query_language":"banglish","label":"exact","expected_product_id":"shirt-ribbed-polo-black","expected_variant_group_id":"ribbed-open-collar-knit-polo","screenshot_color":"black","requested_color":null,"expected_available_colors":["black","grey","olive","white"],"acceptable_similar_product_ids":[],"rationale":"Shop's own black polo reshared from their FB page; exact SKU in catalog.","annotators":["a1","a3"],"agreement":1.0}
{"case_id":"ribbed_polo_white_from_black_shot","query_image":"queries/wa_0044.jpg","query_source":"whatsapp","difficulty_tags":["low_res"],"query_text":"same design white ache?","query_language":"banglish","label":"same_design_variant","expected_product_id":"shirt-ribbed-polo-white","expected_variant_group_id":"ribbed-open-collar-knit-polo","screenshot_color":"black","requested_color":"white","expected_available_colors":["black","grey","olive","white"],"acceptable_similar_product_ids":[],"rationale":"Screenshot shows black; customer asks for white. Same group, white in stock at L/XL.","annotators":["a2","a3"],"agreement":1.0}
{"case_id":"outside_red_jamdani_similar","query_image":"queries/insta_0091.jpg","query_source":"instagram","difficulty_tags":["mannequin","glare"],"query_text":"eirokom saree ache?","query_language":"banglish","label":"similar","expected_product_id":null,"expected_variant_group_id":null,"screenshot_color":"red","requested_color":null,"expected_available_colors":[],"acceptable_similar_product_ids":["saree-jmd-lotus-red","saree-jmd-buti-maroon"],"rationale":"Red jamdani from another shop's page — not our SKU, but we carry close red jamdani. Any listed similar is acceptable; claiming exact is wrong.","annotators":["a1","a2"],"agreement":0.5}
{"case_id":"white_formal_white_bg_hard","query_image":"queries/fb_0077.jpg","query_source":"facebook","difficulty_tags":["white_on_white","cropped"],"query_text":"","query_language":"none","label":"exact","expected_product_id":"shirt-formal-white-l","expected_variant_group_id":"classic-formal-shirt","screenshot_color":"white","requested_color":null,"expected_available_colors":["white","blue"],"acceptable_similar_product_ids":[],"rationale":"Hard case: white shirt on white background, edges nearly lost.","annotators":["a1","a3"],"agreement":1.0}
{"case_id":"ood_kids_toy_no_match","query_image":"queries/fb_0130.jpg","query_source":"facebook","difficulty_tags":["multi_product"],"query_text":"eta ache?","query_language":"banglish","label":"no_match","expected_product_id":null,"expected_variant_group_id":null,"screenshot_color":null,"requested_color":null,"expected_available_colors":[],"acceptable_similar_product_ids":[],"rationale":"A children's toy — outside this boutique's domain. System must abstain.","annotators":["a1","a2","a3"],"agreement":1.0}
```

Key fields that make it a benchmark, not a demo:
- `label` ∈ `{exact, same_design_variant, similar, no_match}`.
- `difficulty_tags` ∈ `{cropped, text_overlay, low_res, dark_fabric,
  white_on_white, multi_product, glare, mannequin, flat_lay}` — enables
  per-difficulty accuracy reporting.
- `acceptable_similar_product_ids` is a *set*, not one answer.
- `requested_color` vs `screenshot_color` — separates image signal from text ask.
- `annotators` + `agreement` — inter-annotator agreement (report Fleiss' κ).

### 8.4 Directory layout
```
benchmark/
  catalog.jsonl              # KB — real shop SKUs with true variant groups
  catalog/{product_id}/*.jpg # shop-owned product photos
  query_benchmark.jsonl      # eval cases
  queries/*.jpg              # real customer screenshots (NOT in catalog/)
  README.md                  # collection + annotation protocol
```

### 8.5 Scale & protocol
- ~400–800 query cases, balanced across the 4 labels, every difficulty tag
  represented.
- 1 catalog of ~100–300 real SKUs from one or a few actual shops.
- 2–3 annotators; report κ. The similar-vs-no_match boundary is where
  disagreement lives — that disagreement is itself a finding.
- Collection: real screenshots from the shop's own DMs/comments, with consent.

### 8.6 Metrics it unlocks
top-1 exact accuracy · same-design recall · **false-exact rate** (the safety
metric) · no-match precision · per-difficulty-tag breakdown · latency.

---

## 9. What can / cannot be built without real data

**Cannot be built (and must not be faked):** the dataset itself. The value is
that screenshots are real and labels come from real annotators. Synthetic
screenshots + invented labels prove nothing and are misconduct for a paper.

**Can be built — the scaffolding/toolchain:**
1. **Schema + validator** — Pydantic models for catalog + query-case formats;
   `validate_benchmark.py` enforcing label/field consistency, image existence,
   no catalog/query leakage, controlled difficulty-tag vocabulary.
2. **Eval runner** — consumes `query_benchmark.jsonl` through
   `InventoryService.image_search()`, emits the metrics table including
   per-difficulty breakdown and false-exact rate. Upgrades
   `scripts/run_image_search_eval.py`.
3. **Annotation kit** — intake CSV/template, κ calculator, optional local HTML
   labeling tool.
4. **Protocol README** — collection + annotation guidelines.
5. **Seed migration** — convert `image_search_gold_set.jsonl` into the new
   schema, with leakage cases flagged for replacement.

Decision deferred — the user will consider pursuing this later. When resuming,
the first concrete step is the scaffolding (section 9), then real screenshot +
catalog collection (section 8.5).

---

## 10. Prior-art check (2026-05-15 web search)

Searched whether the proposed "disentangled product-identity encoder + corrective
RAG + abstention" architecture is novel. **It is not, as a combination of known
parts.** Component-by-component prior art:

| Proposed component | Already published / shipped as |
|---|---|
| Disentangled design / color / category embedding for fashion | **DAtRNet** (CVPR 2022 W) — literally "Disentangling Fashion Attribute Embedding for Substitute Item Retrieval"; **ADDE** (Amazon Science); **GAMMA**; self-supervised color/shape disentanglement. |
| Retrieval evaluator → {use / refine / discard+search-elsewhere} | **CRAG** (arXiv 2401.15884); **Self-RAG**; Agentic RAG — the canonical 3-branch corrective pattern. |
| Multimodal RAG with retrieval-quality evaluation and re-routing | Multimodal RAG survey (arXiv 2504.08748); Awesome-RAG-Vision. |
| Abstention / OOD as a trained output | Mature field — abstention class baselines, selective prediction, generalized ODIN. |
| exact / same-design-variant / similar 3-way product decision | **Intelligence Node** ships exactly "Exact match / Similar match / Variant match" commercially. |
| Screenshot → catalog visual search; conversational commerce | Deployed: Rezolve AI, Alhena, Shopify visual search, ChatGPT visual shopping. |

**Implication:** A methods paper that frames "disentangled identity encoder +
corrective loop + abstention for product retrieval" as novel will be rejected as
an incremental combination of known techniques. The original plan in section 5
needs to drop disentanglement and the CRAG loop as headline novelty claims.

### 10.1 The narrow architecture-novelty angle that may survive

Where prior art is thinner — and worth checking again with a fresh, deeper
search before committing — is the **integration of visual evidence with a
structured catalog as the calibrated ground truth**:

- CRAG corrects by going to web search; this architecture corrects against a
  *structured catalog of SKU identity* (variant group, stock, owner mappings).
  That's "RAG that grounds in structured business truth," not in unstructured
  web text.
- **`false-exact rate` as a first-class safety objective**, paired with a
  feedback-trained abstention head, is less explored than disentanglement and
  CRAG individually.
- The deployment-loop framing (owner corrections retrain the abstention head) as
  *part of the named architecture* is also under-claimed in the published work.

Honest read: this is *integration* novelty — defensible as a workshop or applied
paper, not as a CVPR/NeurIPS main-track methods contribution.

### 10.2 Venue fit

**GRAIL-V @ CVPR 2026** explicitly calls for "grounded multimodal retrieval,
reranking, and verification … abstention behavior" — almost exactly this
problem. This is the right venue for an architecture-as-headline paper given
the prior art.

Other realistic targets: ECNLP @ ACL, EMNLP industry, WWW/RecSys industry,
ECCV / CVPR fashion & e-commerce workshops.

### 10.3 Recommendation update

1. Drop "disentangled encoder" and "corrective RAG loop" as novelty claims —
   they will not survive review.
2. Narrow the architecture pitch to **catalog-grounded identity arbitration +
   false-exact-rate safety + feedback-trained abstention** as the named
   contribution, and target a workshop/applied venue where integration novelty
   is acceptable.
3. The benchmark (section 8) is still required either way — it is what lets the
   architecture be evaluated at all, and is the lower-risk citable contribution
   on its own.
4. When `WebSearch` is available again, run a fresh round on the narrow angle
   ("catalog-grounded RAG", "structured-knowledge corrective retrieval",
   "deployment-feedback abstention for retrieval") before finalizing the
   novelty claim, to confirm the gap.

### 10.4 Search queries used (2026-05-15)
- `"disentangled fashion product embedding color design separation retrieval"`
- `"corrective RAG multimodal image retrieval abstention 2025"`
- `"exact product matching same design different color variant retrieval e-commerce SKU"`
- `"out-of-distribution abstention image retrieval is this product in catalog verification"`
- `"corrective RAG visual product search fashion self-correcting retrieval evaluator 2025 2026"`
- `"screenshot product search social media customer conversational commerce visual catalog grounding"`

Two follow-up queries were attempted (`corrective RAG fashion image retrieval
arxiv 2026`, `visual evidence reconciliation structured catalog product identity
calibrated retrieval decision`) but blocked by the WebSearch daily rate limit;
run these next.
