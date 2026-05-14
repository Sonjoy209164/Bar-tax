import json
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.schemas import (
    CustomerProfileResponse,
    ImageIndexRebuildRequest,
    ImageIndexRebuildResponse,
    ImageIndexStatusResponse,
    ImageSearchCorrectionListResponse,
    ImageSearchCorrectionRequest,
    ImageSearchCorrectionResponse,
    ImageSearchFailureListResponse,
    ImageSearchRequest,
    ImageSearchResponse,
    ImageSearchHit,
    InventoryAgenticRequest,
    InventoryAgenticResponse,
    InventoryAgenticStatusResponse,
    InventoryAgenticTraceResponse,
    InventoryAskRequest,
    InventoryAskResponse,
    InventoryBusinessSignalsDeleteResponse,
    InventoryBusinessSignalsResponse,
    InventoryBusinessSignalsUpsertRequest,
    InventoryBusinessSignalsUpsertResponse,
    InventoryBusinessStatusResponse,
    InventoryCatalogResponse,
    InventoryChatTraceResponse,
    InventoryDeleteRequest,
    InventoryDeleteResponse,
    InventoryItemRecord,
    InventoryPolicyContractResponse,
    InventoryProductionStatusResponse,
    InventoryRouteRequest,
    InventoryRouteResponse,
    InventorySearchRequest,
    InventorySearchResponse,
    InventoryStatusResponse,
    InventorySyncRebuildResponse,
    InventorySyncStatusResponse,
    InventorySyncValidateRequest,
    InventorySyncValidateResponse,
    InventoryUpsertRequest,
    InventoryUpsertResponse,
    POSSyncImportRequest,
    POSSyncResponse,
    POSSyncStatusResponse,
    POSSyncWebhookRequest,
    PolicyQARequest,
    PolicyQAResponse,
)
from app.inventory.catalog_audit import audit_catalog, enrich_item_attributes
from app.inventory.clip_matcher import CLIPImageMatcher
from app.inventory.conversation_state import get_state_store
from app.inventory.image_feedback import (
    ImageSearchCorrection,
    ImageSearchFailure,
    list_image_search_corrections,
    list_image_search_failures,
    save_image_search_correction,
    save_image_search_failure,
)
from app.inventory.image_index import build_image_index, image_index_status
from app.inventory.image_matcher import (
    ImageMatcher,
    ImageSearchDecision,
    apply_owner_corrections,
    finalize_image_search,
    query_image_id_from_b64,
)
from app.inventory.policy import inventory_policy_contract
from app.inventory.waitlist import WaitlistManager
from app.inventory.policy_qa import PolicyQAEngine
from app.inventory.pos_sync import POSSyncEngine
from app.services.inventory_service import get_inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])

_STREAMING_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_event(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


def _chunk_text(text: str, *, chunk_size: int = 160) -> list[str]:
    if not text:
        return [""]

    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        next_cursor = min(cursor + chunk_size, len(text))
        if next_cursor < len(text):
            split_index = text.rfind(" ", cursor, next_cursor)
            if split_index > cursor:
                next_cursor = split_index + 1
        chunks.append(text[cursor:next_cursor])
        cursor = next_cursor
    return chunks


def _stream_metadata(response: InventoryAskResponse | InventoryAgenticResponse) -> dict[str, object]:
    metadata: dict[str, object] = {
        "trace_id": response.trace_id,
        "answer_engine": response.answer_engine,
        "confidence_score": response.confidence_score,
        "abstained": response.abstained,
        "abstention_reason": response.abstention_reason,
        "follow_up_question": response.follow_up_question,
        "recommended_product_ids": response.recommended_product_ids,
        "cross_sell_product_ids": response.cross_sell_product_ids,
        "total_hits": response.total_hits,
    }
    if isinstance(response, InventoryAgenticResponse):
        metadata["execution_path"] = response.execution_path
        metadata["retrieval_steps_used"] = response.retrieval_steps_used
    return metadata


async def _stream_inventory_response(
    responder: Callable[[], InventoryAskResponse | InventoryAgenticResponse],
) -> AsyncIterator[str]:
    yield _sse_event("status", {"status": "started"})

    try:
        response = responder()
    except ValueError as exc:
        yield _sse_event(
            "error",
            {"error": "invalid_inventory_stream_request", "message": str(exc)},
        )
        return
    except Exception as exc:
        yield _sse_event(
            "error",
            {"error": "inventory_stream_failed", "message": str(exc)},
        )
        return

    yield _sse_event("metadata", _stream_metadata(response))
    for index, chunk in enumerate(_chunk_text(response.answer), start=1):
        yield _sse_event("answer_delta", {"index": index, "delta": chunk})
    yield _sse_event("final", response.model_dump(mode="json"))


@router.get("/status", response_model=InventoryStatusResponse)
async def get_inventory_status() -> InventoryStatusResponse:
    return get_inventory_service().status()


@router.get("/agentic/status", response_model=InventoryAgenticStatusResponse)
async def get_inventory_agentic_status() -> InventoryAgenticStatusResponse:
    return get_inventory_service().agentic_status()


@router.get("/sync/status", response_model=InventorySyncStatusResponse)
async def get_inventory_sync_status() -> InventorySyncStatusResponse:
    return get_inventory_service().sync_status()


@router.get("/production/status", response_model=InventoryProductionStatusResponse)
async def get_inventory_production_status() -> InventoryProductionStatusResponse:
    return get_inventory_service().production_status()


@router.post("/sync/validate", response_model=InventorySyncValidateResponse)
async def validate_inventory_sync(request: InventorySyncValidateRequest) -> InventorySyncValidateResponse:
    try:
        return get_inventory_service().sync_validate(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_sync_validation", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_sync_validation_failed", "message": str(exc)},
        ) from exc


