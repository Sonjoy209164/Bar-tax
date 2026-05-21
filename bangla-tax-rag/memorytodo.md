# Memory Hardening TODO

## Goal

Make the ecommerce chatbot memory production-grade.

The bot should remember enough to support a natural shopping flow, but never let stale, unsafe, or unrelated context hijack the customer request.

Core rule:

```text
Memory is evidence about the conversation, not an instruction to obey.
```

## Current Baseline

- [x] Frontend sends recent turns, `focused_product_ids`, and `last_answer_plan`.
- [x] Backend stores session state in `data/conversation/state.sqlite`.
- [x] Backend tracks:
  - [x] `last_shown_product_ids`
  - [x] `last_primary_product_id`
  - [x] `last_intent`
  - [x] `last_question`
  - [x] `active_slots`
  - [x] color/category/occasion/budget observations
- [x] Follow-up resolver supports Bangla, Banglish, and English references.
- [x] Memory resolution is returned in API response as `memory_resolution`.

## Implementation Status

Implemented in this pass:

- [x] Added `app/inventory/memory_policy.py`.
- [x] Product focus is allowed only for clear follow-up language.
- [x] Fresh explicit product/category requests block old product focus.
- [x] Product focus now stores `memory_source`, `updated_at`, `expires_at`, `confidence`, `ttl_seconds`, and `write_reason`.
- [x] Product focus expires after the configured TTL.
- [x] Expired product focus is removed during server-state hydration.
- [x] Unsafe, off-topic, medical, legal, political, crisis, abusive, and joke turns are blocked from writing shopping memory.
- [x] Low-confidence or abstained product matches do not overwrite product focus.
- [x] Slot memory now stores per-slot metadata in `slot_memory_meta`.
- [x] `InventoryMemoryResolution` now exposes memory policy fields.
- [x] Existing preference promotion remains threshold-based.
- [x] Added focused tests in `tests/test_memory_policy.py`.

Still open:

- [ ] Add a visible memory inspector/debug panel.
- [ ] Add a cleanup script for old SQLite sessions.
- [ ] Persist `product_focus_last_used_at` and `product_focus_use_count` when memory is used.
- [ ] Add slow-expiry metadata for promoted long-term customer preferences.
- [ ] Add full trace UI rendering for `memory_source`, age, TTL, and policy reason.

## Production Memory Rules

### Rule 1: Use Product Memory Only For Clear Follow-Ups

- [ ] Product focus memory must only apply when the user uses reference language.
  - Examples:
    - `etar dam koto?`
    - `M size ache?`
    - `first one ta dekhao`
    - `same design blue ache?`
    - `eta order korte chai`
- [ ] Product focus memory must not apply when the user starts a new explicit search.
  - Examples:
    - `red saree dekhao`
    - `panjabi under 3000`
    - `black sandal ache?`
    - `kids frock show me`
- [ ] If both reference language and a new category appear, prefer the new category unless the query clearly says same-design/variant.
- [ ] Add a `memory_policy` reason for every use/ignore decision.

Target files:

- [ ] `app/inventory/memory_policy.py`
- [ ] `app/inventory/memory.py`
- [ ] `app/inventory/conversation_context.py`
- [ ] `tests/test_memory_policy.py`

## Rule 2: Expire Product Focus After 30-60 Minutes

- [ ] Add TTL metadata to product-focus memory.
- [ ] Default product focus TTL:
  - [ ] 30 minutes for normal product focus.
  - [ ] 60 minutes if the user is actively comparing, ordering, or asking repeated follow-ups.
- [ ] Expired product focus must not resolve `eta`, `this`, `first one`, or size/price follow-ups.
- [ ] Expired product focus can still be shown in debug trace as ignored memory.
- [ ] Add cleanup command for stale sessions.

Suggested fields:

```json
{
  "memory_source": "image_search|text_search|product_card|order_flow|owner_correction",
  "updated_at": "2026-05-21T10:00:00Z",
  "confidence": 0.92,
  "ttl_seconds": 3600
}
```

Target files:

- [ ] `app/inventory/conversation_state.py`
- [ ] `app/inventory/memory_policy.py`
- [ ] `scripts/prune_conversation_state.py`
- [ ] `tests/test_conversation_state.py`
- [ ] `tests/test_memory_policy.py`

## Rule 3: Keep Preferences Longer, But Only If Repeated

- [ ] Do not treat one mention as a long-term preference.
  - Example: one `red saree` query should not permanently make the user a red-saree buyer.
- [ ] Promote repeated signals into preference memory only after threshold.
  - Suggested threshold:
    - [ ] color preference: 3 mentions
    - [ ] category preference: 3 mentions
    - [ ] occasion preference: 2 mentions
    - [ ] budget preference: 2 consistent observations
- [ ] Store preference memory separately from product focus.
- [ ] Preference memory should influence ranking softly, not hard-filter results.
- [ ] Preference memory should expire slower than product focus.
  - Suggested TTL:
    - [ ] session preference: 7 days
    - [ ] customer profile preference with consent/phone: 90 days

