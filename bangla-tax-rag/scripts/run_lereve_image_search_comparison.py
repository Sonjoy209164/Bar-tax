from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryItemRecord  # noqa: E402
from app.inventory.catalog_taxonomy import canonicalize, compatible_categories_for  # noqa: E402
from app.inventory.clip_matcher import EMBEDDING_VERSION, _cosine, embedding_metadata  # noqa: E402
from scripts.run_lereve_clip100_baseline import (  # noqa: E402
    cached_encode,
    load_cache,
    percentile,
    ratio,
    relative_or_abs,
    save_cache,
)


DEFAULT_CATALOG = ROOT / "data" / "inventory" / "lereve_clip1000_catalog.jsonl"
DEFAULT_EVAL = ROOT / "evaluation" / "lereve_clip1000_exact_eval.jsonl"
DEFAULT_CACHE = ROOT / "data" / "inventory" / "lereve_clip1000_clip_vectors.json"
DEFAULT_OUT_DIR = ROOT / "results"

UNKNOWN_VALUES = {"", "unknown", "none", "n/a", "fashion", "product"}


@dataclass(frozen=True)
class RankedHit:
    product_id: str
    clip_score: float
    metadata_score: float
    final_score: float
    category_match: bool
    color_match: bool
    category: str
    color: str
    name: str
    decision_label: str = "candidate"
    accepted_exact: bool = False
    decision_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "clip_score": round(self.clip_score, 6),
            "metadata_score": round(self.metadata_score, 6),
            "final_score": round(self.final_score, 6),
            "category_match": self.category_match,
            "color_match": self.color_match,
            "category": self.category,
            "color": self.color,
            "name": self.name,
            "decision_label": self.decision_label,
            "accepted_exact": self.accepted_exact,
            "decision_reason": self.decision_reason,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Le Reve image-search method comparison on the frozen exact-product eval set: "
            "CLIP-only, CLIP + metadata-factor rerank, and CIF-RAG guarded decision."
        )
    )
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--eval", default=str(DEFAULT_EVAL))
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--limit", type=int, default=0, help="Optional cap for quick debugging. 0 = all cases.")
    parser.add_argument("--force-cache", action="store_true")
    parser.add_argument(
        "--allow-encode",
        action="store_true",
        help="Encode missing images with CLIP. Default is cache-only for reproducible/offline ablations.",
    )
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    eval_path = Path(args.eval)
    cache_path = Path(args.cache_path)
    catalog = load_catalog(catalog_path)
    cases = read_jsonl(eval_path)
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    if not catalog:
        raise SystemExit(f"No catalog rows found: {catalog_path}")
    if not cases:
        raise SystemExit(f"No eval cases found: {eval_path}")

    started = perf_counter()
    cache = {} if args.force_cache else load_cache(cache_path)
    catalog_vectors = encode_catalog(catalog, cache, allow_encode=args.allow_encode)
    methods = run_methods(
        catalog=catalog,
        catalog_vectors=catalog_vectors,
        cases=cases,
        cache=cache,
        allow_encode=args.allow_encode,
    )
    save_cache(cache_path, cache)
    latency_ms = (perf_counter() - started) * 1000

    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    payload = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "catalog": relative_or_abs(catalog_path),
        "eval": relative_or_abs(eval_path),
        "cache_path": relative_or_abs(cache_path),
        "model": embedding_metadata(),
        "latency_ms": round(latency_ms, 2),
        "method_notes": {
            "clip_only_rgb_cosine": "Raw CLIP cosine over indexed primary product images.",
            "clip_metadata_factor_rerank": (
                "CLIP plus query category/color factors from the labeled eval set. "
                "This is an upper-bound proxy for a future visual factor extractor, not a customer-visible oracle."
            ),
            "cif_rag_without_claim_contracts": (
                "Ablation: keeps the visual risk score/margin gate, but removes typed claim-contract evidence "
                "such as category agreement and product-photo proof before accepting an exact-product claim."
            ),
            "cif_rag_without_risk_policy": (
                "Ablation: keeps typed claim-contract evidence such as category and product-photo proof, "
                "but removes score/margin risk gating before accepting an exact-product claim."
            ),
            "cif_rag_guarded_decision": (
                "Uses the metadata-reranked list, then only accepts exact product claims when category, "
                "score, margin, and product-photo evidence pass a conservative commerce-risk gate."
            ),
        },
        "selection": {
            "products": len(catalog),
            "query_images": len(cases),
            "policy": "same eval set as CLIP-only baseline; held-out gallery query image per product",
        },
        "methods": methods,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"lereve_clip{len(cases)}_comparison_{run_id}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print("Le Reve image-search comparison complete")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    for name, result in methods.items():
        metrics = result["metrics"]
        print(
            f"  {name}: "
            f"top1={metrics['top1_accuracy']:.1%}, "
            f"top5={metrics['top5_recall']:.1%}, "
            f"top10={metrics['top10_recall']:.1%}, "
            f"wrong_category={metrics['wrong_category_top1_rate']:.1%}"
        )
    return 0


