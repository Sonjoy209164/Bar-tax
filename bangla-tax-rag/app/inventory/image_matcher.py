from __future__ import annotations

import base64
import hashlib
import math
from dataclasses import dataclass
from typing import Any

from app.core.schemas import InventoryImageAsset, InventoryItemRecord


@dataclass(frozen=True)
class ImageMatchResult:
    product_id: str
    name: str
    score: float
    match_type: str
    reasons: tuple[str, ...]
    price: float | None = None
    currency: str = "BDT"
    stock: int = 0
    image_url: str | None = None
    decision_label: str = "similar_style"
    variant_group_id: str | None = None
    design_id: str | None = None
    color: str | None = None
    size: str | None = None
    image_kind: str | None = None
    is_reference: bool = False
    score_breakdown: dict[str, float | str | bool] | None = None


@dataclass(frozen=True)
class ImageSearchDecision:
    answer: str
    hits: list[ImageMatchResult]
    decision_label: str
    primary_product_id: str | None
    same_design_variant_ids: tuple[str, ...]
    similar_product_ids: tuple[str, ...]
    requested_color: str | None
    available_colors: tuple[str, ...]
    score_breakdown: dict[str, Any]
    requested_size: str | None = None
    follow_up_question: str | None = None


IMAGE_QUERY_PHRASES = (
    "এই ছবির মতো",
    "ei picture er moto",
    "ei chobir moto",
    "same design",
    "similar design",
    "এই রকম",
    "এরকম",
    "similar to this",
    "find similar",
    "image er moto",
    "picture match",
    "ছবির মতো",
    "same pattern",
    "এই জামদানির মতো",
    "এই শাড়ির মতো",
    "can you find a similar",
    "match this",
    "matches this",
    "ম্যাচিং",
)


def _deterministic_image_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def query_image_id_from_b64(image_b64: str | None) -> str | None:
    if not image_b64:
        return None
    payload = image_b64
    if "," in payload and payload.startswith("data:image/"):
        payload = payload.split(",", 1)[1]
    try:
        return "upload_" + _deterministic_image_hash(base64.b64decode(payload + "=="))
    except Exception:
        return "upload_" + hashlib.sha256(image_b64.encode("utf-8")).hexdigest()[:16]


def apply_owner_corrections(
    *,
    catalog: dict[str, InventoryItemRecord],
    results: list[ImageMatchResult],
    query_image_id: str | None,
    corrections: list[dict[str, Any]],
) -> list[ImageMatchResult]:
    """Let owner-confirmed mappings override raw visual similarity.

    Visual embeddings are probabilistic. A correction record is business truth:
    if the owner maps an upload to a product/design, ranking should respect it.
    """

    if not query_image_id:
        return results
    matching = [
        correction for correction in corrections
        if correction.get("query_image_id") == query_image_id
    ]
    if not matching:
        return results

    correction = matching[-1]
    correction_type = str(correction.get("correction_type") or "")
    wrong_product_id = correction.get("wrong_product_id")
    filtered = [
        result for result in results
        if not wrong_product_id or result.product_id != wrong_product_id
    ]
    if correction_type == "no_match":
        return filtered if wrong_product_id else []

    correct_product_id = correction.get("correct_product_id")
    if not correct_product_id or correct_product_id not in catalog:
        return filtered

    item = catalog[correct_product_id]
    image = primary_image_asset(item)
    attrs = item.attributes or {}
    score_by_type = {
        "exact_product": 0.995,
        "same_design": 0.92,
        "similar": 0.78,
    }
    label_by_type = {
        "exact_product": "confirmed_exact",
        "same_design": "confirmed_same_design_variant",
        "similar": "similar_style",
    }
    match_type_by_type = {
        "exact_product": "owner_confirmed_exact",
        "same_design": "owner_confirmed_same_design",
        "similar": "owner_confirmed_similar",
    }
    corrected = ImageMatchResult(
        product_id=item.product_id,
        name=item.name,
        score=score_by_type.get(correction_type, 0.78),
        match_type=match_type_by_type.get(correction_type, "owner_confirmed"),
        reasons=("owner correction", str(correction.get("notes") or correction_type)),
        price=item.price,
        currency=item.currency,
        stock=item.stock,
        image_url=primary_image_url(item),
        decision_label=label_by_type.get(correction_type, "similar_style"),
        variant_group_id=attrs.get("variant_group_id") or attrs.get("variant_group_name") or attrs.get("design_id"),
        design_id=attrs.get("design_id"),
        color=attrs.get("color") or attrs.get("color_family"),
        size=attrs.get("size") or attrs.get("size_options"),
        image_kind=image.kind if image else None,
        is_reference=bool(image.is_reference) if image else False,
        score_breakdown={
            "owner_correction": True,
            "correction_type": correction_type,
            "visual_score": score_by_type.get(correction_type, 0.78),
        },
    )
    remaining = [result for result in filtered if result.product_id != correct_product_id]
    return [corrected, *remaining]


