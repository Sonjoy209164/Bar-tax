# Conversation Entry Layer — Architecture

This document is the source of truth for how messages flow into the bot before they reach the inventory retrieval pipeline. It complements [../to_doimprove.md](../to_doimprove.md), which is the active checklist.

## Before / After

**Before** ([git log of polite_boundary.py](../app/inventory/polite_boundary.py) prior to this refactor):

```text
┌───────────────────────────────────────────────────────┐
│ polite_boundary.py  (~1200 LOC)                       │
│                                                       │
│  • 20+ flat keyword tuples (EVENT, ROMANTIC, EMOTION, │
│    POLITICAL, MEDICAL, LEGAL, ABUSIVE, VAGUE, ...)    │
│  • one big classify_polite_boundary() if/elif         │
│  • 600 LOC of hand-written templates per              │
│    (boundary_type × {english, banglish, bangla})      │
│  • zero use of the existing LLM intent classifier     │
└───────────────────────────────────────────────────────┘

Eval: scripts/run_offtopic_boundary_500_eval.py generates cases
from the SAME templates the regex was tuned for. Green means
the regex matches itself.
```

**After** (this branch):

```text
user message
  │
  ▼
┌──────────────────────────────────────────────┐
│ Layer 1 — safety_rules.py                    │
│   regex-allowed (deterministic + narrow)     │
│   - self_harm_or_crisis                      │
│   - abusive_severe / abusive_mild            │
│   - medical_or_health_advice                 │
│   - legal_advice                             │
│   - political                                │
│   - random_tech                              │
│   - order_tracking_support / payment_support │
└──────────────────────────────────────────────┘
  │ no safety hit
  ▼
┌──────────────────────────────────────────────┐
│ boundary_fallback_rules.is_concrete_         │
│ shopping_or_support(text)                    │
│   → True ⇒ return None  (passthrough to      │
│            inventory pipeline)                │
└──────────────────────────────────────────────┘
  │ not concrete
  ▼
┌──────────────────────────────────────────────┐
│ Layer 2 — boundary_classifier.py             │
│   ① classify_with_llm()  (Ollama, primary)   │
│      env: POLITE_BOUNDARY_LLM_ENABLED=true   │
│   ② classify_fallback() (boundary_fallback_  │
│      rules.py — offline keyword backstop)    │
│   returns sub_intent + slots + confidence    │
└──────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────┐
│ Layer 4 — boundary_templates.py              │
│   loads config/boundary_templates.yaml once  │
│   renders (boundary_type, language) → text   │
│   substitutes {event}, {categories},         │
│   {recipient}                                │
└──────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────┐
│ conversation_logger.py                       │
│   appends one row to                         │
│   data/conversation_logs/raw_offtopic.jsonl  │
│   (PII-masked: emails, phones, order IDs)    │
└──────────────────────────────────────────────┘
  │
  ▼
BoundaryDecision (returned to inventory_service)
```

## File map

| File | Role | LOC budget |
|---|---|---|
| [app/inventory/safety_rules.py](../app/inventory/safety_rules.py) | Layer 1 deterministic safety | ~200 |
| [app/inventory/boundary_classifier.py](../app/inventory/boundary_classifier.py) | Layer 2 LLM-first classifier | ~250 |
| [app/inventory/boundary_fallback_rules.py](../app/inventory/boundary_fallback_rules.py) | Offline keyword backstop for Layer 2 | ~350 |
| [app/inventory/boundary_templates.py](../app/inventory/boundary_templates.py) | Layer 4 YAML renderer | ~120 |
| [app/inventory/boundary_text.py](../app/inventory/boundary_text.py) | Shared normalize / detect_language / has_any | ~50 |
| [app/inventory/conversation_logger.py](../app/inventory/conversation_logger.py) | Append-only sink for real traffic | ~70 |
| [app/inventory/polite_boundary.py](../app/inventory/polite_boundary.py) | Thin compat shim — re-exports the public API | ~30 |
| [config/boundary_templates.yaml](../config/boundary_templates.yaml) | All reply strings, by `boundary_type × language` | data |

## Public API (unchanged)

```python
from app.inventory.polite_boundary import (
    classify_polite_boundary,    # (question, *, assistant_mode, reply_style) -> Decision | None
    PoliteBoundaryDecision,      # the dataclass
)
```

These remain the only symbols imported by [app/services/inventory_service.py](../app/services/inventory_service.py) and the existing test suite. The new `BoundaryDecision` exported from `boundary_classifier` is the same dataclass, just renamed.

New code should import from `boundary_classifier` directly:

```python
from app.inventory.boundary_classifier import BoundaryDecision, classify_boundary, set_llm_enabled
```

## Toggling the LLM path

By default the LLM path is **off** — important for CI determinism and so the bot degrades gracefully without Ollama.

Enable in production:
```bash
export POLITE_BOUNDARY_LLM_ENABLED=true
export POLITE_BOUNDARY_OLLAMA_URL=http://localhost:11434
export POLITE_BOUNDARY_OLLAMA_MODEL=qwen3:8b
```

Enable in a test:
```python
from app.inventory.boundary_classifier import set_llm_enabled
set_llm_enabled(True)
try:
    ...
finally:
    set_llm_enabled(None)  # restore env-driven default
```

## Evaluation

| Tool | What it measures | When |
|---|---|---|
| [tests/test_polite_boundary.py](../tests/test_polite_boundary.py) | Public API contract (22 representative cases) | Every PR |
| [scripts/run_offtopic_boundary_500_eval.py](../scripts/run_offtopic_boundary_500_eval.py) | Synthetic smoke — 500 template-generated cases | Nightly (downgraded from a quality signal — see `to_doimprove.md` Phase 5) |
| [tests/test_offtopic_real_regression.py](../tests/test_offtopic_real_regression.py) | Real-customer intent + risk on the labeled set | Every PR once the set has ≥10 rows |
| [scripts/score_response_quality.py](../scripts/score_response_quality.py) | Multi-dimensional reply quality (human, brand, redirect, safety) via an LLM judge | Weekly + on prompt/template changes |

## Adding a new sub-intent (the new path)

1. Collect ≥5 real examples of the new sub-intent from `data/conversation_logs/raw_offtopic.jsonl` or from 👎 feedback.
2. Add them to [evaluation/offtopic_real_labeled.jsonl](../evaluation/offtopic_real_labeled.jsonl).
3. Extend `VALID_SUB_INTENTS` and add an example block to `_LLM_PROMPT` in [boundary_classifier.py](../app/inventory/boundary_classifier.py).
4. Add a template block in [config/boundary_templates.yaml](../config/boundary_templates.yaml) for `english`, `banglish`, `bangla`.
5. Optionally extend [boundary_fallback_rules.py](../app/inventory/boundary_fallback_rules.py) for offline coverage — only when the LLM is unreachable.
6. Run [scripts/score_response_quality.py](../scripts/score_response_quality.py) and confirm composite ≥0.85, risk match =1.0.

**Do not add a new keyword tuple to detect a sub-intent.** That is what we just moved away from.
