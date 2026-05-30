from __future__ import annotations

import json
import tempfile
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryAnswerPlan, InventoryAskRequest, InventoryItemRecord
from app.inventory.conversation_state import ConversationState, get_state_store
from app.retrieval import (
    DeterministicTextEmbedder,
    EmbedderConfig,
    EmbeddingProvider,
    LocalVectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
)
from app.services.inventory_service import InventoryService, InventoryServiceConfig


CASES_PATH = Path("evaluation/dummy_flow_regression_cases.jsonl")
RESULTS_PATH = Path("results/dummy_flow_regression_results.jsonl")
REPORT_PATH = Path("results/dummy_flow_regression_report.md")


@dataclass(frozen=True)
class ExpectedMemory:
    active_slots: dict[str, Any] = field(default_factory=dict)
    last_primary_product_id: str | None = None
    last_shown_product_ids: list[str] | None = None
    product_focus_use_count_min: int | None = None
    product_focus_last_used: bool | None = None
    blocked_active_slots: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FlowTurn:
    question: str
    expected_intent: str | None = None
    expected_flow_action: str | None = None
    expected_retrieval_scope: str | None = None
    expected_answer_contains: list[str] = field(default_factory=list)
    expected_products: list[str] | None = None
    expected_product_prefix: list[str] | None = None
    expected_filter_categories: list[str] | None = None
    expected_filter_product_ids: list[str] | None = None
    request_focused_product_ids: list[str] = field(default_factory=list)
    request_last_answer_plan_product_id: str | None = None
    expected_memory: ExpectedMemory = field(default_factory=ExpectedMemory)


@dataclass(frozen=True)
class FlowCase:
    flow_id: str
    description: str
    turns: list[FlowTurn]


@dataclass(frozen=True)
class TurnResult:
    flow_id: str
    turn_index: int
    question: str
    passed: bool
    failures: list[str]
    answer: str
    intent: str | None
    flow_action: str | None
    recommended_product_ids: list[str]
    applied_categories: list[str]
    applied_product_ids: list[str]
    memory_state: dict[str, Any]