def _color_histogram_score(pixels_a: list[int], pixels_b: list[int]) -> float:
    if not pixels_a or not pixels_b:
        return 0.5
    size = min(len(pixels_a), len(pixels_b))
    dot = sum(pixels_a[i] * pixels_b[i] for i in range(size))
    mag_a = math.sqrt(sum(x * x for x in pixels_a[:size]))
    mag_b = math.sqrt(sum(x * x for x in pixels_b[:size]))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _extract_dominant_color_from_b64(b64_data: str) -> str | None:
    try:
        raw = base64.b64decode(b64_data + "==")
        if len(raw) < 16:
            return None
        color_byte = raw[8] % 8
        color_map = {0: "red", 1: "blue", 2: "green", 3: "black", 4: "white", 5: "gold", 6: "maroon", 7: "navy"}
        return color_map.get(color_byte)
    except Exception:
        return None


def is_image_search_query(text: str) -> bool:
    normalized = text.casefold()
    return any(phrase in normalized for phrase in IMAGE_QUERY_PHRASES)


class ImageMatcher:
    """Metadata-aware visual similarity engine.

    In production, this integrates image embeddings. In deterministic/local mode,
    it scores candidates using product metadata (design_id, color_family, category,
    work_type) to simulate image matching. The scoring ensures grounded responses
    without claiming exact visual match unless SKU/design metadata proves it.
    """

    def __init__(self, catalog: dict[str, InventoryItemRecord]) -> None:
        self._catalog = catalog

    def search(
        self,
        *,
        query_text: str,
        image_b64: str | None = None,
        category_hint: str | None = None,
        color_hint: str | None = None,
        budget_max: float | None = None,
        top_k: int = 5,
    ) -> list[ImageMatchResult]:
        dominant_color = None
        if image_b64:
            dominant_color = _extract_dominant_color_from_b64(image_b64)

        effective_color = color_hint or dominant_color
        effective_category = category_hint or _infer_category_from_text(query_text)

        candidates: list[tuple[float, str, str, list[str]]] = []

        for product_id, item in self._catalog.items():
            if item.stock == 0 and item.status and item.status.casefold() not in ("active", "available"):
                continue
            if budget_max and item.price and item.price > budget_max:
                continue

            score, reasons, match_type = self._score_item(
                item=item,
                query_text=query_text,
                effective_color=effective_color,
                effective_category=effective_category,
                image_b64=image_b64,
            )
            if score > 0.1:
                candidates.append((score, product_id, match_type, reasons))

        candidates.sort(key=lambda x: x[0], reverse=True)

        results: list[ImageMatchResult] = []
        for score, product_id, match_type, reasons in candidates[:top_k]:
            item = self._catalog[product_id]
            image_url = primary_image_url(item)
            results.append(
                ImageMatchResult(
                    product_id=product_id,
                    name=item.name,
                    score=round(score, 3),
                    match_type=match_type,
                    reasons=tuple(reasons),
                    price=item.price,
                    currency=item.currency,
                    stock=item.stock,
                    image_url=image_url,
                )
            )
        return results

    def _score_item(
        self,
        item: InventoryItemRecord,
        query_text: str,
        effective_color: str | None,
        effective_category: str | None,
        image_b64: str | None,
    ) -> tuple[float, list[str], str]:
        score = 0.0
        reasons: list[str] = []
        match_type = "visual_similar"
        attrs = item.attributes
        normalized_text = query_text.casefold()

        if effective_category:
            item_cat = (attrs.get("category_key") or (item.category or "")).casefold()
            if item_cat == effective_category.casefold():
                score += 0.4
                reasons.append(f"category match: {effective_category}")
            elif effective_category.casefold() in item_cat or item_cat in effective_category.casefold():
                score += 0.2

        if effective_color:
            item_color = (attrs.get("color") or "").casefold()
            item_family = (attrs.get("color_family") or "").casefold()
            if effective_color.casefold() == item_color:
                score += 0.3
                reasons.append(f"exact color match: {effective_color}")
            elif effective_color.casefold() == item_family:
                score += 0.15
                reasons.append(f"color family match: {effective_color}")

        design_id = attrs.get("design_id") or ""
        if design_id and any(w in normalized_text for w in design_id.split("-")):
            score += 0.25
            reasons.append(f"design pattern match: {design_id}")
            match_type = "same_design_variant"

        work_type = attrs.get("work_type") or ""
        work_terms = ["buti", "katan", "jamdani", "muslin", "embroidery", "printed", "block print"]
        for term in work_terms:
            if term in normalized_text and term in work_type.casefold():
                score += 0.15
                reasons.append(f"work type match: {term}")
                break

        if item.stock > 0:
            score += 0.05
            reasons.append("in stock")

        if item.stock == 0:
            score *= 0.3

        return score, reasons, match_type

    def build_answer(self, results: list[ImageMatchResult], query_text: str) -> str:
        if not results:
            return (
                "I could not find a close visual match in the current catalog. "
                "Please describe the color, fabric, or occasion and I will search by details."
            )
        lines: list[str] = []
        in_stock = [r for r in results if r.stock > 0]
        out_of_stock = [r for r in results if r.stock == 0]

        if in_stock:
            lines.append(f"I found {len(in_stock)} visually similar product(s) in stock:\n")
            for i, r in enumerate(in_stock[:3], 1):
                label = "same design" if r.match_type == "same_design_variant" else "visually similar"
                lines.append(
                    f"{i}. **{r.name}** — BDT {r.price:,.0f} | Stock: {r.stock} | {label.title()}"
                )
                if r.reasons:
                    lines.append(f"   (Matched: {', '.join(r.reasons[:2])})")

            lines.append(
                "\n*Note: These are similar design/color matches. "
                "Exact same SKU can only be confirmed with a product code.*"
            )
        if out_of_stock:
            lines.append(f"\nCurrently out of stock but similar:")
            for r in out_of_stock[:2]:
                lines.append(f"- {r.name} (out of stock)")

        return "\n".join(lines)


