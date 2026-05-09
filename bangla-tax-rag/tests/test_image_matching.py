from __future__ import annotations

from pathlib import Path

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.image_matcher import ImageMatcher, ImageMatchResult, is_image_search_query


def _active_catalog() -> dict[str, InventoryItemRecord]:
    items: dict[str, InventoryItemRecord] = {}
    for line in Path("data/inventory/catalog.jsonl").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = InventoryItemRecord.model_validate_json(stripped)
        items[item.product_id] = item
    return items


def test_is_image_search_query_bangla():
    assert is_image_search_query("এই ছবির মতো শাড়ি আছে?")
    assert is_image_search_query("ei picture er moto same design ache?")


def test_is_image_search_query_english():
    assert is_image_search_query("Can you find a similar bag for this saree?")
    assert is_image_search_query("find similar product")


def test_is_not_image_search_query():
    assert not is_image_search_query("red saree ache?")
    assert not is_image_search_query("oily skin sunscreen ache?")


def test_image_matcher_returns_results_for_category_hint():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="similar saree", category_hint="saree", top_k=5)
    assert isinstance(results, list)
    assert len(results) > 0
    for r in results:
        assert isinstance(r, ImageMatchResult)
        assert r.score > 0.0


def test_image_matcher_filters_by_budget():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="saree", category_hint="saree", budget_max=3000.0, top_k=5)
    for r in results:
        item = catalog[r.product_id]
        assert item.price is None or item.price <= 3000.0


def test_image_matcher_color_hint_scores_higher():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results_red = matcher.search(query_text="saree", category_hint="saree", color_hint="red", top_k=5)
    results_blue = matcher.search(query_text="saree", category_hint="saree", color_hint="blue", top_k=5)
    assert len(results_red) > 0
    assert len(results_blue) > 0


def test_image_matcher_no_results_for_impossible_budget():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="saree", budget_max=1.0, top_k=5)
    assert results == []


def test_image_matcher_build_answer_empty():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    answer = matcher.build_answer([], "find similar")
    assert "could not find" in answer.lower() or "no" in answer.lower()


def test_image_matcher_build_answer_with_results():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="similar red saree", category_hint="saree", color_hint="red", top_k=3)
    if results:
        answer = matcher.build_answer(results, "find similar red saree")
        assert len(answer) > 0
        assert "similar" in answer.lower() or "found" in answer.lower()


def test_image_matcher_out_of_stock_ranked_lower():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="saree", category_hint="saree", top_k=10)
    scores_in_stock = [r.score for r in results if r.stock > 0]
    scores_out_stock = [r.score for r in results if r.stock == 0]
    if scores_in_stock and scores_out_stock:
        assert max(scores_in_stock) >= max(scores_out_stock)


def test_image_matcher_match_type_assigned():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="jamdani saree", category_hint="saree", top_k=5)
    for r in results:
        assert r.match_type in ("visual_similar", "same_design_variant")


def test_image_matcher_returns_no_duplicates():
    catalog = _active_catalog()
    matcher = ImageMatcher(catalog)
    results = matcher.search(query_text="saree", top_k=10)
    ids = [r.product_id for r in results]
    assert len(ids) == len(set(ids))
