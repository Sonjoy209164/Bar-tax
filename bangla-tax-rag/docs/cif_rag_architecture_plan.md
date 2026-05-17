# CIF-RAG Architecture Plan

## Working Title

**CIF-RAG: Counterfactual Identity-Factorized Retrieval-Augmented Generation for Safe Conversational Commerce**

This is the proposed architectural novelty direction for the image-aware boutique chatbot.

The goal is not to invent another CLIP visual-search wrapper. That would be weak.

The goal is to build a new decision architecture for commerce:

```text
Customer screenshot + customer language
  -> factorize product identity
  -> compile the user request into counterfactual operations
  -> retrieve visual/catalog evidence
  -> verify typed commerce claims
  -> answer only what is commercially provable
```

## Problem Statement

Small online shops receive customer questions like:

```text
ei same design ta blue color e ache?
eta M size ache?
Facebook e dekhlam, apnader kase ache?
exact eta na thakle similar dekhan
```

This is not only visual search.

It is a high-risk commerce decision problem because the system must distinguish:

- exact same product
- same design, different color
- same product family, different size
- visually similar alternative
- no confident match
- available vs unavailable
- known fact vs missing catalog fact

Standard image retrieval collapses these into one score. That causes false exact claims and wrong stock promises.

## Core Architectural Novelty

CIF-RAG treats a customer screenshot query as a **counterfactual product-identity question**, not as a nearest-neighbor lookup.

Example:

```text
User: ei same design ta blue color e ache?
```

CIF-RAG representation:

```text
HOLD(design = design inferred from uploaded image)
INTERVENE(color = blue)
VERIFY(stock > 0)
ANSWER_WITH_EVIDENCE()
```

This is the main architectural move.

## One-Line Claim

```text
CIF-RAG reduces unsafe commerce answers by separating visual similarity from product identity,
then verifying counterfactual customer requests against typed catalog, variant, and stock evidence.
```

## Architecture Overview

```text
Customer Image + Text
        |
        v
1. Multimodal Factor Encoder
        |
        v
2. Product Factor Graph
        |
        v
3. Counterfactual Query Planner
        |
        v
4. Candidate Evidence Retriever
        |
        v
5. Claim Contract Compiler
        |
        v
6. Risk-Cost Decision Automaton
        |
        v
7. Grounded Salesperson Answer
        |
        v
8. Owner Correction + Continual Identity Memory
```

## Layer 1: Multimodal Factor Encoder

### Purpose

Convert image and text into separate product factors instead of one blended vector.

### Why It Matters

For same-design/different-color search, color must not dominate design.

Bad architecture:

```text
one CLIP vector = color + category + shape + pattern mixed together
```

Better architecture:

```text
category factor
shape factor
design/pattern factor
color factor
material/texture factor
text slot factor
source trust factor
```

### Existing Code To Reuse

- `app/inventory/clip_matcher.py`
- `app/inventory/image_matcher.py`
- `app/inventory/image_preprocessing.py`
- `app/inventory/image_index.py`

### New Code

```text
app/inventory/product_factors.py
```

### Proposed Output Schema

```json
{
  "product_id": "shirt-ribbed-polo-black",
  "image_id": "shirt-ribbed-polo-black-primary-1",
  "category_factor": {"label": "shirt", "score": 0.94},
  "design_factor": {"label": "vertical ribbed open collar", "score": 0.88},
  "color_factor": {"label": "black", "family": "black", "score": 0.92},
  "shape_factor": {"label": "short sleeve polo", "score": 0.86},
  "texture_factor": {"label": "ribbed knit", "score": 0.82},
  "source_trust": "product_photo"
}
```

### Implementation Notes

- Keep CLIP as full visual baseline.
- Use grayscale/pattern channel for design.
- Use dominant-color extraction as a separate signal.
- Use visual tags and structured catalog attributes as text factor.
- Later compare CLIP, FashionCLIP, DINOv2, SigLIP.

## Layer 2: Product Factor Graph

### Purpose

