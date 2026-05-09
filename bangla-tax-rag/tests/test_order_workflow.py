from __future__ import annotations

import pytest
from app.inventory.order_workflow import (
    OrderDraft,
    OrderItem,
    OrderWorkflowEngine,
    ORDER_INTENT_PHRASES,
)


def _sample_engine_with_draft() -> OrderWorkflowEngine:
    engine = OrderWorkflowEngine()
    engine.start_draft(
        product_id="saree-jmd-lotus-red",
        sku="SAR-JMD-LOTUS-RED",
        name="Lotus Buti Dhakai Jamdani Saree - Red",
        unit_price=6800.0,
        quantity=1,
    )
    return engine


def test_order_draft_creates_correctly():
    engine = _sample_engine_with_draft()
    draft = engine.get_draft()
    assert draft is not None
    assert draft.items[0].product_id == "saree-jmd-lotus-red"
    assert draft.items[0].unit_price == 6800.0
    assert draft.items[0].quantity == 1


def test_order_draft_subtotal():
    engine = _sample_engine_with_draft()
    draft = engine.get_draft()
    assert draft is not None
    assert draft.subtotal() == 6800.0


def test_order_draft_delivery_charge_inside_dhaka():
    engine = OrderWorkflowEngine()
    engine.start_draft(
        product_id="saree-cheap-test",
        sku="SAR-CHEAP-001",
        name="Cheap Test Saree",
        unit_price=2000.0,
        quantity=1,
    )
    draft = engine.get_draft()
    assert draft is not None
    draft.delivery_area = "Dhanmondi"
    charge = draft.delivery_charge()
    assert charge == 80


def test_order_draft_delivery_charge_outside_dhaka():
    engine = _sample_engine_with_draft()
    draft = engine.get_draft()
    assert draft is not None
    draft.delivery_area = "Sylhet"
    assert draft.delivery_charge() == 150


def test_order_draft_free_delivery_over_threshold():
    engine = OrderWorkflowEngine()
    engine.start_draft(
        product_id="saree-expensive",
        sku="SAR-EXP-001",
        name="Expensive Saree",
        unit_price=6000.0,
        quantity=1,
    )
    draft = engine.get_draft()
    assert draft is not None
    draft.delivery_area = "Dhaka"
    assert draft.delivery_charge() == 0


def test_order_draft_missing_fields():
    engine = _sample_engine_with_draft()
    draft = engine.get_draft()
    assert draft is not None
    missing = draft.missing_fields()
    assert "name" in missing
    assert "phone" in missing
    assert "delivery area" in missing
    assert "payment method" in missing


def test_order_draft_ready_to_confirm_when_complete():
    engine = _sample_engine_with_draft()
    draft = engine.get_draft()
    assert draft is not None
    draft.customer_name = "Sonjoy Ahmed"
    draft.customer_phone = "01711111111"
    draft.delivery_area = "Dhanmondi"
    draft.payment_method = "cod"
    assert draft.is_ready_to_confirm()


def test_order_intent_detection():
    engine = OrderWorkflowEngine()
    assert engine.is_order_intent("order korte chai")
    assert engine.is_order_intent("eta nibo")
    assert engine.is_order_intent("book kore din")
    assert engine.is_order_intent("checkout")


def test_confirm_intent_detection():
    engine = OrderWorkflowEngine()
    assert engine.is_confirm("yes")
    assert engine.is_confirm("haa")
    assert engine.is_confirm("confirm")
    assert engine.is_confirm("ok")


def test_cancel_intent_detection():
    engine = OrderWorkflowEngine()
    assert engine.is_cancel("cancel")
    assert engine.is_cancel("no")
    assert engine.is_cancel("na")


def test_update_from_text_extracts_phone():
    engine = _sample_engine_with_draft()
    engine.update_from_text("Sonjoy, 01711234567, Dhanmondi, COD")
    draft = engine.get_draft()
    assert draft is not None
    assert draft.customer_phone == "01711234567"


def test_update_from_text_extracts_payment():
    engine = _sample_engine_with_draft()
    engine.update_from_text("payment bkash dibo")
    draft = engine.get_draft()
    assert draft is not None
    assert draft.payment_method == "bkash"


def test_update_from_text_extracts_delivery_area():
    engine = _sample_engine_with_draft()
    engine.update_from_text("Dhanmondi te deliver koro")
    draft = engine.get_draft()
    assert draft is not None
    assert draft.delivery_area is not None


def test_full_order_confirmation_flow():
    engine = OrderWorkflowEngine()
    engine.start_draft(
        product_id="saree-jmd-lotus-red",
        sku="SAR-JMD-LOTUS-RED",
        name="Lotus Buti Jamdani Red",
        unit_price=6800.0,
    )
    draft = engine.get_draft()
    assert draft is not None
    draft.customer_name = "Test User"
    draft.customer_phone = "01711111111"
    draft.delivery_area = "Gulshan"
    draft.payment_method = "cod"

    message, confirmed = engine.confirm()
    assert "confirmed" in message.lower() or "ORD" in message
    assert confirmed is not None
    assert confirmed.status == "confirmed"
    assert confirmed.order_id.startswith("ORD-")


def test_order_summary_text():
    engine = _sample_engine_with_draft()
    draft = engine.get_draft()
    assert draft is not None
    draft.customer_name = "Test"
    draft.customer_phone = "01700000000"
    draft.delivery_area = "Mirpur"
    draft.payment_method = "bkash"
    summary = draft.summary_text()
    assert "Lotus Buti" in summary
    assert "6,800" in summary
    assert "Test" in summary


def test_cancel_clears_draft():
    engine = _sample_engine_with_draft()
    engine.cancel()
    assert engine.get_draft() is None
    assert not engine.has_active_draft


def test_order_item_line_total():
    item = OrderItem(
        product_id="p1",
        sku="S1",
        name="Test Product",
        quantity=3,
        unit_price=1000.0,
    )
    assert item.line_total() == 3000.0
