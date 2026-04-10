from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class ErrorResponse(BaseModel):
    status: str = "error"
    error: str
    message: str


class IngestRequest(BaseModel):
    input_pdf_path: str = Field(..., description="Path to the input PDF.")
    doc_id: str = Field(..., description="Unique document identifier.")
    doc_title: str | None = Field(default=None, description="Human-readable document title.")
    doc_type: str = Field(default="tax_document")
    authority_level: str = Field(default="unknown")
    chunking_mode: str = Field(default="section_aware")
    output_jsonl_path: str | None = None
    chunk_size: int = Field(default=1000, ge=200, le=5000)
    ocr_enabled: bool = False
    ocr_language: str = Field(default="ben+eng")
    ocr_force: bool = True
    ocr_output_pdf_path: str | None = None


class ParsedPage(BaseModel):
    page_no: int
    raw_text: str
    normalized_text: str
    headings: list[str] = Field(default_factory=list)
    section_markers: list[str] = Field(default_factory=list)
    tax_years: list[str] = Field(default_factory=list)
    sro_ids: list[str] = Field(default_factory=list)
    is_appendix: bool = False
    is_example: bool = False
    is_table_like: bool = False
    line_count: int = 0


class IngestResponse(BaseModel):
    status: str
    doc_id: str
    number_of_pages: int = 0
    number_of_chunks: int
    output_path: str | None = None
    output_jsonl_path: str | None = None
    chunking_mode: str
    ocr_applied: bool = False
    ocr_output_pdf_path: str | None = None
    message: str | None = None


