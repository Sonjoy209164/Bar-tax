from fastapi import APIRouter, HTTPException, status

from app.core.schemas import (
    InventoryAskRequest,
    InventoryAskResponse,
    InventoryCatalogResponse,
    InventoryDeleteRequest,
    InventoryDeleteResponse,
    InventoryItemRecord,
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
