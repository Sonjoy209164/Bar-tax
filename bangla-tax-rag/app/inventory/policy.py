from __future__ import annotations

from functools import lru_cache

from app.core.schemas import (
    InventoryAbstainTriggerContract,
    InventoryCanonicalEvalContractCase,
    InventoryPolicyContractResponse,
    InventoryQuestionFamilyContract,
)

INVENTORY_POLICY_VERSION = "inventory-contract-v1"


def inventory_question_family_contract(family: str) -> InventoryQuestionFamilyContract | None:
    normalized = family.strip().casefold()
    for contract in _question_family_contracts():
        if contract.family.casefold() == normalized:
            return contract.model_copy(deep=True)
    return None


def inventory_family_abstain_triggers(family: str) -> list[InventoryAbstainTriggerContract]:
    normalized = family.strip().casefold()
    applicable: list[InventoryAbstainTriggerContract] = []
    for trigger in _hard_abstain_triggers():
        applies = {entry.casefold() for entry in trigger.applies_to_families}
        if "all" in applies or normalized in applies:
            applicable.append(trigger.model_copy(deep=True))
    return applicable


def inventory_canonical_eval_case_ids() -> list[str]:
    return [case.case_id for case in _canonical_eval_cases()]


@lru_cache(maxsize=1)
def inventory_policy_contract() -> InventoryPolicyContractResponse:
    families = [contract.model_copy(deep=True) for contract in _question_family_contracts()]
    triggers = [trigger.model_copy(deep=True) for trigger in _hard_abstain_triggers()]
    eval_cases = [case.model_copy(deep=True) for case in _canonical_eval_cases()]
    return InventoryPolicyContractResponse(
        status="success",
        version=INVENTORY_POLICY_VERSION,
        summary=(
            "Inventory chat uses a fixed contract for supported question families, default execution paths, "
            "hard abstain triggers, and the canonical evaluation set used to guard regressions."
        ),
        supported_question_families=families,
        hard_abstain_triggers=triggers,
        canonical_eval_cases=eval_cases,
        canonical_eval_case_ids=[case.case_id for case in eval_cases],
    )