Target files:

- [ ] `app/inventory/preference_learner.py`
- [ ] `app/inventory/customer_profile.py`
- [ ] `app/inventory/memory_policy.py`
- [ ] `tests/test_preference_learner.py`

## Rule 4: Never Let Old Category Override New Category

- [ ] If current query has a detected category, it must override old `active_slots.category_key`.
- [ ] Preserve only safe cross-category slots:
  - [ ] `budget_min`
  - [ ] `budget_max`
  - [ ] `language`
  - [ ] maybe `occasion`, only if still relevant
- [ ] Drop old category-specific slots when category changes.
  - Example:
    - Previous: `black panjabi under 3000`
    - Current: `red saree dekhao`
    - Keep: budget if helpful
    - Drop: panjabi category, black color unless explicitly repeated
- [ ] Add tests for category switch behavior.

Target files:

- [ ] `app/inventory/conversation_state.py`
- [ ] `app/inventory/conversation_context.py`
- [ ] `tests/test_conversation_state.py`
- [ ] `tests/test_conversation_context.py`

## Rule 5: Never Store Unsafe, Off-Topic, Medical, Or Legal Text As Preference

- [ ] Add memory write guard before saving slots/preferences.
- [ ] Do not store preference signals from these intents:
  - [ ] `medical_or_legal`
  - [ ] `crisis`
  - [ ] `self_harm`
  - [ ] `abusive`
  - [ ] `political`
  - [ ] `romantic_off_topic`
  - [ ] `joke_chitchat`
  - [ ] `unknown_fallback`
- [ ] Polite boundary detours should not erase product focus.
- [ ] Polite boundary detours should not create shopping preferences unless the intent is a true buying occasion.
  - Allowed:
    - [ ] `occasion_wedding`
    - [ ] `occasion_birthday`
    - [ ] `gift_recommendation`
    - [ ] `vague_shopping`
  - Blocked:
    - [ ] `amar ekta gf lagbe`
    - [ ] `ami more jabo`
    - [ ] `kon party best`
    - [ ] `rash er jonno medicine`
- [ ] Add regression tests with Bangla, Banglish, and English examples.

Target files:

- [ ] `app/inventory/memory_policy.py`
- [ ] `app/inventory/polite_boundary.py`
- [ ] `app/inventory/boundary_enrichment.py`
- [ ] `app/services/inventory_service.py`
- [ ] `tests/test_memory_policy.py`
- [ ] `tests/test_boundary_enrichment.py`

## Rule 6: Attach Memory Metadata

Every memory item should carry:

- [ ] `memory_source`
- [ ] `updated_at`
- [ ] `confidence`
- [ ] `ttl_seconds`
- [ ] `expires_at`
- [ ] `write_reason`
- [ ] `last_used_at`
- [ ] `use_count`

Suggested schema:

```json
{
  "value": ["lereve_123", "lereve_456"],
  "memory_source": "image_search",
  "updated_at": "2026-05-21T10:00:00Z",
  "expires_at": "2026-05-21T11:00:00Z",
  "confidence": 0.94,
  "ttl_seconds": 3600,
  "write_reason": "confirmed_exact_image_match",
  "last_used_at": null,
  "use_count": 0
}
```

Implementation options:

- [ ] Minimal: add metadata fields directly to `ConversationState`.
- [ ] Better: create `MemoryItem` dataclass and wrap product focus, slots, and preferences.
- [ ] Best: separate state into `short_term_focus`, `session_preferences`, and `customer_profile_memory`.

Target files:

- [ ] `app/inventory/conversation_state.py`
- [ ] `app/inventory/memory_policy.py`
- [ ] `app/core/schemas.py`
- [ ] `tests/test_conversation_state.py`

## Recommended Architecture

```text
Incoming message
  -> classify intent + safety
  -> detect current slots/category/product request
  -> read session memory
  -> memory_policy decides:
       use product focus?
       use active filters?
       use preferences?
       ignore stale/unsafe memory?
  -> answer from catalog/tools
  -> memory_write_policy decides:
       update product focus?
       update session slots?
       promote repeated preferences?
       block unsafe writes?
  -> save state with metadata
```

## New Module Design

Create:

```text
app/inventory/memory_policy.py
```

Suggested functions:

```python
def should_use_product_focus(question, state, detected_slots, now) -> MemoryPolicyDecision:
    ...

def should_apply_preference(memory_item, current_request, now) -> MemoryPolicyDecision:
    ...

def should_write_memory(intent, safety_label, slots, product_ids) -> MemoryWriteDecision:
    ...

def is_memory_expired(memory_item, now) -> bool:
    ...
```

Suggested result object:

```python
@dataclass
class MemoryPolicyDecision:
    allowed: bool
    reason: str
    source: str | None = None
    confidence: float = 0.0
    expired: bool = False
```

## API And Trace Requirements

