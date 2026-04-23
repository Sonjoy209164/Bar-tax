from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from app.core.schemas import (
    InventoryAgenticRequest,
    InventoryAgenticResponse,
    InventoryAgenticStatusResponse,
    InventoryAgenticStep,
    InventoryAgenticTraceResponse,
    InventoryAnswerPlan,
    InventoryAnswerVerification,
    InventoryAskRequest,
    InventoryAskResponse,
    InventoryBusinessSignalRecord,
    InventoryBusinessSignalsDeleteResponse,
    InventoryBusinessSignalsResponse,
    InventoryBusinessSignalsUpsertResponse,
    InventoryBusinessStatusResponse,
    InventoryCatalogResponse,
    InventoryChatTraceResponse,
    InventoryConversationTurn,
    InventoryDeleteResponse,
    InventoryExecutionContract,
    InventoryItemRecord,
    InventoryMemoryResolution,
    InventoryProductionStatusResponse,
    InventoryRouteRequest,
    InventoryRouteResponse,
    InventoryRouteSignals,
    InventorySearchFilters,
    InventorySearchHit,
    InventorySearchRequest,
    InventorySearchResponse,
    InventoryStatusResponse,
    InventorySyncRebuildResponse,
    InventorySyncIssue,
    InventorySyncStatusResponse,
    InventorySyncValidateRequest,
    InventorySyncValidateResponse,
    InventoryTraceCandidateDebug,
    InventoryUpsertResponse,
)
from app.core.settings import get_settings
from app.generation.generator import ChatMessage, build_generation_options, get_chat_client
from app.inventory import (
    EcommerceReranker,
    InventoryAnswerPlanner,
    InventoryDecisionScorer,
    InventoryEvidenceContractBuilder,
    InventoryFinalAnswerVerifier,
    InventoryIntentClassifier,
    InventoryIntentResult,
    InventoryMemoryResolver,
    InventoryPreferenceExtractor,
    InventoryPreferenceProfile,
    InventorySpecRequirement,
    ProductOntology,
)
from app.inventory.policy import (
    INVENTORY_POLICY_VERSION,
    inventory_family_abstain_triggers,
    inventory_question_family_contract,
)
from app.inventory.storage import InventoryMirrorStore, build_inventory_mirror_store
from app.retrieval import TextEmbedder, VectorRecord, VectorStore, build_embedder, build_vector_store

logger = logging.getLogger(__name__)

_UNDER_PRICE_PATTERN = re.compile(r"(?:under|below|less than)\s*\$?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_OVER_PRICE_PATTERN = re.compile(r"(?:over|above|more than)\s*\$?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_BUDGET_HINTS = ["budget", "affordable", "value", "cheap", "cheapest", "under", "below", "less than"]
_PREMIUM_HINTS = ["premium", "best", "top", "flagship", "high-end", "high end", "luxury", "most expensive"]
_AVAILABILITY_HINTS = ["in stock", "available now", "ready to sell", "available"]
_PREMIUM_ITEM_HINTS = ["premium", "pro", "max", "flagship", "elite", "ultra", "noise cancellation"]
_GREETING_PHRASES = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]
_HOW_ARE_YOU_PHRASES = ["how are you", "how are you doing", "how's it going", "how is it going"]
_THANKS_PHRASES = ["thanks", "thank you", "appreciate it", "much appreciated"]
_HELP_PHRASES = ["help", "what can you do", "how can you help", "can you help"]
_IDENTITY_PHRASES = ["who are you", "what are you", "what is your role", "what do you do"]
_CLOSING_PHRASES = ["bye", "goodbye", "see you", "talk later"]
_DETAIL_REQUEST_PHRASES = ["tell me about", "details on", "detail on", "more about", "what about"]
_FIRST_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_BOOLEAN_TRUE_VALUES = {"1", "true", "yes", "y", "on", "supported", "available", "included"}
_BOOLEAN_FALSE_VALUES = {"0", "false", "no", "n", "off", "none", "unsupported", "not supported"}
_EXACT_LOOKUP_PHRASES = [
    "do you have",
    "have any",
    "show me",
    "find me",
    "find",
    "looking for",
    "i need",
    "need a",
    "need an",
    "need some",
]
_AMBIGUOUS_REQUEST_PHRASES = [
    "recommend something",
    "show something",
    "show me something",
    "show products",
    "show me products",
    "show options",
    "show me options",
    "need something",
    "i need something",
    "what do you have",
    "what should i buy",
    "what should i sell",
]
_PRICE_OBJECTION_PHRASES = [
    "too expensive",
    "too pricey",
    "cheaper",
    "more affordable",
    "lower price",
    "over budget",
    "price is high",
]
_AVAILABILITY_OBJECTION_PHRASES = [
    "out of stock",
    "not available",
    "unavailable",
    "need it now",
    "need this now",
    "can't wait",
    "cannot wait",
    "need an in stock option",
    "need an available option",
]
_QUALITY_OBJECTION_PHRASES = [
    "better option",
    "something better",
    "more premium",
    "higher end",
    "higher-end",
    "better quality",
]
_CROSS_SELL_HINTS = [
    "add on",
    "add-on",
    "addon",
    "accessory",
    "accessories",
    "bundle",
    "cross sell",
    "cross-sell",
    "complete setup",
    "full setup",
    "go with",
    "pair with",
    "upsell bundle",
]
_GENERIC_RELATION_TAGS = {
    "active",
    "budget",
    "bluetooth",
    "office",
    "portable",
    "premium",
    "travel",
    "wireless",
}
_INVENTORY_REQUEST_HINTS = [
    "product",
    "products",
    "item",
    "items",
    "inventory",
    "stock",
    "price",
    "pricing",
    "recommend",
    "suggest",
    "find",
    "show",
    "list",
    "search",
    "category",
    "brand",
    "restock",
    "customer",
    "premium",
    "budget",
]
_HISTORICAL_DATA_HINTS = [
    "trend",
    "trends",
    "over time",
    "historical",
    "history",
    "this month",
    "last month",
    "this quarter",
    "last quarter",
    "week over week",
    "month over month",
    "forecast",
    "predict",
    "prediction",
    "demand",
]
_CROSS_SYSTEM_HINTS = [
    "sales",
    "orders",
    "order volume",
    "returns",
    "return rate",
    "profit",
    "margin",
    "revenue",
    "supplier",
    "suppliers",
    "vendor",
    "vendors",
    "customer segment",
    "customers",
    "campaign",
]
_WORKFLOW_ACTION_HINTS = [
    "what should we do",
    "what should i do",
    "action plan",
    "restock first",
    "reorder plan",
    "purchase order",
    "notify supplier",
    "prioritize",
    "next step",
    "next steps",
]
_ROOT_CAUSE_HINTS = ["why", "root cause", "what changed", "reason behind", "reason for", "cause"]
_MULTI_STEP_REASONING_HINTS = [
    "across categories",
    "across brands",
    "compare all",
    "portfolio",
    "entire inventory",
    "step by step",
    "step-by-step",
    "optimize",
]
_QUERY_STOPWORDS = {
    "a",
    "an",
    "about",
    "any",
    "are",
    "can",
    "could",
    "customer",
    "detail",
    "details",
    "did",
    "do",
    "does",
    "find",
    "for",
    "got",
    "had",
    "has",
    "have",
    "how",
    "i",
    "item",
    "items",
    "list",
    "look",
    "looking",
    "me",
    "more",
    "my",
    "need",
    "of",
    "one",
    "please",
    "product",
    "products",
    "recommend",
    "search",
    "show",
    "some",
    "suggest",
    "tell",
    "that",
    "the",
    "there",
    "this",
    "under",
    "want",
    "what",
    "would",
    "you",
    "your",
}


class InventoryServiceConfig(BaseModel):
    catalog_path: str = "data/inventory/catalog.jsonl"
    namespace: str = "inventory"
    default_top_k: int = Field(default=5, ge=1, le=50)
    max_top_k: int = Field(default=20, ge=1, le=100)
    search_candidate_multiplier: int = Field(default=4, ge=1, le=20)
    low_stock_threshold: int = Field(default=10, ge=0, le=10000)
    agentic_trace_dir: str = "results/traces/inventory_agentic"
    chat_trace_dir: str | None = None
    business_signal_path: str = "data/inventory/business_signals.jsonl"
    inventory_storage_backend: str = Field(default="jsonl")
    inventory_sqlite_path: str = "data/inventory/inventory_mirror.sqlite3"
    default_agentic_max_reasoning_steps: int = Field(default=4, ge=1, le=8)
    natural_answers_enabled: bool = False
    natural_answer_model_name: str | None = None
    natural_answer_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    natural_answer_max_tokens: int = Field(default=320, ge=64, le=4096)
    natural_answer_min_confidence: float = Field(default=0.45, ge=0.0, le=1.0)
    natural_answer_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    conversation_history_limit: int = Field(default=6, ge=0, le=20)


class InventoryAgenticTraceStore:
    def __init__(self, trace_dir: str | Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, object]] = {}

    def save(self, payload: dict[str, object]) -> str:
        trace_id = str(payload["trace_id"])
        self._cache[trace_id] = payload
        trace_path = self.trace_dir / f"{trace_id}.json"
        trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return trace_id

    def load(self, trace_id: str) -> dict[str, object] | None:
        if trace_id in self._cache:
            return self._cache[trace_id]
        trace_path = self.trace_dir / f"{trace_id}.json"
        if not trace_path.exists():
            return None
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        self._cache[trace_id] = payload
        return payload


class InventoryReply(BaseModel):
    answer: str
    recommended_product_ids: list[str] = Field(default_factory=list)
    cross_sell_product_ids: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    answer_plan: InventoryAnswerPlan = Field(default_factory=InventoryAnswerPlan)
    verification: InventoryAnswerVerification = Field(default_factory=InventoryAnswerVerification)


class InventoryNaturalAnswer(BaseModel):
    answer: str
    follow_up_question: str | None = None
    abstained: bool = False
    abstention_reason: str | None = None


class InventoryBusinessInsight(BaseModel):
    answer_addendum: str = ""
    reasoning_summary: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    selected_product_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class InventoryAgenticPlanStepSpec:
    action: str
    mode: str
    query_text: str | None = None
    filters: InventorySearchFilters | None = None


@dataclass(frozen=True)
class InventoryAgenticExecutionPlan:
    strategy: str
    search_steps: tuple[InventoryAgenticPlanStepSpec, ...]
    analysis_actions: tuple[str, ...] = ()
    abstain_on_missing_domains: bool = False


@dataclass(frozen=True)
class InventorySearchTraceDiagnostics:
    rejected_candidates: tuple[InventoryTraceCandidateDebug, ...] = ()


