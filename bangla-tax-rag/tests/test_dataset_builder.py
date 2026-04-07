from pathlib import Path

from app.eval.annotation import merge_annotation_files
from app.eval.dataset_builder import build_annotation_candidates_from_chunks
from app.retrieval.sparse import load_chunk_records_from_jsonl


def test_candidate_generation_from_synthetic_chunks() -> None:
    chunk_records = load_chunk_records_from_jsonl("data/processed/sample_chunks.jsonl")
    candidates = build_annotation_candidates_from_chunks(chunk_records)

    assert candidates
    assert candidates[0].question_id.startswith("cand-")
    assert candidates[0].question_type in {
        "rate_lookup",
        "definition",
        "amendment",
        "procedure",
        "example_based",
        "calculation",
        "comparison",
        "authority_conflict",
    }


def test_merge_behavior(tmp_path: Path) -> None:
    first_file = tmp_path / "ann1.jsonl"
    second_file = tmp_path / "ann2.jsonl"
    first_file.write_text(
        '{"question_id":"q1","question_text":"Q1","question_type":"definition","answer_text":"A1","expected_chunk_ids":["sample-tax-2025-p001-c001"],"expected_doc_ids":["sample-tax-2025"],"expected_sections":["3.1"],"expected_tax_year":"2025-2026","answer_language":"bangla"}\n',
        encoding="utf-8",
    )
    second_file.write_text(
        '{"question_id":"q1","question_text":"Q1 updated","question_type":"definition","answer_text":"A1 updated","expected_chunk_ids":["sample-tax-2025-p001-c001"],"expected_doc_ids":["sample-tax-2025"],"expected_sections":["3.1"],"expected_tax_year":"2025-2026","answer_language":"bangla"}\n'
        '{"question_id":"q2","question_text":"Q2","question_type":"rate_lookup","answer_text":"A2","expected_chunk_ids":["sample-tax-2024-p001-c001"],"expected_doc_ids":["sample-tax-2024"],"expected_sections":["3.1"],"expected_tax_year":"2024-2025","answer_language":"bangla"}\n',
        encoding="utf-8",
    )

    merged_rows = merge_annotation_files([first_file, second_file])

    assert len(merged_rows) == 2
    assert any(row.question_text == "Q1 updated" for row in merged_rows)
