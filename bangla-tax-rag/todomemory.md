# TODO: Industry-Standard Flow Memory

## Product Goal

Make the chatbot behave like a trained ecommerce salesperson:

```text
User asks for a product
Bot answers from catalog
User adds details
Bot keeps the product context and refines the answer
```

The bot should not ask unnecessary clarification questions. It should answer first when the catalog gives enough evidence.

## Current Failure

Bad flow:

```text
User: do you have Salwar Kameez?
Bot: What occasion is the kurti for, and any preferred color?
User: wedding,red
Bot: recommends Formal Shoe and Jute Bag
```

Why this is wrong:

- The bot confused `Salwar Kameez` with weaker `kameez/kurti` context.
- It asked a clarification even though the category was clear.
- It treated `wedding,red` as a generic occasion request instead of a slot update for Salwar Kameez.
- It allowed broad occasion recommendations to override active product flow.

Correct flow:

```text
User: do you have Salwar Kameez?
Bot: shows Salwar Kameez options from catalog
User: wedding,red
Bot: filters/refines Salwar Kameez by wedding + red
```

## Architecture Target

Use a flow-based memory controller before retrieval and answer generation.

```text
Incoming user text
  -> Conversation Flow Controller
  -> Memory policy
  -> Slot/filter hydration
  -> Product/category retrieval
  -> Catalog-grounded answer
```

## Flow Decisions

- [ ] `START_NEW_FLOW`
  - User names a new product/category.
  - Example: `red saree dekhao`, `do you have Salwar Kameez?`

- [ ] `CONTINUE_FLOW`
  - User refers to current product/list.
  - Example: `etar dam koto?`, `second one er size ache?`

- [ ] `UPDATE_FLOW_SLOTS`
  - User adds color, occasion, budget, or size after a category is already active.
  - Example: `wedding, red`, `under 3000`, `M size`

- [ ] `CLEAR_PRODUCT_FOCUS`
  - User switches category.
  - Example: after saree flow, user says `black sandal ache?`

- [ ] `SUPPORT_ROUTE`
  - Delivery/order/payment questions should not overwrite product memory.
  - Example: `delivery charge koto?`

- [ ] `SAFETY_ROUTE`
  - Medical/legal/crisis/abuse should not write shopping preferences.

## Implementation Checklist

### Phase 1: Flow Controller

- [x] Add `app/inventory/conversation_flow.py`.
- [x] Detect slot-only updates:
  - colors: red, blue, black, white, etc.
  - occasions: wedding, birthday, eid, office, casual, etc.
  - budget: under 3000, 5000 er moddhe
  - size: M, L, XL, 38, 40
- [x] Block slot continuation for support/safety/off-topic text.
- [x] Continue flow only if state has active `category_key`.

### Phase 2: Hydration

- [x] In `hydrate_request_from_state`, if the user sends slot-only text and the state has an active category, inject the category into request filters.
- [x] Preserve active slots in conversation summary.
- [x] Do not restore stale product focus if TTL expired.
- [x] Do not let old category override explicit new category.

### Phase 3: Boundary Routing

- [x] If active category exists and the current message is a slot update, skip polite-boundary occasion handling.
- [x] Example: `wedding, red` should not become generic `occasion_wedding`.

### Phase 4: Clarification Policy

- [x] Stop asking unnecessary questions when category is clear.
- [x] For `do you have Salwar Kameez?`, show catalog options first.
- [x] Ask only when category is missing or no safe catalog answer can be produced.

### Phase 5: Regression Tests

- [x] `do you have Salwar Kameez?` returns Salwar Kameez products.
- [x] Follow-up `wedding, red` keeps Salwar Kameez category.
- [x] Follow-up does not recommend shoes/bags as primary.
- [x] `delivery charge koto?` does not overwrite product flow.
- [x] `rash er jonno medicine?` does not write shopping memory.
- [x] Category switch clears old flow.

## Definition Of Done

- [x] Bot answers direct product/category questions without unnecessary clarification.
- [x] Slot-only follow-ups refine the active product flow.
- [x] Support/safety/off-topic messages do not overwrite shopping state.
- [x] New category requests override old category.
- [x] Regression tests pass.

## Implemented Files

- `app/inventory/conversation_flow.py`
- `app/inventory/conversation_context.py`
- `app/services/inventory_service.py`
- `app/inventory/fashion_retail.py`
- `app/inventory/ontology.py`
- `tests/test_conversation_flow.py`
- `tests/test_conversation_context.py`
- `tests/test_fashion_retail.py`
- `tests/test_inventory_api.py`

## Current Verification

```bash
.venv/bin/python -m pytest \
  tests/test_conversation_flow.py \
  tests/test_conversation_context.py \
  tests/test_fashion_retail.py \
  tests/test_memory_policy.py \
  tests/test_inventory_api.py::test_inventory_ask_continues_category_flow_for_slot_only_refinement \
  tests/test_inventory_intelligence.py::test_inventory_memory_resolver_uses_reference_but_ignores_new_explicit_request \
  tests/test_inventory_intelligence.py::test_inventory_memory_resolver_handles_banglish_followups \
  tests/test_image_search_ask.py \
  tests/test_boundary_enrichment.py \
  -q
```

Result:

```text
67 passed
```

```bash
.venv/bin/python scripts/run_memory_flow_eval.py
```

Result:

```text
Memory flow eval: 100/100 passed
```