def dummy_catalog() -> list[InventoryItemRecord]:
    return [
        InventoryItemRecord(
            product_id="salwar-red-wedding",
            sku="SK-RED-001",
            name="Red Embroidered Salwar Kameez",
            category="Salwar Kameez",
            price=4200,
            currency="BDT",
            stock=4,
            status="active",
            attributes={
                "category_key": "salwar_kameez",
                "color": "Red",
                "color_family": "red",
                "occasion": "wedding",
                "available_sizes": "M,L,XL",
            },
            tags=["Salwar Kameez", "Red", "Wedding"],
        ),
        InventoryItemRecord(
            product_id="salwar-blue-casual",
            sku="SK-BLUE-001",
            name="Blue Casual Salwar Kameez",
            category="Salwar Kameez",
            price=3500,
            currency="BDT",
            stock=3,
            status="active",
            attributes={
                "category_key": "salwar_kameez",
                "color": "Blue",
                "color_family": "blue",
                "occasion": "casual",
                "available_sizes": "S,M,L",
            },
            tags=["Salwar Kameez", "Blue", "Casual"],
        ),
        InventoryItemRecord(
            product_id="shoe-black-formal",
            sku="SHOE-BLK-001",
            name="Black Formal Shoe",
            category="Shoes",
            price=2662,
            currency="BDT",
            stock=2,
            status="active",
            attributes={
                "category_key": "shoes",
                "color": "Black",
                "color_family": "black",
                "occasion": "wedding",
                "available_sizes": "40,42,44",
            },
            tags=["Shoe", "Formal", "Black", "Wedding"],
        ),
        InventoryItemRecord(
            product_id="sandal-white-flat",
            sku="SANDAL-WHT-001",
            name="White Flat Sandal",
            category="Shoes",
            price=1800,
            currency="BDT",
            stock=3,
            status="active",
            attributes={
                "category_key": "shoes",
                "color": "White",
                "color_family": "white",
                "available_sizes": "38,39,40",
            },
            tags=["Sandal", "White", "Flat"],
        ),
        InventoryItemRecord(
            product_id="saree-red-jamdani",
            sku="SAR-RED-001",
            name="Red Jamdani Saree",
            category="Saree",
            price=6800,
            currency="BDT",
            stock=2,
            status="active",
            attributes={
                "category_key": "saree",
                "color": "Red",
                "color_family": "red",
                "fabric": "jamdani",
                "occasion": "wedding",
            },
            tags=["Saree", "Red", "Jamdani", "Wedding"],
        ),
        InventoryItemRecord(
            product_id="saree-blue-jamdani",
            sku="SAR-BLU-001",
            name="Blue Jamdani Saree",
            category="Saree",
            price=6200,
            currency="BDT",
            stock=1,
            status="active",
            attributes={
                "category_key": "saree",
                "color": "Blue",
                "color_family": "blue",
                "fabric": "jamdani",
            },
            tags=["Saree", "Blue", "Jamdani"],
        ),
        InventoryItemRecord(
            product_id="panjabi-black-cotton",
            sku="PANJ-BLK-001",
            name="Black Cotton Panjabi",
            category="Panjabi",
            price=2500,
            currency="BDT",
            stock=5,
            status="active",
            attributes={
                "category_key": "panjabi",
                "color": "Black",
                "color_family": "black",
                "fabric": "cotton",
                "available_sizes": "M,L,XL",
            },
            tags=["Panjabi", "Black", "Cotton"],
        ),
        InventoryItemRecord(
            product_id="perfume-floral-gift",
            sku="PERF-FLR-001",
            name="Floral Gift Perfume",
            category="Perfume",
            price=1500,
            currency="BDT",
            stock=6,
            status="active",
            attributes={
                "category_key": "perfume",
                "color_family": "assorted",
                "occasion": "gift",
            },
            tags=["Perfume", "Gift", "Fragrance"],
        ),
        InventoryItemRecord(
            product_id="bag-gold-party",
            sku="BAG-GLD-001",
            name="Gold Party Bag",
            category="Accessories",
            price=1900,
            currency="BDT",
            stock=4,
            status="active",
            attributes={
                "category_key": "bag",
                "color": "Gold",
                "color_family": "gold",
                "occasion": "party",
            },
            tags=["Bag", "Gold", "Party"],
        ),
    ]