@router.post("/sync/rebuild", response_model=InventorySyncRebuildResponse)
async def rebuild_inventory_sync() -> InventorySyncRebuildResponse:
    try:
        return get_inventory_service().sync_rebuild()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_sync_rebuild_failed", "message": str(exc)},
        ) from exc


@router.get("/business/status", response_model=InventoryBusinessStatusResponse)
async def get_inventory_business_status() -> InventoryBusinessStatusResponse:
    return get_inventory_service().business_status()


@router.get("/business/signals", response_model=InventoryBusinessSignalsResponse)
async def list_inventory_business_signals(product_id: str | None = None) -> InventoryBusinessSignalsResponse:
    return get_inventory_service().list_business_signals(product_id=product_id)


@router.post("/business/signals/upsert", response_model=InventoryBusinessSignalsUpsertResponse)
async def upsert_inventory_business_signals(
    request: InventoryBusinessSignalsUpsertRequest,
) -> InventoryBusinessSignalsUpsertResponse:
    try:
        return get_inventory_service().upsert_business_signals(request.signals)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_business_signal", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_business_signal_upsert_failed", "message": str(exc)},
        ) from exc


@router.get("/items", response_model=InventoryCatalogResponse)
async def list_inventory_items() -> InventoryCatalogResponse:
    return get_inventory_service().list_items()


@router.get("/items/{product_id}", response_model=InventoryItemRecord)
async def read_inventory_item(product_id: str) -> InventoryItemRecord:
    item = get_inventory_service().get_item(product_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "inventory_item_not_found", "message": f"Product {product_id} was not found."},
        )
    return item


@router.post("/items/upsert", response_model=InventoryUpsertResponse)
async def upsert_inventory_items(request: InventoryUpsertRequest) -> InventoryUpsertResponse:
    try:
        return get_inventory_service().upsert_items(request.items)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_item", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_upsert_failed", "message": str(exc)},
        ) from exc


@router.post("/items/delete", response_model=InventoryDeleteResponse)
async def delete_inventory_items(request: InventoryDeleteRequest) -> InventoryDeleteResponse:
    try:
        return get_inventory_service().delete_items(request.product_ids)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_delete_failed", "message": str(exc)},
        ) from exc


@router.post("/business/signals/delete", response_model=InventoryBusinessSignalsDeleteResponse)
async def delete_inventory_business_signals(
    request: InventoryDeleteRequest,
) -> InventoryBusinessSignalsDeleteResponse:
    try:
        return get_inventory_service().delete_business_signals(request.product_ids)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_business_signal_delete_failed", "message": str(exc)},
        ) from exc


@router.post("/search", response_model=InventorySearchResponse)
async def search_inventory(request: InventorySearchRequest) -> InventorySearchResponse:
    try:
        return get_inventory_service().search(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_search", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_search_failed", "message": str(exc)},
        ) from exc