class ChunkRecord(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    authority_level: str
    tax_year: str | None = None
    effective_start: str | None = None
    effective_end: str | None = None
    page_no: int
    section_id: str | None = None
    subsection_id: str | None = None
    appendix_id: str | None = None
    sro_id: str | None = None
    chunk_type: str
    heading_path: list[str] = Field(default_factory=list)
    original_text: str
    normalized_text: str
    cross_refs: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question_text: str
    retrieval_mode: Literal["sparse", "dense", "hybrid"] = "hybrid"
    tax_year: str | None = None
    doc_type: str | None = None
    authority_level_min: str | None = None
    chunk_type: str | None = None
    final_evidence_k: int | None = Field(default=None, ge=1, le=20)
    include_intermediate_hits: bool = False
    generate_answer: bool = True
    top_k: int = Field(default=5, ge=1, le=20)


class QuerySignals(BaseModel):
    original_query: str
    normalized_query: str
    rewritten_query: str | None = None
    tax_year: str | None = None
    section_reference: str | None = None
    section_id: str | None = None
    subsection_id: str | None = None
    appendix_reference: str | None = None
    appendix_id: str | None = None
    sro_reference: str | None = None
    sro_id: str | None = None
    query_type: str = "general"
    query_intent: str = "general"


class RetrievalHit(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    page_no: int
    section_id: str | None = None
    subsection_id: str | None = None
    chunk_type: str
    authority_level: str
    tax_year: str | None = None
    original_text: str
    normalized_text: str
    heading_path: list[str] = Field(default_factory=list)
    content: str
    score: float
    intermediate_scores: dict[str, float | int | str | None] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    status: str
    query: str
    signals: QuerySignals
    hits: list[RetrievalHit] = Field(default_factory=list)


class HybridRetrievalResponse(BaseModel):
    query_text: str
    analyzed_query: QuerySignals
    sparse_hits: list[RetrievalHit] = Field(default_factory=list)
    dense_hits: list[RetrievalHit] = Field(default_factory=list)
    fused_hits: list[RetrievalHit] = Field(default_factory=list)
    final_hits: list[RetrievalHit] = Field(default_factory=list)
    conflict_notes: list[str] = Field(default_factory=list)
    evidence_summary: str = ""
    dropped_duplicates: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    status: str
    answer: str
    citations: list[str]
    retrieved_chunks: list[RetrievalHit]


class GenerationOptions(BaseModel):
    provider: str = "mock"
    model_name: str = "mock-grounded-generator"
    base_url: str | None = None
    api_key: str | None = None
    max_generation_tokens: int = 512
    temperature: float = 0.0
    abstention_score_threshold: float = 0.75
    verification_enabled: bool = True
    fallback_to_mock: bool = True


class CitationRecord(BaseModel):
    marker: str
    chunk_id: str
    doc_title: str
    page_no: int
    section_id: str | None = None
    subsection_id: str | None = None
    evidence_snippet: str


class AnswerSentence(BaseModel):
    sentence_text: str
    citation_markers: list[str] = Field(default_factory=list)
    supported: bool = True
    support_notes: str | None = None


class AbstentionDecision(BaseModel):
    abstained: bool
    reason: str | None = None
    stage: str | None = None


class GeneratedAnswer(BaseModel):
    answer_text: str
    answer_sentences: list[AnswerSentence] = Field(default_factory=list)
    citations: list[CitationRecord] = Field(default_factory=list)
    used_chunk_ids: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    abstained: bool = False
    abstention_reason: str | None = None
    conflict_notes: list[str] = Field(default_factory=list)
    verification_passed: bool = False


class QueryAPIResponse(BaseModel):
    status: str
    retrieval_mode: Literal["sparse", "dense", "hybrid"]
    analyzed_query: QuerySignals
    final_hits: list[RetrievalHit] = Field(default_factory=list)
    conflict_notes: list[str] = Field(default_factory=list)
    answer: str | None = None
    citations: list[CitationRecord] = Field(default_factory=list)
    abstained: bool | None = None
    abstention_reason: str | None = None
    confidence_score: float | None = None
    sparse_hits: list[RetrievalHit] = Field(default_factory=list)
    dense_hits: list[RetrievalHit] = Field(default_factory=list)
    fused_hits: list[RetrievalHit] = Field(default_factory=list)


class EvalRequest(BaseModel):
    dataset_path: str
    retrieval_modes: list[Literal["sparse", "dense", "hybrid"]] = Field(default_factory=lambda: ["hybrid"])
    generate_answers: bool = True
    output_dir: str | None = None


class EvalResponse(BaseModel):
    status: str
    output_paths: list[str] = Field(default_factory=list)
    metrics_summary: dict[str, Any]


class AnnotationCandidate(BaseModel):
    question_id: str
    source_chunk_id: str
    source_doc_id: str
    source_doc_title: str
    question_text: str
    question_type: Literal[
        "rate_lookup",
        "definition",
        "amendment",
        "procedure",
        "example_based",
        "calculation",
        "comparison",
        "authority_conflict",
    ]
    heading_path: list[str] = Field(default_factory=list)
    tax_year: str | None = None
    section_id: str | None = None
    subsection_id: str | None = None
    chunk_type: str
    evidence_snippet: str
    notes: str | None = None


class EvidenceLabel(BaseModel):
    chunk_id: str
    doc_id: str
    section_id: str | None = None
    subsection_id: str | None = None
    tax_year: str | None = None
    authority_level: str | None = None


class AnnotatedQuestion(BaseModel):
    question_id: str
    question_text: str
    question_type: Literal[
        "rate_lookup",
        "definition",
        "amendment",
        "procedure",
        "example_based",
        "calculation",
        "comparison",
        "authority_conflict",
    ]
    answer_text: str | None = None
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_doc_ids: list[str] = Field(default_factory=list)
    expected_sections: list[str] = Field(default_factory=list)
    expected_tax_year: str | None = None
    preferred_authority_level: str | None = None
    should_abstain: bool | None = None
    answer_language: str = "bangla"
    notes: str | None = None


class DatasetValidationReport(BaseModel):
    valid: bool
    dataset_path: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BuildIndexRequest(BaseModel):
    chunk_jsonl_path: str
    build_sparse: bool = True
    build_dense: bool = False


class BuildIndexResponse(BaseModel):
    status: str
    sparse_index_path: str | None = None
    dense_index_path: str | None = None
    number_of_chunks_indexed: int


class ConfigResponse(BaseModel):
    app_name: str
    app_env: str
    raw_data_dir: str
    processed_data_dir: str
    sparse_index_dir: str
    dense_index_dir: str
    results_dir: str
    ui_backend_base_url: str
    retrieval_mode: str
    top_k: int
    final_evidence_k: int
    generator_provider: str
    generator_model_name: str
    generator_base_url: str | None = None
    max_generation_tokens: int
    temperature: float
    abstention_score_threshold: float
    verification_enabled: bool
    embedding_provider: str
    embedding_model_name: str
    reranker_provider: str
    reranker_model_name: str
