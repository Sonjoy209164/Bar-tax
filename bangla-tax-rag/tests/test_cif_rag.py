from __future__ import annotations

import json
from pathlib import Path

from app.core.schemas import InventoryItemRecord
from app.inventory.cif_engine import CifRagEngine
from app.inventory.commerce_claims import CommerceClaimCompiler
from app.inventory.counterfactual_planner import CounterfactualQueryPlanner
from app.inventory.image_matcher import ImageMatchResult, ImageSearchDecision, finalize_image_search
from app.inventory.product_factor_graph import ProductFactorGraph
from app.inventory.risk_decision_automaton import RiskCostDecisionAutomaton


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "inventory" / "catalog.jsonl"


def _catalog() -> dict[str, InventoryItemRecord]:
    return {
        item.product_id: item
        for item in (
            InventoryItemRecord.model_validate(json.loads(line))
            for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _raw_hit(catalog: dict[str, InventoryItemRecord], product_id: str, score: float = 0.99) -> ImageMatchResult:
    item = catalog[product_id]
    return ImageMatchResult(
        product_id=item.product_id,
        name=item.name,
        score=score,
        match_type="visual_similar",
        reasons=("test visual hit",),
        price=item.price,
        currency=item.currency,
        stock=item.stock,
    )


def test_product_factor_graph_groups_same_design_and_stock():
    catalog = _catalog()
    graph = ProductFactorGraph.from_catalog(catalog)

    siblings = graph.same_design_siblings("shirt-ribbed-polo-black")
    sibling_ids = {node.product_id for node in siblings}
    assert {
        "shirt-ribbed-polo-black",
        "shirt-ribbed-polo-grey",
        "shirt-ribbed-polo-olive",
        "shirt-ribbed-polo-white",
    } <= sibling_ids
    assert set(graph.available_colors("shirt-ribbed-polo-black")) >= {"black", "grey", "olive", "white"}
    assert graph.can_claim_exact("shirt-ribbed-polo-black")
    assert not graph.can_claim_exact("saree-jmd-lotus-red")

    m_black = graph.size_availability("shirt-ribbed-polo-black", "M")
    m_white = graph.size_availability("shirt-ribbed-polo-white", "M")
    assert m_black and m_black.known and m_black.available and m_black.stock == 2
    assert m_white and m_white.known and not m_white.available and m_white.stock == 0


def test_counterfactual_planner_compiles_same_design_color_query():
    plan = CounterfactualQueryPlanner().plan(
        query_text="ei same design ta blue color e ache?",
        has_image=True,
    )
    operations = [(op.op, op.target, op.value) for op in plan.operations]
    assert plan.query_family == "same_design_color_intervention"
    assert ("HOLD", "design", None) in operations
    assert ("INTERVENE", "color", "blue") in operations
    assert ("VERIFY", "stock_status", None) in operations


def test_cif_engine_reports_claims_and_low_risk_for_confirmed_product():
    catalog = _catalog()
    decision = finalize_image_search(
        catalog=catalog,
        results=[_raw_hit(catalog, "shirt-ribbed-polo-black")],
        query_text="eta ache?",
        top_k=6,
    )
    result = CifRagEngine(catalog).analyze(
        query_text="eta ache?",
        has_image=True,
        decision=decision,
    )
    trace = result.to_trace()
    assert trace["architecture"] == "CIF-RAG"
    assert trace["plan"]["query_family"] == "exact_product_check"
    assert trace["risk_decision"]["safe_to_answer"] is True
    assert trace["claims"]["claim_evidence_coverage"] == 1.0


def test_claim_contract_supports_requested_color_absence():
    catalog = _catalog()
    graph = ProductFactorGraph.from_catalog(catalog)
    decision = finalize_image_search(
        catalog=catalog,
        results=[_raw_hit(catalog, "shirt-ribbed-polo-white")],
        query_text="blue color ache?",
        top_k=6,
    )
    plan = CounterfactualQueryPlanner().plan(query_text="blue color ache?", has_image=True)
    claims = CommerceClaimCompiler(graph).compile(plan=plan, decision=decision)
    absence_claims = [claim for claim in claims.claims if claim.claim_type == "absence"]
    assert absence_claims
    assert absence_claims[0].supported
    assert "blue" not in decision.available_colors


def test_risk_automaton_flags_unsupported_reference_exact_claim():
    catalog = _catalog()
    graph = ProductFactorGraph.from_catalog(catalog)
    plan = CounterfactualQueryPlanner().plan(query_text="eta exact ache?", has_image=True)
    bad_decision = ImageSearchDecision(
        answer="Bad exact answer",
        hits=[_raw_hit(catalog, "saree-jmd-lotus-red")],
        decision_label="confirmed_exact",
        primary_product_id="saree-jmd-lotus-red",
        same_design_variant_ids=(),
        similar_product_ids=(),
        requested_color=None,
        available_colors=(),
        score_breakdown={},
    )
    claims = CommerceClaimCompiler(graph).compile(plan=plan, decision=bad_decision)
    risk = RiskCostDecisionAutomaton().evaluate(
        plan=plan,
        decision=bad_decision,
        claim_contract=claims,
        graph=graph,
    )
    assert risk.risk_level in {"high", "critical"}
    assert not risk.safe_to_answer
    assert "exact_product" in risk.unsupported_high_risk_claims
