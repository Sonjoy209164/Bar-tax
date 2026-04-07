from fastapi import APIRouter

from app.core.schemas import IngestRequest, IngestResponse
from app.ingest.chunker import chunk_text
from app.ingest.parser import parse_document

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest) -> IngestResponse:
    parsed_document = parse_document(request.source_path)
    chunks = chunk_text(parsed_document["content"], request.chunk_size)
    return IngestResponse(
        status="accepted",
        document_id=request.document_id,
        chunk_count=len(chunks),
        message="Ingestion scaffold completed.",
    )
