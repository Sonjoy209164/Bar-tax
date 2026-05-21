# Memory Flow Learning Report

Created: 2026-05-21

## Goal

Make conversation memory useful without letting old context hijack new shopping intent.

The memory rules being tested:

- Use product memory only for clear follow-ups.
- Expire product focus after 30-60 minutes.
- Keep preferences longer only when repeated.
- Never let an old category override a new category.
- Never store unsafe/off-topic/medical/legal text as shopping preference.
- Attach memory source, updated time, confidence, and TTL metadata.

## What Was Built

- `scripts/run_memory_flow_eval.py`
  - Generates and runs 100 multi-turn memory cases.
  - Uses temporary SQLite state so tests do not depend on the live chat database.
  - Exercises the same memory resolver and server-side hydration code used by the app.

- `evaluation/memory_multiturn_100_cases.jsonl`
  - The 100-case test set.
  - Covers Bangla, Banglish, English, image-search memory, product switching, off-topic detours, sensitive topics, expiry, low-confidence image matches, and ambiguous questions.

- `results/memory_flow_100_eval.jsonl`
  - Machine-readable run output.

- `results/memory_flow_100_eval.md`
  - Human-readable report.

## Example Multi-Turn Flow

```text
1. User: black panjabi under 3000 dekhao
   Expected: new product search, write focus = panjabi_1, panjabi_2, panjabi_3

2. User: etar price koto?
   Expected: clear follow-up, resolve to panjabi_1

3. User: second one er size ache?
   Expected: ordinal follow-up, resolve to panjabi_2

4. User: same design blue color e ache?
   Expected: same-design follow-up, use previous panjabi focus

5. User: red saree dekhao
   Expected: new category request, old panjabi focus must not override saree

6. User: etar stock ache?
   Expected: now resolve to saree_1, not panjabi_1
```

## First Run Result

Initial memory harness result:

```text
75/100 passed
25/100 failed
```

This was not good enough. The failures were real product risks, not harmless test noise.

## Failure Types Found

### 1. Weak Fact Words Overused Old Memory

Problem:

```text
kachchi biryani ache?
amar boyosh koto?
delivery charge koto?
```

Some of these were being treated like product follow-ups because they contain `ache` or `koto`.

Fix:

- Added non-product fact-topic guards.
- Made price/availability follow-ups stricter.
- Prevented delivery, order, age, legal, food, and random personal questions from using product focus.

### 2. Same-Design And Color Follow-Ups Were Too Weak

Problem:

```text
same design blue color e ache?
white ache?
ar ki color ache?
```

These should use the current product/design focus, especially after image search.

Fix:

- Added same-design, color, similar, matching, and cross-sell phrases as memory references.
- Kept color-only follow-ups useful when no new product category is mentioned.

### 3. Bangla Was Losing Signal

Problem:

Some Bangla phrases were normalized into empty or incomplete text before memory checks.

Fix:

- Memory matching now preserves raw Bangla text beside normalized Banglish/English text.
- Added Bangla direct-reference, price, size, stock, color, and order terms.

### 4. Anchored Cross-Sell Was Misread As New Search

Problem:

```text
etar sathe matching blouse ache?
```

The system saw `blouse ache` and treated it as a brand-new blouse search, losing the prior saree focus.

Fix:

- Added direct-anchor protection for `eta`, `etar`, `this`, `that`, `it`, `এটা`, `এটার`, etc.
- A product word inside an anchored follow-up can now use the previous product as the source item.

### 5. Fresh Product Names Were Misread As Follow-Ups

Problem:

```text
white pearl earrings
same color shoe ache?
```

Because `white` and `same color` are memory-like signals, the resolver could incorrectly reuse an old watch/bag/frock context.

Fix:

- Any fresh product/category mention blocks old product focus unless there is a direct anchor like `eta`, `etar`, `this`, or `it`.
- This enforces the business rule: old category never overrides new category.

## Code Changes

### `app/inventory/memory_policy.py`

- Added stricter product-term detection.
- Added non-product fact-topic blocking.
- Added word-boundary phrase matching to avoid substring accidents.
- Added color and product-term handling.
- Tightened follow-up use so broad `ache/koto` does not blindly use memory.

### `app/inventory/memory.py`

- Added Bangla raw-text support.
- Added same-design, color, similar, matching, and cross-sell memory references.
- Added fresh product/category override logic.
- Added direct-anchor exception for anchored cross-sell queries.
- Improved cross-sell fallback so `what goes with this?` can resolve to the current focused product.

### `app/inventory/conversation_context.py`

- Added direct-anchor guard in `question_looks_like_new_request`.
- Prevents anchored follow-ups from being misclassified as brand-new searches.
- Improved Bangla follow-up detection.

## Final Run Result

Memory flow harness:

```text
Memory flow eval: 100/100 passed
```

Focused regression suite:

```text
118 passed, 3 warnings
```

The warnings are dependency/import warnings, not memory failures.

## Scenario Coverage

| Scenario | Result |
|---|---:|
| Basic Banglish product memory | 10/10 |
| Off-topic and polite-boundary detours | 10/10 |
| Sensitive-topic memory guard | 10/10 |
| Image-search memory and variants | 10/10 |
| Product-focus expiry | 10/10 |
| Preference and category override | 10/10 |
| Bangla flow | 10/10 |
| English flow | 10/10 |
| Ambiguous/off-topic fact words | 10/10 |
| Low-confidence/no-match safety | 10/10 |

## Commands

Run the 100-case memory flow eval:

```bash
.venv/bin/python scripts/run_memory_flow_eval.py
```

Run focused regressions:

```bash
.venv/bin/python -m pytest \
  tests/test_memory_policy.py \
  tests/test_conversation_state.py \
  tests/test_conversation_context.py \
  tests/test_coreference_resolver.py \
  tests/test_inventory_intelligence.py::test_inventory_memory_resolver_uses_reference_but_ignores_new_explicit_request \
  tests/test_inventory_intelligence.py::test_inventory_memory_resolver_handles_banglish_followups \
  tests/test_image_search_ask.py \
  tests/test_preference_learner.py \
  tests/test_boundary_enrichment.py \
  tests/test_image_matching.py \
  -q
```

## What This Proves

This proves the memory policy is now much safer at the intent-routing level:

- It can carry product focus through normal follow-ups.
- It survives off-topic and sensitive detours.
- It handles Bangla/Banglish/English follow-ups.
- It refuses to let stale context override fresh product intent.
- It expires product focus.
- It does not promote unsafe topics into shopping preferences.

## What This Does Not Prove Yet

This does not prove the full chat answer quality is perfect.

The current harness validates memory policy, hydration, and resolver behavior. The next serious test should replay 100 full API chat flows and judge the actual customer-facing answer text, product cards, and catalog grounding.

## Next Task

Build an API-level multi-turn evaluator:

```text
100 scripted sessions
  -> call /inventory/ask
  -> inspect final answer text
  -> inspect product cards
  -> inspect focused_product_ids
  -> inspect memory metadata
  -> score whether the answer follows the intended shopping flow
```

That is the next level from "memory engine is safe" to "customer chat feels natural."
