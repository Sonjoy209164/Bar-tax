from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class IngestRequest(BaseModel):
    document_id: str = Field(..., description="Unique document identifier.")
    source_path: str = Field(..., description="Path to the raw input document.")
    chunk_size: int = Field(default=500, ge=100, le=5000)


class IngestResponse(BaseModel):
    status: str
    document_id: str
    chunk_count: int
    message: str


class QueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedChunk(BaseModel):
    chunk_id: str
    content: str
    score: float


class QueryResponse(BaseModel):
    status: str
    answer: str
    citations: list[str]
    retrieved_chunks: list[RetrievedChunk]


class EvalRequest(BaseModel):
    predictions: list[str]
    references: list[str]


class EvalResponse(BaseModel):
    status: str
    metric_name: str
    score: float
    details: dict[str, Any]
