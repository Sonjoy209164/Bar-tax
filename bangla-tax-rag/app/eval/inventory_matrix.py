from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.core.schemas import (
    InventoryAskRequest,
    InventoryAskResponse,
    InventoryBusinessSignalRecord,
    InventoryItemRecord,
    InventorySearchFilters,
    InventorySearchHit,
)
from app.retrieval import (
    EmbedderConfig,
    EmbeddingBatch,
    EmbeddingProvider,
    LocalVectorStore,
    TextEmbedder,
    VectorStoreConfig,
    VectorStoreProvider,
)
from app.services.inventory_service import InventoryService, InventoryServiceConfig


class InventoryEvalKeywordEmbedder(TextEmbedder):
    VOCAB = [
        "16",
        "32",
        "about",
        "audio",
        "available",
        "bag",
        "battery",
        "budget",
        "business",
        "computing",
        "detail",
        "elite",
        "essential",
        "gb",
        "headphones",
        "in",
        "laptop",
        "monitor",
        "noise",
        "office",
        "pair",
        "premium",
        "price",
        "pro",
        "ram",
        "recommend",
        "speaker",
        "stock",
        "tell",
        "under",
        "wireless",
    ]

    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.casefold()
            vectors.append([float(lowered.count(token)) for token in self.VOCAB])
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self.config.model_name,
            provider=self.provider,
            dimensions=len(self.VOCAB),
        )


@dataclass(frozen=True)
class InventoryEvalCase:
    case_id: str
    family: str
    description: str
    tags: tuple[str, ...]
    items: tuple[InventoryItemRecord, ...]
    request: InventoryAskRequest
    execution_mode: str = "ask"
    direct_hits: tuple[InventorySearchHit, ...] = ()
    business_signals: tuple[InventoryBusinessSignalRecord, ...] = ()
    expected_abstained: bool = False
    expected_primary_product_id: str | None = None
    expected_recommended_product_ids: tuple[str, ...] = ()
    required_answer_substrings: tuple[str, ...] = ()
    forbidden_answer_substrings: tuple[str, ...] = ()
    required_hard_issue_substrings: tuple[str, ...] = ()


def run_inventory_eval_matrix(*, case_ids: list[str] | None = None) -> dict[str, object]:
    selected_cases = _select_cases(case_ids)
    case_results: list[dict[str, object]] = []
    answer_engine_counts: Counter[str] = Counter()
    family_rollup: dict[str, list[dict[str, object]]] = defaultdict(list)
    covered_failure_modes: Counter[str] = Counter()

    with TemporaryDirectory(prefix="inventory_eval_matrix_") as temp_root:
        root = Path(temp_root)
        for case in selected_cases:
            covered_failure_modes.update(case.tags)
            service = _build_inventory_eval_service(root / case.case_id)
            service.upsert_items([item.model_copy(deep=True) for item in case.items])
            if case.business_signals:
                service.upsert_business_signals([signal.model_copy(deep=True) for signal in case.business_signals])

            started_at = perf_counter()
            response = _run_case(service=service, case=case)
            latency_ms = round((perf_counter() - started_at) * 1000, 2)

            result = _evaluate_case(case=case, response=response, latency_ms=latency_ms)
            case_results.append(result)
            family_rollup[case.family].append(result)
            answer_engine_counts.update([response.answer_engine])

    total_cases = len(case_results)
    passed_cases = sum(1 for result in case_results if result["passed"])
    failed_cases = total_cases - passed_cases
    retrieval_stage_failures = sum(1 for result in case_results if result["failure_stage"] == "retrieval")
    answer_stage_failures = sum(1 for result in case_results if result["failure_stage"] == "answer")
    false_positive_abstains = sum(
        1 for result in case_results if not result["expected"]["expected_abstained"] and result["response"]["abstained"]
    )
    false_negative_abstains = sum(
        1 for result in case_results if result["expected"]["expected_abstained"] and not result["response"]["abstained"]
    )
    family_breakdown = {
        family: _family_summary(results)
        for family, results in sorted(family_rollup.items())
    }
    observed_failure_modes: Counter[str] = Counter()
    for result in case_results:
        if not result["passed"]:
            observed_failure_modes.update(result["tags"])

    average_latency_ms = round(
        sum(float(result["latency_ms"]) for result in case_results) / total_cases,
        2,
    ) if total_cases else 0.0

    return {
        "suite_name": "inventory_phase8_eval_matrix",
        "available_case_ids": [case.case_id for case in inventory_eval_cases()],
        "selected_case_ids": [case.case_id for case in selected_cases],
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "accuracy": round(passed_cases / total_cases, 3) if total_cases else 0.0,
        "family_breakdown": family_breakdown,
        "covered_failure_modes": dict(sorted(covered_failure_modes.items())),
        "observed_failure_modes": dict(sorted(observed_failure_modes.items())),
        "retrieval_stage_failures": retrieval_stage_failures,
        "answer_stage_failures": answer_stage_failures,
        "abstain_metrics": {
            "expected_abstain_cases": sum(1 for result in case_results if result["expected"]["expected_abstained"]),
            "expected_non_abstain_cases": sum(1 for result in case_results if not result["expected"]["expected_abstained"]),
            "false_positive_abstains": false_positive_abstains,
            "false_negative_abstains": false_negative_abstains,
        },
        "answer_engine_breakdown": dict(sorted(answer_engine_counts.items())),
        "answer_engine_rates": {
            engine: round(count / total_cases, 3) if total_cases else 0.0
            for engine, count in sorted(answer_engine_counts.items())
        },
        "average_latency_ms": average_latency_ms,
        "case_results": case_results,
    }