Represent catalog truth as relationships, not flat rows.

### Why It Matters

The bot can only answer "same design blue ache?" if it knows what "same design" means structurally.

### Graph Model

```text
Product
  -> belongs_to VariantGroup
  -> has Design
  -> has ColorVariant
  -> has SizeStock
  -> has ImageAsset
  -> has SourceTrustLevel
  -> has BusinessState
```

### Existing Code To Reuse

- `data/inventory/catalog.jsonl`
- `app/inventory/catalog_identity.py`
- `app/inventory/catalog_audit.py`

### New Code

```text
app/inventory/product_factor_graph.py
```

### Proposed Node Types

```text
ProductNode
DesignNode
VariantGroupNode
ColorNode
SizeStockNode
ImageEvidenceNode
BusinessStateNode
```

### Proposed Edge Types

```text
HAS_DESIGN
IN_VARIANT_GROUP
HAS_COLOR
HAS_SIZE_STOCK
HAS_IMAGE
HAS_TRUST_LEVEL
HAS_PRICE
HAS_STATUS
```

### Example

```text
shirt-ribbed-polo-black
  -> IN_VARIANT_GROUP ribbed-open-collar-knit-polo
  -> HAS_DESIGN vertical-ribbed-open-collar-knit
  -> HAS_COLOR black
  -> HAS_SIZE_STOCK M:2, L:2, XL:1
  -> HAS_IMAGE product_photo
```

## Layer 3: Counterfactual Query Planner

### Purpose

Convert customer intent into product-identity operations.

### Why It Matters

Most queries are not direct searches. They are transformations over a found product identity.

### Existing Code To Reuse

- `app/inventory/fashion_retail.py`
- `app/inventory/llm_slot_extractor.py`
- `app/inventory/intent_planner.py`
- `app/inventory/image_matcher.py`

### New Code

```text
app/inventory/counterfactual_planner.py
```

### Operation Types

```text
IDENTIFY(product_from_image)
HOLD(factor)
INTERVENE(factor=value)
VERIFY(fact)
RELAX(factor)
ABSTAIN(reason)
```

### Query Compilation Examples

#### Exact Product

```text
User: eta ache?

Plan:
IDENTIFY(product_from_image)
VERIFY(product_status)
VERIFY(stock)
```

#### Same Design In Another Color

```text
User: same design blue color e ache?

Plan:
IDENTIFY(product_from_image)
HOLD(design)
INTERVENE(color=blue)
VERIFY(variant_exists)
VERIFY(stock)
```

#### Size Availability

```text
User: M size ache?

Plan:
IDENTIFY(product_or_memory_anchor)
VERIFY(size=M)
VERIFY(size_stock)
```

#### Similar Alternative

```text
User: exact eta na thakle similar dekhan

Plan:
IDENTIFY(product_from_image)
RELAX(product_id)
HOLD(category)
HOLD(style/design if confident)
RETRIEVE(similar_style)
VERIFY(stock)
```

## Layer 4: Candidate Evidence Retriever

### Purpose

Retrieve possible evidence for the counterfactual plan.

### Retrieval Channels

```text
full_visual_vector
pattern_visual_vector
catalog_identity_graph
structured filters
text slots
owner corrections
```

### Existing Code To Reuse

- `app/inventory/clip_matcher.py`
- `app/retrieval/elasticsearch_store.py`
- `app/inventory/image_index.py`
- `app/inventory/image_feedback.py`

### New Code

```text
app/inventory/cif_retriever.py
```

### Important Rule

Retrieval returns candidates, not truth.

```text
retrieval score != permission to claim exact match
```

## Layer 5: Claim Contract Compiler

### Purpose

Translate planned answers into typed claims and required evidence.

### Why It Matters

The answer is safe only if every commercial claim has the right evidence type.

### Existing Code To Reuse

- `app/inventory/evidence_contract.py`
- `app/inventory/verifier.py`
- `app/inventory/answer_critic.py`

### New Code

```text
app/inventory/commerce_claims.py
```

### Claim Types