@router.post("/route", response_model=InventoryRouteResponse)
async def route_inventory_question(request: InventoryRouteRequest) -> InventoryRouteResponse:
    try:
        return get_inventory_service().route(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_route", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_route_failed", "message": str(exc)},
        ) from exc


@router.get("/policy", response_model=InventoryPolicyContractResponse)
async def get_inventory_policy() -> InventoryPolicyContractResponse:
    return inventory_policy_contract()


@router.post("/agentic/ask", response_model=InventoryAgenticResponse)
async def ask_inventory_agentic(request: InventoryAgenticRequest) -> InventoryAgenticResponse:
    try:
        return get_inventory_service().agentic_ask(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_agentic_question", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_agentic_question_failed", "message": str(exc)},
        ) from exc


@router.post("/agentic/ask/stream")
async def ask_inventory_agentic_stream(request: InventoryAgenticRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_inventory_response(lambda: get_inventory_service().agentic_ask(request)),
        media_type="text/event-stream",
        headers=_STREAMING_HEADERS,
    )


@router.get("/agentic/trace/{trace_id}", response_model=InventoryAgenticTraceResponse)
async def read_inventory_agentic_trace(trace_id: str) -> InventoryAgenticTraceResponse:
    trace = get_inventory_service().get_agentic_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "inventory_agentic_trace_not_found", "message": f"Trace {trace_id} was not found."},
        )
    return trace


@router.get("/chat/trace/{trace_id}", response_model=InventoryChatTraceResponse)
async def read_inventory_chat_trace(trace_id: str) -> InventoryChatTraceResponse:
    trace = get_inventory_service().get_chat_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "inventory_chat_trace_not_found", "message": f"Trace {trace_id} was not found."},
        )
    return trace


@router.post("/ask", response_model=InventoryAskResponse)
async def ask_inventory(request: InventoryAskRequest) -> InventoryAskResponse:
    try:
        return get_inventory_service().ask(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_question", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inventory_question_failed", "message": str(exc)},
        ) from exc


@router.post("/ask/stream")
async def ask_inventory_stream(request: InventoryAskRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_inventory_response(lambda: get_inventory_service().ask(request)),
        media_type="text/event-stream",
        headers=_STREAMING_HEADERS,
    )


def _record_image_search_state(request: ImageSearchRequest, decision: ImageSearchDecision) -> None:
    if not request.session_id:
        return
    primary = decision.hits[0] if decision.hits else None
    product_ids = [hit.product_id for hit in decision.hits]
    slots = {
        "color": decision.requested_color or (primary.color if primary else None),
        "color_family": decision.requested_color or (primary.color if primary else None),
        "variant_group_id": primary.variant_group_id if primary else None,
        "design_id": primary.design_id if primary else None,
        "category_key": (
            (primary.score_breakdown or {}).get("category")
            if primary and primary.score_breakdown
            else None
        ),
    }
    confidence = max((hit.score for hit in decision.hits), default=0.0)
    get_state_store().record_turn(
        session_id=request.session_id,
        question=request.query_text or "[image upload]",
        intent="image_search",
        slots=slots,
        product_ids=product_ids,
        primary_product_id=decision.primary_product_id,
        confidence=confidence,
        abstained=decision.decision_label == "no_confident_match",
    )


def _log_image_search_failure_if_needed(
    request: ImageSearchRequest,
    decision: ImageSearchDecision,
    query_image_id: str | None,
) -> None:
    top_score = max((hit.score for hit in decision.hits), default=0.0)
    if decision.decision_label != "no_confident_match" and decision.hits and top_score >= 0.22:
        return
    reason = "no_confident_match" if decision.decision_label == "no_confident_match" else "low_visual_score"
    save_image_search_failure(
        ImageSearchFailure(
            query_text=request.query_text,
            session_id=request.session_id,
            query_image_id=query_image_id,
            decision_label=decision.decision_label,
            primary_product_id=decision.primary_product_id,
            top_product_ids=[hit.product_id for hit in decision.hits[:5]],
            reason=reason,
            score_breakdown=decision.score_breakdown,
        )
    )


