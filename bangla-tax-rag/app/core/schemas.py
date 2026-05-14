from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.query_taxonomy import QueryExecutionPath, QueryType


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
    generator_model_name: str | None = None
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
    query_type: QueryType = QueryType.GENERAL
    query_intent: QueryType = QueryType.GENERAL
    execution_path: QueryExecutionPath = QueryExecutionPath.FAST_PATH


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
    provider: str = "openai_compatible"
    model_name: str = "deepseek-r1:7b"
    base_url: str | None = None
    api_key: str | None = None
    max_generation_tokens: int = 512
    temperature: float = 0.0
    abstention_score_threshold: float = 0.75
    verification_enabled: bool = True
    fallback_to_mock: bool = False


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
    generation_model_name: str | None = None
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


class InventoryEvalRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    baseline_summary_path: str | None = None

    @field_validator("case_ids")
    @classmethod
    def normalize_case_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for case_id in value:
            stripped = case_id.strip()
            if not stripped:
                continue
            lowered = stripped.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(stripped)
        return normalized

    @field_validator("output_dir", "baseline_summary_path")
    @classmethod
    def normalize_optional_eval_paths(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


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
    api_auth_enabled: bool = False
    api_key_rotation_enabled: bool = False
    api_rate_limit_requests: int = 0
    api_rate_limit_window_seconds: int = 60
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


class InventoryImageAsset(BaseModel):
    image_id: str = Field(..., description="Stable image identifier, usually product_id plus sequence.")
    url: str | None = Field(default=None, description="Direct HTTP(S) image URL for display or embedding.")
    local_path: str | None = Field(default=None, description="Optional local image path when assets are stored in the repo/POS.")
    source_url: str | None = Field(default=None, description="Human-reviewable source page for attribution.")
    source_name: str | None = Field(default=None, description="Source system or website name.")
    license: str | None = Field(default=None, description="Image license label when externally sourced.")
    license_url: str | None = Field(default=None, description="URL for the image license.")
    attribution: str | None = Field(default=None, description="Creator/owner attribution when required.")
    role: Literal["primary", "alternate", "detail", "reference"] = Field(default="primary")
    kind: Literal["product_photo", "supplier_photo", "reference_photo", "generated"] = Field(default="product_photo")
    is_reference: bool = Field(
        default=False,
        description="True when the image is a demo/reference image, not an actual SKU photo.",
    )
    visual_tags: list[str] = Field(default_factory=list, description="Color/category/material/pattern tags for visual fallback.")
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)

    @field_validator("image_id")
    @classmethod
    def validate_image_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("image_id must not be empty")
        return stripped

    @model_validator(mode="after")
    def validate_location(self) -> "InventoryImageAsset":
        if not self.url and not self.local_path:
            raise ValueError("InventoryImageAsset requires either url or local_path")
        return self


class InventoryItemRecord(BaseModel):
    product_id: str = Field(..., description="Stable product identifier from the inventory system.")
    sku: str = Field(..., description="Human-readable stock keeping unit.")
    name: str = Field(..., description="Primary product name.")
    category: str | None = Field(default=None, description="High-level product category.")
    brand: str | None = Field(default=None, description="Brand or manufacturer name.")
    short_description: str | None = Field(default=None, description="Short description for list views.")
    full_description: str | None = Field(default=None, description="Long-form description for retrieval.")
    price: float | None = Field(default=None, ge=0, description="Current unit price.")
    currency: str = Field(default="USD", description="Display currency.")
    stock: int = Field(default=0, ge=0, description="Current stock quantity.")
    status: str | None = Field(default=None, description="Operational stock status.")
    tags: list[str] = Field(default_factory=list, description="Free-form tags used for search and filtering.")
    attributes: dict[str, str] = Field(default_factory=dict, description="Structured product attributes.")
    images: list[InventoryImageAsset] = Field(default_factory=list, description="Product or reference images for visual search.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional opaque metadata from the inventory system.")
    include_in_rag: bool = Field(default=True, description="Whether the product should be indexed for semantic retrieval.")
    updated_at: str | None = Field(default=None, description="Last updated timestamp from the source system.")

    @field_validator("product_id", "sku", "name")
    @classmethod
    def validate_required_text_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Required inventory text fields must not be empty.")
        return stripped

    @field_validator("category", "brand", "short_description", "full_description", "status", "updated_at")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("currency must not be empty")
        return stripped.upper()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for tag in value:
            normalized = tag.strip()
            if not normalized:
                continue
            lowered = normalized.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(normalized)
        return deduped


