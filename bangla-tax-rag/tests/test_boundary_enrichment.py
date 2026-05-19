"""
Tests for the conversation entry layer composition:
  - tone detection from the customer's message
  - memory ack from prior ConversationState slots
  - catalog product picks from recommended_categories
  - human-handoff line on sensitive boundaries
  - end-to-end enrich() assembly
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from app.core.schemas import InventoryImageAsset, InventoryItemRecord
from app.inventory.boundary_classifier import BoundaryDecision
from app.inventory.boundary_enrichment import (
    PriorContext,
    build_memory_ack,
    build_prior_context,
    detect_tone,
    enrich,
    format_catalog_snippet,
    pick_catalog_products,
    reload_handoff,
    render_handoff_line,
)


def _make_item(
    pid: str,
    *,
    name: str,
    category: str,
    category_key: str,
    tags: list[str],
    price: float,
    stock: int = 5,
) -> InventoryItemRecord:
    return InventoryItemRecord(
        product_id=pid,
        sku=pid.upper().replace("-", "_"),
        name=name,
        category=category,
        brand="Demo",
        short_description=f"{name} — short",
        full_description=f"{name} — long",
        price=price,
        currency="BDT",
        stock=stock,
        status="Active",
        tags=tags,
        attributes={"category_key": category_key, "color": "white"},
        images=[
            InventoryImageAsset(
                image_id=f"{pid}-img",
                local_path=f"/tmp/{pid}.jpg",
                source_name="test",
                role="primary",
                kind="reference_photo",
                is_reference=True,
            )
        ],
    )


def _make_catalog() -> dict[str, InventoryItemRecord]:
    return {
        "perfume-rose": _make_item(
            "perfume-rose", name="Rose Eau de Parfum", category="Perfume",
            category_key="perfume", tags=["perfume", "fragrance"], price=1500,
        ),
        "perfume-musk": _make_item(
            "perfume-musk", name="Musk Body Spray", category="Perfume",
            category_key="perfume", tags=["perfume", "fragrance"], price=900, stock=12,
        ),
        "perfume-oud": _make_item(
            "perfume-oud", name="Oud Premium", category="Perfume",
            category_key="perfume", tags=["perfume", "fragrance"], price=3500, stock=2,
        ),
        "watch-classic": _make_item(
            "watch-classic", name="Classic Steel Watch", category="Watch",
            category_key="watch", tags=["watch"], price=2200,
        ),
        "saree-jamdani": _make_item(
            "saree-jamdani", name="Jamdani Saree", category="Saree",
            category_key="saree", tags=["saree", "jamdani", "wedding"], price=4500,
        ),
        "bag-out-of-stock": _make_item(
            "bag-out-of-stock", name="Old Tote", category="Bag",
            category_key="bag", tags=["bag"], price=600, stock=0,
        ),
    }


# ----------------------------------------------------------------------
# Tone detection
# ----------------------------------------------------------------------

def test_detect_tone_neutral_default() -> None:
    assert detect_tone("amar ekta gift lagbe") == "neutral"


def test_detect_tone_frustrated_on_kobe_kothay() -> None:
    assert detect_tone("amar order kobe ashbe??? answer dao") == "frustrated"


def test_detect_tone_frustrated_on_caps_run() -> None:
    assert detect_tone("WHERE IS MY ORDER") == "frustrated"


def test_detect_tone_sad_on_mon_kharap() -> None:
    assert detect_tone("amar mon kharap, valo kichu dekhao") == "sad"


def test_detect_tone_excited_on_double_bang() -> None:
    assert detect_tone("darun!! love it!!") == "excited"


def test_detect_tone_curious_on_short_question() -> None:
    assert detect_tone("perfume ache?") == "curious"


# ----------------------------------------------------------------------
# Memory ack
# ----------------------------------------------------------------------

def test_build_prior_context_returns_none_when_empty_slots() -> None:
    state = SimpleNamespace(
        active_slots={},
        last_intent=None,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    assert build_prior_context(state) is None


def test_build_prior_context_distills_relevant_slots() -> None:
    state = SimpleNamespace(
        active_slots={"recipient": "girlfriend", "occasion": "birthday", "budget_max": 3000},
        last_intent="gift_recommendation",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    ctx = build_prior_context(state)
    assert ctx is not None
    assert ctx.recipient == "girlfriend"
    assert ctx.occasion == "birthday"
    assert ctx.budget_max == 3000.0


def test_build_prior_context_drops_stale_state() -> None:
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    state = SimpleNamespace(
        active_slots={"recipient": "wife"},
        last_intent="gift_recommendation",
        updated_at=stale_ts,
    )
    assert build_prior_context(state) is None


def test_build_memory_ack_english_mentions_slots() -> None:
    ack = build_memory_ack(
        prior=PriorContext(recipient="wife", occasion="anniversary", budget_max=5000),
        language="english",
    )
    assert ack is not None
    assert "anniversary" in ack
    assert "wife" in ack
    assert "5000" in ack


def test_build_memory_ack_bangla_uses_bangla_currency_marker() -> None:
    ack = build_memory_ack(
        prior=PriorContext(occasion="wedding", budget_max=4000),
        language="bangla",
    )
    assert ack is not None
    assert "৳" in ack or "বাজেট" in ack


# ----------------------------------------------------------------------
# Catalog picks
# ----------------------------------------------------------------------

def test_pick_catalog_products_filters_out_of_stock() -> None:
    catalog = _make_catalog()
    picks = pick_catalog_products(catalog=catalog, recommended_categories=("bag",))
    assert all(p.product_id != "bag-out-of-stock" for p in picks)


def test_pick_catalog_products_matches_by_recommended_category() -> None:
    catalog = _make_catalog()
    picks = pick_catalog_products(catalog=catalog, recommended_categories=("perfume",), n=3)
    ids = {p.product_id for p in picks}
    assert ids == {"perfume-rose", "perfume-musk", "perfume-oud"}


def test_pick_catalog_products_expands_synonyms() -> None:
    catalog = _make_catalog()
    picks = pick_catalog_products(catalog=catalog, recommended_categories=("outfit",), n=2)
    assert any(p.product_id == "saree-jamdani" for p in picks)


def test_pick_catalog_products_returns_empty_on_no_match() -> None:
    catalog = _make_catalog()
    picks = pick_catalog_products(catalog=catalog, recommended_categories=("laptop",))
    assert picks == []


def test_format_catalog_snippet_renders_bdt_marker() -> None:
    catalog = _make_catalog()
    picks = pick_catalog_products(catalog=catalog, recommended_categories=("perfume",), n=2)
    snippet = format_catalog_snippet(picks, language="english")
    assert "Rose Eau de Parfum" in snippet
    assert "৳" in snippet


# ----------------------------------------------------------------------
# Handoff
# ----------------------------------------------------------------------

def test_render_handoff_line_uses_per_language_template() -> None:
    reload_handoff()
    line = render_handoff_line("english")
    assert "+880" in line
    assert "Sat-Thu" in line or "WhatsApp" in line


def test_render_handoff_line_bangla_keeps_bangla_text() -> None:
    reload_handoff()
    line = render_handoff_line("bangla")
    assert "টিম" in line or "WhatsApp" in line


# ----------------------------------------------------------------------
# enrich() end-to-end assembly
# ----------------------------------------------------------------------

def test_enrich_assembles_memory_tone_base_catalog_handoff() -> None:
    catalog = _make_catalog()
    decision = BoundaryDecision(
        boundary_type="gift_recommendation",
        answer="For a gift, I can suggest perfume, watch.",
        follow_up_question="What is your Budget?",
        confidence=0.9,
        language="english",
        risk_level="low",
        allowed_action="ask_clarifying_question",
        handoff_recommended=False,
        slots={"recipient": "wife"},
        recommended_categories=("perfume", "watch"),
        reasoning=("gift intent",),
        source="fallback",
    )
    prior = PriorContext(occasion="anniversary", budget_max=4000)

    enriched = enrich(
        decision=decision,
        question="something nice for my wife please",
        catalog=catalog,
        prior=prior,
    )

    assert "anniversary" in enriched.answer
    assert "For a gift" in enriched.answer
    # tone for "...please" is neutral here, so no tone ack
    assert enriched.tone == "neutral"
    assert len(enriched.catalog_picks) >= 1
    assert "Rose Eau de Parfum" in enriched.answer or "Classic Steel Watch" in enriched.answer
    assert enriched.handoff_line is None


def test_enrich_does_not_show_products_on_safe_refusal() -> None:
    catalog = _make_catalog()
    decision = BoundaryDecision(
        boundary_type="medical_or_health_advice",
        answer="I cannot provide medical advice.",
        follow_up_question=None,
        confidence=0.9,
        language="english",
        risk_level="high",
        allowed_action="safe_refusal_redirect",
        handoff_recommended=True,
        slots={},
        recommended_categories=("wellness", "self-care"),
        reasoning=("medical",),
        source="safety",
    )

    enriched = enrich(
        decision=decision,
        question="I have a rash, what medicine should I take?",
        catalog=catalog,
        prior=None,
    )

    # No product suggestions on a sensitive refusal — even though we have wellness items.
    assert enriched.catalog_picks == []
    # But a handoff line is appended.
    assert enriched.handoff_line is not None
    assert "+880" in enriched.answer


def test_enrich_prepends_tone_ack_for_frustrated_customer() -> None:
    decision = BoundaryDecision(
        boundary_type="order_tracking_support",
        answer="I can help track an order, but I need the order ID or phone number first.",
        follow_up_question="Please share the order ID or phone number.",
        confidence=0.9,
        language="english",
        risk_level="low",
        allowed_action="store_support_redirect",
        handoff_recommended=False,
        slots={"support_topic": "order_tracking"},
        recommended_categories=(),
        reasoning=("order tracking",),
        source="safety",
    )

    enriched = enrich(
        decision=decision,
        question="WHERE IS MY ORDER, still nothing???",
        catalog={},
        prior=None,
    )
    assert enriched.tone == "frustrated"
    assert "sorry" in enriched.answer.casefold()
