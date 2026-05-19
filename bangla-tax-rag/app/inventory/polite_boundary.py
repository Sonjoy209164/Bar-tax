"""
Backwards-compatibility shim for the conversation entry layer.

The implementation has moved into four focused modules:
  - safety_rules.py             (Layer 1: deterministic crisis/abuse/etc.)
  - boundary_classifier.py      (Layer 2: LLM-first sub-intent classifier)
  - boundary_fallback_rules.py  (offline keyword backstop for Layer 2)
  - boundary_templates.py       (Layer 4: YAML-driven reply renderer)

Existing call sites (inventory_service.py, tests/, __init__.py) only need
`classify_polite_boundary` and `PoliteBoundaryDecision`. Those are re-exported
here as thin aliases so the cutover is invisible to callers. New code should
import from `boundary_classifier` directly.

See `to_doimprove.md` for the full architecture plan.
"""
from __future__ import annotations

from app.inventory.boundary_classifier import (
    BoundaryDecision as PoliteBoundaryDecision,
    classify_boundary,
)


def classify_polite_boundary(
    question: str,
    *,
    assistant_mode: str = "support",
    reply_style: str = "short",
) -> PoliteBoundaryDecision | None:
    """Compatibility wrapper. Delegates to `boundary_classifier.classify_boundary`."""
    return classify_boundary(
        question,
        assistant_mode=assistant_mode,
        reply_style=reply_style,
    )


__all__ = ["PoliteBoundaryDecision", "classify_polite_boundary"]