def inventory_eval_cases() -> tuple[InventoryEvalCase, ...]:
    budget = _item(
        product_id="budget",
        sku="CMP-LAP-001",
        name="Nimbus 14 Essential",
        category="Computing",
        brand="Nimbus",
        short_description="Lower-cost business laptop for general office work.",
        price=899.0,
        stock=16,
        tags=["computing", "laptop"],
        attributes={"ram_gb": "16", "storage_gb": "512"},
    )
    premium = _item(
        product_id="premium",
        sku="CMP-LAP-002",
        name="Nimbus 14 Elite",
        category="Computing",
        brand="Nimbus",
        short_description="Premium laptop with OLED display and higher-end performance.",
        price=1799.0,
        stock=11,
        tags=["computing", "laptop", "premium"],
        attributes={"ram_gb": "32", "storage_gb": "1024"},
    )
    step_up = _item(
        product_id="step-up",
        sku="CMP-LAP-010",
        name="Nimbus 14 Pro",
        category="Computing",
        brand="Nimbus",
        short_description="Stronger laptop with faster processor and sharper display.",
        price=1149.0,
        stock=14,
        tags=["computing", "laptop", "premium"],
        attributes={"ram_gb": "32", "storage_gb": "1024"},
    )
    monitor = _item(
        product_id="prod-monitor",
        sku="AUD-MON-005",
        name="Auralite Pro Monitor Pair",
        category="Audio",
        brand="Auralite",
        short_description="Reference monitor speakers for editing suites and premium content desks.",
        price=399.0,
        stock=7,
        tags=["audio", "monitor", "speaker"],
    )
    headphone = _item(
        product_id="prod-headphone",
        sku="AUD-HP-001",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        brand="Auralite",
        short_description="Wireless noise-cancelling headphones under 300 for focused office work.",
        price=249.0,
        stock=18,
        tags=["audio", "headphones", "wireless"],
        attributes={"battery_hours": "35"},
    )

    return (
        InventoryEvalCase(
            case_id="valid-recommendation",
            family="recommendation",
            description="A strong premium recommendation should stay grounded and avoid abstaining.",
            tags=("abstain_false_positive",),
            items=(budget, premium),
            request=InventoryAskRequest(
                question="Recommend a premium laptop for this customer",
                assistant_mode="sales",
                reply_style="detailed",
                top_k=5,
            ),
            expected_abstained=False,
            expected_primary_product_id="premium",
            expected_recommended_product_ids=("premium",),
            required_answer_substrings=("Nimbus 14 Elite",),
        ),
        InventoryEvalCase(
            case_id="exact-product-detail",
            family="product_detail",
            description="Exact product detail should not false-abstain and should resolve the right product record.",
            tags=("missed_exact_match", "abstain_false_positive"),
            items=(monitor, headphone),
            request=InventoryAskRequest(
                question="tell me about Auralite Pro Monitor Pair",
                assistant_mode="support",
                reply_style="detailed",
                top_k=5,
            ),
            expected_abstained=False,
            expected_primary_product_id="prod-monitor",
            required_answer_substrings=("Auralite Pro Monitor Pair is",),
        ),
        InventoryEvalCase(
            case_id="budget-ceiling-violation",
            family="recommendation",
            description="A recommendation that breaks the budget ceiling should abstain.",
            tags=("false_price_claim", "weak_abstain_behavior"),
            items=(step_up,),
            request=InventoryAskRequest(
                question="Recommend a laptop under $1000",
                assistant_mode="sales",
                reply_style="detailed",
                top_k=5,
            ),
            execution_mode="build_answer",
            direct_hits=(
                _hit_from_item(
                    step_up,
                    score=0.74,
                    evidence_scores={
                        "final_score": 0.74,
                        "product_type_match": 1.0,
                        "premium_fit": 0.92,
                        "stock_fit": 1.0,
                    },
                ),
            ),
            expected_abstained=True,
            required_hard_issue_substrings=("budget ceiling",),
        ),
        InventoryEvalCase(
            case_id="alternative-violation",
            family="recommendation",
            description="A step-up alternative that breaks hard budget constraints should force abstention.",
            tags=("alternative_violation", "weak_abstain_behavior"),
            items=(budget, step_up),
            request=InventoryAskRequest(
                question="Recommend a laptop under $1000, but show the next stronger option too",
                assistant_mode="sales",
                reply_style="detailed",
                top_k=5,
            ),
            execution_mode="build_answer",
            direct_hits=(
                _hit_from_item(
                    budget,
                    score=0.88,
                    evidence_scores={
                        "final_score": 0.88,
                        "product_type_match": 1.0,
                        "price_fit": 0.95,
                        "budget_fit": 1.0,
                        "stock_fit": 1.0,
                    },
                ),
                _hit_from_item(
                    step_up,
                    score=0.74,
                    evidence_scores={
                        "final_score": 0.74,
                        "product_type_match": 1.0,
                        "premium_fit": 0.92,
                        "structured_spec_match": 0.7,
                        "stock_fit": 1.0,
                    },
                ),
            ),
            expected_abstained=True,
            required_hard_issue_substrings=("budget ceiling",),
        ),
        InventoryEvalCase(
            case_id="spec-mismatch",
            family="recommendation",
            description="A selected product that misses the requested structured spec should abstain.",
            tags=("false_spec_claim", "weak_abstain_behavior"),
            items=(budget,),
            request=InventoryAskRequest(
                question="Recommend a laptop with 32GB RAM",
                assistant_mode="sales",
                reply_style="detailed",
                top_k=5,
            ),
            expected_abstained=True,
            required_hard_issue_substrings=("ram_gb gte 32.0",),
        ),
        InventoryEvalCase(
            case_id="conflicting-stock-signals",
            family="availability",
            description="Conflicting catalog and business stock signals should trigger abstention.",
            tags=("false_in_stock_claim", "weak_abstain_behavior"),
            items=(budget.model_copy(update={"stock": 4}),),
            business_signals=(
                InventoryBusinessSignalRecord(
                    product_id="budget",
                    inventory_on_hand=0,
                    inventory_snapshot_at="2026-04-20T10:00:00Z",
                ),
            ),
            request=InventoryAskRequest(
                question="Show me an in stock laptop",
                assistant_mode="support",
                reply_style="detailed",
                top_k=5,
            ),
            expected_abstained=True,
            required_hard_issue_substrings=("conflicting stock evidence",),
        ),
        InventoryEvalCase(
            case_id="abstain-false-positive-guardrail",
            family="recommendation",
            description="A valid budget-fit recommendation should not abstain just because another candidate is over budget.",
            tags=("abstain_false_positive",),
            items=(budget, premium),
            request=InventoryAskRequest(
                question="Recommend a laptop under $1000",
                assistant_mode="sales",
                reply_style="detailed",
                top_k=5,
            ),
            expected_abstained=False,
            expected_primary_product_id="budget",
            expected_recommended_product_ids=("budget",),
            required_answer_substrings=("Nimbus 14 Essential",),
        ),
    )


