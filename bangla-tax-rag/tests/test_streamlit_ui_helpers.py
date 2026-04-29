from app.ui.streamlit_app import derive_chunk_browser_default_path, is_agentic_response


def test_is_agentic_response_detects_agentic_payload() -> None:
    assert is_agentic_response({"trace_id": "trace-123", "execution_path": "fast_path"}) is True
    assert is_agentic_response({"_ui_pipeline_mode": "agentic"}) is True
    assert is_agentic_response({"_ui_pipeline_mode": "bangla_tax"}) is True
    assert is_agentic_response({"answer": "legacy"}) is False


def test_derive_chunk_browser_default_path_for_agentic_ingest() -> None:
    path = derive_chunk_browser_default_path(
        {
            "_ui_pipeline_mode": "agentic",
            "graph_path": "/tmp/agentic_store/income-tax-act-2023/graph/legal_graph.json",
        }
    )

    assert path == "/tmp/agentic_store/income-tax-act-2023/chunks/retrieval_chunks.jsonl"


def test_derive_chunk_browser_default_path_for_bangla_tax_ingest() -> None:
    path = derive_chunk_browser_default_path(
        {
            "_ui_pipeline_mode": "bangla_tax",
            "graph_path": "/tmp/agentic_store/income-tax-paripatra-2025-2026/graph/legal_graph.json",
        }
    )

    assert path == "/tmp/agentic_store/income-tax-paripatra-2025-2026/chunks/retrieval_chunks.jsonl"


def test_derive_chunk_browser_default_path_for_legacy_ingest() -> None:
    path = derive_chunk_browser_default_path(
        {
            "_ui_pipeline_mode": "legacy",
            "output_jsonl_path": "data/processed/income-tax-act-2023.jsonl",
        }
    )

    assert path == "data/processed/income-tax-act-2023.jsonl"