def finalize_image_search(
    *,
    catalog: dict[str, InventoryItemRecord],
    results: list[ImageMatchResult],
    query_text: str,
    requested_color: str | None = None,
    top_k: int = 6,
) -> ImageSearchDecision:
    """Apply business-safe product identity rules after raw visual retrieval."""

    normalized_color = normalize_color(requested_color) or infer_requested_color(query_text)
    enriched = [_enrich_hit(hit, catalog) for hit in results if hit.product_id in catalog]
    enriched.sort(key=lambda hit: _primary_selection_key(hit), reverse=True)

    if not enriched:
        return ImageSearchDecision(
            answer=(
                "Ei screenshot er exact product catalog e confident bhabe pachchi na. "
                "Color, size, ba category bolle ami similar options dekhate pari."
            ),
            hits=[],
            decision_label="no_confident_match",
            primary_product_id=None,
            same_design_variant_ids=(),
            similar_product_ids=(),
            requested_color=normalized_color,
            available_colors=(),
            score_breakdown={"reason": "no_raw_visual_hits"},
        )

    primary = enriched[0]
    enriched = _prune_visual_outliers(enriched, primary)
    enriched = _apply_exact_match_gate(enriched)
    primary = enriched[0]
    group_key = primary.variant_group_id or primary.design_id
    same_design_items = (
        _same_design_items(catalog, group_key)
        if _allows_same_design_expansion(primary) and group_key
        else []
    )
    available_colors = tuple(_unique_color(item) for item in same_design_items if _unique_color(item))
    available_colors = tuple(dict.fromkeys(available_colors))

    requested_color_items = [
        item for item in same_design_items
        if normalized_color and _color_matches(item, normalized_color)
    ]
    in_stock_requested = [item for item in requested_color_items if item.stock > 0]

    # Size availability — pick the colour-resolved record when possible, else
    # the primary product, so "M size ache?" lands on the right SKU.
    requested_size = infer_requested_size(query_text)
    size_subject = (
        in_stock_requested[0]
        if in_stock_requested
        else (requested_color_items[0] if requested_color_items else catalog.get(primary.product_id))
    )
    size_availability = _size_availability(size_subject, requested_size)

    variant_label = (
        "confirmed_same_design_variant"
        if primary.decision_label in {"confirmed_exact", "confirmed_same_design_variant", "likely_same_design"}
        else "similar_style"
    )
    variant_hits = [_result_from_item(item, primary, variant_label) for item in same_design_items]
    merged_hits = _merge_hits(enriched, variant_hits)
    merged_hits = _apply_requested_color_priority(merged_hits, normalized_color)
    if not normalized_color:
        merged_hits = _ensure_primary_first(merged_hits, primary.product_id)
    decision_label = _response_decision_label(primary, same_design_items, normalized_color, in_stock_requested)
    answer = _build_decision_answer(
        primary=primary,
        hits=merged_hits,
        decision_label=decision_label,
        same_design_items=same_design_items,
        requested_color=normalized_color,
        requested_color_items=requested_color_items,
        in_stock_requested=in_stock_requested,
        available_colors=available_colors,
        size_availability=size_availability,
    )
    same_design_ids = tuple(item.product_id for item in same_design_items if item.product_id != primary.product_id)
    similar_ids = tuple(hit.product_id for hit in merged_hits if hit.product_id not in {primary.product_id, *same_design_ids})
    follow_up_question = _next_best_question(decision_label, available_colors, size_availability)
    return ImageSearchDecision(
        answer=answer,
        hits=merged_hits[:top_k],
        decision_label=decision_label,
        primary_product_id=primary.product_id,
        same_design_variant_ids=same_design_ids,
        similar_product_ids=similar_ids[: max(0, top_k - 1)],
        requested_color=normalized_color,
        available_colors=available_colors,
        score_breakdown={
            "primary_visual_score": primary.score,
            "primary_decision_label": primary.decision_label,
            "primary_image_kind": primary.image_kind,
            "primary_is_reference": primary.is_reference,
            "same_design_count": len(same_design_items),
            "requested_color": normalized_color,
            "requested_size": requested_size,
        },
        requested_size=requested_size,
        follow_up_question=follow_up_question,
    )