def _select_cases(case_ids: list[str] | None) -> list[InventoryEvalCase]:
    all_cases = inventory_eval_cases()
    if not case_ids:
        return list(all_cases)
    case_by_id = {case.case_id.casefold(): case for case in all_cases}
    selected: list[InventoryEvalCase] = []
    missing: list[str] = []
    for case_id in case_ids:
        match = case_by_id.get(case_id.casefold())
        if match is None:
            missing.append(case_id)
            continue
        selected.append(match)
    if missing:
        available = ", ".join(case.case_id for case in all_cases)
        raise ValueError(f"Unknown inventory eval case ids: {', '.join(missing)}. Available cases: {available}")
    return selected


def _build_inventory_eval_service(root: Path) -> InventoryService:
    root.mkdir(parents=True, exist_ok=True)
    embedder = InventoryEvalKeywordEmbedder(
        EmbedderConfig(
            provider=EmbeddingProvider.DETERMINISTIC,
            model_name="inventory-eval-keyword",
            dimensions=len(InventoryEvalKeywordEmbedder.VOCAB),
            normalize=False,
        )
    )
    vector_store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            local_store_path=str(root / "inventory_vectors.jsonl"),
            namespace="inventory-eval",
            dimensions=len(InventoryEvalKeywordEmbedder.VOCAB),
        )
    )
    return InventoryService(
        embedder=embedder,
        vector_store=vector_store,
        config=InventoryServiceConfig(
            catalog_path=str(root / "inventory_catalog.jsonl"),
            namespace="inventory-eval",
            low_stock_threshold=10,
            agentic_trace_dir=str(root / "inventory_agentic_traces"),
            business_signal_path=str(root / "inventory_business_signals.jsonl"),
            inventory_storage_backend="jsonl",
            inventory_sqlite_path=str(root / "inventory_mirror.sqlite3"),
        ),
    )


