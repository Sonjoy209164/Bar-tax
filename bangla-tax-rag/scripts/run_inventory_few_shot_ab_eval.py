from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import (  # noqa: E402
    InventoryAgenticRequest,
    InventoryAskRequest,
    InventoryBusinessSignalRecord,
    InventoryItemRecord,
    InventoryRouteRequest,
)
from app.core.settings import get_settings  # noqa: E402
from app.eval.inventory_matrix import run_inventory_eval_matrix  # noqa: E402
from app.retrieval import (  # noqa: E402
    LocalVectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    build_embedder,
)
from app.services.inventory_service import InventoryService, InventoryServiceConfig  # noqa: E402

DEFAULT_DATA_DOMAINS = [
    "catalog",
    "sales",
    "orders",
    "inventory_snapshots",
    "suppliers",
    "margins",
    "returns",
    "customers",
]

FEW_SHOT_LEAK_MARKERS = [
    "EchoWave Studio Earbuds",
    "32GB RAM requirement first",
    "over-ear comfort or smaller travel-friendly size",
]


def load_sample_fixture() -> dict[str, Any]:
    sample_path = ROOT / "frontend" / "data" / "products.json"
    return json.loads(sample_path.read_text(encoding="utf-8"))


def normalize_search_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def build_request_context(question: str, items: list[InventoryItemRecord]) -> dict[str, Any]:
    normalized_question = normalize_search_text(question)
    focused_product_ids: list[str] = []
    for item in items:
        candidates = [
            normalize_search_text(item.product_id),
            normalize_search_text(item.sku),
            normalize_search_text(item.name),
            normalize_search_text(item.brand),
        ]
        if any(candidate and candidate in normalized_question for candidate in candidates):
            focused_product_ids.append(item.product_id)
    focused_product_ids = dedupe(focused_product_ids)[:12]
    filters = {"product_ids": focused_product_ids} if focused_product_ids else None
    return {"focused_product_ids": focused_product_ids, "filters": filters}


def build_full_system_service(
    *,
    root: Path,
    few_shot_enabled: bool,
) -> InventoryService:
    settings = get_settings()
    embedder = build_embedder()
    probe_batch = embedder.embed_texts(["inventory few shot ab eval"])
    vector_store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            metric=settings.vector_metric,
            namespace="inventory-few-shot-ab",
            dimensions=probe_batch.dimensions,
            local_store_path=str(root / "inventory_vectors.jsonl"),
        )
    )
    return InventoryService(
        embedder=embedder,
        vector_store=vector_store,
        config=InventoryServiceConfig(
            catalog_path=str(root / "inventory_catalog.jsonl"),
            namespace="inventory-few-shot-ab",
            default_top_k=6,
            agentic_trace_dir=str(root / "traces" / "agentic"),
            chat_trace_dir=str(root / "traces" / "chat"),
            business_signal_path=str(root / "inventory_business_signals.jsonl"),
            inventory_storage_backend="jsonl",
            inventory_sqlite_path=str(root / "inventory_mirror.sqlite3"),
            natural_answers_enabled=True,
            natural_answer_model_name=settings.inventory_natural_answer_model_name,
            natural_answer_temperature=settings.inventory_natural_answer_temperature,
            natural_answer_max_tokens=settings.inventory_natural_answer_max_tokens,
            natural_answer_min_confidence=settings.inventory_natural_answer_min_confidence,
            natural_answer_timeout_seconds=settings.inventory_natural_answer_timeout_seconds,
            natural_answer_few_shot_enabled=few_shot_enabled,
            natural_answer_few_shot_max_examples=settings.inventory_natural_answer_few_shot_max_examples,
            conversation_history_limit=settings.inventory_conversation_history_limit,
        ),
    )


