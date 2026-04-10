from pathlib import Path

from app.eval.metrics import evaluate_dataset_file
from app.main import app
from app.retrieval.dense import build_dense_index_artifacts, load_dense_index_metadata
from app.retrieval.sparse import build_sparse_index, load_chunk_records_from_jsonl, load_sparse_index, save_sparse_index


def test_api_startup_import() -> None:
    assert app.title == "bangla-tax-rag"


def test_sparse_index_load(tmp_path: Path) -> None:
    chunk_records = load_chunk_records_from_jsonl("data/processed/sample_chunks.jsonl")
    sparse_index = build_sparse_index(chunk_records)
    save_sparse_index(sparse_index, tmp_path / "sparse")
    loaded_index = load_sparse_index(tmp_path / "sparse")

    assert len(loaded_index.chunk_records) == len(chunk_records)


def test_dense_index_load(tmp_path: Path) -> None:
    output_dir, chunk_count = build_dense_index_artifacts(
        "data/processed/sample_chunks.jsonl",
        tmp_path / "dense",
        provider="mock",
    )
    metadata = load_dense_index_metadata(output_dir)

    assert metadata["chunk_count"] == chunk_count


def test_evaluation_output_generation(tmp_path: Path) -> None:
    metrics = evaluate_dataset_file("data/processed/sample_eval.jsonl")
    output_path = tmp_path / "evaluation_summary.json"
    output_path.write_text(str(metrics), encoding="utf-8")

    assert output_path.exists()
    assert metrics["details"]["dataset_size"] == 2