def _run_case(
    *,
    service: InventoryService,
    case: InventoryEvalCase,
) -> InventoryAskResponse:
    if case.execution_mode == "ask":
        return service.ask(case.request.model_copy(deep=True))
    if case.execution_mode != "build_answer":
        raise ValueError(f"Unsupported inventory eval execution mode: {case.execution_mode}")

    hits = [hit.model_copy(deep=True) for hit in case.direct_hits]
    reply = service._build_answer(
        question=case.request.question,
        hits=hits,
        filters=case.request.filters.model_copy(deep=True),
        low_stock_threshold=case.request.low_stock_threshold,
        assistant_mode=case.request.assistant_mode,
        reply_style=case.request.reply_style,
    )
    confidence_score = service._estimate_confidence(hits)
    reply, answer_engine, abstained, abstention_reason, _fallback_reason = service._finalize_inventory_reply(
        question=case.request.question,
        assistant_mode=case.request.assistant_mode,
        reply_style=case.request.reply_style,
        requested_answer_engine=case.request.answer_engine,
        confidence_score=confidence_score,
        hits=hits,
        base_reply=reply,
        conversation_history=[],
        conversation_summary=None,
        abstention_reason=None,
        execution_path=f"inventory_eval_{case.case_id}",
    )
    return InventoryAskResponse(
        status="success",
        question=case.request.question,
        answer=reply.answer,
        assistant_mode=case.request.assistant_mode,
        reply_style=case.request.reply_style,
        answer_engine=answer_engine,
        confidence_score=confidence_score,
        trace_id=f"inventory-eval-{case.case_id}",
        abstained=abstained,
        abstention_reason=abstention_reason,
        total_hits=len(hits),
        applied_filters=case.request.filters.model_copy(deep=True),
        hits=hits,
        recommended_product_ids=reply.recommended_product_ids,
        cross_sell_product_ids=reply.cross_sell_product_ids,
        follow_up_question=reply.follow_up_question,
        answer_plan=reply.answer_plan,
        verification=reply.verification,
    )