@router.post("/image-search", response_model=ImageSearchResponse)
async def image_search(request: ImageSearchRequest) -> ImageSearchResponse:
    catalog = get_inventory_service().load_catalog()
    query_image_id = request.query_image_id or query_image_id_from_b64(request.image_b64)
    raw_top_k = min(max(request.top_k * 4, 12), 20)
    if CLIPImageMatcher.is_available():
        from app.inventory.clip_matcher import precompute_catalog_embeddings
        precompute_catalog_embeddings(catalog)
        matcher: CLIPImageMatcher | ImageMatcher = CLIPImageMatcher()
        results = matcher.search(
            query_text=request.query_text,
            image_b64=request.image_b64,
            catalog=catalog,
            category_hint=request.category_hint,
            color_hint=request.color_hint,
            budget_max=request.budget_max,
            top_k=raw_top_k,
        )
    else:
        matcher = ImageMatcher(catalog)
        results = matcher.search(
            query_text=request.query_text,
            image_b64=request.image_b64,
            category_hint=request.category_hint,
            color_hint=request.color_hint,
            budget_max=request.budget_max,
            top_k=raw_top_k,
        )
    results = apply_owner_corrections(
        catalog=catalog,
        results=results,
        query_image_id=query_image_id,
        corrections=list_image_search_corrections(limit=1000),
    )
    decision = finalize_image_search(
        catalog=catalog,
        results=results,
        query_text=request.query_text,
        requested_color=request.color_hint,
        top_k=request.top_k,
    )
    try:
        _record_image_search_state(request, decision)
        _log_image_search_failure_if_needed(request, decision, query_image_id)
    except Exception:
        pass
    hits = [
        ImageSearchHit(
            product_id=r.product_id,
            name=r.name,
            score=r.score,
            match_type=r.match_type,
            reasons=list(r.reasons),
            price=r.price,
            currency=r.currency,
            stock=r.stock,
            image_url=r.image_url,
            decision_label=r.decision_label,
            variant_group_id=r.variant_group_id,
            design_id=r.design_id,
            color=r.color,
            size=r.size,
            image_kind=r.image_kind,
            is_reference=r.is_reference,
            score_breakdown=r.score_breakdown,
        )
        for r in decision.hits
    ]
    return ImageSearchResponse(
        status="success",
        answer=decision.answer,
        query_image_id=query_image_id,
        hits=hits,
        total=len(hits),
        decision_label=decision.decision_label,
        primary_product_id=decision.primary_product_id,
        same_design_variant_ids=list(decision.same_design_variant_ids),
        similar_product_ids=list(decision.similar_product_ids),
        requested_color=decision.requested_color,
        available_colors=list(decision.available_colors),
        score_breakdown=decision.score_breakdown,
    )


@router.get("/image-index/status", response_model=ImageIndexStatusResponse)
async def get_image_index_status() -> ImageIndexStatusResponse:
    catalog = get_inventory_service().load_catalog()
    return ImageIndexStatusResponse(**image_index_status(catalog).to_dict())


@router.post("/image-index/rebuild", response_model=ImageIndexRebuildResponse)
async def rebuild_image_index(request: ImageIndexRebuildRequest) -> ImageIndexRebuildResponse:
    catalog = get_inventory_service().load_catalog()
    records = build_image_index(
        catalog,
        force=request.force,
        include_embeddings=request.include_embeddings,
    )
    status_data = image_index_status(catalog).to_dict()
    return ImageIndexRebuildResponse(rebuilt_count=len(records), **status_data)


@router.get("/image-search/failures", response_model=ImageSearchFailureListResponse)
async def read_image_search_failures(limit: int = 50) -> ImageSearchFailureListResponse:
    failures = list_image_search_failures(limit=limit)
    return ImageSearchFailureListResponse(status="success", total=len(failures), failures=failures)


@router.get("/image-search/corrections", response_model=ImageSearchCorrectionListResponse)
async def read_image_search_corrections(limit: int = 50) -> ImageSearchCorrectionListResponse:
    corrections = list_image_search_corrections(limit=limit)
    return ImageSearchCorrectionListResponse(status="success", total=len(corrections), corrections=corrections)