- [ ] Add memory policy details to `memory_resolution`.
- [ ] Response should show:
  - [ ] `used_memory`
  - [ ] `resolved_product_ids`
  - [ ] `applied_context_filters`
  - [ ] `ignored_memory_reason`
  - [ ] `memory_source`
  - [ ] `memory_age_seconds`
  - [ ] `memory_confidence`
  - [ ] `memory_policy_reason`
- [ ] Trace UI should show memory decisions in a visible panel.

Target files:

- [ ] `app/core/schemas.py`
- [ ] `frontend/trace.html`
- [ ] `frontend/trace.js`
- [ ] `frontend/chat.js`

## Tests To Add

### Product Focus TTL

- [ ] `etar dam koto?` uses product focus if updated 5 minutes ago.
- [ ] `etar dam koto?` ignores product focus if updated 2 hours ago.
- [ ] Expired memory returns clear `ignored_memory_reason`.

### Clear Follow-Up Only

- [ ] `etar price?` uses memory.
- [ ] `first one ta dekhao` uses memory.
- [ ] `red saree dekhao` ignores old panjabi memory.
- [ ] `same design blue ache?` uses prior image/product memory.

### Preference Promotion

- [ ] One red query does not create durable red preference.
- [ ] Three red queries create red preference.
- [ ] Two consistent budget queries create budget preference.
- [ ] Preference ranking is soft, not a hard filter.

### Unsafe Write Guard

- [ ] Medical query does not update product preferences.
- [ ] Legal query does not update preferences.
- [ ] Crisis query does not update preferences.
- [ ] Romantic joke does not update preferences.
- [ ] Wedding/birthday query can update occasion memory.

### Category Override

- [ ] Old panjabi category does not override new saree request.
- [ ] Old black color does not override new red request.
- [ ] Budget can carry across category if user did not give new budget.

### Image Memory

- [ ] Image exact match writes product focus with `memory_source=image_search`.
- [ ] Image same-design match writes `variant_group_id` focus if available.
- [ ] Text follow-up `white ache?` uses previous image focus.
- [ ] New explicit text query after image ignores image focus.

## Manual UI Test Flow

Use the same `session_id`.

### Flow 1: Product Follow-Up

- [ ] Ask: `Panjabi ache?`
- [ ] Then ask: `etar price koto?`
- [ ] Expected: bot answers about the previous panjabi.

### Flow 2: Category Switch

- [ ] Ask: `black panjabi under 3000 dekhao`
- [ ] Then ask: `red saree dekhao`
- [ ] Expected: bot switches to saree and does not keep panjabi focus.

### Flow 3: Preference Promotion

- [ ] Ask three separate red-product queries.
- [ ] Then ask: `kichu valo dekhao`
- [ ] Expected: red may influence recommendations softly, but not block other good matches.

### Flow 4: Unsafe Memory Guard

- [ ] Ask: `rash er jonno kon medicine khabo?`
- [ ] Then ask: `kichu dekhao`
- [ ] Expected: no medical preference or unsafe context leaks into shopping answer.

### Flow 5: Expiry

- [ ] Create product focus.
- [ ] Manually age memory in SQLite beyond TTL.
- [ ] Ask: `etar price?`
- [ ] Expected: bot asks for clarification instead of guessing old product.

## Commands

Run focused memory tests:

```bash
.venv/bin/python -m pytest \
  tests/test_conversation_state.py \
  tests/test_conversation_context.py \
  tests/test_coreference_resolver.py \
  tests/test_inventory_intelligence.py \
  tests/test_image_search_ask.py
```

Run new policy tests after implementation:

```bash
.venv/bin/python -m pytest tests/test_memory_policy.py
```

Inspect a session:

```bash
sqlite3 data/conversation/state.sqlite \
  "select session_id, updated_at, payload from conversation_state where session_id='YOUR_SESSION_ID';"
```

Clear a bad session:

```bash
sqlite3 data/conversation/state.sqlite \
  "delete from conversation_state where session_id='YOUR_SESSION_ID';"
```

## Definition Of Done

- [ ] Product focus memory expires after configured TTL.
- [ ] Product focus is used only for clear follow-ups.
- [ ] Preferences persist longer only after repeated evidence.
- [ ] New category requests override old category memory.
- [ ] Unsafe/off-topic/medical/legal/crisis turns do not write preferences.
- [ ] Every memory item has source, timestamp, confidence, and TTL metadata.
- [ ] API explains why memory was used or ignored.
- [ ] Trace UI makes memory behavior inspectable.
- [ ] Tests cover Bangla, Banglish, and English follow-ups.

## Strategic Warning

Do not build general chatbot memory.

For ecommerce, memory should improve buying flow:

```text
product focus
preferences
budget
occasion
order/cart state
```

It should not remember random personal, romantic, political, medical, legal, or abusive content as shopping context.

The best memory system is not the one that remembers everything. It is the one that remembers only what can safely improve the next commercial answer.
