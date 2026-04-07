from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.schemas import BuildIndexRequest, BuildIndexResponse, ChunkRecord, IngestRequest, IngestResponse
from app.core.settings import get_settings
from app.core.utils import ensure_directory, ensure_file_exists, write_jsonl
from app.ingest.chunker import chunk_pages
from app.ingest.parser import parse_document
from app.retrieval.dense import build_dense_index_artifacts
from app.retrieval.sparse import build_sparse_index, load_chunk_records_from_jsonl, save_sparse_index

router = APIRouter(tags=["ingest"])


def _run_ingestion(request: IngestRequest) -> IngestResponse:
    settings = get_settings()
    input_path = ensure_file_exists(request.input_pdf_path)
    output_path = request.output_jsonl_path or str(
        Path(settings.processed_data_dir) / f"{request.doc_id}.jsonl"
    )
    parsed_pages = parse_document(str(input_path))
    chunks = chunk_pages(
        parsed_pages,
        doc_id=request.doc_id,
        doc_title=request.doc_title or request.doc_id,
        doc_type=request.doc_type,
        authority_level=request.authority_level,
        chunking_mode=request.chunking_mode,
        chunk_size=request.chunk_size,
    )
    write_jsonl([chunk.model_dump() for chunk in chunks], output_path)
    return IngestResponse(
        status="success",
        doc_id=request.doc_id,
        number_of_pages=len(parsed_pages),
        number_of_chunks=len(chunks),
        output_path=output_path,
        output_jsonl_path=output_path,
        chunking_mode=request.chunking_mode,
        message="PDF parsed and chunked successfully.",
    )


def _build_requested_indexes(request: BuildIndexRequest) -> BuildIndexResponse:
    settings = get_settings()
    chunk_jsonl_path = ensure_file_exists(request.chunk_jsonl_path)
    chunk_records = load_chunk_records_from_jsonl(chunk_jsonl_path)
    sparse_index_path: str | None = None
    dense_index_path: str | None = None
    if request.build_sparse:
        sparse_index = build_sparse_index(chunk_records)
        sparse_index_path = str(save_sparse_index(sparse_index, settings.sparse_index_dir))
    if request.build_dense:
        dense_output_dir, _ = build_dense_index_artifacts(chunk_jsonl_path, settings.dense_index_dir)
        dense_index_path = str(dense_output_dir)
    return BuildIndexResponse(
        status="success",
        sparse_index_path=sparse_index_path,
        dense_index_path=dense_index_path,
        number_of_chunks_indexed=len(chunk_records),
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest) -> IngestResponse:
    try:
        return _run_ingestion(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "ingest_failed", "message": str(exc)},
        ) from exc


@router.post("/build-index", response_model=BuildIndexResponse)
async def build_index(request: BuildIndexRequest) -> BuildIndexResponse:
    if not request.build_sparse and not request.build_dense:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_request", "message": "At least one index type must be selected."},
        )
    try:
        return _build_requested_indexes(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": str(exc)},
        ) from exc
