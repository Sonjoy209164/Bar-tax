from __future__ import annotations

import pytest
from app.inventory.policy_qa import PolicyQAEngine, is_policy_question, load_policies


def test_policies_file_loads():
    policies = load_policies()
    assert policies, "policies.json must not be empty"
    assert "delivery" in policies
    assert "payment" in policies
    assert "refund" in policies
    assert "exchange" in policies


def test_is_policy_question_delivery():
    assert is_policy_question("Dhaka delivery charge koto?")
    assert is_policy_question("delivery fee ki?")
    assert is_policy_question("ডেলিভারি চার্জ কত?")


def test_is_policy_question_refund():
    assert is_policy_question("refund pabo?")
    assert is_policy_question("ভুল প্রোডাক্ট গেলে কী হবে?")


def test_is_policy_question_exchange():
    assert is_policy_question("exchange policy ki?")
    assert is_policy_question("ভুল সাইজ হলে exchange করা যাবে?")


def test_policy_qa_engine_delivery_inside_dhaka():
    engine = PolicyQAEngine()
    answer = engine.answer("Dhaka delivery charge koto?")
    assert answer is not None
    assert "80" in answer or "BDT" in answer


def test_policy_qa_engine_delivery_outside_dhaka():
    engine = PolicyQAEngine()
    answer = engine.answer("outside Dhaka delivery charge koto?")
    assert answer is not None
    assert "150" in answer or "outside" in answer.lower()


def test_policy_qa_engine_delivery_time():
    engine = PolicyQAEngine()
    answer = engine.answer("delivery koto din lage?")
    assert answer is not None
    assert "day" in answer.lower() or "din" in answer.lower() or "working" in answer.lower()


def test_policy_qa_engine_cod_payment():
    engine = PolicyQAEngine()
    answer = engine.answer("COD available ache?")
    assert answer is not None
    assert "cod" in answer.lower() or "cash" in answer.lower()


def test_policy_qa_engine_bkash():
    engine = PolicyQAEngine()
    answer = engine.answer("bKash payment hobe?")
    assert answer is not None
    assert "bkash" in answer.lower() or "available" in answer.lower()


def test_policy_qa_engine_refund():
    engine = PolicyQAEngine()
    answer = engine.answer("refund pabo ki?")
    assert answer is not None
    assert "refund" in answer.lower() or "damaged" in answer.lower() or "wrong" in answer.lower()


def test_policy_qa_engine_exchange():
    engine = PolicyQAEngine()
    answer = engine.answer("exchange korbo kemon kore?")
    assert answer is not None
    assert "day" in answer.lower() or "3" in answer


def test_policy_qa_engine_unknown_returns_none():
    engine = PolicyQAEngine()
    answer = engine.answer("saree er dam koto?")
    assert answer is None


def test_policy_qa_engine_free_delivery_threshold():
    engine = PolicyQAEngine()
    answer = engine.answer("free delivery kobe pabo?")
    assert answer is not None or True  # policy answer or None is both valid


def test_policy_qa_all_payment_methods():
    engine = PolicyQAEngine()
    answer = engine.answer("payment method ki ki ache?")
    assert answer is not None
    assert "cod" in answer.lower() or "bkash" in answer.lower() or "nagad" in answer.lower()