```text
ExactProductClaim
SameDesignVariantClaim
SimilarStyleClaim
ColorAvailabilityClaim
SizeStockClaim
PriceClaim
AbsenceClaim
SourceTrustClaim
```

### Evidence Requirements

```text
ExactProductClaim
  requires:
    - product_id match OR owner correction
    - product_photo/supplier_photo trust
    - high visual score or confirmed mapping

SameDesignVariantClaim
  requires:
    - variant_group_id OR design_id
    - requested color match
    - stock/status checked

SizeStockClaim
  requires:
    - size_stock field OR explicit missing-fact hedge

AbsenceClaim
  requires:
    - full variant group checked
    - no matching color/size found
```

## Layer 6: Risk-Cost Decision Automaton

### Purpose

Choose the safest commercially useful answer based on claim risk.

### Why It Matters

Not all mistakes are equal.

```text
False exact match       = high risk
Wrong stock answer      = high risk
Wrong price             = high risk
Missed alternative      = medium risk
Conservative hedge      = low risk
```

### Existing Code To Reuse

- `app/inventory/image_matcher.py`
- `app/inventory/policy.py`
- `app/inventory/verifier.py`

### New Code

```text
app/inventory/risk_decision_automaton.py
```

### Decision Labels

```text
confirmed_exact
confirmed_same_design_variant
likely_same_design
similar_style
no_confident_match
missing_fact
needs_owner_review
```

### Decision Principle

```text
Prefer a useful conservative answer over a risky confident answer.
```

## Layer 7: Grounded Salesperson Answer

### Purpose

Generate customer-friendly replies whose wording matches evidence strength.

### Existing Code To Reuse

- `app/inventory/natural_answer.py`
- `app/services/inventory_service.py`
- `frontend/chat.js`

### New Code

```text
app/inventory/cif_answerer.py
```

### Example Outputs

#### Confirmed Same Design

```text
Same design ta ache. White color stock e ache, price BDT 1,750.
Black, grey, olive o available. M size white e currently nei, L/XL ache.
```

#### Similar Only

```text
Exact same confirm korte parchi na, but closest ribbed open-collar design gula eta.
Blue nei, available colors: black, grey, olive, white.
```

#### Missing Fact

```text
Ei product er size-wise stock catalog e clear na. Ami exact size confirm korte parchi na,
but product ta catalog e ache.
```

## Layer 8: Owner Correction + Continual Identity Memory

### Purpose

Let the shop owner correct matches without retraining the whole model.

### Existing Code To Reuse

- `app/inventory/image_feedback.py`
- `data/feedback/image_search_corrections.jsonl`
- `data/feedback/image_search_failures.jsonl`

### New Code

```text
app/inventory/identity_corrections.py
frontend/owner_corrections.html
frontend/owner_corrections.js
```

### Correction Types

```text
exact_product
same_design
similar_style
not_same
no_match
wrong_color
wrong_category
```

### Strategic Value

This turns daily shop operation into weak supervision:

```text
customer upload -> model wrong -> owner corrects -> future ranking improves
```

## Research Dataset Plan

### Dataset Name

```text
Boutique-CIF-Search
```

### Minimum Publishable Version

```text
100 products
300-500 product images
500 customer-style screenshot queries
Bangla/Banglish/English text
owner-confirmed labels
```

### Ideal Version

```text
500 products
1500-3000 images
3000-5000 queries
multiple stores
multiple categories
live stock/size snapshots
```

### Labels

```text
exact_product_id
same_design_variant_ids
requested_color
requested_size
availability_truth
similar_product_ids
no_match
forbidden_claims
required_evidence
```

## Evaluation Metrics

### Retrieval Metrics

```text
Top-1 exact accuracy
Top-3 target recall
Same-design recall
Cross-category violation rate
```

### Commerce Safety Metrics

```text
False Commercial Claim Rate
False Exact Match Rate
Wrong Stock Claim Rate
Wrong Size Claim Rate
Wrong Price Claim Rate
Grounded Absence Precision
```