def execute_question_pack(
    *,
    few_shot_enabled: bool,
) -> dict[str, Any]:
    sample = load_sample_fixture()
    items = [InventoryItemRecord.model_validate(item) for item in sample.get("items", [])]
    business_signals = [
        InventoryBusinessSignalRecord.model_validate(signal)
        for signal in sample.get("business_signals", [])
    ]
    question_cases = list(sample.get("test_questions", []))
    run_label = "few_shot_on" if few_shot_enabled else "few_shot_off"

    with TemporaryDirectory(prefix=f"inventory_full_system_{run_label}_") as temp_root:
        root = Path(temp_root)
        service = build_full_system_service(root=root, few_shot_enabled=few_shot_enabled)
        service.upsert_items([item.model_copy(deep=True) for item in items])
        if business_signals:
            service.upsert_business_signals([signal.model_copy(deep=True) for signal in business_signals])

        case_results: list[dict[str, Any]] = []
        answer_engine_counts: Counter[str] = Counter()
        route_counts: Counter[str] = Counter()
        format_flag_counts: Counter[str] = Counter()
        fallback_count = 0
        fallback_attempts = 0
        false_positive_abstains = 0
        false_negative_abstains = 0

        for index, case in enumerate(question_cases, start=1):
            question = str(case.get("question", ""))
            assistant_mode = str(case.get("assistant_mode", "support"))
            reply_style = str(case.get("reply_style", "short"))
            request_context = build_request_context(question, items)

            route_request_payload: dict[str, Any] = {
                "question": question,
                "assistant_mode": assistant_mode,
                "reply_style": reply_style,
                "audience": "manager",
                "prefer_fast_response": True,
                "allow_agentic": True,
                "available_data_domains": list(DEFAULT_DATA_DOMAINS),
            }
            if request_context["filters"]:
                route_request_payload["filters"] = request_context["filters"]
            route_request = InventoryRouteRequest(**route_request_payload)
            route_response = service.route(route_request)
            resolved_endpoint = "agentic" if route_response.recommended_path == "agentic" else "ask"
            route_counts.update([resolved_endpoint])

            if resolved_endpoint == "agentic":
                response = service.agentic_ask(
                    InventoryAgenticRequest(
                        question=question,
                        assistant_mode=assistant_mode,
                        reply_style=reply_style,
                        top_k=6,
                        answer_engine="auto",
                        conversation_history=[],
                        focused_product_ids=request_context["focused_product_ids"],
                        active_filters=None,
                        last_answer_plan=None,
                        max_reasoning_steps=4,
                        audience="manager",
                        available_data_domains=list(DEFAULT_DATA_DOMAINS),
                    )
                )
            else:
                ask_payload: dict[str, Any] = {
                    "question": question,
                    "assistant_mode": assistant_mode,
                    "reply_style": reply_style,
                    "top_k": 6,
                    "answer_engine": "auto",
                    "conversation_history": [],
                    "focused_product_ids": request_context["focused_product_ids"],
                    "active_filters": None,
                    "last_answer_plan": None,
                }
                if request_context["filters"]:
                    ask_payload["filters"] = request_context["filters"]
                response = service.ask(
                    InventoryAskRequest(**ask_payload)
                )

            chat_trace = service.get_chat_trace(response.trace_id)
            answer_engine_counts.update([response.answer_engine])

            surfaced_product_ids = dedupe(
                [
                    *response.recommended_product_ids,
                    *response.cross_sell_product_ids,
                    *(hit.product_id for hit in response.hits),
                ]
            )
            expected_product_ids = [str(value) for value in case.get("expected_product_ids", [])]
            forbidden_product_ids = [str(value) for value in case.get("forbidden_product_ids", [])]
            must_include_text = [str(value) for value in case.get("must_include_text", [])]
            missing_expected = [product_id for product_id in expected_product_ids if product_id not in surfaced_product_ids]
            forbidden_surfaced = [product_id for product_id in forbidden_product_ids if product_id in surfaced_product_ids]
            missing_required_text = [
                snippet for snippet in must_include_text if snippet.casefold() not in response.answer.casefold()
            ]
            expected_no_hits = bool(case.get("expected_no_hits"))
            expected_no_hits_check = (response.total_hits == 0 and response.abstained) if expected_no_hits else True
            route_match = resolved_endpoint == str(case.get("endpoint", "ask"))
            passed = (
                route_match
                and expected_no_hits_check
                and not missing_expected
                and not forbidden_surfaced
                and not missing_required_text
            )

            if expected_no_hits and not response.abstained:
                false_negative_abstains += 1
            if not expected_no_hits and response.abstained:
                false_positive_abstains += 1

            fallback_reason = chat_trace.fallback_reason if chat_trace is not None else None
            natural_fallback = bool(
                fallback_reason and "deterministic fallback was used" in fallback_reason.casefold()
            )
            attempted_natural = response.answer_engine == "natural" or natural_fallback
            if attempted_natural:
                fallback_attempts += 1
            if natural_fallback:
                fallback_count += 1

            format_flags: list[str] = []
            if response.answer.strip().startswith("{") or "```" in response.answer:
                format_flags.append("json_or_markdown_leak")
            if response.answer.count("?") > 1:
                format_flags.append("multiple_follow_up_questions")
            if any(marker.casefold() in response.answer.casefold() for marker in FEW_SHOT_LEAK_MARKERS):
                format_flags.append("few_shot_example_leak")
            if response.verification.final_answer_issues:
                format_flags.append("final_answer_verification_issue")
            if response.verification.issues:
                format_flags.append("answer_plan_verification_issue")
            format_flag_counts.update(format_flags)

            case_results.append(
                {
                    "index": index,
                    "label": case.get("label"),
                    "question": question,
                    "expected_endpoint": case.get("endpoint", "ask"),
                    "routed_endpoint": resolved_endpoint,
                    "route_match": route_match,
                    "route_family": route_response.signals.question_family,
                    "answer_engine": response.answer_engine,
                    "execution_path": getattr(response, "execution_path", "inventory_ask"),
                    "abstained": response.abstained,
                    "abstention_reason": response.abstention_reason,
                    "total_hits": response.total_hits,
                    "surface_product_ids": surfaced_product_ids,
                    "recommended_product_ids": list(response.recommended_product_ids),
                    "cross_sell_product_ids": list(response.cross_sell_product_ids),
                    "missing_expected_product_ids": missing_expected,
                    "forbidden_product_ids_surfaced": forbidden_surfaced,
                    "missing_required_text": missing_required_text,
                    "expected_no_hits": expected_no_hits,
                    "expected_no_hits_check": expected_no_hits_check,
                    "passed": passed,
                    "fallback_reason": fallback_reason,
                    "natural_fallback": natural_fallback,
                    "attempted_natural_answer": attempted_natural,
                    "trace_id": response.trace_id,
                    "format_flags": format_flags,
                    "verification_issues": list(response.verification.issues),
                    "final_answer_issues": list(response.verification.final_answer_issues),
                    "answer": response.answer,
                }
            )

    total_cases = len(case_results)
    passed_cases = sum(1 for case in case_results if case["passed"])
    return {
        "suite_name": "inventory_full_system_question_pack",
        "variant": run_label,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": total_cases - passed_cases,
        "accuracy": round(passed_cases / total_cases, 3) if total_cases else 0.0,
        "abstain_metrics": {
            "false_positive_abstains": false_positive_abstains,
            "false_negative_abstains": false_negative_abstains,
        },
        "answer_engine_breakdown": dict(sorted(answer_engine_counts.items())),
        "route_breakdown": dict(sorted(route_counts.items())),
        "natural_answer_metrics": {
            "attempted_cases": fallback_attempts,
            "fallback_cases": fallback_count,
            "fallback_rate": round(fallback_count / fallback_attempts, 3) if fallback_attempts else 0.0,
            "natural_success_cases": sum(1 for case in case_results if case["answer_engine"] == "natural"),
        },
        "format_flag_counts": dict(sorted(format_flag_counts.items())),
        "case_results": case_results,
    }


