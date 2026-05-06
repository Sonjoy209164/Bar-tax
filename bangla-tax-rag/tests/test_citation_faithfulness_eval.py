import json

from app.core.schemas import ChunkRecord
from scripts.run_citation_faithfulness_eval import evaluate_dataset_citation_faithfulness


def _write_jsonl(path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_citation_faithfulness_counts_supported_claims_and_abstentions(tmp_path) -> None:
    chunk = ChunkRecord(
        chunk_id="btax14_014-p010-c072",
        doc_id="btax14_014",
        doc_title="Income Tax Paripatra 2025-2026",
        doc_type="paripatra",
        authority_level="national",
        tax_year="2025-2026",
        page_no=10,
        chunk_type="text",
        heading_path=["করহার"],
        original_text="নতুন করদাতার জন্য ন্যূনতম কর ১,০০০ টাকা।",
        normalized_text="নতুন করদাতার জন্য ন্যূনতম কর 1,000 টাকা।",
    )
    chunks_path = tmp_path / "chunks.jsonl"
    _write_jsonl(chunks_path, [chunk.model_dump()])

    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "question_id": "q1",
                "question_text": "নতুন করদাতার ন্যূনতম কর কত?",
                "question_type": "rate_lookup",
                "answer_text": "নতুন করদাতার জন্য ন্যূনতম কর ১,০০০ টাকা।",
                "expected_chunk_ids": ["btax14_014-p010-c072"],
                "should_abstain": False,
            },
            {
                "question_id": "q2",
                "question_text": "প্রমাণে নেই এমন প্রশ্ন",
                "question_type": "procedure",
                "answer_text": "এই প্রমাণে নির্ভরযোগ্য উত্তর দেওয়া যাবে না।",
                "expected_chunk_ids": [],
                "should_abstain": True,
            },
        ],
    )

    report = evaluate_dataset_citation_faithfulness(dataset_path=dataset_path, chunks_path=chunks_path)

    assert report["counts"]["answerable_rows"] == 1
    assert report["counts"]["abstention_rows"] == 1
    assert report["counts"]["supported_claims"] == 1
    assert report["metrics"]["citation_support_precision"] == 1.0
    assert report["metrics"]["abstention_accuracy"] == 1.0
