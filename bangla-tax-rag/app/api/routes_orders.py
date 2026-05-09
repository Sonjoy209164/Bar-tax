from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from pydantic import BaseModel

from app.core.schemas import (
    OrderConfirmRequest,
    OrderDraftRequest,
    OrderResponse,
    OrderItemSchema,
    OrderUpdateRequest,
)


class CartRemoveRequest(BaseModel):
    session_id: str
    product_id: str


class CartQuantityRequest(BaseModel):
    session_id: str
    product_id: str
    quantity: int


class OrderTrackingUpdateRequest(BaseModel):
    tracking_status: str  # pending | processing | dispatched | delivered | cancelled
from app.inventory.order_workflow import (
    OrderWorkflowEngine,
    load_order,
    load_orders_by_phone,
    update_order_tracking,
)

router = APIRouter(prefix="/orders", tags=["orders"])

_SESSION_ENGINES: dict[str, OrderWorkflowEngine] = {}


def _get_engine(session_id: str) -> OrderWorkflowEngine:
    if session_id not in _SESSION_ENGINES:
        _SESSION_ENGINES[session_id] = OrderWorkflowEngine()
    return _SESSION_ENGINES[session_id]


def _draft_to_response(engine: OrderWorkflowEngine, message: str) -> OrderResponse:
    draft = engine.get_draft()
    if draft is None:
        return OrderResponse(status="no_draft", message=message)
    items = [
        OrderItemSchema(
            product_id=i.product_id,
            sku=i.sku,
            name=i.name,
            quantity=i.quantity,
            unit_price=i.unit_price,
            currency=i.currency,
            line_total=i.line_total(),
        )
        for i in draft.items
    ]
    return OrderResponse(
        status="draft",
        order_id=draft.order_id,
        message=message,
        items=items,
        subtotal=draft.subtotal(),
        delivery_charge=float(draft.delivery_charge()),
        grand_total=draft.grand_total(),
        customer_name=draft.customer_name,
        customer_phone=draft.customer_phone,
        delivery_area=draft.delivery_area,
        payment_method=draft.payment_method,
        order_status=draft.status,
        missing_fields=draft.missing_fields(),
        ready_to_confirm=draft.is_ready_to_confirm(),
    )


@router.post("/draft", response_model=OrderResponse)
async def create_order_draft(request: OrderDraftRequest) -> OrderResponse:
    engine = _get_engine(request.session_id)
    engine.start_draft(
        product_id=request.product_id,
        sku=request.sku,
        name=request.name,
        unit_price=request.unit_price,
        quantity=request.quantity,
        currency=request.currency,
    )
    return _draft_to_response(engine, f"Draft started for {request.name}. Please provide name, phone, delivery area, and payment method.")


@router.post("/update", response_model=OrderResponse)
async def update_order_draft(request: OrderUpdateRequest) -> OrderResponse:
    engine = _get_engine(request.session_id)
    draft = engine.get_draft()
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "no_active_draft", "message": "No active order draft for this session."},
        )
    if request.customer_name:
        draft.customer_name = request.customer_name
    if request.customer_phone:
        draft.customer_phone = request.customer_phone
    if request.delivery_area:
        draft.delivery_area = request.delivery_area
    if request.payment_method:
        draft.payment_method = request.payment_method
    if request.notes:
        draft.notes = request.notes

    if draft.is_ready_to_confirm():
        summary, _ = engine.prepare_confirmation()
        return _draft_to_response(engine, summary)
    return _draft_to_response(engine, engine.build_ask_for_missing())


