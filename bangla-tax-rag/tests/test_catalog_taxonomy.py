from __future__ import annotations

import pytest

from app.inventory.catalog_taxonomy import (
    canonicalize,
    compatible_categories_for,
    compatible_for_exact,
)


# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------


class TestCanonicalize:
    def test_empty_string_returns_empty(self):
        assert canonicalize("") == ""

    def test_none_like_returns_empty(self):
        assert canonicalize("unknown") == ""
        assert canonicalize("Unknown") == ""
        assert canonicalize("UNKNOWN") == ""
        assert canonicalize("none") == ""
        assert canonicalize("n/a") == ""

    def test_casing_invariant(self):
        assert canonicalize("Panjabi") == "panjabi"
        assert canonicalize("PANJABI") == "panjabi"
        assert canonicalize("panjabi") == "panjabi"

    def test_punctuation_stripped(self):
        # Hyphens and spaces become underscores during normalization.
        assert canonicalize("T Shirt") == "t_shirt"
        assert canonicalize("T-Shirt") == "t_shirt"
        assert canonicalize("Salwar Kameez") == "salwar_kameez"
        assert canonicalize("Salwar-Kameez") == "salwar_kameez"

    def test_aliases_resolve(self):
        # Scarf → dupatta
        assert canonicalize("Scarf") == "dupatta"
        assert canonicalize("scarf") == "dupatta"
        assert canonicalize("Hijab") == "dupatta"
        assert canonicalize("Infinity Scarf") == "dupatta"

        # Frock variants
        assert canonicalize("frock") == "frock"
        assert canonicalize("girls_frock") == "frock"
        assert canonicalize("kids frock") == "frock"
        assert canonicalize("Girls Frock") == "frock"

        # Panjabi variants
        assert canonicalize("punjabi") == "panjabi"
        assert canonicalize("Punjabi") == "panjabi"
        assert canonicalize("Kids Panjabi") == "panjabi"
        assert canonicalize("fatua") == "panjabi"

        # Salwar Kameez aliases
        assert canonicalize("kameez set") == "salwar_kameez"
        assert canonicalize("three piece") == "salwar_kameez"

        # Pants
        assert canonicalize("trouser") == "pant"
        assert canonicalize("leggings") == "pant"
        assert canonicalize("bermuda pant") == "pant"

        # Denim
        assert canonicalize("denim pant") == "jeans"
        assert canonicalize("Denim Long") == "jeans"

        # Sandals
        assert canonicalize("juttie") == "sandal"
        assert canonicalize("Mules") == "sandal"
        assert canonicalize("slipper") == "sandal"

    def test_direct_passthrough(self):
        for raw in ("saree", "tunic", "palazzo", "jacket", "bag", "skirt", "gown"):
            assert canonicalize(raw) == raw

    def test_unknown_token_passes_through(self):
        # Tokens not in the map come back as-is so new categories are not silently lost.
        assert canonicalize("kancheevaram") == "kancheevaram"


# ---------------------------------------------------------------------------
# compatible_for_exact
# ---------------------------------------------------------------------------


class TestCompatibleForExact:
    def test_identical_raw_strings(self):
        assert compatible_for_exact("panjabi", "panjabi") is True
        assert compatible_for_exact("Saree", "saree") is True

    def test_alias_resolves_to_same_canonical(self):
        assert compatible_for_exact("scarf", "dupatta") is True
        assert compatible_for_exact("Hijab", "Dupatta") is True
        assert compatible_for_exact("punjabi", "panjabi") is True
        assert compatible_for_exact("Girls Frock", "frock") is True

    def test_sibling_categories(self):
        # Pant / Jeans are siblings
        assert compatible_for_exact("pant", "jeans") is True
        assert compatible_for_exact("jeans", "pant") is True
        # Kameez / Salwar Kameez are siblings
        assert compatible_for_exact("kameez", "salwar_kameez") is True
        # Polo / T-shirt are siblings
        assert compatible_for_exact("polo", "t_shirt") is True

    def test_incompatible_pairs(self):
        assert compatible_for_exact("saree", "panjabi") is False
        assert compatible_for_exact("shirt", "saree") is False
        assert compatible_for_exact("bag", "sandal") is False
        assert compatible_for_exact("gown", "palazzo") is False

    def test_empty_category_is_compatible(self):
        # Empty/unknown on either side means no evidence → do not block.
        assert compatible_for_exact("", "saree") is True
        assert compatible_for_exact("unknown", "panjabi") is True
        assert compatible_for_exact("panjabi", "") is True


# ---------------------------------------------------------------------------
# compatible_categories_for
# ---------------------------------------------------------------------------


class TestCompatibleCategoriesFor:
    def test_unknown_returns_empty(self):
        assert compatible_categories_for("unknown") == frozenset()
        assert compatible_categories_for("") == frozenset()

    def test_always_includes_self(self):
        cats = compatible_categories_for("saree")
        assert "saree" in cats

    def test_includes_siblings(self):
        cats = compatible_categories_for("pant")
        assert "jeans" in cats
        assert "pant" in cats

        cats = compatible_categories_for("dupatta")
        assert "scarf" in cats or "dupatta" in cats

    def test_alias_resolved_before_lookup(self):
        # "scarf" canonicalizes to "dupatta"; siblings of "dupatta" are returned.
        cats = compatible_categories_for("scarf")
        assert "dupatta" in cats

    def test_no_cross_contamination(self):
        saree_cats = compatible_categories_for("saree")
        pant_cats = compatible_categories_for("pant")
        # saree and pant share no siblings
        assert not (saree_cats & pant_cats)