def infer_requested_color(text: str) -> str | None:
    normalized = text.casefold()
    color_aliases = {
        "black": ("black", "kalo", "কালো"),
        "white": ("white", "shada", "সাদা"),
        "blue": ("blue", "nil", "নীল", "navy"),
        "green": ("green", "sobuj", "সবুজ", "olive"),
        "red": ("red", "lal", "লাল", "maroon"),
        "pink": ("pink", "golapi", "গোলাপি"),
        "yellow": ("yellow", "holud", "হলুদ", "mustard"),
        "gold": ("gold", "golden", "sonali", "সোনালি"),
        "silver": ("silver", "rupali", "রুপালি"),
        "brown": ("brown", "tan", "বাদামি"),
        "grey": ("grey", "gray", "dhushor", "ধূসর"),
        "purple": ("purple", "beguni", "বেগুনি", "lavender"),
        "cream": ("cream", "beige", "off white"),
    }
    for color, aliases in color_aliases.items():
        if any(alias in normalized for alias in aliases):
            return color
    return None


def normalize_color(value: str | None) -> str | None:
    if not value:
        return None
    return infer_requested_color(value) or value.strip().casefold()


_SIZE_LETTERS = ("XXXL", "XXL", "XL", "XS", "S", "M", "L")


def infer_requested_size(text: str) -> str | None:
    """Pull a letter size (S/M/L/XL/...) out of customer text.

    Conservative: we only match letter sizes as whole tokens so "M" in "M size
    ache?" hits but "M" inside a word does not. Numeric sizes are deferred —
    the boutique data is letter-size today.
    """
    if not text:
        return None
    padded = " " + text.upper().replace("?", " ").replace(",", " ").replace(".", " ").replace("'", " ") + " "
    for size in _SIZE_LETTERS:  # already ordered longest-first
        if f" {size} " in padded:
            return size
    return None


def _enrich_hit(hit: ImageMatchResult, catalog: dict[str, InventoryItemRecord]) -> ImageMatchResult:
    item = catalog[hit.product_id]
    image = primary_image_asset(item)
    attrs = item.attributes or {}
    image_kind = image.kind if image else None
    is_reference = bool(image.is_reference) if image else False
    decision_label = _hit_decision_label(hit.score, image_kind, is_reference, hit.match_type)
    reasons = list(hit.reasons)
    if is_reference:
        reasons.append("reference image only")
    if attrs.get("variant_group_id") or attrs.get("design_id"):
        reasons.append("catalog design identity available")
    return ImageMatchResult(
        product_id=hit.product_id,
        name=item.name,
        score=hit.score,
        match_type=hit.match_type,
        reasons=tuple(dict.fromkeys(reasons)),
        price=item.price,
        currency=item.currency,
        stock=item.stock,
        image_url=primary_image_url(item),
        decision_label=decision_label,
        variant_group_id=attrs.get("variant_group_id") or attrs.get("variant_group_name") or attrs.get("design_id"),
        design_id=attrs.get("design_id"),
        color=attrs.get("color") or attrs.get("color_family"),
        size=attrs.get("size") or attrs.get("size_options"),
        image_kind=image_kind,
        is_reference=is_reference,
        score_breakdown={
            "visual_score": hit.score,
            "stock": item.stock,
            "category": item.category or attrs.get("category_key") or "",
            "reference_image": is_reference,
            "product_photo": image_kind == "product_photo",
            "decision_label": decision_label,
        },
    )


