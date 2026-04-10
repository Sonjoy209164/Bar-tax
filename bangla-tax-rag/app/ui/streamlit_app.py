from __future__ import annotations

import json
import sys
from typing import Any
from pathlib import Path
from collections import defaultdict

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings

try:
    import fitz
except Exception:  # pragma: no cover - optional UI dependency
    fitz = None

REQUEST_TIMEOUT_SECONDS = 30
INGEST_TIMEOUT_SECONDS = 300
INDEX_BUILD_TIMEOUT_SECONDS = 120
QUERY_TIMEOUT_SECONDS = 90
GENERATION_TEST_QUESTIONS = [
    "What are the income tax authorities under section 4?",
    "What is the definition of Commissioner?",
    "What does section 32 say about income from employment?",
    "Is software service mentioned in the Act?",
    "What does the Act say about software test lab service?",
    "What is the tax day for a company?",
]


def initialize_session_state() -> None:
    settings = get_settings()
    defaults: dict[str, Any] = {
        "backend_base_url": settings.ui_backend_base_url,
        "last_query_response": None,
        "last_ingest_response": None,
        "last_build_index_response": None,
        "last_retrieval_inspector_response": None,
        "question_preset": GENERATION_TEST_QUESTIONS[0],
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


@st.cache_data(show_spinner=False)
def load_index_artifacts(
    index_dir: str,
    *,
    max_chunks: int = 100,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return {}, [], f"Index directory not found: {path}"
    metadata_path = path / "metadata.json"
    chunks_path = path / "chunks.jsonl"
    if not chunks_path.exists():
        return {}, [], f"Index chunks file not found: {chunks_path}"

    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {}, [], f"Invalid metadata.json: {exc}"

    chunk_records, error_message = load_chunk_records(str(chunks_path), max_chunks=max_chunks)
    if error_message:
        return {}, [], error_message
    return metadata, chunk_records, None


@st.cache_data(show_spinner=False)
def load_parsed_pages(pdf_path: str) -> tuple[list[dict[str, Any]], str | None]:
    path = Path(pdf_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return [], f"PDF file not found: {path}"
    try:
        from app.ingest.parser import parse_document

        parsed_pages = parse_document(str(path))
    except Exception as exc:  # pragma: no cover - defensive UI handling
        return [], str(exc)
    return [page.model_dump() for page in parsed_pages], None


@st.cache_data(show_spinner=False)
def load_pdf_page_snapshot(pdf_path: str, page_no: int, zoom_factor: float = 1.2) -> tuple[bytes | None, str | None]:
    if fitz is None:
        return None, "PyMuPDF is not available for PDF snapshots."
    path = Path(pdf_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return None, f"PDF file not found: {path}"
    try:
        with fitz.open(path) as pdf_document:
            if page_no < 1 or page_no > pdf_document.page_count:
                return None, f"Page {page_no} is out of range."
            page = pdf_document.load_page(page_no - 1)
            matrix = fitz.Matrix(zoom_factor, zoom_factor)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            return pixmap.tobytes("png"), None
    except Exception as exc:  # pragma: no cover - defensive UI handling
        return None, str(exc)


@st.cache_data(show_spinner=False)
def run_local_retrieval_inspection(
    *,
    query_text: str,
    retrieval_mode: str,
    index_dir: str,
    tax_year: str | None,
    top_k: int,
    final_evidence_k: int,
) -> dict[str, Any]:
    from app.core.utils import extract_salient_query_terms, preprocess_query, tokenize_for_bm25
    from app.core.settings import get_settings
    from app.retrieval.dense import dense_search
    from app.retrieval.hybrid import run_hybrid_retrieval
    from app.retrieval.sparse import sparse_search

    settings = get_settings()
    analyzed_query = preprocess_query(query_text)
    search_query = analyzed_query.rewritten_query or analyzed_query.normalized_query
    query_tokens = tokenize_for_bm25(search_query)
    salient_terms = sorted(extract_salient_query_terms(search_query))
    effective_tax_year = tax_year or analyzed_query.tax_year

    payload: dict[str, Any] = {
        "query_text": query_text,
        "retrieval_mode": retrieval_mode,
        "index_dir": index_dir,
        "analyzed_query": analyzed_query.model_dump(),
        "search_query": search_query,
        "query_tokens": query_tokens,
        "salient_terms": salient_terms,
        "tax_year": effective_tax_year,
        "top_k": top_k,
        "final_evidence_k": final_evidence_k,
        "sparse_hits": [],
        "dense_hits": [],
        "fused_hits": [],
        "final_hits": [],
        "conflict_notes": [],
        "evidence_summary": "",
    }

    if retrieval_mode == "sparse":
        sparse_hits = sparse_search(
            query_text,
            top_k=top_k,
            tax_year=effective_tax_year,
            index_dir=index_dir,
        )
        payload["sparse_hits"] = sparse_hits
        payload["final_hits"] = sparse_hits
        return payload

    if retrieval_mode == "dense":
        dense_hits = dense_search(
            query_text,
            top_k=top_k,
            tax_year=effective_tax_year,
            index_dir=settings.dense_index_dir,
        )
        payload["dense_hits"] = dense_hits
        payload["final_hits"] = dense_hits
        return payload

    hybrid_response = run_hybrid_retrieval(
        query=query_text,
        sparse_top_k=max(top_k * 2, 10),
        dense_top_k=max(top_k * 2, 10),
        final_top_k=final_evidence_k,
        tax_year=effective_tax_year,
        index_dir=index_dir,
        dense_index_dir=settings.dense_index_dir,
    )
    payload["sparse_hits"] = [hit.model_dump() for hit in hybrid_response.sparse_hits]
    payload["dense_hits"] = [hit.model_dump() for hit in hybrid_response.dense_hits]
    payload["fused_hits"] = [hit.model_dump() for hit in hybrid_response.fused_hits]
    payload["final_hits"] = [hit.model_dump() for hit in hybrid_response.final_hits]
    payload["conflict_notes"] = hybrid_response.conflict_notes
    payload["evidence_summary"] = hybrid_response.evidence_summary
    return payload


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
    with st.expander("Suggested Questions For Generation", expanded=False):
        st.caption("Load one of these into the query box to test grounded answer generation quickly.")
        preset_column, action_column = st.columns([3, 1])
        with preset_column:
            selected_question = st.selectbox(
                "Question Preset",
                options=GENERATION_TEST_QUESTIONS,
                key="question_preset",
            )
        with action_column:
            st.write("")
            if st.button("Use Question", use_container_width=True):
                st.session_state["question_text"] = selected_question
                st.session_state["last_query_response"] = None
        st.markdown("**Preset List**")
        for question in GENERATION_TEST_QUESTIONS:
            st.code(question, language="text")

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


def render_hit_card(
    hit: dict[str, Any],
    heading: str | None = None,
    *,
    show_intermediate_scores: bool = False,
) -> None:
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
        if show_intermediate_scores and hit.get("intermediate_scores"):
            st.markdown("**Intermediate Scores**")
            st.json(hit.get("intermediate_scores"))
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


def render_parsed_page_card(page: dict[str, Any], *, pdf_path: str, show_snapshot: bool) -> None:
    title = f"page {page.get('page_no', '-')} | lines {page.get('line_count', '-')}"
    with st.expander(title, expanded=False):
        if show_snapshot:
            snapshot_column, detail_column = st.columns([1, 1.4])
        else:
            snapshot_column, detail_column = None, st.container()

        if show_snapshot and snapshot_column is not None:
            with snapshot_column:
                snapshot_bytes, snapshot_error = load_pdf_page_snapshot(pdf_path, int(page.get("page_no") or 0))
                if snapshot_bytes is not None:
                    st.image(snapshot_bytes, caption=f"PDF snapshot: page {page.get('page_no')}", use_container_width=True)
                else:
                    st.caption(f"Snapshot unavailable: {snapshot_error}")

        with detail_column:
            metadata_columns = st.columns(4)
            metadata_columns[0].metric("Appendix", "Yes" if page.get("is_appendix") else "No")
            metadata_columns[1].metric("Example", "Yes" if page.get("is_example") else "No")
            metadata_columns[2].metric("Table Like", "Yes" if page.get("is_table_like") else "No")
            metadata_columns[3].metric("Line Count", str(page.get("line_count") or 0))
            if page.get("headings"):
                st.markdown(f"**Headings:** {' | '.join(page.get('headings') or [])}")
            st.markdown(f"**Section Markers:** {page.get('section_markers') or []}")
            st.markdown(f"**Tax Years:** {page.get('tax_years') or []}")
            st.markdown(f"**SRO IDs:** {page.get('sro_ids') or []}")
            st.markdown("**Raw Text**")
            st.code(page.get("raw_text") or "", language="text")
            normalized_text = page.get("normalized_text") or ""
            raw_text = page.get("raw_text") or ""
            if normalized_text and normalized_text != raw_text:
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


def render_parser_inspector() -> None:
    st.subheader("Parser Inspector")
    st.caption("Inspect page-level parser output before chunking. This runs locally and does not call the API.")
    parser_left, parser_right = st.columns([3, 1])
    with parser_left:
        parser_input_path = st.text_input(
            "PDF Path For Parser Inspection",
            value="/home/sonjoy/Bar tax/Income_tax_act_2023.pdf",
            help="Use a local PDF path. The parser will extract page text, headings, section markers, and page flags.",
        )
    with parser_right:
        preview_limit = st.number_input("Preview Pages", min_value=5, max_value=200, value=20, step=5)
    show_snapshot = st.checkbox("Show PDF snapshots beside parsed output", value=True)

    parsed_pages, error_message = load_parsed_pages(parser_input_path)
    if error_message:
        st.warning(f"Error loading pages: {error_message}")
        return
    if not parsed_pages:
        st.info("No parsed pages available for the selected PDF.")
        return

    filter_left, filter_right = st.columns(2)
    with filter_left:
        page_filter = st.text_input("Filter Single Page Number", value="", placeholder="Example: 24").strip()
    with filter_right:
        parser_view = st.selectbox(
            "Parser View",
            options=["all", "headings only", "table-like only", "appendix only"],
            index=0,
        )

    filtered_pages = parsed_pages
    if page_filter.isdigit():
        filtered_pages = [page for page in filtered_pages if int(page.get("page_no", -1)) == int(page_filter)]
    if parser_view == "headings only":
        filtered_pages = [page for page in filtered_pages if page.get("headings")]
    elif parser_view == "table-like only":
        filtered_pages = [page for page in filtered_pages if page.get("is_table_like")]
    elif parser_view == "appendix only":
        filtered_pages = [page for page in filtered_pages if page.get("is_appendix")]

    limited_pages = filtered_pages[: int(preview_limit)]
    st.json(
        {
            "total_pages_parsed": len(parsed_pages),
            "pages_shown": len(limited_pages),
            "pages_with_headings": sum(1 for page in parsed_pages if page.get("headings")),
            "table_like_pages": sum(1 for page in parsed_pages if page.get("is_table_like")),
            "appendix_pages": sum(1 for page in parsed_pages if page.get("is_appendix")),
        }
    )
    for page in limited_pages:
        render_parsed_page_card(page, pdf_path=parser_input_path, show_snapshot=show_snapshot)


def render_indexed_chunk_card(chunk: dict[str, Any], *, weighted_search_text: str, tokenized_terms: list[str]) -> None:
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
        st.markdown("**Indexed Search Text**")
        st.code(weighted_search_text, language="text")
        st.markdown("**BM25 Tokens**")
        st.code(" ".join(tokenized_terms), language="text")
        st.markdown("**Original Chunk Text**")
        st.code(chunk.get("original_text") or "", language="text")


def _build_index_tree(
    chunk_records: list[dict[str, Any]],
) -> dict[str, dict[int, dict[str, list[dict[str, Any]]]]]:
    tree: dict[str, dict[int, dict[str, list[dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for chunk in chunk_records:
        doc_label = f"{chunk.get('doc_title') or chunk.get('doc_id') or 'unknown document'} [{chunk.get('doc_id') or '-'}]"
        page_no = int(chunk.get("page_no") or -1)
        section_label = (
            chunk.get("subsection_id")
            or chunk.get("section_id")
            or "unlabeled-section"
        )
        tree[doc_label][page_no][str(section_label)].append(chunk)
    return {
        doc_label: {
            page_no: dict(section_map)
            for page_no, section_map in sorted(page_map.items())
        }
        for doc_label, page_map in sorted(tree.items())
    }


def render_index_tree(chunk_records: list[dict[str, Any]]) -> None:
    tree = _build_index_tree(chunk_records)
    st.markdown("**Index Tree**")
    for doc_label, page_map in tree.items():
        doc_chunk_count = sum(
            len(chunks)
            for section_map in page_map.values()
            for chunks in section_map.values()
        )
        with st.container(border=True):
            st.markdown(f"### {doc_label}")
            st.caption(f"{len(page_map)} pages | {doc_chunk_count} chunks")
            for page_no, section_map in page_map.items():
                page_chunk_count = sum(len(chunks) for chunks in section_map.values())
                with st.container(border=True):
                    st.markdown(f"**page {page_no}**")
                    st.caption(f"{len(section_map)} sections | {page_chunk_count} chunks")
                    for section_label, chunks in section_map.items():
                        chunk_type_summary = sorted({str(chunk.get('chunk_type') or 'unknown') for chunk in chunks})
                        st.markdown(
                            f"- **section {section_label}** | {len(chunks)} chunks | {', '.join(chunk_type_summary)}"
                        )
                        for chunk in chunks:
                            chunk_label = (
                                f"{chunk.get('chunk_id', 'unknown-chunk')} | "
                                f"{chunk.get('chunk_type', '-')} | "
                                f"{(chunk.get('heading_path') or ['-'])[-1]}"
                            )
                            with st.container(border=True):
                                st.caption(chunk_label)
                                metadata_columns = st.columns(4)
                                metadata_columns[0].metric("Section", str(chunk.get("section_id") or "-"))
                                metadata_columns[1].metric("Subsection", str(chunk.get("subsection_id") or "-"))
                                metadata_columns[2].metric("Authority", str(chunk.get("authority_level") or "-"))
                                metadata_columns[3].metric("Tax Year", str(chunk.get("tax_year") or "-"))
                                st.code(chunk.get("original_text") or "", language="text")


def render_index_inspector() -> None:
    st.subheader("Index Inspector")
    st.caption("Inspect saved index artifacts after chunking and before retrieval. This reads local index files directly.")

    last_build_index_response = st.session_state.get("last_build_index_response")
    if not isinstance(last_build_index_response, dict):
        last_build_index_response = {}
    default_index_dir = (
        last_build_index_response.get("sparse_index_path")
        or last_build_index_response.get("dense_index_path")
        or "indexes/sparse-english"
    )

    inspector_left, inspector_right = st.columns([3, 1])
    with inspector_left:
        index_dir = st.text_input(
            "Index Directory",
            value=default_index_dir,
            help="Point this to an index directory containing metadata.json and chunks.jsonl.",
        )
    with inspector_right:
        preview_limit = st.number_input("Preview Chunks", min_value=5, max_value=500, value=50, step=5)

    metadata, chunk_records, error_message = load_index_artifacts(index_dir, max_chunks=int(preview_limit))
    if error_message:
        st.warning(f"Error loading index: {error_message}")
        return
    if not chunk_records:
        st.info("No indexed chunks available in the selected index directory.")
        return

    inferred_index_type = "dense" if "dense" in index_dir.lower() else "sparse"
    st.json(
        {
            "index_dir": index_dir,
            "index_type": inferred_index_type,
            "chunk_count_in_metadata": metadata.get("chunk_count"),
            "chunks_loaded_for_preview": len(chunk_records),
            "available_files": ["metadata.json", "chunks.jsonl"],
        }
    )

    available_chunk_types = sorted({str(chunk.get("chunk_type") or "unknown") for chunk in chunk_records})
    filter_left, filter_right = st.columns(2)
    with filter_left:
        chunk_type_filter = st.multiselect(
            "Filter Indexed Chunk Types",
            options=available_chunk_types,
            default=[],
        )
    with filter_right:
        page_filter = st.text_input(
            "Filter Indexed Page Number",
            value="",
            placeholder="Example: 24",
        ).strip()
    view_mode = st.radio(
        "Index View Mode",
        options=["tree", "flat", "both"],
        horizontal=True,
        index=0,
    )

    filtered_chunks = chunk_records
    if chunk_type_filter:
        filtered_chunks = [chunk for chunk in filtered_chunks if chunk.get("chunk_type") in chunk_type_filter]
    if page_filter.isdigit():
        filtered_chunks = [chunk for chunk in filtered_chunks if int(chunk.get("page_no", -1)) == int(page_filter)]

    st.caption(f"Showing {len(filtered_chunks)} of {len(chunk_records)} loaded index chunks")

    if view_mode in {"tree", "both"}:
        render_index_tree(filtered_chunks)

    from app.core.utils import tokenize_for_bm25
    from app.core.schemas import ChunkRecord
    from app.retrieval.sparse import build_weighted_search_text

    if view_mode in {"flat", "both"}:
        st.markdown("**Indexed Chunk Cards**")
        for chunk in filtered_chunks:
            chunk_record = ChunkRecord.model_validate(chunk)
            weighted_search_text = build_weighted_search_text(chunk_record)
            tokenized_terms = tokenize_for_bm25(weighted_search_text)
            render_indexed_chunk_card(
                chunk,
                weighted_search_text=weighted_search_text,
                tokenized_terms=tokenized_terms,
            )


def render_retrieval_inspector() -> None:
    st.subheader("Retrieval Inspector")
    st.caption("Inspect local retrieval before generation. This runs sparse, dense, or hybrid retrieval directly against the selected index directory.")

    last_build_index_response = st.session_state.get("last_build_index_response")
    if not isinstance(last_build_index_response, dict):
        last_build_index_response = {}
    default_index_dir = (
        last_build_index_response.get("sparse_index_path")
        or last_build_index_response.get("dense_index_path")
        or "indexes/sparse-english"
    )

    with st.form("retrieval_inspector_form", clear_on_submit=False):
        question_text = st.text_area(
            "Inspector Query",
            value="What are the income tax authorities under section 4?",
            height=100,
        )
        selection_left, selection_right = st.columns(2)
        with selection_left:
            retrieval_mode = st.selectbox("Retrieval Mode", options=["sparse", "dense", "hybrid"], index=0)
            index_dir = st.text_input("Index Directory", value=default_index_dir)
            tax_year = st.text_input("Tax Year (optional)", value="", placeholder="2025-2026")
        with selection_right:
            top_k = st.number_input("Top K", min_value=1, max_value=20, value=5, step=1)
            final_evidence_k = st.number_input("Final Evidence K", min_value=1, max_value=20, value=5, step=1)
        submitted = st.form_submit_button("Run Retrieval Inspection", use_container_width=True)

    if submitted:
        try:
            response_payload = run_local_retrieval_inspection(
                query_text=question_text,
                retrieval_mode=retrieval_mode,
                index_dir=index_dir,
                tax_year=tax_year or None,
                top_k=int(top_k),
                final_evidence_k=int(final_evidence_k),
            )
        except Exception as exc:  # pragma: no cover - defensive UI handling
            st.error(f"Retrieval inspection failed: {exc}")
        else:
            st.session_state["last_retrieval_inspector_response"] = response_payload
            st.success("Retrieval inspection completed.")

    response_payload = st.session_state.get("last_retrieval_inspector_response")
    if not response_payload:
        st.info("Run a local retrieval inspection to see analyzed query signals, tokens, and hits.")
        return

    st.markdown("**Analyzed Query**")
    st.json(response_payload.get("analyzed_query") or {})
    search_query = response_payload.get("search_query")
    if search_query:
        st.markdown("**Effective Search Query**")
        st.code(search_query, language="text")

    token_left, token_right = st.columns(2)
    with token_left:
        st.markdown("**Query Tokens**")
        st.code(" ".join(response_payload.get("query_tokens") or []), language="text")
    with token_right:
        st.markdown("**Salient Terms**")
        st.code(" ".join(response_payload.get("salient_terms") or []), language="text")

    conflict_notes = response_payload.get("conflict_notes") or []
    if conflict_notes:
        st.warning("Conflicts detected during final evidence selection.")
        for note in conflict_notes:
            st.write(f"- {note}")

    evidence_summary = response_payload.get("evidence_summary")
    if evidence_summary:
        st.markdown("**Evidence Summary**")
        st.code(evidence_summary, language="text")

    retrieval_mode = response_payload.get("retrieval_mode")
    if retrieval_mode == "hybrid":
        sparse_tab, dense_tab, fused_tab, final_tab = st.tabs(["Sparse", "Dense", "Fused", "Final Evidence"])
        with sparse_tab:
            sparse_hits = response_payload.get("sparse_hits") or []
            if not sparse_hits:
                st.caption("No sparse hits returned.")
            for hit in sparse_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        with dense_tab:
            dense_hits = response_payload.get("dense_hits") or []
            if not dense_hits:
                st.caption("No dense hits returned.")
            for hit in dense_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        with fused_tab:
            fused_hits = response_payload.get("fused_hits") or []
            if not fused_hits:
                st.caption("No fused hits returned.")
            for hit in fused_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        with final_tab:
            final_hits = response_payload.get("final_hits") or []
            if not final_hits:
                st.caption("No final evidence hits returned.")
            for hit in final_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        return

    st.markdown("**Retrieved Hits**")
    hits = response_payload.get("sparse_hits") if retrieval_mode == "sparse" else response_payload.get("dense_hits")
    if not hits:
        st.info("No hits returned.")
        return
    for hit in hits:
        render_hit_card(hit, show_intermediate_scores=True)


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

    st.sidebar.header("Navigation")
    view_name = st.sidebar.radio(
        "View",
        options=["Research Workspace", "Parser Inspector", "Index Inspector", "Retrieval Inspector"],
        index=0,
    )

    config_payload, api_reachable = render_api_connection_panel(st.session_state["backend_base_url"])
    if not api_reachable:
        st.warning("Backend API is not confirmed reachable. You can still fill the forms, but actions may fail until the API is running.")
    if config_payload:
        with st.expander("Runtime Config Snapshot", expanded=False):
            st.json(config_payload)

    if view_name == "Parser Inspector":
        render_parser_inspector()
        return
    if view_name == "Index Inspector":
        render_index_inspector()
        return
    if view_name == "Retrieval Inspector":
        render_retrieval_inspector()
        return

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