def _question_family_contracts() -> tuple[InventoryQuestionFamilyContract, ...]:
    return (
        InventoryQuestionFamilyContract(
            family="small_talk",
            description="Greeting or conversational chatter that should not enter the retrieval stack.",
            classifier_intents=["small_talk"],
            default_execution_path="normal_rag",
            supported_execution_paths=["normal_rag"],
            reasoning_mode="deterministic",
            external_data_required=False,
            canonical_eval_case_ids=[],
            notes=[
                "Handled with deterministic conversational replies.",
                "Covered today by API behavior tests rather than the inventory eval matrix.",
            ],
        ),
        InventoryQuestionFamilyContract(
            family="exact_lookup",
            description="Direct product detail, SKU lookup, alias lookup, or simple catalog search.",
            classifier_intents=["exact_lookup", "product_detail", "product_search"],
            default_execution_path="normal_rag",
            supported_execution_paths=["normal_rag"],
            reasoning_mode="deterministic",
            external_data_required=False,
            canonical_eval_case_ids=[
                "exact-product-detail",
                "lexical-miss-recovery",
                "alias-recovery",
            ],
            notes=[
                "This family stays deterministic by default because mirrored catalog evidence should be enough.",
                "The retrieval stack must recover exact names, lexical near-misses, and explicit aliases before generation begins.",
            ],
        ),
        InventoryQuestionFamilyContract(
            family="comparison",
            description="Side-by-side comparison between products or variants.",
            classifier_intents=["comparison"],
            default_execution_path="normal_rag",
            supported_execution_paths=["normal_rag", "agentic"],
            reasoning_mode="deterministic_with_optional_agentic",
            external_data_required=False,
            canonical_eval_case_ids=["agentic-compare"],
            notes=[
                "Default route stays fast when the mirrored catalog can answer the comparison directly.",
                "Bounded agentic decomposition remains supported for explicit compare workflows.",
            ],
        ),
        InventoryQuestionFamilyContract(
            family="recommendation",
            description="Recommendations, objection handling, product-fit guidance, and deterministic cross-sell suggestions.",
            classifier_intents=[
                "recommendation",
                "price_objection",
                "availability_objection",
                "quality_objection",
                "cross_sell",
            ],
            default_execution_path="normal_rag",
            supported_execution_paths=["normal_rag"],
            reasoning_mode="deterministic",
            external_data_required=False,
            canonical_eval_case_ids=[
                "valid-recommendation",
                "wrong-product-type",
                "budget-ceiling-violation",
                "alternative-violation",
                "spec-mismatch",
                "conflicting-stock-signals",
                "abstain-false-positive-guardrail",
            ],
            notes=[
                "Primary and alternative selection must come from deterministic scorecards, not hit order.",
                "Hard-fit verification can still force abstention even when retrieval found plausible products.",
            ],
        ),
        InventoryQuestionFamilyContract(
            family="diagnosis_root_cause",
            description="Why questions that require operational diagnosis across business signals and catalog facts.",
            classifier_intents=["business_analysis"],
            default_execution_path="agentic",
            supported_execution_paths=["agentic"],
            reasoning_mode="bounded_agentic",
            external_data_required=True,
            canonical_eval_case_ids=["agentic-diagnosis-root-cause"],
            notes=[
                "This family requires bounded multi-step decomposition.",
                "The system must abstain when the needed business domains are unavailable.",
            ],
        ),
        InventoryQuestionFamilyContract(
            family="planning_agentic_workflow",
            description="Action-oriented planning such as restock prioritization, bundling, and operational next-step guidance.",
            classifier_intents=["restock", "business_analysis", "cross_sell"],
            default_execution_path="agentic",
            supported_execution_paths=["agentic"],
            reasoning_mode="bounded_agentic",
            external_data_required=True,
            canonical_eval_case_ids=[
                "agentic-bundle",
                "agentic-restock",
                "agentic-operational-planning",
                "agentic-missing-domain-abstain",
            ],
            notes=[
                "This family is agentic by default because it needs explicit bounded sub-goals.",
                "Missing required domains is a hard abstain condition, not a reason to bluff with catalog-only text.",
            ],
        ),
        InventoryQuestionFamilyContract(
            family="no_match_or_abstain",
            description="Underspecified, unsupported, or unsafe requests that should clarify or abstain instead of forcing retrieval.",
            classifier_intents=["unknown"],
            default_execution_path="clarify_or_abstain",
            supported_execution_paths=["normal_rag"],
            reasoning_mode="abstain_or_clarify",
            external_data_required=False,
            canonical_eval_case_ids=[],
            notes=[
                "This family exists to prevent generic fall-through behavior.",
                "Covered today mainly by route and API behavior tests instead of the inventory eval matrix.",
            ],
        ),
    )


def _hard_abstain_triggers() -> tuple[InventoryAbstainTriggerContract, ...]:
    return (
        InventoryAbstainTriggerContract(
            trigger_id="non_inventory_or_underspecified_request",
            description="The request is not clearly inventory-related or is too underspecified to answer safely.",
            stage="routing",
            applies_to_families=["no_match_or_abstain", "recommendation"],
            examples=[
                "Show me something good",
                "Can you help me?",
            ],
        ),
        InventoryAbstainTriggerContract(
            trigger_id="missing_required_data_domains",
            description="The chosen question family requires external domains that are not currently available.",
            stage="routing",
            applies_to_families=["diagnosis_root_cause", "planning_agentic_workflow"],
            examples=[
                "Restock planning without sales or inventory snapshots",
                "Returns diagnosis without returns data",
            ],
        ),
        InventoryAbstainTriggerContract(
            trigger_id="exact_lookup_without_catalog_match",
            description="A direct product detail or exact lookup request has no exact or near-exact grounded catalog match.",
            stage="retrieval",
            applies_to_families=["exact_lookup"],
            examples=[
                "Detail request for an unknown SKU",
                "Alias lookup with no grounded product match",
            ],
        ),
        InventoryAbstainTriggerContract(
            trigger_id="hard_constraint_violation",
            description="The chosen primary or alternative violates a hard user constraint such as category, budget, stock, or required spec filters.",
            stage="verification",
            applies_to_families=["recommendation", "comparison"],
            examples=[
                "Budget ceiling violation",
                "Requested product type mismatch",
                "Required RAM or battery filter not met",
            ],
        ),
        InventoryAbstainTriggerContract(
            trigger_id="conflicting_evidence",
            description="Structured evidence conflicts in a way that makes the answer unsafe, such as catalog stock contradicting business snapshots.",
            stage="verification",
            applies_to_families=["recommendation", "exact_lookup", "planning_agentic_workflow"],
            examples=[
                "Catalog says in stock but inventory snapshot says zero",
            ],
        ),
        InventoryAbstainTriggerContract(
            trigger_id="missing_required_facts_for_claim",
            description="The answer would require a claim the evidence contract cannot support with allowed facts.",
            stage="planning",
            applies_to_families=["all"],
            examples=[
                "Recommending a spec the contract does not contain",
                "Claiming a business rationale without supporting signals",
            ],
        ),
    )


