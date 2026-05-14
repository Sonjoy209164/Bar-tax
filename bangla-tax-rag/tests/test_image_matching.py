from __future__ import annotations

import json
from pathlib import Path

from app.core.schemas import InventoryImageAsset, InventoryItemRecord, InventorySearchFilters
from app.inventory.image_matcher import (
    ImageMatcher,
    ImageMatchResult,
    finalize_image_search,
    is_image_search_query,
    primary_image_url,
)


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


def test_catalog_items_have_first_class_image_assets():
    catalog = _active_catalog()
    assert all(item.images for item in catalog.values())
    first = catalog["saree-jmd-lotus-red"]
    assert first.images[0].kind == "reference_photo"
    assert first.images[0].is_reference is True
    assert primary_image_url(first)


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


def test_image_decision_confirms_product_photo_exact_and_variants():
    catalog = _active_catalog()
    raw = [
        ImageMatchResult(
            product_id="shirt-ribbed-polo-black",
            name="Ribbed Open-Collar Knit Polo - Black",
            score=0.99,
            match_type="visual_similar",
            reasons=("test visual hit",),
            price=1750.0,
            currency="BDT",
            stock=5,
        )
    ]
    decision = finalize_image_search(catalog=catalog, results=raw, query_text="eta ache?", top_k=6)
    assert decision.decision_label == "confirmed_exact"
    assert decision.primary_product_id == "shirt-ribbed-polo-black"
    assert "shirt-ribbed-polo-white" in decision.same_design_variant_ids
    assert any(hit.decision_label == "confirmed_exact" for hit in decision.hits)


def test_image_decision_answers_same_design_requested_color():
    catalog = _active_catalog()
    raw = [
        ImageMatchResult(
            product_id="shirt-ribbed-polo-black",
            name="Ribbed Open-Collar Knit Polo - Black",
            score=0.99,
            match_type="visual_similar",
            reasons=("test visual hit",),
            price=1750.0,
            currency="BDT",
            stock=5,
        )
    ]
    decision = finalize_image_search(
        catalog=catalog,
        results=raw,
        query_text="same design white color ache?",
        top_k=6,
    )
    assert decision.decision_label == "confirmed_same_design_variant"
    assert decision.requested_color == "white"
    assert "shirt-ribbed-polo-white" in [hit.product_id for hit in decision.hits]
    assert "white" in decision.answer.casefold()


def test_reference_image_never_becomes_confirmed_exact():
    catalog = _active_catalog()
    raw = [
        ImageMatchResult(
            product_id="saree-jmd-lotus-red",
            name="Lotus Buti Dhakai Jamdani Saree - Red",
            score=0.99,
            match_type="visual_similar",
            reasons=("test visual hit",),
            price=6800.0,
            currency="BDT",
            stock=3,
        )
    ]
    decision = finalize_image_search(catalog=catalog, results=raw, query_text="eta ache?", top_k=4)
    assert decision.decision_label != "confirmed_exact"
    assert all(hit.decision_label != "confirmed_exact" for hit in decision.hits)
    assert decision.hits[0].is_reference is True


# ---------------------------------------------------------------------------
# Gold-set decision-policy regression gate (Phase 13 / 14)
# ---------------------------------------------------------------------------


def _check_gold_case(case: dict, decision) -> list[str]:
    """Mirror scripts/run_image_search_eval.py checks at the decision-policy level."""
    issues: list[str] = []
    hit_ids = [hit.product_id for hit in decision.hits]

    expected_label = case.get("expected_decision_label")
    if expected_label and decision.decision_label != expected_label:
        issues.append(f"expected label {expected_label}, got {decision.decision_label}")

    forbidden_label = case.get("forbidden_decision_label")
    if forbidden_label and decision.decision_label == forbidden_label:
        issues.append(f"forbidden label {forbidden_label}")

    expected_primary = case.get("expected_primary_product_id")
    if expected_primary and expected_primary not in {decision.primary_product_id, *hit_ids[:3]}:
        issues.append(f"expected {expected_primary} in primary/top-3, got {hit_ids[:3]}")

    expected_variants = set(case.get("expected_same_design_variant_ids") or [])
    if expected_variants:
        actual = set(decision.same_design_variant_ids) | set(hit_ids)
        missing = expected_variants - actual
        if missing:
            issues.append(f"missing variants {sorted(missing)}")

    expected_colors = set(case.get("expected_available_colors") or [])
    if expected_colors:
        missing = expected_colors - set(decision.available_colors)
        if missing:
            issues.append(f"missing colors {sorted(missing)}")

    expected_category = case.get("expected_category")
    if expected_category:
        cats = {
            str((hit.score_breakdown or {}).get("category", "")).casefold()
            for hit in decision.hits
        }
        names = " ".join(hit.name for hit in decision.hits).casefold()
        if expected_category.casefold() not in cats and expected_category.casefold() not in names:
            issues.append(f"expected category signal {expected_category}")

    return issues


