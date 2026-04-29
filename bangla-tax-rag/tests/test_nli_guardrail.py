from app.domain import CitationRelation, LegalCitation, QueryType
from app.domain.models import EvidenceItem
from app.reasoning import REFUSAL_TEXT, apply_answer_policy, verify_draft_answer


def _evidence(
    evidence_id: str,
    text: str,
    *,
    section_number: str = "23",
    relation: CitationRelation = CitationRelation.DIRECT,
    node_type: str = "section",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        node_id=f"node-{evidence_id}",
        citation=LegalCitation(
            node_id=f"node-{evidence_id}",
            document_id="income-tax-act-2023",
            act_title="Income Tax Act 2023",
            relation=relation,
            section_number=section_number,
            page_start=10,
            page_end=10,
        ),
        source_text=text,
        score=0.9,
        retrieval_method="hybrid",
        metadata={"node_type": node_type},
    )


def test_guardrail_accepts_supported_numeric_claim() -> None:
    verification = verify_draft_answer(
        "The retrieved rule and table evidence indicate: Stock dividend | 10 percent.",
        evidence_items=[
            _evidence("e1", "Stock dividend | 10 percent"),
            _evidence("e2", "Tax on stock dividend under section 23."),
        ],
        query_type=QueryType.RATE_LOOKUP,
    )

    assert verification.has_errors is False
    assert len(verification.supported_claims) >= 1


def test_guardrail_accepts_supported_bangla_rate_claim() -> None:
    verification = verify_draft_answer(
        "প্রথম ৩,৫০,০০০ টাকা পর্যন্ত মোট আয়ের উপর -- শূন্য.",
        evidence_items=[
            _evidence(
                "e1",
                "মোট আয় হার\n(ক) প্রথম ৩,৫০,০০০ টাকা পর্যন্ত মোট আয়ের উপর -- শূন্য\n(খ) পরবর্তী ১,০০,০০০ টাকা পর্যন্ত মোট আয়ের উপর -- ৫%",
                section_number="2.1",
            )
        ],
        query_type=QueryType.RATE_LOOKUP,
    )

    assert verification.has_errors is False
    assert verification.supported_claims[0].support_score > 0.5


def test_guardrail_rejects_unsupported_numeric_claim() -> None:
    verification = verify_draft_answer(
        "The retrieved rule and table evidence indicate: Stock dividend | 15 percent.",
        evidence_items=[
            _evidence("e1", "Stock dividend | 10 percent"),
            _evidence("e2", "Tax on stock dividend under section 23."),
        ],
        query_type=QueryType.RATE_LOOKUP,
    )

    assert verification.has_errors is True
    assert any("15" in failure.claim_text for failure in verification.failures)


def test_guardrail_rejects_unsupported_section_reference() -> None:
    verification = verify_draft_answer(
        "Section 99 sets the tax day.",
        evidence_items=[_evidence("e1", "Section 23 sets the tax on stock dividend.", section_number="23")],
        query_type=QueryType.SECTION_LOOKUP,
    )

    assert verification.has_errors is True
    assert any("Section 99" in failure.claim_text for failure in verification.failures)


def test_answer_policy_removes_unsupported_claims_but_keeps_supported_lines() -> None:
    verification = verify_draft_answer(
        "Stock dividend is 10 percent. Cash dividend is 50 percent.",
        evidence_items=[
            _evidence("e1", "Stock dividend is 10 percent."),
            _evidence("e2", "Cash dividend is 20 percent."),
        ],
        query_type=QueryType.RATE_LOOKUP,
    )

    decision = apply_answer_policy("Stock dividend is 10 percent. Cash dividend is 50 percent.", verification)

    assert decision.refused is False
    assert "Stock dividend is 10 percent." in decision.final_draft
    assert "Cash dividend is 50 percent." not in decision.final_draft
    assert decision.appended_notice == REFUSAL_TEXT


def test_answer_policy_refuses_when_everything_is_unsupported() -> None:
    verification = verify_draft_answer(
        "The tax rate is 99 percent.",
        evidence_items=[_evidence("e1", "The tax rate is 10 percent.")],
        query_type=QueryType.RATE_LOOKUP,
    )

    decision = apply_answer_policy("The tax rate is 99 percent.", verification)

    assert decision.refused is True
    assert decision.final_draft == REFUSAL_TEXT