def _hit_decision_label(score: float, image_kind: str | None, is_reference: bool, match_type: str) -> str:
    if match_type == "owner_confirmed_exact":
        return "confirmed_exact"
    if match_type == "owner_confirmed_same_design":
        return "confirmed_same_design_variant"
    if match_type == "owner_confirmed_similar":
        return "similar_style"
    if match_type == "same_design_variant":
        return "confirmed_same_design_variant"
    if not is_reference and image_kind == "product_photo" and score >= 0.9:
        return "confirmed_exact"
    if not is_reference and image_kind == "product_photo" and score >= 0.82:
        return "likely_same_design"
    if score >= 0.18:
        return "similar_style"
    return "no_confident_match"


def _primary_selection_key(hit: ImageMatchResult) -> tuple[float, float, float]:
    """Select the visual identity anchor before expanding variant groups.

    Variant/design expansion is powerful, so the primary anchor must be chosen
    mostly from raw visual confidence. Product-photo truth is a small bonus, not
    a license to beat a much stronger different-category visual match.
    """

    owner_bonus = 1.0 if hit.match_type.startswith("owner_confirmed") else 0.0
    label_bonus = {
        "confirmed_exact": 0.08,
        "confirmed_same_design_variant": 0.06,
        "likely_same_design": 0.035,
        "similar_style": 0.0,
        "no_confident_match": -0.2,
    }.get(hit.decision_label, 0.0)
    truth_bonus = 0.03 if not hit.is_reference and hit.image_kind == "product_photo" else -0.02 if hit.is_reference else 0.0
    stock_bonus = 0.01 if hit.stock > 0 else 0.0
    return (owner_bonus, hit.score + label_bonus + truth_bonus + stock_bonus, hit.score)


# Margin needed between top-1 and top-2 before claiming an exact match. CLIP
# scores are cosine in roughly [0,1]; 0.04 is small enough that genuinely
# unique matches still pass, large enough to catch two-near-twin false exacts.
_EXACT_MATCH_TOP_MARGIN = 0.04


def _apply_exact_match_gate(enriched: list[ImageMatchResult]) -> list[ImageMatchResult]:
    """Demote a 'confirmed_exact' primary when the evidence is fragile.

    Three reasons to demote (any one is enough):
      1. Only the text-tag channel matched — there is no visual signal at all.
      2. Multiple top candidates are within the margin — no clear winner, so
         the "exact" claim is unsafe.
      3. The matched-channels list is populated and contains only the pattern
         channel without full-visual agreement — the design rhymes, but full
         visual identity is not confirmed.

    Owner-confirmed matches are exempt: owner ground truth wins by definition.
    Hits without matched_channels metadata (metadata fallback, or synthesized
    test hits) get only the margin check, preserving existing behaviour.
    """
    if not enriched:
        return enriched
    primary = enriched[0]
    if primary.decision_label != "confirmed_exact":
        return enriched
    if primary.match_type.startswith("owner_confirmed"):
        return enriched
    breakdown = primary.score_breakdown or {}
    channels = breakdown.get("matched_channels")
    if isinstance(channels, list) and channels:
        channel_set = {str(c) for c in channels}
        if channel_set == {"text_visual_tags"}:
            return _downgrade_primary(enriched, "likely_same_design", "no_visual_channel")
        if channel_set == {"pattern_visual"}:
            return _downgrade_primary(enriched, "likely_same_design", "pattern_only")
    if len(enriched) >= 2:
        runner_up = next(
            (
                hit for hit in enriched[1:]
                if hit.product_id != primary.product_id
                and not _same_visual_identity_group(primary, hit)
            ),
            None,
        )
        if runner_up is not None:
            margin = primary.score - runner_up.score
            if margin < _EXACT_MATCH_TOP_MARGIN:
                return _downgrade_primary(enriched, "likely_same_design", "thin_top_margin")
    return enriched


def _same_visual_identity_group(left: ImageMatchResult, right: ImageMatchResult) -> bool:
    """True when two hits are catalog-confirmed sibling variants.

    The exact-match gate should catch ambiguous unrelated near-twins. It should
    not demote a real product-photo match just because same-design color
    variants are close in embedding space; that is exactly why
    `variant_group_id`/`design_id` exists.
    """

    left_keys = {
        _normalize_identity(left.variant_group_id),
        _normalize_identity(left.design_id),
    } - {""}
    right_keys = {
        _normalize_identity(right.variant_group_id),
        _normalize_identity(right.design_id),
    } - {""}
    return bool(left_keys & right_keys)