def load_catalog(path: Path) -> dict[str, InventoryItemRecord]:
    catalog: dict[str, InventoryItemRecord] = {}
    for row in read_jsonl(path):
        item = InventoryItemRecord.model_validate(row)
        catalog[item.product_id] = item
    return catalog


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def encode_catalog(
    catalog: dict[str, InventoryItemRecord],
    cache: dict[str, Any],
    *,
    allow_encode: bool,
) -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    for product_id, item in catalog.items():
        if not item.images:
            continue
        image_path = item.images[0].local_path
        if not image_path:
            continue
        vector = cache_or_encode(image_path, cache, allow_encode=allow_encode)
        if vector:
            vectors[product_id] = vector
    missing = sorted(set(catalog) - set(vectors))
    if missing:
        raise SystemExit(
            f"Missing cached vectors for {len(missing)} catalog images; first missing: {missing[:5]}. "
            "Rerun with --allow-encode on a machine that has the CLIP model available."
        )
    return vectors


def run_methods(
    *,
    catalog: dict[str, InventoryItemRecord],
    catalog_vectors: dict[str, list[float]],
    cases: list[dict[str, Any]],
    cache: dict[str, Any],
    allow_encode: bool,
) -> dict[str, Any]:
    clip_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    no_contract_rows: list[dict[str, Any]] = []
    no_risk_rows: list[dict[str, Any]] = []
    cif_rows: list[dict[str, Any]] = []

    product_ids = list(catalog_vectors)
    product_index = {product_id: index for index, product_id in enumerate(product_ids)}
    vector_matrix = normalized_matrix([catalog_vectors[product_id] for product_id in product_ids])
    catalog_factors = build_catalog_factor_cache(product_ids, catalog)
    empty_mask = np.zeros(len(product_ids), dtype=bool)

    for case in cases:
        query_vector = cache_or_encode(case["image_path"], cache, allow_encode=allow_encode)
        if not query_vector:
            error_row = {"case": case, "error": "query_encode_failed", "rank": None, "hits": []}
            clip_rows.append(error_row)
            metadata_rows.append(error_row)
            no_contract_rows.append(error_row)
            no_risk_rows.append(error_row)
            cif_rows.append(error_row)
            continue

        expected_index = product_index.get(case["expected_primary_product_id"])
        query_array = normalized_vector(query_vector)
        clip_scores = vector_matrix @ query_array
        metadata_scores, category_matches, color_matches = metadata_factor_score_arrays(
            case,
            catalog_factors,
            empty_mask,
        )
        final_scores = clip_scores + metadata_scores

        clip_top = top_indices(clip_scores, 10)
        metadata_top = top_indices_pair(final_scores, clip_scores, 10)
        no_contract_top, no_contract_decision = decide_vectorized_cif_top(
            metadata_top,
            clip_scores=clip_scores,
            final_scores=final_scores,
            metadata_scores=metadata_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            catalog_factors=catalog_factors,
            use_claim_contracts=False,
            use_risk_policy=True,
        )
        no_risk_top, no_risk_decision = decide_vectorized_cif_top(
            metadata_top,
            clip_scores=clip_scores,
            final_scores=final_scores,
            metadata_scores=metadata_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            catalog_factors=catalog_factors,
            use_claim_contracts=True,
            use_risk_policy=False,
        )
        cif_top, cif_decision = decide_vectorized_cif_top(
            metadata_top,
            clip_scores=clip_scores,
            final_scores=final_scores,
            metadata_scores=metadata_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            catalog_factors=catalog_factors,
            use_claim_contracts=True,
            use_risk_policy=True,
        )

        clip_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_single_score(clip_scores, expected_index),
                top_indices=clip_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=clip_scores,
                metadata_scores=np.zeros_like(metadata_scores),
                final_scores=clip_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=None,
            )
        )
        metadata_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, clip_scores, expected_index),
                top_indices=metadata_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=clip_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=None,
            )
        )
        no_contract_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, clip_scores, expected_index),
                top_indices=no_contract_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=clip_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=no_contract_decision,
            )
        )
        no_risk_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, clip_scores, expected_index),
                top_indices=no_risk_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=clip_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=no_risk_decision,
            )
        )
        cif_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, clip_scores, expected_index),
                top_indices=cif_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=clip_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=cif_decision,
            )
        )

    return {
        "clip_only_rgb_cosine": {
            "metrics": compute_metrics(clip_rows, decision_mode=False),
            "per_category_metrics": compute_per_category_metrics(clip_rows, decision_mode=False),
            "rows": clip_rows,
        },
        "clip_metadata_factor_rerank": {
            "metrics": compute_metrics(metadata_rows, decision_mode=False),
            "per_category_metrics": compute_per_category_metrics(metadata_rows, decision_mode=False),
            "rows": metadata_rows,
        },
        "cif_rag_without_claim_contracts": {
            "metrics": compute_metrics(no_contract_rows, decision_mode=True),
            "per_category_metrics": compute_per_category_metrics(no_contract_rows, decision_mode=True),
            "rows": no_contract_rows,
        },
        "cif_rag_without_risk_policy": {
            "metrics": compute_metrics(no_risk_rows, decision_mode=True),
            "per_category_metrics": compute_per_category_metrics(no_risk_rows, decision_mode=True),
            "rows": no_risk_rows,
        },
        "cif_rag_guarded_decision": {
            "metrics": compute_metrics(cif_rows, decision_mode=True),
            "per_category_metrics": compute_per_category_metrics(cif_rows, decision_mode=True),
            "rows": cif_rows,
        },
    }


