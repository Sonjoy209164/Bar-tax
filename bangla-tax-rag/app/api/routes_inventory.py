from fastapi import APIRouter, HTTPException, status

from app.core.schemas import (
    InventoryAgenticRequest,
    InventoryAgenticResponse,
    InventoryAgenticStatusResponse,
    InventoryAgenticTraceResponse,
    InventoryAskRequest,
    InventoryAskResponse,
    InventoryCatalogResponse,
    InventoryDeleteRequest,
    InventoryDeleteResponse,
    InventoryItemRecord,
    InventoryRouteRequest,
    InventoryRouteResponse,
    InventorySearchRequest,
    InventorySearchResponse,
    InventoryStatusResponse,
    InventoryUpsertRequest,
    InventoryUpsertResponse,
)
from app.services.inventory_service import get_inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/status", response_model=InventoryStatusResponse)
async def get_inventory_status() -> InventoryStatusResponse:
    return get_inventory_service().status()


@router.get("/agentic/status", response_model=InventoryAgenticStatusResponse)
async def get_inventory_agentic_status() -> InventoryAgenticStatusResponse:
    return get_inventory_service().agentic_status()


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


@router.get("/agentic/trace/{trace_id}", response_model=InventoryAgenticTraceResponse)
async def read_inventory_agentic_trace(trace_id: str) -> InventoryAgenticTraceResponse:
    trace = get_inventory_service().get_agentic_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "inventory_agentic_trace_not_found", "message": f"Trace {trace_id} was not found."},
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
