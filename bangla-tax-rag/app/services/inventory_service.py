from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

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
    InventoryCatalogResponse,
    InventoryConversationTurn,
    InventoryDeleteResponse,
    InventoryExecutionContract,
    InventoryItemRecord,
    InventoryRouteRequest,
    InventoryRouteResponse,
    InventoryRouteSignals,
    InventorySearchFilters,
    InventorySearchHit,
    InventorySearchRequest,
    InventorySearchResponse,
    InventoryStatusResponse,
    InventoryUpsertResponse,
)
from app.core.settings import get_settings
from app.generation.generator import ChatMessage, build_generation_options, get_chat_client
from app.inventory import (
    InventoryIntentClassifier,
    InventoryIntentResult,
    InventoryPreferenceExtractor,
    InventoryPreferenceProfile,
    ProductOntology,
)
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
        self.product_ontology = ProductOntology()
        self.intent_classifier = InventoryIntentClassifier(self.product_ontology)
        self.preference_extractor = InventoryPreferenceExtractor(self.product_ontology)

    def status(self) -> InventoryStatusResponse:
        items = self._load_catalog()
        rag_enabled_count = sum(1 for item in items.values() if item.include_in_rag)
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
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
        catalog = self._load_catalog()
        top_k = min(request.top_k, self.config.max_top_k)
        query_text = (request.query_text or "").strip()
        if query_text:
            hits = self._semantic_search(query_text=query_text, top_k=top_k, filters=request.filters, catalog=catalog)
        else:
            hits = self._browse_items(top_k=top_k, filters=request.filters, catalog=catalog)
        return InventorySearchResponse(
            status="success",
            query_text=query_text or None,
            total_hits=len(hits),
            applied_filters=request.filters,
            hits=hits,
        )

    def ask(self, request: InventoryAskRequest) -> InventoryAskResponse:
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
            return InventoryAskResponse(
                status="success",
                question=request.question,
                answer=reply.answer,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
                answer_engine="deterministic",
                confidence_score=confidence_score,
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
            )

        effective_filters = self._merge_question_filters(
            question=request.question,
            filters=request.filters,
            low_stock_threshold=request.low_stock_threshold,
        )
        search_response = self.search(
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
        reply = self._build_answer(
            question=request.question,
            hits=ordered_hits,
            filters=effective_filters,
            low_stock_threshold=request.low_stock_threshold,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
        )
        confidence_score = self._estimate_confidence(ordered_hits)
        abstention_reason = self._build_abstention_reason(
            question=request.question,
            hits=ordered_hits,
        )
        reply, answer_engine, abstained, abstention_reason = self._finalize_inventory_reply(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            requested_answer_engine=request.answer_engine,
            confidence_score=confidence_score,
            hits=ordered_hits,
            base_reply=reply,
            conversation_history=request.conversation_history,
            conversation_summary=request.conversation_summary,
            abstention_reason=abstention_reason,
            execution_path="inventory_ask",
        )
        return InventoryAskResponse(
            status="success",
            question=request.question,
            answer=reply.answer,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            answer_engine=answer_engine,
            confidence_score=confidence_score,
            abstained=abstained,
            abstention_reason=abstention_reason,
            total_hits=search_response.total_hits,
            applied_filters=effective_filters,
            hits=ordered_hits,
            recommended_product_ids=reply.recommended_product_ids,
            cross_sell_product_ids=reply.cross_sell_product_ids,
            follow_up_question=reply.follow_up_question,
            answer_plan=reply.answer_plan,
            verification=reply.verification,
        )

    def route(self, request: InventoryRouteRequest) -> InventoryRouteResponse:
        signals = self._build_route_signals(
            question=request.question,
            filters=request.filters,
        )
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
            recommended_path=recommended_path,
            fallback_path="normal_rag",
            decision_confidence=decision_confidence,
            reason_summary=reason_summary,
            decision_factors=decision_factors,
            required_data_domains=required_data_domains,
            missing_data_domains=missing_data_domains,
            signals=signals,
            normal_rag_contract=self._build_normal_rag_contract(request=request),
            agentic_contract=self._build_agentic_contract(
                request=request,
                required_data_domains=required_data_domains,
                missing_data_domains=missing_data_domains,
            ),
        )

    def agentic_ask(self, request: InventoryAgenticRequest) -> InventoryAgenticResponse:
        reasoning_summary: list[str] = []
        missing_facts: list[str] = []
        route_request = InventoryRouteRequest(
            question=request.question,
            assistant_mode=request.assistant_mode,
            reply_style=request.reply_style,
            filters=request.filters.model_copy(deep=True),
            audience=request.audience,
            prefer_fast_response=False,
            allow_agentic=True,
            available_data_domains=list(request.available_data_domains),
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
            filters=request.filters.model_copy(deep=True),
            low_stock_threshold=request.low_stock_threshold,
        )
        search_requests = self._build_agentic_search_requests(
            question=request.question,
            filters=effective_filters,
            low_stock_threshold=request.low_stock_threshold,
            max_reasoning_steps=request.max_reasoning_steps or self.config.default_agentic_max_reasoning_steps,
            route_response=route_response,
        )

        retrieval_steps: list[InventoryAgenticStep] = []
        aggregated_hits: list[InventorySearchHit] = []
        seen_hits: set[str] = set()
        for step_number, search_request in enumerate(search_requests, start=1):
            search_response = self.search(search_request)
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
            )
            retrieval_steps.append(
                InventoryAgenticStep(
                    step_number=step_number,
                    action=self._label_agentic_action(search_request=search_request, route_response=route_response),
                    query_text=search_request.query_text,
                    applied_filters=search_request.filters.model_copy(deep=True),
                    total_hits=search_response.total_hits,
                    selected_product_ids=[hit.product_id for hit in selected_hits],
                    observation=observation,
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
            final_reply = self._build_answer(
                question=request.question,
                hits=ordered_hits,
                filters=effective_filters,
                low_stock_threshold=request.low_stock_threshold,
                assistant_mode=request.assistant_mode,
                reply_style=request.reply_style,
            )
            confidence_score = self._estimate_confidence(ordered_hits)

        answer = self._compose_agentic_answer(
            base_answer=final_reply.answer,
            route_response=route_response,
            missing_facts=missing_facts,
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
            recommended_product_ids=final_reply.recommended_product_ids,
            cross_sell_product_ids=final_reply.cross_sell_product_ids,
            follow_up_question=final_reply.follow_up_question,
            answer_plan=final_reply.answer_plan,
            verification=final_reply.verification,
        )
        composed_reply, answer_engine, abstained, abstention_reason = self._finalize_inventory_reply(
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
        )
        answer = composed_reply.answer

        trace_id = str(uuid4())
        trace_payload = {
            "trace_id": trace_id,
            "question": request.question,
            "assistant_mode": request.assistant_mode,
            "reply_style": request.reply_style,
            "execution_path": "inventory_agentic",
            "reasoning_summary": reasoning_summary,
            "missing_facts": missing_facts,
            "retrieval_steps": [step.model_dump(mode="json") for step in retrieval_steps],
            "final_answer": answer,
            "confidence_score": confidence_score,
        }
        self.trace_store.save(trace_payload)
        return InventoryAgenticResponse(
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
        )

    def get_agentic_trace(self, trace_id: str) -> InventoryAgenticTraceResponse | None:
        payload = self.trace_store.load(trace_id)
        if payload is None:
            return None
        return InventoryAgenticTraceResponse.model_validate(payload)

    def _semantic_search(
        self,
        *,
        query_text: str,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
    ) -> list[InventorySearchHit]:
        query_vector = self.embedder.embed_text(query_text)
        vector_filters = self._build_vector_filters(filters)
        candidate_limit = max(top_k * self.config.search_candidate_multiplier, top_k)
        result = self.vector_store.query(
            query_vector,
            top_k=candidate_limit,
            filters=vector_filters or None,
            namespace=self.config.namespace,
        )

        vector_scores = {
            match.record_id: match.score
            for match in result.matches
            if match.record_id in catalog and self._item_matches_filters(catalog[match.record_id], filters)
        }
        query_terms = self._extract_query_terms(query_text)
        subject_phrase = self._extract_subject_phrase(query_text)
        detail_request = self._is_detail_request(query_text)
        exact_lookup = self._should_require_exact_lookup(
            query_text=query_text,
            query_terms=query_terms,
            subject_phrase=subject_phrase,
            detail_request=detail_request,
        )
        preference_profile = self.preference_extractor.extract(
            query_text,
            filters=filters,
            products=list(catalog.values()),
        )
        requested_product_type = preference_profile.product_type
        if detail_request and subject_phrase and len(subject_phrase.split()) >= 3:
            requested_product_type = None

        candidates: list[tuple[InventorySearchHit, float, float, int, int]] = []
        for item in catalog.values():
            if not self._item_matches_filters(item, filters):
                continue
            lexical_score = self._lexical_match_score(
                item=item,
                query_terms=query_terms,
                subject_phrase=subject_phrase,
            )
            coverage = self._query_term_coverage(item=item, query_terms=query_terms)
            vector_score = vector_scores.get(item.product_id, 0.0)
            if lexical_score <= 0 and item.product_id not in vector_scores:
                continue
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
            return []

        if requested_product_type:
            exact_type_candidates = [candidate for candidate in candidates if candidate[4] >= 3]
            related_type_candidates = [candidate for candidate in candidates if candidate[4] >= 2]
            if exact_type_candidates:
                candidates = exact_type_candidates
            elif related_type_candidates and not exact_lookup:
                candidates = related_type_candidates
            elif exact_lookup:
                return []

        if exact_lookup:
            max_coverage = max(coverage for _, _, _, coverage, _ in candidates)
            if max_coverage <= 0:
                return []
            coverage_threshold = len(query_terms) if len(query_terms) <= 2 else max(1, len(query_terms) - 1)
            exact_candidates = [candidate for candidate in candidates if candidate[3] >= coverage_threshold]
            if exact_candidates:
                candidates = exact_candidates
            else:
                return []

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
                candidates = anchored_candidates

        ranked_candidates = sorted(
            candidates,
            key=lambda candidate: (
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
        return [hit for hit, _, _, _, _ in ranked_candidates[:top_k]]

    def _browse_items(
        self,
        *,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
    ) -> list[InventorySearchHit]:
        items = [
            item
            for item in sorted(catalog.values(), key=self._catalog_sort_key, reverse=True)
            if self._item_matches_filters(item, filters)
        ]
        return [self._build_search_hit(item=item, score=0.0) for item in items[:top_k]]

    def _merge_question_filters(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        low_stock_threshold: int,
    ) -> InventorySearchFilters:
        merged = filters.model_copy(deep=True)
        lowered = question.casefold()

        if self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]):
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
        needs_root_cause_reasoning = self._has_any_phrase(normalized, _ROOT_CAUSE_HINTS) and not is_small_talk
        needs_workflow_action = self._has_any_phrase(normalized, _WORKFLOW_ACTION_HINTS) or (
            "should we" in normalized or "should i" in normalized
        )
        needs_multi_step_reasoning = self._has_any_phrase(normalized, _MULTI_STEP_REASONING_HINTS)
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
                has_explicit_product_reference
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
            is_small_talk=is_small_talk,
            has_explicit_product_reference=has_explicit_product_reference,
            simple_catalog_lookup=simple_catalog_lookup,
            needs_historical_data=needs_historical_data,
            needs_cross_system_data=needs_cross_system_data,
            needs_root_cause_reasoning=needs_root_cause_reasoning,
            needs_workflow_action=needs_workflow_action,
            needs_multi_step_reasoning=needs_multi_step_reasoning,
        )

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
        if "order" in normalized or "orders" in normalized:
            required.append("orders")
        if any(term in normalized for term in ("supplier", "suppliers", "vendor", "vendors", "purchase order")):
            required.append("suppliers")
        if "customer" in normalized or "customers" in normalized:
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
        return "Escalate to agentic handling because the question needs multi-step reasoning beyond straightforward catalog retrieval."

    def _build_agentic_search_requests(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        low_stock_threshold: int,
        max_reasoning_steps: int,
        route_response: InventoryRouteResponse,
    ) -> list[InventorySearchRequest]:
        search_requests: list[InventorySearchRequest] = [
            InventorySearchRequest(
                query_text=question,
                top_k=min(max(self.config.default_top_k, 5), self.config.max_top_k),
                filters=filters.model_copy(deep=True),
            )
        ]
        signals = route_response.signals
        if max_reasoning_steps <= 1:
            return search_requests

        keyword_query = " ".join(self._extract_query_terms(question))
        if not signals.has_explicit_product_reference and keyword_query and keyword_query != self._normalize_conversation_text(question):
            search_requests.append(
                InventorySearchRequest(
                    query_text=keyword_query,
                    top_k=min(max(self.config.default_top_k, 5), self.config.max_top_k),
                    filters=filters.model_copy(deep=True),
                )
            )

        if len(search_requests) >= max_reasoning_steps:
            return search_requests[:max_reasoning_steps]

        if signals.needs_workflow_action or self._has_any_phrase(
            self._normalize_conversation_text(question),
            ["restock", "reorder", "low stock", "running low"],
        ):
            low_stock_filters = filters.model_copy(deep=True)
            if low_stock_filters.max_stock is None:
                low_stock_filters.max_stock = low_stock_threshold
            search_requests.append(
                InventorySearchRequest(
                    query_text=keyword_query or question,
                    top_k=min(max(self.config.default_top_k, 5), self.config.max_top_k),
                    filters=low_stock_filters,
                )
            )

        if len(search_requests) >= max_reasoning_steps:
            return search_requests[:max_reasoning_steps]

        return search_requests[:max_reasoning_steps]

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
    ) -> str:
        if total_hits == 0:
            return f"Step {step_number} found no supporting catalog hits for the current search angle."
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

    def _compose_agentic_answer(
        self,
        *,
        base_answer: str,
        route_response: InventoryRouteResponse,
        missing_facts: list[str],
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
    ) -> tuple[InventoryReply, str, bool, str | None]:
        abstained = abstention_reason is not None
        answer_engine = self._resolve_inventory_answer_engine(
            requested_answer_engine=requested_answer_engine,
            confidence_score=confidence_score,
            hits=hits,
            abstention_reason=abstention_reason,
        )
        if answer_engine != "natural":
            return base_reply, "deterministic", abstained, abstention_reason

        synthesized_reply = self._synthesize_inventory_reply(
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
        )
        if synthesized_reply is None or synthesized_reply.abstained or not synthesized_reply.answer.strip():
            return base_reply, "deterministic", abstained, abstention_reason

        return (
            InventoryReply(
                answer=synthesized_reply.answer.strip(),
                recommended_product_ids=base_reply.recommended_product_ids,
                cross_sell_product_ids=base_reply.cross_sell_product_ids,
                follow_up_question=synthesized_reply.follow_up_question or base_reply.follow_up_question,
                answer_plan=base_reply.answer_plan,
                verification=base_reply.verification,
            ),
            "natural",
            False,
            None,
        )

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
    ) -> InventoryNaturalAnswer | None:
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
            )
            return self._parse_inventory_answer_model_output(raw_output)
        except Exception:
            logger.exception("Inventory natural answer synthesis failed; falling back to deterministic reply.")
            return None

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
    ) -> list[ChatMessage]:
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
            "draft_reply": {
                "answer": base_reply.answer,
                "follow_up_question": base_reply.follow_up_question,
                "recommended_product_ids": base_reply.recommended_product_ids,
                "cross_sell_product_ids": base_reply.cross_sell_product_ids,
            },
            "answer_plan": base_reply.answer_plan.model_dump(mode="json"),
            "verification": base_reply.verification.model_dump(mode="json"),
            "reasoning_summary": reasoning_summary,
            "missing_facts": missing_facts,
            "hits": self._serialize_inventory_hits(hits),
        }
        system_prompt = (
            "You are a grounded ecommerce sales and support assistant. "
            "Write like a natural human assistant, but only from the supplied answer plan, catalog evidence, metadata, and draft reply. "
            "Do not invent products, prices, stock levels, brands, categories, features, or policies. "
            "Do not change the product selection in answer_plan. "
            "Treat answer_plan as the product-selection authority and the draft reply as the wording scaffold. "
            "Use attributes and metadata when they are relevant, but never expose internal IDs or database implementation details to the user. "
            "Never mention products listed in answer_plan.excluded_product_ids as recommendations, alternatives, or cross-sells. "
            "If verification.passed is false, preserve caution and do not expand the recommendation. "
            "If the draft or evidence indicates no exact match, preserve that exactness and do not offer unrelated substitutes. "
            "Keep 'short' replies tight and conversational. Keep 'detailed' replies richer but still concise. "
            "If the evidence is too weak, set abstained to true. "
            "Return strict JSON with this shape: "
            '{"answer":"...", "follow_up_question":null, "abstained":false, "abstention_reason":null}'
        )
        if assistant_mode == "sales":
            system_prompt += (
                " In sales mode, sound helpful and persuasive, but never overclaim beyond the evidence."
            )
        else:
            system_prompt += " In support mode, sound clear, calm, and operationally reliable."
        user_prompt = (
            "Rewrite the grounded draft into a more natural answer.\n\n"
            "Evidence package:\n"
            f"{json.dumps(evidence_payload, ensure_ascii=False, indent=2)}"
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

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
        if assistant_mode == "sales":
            reply = self._build_sales_answer(
                question=question,
                hits=hits,
                filters=filters,
                low_stock_threshold=low_stock_threshold,
                reply_style=reply_style,
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
            hits=hits,
            strategy=reply.answer_plan.intent if reply.answer_plan.intent != "unknown" else assistant_mode,
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

        alternative = self._select_sales_alternative(
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
        plan = self._enrich_answer_plan(
            answer_plan=reply.answer_plan,
            intent_result=intent_result,
            preference_profile=preference_profile,
            strategy=strategy,
        )
        return InventoryReply(
            answer=reply.answer,
            recommended_product_ids=reply.recommended_product_ids,
            cross_sell_product_ids=reply.cross_sell_product_ids,
            follow_up_question=reply.follow_up_question,
            answer_plan=plan,
            verification=self._verify_answer_plan(answer_plan=plan, hits=hits),
        )

    @staticmethod
    def _enrich_answer_plan(
        *,
        answer_plan: InventoryAnswerPlan,
        intent_result: InventoryIntentResult,
        preference_profile: InventoryPreferenceProfile,
        strategy: str | None,
    ) -> InventoryAnswerPlan:
        plan_intent = answer_plan.intent
        if plan_intent == "unknown":
            plan_intent = intent_result.intent
        return answer_plan.model_copy(
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
        return InventoryAnswerVerification(passed=not issues, issues=issues)

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
            metadata=dict(item.metadata),
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
        return VectorRecord(
            record_id=item.product_id,
            vector=self.embedder.embed_text(self._build_search_text(item)),
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
            },
            text=self._build_search_text(item),
            namespace=self.config.namespace,
        )

    def _build_search_text(self, item: InventoryItemRecord) -> str:
        attribute_text = " ".join(f"{key} {value}" for key, value in sorted(item.attributes.items()))
        metadata_text = " ".join(f"{key} {value}" for key, value in sorted(item.metadata.items()))
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
        ]
        return " ".join(value.strip() for value in fields if isinstance(value, str) and value.strip())

    def _catalog_path(self) -> Path:
        return Path(self.config.catalog_path)

    def _load_catalog(self) -> dict[str, InventoryItemRecord]:
        catalog_path = self._catalog_path()
        if not catalog_path.exists():
            return {}
        items: dict[str, InventoryItemRecord] = {}
        with catalog_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                item = InventoryItemRecord.model_validate_json(stripped)
                items[item.product_id] = item
        return items

    def _persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        catalog_path = self._catalog_path()
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with catalog_path.open("w", encoding="utf-8") as handle:
            for item in sorted(items.values(), key=self._catalog_sort_key):
                handle.write(item.model_dump_json())
                handle.write("\n")

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
        if sales_style == "budget":
            return sorted(
                hits,
                key=lambda hit: (
                    self._is_out_of_stock(hit),
                    -self._quality_score(hit),
                    self._price_sort_key(hit),
                    -hit.score,
                    -(hit.stock or 0),
                    hit.name.casefold(),
                ),
            )
        if sales_style == "premium":
            return sorted(
                hits,
                key=lambda hit: (
                    self._is_out_of_stock(hit),
                    -self._premium_signal(hit),
                    -self._quality_score(hit),
                    self._price_sort_key(hit, reverse=True),
                    -hit.score,
                    -(hit.stock or 0),
                    hit.name.casefold(),
                ),
            )
        if sales_style == "urgency":
            return sorted(
                hits,
                key=lambda hit: (
                    self._is_out_of_stock(hit),
                    float("inf") if hit.stock is None else hit.stock,
                    -self._quality_score(hit),
                    -hit.score,
                    self._price_sort_key(hit),
                    hit.name.casefold(),
                ),
            )
        if sales_style == "availability":
            return sorted(
                hits,
                key=lambda hit: (
                    self._is_out_of_stock(hit),
                    -(hit.stock or 0),
                    -self._quality_score(hit),
                    -hit.score,
                    self._price_sort_key(hit),
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

    def _select_sales_alternative(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
        sales_style: str,
    ) -> InventorySearchHit | None:
        if not hits:
            return None
        quality_hits = [hit for hit in hits if self._quality_score(hit) >= 3]
        candidate_hits = quality_hits or hits
        if sales_style == "premium":
            lower_priced_hits = [
                hit
                for hit in candidate_hits
                if hit.price is not None and (primary.price is None or hit.price < primary.price)
            ]
            if lower_priced_hits:
                return min(
                    lower_priced_hits,
                    key=lambda hit: (-self._quality_score(hit), abs((primary.price or 0.0) - hit.price), -hit.score),
                )
        if sales_style == "budget":
            higher_priced_hits = [
                hit
                for hit in candidate_hits
                if hit.price is not None and (primary.price is None or hit.price > primary.price)
            ]
            if higher_priced_hits:
                return min(
                    higher_priced_hits,
                    key=lambda hit: (-self._quality_score(hit), hit.price, -hit.score),
                )
        cheaper_hits = [
            hit
            for hit in candidate_hits
            if hit.price is not None and (primary.price is None or hit.price < primary.price)
        ]
        if cheaper_hits:
            return min(
                cheaper_hits,
                key=lambda hit: (-self._quality_score(hit), hit.price, -hit.score),
            )
        return candidate_hits[0]

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
            subject_terms = self._extract_query_terms(subject)
            if not subject_terms:
                return None
            return " ".join(subject_terms)
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
        all_text = " ".join(
            part for part in (name_text, sku_text, category_text, brand_text, status_text, tag_text, snippet_text) if part
        )

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

        if query_terms and all(term in field_tokens["all"] for term in query_terms):
            score += 5.0
        if query_terms and all(term in field_tokens["name"] for term in query_terms):
            score += 4.0
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
        if subject_phrase and (subject_phrase == name_text or subject_phrase in name_text or subject_phrase in sku_text):
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
            natural_answers_enabled=settings.inventory_natural_answers_enabled,
            natural_answer_model_name=settings.inventory_natural_answer_model_name,
            natural_answer_temperature=settings.inventory_natural_answer_temperature,
            natural_answer_max_tokens=settings.inventory_natural_answer_max_tokens,
            natural_answer_min_confidence=settings.inventory_natural_answer_min_confidence,
            natural_answer_timeout_seconds=settings.inventory_natural_answer_timeout_seconds,
            conversation_history_limit=settings.inventory_conversation_history_limit,
        ),
    )