class InventoryCatalogResponse(BaseModel):
    status: str
    total_items: int
    items: list[InventoryItemRecord] = Field(default_factory=list)


class InventoryStatusResponse(BaseModel):
    status: str
    ready: bool
    total_items: int
    rag_enabled_items: int
    vector_record_count: int
    namespace: str
    catalog_path: str
    vector_backend: str
    vector_store_path: str | None = None
    storage_backend: str | None = None
    storage_path: str | None = None


class InventorySyncIssue(BaseModel):
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    product_id: str | None = None


class InventoryProductionStatusResponse(BaseModel):
    status: str
    production_ready: bool
    storage_backend: str
    storage_path: str | None = None
    vector_backend: str
    vector_index_name: str | None = None
    vector_namespace: str | None = None
    vector_record_count: int | None = None
    issues: list[InventorySyncIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class InventorySyncStatusResponse(BaseModel):
    status: str
    ready: bool
    catalog_count: int
    rag_enabled_count: int
    vector_record_count: int
    vector_ids_available: bool
    vector_synced: bool | None = None
    missing_vector_ids: list[str] = Field(default_factory=list)
    stale_vector_ids: list[str] = Field(default_factory=list)
    invalid_catalog_product_ids: list[str] = Field(default_factory=list)
    issues: list[InventorySyncIssue] = Field(default_factory=list)


class InventorySyncValidateRequest(BaseModel):
    source_product_ids: list[str] = Field(
        default_factory=list,
        description="Product IDs from PostgreSQL/source of truth.",
    )
    source_items: list[InventoryItemRecord] = Field(
        default_factory=list,
        description="Optional full source items from PostgreSQL for deeper stale/data-quality validation.",
    )

    @field_validator("source_product_ids")
    @classmethod
    def normalize_source_product_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for product_id in value:
            stripped = product_id.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized


class InventorySyncValidateResponse(BaseModel):
    status: str
    valid: bool
    source_count: int
    catalog_count: int
    rag_enabled_count: int
    vector_record_count: int
    vector_ids_available: bool
    missing_in_catalog: list[str] = Field(default_factory=list)
    extra_in_catalog: list[str] = Field(default_factory=list)
    stale_catalog_product_ids: list[str] = Field(default_factory=list)
    missing_vector_ids: list[str] = Field(default_factory=list)
    stale_vector_ids: list[str] = Field(default_factory=list)
    invalid_catalog_product_ids: list[str] = Field(default_factory=list)
    issues: list[InventorySyncIssue] = Field(default_factory=list)


class InventorySyncRebuildResponse(BaseModel):
    status: str
    ready: bool
    rebuilt_count: int
    deleted_vector_count: int
    catalog_count: int
    rag_enabled_count: int
    vector_record_count: int
    vector_ids_available: bool
    vector_synced: bool | None = None
    missing_vector_ids: list[str] = Field(default_factory=list)
    stale_vector_ids: list[str] = Field(default_factory=list)
    invalid_catalog_product_ids: list[str] = Field(default_factory=list)
    issues: list[InventorySyncIssue] = Field(default_factory=list)
    namespace: str
    catalog_path: str


class InventoryBusinessSignalRecord(BaseModel):
    product_id: str = Field(..., description="Stable product identifier from PostgreSQL/source of truth.")
    period_start: str | None = Field(default=None, description="Start of the metric window.")
    period_end: str | None = Field(default=None, description="End of the metric window.")
    units_sold: int | None = Field(default=None, ge=0)
    revenue: float | None = Field(default=None, ge=0)
    order_count: int | None = Field(default=None, ge=0)
    return_count: int | None = Field(default=None, ge=0)
    return_rate: float | None = Field(default=None, ge=0, le=1)
    gross_margin: float | None = None
    gross_margin_rate: float | None = Field(default=None, ge=-1, le=1)
    inventory_on_hand: int | None = Field(default=None, ge=0)
    inventory_snapshot_at: str | None = None
    supplier_id: str | None = None
    supplier_name: str | None = None
    supplier_lead_time_days: int | None = Field(default=None, ge=0)
    supplier_risk_score: float | None = Field(default=None, ge=0, le=1)
    customer_segments: list[str] = Field(default_factory=list)
    demand_score: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_business_product_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("product_id must not be empty")
        return stripped

    @field_validator(
        "period_start",
        "period_end",
        "inventory_snapshot_at",
        "supplier_id",
        "supplier_name",
        "updated_at",
    )
    @classmethod
    def normalize_business_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("customer_segments")
    @classmethod
    def normalize_customer_segments(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for segment in value:
            stripped = segment.strip()
            if not stripped:
                continue
            lowered = stripped.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(stripped)
        return normalized


class InventoryBusinessSignalsUpsertRequest(BaseModel):
    signals: list[InventoryBusinessSignalRecord] = Field(default_factory=list, min_length=1)


class InventoryBusinessSignalsUpsertResponse(BaseModel):
    status: str
    upserted_count: int
    total_signals: int
    product_count: int
    business_signal_path: str


class InventoryBusinessSignalsResponse(BaseModel):
    status: str
    total_signals: int
    signals: list[InventoryBusinessSignalRecord] = Field(default_factory=list)


class InventoryBusinessSignalsDeleteResponse(BaseModel):
    status: str
    deleted_count: int
    total_signals: int
    product_count: int
    business_signal_path: str


class InventoryBusinessStatusResponse(BaseModel):
    status: str
    ready: bool
    total_signals: int
    product_count: int
    domains_available: list[str] = Field(default_factory=list)
    latest_updated_at: str | None = None
    business_signal_path: str


class InventoryUpsertRequest(BaseModel):
    items: list[InventoryItemRecord] = Field(default_factory=list, min_length=1)


class InventoryUpsertResponse(BaseModel):
    status: str
    upserted_count: int
    rag_enabled_count: int
    total_items: int
    namespace: str
    catalog_path: str


class InventoryDeleteRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list, min_length=1)

    @field_validator("product_ids")
    @classmethod
    def normalize_product_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for product_id in value:
            stripped = product_id.strip()
            if not stripped:
                continue
            if stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        if not normalized:
            raise ValueError("At least one product_id is required.")
        return normalized


class InventoryDeleteResponse(BaseModel):
    status: str
    deleted_count: int
    total_items: int
    namespace: str
    catalog_path: str


class InventorySearchFilters(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    min_stock: int | None = Field(default=None, ge=0)
    max_stock: int | None = Field(default=None, ge=0)
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    rag_only: bool = Field(default=True, description="Restrict results to products that are indexed for semantic retrieval.")

    @field_validator("product_ids", "categories", "brands", "statuses", "tags")
    @classmethod
    def normalize_string_lists(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            stripped = item.strip()
            if not stripped:
                continue
            lowered = stripped.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(stripped)
        return normalized

    @model_validator(mode="after")
    def validate_ranges(self) -> "InventorySearchFilters":
        if self.min_stock is not None and self.max_stock is not None and self.min_stock > self.max_stock:
            raise ValueError("min_stock must be less than or equal to max_stock")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be less than or equal to max_price")
        return self


class InventorySearchRequest(BaseModel):
    query_text: str | None = Field(default=None, description="Semantic query over indexed inventory items.")
    top_k: int = Field(default=5, ge=1, le=50)
    filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)


class InventorySearchHit(BaseModel):
    product_id: str
    sku: str
    name: str
    category: str | None = None
    brand: str | None = None
    status: str | None = None
    price: float | None = None
    currency: str | None = None
    stock: int | None = None
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    snippet: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_scores: dict[str, Any] = Field(
        default_factory=dict,
        description="Debug-friendly ecommerce reranking score components.",
    )
    score: float


class InventorySearchResponse(BaseModel):
    status: str
    query_text: str | None = None
    total_hits: int
    applied_filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    hits: list[InventorySearchHit] = Field(default_factory=list)


class InventoryFactProvenance(BaseModel):
    source_type: Literal["catalog", "business_signal", "reranker", "inferred"]
    source_field: str
    source_updated_at: str | None = None
    note: str | None = None


class InventoryFact(BaseModel):
    key: str
    value: Any | None = None
    status: Literal["present", "missing", "conflicting", "inferred"] = "present"
    unit: str | None = None
    provenance: list[InventoryFactProvenance] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InventoryProductEvidence(BaseModel):
    product_id: str
    sku: str
    name: str
    category: str | None = None
    brand: str | None = None
    currency: str | None = None
    price: float | None = None
    stock: int | None = None
    tags: list[str] = Field(default_factory=list)
    snippet: str | None = None
    role: Literal["primary", "alternative", "cross_sell", "rejected", "candidate"] = "candidate"
    score: float | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    inclusion_reasons: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    facts: list[InventoryFact] = Field(default_factory=list)
    allowed_claims: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)


class InventoryEvidenceContract(BaseModel):
    question: str | None = None
    primary_product_id: str | None = None
    primary_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    candidate_evidence: list[InventoryProductEvidence] = Field(default_factory=list)
    required_tradeoffs: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    allowed_claims: list[str] = Field(default_factory=list)
    follow_up_question_rules: list[str] = Field(default_factory=list)


class InventoryAnswerPlan(BaseModel):
    intent: str = "unknown"
    detected_intent: str | None = None
    intent_confidence: float | None = Field(default=None, ge=0, le=1)
    intent_reasons: list[str] = Field(default_factory=list)
    strategy: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    product_type: str | None = None
    product_family: str | None = None
    primary_product_id: str | None = None
    alternative_product_ids: list[str] = Field(default_factory=list)
    cross_sell_product_ids: list[str] = Field(default_factory=list)
    excluded_product_ids: list[str] = Field(default_factory=list)
    primary_reason: str | None = None
    alternative_reason: str | None = None
    cross_sell_reason: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    next_best_question: str | None = None
    confidence_breakdown: dict[str, Any] = Field(default_factory=dict)
    reasoning_steps: list[str] = Field(default_factory=list)
    metadata_used: list[str] = Field(default_factory=list)
    evidence_contract: InventoryEvidenceContract | None = None
    abstain: bool = False
    abstention_reason: str | None = None


class InventoryAnswerVerification(BaseModel):
    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    hard_constraint_issues: list[str] = Field(default_factory=list)
    requires_abstention: bool = False
    checked_final_answer: bool = False
    final_answer_issues: list[str] = Field(default_factory=list)


class InventoryConversationTurn(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"user", "assistant"}:
            raise ValueError("role must be either 'user' or 'assistant'")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty")
        return stripped


class InventoryMemoryResolution(BaseModel):
    used_memory: bool = False
    reason: str | None = None
    resolved_product_ids: list[str] = Field(default_factory=list)
    applied_context_filters: bool = False
    ignored_memory_reason: str | None = None


class InventoryAskRequest(BaseModel):
    question: str = Field(..., description="Natural-language inventory question.")
    top_k: int = Field(default=5, ge=1, le=50)
    filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    low_stock_threshold: int = Field(default=10, ge=0, le=10000)
    assistant_mode: str = Field(
        default="support",
        description="Assistant tone for the answer. Use 'sales' for recommendation-style replies.",
    )
    reply_style: str = Field(
        default="short",
        description="Response length and detail level. Use 'detailed' for longer guidance with reasoning and follow-up.",
    )
    answer_engine: str = Field(
        default="auto",
        description="Answer generation strategy. Use 'natural' for grounded LLM synthesis, 'deterministic' for rule-based replies, or 'auto' to let the service choose.",
    )
    conversation_history: list[InventoryConversationTurn] = Field(default_factory=list)
    conversation_summary: str | None = Field(
        default=None,
        description="Optional server-built summary of the recent chat state so follow-up answers remain grounded.",
    )
    focused_product_ids: list[str] = Field(
        default_factory=list,
        description="Product IDs from the current UI/chat focus. Used only for clear follow-up references like 'it' or 'the first one'.",
    )
    active_filters: InventorySearchFilters | None = Field(
        default=None,
        description="Optional filters from the current chat/search context. Current request filters override these.",
    )
    last_answer_plan: InventoryAnswerPlan | None = Field(
        default=None,
        description="Previous answer plan from the main backend. Used for safe reference resolution only.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional browser/client session ID. Used to load saved customer preferences (budget, colours, sizes) as context.",
    )
    debug_retrieval_probe: bool = Field(
        default=False,
        description=(
            "Debug/observer mode only. When true, structured inventory answers also run "
            "a sidecar retrieval probe so traces show vector/BM25 backend activity."
        ),
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped

    @field_validator("assistant_mode")
    @classmethod
    def validate_assistant_mode(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"support", "sales"}:
            raise ValueError("assistant_mode must be either 'support' or 'sales'")
        return normalized

    @field_validator("reply_style")
    @classmethod
    def validate_reply_style(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"short", "detailed"}:
            raise ValueError("reply_style must be either 'short' or 'detailed'")
        return normalized

    @field_validator("answer_engine")
    @classmethod
    def validate_answer_engine(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"auto", "deterministic", "natural"}:
            raise ValueError("answer_engine must be one of: auto, deterministic, natural")
        return normalized

    @field_validator("conversation_summary")
    @classmethod
    def normalize_conversation_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("focused_product_ids")
    @classmethod
    def normalize_focused_product_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for product_id in value:
            stripped = product_id.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized


class InventoryAskResponse(BaseModel):
    status: str
    question: str
    answer: str
    assistant_mode: str
    reply_style: str
    answer_engine: str
    confidence_score: float
    trace_id: str
    abstained: bool = False
    abstention_reason: str | None = None
    total_hits: int
    applied_filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    hits: list[InventorySearchHit] = Field(default_factory=list)
    recommended_product_ids: list[str] = Field(default_factory=list)
    cross_sell_product_ids: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    answer_plan: InventoryAnswerPlan = Field(default_factory=InventoryAnswerPlan)
    verification: InventoryAnswerVerification = Field(default_factory=InventoryAnswerVerification)
    memory_resolution: InventoryMemoryResolution = Field(default_factory=InventoryMemoryResolution)


class InventoryQuestionFamilyContract(BaseModel):
    family: str
    supported: bool = True
    description: str
    classifier_intents: list[str] = Field(default_factory=list)
    default_execution_path: Literal["normal_rag", "agentic", "clarify_or_abstain"]
    supported_execution_paths: list[str] = Field(default_factory=list)
    reasoning_mode: Literal[
        "deterministic",
        "deterministic_with_optional_agentic",
        "bounded_agentic",
        "abstain_or_clarify",
    ]
    external_data_required: bool = False
    canonical_eval_case_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InventoryAbstainTriggerContract(BaseModel):
    trigger_id: str
    description: str
    stage: Literal["routing", "retrieval", "planning", "verification"]
    applies_to_families: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class InventoryCanonicalEvalContractCase(BaseModel):
    case_id: str
    family: str
    example_question: str
    purpose: str
    expected_execution_path: str


class InventoryPolicyContractResponse(BaseModel):
    status: str
    version: str
    summary: str
    supported_question_families: list[InventoryQuestionFamilyContract] = Field(default_factory=list)
    hard_abstain_triggers: list[InventoryAbstainTriggerContract] = Field(default_factory=list)
    canonical_eval_cases: list[InventoryCanonicalEvalContractCase] = Field(default_factory=list)
    canonical_eval_case_ids: list[str] = Field(default_factory=list)


class InventoryRouteRequest(BaseModel):
    question: str = Field(..., description="Inventory chat question to route between normal RAG and agentic handling.")
    assistant_mode: str = Field(default="support", description="Intended assistant tone for the eventual answer.")
    reply_style: str = Field(default="short", description="Desired reply detail level for the eventual answer.")
    filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    audience: str = Field(
        default="customer",
        description="Primary user context. Use 'manager' or 'operator' for deeper internal workflows.",
    )
    prefer_fast_response: bool = Field(
        default=True,
        description="Bias routing toward faster normal RAG when the question is still answerable from the catalog mirror.",
    )
    allow_agentic: bool = Field(
        default=True,
        description="Whether the caller is willing to escalate this question into a slower agentic workflow.",
    )
    available_data_domains: list[str] = Field(
        default_factory=lambda: ["catalog"],
        description="Data domains currently available to an agentic backend, such as catalog, inventory_snapshots, sales, orders, suppliers, or customers.",
    )

    @field_validator("question")
    @classmethod
    def validate_route_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped

    @field_validator("assistant_mode")
    @classmethod
    def validate_route_assistant_mode(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"support", "sales"}:
            raise ValueError("assistant_mode must be either 'support' or 'sales'")
        return normalized

    @field_validator("reply_style")
    @classmethod
    def validate_route_reply_style(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"short", "detailed"}:
            raise ValueError("reply_style must be either 'short' or 'detailed'")
        return normalized

    @field_validator("audience")
    @classmethod
    def validate_audience(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"customer", "staff", "manager", "operator"}:
            raise ValueError("audience must be one of: customer, staff, manager, operator")
        return normalized

    @field_validator("available_data_domains")
    @classmethod
    def normalize_available_data_domains(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            stripped = item.strip().casefold()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized or ["catalog"]


class InventoryRouteSignals(BaseModel):
    detected_intent: str = "unknown"
    intent_confidence: float | None = Field(default=None, ge=0, le=1)
    intent_reasons: list[str] = Field(default_factory=list)
    question_family: str = "unknown"
    family_confidence: float | None = Field(default=None, ge=0, le=1)
    family_reasons: list[str] = Field(default_factory=list)
    is_small_talk: bool = False
    has_explicit_product_reference: bool = False
    simple_catalog_lookup: bool = False
    needs_historical_data: bool = False
    needs_cross_system_data: bool = False
    needs_root_cause_reasoning: bool = False
    needs_workflow_action: bool = False
    needs_multi_step_reasoning: bool = False


class InventoryExecutionContract(BaseModel):
    mode: str
    implementation_status: str
    target_system: str
    method: str
    endpoint: str
    purpose: str
    payload_template: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class InventoryRouteResponse(BaseModel):
    status: str
    question: str
    policy_version: str | None = None
    recommended_path: str
    fallback_path: str
    decision_confidence: float
    reason_summary: str
    decision_factors: list[str] = Field(default_factory=list)
    required_data_domains: list[str] = Field(default_factory=list)
    missing_data_domains: list[str] = Field(default_factory=list)
    signals: InventoryRouteSignals = Field(default_factory=InventoryRouteSignals)
    family_contract: InventoryQuestionFamilyContract | None = None
    applicable_hard_abstain_triggers: list[InventoryAbstainTriggerContract] = Field(default_factory=list)
    normal_rag_contract: InventoryExecutionContract
    agentic_contract: InventoryExecutionContract


class InventoryAgenticRequest(BaseModel):
    question: str = Field(..., description="Inventory question that may require multi-step retrieval and reasoning.")
    top_k: int = Field(default=5, ge=1, le=50)
    filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    low_stock_threshold: int = Field(default=10, ge=0, le=10000)
    assistant_mode: str = Field(default="support")
    reply_style: str = Field(default="short")
    answer_engine: str = Field(default="auto")
    conversation_history: list[InventoryConversationTurn] = Field(default_factory=list)
    conversation_summary: str | None = None
    focused_product_ids: list[str] = Field(default_factory=list)
    active_filters: InventorySearchFilters | None = None
    last_answer_plan: InventoryAnswerPlan | None = None
    max_reasoning_steps: int = Field(default=4, ge=1, le=8)
    audience: str = Field(default="customer")
    available_data_domains: list[str] = Field(default_factory=lambda: ["catalog"])

    @field_validator("question")
    @classmethod
    def validate_agentic_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped

    @field_validator("assistant_mode")
    @classmethod
    def validate_agentic_assistant_mode(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"support", "sales"}:
            raise ValueError("assistant_mode must be either 'support' or 'sales'")
        return normalized

    @field_validator("reply_style")
    @classmethod
    def validate_agentic_reply_style(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"short", "detailed"}:
            raise ValueError("reply_style must be either 'short' or 'detailed'")
        return normalized

    @field_validator("answer_engine")
    @classmethod
    def validate_agentic_answer_engine(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"auto", "deterministic", "natural"}:
            raise ValueError("answer_engine must be one of: auto, deterministic, natural")
        return normalized

    @field_validator("audience")
    @classmethod
    def validate_agentic_audience(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"customer", "staff", "manager", "operator"}:
            raise ValueError("audience must be one of: customer, staff, manager, operator")
        return normalized

    @field_validator("conversation_summary")
    @classmethod
    def normalize_agentic_conversation_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("focused_product_ids")
    @classmethod
    def normalize_agentic_focused_product_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for product_id in value:
            stripped = product_id.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized

    @field_validator("available_data_domains")
    @classmethod
    def normalize_agentic_available_domains(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            stripped = item.strip().casefold()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized or ["catalog"]


class InventoryTraceCandidateDebug(BaseModel):
    product_id: str
    name: str
    category: str | None = None
    score: float | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)


class InventoryAgenticStep(BaseModel):
    step_number: int
    action: str
    query_text: str | None = None
    applied_filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    total_hits: int = 0
    selected_product_ids: list[str] = Field(default_factory=list)
    selected_candidates: list[InventoryTraceCandidateDebug] = Field(default_factory=list)
    rejected_candidates: list[InventoryTraceCandidateDebug] = Field(default_factory=list)
    observation: str
    retrieval_stage_counts: dict[str, int] = Field(default_factory=dict)


class InventoryAgenticStatusResponse(BaseModel):
    status: str
    ready: bool
    total_items: int
    rag_enabled_items: int
    vector_record_count: int
    namespace: str
    trace_dir: str
    vector_backend: str
    vector_store_path: str | None = None


class InventoryAgenticResponse(BaseModel):
    status: str
    question: str
    answer: str
    assistant_mode: str
    reply_style: str
    answer_engine: str
    execution_path: str
    confidence_score: float
    abstained: bool = False
    abstention_reason: str | None = None
    trace_id: str
    reasoning_summary: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    retrieval_steps_used: int = 0
    total_hits: int
    applied_filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    hits: list[InventorySearchHit] = Field(default_factory=list)
    recommended_product_ids: list[str] = Field(default_factory=list)
    cross_sell_product_ids: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    answer_plan: InventoryAnswerPlan = Field(default_factory=InventoryAnswerPlan)
    verification: InventoryAnswerVerification = Field(default_factory=InventoryAnswerVerification)
    memory_resolution: InventoryMemoryResolution = Field(default_factory=InventoryMemoryResolution)


class InventoryAgenticTraceResponse(BaseModel):
    trace_id: str
    question: str
    assistant_mode: str
    reply_style: str
    execution_path: str
    route_decision: dict[str, Any] = Field(default_factory=dict)
    retrieval_stage_counts: dict[str, int] = Field(default_factory=dict)
    reasoning_summary: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    retrieval_steps: list[InventoryAgenticStep] = Field(default_factory=list)
    final_answer: str
    confidence_score: float


class InventoryChatTraceResponse(BaseModel):
    trace_id: str
    request_id: str
    created_at: str
    question: str
    assistant_mode: str
    reply_style: str
    answer_engine: str
    execution_path: str
    latency_ms: float
    fallback_reason: str | None = None
    intent: str | None = None
    route_decision: dict[str, Any] = Field(default_factory=dict)
    retrieval_stage_counts: dict[str, int] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    retrieved_product_ids: list[str] = Field(default_factory=list)
    reranked_product_ids: list[str] = Field(default_factory=list)
    recommended_product_ids: list[str] = Field(default_factory=list)
    cross_sell_product_ids: list[str] = Field(default_factory=list)
    total_hits: int = 0
    confidence_score: float
    abstained: bool = False
    abstention_reason: str | None = None
    applied_filters: InventorySearchFilters = Field(default_factory=InventorySearchFilters)
    answer_plan: InventoryAnswerPlan = Field(default_factory=InventoryAnswerPlan)
    verification: InventoryAnswerVerification = Field(default_factory=InventoryAnswerVerification)
    memory_resolution: InventoryMemoryResolution = Field(default_factory=InventoryMemoryResolution)
    reasoning_summary: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    retrieval_steps: list[InventoryAgenticStep] = Field(default_factory=list)
    final_answer: str


# ---------------------------------------------------------------------------
# Order workflow schemas
# ---------------------------------------------------------------------------

class OrderItemSchema(BaseModel):
    product_id: str
    sku: str
    name: str
    quantity: int = Field(default=1, ge=1)
    unit_price: float
    currency: str = "BDT"
    line_total: float = 0.0


class OrderDraftRequest(BaseModel):
    session_id: str
    product_id: str
    sku: str
    name: str
    unit_price: float
    quantity: int = Field(default=1, ge=1)
    currency: str = "BDT"


class OrderUpdateRequest(BaseModel):
    session_id: str
    customer_name: str | None = None
    customer_phone: str | None = None
    delivery_area: str | None = None
    payment_method: str | None = None
    notes: str | None = None


class OrderConfirmRequest(BaseModel):
    session_id: str
    order_id: str


class OrderResponse(BaseModel):
    status: str
    order_id: str | None = None
    message: str
    items: list[OrderItemSchema] = Field(default_factory=list)
    subtotal: float = 0.0
    delivery_charge: float = 0.0
    grand_total: float = 0.0
    customer_name: str | None = None
    customer_phone: str | None = None
    delivery_area: str | None = None
    payment_method: str | None = None
    order_status: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    ready_to_confirm: bool = False


# ---------------------------------------------------------------------------
# Image search schemas
# ---------------------------------------------------------------------------

class ImageSearchRequest(BaseModel):
    query_text: str = ""
    image_b64: str | None = None
    category_hint: str | None = None
    color_hint: str | None = None
    budget_max: float | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class ImageSearchHit(BaseModel):
    product_id: str
    name: str
    score: float
    match_type: str
    reasons: list[str] = Field(default_factory=list)
    price: float | None = None
    currency: str = "BDT"
    stock: int = 0
    image_url: str | None = None


class ImageSearchResponse(BaseModel):
    status: str
    answer: str
    hits: list[ImageSearchHit] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# POS sync schemas
# ---------------------------------------------------------------------------

class POSSyncImportRequest(BaseModel):
    csv_text: str = Field(..., description="Raw CSV content as text.")
    source: str = "manual_upload"


class POSSyncWebhookRequest(BaseModel):
    source: str = "pos"
    event: str = "stock_updated"
    items: list[dict[str, Any]] = Field(default_factory=list)


class POSSyncResponse(BaseModel):
    status: str
    inserted: int = 0
    updated: int = 0
    stock_changed: int = 0
    deactivated: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    summary: str = ""
    timestamp: str = ""


class POSSyncStatusResponse(BaseModel):
    status: str
    total_products: int = 0
    active_products: int = 0
    out_of_stock: int = 0
    last_sync: str = "never"


# ---------------------------------------------------------------------------
# Customer profile schemas
# ---------------------------------------------------------------------------

class CustomerProfileResponse(BaseModel):
    status: str
    session_id: str
    profile_summary: str
    preferred_language: str | None = None
    sizes: dict[str, str] = Field(default_factory=dict)
    favorite_colors: list[str] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_categories: list[str] = Field(default_factory=list)
    skin_type: str | None = None
    delivery_area: str | None = None


# ---------------------------------------------------------------------------
# Policy QA schemas
# ---------------------------------------------------------------------------

class PolicyQARequest(BaseModel):
    question: str


class PolicyQAResponse(BaseModel):
    status: str
    answer: str
    source: str = "policies.json"