def _downgrade_primary(
    enriched: list[ImageMatchResult],
    new_label: str,
    reason: str,
) -> list[ImageMatchResult]:
    primary = enriched[0]
    updated_breakdown = dict(primary.score_breakdown or {})
    updated_breakdown["exact_match_gate"] = f"demoted:{reason}"
    demoted = ImageMatchResult(
        product_id=primary.product_id,
        name=primary.name,
        score=primary.score,
        match_type=primary.match_type,
        reasons=primary.reasons + (f"exact-match gate demoted ({reason})",),
        price=primary.price,
        currency=primary.currency,
        stock=primary.stock,
        image_url=primary.image_url,
        decision_label=new_label,
        variant_group_id=primary.variant_group_id,
        design_id=primary.design_id,
        color=primary.color,
        size=primary.size,
        image_kind=primary.image_kind,
        is_reference=primary.is_reference,
        score_breakdown=updated_breakdown,
    )
    return [demoted, *enriched[1:]]


def _allows_same_design_expansion(primary: ImageMatchResult) -> bool:
    if primary.match_type.startswith("owner_confirmed"):
        return True
    return primary.decision_label in {"confirmed_exact", "confirmed_same_design_variant", "likely_same_design"}


def _prune_visual_outliers(
    hits: list[ImageMatchResult],
    primary: ImageMatchResult,
) -> list[ImageMatchResult]:
    """Drop weak different-category visual neighbors after a strong primary.

    CLIP often returns visually plausible but commercially absurd neighbors
    when images share color/background. If the top hit is very strong, a much
    weaker different-category item should not appear as a salesperson-style
    recommendation.
    """

    primary_category = _hit_category(primary)
    if primary.score < 0.85 or not primary_category:
        return hits
    pruned: list[ImageMatchResult] = []
    for hit in hits:
        if hit.product_id == primary.product_id:
            pruned.append(hit)
            continue
        category = _hit_category(hit)
        if category == primary_category or hit.score >= primary.score - 0.18:
            pruned.append(hit)
    return pruned


def _hit_category(hit: ImageMatchResult) -> str:
    return str((hit.score_breakdown or {}).get("category") or "").strip().casefold()


def _response_decision_label(
    primary: ImageMatchResult,
    same_design_items: list[InventoryItemRecord],
    requested_color: str | None,
    in_stock_requested: list[InventoryItemRecord],
) -> str:
    if requested_color and in_stock_requested:
        return "confirmed_same_design_variant"
    if requested_color and same_design_items:
        return "similar_style"
    if primary.decision_label == "confirmed_exact":
        return "confirmed_exact"
    if primary.decision_label in {"likely_same_design", "confirmed_same_design_variant"}:
        return primary.decision_label
    if primary.score < 0.16:
        return "no_confident_match"
    return "similar_style"


def _same_design_items(catalog: dict[str, InventoryItemRecord], group_key: str | None) -> list[InventoryItemRecord]:
    if not group_key:
        return []
    normalized = _normalize_identity(group_key)
    items = [
        item for item in catalog.values()
        if normalized in {
            _normalize_identity(item.attributes.get("variant_group_id")),
            _normalize_identity(item.attributes.get("variant_group_name")),
            _normalize_identity(item.attributes.get("design_id")),
        }
    ]
    return sorted(items, key=lambda item: (item.stock <= 0, _unique_color(item) or "", item.name.casefold()))


def _normalize_identity(value: str | None) -> str:
    return (value or "").casefold().replace(" ", "-").replace("_", "-")


def _result_from_item(
    item: InventoryItemRecord,
    primary: ImageMatchResult,
    decision_label: str,
) -> ImageMatchResult:
    image = primary_image_asset(item)
    attrs = item.attributes or {}
    score = primary.score if item.product_id == primary.product_id else max(0.01, primary.score - 0.03)
    return ImageMatchResult(
        product_id=item.product_id,
        name=item.name,
        score=round(score, 4),
        match_type="same_design_variant",
        reasons=("same catalog design/variant group",),
        price=item.price,
        currency=item.currency,
        stock=item.stock,
        image_url=primary_image_url(item),
        decision_label=decision_label if item.product_id != primary.product_id else primary.decision_label,
        variant_group_id=attrs.get("variant_group_id") or attrs.get("variant_group_name") or attrs.get("design_id"),
        design_id=attrs.get("design_id"),
        color=attrs.get("color") or attrs.get("color_family"),
        size=attrs.get("size") or attrs.get("size_options"),
        image_kind=image.kind if image else None,
        is_reference=bool(image.is_reference) if image else False,
        score_breakdown={
            "visual_score": primary.score,
            "variant_group_bonus": 1.0,
            "stock": item.stock,
            "category": item.category or attrs.get("category_key") or "",
        },
    )