class InventoryService:
    def __init__(
        self,
        *,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        config: InventoryServiceConfig | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.config = config or InventoryServiceConfig()
        self.trace_store = InventoryAgenticTraceStore(self.config.agentic_trace_dir)
        self.chat_trace_store = InventoryAgenticTraceStore(self._chat_trace_dir())
        self.mirror_store: InventoryMirrorStore = build_inventory_mirror_store(
            backend=self.config.inventory_storage_backend,
            catalog_path=self.config.catalog_path,
            business_signal_path=self.config.business_signal_path,
            sqlite_path=self.config.inventory_sqlite_path,
        )
        self.product_ontology = ProductOntology()
        self.intent_classifier = InventoryIntentClassifier(self.product_ontology)
        self.preference_extractor = InventoryPreferenceExtractor(self.product_ontology)
        self.ecommerce_reranker = EcommerceReranker(self.product_ontology)
        self.decision_scorer = InventoryDecisionScorer(self.product_ontology)
        self.evidence_contract_builder = InventoryEvidenceContractBuilder(self.product_ontology)
        self.answer_planner = InventoryAnswerPlanner(self.product_ontology)
        self.final_answer_verifier = InventoryFinalAnswerVerifier(self.product_ontology)
        self.memory_resolver = InventoryMemoryResolver(self.product_ontology)

    def _chat_trace_dir(self) -> str:
        if self.config.chat_trace_dir:
            return self.config.chat_trace_dir
        return str(Path(self.config.agentic_trace_dir).with_name("inventory_chat"))

    @staticmethod
    def _inventory_storage_path(storage_description: dict[str, str]) -> str | None:
        return (
            storage_description.get("sqlite_path")
            or storage_description.get("catalog_path")
            or storage_description.get("business_signal_path")
        )

    def status(self) -> InventoryStatusResponse:
        items = self._load_catalog()
        rag_enabled_count = sum(1 for item in items.values() if item.include_in_rag)
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
        storage_description = self.mirror_store.describe()
        return InventoryStatusResponse(
            status="success",
            ready=True,
            total_items=len(items),
            rag_enabled_items=rag_enabled_count,
            vector_record_count=vector_stats.total_vector_count or 0,
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
            vector_backend=self.vector_store.provider.value,
            vector_store_path=getattr(self.vector_store.config, "local_store_path", None),
            storage_backend=storage_description.get("backend"),
            storage_path=self._inventory_storage_path(storage_description),
        )

    def production_status(self) -> InventoryProductionStatusResponse:
        storage_description = self.mirror_store.describe()
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
        issues: list[InventorySyncIssue] = []
        recommendations: list[str] = []

        storage_backend = storage_description.get("backend", "unknown")
        if storage_backend == "jsonl":
            issues.append(
                InventorySyncIssue(
                    severity="warning",
                    code="jsonl_inventory_storage",
                    message="Inventory mirror is using JSONL storage, which is suitable for development but weak for production concurrency and durability.",
                )
            )
            recommendations.append("Set INVENTORY_STORAGE_BACKEND=sqlite for a durable local mirror or move the mirror into PostgreSQL.")
        elif storage_backend == "sqlite":
            recommendations.append("SQLite mirror storage is enabled. For multi-instance production, prefer PostgreSQL or another shared durable store.")
        else:
            issues.append(
                InventorySyncIssue(
                    severity="error",
                    code="unknown_inventory_storage",
                    message=f"Unknown inventory storage backend: {storage_backend}.",
                )
            )

        if self.vector_store.provider.value == "local":
            issues.append(
                InventorySyncIssue(
                    severity="warning",
                    code="local_vector_backend",
                    message="Vector retrieval is using a local JSONL vector store. Use Milvus or Pinecone for production-grade vector search.",
                )
            )
            recommendations.append("Set VECTOR_DB=milvus or VECTOR_DB=pinecone and configure the matching collection/index settings.")
        else:
            recommendations.append(f"{self.vector_store.provider.value} vector backend is configured.")

        has_error = any(issue.severity == "error" for issue in issues)
        production_ready = not has_error and storage_backend != "jsonl" and self.vector_store.provider.value != "local"
        return InventoryProductionStatusResponse(
            status="success",
            production_ready=production_ready,
            storage_backend=storage_backend,
            storage_path=self._inventory_storage_path(storage_description),
            vector_backend=self.vector_store.provider.value,
            vector_index_name=vector_stats.index_name,
            vector_namespace=vector_stats.namespace,
            vector_record_count=vector_stats.total_vector_count,
            issues=issues,
            recommendations=recommendations,
        )

    def agentic_status(self) -> InventoryAgenticStatusResponse:
        items = self._load_catalog()
        rag_enabled_count = sum(1 for item in items.values() if item.include_in_rag)
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
        return InventoryAgenticStatusResponse(
            status="success",
            ready=True,
            total_items=len(items),
            rag_enabled_items=rag_enabled_count,
            vector_record_count=vector_stats.total_vector_count or 0,
            namespace=self.config.namespace,
            trace_dir=str(Path(self.config.agentic_trace_dir)),
            vector_backend=self.vector_store.provider.value,
            vector_store_path=getattr(self.vector_store.config, "local_store_path", None),
        )

    def sync_status(self) -> InventorySyncStatusResponse:
        catalog = self._load_catalog()
        rag_enabled_ids = {product_id for product_id, item in catalog.items() if item.include_in_rag}
        vector_ids = self._vector_record_ids()
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
        invalid_catalog_issues = self._catalog_quality_issues(catalog)
        issues: list[InventorySyncIssue] = []

        if vector_ids is None:
            issues.append(
                InventorySyncIssue(
                    severity="warning",
                    code="vector_ids_unavailable",
                    message="Vector backend does not expose record IDs; only vector counts can be checked.",
                )
            )
            missing_vector_ids: list[str] = []
            stale_vector_ids: list[str] = []
            vector_synced: bool | None = None
        else:
            missing_vector_ids = sorted(rag_enabled_ids - vector_ids)
            stale_vector_ids = sorted(vector_ids - rag_enabled_ids)
            vector_synced = not missing_vector_ids and not stale_vector_ids
            issues.extend(
                InventorySyncIssue(
                    severity="error",
                    code="missing_vector",
                    product_id=product_id,
                    message=f"RAG-enabled product {product_id} is missing from the vector index.",
                )
                for product_id in missing_vector_ids
            )
            issues.extend(
                InventorySyncIssue(
                    severity="warning",
                    code="stale_vector",
                    product_id=product_id,
                    message=f"Vector index contains stale product {product_id} that is not RAG-enabled in the catalog.",
                )
                for product_id in stale_vector_ids
            )

        issues.extend(invalid_catalog_issues)
        has_error = any(issue.severity == "error" for issue in issues)
        return InventorySyncStatusResponse(
            status="success",
            ready=not has_error,
            catalog_count=len(catalog),
            rag_enabled_count=len(rag_enabled_ids),
            vector_record_count=vector_stats.total_vector_count or 0,
            vector_ids_available=vector_ids is not None,
            vector_synced=vector_synced,
            missing_vector_ids=missing_vector_ids,
            stale_vector_ids=stale_vector_ids,
            invalid_catalog_product_ids=sorted({issue.product_id for issue in invalid_catalog_issues if issue.product_id}),
            issues=issues,
        )

    def sync_validate(self, request: InventorySyncValidateRequest) -> InventorySyncValidateResponse:
        catalog = self._load_catalog()
        source_items_by_id = {item.product_id: item for item in request.source_items}
        source_ids = set(request.source_product_ids).union(source_items_by_id)
        catalog_ids = set(catalog)
        rag_enabled_ids = {product_id for product_id, item in catalog.items() if item.include_in_rag}
        vector_ids = self._vector_record_ids()
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
        invalid_catalog_issues = self._catalog_quality_issues(catalog)
        issues: list[InventorySyncIssue] = []

        missing_in_catalog = sorted(source_ids - catalog_ids) if source_ids else []
        extra_in_catalog = sorted(catalog_ids - source_ids) if source_ids else []
        stale_catalog_product_ids = self._stale_catalog_product_ids(
            catalog=catalog,
            source_items_by_id=source_items_by_id,
        )

        issues.extend(
            InventorySyncIssue(
                severity="error",
                code="missing_in_catalog",
                product_id=product_id,
                message=f"Source product {product_id} is missing from the RAG catalog mirror.",
            )
            for product_id in missing_in_catalog
        )
        issues.extend(
            InventorySyncIssue(
                severity="warning",
                code="extra_in_catalog",
                product_id=product_id,
                message=f"Catalog mirror contains product {product_id} that was not present in the source product list.",
            )
            for product_id in extra_in_catalog
        )
        issues.extend(
            InventorySyncIssue(
                severity="error",
                code="stale_catalog_item",
                product_id=product_id,
                message=f"Catalog mirror product {product_id} differs from the provided source item.",
            )
            for product_id in stale_catalog_product_ids
        )

        if vector_ids is None:
            missing_vector_ids: list[str] = []
            stale_vector_ids: list[str] = []
            issues.append(
                InventorySyncIssue(
                    severity="warning",
                    code="vector_ids_unavailable",
                    message="Vector backend does not expose record IDs; vector drift was not fully validated.",
                )
            )
        else:
            expected_vector_ids = (
                {
                    product_id
                    for product_id in source_ids
                    if product_id in catalog and catalog[product_id].include_in_rag
                }
                if source_ids
                else rag_enabled_ids
            )
            missing_vector_ids = sorted(expected_vector_ids - vector_ids)
            stale_vector_ids = sorted(vector_ids - rag_enabled_ids)
            issues.extend(
                InventorySyncIssue(
                    severity="error",
                    code="missing_vector",
                    product_id=product_id,
                    message=f"Expected RAG vector for product {product_id}, but it was not found.",
                )
                for product_id in missing_vector_ids
            )
            issues.extend(
                InventorySyncIssue(
                    severity="warning",
                    code="stale_vector",
                    product_id=product_id,
                    message=f"Vector index contains stale product {product_id}.",
                )
                for product_id in stale_vector_ids
            )

        issues.extend(invalid_catalog_issues)
        has_error = any(issue.severity == "error" for issue in issues)
        return InventorySyncValidateResponse(
            status="success",
            valid=not has_error,
            source_count=len(source_ids),
            catalog_count=len(catalog),
            rag_enabled_count=len(rag_enabled_ids),
            vector_record_count=vector_stats.total_vector_count or 0,
            vector_ids_available=vector_ids is not None,
            missing_in_catalog=missing_in_catalog,
            extra_in_catalog=extra_in_catalog,
            stale_catalog_product_ids=stale_catalog_product_ids,
            missing_vector_ids=missing_vector_ids,
            stale_vector_ids=stale_vector_ids,
            invalid_catalog_product_ids=sorted({issue.product_id for issue in invalid_catalog_issues if issue.product_id}),
            issues=issues,
        )

    def sync_rebuild(self) -> InventorySyncRebuildResponse:
        catalog = self._load_catalog()
        rag_enabled_items = [item for item in catalog.values() if item.include_in_rag]
        rag_enabled_ids = {item.product_id for item in rag_enabled_items}
        vector_ids = self._vector_record_ids()

        deleted_vector_ids = {item.product_id for item in catalog.values() if not item.include_in_rag}
        if vector_ids is not None:
            deleted_vector_ids.update(vector_ids - rag_enabled_ids)

        records_to_upsert = [self._build_vector_record(item) for item in rag_enabled_items]
        deleted_vector_id_list = sorted(deleted_vector_ids)
        if deleted_vector_id_list:
            self.vector_store.delete(deleted_vector_id_list, namespace=self.config.namespace)
        if records_to_upsert:
            self.vector_store.upsert(records_to_upsert, namespace=self.config.namespace)

        rebuilt_status = self.sync_status()
        return InventorySyncRebuildResponse(
            status="success",
            ready=rebuilt_status.ready,
            rebuilt_count=len(records_to_upsert),
            deleted_vector_count=len(deleted_vector_id_list),
            catalog_count=rebuilt_status.catalog_count,
            rag_enabled_count=rebuilt_status.rag_enabled_count,
            vector_record_count=rebuilt_status.vector_record_count,
            vector_ids_available=rebuilt_status.vector_ids_available,
            vector_synced=rebuilt_status.vector_synced,
            missing_vector_ids=rebuilt_status.missing_vector_ids,
            stale_vector_ids=rebuilt_status.stale_vector_ids,
            invalid_catalog_product_ids=rebuilt_status.invalid_catalog_product_ids,
            issues=rebuilt_status.issues,
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
        )

    def business_status(self) -> InventoryBusinessStatusResponse:
        signals = self._load_business_signals()
        return InventoryBusinessStatusResponse(
            status="success",
            ready=bool(signals),
            total_signals=len(signals),
            product_count=len(signals),
            domains_available=self._business_domains_available(signals),
            latest_updated_at=self._latest_business_signal_update(signals),
            business_signal_path=str(self._business_signal_path()),
        )

    def list_business_signals(self, product_id: str | None = None) -> InventoryBusinessSignalsResponse:
        signals = self._load_business_signals()
        items = sorted(signals.values(), key=self._business_signal_sort_key, reverse=True)
        if product_id:
            items = [signal for signal in items if signal.product_id == product_id]
        return InventoryBusinessSignalsResponse(
            status="success",
            total_signals=len(items),
            signals=items,
        )

    def upsert_business_signals(
        self,
        signals: list[InventoryBusinessSignalRecord],
    ) -> InventoryBusinessSignalsUpsertResponse:
        existing_signals = self._load_business_signals()
        for signal in signals:
            existing_signals[signal.product_id] = signal
        self._persist_business_signals(existing_signals)
        return InventoryBusinessSignalsUpsertResponse(
            status="success",
            upserted_count=len(signals),
            total_signals=len(existing_signals),
            product_count=len(existing_signals),
            business_signal_path=str(self._business_signal_path()),
        )

    def delete_business_signals(self, product_ids: list[str]) -> InventoryBusinessSignalsDeleteResponse:
        existing_signals = self._load_business_signals()
        deleted_ids = [product_id for product_id in product_ids if product_id in existing_signals]
        for product_id in deleted_ids:
            existing_signals.pop(product_id, None)
        self._persist_business_signals(existing_signals)
        return InventoryBusinessSignalsDeleteResponse(
            status="success",
            deleted_count=len(deleted_ids),
            total_signals=len(existing_signals),
            product_count=len(existing_signals),
            business_signal_path=str(self._business_signal_path()),
        )

    def list_items(self) -> InventoryCatalogResponse:
        items = sorted(self._load_catalog().values(), key=self._catalog_sort_key, reverse=True)
        return InventoryCatalogResponse(status="success", total_items=len(items), items=items)

    def get_item(self, product_id: str) -> InventoryItemRecord | None:
        return self._load_catalog().get(product_id)

    def upsert_items(self, items: list[InventoryItemRecord]) -> InventoryUpsertResponse:
        catalog = self._load_catalog()
        rag_enabled_count = 0
        records_to_upsert: list[VectorRecord] = []
        record_ids_to_delete: list[str] = []

        for item in items:
            catalog[item.product_id] = item
            if item.include_in_rag:
                rag_enabled_count += 1
                records_to_upsert.append(self._build_vector_record(item))
            else:
                record_ids_to_delete.append(item.product_id)

        self._persist_catalog(catalog)
        if record_ids_to_delete:
            self.vector_store.delete(record_ids_to_delete, namespace=self.config.namespace)
        if records_to_upsert:
            self.vector_store.upsert(records_to_upsert, namespace=self.config.namespace)

        return InventoryUpsertResponse(
            status="success",
            upserted_count=len(items),
            rag_enabled_count=rag_enabled_count,
            total_items=len(catalog),
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
        )

    def delete_items(self, product_ids: list[str]) -> InventoryDeleteResponse:
        catalog = self._load_catalog()
        deleted_ids = [product_id for product_id in product_ids if product_id in catalog]
        for product_id in deleted_ids:
            catalog.pop(product_id, None)
        self._persist_catalog(catalog)
        if deleted_ids:
            self.vector_store.delete(deleted_ids, namespace=self.config.namespace)
        return InventoryDeleteResponse(
            status="success",
            deleted_count=len(deleted_ids),
            total_items=len(catalog),
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
        )

    def search(self, request: InventorySearchRequest) -> InventorySearchResponse:
        response, _ = self._search_with_diagnostics(request)
        return response

    def _search_with_diagnostics(
        self,
        request: InventorySearchRequest,
    ) -> tuple[InventorySearchResponse, dict[str, int]]:
        response, retrieval_stage_counts, _trace_diagnostics = self._search_with_trace_diagnostics(request)
        return response, retrieval_stage_counts

    def _search_with_trace_diagnostics(
        self,
        request: InventorySearchRequest,
    ) -> tuple[InventorySearchResponse, dict[str, int], InventorySearchTraceDiagnostics]:
        catalog = self._load_catalog()
        top_k = min(request.top_k, self.config.max_top_k)
        query_text = (request.query_text or "").strip()
        if query_text:
            hits, retrieval_stage_counts, trace_diagnostics = self._semantic_search(
                query_text=query_text,
                top_k=top_k,
                filters=request.filters,
                catalog=catalog,
            )
        else:
            hits, retrieval_stage_counts, trace_diagnostics = self._browse_items(
                top_k=top_k,
                filters=request.filters,
                catalog=catalog,
            )
        response = InventorySearchResponse(
            status="success",
            query_text=query_text or None,
            total_hits=len(hits),
            applied_filters=request.filters,
            hits=hits,
        )
        retrieval_stage_counts["search_requests"] = retrieval_stage_counts.get("search_requests", 0) + 1
        return response, retrieval_stage_counts, trace_diagnostics

    def ask(self, request: InventoryAskRequest) -> InventoryAskResponse:
        started_at = perf_counter()
        trace_id = str(uuid4())
        memory_resolution = InventoryMemoryResolution()
        conversational_reply = self._build_conversational_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
        )
        if conversational_reply is not None:
            reply, confidence_score = conversational_reply
            reply = self._enrich_reply_plan(
                reply=reply,
                question=request.question,
                filters=request.filters,
                hits=[],
                strategy="conversation",
            )
            response = InventoryAskResponse(
                status="success",
                question=request.question,
                answer=reply.answer,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                answer_engine="deterministic",
                confidence_score=confidence_score,
                trace_id=trace_id,
                abstained=False,
                abstention_reason=None,
                total_hits=0,
                applied_filters=request.filters.model_copy(deep=True),
                hits=[],
                recommended_product_ids=reply.recommended_product_ids,
                cross_sell_product_ids=reply.cross_sell_product_ids,
                follow_up_question=reply.follow_up_question,
                answer_plan=reply.answer_plan,
                verification=reply.verification,
                memory_resolution=memory_resolution,
            )
            self._save_inventory_chat_trace(
                trace_id=trace_id,
                response=response,
                execution_path="inventory_ask",
                started_at=started_at,
                requested_answer_engine=request.answer_engine,
                retrieved_hits=[],
                reranked_hits=[],
            )
            return response

        resolved_memory = self.memory_resolver.resolve(
            question=request.question,
            filters=request.filters.model_copy(deep=True),
            focused_product_ids=request.focused_product_ids,
            active_filters=request.active_filters,
            last_answer_plan=request.last_answer_plan,
        )
        memory_resolution = resolved_memory.resolution
        effective_filters = self._merge_question_filters(
            question=request.question,
            filters=resolved_memory.filters,
            low_stock_threshold=request.low_stock_threshold,
        )
        route_signals = self._build_route_signals(
            question=request.question,
            filters=effective_filters,
        )
        search_response, retrieval_stage_counts, search_trace_diagnostics = self._search_with_trace_diagnostics(
            InventorySearchRequest(
                query_text=request.question,
                top_k=request.top_k,
                filters=effective_filters,
            )
        )
        ordered_hits = self._order_hits_for_assistant(
            question=request.question,
            hits=search_response.hits,
            filters=effective_filters,
            low_stock_threshold=request.low_stock_threshold,
            assistant_mode=request.assistant_mode,
        )
        guarded_no_match = self._build_no_match_or_abstain_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            filters=effective_filters,
            hits=ordered_hits,
            route_signals=route_signals,
        )
        if guarded_no_match is not None:
            reply, response_hits, confidence_score, abstention_reason = guarded_no_match
            finalize_hits: list[InventorySearchHit] = []
            response_total_hits = 0
        else:
            reply = self._build_answer(
                question=request.question,
                hits=ordered_hits,
                filters=effective_filters,
                low_stock_threshold=request.low_stock_threshold,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
            )
            response_hits = ordered_hits
            finalize_hits = ordered_hits
            response_total_hits = search_response.total_hits
            confidence_score = self._estimate_confidence(ordered_hits)
            abstention_reason = self._build_abstention_reason(
                question=request.question,
                hits=ordered_hits,
            )
        ask_trace_selected_hits = ordered_hits[: min(3, len(ordered_hits))]
        rejected_count = len(search_trace_diagnostics.rejected_candidates)
        if search_response.total_hits == 0:
            ask_trace_observation = "Direct inventory search found no supporting catalog hits."
        else:
            ask_trace_observation = (
                f"Direct inventory search found {search_response.total_hits} catalog hit(s) led by "
                f"{self._natural_join(hit.name for hit in ask_trace_selected_hits)}."
            )
            if rejected_count:
                ask_trace_observation += f" Rejected {rejected_count} weaker or mismatched candidate(s) during filtering and reranking."
        retrieval_steps = [
            self._build_trace_step(
                step_number=1,
                action="inventory_search",
                query_text=request.question,
                applied_filters=effective_filters,
                total_hits=search_response.total_hits,
                selected_hits=ask_trace_selected_hits,
                rejected_candidates=list(search_trace_diagnostics.rejected_candidates[:5]),
                observation=ask_trace_observation,
                retrieval_stage_counts=retrieval_stage_counts,
            )
        ]
        reply, answer_engine, abstained, abstention_reason, fallback_reason = self._finalize_inventory_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            requested_answer_engine=request.answer_engine,
            confidence_score=confidence_score,
            hits=finalize_hits,
            base_reply=reply,
            conversation_history=request.conversation_history,
            conversation_summary=request.conversation_summary,
            abstention_reason=abstention_reason,
            execution_path="inventory_ask",
            memory_resolution=memory_resolution,
        )
        response = InventoryAskResponse(
            status="success",
            question=request.question,
            answer=reply.answer,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            answer_engine=answer_engine,
            confidence_score=confidence_score,
            trace_id=trace_id,
            abstained=abstained,
            abstention_reason=abstention_reason,
            total_hits=response_total_hits,
            applied_filters=effective_filters,
            hits=response_hits,
            recommended_product_ids=reply.recommended_product_ids,
            cross_sell_product_ids=reply.cross_sell_product_ids,
            follow_up_question=reply.follow_up_question,
            answer_plan=reply.answer_plan,
            verification=reply.verification,
            memory_resolution=memory_resolution,
        )
        self._save_inventory_chat_trace(
            trace_id=trace_id,
            response=response,
            execution_path="inventory_ask",
            started_at=started_at,
            requested_answer_engine=request.answer_engine,
            retrieved_hits=search_response.hits,
            reranked_hits=ordered_hits,
            fallback_reason_override=fallback_reason,
            retrieval_stage_counts=retrieval_stage_counts,
            retrieval_steps=retrieval_steps,
        )
        return response

    def route(self, request: InventoryRouteRequest) -> InventoryRouteResponse:
        signals = self._build_route_signals(
            question=request.question,
            filters=request.filters,
        )
        family_contract = inventory_question_family_contract(signals.question_family)
        required_data_domains = self._required_data_domains_for_route(
            question=request.question,
            signals=signals,
        )
        available_data_domains = set(request.available_data_domains)
        missing_data_domains = [domain for domain in required_data_domains if domain not in available_data_domains]
        recommended_path, decision_confidence, decision_factors = self._select_route(
            request=request,
            signals=signals,
        )
        reason_summary = self._build_route_summary(
            recommended_path=recommended_path,
            signals=signals,
            missing_data_domains=missing_data_domains,
            prefer_fast_response=request.prefer_fast_response,
        )
        return InventoryRouteResponse(
            status="success",
            question=request.question,
            policy_version=INVENTORY_POLICY_VERSION,
            recommended_path=recommended_path,
            fallback_path="normal_rag",
            decision_confidence=decision_confidence,
            reason_summary=reason_summary,
            decision_factors=decision_factors,
            required_data_domains=required_data_domains,
            missing_data_domains=missing_data_domains,
            signals=signals,
            family_contract=family_contract,
            applicable_hard_abstain_triggers=inventory_family_abstain_triggers(signals.question_family),
            normal_rag_contract=self._build_normal_rag_contract(request=request),
            agentic_contract=self._build_agentic_contract(
                request=request,
                required_data_domains=required_data_domains,
                missing_data_domains=missing_data_domains,
            ),
        )

    def agentic_ask(self, request: InventoryAgenticRequest) -> InventoryAgenticResponse:
        started_at = perf_counter()
        trace_id = str(uuid4())
        reasoning_summary: list[str] = []
        missing_facts: list[str] = []
        conversational_reply = self._build_conversational_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
        )
        if conversational_reply is not None:
            reply, confidence_score = conversational_reply
            reply = self._enrich_reply_plan(
                reply=reply,
                question=request.question,
                filters=request.filters,
                hits=[],
                strategy="conversation",
            )
            reasoning_summary.append("Handled as conversational small talk; retrieval and agentic tool use were skipped.")
            response = InventoryAgenticResponse(
                status="success",
                question=request.question,
                answer=reply.answer,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                answer_engine="deterministic",
                execution_path="inventory_agentic_conversation",
                confidence_score=confidence_score,
                abstained=False,
                abstention_reason=None,
                trace_id=trace_id,
                reasoning_summary=reasoning_summary,
                missing_facts=[],
                retrieval_steps_used=0,
                total_hits=0,
                applied_filters=request.filters.model_copy(deep=True),
                hits=[],
                recommended_product_ids=reply.recommended_product_ids,
                cross_sell_product_ids=reply.cross_sell_product_ids,
                follow_up_question=reply.follow_up_question,
                answer_plan=reply.answer_plan,
                verification=reply.verification,
                memory_resolution=InventoryMemoryResolution(),
            )
            trace_payload = {
                "trace_id": trace_id,
                "question": request.question,
                "assistant_mode": request.assistant_mode,
                "reply_style": request.reply_style,
                "execution_path": "inventory_agentic_conversation",
                "route_decision": self._build_route_trace_metadata(
                    question=request.question,
                    filters=request.filters,
                    execution_path="inventory_agentic_conversation",
                ),
                "retrieval_stage_counts": {},
                "reasoning_summary": reasoning_summary,
                "missing_facts": [],
                "retrieval_steps": [],
                "final_answer": response.answer,
                "confidence_score": confidence_score,
            }
            self.trace_store.save(trace_payload)
            self._save_inventory_chat_trace(
                trace_id=trace_id,
                response=response,
                execution_path="inventory_agentic_conversation",
                started_at=started_at,
                requested_answer_engine=request.answer_engine,
                retrieved_hits=[],
                reranked_hits=[],
                retrieval_stage_counts={},
                reasoning_summary=reasoning_summary,
                missing_facts=[],
                retrieval_steps=[],
                route_decision_override=self._build_route_trace_metadata(
                    question=request.question,
                    filters=request.filters,
                    execution_path="inventory_agentic_conversation",
                ),
            )
            return response

        business_signals = self._load_business_signals()
        business_domains = self._business_domains_available(business_signals)
        available_data_domains = sorted(set(request.available_data_domains).union(business_domains))
        resolved_memory = self.memory_resolver.resolve(
            question=request.question,
            filters=request.filters.model_copy(deep=True),
            focused_product_ids=request.focused_product_ids,
            active_filters=request.active_filters,
            last_answer_plan=request.last_answer_plan,
        )
        if resolved_memory.resolution.used_memory and resolved_memory.resolution.reason:
            reasoning_summary.append(resolved_memory.resolution.reason)
        route_request = InventoryRouteRequest(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            filters=resolved_memory.filters.model_copy(deep=True),
            audience=request.audience,
            prefer_fast_response=False,
            allow_agentic=True,
            available_data_domains=available_data_domains,
        )
        route_response = self.route(route_request)
        reasoning_summary.append(route_response.reason_summary)
        reasoning_summary.extend(route_response.decision_factors)
        if route_response.missing_data_domains:
            missing_facts.extend(
                [f"Missing data domain: {domain}" for domain in route_response.missing_data_domains]
            )

        effective_filters = self._merge_question_filters(
            question=request.question,
            filters=resolved_memory.filters.model_copy(deep=True),
            low_stock_threshold=request.low_stock_threshold,
        )
        guarded_no_match = self._build_no_match_or_abstain_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            filters=effective_filters,
            hits=[],
            route_signals=route_response.signals,
        )
        if guarded_no_match is not None:
            final_reply, safe_hits, confidence_score, abstention_reason = guarded_no_match
            reasoning_summary.append(
                "Short-circuited before agentic retrieval because the question was classified as a clarification or abstain case."
            )
            final_reply, answer_engine, abstained, abstention_reason, fallback_reason = self._finalize_inventory_reply(
                question=request.question,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                requested_answer_engine=request.answer_engine,
                confidence_score=confidence_score,
                hits=safe_hits,
                base_reply=final_reply,
                conversation_history=request.conversation_history,
                conversation_summary=request.conversation_summary,
                abstention_reason=abstention_reason,
                execution_path="inventory_agentic",
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                memory_resolution=resolved_memory.resolution,
            )
            response = InventoryAgenticResponse(
                status="success",
                question=request.question,
                answer=final_reply.answer,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                answer_engine=answer_engine,
                execution_path="inventory_agentic_no_match_or_abstain",
                confidence_score=confidence_score,
                abstained=abstained,
                abstention_reason=abstention_reason,
                trace_id=trace_id,
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                retrieval_steps_used=0,
                total_hits=0,
                applied_filters=effective_filters,
                hits=safe_hits,
                recommended_product_ids=final_reply.recommended_product_ids,
                cross_sell_product_ids=final_reply.cross_sell_product_ids,
                follow_up_question=final_reply.follow_up_question,
                answer_plan=final_reply.answer_plan,
                verification=final_reply.verification,
                memory_resolution=resolved_memory.resolution,
            )
            trace_payload = {
                "trace_id": trace_id,
                "question": request.question,
                "assistant_mode": request.assistant_mode,
                "reply_style": request.reply_style,
                "execution_path": "inventory_agentic_no_match_or_abstain",
                "route_decision": self._serialize_route_response(route_response),
                "retrieval_stage_counts": {},
                "reasoning_summary": reasoning_summary,
                "missing_facts": missing_facts,
                "retrieval_steps": [],
                "final_answer": final_reply.answer,
                "confidence_score": confidence_score,
            }
            self.trace_store.save(trace_payload)
            self._save_inventory_chat_trace(
                trace_id=trace_id,
                response=response,
                execution_path="inventory_agentic_no_match_or_abstain",
                started_at=started_at,
                requested_answer_engine=request.answer_engine,
                retrieved_hits=[],
                reranked_hits=[],
                retrieval_stage_counts={},
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                retrieval_steps=[],
                fallback_reason_override=fallback_reason,
                route_decision_override=self._serialize_route_response(route_response),
            )
            return response

        execution_plan = self._build_agentic_execution_plan(
            question=request.question,
            filters=effective_filters,
            low_stock_threshold=request.low_stock_threshold,
            max_reasoning_steps=request.max_reasoning_steps or self.config.default_agentic_max_reasoning_steps,
            route_response=route_response,
        )
        business_intent = self._agentic_business_intent(
            question=request.question,
            strategy=execution_plan.strategy,
        )
        if execution_plan.abstain_on_missing_domains and route_response.missing_data_domains:
            missing_domain_reply = self._build_missing_domain_abstain_reply(
                question=request.question,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                filters=effective_filters,
                missing_data_domains=route_response.missing_data_domains,
            )
            reasoning_summary.append(
                "Abstained before retrieval because the workflow requires data domains that are not available to this agent."
            )
            final_reply, answer_engine, abstained, abstention_reason, fallback_reason = self._finalize_inventory_reply(
                question=request.question,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                requested_answer_engine=request.answer_engine,
                confidence_score=0.18,
                hits=[],
                base_reply=missing_domain_reply,
                conversation_history=request.conversation_history,
                conversation_summary=request.conversation_summary,
                abstention_reason=missing_domain_reply.answer_plan.abstention_reason,
                execution_path="inventory_agentic_missing_domain_abstain",
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                memory_resolution=resolved_memory.resolution,
            )
            response = InventoryAgenticResponse(
                status="success",
                question=request.question,
                answer=final_reply.answer,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                answer_engine=answer_engine,
                execution_path="inventory_agentic_missing_domain_abstain",
                confidence_score=0.18,
                abstained=abstained,
                abstention_reason=abstention_reason,
                trace_id=trace_id,
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                retrieval_steps_used=0,
                total_hits=0,
                applied_filters=effective_filters,
                hits=[],
                recommended_product_ids=final_reply.recommended_product_ids,
                cross_sell_product_ids=final_reply.cross_sell_product_ids,
                follow_up_question=final_reply.follow_up_question,
                answer_plan=final_reply.answer_plan,
                verification=final_reply.verification,
                memory_resolution=resolved_memory.resolution,
            )
            trace_payload = {
                "trace_id": trace_id,
                "question": request.question,
                "assistant_mode": request.assistant_mode,
                "reply_style": request.reply_style,
                "execution_path": "inventory_agentic_missing_domain_abstain",
                "route_decision": self._serialize_route_response(route_response),
                "retrieval_stage_counts": {},
                "reasoning_summary": reasoning_summary,
                "missing_facts": missing_facts,
                "retrieval_steps": [],
                "final_answer": final_reply.answer,
                "confidence_score": 0.18,
            }
            self.trace_store.save(trace_payload)
            self._save_inventory_chat_trace(
                trace_id=trace_id,
                response=response,
                execution_path="inventory_agentic_missing_domain_abstain",
                started_at=started_at,
                requested_answer_engine=request.answer_engine,
                retrieved_hits=[],
                reranked_hits=[],
                retrieval_stage_counts={},
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                retrieval_steps=[],
                fallback_reason_override=fallback_reason,
                route_decision_override=self._serialize_route_response(route_response),
            )
            return response

        retrieval_steps: list[InventoryAgenticStep] = []
        aggregated_retrieval_stage_counts: dict[str, int] = {}
        aggregated_hits: list[InventorySearchHit] = []
        seen_hits: set[str] = set()
        for step_number, plan_step in enumerate(execution_plan.search_steps, start=1):
            if plan_step.mode == "bundle_add_on_search":
                primary = self._agentic_primary_hit_for_bundle(
                    question=request.question,
                    hits=aggregated_hits,
                    filters=effective_filters,
                )
                if primary is None:
                    retrieval_steps.append(
                        self._build_trace_step(
                            step_number=step_number,
                            action=plan_step.action,
                            query_text=plan_step.query_text,
                            applied_filters=(plan_step.filters or effective_filters).model_copy(deep=True),
                            total_hits=0,
                            selected_hits=[],
                            observation=f"Step {step_number} skipped because no stable primary candidate was available yet.",
                        )
                    )
                    reasoning_summary.append(
                        f"Step {step_number} skipped because no stable primary candidate was available yet."
                    )
                    continue

                bundle_filters = (plan_step.filters or effective_filters).model_copy(deep=True)
                bundle_hits = self._bundle_add_on_hits(
                    primary=primary,
                    filters=bundle_filters,
                    top_k=min(max(request.top_k, 5), self.config.max_top_k),
                )
                bundle_stage_counts = {"deterministic_bundle_catalog_scan": len(bundle_hits)}
                aggregated_retrieval_stage_counts = self._merge_retrieval_stage_counts(
                    aggregated_retrieval_stage_counts,
                    bundle_stage_counts,
                )
                selected_hits = bundle_hits[: min(3, len(bundle_hits))]
                for hit in bundle_hits:
                    if hit.product_id in seen_hits:
                        continue
                    seen_hits.add(hit.product_id)
                    aggregated_hits.append(hit)
                observation = self._build_agentic_step_observation(
                    step_number=step_number,
                    request=InventorySearchRequest(
                        query_text=self._bundle_add_on_query(primary=primary, question=request.question),
                        top_k=min(max(request.top_k, 5), self.config.max_top_k),
                        filters=bundle_filters,
                    ),
                    route_response=route_response,
                    total_hits=len(bundle_hits),
                    selected_hits=selected_hits,
                    action=plan_step.action,
                )
                retrieval_steps.append(
                    self._build_trace_step(
                        step_number=step_number,
                        action=plan_step.action,
                        query_text=self._bundle_add_on_query(primary=primary, question=request.question),
                        applied_filters=bundle_filters,
                        total_hits=len(bundle_hits),
                        selected_hits=selected_hits,
                        rejected_candidates=self._trace_ranked_out_candidates(
                            hits=bundle_hits[len(selected_hits):],
                            reason="Not selected for the compatible add-on shortlist because stronger compatible add-ons ranked higher.",
                        ),
                        observation=observation,
                        retrieval_stage_counts=bundle_stage_counts,
                    )
                )
                reasoning_summary.append(observation)
                continue

            if plan_step.mode == "business":
                business_hits = self._business_candidate_hits(
                    question=request.question,
                    filters=(plan_step.filters or effective_filters).model_copy(deep=True),
                    business_signals=business_signals,
                    top_k=min(max(request.top_k, 5), self.config.max_top_k),
                )
                selected_hits = business_hits[: min(3, len(business_hits))]
                for hit in business_hits:
                    existing_index = next(
                        (index for index, existing_hit in enumerate(aggregated_hits) if existing_hit.product_id == hit.product_id),
                        None,
                    )
                    if existing_index is not None:
                        aggregated_hits[existing_index] = hit
                        continue
                    seen_hits.add(hit.product_id)
                    aggregated_hits.append(hit)
                business_observation = self._build_business_signal_observation(
                    business_intent=business_intent or "business",
                    selected_hits=selected_hits,
                    business_signals=business_signals,
                )
                retrieval_steps.append(
                    self._build_trace_step(
                        step_number=step_number,
                        action=plan_step.action,
                        query_text=plan_step.query_text,
                        applied_filters=(plan_step.filters or effective_filters).model_copy(deep=True),
                        total_hits=len(business_hits),
                        selected_hits=selected_hits,
                        rejected_candidates=self._trace_ranked_out_candidates(
                            hits=business_hits[len(selected_hits):],
                            reason="Not selected for the business-signal shortlist because stronger operational evidence ranked higher.",
                        ),
                        observation=business_observation,
                    )
                )
                reasoning_summary.append(business_observation)
                continue

            search_request = self._agentic_search_request_for_step(
                plan_step=plan_step,
                question=request.question,
                filters=effective_filters,
                top_k=min(max(self.config.default_top_k, 5), self.config.max_top_k),
                hits_so_far=aggregated_hits,
            )
            if search_request is None:
                retrieval_steps.append(
                    self._build_trace_step(
                        step_number=step_number,
                        action=plan_step.action,
                        query_text=plan_step.query_text,
                        applied_filters=(plan_step.filters or effective_filters).model_copy(deep=True),
                        total_hits=0,
                        selected_hits=[],
                        observation=f"Step {step_number} skipped because no stable primary candidate was available yet.",
                    )
                )
                reasoning_summary.append(f"Step {step_number} skipped because no stable primary candidate was available yet.")
                continue

            search_response, retrieval_stage_counts, search_trace_diagnostics = self._search_with_trace_diagnostics(search_request)
            aggregated_retrieval_stage_counts = self._merge_retrieval_stage_counts(
                aggregated_retrieval_stage_counts,
                retrieval_stage_counts,
            )
            selected_hits = search_response.hits[: min(3, len(search_response.hits))]
            for hit in search_response.hits:
                if hit.product_id in seen_hits:
                    continue
                seen_hits.add(hit.product_id)
                aggregated_hits.append(hit)
            observation = self._build_agentic_step_observation(
                step_number=step_number,
                request=search_request,
                route_response=route_response,
                total_hits=search_response.total_hits,
                selected_hits=selected_hits,
                action=plan_step.action,
            )
            retrieval_steps.append(
                self._build_trace_step(
                    step_number=step_number,
                    action=plan_step.action,
                    query_text=search_request.query_text,
                    applied_filters=search_request.filters.model_copy(deep=True),
                    total_hits=search_response.total_hits,
                    selected_hits=selected_hits,
                    rejected_candidates=list(search_trace_diagnostics.rejected_candidates[:5]),
                    observation=observation,
                    retrieval_stage_counts=retrieval_stage_counts,
                )
            )
            reasoning_summary.append(observation)

        if not aggregated_hits:
            final_reply = InventoryReply(
                answer="I could not build a strong inventory-backed answer from the current catalog.",
                follow_up_question="Give me a product name, category, budget, or stock angle and I will narrow it down.",
            )
            confidence_score = 0.2
            ordered_hits: list[InventorySearchHit] = []
        else:
            ordered_hits = self._order_hits_for_assistant(
                question=request.question,
                hits=aggregated_hits,
                filters=effective_filters,
                low_stock_threshold=request.low_stock_threshold,
                assistant_mode=request.assistant_mode,
            )
            if execution_plan.strategy == "compare":
                final_reply = self._build_agentic_compare_reply(
                    question=request.question,
                    hits=ordered_hits,
                    filters=effective_filters,
                    reply_style=request.reply_style,
                )
            elif execution_plan.strategy == "restock":
                final_reply = self._build_agentic_restock_reply(
                    question=request.question,
                    hits=ordered_hits,
                    filters=effective_filters,
                    reply_style=request.reply_style,
                    business_signals=business_signals,
                )
            elif execution_plan.strategy == "bundle":
                final_reply = self._build_agentic_bundle_reply(
                    question=request.question,
                    hits=ordered_hits,
                    filters=effective_filters,
                    reply_style=request.reply_style,
                )
            else:
                final_reply = self._build_answer(
                    question=request.question,
                    hits=ordered_hits,
                    filters=effective_filters,
                    low_stock_threshold=request.low_stock_threshold,
                    assistant_mode=request.assistant_mode,
                    reply_style=request.reply_style,
                )
            confidence_score = self._estimate_confidence(ordered_hits)

        business_insight = self._build_business_tool_insight(
            question=request.question,
            hits=ordered_hits,
            business_signals=business_signals,
            business_intent=business_intent,
        )
        final_reply = self._align_agentic_reply_with_business_insight(
            reply=final_reply,
            hits=ordered_hits,
            business_insight=business_insight,
            business_intent=business_intent,
            question_family=route_response.signals.question_family,
            strategy=execution_plan.strategy,
        )
        if business_insight.reasoning_summary:
            reasoning_summary.extend(business_insight.reasoning_summary)
        if business_insight.missing_facts:
            missing_facts.extend(business_insight.missing_facts)
        retrieval_steps = self._append_agentic_analysis_steps(
            retrieval_steps=retrieval_steps,
            analysis_actions=execution_plan.analysis_actions,
            question=request.question,
            reply=final_reply,
            business_insight=business_insight,
            max_reasoning_steps=request.max_reasoning_steps or self.config.default_agentic_max_reasoning_steps,
        )

        answer = self._compose_agentic_answer(
            base_answer=final_reply.answer,
            route_response=route_response,
            missing_facts=missing_facts,
            business_insight=business_insight,
        )
        confidence_score = self._adjust_agentic_confidence(
            confidence_score=confidence_score,
            missing_facts=missing_facts,
            retrieval_steps=len(retrieval_steps),
        )
        abstention_reason = self._build_abstention_reason(
            question=request.question,
            hits=ordered_hits,
        )
        composed_reply = InventoryReply(
            answer=answer,
            recommended_product_ids=business_insight.selected_product_ids[:3] or final_reply.recommended_product_ids,
            cross_sell_product_ids=final_reply.cross_sell_product_ids,
            follow_up_question=final_reply.follow_up_question,
            answer_plan=final_reply.answer_plan,
            verification=final_reply.verification,
        )
        composed_reply, answer_engine, abstained, abstention_reason, fallback_reason = self._finalize_inventory_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            requested_answer_engine=request.answer_engine,
            confidence_score=confidence_score,
            hits=ordered_hits,
            base_reply=composed_reply,
            conversation_history=request.conversation_history,
            conversation_summary=request.conversation_summary,
            abstention_reason=abstention_reason,
            execution_path="inventory_agentic",
            reasoning_summary=reasoning_summary,
            missing_facts=missing_facts,
            memory_resolution=resolved_memory.resolution,
        )
        answer = composed_reply.answer

        trace_payload = {
            "trace_id": trace_id,
            "question": request.question,
            "assistant_mode": request.assistant_mode,
            "reply_style": request.reply_style,
            "execution_path": "inventory_agentic",
            "route_decision": self._serialize_route_response(route_response),
            "retrieval_stage_counts": aggregated_retrieval_stage_counts,
            "reasoning_summary": reasoning_summary,
            "missing_facts": missing_facts,
            "retrieval_steps": [step.model_dump(mode="json") for step in retrieval_steps],
            "final_answer": answer,
            "confidence_score": confidence_score,
        }
        self.trace_store.save(trace_payload)
        response = InventoryAgenticResponse(
            status="success",
            question=request.question,
            answer=answer,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            answer_engine=answer_engine,
            execution_path="inventory_agentic",
            confidence_score=confidence_score,
            abstained=abstained,
            abstention_reason=abstention_reason,
            trace_id=trace_id,
            reasoning_summary=reasoning_summary,
            missing_facts=missing_facts,
            retrieval_steps_used=len(retrieval_steps),
            total_hits=len(ordered_hits),
            applied_filters=effective_filters,
            hits=ordered_hits,
            recommended_product_ids=composed_reply.recommended_product_ids,
            cross_sell_product_ids=composed_reply.cross_sell_product_ids,
            follow_up_question=composed_reply.follow_up_question,
            answer_plan=composed_reply.answer_plan,
            verification=composed_reply.verification,
            memory_resolution=resolved_memory.resolution,
        )
        self._save_inventory_chat_trace(
            trace_id=trace_id,
            response=response,
            execution_path="inventory_agentic",
            started_at=started_at,
            requested_answer_engine=request.answer_engine,
            retrieved_hits=aggregated_hits,
            reranked_hits=ordered_hits,
            retrieval_stage_counts=aggregated_retrieval_stage_counts,
            reasoning_summary=reasoning_summary,
            missing_facts=missing_facts,
            retrieval_steps=retrieval_steps,
            fallback_reason_override=fallback_reason,
            route_decision_override=self._serialize_route_response(route_response),
        )
        return response

    def get_agentic_trace(self, trace_id: str) -> InventoryAgenticTraceResponse | None:
        payload = self.trace_store.load(trace_id)
        if payload is None:
            return None
        return InventoryAgenticTraceResponse.model_validate(payload)

    def get_chat_trace(self, trace_id: str) -> InventoryChatTraceResponse | None:
        payload = self.chat_trace_store.load(trace_id)
        if payload is None:
            return None
        return InventoryChatTraceResponse.model_validate(payload)

    def _save_inventory_chat_trace(
        self,
        *,
        trace_id: str,
        response: InventoryAskResponse | InventoryAgenticResponse,
        execution_path: str,
        started_at: float,
        requested_answer_engine: str,
        retrieved_hits: list[InventorySearchHit],
        reranked_hits: list[InventorySearchHit],
        retrieval_stage_counts: dict[str, int] | None = None,
        reasoning_summary: list[str] | None = None,
        missing_facts: list[str] | None = None,
        retrieval_steps: list[InventoryAgenticStep] | None = None,
        fallback_reason_override: str | None = None,
        route_decision_override: dict[str, object] | None = None,
    ) -> None:
        latency_ms = round((perf_counter() - started_at) * 1000, 3)
        intent = response.answer_plan.detected_intent or response.answer_plan.intent
        route_decision = route_decision_override or self._build_route_trace_metadata(
            question=response.question,
            filters=response.applied_filters,
            execution_path=execution_path,
        )
        fallback_reason = fallback_reason_override
        if fallback_reason is None:
            fallback_reason = self._trace_fallback_reason(
                requested_answer_engine=requested_answer_engine,
                response=response,
            )
        payload = {
            "trace_id": trace_id,
            "request_id": trace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "question": response.question,
            "assistant_mode": response.assistant_mode,
            "reply_style": response.reply_style,
            "answer_engine": response.answer_engine,
            "execution_path": execution_path,
            "latency_ms": latency_ms,
            "fallback_reason": fallback_reason,
            "intent": intent,
            "route_decision": route_decision,
            "retrieval_stage_counts": dict(retrieval_stage_counts or {}),
            "preferences": response.answer_plan.preferences,
            "retrieved_product_ids": self._trace_product_ids(retrieved_hits),
            "reranked_product_ids": self._trace_product_ids(reranked_hits),
            "recommended_product_ids": response.recommended_product_ids,
            "cross_sell_product_ids": response.cross_sell_product_ids,
            "total_hits": response.total_hits,
            "confidence_score": response.confidence_score,
            "abstained": response.abstained,
            "abstention_reason": response.abstention_reason,
            "applied_filters": response.applied_filters.model_dump(mode="json"),
            "answer_plan": response.answer_plan.model_dump(mode="json"),
            "verification": response.verification.model_dump(mode="json"),
            "memory_resolution": response.memory_resolution.model_dump(mode="json"),
            "reasoning_summary": reasoning_summary or [],
            "missing_facts": missing_facts or [],
            "retrieval_steps": [step.model_dump(mode="json") for step in retrieval_steps or []],
            "final_answer": response.answer,
        }
        self.chat_trace_store.save(payload)
        logger.info(
            "inventory_chat_trace trace_id=%s execution_path=%s intent=%s answer_engine=%s total_hits=%s latency_ms=%s fallback_reason=%s",
            trace_id,
            execution_path,
            intent,
            response.answer_engine,
            response.total_hits,
            latency_ms,
            fallback_reason,
        )

    @staticmethod
    def _trace_product_ids(hits: list[InventorySearchHit]) -> list[str]:
        product_ids: list[str] = []
        for hit in hits:
            if hit.product_id in product_ids:
                continue
            product_ids.append(hit.product_id)
        return product_ids

    @staticmethod
    def _trace_score_breakdown(hit: InventorySearchHit) -> dict[str, object]:
        if not hit.evidence_scores:
            return {}
        allowed_keys = {
            "final_score",
            "semantic_score",
            "lexical_score",
            "exact_name_match",
            "exact_sku_match",
            "category_match",
            "brand_match",
            "product_type_match",
            "family_match",
            "price_fit",
            "stock_fit",
            "metadata_match",
            "structured_spec_match",
            "premium_fit",
            "budget_fit",
            "unrelated_category_penalty",
            "out_of_stock_penalty",
            "business_signal_score",
            "business_intent",
            "business_reasons",
            "reasons",
        }
        breakdown: dict[str, object] = {}
        for key, value in hit.evidence_scores.items():
            if key in allowed_keys or key.startswith("deterministic_"):
                breakdown[key] = value
        return breakdown

    def _trace_candidate_debug(
        self,
        *,
        hit: InventorySearchHit,
        rejection_reasons: list[str] | None = None,
        score_breakdown: dict[str, object] | None = None,
    ) -> InventoryTraceCandidateDebug:
        return InventoryTraceCandidateDebug(
            product_id=hit.product_id,
            name=hit.name,
            category=hit.category,
            score=hit.score,
            score_breakdown=dict(score_breakdown or self._trace_score_breakdown(hit)),
            rejection_reasons=list(rejection_reasons or []),
        )

    def _trace_candidate_debugs_from_hits(
        self,
        hits: list[InventorySearchHit],
        *,
        limit: int = 3,
    ) -> list[InventoryTraceCandidateDebug]:
        return [self._trace_candidate_debug(hit=hit) for hit in hits[:limit]]

    def _record_rejected_candidate(
        self,
        *,
        rejection_log: dict[str, InventoryTraceCandidateDebug],
        hit: InventorySearchHit,
        reason: str,
    ) -> None:
        existing = rejection_log.get(hit.product_id)
        if existing is None:
            rejection_log[hit.product_id] = self._trace_candidate_debug(
                hit=hit,
                rejection_reasons=[reason],
            )
            return
        reasons = list(existing.rejection_reasons)
        if reason not in reasons:
            reasons.append(reason)
        rejection_log[hit.product_id] = existing.model_copy(
            update={
                "score": hit.score,
                "score_breakdown": existing.score_breakdown or self._trace_score_breakdown(hit),
                "rejection_reasons": reasons,
            }
        )

    def _trace_ranked_out_candidates(
        self,
        *,
        hits: list[InventorySearchHit],
        reason: str,
        limit: int = 5,
    ) -> list[InventoryTraceCandidateDebug]:
        return [
            self._trace_candidate_debug(hit=hit, rejection_reasons=[reason])
            for hit in hits[:limit]
        ]

    @staticmethod
    def _trace_candidate_debug_from_evidence_candidate(candidate: BaseModel) -> InventoryTraceCandidateDebug:
        product_id = getattr(candidate, "product_id", None)
        name = getattr(candidate, "name", None)
        category = getattr(candidate, "category", None)
        score = getattr(candidate, "score", None)
        score_breakdown = getattr(candidate, "score_breakdown", {}) or {}
        rejection_reasons = getattr(candidate, "rejection_reasons", []) or []
        return InventoryTraceCandidateDebug(
            product_id=product_id,
            name=name,
            category=category,
            score=score,
            score_breakdown=dict(score_breakdown),
            rejection_reasons=list(rejection_reasons),
        )

    def _build_trace_step(
        self,
        *,
        step_number: int,
        action: str,
        query_text: str | None,
        applied_filters: InventorySearchFilters,
        total_hits: int,
        selected_hits: list[InventorySearchHit],
        observation: str,
        retrieval_stage_counts: dict[str, int] | None = None,
        rejected_candidates: list[InventoryTraceCandidateDebug] | None = None,
    ) -> InventoryAgenticStep:
        return InventoryAgenticStep(
            step_number=step_number,
            action=action,
            query_text=query_text,
            applied_filters=applied_filters.model_copy(deep=True),
            total_hits=total_hits,
            selected_product_ids=[hit.product_id for hit in selected_hits],
            selected_candidates=self._trace_candidate_debugs_from_hits(selected_hits, limit=len(selected_hits)),
            rejected_candidates=list(rejected_candidates or []),
            observation=observation,
            retrieval_stage_counts=dict(retrieval_stage_counts or {}),
        )

    @staticmethod
    def _trace_fallback_reason(
        *,
        requested_answer_engine: str,
        response: InventoryAskResponse | InventoryAgenticResponse,
    ) -> str | None:
        if response.abstention_reason:
            return response.abstention_reason
        if requested_answer_engine == "natural" and response.answer_engine != "natural":
            return "Natural answer was requested but deterministic fallback was used."
        if response.verification.final_answer_issues:
            return "Final answer verification reported issues."
        if response.verification.issues:
            return "Answer plan verification reported issues."
        return None

    @staticmethod
    def _empty_retrieval_stage_counts() -> dict[str, int]:
        return {
            "search_requests": 0,
            "dense_raw_matches": 0,
            "dense_pool_candidates": 0,
            "lexical_pool_candidates": 0,
            "merged_pool_candidates": 0,
            "spec_filtered_candidates": 0,
            "type_gated_candidates": 0,
            "category_gated_candidates": 0,
            "exact_lookup_candidates": 0,
            "lexical_anchor_candidates": 0,
            "browse_candidates": 0,
            "reranked_candidates": 0,
            "returned_hits": 0,
        }

    @staticmethod
    def _merge_retrieval_stage_counts(
        base: dict[str, int],
        delta: dict[str, int],
    ) -> dict[str, int]:
        merged = dict(base)
        for key, value in delta.items():
            merged[key] = merged.get(key, 0) + int(value)
        return merged

    def _dense_candidate_scores(
        self,
        *,
        query_text: str,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
        derived_filters: dict[str, object] | None = None,
    ) -> tuple[dict[str, float], int]:
        query_vector = self.embedder.embed_text(query_text)
        vector_filters = self._build_vector_filters(filters)
        if derived_filters:
            vector_filters.update(derived_filters)
        candidate_limit = max(top_k * self.config.search_candidate_multiplier, top_k)
        result = self.vector_store.query(
            query_vector,
            top_k=candidate_limit,
            filters=vector_filters or None,
            namespace=self.config.namespace,
        )
        dense_scores = {
            match.record_id: match.score
            for match in result.matches
            if match.record_id in catalog and self._item_matches_filters(catalog[match.record_id], filters)
        }
        return dense_scores, len(result.matches)

    def _lexical_candidate_scores(
        self,
        *,
        catalog: dict[str, InventoryItemRecord],
        filters: InventorySearchFilters,
        query_terms: list[str],
        subject_phrase: str | None,
    ) -> dict[str, tuple[float, int]]:
        lexical_scores: dict[str, tuple[float, int]] = {}
        for item in catalog.values():
            if not self._item_matches_filters(item, filters):
                continue
            lexical_score = self._lexical_match_score(
                item=item,
                query_terms=query_terms,
                subject_phrase=subject_phrase,
            )
            if lexical_score <= 0:
                continue
            lexical_scores[item.product_id] = (
                lexical_score,
                self._query_term_coverage(item=item, query_terms=query_terms),
            )
        return lexical_scores

    def _semantic_search(
        self,
        *,
        query_text: str,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
    ) -> tuple[list[InventorySearchHit], dict[str, int], InventorySearchTraceDiagnostics]:
        retrieval_stage_counts = self._empty_retrieval_stage_counts()
        rejection_log: dict[str, InventoryTraceCandidateDebug] = {}
        query_terms = self._extract_query_terms(query_text)
        subject_phrase = self._extract_subject_phrase(query_text)
        detail_request = self._is_detail_request(query_text)
        exact_lookup = self._should_require_exact_lookup(
            query_text=query_text,
            query_terms=query_terms,
            subject_phrase=subject_phrase,
            detail_request=detail_request,
        )
        if filters.product_ids:
            exact_lookup = False
        preference_profile = self.preference_extractor.extract(
            query_text,
            filters=filters,
            products=list(catalog.values()),
        )
        vector_scores, dense_raw_matches = self._dense_candidate_scores(
            query_text=query_text,
            top_k=top_k,
            filters=filters,
            catalog=catalog,
            derived_filters=self._build_requirement_vector_filters(preference_profile),
        )
        retrieval_stage_counts["dense_raw_matches"] = dense_raw_matches
        retrieval_stage_counts["dense_pool_candidates"] = len(vector_scores)
        requested_product_type = preference_profile.product_type
        if detail_request and subject_phrase and len(subject_phrase.split()) >= 3:
            requested_product_type = None

        lexical_candidates = self._lexical_candidate_scores(
            catalog=catalog,
            filters=filters,
            query_terms=query_terms,
            subject_phrase=subject_phrase,
        )
        retrieval_stage_counts["lexical_pool_candidates"] = len(lexical_candidates)
        merged_candidate_ids = list(dict.fromkeys([*lexical_candidates.keys(), *vector_scores.keys()]))
        retrieval_stage_counts["merged_pool_candidates"] = len(merged_candidate_ids)

        candidates: list[tuple[InventorySearchHit, float, float, int, int]] = []
        for product_id in merged_candidate_ids:
            item = catalog[product_id]
            lexical_score, coverage = lexical_candidates.get(product_id, (0.0, 0))
            vector_score = vector_scores.get(product_id, 0.0)
            confidence_score = max(vector_score, min(1.0, lexical_score / 12.0))
            relation_score = self.product_ontology.relation_score(requested_product_type, item)
            candidates.append(
                (
                    self._build_search_hit(item=item, score=confidence_score),
                    lexical_score,
                    vector_score,
                    coverage,
                    relation_score,
                )
            )

        if not candidates:
            return [], retrieval_stage_counts, InventorySearchTraceDiagnostics()

        if preference_profile.spec_requirements:
            spec_match_scores = [
                self._hit_spec_match_score(candidate[0], preference_profile.spec_requirements)
                for candidate in candidates
            ]
            exact_spec_candidates = [
                candidate
                for candidate, score in zip(candidates, spec_match_scores, strict=False)
                if score >= 1.0
            ]
            retrieval_stage_counts["spec_filtered_candidates"] = len(exact_spec_candidates)
            strict_spec_requirements = all(
                requirement.operator == "eq" for requirement in preference_profile.spec_requirements
            )
            if strict_spec_requirements and exact_spec_candidates:
                for candidate, score in zip(candidates, spec_match_scores, strict=False):
                    if score >= 1.0:
                        continue
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the spec gate because it did not satisfy all required exact spec filters.",
                    )
                candidates = exact_spec_candidates
            elif max(spec_match_scores, default=0.0) <= 0.0 and len(query_terms) >= 3:
                for candidate in candidates:
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the spec gate because no candidate satisfied the requested structured specs.",
                    )
                retrieval_stage_counts["spec_filtered_candidates"] = 0
                return [], retrieval_stage_counts, InventorySearchTraceDiagnostics(
                    rejected_candidates=tuple(rejection_log.values())
                )
        else:
            retrieval_stage_counts["spec_filtered_candidates"] = len(candidates)

        if requested_product_type:
            exact_type_candidates = [candidate for candidate in candidates if candidate[4] >= 3]
            related_type_candidates = [candidate for candidate in candidates if candidate[4] >= 2]
            if exact_type_candidates:
                kept_ids = {candidate[0].product_id for candidate in exact_type_candidates}
                for candidate in candidates:
                    if candidate[0].product_id in kept_ids:
                        continue
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the product-type gate because it was not a close enough match for the requested product family.",
                    )
                candidates = exact_type_candidates
            elif related_type_candidates and not exact_lookup:
                kept_ids = {candidate[0].product_id for candidate in related_type_candidates}
                for candidate in candidates:
                    if candidate[0].product_id in kept_ids:
                        continue
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the product-type gate because stronger family matches were available.",
                    )
                candidates = related_type_candidates
            elif exact_lookup or preference_profile.confidence >= 0.28:
                for candidate in candidates:
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the product-type gate because no candidate matched the requested product type strongly enough.",
                    )
                retrieval_stage_counts["type_gated_candidates"] = 0
                return [], retrieval_stage_counts, InventorySearchTraceDiagnostics(
                    rejected_candidates=tuple(rejection_log.values())
                )
        retrieval_stage_counts["type_gated_candidates"] = len(candidates)

        requested_category = self._resolve_explicit_requested_category(
            query_text=query_text,
            filters=filters,
            catalog=catalog,
            preference_profile=preference_profile,
        )
        if requested_category:
            category_matched_candidates = [
                candidate
                for candidate in candidates
                if candidate[0].category and candidate[0].category.casefold() == requested_category.casefold()
            ]
            if category_matched_candidates:
                kept_ids = {candidate[0].product_id for candidate in category_matched_candidates}
                for candidate in candidates:
                    if candidate[0].product_id in kept_ids:
                        continue
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the category gate because it did not match the explicitly requested category.",
                    )
                candidates = category_matched_candidates
        retrieval_stage_counts["category_gated_candidates"] = len(candidates)

        if exact_lookup:
            max_coverage = max(coverage for _, _, _, coverage, _ in candidates)
            if max_coverage <= 0:
                for candidate in candidates:
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the exact-lookup gate because it did not cover the referenced product terms.",
                    )
                retrieval_stage_counts["exact_lookup_candidates"] = 0
                return [], retrieval_stage_counts, InventorySearchTraceDiagnostics(
                    rejected_candidates=tuple(rejection_log.values())
                )
            coverage_threshold = len(query_terms) if len(query_terms) <= 2 else max(1, len(query_terms) - 1)
            exact_candidates = [candidate for candidate in candidates if candidate[3] >= coverage_threshold]
            if exact_candidates:
                kept_ids = {candidate[0].product_id for candidate in exact_candidates}
                for candidate in candidates:
                    if candidate[0].product_id in kept_ids:
                        continue
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the exact-lookup gate because it missed too many exact reference terms.",
                    )
                candidates = exact_candidates
            else:
                for candidate in candidates:
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the exact-lookup gate because it missed too many exact reference terms.",
                    )
                retrieval_stage_counts["exact_lookup_candidates"] = 0
                return [], retrieval_stage_counts, InventorySearchTraceDiagnostics(
                    rejected_candidates=tuple(rejection_log.values())
                )
        retrieval_stage_counts["exact_lookup_candidates"] = len(candidates)

        best_lexical_score = max(lexical_score for _, lexical_score, _, _, _ in candidates)
        anchor_to_lexical = self._should_anchor_to_lexical(
            query_terms=query_terms,
            subject_phrase=subject_phrase,
            best_lexical_score=best_lexical_score,
            detail_request=detail_request,
        )
        if anchor_to_lexical:
            lexical_threshold = max(4.0, best_lexical_score * 0.6)
            anchored_candidates = [
                candidate for candidate in candidates if candidate[1] >= lexical_threshold
            ]
            if anchored_candidates:
                kept_ids = {candidate[0].product_id for candidate in anchored_candidates}
                for candidate in candidates:
                    if candidate[0].product_id in kept_ids:
                        continue
                    self._record_rejected_candidate(
                        rejection_log=rejection_log,
                        hit=candidate[0],
                        reason="Rejected at the lexical anchor gate because exact-text evidence was too weak relative to the strongest lexical matches.",
                    )
                candidates = anchored_candidates
        retrieval_stage_counts["lexical_anchor_candidates"] = len(candidates)

        max_vector_score = max((vector_score for _, _, vector_score, _, _ in candidates), default=0.0)
        max_lexical_score = max((lexical_score for _, lexical_score, _, _, _ in candidates), default=0.0)
        scored_candidates: list[tuple[InventorySearchHit, float, float, int, int, float]] = []
        for hit, lexical_score, vector_score, coverage, relation_score in candidates:
            exact_name_match, exact_sku_match = self._exact_reference_match_signals(
                query_text=query_text,
                query_terms=query_terms,
                subject_phrase=subject_phrase,
                item=InventoryItemRecord(
                    product_id=hit.product_id,
                    sku=hit.sku,
                    name=hit.name,
                    category=hit.category,
                    brand=hit.brand,
                    short_description=hit.snippet,
                    price=hit.price,
                    currency=hit.currency or "USD",
                    stock=hit.stock or 0,
                    status=hit.status,
                    tags=list(hit.tags),
                    attributes=dict(hit.attributes),
                    metadata=dict(hit.metadata),
                    include_in_rag=True,
                    updated_at=hit.updated_at,
                ),
            )
            evidence_score = self.ecommerce_reranker.score_product(
                hit,
                preferences=preference_profile,
                semantic_score=(vector_score / max_vector_score) if max_vector_score > 0 else 0.0,
                lexical_score=(lexical_score / max_lexical_score) if max_lexical_score > 0 else 0.0,
                exact_name_match=exact_name_match,
                exact_sku_match=exact_sku_match,
            )
            scored_hit = hit.model_copy(
                update={
                    "score": evidence_score.final_score,
                    "evidence_scores": evidence_score.to_debug_dict(),
                }
            )
            scored_candidates.append(
                (
                    scored_hit,
                    lexical_score,
                    vector_score,
                    coverage,
                    relation_score,
                    evidence_score.final_score,
                )
            )

        ranked_candidates = sorted(
            scored_candidates,
            key=lambda candidate: (
                -candidate[5],
                -candidate[3],
                -candidate[4],
                -candidate[1],
                -candidate[2],
                self._is_out_of_stock(candidate[0]),
                -self._quality_score(candidate[0]),
                self._price_sort_key(candidate[0]),
                candidate[0].name.casefold(),
            ),
        )
        retrieval_stage_counts["reranked_candidates"] = len(ranked_candidates)
        returned_hits = [hit for hit, _, _, _, _, _ in ranked_candidates[:top_k]]
        for hit, *_rest in ranked_candidates[top_k:]:
            self._record_rejected_candidate(
                rejection_log=rejection_log,
                hit=hit,
                reason="Rejected after deterministic reranking because it fell below the returned top_k cutoff.",
            )
        retrieval_stage_counts["returned_hits"] = len(returned_hits)
        return returned_hits, retrieval_stage_counts, InventorySearchTraceDiagnostics(
            rejected_candidates=tuple(rejection_log.values())
        )

    def _browse_items(
        self,
        *,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
    ) -> tuple[list[InventorySearchHit], dict[str, int], InventorySearchTraceDiagnostics]:
        items = [
            item
            for item in sorted(catalog.values(), key=self._catalog_sort_key, reverse=True)
            if self._item_matches_filters(item, filters)
        ]
        retrieval_stage_counts = self._empty_retrieval_stage_counts()
        retrieval_stage_counts["browse_candidates"] = len(items)
        retrieval_stage_counts["reranked_candidates"] = len(items)
        all_hits = [self._build_search_hit(item=item, score=0.0) for item in items]
        hits = all_hits[:top_k]
        retrieval_stage_counts["returned_hits"] = len(hits)
        return hits, retrieval_stage_counts, InventorySearchTraceDiagnostics(
            rejected_candidates=tuple(
                self._trace_ranked_out_candidates(
                    hits=all_hits[top_k:],
                    reason="Excluded from browse results because it fell beyond the returned top_k cutoff.",
                )
            )
        )

    def _merge_question_filters(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        low_stock_threshold: int,
    ) -> InventorySearchFilters:
        merged = filters.model_copy(deep=True)
        lowered = question.casefold()

        if self._has_any_phrase(lowered, ["prevent stockout", "prevent stock out", "avoid stockout", "avoid stock out"]):
            if merged.max_stock is None:
                merged.max_stock = low_stock_threshold
        elif self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]):
            if merged.max_stock is None:
                merged.max_stock = 0
        elif self._has_any_phrase(lowered, ["low stock", "running low", "below threshold", "limited stock"]):
            if merged.max_stock is None:
                merged.max_stock = low_stock_threshold

        under_match = _UNDER_PRICE_PATTERN.search(question)
        if under_match and merged.max_price is None:
            merged.max_price = float(under_match.group(1))

        over_match = _OVER_PRICE_PATTERN.search(question)
        if over_match and merged.min_price is None:
            merged.min_price = float(over_match.group(1))

        return merged

    def _build_conversational_reply(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
    ) -> tuple[InventoryReply, float] | None:
        normalized = self._normalize_conversation_text(question)
        token_count = len(normalized.split())
        inventory_request = self._looks_like_inventory_request(normalized)

        if self._has_any_phrase(normalized, _HOW_ARE_YOU_PHRASES):
            if assistant_mode == "sales":
                return (
                    InventoryReply(
                        answer=(
                            "I am doing well and ready to help you sell. Tell me the customer need, budget, or product category and I will suggest the best option."
                        ),
                        follow_up_question=(
                            "What is the customer shopping for, and are they more price-sensitive or looking for a premium option?"
                            if reply_style == "detailed"
                            else None
                        ),
                    ),
                    1.0,
                )
            return (
                InventoryReply(
                    answer=(
                        "I am doing well and ready to help with product questions, stock checks, pricing, and restocking. Tell me what you need."
                    ),
                    follow_up_question=(
                        "What would you like help with first: product search, stock, pricing, or restocking?"
                        if reply_style == "detailed"
                        else None
                    ),
                ),
                1.0,
            )

        if token_count <= 6 and self._has_any_phrase(normalized, _GREETING_PHRASES) and not inventory_request:
            if assistant_mode == "sales":
                return (
                    InventoryReply(
                        answer=(
                            "Hello. I can help you recommend the right product, position premium options, or find a lower-price fallback for a customer."
                        ),
                        follow_up_question=(
                            "Are we selling into audio, office, computing, or something else?"
                            if reply_style == "detailed"
                            else None
                        ),
                    ),
                    1.0,
                )
            return (
                InventoryReply(
                    answer="Hello. I can help with inventory, availability, pricing, and restocking questions.",
                    follow_up_question=(
                        "Do you want to check stock, compare products, or find something specific?"
                        if reply_style == "detailed"
                        else None
                    ),
                ),
                1.0,
            )

        if token_count <= 8 and self._has_any_phrase(normalized, _THANKS_PHRASES) and not inventory_request:
            if assistant_mode == "sales":
                return (
                    InventoryReply(
                        answer="Anytime. If you want, give me a customer scenario and I will help you pitch the best match."
                    ),
                    1.0,
                )
            return (
                InventoryReply(
                    answer="Anytime. Ask me about stock, pricing, products, or restocking whenever you are ready."
                ),
                1.0,
            )

        if token_count <= 8 and self._has_any_phrase(normalized, _CLOSING_PHRASES) and not inventory_request:
            if assistant_mode == "sales":
                return (
                    InventoryReply(answer="Talk soon. When you are back, I can help you sell, upsell, or compare products."),
                    1.0,
                )
            return (
                InventoryReply(answer="Talk soon. When you are back, I can help with inventory and support questions."),
                1.0,
            )

        if self._has_any_phrase(normalized, _IDENTITY_PHRASES):
            if assistant_mode == "sales":
                return (
                    InventoryReply(
                        answer=(
                            "I am your inventory sales assistant. I use the indexed product catalog to recommend what to pitch, what to upsell, and what to avoid overpromising."
                        )
                    ),
                    1.0,
                )
            return (
                InventoryReply(
                    answer=(
                        "I am your inventory support assistant. I use the indexed product catalog to answer stock, pricing, and product questions."
                    )
                ),
                1.0,
            )

        if token_count <= 10 and self._has_any_phrase(normalized, _HELP_PHRASES) and not inventory_request:
            if assistant_mode == "sales":
                return (
                    InventoryReply(
                        answer=(
                            "I can recommend products for a customer, suggest premium or budget options, handle common objections, and give you a cleaner sales angle based on real catalog data."
                        ),
                        follow_up_question=(
                            "Do you want help with a premium pitch, a budget alternative, or a product comparison?"
                            if reply_style == "detailed"
                            else None
                        ),
                    ),
                    1.0,
                )
            return (
                InventoryReply(
                    answer=(
                        "I can check stock, pricing, category matches, restocking priorities, and product availability. Ask me something like 'show low stock audio items' or 'find premium office products'."
                    ),
                    follow_up_question=(
                        "Would you like to search products, check stock urgency, or compare prices?"
                        if reply_style == "detailed"
                        else None
                    ),
                ),
                1.0,
            )

        return None

    def _build_route_signals(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
    ) -> InventoryRouteSignals:
        intent_result, question_family, family_confidence, family_reasons = self._classify_route_question_family(
            question=question,
            filters=filters,
        )
        normalized = self._normalize_conversation_text(question)
        is_small_talk = (
            not self._looks_like_inventory_request(normalized)
            and (
                self._has_any_phrase(normalized, _GREETING_PHRASES)
                or self._has_any_phrase(normalized, _HOW_ARE_YOU_PHRASES)
                or self._has_any_phrase(normalized, _THANKS_PHRASES)
                or self._has_any_phrase(normalized, _HELP_PHRASES)
                or self._has_any_phrase(normalized, _IDENTITY_PHRASES)
                or self._has_any_phrase(normalized, _CLOSING_PHRASES)
            )
        )
        has_explicit_product_reference = bool(filters.product_ids) or self._is_detail_request(question) or bool(
            re.search(r"\b[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+\b", question)
        )
        needs_historical_data = self._has_any_phrase(normalized, _HISTORICAL_DATA_HINTS)
        needs_cross_system_data = self._has_any_phrase(normalized, _CROSS_SYSTEM_HINTS)
        needs_root_cause_reasoning = (
            question_family == "diagnosis_root_cause"
            or (self._has_any_phrase(normalized, _ROOT_CAUSE_HINTS) and not is_small_talk)
        )
        needs_workflow_action = question_family == "planning_agentic_workflow" or self._has_any_phrase(normalized, _WORKFLOW_ACTION_HINTS) or (
            "should we" in normalized or "should i" in normalized
        )
        needs_multi_step_reasoning = question_family in {"comparison", "diagnosis_root_cause", "planning_agentic_workflow"} or self._has_any_phrase(normalized, _MULTI_STEP_REASONING_HINTS)
        if sum(
            (
                int(needs_historical_data),
                int(needs_cross_system_data),
                int(needs_root_cause_reasoning),
                int(needs_workflow_action),
            )
        ) >= 2:
            needs_multi_step_reasoning = True

        simple_catalog_lookup = (
            not any(
                (
                    needs_historical_data,
                    needs_cross_system_data,
                    needs_root_cause_reasoning,
                    needs_workflow_action,
                )
            )
            and (
                question_family in {"exact_lookup", "comparison", "recommendation", "no_match_or_abstain"}
                or question_family == "small_talk"
                or has_explicit_product_reference
                or self._looks_like_inventory_request(normalized)
                or bool(_UNDER_PRICE_PATTERN.search(question))
                or bool(_OVER_PRICE_PATTERN.search(question))
                or self._has_any_phrase(
                    normalized,
                    [
                        "compare",
                        "vs",
                        "versus",
                        "difference between",
                        "cheapest",
                        "most expensive",
                        "best option",
                    ],
                )
            )
        )
        return InventoryRouteSignals(
            detected_intent=intent_result.intent,
            intent_confidence=intent_result.confidence,
            intent_reasons=list(intent_result.reasons),
            question_family=question_family,
            family_confidence=family_confidence,
            family_reasons=family_reasons,
            is_small_talk=is_small_talk,
            has_explicit_product_reference=has_explicit_product_reference,
            simple_catalog_lookup=simple_catalog_lookup,
            needs_historical_data=needs_historical_data,
            needs_cross_system_data=needs_cross_system_data,
            needs_root_cause_reasoning=needs_root_cause_reasoning,
            needs_workflow_action=needs_workflow_action,
            needs_multi_step_reasoning=needs_multi_step_reasoning,
        )

    def _classify_route_question_family(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
    ) -> tuple[InventoryIntentResult, str, float, list[str]]:
        intent_result = self.intent_classifier.classify(question, filters=filters)
        normalized = self._normalize_conversation_text(question)
        has_explicit_product_reference = bool(filters.product_ids) or self._is_detail_request(question) or bool(
            re.search(r"\b[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+\b", question)
        )
        has_root_cause_signal = self._has_any_phrase(normalized, _ROOT_CAUSE_HINTS)
        has_workflow_signal = self._has_any_phrase(normalized, _WORKFLOW_ACTION_HINTS) or (
            "should we" in normalized or "should i" in normalized
        )

        family = "no_match_or_abstain"
        confidence = max(0.5, intent_result.confidence)
        reasons = list(intent_result.reasons)

        if intent_result.intent == "small_talk":
            return intent_result, "small_talk", 0.98, ["Detected conversational small talk."]

        if has_workflow_signal and (
            intent_result.intent in {"restock", "business_analysis", "cross_sell"}
            or (
                intent_result.intent == "product_search"
                and self._has_any_phrase(
                    normalized,
                    [
                        "supplier",
                        "vendor",
                        "lead time",
                        "lead-time",
                        "delay",
                        "delays",
                        "margin",
                        "profit",
                        "sales",
                        "demand",
                        "stockout",
                        "reorder",
                        "restock",
                    ],
                )
            )
            or has_root_cause_signal
        ):
            family = "planning_agentic_workflow"
            confidence = max(confidence, 0.9)
            reasons.append("Question includes workflow or action-planning language.")
            if has_root_cause_signal:
                reasons.append("Question also includes diagnosis or root-cause language.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if intent_result.intent == "comparison" or self._has_any_phrase(
            normalized,
            ("compare", "vs", "versus", "difference between", "which is better"),
        ):
            family = "comparison"
            confidence = max(confidence, 0.9)
            reasons.append("Question asks for side-by-side product comparison.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if has_root_cause_signal and intent_result.intent in {"business_analysis", "unknown"}:
            family = "diagnosis_root_cause"
            confidence = max(confidence, 0.84)
            reasons.append("Question asks why something happened and likely needs diagnosis.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if intent_result.intent in {
            "recommendation",
            "price_objection",
            "availability_objection",
            "quality_objection",
            "cross_sell",
        }:
            family = "recommendation"
            confidence = max(confidence, 0.86)
            reasons.append("Question is asking for a recommendation, objection handling, or add-on guidance.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if intent_result.intent in {"exact_lookup", "product_detail", "product_search"}:
            family = "exact_lookup"
            confidence = max(confidence, 0.78 if has_explicit_product_reference else 0.72)
            if has_explicit_product_reference:
                reasons.append("Question includes an explicit product or SKU reference.")
            else:
                reasons.append("Question looks like a direct catalog lookup.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if intent_result.intent == "restock" or has_workflow_signal:
            family = "planning_agentic_workflow"
            confidence = max(confidence, 0.82)
            reasons.append("Question is asking what action to take next.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if intent_result.intent == "business_analysis":
            family = "diagnosis_root_cause"
            confidence = max(confidence, 0.76)
            reasons.append("Question needs operational diagnosis instead of a simple lookup.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        if self._looks_like_inventory_request(normalized):
            family = "no_match_or_abstain"
            confidence = max(confidence, 0.58)
            reasons.append("Question looks inventory-related but lacks a strong direct lookup or workflow signature.")
            return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

        reasons.append("Question does not map cleanly to a retrieval family and may need clarification or abstain behavior.")
        return intent_result, family, confidence, self._dedupe_route_reasons(reasons)

    def _build_route_trace_metadata(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        execution_path: str,
    ) -> dict[str, object]:
        signals = self._build_route_signals(question=question, filters=filters)
        return {
            "execution_path": execution_path,
            "detected_intent": signals.detected_intent,
            "intent_confidence": signals.intent_confidence,
            "question_family": signals.question_family,
            "family_confidence": signals.family_confidence,
            "family_reasons": list(signals.family_reasons),
            "signals": signals.model_dump(mode="json"),
        }

    @staticmethod
    def _serialize_route_response(route_response: InventoryRouteResponse) -> dict[str, object]:
        return {
            "policy_version": route_response.policy_version,
            "recommended_path": route_response.recommended_path,
            "fallback_path": route_response.fallback_path,
            "decision_confidence": route_response.decision_confidence,
            "reason_summary": route_response.reason_summary,
            "decision_factors": list(route_response.decision_factors),
            "required_data_domains": list(route_response.required_data_domains),
            "missing_data_domains": list(route_response.missing_data_domains),
            "signals": route_response.signals.model_dump(mode="json"),
            "family_contract": (
                route_response.family_contract.model_dump(mode="json")
                if route_response.family_contract is not None
                else None
            ),
            "applicable_hard_abstain_triggers": [
                trigger.model_dump(mode="json")
                for trigger in route_response.applicable_hard_abstain_triggers
            ],
        }

    @staticmethod
    def _dedupe_route_reasons(reasons: list[str]) -> list[str]:
        deduped: list[str] = []
        for reason in reasons:
            if not reason or reason in deduped:
                continue
            deduped.append(reason)
        return deduped

    def _required_data_domains_for_route(
        self,
        *,
        question: str,
        signals: InventoryRouteSignals,
    ) -> list[str]:
        normalized = self._normalize_conversation_text(question)
        required: list[str] = []
        if signals.needs_historical_data:
            required.append("inventory_snapshots")
        if any(term in normalized for term in ("sales", "revenue", "profit", "margin")):
            required.append("sales")
        if any(term in normalized for term in ("demand", "selling", "sold", "velocity", "trend", "dropped")):
            required.append("sales")
        if "order" in normalized or "orders" in normalized:
            required.append("orders")
        if any(term in normalized for term in ("supplier", "suppliers", "vendor", "vendors", "purchase order")):
            required.append("suppliers")
        if any(term in normalized for term in ("lead time", "lead-time")):
            required.append("suppliers")
        if any(term in normalized for term in ("restock", "reorder", "stockout", "stock out", "running low")):
            required.append("inventory_snapshots")
            required.append("sales")
        if any(term in normalized for term in ("return rate", "returns", "returned")):
            required.append("returns")
        if any(term in normalized for term in ("margin", "profit", "profitable")):
            required.append("margins")
        if "customer" in normalized or "customers" in normalized:
            required.append("customers")
        if "segment" in normalized or "segments" in normalized:
            required.append("customers")
        deduped: list[str] = []
        seen: set[str] = set()
        for domain in required:
            if domain in seen:
                continue
            seen.add(domain)
            deduped.append(domain)
        return deduped

    def _select_route(
        self,
        *,
        request: InventoryRouteRequest,
        signals: InventoryRouteSignals,
    ) -> tuple[str, float, list[str]]:
        decision_factors: list[str] = []
        agentic_score = 0

        if signals.question_family == "planning_agentic_workflow":
            agentic_score += 3
            decision_factors.append("Classified as a workflow or action-planning question.")
        elif signals.question_family == "diagnosis_root_cause":
            agentic_score += 3
            decision_factors.append("Classified as a diagnosis or root-cause question.")
        elif signals.question_family == "comparison":
            agentic_score += 1
            decision_factors.append("Classified as a comparison question that may need structured side-by-side reasoning.")
        elif signals.question_family == "recommendation":
            decision_factors.append("Classified as a recommendation question.")
        elif signals.question_family == "exact_lookup":
            agentic_score -= 2
            decision_factors.append("Classified as a direct lookup question.")
        elif signals.question_family == "no_match_or_abstain":
            agentic_score -= 1
            decision_factors.append("Looks underspecified enough that clarification or abstain may be safer than deeper escalation.")

        if signals.needs_historical_data:
            agentic_score += 3
            decision_factors.append("Needs historical or over-time reasoning.")
        if signals.needs_cross_system_data:
            agentic_score += 3
            decision_factors.append("Needs signals beyond the mirrored inventory catalog.")
        if signals.needs_root_cause_reasoning:
            agentic_score += 2
            decision_factors.append("Looks like a root-cause or 'why' question.")
        if signals.needs_workflow_action:
            agentic_score += 2
            decision_factors.append("Looks like an action-planning or workflow question.")
        if signals.needs_multi_step_reasoning:
            agentic_score += 1
            decision_factors.append("May require multiple reasoning steps.")
        if signals.has_explicit_product_reference:
            agentic_score -= 2
            decision_factors.append("Has an explicit product reference, which normal RAG usually handles well.")
        if signals.simple_catalog_lookup:
            agentic_score -= 2
            decision_factors.append("Looks like a direct catalog lookup or support question.")
        if signals.is_small_talk:
            agentic_score -= 3
            decision_factors.append("Looks like conversational small talk.")
        if request.audience in {"manager", "operator"} and any(
            (
                signals.needs_historical_data,
                signals.needs_cross_system_data,
                signals.needs_workflow_action,
            )
        ):
            agentic_score += 1
            decision_factors.append("Internal operator/manager context supports deeper analysis.")
        if request.prefer_fast_response and agentic_score < 5:
            agentic_score -= 1
            decision_factors.append("Caller prefers fast responses when normal RAG is sufficient.")

        if not request.allow_agentic:
            decision_factors.append("Caller disabled agentic escalation.")
            return "normal_rag", 0.94 if signals.simple_catalog_lookup else 0.78, decision_factors

        if agentic_score >= 4:
            confidence = round(min(0.97, 0.62 + (agentic_score * 0.06)), 3)
            return "agentic", confidence, decision_factors

        confidence = round(
            min(
                0.96,
                0.72
                + (0.08 if signals.simple_catalog_lookup else 0.0)
                + (0.06 if signals.has_explicit_product_reference else 0.0)
                + (0.06 if signals.is_small_talk else 0.0),
            ),
            3,
        )
        return "normal_rag", confidence, decision_factors

    def _build_route_summary(
        self,
        *,
        recommended_path: str,
        signals: InventoryRouteSignals,
        missing_data_domains: list[str],
        prefer_fast_response: bool,
    ) -> str:
        if recommended_path == "normal_rag":
            if signals.is_small_talk:
                return "Use normal RAG because this is conversational and does not need deep multi-step reasoning."
            if signals.question_family == "comparison":
                return "Use normal RAG because this is a direct comparison question that the mirrored catalog should handle without agentic overhead."
            if signals.question_family == "recommendation":
                return "Use normal RAG because this recommendation can be grounded in the mirrored catalog without deeper workflow analysis."
            if signals.question_family == "no_match_or_abstain":
                return "Use normal RAG first because this looks like a clarification or abstain case rather than a workflow problem."
            if signals.has_explicit_product_reference:
                return "Use normal RAG because this looks like a direct product-level question that should be answered from the mirrored catalog."
            return (
                "Use normal RAG because this looks like a direct catalog/support question and should be answered quickly from the indexed inventory mirror."
                if prefer_fast_response
                else "Use normal RAG because the mirrored catalog should be enough to answer this question without agentic overhead."
            )

        if missing_data_domains:
            return (
                "Escalate to agentic handling because the question needs deeper cross-system or historical reasoning, "
                f"but the current context is still missing {self._natural_join(missing_data_domains)}."
            )
        if signals.question_family == "planning_agentic_workflow":
            return "Escalate to agentic handling because this question is asking for a concrete workflow or planning decision."
        if signals.question_family == "diagnosis_root_cause":
            return "Escalate to agentic handling because this question needs diagnosis and multi-step reasoning beyond direct catalog retrieval."
        return "Escalate to agentic handling because the question needs multi-step reasoning beyond straightforward catalog retrieval."

    def _build_agentic_execution_plan(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        low_stock_threshold: int,
        max_reasoning_steps: int,
        route_response: InventoryRouteResponse,
    ) -> InventoryAgenticExecutionPlan:
        signals = route_response.signals
        strategy = self._agentic_strategy(question=question, route_response=route_response)
        analysis_business_intent = self._agentic_business_intent(question=question, strategy=strategy)
        keyword_query = " ".join(self._extract_query_terms(question))
        normalized_question = self._normalize_conversation_text(question)
        steps: list[InventoryAgenticPlanStepSpec] = []
        analysis_actions: list[str] = []
        abstain_on_missing_domains = bool(
            route_response.missing_data_domains
            and (
                signals.needs_cross_system_data
                or signals.needs_historical_data
                or signals.question_family in {"planning_agentic_workflow", "diagnosis_root_cause"}
            )
        )

        if strategy == "compare":
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="find_comparison_candidates",
                    mode="search",
                    query_text=question,
                    filters=filters.model_copy(deep=True),
                )
            )
            if not signals.has_explicit_product_reference and keyword_query and keyword_query != normalized_question:
                steps.append(
                    InventoryAgenticPlanStepSpec(
                        action="expand_comparison_candidates",
                        mode="search",
                        query_text=keyword_query,
                        filters=filters.model_copy(deep=True),
                    )
                )
            analysis_actions.append("align_comparison_facts")
        elif strategy == "bundle":
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="find_bundle_primary",
                    mode="search",
                    query_text=question,
                    filters=filters.model_copy(deep=True),
                )
            )
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="find_compatible_add_ons",
                    mode="bundle_add_on_search",
                    query_text=question,
                    filters=filters.model_copy(deep=True),
                )
            )
            analysis_actions.append("filter_compatible_add_ons")
        elif strategy == "restock":
            low_stock_filters = filters.model_copy(deep=True)
            if low_stock_filters.max_stock is None:
                low_stock_filters.max_stock = low_stock_threshold
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="find_restock_candidates",
                    mode="search",
                    query_text=keyword_query or question,
                    filters=low_stock_filters,
                )
            )
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="business_signal_analysis",
                    mode="business",
                    query_text=f"business_signals:{analysis_business_intent or 'restock'}",
                    filters=low_stock_filters,
                )
            )
            analysis_actions.append("rank_operational_candidates")
        elif strategy == "diagnosis":
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="find_root_cause_candidates",
                    mode="search",
                    query_text=question,
                    filters=filters.model_copy(deep=True),
                )
            )
            if not signals.has_explicit_product_reference and keyword_query and keyword_query != normalized_question:
                steps.append(
                    InventoryAgenticPlanStepSpec(
                        action="focus_root_cause_candidates",
                        mode="search",
                        query_text=keyword_query,
                        filters=filters.model_copy(deep=True),
                    )
                )
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="business_signal_analysis",
                    mode="business",
                    query_text=f"business_signals:{analysis_business_intent or 'demand'}",
                    filters=filters.model_copy(deep=True),
                )
            )
            analysis_actions.append("diagnose_root_cause_facts")
        elif strategy == "operational_planning":
            planning_filters = filters.model_copy(deep=True)
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="find_operational_candidates",
                    mode="search",
                    query_text=keyword_query or question,
                    filters=planning_filters,
                )
            )
            if not signals.has_explicit_product_reference and keyword_query and keyword_query != normalized_question:
                steps.append(
                    InventoryAgenticPlanStepSpec(
                        action="expand_operational_candidates",
                        mode="search",
                        query_text=question,
                        filters=planning_filters,
                    )
                )
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="business_signal_analysis",
                    mode="business",
                    query_text=f"business_signals:{analysis_business_intent or 'demand'}",
                    filters=planning_filters,
                )
            )
            if signals.needs_root_cause_reasoning:
                analysis_actions.append("diagnose_root_cause_facts")
            analysis_actions.append("compose_operational_plan")
        else:
            steps.append(
                InventoryAgenticPlanStepSpec(
                    action="broad_inventory_search",
                    mode="search",
                    query_text=question,
                    filters=filters.model_copy(deep=True),
                )
            )
            if not signals.has_explicit_product_reference and keyword_query and keyword_query != normalized_question:
                steps.append(
                    InventoryAgenticPlanStepSpec(
                        action="keyword_focus_pass",
                        mode="search",
                        query_text=keyword_query,
                        filters=filters.model_copy(deep=True),
                    )
                )
            if signals.needs_workflow_action and self._has_any_phrase(
                normalized_question,
                ["restock", "reorder", "low stock", "running low"],
            ):
                low_stock_filters = filters.model_copy(deep=True)
                if low_stock_filters.max_stock is None:
                    low_stock_filters.max_stock = low_stock_threshold
                steps.append(
                    InventoryAgenticPlanStepSpec(
                        action="target_low_stock_scan",
                        mode="search",
                        query_text=keyword_query or question,
                        filters=low_stock_filters,
                    )
                )

        bounded_steps = tuple(steps[:max_reasoning_steps])
        max_analysis = max(0, max_reasoning_steps - len(bounded_steps))
        return InventoryAgenticExecutionPlan(
            strategy=strategy,
            search_steps=bounded_steps,
            analysis_actions=tuple(analysis_actions[:max_analysis]),
            abstain_on_missing_domains=abstain_on_missing_domains,
        )

    def _agentic_strategy(self, *, question: str, route_response: InventoryRouteResponse) -> str:
        normalized = self._normalize_conversation_text(question)
        business_intent = self._business_tool_intent(question)
        if route_response.signals.question_family == "comparison" or self._has_any_phrase(
            normalized,
            ["compare", "vs", "versus", "difference between", "which is better"],
        ):
            return "compare"
        if self._should_offer_cross_sell(question):
            return "bundle"
        if route_response.signals.question_family == "diagnosis_root_cause":
            return "diagnosis"
        if route_response.signals.question_family == "planning_agentic_workflow" and business_intent not in {
            "restock",
            "stockout_prevention",
        }:
            return "operational_planning"
        if business_intent == "restock" or self._has_any_phrase(
            normalized,
            ["restock", "reorder", "stockout", "running low", "low stock"],
        ):
            return "restock"
        return "default"

    def _agentic_business_intent(self, *, question: str, strategy: str) -> str | None:
        base_intent = self._business_tool_intent(question)
        normalized = self._normalize_conversation_text(question)
        if strategy in {"diagnosis", "operational_planning"}:
            if self._has_any_phrase(normalized, ["return rate", "returns", "returned"]):
                return "returns"
            if self._has_any_phrase(normalized, ["supplier", "vendor", "lead time", "lead-time", "delay", "delays"]):
                return "supplier_risk"
            if self._has_any_phrase(normalized, ["margin", "profit", "profitable"]):
                return "margin"
            if self._has_any_phrase(
                normalized,
                ["sales", "demand", "selling", "sold", "velocity", "trend", "drop", "dropping", "decline", "declining"],
            ):
                return "demand"
            if strategy == "diagnosis":
                return base_intent or "demand"
        return base_intent

    def _agentic_search_request_for_step(
        self,
        *,
        plan_step: InventoryAgenticPlanStepSpec,
        question: str,
        filters: InventorySearchFilters,
        top_k: int,
        hits_so_far: list[InventorySearchHit],
    ) -> InventorySearchRequest | None:
        if plan_step.mode == "bundle_add_on_search":
            primary = self._agentic_primary_hit_for_bundle(question=question, hits=hits_so_far, filters=filters)
            if primary is None:
                return None
            bundle_filters = (plan_step.filters or filters).model_copy(deep=True)
            bundle_filters.product_ids = []
            bundle_filters.categories = []
            query_text = self._bundle_add_on_query(primary=primary, question=question)
            return InventorySearchRequest(query_text=query_text, top_k=top_k, filters=bundle_filters)
        return InventorySearchRequest(
            query_text=plan_step.query_text or question,
            top_k=top_k,
            filters=(plan_step.filters or filters).model_copy(deep=True),
        )

    def _label_agentic_action(
        self,
        *,
        search_request: InventorySearchRequest,
        route_response: InventoryRouteResponse,
    ) -> str:
        if search_request.filters.max_stock is not None:
            return "target_low_stock_scan"
        if search_request.filters.categories:
            return "category_focus_pass"
        if route_response.signals.has_explicit_product_reference:
            return "targeted_product_lookup"
        if route_response.signals.needs_cross_system_data or route_response.signals.needs_historical_data:
            return "catalog_reconnaissance"
        return "broad_inventory_search"

    def _build_agentic_step_observation(
        self,
        *,
        step_number: int,
        request: InventorySearchRequest,
        route_response: InventoryRouteResponse,
        total_hits: int,
        selected_hits: list[InventorySearchHit],
        action: str | None = None,
    ) -> str:
        if total_hits == 0:
            return f"Step {step_number} found no supporting catalog hits for the current search angle."
        if action == "find_comparison_candidates":
            return (
                f"Step {step_number} found comparison candidates led by {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if action == "find_bundle_primary":
            return (
                f"Step {step_number} identified the bundle anchor candidate as {self._natural_join(hit.name for hit in selected_hits[:2])}."
            )
        if action == "find_compatible_add_ons":
            return (
                f"Step {step_number} searched for compatible add-ons and surfaced {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if action == "find_restock_candidates":
            return (
                f"Step {step_number} narrowed the catalog to restock candidates led by {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if action == "find_root_cause_candidates":
            return (
                f"Step {step_number} found root-cause candidates led by {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if action == "focus_root_cause_candidates":
            return (
                f"Step {step_number} tightened the diagnosis pass around {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if action == "find_operational_candidates":
            return (
                f"Step {step_number} gathered operational candidates led by {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if action == "expand_operational_candidates":
            return (
                f"Step {step_number} expanded the workflow candidate set and surfaced {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if route_response.signals.needs_historical_data or route_response.signals.needs_cross_system_data:
            return (
                f"Step {step_number} gathered {total_hits} catalog-backed product signal(s) while deeper external analysis remains required."
            )
        if request.filters.max_stock is not None:
            return (
                f"Step {step_number} narrowed the search to low-stock inventory and surfaced {self._natural_join(hit.name for hit in selected_hits[:3])}."
            )
        if request.filters.categories:
            return (
                f"Step {step_number} focused on {self._natural_join(request.filters.categories)} and found {total_hits} relevant item(s)."
            )
        return f"Step {step_number} found {total_hits} relevant catalog item(s) led by {self._natural_join(hit.name for hit in selected_hits[:3])}."

    def _business_tool_intent(self, question: str) -> str | None:
        normalized = self._normalize_conversation_text(question)
        if self._has_any_phrase(normalized, ["stockout", "stock out", "prevent stockout", "avoid stockout"]):
            return "stockout_prevention"
        if self._has_any_phrase(normalized, ["restock", "reorder", "running low", "low stock"]):
            return "restock"
        if self._has_any_phrase(normalized, ["supplier", "vendor", "lead time", "lead-time", "purchase order", "delay", "delays"]):
            return "supplier_risk"
        if self._has_any_phrase(normalized, ["margin", "profit", "profitable"]):
            return "margin"
        if self._has_any_phrase(normalized, ["return rate", "returns", "returned"]):
            return "returns"
        if self._has_any_phrase(normalized, ["customer segment", "customer segments", "segment", "segments"]):
            return "customer_segments"
        if self._has_any_phrase(normalized, ["demand", "sales", "sold", "selling", "velocity", "trend", "dropped", "drop", "dropping", "decline", "declining"]):
            return "demand"
        return None

    def _business_candidate_hits(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        business_signals: dict[str, InventoryBusinessSignalRecord],
        top_k: int,
    ) -> list[InventorySearchHit]:
        if not business_signals:
            return []
        catalog = self._load_catalog()
        candidate_tuples: list[tuple[InventorySearchHit, InventoryItemRecord, InventoryBusinessSignalRecord]] = []
        for signal in business_signals.values():
            item = catalog.get(signal.product_id)
            if item is None or not self._item_matches_filters(item, filters):
                continue
            hit = self._build_search_hit(item=item, score=0.0)
            candidate_tuples.append((hit, item, signal))
        ranked_hits = self.decision_scorer.rank_restock_candidates(candidates=candidate_tuples)
        business_intent = self._business_tool_intent(question)
        enriched_hits: list[InventorySearchHit] = []
        for hit in ranked_hits:
            score = self._decision_score(hit=hit, strategy="restock", fallback=hit.score)
            if score <= 0:
                continue
            evidence_scores = {
                **hit.evidence_scores,
                "business_signal_score": round(score, 4),
                "business_intent": business_intent,
                "business_reasons": hit.evidence_scores.get(
                    "deterministic_restock_reasons",
                    self._business_signal_reasons(
                        signal=business_signals[hit.product_id],
                        business_intent=business_intent,
                    ),
                ),
            }
            enriched_hits.append(hit.model_copy(update={"score": round(score, 4), "evidence_scores": evidence_scores}))
        return enriched_hits[:top_k]

    def _build_business_signal_observation(
        self,
        *,
        business_intent: str,
        selected_hits: list[InventorySearchHit],
        business_signals: dict[str, InventoryBusinessSignalRecord],
    ) -> str:
        if not selected_hits:
            return f"Business signal tool found no matched product signals for {business_intent}."
        summaries = [
            self._format_business_signal_summary(
                hit=hit,
                signal=business_signals[hit.product_id],
                include_margin=business_intent == "margin",
                include_supplier=business_intent in {"restock", "stockout_prevention", "supplier_risk"},
                include_returns=business_intent == "returns",
                include_segments=business_intent == "customer_segments",
            )
            for hit in selected_hits
            if hit.product_id in business_signals
        ]
        return (
            f"Business signal tool analyzed {business_intent.replace('_', ' ')} using "
            f"{self._natural_join(summaries)}."
        )

    def _build_business_tool_insight(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        business_signals: dict[str, InventoryBusinessSignalRecord],
        business_intent: str | None,
    ) -> InventoryBusinessInsight:
        if business_intent is None:
            return InventoryBusinessInsight()
        if not business_signals:
            return InventoryBusinessInsight(
                missing_facts=[
                    "Missing business signal mirror: sales, orders, supplier, margin, return, customer, or inventory snapshot data."
                ]
            )

        catalog = self._load_catalog()
        hits_with_signals = [hit for hit in hits if hit.product_id in business_signals]
        if business_intent in {"restock", "stockout_prevention"}:
            hits_with_signals = sorted(
                hits_with_signals,
                key=lambda hit: (
                    -self._decision_score(hit=hit, strategy="restock", fallback=hit.score),
                    hit.name.casefold(),
                ),
            )
        else:
            hits_with_signals = sorted(
                hits_with_signals,
                key=lambda hit: self._business_priority_score(
                    item=catalog[hit.product_id],
                    signal=business_signals[hit.product_id],
                    business_intent=business_intent,
                ),
                reverse=True,
            )
        if not hits_with_signals:
            return InventoryBusinessInsight(
                missing_facts=[f"No product-level business signals matched this {business_intent} question."]
            )

        selected_hits = hits_with_signals[:3]
        primary = selected_hits[0]
        primary_signal = business_signals[primary.product_id]
        reasoning_summary = [
            f"Used mirrored business signals for {self._natural_join(self._business_domains_available(business_signals))}.",
            self._build_business_signal_observation(
                business_intent=business_intent,
                selected_hits=selected_hits,
                business_signals=business_signals,
            ),
        ]
        addendum = self._business_insight_sentence(
            business_intent=business_intent,
            primary=primary,
            primary_signal=primary_signal,
            selected_hits=selected_hits,
            business_signals=business_signals,
        )
        return InventoryBusinessInsight(
            answer_addendum=addendum,
            reasoning_summary=reasoning_summary,
            selected_product_ids=[hit.product_id for hit in selected_hits],
        )

    def _align_agentic_reply_with_business_insight(
        self,
        *,
        reply: InventoryReply,
        hits: list[InventorySearchHit],
        business_insight: InventoryBusinessInsight,
        business_intent: str | None,
        question_family: str,
        strategy: str,
    ) -> InventoryReply:
        selected_ids = business_insight.selected_product_ids[:3]
        if strategy not in {"diagnosis", "operational_planning"} or not selected_ids:
            return reply

        primary_id = selected_ids[0]
        if reply.answer_plan.primary_product_id == primary_id and reply.recommended_product_ids == selected_ids:
            return reply

        primary_hit = next((hit for hit in hits if hit.product_id == primary_id), None)
        if primary_hit is None:
            return reply.model_copy(update={"recommended_product_ids": selected_ids})

        evidence_contract = reply.answer_plan.evidence_contract
        if evidence_contract is not None:
            ordered_candidate_ids = [primary_id, *[candidate_id for candidate_id in evidence_contract.primary_candidate_ids if candidate_id != primary_id]]
            evidence_contract = evidence_contract.model_copy(
                update={
                    "primary_product_id": primary_id,
                    "primary_candidate_ids": ordered_candidate_ids,
                }
            )

        reasoning_steps = list(reply.answer_plan.reasoning_steps)
        alignment_label = "diagnosis" if question_family == "diagnosis_root_cause" else "operational"
        alignment_step = (
            f"Aligned the {alignment_label} primary product to {primary_hit.name} because it has the strongest matched "
            f"{(business_intent or 'business').replace('_', ' ')} signal."
        )
        if alignment_step not in reasoning_steps:
            reasoning_steps.append(alignment_step)

        confidence_breakdown = dict(reply.answer_plan.confidence_breakdown)
        confidence_breakdown["diagnosis_business_signal_primary"] = {
            "product_id": primary_id,
            "intent": business_intent,
        }
        confidence_breakdown.pop("alternative", None)

        previous_primary_id = reply.answer_plan.primary_product_id
        reasoning_steps = [
            step
            for step in reasoning_steps
            if not step.startswith("Primary recommendation is ") and not step.startswith("Alternative is ")
        ]

        plan = reply.answer_plan.model_copy(
            update={
                "primary_product_id": primary_id,
                "alternative_product_ids": [],
                "primary_reason": (
                    f"{primary_hit.name} carries the strongest matched "
                    f"{(business_intent or 'business').replace('_', ' ')} signal in the business mirror."
                ),
                "alternative_reason": None,
                "tradeoffs": [],
                "strategy": strategy,
                "reasoning_steps": reasoning_steps,
                "confidence_breakdown": confidence_breakdown,
                "evidence_contract": evidence_contract,
            }
        )
        aligned_reply = reply.model_copy(
            update={
                "recommended_product_ids": selected_ids,
                "answer_plan": plan,
                "verification": self._verify_answer_plan(answer_plan=plan, hits=hits),
            }
        )
        if aligned_reply.verification.requires_abstention and not plan.abstain:
            return self._build_hard_constraint_abstain_reply(reply=aligned_reply)
        return aligned_reply

    def _business_insight_sentence(
        self,
        *,
        business_intent: str,
        primary: InventorySearchHit,
        primary_signal: InventoryBusinessSignalRecord,
        selected_hits: list[InventorySearchHit],
        business_signals: dict[str, InventoryBusinessSignalRecord],
    ) -> str:
        primary_summary = self._format_business_signal_summary(
            hit=primary,
            signal=primary_signal,
            include_margin=business_intent == "margin",
            include_supplier=business_intent in {"restock", "stockout_prevention", "supplier_risk"},
            include_returns=business_intent == "returns",
            include_segments=business_intent == "customer_segments",
        )
        other_names = [hit.name for hit in selected_hits[1:3]]
        next_clause = f" Next items to review are {self._natural_join(other_names)}." if other_names else ""
        if business_intent in {"restock", "stockout_prevention"}:
            return (
                f"Business-tool read: prioritize {primary.name} because its operational signal is strongest: "
                f"{primary_summary}.{next_clause}"
            )
        if business_intent == "demand":
            return f"Demand read: {primary_summary} is the strongest demand signal in the matched set.{next_clause}"
        if business_intent == "margin":
            return f"Margin read: {primary_summary} gives the clearest margin-aware signal among the matched products.{next_clause}"
        if business_intent == "supplier_risk":
            return f"Supplier-risk read: {primary_summary}; avoid promising fast replenishment unless the main backend confirms purchase-order timing.{next_clause}"
        if business_intent == "returns":
            return f"Returns read: {primary_summary}; review quality or expectation-setting before pushing it harder.{next_clause}"
        if business_intent == "customer_segments":
            return f"Customer-segment read: {primary_summary}; use those segments to frame the next recommendation.{next_clause}"
        return f"Business-tool read: {primary_summary}.{next_clause}"

    def _format_business_signal_summary(
        self,
        *,
        hit: InventorySearchHit,
        signal: InventoryBusinessSignalRecord,
        include_margin: bool,
        include_supplier: bool,
        include_returns: bool,
        include_segments: bool,
    ) -> str:
        parts = [hit.name]
        if signal.units_sold is not None:
            parts.append(f"sold quantity {signal.units_sold}")
        if signal.order_count is not None:
            parts.append(f"order count {signal.order_count}")
        if signal.demand_score is not None:
            parts.append(f"demand score {signal.demand_score:.2f}")
        if signal.inventory_on_hand is not None:
            parts.append(f"business snapshot inventory level {signal.inventory_on_hand}")
        if include_supplier and signal.supplier_lead_time_days is not None:
            parts.append(f"supplier lead time {signal.supplier_lead_time_days} day(s)")
        if include_supplier and signal.supplier_risk_score is not None:
            parts.append(f"supplier risk {signal.supplier_risk_score:.2f}")
        if include_margin and signal.gross_margin_rate is not None:
            parts.append(f"margin rate {self._format_business_percent(signal.gross_margin_rate)}")
        if include_returns and signal.return_rate is not None:
            parts.append(f"return rate {self._format_business_percent(signal.return_rate)}")
        if include_segments and signal.customer_segments:
            parts.append(f"customer segments {self._natural_join(signal.customer_segments[:3])}")
        return ", ".join(parts)

    def _business_priority_score(
        self,
        *,
        item: InventoryItemRecord,
        signal: InventoryBusinessSignalRecord,
        business_intent: str | None,
    ) -> float:
        if not self._business_signal_has_value(signal):
            return 0.0
        score = 0.12
        if signal.demand_score is not None:
            score += signal.demand_score * 0.35
        if signal.units_sold is not None:
            score += min(signal.units_sold / 80.0, 1.0) * 0.25
        inventory_level = signal.inventory_on_hand if signal.inventory_on_hand is not None else item.stock
        if inventory_level <= 0:
            score += 0.28
        elif inventory_level <= 5:
            score += 0.22
        elif inventory_level <= 10:
            score += 0.14
        if signal.supplier_lead_time_days is not None:
            lead_time_score = min(signal.supplier_lead_time_days / 45.0, 1.0)
            score += lead_time_score * (0.2 if business_intent in {"restock", "stockout_prevention", "supplier_risk"} else 0.08)
        if signal.supplier_risk_score is not None and business_intent == "supplier_risk":
            score += signal.supplier_risk_score * 0.22
        if signal.gross_margin_rate is not None and business_intent == "margin":
            score += max(0.0, signal.gross_margin_rate) * 0.28
        if signal.return_rate is not None:
            if business_intent == "returns":
                score += signal.return_rate * 0.25
            else:
                score -= signal.return_rate * 0.12
        return round(max(0.0, min(0.99, score)), 4)

    @staticmethod
    def _business_signal_has_value(signal: InventoryBusinessSignalRecord) -> bool:
        return any(
            value is not None
            for value in (
                signal.units_sold,
                signal.revenue,
                signal.order_count,
                signal.return_count,
                signal.return_rate,
                signal.gross_margin,
                signal.gross_margin_rate,
                signal.inventory_on_hand,
                signal.supplier_lead_time_days,
                signal.supplier_risk_score,
                signal.demand_score,
            )
        ) or bool(signal.supplier_id or signal.supplier_name or signal.customer_segments)

    def _business_signal_reasons(
        self,
        *,
        signal: InventoryBusinessSignalRecord,
        business_intent: str | None,
    ) -> list[str]:
        reasons: list[str] = []
        if signal.units_sold is not None:
            reasons.append(f"sales quantity signal: {signal.units_sold}")
        if signal.order_count is not None:
            reasons.append(f"order count signal: {signal.order_count}")
        if signal.inventory_on_hand is not None:
            reasons.append(f"inventory snapshot signal: {signal.inventory_on_hand}")
        if signal.supplier_lead_time_days is not None:
            reasons.append(f"supplier lead time signal: {signal.supplier_lead_time_days} day(s)")
        if signal.gross_margin_rate is not None:
            reasons.append(f"margin rate signal: {self._format_business_percent(signal.gross_margin_rate)}")
        if signal.return_rate is not None:
            reasons.append(f"return rate signal: {self._format_business_percent(signal.return_rate)}")
        if signal.customer_segments:
            reasons.append(f"customer segment signal: {self._natural_join(signal.customer_segments[:3])}")
        if business_intent:
            reasons.append(f"business intent: {business_intent}")
        return reasons

    @staticmethod
    def _format_business_percent(value: float) -> str:
        return f"{value * 100:.1f}%"

    def _compose_agentic_answer(
        self,
        *,
        base_answer: str,
        route_response: InventoryRouteResponse,
        missing_facts: list[str],
        business_insight: InventoryBusinessInsight | None = None,
    ) -> str:
        answer_parts: list[str] = []
        if route_response.recommended_path == "agentic":
            answer_parts.append("I used a multi-step inventory reasoning pass for this question.")
        if missing_facts:
            readable_missing = [fact.removeprefix("Missing data domain: ").replace("_", " ") for fact in missing_facts]
            answer_parts.append(
                f"I can only answer part of it from the current catalog mirror because I do not have {self._natural_join(readable_missing)} in this agent yet."
            )
        answer_parts.append(base_answer)
        if business_insight and business_insight.answer_addendum:
            answer_parts.append(business_insight.answer_addendum)
        return " ".join(part for part in answer_parts if part)

    @staticmethod
    def _adjust_agentic_confidence(
        *,
        confidence_score: float,
        missing_facts: list[str],
        retrieval_steps: int,
    ) -> float:
        adjusted = confidence_score
        if missing_facts:
            adjusted -= min(0.35, 0.1 * len(missing_facts))
        if retrieval_steps > 1:
            adjusted = min(1.0, adjusted + 0.05)
        return round(max(0.0, adjusted), 3)

    def _build_abstention_reason(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
    ) -> str | None:
        if hits:
            return None
        return self._build_exact_no_match_answer(question=question) or "No reliable catalog evidence was found for this request."

    def _build_no_match_or_abstain_reply(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
        filters: InventorySearchFilters,
        hits: list[InventorySearchHit],
        route_signals: InventoryRouteSignals,
    ) -> tuple[InventoryReply, list[InventorySearchHit], float, str | None] | None:
        if route_signals.question_family != "no_match_or_abstain":
            return None

        normalized = self._normalize_conversation_text(question)
        inventory_like = self._looks_like_inventory_request(normalized)
        clarification_question = self._build_clarification_question(
            question=question,
            assistant_mode=assistant_mode,
            hits=hits,
            filters=filters,
        )
        has_structured_constraints = any(
            (
                filters.product_ids,
                filters.categories,
                filters.brands,
                filters.tags,
                filters.min_stock is not None,
                filters.max_stock is not None,
                filters.min_price is not None,
                filters.max_price is not None,
            )
        )
        top_hit = hits[0] if hits else None
        weak_top_hit = top_hit is None or top_hit.score < 0.6 or self._quality_score(top_hit) < 5
        base_reason = route_signals.family_reasons[0] if route_signals.family_reasons else (
            "Question was classified as a clarification or abstain case before answer generation."
        )

        should_clarify = clarification_question is not None and (
            self._should_prioritize_clarification(question=question, filters=filters)
            or (inventory_like and (not has_structured_constraints or weak_top_hit))
        )
        if should_clarify:
            if assistant_mode == "sales":
                answer = "I can help with that, but I need one more detail before I make a grounded recommendation."
            else:
                answer = "I can help with that, but I need one more detail before I narrow the inventory down safely."
            answer += f" {clarification_question}"
            reasoning_steps = [
                base_reason,
                "Held back weak retrieval guesses until the question includes a clearer product, category, budget, or brand constraint.",
            ]
            plan = self._build_inventory_answer_plan(
                intent=f"{assistant_mode}_no_match",
                primary=None,
                abstain=False,
                reasoning_steps=reasoning_steps,
            )
            reply = self._enrich_reply_plan(
                reply=InventoryReply(
                    answer=answer,
                    follow_up_question=clarification_question,
                    answer_plan=plan,
                    verification=self._verify_answer_plan(answer_plan=plan, hits=[]),
                ),
                question=question,
                filters=filters,
                hits=[],
                strategy="no_match_or_abstain",
            )
            return reply, [], 0.42, None

        exact_no_match = self._build_exact_no_match_answer(question=question)
        if exact_no_match:
            abstention_reason = exact_no_match
        elif inventory_like:
            abstention_reason = "I do not have enough grounded catalog evidence to answer that safely yet."
        else:
            abstention_reason = "That does not map cleanly to a supported inventory question I can answer from the current catalog."

        answer = abstention_reason
        if reply_style == "detailed" and clarification_question and inventory_like:
            answer += f" {clarification_question}"
        reasoning_steps = [
            base_reason,
            "Returned abstain behavior because the request could not be grounded in a reliable inventory answer path.",
        ]
        plan = self._build_inventory_answer_plan(
            intent=f"{assistant_mode}_no_match",
            primary=None,
            abstain=True,
            abstention_reason=abstention_reason,
            reasoning_steps=reasoning_steps,
        )
        reply = self._enrich_reply_plan(
            reply=InventoryReply(
                answer=answer,
                follow_up_question=clarification_question if inventory_like else None,
                answer_plan=plan,
                verification=self._verify_answer_plan(answer_plan=plan, hits=[]),
            ),
            question=question,
            filters=filters,
            hits=[],
            strategy="no_match_or_abstain",
        )
        return reply, [], 0.24, abstention_reason

    def _finalize_inventory_reply(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
        requested_answer_engine: str,
        confidence_score: float,
        hits: list[InventorySearchHit],
        base_reply: InventoryReply,
        conversation_history: list[InventoryConversationTurn],
        conversation_summary: str | None,
        abstention_reason: str | None,
        execution_path: str,
        reasoning_summary: list[str] | None = None,
        missing_facts: list[str] | None = None,
        memory_resolution: InventoryMemoryResolution | None = None,
    ) -> tuple[InventoryReply, str, bool, str | None, str | None]:
        resolved_abstention_reason = abstention_reason or base_reply.answer_plan.abstention_reason
        abstained = bool(resolved_abstention_reason) or base_reply.answer_plan.abstain
        if abstained and resolved_abstention_reason is None:
            resolved_abstention_reason = "I do not have a reliable catalog fit that satisfies the required constraints."
        answer_engine = self._resolve_inventory_answer_engine(
            requested_answer_engine=requested_answer_engine,
            confidence_score=confidence_score,
            hits=hits,
            abstention_reason=resolved_abstention_reason if abstained else None,
        )
        if answer_engine != "natural":
            verified_base_reply = self._with_final_answer_verification(reply=base_reply, hits=hits)
            if self._verified_reply_is_acceptable(reply=verified_base_reply):
                return verified_base_reply, "deterministic", abstained, resolved_abstention_reason, None
            safe_reply = self._build_safe_final_answer_reply(
                base_reply=verified_base_reply,
                hits=hits,
                reason="The deterministic answer did not pass final answer verification.",
            )
            return safe_reply, "deterministic", True, safe_reply.answer_plan.abstention_reason, None

        synthesized_reply, natural_fallback_reason = self._synthesize_inventory_reply(
            question=question,
            assistant_mode=assistant_mode,
            reply_style=reply_style,
            confidence_score=confidence_score,
            hits=hits,
            base_reply=base_reply,
            conversation_history=conversation_history,
            conversation_summary=conversation_summary,
            execution_path=execution_path,
            reasoning_summary=reasoning_summary or [],
            missing_facts=missing_facts or [],
            memory_resolution=memory_resolution,
        )
        if synthesized_reply is None:
            verified_base_reply = self._with_final_answer_verification(reply=base_reply, hits=hits)
            return (
                verified_base_reply,
                "deterministic",
                abstained,
                resolved_abstention_reason,
                natural_fallback_reason or "Natural answer model failed; deterministic fallback was used.",
            )
        if synthesized_reply.abstained or not synthesized_reply.answer.strip():
            verified_base_reply = self._with_final_answer_verification(reply=base_reply, hits=hits)
            fallback_reason = synthesized_reply.abstention_reason or (
                "Natural answer model returned no usable content; deterministic fallback was used."
            )
            return verified_base_reply, "deterministic", abstained, resolved_abstention_reason, fallback_reason

        natural_reply = InventoryReply(
            answer=synthesized_reply.answer.strip(),
            recommended_product_ids=base_reply.recommended_product_ids,
            cross_sell_product_ids=base_reply.cross_sell_product_ids,
            follow_up_question=synthesized_reply.follow_up_question or base_reply.follow_up_question,
            answer_plan=base_reply.answer_plan,
            verification=base_reply.verification,
        )
        verified_natural_reply = self._with_final_answer_verification(reply=natural_reply, hits=hits)
        if verified_natural_reply.verification.passed:
            return verified_natural_reply, "natural", False, None, None

        logger.warning(
            "Inventory natural answer failed final verification; falling back to deterministic answer. issues=%s",
            verified_natural_reply.verification.final_answer_issues,
        )
        verified_base_reply = self._with_final_answer_verification(reply=base_reply, hits=hits)
        if self._verified_reply_is_acceptable(reply=verified_base_reply):
            return (
                verified_base_reply,
                "deterministic",
                abstained,
                resolved_abstention_reason,
                "Natural answer failed final answer verification; deterministic fallback was used.",
            )

        safe_reply = self._build_safe_final_answer_reply(
            base_reply=verified_base_reply,
            hits=hits,
            reason="Both natural and deterministic answers failed final answer verification.",
        )
        return (
            safe_reply,
            "deterministic",
            True,
            safe_reply.answer_plan.abstention_reason,
            "Both natural and deterministic answers failed final answer verification.",
        )

    def _with_final_answer_verification(
        self,
        *,
        reply: InventoryReply,
        hits: list[InventorySearchHit],
    ) -> InventoryReply:
        final_verification = self.final_answer_verifier.verify(
            answer=reply.answer,
            answer_plan=reply.answer_plan,
            hits=hits,
        )
        existing_verification = reply.verification
        issues = self._dedupe_verification_issues(
            [
                *existing_verification.issues,
                *final_verification.final_answer_issues,
            ]
        )
        verification = InventoryAnswerVerification(
            passed=existing_verification.passed and final_verification.passed,
            issues=issues,
            hard_constraint_issues=existing_verification.hard_constraint_issues,
            requires_abstention=existing_verification.requires_abstention,
            checked_final_answer=True,
            final_answer_issues=final_verification.final_answer_issues,
        )
        return reply.model_copy(update={"verification": verification})

    @staticmethod
    def _verified_reply_is_acceptable(
        *,
        reply: InventoryReply,
    ) -> bool:
        if reply.verification.passed:
            return True
        return reply.answer_plan.abstain and not reply.verification.final_answer_issues

    def _build_safe_final_answer_reply(
        self,
        *,
        base_reply: InventoryReply,
        hits: list[InventorySearchHit],
        reason: str,
    ) -> InventoryReply:
        plan = base_reply.answer_plan.model_copy(
            update={
                "abstain": True,
                "abstention_reason": reason,
                "risk_notes": self._dedupe_verification_issues([*base_reply.answer_plan.risk_notes, reason]),
            }
        )
        answer = (
            "I need to be careful here: the generated inventory answer did not pass final verification. "
            "Please ask again with a product name, category, budget, or stock question and I will answer from verified catalog data."
        )
        safe_reply = InventoryReply(
            answer=answer,
            recommended_product_ids=[],
            cross_sell_product_ids=[],
            follow_up_question="What exact product, category, budget, or stock question should I verify?",
            answer_plan=plan,
            verification=base_reply.verification,
        )
        return self._with_final_answer_verification(reply=safe_reply, hits=hits)

    @staticmethod
    def _dedupe_verification_issues(issues: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for issue in issues:
            if issue in seen:
                continue
            seen.add(issue)
            deduped.append(issue)
        return deduped

    def _resolve_inventory_answer_engine(
        self,
        *,
        requested_answer_engine: str,
        confidence_score: float,
        hits: list[InventorySearchHit],
        abstention_reason: str | None,
    ) -> str:
        if requested_answer_engine == "deterministic":
            return "deterministic"
        if abstention_reason is not None or not hits:
            return "deterministic"
        if not self.config.natural_answers_enabled:
            return "deterministic"
        if confidence_score < self.config.natural_answer_min_confidence:
            return "deterministic"
        if requested_answer_engine in {"auto", "natural"}:
            return "natural"
        return "deterministic"

    def _synthesize_inventory_reply(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
        confidence_score: float,
        hits: list[InventorySearchHit],
        base_reply: InventoryReply,
        conversation_history: list[InventoryConversationTurn],
        conversation_summary: str | None,
        execution_path: str,
        reasoning_summary: list[str],
        missing_facts: list[str],
        memory_resolution: InventoryMemoryResolution | None,
    ) -> tuple[InventoryNaturalAnswer | None, str | None]:
        try:
            raw_output = self._run_inventory_answer_model(
                question=question,
                assistant_mode=assistant_mode,
                reply_style=reply_style,
                confidence_score=confidence_score,
                hits=hits,
                base_reply=base_reply,
                conversation_history=conversation_history,
                conversation_summary=conversation_summary,
                execution_path=execution_path,
                reasoning_summary=reasoning_summary,
                missing_facts=missing_facts,
                memory_resolution=memory_resolution,
            )
        except httpx.TimeoutException:
            reason = (
                f"Natural answer model timed out after {self.config.natural_answer_timeout_seconds:g}s; "
                "deterministic fallback was used."
            )
            logger.warning(reason)
            return None, reason
        except httpx.HTTPError as exc:
            reason = "Natural answer model request failed; deterministic fallback was used."
            logger.warning("%s error=%s", reason, exc)
            return None, reason
        except Exception:
            reason = "Natural answer synthesis failed; deterministic fallback was used."
            logger.exception(reason)
            return None, reason

        parsed_reply = self._parse_inventory_answer_model_output(raw_output)
        if parsed_reply is None:
            reason = "Natural answer model returned invalid structured output; deterministic fallback was used."
            logger.warning(reason)
            return None, reason
        return parsed_reply, None

    def _build_inventory_answer_messages(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
        confidence_score: float,
        hits: list[InventorySearchHit],
        base_reply: InventoryReply,
        conversation_history: list[InventoryConversationTurn],
        conversation_summary: str | None,
        execution_path: str,
        reasoning_summary: list[str],
        missing_facts: list[str],
        memory_resolution: InventoryMemoryResolution | None,
    ) -> list[ChatMessage]:
        answer_plan_payload = base_reply.answer_plan.model_dump(mode="json")
        verification_payload = base_reply.verification.model_dump(mode="json")
        allowed_product_ids = self._allowed_answer_product_ids(
            hits=hits,
            answer_plan=base_reply.answer_plan,
        )
        evidence_payload = {
            "question": question,
            "assistant_mode": assistant_mode,
            "reply_style": reply_style,
            "execution_path": execution_path,
            "confidence_score": confidence_score,
            "conversation_summary": conversation_summary,
            "conversation_history": [
                turn.model_dump(mode="json")
                for turn in self._trim_conversation_history(conversation_history)
            ],
            "memory_resolution": (memory_resolution or InventoryMemoryResolution()).model_dump(mode="json"),
            "draft_reply": {
                "answer": base_reply.answer,
                "follow_up_question": base_reply.follow_up_question,
                "recommended_product_ids": base_reply.recommended_product_ids,
                "cross_sell_product_ids": base_reply.cross_sell_product_ids,
            },
            "writer_contract": {
                "decision_authority": "answer_plan",
                "allowed_product_ids": allowed_product_ids,
                "primary_product_id": base_reply.answer_plan.primary_product_id,
                "alternative_product_ids": base_reply.answer_plan.alternative_product_ids,
                "cross_sell_product_ids": base_reply.answer_plan.cross_sell_product_ids,
                "excluded_product_ids": base_reply.answer_plan.excluded_product_ids,
                "required_tradeoffs": base_reply.answer_plan.tradeoffs,
                "risk_notes": base_reply.answer_plan.risk_notes,
                "next_best_question": base_reply.answer_plan.next_best_question,
                "abstain": base_reply.answer_plan.abstain,
                "abstention_reason": base_reply.answer_plan.abstention_reason,
            },
            "answer_plan": answer_plan_payload,
            "verification": verification_payload,
            "reasoning_summary": reasoning_summary,
            "missing_facts": missing_facts,
            "hits": self._serialize_inventory_hits(hits),
        }
        system_prompt = (
            "You are the natural-language writer for a grounded ecommerce inventory assistant. "
            "The system has already decided what to recommend. Your job is to express that decision clearly, naturally, and safely. "
            "Decision hierarchy: answer_plan is authoritative, writer_contract is binding, catalog hits are factual evidence, draft_reply is wording guidance, and conversation history is context only. "
            "Do not choose products, reorder product roles, add products, remove required caveats, or override answer_plan. "
            "Use answer_plan.primary_reason, alternative_reason, cross_sell_reason, tradeoffs, risk_notes, next_best_question, and confidence_breakdown when they are present. "
            "If answer_plan.tradeoffs contains caveats, include the important caveat in plain language, especially for nearby alternatives and cross-sells. "
            "If answer_plan.abstain is true or verification.passed is false, be cautious and do not expand into a recommendation. "
            "Never recommend, pitch, substitute, or cross-sell a product in writer_contract.excluded_product_ids. "
            "Never treat writer_contract.cross_sell_product_ids as substitutes or replacements; they are add-ons only. "
            "Never present a nearby product-family alternative as an exact substitute unless answer_plan says it is exact. "
            "Do not invent products, prices, stock levels, brands, categories, warranties, shipping, discounts, policies, specs, or features. "
            "Use attributes, metadata, and evidence_scores only if they appear in the evidence package. "
            "Do not expose internal database implementation details, raw IDs, or the phrase 'answer_plan' to the user. "
            "Ask at most one follow-up question, and prefer writer_contract.next_best_question. "
            "Keep short replies concise and human. Keep detailed replies richer but not rambling. "
            "Return only strict JSON with exactly this schema: "
            '{"answer":"...", "follow_up_question":null, "abstained":false, "abstention_reason":null}. '
            "No markdown, no extra keys, no commentary outside JSON."
        )
        if assistant_mode == "sales":
            system_prompt += (
                " In sales mode, sound helpful and persuasive, handle the buyer concern directly, and keep staff-facing coaching practical without overclaiming."
            )
        else:
            system_prompt += " In support mode, sound clear, calm, factual, and operationally reliable."
        user_prompt = (
            "Write the final customer-facing answer from this evidence package. "
            "Follow the writer_contract and answer_plan exactly.\n\n"
            "Evidence package:\n"
            f"{json.dumps(evidence_payload, ensure_ascii=False, indent=2)}"
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

    @staticmethod
    def _allowed_answer_product_ids(
        *,
        hits: list[InventorySearchHit],
        answer_plan: InventoryAnswerPlan,
    ) -> list[str]:
        allowed: list[str] = []
        for product_id in [
            answer_plan.primary_product_id,
            *answer_plan.alternative_product_ids,
            *answer_plan.cross_sell_product_ids,
            *(hit.product_id for hit in hits[:5]),
        ]:
            if not product_id or product_id in answer_plan.excluded_product_ids or product_id in allowed:
                continue
            allowed.append(product_id)
        return allowed

    def _serialize_inventory_hits(self, hits: list[InventorySearchHit], limit: int = 5) -> list[dict[str, object]]:
        serialized_hits: list[dict[str, object]] = []
        for hit in hits[:limit]:
            serialized_hits.append(
                {
                    "product_id": hit.product_id,
                    "sku": hit.sku,
                    "name": hit.name,
                    "category": hit.category,
                    "brand": hit.brand,
                    "status": hit.status,
                    "price": hit.price,
                    "currency": hit.currency,
                    "stock": hit.stock,
                    "tags": hit.tags,
                    "snippet": hit.snippet,
                    "attributes": hit.attributes,
                    "metadata": hit.metadata,
                    "evidence_scores": hit.evidence_scores,
                    "score": hit.score,
                }
            )
        return serialized_hits

    def _trim_conversation_history(
        self,
        conversation_history: list[InventoryConversationTurn],
    ) -> list[InventoryConversationTurn]:
        if self.config.conversation_history_limit <= 0:
            return []
        return conversation_history[-self.config.conversation_history_limit :]

    def _run_inventory_answer_model(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
        confidence_score: float,
        hits: list[InventorySearchHit],
        base_reply: InventoryReply,
        conversation_history: list[InventoryConversationTurn],
        conversation_summary: str | None,
        execution_path: str,
        reasoning_summary: list[str],
        missing_facts: list[str],
        memory_resolution: InventoryMemoryResolution | None,
    ) -> str:
        options = build_generation_options(
            model_name=self.config.natural_answer_model_name or None,
        ).model_copy(
            update={
                "temperature": self.config.natural_answer_temperature,
                "max_generation_tokens": self.config.natural_answer_max_tokens,
            }
        )
        messages = self._build_inventory_answer_messages(
            question=question,
            assistant_mode=assistant_mode,
            reply_style=reply_style,
            confidence_score=confidence_score,
            hits=hits,
            base_reply=base_reply,
            conversation_history=conversation_history,
            conversation_summary=conversation_summary,
            execution_path=execution_path,
            reasoning_summary=reasoning_summary,
            missing_facts=missing_facts,
            memory_resolution=memory_resolution,
        )
        client = get_chat_client(options)
        return client.complete(
            messages=messages,
            model_name=options.model_name,
            temperature=options.temperature,
            max_tokens=options.max_generation_tokens,
            timeout_seconds=self.config.natural_answer_timeout_seconds,
            response_format={"type": "json_object"},
        )

    def _parse_inventory_answer_model_output(self, raw_output: str) -> InventoryNaturalAnswer | None:
        stripped_output = raw_output.strip()
        candidates = [stripped_output]
        unfenced_output = self._strip_json_code_fence(stripped_output)
        if unfenced_output != stripped_output:
            candidates.append(unfenced_output)
        extracted_json = self._extract_first_json_object(unfenced_output)
        if extracted_json and extracted_json not in candidates:
            candidates.append(extracted_json)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if parsed.get("abstained") and not parsed.get("answer") and parsed.get("abstention_reason"):
                parsed["answer"] = parsed["abstention_reason"]
            try:
                return InventoryNaturalAnswer.model_validate(parsed)
            except Exception:
                continue
        return None

    @staticmethod
    def _strip_json_code_fence(text: str) -> str:
        stripped = text.strip()
        fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            return fence_match.group(1).strip()
        return stripped

    @staticmethod
    def _extract_first_json_object(text: str) -> str | None:
        start_index = text.find("{")
        if start_index < 0:
            return None
        depth = 0
        in_string = False
        escape_next = False
        for index, char in enumerate(text[start_index:], start=start_index):
            if in_string:
                if escape_next:
                    escape_next = False
                elif char == "\\":
                    escape_next = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start_index:index + 1]
        return None

    def _build_normal_rag_contract(self, *, request: InventoryRouteRequest) -> InventoryExecutionContract:
        return InventoryExecutionContract(
            mode="normal_rag",
            implementation_status="implemented",
            target_system="rag_sidecar",
            method="POST",
            endpoint="/inventory/ask",
            purpose="Fast support or sales response grounded in the mirrored inventory catalog.",
            payload_template={
                "question": request.question,
                "assistant_mode": request.assistant_mode,
                "reply_style": request.reply_style,
                "top_k": self.config.default_top_k,
                "filters": request.filters.model_dump(mode="json"),
            },
            notes=[
                "Use this for product lookup, pricing, availability, recommendations, and direct support questions.",
                "This is the default customer-facing path because it is faster and more predictable than agentic execution.",
            ],
        )

    def _build_agentic_contract(
        self,
        *,
        request: InventoryRouteRequest,
        required_data_domains: list[str],
        missing_data_domains: list[str],
    ) -> InventoryExecutionContract:
        notes = [
            "Call this server-side or through the main backend proxy, not directly from browser code if you want to keep the API key private.",
            "This endpoint performs bounded multi-step retrieval over the mirrored inventory catalog.",
            "Use normal RAG as the fallback if this path is unavailable or too slow.",
        ]
        if missing_data_domains:
            notes.append(
                f"To answer this well, the agentic backend still needs {self._natural_join(missing_data_domains)}."
            )
        return InventoryExecutionContract(
            mode="agentic",
            implementation_status="implemented",
            target_system="rag_sidecar",
            method="POST",
            endpoint="/inventory/agentic/ask",
            purpose="Inventory agentic path for bounded multi-step reasoning, trace capture, and deeper catalog-backed analysis.",
            payload_template={
                "question": request.question,
                "assistant_mode": request.assistant_mode,
                "reply_style": request.reply_style,
                "audience": request.audience,
                "max_reasoning_steps": self.config.default_agentic_max_reasoning_steps,
                "available_data_domains": request.available_data_domains,
                "filters": request.filters.model_dump(mode="json"),
            },
            notes=notes,
        )

    def _order_hits_for_assistant(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        low_stock_threshold: int,
        assistant_mode: str,
    ) -> list[InventorySearchHit]:
        if assistant_mode == "sales":
            sales_style = self._classify_sales_style(question=question, filters=filters)
            return self._rank_sales_hits(hits=hits, sales_style=sales_style)
        return self._rank_support_hits(
            question=question,
            hits=hits,
            filters=filters,
            low_stock_threshold=low_stock_threshold,
        )

    def _build_answer(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        low_stock_threshold: int,
        assistant_mode: str,
        reply_style: str,
    ) -> InventoryReply:
        plan_hits = hits
        if assistant_mode == "sales":
            sales_style = self._classify_sales_style(question=question, filters=filters)
            plan_hits = self._rank_sales_hits(hits=hits, sales_style=sales_style)
            reply = self._build_sales_answer(
                question=question,
                hits=plan_hits,
                filters=filters,
                low_stock_threshold=low_stock_threshold,
                reply_style=reply_style,
            )
            plan_hits = self._annotate_sales_alternative_scores(
                hits=plan_hits,
                primary_product_id=reply.answer_plan.primary_product_id,
                sales_style=sales_style,
            )
        else:
            reply = self._build_support_answer(
                question=question,
                hits=hits,
                filters=filters,
                low_stock_threshold=low_stock_threshold,
                reply_style=reply_style,
        )
        return self._enrich_reply_plan(
            reply=reply,
            question=question,
            filters=filters,
            hits=plan_hits,
            strategy=reply.answer_plan.intent if reply.answer_plan.intent != "unknown" else assistant_mode,
        )

    def _build_agentic_compare_reply(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        reply_style: str,
    ) -> InventoryReply:
        if len(hits) < 2:
            return self._build_answer(
                question=question,
                hits=hits,
                filters=filters,
                low_stock_threshold=self.config.low_stock_threshold,
                assistant_mode="support",
                reply_style=reply_style,
            )
        ranked_hits, primary, alternative = self.decision_scorer.select_comparison_pair(hits=hits)
        if primary is None or alternative is None:
            return self._build_answer(
                question=question,
                hits=ranked_hits or hits,
                filters=filters,
                low_stock_threshold=self.config.low_stock_threshold,
                assistant_mode="support",
                reply_style=reply_style,
            )
        primary_score = self._decision_score(hit=primary, strategy="comparison", fallback=primary.score)
        alternative_score = self._decision_score(hit=alternative, strategy="comparison", fallback=alternative.score)
        answer_parts = [
            f"Best side-by-side comparison: {self._format_option_label(primary)} versus {self._format_option_label(alternative)}."
        ]
        price_note = self._comparison_price_note(primary=primary, alternative=alternative)
        if price_note:
            answer_parts.append(price_note)
        primary_reasons = self._decision_reasons(hit=primary, strategy="comparison")
        alternative_reasons = self._decision_reasons(hit=alternative, strategy="comparison")
        if primary_reasons:
            answer_parts.append(
                f"{primary.name} leads the comparison scorecard at {primary_score:.2f} because {self._natural_join(primary_reasons[:2])}."
            )
        if alternative_reasons:
            answer_parts.append(
                f"{alternative.name} follows at {alternative_score:.2f} because {self._natural_join(alternative_reasons[:2])}."
            )
        if reply_style == "detailed":
            answer_parts.append(
                f"{primary.name} is the stronger lead when you want the closest fit, while {alternative.name} is the main fallback or tradeoff option."
            )
            answer_parts.append("Should I compare price, stock, battery, or use-case fit next?")
        reply = InventoryReply(
            answer=" ".join(answer_parts),
            recommended_product_ids=[primary.product_id, alternative.product_id],
            follow_up_question="Should I compare price, stock, battery, or use-case fit next?",
            answer_plan=self._build_inventory_answer_plan(
                intent="comparison",
                primary=primary,
                alternative=alternative,
                excluded_hits=[hit for hit in hits if hit.product_id not in {primary.product_id, alternative.product_id}],
                metadata_source=primary,
                reasoning_steps=[
                    "Compared the strongest candidate pair for a bounded side-by-side answer.",
                    "Reserved deeper tradeoff explanation for the evidence contract and final planner.",
                ],
            ),
        )
        reply = self._enrich_reply_plan(
            reply=reply,
            question=question,
            filters=filters,
            hits=ranked_hits,
            strategy="comparison",
        )
        return reply.model_copy(
            update={
                "verification": self._verify_answer_plan(answer_plan=reply.answer_plan, hits=ranked_hits),
            }
        )

    def _build_agentic_bundle_reply(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        reply_style: str,
    ) -> InventoryReply:
        primary = self._agentic_primary_hit_for_bundle(question=question, hits=hits, filters=filters)
        if primary is None:
            return self._build_answer(
                question=question,
                hits=hits,
                filters=filters,
                low_stock_threshold=self.config.low_stock_threshold,
                assistant_mode="support",
                reply_style=reply_style,
            )
        cross_sell = self._select_cross_sell_candidate(primary=primary, hits=hits[1:], question=question)
        if cross_sell is None:
            return self._build_answer(
                question=question,
                hits=hits,
                filters=filters,
                low_stock_threshold=self.config.low_stock_threshold,
                assistant_mode="support",
                reply_style=reply_style,
            )
        answer_parts = [
            f"For a clean bundle, start with {self._format_option_label(primary)}."
        ]
        answer_parts.append(self._build_cross_sell_line(primary=primary, cross_sell=cross_sell))
        if reply_style == "detailed":
            answer_parts.append(
                f"I filtered add-ons to keep only items that are complementary to {primary.name}, not weak substitutes."
            )
            answer_parts.append("Do you want a cheaper bundle, a premium bundle, or just the core product?")
        reply = InventoryReply(
            answer=" ".join(answer_parts),
            recommended_product_ids=[primary.product_id],
            cross_sell_product_ids=[cross_sell.product_id],
            follow_up_question="Do you want a cheaper bundle, a premium bundle, or just the core product?",
            answer_plan=self._build_inventory_answer_plan(
                intent="bundle_recommendation",
                primary=primary,
                cross_sell=cross_sell,
                excluded_hits=[hit for hit in hits if hit.product_id not in {primary.product_id, cross_sell.product_id}],
                metadata_source=primary,
                reasoning_steps=[
                    "Selected a primary bundle anchor first.",
                    "Filtered candidate add-ons to only compatible cross-sells.",
                ],
            ),
        )
        reply = self._enrich_reply_plan(
            reply=reply,
            question=question,
            filters=filters,
            hits=hits,
            strategy="bundle_recommendation",
        )
        return reply.model_copy(
            update={
                "verification": self._verify_answer_plan(answer_plan=reply.answer_plan, hits=hits),
            }
        )

    def _build_agentic_restock_reply(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        reply_style: str,
        business_signals: dict[str, InventoryBusinessSignalRecord],
    ) -> InventoryReply:
        restock_hits = [
            hit for hit in hits if self._decision_score(hit=hit, strategy="restock", fallback=0.0) > 0
        ]
        restock_hits = sorted(
            restock_hits,
            key=lambda hit: (
                -self._decision_score(hit=hit, strategy="restock", fallback=hit.score),
                hit.name.casefold(),
            ),
        )
        if not restock_hits:
            return self._build_answer(
                question=question,
                hits=hits,
                filters=filters,
                low_stock_threshold=self.config.low_stock_threshold,
                assistant_mode="support",
                reply_style=reply_style,
            )
        primary = restock_hits[0]
        alternatives = restock_hits[1:3]
        primary_score = self._decision_score(hit=primary, strategy="restock", fallback=primary.score)
        primary_reasons = self._decision_reasons(hit=primary, strategy="restock")
        answer_parts = [
            f"Restock {self._format_option_label(primary)} first."
        ]
        if primary_reasons:
            answer_parts.append(
                f"It leads the restock scorecard at {primary_score:.2f} because {self._natural_join(primary_reasons[:3])}."
            )
        summary = self._format_business_signal_summary(
            hit=primary,
            signal=business_signals[primary.product_id],
            include_margin=True,
            include_supplier=True,
            include_returns=False,
            include_segments=False,
        )
        answer_parts.append(f"Operational read: {summary}.")
        if alternatives:
            answer_parts.append(
                f"Next restock candidates are {self._natural_join(self._format_option_label(hit) for hit in alternatives)}."
            )
        follow_up_question = "Do you want the full restock ranking or the safest backup options after this?"
        if reply_style == "detailed":
            answer_parts.append(follow_up_question)
        reply = InventoryReply(
            answer=" ".join(answer_parts),
            recommended_product_ids=[primary.product_id, *[hit.product_id for hit in alternatives[:2]]],
            follow_up_question=follow_up_question,
            answer_plan=self._build_inventory_answer_plan(
                intent="restock_recommendation",
                primary=primary,
                excluded_hits=[hit for hit in hits if hit.product_id not in {primary.product_id, *[item.product_id for item in alternatives]}],
                metadata_source=primary,
                reasoning_steps=[
                    "Ranked restock candidates with a deterministic scorecard over demand, stock pressure, lead time, margin, and supplier risk.",
                    "Kept the answer tied to mirrored catalog items with supporting business signals.",
                ],
            ),
        )
        reply = self._enrich_reply_plan(
            reply=reply,
            question=question,
            filters=filters,
            hits=restock_hits,
            strategy="restock",
        )
        return reply.model_copy(
            update={
                "verification": self._verify_answer_plan(answer_plan=reply.answer_plan, hits=restock_hits),
            }
        )

    def _build_missing_domain_abstain_reply(
        self,
        *,
        question: str,
        assistant_mode: str,
        reply_style: str,
        filters: InventorySearchFilters,
        missing_data_domains: list[str],
    ) -> InventoryReply:
        missing = self._natural_join(domain.replace("_", " ") for domain in missing_data_domains)
        answer = (
            f"I cannot make a reliable workflow recommendation yet because I do not have {missing} in this agent."
        )
        if reply_style == "detailed":
            answer += " Narrow the question to the mirrored catalog, or connect the missing domains and ask again."
        reply = InventoryReply(
            answer=answer,
            follow_up_question="Do you want a catalog-only answer instead, or should I wait for those data domains?",
            answer_plan=self._build_inventory_answer_plan(
                intent="agentic_missing_data_abstain",
                primary=None,
                abstain=True,
                abstention_reason=f"Missing required data domains: {missing}.",
                reasoning_steps=["Abstained because required workflow data domains are unavailable."],
            ),
        )
        reply = self._enrich_reply_plan(
            reply=reply,
            question=question,
            filters=filters,
            hits=[],
            strategy="agentic_missing_data_abstain",
        )
        return reply.model_copy(
            update={
                "verification": self._verify_answer_plan(answer_plan=reply.answer_plan, hits=[]),
            }
        )

    def _build_support_answer(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        low_stock_threshold: int,
        reply_style: str,
    ) -> InventoryReply:
        if not hits:
            follow_up_question = self._build_clarification_question(
                question=question,
                assistant_mode="support",
                hits=hits,
                filters=filters,
            )
            exact_no_match = self._build_exact_no_match_answer(question=question)
            answer = exact_no_match or "I could not find a solid catalog match for that yet."
            if reply_style == "detailed" and follow_up_question:
                answer += f" {follow_up_question}"
            else:
                answer += " Tell me the product type, brand, budget, or stock question and I will narrow it down."
            plan = self._build_inventory_answer_plan(
                intent="support_no_match",
                primary=None,
                abstain=True,
                abstention_reason=exact_no_match or "No reliable catalog match.",
                reasoning_steps=["No retrieved product passed the exact or confidence checks."],
            )
            return InventoryReply(
                answer=answer,
                follow_up_question=follow_up_question,
                answer_plan=plan,
                verification=self._verify_answer_plan(answer_plan=plan, hits=hits),
            )

        lowered = question.casefold()
        objection_type = self._detect_objection_type(lowered)
        if objection_type:
            return self._build_support_objection_reply(
                objection_type=objection_type,
                question=question,
                hits=hits,
                filters=filters,
                reply_style=reply_style,
            )

        detail_reply = self._build_support_detail_reply(
            question=question,
            hits=hits,
            reply_style=reply_style,
        )
        if detail_reply is not None:
            return detail_reply

        clarification_question = self._build_clarification_question(
            question=question,
            assistant_mode="support",
            hits=hits,
            filters=filters,
        )
        if clarification_question and self._should_prioritize_clarification(question=question, filters=filters):
            primary = hits[0]
            answer = "I can help with that."
            if reply_style == "detailed" and self._quality_score(primary) >= 3:
                answer = f"A strong starting point is {self._format_option_label(primary)}."
            if clarification_question:
                answer += f" {clarification_question}"
            return InventoryReply(answer=answer, follow_up_question=clarification_question)

        if self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]):
            zero_stock_hits = [hit for hit in hits if (hit.stock or 0) == 0]
            selected_hits = zero_stock_hits or hits
            primary = selected_hits[0]
            answer = (
                f"{primary.name} is currently out of stock{self._format_optional_price_suffix(self._format_price_text(primary))}."
            )
            if len(selected_hits) > 1:
                answer += f" Other out-of-stock matches are {self._natural_join(self._format_option_label(hit) for hit in selected_hits[1:3])}."
            answer += " If you want, I can suggest the closest in-stock alternatives."
            return InventoryReply(answer=answer, follow_up_question="Do you want the closest in-stock alternatives instead?")

        if self._has_any_phrase(lowered, ["low stock", "running low", "below threshold", "limited stock"]):
            threshold = filters.max_stock if filters.max_stock is not None else low_stock_threshold
            low_stock_hits = [hit for hit in hits if hit.stock is not None and hit.stock <= threshold]
            selected_hits = low_stock_hits or hits
            primary = selected_hits[0]
            answer = (
                f"{primary.name} is the most urgent low-stock match right now with {primary.stock or 0} unit(s) left"
                f"{self._format_optional_price_suffix(self._format_price_text(primary))}."
            )
            if len(selected_hits) > 1:
                answer += f" Other low-stock matches are {self._natural_join(self._format_option_label(hit) for hit in selected_hits[1:3])}."
            follow_up_question = "Do you want me to sort the remaining low-stock items by urgency, category, or price?"
            if reply_style == "detailed":
                answer += f" {follow_up_question}"
            return InventoryReply(answer=answer, follow_up_question=follow_up_question)

        if self._has_any_phrase(lowered, ["most expensive", "highest price", "expensive"]):
            selected_hits = sorted(
                hits,
                key=lambda item: (self._price_sort_key(item, reverse=True), -self._quality_score(item), item.name.casefold()),
            )
            primary = selected_hits[0]
            answer = f"The highest-priced match is {self._format_option_label(primary)}."
            if len(selected_hits) > 1:
                answer += f" Next premium-priced options are {self._natural_join(self._format_option_label(hit) for hit in selected_hits[1:3])}."
            return InventoryReply(answer=answer)

        if self._has_any_phrase(lowered, ["cheapest", "lowest price", "least expensive"]):
            selected_hits = sorted(
                hits,
                key=lambda item: (self._price_sort_key(item), -self._quality_score(item), item.name.casefold()),
            )
            primary = selected_hits[0]
            answer = f"The most affordable match is {self._format_option_label(primary)}."
            if len(selected_hits) > 1:
                answer += f" Other lower-priced options are {self._natural_join(self._format_option_label(hit) for hit in selected_hits[1:3])}."
            return InventoryReply(answer=answer)

        top_hits = hits[:3]
        answer = f"I found {len(hits)} matching product(s). The strongest matches are {self._natural_join(self._format_option_label(hit) for hit in top_hits)}."
        if len(hits) > 3:
            answer += f" There are {len(hits) - 3} more relevant option(s) behind those."
        if reply_style == "detailed":
            follow_up_question = clarification_question or "If you tell me your budget, preferred brand, or use case, I can narrow this down further."
            answer += f" {follow_up_question}"
        else:
            follow_up_question = clarification_question
        primary = top_hits[0] if top_hits else None
        plan = self._build_inventory_answer_plan(
            intent="support_product_search",
            primary=primary,
            alternative=top_hits[1] if len(top_hits) > 1 else None,
            excluded_hits=[],
            metadata_source=primary,
            reasoning_steps=[
                "Summarized the highest-ranked matching products.",
                "Kept the answer grounded in retrieved catalog fields including price, stock, brand, and metadata when present.",
            ],
        )
        return InventoryReply(
            answer=answer,
            follow_up_question=follow_up_question,
            answer_plan=plan,
            verification=self._verify_answer_plan(answer_plan=plan, hits=hits),
        )

    def _format_answer(self, *, intro: str, hits: list[InventorySearchHit], limit: int = 5) -> str:
        lines = [intro]
        for hit in hits[:limit]:
            lines.append(self._format_hit_line(hit))
        return " ".join(lines)

    def _build_sales_answer(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        low_stock_threshold: int,
        reply_style: str,
    ) -> InventoryReply:
        if not hits:
            follow_up_question = self._build_clarification_question(
                question=question,
                assistant_mode="sales",
                hits=hits,
                filters=filters,
            )
            answer = "I do not have a reliable catalog-backed match for that yet."
            if reply_style == "detailed" and follow_up_question:
                answer += f" {follow_up_question}"
            else:
                answer += " Give me the product type, budget, or customer need and I will recommend something I can actually support with inventory data."
            plan = self._build_inventory_answer_plan(
                intent="sales_no_match",
                primary=None,
                abstain=True,
                abstention_reason="No reliable catalog-backed sales match.",
                reasoning_steps=["No retrieved product was strong enough to recommend."],
            )
            return InventoryReply(
                answer=answer,
                follow_up_question=follow_up_question,
                answer_plan=plan,
                verification=self._verify_answer_plan(answer_plan=plan, hits=hits),
            )

        sales_style = self._classify_sales_style(
            question=question,
            filters=filters,
        )
        ranked_hits = self._rank_sales_hits(hits=hits, sales_style=sales_style)
        in_stock_hits = [hit for hit in ranked_hits if not self._is_out_of_stock(hit)]
        objection_type = self._detect_objection_type(question.casefold())

        if objection_type:
            return self._build_sales_objection_reply(
                objection_type=objection_type,
                question=question,
                hits=in_stock_hits or ranked_hits,
                sales_style=sales_style,
                reply_style=reply_style,
            )

        clarification_question = self._build_clarification_question(
            question=question,
            assistant_mode="sales",
            hits=in_stock_hits or ranked_hits,
            filters=filters,
        )
        if clarification_question and self._should_prioritize_clarification(question=question, filters=filters):
            answer = "I can help, but I need one more detail before I make a clean recommendation."
            if in_stock_hits and reply_style == "detailed" and self._quality_score(in_stock_hits[0]) >= 3:
                answer += f" A strong starting point is {self._format_option_label(in_stock_hits[0])}."
            answer += f" {clarification_question}"
            return InventoryReply(
                answer=answer,
                recommended_product_ids=[
                    in_stock_hits[0].product_id
                ]
                if in_stock_hits and reply_style == "detailed" and self._quality_score(in_stock_hits[0]) >= 3
                else [],
                follow_up_question=clarification_question,
            )

        if not in_stock_hits:
            follow_up_question = "Do you want me to suggest the closest in-stock substitutes instead?"
            answer = "I found matching products, but none of them are currently ready to sell from live stock."
            if reply_style == "detailed":
                answer += " I would avoid pitching them until inventory is available. " + follow_up_question
            return InventoryReply(
                answer=answer,
                follow_up_question=follow_up_question,
            )

        primary = in_stock_hits[0]
        coherent_hits = self._filter_coherent_sales_hits(primary=primary, hits=in_stock_hits)
        excluded_hits = [hit for hit in in_stock_hits if hit.product_id not in {candidate.product_id for candidate in coherent_hits}]
        coherent_clarification_question = self._build_clarification_question(
            question=question,
            assistant_mode="sales",
            hits=coherent_hits,
            filters=filters,
        )
        answer_parts = [self._build_sales_intro(primary=primary, sales_style=sales_style)]

        reason_parts = self._build_sales_reason_parts(
            primary=primary,
            hits=coherent_hits,
            sales_style=sales_style,
            low_stock_threshold=low_stock_threshold,
        )
        if reason_parts:
            if reply_style == "detailed":
                answer_parts.append(" ".join(reason_parts))
            elif reason_parts:
                answer_parts.append(reason_parts[0])

        alternative = self.decision_scorer.select_sales_alternative(
            primary=primary,
            hits=coherent_hits[1:],
            sales_style=sales_style,
        )
        if alternative is not None:
            if reply_style == "detailed":
                answer_parts.append(
                    self._build_sales_alternative_line(
                        primary=primary,
                        alternative=alternative,
                        sales_style=sales_style,
                    )
                )
            else:
                answer_parts.append(f"If they push back on price, I would shift to {alternative.name}.")

        upsell_candidate = self._select_sales_upsell_candidate(
            primary=primary,
            hits=coherent_hits[1:],
            sales_style=sales_style,
        )
        if upsell_candidate is not None and reply_style == "detailed":
            answer_parts.append(self._build_sales_upsell_line(primary=primary, upsell=upsell_candidate))

        cross_sell_candidate = self._select_cross_sell_candidate(
            primary=primary,
            hits=in_stock_hits[1:],
            question=question,
        )
        cross_sell_product_ids = [cross_sell_candidate.product_id] if cross_sell_candidate is not None else []
        if cross_sell_candidate is not None and reply_style == "detailed":
            answer_parts.append(self._build_cross_sell_line(primary=primary, cross_sell=cross_sell_candidate))

        follow_up_question = coherent_clarification_question or self._build_sales_follow_up_question(
            sales_style=sales_style,
            primary=primary,
        )
        if reply_style == "detailed":
            answer_parts.append(
                "I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data."
            )
            if follow_up_question:
                answer_parts.append(follow_up_question)
        recommended_product_ids = self._build_recommended_product_ids(
            primary=primary,
            alternative=alternative,
            upsell=upsell_candidate,
            coherent_hits=coherent_hits,
        )
        answer_plan = self._build_inventory_answer_plan(
            intent=f"sales_{sales_style}",
            primary=primary,
            alternative=alternative,
            cross_sell=cross_sell_candidate,
            excluded_hits=excluded_hits,
            metadata_source=primary,
            reasoning_steps=self._build_sales_plan_steps(
                primary=primary,
                alternative=alternative,
                cross_sell=cross_sell_candidate,
                sales_style=sales_style,
                excluded_hits=excluded_hits,
            ),
        )
        verification = self._verify_answer_plan(answer_plan=answer_plan, hits=hits)
        return InventoryReply(
            answer=" ".join(part for part in answer_parts if part),
            recommended_product_ids=recommended_product_ids,
            cross_sell_product_ids=cross_sell_product_ids,
            follow_up_question=follow_up_question,
            answer_plan=answer_plan,
            verification=verification,
        )

    def _format_hit_line(self, hit: InventorySearchHit) -> str:
        details = [f"{hit.name} (SKU {hit.sku})"]
        if hit.category:
            details.append(f"category {hit.category}")
        if hit.price is not None:
            details.append(f"price {hit.currency or 'USD'} {hit.price:.2f}")
        if hit.stock is not None:
            details.append(f"stock {hit.stock}")
        if hit.status:
            details.append(f"status {hit.status}")
        return "; ".join(details) + "."

    def _filter_coherent_sales_hits(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
    ) -> list[InventorySearchHit]:
        coherent_hits: list[InventorySearchHit] = []
        seen: set[str] = set()
        for hit in hits:
            if hit.product_id in seen:
                continue
            if hit.product_id == primary.product_id or self._is_coherent_recommendation_candidate(
                primary=primary,
                candidate=hit,
            ):
                coherent_hits.append(hit)
                seen.add(hit.product_id)
        return coherent_hits or [primary]

    def _is_coherent_recommendation_candidate(
        self,
        *,
        primary: InventorySearchHit,
        candidate: InventorySearchHit,
    ) -> bool:
        return self.product_ontology.valid_alternative(primary, candidate)

    @staticmethod
    def _build_recommended_product_ids(
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit | None,
        upsell: InventorySearchHit | None,
        coherent_hits: list[InventorySearchHit],
    ) -> list[str]:
        product_ids: list[str] = []
        for candidate in (primary, alternative, upsell, *coherent_hits[1:2]):
            if candidate is None or candidate.product_id in product_ids:
                continue
            product_ids.append(candidate.product_id)
            if len(product_ids) >= 3:
                break
        return product_ids

    def _build_inventory_answer_plan(
        self,
        *,
        intent: str,
        primary: InventorySearchHit | None,
        alternative: InventorySearchHit | None = None,
        cross_sell: InventorySearchHit | None = None,
        excluded_hits: list[InventorySearchHit] | None = None,
        metadata_source: InventorySearchHit | None = None,
        reasoning_steps: list[str] | None = None,
        abstain: bool = False,
        abstention_reason: str | None = None,
    ) -> InventoryAnswerPlan:
        metadata_used = self._metadata_used_for_hit(metadata_source or primary)
        return InventoryAnswerPlan(
            intent=intent,
            primary_product_id=primary.product_id if primary else None,
            alternative_product_ids=[alternative.product_id] if alternative else [],
            cross_sell_product_ids=[cross_sell.product_id] if cross_sell else [],
            excluded_product_ids=[hit.product_id for hit in excluded_hits or []],
            reasoning_steps=reasoning_steps or [],
            metadata_used=metadata_used,
            abstain=abstain,
            abstention_reason=abstention_reason,
        )

    def _enrich_reply_plan(
        self,
        *,
        reply: InventoryReply,
        question: str,
        filters: InventorySearchFilters,
        hits: list[InventorySearchHit],
        strategy: str | None,
    ) -> InventoryReply:
        intent_result = self.intent_classifier.classify(question, filters=filters)
        preference_profile = self.preference_extractor.extract(
            question,
            filters=filters,
            products=list(hits),
        )
        business_signals = self._load_business_signals()
        plan = self._enrich_answer_plan(
            answer_plan=reply.answer_plan,
            intent_result=intent_result,
            preference_profile=preference_profile,
            hits=hits,
            business_signals=business_signals,
            question=question,
            strategy=strategy,
            next_best_question=reply.follow_up_question,
        )
        verification = self._verify_answer_plan(answer_plan=plan, hits=hits)
        enriched_reply = InventoryReply(
            answer=reply.answer,
            recommended_product_ids=reply.recommended_product_ids,
            cross_sell_product_ids=reply.cross_sell_product_ids,
            follow_up_question=reply.follow_up_question,
            answer_plan=plan,
            verification=verification,
        )
        if verification.requires_abstention and not plan.abstain:
            return self._build_hard_constraint_abstain_reply(reply=enriched_reply)
        return enriched_reply

    def _build_hard_constraint_abstain_reply(
        self,
        *,
        reply: InventoryReply,
    ) -> InventoryReply:
        issues = self._dedupe_verification_issues(
            reply.verification.hard_constraint_issues or reply.verification.issues
        )
        reason = issues[0] if issues else "I could not verify a catalog fit for the required constraints."
        follow_up_question = (
            reply.follow_up_question
            or reply.answer_plan.next_best_question
            or (
                reply.answer_plan.evidence_contract.follow_up_question_rules[0]
                if reply.answer_plan.evidence_contract and reply.answer_plan.evidence_contract.follow_up_question_rules
                else None
            )
            or "Tell me which constraint matters most: category, budget, stock, or a specific spec."
        )
        evidence_contract = reply.answer_plan.evidence_contract
        if evidence_contract is not None:
            evidence_contract = evidence_contract.model_copy(update={"primary_product_id": None})
        abstain_plan = reply.answer_plan.model_copy(
            update={
                "primary_product_id": None,
                "alternative_product_ids": [],
                "cross_sell_product_ids": [],
                "primary_reason": None,
                "alternative_reason": None,
                "cross_sell_reason": None,
                "tradeoffs": [],
                "risk_notes": self._dedupe_verification_issues([*reply.answer_plan.risk_notes, *issues]),
                "reasoning_steps": [
                    *reply.answer_plan.reasoning_steps,
                    "Abstained because the selected product fit violated hard constraints: "
                    + self._natural_join(issues[:3])
                    + ".",
                ],
                "next_best_question": follow_up_question,
                "abstain": True,
                "abstention_reason": reason,
                "evidence_contract": evidence_contract,
            }
        )
        verification = reply.verification.model_copy(
            update={
                "passed": False,
                "issues": self._dedupe_verification_issues([*reply.verification.issues, *issues]),
                "hard_constraint_issues": issues,
                "requires_abstention": True,
            }
        )
        return InventoryReply(
            answer=(
                "I do not have a reliable catalog fit that satisfies the required category, budget, "
                "stock, or spec constraints for this request."
            ),
            recommended_product_ids=[],
            cross_sell_product_ids=[],
            follow_up_question=follow_up_question,
            answer_plan=abstain_plan,
            verification=verification,
        )

    def _enrich_answer_plan(
        self,
        *,
        answer_plan: InventoryAnswerPlan,
        intent_result: InventoryIntentResult,
        preference_profile: InventoryPreferenceProfile,
        hits: list[InventorySearchHit],
        business_signals: dict[str, InventoryBusinessSignalRecord],
        question: str,
        strategy: str | None,
        next_best_question: str | None,
    ) -> InventoryAnswerPlan:
        plan_intent = answer_plan.intent
        if plan_intent == "unknown":
            plan_intent = intent_result.intent
        base_plan = answer_plan.model_copy(
            update={
                "intent": plan_intent,
                "detected_intent": intent_result.intent,
                "intent_confidence": intent_result.confidence,
                "intent_reasons": list(intent_result.reasons),
                "strategy": strategy if strategy != plan_intent else answer_plan.strategy,
                "preferences": preference_profile.to_plan_dict(),
                "product_type": preference_profile.product_type,
                "product_family": preference_profile.product_family,
            }
        )
        evidence_contract = self.evidence_contract_builder.build(
            question=question,
            answer_plan=base_plan,
            hits=hits,
            preferences=preference_profile,
            business_signals={hit.product_id: business_signals[hit.product_id] for hit in hits if hit.product_id in business_signals},
            next_best_question=next_best_question,
        )
        base_plan = base_plan.model_copy(update={"evidence_contract": evidence_contract})
        return self.answer_planner.enrich_plan(
            answer_plan=base_plan,
            evidence_contract=evidence_contract,
            intent_result=intent_result,
            preferences=preference_profile,
            strategy=strategy,
            next_best_question=next_best_question,
        )

    def _build_sales_plan_steps(
        self,
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit | None,
        cross_sell: InventorySearchHit | None,
        sales_style: str,
        excluded_hits: list[InventorySearchHit],
    ) -> list[str]:
        steps = [
            f"Selected {primary.name} because it is the strongest {sales_style} match after stock, relevance, and quality ranking.",
        ]
        if primary.category:
            steps.append(f"Kept recommendation logic anchored to the {primary.category} category unless an explicit cross-sell is requested.")
        metadata_step = self._metadata_reason_step(primary)
        if metadata_step:
            steps.append(metadata_step)
        if alternative is not None:
            steps.append(
                f"Selected {alternative.name} as a related fallback, not a random semantic neighbor. "
                + self.product_ontology.explain_relationship(primary, alternative)
            )
        if cross_sell is not None:
            steps.append(
                f"Selected {cross_sell.name} as a cross-sell only because the user asked for an add-on or bundle-style suggestion. "
                + self.product_ontology.explain_relationship(primary, cross_sell)
            )
        if excluded_hits:
            steps.append(
                "Excluded unrelated retrieval hits from recommendation logic: "
                + self._natural_join(hit.name for hit in excluded_hits[:3])
                + "."
            )
        return steps

    def _verify_answer_plan(
        self,
        *,
        answer_plan: InventoryAnswerPlan,
        hits: list[InventorySearchHit],
    ) -> InventoryAnswerVerification:
        issues: list[str] = []
        hit_by_id = {hit.product_id: hit for hit in hits}
        primary = hit_by_id.get(answer_plan.primary_product_id or "")
        if answer_plan.primary_product_id and primary is None:
            issues.append("Primary product is not present in retrieved evidence.")
        for product_id in answer_plan.alternative_product_ids:
            candidate = hit_by_id.get(product_id)
            if candidate is None:
                issues.append(f"Alternative product {product_id} is not present in retrieved evidence.")
                continue
            if primary is not None and not self._is_coherent_recommendation_candidate(primary=primary, candidate=candidate):
                issues.append(f"Alternative product {candidate.name} is not logically related to the primary recommendation.")
        for product_id in answer_plan.cross_sell_product_ids:
            candidate = hit_by_id.get(product_id)
            if candidate is None:
                issues.append(f"Cross-sell product {product_id} is not present in retrieved evidence.")
        used_product_ids = {
            product_id
            for product_id in [
                answer_plan.primary_product_id,
                *answer_plan.alternative_product_ids,
                *answer_plan.cross_sell_product_ids,
            ]
            if product_id
        }
        overlapping_exclusions = set(answer_plan.excluded_product_ids).intersection(used_product_ids)
        if overlapping_exclusions:
            issues.append("Answer plan both used and excluded the same product IDs.")
        product_fit_verification = self.final_answer_verifier.verify_product_fit(
            answer_plan=answer_plan,
            hits=hits,
        )
        merged_issues = self._dedupe_verification_issues([*issues, *product_fit_verification.issues])
        hard_constraint_issues = self._dedupe_verification_issues(product_fit_verification.hard_constraint_issues)
        return InventoryAnswerVerification(
            passed=not merged_issues,
            issues=merged_issues,
            hard_constraint_issues=hard_constraint_issues,
            requires_abstention=product_fit_verification.requires_abstention,
        )

    def _metadata_used_for_hit(self, hit: InventorySearchHit | None) -> list[str]:
        if hit is None:
            return []
        fields: list[str] = []
        for key in sorted(hit.attributes):
            if key not in fields:
                fields.append(f"attributes.{key}")
        for key in sorted(hit.metadata):
            if key == "raw_attributes" and isinstance(hit.metadata.get(key), dict):
                for raw_key in sorted(hit.metadata[key]):
                    fields.append(f"metadata.raw_attributes.{raw_key}")
            elif key not in {"source_record_id"}:
                fields.append(f"metadata.{key}")
        return fields[:12]

    def _metadata_reason_step(self, hit: InventorySearchHit) -> str | None:
        useful_bits: list[str] = []
        for key in ("connectivity", "battery_hours", "warranty_years", "input", "use_case", "watts"):
            value = hit.attributes.get(key)
            if value:
                useful_bits.append(f"{key.replace('_', ' ')}: {value}")
        if not useful_bits:
            raw_attributes = hit.metadata.get("raw_attributes")
            if isinstance(raw_attributes, dict):
                for key, value in list(sorted(raw_attributes.items()))[:3]:
                    useful_bits.append(f"{key.replace('_', ' ')}: {value}")
        if not useful_bits:
            return None
        return "Used structured metadata/attributes for the recommendation: " + "; ".join(useful_bits[:4]) + "."

    def _metadata_answer_sentence(self, hit: InventorySearchHit) -> str | None:
        useful_bits: list[str] = []
        display_names = {
            "connectivity": "connectivity",
            "battery_hours": "battery life",
            "warranty_years": "warranty",
            "input": "input",
            "use_case": "use case",
            "watts": "power",
            "color": "color",
        }
        for key, label in display_names.items():
            value = hit.attributes.get(key)
            if value:
                suffix = " hours" if key == "battery_hours" and str(value).isdigit() else ""
                suffix = " year(s)" if key == "warranty_years" and str(value).isdigit() else suffix
                useful_bits.append(f"{label}: {value}{suffix}")
        if not useful_bits:
            return None
        return "Structured details include " + "; ".join(useful_bits[:4]) + "."

    def _estimate_confidence(self, hits: list[InventorySearchHit]) -> float:
        if not hits:
            return 0.0
        top_score = hits[0].score
        if top_score == 0.0:
            return 0.5
        normalized = (top_score + 1.0) / 2.0
        return round(max(0.0, min(1.0, normalized)), 3)

    def _build_vector_filters(self, filters: InventorySearchFilters) -> dict[str, object]:
        vector_filters: dict[str, object] = {}
        if filters.product_ids:
            vector_filters["product_id"] = filters.product_ids
        if filters.categories:
            vector_filters["category_key"] = [category.casefold() for category in filters.categories]
        if filters.brands:
            vector_filters["brand_key"] = [brand.casefold() for brand in filters.brands]
        if filters.statuses:
            vector_filters["status_key"] = [status.casefold() for status in filters.statuses]
        stock_filter: dict[str, int] = {}
        if filters.min_stock is not None:
            stock_filter["$gte"] = filters.min_stock
        if filters.max_stock is not None:
            stock_filter["$lte"] = filters.max_stock
        if stock_filter:
            vector_filters["stock"] = stock_filter
        price_filter: dict[str, float] = {}
        if filters.min_price is not None:
            price_filter["$gte"] = filters.min_price
        if filters.max_price is not None:
            price_filter["$lte"] = filters.max_price
        if price_filter:
            vector_filters["price"] = price_filter
        return vector_filters

    def _build_requirement_vector_filters(self, preferences: InventoryPreferenceProfile) -> dict[str, object]:
        vector_filters: dict[str, object] = {}
        for requirement in preferences.spec_requirements:
            if requirement.operator == "eq":
                vector_filters[requirement.key] = {"$eq": requirement.value}
            elif requirement.operator == "gte":
                vector_filters[requirement.key] = {"$gte": requirement.value}
        return vector_filters

    def _hit_satisfies_spec_requirements(
        self,
        hit: InventorySearchHit,
        requirements: tuple[InventorySpecRequirement, ...],
    ) -> bool:
        return self._hit_spec_match_score(hit, requirements) >= 1.0

    def _hit_spec_match_score(
        self,
        hit: InventorySearchHit,
        requirements: tuple[InventorySpecRequirement, ...],
    ) -> float:
        if not requirements:
            return 1.0
        satisfied = 0.0
        for requirement in requirements:
            actual = self._hit_metadata_value(hit, requirement.key)
            if self._spec_requirement_satisfied(actual, requirement):
                satisfied += 1.0
                continue
            partial = self._spec_requirement_partial_credit(actual, requirement)
            satisfied += partial
        return satisfied / len(requirements)

    @staticmethod
    def _hit_metadata_value(hit: InventorySearchHit, key: str) -> object | None:
        aliases = {
            "ram_gb": ("ram_gb", "ram"),
            "storage_gb": ("storage_gb", "storage"),
            "battery_hours": ("battery_hours",),
            "screen_size_inch": ("screen_size_inch", "display_size_inch", "screen_size", "display"),
            "gps_support": ("gps_support", "gps"),
            "anc_support": ("anc_support", "anc", "noise_cancellation", "noise_cancelling", "noise_canceling"),
            "inverter_support": ("inverter_support", "inverter"),
        }.get(key, (key,))
        for alias in aliases:
            if alias in hit.metadata:
                return hit.metadata.get(alias)
        raw_attributes = hit.metadata.get("raw_attributes")
        if isinstance(raw_attributes, dict):
            for alias in aliases:
                if alias in raw_attributes:
                    return raw_attributes.get(alias)
        for alias in aliases:
            if alias in hit.attributes:
                return hit.attributes.get(alias)
        return None

    @staticmethod
    def _spec_requirement_satisfied(actual: object | None, requirement: InventorySpecRequirement) -> bool:
        if actual is None:
            return False
        if requirement.operator == "eq":
            if isinstance(requirement.value, bool):
                if isinstance(actual, bool):
                    return actual is requirement.value
                normalized_actual = str(actual).strip().casefold()
                if normalized_actual in _BOOLEAN_FALSE_VALUES:
                    return requirement.value is False
                if normalized_actual in _BOOLEAN_TRUE_VALUES:
                    return requirement.value is True
                return requirement.value is True
            return str(actual).strip().casefold() == str(requirement.value).strip().casefold()
        if requirement.operator == "gte":
            if isinstance(actual, bool):
                return False
            try:
                return float(actual) >= float(requirement.value)
            except (TypeError, ValueError):
                return False
        return False

    @staticmethod
    def _spec_requirement_partial_credit(actual: object | None, requirement: InventorySpecRequirement) -> float:
        if actual is None:
            return 0.0
        if requirement.operator == "eq":
            return 0.0
        if requirement.operator == "gte":
            if isinstance(actual, bool):
                return 0.0
            try:
                actual_number = float(actual)
                expected_number = float(requirement.value)
            except (TypeError, ValueError):
                return 0.0
            if expected_number <= 0:
                return 0.0
            if actual_number <= 0:
                return 0.0
            return max(0.0, min(0.75, actual_number / expected_number))
        return 0.0

    def _item_matches_filters(self, item: InventoryItemRecord, filters: InventorySearchFilters) -> bool:
        if filters.rag_only and not item.include_in_rag:
            return False
        if filters.product_ids and item.product_id not in filters.product_ids:
            return False
        if filters.categories and not self._matches_text_filter(item.category, filters.categories):
            return False
        if filters.brands and not self._matches_text_filter(item.brand, filters.brands):
            return False
        if filters.statuses and not self._matches_text_filter(item.status, filters.statuses):
            return False
        if filters.tags:
            item_tags = {tag.casefold() for tag in item.tags}
            requested_tags = {tag.casefold() for tag in filters.tags}
            if not item_tags.intersection(requested_tags):
                return False
        if filters.min_stock is not None and item.stock < filters.min_stock:
            return False
        if filters.max_stock is not None and item.stock > filters.max_stock:
            return False
        if filters.min_price is not None and (item.price is None or item.price < filters.min_price):
            return False
        if filters.max_price is not None and (item.price is None or item.price > filters.max_price):
            return False
        return True

    def _build_search_hit(self, *, item: InventoryItemRecord, score: float) -> InventorySearchHit:
        curated_metadata = self._build_curated_vector_metadata(item)
        metadata = dict(item.metadata)
        for key, value in curated_metadata.items():
            metadata.setdefault(key, value)
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
            updated_at=item.updated_at,
            snippet=self._build_snippet(item),
            attributes=dict(item.attributes),
            metadata=metadata,
            score=round(score, 4),
        )

    def _build_snippet(self, item: InventoryItemRecord) -> str | None:
        for candidate in (item.short_description, item.full_description):
            if candidate:
                return candidate[:240]
        if item.attributes:
            return ", ".join(f"{key}: {value}" for key, value in sorted(item.attributes.items()))
        return None

    def _build_vector_record(self, item: InventoryItemRecord) -> VectorRecord:
        curated_metadata = self._build_curated_vector_metadata(item)
        search_text = self._build_search_text(item, curated_metadata=curated_metadata)
        return VectorRecord(
            record_id=item.product_id,
            vector=self.embedder.embed_text(search_text),
            metadata={
                "product_id": item.product_id,
                "sku": item.sku,
                "category": item.category,
                "category_key": item.category.casefold() if item.category else None,
                "brand": item.brand,
                "brand_key": item.brand.casefold() if item.brand else None,
                "status": item.status,
                "status_key": item.status.casefold() if item.status else None,
                "stock": item.stock,
                "price": item.price,
                "currency": item.currency,
                "include_in_rag": item.include_in_rag,
                "updated_at": item.updated_at,
                **curated_metadata,
            },
            text=search_text,
            namespace=self.config.namespace,
        )

    def _build_search_text(
        self,
        item: InventoryItemRecord,
        *,
        curated_metadata: dict[str, object] | None = None,
    ) -> str:
        if curated_metadata is None:
            curated_metadata = self._build_curated_vector_metadata(item)
        attribute_text = " ".join(f"{key} {value}" for key, value in sorted(item.attributes.items()))
        metadata_text = " ".join(f"{key} {value}" for key, value in sorted(item.metadata.items()))
        curated_metadata_text = self._build_curated_search_text(curated_metadata)
        alias_text = " ".join(self._search_alias_texts(item))
        fields = [
            item.name,
            item.sku,
            item.category,
            item.brand,
            item.short_description,
            item.full_description,
            item.status,
            " ".join(item.tags),
            attribute_text,
            metadata_text,
            curated_metadata_text,
            alias_text,
        ]
        return " ".join(value.strip() for value in fields if isinstance(value, str) and value.strip())

    def _build_curated_vector_metadata(self, item: InventoryItemRecord) -> dict[str, object]:
        source = self._attribute_metadata_source(item)
        metadata: dict[str, object] = {}

        numeric_aliases = {
            "ram_gb": ("ram_gb", "ram"),
            "storage_gb": ("storage_gb", "storage"),
            "battery_hours": ("battery_hours",),
            "battery_days": ("battery_days",),
            "battery_mah": ("battery_mah",),
            "screen_size_inch": ("screen_size_inch", "display_size_inch", "screen_size", "display"),
            "refresh_rate_hz": ("refresh_rate_hz", "refresh_rate"),
            "capacity_tb": ("capacity_tb",),
            "coverage_sqft": ("coverage_sqft",),
        }
        for target_key, aliases in numeric_aliases.items():
            value = self._normalize_numeric_attribute_value(
                self._first_metadata_value(source, aliases),
                target_key=target_key,
            )
            if value is not None:
                metadata[target_key] = value

        text_aliases = {
            "connectivity": ("connectivity",),
            "water_resistance": ("water_resistance",),
            "processor": ("processor",),
            "operating_system": ("operating_system",),
            "panel_type": ("panel_type", "panel"),
            "smart_platform": ("smart_platform",),
            "wifi_standard": ("wifi_standard",),
            "use_case": ("use_case",),
        }
        for target_key, aliases in text_aliases.items():
            value = self._normalize_text_attribute_value(self._first_metadata_value(source, aliases))
            if value:
                metadata[target_key] = value

        boolean_aliases = {
            "gps_support": ("gps",),
            "anc_support": ("anc", "noise_cancellation", "noise_cancelling", "noise_canceling"),
            "inverter_support": ("inverter", "inverter_support"),
            "stylus_support": ("stylus_support",),
            "voice_support": ("voice_support",),
        }
        for target_key, aliases in boolean_aliases.items():
            value = self._normalize_boolean_attribute_value(self._first_metadata_value(source, aliases))
            if value is not None:
                metadata[target_key] = value

        gps_value = self._normalize_text_attribute_value(self._first_metadata_value(source, ("gps",)))
        if gps_value and gps_value not in {"none", "no"}:
            metadata["gps_mode"] = gps_value

        return metadata

    def _build_curated_search_text(self, curated_metadata: dict[str, object]) -> str:
        fragments: list[str] = []
        if (ram_gb := curated_metadata.get("ram_gb")) is not None:
            fragments.append(f"{self._format_search_number(ram_gb)} gb ram")
        if (storage_gb := curated_metadata.get("storage_gb")) is not None:
            fragments.append(f"{self._format_search_number(storage_gb)} gb storage")
        if (battery_hours := curated_metadata.get("battery_hours")) is not None:
            fragments.append(f"{self._format_search_number(battery_hours)} hour battery")
        if (battery_days := curated_metadata.get("battery_days")) is not None:
            fragments.append(f"{self._format_search_number(battery_days)} day battery")
        if (battery_mah := curated_metadata.get("battery_mah")) is not None:
            fragments.append(f"{self._format_search_number(battery_mah)} mah battery")
        if (screen_size := curated_metadata.get("screen_size_inch")) is not None:
            fragments.append(f"{self._format_search_number(screen_size)} inch screen")
        if (refresh_rate := curated_metadata.get("refresh_rate_hz")) is not None:
            fragments.append(f"{self._format_search_number(refresh_rate)} hz refresh rate")
        if (capacity_tb := curated_metadata.get("capacity_tb")) is not None:
            fragments.append(f"{self._format_search_number(capacity_tb)} tb capacity")
        if (coverage_sqft := curated_metadata.get("coverage_sqft")) is not None:
            fragments.append(f"{self._format_search_number(coverage_sqft)} sqft coverage")

        for key in (
            "connectivity",
            "water_resistance",
            "processor",
            "operating_system",
            "panel_type",
            "smart_platform",
            "wifi_standard",
            "use_case",
            "gps_mode",
        ):
            value = curated_metadata.get(key)
            if isinstance(value, str) and value:
                fragments.append(value)

        if curated_metadata.get("gps_support") is True:
            fragments.append("gps")
        if curated_metadata.get("anc_support") is True:
            fragments.append("anc noise cancellation")
        if curated_metadata.get("inverter_support") is True:
            fragments.append("inverter")
        if curated_metadata.get("stylus_support") is True:
            fragments.append("stylus support")
        if curated_metadata.get("voice_support") is True:
            fragments.append("voice support")

        return " ".join(fragments)

    @staticmethod
    def _attribute_metadata_source(item: InventoryItemRecord) -> dict[str, object]:
        source: dict[str, object] = {}
        raw_attributes = item.metadata.get("raw_attributes")
        if isinstance(raw_attributes, dict):
            source.update(raw_attributes)
        for key, value in item.attributes.items():
            source.setdefault(key, value)
        return source

    def _search_alias_texts(self, item: InventoryItemRecord) -> list[str]:
        alias_texts: list[str] = []
        seen: set[str] = set()

        def add_alias(value: object) -> None:
            if value is None:
                return
            normalized = self._normalize_search_text(str(value))
            if len(normalized) < 2:
                return
            if normalized not in seen:
                seen.add(normalized)
                alias_texts.append(normalized)
            compact = normalized.replace(" ", "")
            if len(compact) >= 4 and compact != normalized and compact not in seen:
                seen.add(compact)
                alias_texts.append(compact)

        alias_sources = (
            item.metadata,
            self._attribute_metadata_source(item),
        )
        alias_keys = (
            "aliases",
            "alias",
            "search_aliases",
            "product_aliases",
            "name_aliases",
            "alternate_names",
            "alternative_names",
            "alternate_name",
            "alternative_name",
            "aka",
            "sku_aliases",
            "model",
            "model_number",
            "part_number",
        )
        for source in alias_sources:
            for key in alias_keys:
                value = source.get(key)
                if value is None:
                    continue
                if isinstance(value, (list, tuple, set)):
                    for entry in value:
                        add_alias(entry)
                    continue
                add_alias(value)

        name_tokens = self._normalize_search_text(item.name).split()
        sku_tokens = self._normalize_search_text(item.sku).split()
        if len(sku_tokens) > 1:
            add_alias("".join(sku_tokens))
        if len(name_tokens) > 1:
            add_alias("".join(name_tokens))
            max_window = min(3, len(name_tokens))
            for window_size in range(2, max_window + 1):
                for index in range(len(name_tokens) - window_size + 1):
                    add_alias("".join(name_tokens[index:index + window_size]))

        return alias_texts

    @staticmethod
    def _first_metadata_value(source: dict[str, object], aliases: tuple[str, ...]) -> object | None:
        for alias in aliases:
            value = source.get(alias)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
        return None

    def _normalize_numeric_attribute_value(self, value: object | None, *, target_key: str) -> int | float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
        else:
            text = str(value).strip().casefold()
            match = _FIRST_NUMBER_PATTERN.search(text)
            if not match:
                return None
            number = float(match.group())
            if target_key in {"storage_gb", "ram_gb"} and "tb" in text and "gb" not in text:
                number *= 1024
            if target_key == "capacity_tb" and "gb" in text and "tb" not in text:
                number /= 1024
        if target_key in {
            "ram_gb",
            "storage_gb",
            "battery_hours",
            "battery_days",
            "battery_mah",
            "refresh_rate_hz",
            "coverage_sqft",
        }:
            return int(round(number))
        rounded = round(number, 2)
        return int(rounded) if float(rounded).is_integer() else rounded

    def _normalize_text_attribute_value(self, value: object | None) -> str | None:
        if value is None:
            return None
        return self._normalize_search_text(str(value)) or None

    @staticmethod
    def _normalize_boolean_attribute_value(value: object | None) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().casefold()
        if not normalized:
            return None
        if normalized in _BOOLEAN_FALSE_VALUES:
            return False
        if normalized in _BOOLEAN_TRUE_VALUES:
            return True
        return True

    @staticmethod
    def _format_search_number(value: object) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _vector_record_ids(self) -> set[str] | None:
        record_ids = getattr(self.vector_store, "record_ids", None)
        if not callable(record_ids):
            return None
        try:
            return set(record_ids(namespace=self.config.namespace))
        except TypeError:
            return set(record_ids())

    def _catalog_quality_issues(self, catalog: dict[str, InventoryItemRecord]) -> list[InventorySyncIssue]:
        issues: list[InventorySyncIssue] = []
        for item in catalog.values():
            if not item.category:
                issues.append(
                    InventorySyncIssue(
                        severity="warning",
                        code="missing_category",
                        product_id=item.product_id,
                        message=f"Product {item.product_id} is missing category metadata.",
                    )
                )
            if item.price is None:
                issues.append(
                    InventorySyncIssue(
                        severity="warning",
                        code="missing_price",
                        product_id=item.product_id,
                        message=f"Product {item.product_id} is missing price metadata.",
                    )
                )
            if self._has_invalid_metadata_keys(item):
                issues.append(
                    InventorySyncIssue(
                        severity="warning",
                        code="invalid_metadata",
                        product_id=item.product_id,
                        message=f"Product {item.product_id} has blank metadata or attribute keys.",
                    )
                )
            if item.include_in_rag and not item.short_description and not item.full_description:
                issues.append(
                    InventorySyncIssue(
                        severity="warning",
                        code="empty_description",
                        product_id=item.product_id,
                        message=f"RAG-enabled product {item.product_id} has no short or full description.",
                    )
                )
            if item.include_in_rag and self.product_ontology.detect_product_type(product=item) is None:
                issues.append(
                    InventorySyncIssue(
                        severity="warning",
                        code="missing_product_type",
                        product_id=item.product_id,
                        message=f"RAG-enabled product {item.product_id} does not map to a known product type.",
                    )
                )
            if item.include_in_rag and not any((item.short_description, item.full_description, item.tags, item.attributes)):
                issues.append(
                    InventorySyncIssue(
                        severity="warning",
                        code="weak_rag_text",
                        product_id=item.product_id,
                        message=f"RAG-enabled product {item.product_id} has weak descriptive text for retrieval.",
                    )
                )
        return issues

    @staticmethod
    def _has_invalid_metadata_keys(item: InventoryItemRecord) -> bool:
        return any(not key.strip() for key in item.attributes) or any(not str(key).strip() for key in item.metadata)

    def _stale_catalog_product_ids(
        self,
        *,
        catalog: dict[str, InventoryItemRecord],
        source_items_by_id: dict[str, InventoryItemRecord],
    ) -> list[str]:
        stale_product_ids: list[str] = []
        comparable_fields = (
            "sku",
            "name",
            "category",
            "brand",
            "short_description",
            "full_description",
            "price",
            "currency",
            "stock",
            "status",
            "tags",
            "attributes",
            "include_in_rag",
            "updated_at",
        )
        for product_id, source_item in source_items_by_id.items():
            catalog_item = catalog.get(product_id)
            if catalog_item is None:
                continue
            for field_name in comparable_fields:
                if getattr(catalog_item, field_name) != getattr(source_item, field_name):
                    stale_product_ids.append(product_id)
                    break
        return sorted(stale_product_ids)

    def _business_signal_path(self) -> Path:
        return Path(self.config.business_signal_path)

    def _load_business_signals(self) -> dict[str, InventoryBusinessSignalRecord]:
        return self.mirror_store.load_business_signals()

    def _persist_business_signals(self, signals: dict[str, InventoryBusinessSignalRecord]) -> None:
        self.mirror_store.persist_business_signals(signals)

    def _business_domains_available(self, signals: dict[str, InventoryBusinessSignalRecord]) -> list[str]:
        domains: set[str] = set()
        for signal in signals.values():
            if signal.units_sold is not None or signal.revenue is not None or signal.demand_score is not None:
                domains.add("sales")
            if signal.order_count is not None:
                domains.add("orders")
            if signal.supplier_id or signal.supplier_name or signal.supplier_lead_time_days is not None:
                domains.add("suppliers")
            if signal.inventory_on_hand is not None or signal.inventory_snapshot_at:
                domains.add("inventory_snapshots")
            if signal.return_count is not None or signal.return_rate is not None:
                domains.add("returns")
            if signal.gross_margin is not None or signal.gross_margin_rate is not None:
                domains.add("margins")
            if signal.customer_segments:
                domains.add("customers")
        return sorted(domains)

    @staticmethod
    def _latest_business_signal_update(signals: dict[str, InventoryBusinessSignalRecord]) -> str | None:
        values = [
            value
            for signal in signals.values()
            for value in (signal.updated_at, signal.period_end, signal.inventory_snapshot_at)
            if value
        ]
        return max(values) if values else None

    @staticmethod
    def _business_signal_sort_key(signal: InventoryBusinessSignalRecord) -> tuple[str, str, str]:
        updated_key = signal.updated_at or signal.period_end or signal.inventory_snapshot_at or ""
        return (updated_key, signal.period_end or "", signal.product_id)

    def _catalog_path(self) -> Path:
        return Path(self.config.catalog_path)

    def _load_catalog(self) -> dict[str, InventoryItemRecord]:
        return self.mirror_store.load_catalog()

    def _persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        self.mirror_store.persist_catalog(items)

    @staticmethod
    def _matches_text_filter(actual: str | None, expected_values: list[str]) -> bool:
        if actual is None:
            return False
        actual_key = actual.casefold()
        return actual_key in {value.casefold() for value in expected_values}

    @staticmethod
    def _has_any_phrase(text: str, phrases: list[str]) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _is_out_of_stock(hit: InventorySearchHit) -> bool:
        return hit.stock is None or hit.stock <= 0

    @staticmethod
    def _price_sort_key(hit: InventorySearchHit, *, reverse: bool = False) -> float:
        if hit.price is None:
            return float("-inf") if reverse else float("inf")
        return -hit.price if reverse else hit.price

    def _classify_sales_style(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
    ) -> str:
        lowered = question.casefold()
        if self._has_any_phrase(lowered, ["low stock", "running low", "below threshold", "limited stock"]):
            return "urgency"
        if self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]) or self._has_any_phrase(
            lowered, _AVAILABILITY_HINTS
        ):
            return "availability"
        if filters.max_price is not None or self._has_any_phrase(lowered, _BUDGET_HINTS):
            return "budget"
        if self._has_any_phrase(lowered, _PREMIUM_HINTS):
            return "premium"
        if self._has_any_phrase(lowered, ["recommend", "suggest", "best for customer"]):
            return "general"
        return "general"

    def _rank_sales_hits(
        self,
        *,
        hits: list[InventorySearchHit],
        sales_style: str,
    ) -> list[InventorySearchHit]:
        ranked_hits = self.decision_scorer.rank_recommendations(hits=hits, sales_style=sales_style)
        return sorted(
            ranked_hits,
            key=lambda hit: (
                -self._decision_score(hit=hit, strategy="recommendation", fallback=hit.score),
                self._is_out_of_stock(hit),
                -self._quality_score(hit),
                self._price_sort_key(hit, reverse=sales_style == "premium"),
                -(hit.stock or 0),
                hit.name.casefold(),
            ),
        )

    def _annotate_sales_alternative_scores(
        self,
        *,
        hits: list[InventorySearchHit],
        primary_product_id: str | None,
        sales_style: str,
    ) -> list[InventorySearchHit]:
        if not hits or not primary_product_id:
            return hits
        primary = next((hit for hit in hits if hit.product_id == primary_product_id), None)
        if primary is None:
            return hits
        ranked_alternatives = self.decision_scorer.rank_sales_alternatives(
            primary=primary,
            hits=[hit for hit in hits if hit.product_id != primary_product_id],
            sales_style=sales_style,
        )
        alternative_by_id = {hit.product_id: hit for hit in ranked_alternatives}
        return [alternative_by_id.get(hit.product_id, hit) for hit in hits]

    def _build_sales_intro(self, *, primary: InventorySearchHit, sales_style: str) -> str:
        if sales_style == "budget":
            return f"I would lead with {primary.name}. It is the strongest budget-friendly match in the current catalog."
        if sales_style == "premium":
            return f"For this customer, I would start with {primary.name} as the premium option."
        if sales_style == "urgency":
            return f"I would move quickly on {primary.name}. It fits the request and gives you a real scarcity angle for the conversation."
        if sales_style == "availability":
            return f"I would steer the customer toward {primary.name} because it is available to sell right now."
        return f"I would start by recommending {primary.name}. It is the strongest overall match from the current catalog."

    def _build_sales_reason_parts(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
        sales_style: str,
        low_stock_threshold: int,
    ) -> list[str]:
        reasons: list[str] = []
        price_text = self._format_price_text(primary)

        if sales_style == "budget":
            if primary.price is not None:
                cheapest_price = min(hit.price for hit in hits if hit.price is not None)
                if primary.price == cheapest_price:
                    reasons.append(f"It is the lowest-priced strong match at {price_text}.")
                else:
                    reasons.append(f"It stays within the requested value range at {price_text}.")
        elif sales_style == "premium":
            if primary.price is not None:
                highest_price = max(hit.price for hit in hits if hit.price is not None)
                if primary.price == highest_price:
                    reasons.append(f"It sits at the top end of this matching set at {price_text}.")
                else:
                    reasons.append(f"It supports a premium pitch at {price_text}.")
        else:
            if primary.price is not None:
                reasons.append(f"The current price is {price_text}.")

        if primary.stock is not None:
            if primary.stock <= low_stock_threshold:
                reasons.append(f"There are only {primary.stock} unit(s) in stock, which gives you a legitimate urgency point.")
            else:
                reasons.append(f"It currently has {primary.stock} unit(s) in stock.")

        if primary.category and primary.brand:
            reasons.append(f"It sits in {primary.category} under {primary.brand}.")
        elif primary.category:
            reasons.append(f"It sits in the {primary.category} category.")
        elif primary.brand:
            reasons.append(f"It is listed under the {primary.brand} brand.")

        if primary.snippet:
            reasons.append(f"The product description highlights {primary.snippet[:160].rstrip('.')}.")
        metadata_sentence = self._metadata_answer_sentence(primary)
        if metadata_sentence:
            reasons.append(metadata_sentence)
        return reasons

    def _build_sales_alternative_line(
        self,
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit,
        sales_style: str,
    ) -> str:
        alternative_price = self._format_price_text(alternative)
        if sales_style == "premium":
            return (
                f"If the customer needs a more accessible price point than {primary.name}, "
                f"I would keep {alternative.name} ready as the fallback at {alternative_price}."
            )
        if sales_style == "budget":
            return (
                f"If the customer wants to step up from {primary.name}, "
                f"the next option to show is {alternative.name} at {alternative_price}."
            )
        if sales_style == "urgency":
            return (
                f"If {primary.name} sells through, I would switch to {alternative.name} as the backup option"
                f"{self._format_optional_price_suffix(alternative_price)}."
            )
        return (
            f"If the customer wants an alternative, I would show {alternative.name} next"
            f"{self._format_optional_price_suffix(alternative_price)}."
        )

    def _premium_signal(self, hit: InventorySearchHit) -> int:
        searchable_text = " ".join([hit.name, hit.snippet or "", " ".join(hit.tags)]).casefold()
        return sum(1 for keyword in _PREMIUM_ITEM_HINTS if keyword in searchable_text)

    @staticmethod
    def _format_price_text(hit: InventorySearchHit) -> str:
        if hit.price is None:
            return "price not listed"
        return f"{hit.currency or 'USD'} {hit.price:.2f}"

    @staticmethod
    def _format_optional_price_suffix(price_text: str) -> str:
        if price_text == "price not listed":
            return ""
        return f" at {price_text}"

    def _detect_objection_type(self, normalized_question: str) -> str | None:
        if self._has_any_phrase(normalized_question, _PRICE_OBJECTION_PHRASES):
            return "price"
        if self._has_any_phrase(normalized_question, _AVAILABILITY_OBJECTION_PHRASES):
            return "availability"
        if self._has_any_phrase(normalized_question, _QUALITY_OBJECTION_PHRASES):
            return "quality"
        return None

    def _should_prioritize_clarification(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
    ) -> bool:
        normalized = self._normalize_conversation_text(question)
        if self._has_any_phrase(normalized, _AMBIGUOUS_REQUEST_PHRASES):
            return True

        has_structured_constraints = any(
            (
                filters.product_ids,
                filters.categories,
                filters.brands,
                filters.tags,
                filters.min_stock is not None,
                filters.max_stock is not None,
                filters.min_price is not None,
                filters.max_price is not None,
            )
        )
        if has_structured_constraints:
            return False

        tokens = normalized.split()
        generic_request = any(keyword in normalized for keyword in ("recommend", "suggest", "show", "find", "need"))
        return generic_request and len(tokens) <= 2

    def _build_clarification_question(
        self,
        *,
        question: str,
        assistant_mode: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
    ) -> str | None:
        if filters.product_ids:
            return None

        category_candidates = self._natural_join(self._top_hit_categories(hits))
        normalized = self._normalize_conversation_text(question)

        if assistant_mode == "sales":
            if category_candidates:
                return (
                    f"Are we selling into {category_candidates}? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability."
                )
            if self._has_any_phrase(normalized, ["recommend", "suggest", "customer", "sell"]):
                return "What category is the customer shopping in, and should I optimize for budget, premium feel, or fast-moving stock?"
            return None

        if category_candidates:
            return f"Are you looking for {category_candidates}? If you also tell me your budget or preferred brand, I can narrow it down."
        if self._has_any_phrase(normalized, ["recommend", "show", "find", "need"]):
            return "What product type or category should I focus on, and do you have a target budget or brand?"
        return None

    def _build_support_objection_reply(
        self,
        *,
        objection_type: str,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        reply_style: str,
    ) -> InventoryReply:
        primary = hits[0]
        follow_up_question: str | None = None
        if objection_type == "price":
            reference_hit = max(
                hits,
                key=lambda hit: (
                    float("-inf") if hit.price is None else hit.price,
                    self._quality_score(hit),
                    hit.score,
                ),
            )
            cheaper = self._select_lower_priced_candidate(
                primary=reference_hit,
                hits=[hit for hit in hits if hit.product_id != reference_hit.product_id],
            )
            if cheaper is not None:
                answer = f"If price is the concern, the better value option is {self._format_option_label(cheaper)}."
                if reply_style == "detailed":
                    answer += f" It comes in below {reference_hit.name} while staying close to the same request."
                follow_up_question = "Do you want the lowest price, or the best value for the money?"
                if reply_style == "detailed":
                    answer += f" {follow_up_question}"
                return InventoryReply(answer=answer, recommended_product_ids=[cheaper.product_id], follow_up_question=follow_up_question)
            return InventoryReply(
                answer="I can see the price concern, but I do not have a clearly cheaper related alternative from the current match set.",
                follow_up_question="Do you want me to widen the search for lower-priced options or focus on a specific product?",
            )

        if objection_type == "availability":
            in_stock_option = next((hit for hit in hits if not self._is_out_of_stock(hit)), None)
            if in_stock_option is not None:
                answer = f"If availability is the concern, I would move to {self._format_option_label(in_stock_option)} because it is sellable now."
                follow_up_question = "Do you want the closest in-stock match or the fastest-moving option?"
                if reply_style == "detailed":
                    answer += f" {follow_up_question}"
                return InventoryReply(answer=answer, recommended_product_ids=[in_stock_option.product_id], follow_up_question=follow_up_question)
            return InventoryReply(
                answer="Availability looks tight across the current matches.",
                follow_up_question="Do you want me to find the closest substitute in a nearby category?",
            )

        better_option = self._select_sales_upsell_candidate(primary=primary, hits=hits[1:], sales_style="general")
        if better_option is not None:
            answer = f"If the concern is quality, the stronger step-up option is {self._format_option_label(better_option)}."
            follow_up_question = "Should I optimize for higher quality or for a safer price point?"
            if reply_style == "detailed":
                answer += f" {follow_up_question}"
            return InventoryReply(answer=answer, recommended_product_ids=[better_option.product_id], follow_up_question=follow_up_question)

        return InventoryReply(
            answer="I can help you move to a better-fit option, but I need one more detail about what is not working.",
            follow_up_question="Is the issue price, availability, premium feel, or something else?",
        )

    def _build_support_detail_reply(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        reply_style: str,
    ) -> InventoryReply | None:
        if not hits or not self._is_detail_request(question):
            return None

        primary = hits[0]
        if not self._is_strong_product_reference(question=question, hit=primary):
            return None

        descriptor_parts: list[str] = []
        if primary.brand and primary.category:
            descriptor_parts.append(f"a {primary.category.lower()} product from {primary.brand}")
        elif primary.category:
            descriptor_parts.append(f"a {primary.category.lower()} product")
        elif primary.brand:
            descriptor_parts.append(f"a product from {primary.brand}")
        if primary.status:
            descriptor_parts.append(f"currently marked {primary.status.lower()}")
        descriptor_text = ", ".join(descriptor_parts)

        answer_parts = [f"{primary.name} is {descriptor_text}." if descriptor_text else f"{primary.name} is in the catalog."]
        if primary.price is not None:
            answer_parts.append(f"The current price is {self._format_price_text(primary)}.")
        if primary.stock is not None:
            answer_parts.append(f"There are {primary.stock} unit(s) in stock right now.")
        if primary.snippet:
            answer_parts.append(f"From the catalog description: {primary.snippet.rstrip('.')}.")
        metadata_sentence = self._metadata_answer_sentence(primary)
        if metadata_sentence:
            answer_parts.append(metadata_sentence)

        follow_up_question = "Do you want a comparison, stock check, or a lower-price alternative for this item?"
        if reply_style == "detailed":
            answer_parts.append(follow_up_question)
        plan = self._build_inventory_answer_plan(
            intent="support_product_detail",
            primary=primary,
            metadata_source=primary,
            reasoning_steps=[
                f"Answered from the exact product record for {primary.name}.",
                "Used price, stock, category, description, and available metadata/attributes.",
            ],
        )
        return InventoryReply(
            answer=" ".join(answer_parts),
            follow_up_question=follow_up_question,
            answer_plan=plan,
            verification=self._verify_answer_plan(answer_plan=plan, hits=hits),
        )

    def _build_sales_objection_reply(
        self,
        *,
        objection_type: str,
        question: str,
        hits: list[InventorySearchHit],
        sales_style: str,
        reply_style: str,
    ) -> InventoryReply:
        primary = hits[0]
        if objection_type == "price":
            reference_hit = max(
                hits,
                key=lambda hit: (
                    float("-inf") if hit.price is None else hit.price,
                    self._quality_score(hit),
                    hit.score,
                ),
            )
            cheaper = self._select_lower_priced_candidate(
                primary=reference_hit,
                hits=[hit for hit in hits if hit.product_id != reference_hit.product_id],
            )
            if cheaper is not None:
                answer = f"If the customer says {reference_hit.name} is too expensive, I would pivot to {cheaper.name} at {self._format_price_text(cheaper)}."
                if reply_style == "detailed":
                    answer += f" That keeps the conversation moving without losing the fit completely. If they can stretch the budget later, you can step them back up to {reference_hit.name}."
                follow_up_question = "Do you want the lowest price alternative, or the best value alternative?"
                if reply_style == "detailed":
                    answer += f" {follow_up_question}"
                return InventoryReply(
                    answer=answer,
                    recommended_product_ids=[cheaper.product_id, reference_hit.product_id],
                    follow_up_question=follow_up_question,
                )
            return InventoryReply(
                answer=(
                    "I can handle the price objection, but I need to know which product the customer is pushing back on before I choose a credible lower-price pivot."
                ),
                follow_up_question="Which product is the customer reacting to, or what price ceiling do you need me to hit?",
            )

        if objection_type == "availability":
            available_option = next((hit for hit in hits if not self._is_out_of_stock(hit)), None)
            if available_option is not None:
                answer = f"If stock timing is the objection, I would steer the customer to {available_option.name} because it is available now."
                if reply_style == "detailed":
                    answer += " That keeps urgency on your side without promising a delayed item."
                follow_up_question = "Do you want the best in-stock option, or the closest substitute to the original choice?"
                if reply_style == "detailed":
                    answer += f" {follow_up_question}"
                return InventoryReply(
                    answer=answer,
                    recommended_product_ids=[available_option.product_id],
                    follow_up_question=follow_up_question,
                )

        better_option = self._select_sales_upsell_candidate(primary=primary, hits=hits[1:], sales_style=sales_style)
        if better_option is not None:
            answer = f"If the customer wants something stronger, I would step them up to {better_option.name}."
            if reply_style == "detailed":
                answer += f" It gives you a cleaner premium story than staying with {primary.name}."
            follow_up_question = "Should I position the next recommendation around premium feel, price control, or immediate availability?"
            if reply_style == "detailed":
                answer += f" {follow_up_question}"
            return InventoryReply(
                answer=answer,
                recommended_product_ids=[better_option.product_id],
                follow_up_question=follow_up_question,
            )

        return InventoryReply(
            answer="I can handle that objection, but I need one more detail before I choose the right pivot.",
            follow_up_question="Is the pushback mainly about price, availability, or quality?",
        )

    def _select_lower_priced_candidate(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
    ) -> InventorySearchHit | None:
        priced_hits = [
            hit
            for hit in hits
            if hit.price is not None
            and (primary.price is None or hit.price < primary.price)
            and not self._is_out_of_stock(hit)
            and self._is_related_candidate(primary=primary, candidate=hit)
        ]
        if not priced_hits:
            return None
        return min(
            priced_hits,
            key=lambda hit: (-self._quality_score(hit), hit.price, -hit.score, hit.name.casefold()),
        )

    def _select_sales_upsell_candidate(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
        sales_style: str,
    ) -> InventorySearchHit | None:
        if sales_style == "premium":
            return None
        higher_priced_hits = [
            hit
            for hit in hits
            if hit.price is not None
            and (primary.price is None or hit.price > primary.price)
            and not self._is_out_of_stock(hit)
            and self._quality_score(hit) >= 3
            and self.product_ontology.valid_alternative(primary, hit)
        ]
        if not higher_priced_hits:
            return None
        same_category_hits = [
            hit
            for hit in higher_priced_hits
            if hit.category and primary.category and hit.category.casefold() == primary.category.casefold()
        ]
        candidate_pool = same_category_hits or higher_priced_hits
        return min(
            candidate_pool,
            key=lambda hit: (abs((hit.price or 0.0) - (primary.price or 0.0)), -self._quality_score(hit), -hit.score),
        )

    def _build_sales_upsell_line(
        self,
        *,
        primary: InventorySearchHit,
        upsell: InventorySearchHit,
    ) -> str:
        return (
            f"If the customer is open to stepping up from {primary.name}, I would upsell to {upsell.name}"
            f"{self._format_optional_price_suffix(self._format_price_text(upsell))}."
        )

    def _select_cross_sell_candidate(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
        question: str,
    ) -> InventorySearchHit | None:
        explicit_cross_sell = self._should_offer_cross_sell(question)
        if not explicit_cross_sell:
            return None
        cross_sell_hits = [
            hit
            for hit in hits
            if not self._is_out_of_stock(hit)
            and self._quality_score(hit) >= 3
            and self.product_ontology.valid_cross_sell(primary, hit, explicit_cross_sell=explicit_cross_sell)
        ]
        if not cross_sell_hits:
            return None
        return max(
            cross_sell_hits,
            key=lambda hit: (self._quality_score(hit), hit.score, -(hit.price or 0.0), hit.name.casefold()),
        )

    def _is_related_candidate(
        self,
        *,
        primary: InventorySearchHit,
        candidate: InventorySearchHit,
    ) -> bool:
        return self.product_ontology.valid_alternative(primary, candidate)

    def _meaningful_tags(self, hit: InventorySearchHit) -> set[str]:
        return self.product_ontology.meaningful_tags(hit)

    def _should_offer_cross_sell(self, question: str) -> bool:
        normalized = self._normalize_conversation_text(question)
        return self._has_any_phrase(normalized, _CROSS_SELL_HINTS)

    def _build_cross_sell_line(
        self,
        *,
        primary: InventorySearchHit,
        cross_sell: InventorySearchHit,
    ) -> str:
        return (
            f"If the customer is building out a fuller setup around {primary.name}, I would also cross-sell {cross_sell.name}"
            f"{self._format_optional_price_suffix(self._format_price_text(cross_sell))}."
        )

    def _comparison_price_note(self, *, primary: InventorySearchHit, alternative: InventorySearchHit) -> str | None:
        if primary.price is None or alternative.price is None:
            return None
        if primary.price < alternative.price:
            return (
                f"{primary.name} is the lower-price option at {self._format_price_text(primary)}, while {alternative.name} is {self._format_price_text(alternative)}."
            )
        if primary.price > alternative.price:
            return (
                f"{alternative.name} is the lower-price option at {self._format_price_text(alternative)}, while {primary.name} is {self._format_price_text(primary)}."
            )
        return f"Both products are listed at {self._format_price_text(primary)}."

    @staticmethod
    def _decision_score(
        *,
        hit: InventorySearchHit,
        strategy: str,
        fallback: float,
    ) -> float:
        value = hit.evidence_scores.get(f"deterministic_{strategy}_score")
        if isinstance(value, (int, float)):
            return float(value)
        return float(fallback)

    @staticmethod
    def _decision_reasons(
        *,
        hit: InventorySearchHit,
        strategy: str,
    ) -> list[str]:
        value = hit.evidence_scores.get(f"deterministic_{strategy}_reasons")
        if isinstance(value, list):
            return [reason for reason in value if isinstance(reason, str) and reason]
        if isinstance(value, tuple):
            return [reason for reason in value if isinstance(reason, str) and reason]
        return []

    def _agentic_primary_hit_for_bundle(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
    ) -> InventorySearchHit | None:
        if not hits:
            return None
        ranked_hits = self._rank_support_hits(
            question=question,
            hits=hits,
            filters=filters,
            low_stock_threshold=self.config.low_stock_threshold,
        )
        for hit in ranked_hits:
            product_type = self.product_ontology.detect_product_type(product=hit)
            if product_type in self.product_ontology.CROSS_SELL_COMPATIBILITY:
                return hit
        return ranked_hits[0]

    def _bundle_add_on_query(self, *, primary: InventorySearchHit, question: str) -> str:
        product_type = self.product_ontology.detect_product_type(product=primary)
        compatible_types = sorted(self.product_ontology.CROSS_SELL_COMPATIBILITY.get(product_type or "", set()))
        compatibility_hint = " ".join(compatible_types)
        anchor = product_type or primary.category or primary.name
        if compatibility_hint:
            return f"{compatibility_hint} accessory add on bundle for {anchor} {primary.category} {primary.name}"
        return f"{anchor} accessory add on bundle pair with {primary.name}"

    def _bundle_add_on_hits(
        self,
        *,
        primary: InventorySearchHit,
        filters: InventorySearchFilters,
        top_k: int,
    ) -> list[InventorySearchHit]:
        compatible_hits: list[InventorySearchHit] = []
        for item in self._load_catalog().values():
            if item.product_id == primary.product_id or not self._item_matches_filters(item, filters):
                continue
            hit = self._build_search_hit(item=item, score=0.0)
            if self._is_out_of_stock(hit):
                continue
            if not self.product_ontology.valid_cross_sell(primary, hit, explicit_cross_sell=True):
                continue
            compatibility_score = round(0.5 + (self._quality_score(hit) / 20.0), 4)
            compatible_hits.append(hit.model_copy(update={"score": compatibility_score}))
        compatible_hits.sort(
            key=lambda hit: (
                self._quality_score(hit),
                hit.score,
                -(hit.price or 0.0),
                hit.name.casefold(),
            ),
            reverse=True,
        )
        return compatible_hits[:top_k]

    def _append_agentic_analysis_steps(
        self,
        *,
        retrieval_steps: list[InventoryAgenticStep],
        analysis_actions: tuple[str, ...],
        question: str,
        reply: InventoryReply,
        business_insight: InventoryBusinessInsight,
        max_reasoning_steps: int,
    ) -> list[InventoryAgenticStep]:
        if not analysis_actions or len(retrieval_steps) >= max_reasoning_steps:
            return retrieval_steps
        evidence_contract = reply.answer_plan.evidence_contract
        if evidence_contract is None:
            return retrieval_steps

        candidate_name = {
            candidate.product_id: candidate.name
            for candidate in evidence_contract.candidate_evidence
        }
        for action in analysis_actions:
            if len(retrieval_steps) >= max_reasoning_steps:
                break
            selected_ids: list[str]
            observation: str
            selected_candidates: list[InventoryTraceCandidateDebug]
            if action == "align_comparison_facts":
                selected_ids = evidence_contract.primary_candidate_ids[:2]
                selected_names = [candidate_name[product_id] for product_id in selected_ids if product_id in candidate_name]
                selected_candidates = [
                    self._trace_candidate_debug_from_evidence_candidate(candidate)
                    for candidate in evidence_contract.candidate_evidence
                    if candidate.product_id in selected_ids
                ]
                observation = (
                    f"Aligned structured comparison facts for {self._natural_join(selected_names)} using the evidence contract."
                )
            elif action == "filter_compatible_add_ons":
                selected_ids = [
                    product_id
                    for product_id in [
                        reply.answer_plan.primary_product_id,
                        *reply.answer_plan.cross_sell_product_ids,
                    ]
                    if product_id
                ]
                selected_names = [candidate_name[product_id] for product_id in selected_ids if product_id in candidate_name]
                selected_candidates = [
                    self._trace_candidate_debug_from_evidence_candidate(candidate)
                    for candidate in evidence_contract.candidate_evidence
                    if candidate.product_id in selected_ids
                ]
                observation = (
                    f"Filtered bundle add-ons through the evidence contract and kept {self._natural_join(selected_names)} as compatible roles."
                )
            elif action == "rank_operational_candidates":
                selected_ids = business_insight.selected_product_ids or evidence_contract.primary_candidate_ids[:3]
                selected_names = [candidate_name[product_id] for product_id in selected_ids if product_id in candidate_name]
                selected_candidates = [
                    self._trace_candidate_debug_from_evidence_candidate(candidate)
                    for candidate in evidence_contract.candidate_evidence
                    if candidate.product_id in selected_ids
                ]
                observation = (
                    f"Ranked operational candidates for restock using demand, margin, lead time, and stock evidence across {self._natural_join(selected_names)}."
                )
            elif action == "diagnose_root_cause_facts":
                selected_ids = business_insight.selected_product_ids or evidence_contract.primary_candidate_ids[:3]
                selected_names = [candidate_name[product_id] for product_id in selected_ids if product_id in candidate_name]
                selected_candidates = [
                    self._trace_candidate_debug_from_evidence_candidate(candidate)
                    for candidate in evidence_contract.candidate_evidence
                    if candidate.product_id in selected_ids
                ]
                observation = (
                    f"Aligned likely root-cause factors for {self._natural_join(selected_names)} using business signals and the evidence contract."
                )
            elif action == "compose_operational_plan":
                selected_ids = business_insight.selected_product_ids or evidence_contract.primary_candidate_ids[:3]
                selected_names = [candidate_name[product_id] for product_id in selected_ids if product_id in candidate_name]
                selected_candidates = [
                    self._trace_candidate_debug_from_evidence_candidate(candidate)
                    for candidate in evidence_contract.candidate_evidence
                    if candidate.product_id in selected_ids
                ]
                observation = (
                    f"Composed a bounded operational plan across {self._natural_join(selected_names)} using catalog constraints and matched business signals."
                )
            else:
                continue
            retrieval_steps.append(
                InventoryAgenticStep(
                    step_number=len(retrieval_steps) + 1,
                    action=action,
                    query_text=question,
                    applied_filters=InventorySearchFilters(),
                    total_hits=len(selected_ids),
                    selected_product_ids=selected_ids,
                    selected_candidates=selected_candidates,
                    rejected_candidates=[],
                    observation=observation,
                )
            )
        return retrieval_steps

    def _build_sales_follow_up_question(
        self,
        *,
        sales_style: str,
        primary: InventorySearchHit,
    ) -> str:
        if sales_style == "budget":
            return "Do you want me to keep the next recommendation budget-first, or should I show the stronger step-up option too?"
        if sales_style == "premium":
            return f"Do you want a more accessible fallback next to {primary.name}, or should I keep the conversation fully premium?"
        if sales_style == "availability":
            return "Should I keep the shortlist focused on what is sellable now, or should I include stronger but tighter-stock options too?"
        return "Do you want a lower-price fallback, a stronger premium option, or a complementary add-on next?"

    def _top_hit_categories(self, hits: list[InventorySearchHit], limit: int = 3) -> list[str]:
        quality_hits = [hit for hit in hits if self._quality_score(hit) >= 3]
        source_hits = quality_hits or hits
        categories: list[str] = []
        seen: set[str] = set()
        for hit in source_hits:
            if not hit.category:
                continue
            lowered = hit.category.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            categories.append(hit.category)
            if len(categories) >= limit:
                break
        return categories

    def _rank_support_hits(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        low_stock_threshold: int,
    ) -> list[InventorySearchHit]:
        lowered = question.casefold()
        if self._has_any_phrase(lowered, ["low stock", "running low", "below threshold", "limited stock"]):
            return sorted(
                hits,
                key=lambda hit: (
                    float("inf") if hit.stock is None else hit.stock,
                    -self._quality_score(hit),
                    -hit.score,
                    hit.name.casefold(),
                ),
            )
        if self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]):
            return sorted(
                hits,
                key=lambda hit: (
                    0 if (hit.stock or 0) == 0 else 1,
                    -self._quality_score(hit),
                    -hit.score,
                    hit.name.casefold(),
                ),
            )
        if self._has_any_phrase(lowered, ["most expensive", "highest price", "expensive"]):
            return sorted(
                hits,
                key=lambda hit: (
                    self._price_sort_key(hit, reverse=True),
                    -self._quality_score(hit),
                    -hit.score,
                    hit.name.casefold(),
                ),
            )
        if self._has_any_phrase(lowered, ["cheapest", "lowest price", "least expensive"]):
            return sorted(
                hits,
                key=lambda hit: (
                    self._price_sort_key(hit),
                    -self._quality_score(hit),
                    -hit.score,
                    hit.name.casefold(),
                ),
            )
        return sorted(
            hits,
            key=lambda hit: (
                self._is_out_of_stock(hit),
                -self._quality_score(hit),
                -hit.score,
                self._price_sort_key(hit),
                -(hit.stock or 0),
                hit.name.casefold(),
            ),
        )

    @staticmethod
    def _normalize_conversation_text(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s']", " ", text.casefold())
        return " ".join(normalized.split())

    def _extract_query_terms(self, text: str) -> list[str]:
        normalized = self._normalize_conversation_text(text)
        terms: list[str] = []
        for token in normalized.split():
            normalized_token = self._normalize_query_token(token)
            if (
                not normalized_token
                or normalized_token in _QUERY_STOPWORDS
                or normalized_token.isdigit()
            ):
                continue
            terms.append(normalized_token)
        return terms

    def _extract_subject_phrase(self, text: str) -> str | None:
        normalized = self._normalize_conversation_text(text)
        for phrase in _DETAIL_REQUEST_PHRASES:
            if phrase not in normalized:
                continue
            subject = normalized.split(phrase, 1)[1].strip()
            if not subject:
                return None
            normalized_subject = self._normalize_search_text(subject)
            if not normalized_subject:
                return None
            return normalized_subject
        return None

    def _is_detail_request(self, text: str) -> bool:
        normalized = self._normalize_conversation_text(text)
        return self._has_any_phrase(normalized, _DETAIL_REQUEST_PHRASES)

    def _should_require_exact_lookup(
        self,
        *,
        query_text: str,
        query_terms: list[str],
        subject_phrase: str | None,
        detail_request: bool,
    ) -> bool:
        if detail_request or subject_phrase:
            return True
        if not query_terms or len(query_terms) > 2:
            return False
        normalized = self._normalize_conversation_text(query_text)
        if self._has_any_phrase(normalized, ["recommend", "suggest", "alternative", "similar"]):
            return False
        return self._has_any_phrase(normalized, _EXACT_LOOKUP_PHRASES)

    @staticmethod
    def _normalize_query_token(token: str) -> str:
        if token.endswith("ies") and len(token) > 4:
            return token[:-3] + "y"
        if token.endswith("es") and len(token) > 4 and not token.endswith(("ses", "xes", "zes")):
            return token[:-2]
        if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
            return token[:-1]
        return token

    def _normalize_search_text(self, text: str | None) -> str:
        if not text:
            return ""
        tokens = [self._normalize_query_token(token) for token in self._normalize_conversation_text(text).split()]
        return " ".join(token for token in tokens if token)

    def _tokenize_search_text(self, text: str | None) -> set[str]:
        return set(self._normalize_search_text(text).split())

    def _lexical_match_score(
        self,
        *,
        item: InventoryItemRecord,
        query_terms: list[str],
        subject_phrase: str | None,
    ) -> float:
        if not query_terms and not subject_phrase:
            return 0.0

        name_text = self._normalize_search_text(item.name)
        sku_text = self._normalize_search_text(item.sku)
        category_text = self._normalize_search_text(item.category)
        brand_text = self._normalize_search_text(item.brand)
        status_text = self._normalize_search_text(item.status)
        tag_text = self._normalize_search_text(" ".join(item.tags))
        snippet_text = self._normalize_search_text(item.short_description or item.full_description)
        alias_texts = self._search_alias_texts(item)
        alias_token_sets = [set(alias.split()) for alias in alias_texts]
        alias_tokens = {token for tokens in alias_token_sets for token in tokens}
        all_text = " ".join(
            part for part in (name_text, sku_text, category_text, brand_text, status_text, tag_text, snippet_text) if part
        )
        compact_subject_phrase = subject_phrase.replace(" ", "") if subject_phrase else None
        compact_query = "".join(query_terms)

        field_tokens = {
            "name": set(name_text.split()),
            "sku": set(sku_text.split()),
            "category": set(category_text.split()),
            "brand": set(brand_text.split()),
            "status": set(status_text.split()),
            "tags": set(tag_text.split()),
            "snippet": set(snippet_text.split()),
            "all": set(all_text.split()),
        }

        score = 0.0
        if subject_phrase:
            if subject_phrase == name_text:
                score += 14.0
            elif subject_phrase in name_text:
                score += 11.0
            elif subject_phrase in all_text:
                score += 8.0
            if subject_phrase in alias_texts:
                score += 13.0
            elif any(subject_phrase in alias for alias in alias_texts):
                score += 9.5
        if compact_subject_phrase:
            if compact_subject_phrase in alias_texts:
                score += 12.0
            elif any(compact_subject_phrase in alias for alias in alias_texts):
                score += 8.5

        for term in query_terms:
            if term in field_tokens["name"]:
                score += 5.0
            elif term in name_text:
                score += 3.5
            if term in field_tokens["sku"]:
                score += 6.0
            if term in field_tokens["category"]:
                score += 4.0
            if term in field_tokens["tags"]:
                score += 4.0
            if term in field_tokens["brand"]:
                score += 3.0
            if term in field_tokens["status"]:
                score += 2.5
            if term in field_tokens["snippet"]:
                score += 1.5
            if term in alias_tokens:
                score += 4.5
            elif any(term in alias for alias in alias_texts):
                score += 3.0

        if query_terms and all(term in field_tokens["all"] for term in query_terms):
            score += 5.0
        if query_terms and all(term in field_tokens["name"] for term in query_terms):
            score += 4.0
        if query_terms and any(all(term in alias_tokens_for_item for term in query_terms) for alias_tokens_for_item in alias_token_sets):
            score += 5.0
        if compact_query and compact_query in alias_texts:
            score += 7.0
        return score

    def _query_term_coverage(
        self,
        *,
        item: InventoryItemRecord,
        query_terms: list[str],
    ) -> int:
        if not query_terms:
            return 0
        searchable_tokens = (
            self._tokenize_search_text(item.name)
            | self._tokenize_search_text(item.sku)
            | self._tokenize_search_text(item.category)
            | self._tokenize_search_text(item.brand)
            | self._tokenize_search_text(item.status)
            | self._tokenize_search_text(" ".join(item.tags))
            | self._tokenize_search_text(item.short_description)
            | self._tokenize_search_text(item.full_description)
        )
        for alias in self._search_alias_texts(item):
            searchable_tokens |= self._tokenize_search_text(alias)
        return sum(1 for term in query_terms if term in searchable_tokens)

    def _build_exact_no_match_answer(self, *, question: str) -> str | None:
        query_terms = self._extract_query_terms(question)
        subject_phrase = self._extract_subject_phrase(question)
        if not self._should_require_exact_lookup(
            query_text=question,
            query_terms=query_terms,
            subject_phrase=subject_phrase,
            detail_request=self._is_detail_request(question),
        ):
            return None
        target = subject_phrase or " ".join(query_terms[:3])
        if not target:
            return "I could not find an exact catalog match for that request."
        return f"I could not find an exact catalog match for {target} in the current inventory."

    def _should_anchor_to_lexical(
        self,
        *,
        query_terms: list[str],
        subject_phrase: str | None,
        best_lexical_score: float,
        detail_request: bool,
    ) -> bool:
        if best_lexical_score < 6.0:
            return False
        if detail_request or subject_phrase:
            return True
        return len(query_terms) <= 3

    def _resolve_explicit_requested_category(
        self,
        *,
        query_text: str,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
        preference_profile: InventoryPreferenceProfile,
    ) -> str | None:
        if filters.categories:
            return filters.categories[0]

        normalized_query = self._normalize_search_text(query_text)
        if not normalized_query:
            return None

        category_candidates: dict[str, str] = {}
        for item in catalog.values():
            if item.category:
                category_candidates.setdefault(self._normalize_search_text(item.category), item.category)
        for category in self.product_ontology.DEFAULT_CATEGORY_BY_TYPE.values():
            category_candidates.setdefault(self._normalize_search_text(category), category)

        matched_categories = [
            category
            for normalized_category, category in category_candidates.items()
            if normalized_category
            and self._contains_normalized_phrase(normalized_query, normalized_category)
        ]
        if matched_categories:
            return max(matched_categories, key=lambda category: len(category.strip()))

        if preference_profile.category and not preference_profile.product_type:
            normalized_category = self._normalize_search_text(preference_profile.category)
            if normalized_category and self._contains_normalized_phrase(normalized_query, normalized_category):
                return preference_profile.category
        return None

    @staticmethod
    def _contains_normalized_phrase(text: str, phrase: str) -> bool:
        return bool(re.search(rf"\b{re.escape(phrase)}\b", text))

    def _exact_reference_match_signals(
        self,
        *,
        query_text: str,
        query_terms: list[str],
        subject_phrase: str | None,
        item: InventoryItemRecord,
    ) -> tuple[float, float]:
        candidate_texts: list[str] = []
        normalized_query = self._normalize_search_text(query_text)
        if normalized_query:
            candidate_texts.append(normalized_query)
        if query_terms:
            candidate_texts.append(" ".join(query_terms))
        if subject_phrase:
            normalized_subject = self._normalize_search_text(subject_phrase)
            if normalized_subject:
                candidate_texts.append(normalized_subject)

        exact_name_targets = {
            normalized
            for normalized in (
                self._normalize_search_text(item.name),
            )
            if normalized
        }
        exact_sku_targets = {
            normalized
            for normalized in (
                self._normalize_search_text(item.sku),
            )
            if normalized
        }
        compact_name_targets = {target.replace(" ", "") for target in exact_name_targets if len(target.replace(" ", "")) >= 4}
        compact_sku_targets = {target.replace(" ", "") for target in exact_sku_targets if len(target.replace(" ", "")) >= 4}

        for candidate_text in candidate_texts:
            compact_candidate = candidate_text.replace(" ", "")
            if candidate_text in exact_sku_targets or compact_candidate in compact_sku_targets:
                return 0.0, 1.0
            if candidate_text in exact_name_targets or compact_candidate in compact_name_targets:
                return 1.0, 0.0
        return 0.0, 0.0

    def _is_strong_product_reference(
        self,
        *,
        question: str,
        hit: InventorySearchHit,
    ) -> bool:
        query_terms = self._extract_query_terms(question)
        subject_phrase = self._extract_subject_phrase(question)
        name_text = self._normalize_search_text(hit.name)
        sku_text = self._normalize_search_text(hit.sku)
        alias_texts = self._search_alias_texts(
            InventoryItemRecord(
                product_id=hit.product_id,
                sku=hit.sku,
                name=hit.name,
                category=hit.category,
                brand=hit.brand,
                short_description=hit.snippet,
                price=hit.price,
                currency=hit.currency or "USD",
                stock=hit.stock or 0,
                status=hit.status,
                tags=list(hit.tags),
                attributes=dict(hit.attributes),
                metadata=dict(hit.metadata),
                include_in_rag=True,
                updated_at=hit.updated_at,
            )
        )
        if subject_phrase and (subject_phrase == name_text or subject_phrase in name_text or subject_phrase in sku_text):
            return True
        if subject_phrase and any(subject_phrase == alias or subject_phrase in alias for alias in alias_texts):
            return True
        if not query_terms:
            return False
        query_term_set = set(query_terms)
        searchable_tokens = (
            self._tokenize_search_text(hit.name)
            | self._tokenize_search_text(hit.sku)
            | self._tokenize_search_text(hit.category)
            | self._tokenize_search_text(hit.brand)
            | self._tokenize_search_text(" ".join(hit.tags))
        )
        for alias in alias_texts:
            searchable_tokens |= self._tokenize_search_text(alias)
        return len(query_term_set.intersection(searchable_tokens)) >= max(1, len(query_term_set) - 1)

    @staticmethod
    def _looks_like_inventory_request(text: str) -> bool:
        return any(phrase in text for phrase in _INVENTORY_REQUEST_HINTS)

    def _quality_score(self, hit: InventorySearchHit) -> int:
        score = 0
        if len(hit.name.strip()) >= 4:
            score += 2
        if hit.category and len(hit.category.strip()) >= 3:
            score += 1
        if hit.brand and len(hit.brand.strip()) >= 3:
            score += 1
        if hit.snippet and len(hit.snippet.strip()) >= 18:
            score += 2
        if hit.price is not None:
            score += 1
        if hit.stock is not None:
            score += 1
        if hit.tags:
            score += 1
        short_fields = [value for value in (hit.category, hit.brand, hit.snippet) if value and len(value.strip()) <= 2]
        score -= len(short_fields)
        return score

    def _format_option_label(self, hit: InventorySearchHit) -> str:
        details: list[str] = []
        if hit.price is not None:
            details.append(self._format_price_text(hit))
        if hit.stock is not None:
            details.append(f"{hit.stock} in stock")
        if hit.brand:
            details.append(hit.brand)
        return f"{hit.name} ({', '.join(details)})" if details else hit.name

    @staticmethod
    def _natural_join(parts: Iterable[str]) -> str:
        values = [part for part in parts if isinstance(part, str) and part]
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]} and {values[1]}"
        return ", ".join(values[:-1]) + f", and {values[-1]}"

    @staticmethod
    def _catalog_sort_key(item: InventoryItemRecord) -> tuple[str, str]:
        updated_key = item.updated_at or ""
        return (updated_key, item.name.casefold())


