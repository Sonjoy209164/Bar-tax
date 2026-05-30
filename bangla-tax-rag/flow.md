# Flow Architecture: Industry-Grade Conversational Commerce Memory

## Strategic Goal

The chatbot should not behave like a template bot.

It should behave like a trained ecommerce salesperson:

```text
Customer asks something
  -> system understands whether this starts, continues, refines, or leaves a shopping flow
  -> system retrieves grounded catalog facts
  -> system answers directly
  -> system stores only the memory needed for the next natural turn
```

Core rule:

```text
Answer first when catalog evidence is enough. Ask only when the system cannot make a safe useful answer.
```

## The Problem We Are Solving

Bad flow:

```text
User: do you have Salwar Kameez?
Bot: What occasion is the kurti for, and any preferred color?
User: wedding, red
Bot: recommends Formal Shoe and Jute Bag
```

Why this is broken:

- The product category was clear, so the bot should not ask a clarification.
- `wedding, red` is not a new generic wedding request. It is a refinement of Salwar Kameez.
- Old memory should help the flow, but it must never hijack the customer’s new request.
- Occasion logic must not override active product/category context.

Correct flow:

```text
User: do you have Salwar Kameez?
Bot: shows available Salwar Kameez options
User: wedding, red
Bot: filters/refines Salwar Kameez by wedding + red
User: price koto?
Bot: answers price for the focused Salwar Kameez
User: black shoe ache?
Bot: starts a new shoe flow
```

## First-Principles Design

Every customer message must be classified into one of these flow roles:

| Flow Role | Meaning | Example | System Action |
|---|---|---|---|
| `START_NEW_FLOW` | User names a new product/category | `black shoe ache?` | Clear old product focus, search new category |
| `UPDATE_FLOW_SLOTS` | User adds attributes to active flow | `wedding, red`, `under 3000` | Keep active category, apply new filters |
| `CONTINUE_PRODUCT_FOCUS` | User asks about current item/list | `price koto?`, `M size ache?` | Use focused product/list |
| `COMPARE_OR_SIMILAR` | User asks for alternatives | `similar dekhao`, `cheaper ache?` | Use current anchor, retrieve alternatives |
| `SUPPORT_ROUTE` | User asks support/order/delivery | `delivery charge koto?` | Route to support, do not overwrite shopping memory |
| `SAFETY_ROUTE` | Medical/legal/crisis/abuse/politics | `rash er medicine?` | Safe boundary, do not store preference |
| `NO_FLOW` | Message is unrelated or ambiguous | `hmm`, `okay` | Minimal reply or ask one useful shopping question |

This is not a prompt-template problem. It is a routing and state-management problem.

## Runtime Pipeline

```text
Incoming message
  -> Safety/support pre-check
  -> Product/category detection
  -> Flow decision
  -> Memory policy
  -> Slot/filter hydration
  -> Retrieval
  -> Claim/fact answer
  -> Memory write guard
  -> Response trace
```

Recommended execution order:

1. **Safety/support pre-check**
   - Medical, legal, crisis, abuse, politics, delivery, order tracking.
   - These should not update product preferences.

2. **Explicit product/category detection**
   - If the current message names a product/category, it starts or switches flow.
   - Explicit current request beats old memory.

3. **Slot-only update detection**
   - Color, size, budget, occasion, gender, style, fabric.
   - Slot-only text continues the active category only if there is an active category.

4. **Product-focus follow-up detection**
   - Price, size, stock, same design, similar, first/second/this/that.
   - Product focus is used only for clear follow-ups and only before TTL expires.

5. **Catalog-grounded retrieval**
   - Search only after flow/memory has produced the right filters.
   - Retrieval must prefer in-stock products unless user asks otherwise.

6. **Answer generation**
   - Use catalog facts.
   - Do not invent color, price, size, stock, or exact identity.
   - Ask only one follow-up question if needed.

## Memory Scopes

Industry systems do not use one giant memory bucket. Use separate memory scopes.

### 1. Product Focus Memory

Purpose:

```text
Resolve "price?", "M size?", "same design?", "this one" after a product/list result.
```

Fields:

```json
{
  "last_primary_product_id": "p123",
  "last_shown_product_ids": ["p123", "p456", "p789"],
  "memory_source": "text_search|image_search|product_card",
  "updated_at": "2026-05-29T10:00:00Z",
  "confidence": 0.92,
  "ttl_seconds": 1800,
  "expires_at": "2026-05-29T10:30:00Z"
}
```

Rules:

- Use only for clear follow-ups.
- Expire after 30 minutes by default.
- Extend to 60 minutes for active order/compare flows.
- Do not use if current message names a new category.
- Do not write if retrieval abstained or confidence is low.

