from pathlib import Path

from app.eval.dataset_builder import validate_annotated_dataset


def test_dataset_validation_success(tmp_path: Path) -> None:
    dataset_path = tmp_path / "valid_dataset.jsonl"
    dataset_path.write_text(
        '{"question_id":"q1","question_text":"করহার কত?","question_type":"rate_lookup","answer_text":"১০ শতাংশ","expected_chunk_ids":["sample-tax-2025-p001-c001"],"expected_doc_ids":["sample-tax-2025"],"expected_sections":["3.1"],"expected_tax_year":"2025-2026","answer_language":"bangla"}\n',
        encoding="utf-8",
    )

    report = validate_annotated_dataset(dataset_path, "data/processed/sample_chunks.jsonl")

    assert report.valid is True
    assert report.invalid_rows == 0


def test_dataset_validation_failure_on_bad_chunk_ids(tmp_path: Path) -> None:
    dataset_path = tmp_path / "invalid_dataset.jsonl"
    dataset_path.write_text(
        '{"question_id":"q1","question_text":"করহার কত?","question_type":"rate_lookup","answer_text":"১০ শতাংশ","expected_chunk_ids":["missing-chunk"],"expected_doc_ids":["sample-tax-2025"],"expected_sections":["3.1"],"expected_tax_year":"2025-2026","answer_language":"bangla"}\n',
        encoding="utf-8",
    )

    report = validate_annotated_dataset(dataset_path, "data/processed/sample_chunks.jsonl")

    assert report.valid is False
    assert report.errors