@lru_cache(maxsize=1)
def get_inventory_service() -> InventoryService:
    settings = get_settings()
    return InventoryService(
        embedder=build_embedder(),
        vector_store=build_vector_store(),
        config=InventoryServiceConfig(
            catalog_path=settings.inventory_catalog_path,
            namespace=settings.inventory_vector_namespace,
            default_top_k=settings.top_k,
            agentic_trace_dir=str(Path(settings.trace_dir) / "inventory_agentic"),
            chat_trace_dir=str(Path(settings.trace_dir) / "inventory_chat"),
            business_signal_path=settings.inventory_business_signal_path,
            inventory_storage_backend=settings.inventory_storage_backend,
            inventory_sqlite_path=settings.inventory_sqlite_path,
            natural_answers_enabled=settings.inventory_natural_answers_enabled,
            natural_answer_model_name=settings.inventory_natural_answer_model_name,
            natural_answer_temperature=settings.inventory_natural_answer_temperature,
            natural_answer_max_tokens=settings.inventory_natural_answer_max_tokens,
            natural_answer_min_confidence=settings.inventory_natural_answer_min_confidence,
            natural_answer_timeout_seconds=settings.inventory_natural_answer_timeout_seconds,
            conversation_history_limit=settings.inventory_conversation_history_limit,
        ),
    )
   
