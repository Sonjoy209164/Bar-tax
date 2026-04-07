from fastapi import APIRouter

from app.core.schemas import QueryRequest, QueryResponse, RetrievedChunk
from app.generation.citations import format_citations
from app.generation.generator import generate_answer
from app.retrieval.hybrid import hybrid_search

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest) -> QueryResponse:
    retrieved_chunks = hybrid_search(request.query, top_k=request.top_k)
    answer = generate_answer(request.query, retrieved_chunks)
    citations = format_citations(retrieved_chunks)
    return QueryResponse(
        status="success",
        answer=answer,
        citations=citations,
        retrieved_chunks=[
            RetrievedChunk(**chunk) for chunk in retrieved_chunks
        ],
    )