@router.post("/confirm", response_model=OrderResponse)
async def confirm_order(request: OrderConfirmRequest) -> OrderResponse:
    engine = _get_engine(request.session_id)
    draft = engine.get_draft()
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "no_active_draft", "message": "No active order draft to confirm."},
        )
    if not draft.is_ready_to_confirm():
        return _draft_to_response(engine, engine.build_ask_for_missing())

    message, confirmed = engine.confirm()
    if confirmed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "confirm_failed", "message": "Order confirmation failed."},
        )
    items = [
        OrderItemSchema(
            product_id=i.product_id,
            sku=i.sku,
            name=i.name,
            quantity=i.quantity,
            unit_price=i.unit_price,
            currency=i.currency,
            line_total=i.line_total(),
        )
        for i in confirmed.items
    ]
    return OrderResponse(
        status="confirmed",
        order_id=confirmed.order_id,
        message=message,
        items=items,
        subtotal=confirmed.subtotal(),
        delivery_charge=float(confirmed.delivery_charge()),
        grand_total=confirmed.grand_total(),
        customer_name=confirmed.customer_name,
        customer_phone=confirmed.customer_phone,
        delivery_area=confirmed.delivery_area,
        payment_method=confirmed.payment_method,
        order_status="confirmed",
        missing_fields=[],
        ready_to_confirm=False,
    )


@router.delete("/cancel/{session_id}", response_model=OrderResponse)
async def cancel_order(session_id: str) -> OrderResponse:
    engine = _get_engine(session_id)
    message = engine.cancel()
    _SESSION_ENGINES.pop(session_id, None)
    return OrderResponse(status="cancelled", message=message)


@router.get("/cart/{session_id}", response_model=OrderResponse)
async def get_cart(session_id: str) -> OrderResponse:
    engine = _get_engine(session_id)
    if not engine.has_active_draft:
        return OrderResponse(status="no_draft", message="No active cart for this session.")
    return _draft_to_response(engine, "Current cart contents.")


@router.post("/cart/remove", response_model=OrderResponse)
async def remove_cart_item(request: CartRemoveRequest) -> OrderResponse:
    engine = _get_engine(request.session_id)
    removed = engine.remove_item(request.product_id)
    msg = f"Removed {request.product_id} from cart." if removed else f"{request.product_id} not found in cart."
    return _draft_to_response(engine, msg)


@router.post("/cart/quantity", response_model=OrderResponse)
async def update_cart_quantity(request: CartQuantityRequest) -> OrderResponse:
    engine = _get_engine(request.session_id)
    updated = engine.update_quantity(request.product_id, request.quantity)
    msg = f"Quantity updated to {request.quantity}." if updated else "Item not found in cart."
    return _draft_to_response(engine, msg)


@router.patch("/{order_id}/status", response_model=dict)
async def update_tracking_status(order_id: str, request: OrderTrackingUpdateRequest) -> dict:
    success = update_order_tracking(order_id, request.tracking_status)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "order_not_found_or_invalid_status", "message": f"Order {order_id} not found or invalid status '{request.tracking_status}'."},
        )
    return {"order_id": order_id, "tracking_status": request.tracking_status, "updated": True}


@router.get("/track/{phone}", response_model=list)
async def track_orders_by_phone(phone: str) -> list:
    orders = load_orders_by_phone(phone)
    result = []
    for o in orders:
        result.append({
            "order_id": o.order_id,
            "status": o.status,
            "tracking_status": o.tracking_status,
            "items": [i.to_dict() for i in o.items],
            "grand_total": o.grand_total(),
            "delivery_area": o.delivery_area,
            "created_at": o.created_at,
            "confirmed_at": o.confirmed_at,
            "dispatched_at": o.dispatched_at,
            "delivered_at": o.delivered_at,
        })
    return result


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    order = load_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "order_not_found", "message": f"Order {order_id} not found."},
        )
    items = [
        OrderItemSchema(
            product_id=i.product_id,
            sku=i.sku,
            name=i.name,
            quantity=i.quantity,
            unit_price=i.unit_price,
            currency=i.currency,
            line_total=i.line_total(),
        )
        for i in order.items
    ]
    return OrderResponse(
        status="found",
        order_id=order.order_id,
        message=f"Order {order.order_id} — status: {order.status}",
        items=items,
        subtotal=order.subtotal(),
        delivery_charge=float(order.delivery_charge()),
        grand_total=order.grand_total(),
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        delivery_area=order.delivery_area,
        payment_method=order.payment_method,
        order_status=order.status,
    )