def delta(current: float | int, baseline: float | int) -> float:
    return round(float(current) - float(baseline), 3)


def build_delta_summary(
    *,
    off_summary: dict[str, Any],
    on_summary: dict[str, Any],
    suite_label: str,
) -> dict[str, Any]:
    return {
        "suite_label": suite_label,
        "pass_rate_delta": delta(on_summary["accuracy"], off_summary["accuracy"]),
        "passed_cases_delta": int(on_summary["passed_cases"]) - int(off_summary["passed_cases"]),
        "false_positive_abstain_delta": int(on_summary["abstain_metrics"]["false_positive_abstains"])
        - int(off_summary["abstain_metrics"]["false_positive_abstains"]),
        "false_negative_abstain_delta": int(on_summary["abstain_metrics"]["false_negative_abstains"])
        - int(off_summary["abstain_metrics"]["false_negative_abstains"]),
    }


def changed_case_pairs(
    off_cases: list[dict[str, Any]],
    on_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    off_by_label = {str(case["label"]): case for case in off_cases}
    on_by_label = {str(case["label"]): case for case in on_cases}
    changed: list[dict[str, Any]] = []
    for label in sorted(set(off_by_label).intersection(on_by_label)):
        off_case = off_by_label[label]
        on_case = on_by_label[label]
        if (
            off_case["passed"] != on_case["passed"]
            or off_case["answer_engine"] != on_case["answer_engine"]
            or off_case["abstained"] != on_case["abstained"]
            or off_case["answer"] != on_case["answer"]
            or off_case["format_flags"] != on_case["format_flags"]
            or off_case["fallback_reason"] != on_case["fallback_reason"]
        ):
            changed.append({"label": label, "off": off_case, "on": on_case})
    return changed


def render_report(
    *,
    matrix_off: dict[str, Any],
    matrix_on: dict[str, Any],
    pack_off: dict[str, Any],
    pack_on: dict[str, Any],
    output_json_path: Path,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    matrix_delta = build_delta_summary(
        off_summary=matrix_off,
        on_summary=matrix_on,
        suite_label="Inventory eval matrix",
    )
    pack_delta = build_delta_summary(
        off_summary=pack_off,
        on_summary=pack_on,
        suite_label="Full-system question pack",
    )
    pack_natural_delta = {
        "attempted_cases_delta": int(pack_on["natural_answer_metrics"]["attempted_cases"])
        - int(pack_off["natural_answer_metrics"]["attempted_cases"]),
        "fallback_cases_delta": int(pack_on["natural_answer_metrics"]["fallback_cases"])
        - int(pack_off["natural_answer_metrics"]["fallback_cases"]),
        "fallback_rate_delta": delta(
            pack_on["natural_answer_metrics"]["fallback_rate"],
            pack_off["natural_answer_metrics"]["fallback_rate"],
        ),
        "natural_success_cases_delta": int(pack_on["natural_answer_metrics"]["natural_success_cases"])
        - int(pack_off["natural_answer_metrics"]["natural_success_cases"]),
    }

    changed_cases = changed_case_pairs(pack_off["case_results"], pack_on["case_results"])
    regression_flags: list[str] = []
    if sum(pack_on["format_flag_counts"].values()) > sum(pack_off["format_flag_counts"].values()):
        regression_flags.append("More format/verification flags were observed with few-shot on.")
    if pack_natural_delta["fallback_rate_delta"] > 0:
        regression_flags.append("Natural-answer fallback rate got worse with few-shot on.")
    if pack_delta["false_positive_abstain_delta"] > 0:
        regression_flags.append("Few-shot on introduced more false-positive abstentions.")
    if not regression_flags:
        regression_flags.append("No new hallucination or format regression signal was detected in this run.")

    lines: list[str] = [
        "# Inventory Few-Shot A/B Eval",
        "",
        f"- Run time: `{now}`",
        "- A/B dimension: `natural_answer_few_shot_enabled`",
        "- Few-shot examples in scope: `premium recommendation`, `nearby alternative with caveat`, `abstain with follow-up`",
        f"- Raw results JSON: `{output_json_path}`",
        "",
        "## Snapshot",
        "",
        "| Suite | Few-shot Off | Few-shot On | Delta |",
        "|---|---:|---:|---:|",
        f"| Inventory eval matrix pass rate | `{matrix_off['accuracy']:.3f}` | `{matrix_on['accuracy']:.3f}` | `{matrix_delta['pass_rate_delta']:+.3f}` |",
        f"| Inventory eval matrix false-positive abstains | `{matrix_off['abstain_metrics']['false_positive_abstains']}` | `{matrix_on['abstain_metrics']['false_positive_abstains']}` | `{matrix_delta['false_positive_abstain_delta']:+d}` |",
        f"| Inventory eval matrix false-negative abstains | `{matrix_off['abstain_metrics']['false_negative_abstains']}` | `{matrix_on['abstain_metrics']['false_negative_abstains']}` | `{matrix_delta['false_negative_abstain_delta']:+d}` |",
        f"| Full-system pack pass rate | `{pack_off['accuracy']:.3f}` | `{pack_on['accuracy']:.3f}` | `{pack_delta['pass_rate_delta']:+.3f}` |",
        f"| Full-system pack false-positive abstains | `{pack_off['abstain_metrics']['false_positive_abstains']}` | `{pack_on['abstain_metrics']['false_positive_abstains']}` | `{pack_delta['false_positive_abstain_delta']:+d}` |",
        f"| Full-system pack false-negative abstains | `{pack_off['abstain_metrics']['false_negative_abstains']}` | `{pack_on['abstain_metrics']['false_negative_abstains']}` | `{pack_delta['false_negative_abstain_delta']:+d}` |",
        f"| Full-system natural-answer fallback rate | `{pack_off['natural_answer_metrics']['fallback_rate']:.3f}` | `{pack_on['natural_answer_metrics']['fallback_rate']:.3f}` | `{pack_natural_delta['fallback_rate_delta']:+.3f}` |",
        "",
        "## Key Deltas",
        "",
        f"- Inventory eval matrix pass count: `{matrix_off['passed_cases']}/{matrix_off['total_cases']}` -> `{matrix_on['passed_cases']}/{matrix_on['total_cases']}`.",
        f"- Full-system pack pass count: `{pack_off['passed_cases']}/{pack_off['total_cases']}` -> `{pack_on['passed_cases']}/{pack_on['total_cases']}`.",
        f"- Full-system natural-answer attempts: `{pack_off['natural_answer_metrics']['attempted_cases']}` -> `{pack_on['natural_answer_metrics']['attempted_cases']}`.",
        f"- Full-system natural-answer fallback cases: `{pack_off['natural_answer_metrics']['fallback_cases']}` -> `{pack_on['natural_answer_metrics']['fallback_cases']}`.",
        f"- Full-system natural-answer success cases: `{pack_off['natural_answer_metrics']['natural_success_cases']}` -> `{pack_on['natural_answer_metrics']['natural_success_cases']}`.",
        "",
        "## Regression Read",
        "",
    ]
    for flag in regression_flags:
        lines.append(f"- {flag}")

    lines.extend(
        [
            "",
            "## Format / Hallucination Signals",
            "",
            f"- Few-shot off format flags: `{pack_off['format_flag_counts']}`",
            f"- Few-shot on format flags: `{pack_on['format_flag_counts']}`",
            "- Interpretation: these flags include JSON/markdown leakage, multiple follow-up questions, few-shot example leakage, and verifier-raised answer issues.",
            "",
            "## Changed Full-System Cases",
            "",
        ]
    )

    if not changed_cases:
        lines.append("- No case changed between few-shot off and few-shot on in this run.")
    else:
        for pair in changed_cases:
            off_case = pair["off"]
            on_case = pair["on"]
            lines.extend(
                [
                    f"### {pair['label']}",
                    "",
                    f"- Pass: `{off_case['passed']}` -> `{on_case['passed']}`",
                    f"- Engine: `{off_case['answer_engine']}` -> `{on_case['answer_engine']}`",
                    f"- Abstained: `{off_case['abstained']}` -> `{on_case['abstained']}`",
                    f"- Fallback reason: `{off_case['fallback_reason']}` -> `{on_case['fallback_reason']}`",
                    f"- Format flags: `{off_case['format_flags']}` -> `{on_case['format_flags']}`",
                    "",
                    "**Few-shot off**",
                    "",
                    "```text",
                    off_case["answer"],
                    "```",
                    "",
                    "**Few-shot on**",
                    "",
                    "```text",
                    on_case["answer"],
                    "```",
                    "",
                ]
            )

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    settings = get_settings()
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    matrix_off = run_inventory_eval_matrix(
        natural_answers_enabled=True,
        natural_answer_few_shot_enabled=False,
        natural_answer_few_shot_max_examples=settings.inventory_natural_answer_few_shot_max_examples,
    )
    matrix_on = run_inventory_eval_matrix(
        natural_answers_enabled=True,
        natural_answer_few_shot_enabled=True,
        natural_answer_few_shot_max_examples=settings.inventory_natural_answer_few_shot_max_examples,
    )
    pack_off = execute_question_pack(few_shot_enabled=False)
    pack_on = execute_question_pack(few_shot_enabled=True)

    output_json_path = results_dir / f"inventory_few_shot_ab_eval_{today}.json"
    output_md_path = ROOT / f"inventory_few_shot_ab_eval_{today}.md"
    payload = {
        "run_date": today,
        "matrix_off": matrix_off,
        "matrix_on": matrix_on,
        "pack_off": pack_off,
        "pack_on": pack_on,
    }
    output_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md_path.write_text(
        render_report(
            matrix_off=matrix_off,
            matrix_on=matrix_on,
            pack_off=pack_off,
            pack_on=pack_on,
            output_json_path=output_json_path,
        ),
        encoding="utf-8",
    )
    print(output_md_path)
    print(output_json_path)


if __name__ == "__main__":
    main()