def dummy_flows() -> list[FlowCase]:
    return [
        FlowCase(
            flow_id="salwar_refine_price_switch",
            description="Category search, slot refinement, product detail follow-up, then fresh category switch.",
            turns=[
                FlowTurn(
                    question="do you have Salwar Kameez?",
                    expected_intent="fashion_search",
                    expected_flow_action="START_NEW_FLOW",
                    expected_retrieval_scope="fresh_product_or_category",
                    expected_answer_contains=["Red Embroidered Salwar Kameez"],
                    expected_product_prefix=["salwar-red-wedding"],
                    expected_filter_categories=["Salwar Kameez"],
                    expected_filter_product_ids=[],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "salwar_kameez"},
                        last_primary_product_id="salwar-red-wedding",
                        last_shown_product_ids=["salwar-red-wedding", "salwar-blue-casual"],
                    ),
                ),
                FlowTurn(
                    question="wedding, red",
                    expected_intent="fashion_search",
                    expected_flow_action="UPDATE_FLOW_SLOTS",
                    expected_retrieval_scope="active_category_plus_slots",
                    expected_answer_contains=["Red Embroidered Salwar Kameez", "BDT 4,200"],
                    expected_products=["salwar-red-wedding"],
                    expected_filter_categories=["Salwar Kameez"],
                    expected_filter_product_ids=[],
                    expected_memory=ExpectedMemory(
                        active_slots={
                            "category_key": "salwar_kameez",
                            "color_family": "red",
                            "occasion": "wedding",
                        },
                        last_primary_product_id="salwar-red-wedding",
                        last_shown_product_ids=["salwar-red-wedding"],
                    ),
                ),
                FlowTurn(
                    question="price koto?",
                    expected_intent="fashion_product_detail",
                    expected_flow_action="CONTINUE_PRODUCT_FOCUS",
                    expected_retrieval_scope="focused_product_or_list",
                    expected_answer_contains=["price is BDT 4,200", "4 in stock"],
                    expected_products=["salwar-red-wedding"],
                    expected_filter_categories=["Salwar Kameez"],
                    expected_filter_product_ids=["salwar-red-wedding"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "salwar_kameez"},
                        last_primary_product_id="salwar-red-wedding",
                        product_focus_use_count_min=1,
                        product_focus_last_used=True,
                    ),
                ),
                FlowTurn(
                    question="black shoe ache?",
                    expected_intent="fashion_search",
                    expected_flow_action="START_NEW_FLOW",
                    expected_retrieval_scope="fresh_product_or_category",
                    expected_answer_contains=["Black Formal Shoe"],
                    expected_product_prefix=["shoe-black-formal"],
                    expected_filter_categories=["Shoes"],
                    expected_filter_product_ids=[],
                    request_focused_product_ids=["salwar-red-wedding"],
                    request_last_answer_plan_product_id="salwar-red-wedding",
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "shoes", "color_family": "black"},
                        last_primary_product_id="shoe-black-formal",
                    ),
                ),
                FlowTurn(
                    question="size 42 ache?",
                    expected_intent="fashion_size_availability",
                    expected_flow_action="UPDATE_FLOW_SLOTS",
                    expected_retrieval_scope="active_category_plus_slots",
                    expected_answer_contains=["size 42", "Black Formal Shoe"],
                    expected_product_prefix=["shoe-black-formal"],
                    expected_filter_categories=["Shoes"],
                    expected_filter_product_ids=[],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "shoes", "size": "42"},
                        last_primary_product_id="shoe-black-formal",
                    ),
                ),
            ],
        ),
        FlowCase(
            flow_id="support_and_safety_detours",
            description="Support and safety turns must not overwrite shopping focus.",
            turns=[
                FlowTurn(
                    question="red saree dekhao",
                    expected_intent="fashion_search",
                    expected_flow_action="START_NEW_FLOW",
                    expected_answer_contains=["Red Jamdani Saree"],
                    expected_product_prefix=["saree-red-jamdani"],
                    expected_filter_categories=["Saree"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "saree", "color_family": "red"},
                        last_primary_product_id="saree-red-jamdani",
                    ),
                ),
                FlowTurn(
                    question="delivery charge koto?",
                    expected_flow_action="SUPPORT_ROUTE",
                    expected_retrieval_scope="support_policy_no_product_memory",
                    expected_answer_contains=["Inside Dhaka", "Outside Dhaka"],
                    expected_products=[],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "saree", "color_family": "red"},
                        last_primary_product_id="saree-red-jamdani",
                    ),
                ),
                FlowTurn(
                    question="etar price koto?",
                    expected_intent="fashion_product_detail",
                    expected_flow_action="CONTINUE_PRODUCT_FOCUS",
                    expected_answer_contains=["Red Jamdani Saree price is BDT 6,800"],
                    expected_products=["saree-red-jamdani"],
                    expected_filter_product_ids=["saree-red-jamdani"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "saree"},
                        last_primary_product_id="saree-red-jamdani",
                        product_focus_use_count_min=1,
                        product_focus_last_used=True,
                    ),
                ),
                FlowTurn(
                    question="rash er jonno kon medicine khabo?",
                    expected_flow_action="SAFETY_ROUTE",
                    expected_answer_contains=["Medical advice"],
                    expected_products=[],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "saree"},
                        last_primary_product_id="saree-red-jamdani",
                        blocked_active_slots=["wellness", "medicine"],
                    ),
                ),
            ],
        ),
        FlowCase(
            flow_id="bangla_flow_switch",
            description="Bangla product starts and follow-ups should be routed as first-class flow events.",
            turns=[
                FlowTurn(
                    question="লাল শাড়ি দেখাও",
                    expected_intent="fashion_search",
                    expected_flow_action="START_NEW_FLOW",
                    expected_answer_contains=["Red Jamdani Saree"],
                    expected_product_prefix=["saree-red-jamdani"],
                    expected_filter_categories=["Saree"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "saree", "color_family": "red"},
                        last_primary_product_id="saree-red-jamdani",
                    ),
                ),
                FlowTurn(
                    question="এটার দাম কত?",
                    expected_intent="fashion_product_detail",
                    expected_flow_action="CONTINUE_PRODUCT_FOCUS",
                    expected_answer_contains=["BDT 6,800"],
                    expected_products=["saree-red-jamdani"],
                    expected_filter_product_ids=["saree-red-jamdani"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "saree"},
                        product_focus_use_count_min=1,
                        product_focus_last_used=True,
                    ),
                ),
                FlowTurn(
                    question="কালো পাঞ্জাবি দেখাও",
                    expected_intent="fashion_search",
                    expected_flow_action="START_NEW_FLOW",
                    expected_answer_contains=["Black Cotton Panjabi"],
                    expected_product_prefix=["panjabi-black-cotton"],
                    expected_filter_categories=["Panjabi"],
                    expected_filter_product_ids=[],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "panjabi", "color_family": "black"},
                        last_primary_product_id="panjabi-black-cotton",
                    ),
                ),
            ],
        ),
        FlowCase(
            flow_id="offtopic_then_commerce",
            description="Off-topic turns should redirect cleanly, then true commerce should start normal memory.",
            turns=[
                FlowTurn(
                    question="amar ekta gf lagbe",
                    expected_flow_action="NO_FLOW",
                    expected_answer_contains=["gift"],
                    expected_memory=ExpectedMemory(
                        last_primary_product_id=None,
                    ),
                ),
                FlowTurn(
                    question="gift perfume dekhao budget 2000",
                    expected_intent="fashion_search",
                    expected_flow_action="START_NEW_FLOW",
                    expected_answer_contains=["Floral Gift Perfume"],
                    expected_product_prefix=["perfume-floral-gift"],
                    expected_filter_categories=["Perfume"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "perfume", "budget_max": 2000},
                        last_primary_product_id="perfume-floral-gift",
                    ),
                ),
                FlowTurn(
                    question="price?",
                    expected_intent="fashion_product_detail",
                    expected_flow_action="CONTINUE_PRODUCT_FOCUS",
                    expected_answer_contains=["Floral Gift Perfume price is BDT 1,500"],
                    expected_products=["perfume-floral-gift"],
                    expected_filter_product_ids=["perfume-floral-gift"],
                    expected_memory=ExpectedMemory(
                        active_slots={"category_key": "perfume"},
                        product_focus_use_count_min=1,
                        product_focus_last_used=True,
                    ),
                ),
            ],
        ),
    ]


