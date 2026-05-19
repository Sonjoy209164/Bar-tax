# to_doimprove.md — Polite Boundary & Conversation Layer

Goal: stop growing [app/inventory/polite_boundary.py](app/inventory/polite_boundary.py) by adding more keyword tuples. Move from a regex/if-else cascade to a layered hybrid that is safety-first for crisis topics and LLM-driven for normal customer language — so the bot stops feeling like a keyword matcher and starts feeling like a salesperson.

---

## 1. Architecture diagnosis (what is wrong today)

- [x] Audit current state — done. Findings:
  - [polite_boundary.py](app/inventory/polite_boundary.py) is ~1200 lines, of which ~470 are flat keyword tuples (`EVENT_KEYWORDS`, `GIFT_KEYWORDS`, `RELATIONSHIP_KEYWORDS`, `IMPRESSION_SHOPPING_KEYWORDS`, `EMOTIONAL_KEYWORDS`, `SELF_HARM_KEYWORDS`, `POLITICAL_KEYWORDS`, `MEDICAL_ADVICE_KEYWORDS`, `LEGAL_ADVICE_KEYWORDS`, `MILD_ABUSIVE_KEYWORDS`, `SEVERE_ABUSIVE_KEYWORDS`, `VAGUE_SHOPPING_KEYWORDS`, `PERSONAL_BOT_KEYWORDS`, `RANDOM_TECH_KEYWORDS`, `CONCRETE_PRODUCT_TERMS`, `SUPPORT_ACTION_TERMS`, `PAYMENT_SUPPORT_KEYWORDS`, `ORDER_TRACKING_KEYWORDS`, …).
  - `classify_polite_boundary` is one long ordered if/elif on `_has_any(text, X_KEYWORDS)` — first match wins, no calibrated scoring.
  - ~600 lines of hand-written reply templates per `boundary_type × language` (`bangla`, `banglish`, `english`) — no personalization, no use of the catalog.
  - [scripts/run_offtopic_boundary_500_eval.py](scripts/run_offtopic_boundary_500_eval.py) generates cases from string templates with the **same vocabulary** the regex was authored for. The 500-case eval validates that the regex matches itself — it does not measure customer reality.
  - Boundary layer runs in [app/services/inventory_service.py:963](app/services/inventory_service.py#L963), **before** the existing LLM intent classifier in [app/inventory/llm_intent_classifier.py](app/inventory/llm_intent_classifier.py). The LLM is never consulted for off-topic / chitchat / romantic / emotional routing.

- [ ] Write a one-page "current vs. target" diff in [docs/conversation_layer_architecture.md](docs/conversation_layer_architecture.md) so reviewers see the shift before reading code.

---

## 2. Target architecture

```text
user message
  │
  ▼
[Layer 1] safety rules (regex-first, narrow)
  - self-harm / crisis
  - explicit threats / severe abuse
  - explicit medical / legal advice ask
  - explicit political ask
  → high-recall, hand-curated, locked behind tests. Cannot be overridden by LLM.
  │ miss
  ▼
[Layer 2] LLM intent + boundary classifier (single call)
  - returns: intent, sub_intent (off_topic/chitchat/romantic/emotional/gift/occasion/vague/...)
  - returns: shopping_intent_score, sensitive_flag, language, slots, confidence
  - reuses the existing Ollama infra in app/inventory/llm_intent_classifier.py
  │
  ▼
[Layer 3] policy router (deterministic, tiny)
  - high confidence shopping → existing inventory pipeline
  - boundary cases → templated reply, possibly LLM-rewritten for warmth
  - low confidence → ask clarifying question, never guess
  │
  ▼
[Layer 4] reply renderer
  - structured template (safety guarantee) + LLM polish (humanness)
  - catalog-aware: pull 2-3 real product picks from inventory when redirecting
  - feedback hooks attached to every reply
```

Rule: **regex only owns Layer 1.** Layers 2-4 own everything else. Adding a new keyword tuple is now a code smell.

- [ ] Document the four layers in [docs/conversation_layer_architecture.md](docs/conversation_layer_architecture.md) with one example trace per layer.

---

## 3. Phase 1 — collect real customer language

Synthetic eval is a self-test. Real traffic is the only ground truth.

- [ ] Add a logging sink in [app/services/inventory_service.py](app/services/inventory_service.py) `_try_polite_boundary_ask` that writes every boundary trigger to `data/conversation_logs/raw_offtopic.jsonl` with: `{ts, question, language, decided_boundary_type, decided_confidence, was_handed_off}`. Strip PII (phone, order id, email) before write.
- [ ] Pull existing UI/chat history into the same file from whatever log store the frontend uses (check [frontend/](frontend/) for log endpoints).
- [ ] Stop at 300 real messages minimum, 1000 target. Don't label until you have ≥300.
- [ ] Label into `evaluation/offtopic_real_labeled.jsonl` with this row schema (no extra fields, kept stable for CI):
  ```json
  {
    "id": "real_0001",
    "question": "...",
    "language": "bangla|banglish|english|mixed",
    "expected_intent": "...",
    "expected_reply_type": "redirect|empathy|refusal|playful|clarify|continue_to_inventory",
    "risk_level": "low|medium|high|critical",
    "should_redirect_to_shopping": true,
    "should_recommend_categories": ["..."],
    "notes": "..."
  }
  ```
- [ ] Write the labeling brief in [evaluation/labeling_guide.md](evaluation/labeling_guide.md) — taxonomy definitions, edge-case rules, two annotators for a 50-case agreement check.

---

## 4. Phase 2 — replace the cascade with a hybrid router

- [ ] Carve [app/inventory/polite_boundary.py](app/inventory/polite_boundary.py) into three modules:
  - [ ] `app/inventory/safety_rules.py` — only crisis / severe-abuse / explicit medical / explicit legal / explicit political. Keep regex, keep tests. Target ≤200 lines.
  - [ ] `app/inventory/boundary_classifier.py` — LLM-first classifier, fallback to a tiny embedding nearest-neighbour over `evaluation/offtopic_real_labeled.jsonl` (no new keyword tuples). Reuse the Ollama transport in [app/inventory/llm_intent_classifier.py](app/inventory/llm_intent_classifier.py).
  - [ ] `app/inventory/boundary_templates.py` — pure reply rendering, language-aware, takes a structured `BoundaryDecision` and returns text + optional catalog picks. No detection logic.
- [ ] Delete the keyword tuples that are no longer referenced (`EVENT_KEYWORDS`, `GIFT_KEYWORDS`, `RELATIONSHIP_KEYWORDS`, `IMPRESSION_SHOPPING_KEYWORDS`, `EMOTIONAL_KEYWORDS`, `VAGUE_SHOPPING_KEYWORDS`, `PERSONAL_BOT_KEYWORDS`, `RANDOM_TECH_KEYWORDS`, `_looks_like_casual_offtopic`). Keep the safety ones.
- [ ] Extend the LLM prompt in [llm_intent_classifier.py](app/inventory/llm_intent_classifier.py) (or a sibling prompt) with boundary sub-intents: `off_topic_chitchat`, `romantic_off_topic`, `impression_shopping`, `emotional_low_mood`, `vague_shopping`, `personal_question_about_bot`, `random_tech`. Add few-shot examples drawn from the real labeled set, not from authors' imagination.
- [ ] Add a `shopping_intent_score` field (0-1) so the router can let high-score messages flow into the normal inventory pipeline even if a sub-intent fired.
- [ ] Cache LLM classifications by normalized question hash for 24h to bound cost.
- [ ] Define the fallback chain explicitly: `safety_rules → LLM classify → embedding kNN → "ask one clarifying question"`. Never silently drop into a hardcoded boundary type.

---

## 5. Phase 3 — make replies feel human, not templated

- [ ] Move the per-language template walls in `_template()` out of code into [config/boundary_templates.yaml](config/boundary_templates.yaml). One row per `boundary_type × language`, with slots for `{recipient}`, `{occasion}`, `{categories}`, `{products}`.
- [ ] Add a `boundary_response_renderer` that:
  - [ ] Pulls 2-3 real product cards from the catalog when the decision has `recommended_categories` (use the existing inventory search, not a fresh keyword search).
  - [ ] Optionally passes the structured decision + template skeleton through the LLM for tone polish in customer language, then runs a deterministic safety check (no medical/legal claims, no political stance, no crisis dismissal) before sending.
- [ ] For category-specific tone, define playbooks once in YAML, not in code:
  - [ ] romantic → playful redirect
  - [ ] birthday / wedding → product recommendation with catalog picks
  - [ ] sad mood → empathy first, then soft self-care suggestion
  - [ ] abuse → calm one-line boundary, no escalation
  - [ ] politics → neutral redirect, no opinions
  - [ ] medical / legal → safe refusal, suggest professional, no product upsell
  - [ ] vague shopping → ask budget + purpose, then suggest

---

## 6. Phase 4 — score response quality, not just intent match

Today's eval reports "intent correct". That misses everything the boss/customer actually cares about.

- [ ] Add [scripts/score_response_quality.py](scripts/score_response_quality.py) that scores every reply against the real labeled set on:
  - [ ] **Intent match** (boolean)
  - [ ] **Risk level match** (boolean, weighted 3× — getting risk wrong is the worst failure)
  - [ ] **Sounded human** (LLM judge, 0-1)
  - [ ] **Protected the brand** (LLM judge, 0-1: neutral on politics, no medical claims, no abuse back)
  - [ ] **Redirected toward shopping** (LLM judge, 0-1: only when `should_redirect_to_shopping` is true)
  - [ ] **Did not impersonate a general chatbot** (LLM judge, 0-1)
  - [ ] **No unsafe advice** (rule-checked first, then LLM judge)
- [ ] Use a strong model (Claude Sonnet 4.6 or better) as the judge with a fixed rubric; cache verdicts by `(question_hash, reply_hash)`.
- [ ] Emit per-category scorecards so we see where we are weak (eg. "emotional: human 0.4, brand 0.9, redirect 0.3 → too cold").
- [ ] Set merge gates: composite ≥0.85, no category <0.7, risk match =1.0 on critical/high.

---

## 7. Phase 5 — real regression in CI

- [ ] Add [tests/test_offtopic_real_regression.py](tests/test_offtopic_real_regression.py) that loads `evaluation/offtopic_real_labeled.jsonl` and asserts intent + risk match. Fails the build on regression.
- [ ] Add a nightly job that runs the response-quality scorer against the real set and posts a one-line diff vs. yesterday to the team channel.
- [ ] Keep the existing tests but reframe:
  - [ ] [tests/test_polite_boundary.py](tests/test_polite_boundary.py) → covers Layer 1 safety rules only (crisis, severe abuse, explicit medical/legal/political).
  - [ ] [scripts/run_offtopic_boundary_500_eval.py](scripts/run_offtopic_boundary_500_eval.py) → kept for synthetic smoke, but downgraded from a quality signal to a sanity check. Document this in its header.

---

## 8. Phase 6 — feedback loop from the UI

- [ ] Add a `/feedback` endpoint that accepts `{trace_id, verdict: "good|bad", expected_reply?, expected_intent?}`. Persist into `data/conversation_logs/feedback.jsonl`.
- [ ] Surface a 👍 / 👎 affordance in the frontend reply bubble (whatever currently lives in [frontend/](frontend/) — find the message component and wire it in).
- [ ] Weekly cron: convert 👎 rows + corrections into new labeled rows in `evaluation/offtopic_real_labeled.jsonl`, with an `origin: feedback` tag.
- [ ] Track the bad-reply rate per `boundary_type` per week. If it climbs week-over-week for a type, that type's prompt or template needs work.

---

## 9. Phase 7 — graduate the safety layer

Once the LLM classifier hits ≥0.95 on the real set for sensitive categories, the safety regex can shrink.

- [ ] Keep regex for: self-harm, explicit threats, hate speech.
- [ ] Move political / medical / legal detection into the LLM with high-confidence thresholding (regex stays as a backstop, not the primary signal).
- [ ] When the safety regex fires, log the reason — so we can prove the layer is still earning its keep.

---

## 10. Definition of done

- [ ] No new keyword tuple has been added to detect a sub-intent in 30 days.
- [ ] `polite_boundary.py` (or its successor `safety_rules.py`) is ≤200 lines.
- [ ] Reply templates live in YAML, not Python.
- [ ] CI runs both the synthetic 500 eval and the real labeled regression — and PRs are gated on the real one.
- [ ] Response-quality scorecard ≥0.85 composite on the real set, with risk match =1.0 on high/critical.
- [ ] At least 300 real labeled cases live in `evaluation/offtopic_real_labeled.jsonl`, growing weekly from the 👎 feedback loop.

---

## What I am explicitly NOT planning

- Building a fine-tuned model. The existing Ollama path with a sharpened prompt + 20 real few-shot examples is enough until the labeled set passes ~2k rows.
- Adding more keyword categories. Every "the regex missed X" is now a label, not a code change.
- Rewriting the inventory pipeline. This plan only changes Layers 1-4 of the conversation entry point; the downstream search/answer engine stays as is.
