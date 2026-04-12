from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.schemas import QueryAPIResponse, QueryRequest, RetrievalHit
from app.core.settings import get_settings
from app.core.utils import preprocess_query
from app.generation.generator import build_generation_options, generate_answer
from app.retrieval.dense import dense_search
from app.retrieval.filters import filter_supportive_hits
from app.retrieval.hybrid import run_hybrid_retrieval
from app.retrieval.sparse import load_sparse_index, search_sparse_index

router = APIRouter(tags=["query"])


def _run_query_pipeline(request: QueryRequest) -> QueryAPIResponse:
    settings = get_settings()
    analyzed_query = preprocess_query(request.question_text)
    effective_top_k = request.top_k or settings.top_k
    effective_final_k = request.final_evidence_k or settings.final_evidence_k
    index_dir = settings.sparse_index_dir
    if not Path(index_dir, "chunks.jsonl").exists():
        raise FileNotFoundError(f"Sparse index not found at {index_dir}")

    sparse_hits: list[RetrievalHit] = []
    dense_hits: list[RetrievalHit] = []
    fused_hits: list[RetrievalHit] = []
    final_hits: list[RetrievalHit] = []
    conflict_notes: list[str] = []

    if request.retrieval_mode == "sparse":
        sparse_response = search_sparse_index(
            query=request.question_text,
            index=load_sparse_index(index_dir),
            top_k=effective_top_k,
            tax_year=request.tax_year,
            doc_type=request.doc_type,
            authority_level_min=request.authority_level_min,
            chunk_type=request.chunk_type,
        )
        final_hits = sparse_response.hits[:effective_final_k]
    elif request.retrieval_mode == "dense":
        dense_hits = [RetrievalHit(**hit) for hit in dense_search(
            request.question_text,
            top_k=effective_top_k,
            tax_year=request.tax_year,
            doc_type=request.doc_type,
            authority_level_min=request.authority_level_min,
            chunk_type=request.chunk_type,
            index_dir=settings.dense_index_dir,
        )]
        final_hits = dense_hits[:effective_final_k]
    elif request.retrieval_mode == "hybrid":
        hybrid_response = run_hybrid_retrieval(
            query=request.question_text,
            sparse_top_k=effective_top_k,
            dense_top_k=effective_top_k,
            final_top_k=effective_final_k,
            tax_year=request.tax_year,
            doc_type=request.doc_type,
            authority_level_min=request.authority_level_min,
            chunk_type=request.chunk_type,
            index_dir=index_dir,
            dense_index_dir=settings.dense_index_dir,
        )
        analyzed_query = hybrid_response.analyzed_query
        sparse_hits = hybrid_response.sparse_hits
        dense_hits = hybrid_response.dense_hits
        fused_hits = hybrid_response.fused_hits
        final_hits = hybrid_response.final_hits
        conflict_notes = hybrid_response.conflict_notes
    else:
        raise ValueError(f"Unsupported retrieval mode: {request.retrieval_mode}")

    answer_text: str | None = None
    citations = []
    abstained: bool | None = None
    abstention_reason: str | None = None
    confidence_score: float | None = None
    effective_generation_model_name = request.generator_model_name or settings.generator_model_name
    supportive_hits = filter_supportive_hits(final_hits, analyzed_query)
    requires_exact_support = bool(analyzed_query.subsection_id) or (
        analyzed_query.query_intent == "rate_lookup" and bool(analyzed_query.section_id)
    )
    if requires_exact_support:
        if supportive_hits:
            final_hits = supportive_hits[:effective_final_k]
        else:
            final_hits = []
            conflict_notes = list(dict.fromkeys([*conflict_notes, "No final evidence directly supports the requested section or subsection."]))
    if request.generate_answer:
        generation_hits = final_hits
        generation_options = build_generation_options(
            provider=settings.generator_provider,
            model_name=effective_generation_model_name,
            base_url=settings.generator_base_url,
            api_key=settings.generator_api_key,
        )
        generated_answer = generate_answer(
            request.question_text,
            generation_hits,
            analyzed_query,
            options=generation_options,
            conflict_notes=conflict_notes,
        )
        answer_text = generated_answer.answer_text if not generated_answer.abstained else None
        citations = generated_answer.citations
        abstained = generated_answer.abstained
        abstention_reason = generated_answer.abstention_reason
        confidence_score = generated_answer.confidence_score
        if requires_exact_support and not final_hits and not generated_answer.abstained:
            answer_text = None
            abstained = True
            abstention_reason = "No final evidence directly supports the requested section or subsection."
            confidence_score = 0.0

    return QueryAPIResponse(
        status="success",
        retrieval_mode=request.retrieval_mode,
        analyzed_query=analyzed_query,
        generation_model_name=effective_generation_model_name if request.generate_answer else None,
        final_hits=final_hits,
        conflict_notes=conflict_notes,
        answer=answer_text,
        citations=citations,
        abstained=abstained,
        abstention_reason=abstention_reason,
        confidence_score=confidence_score,
        sparse_hits=sparse_hits if request.include_intermediate_hits else [],
        dense_hits=dense_hits if request.include_intermediate_hits else [],
        fused_hits=fused_hits if request.include_intermediate_hits else [],
    )


@router.post("/query", response_model=QueryAPIResponse)
async def query_documents(request: QueryRequest) -> QueryAPIResponse:
    try:
        return _run_query_pipeline(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_index", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_request", "message": str(exc)},
        ) from exc
