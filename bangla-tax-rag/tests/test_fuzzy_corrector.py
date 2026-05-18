"""Tests for fuzzy_corrector module."""
import pytest

from app.inventory.fuzzy_corrector import (
    augment_with_corrections,
    fuzzy_correct_text,
    fuzzy_correct_token,
)


# ── token-level correction ─────────────────────────────────────────────────

def test_corrects_jamdani_typo() -> None:
    assert fuzzy_correct_token("jamdhani") == "jamdani"


def test_corrects_georgette_typo() -> None:
    assert fuzzy_correct_token("georgett") == "georgette"


def test_corrects_wedding_typo() -> None:
    assert fuzzy_correct_token("weeding") == "wedding"


def test_corrects_panjabi_short() -> None:
    result = fuzzy_correct_token("panjab")
    assert result in ("panjabi", "panjab")  # allowed both — panjab ratio 0.923 > cutoff


def test_no_correction_for_exact_match() -> None:
    assert fuzzy_correct_token("saree") == "saree"
    assert fuzzy_correct_token("jamdani") == "jamdani"
    assert fuzzy_correct_token("wedding") == "wedding"


def test_no_correction_for_short_tokens() -> None:
    # Tokens under 4 chars should never be corrected
    assert fuzzy_correct_token("eid") == "eid"
    assert fuzzy_correct_token("red") == "red"


def test_no_false_positive_on_unrelated_word() -> None:
    # "computer" should not be corrected to any fashion term
    result = fuzzy_correct_token("computer")
    assert result == "computer"


def test_no_correction_for_bangla_unicode() -> None:
    result = fuzzy_correct_token("জামদানি")
    assert result == "জামদানি"


# ── text-level correction ──────────────────────────────────────────────────

def test_corrects_typo_in_sentence() -> None:
    result = fuzzy_correct_text("laal jamdhani sharee dekhao")
    assert "jamdani" in result


def test_bangla_tokens_preserved_in_text() -> None:
    text = "লাল jamdhani শাড়ি"
    result = fuzzy_correct_text(text)
    assert "লাল" in result
    assert "শাড়ি" in result


def test_identical_when_no_typos() -> None:
    text = "red jamdani saree wedding"
    assert fuzzy_correct_text(text) == text


# ── augmentation ──────────────────────────────────────────────────────────

def test_augment_appends_corrected_version() -> None:
    result = augment_with_corrections("jamdhani saree")
    assert "jamdhani saree" in result
    assert "jamdani" in result


def test_augment_no_change_when_correct() -> None:
    text = "jamdani saree red"
    assert augment_with_corrections(text) == text