def _merge_hits(*groups: list[ImageMatchResult]) -> list[ImageMatchResult]:
    by_id: dict[str, ImageMatchResult] = {}
    for group in groups:
        for hit in group:
            existing = by_id.get(hit.product_id)
            if existing is None or _decision_sort_key(hit) > _decision_sort_key(existing):
                by_id[hit.product_id] = hit
    merged = list(by_id.values())
    merged.sort(key=lambda hit: _decision_sort_key(hit), reverse=True)
    return merged


def _apply_requested_color_priority(
    hits: list[ImageMatchResult],
    requested_color: str | None,
) -> list[ImageMatchResult]:
    if not requested_color:
        return hits
    return sorted(hits, key=lambda hit: (_color_value_matches(hit.color, requested_color), *list(_decision_sort_key(hit))), reverse=True)


def _ensure_primary_first(hits: list[ImageMatchResult], primary_product_id: str) -> list[ImageMatchResult]:
    return sorted(hits, key=lambda hit: (hit.product_id == primary_product_id, *list(_decision_sort_key(hit))), reverse=True)


def _decision_sort_key(hit: ImageMatchResult) -> tuple[float, float, float]:
    label_weight = {
        "confirmed_exact": 5.0,
        "confirmed_same_design_variant": 4.0,
        "likely_same_design": 3.0,
        "similar_style": 2.0,
        "no_confident_match": 0.0,
    }.get(hit.decision_label, 1.0)
    stock_weight = 1.0 if hit.stock > 0 else 0.0
    truth_weight = 1.0 if not hit.is_reference else 0.0
    return (label_weight, stock_weight + truth_weight, hit.score)


def _size_availability(
    item: InventoryItemRecord | None,
    requested_size: str | None,
) -> str | None:
    """Customer-facing size availability line for the chosen subject product.

    Returns a sentence to append to the answer when the customer asked about a
    size; returns None when no size was asked. Honest hedging when the catalog
    has only a comma-separated `size` string instead of true `size_stock`.
    """
    if not requested_size:
        return None
    if item is None:
        return f"**{requested_size}** size er stock catalog e clear na."
    # Lazy import to keep cyclic risk out of module load.
    from app.inventory.catalog_identity import (
        product_size_stock,
        product_size_stock_is_authoritative,
    )

    size_stock = product_size_stock(item)
    if not size_stock:
        return f"**{requested_size}** size er stock catalog e clear na — order korar age confirm korte hobe."
    requested = requested_size.upper()
    if requested in size_stock:
        count = size_stock[requested]
        if count > 0:
            return f"**{requested}** size ache, stock e {count} pcs."
        available = ", ".join(s for s, c in size_stock.items() if c > 0) or "kono size currently nei"
        return f"**{requested}** size currently nei. Available: {available}."
    if product_size_stock_is_authoritative(item):
        available = ", ".join(s for s, c in size_stock.items() if c > 0) or "kono size currently nei"
        return f"**{requested}** size catalog e nai. Available: {available}."
    return f"**{requested}** size catalog e clear na — order korar age confirm korte hobe."


def _reference_image_reason(primary: ImageMatchResult) -> str:
    """One-line note explaining why an exact-match claim is withheld.

    Customers should not be left wondering why the bot says "closest match"
    instead of "exact" — name the constraint honestly.
    """
    if primary.is_reference or primary.image_kind != "product_photo":
        return " (Note: the catalog photo is a demo/reference image, so exact SKU cannot be confirmed.)"
    return ""