def _canonical_eval_cases() -> tuple[InventoryCanonicalEvalContractCase, ...]:
    return (
        InventoryCanonicalEvalContractCase(
            case_id="valid-recommendation",
            family="recommendation",
            example_question="Recommend a premium laptop for this customer",
            purpose="Guard the happy-path premium recommendation flow.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="exact-product-detail",
            family="exact_lookup",
            example_question="tell me about Auralite Pro Monitor Pair",
            purpose="Guard exact product-detail resolution.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="lexical-miss-recovery",
            family="exact_lookup",
            example_question="tell me about Auralite Pro monitr pair",
            purpose="Guard lexical near-miss recovery for direct detail questions.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="alias-recovery",
            family="exact_lookup",
            example_question="tell me about N14E",
            purpose="Guard alias-only recovery for direct detail questions.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="wrong-product-type",
            family="recommendation",
            example_question="Recommend wireless headphones for office calls",
            purpose="Prevent category drift in deterministic recommendations.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="budget-ceiling-violation",
            family="recommendation",
            example_question="Recommend a laptop under $1000",
            purpose="Force abstention on budget-breaking recommendations.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="alternative-violation",
            family="recommendation",
            example_question="Recommend a laptop under $1000, but show the next stronger option too",
            purpose="Force abstention when the alternative breaks hard fit constraints.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="spec-mismatch",
            family="recommendation",
            example_question="Recommend a laptop with 32GB RAM",
            purpose="Force abstention when structured spec requirements are not met.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="conflicting-stock-signals",
            family="recommendation",
            example_question="Show me an in stock laptop",
            purpose="Guard against unsafe stock claims when evidence conflicts.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="abstain-false-positive-guardrail",
            family="recommendation",
            example_question="Recommend a laptop under $1000",
            purpose="Prevent unnecessary abstention when one grounded option remains valid.",
            expected_execution_path="inventory_ask",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="agentic-compare",
            family="comparison",
            example_question="Compare CreatorCraft 16 Pro vs CreatorCraft 16 Air",
            purpose="Guard bounded comparison decomposition and fact alignment.",
            expected_execution_path="inventory_agentic",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="agentic-bundle",
            family="planning_agentic_workflow",
            example_question="What should I bundle with Nimbus 14 Business Ultrabook?",
            purpose="Guard primary-product plus compatible add-on planning.",
            expected_execution_path="inventory_agentic",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="agentic-restock",
            family="planning_agentic_workflow",
            example_question="What should I restock first to prevent stockout?",
            purpose="Guard restock prioritization over demand, margin, and lead time signals.",
            expected_execution_path="inventory_agentic",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="agentic-diagnosis-root-cause",
            family="diagnosis_root_cause",
            example_question="Why are Auralite Max Earbuds returns increasing this quarter?",
            purpose="Guard bounded diagnosis with matched business evidence.",
            expected_execution_path="inventory_agentic",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="agentic-operational-planning",
            family="planning_agentic_workflow",
            example_question="What should we do first about supplier delays across audio products?",
            purpose="Guard operational planning decomposition beyond generic recommendation logic.",
            expected_execution_path="inventory_agentic",
        ),
        InventoryCanonicalEvalContractCase(
            case_id="agentic-missing-domain-abstain",
            family="planning_agentic_workflow",
            example_question="What should I restock first next month?",
            purpose="Force abstention when required planning domains are unavailable.",
            expected_execution_path="inventory_agentic_missing_domain_abstain",
        ),
    )