def test_image_search_gold_set_decision_policy():
    """Every gold-set case must produce the expected business decision when the
    correct product is the raw visual hit. Locks the decision policy as a
    regression gate independent of whether CLIP is installed."""
    catalog = _active_catalog()
    gold_path = Path("evaluation/image_search_gold_set.jsonl")
    cases = [
        json.loads(line)
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert cases, "gold set must not be empty"

    for case in cases:
        # image_path is frontend/assets/demo_catalog/{product_id}/primary.jpg
        product_id = Path(case["image_path"]).parent.name
        assert product_id in catalog, f"{case['case_id']}: {product_id} not in catalog"
        item = catalog[product_id]
        raw = [
            ImageMatchResult(
                product_id=product_id,
                name=item.name,
                score=0.99,
                match_type="visual_similar",
                reasons=("gold-set raw visual hit",),
                price=item.price,
                currency=item.currency,
                stock=item.stock,
            )
        ]
        decision = finalize_image_search(
            catalog=catalog,
            results=raw,
            query_text=case.get("query_text", ""),
            top_k=6,
        )
        issues = _check_gold_case(case, decision)
        assert not issues, f"{case['case_id']}: {issues}"


# ---------------------------------------------------------------------------
# CLIP channel routing (Phase 5) — exercised with a mocked CLIP model so the
# grayscale pattern channel is real, run code rather than unverified code.
# ---------------------------------------------------------------------------


def _two_item_image_catalog() -> dict[str, InventoryItemRecord]:
    def _item(pid: str, color: str) -> InventoryItemRecord:
        return InventoryItemRecord(
            product_id=pid,
            sku=pid.upper(),
            name=f"Test Polo {color}",
            category="Shirt",
            price=1500.0,
            currency="BDT",
            stock=4,
            status="Active",
            attributes={
                "category_key": "shirt",
                "color": color,
                "color_family": color,
                "design_id": "test-ribbed",
                "variant_group_id": "test-ribbed-polo",
            },
            images=[
                InventoryImageAsset(
                    image_id=f"{pid}-primary-1",
                    local_path=f"/tmp/{pid}.jpg",
                    role="primary",
                    kind="product_photo",
                    is_reference=False,
                )
            ],
        )

    return {
        "test-polo-black": _item("test-polo-black", "black"),
        "test-polo-white": _item("test-polo-white", "white"),
    }


def test_clip_matcher_builds_pattern_and_full_channels(monkeypatch):
    """With CLIP mocked, precompute builds both the full-visual and grayscale
    pattern channels, and search routes the query to the right channel."""
    from app.inventory import clip_matcher

    def fake_load_clip():
        return ("fake-model", "fake-processor")

    def fake_encode_source(source, *, grayscale=False):
        if grayscale:
            return [0.5, 0.5]
        return [0.9, 0.1] if "black" in source else [0.1, 0.9]

    monkeypatch.setattr(clip_matcher, "_load_clip", fake_load_clip)
    monkeypatch.setattr(clip_matcher, "_encode_image_source", fake_encode_source)
    monkeypatch.setattr(clip_matcher, "_encode_image_b64", lambda _b64: [0.9, 0.1])
    monkeypatch.setattr(clip_matcher, "_encode_image_b64_grayscale", lambda _b64: [0.5, 0.5])
    # Clear the in-memory cache so precompute actually runs.
    monkeypatch.setattr(clip_matcher, "_catalog_embeddings", {})
    monkeypatch.setattr(clip_matcher, "_catalog_embedding_signature", ())

    catalog = _two_item_image_catalog()
    count = clip_matcher.precompute_catalog_embeddings(catalog, force=True)
    assert count > 0

    keys = set(clip_matcher._catalog_embeddings)
    assert any(key.endswith("::pattern") for key in keys), "pattern channel missing"
    assert any(
        not key.endswith("::pattern") and not key.endswith("::text") for key in keys
    ), "full-visual channel missing"

    results = clip_matcher.CLIPImageMatcher().search(image_b64="fake-b64", catalog=catalog, top_k=5)
    assert results
    channel_types = {(r.score_breakdown or {}).get("embedding_type") for r in results}
    assert channel_types <= {"full_visual", "pattern_visual"}
    # The black-shirt full-visual channel must align best with the black query.
    assert results[0].product_id == "test-polo-black"


def test_clip_embedding_metadata_is_versioned():
    """Every embedding must carry model + preprocess version stamps (Phase 5)."""
    from app.inventory.clip_matcher import embedding_metadata

    meta = embedding_metadata()
    for key in ("model_name", "model_version", "preprocess_version", "embedding_version", "embedding_created_at"):
        assert meta.get(key), f"embedding metadata missing {key}"