@router.post("/image-search/corrections", response_model=ImageSearchCorrectionResponse)
async def create_image_search_correction(
    request: ImageSearchCorrectionRequest,
) -> ImageSearchCorrectionResponse:
    correction = ImageSearchCorrection(
        query_image_id=request.query_image_id,
        correction_type=request.correction_type,
        correct_product_id=request.correct_product_id,
        wrong_product_id=request.wrong_product_id,
        notes=request.notes,
        session_id=request.session_id,
        query_text=request.query_text,
    )
    save_image_search_correction(correction)
    return ImageSearchCorrectionResponse(status="success", correction=asdict(correction))


@router.post("/sync/import", response_model=POSSyncResponse)
async def pos_sync_csv_import(request: POSSyncImportRequest) -> POSSyncResponse:
    engine = POSSyncEngine()
    result = engine.import_from_csv(request.csv_text)
    return POSSyncResponse(
        status="success" if not result.errors else "partial",
        inserted=result.inserted,
        updated=result.updated,
        stock_changed=result.stock_changed,
        deactivated=result.deactivated,
        skipped=result.skipped,
        errors=result.errors[:10],
        summary=result.summary(),
        timestamp=result.timestamp,
    )


@router.post("/sync/webhook", response_model=POSSyncResponse)
async def pos_sync_webhook(request: POSSyncWebhookRequest) -> POSSyncResponse:
    engine = POSSyncEngine()
    result = engine.import_from_webhook({"source": request.source, "event": request.event, "items": request.items})
    return POSSyncResponse(
        status="success" if not result.errors else "partial",
        inserted=result.inserted,
        updated=result.updated,
        stock_changed=result.stock_changed,
        deactivated=result.deactivated,
        skipped=result.skipped,
        errors=result.errors[:10],
        summary=result.summary(),
        timestamp=result.timestamp,
    )


@router.get("/sync/status", response_model=POSSyncStatusResponse)
async def pos_sync_status() -> POSSyncStatusResponse:
    engine = POSSyncEngine()
    data = engine.get_sync_status()
    return POSSyncStatusResponse(
        status="success",
        total_products=data["total_products"],
        active_products=data["active_products"],
        out_of_stock=data["out_of_stock"],
        last_sync=data["last_sync"],
    )


@router.post("/policy-qa", response_model=PolicyQAResponse)
async def policy_qa(request: PolicyQARequest) -> PolicyQAResponse:
    engine = PolicyQAEngine()
    answer = engine.answer(request.question)
    if answer is None:
        return PolicyQAResponse(
            status="not_found",
            answer="I don't have a specific policy answer for that question. Please contact us directly.",
            source="policies.json",
        )
    return PolicyQAResponse(status="success", answer=answer, source="policies.json")


from pydantic import BaseModel as _BaseModel  # noqa: E402


class _WaitlistRequest(_BaseModel):
    product_id: str
    product_name: str = ""
    session_id: str
    phone: str | None = None


@router.get("/audit")
async def get_catalog_audit() -> dict:
    svc = get_inventory_service()
    catalog_path = svc._catalog_path() if hasattr(svc, "_catalog_path") else "data/inventory/catalog.jsonl"
    report = audit_catalog(catalog_path)
    return {
        "total_products": report.total_products,
        "active_products": report.active_products,
        "rag_enabled": report.rag_enabled,
        "out_of_stock": report.out_of_stock,
        "completeness_score": report.completeness_score,
        "attribute_coverage": report.attribute_coverage,
        "category_counts": report.category_counts,
        "brand_counts": report.brand_counts,
        "price_range": report.price_range,
        "enrichment_candidates": report.enrichment_candidates,
        "issues": [
            {"product_id": i.product_id, "name": i.name, "issue_type": i.issue_type, "detail": i.detail}
            for i in report.issues
        ],
    }


@router.post("/waitlist")
async def join_waitlist(request: _WaitlistRequest) -> dict:
    mgr = WaitlistManager()
    mgr.add(
        session_id=request.session_id,
        product_id=request.product_id,
        product_name=request.product_name,
        phone=request.phone,
    )
    return {"status": "added", "product_id": request.product_id}


@router.get("/waitlist/status")
async def waitlist_status(product_id: str | None = None) -> dict:
    mgr = WaitlistManager()
    if product_id:
        return {"product_id": product_id, "entries": mgr.get_waitlist(product_id)}
    return {"pending": mgr.get_all_pending()}
