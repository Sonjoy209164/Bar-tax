"""Tests for the coreference resolver."""
from __future__ import annotations

from app.inventory.coreference_resolver import resolve_coreference


SHOWN = ["p1", "p2", "p3"]


# ── empty / no-match cases ────────────────────────────────────────────────────

def test_no_pronoun_no_resolution() -> None:
    r = resolve_coreference(
        question="red saree achhe?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id is None
    assert r.resolution_type == "none"


def test_no_context_no_resolution() -> None:
    r = resolve_coreference(
        question="এটার দাম কত?",
        last_shown_product_ids=[],
        last_primary_product_id=None,
    )
    assert r.resolved_product_id is None


# ── "this" / "এটা" → primary or first ────────────────────────────────────────

def test_this_resolves_to_primary() -> None:
    r = resolve_coreference(
        question="এটার দাম কত?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"
    assert r.resolution_type == "this"


def test_this_english_resolves() -> None:
    r = resolve_coreference(
        question="What's the price of this one?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p2",
    )
    assert r.resolved_product_id == "p2"


def test_eta_banglish_resolves() -> None:
    r = resolve_coreference(
        question="etar dam koto?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"


def test_tar_banglish_resolves() -> None:
    r = resolve_coreference(
        question="tar dam koto?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p2",
    )
    assert r.resolved_product_id == "p2"


def test_eita_banglish_resolves() -> None:
    r = resolve_coreference(
        question="eitar size M ache?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"


# ── "that" / "ওটা" ────────────────────────────────────────────────────────────

def test_that_resolves() -> None:
    r = resolve_coreference(
        question="ওটার size kichu?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"
    assert r.resolution_type == "that"


# ── ordinal references ────────────────────────────────────────────────────────

def test_first_one() -> None:
    r = resolve_coreference(
        question="show me details of the first one",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"
    assert r.resolution_type.startswith("ordinal")


def test_second_one() -> None:
    r = resolve_coreference(
        question="give me the second one",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p2"


def test_third_one() -> None:
    r = resolve_coreference(
        question="3rd ta dekhao",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p3"


def test_last_one() -> None:
    r = resolve_coreference(
        question="last ta nibo",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p3"


def test_prothom_bangla_word() -> None:
    r = resolve_coreference(
        question="প্রথম টা ভাল লাগে",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"


# ── same design ──────────────────────────────────────────────────────────────

def test_same_design_resolves() -> None:
    r = resolve_coreference(
        question="same design e blue ache?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id == "p1"
    assert r.resolution_type == "same_design"


# ── word boundary safety ──────────────────────────────────────────────────────

def test_does_not_match_eta_inside_word() -> None:
    # "metar" is a unit of measurement — should not falsely match "eta"
    r = resolve_coreference(
        question="metar koto?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id is None


def test_does_not_match_this_inside_word() -> None:
    r = resolve_coreference(
        question="thistle flower achhe?",
        last_shown_product_ids=SHOWN,
        last_primary_product_id="p1",
    )
    assert r.resolved_product_id is None


# ── fallback: first shown when no primary ────────────────────────────────────

def test_this_falls_back_to_first_shown_when_no_primary() -> None:
    r = resolve_coreference(
        question="this one",
        last_shown_product_ids=SHOWN,
        last_primary_product_id=None,
    )
    assert r.resolved_product_id == "p1"
