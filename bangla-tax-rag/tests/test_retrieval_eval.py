from scripts.run_retrieval_eval import (
    EvalQuestion,
    adjacent_page_hit_at_k,
    compute_mode_metrics,
    derive_expected_doc_ids,
    evaluate_question_hits,
    expected_doc_page_pairs,
)
from app.core.schemas import RetrievalHit


def _hit(chunk_id: str, *, doc_id: str = "btax14_001", page_no: int = 1, tax_year: str | None = "2025-2026") -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title="Test",
        page_no=page_no,
        section_id=None,
        subsection_id=None,
        chunk_type="text",
        authority_level="national",
        tax_year=tax_year,
        original_text="evidence text",
        normalized_text="evidence text",
        heading_path=[],
        content="evidence text",
        score=1.0,
    )


def test_expected_doc_and_page_helpers_parse_chunk_ids() -> None:
    chunk_ids = ("btax14_014-p015-c086", "btax14_013-p021-c054")

    assert derive_expected_doc_ids(chunk_ids) == ["btax14_014", "btax14_013"]
    assert expected_doc_page_pairs(chunk_ids) == {("btax14_014", 15), ("btax14_013", 21)}


def test_evaluate_question_hits_marks_rank_and_adjacent_page() -> None:
    question = EvalQuestion(
        question_id="q1",
        question_text="করহার কত?",
        question_type="rate_lookup",
        expected_chunk_ids=("btax14_014-p015-c086",),
        expected_doc_ids=("btax14_014",),
        expected_tax_year="2025-2026",
        query_tax_year="2025-2026",
        should_abstain=False,
    )
    hits = [
        _hit("btax14_014-p014-c082", doc_id="btax14_014", page_no=14),
        _hit("btax14_014-p015-c086", doc_id="btax14_014", page_no=15),
    ]

    row = evaluate_question_hits(question, "sparse", hits)

    assert row["gold_rank"] == 2
    assert row["gold_chunk_in_top_1"] is False
    assert row["gold_chunk_in_top_3"] is True
    assert row["doc_hit_at_5"] is True
    assert row["page_hit_at_5"] is True
    assert adjacent_page_hit_at_k(hits, question.expected_chunk_ids, 1) is True


def test_compute_mode_metrics_excludes_abstentions_from_evidence_scores() -> None:
    answerable_question = EvalQuestion(
        question_id="q1",
        question_text="করহার কত?",
        question_type="rate_lookup",
        expected_chunk_ids=("btax14_014-p015-c086",),
        expected_doc_ids=("btax14_014",),
        expected_tax_year="2025-2026",
        query_tax_year="2025-2026",
        should_abstain=False,
    )
    abstention_question = EvalQuestion(
        question_id="q2",
        question_text="ক্রিপ্টো করহার কত?",
        question_type="rate_lookup",
        expected_chunk_ids=(),
        expected_doc_ids=(),
        expected_tax_year="2025-2026",
        query_tax_year="2025-2026",
        should_abstain=True,
    )

    rows = [
        evaluate_question_hits(
            answerable_question,
            "hybrid",
            [_hit("other-p001-c001", doc_id="other", page_no=1, tax_year="2024-2025")],
        ),
        evaluate_question_hits(
            abstention_question,
            "hybrid",
            [_hit("btax14_014-p015-c086", doc_id="btax14_014", page_no=15)],
        ),
    ]

    summary = compute_mode_metrics(rows)

    assert summary["total_questions"] == 2
    assert summary["answerable_evidence_questions"] == 1
    assert summary["abstention_questions"] == 1
    assert summary["metrics"]["evidence_hit_at_5"] == 0.0
    assert summary["metrics"]["wrong_year_retrieval_rate_top1"] == 1.0


def test_evaluate_question_hits_marks_gold_miss_as_false_not_na() -> None:
    question = EvalQuestion(
        question_id="q1",
        question_text="করহার কত?",
        question_type="rate_lookup",
        expected_chunk_ids=("btax14_014-p015-c086",),
        expected_doc_ids=("btax14_014",),
        expected_tax_year=None,
        query_tax_year=None,
        should_abstain=False,
    )

    row = evaluate_question_hits(question, "sparse", [_hit("btax14_014-p010-c001", page_no=10)])

    assert row["gold_rank"] is None
    assert row["gold_chunk_in_top_1"] is False
    assert row["gold_chunk_in_top_3"] is False
    assert row["gold_chunk_in_top_5"] is False
