from __future__ import annotations

import json
import sys
from typing import Any
from pathlib import Path

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings

REQUEST_TIMEOUT_SECONDS = 30
INGEST_TIMEOUT_SECONDS = 300
INDEX_BUILD_TIMEOUT_SECONDS = 120
QUERY_TIMEOUT_SECONDS = 90


def initialize_session_state() -> None:
    settings = get_settings()
    defaults: dict[str, Any] = {
        "backend_base_url": settings.ui_backend_base_url,
        "last_query_response": None,
        "last_ingest_response": None,
        "last_build_index_response": None,
        "question_text": "২০২৫-২০২৬ করবর্ষে কোম্পানির করহার কী?",
        "retrieval_mode": settings.retrieval_mode,
        "tax_year": "",
        "top_k": settings.top_k,
        "final_evidence_k": settings.final_evidence_k,
        "include_intermediate_hits": False,
        "generate_answer": True,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def load_chunk_records(chunk_jsonl_path: str, *, max_chunks: int = 100) -> tuple[list[dict[str, Any]], str | None]:
    path = Path(chunk_jsonl_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return [], f"Chunk file not found: {path}"

    chunk_records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as chunk_file:
            for line_number, line in enumerate(chunk_file, start=1):
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                try:
                    chunk_records.append(json.loads(stripped_line))
                except json.JSONDecodeError as exc:
                    return [], f"Invalid JSONL at line {line_number}: {exc}"
                if len(chunk_records) >= max_chunks:
                    break
    except OSError as exc:
        return [], str(exc)
    return chunk_records, None


def api_get(base_url: str, endpoint: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        response = requests.get(f"{base_url.rstrip('/')}{endpoint}", timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return True, response.json(), None
    except requests.RequestException as exc:
        return False, None, str(exc)


def api_post(
    base_url: str,
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}{endpoint}",
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return True, response.json(), None
    except requests.RequestException as exc:
        message = str(exc)
        if exc.response is not None:
            try:
                message = str(exc.response.json())
            except ValueError:
                message = exc.response.text or message
        return False, None, message


def render_api_connection_panel(base_url: str) -> tuple[dict[str, Any] | None, bool]:
    st.sidebar.header("API Connection")
    backend_base_url = st.sidebar.text_input(
        "Backend Base URL",
        key="backend_base_url",
        help="Expected local default: http://127.0.0.1:8000",
    )
    check_connection = st.sidebar.button("Check API Health", use_container_width=True)
    config_payload: dict[str, Any] | None = None
    api_reachable = False
    if check_connection or backend_base_url:
        health_ok, health_payload, health_error = api_get(backend_base_url, "/health")
        if health_ok:
            api_reachable = True
            st.sidebar.success(f"API reachable: {health_payload.get('service', 'unknown service')}")
            config_ok, config_payload, config_error = api_get(backend_base_url, "/config")
            if config_ok and config_payload is not None:
                st.sidebar.caption(f"Mode: {config_payload.get('retrieval_mode')} | Top K: {config_payload.get('top_k')}")
            elif config_error:
                st.sidebar.warning(f"Config unavailable: {config_error}")
        elif check_connection:
            st.sidebar.warning(f"API unreachable: {health_error}")
    return config_payload, api_reachable


def render_ingestion_panel(base_url: str) -> None:
    st.subheader("PDF Ingestion")
    with st.form("ingest_form", clear_on_submit=False):
        input_pdf_path = st.text_input("Input PDF Path", value="/home/sonjoy/Bar tax/Income_tax_act_2023.pdf")
        doc_id = st.text_input("Document ID", value="income-tax-act-2023")
        doc_title = st.text_input("Document Title", value="Income Tax Act 2023")
        column_left, column_right = st.columns(2)
        with column_left:
            doc_type = st.text_input("Document Type", value="statute")
            authority_level = st.selectbox("Authority Level", options=["unknown", "local", "regional", "national", "statute", "constitutional"], index=3)
        with column_right:
            chunking_mode = st.selectbox("Chunking Mode", options=["section_aware", "naive", "example_aware", "table_aware"], index=0)
            output_jsonl_path = st.text_input("Output JSONL Path", value="data/processed/income-tax-act-2023.jsonl")
        ocr_column_left, ocr_column_right = st.columns(2)
        with ocr_column_left:
            ocr_enabled = st.checkbox("Enable OCR For Bangla PDF", value=False)
            ocr_force = st.checkbox("Force OCR Even If Text Exists", value=True)
        with ocr_column_right:
            ocr_language = st.text_input("OCR Language", value="ben+eng")
            ocr_output_pdf_path = st.text_input(
                "OCR Output PDF Path",
                value="data/processed/income-tax-act-2023.ocr.pdf",
            )
        submitted = st.form_submit_button("Ingest PDF", use_container_width=True)

    if submitted:
        payload = {
            "input_pdf_path": input_pdf_path,
            "doc_id": doc_id,
            "doc_title": doc_title,
            "doc_type": doc_type,
            "authority_level": authority_level,
            "chunking_mode": chunking_mode,
            "output_jsonl_path": output_jsonl_path or None,
            "ocr_enabled": ocr_enabled,
            "ocr_language": ocr_language,
            "ocr_force": ocr_force,
            "ocr_output_pdf_path": ocr_output_pdf_path or None,
        }
        success, response_payload, error_message = api_post(
            base_url,
            "/ingest",
            payload,
            timeout_seconds=INGEST_TIMEOUT_SECONDS,
        )
        if success and response_payload is not None:
            st.session_state["last_ingest_response"] = response_payload
            st.success("PDF ingestion completed.")
        else:
            st.error(f"Ingestion failed: {error_message}")
            st.caption("Large or messy Bangla PDFs can take longer to parse. If this keeps happening, try the CLI ingestion command first.")

    if st.session_state.get("last_ingest_response"):
        ingest_response = st.session_state["last_ingest_response"]
        st.json(
            {
                "status": ingest_response.get("status"),
                "number_of_pages": ingest_response.get("number_of_pages"),
                "number_of_chunks": ingest_response.get("number_of_chunks"),
                "output_jsonl_path": ingest_response.get("output_jsonl_path"),
                "chunking_mode": ingest_response.get("chunking_mode"),
                "ocr_applied": ingest_response.get("ocr_applied"),
                "ocr_output_pdf_path": ingest_response.get("ocr_output_pdf_path"),
            }
        )


def render_index_building_panel(base_url: str) -> None:
    st.subheader("Index Building")
    with st.form("build_index_form", clear_on_submit=False):
        chunk_jsonl_path = st.text_input("Chunk JSONL Path", value="data/processed/income-tax-act-2023.jsonl")
        build_sparse = st.checkbox("Build Sparse Index", value=True)
        build_dense = st.checkbox("Build Dense Index", value=False)
        submitted = st.form_submit_button("Build Index", use_container_width=True)

    if submitted:
        payload = {
            "chunk_jsonl_path": chunk_jsonl_path,
            "build_sparse": build_sparse,
            "build_dense": build_dense,
        }
        success, response_payload, error_message = api_post(
            base_url,
            "/build-index",
            payload,
            timeout_seconds=INDEX_BUILD_TIMEOUT_SECONDS,
        )
        if success and response_payload is not None:
            st.session_state["last_build_index_response"] = response_payload
            st.success("Index build completed.")
        else:
            st.error(f"Index build failed: {error_message}")

    if st.session_state.get("last_build_index_response"):
        build_response = st.session_state["last_build_index_response"]
        st.json(
            {
                "status": build_response.get("status"),
                "sparse_index_path": build_response.get("sparse_index_path"),
                "dense_index_path": build_response.get("dense_index_path"),
                "number_of_chunks_indexed": build_response.get("number_of_chunks_indexed"),
            }
        )


def render_query_panel(base_url: str) -> None:
    st.subheader("Query")
    with st.form("query_form", clear_on_submit=False):
        question_text = st.text_area(
            "Question Text",
            key="question_text",
            height=100,
            placeholder="Ask in Bangla or English.",
        )
        selection_left, selection_right = st.columns(2)
        with selection_left:
            retrieval_mode = st.selectbox("Retrieval Mode", options=["sparse", "dense", "hybrid"], key="retrieval_mode")
            tax_year = st.text_input("Tax Year (optional)", key="tax_year", placeholder="2025-2026")
            top_k = st.number_input("Top K", min_value=1, max_value=20, step=1, key="top_k")
        with selection_right:
            final_evidence_k = st.number_input("Final Evidence K", min_value=1, max_value=20, step=1, key="final_evidence_k")
            include_intermediate_hits = st.checkbox("Include Intermediate Hits", key="include_intermediate_hits")
            generate_answer = st.checkbox("Generate Grounded Answer", key="generate_answer")
        submitted = st.form_submit_button("Run Query", use_container_width=True)

    if submitted:
        payload = {
            "question_text": question_text,
            "retrieval_mode": retrieval_mode,
            "tax_year": tax_year or None,
            "top_k": int(top_k),
            "final_evidence_k": int(final_evidence_k),
            "include_intermediate_hits": include_intermediate_hits,
            "generate_answer": generate_answer,
        }
        success, response_payload, error_message = api_post(
            base_url,
            "/query",
            payload,
            timeout_seconds=QUERY_TIMEOUT_SECONDS,
        )
        if success and response_payload is not None:
            st.session_state["last_query_response"] = response_payload
            st.success("Query completed.")
        else:
            st.error(f"Query failed: {error_message}")


def render_citations(citations: list[dict[str, Any]]) -> None:
    if not citations:
        return
    st.markdown("**Sentence-level Citations**")
    for citation in citations:
        with st.container(border=True):
            st.markdown(f"`{citation.get('marker')}` {citation.get('doc_title')} | page {citation.get('page_no')}")
            st.caption(
                f"chunk_id={citation.get('chunk_id')} | section={citation.get('section_id') or '-'} | "
                f"subsection={citation.get('subsection_id') or '-'}"
            )
            st.write(citation.get("evidence_snippet", ""))


def render_hit_card(hit: dict[str, Any], heading: str | None = None) -> None:
    title = heading or f"{hit.get('doc_title', 'Untitled Document')} | page {hit.get('page_no', '-')}"
    with st.expander(title, expanded=False):
        metadata_columns = st.columns(4)
        metadata_columns[0].metric("Score", f"{hit.get('score', 0):.4f}" if isinstance(hit.get("score"), (int, float)) else hit.get("score", "-"))
        metadata_columns[1].metric("Chunk Type", str(hit.get("chunk_type", "-")))
        metadata_columns[2].metric("Authority", str(hit.get("authority_level", "-")))
        metadata_columns[3].metric("Tax Year", str(hit.get("tax_year", "-")))
        st.caption(
            f"chunk_id={hit.get('chunk_id')} | section={hit.get('section_id') or '-'} | "
            f"subsection={hit.get('subsection_id') or '-'}"
        )
        heading_path = hit.get("heading_path") or []
        if heading_path:
            st.markdown(f"**Heading Path:** {' > '.join(heading_path)}")
        snippet = hit.get("original_text") or hit.get("content") or hit.get("normalized_text") or ""
        st.write(snippet)


def render_chunk_card(chunk: dict[str, Any]) -> None:
    title = (
        f"{chunk.get('chunk_id', 'unknown-chunk')} | "
        f"page {chunk.get('page_no', '-')} | "
        f"{chunk.get('chunk_type', '-')}"
    )
    with st.expander(title, expanded=False):
        metadata_columns = st.columns(4)
        metadata_columns[0].metric("Section", str(chunk.get("section_id") or "-"))
        metadata_columns[1].metric("Subsection", str(chunk.get("subsection_id") or "-"))
        metadata_columns[2].metric("Authority", str(chunk.get("authority_level") or "-"))
        metadata_columns[3].metric("Tax Year", str(chunk.get("tax_year") or "-"))
        heading_path = chunk.get("heading_path") or []
        if heading_path:
            st.markdown(f"**Heading Path:** {' > '.join(heading_path)}")
        st.markdown("**Original Text**")
        st.code(chunk.get("original_text") or "", language="text")
        normalized_text = chunk.get("normalized_text") or ""
        if normalized_text and normalized_text != chunk.get("original_text"):
            st.markdown("**Normalized Text**")
            st.code(normalized_text, language="text")


def render_chunk_browser() -> None:
    st.subheader("Chunk Browser")
    last_ingest_response = st.session_state.get("last_ingest_response")
    if not isinstance(last_ingest_response, dict):
        last_ingest_response = {}
    default_chunk_path = (
        last_ingest_response.get("output_jsonl_path")
        or "data/processed/income-tax-act-2023.jsonl"
    )
    browser_left, browser_right = st.columns([3, 1])
    with browser_left:
        chunk_jsonl_path = st.text_input(
            "Chunk JSONL Path For Preview",
            value=default_chunk_path,
            help="Browse locally generated chunk records without calling the API.",
        )
    with browser_right:
        max_chunks = st.number_input("Preview Count", min_value=10, max_value=500, value=50, step=10)

    chunk_records, error_message = load_chunk_records(chunk_jsonl_path, max_chunks=int(max_chunks))
    if error_message:
        st.warning(error_message)
        return
    if not chunk_records:
        st.info("No chunks found in the selected file.")
        return

    available_chunk_types = sorted({str(chunk.get("chunk_type") or "unknown") for chunk in chunk_records})
    filter_left, filter_right = st.columns(2)
    with filter_left:
        chunk_type_filter = st.multiselect(
            "Filter Chunk Types",
            options=available_chunk_types,
            default=[],
        )
    with filter_right:
        page_filter = st.text_input(
            "Filter Page Number",
            value="",
            placeholder="Example: 17",
        ).strip()

    filtered_chunks = chunk_records
    if chunk_type_filter:
        filtered_chunks = [chunk for chunk in filtered_chunks if chunk.get("chunk_type") in chunk_type_filter]
    if page_filter.isdigit():
        filtered_chunks = [chunk for chunk in filtered_chunks if int(chunk.get("page_no", -1)) == int(page_filter)]

    st.caption(f"Showing {len(filtered_chunks)} of {len(chunk_records)} loaded chunks")
    for chunk in filtered_chunks:
        render_chunk_card(chunk)


def render_results_panel() -> None:
    st.subheader("Results")
    response_payload = st.session_state.get("last_query_response")
    if not response_payload:
        st.info("Run a query to view analyzed query signals, grounded answers, and evidence hits.")
        return

    analyzed_query = response_payload.get("analyzed_query", {})
    st.markdown("**Analyzed Query**")
    st.json(analyzed_query)
    rewritten_query = analyzed_query.get("rewritten_query")
    if rewritten_query and rewritten_query != analyzed_query.get("normalized_query"):
        st.markdown("**Rewritten Query**")
        st.code(rewritten_query, language="text")

    answer_text = response_payload.get("answer")
    abstained = response_payload.get("abstained")
    abstention_reason = response_payload.get("abstention_reason")
    confidence_score = response_payload.get("confidence_score")
    if abstained:
        st.warning(f"Generation abstained. {abstention_reason or ''}".strip())
    elif answer_text:
        st.markdown("**Answer**")
        st.write(answer_text)
    else:
        st.info("Generation disabled or no answer returned.")

    if confidence_score is not None:
        st.metric("Confidence Score", f"{confidence_score:.4f}")

    conflict_notes = response_payload.get("conflict_notes") or []
    if conflict_notes:
        st.warning("Conflicts detected in evidence.")
        for note in conflict_notes:
            st.write(f"- {note}")

    render_citations(response_payload.get("citations") or [])

    st.markdown("**Final Evidence Hits**")
    final_hits = response_payload.get("final_hits") or []
    if not final_hits:
        st.info("No final evidence hits returned.")
    for hit in final_hits:
        render_hit_card(hit)

    if (
        response_payload.get("sparse_hits")
        or response_payload.get("dense_hits")
        or response_payload.get("fused_hits")
    ):
        st.markdown("**Intermediate Retrieval Views**")
        sparse_tab, dense_tab, fused_tab = st.tabs(["Sparse", "Dense", "Fused"])
        with sparse_tab:
            sparse_hits = response_payload.get("sparse_hits") or []
            if not sparse_hits:
                st.caption("No sparse hits returned.")
            for hit in sparse_hits:
                render_hit_card(hit)
        with dense_tab:
            dense_hits = response_payload.get("dense_hits") or []
            if not dense_hits:
                st.caption("No dense hits returned.")
            for hit in dense_hits:
                render_hit_card(hit)
        with fused_tab:
            fused_hits = response_payload.get("fused_hits") or []
            if not fused_hits:
                st.caption("No fused hits returned.")
            for hit in fused_hits:
                render_hit_card(hit)


def main() -> None:
    initialize_session_state()
    st.set_page_config(page_title="Bangla Tax RAG", layout="wide")
    st.title("Bangla Tax RAG")
    st.caption("Research UI for PDF ingestion, index building, grounded retrieval, and cited answer exploration.")

    config_payload, api_reachable = render_api_connection_panel(st.session_state["backend_base_url"])
    if not api_reachable:
        st.warning("Backend API is not confirmed reachable. You can still fill the forms, but actions may fail until the API is running.")
    if config_payload:
        with st.expander("Runtime Config Snapshot", expanded=False):
            st.json(config_payload)

    ingest_column, build_column = st.columns(2)
    with ingest_column:
        render_ingestion_panel(st.session_state["backend_base_url"])
    with build_column:
        render_index_building_panel(st.session_state["backend_base_url"])

    render_chunk_browser()
    render_query_panel(st.session_state["backend_base_url"])
    render_results_panel()


if __name__ == "__main__":
    main()