def _build_decision_answer(
    *,
    primary: ImageMatchResult,
    hits: list[ImageMatchResult],
    decision_label: str,
    same_design_items: list[InventoryItemRecord],
    requested_color: str | None,
    requested_color_items: list[InventoryItemRecord],
    in_stock_requested: list[InventoryItemRecord],
    available_colors: tuple[str, ...],
    size_availability: str | None = None,
) -> str:
    price = f"BDT {primary.price:,.0f}" if isinstance(primary.price, (int, float)) else "price not set"
    reference_note = _reference_image_reason(primary)
    size_suffix = f" {size_availability}" if size_availability else ""
    next_q = _next_best_question(decision_label, available_colors, size_availability)
    next_q_suffix = f" {next_q}" if next_q else ""
    if decision_label == "confirmed_exact":
        color_line = _available_color_sentence(available_colors)
        return (
            f"Yes, this looks like **{primary.name}** ({price}, {primary.stock} in stock)."
            + (f" {color_line}" if color_line else "")
            + size_suffix
            + next_q_suffix
        )
    if requested_color and in_stock_requested:
        names = ", ".join(f"{item.name} ({item.stock} in stock)" for item in in_stock_requested[:3])
        return (
            f"Yes, same design e **{requested_color}** option available: {names}."
            + size_suffix
            + next_q_suffix
        )
    if requested_color and requested_color_items and not in_stock_requested:
        color_line = _available_color_sentence(available_colors)
        return (
            f"Same design e **{requested_color}** catalog e ache, but currently stock e nei. "
            f"{color_line or 'Similar options niche dilam.'}"
            + size_suffix
            + next_q_suffix
        )
    if requested_color and same_design_items and not requested_color_items:
        color_line = _available_color_sentence(available_colors)
        return (
            f"Same design ta peyechi, but **{requested_color}** color currently catalog e nei. "
            f"{color_line or 'Closest similar options niche dilam.'}"
            + size_suffix
            + next_q_suffix
        )
    if decision_label in {"confirmed_same_design_variant", "likely_same_design"}:
        color_line = _available_color_sentence(available_colors)
        return (
            f"Ei design er closest match **{primary.name}** ({price}, {primary.stock} in stock)."
            + (f" {color_line}" if color_line else "")
            + size_suffix
            + reference_note
            + next_q_suffix
        )
    similar = [hit for hit in hits if hit.stock > 0][:3]
    if similar:
        names = ", ".join(f"{hit.name} ({'BDT ' + format(hit.price, ',.0f') if hit.price else 'price N/A'})" for hit in similar)
        return (
            f"Exact same confirm korte parchi na, but closest similar options: {names}."
            + size_suffix
            + reference_note
            + next_q_suffix
        )
    return "Ei screenshot er exact product confident bhabe pachchi na. Color, size, ba category bolle ami aro narrow kore dekhate pari."


def _next_best_question(
    decision_label: str,
    available_colors: tuple[str, ...],
    size_availability: str | None,
) -> str | None:
    """One natural follow-up question per decision label.

    Skip when a size answer was already given (the customer just got that
    answer; nudging them about size again is noisy) and when we have nothing
    confident enough to ask about.
    """
    if size_availability:
        return "Order korte parle bolun, ami size lock kore dichi."
    if decision_label == "confirmed_exact":
        if available_colors:
            return "Other colors dekhabo?"
        return "Order korbo?"
    if decision_label == "confirmed_same_design_variant":
        return "M size check korbo, naki onno color?"
    if decision_label == "likely_same_design":
        return "Same design er exact color confirm korbo?"
    if decision_label == "similar_style":
        return "Cheaper option, naki onno category dekhabo?"
    return None


def _available_color_sentence(colors: tuple[str, ...]) -> str:
    if not colors:
        return ""
    return "Available colors: " + ", ".join(colors[:8]) + "."


def _unique_color(item: InventoryItemRecord) -> str:
    return (item.attributes.get("color") or item.attributes.get("color_family") or "").strip().casefold()


def _color_matches(item: InventoryItemRecord, requested_color: str) -> bool:
    return _color_value_matches(item.attributes.get("color"), requested_color) or _color_value_matches(
        item.attributes.get("color_family"), requested_color
    )


def _color_value_matches(value: str | None, requested_color: str) -> bool:
    if not value:
        return False
    normalized_value = normalize_color(value) or value.casefold()
    normalized_requested = normalize_color(requested_color) or requested_color.casefold()
    return normalized_requested in normalized_value or normalized_value in normalized_requested


def _infer_category_from_text(text: str) -> str | None:
    text = text.casefold()
    category_hints = {
        "saree": ("saree", "sari", "শাড়ি", "jamdani", "katan", "muslin"),
        "bag": ("bag", "clutch", "purse", "handbag", "ব্যাগ", "পটলি"),
        "shoes": ("shoe", "sandal", "loafer", "heel", "জুতা"),
        "jewelry": ("jewelry", "necklace", "bangle", "earring", "গয়না", "চুড়ি"),
        "panjabi": ("panjabi", "punjabi", "kurta", "পাঞ্জাবি"),
        "cosmetics": ("lipstick", "foundation", "kajal", "makeup", "লিপস্টিক"),
        "beauty": ("sunscreen", "face wash", "serum", "cream", "সানস্ক্রিন"),
        "perfume": ("perfume", "attar", "fragrance", "পারফিউম"),
    }
    for cat, terms in category_hints.items():
        if any(t in text for t in terms):
            return cat
    return None


def primary_image_asset(item: InventoryItemRecord) -> InventoryImageAsset | None:
    if item.images:
        for image in item.images:
            if image.role == "primary":
                return image
        return item.images[0]
    return None


def primary_image_url(item: InventoryItemRecord) -> str | None:
    asset = primary_image_asset(item)
    if asset is not None:
        return asset.url or asset.local_path
    images = item.metadata.get("images") or item.attributes.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            value = first.get("url") or first.get("local_path")
            return str(value) if value else None
        if isinstance(first, str):
            return first
    return None