def _evaluate_case(
    *,
    case: InventoryEvalCase,
    response,
    latency_ms: float,
) -> dict[str, object]:
    failures: list[str] = []
    answer_text = response.answer.casefold()
    hard_issues_text = " ".join(response.verification.hard_constraint_issues).casefold()

    if response.abstained is not case.expected_abstained:
        failures.append(
            f"Expected abstained={case.expected_abstained} but got abstained={response.abstained}."
        )
    if response.answer_plan.abstain is not case.expected_abstained:
        failures.append(
            f"Expected answer_plan.abstain={case.expected_abstained} but got {response.answer_plan.abstain}."
        )
    if case.expected_primary_product_id != response.answer_plan.primary_product_id:
        failures.append(
            f"Expected primary product {case.expected_primary_product_id} but got {response.answer_plan.primary_product_id}."
        )
    if case.expected_recommended_product_ids and tuple(response.recommended_product_ids) != case.expected_recommended_product_ids:
        failures.append(
            "Expected recommended product IDs "
            f"{list(case.expected_recommended_product_ids)} but got {response.recommended_product_ids}."
        )
    for snippet in case.required_answer_substrings:
        if snippet.casefold() not in answer_text:
            failures.append(f"Answer is missing required text: {snippet}.")
    for snippet in case.forbidden_answer_substrings:
        if snippet.casefold() in answer_text:
            failures.append(f"Answer contains forbidden text: {snippet}.")
    for snippet in case.required_hard_issue_substrings:
        if snippet.casefold() not in hard_issues_text:
            failures.append(f"Hard constraint issues are missing required text: {snippet}.")

    failure_stage = _infer_failure_stage(case=case, response=response, failures=failures)
    return {
        "case_id": case.case_id,
        "family": case.family,
        "description": case.description,
        "tags": list(case.tags),
        "passed": not failures,
        "failures": failures,
        "failure_stage": failure_stage,
        "latency_ms": latency_ms,
        "expected": {
            "expected_abstained": case.expected_abstained,
            "expected_primary_product_id": case.expected_primary_product_id,
            "expected_recommended_product_ids": list(case.expected_recommended_product_ids),
            "required_hard_issue_substrings": list(case.required_hard_issue_substrings),
        },
        "response": {
            "question": response.question,
            "abstained": response.abstained,
            "abstention_reason": response.abstention_reason,
            "answer_engine": response.answer_engine,
            "primary_product_id": response.answer_plan.primary_product_id,
            "recommended_product_ids": list(response.recommended_product_ids),
            "total_hits": response.total_hits,
            "answer": response.answer,
            "verification_requires_abstention": response.verification.requires_abstention,
            "hard_constraint_issues": list(response.verification.hard_constraint_issues),
            "verification_issues": list(response.verification.issues),
        },
    }


def _infer_failure_stage(*, case: InventoryEvalCase, response, failures: list[str]) -> str | None:
    if not failures:
        return None
    returned_product_ids = {hit.product_id for hit in response.hits}
    if case.expected_primary_product_id and case.expected_primary_product_id not in returned_product_ids:
        return "retrieval"
    if not response.hits and not case.expected_abstained:
        return "retrieval"
    return "answer"


def _family_summary(results: list[dict[str, object]]) -> dict[str, object]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    return {
        "total_cases": total,
        "passed_cases": passed,
        "accuracy": round(passed / total, 3) if total else 0.0,
        "average_latency_ms": round(
            sum(float(result["latency_ms"]) for result in results) / total,
            2,
        ) if total else 0.0,
    }


def _item(
    *,
    product_id: str,
    sku: str,
    name: str,
    category: str,
    brand: str,
    short_description: str,
    price: float,
    stock: int,
    tags: list[str],
    attributes: dict[str, str] | None = None,
) -> InventoryItemRecord:
    return InventoryItemRecord(
        product_id=product_id,
        sku=sku,
        name=name,
        category=category,
        brand=brand,
        short_description=short_description,
        price=price,
        currency="USD",
        stock=stock,
        status="Active",
        tags=tags,
        attributes=attributes or {},
        include_in_rag=True,
    )


def _hit_from_item(
    item: InventoryItemRecord,
    *,
    score: float,
    evidence_scores: dict[str, object] | None = None,
) -> InventorySearchHit:
    return InventorySearchHit(
        product_id=item.product_id,
        sku=item.sku,
        name=item.name,
        category=item.category,
        brand=item.brand,
        status=item.status,
        price=item.price,
        currency=item.currency,
        stock=item.stock,
        tags=list(item.tags),
        snippet=item.short_description,
        attributes=dict(item.attributes),
        metadata=dict(item.metadata),
        evidence_scores=dict(evidence_scores or {}),
        score=score,
    )
