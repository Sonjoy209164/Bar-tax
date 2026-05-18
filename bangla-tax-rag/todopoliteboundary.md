# TODO: Polite Boundary And Smart Redirection Layer

## Safety Upgrade Note

The first-pass MVP labels in this file have now been hardened into the production taxonomy described in `todo_notrelated.md`.

Current implementation uses safer labels such as:

- `romantic_off_topic`
- `occasion_wedding`
- `gift_recommendation`
- `emotional_low_mood`
- `medical_or_health_advice`
- `legal_advice`
- `political`
- `self_harm_or_crisis`
- `abusive_mild`
- `abusive_severe`
- `vague_shopping`

Safety rule now enforced in code:

```text
real product/order/business query
  -> normal inventory pipeline

crisis / medical / legal / political / abuse
  -> safe guardrail response

harmless off-topic / romantic / vague / event
  -> short friendly redirect toward shopping
```

The most important protection is:

```text
Do not steal concrete product queries.
```

Example that must continue to inventory search:

```text
amar biyete porar jonno saree under 5000 dekhan
date er jonno perfume ache?
Dhaka delivery charge koto?
which products should I restock?
```

## Goal

Build a business-safe conversation layer for the ecommerce bot so it can handle off-topic, joking, emotional, romantic, vague, or event-based messages smoothly.

The bot should not answer every irrelevant question directly. It should:

```text
understand the user tone
  -> set a polite boundary when needed
  -> detect hidden shopping intent
  -> redirect toward products, categories, gifts, outfits, prices, delivery, or orders
```

The goal is not to sound robotic.

The goal is to sound like a helpful salesperson who knows when to play along lightly, when to redirect, and when to turn casual talk into a shopping journey.

## Core Principle

```text
Friendly acknowledgement
  -> clear business-safe boundary
  -> useful shopping redirection
```

Bad:

```text
Sorry, I do not understand.
```

Better:

```text
I may not be able to help with that directly, but I can help you find the right product for the situation.
```

Best:

```text
I cannot help you find a girlfriend, but I can help you choose a perfume, outfit, watch, or gift that makes a good impression.
```

## Target User Cases

- [x] Pure joke or irrelevant message.
  - Example: `amar ekta gf lagbe`
  - Desired behavior: light acknowledgement + redirect to gift/outfit/perfume.

- [x] Hidden shopping intent.
  - Example: `amar ekta biyete jaowa dorkar`
  - Desired behavior: treat as wedding shopping occasion.

- [x] Emotional but safe message.
  - Example: `amar mon kharap`
  - Desired behavior: empathetic reply + self-care/gift/product suggestions.

- [x] Romantic/flirty message to bot.
  - Example: `tumi ki amar sathe prem korba`
  - Desired behavior: polite boundary + redirect to gifts for someone special.

- [x] Celebration/event message.
  - Example: `ajke amar birthday`
  - Desired behavior: birthday outfit/gift/self-purchase suggestions.

- [x] Vague lifestyle message.
  - Example: `ami office e jai, ki nibo`
  - Desired behavior: office outfit/bag/shoes/perfume recommendations.

- [x] Unsafe or abusive message.
  - Desired behavior: short boundary; do not escalate; redirect only if appropriate.

## Conversation Classes

- [x] Add `off_topic_joke`.
  - Purpose: harmless irrelevant messages.
  - Example: `gf lagbe`, `tomar boyosh koto`, `tumi ki real`.

- [x] Add `event_need`.
  - Purpose: event mention that implies shopping.
  - Example: wedding, birthday, office, Eid, Puja, date, interview, travel.

- [x] Add `gift_need`.
  - Purpose: user needs product for someone else.
  - Example: `gf er jonno gift`, `husband er jonno perfume`, `friend er birthday`.

- [x] Add `emotional_need`.
  - Purpose: user expresses mood; respond with empathy and product-safe options.
  - Example: `mon kharap`, `nijer jonno kichu nibo`.

- [x] Add `romantic_boundary`.
  - Purpose: user flirts with bot or asks for relationship.
  - Example: `prem korba`, `gf lagbe`, `bf lagbe`.