def normalized_matrix(vectors: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


def normalized_vector(vector: list[float]) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return array
    return array / norm


def build_catalog_factor_cache(
    product_ids: list[str],
    catalog: dict[str, InventoryItemRecord],
) -> dict[str, Any]:
    category_to_mask: dict[str, np.ndarray] = {}
    color_to_mask: dict[str, np.ndarray] = {}
    stock_mask = np.zeros(len(product_ids), dtype=bool)
    product_photo_mask = np.zeros(len(product_ids), dtype=bool)

    for index, product_id in enumerate(product_ids):
        item = catalog[product_id]
        stock_mask[index] = item.stock > 0
        product_photo_mask[index] = image_can_confirm_exact(item)
        for category in normalized_item_categories(item):
            # Index by canonical form so query and catalog agree on aliases.
            canon = canonicalize(category) or category
            category_to_mask.setdefault(canon, np.zeros(len(product_ids), dtype=bool))[index] = True
        for color in normalized_item_colors(item):
            color_to_mask.setdefault(color, np.zeros(len(product_ids), dtype=bool))[index] = True

    return {
        "category_to_mask": category_to_mask,
        "color_to_mask": color_to_mask,
        "stock_mask": stock_mask,
        "product_photo_mask": product_photo_mask,
    }


def metadata_factor_score_arrays(
    case: dict[str, Any],
    catalog_factors: dict[str, Any],
    empty_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    score = np.zeros(len(empty_mask), dtype=np.float32)
    query_category = normalized_case_category(case)
    query_color = normalize_token(case.get("color_hint"))

    # No query category → no category evidence → treat all items as compatible
    # so the category guard does not incorrectly block unknown-category products.
    all_true_mask = np.ones(len(empty_mask), dtype=bool)
    category_matches = all_true_mask
    color_matches = empty_mask

    if query_category:
        # Build a union mask across all canonically compatible categories so
        # that aliases (e.g. dupatta/scarf, pant/jeans) are not penalised.
        compatible = compatible_categories_for(query_category)
        compat_mask = np.zeros(len(empty_mask), dtype=bool)
        for cat in compatible:
            compat_mask |= catalog_factors["category_to_mask"].get(cat, empty_mask)
        category_matches = compat_mask
        score += np.where(category_matches, 0.18, -0.08).astype(np.float32)

    if query_color:
        color_matches = catalog_factors["color_to_mask"].get(query_color, empty_mask)
        score += np.where(color_matches, 0.035, -0.012).astype(np.float32)

    score += np.where(catalog_factors["stock_mask"], 0.006, 0.0).astype(np.float32)
    return score, category_matches, color_matches


def top_indices(scores: np.ndarray, k: int) -> np.ndarray:
    if len(scores) <= k:
        indices = np.arange(len(scores))
    else:
        indices = np.argpartition(-scores, k - 1)[:k]
    return indices[np.argsort(-scores[indices], kind="stable")]


def top_indices_pair(primary_scores: np.ndarray, secondary_scores: np.ndarray, k: int) -> np.ndarray:
    if len(primary_scores) <= k:
        candidates = np.arange(len(primary_scores))
    else:
        candidates = np.argpartition(-primary_scores, k - 1)[:k]
    order = np.lexsort((-secondary_scores[candidates], -primary_scores[candidates]))
    return candidates[order]


def rank_single_score(scores: np.ndarray, expected_index: int | None) -> int | None:
    if expected_index is None:
        return None
    expected_score = scores[expected_index]
    return int(np.count_nonzero(scores > expected_score) + 1)


def rank_pair_score(
    primary_scores: np.ndarray,
    secondary_scores: np.ndarray,
    expected_index: int | None,
) -> int | None:
    if expected_index is None:
        return None
    expected_primary = primary_scores[expected_index]
    expected_secondary = secondary_scores[expected_index]
    better = (primary_scores > expected_primary) | (
        np.isclose(primary_scores, expected_primary) & (secondary_scores > expected_secondary)
    )
    return int(np.count_nonzero(better) + 1)


def decide_vectorized_cif_top(
    ranked_indices: np.ndarray,
    *,
    clip_scores: np.ndarray,
    final_scores: np.ndarray,
    metadata_scores: np.ndarray,
    category_matches: np.ndarray,
    color_matches: np.ndarray,
    catalog_factors: dict[str, Any],
    use_claim_contracts: bool,
    use_risk_policy: bool,
) -> tuple[np.ndarray, dict[str, Any] | None]:
    if len(ranked_indices) == 0:
        return ranked_indices, None
    top_index = int(ranked_indices[0])
    runner_up_index = int(ranked_indices[1]) if len(ranked_indices) > 1 else None
    category_safe = bool(category_matches[top_index])
    product_photo_safe = bool(catalog_factors["product_photo_mask"][top_index])
    claim_contract_passed = category_safe and product_photo_safe
    final_margin = float(final_scores[top_index] - final_scores[runner_up_index]) if runner_up_index is not None else 1.0
    clip_margin = float(clip_scores[top_index] - clip_scores[runner_up_index]) if runner_up_index is not None else 1.0
    risk_policy_passed = bool(clip_scores[top_index] >= 0.84 and (final_margin >= 0.025 or clip_margin >= 0.045))

    accepted_exact = bool(
        (claim_contract_passed or not use_claim_contracts)
        and (risk_policy_passed or not use_risk_policy)
    )
    if accepted_exact:
        label = "confirmed_exact"
        if use_claim_contracts and use_risk_policy:
            reason = "category/product-photo/score/margin evidence passed"
        elif not use_claim_contracts:
            reason = "ablation accepted exact without typed claim-contract evidence"
        else:
            reason = "ablation accepted exact without score/margin risk policy"
    elif use_claim_contracts and not category_safe:
        label = "no_confident_match"
        reason = "category guard blocked exact product claim"
    elif use_claim_contracts and not product_photo_safe:
        label = "no_confident_match"
        reason = "product-photo evidence guard blocked exact product claim"
    elif use_risk_policy and not risk_policy_passed and clip_scores[top_index] >= 0.78:
        label = "similar_style"
        reason = "visually plausible but exact margin or score is unsafe"
    elif use_risk_policy and not risk_policy_passed:
        label = "no_confident_match"
        reason = "visual score below commerce-safe threshold"
    elif clip_scores[top_index] >= 0.78:
        label = "similar_style"
        reason = "visually plausible, but exact claim was not accepted"
    else:
        label = "no_confident_match"
        reason = "no exact claim accepted"

    return ranked_indices, {
        "top_index": top_index,
        "decision_label": label,
        "accepted_exact": accepted_exact,
        "decision_reason": reason,
        "metadata_score": float(metadata_scores[top_index]),
        "category_match": bool(category_matches[top_index]),
        "color_match": bool(color_matches[top_index]),
    }


def row_from_vectorized_hits(
    *,
    case: dict[str, Any],
    expected_index: int | None,
    rank: int | None,
    top_indices: np.ndarray,
    product_ids: list[str],
    catalog: dict[str, InventoryItemRecord],
    clip_scores: np.ndarray,
    metadata_scores: np.ndarray,
    final_scores: np.ndarray,
    category_matches: np.ndarray,
    color_matches: np.ndarray,
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    expected = case["expected_primary_product_id"]
    top_index = int(top_indices[0]) if len(top_indices) else None
    top_product_id = product_ids[top_index] if top_index is not None else None
    accepted_exact = bool(decision and decision.get("accepted_exact")) if decision is not None else True
    safe_exact_correct = bool(decision and decision.get("accepted_exact") and top_index == expected_index)
    hits = [
        vectorized_hit_to_dict(
            index=int(index),
            product_ids=product_ids,
            catalog=catalog,
            clip_scores=clip_scores,
            metadata_scores=metadata_scores,
            final_scores=final_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            decision=decision if position == 0 else None,
        )
        for position, index in enumerate(top_indices[:10])
    ]
    return {
        "case": case,
        "expected_product_id": expected,
        "rank": rank,
        "top1_product_id": top_product_id,
        "top1_score": round(float(final_scores[top_index]), 6) if top_index is not None else None,
        "top1_clip_score": round(float(clip_scores[top_index]), 6) if top_index is not None else None,
        "top1_same_category": bool(category_matches[top_index]) if top_index is not None else False,
        "top1_decision_label": decision.get("decision_label") if decision else None,
        "accepted_exact": accepted_exact,
        "safe_exact_correct": safe_exact_correct,
        "hits": hits,
    }


def vectorized_hit_to_dict(
    *,
    index: int,
    product_ids: list[str],
    catalog: dict[str, InventoryItemRecord],
    clip_scores: np.ndarray,
    metadata_scores: np.ndarray,
    final_scores: np.ndarray,
    category_matches: np.ndarray,
    color_matches: np.ndarray,
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    product_id = product_ids[index]
    item = catalog[product_id]
    return {
        "product_id": product_id,
        "clip_score": round(float(clip_scores[index]), 6),
        "metadata_score": round(float(metadata_scores[index]), 6),
        "final_score": round(float(final_scores[index]), 6),
        "category_match": bool(category_matches[index]),
        "color_match": bool(color_matches[index]),
        "category": item_category(item),
        "color": item_color(item),
        "name": item.name,
        "decision_label": decision.get("decision_label") if decision else "candidate",
        "accepted_exact": bool(decision.get("accepted_exact")) if decision else False,
        "decision_reason": decision.get("decision_reason") if decision else None,
    }


def build_hit(
    *,
    product_id: str,
    item: InventoryItemRecord,
    clip_score: float,
    case: dict[str, Any],
    method: str,
) -> RankedHit:
    metadata_score, category_match, color_match = metadata_factor_score(case, item)
    final_score = clip_score if method == "clip" else clip_score + metadata_score
    return RankedHit(
        product_id=product_id,
        clip_score=clip_score,
        metadata_score=metadata_score if method != "clip" else 0.0,
        final_score=final_score,
        category_match=category_match,
        color_match=color_match,
        category=item_category(item),
        color=item_color(item),
        name=item.name,
    )


def metadata_factor_score(case: dict[str, Any], item: InventoryItemRecord) -> tuple[float, bool, bool]:
    score = 0.0
    query_category = normalized_case_category(case)
    query_color = normalize_token(case.get("color_hint"))
    category_match = False
    color_match = False

    if query_category:
        item_categories = normalized_item_categories(item)
        category_match = query_category in item_categories
        score += 0.18 if category_match else -0.08

    if query_color:
        item_colors = normalized_item_colors(item)
        color_match = query_color in item_colors or any(query_color in color or color in query_color for color in item_colors)
        score += 0.035 if color_match else -0.012

    if item.stock > 0:
        score += 0.006
    return score, category_match, color_match


def apply_cif_decision_policy(
    ranked_hits: list[RankedHit],
    *,
    case: dict[str, Any],
    catalog: dict[str, InventoryItemRecord],
    use_claim_contracts: bool = True,
    use_risk_policy: bool = True,
) -> list[RankedHit]:
    if not ranked_hits:
        return ranked_hits
    top = ranked_hits[0]
    runner_up = ranked_hits[1] if len(ranked_hits) > 1 else None
    query_category = normalized_case_category(case)
    has_category_evidence = bool(query_category)
    category_safe = (not has_category_evidence) or top.category_match
    product_photo_safe = image_can_confirm_exact(catalog[top.product_id])
    claim_contract_passed = category_safe and product_photo_safe
    final_margin = top.final_score - runner_up.final_score if runner_up else 1.0
    clip_margin = top.clip_score - runner_up.clip_score if runner_up else 1.0
    risk_policy_passed = top.clip_score >= 0.84 and (final_margin >= 0.025 or clip_margin >= 0.045)

    accepted_exact = bool(
        (claim_contract_passed or not use_claim_contracts)
        and
        (risk_policy_passed or not use_risk_policy)
    )
    if accepted_exact:
        label = "confirmed_exact"
        if use_claim_contracts and use_risk_policy:
            reason = "category/product-photo/score/margin evidence passed"
        elif not use_claim_contracts:
            reason = "ablation accepted exact without typed claim-contract evidence"
        else:
            reason = "ablation accepted exact without score/margin risk policy"
    elif use_claim_contracts and not category_safe:
        label = "no_confident_match"
        reason = "category guard blocked exact product claim"
    elif use_claim_contracts and not product_photo_safe:
        label = "no_confident_match"
        reason = "product-photo evidence guard blocked exact product claim"
    elif use_risk_policy and not risk_policy_passed and top.clip_score >= 0.78:
        label = "similar_style"
        reason = "visually plausible but exact margin or score is unsafe"
    elif use_risk_policy and not risk_policy_passed:
        label = "no_confident_match"
        reason = "visual score below commerce-safe threshold"
    elif top.clip_score >= 0.78:
        label = "similar_style"
        reason = "visually plausible, but exact claim was not accepted"
    else:
        label = "no_confident_match"
        reason = "no exact claim accepted"

    decided_top = RankedHit(
        product_id=top.product_id,
        clip_score=top.clip_score,
        metadata_score=top.metadata_score,
        final_score=top.final_score,
        category_match=top.category_match,
        color_match=top.color_match,
        category=top.category,
        color=top.color,
        name=top.name,
        decision_label=label,
        accepted_exact=accepted_exact,
        decision_reason=reason,
    )
    return [decided_top, *ranked_hits[1:]]


def row_from_hits(
    *,
    case: dict[str, Any],
    ranked_hits: list[RankedHit],
    decision_mode: bool,
) -> dict[str, Any]:
    expected = case["expected_primary_product_id"]
    rank = next((i for i, hit in enumerate(ranked_hits, start=1) if hit.product_id == expected), None)
    top = ranked_hits[0] if ranked_hits else None
    accepted_exact = bool(top and top.accepted_exact) if decision_mode else True
    return {
        "case": case,
        "expected_product_id": expected,
        "rank": rank,
        "top1_product_id": top.product_id if top else None,
        "top1_score": round(top.final_score, 6) if top else None,
        "top1_clip_score": round(top.clip_score, 6) if top else None,
        "top1_same_category": bool(top and top.category_match),
        "top1_decision_label": top.decision_label if top else None,
        "accepted_exact": accepted_exact,
        "safe_exact_correct": bool(top and top.accepted_exact and top.product_id == expected),
        "hits": [hit.to_dict() for hit in ranked_hits[:10]],
    }


def compute_metrics(rows: list[dict[str, Any]], *, decision_mode: bool) -> dict[str, Any]:
    total = len(rows)
    valid = [row for row in rows if row.get("rank")]
    ranks = [int(row["rank"]) for row in valid]
    top1_correct = sum(1 for row in rows if row.get("rank") == 1)
    if decision_mode:
        top1_correct = sum(1 for row in rows if row.get("safe_exact_correct"))
    accepted = [row for row in rows if row.get("accepted_exact")]
    accepted_wrong = [row for row in accepted if row.get("top1_product_id") != row.get("expected_product_id")]
    wrong_category = [row for row in rows if row.get("hits") and not row.get("top1_same_category")]
    accepted_wrong_category = [row for row in accepted if row.get("hits") and not row.get("top1_same_category")]
    return {
        "cases": total,
        "encoded_cases": len(valid),
        "top1_accuracy": ratio(top1_correct, total),
        "top3_recall": ratio(sum(1 for rank in ranks if rank <= 3), total),
        "top5_recall": ratio(sum(1 for rank in ranks if rank <= 5), total),
        "top10_recall": ratio(sum(1 for rank in ranks if rank <= 10), total),
        "mean_reciprocal_rank": round(sum(1.0 / rank for rank in ranks) / total, 6) if total else 0.0,
        "mean_rank": round(sum(ranks) / len(ranks), 3) if ranks else None,
        "median_rank": percentile(ranks, 50),
        "p90_rank": percentile(ranks, 90),
        "wrong_category_top1_rate": ratio(len(wrong_category), total),
        "query_encode_failures": total - len(valid),
        "accepted_exact_rate": ratio(len(accepted), total),
        "accepted_exact_precision": ratio(len(accepted) - len(accepted_wrong), len(accepted)),
        "accepted_wrong_exact_rate": ratio(len(accepted_wrong), total),
        "accepted_wrong_category_rate": ratio(len(accepted_wrong_category), len(accepted)),
        "abstention_or_non_exact_rate": ratio(total - len(accepted), total),
    }


def compute_per_category_metrics(rows: list[dict[str, Any]], *, decision_mode: bool) -> dict[str, dict[str, Any]]:
    """Group rows by query category_hint and compute per-category metrics."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        cat = canonicalize(row["case"].get("category_hint") or "") or "unknown"
        by_category.setdefault(cat, []).append(row)
    return {
        cat: compute_metrics(cat_rows, decision_mode=decision_mode)
        for cat, cat_rows in sorted(by_category.items())
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Le Reve Image Search Comparison {payload['selection']['query_images']}",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Created: `{payload['created_at']}`",
        f"- Catalog: `{payload['catalog']}`",
        f"- Eval: `{payload['eval']}`",
        f"- Cache: `{payload['cache_path']}`",
        f"- Products indexed: **{payload['selection']['products']}**",
        f"- Held-out query images: **{payload['selection']['query_images']}**",
        f"- Latency: **{payload['latency_ms']:.0f} ms**",
        "",
        "## Method Notes",
        "",
    ]
    for method, note in payload["method_notes"].items():
        lines.append(f"- `{method}`: {note}")

    lines.extend(
        [
            "",
            "## Main Table",
            "",
            "| Method | Top-1 Exact | Top-3 Recall | Top-5 Recall | Top-10 Recall | Wrong Category Top-1 | Accepted Exact Rate | Accepted Exact Precision |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for method, result in payload["methods"].items():
        m = result["metrics"]
        lines.append(
            f"| `{method}` | {m['top1_accuracy']:.1%} | {m['top3_recall']:.1%} | "
            f"{m['top5_recall']:.1%} | {m['top10_recall']:.1%} | "
            f"{m['wrong_category_top1_rate']:.1%} | {m['accepted_exact_rate']:.1%} | "
            f"{m['accepted_exact_precision']:.1%} |"
        )

    lines.extend(["", "## Safety Metrics", ""])
    lines.append(
        "| Method | Accepted Wrong Exact / All | Accepted Wrong Category / Accepted | Abstain Or Non-Exact | MRR | Median Rank | P90 Rank |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for method, result in payload["methods"].items():
        m = result["metrics"]
        lines.append(
            f"| `{method}` | {m['accepted_wrong_exact_rate']:.1%} | "
            f"{m['accepted_wrong_category_rate']:.1%} | {m['abstention_or_non_exact_rate']:.1%} | "
            f"{m['mean_reciprocal_rank']:.3f} | {m['median_rank']} | {m['p90_rank']} |"
        )

    lines.extend(["", "## Per-Category Breakdown (Full CIF-RAG)", ""])
    cif_method = payload["methods"]["cif_rag_guarded_decision"]
    per_cat = compute_per_category_metrics(cif_method["rows"], decision_mode=True)
    lines.append(
        "| Category | Cases | Top-1 Exact | Top-5 Recall | Accepted Exact Rate | Accepted Exact Precision | Wrong Category Top-1 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for cat, m in sorted(per_cat.items(), key=lambda kv: -kv[1]["cases"]):
        lines.append(
            f"| `{cat}` | {m['cases']} | {m['top1_accuracy']:.1%} | {m['top5_recall']:.1%} | "
            f"{m['accepted_exact_rate']:.1%} | {m['accepted_exact_precision']:.1%} | "
            f"{m['wrong_category_top1_rate']:.1%} |"
        )

    # Worst categories by accepted exact rate (how much coverage is lost)
    sorted_by_coverage = sorted(per_cat.items(), key=lambda kv: kv[1]["accepted_exact_rate"])
    lines.extend(["", "### Worst 5 Categories by Accepted Exact Rate", ""])
    lines.append("| Category | Cases | Accepted Exact Rate | Accepted Exact Precision | Top-5 Recall |")
    lines.append("|---|---:|---:|---:|---:|")
    for cat, m in sorted_by_coverage[:5]:
        lines.append(
            f"| `{cat}` | {m['cases']} | {m['accepted_exact_rate']:.1%} | "
            f"{m['accepted_exact_precision']:.1%} | {m['top5_recall']:.1%} |"
        )

    lines.extend(["", "## Top CIF Blocks", ""])
    cif_rows = payload["methods"]["cif_rag_guarded_decision"]["rows"]
    blocked = [
        row for row in cif_rows
        if row.get("top1_decision_label") in {"no_confident_match", "similar_style"}
        and row.get("top1_product_id") != row.get("expected_product_id")
    ]
    if not blocked:
        lines.append("No unsafe wrong top-1 cases were blocked.")
    else:
        for row in blocked[:20]:
            case = row["case"]
            top = row["hits"][0] if row.get("hits") else {}
            lines.extend(
                [
                    f"### {case['case_id']} rank={row.get('rank')}",
                    "",
                    f"- Expected: `{case['expected_primary_product_id']}` / {case.get('name')}",
                    f"- Top-1 candidate: `{top.get('product_id')}` / {top.get('name')}",
                    f"- Decision: `{top.get('decision_label')}` / {top.get('decision_reason')}",
                    f"- Scores: clip `{top.get('clip_score')}`, final `{top.get('final_score')}`",
                    f"- Query image: `{case.get('image_path')}`",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def image_can_confirm_exact(item: InventoryItemRecord) -> bool:
    image = item.images[0] if item.images else None
    return bool(image and image.kind == "product_photo" and not image.is_reference)


def cache_or_encode(image_path: str, cache: dict[str, Any], *, allow_encode: bool) -> list[float] | None:
    path = Path(image_path)
    stat = path.stat()
    key = f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{EMBEDDING_VERSION}"
    cached = cache.get(key)
    if cached:
        return cached
    if not allow_encode:
        return None
    return cached_encode(image_path, cache)


def normalized_case_category(case: dict[str, Any]) -> str:
    raw = case.get("category_hint") or case.get("expected_category") or ""
    return canonicalize(raw)


def normalized_item_categories(item: InventoryItemRecord) -> set[str]:
    attrs = item.attributes or {}
    values = [
        item.category,
        attrs.get("category_key"),
        attrs.get("garment_type"),
    ]
    raw_tokens = {token for value in values for token in split_normalized_values(value)} - UNKNOWN_VALUES
    # Return raw tokens; callers that need canonical form apply canonicalize().
    return raw_tokens


def normalized_item_colors(item: InventoryItemRecord) -> set[str]:
    attrs = item.attributes or {}
    values = [
        attrs.get("color"),
        attrs.get("color_family"),
        *item.tags,
    ]
    return {token for value in values for token in split_normalized_values(value)} - UNKNOWN_VALUES


def item_category(item: InventoryItemRecord) -> str:
    return item.category or item.attributes.get("category_key") or ""


def item_color(item: InventoryItemRecord) -> str:
    return item.attributes.get("color") or item.attributes.get("color_family") or ""


def split_normalized_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    else:
        values = str(value).replace("|", ",").replace("/", ",").split(",")
    return [token for entry in values if (token := normalize_token(entry))]


def normalize_token(value: Any) -> str:
    text = str(value or "").casefold().replace("&", "and")
    chars = []
    for char in text:
        chars.append(char if char.isalnum() else " ")
    return "_".join("".join(chars).split())


if __name__ == "__main__":
    raise SystemExit(main())