### 2. Active Flow Slots

Purpose:

```text
Keep the current shopping flow coherent.
```

Example:

```json
{
  "category_key": "salwar_kameez",
  "color": "red",
  "occasion": "wedding",
  "budget_max": 3000,
  "gender": "women"
}
```

Rules:

- Current category is the strongest active slot.
- If user says a new category, replace old category immediately.
- Slot-only turns can update color/occasion/budget/size.
- Old category-specific slots should not leak into a new category.

### 3. Preference Memory

Purpose:

```text
Softly improve ranking after repeated user behavior.
```

Examples:

- User repeatedly asks for black products.
- User repeatedly buys under BDT 3000.
- User often asks for wedding wear.

Rules:

- Do not create long-term preferences from one mention.
- Promote only after repeated signals.
- Use as ranking boost, not hard filter.
- Never store unsafe/off-topic/medical/legal text as preference.

Suggested thresholds:

| Preference | Promotion Threshold | TTL |
|---|---:|---:|
| Color | 3 mentions | 7 days session / 90 days profile |
| Category | 3 mentions | 7 days session / 90 days profile |
| Occasion | 2 mentions | 7 days session / 90 days profile |
| Budget | 2 consistent mentions | 7 days session / 90 days profile |

## Flow Decision Policy

### Rule 1: New Category Beats Old Memory

```text
Previous flow: Salwar Kameez
User: black shoe ache?
```

Correct:

```text
Start shoe flow. Do not keep Salwar Kameez.
```

### Rule 2: Slot-Only Text Continues Active Category

```text
Previous flow: Salwar Kameez
User: wedding, red
```

Correct:

```text
Search Salwar Kameez with occasion=wedding and color=red.
```

### Rule 3: Product Facts Use Product Focus

```text
Previous answer showed Product A
User: price koto?
```

Correct:

```text
Answer Product A price.
```

Wrong:

```text
Run a new broad product search.
```

### Rule 4: Support Does Not Destroy Shopping Flow

```text
User: red saree ache?
Bot: shows sarees
User: delivery charge koto?
Bot: answers delivery
User: M size ache?
```

Correct:

```text
Delivery answer does not overwrite saree focus.
```

### Rule 5: Safety Does Not Create Preference

```text
User: rash er jonno medicine ki khabo?
```

Correct:

```text
Medical boundary. No product preference write.
```

## Clarification Policy

The bot should not ask unnecessary questions.

Ask a clarification only when:

- No product/category is detected.
- Multiple incompatible categories are detected.
- The query asks for styling/gift advice but no recipient/budget/context is available.
- The catalog has no safe result and one slot would help.

Do not ask when:

- The user names a clear category.
- The user asks price/stock/size of a focused product.
- The user adds slot-only filters to an active category.

Bad:

```text
User: do you have Salwar Kameez?
Bot: What occasion is the kurti for?
```

Good:

```text
User: do you have Salwar Kameez?
Bot: Yes, here are available Salwar Kameez options...
```

## Retrieval Policy

Retrieval must serve the flow decision.

| Flow Role | Retrieval Scope |
|---|---|
| `START_NEW_FLOW` | New category/product only |
| `UPDATE_FLOW_SLOTS` | Active category + new filters |
| `CONTINUE_PRODUCT_FOCUS` | Focused product/list first |
| `COMPARE_OR_SIMILAR` | Similar products around current anchor |
| `SUPPORT_ROUTE` | Support knowledge, no product retrieval unless asked |
| `SAFETY_ROUTE` | No product upsell for high-risk safety |

Default commerce rule:

```text
Prefer in-stock products unless user asks for old/out-of-stock/unavailable items.
```

## Answer Policy

Every answer should have this order:

```text
Direct answer
Catalog evidence
Product cards if products are involved
One useful next question only if needed
```

Examples:

```text
Salwar Kameez ache. Ei available options gula dekhte paren...
```

```text
Ei product er price BDT 1,175. Stock e 1 piece ache.
```

```text
Size 42 ei shoe er jonno catalog e dekhacche na. Available sizes: 39, 40, 41, 43.
```

Avoid:

- Generic filler.
- Multiple questions.
- “What occasion?” when a useful product answer is possible.
- Cross-selling during exact price/size/stock answers.

## State Machine