- [x] Add `unsafe_or_abusive`.
  - Purpose: protect brand tone and avoid harmful engagement.

## Intent Detection Rules

- [x] Detect event words.
  - Bangla/Banglish:
    - `biye`, `biyete`, `wedding`, `eid`, `puja`, `birthday`, `office`, `interview`, `date`, `party`, `tour`, `travel`
  - Action: route to occasion-based recommendation.

- [x] Detect relationship/joke words.
  - Bangla/Banglish:
    - `gf`, `girlfriend`, `bf`, `boyfriend`, `prem`, `date korba`, `biye korba`
  - Action: playful boundary + shopping redirect.

- [x] Detect gift words.
  - Bangla/Banglish:
    - `gift`, `upohar`, `present`, `birthday gift`, `gf er jonno`, `wife er jonno`, `husband er jonno`
  - Action: ask recipient, budget, occasion.

- [x] Detect mood words.
  - Bangla/Banglish:
    - `mon kharap`, `sad`, `bhalo lagche na`, `nijer jonno kichu`
  - Action: empathetic product suggestions.

- [x] Detect unsupported topic.
  - Examples:
    - politics, medical/legal advice, romantic advice, personal relationship resolution
  - Action: boundary + product-safe redirect.

## Response Policy

- [x] Keep off-topic replies short.
  - Purpose: do not reward irrelevant long conversations.

- [x] Never shame the customer.
  - Purpose: ecommerce tone should stay friendly.

- [x] Do not pretend the bot can solve non-commerce problems.
  - Purpose: avoid false capability.

- [x] Always redirect toward one of:
  - products
  - categories
  - gifts
  - outfits
  - accessories
  - budget
  - event
  - order/delivery/payment

- [x] If a message contains an occasion, treat it as a recommendation opportunity.
  - Example: `amar ekta biyete jaowa dorkar`
  - This is not irrelevant. This is a shopping signal.

- [x] If the user is joking, answer lightly once, then redirect.
  - Do not continue romantic or irrelevant roleplay.

## Template Library

### Pure Joke

User:

```text
amar ekta gf lagbe
```

Reply:

```text
Girlfriend khuje dite parbo na, but impress korar jonno ekta smart perfume, outfit, watch, ba gift suggest korte pari.
```

### Wedding Occasion

User:

```text
amar ekta biyete jaowa dorkar
```

Reply:

```text
Perfect, wedding er jonno outfit, shoes, perfume, bag, ba gift suggest korte pari. Apni guest, close friend, naki family side?
```

### Romantic Boundary

User:

```text
tumi ki amar sathe prem korba?
```

Reply:

```text
Ami shopping help er jonno achi, dating er jonno na. But someone special ke impress korar jonno gift ba outfit choose korte help korte pari.
```

### Birthday

User:

```text
ajke amar birthday
```

Reply:

```text
Happy birthday! Nijer jonno outfit, perfume, watch, bag, ba gift-style kichu dekhate pari. Budget koto rakhben?
```

### Emotional But Safe

User:

```text
amar mon kharap
```

Reply:

```text
Sorry je emon feel korchen. Nijer jonno comforting kichu, perfume, self-care item, ba simple outfit suggest korte pari.
```

### Unsupported Topic

User:

```text
amar relationship problem solve kore dao
```

Reply:

```text
Eta niye direct advice dite parbo na, but gift, outfit, ba thoughtful kichu choose korte help korte pari.
```

## Prompt Rule To Add

```text
If the user asks an off-topic or casual question, respond warmly in one short sentence, then redirect toward relevant products, prices, categories, gifts, outfits, or shopping help.

If the message contains a possible buying occasion such as wedding, birthday, date, Eid, office, interview, travel, party, gift, or family event, treat it as a product recommendation opportunity.

Do not give long unrelated answers. Do not flirt, roleplay romance, discuss politics, or provide non-shopping advice. Keep the tone friendly, brand-safe, and commercially useful.
```

## Implementation Plan

### Phase 1: Classifier

