from __future__ import annotations

from pydantic import BaseModel, Field


class BanglaTaxIngestPathRequest(BaseModel):
    source_path: str = Field(..., description="Local path to a Bangla PDF.")
    document_id: str | None = Field(default=None, description="Stable document id for this legal corpus item.")
    act_title: str | None = Field(default=None, description="Human-readable legal document title.")
    ocr_enabled: bool | None = Field(default=None, description="Run OCRmyPDF before parsing.")
    ocr_language: str = Field(default="ben+eng", description="OCR language passed to OCRmyPDF.")
    ocr_force: bool = Field(default=True, description="Force OCR instead of skipping pages with text.")


class BanglaTaxUploadResponse(BaseModel):
    status: str
    document_id: str
    act_title: str
    parser_provider: str
    source_path: str
    graph_path: str
    bm25_index_dir: str
    retrieval_chunk_count: int
    reasoning_chunk_count: int
    vector_record_count: int
    ocr_applied: bool = False
    ocr_output_pdf_path: str | None = None
    message: str