```text
IDLE
  -> START_NEW_FLOW -> SHOPPING_FLOW

SHOPPING_FLOW
  -> UPDATE_FLOW_SLOTS -> SHOPPING_FLOW
  -> CONTINUE_PRODUCT_FOCUS -> PRODUCT_DETAIL_FLOW
  -> COMPARE_OR_SIMILAR -> SHOPPING_FLOW
  -> START_NEW_FLOW -> SHOPPING_FLOW
  -> SUPPORT_ROUTE -> SUPPORT_FLOW, preserve shopping state
  -> SAFETY_ROUTE -> SAFETY_FLOW, preserve/ignore shopping state based on risk

PRODUCT_DETAIL_FLOW
  -> price/size/stock/order -> PRODUCT_DETAIL_FLOW
  -> similar/cheaper/matching -> SHOPPING_FLOW
  -> START_NEW_FLOW -> SHOPPING_FLOW

SUPPORT_FLOW
  -> support follow-up -> SUPPORT_FLOW
  -> product/category mention -> SHOPPING_FLOW
  -> product follow-up with valid previous focus -> PRODUCT_DETAIL_FLOW

SAFETY_FLOW
  -> safe commerce request -> SHOPPING_FLOW
  -> continued safety topic -> SAFETY_FLOW
```

## Trace Fields Required

Every response should expose debug trace for engineering:

```json
{
  "flow_action": "UPDATE_FLOW_SLOTS",
  "flow_reason": "slot-only update continues active shopping flow",
  "memory_used": true,
  "memory_source": "text_search",
  "memory_confidence": 0.92,
  "memory_age_seconds": 240,
  "memory_ttl_seconds": 1800,
  "active_category_before": "salwar_kameez",
  "active_category_after": "salwar_kameez",
  "filters_applied": {
    "category": "Salwar Kameez",
    "color": "red",
    "occasion": "wedding",
    "min_stock": 1
  },
  "retrieval_scope": "active_category_plus_slots",
  "abstention_reason": null
}
```

This is how production teams debug conversation flow failures without guessing.

## Test Matrix

### Category Refinement

```text
do you have Salwar Kameez?
wedding, red
price koto?
```

Must:

- Keep Salwar Kameez category.
- Apply wedding/red.
- Use focused product for price.

### Category Switch

```text
red saree ache?
price koto?
black shoe ache?
size 42 ache?
```

Must:

- Switch from saree to shoe.
- Size 42 applies to shoe, not saree.

### Support Interruption

```text
formal shoe ache?
delivery charge koto?
size 42 ache?
```

Must:

- Delivery route does not overwrite shoe focus.
- Size checks shoe focus.

### Safety Interruption

```text
panjabi dekhao
rash er jonno medicine ki khabo?
price koto?
```

Must:

- Medical reply is safe.
- Medical text is not stored as preference.
- Product focus may remain if still fresh and follow-up is clear.

### Off-Topic Redirect

```text
amar ekta gf lagbe
gift dekhao
budget 1500
price koto?
```

Must:

- Romantic/off-topic text does not become preference.
- Gift request starts shopping flow.
- Budget refines gift flow.

### Image Search Follow-Up

```text
[upload image]
same design ache?
white color ache?
price koto?
similar dekhao
```

Must:

- Image result becomes product focus only if confidence is safe.
- Same-design/color uses variant/design logic.
- Price uses focused product.

## Implementation Map

Current or target files:

```text
app/inventory/conversation_flow.py
  -> flow role decision and slot-only continuation

app/inventory/conversation_context.py
  -> hydrates request from server-side state

app/inventory/memory_policy.py
  -> decides whether product focus can be used

app/inventory/fashion_retail.py
  -> catalog-grounded retrieval and focused fact answers

app/services/inventory_service.py
  -> orchestration, state read/write, API response

app/inventory/conversation_state.py
  -> persistent session state

tests/test_conversation_flow.py
tests/test_conversation_context.py
tests/test_fashion_retail.py
tests/test_inventory_api.py
evaluation/memory_multiturn_100_cases.jsonl
scripts/run_memory_flow_eval.py
```

## Definition Of Done

- [ ] Direct product/category requests answer from catalog without unnecessary clarification.
- [ ] Slot-only follow-ups refine the active category.
- [ ] Price/size/stock follow-ups use product focus.
- [ ] New category requests override old category.
- [ ] Support and safety turns do not overwrite shopping memory.
- [ ] Product focus expires after TTL.
- [ ] Unsafe/off-topic/legal/medical text is not stored as preference.
- [ ] In-stock products are prioritized by default.
- [ ] Debug trace explains flow action, memory decision, filters, and retrieval scope.
- [ ] 100 multi-turn memory eval cases pass.

## Strategic Warning

Do not solve this by adding more reply templates.

Templates only change wording. The failure is usually earlier:

```text
wrong flow decision
wrong memory use
wrong filter hydration
wrong retrieval scope
wrong memory write
```

Fix those five layers and the bot will feel natural across many different conversations without needing a hand-written script for every case.