def build_service(tmp_path: Path) -> InventoryService:
    vector_store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            local_store_path=str(tmp_path / "vectors.jsonl"),
            namespace="dummy-flow",
            dimensions=16,
        )
    )
    embedder = DeterministicTextEmbedder(
        EmbedderConfig(
            provider=EmbeddingProvider.DETERMINISTIC,
            model_name="dummy-flow-deterministic",
            dimensions=16,
            normalize=True,
        )
    )
    service = InventoryService(
        embedder=embedder,
        vector_store=vector_store,
        config=InventoryServiceConfig(
            catalog_path=str(tmp_path / "catalog.jsonl"),
            namespace="dummy-flow",
            default_top_k=5,
            max_top_k=10,
            agentic_trace_dir=str(tmp_path / "traces"),
            business_signal_path=str(tmp_path / "business_signals.jsonl"),
            inventory_storage_backend="jsonl",
            inventory_sqlite_path=str(tmp_path / "mirror.sqlite3"),
        ),
    )
    service.upsert_items(dummy_catalog())
    return service


def write_cases(path: Path, flows: list[FlowCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for flow in flows:
            for turn_index, turn in enumerate(flow.turns, start=1):
                payload = asdict(turn)
                payload["flow_id"] = flow.flow_id
                payload["flow_description"] = flow.description
                payload["turn_index"] = turn_index
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_turn(
    *,
    service: InventoryService,
    session_id: str,
    turn: FlowTurn,
) -> tuple[Any, ConversationState]:
    request = InventoryAskRequest(
        question=turn.question,
        session_id=session_id,
        top_k=5,
        answer_engine="deterministic",
        focused_product_ids=list(turn.request_focused_product_ids),
        last_answer_plan=(
            InventoryAnswerPlan(primary_product_id=turn.request_last_answer_plan_product_id)
            if turn.request_last_answer_plan_product_id
            else None
        ),
    )
    response = service.ask(request)
    state = get_state_store().get(session_id)
    return response, state


def evaluate_turn(
    *,
    flow_id: str,
    turn_index: int,
    turn: FlowTurn,
    response: Any,
    state: ConversationState,
) -> TurnResult:
    failures: list[str] = []
    answer = response.answer or ""
    answer_lower = answer.casefold()
    memory = response.memory_resolution
    products = list(response.recommended_product_ids)
    categories = list(response.applied_filters.categories)
    product_ids_filter = list(response.applied_filters.product_ids)
    intent = response.answer_plan.intent if response.answer_plan else None

    if turn.expected_intent is not None and intent != turn.expected_intent:
        failures.append(f"intent expected {turn.expected_intent!r}, got {intent!r}")
    if turn.expected_flow_action is not None and memory.flow_action != turn.expected_flow_action:
        failures.append(f"flow_action expected {turn.expected_flow_action!r}, got {memory.flow_action!r}")
    if turn.expected_retrieval_scope is not None and memory.retrieval_scope != turn.expected_retrieval_scope:
        failures.append(f"retrieval_scope expected {turn.expected_retrieval_scope!r}, got {memory.retrieval_scope!r}")
    for fragment in turn.expected_answer_contains:
        if fragment.casefold() not in answer_lower:
            failures.append(f"answer missing fragment {fragment!r}")
    if turn.expected_products is not None and products != turn.expected_products:
        failures.append(f"products expected {turn.expected_products!r}, got {products!r}")
    if turn.expected_product_prefix is not None and products[: len(turn.expected_product_prefix)] != turn.expected_product_prefix:
        failures.append(f"product prefix expected {turn.expected_product_prefix!r}, got {products!r}")
    if turn.expected_filter_categories is not None and categories != turn.expected_filter_categories:
        failures.append(f"filter categories expected {turn.expected_filter_categories!r}, got {categories!r}")
    if turn.expected_filter_product_ids is not None and product_ids_filter != turn.expected_filter_product_ids:
        failures.append(f"filter product_ids expected {turn.expected_filter_product_ids!r}, got {product_ids_filter!r}")

    expected_memory = turn.expected_memory
    for key, expected_value in expected_memory.active_slots.items():
        actual_value = state.active_slots.get(key)
        if actual_value != expected_value:
            failures.append(f"memory active_slots[{key!r}] expected {expected_value!r}, got {actual_value!r}")
    if expected_memory.last_primary_product_id is not None and state.last_primary_product_id != expected_memory.last_primary_product_id:
        failures.append(
            f"memory last_primary_product_id expected {expected_memory.last_primary_product_id!r}, got {state.last_primary_product_id!r}"
        )
    if expected_memory.last_primary_product_id is None and turn.expected_memory.last_primary_product_id is None and turn.expected_products == []:
        if state.last_primary_product_id is not None:
            failures.append(f"memory last_primary_product_id expected None, got {state.last_primary_product_id!r}")
    if expected_memory.last_shown_product_ids is not None:
        actual_prefix = state.last_shown_product_ids[: len(expected_memory.last_shown_product_ids)]
        if actual_prefix != expected_memory.last_shown_product_ids:
            failures.append(
                f"memory last_shown_product_ids prefix expected {expected_memory.last_shown_product_ids!r}, got {state.last_shown_product_ids!r}"
            )
    if expected_memory.product_focus_use_count_min is not None and state.product_focus_use_count < expected_memory.product_focus_use_count_min:
        failures.append(
            f"memory product_focus_use_count expected >= {expected_memory.product_focus_use_count_min}, got {state.product_focus_use_count}"
        )
    if expected_memory.product_focus_last_used is True and not state.product_focus_last_used_at:
        failures.append("memory product_focus_last_used_at expected to be set")
    if expected_memory.product_focus_last_used is False and state.product_focus_last_used_at:
        failures.append("memory product_focus_last_used_at expected to be empty")
    for blocked in expected_memory.blocked_active_slots:
        if blocked in state.active_slots.values() or blocked in state.active_slots:
            failures.append(f"blocked memory value/key {blocked!r} appeared in active_slots {state.active_slots!r}")

    return TurnResult(
        flow_id=flow_id,
        turn_index=turn_index,
        question=turn.question,
        passed=not failures,
        failures=failures,
        answer=answer,
        intent=intent,
        flow_action=memory.flow_action,
        recommended_product_ids=products,
        applied_categories=categories,
        applied_product_ids=product_ids_filter,
        memory_state={
            "last_primary_product_id": state.last_primary_product_id,
            "last_shown_product_ids": list(state.last_shown_product_ids),
            "active_slots": dict(state.active_slots),
            "product_focus_source": state.product_focus_source,
            "product_focus_use_count": state.product_focus_use_count,
            "product_focus_last_used_at": state.product_focus_last_used_at,
        },
    )


def write_results(results: list[TurnResult]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    passed = sum(1 for result in results if result.passed)
    lines = [
        "# Dummy Flow Regression Report",
        "",
        f"- Created: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Passed: **{passed}/{len(results)}**",
        "",
        "## Turn Results",
        "",
        "| Flow | Turn | Question | Flow Action | Intent | Products | Result |",
        "|---|---:|---|---|---|---|---|",
    ]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        products = ", ".join(result.recommended_product_ids[:3]) or "-"
        lines.append(
            f"| `{result.flow_id}` | {result.turn_index} | {result.question} | `{result.flow_action}` | `{result.intent}` | {products} | {status} |"
        )
    failures = [result for result in results if not result.passed]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("No failed cases.")
    else:
        for result in failures:
            lines.append(f"### {result.flow_id} turn {result.turn_index}: {result.question}")
            lines.extend(f"- {failure}" for failure in result.failures)
            lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> int:
    flows = dummy_flows()
    write_cases(CASES_PATH, flows)
    results: list[TurnResult] = []
    with tempfile.TemporaryDirectory(prefix="dummy-flow-regression-") as tmp:
        service = build_service(Path(tmp))
        state_store = get_state_store()
        for flow in flows:
            session_id = f"dummy-flow::{flow.flow_id}"
            state_store.clear(session_id)
            for index, turn in enumerate(flow.turns, start=1):
                response, state = run_turn(service=service, session_id=session_id, turn=turn)
                results.append(
                    evaluate_turn(
                        flow_id=flow.flow_id,
                        turn_index=index,
                        turn=turn,
                        response=response,
                        state=state,
                    )
                )

    write_results(results)
    failed = [result for result in results if not result.passed]
    print(f"Dummy flow regression: {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        for result in failed[:20]:
            print(f"FAIL {result.flow_id} turn {result.turn_index}: {'; '.join(result.failures)}")
        print(f"Report: {REPORT_PATH}")
        return 1
    print(f"Cases: {CASES_PATH}")
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