- [x] Add polite-boundary categories to intent detection.
  - Target files:
    - `app/inventory/polite_boundary.py`
    - `app/services/inventory_service.py`
  - Note: implemented as a fast pre-retrieval business-boundary classifier, not through the slower LLM planner.

- [x] Add rule-based Bangla/Banglish keyword detection.
  - Target file:
    - `app/inventory/polite_boundary.py`

- [x] Keep LLM classifier optional.
  - Purpose: simple jokes/events should not require slow LLM calls.

### Phase 2: Response Generator

- [x] Add polite-boundary response helper.
  - Suggested file:
    - `app/inventory/polite_boundary.py`

- [x] Add template responses by class.
  - Classes:
    - `off_topic_joke`
    - `event_need`
    - `gift_need`
    - `emotional_need`
    - `romantic_boundary`
    - `unsafe_or_abusive`

- [x] Route event/gift cases into product recommendation.
  - Target file:
    - `app/services/inventory_service.py`

### Phase 3: Product Redirection

- [x] Map event types to product categories.
  - Wedding:
    - saree, panjabi, shirt, shoes, perfume, bag, jewelry, watch, gift
  - Birthday:
    - gift, perfume, watch, bag, cosmetics, outfit
  - Office:
    - shirt, pant, bag, shoes, watch, perfume
  - Date:
    - outfit, perfume, watch, gift

- [x] Ask one useful narrowing question.
  - Examples:
    - `Budget koto?`
    - `Apni male/female outfit khujchen?`
    - `Simple naki premium look?`
    - `Gift naki nijer jonno?`

### Phase 4: Memory

- [x] Store occasion in conversation memory.
  - Example:
    - `occasion = wedding`

- [x] Store recipient if mentioned.
  - Example:
    - `recipient = girlfriend`

- [ ] Store budget if mentioned.
  - Example:
    - `budget_max = 3000`

- [ ] Use memory in follow-up.
  - Example:
    - User: `amar biyete jaowa dorkar`
    - Bot: asks budget.
    - User: `5000 er moddhe`
    - Bot: recommends wedding guest products under 5000.

### Phase 5: Tests

- [x] Add tests for pure joke redirect.
  - Example:
    - `amar ekta gf lagbe`

- [x] Add tests for event intent expansion.
  - Example:
    - `amar ekta biyete jaowa dorkar`

- [x] Add tests for romantic boundary.
  - Example:
    - `tumi ki amar sathe prem korba`

- [x] Add tests for emotional safe redirect.
  - Example:
    - `amar mon kharap`

- [x] Add tests for Bangla/Banglish/English variants.

## Evaluation Examples

```json
{
  "query": "amar ekta gf lagbe",
  "expected_class": "romantic_boundary",
  "must_include_intent": "gift_or_style_redirect",
  "must_not_include": ["romantic roleplay", "relationship advice"]
}
```

```json
{
  "query": "amar ekta biyete jaowa dorkar",
  "expected_class": "event_need",
  "expected_redirect_categories": ["outfit", "shoes", "perfume", "bag", "gift"],
  "must_ask": ["budget or role or style preference"]
}
```

```json
{
  "query": "ajke amar birthday",
  "expected_class": "event_need",
  "expected_tone": "warm",
  "expected_redirect_categories": ["gift", "outfit", "perfume", "watch", "bag"]
}
```

## Definition Of Done

- [x] Bot does not reply `I do not understand` for harmless casual messages.
- [x] Bot handles jokes with one friendly redirect.
- [x] Bot turns event messages into shopping journeys.
- [x] Bot keeps romantic/flirty messages brand-safe.
- [x] Bot asks one useful next question after redirection.
- [ ] Bot remembers event, budget, recipient, and product category in follow-up.
- [x] Tests cover Bangla, Banglish, and English cases.

## Strategic Warning

Do not overbuild this into a general companion chatbot.

The ecommerce bot should be:

```text
warm enough to feel human
bounded enough to protect the brand
smart enough to convert vague situations into shopping intent
```

That is the business-standard behavior.
