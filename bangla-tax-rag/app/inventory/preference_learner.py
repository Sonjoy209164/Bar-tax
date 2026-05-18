"""
Implicit preference learning from conversation patterns.

Watches the conversation state and silently updates the customer's profile
when patterns emerge:

  - Same color asked 3+ times      → save as favorite_color
  - Same occasion asked 2+ times   → save as preferred_occasion
  - Same category asked 3+ times   → add to preferred_categories
  - Budget mentioned 2+ times      → save typical_budget (median)

Only writes to IdentityStore when the session has a phone linked, so we
never persist preferences for anonymous browsers (privacy + storage).
"""
from __future__ import annotations

import logging
import statistics
from typing import Any

from app.inventory.conversation_state import ConversationState

logger = logging.getLogger(__name__)

# Thresholds — kept here so they're easy to tune
COLOR_REPEAT_THRESHOLD = 3
OCCASION_REPEAT_THRESHOLD = 2
CATEGORY_REPEAT_THRESHOLD = 3
BUDGET_OBSERVATION_THRESHOLD = 2

MAX_FAVORITE_COLORS = 5
MAX_PREFERRED_CATEGORIES = 5


def derive_preferences(state: ConversationState) -> dict[str, Any]:
    """
    Pure function: read state counters, return a partial profile patch.
    Returns {} when no preference is strong enough to record yet.
    """
    patch: dict[str, Any] = {}

    # Favorite colors — anything mentioned >= threshold times
    favorite_colors = [
        color for color, count in state.color_counts.items()
        if count >= COLOR_REPEAT_THRESHOLD
    ]
    if favorite_colors:
        # Sort by count descending so the most-asked colour appears first
        favorite_colors.sort(key=lambda c: state.color_counts[c], reverse=True)
        patch["favorite_colors"] = favorite_colors[:MAX_FAVORITE_COLORS]

    # Preferred categories
    preferred_categories = [
        cat for cat, count in state.category_counts.items()
        if count >= CATEGORY_REPEAT_THRESHOLD
    ]
    if preferred_categories:
        preferred_categories.sort(key=lambda c: state.category_counts[c], reverse=True)
        patch["preferred_categories"] = preferred_categories[:MAX_PREFERRED_CATEGORIES]

    # Preferred occasion (single most repeated)
    if state.occasion_counts:
        top_occasion, count = max(state.occasion_counts.items(), key=lambda kv: kv[1])
        if count >= OCCASION_REPEAT_THRESHOLD:
            patch["preferred_occasion"] = top_occasion

    # Typical budget — median of observed budgets
    if len(state.budget_observations) >= BUDGET_OBSERVATION_THRESHOLD:
        try:
            patch["typical_budget"] = round(statistics.median(state.budget_observations), 0)
        except statistics.StatisticsError:
            pass

    return patch


def apply_preferences_to_profile(
    *,
    state: ConversationState,
    identity_store: Any,  # IdentityStore-like
    phone: str | None,
) -> dict[str, Any]:
    """
    Compute the patch and write it to the customer's profile if there's a
    phone linked to this session. Returns the patch (empty if nothing to do).
    """
    if not phone:
        return {}
    patch = derive_preferences(state)
    if not patch:
        return {}
    try:
        existing = identity_store.get_profile(phone) or {}
        merged = _merge_profile(existing, patch)
        identity_store.upsert_profile(phone, merged)
        logger.debug("Updated profile for %s with patch: %s", phone[-4:], patch)
        return patch
    except Exception as exc:
        logger.debug("Preference write failed: %s", exc)
        return {}


def _merge_profile(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """
    Merge patch into existing profile. List-valued fields union (keep the
    patch's order — it reflects current preference); scalars overwrite.
    """
    merged = dict(existing)
    for key, value in patch.items():
        if isinstance(value, list):
            existing_list = merged.get(key, [])
            if not isinstance(existing_list, list):
                existing_list = []
            seen = set()
            combined: list[Any] = []
            for item in list(value) + list(existing_list):
                if item not in seen:
                    seen.add(item)
                    combined.append(item)
            merged[key] = combined[:MAX_FAVORITE_COLORS]
        else:
            merged[key] = value
    return merged