### Counterfactual Metrics

```text
Counterfactual Variant Accuracy
  -> Did the system hold design constant and change only requested factor?

Intervention Success Rate
  -> For DO(color=blue), did it search only sibling variants before fallback?

Claim Evidence Coverage
  -> What percentage of answer claims have required evidence?
```

### Conversation Metrics

```text
Banglish Intent Success
Follow-up Resolution Accuracy
Memory Anchor Accuracy
Human Helpfulness Score
```

## Ablation Table

This is the paper's backbone.

| Method | Expected Weakness | What It Proves |
|---|---|---|
| CLIP-only | false exact claims, weak stock grounding | visual similarity alone is unsafe |
| FashionCLIP-only | better fashion retrieval but still no business truth | model specialization is not enough |
| Metadata-only | safe but misses screenshot matches | visual retrieval is necessary |
| No factor separation | color dominates design | factorization is necessary |
| No product graph | same-design/color queries fail | identity graph is necessary |
| No counterfactual planner | follow-up and intervention queries fail | planner is necessary |
| No claim contracts | unsupported answer claims increase | evidence contracts are necessary |
| Full CIF-RAG | best safety/usefulness tradeoff | full architecture contribution |

## Proposed Implementation Phases

## Current Implementation Status

First CIF-RAG MVP implemented:

- [x] Product factor extraction: `app/inventory/product_factors.py`
- [x] Product factor graph: `app/inventory/product_factor_graph.py`
- [x] Counterfactual planner: `app/inventory/counterfactual_planner.py`
- [x] Typed commerce claim contracts: `app/inventory/commerce_claims.py`
- [x] Risk-cost decision automaton: `app/inventory/risk_decision_automaton.py`
- [x] CIF orchestration wrapper: `app/inventory/cif_engine.py`
- [x] Image-search trace integration: `app/services/inventory_service.py`
- [x] CIF unit/integration tests: `tests/test_cif_rag.py`
- [x] CIF architecture evaluation set: `evaluation/cif_counterfactual_commerce_set.jsonl`
- [x] CIF architecture evaluation runner: `scripts/run_cif_rag_research_eval.py`

Current output artifact:

```text
results/cif_rag_research_pass_20260517_080150.md
```

Current targeted verification:

```text
40 passed, 3 warnings
```

Important boundary:

```text
The first implementation adds CIF-RAG traceability and architecture evaluation while preserving the current customer-facing image-search answer behavior.
```

### Phase 0: Freeze Current Baseline

Goal:

```text
Preserve current image-search behavior as baseline.
```

Tasks:

- [ ] Keep current `q1_image_search_research_set.jsonl`.
- [ ] Keep `run_q1_image_research_pass.py`.
- [ ] Save current report as baseline.
- [ ] Add a short baseline summary to `results/`.

### Phase 1: Product Factor Graph

Goal:

```text
Make catalog identity explicit and queryable.
```

Files:

- [ ] `app/inventory/product_factor_graph.py`
- [ ] `tests/test_product_factor_graph.py`

Deliverables:

- [ ] Build graph from `catalog.jsonl`.
- [ ] Query same-design siblings.
- [ ] Query color variants.
- [ ] Query size stock.
- [ ] Query image trust.

### Phase 2: Counterfactual Planner

Goal:

```text
Compile customer queries into operations.
```

Files:

- [ ] `app/inventory/counterfactual_planner.py`
- [ ] `tests/test_counterfactual_planner.py`

Deliverables:

- [ ] Parse `same design blue`.
- [ ] Parse `M size ache`.
- [ ] Parse `exact eta`.
- [ ] Parse `similar dekhan`.
- [ ] Use previous image memory as anchor.

### Phase 3: Claim Contracts

Goal:

```text
Make every answer claim typed and evidence-bound.
```

Files:

- [ ] `app/inventory/commerce_claims.py`
- [ ] `tests/test_commerce_claims.py`

Deliverables:

- [ ] Exact product claim contract.
- [ ] Same-design variant claim contract.
- [ ] Size/stock claim contract.
- [ ] Absence claim contract.
- [ ] Missing-fact hedge contract.

### Phase 4: Risk-Cost Decision Automaton

Goal:

```text
Choose answer confidence based on business risk, not only score.
```

Files:

- [ ] `app/inventory/risk_decision_automaton.py`
- [ ] `tests/test_risk_decision_automaton.py`

Deliverables:

- [ ] Cost matrix.
- [ ] Confidence thresholds by claim type.
- [ ] Reference-image demotion.
- [ ] No-match and owner-review routes.

### Phase 5: CIF Orchestrator

Goal:

```text
Wire factors + graph + planner + claims + risk policy into one engine.
```

Files:

- [ ] `app/inventory/cif_engine.py`
- [ ] `app/services/inventory_service.py`
- [ ] `tests/test_cif_engine.py`

Deliverables:

- [ ] Image + text query end-to-end.
- [ ] Follow-up query end-to-end.
- [ ] Product cards with decision labels.
- [ ] Trace output showing every operation.

### Phase 6: Research Evaluation

Goal:

```text
Prove architecture value through ablations.
```

Files:

- [ ] `evaluation/cif_counterfactual_commerce_set.jsonl`
- [ ] `scripts/run_cif_rag_research_eval.py`
- [ ] `results/cif_rag_research_pass_*.md`

Deliverables:

- [ ] Add counterfactual query cases.
- [ ] Add factor ablations.
- [ ] Add claim-safety metrics.
- [ ] Add paper-style tables.

## One-Pass MVP Build Order

If we want a first visible version quickly:

```text
1. Product Factor Graph
2. Counterfactual Planner
3. Claim Contracts
4. Risk Decision Automaton
5. CIF Engine wrapper around current image matcher
6. Evaluation runner with ablations
```

Do not start with fine-tuning.

Fine-tuning comes after the architecture produces measurable failure cases.

## Paper Contribution Structure

### Contribution 1

```text
We formalize screenshot-based boutique commerce QA as counterfactual product-identity retrieval.
```

### Contribution 2

```text
We propose CIF-RAG, a modular architecture that separates visual factors, catalog identity,
claim evidence, and business-risk decision policy.
```

### Contribution 3

```text
We introduce metrics for safe conversational commerce:
false commercial claim rate, counterfactual variant accuracy, and claim evidence coverage.
```

### Contribution 4

```text
We build and evaluate a Bangla/Banglish boutique-commerce dataset with screenshot queries,
same-design variants, and stock/size constraints.
```

## What Would Make This Strong Enough

Minimum bar:

- [ ] Real shop-owned dataset.
- [ ] At least 500 labeled image-text queries.
- [ ] Strong ablation table.
- [ ] Human evaluation on helpfulness/safety.
- [ ] Error taxonomy.

Strong bar:

- [ ] Multiple stores.
- [ ] Daily catalog update simulation.
- [ ] Owner correction loop evaluation.
- [ ] Comparison with CLIP, FashionCLIP, and DINOv2.
- [ ] Public anonymized dataset or reproducible benchmark subset.

## Biggest Risks

### Risk 1: Architecture Sounds Bigger Than Evidence

Fix:

```text
Keep claims tied to metrics. Do not overclaim novelty without ablations.
```

### Risk 2: Dataset Is Too Small

Fix:

```text
Collect real product photos and customer-style screenshots early.
```

### Risk 3: Reviewers Say It Is Just Rules

Fix:

```text
Frame rules as typed claim contracts and risk-cost automata, then show measured reduction in false commercial claims.
```

### Risk 4: No Model Novelty

Fix:

```text
Do not compete on model architecture. Compete on system architecture, evaluation, and safety metrics.
```

## Final Strategic Position

The defensible novelty is not:

```text
We use CLIP for fashion search.
```

The defensible novelty is:

```text
We introduce a counterfactual, claim-verified commerce RAG architecture that prevents visual retrieval
from becoming unsafe product promises.
```

That is the idea worth building.
