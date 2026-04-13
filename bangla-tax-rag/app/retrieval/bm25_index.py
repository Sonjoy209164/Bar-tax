from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from rank_bm25 import BM25Okapi

from app.core.utils import detect_query_type, extract_query_section_references, normalize_text, tokenize_for_bm25
from app.domain.query_taxonomy import QueryType, canonicalize_query_type
from app.ingestion.chunker import ChunkingArtifacts, LegalChunk

DEFAULT_BM25_INDEX_NAME = "legal_bm25"
DEFAULT_BM25_FIELDS = ("body", "heading", "structure")
SECTION_HEADING_PATTERN_TEMPLATE = r"(^|\b)section\s+{section}\b"
LIST_MARKER_PATTERN = re.compile(r"^\(([a-z0-9]+)\)\s+", re.IGNORECASE)


class BM25IndexConfig(BaseModel):
    index_name: str = DEFAULT_BM25_INDEX_NAME
    k1: float = Field(default=1.5, gt=0)
    b: float = Field(default=0.75, ge=0, le=1)
    fields: tuple[str, str, str] = DEFAULT_BM25_FIELDS


class BM25SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1)
    query_type: QueryType | None = None
    section_reference: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_inferred_fields(self) -> "BM25SearchRequest":
        if self.query_type is None:
            self.query_type = canonicalize_query_type(detect_query_type(self.query))
        if self.section_reference is None:
            section_references = extract_query_section_references(self.query)
            self.section_reference = section_references[0] if section_references else None
        return self


class BM25SearchMatch(BaseModel):
    chunk: LegalChunk
    score: float
    rank: int
    matched_terms: list[str] = Field(default_factory=list)
    field_scores: dict[str, float] = Field(default_factory=dict)


class BM25SearchResult(BaseModel):
    query: str
    normalized_query: str
    query_type: QueryType
    section_reference: str | None = None
    top_k: int
    field_weights: dict[str, float] = Field(default_factory=dict)
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    matches: list[BM25SearchMatch] = Field(default_factory=list)


class BM25IndexStats(BaseModel):
    index_name: str
    chunk_count: int
    average_token_count: float
    fields: tuple[str, str, str] = DEFAULT_BM25_FIELDS
    chunk_scope: str = "retrieval_child"


@dataclass
class BM25Index:
    config: BM25IndexConfig
    chunks: list[LegalChunk]
    body_texts: list[str]
    heading_texts: list[str]
    structure_texts: list[str]
    body_bm25: BM25Okapi
    heading_bm25: BM25Okapi
    structure_bm25: BM25Okapi

    def search(self, request: BM25SearchRequest) -> BM25SearchResult:
        normalized_query = normalize_text(request.query)
        query_type = canonicalize_query_type(request.query_type)
        query_tokens = _tokenize_bm25_field(normalized_query)
        field_weights = _field_score_weights(query_type, section_reference=request.section_reference)

        body_scores = self.body_bm25.get_scores(query_tokens).tolist()
        heading_scores = self.heading_bm25.get_scores(query_tokens).tolist()
        structure_scores = self.structure_bm25.get_scores(query_tokens).tolist()

        normalized_body_scores = _normalize_field_scores(body_scores)
        normalized_heading_scores = _normalize_field_scores(heading_scores)
        normalized_structure_scores = _normalize_field_scores(structure_scores)

        matches: list[BM25SearchMatch] = []
        query_terms = set(tokenize_for_bm25(normalized_query))
        for position, chunk in enumerate(self.chunks):
            if not _chunk_matches_filters(chunk, request.filters):
                continue

            base_score = 12.0 * (
                (normalized_body_scores[position] * field_weights["body"])
                + (normalized_heading_scores[position] * field_weights["heading"])
                + (normalized_structure_scores[position] * field_weights["structure"])
            )
            final_score = _apply_section_and_type_boosts(
                chunk,
                query_type=query_type,
                section_reference=request.section_reference,
                base_score=float(base_score),
                query_terms=query_terms,
            )
            if final_score <= 0:
                continue

            chunk_terms = set(tokenize_for_bm25(_build_searchable_text(chunk)))
            matched_terms = sorted(term for term in query_terms if term in chunk_terms)
            matches.append(
                BM25SearchMatch(
                    chunk=chunk,
                    score=round(final_score, 6),
                    rank=0,
                    matched_terms=matched_terms,
                    field_scores={
                        "body": round(body_scores[position], 6),
                        "heading": round(heading_scores[position], 6),
                        "structure": round(structure_scores[position], 6),
                    },
                )
            )

        ranked_matches = sorted(matches, key=lambda match: match.score, reverse=True)[: request.top_k]
        for rank, match in enumerate(ranked_matches, start=1):
            match.rank = rank
        return BM25SearchResult(
            query=request.query,
            normalized_query=normalized_query,
            query_type=query_type,
            section_reference=request.section_reference,
            top_k=request.top_k,
            field_weights=field_weights,
            applied_filters=request.filters,
            matches=ranked_matches,
        )

    def describe(self) -> BM25IndexStats:
        average_token_count = (
            sum(chunk.token_count for chunk in self.chunks) / len(self.chunks) if self.chunks else 0.0
        )
        return BM25IndexStats(
            index_name=self.config.index_name,
            chunk_count=len(self.chunks),
            average_token_count=round(average_token_count, 4),
            fields=self.config.fields,
        )


def build_bm25_index(
    chunks_or_artifacts: list[LegalChunk] | ChunkingArtifacts,
    *,
    config: BM25IndexConfig | None = None,
) -> BM25Index:
    resolved_config = config or BM25IndexConfig()
    chunks = _resolve_retrieval_chunks(chunks_or_artifacts)
    body_texts = [_build_body_text(chunk) for chunk in chunks]
    heading_texts = [_build_heading_text(chunk) for chunk in chunks]
    structure_texts = [_build_structure_text(chunk) for chunk in chunks]
    return BM25Index(
        config=resolved_config,
        chunks=chunks,
        body_texts=body_texts,
        heading_texts=heading_texts,
        structure_texts=structure_texts,
        body_bm25=BM25Okapi([_tokenize_bm25_field(text) for text in body_texts], k1=resolved_config.k1, b=resolved_config.b),
        heading_bm25=BM25Okapi(
            [_tokenize_bm25_field(text) for text in heading_texts],
            k1=resolved_config.k1,
            b=resolved_config.b,
        ),
        structure_bm25=BM25Okapi(
            [_tokenize_bm25_field(text) for text in structure_texts],
            k1=resolved_config.k1,
            b=resolved_config.b,
        ),
    )


def save_bm25_index(index: BM25Index, output_dir: str | Path) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    chunks_path = output_path / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in index.chunks:
            handle.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) + "\n")

    metadata_path = output_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "index_name": index.config.index_name,
                "index_type": "field_aware_bm25",
                "k1": index.config.k1,
                "b": index.config.b,
                "fields": list(index.config.fields),
                "chunk_count": len(index.chunks),
                "chunk_scope": "retrieval_child",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


def load_bm25_index(index_dir: str | Path, *, config: BM25IndexConfig | None = None) -> BM25Index:
    input_dir = Path(index_dir)
    chunks: list[LegalChunk] = []
    with (input_dir / "chunks.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            chunks.append(LegalChunk.model_validate_json(stripped))

    resolved_config = config or _load_config_from_metadata(input_dir / "metadata.json")
    return build_bm25_index(chunks, config=resolved_config)


def _load_config_from_metadata(metadata_path: Path) -> BM25IndexConfig:
    if not metadata_path.exists():
        return BM25IndexConfig()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    return BM25IndexConfig(
        index_name=payload.get("index_name", DEFAULT_BM25_INDEX_NAME),
        k1=payload.get("k1", 1.5),
        b=payload.get("b", 0.75),
        fields=tuple(payload.get("fields", list(DEFAULT_BM25_FIELDS))),
    )


def _resolve_retrieval_chunks(chunks_or_artifacts: list[LegalChunk] | ChunkingArtifacts) -> list[LegalChunk]:
    if isinstance(chunks_or_artifacts, ChunkingArtifacts):
        candidate_chunks = chunks_or_artifacts.retrieval_chunks
    else:
        candidate_chunks = chunks_or_artifacts
    return [chunk for chunk in candidate_chunks if chunk.chunk_scope == "retrieval_child"]


def _build_body_text(chunk: LegalChunk) -> str:
    return chunk.normalized_text


def _build_heading_text(chunk: LegalChunk) -> str:
    return " ".join(
        part
        for part in [
            chunk.citability_label,
            chunk.label,
            chunk.title,
            chunk.metadata.get("heading_text"),
        ]
        if isinstance(part, str) and part.strip()
    )


def _build_structure_text(chunk: LegalChunk) -> str:
    parts = [
        chunk.act_title,
        chunk.chunk_scope,
        chunk.chunk_type,
        chunk.source_node_type.value,
        chunk.part_number,
        chunk.part_title,
        chunk.chapter_number,
        chunk.chapter_title,
        chunk.section_number,
        f"section {chunk.section_number}" if chunk.section_number else None,
        chunk.subsection_number,
        f"subsection {chunk.subsection_number}" if chunk.subsection_number else None,
        chunk.clause_number,
        f"clause {chunk.clause_number}" if chunk.clause_number else None,
        chunk.metadata.get("governing_rule_id"),
        chunk.metadata.get("reasoning_root_id"),
    ]
    return " ".join(str(part).strip() for part in parts if part is not None and str(part).strip())


def _build_searchable_text(chunk: LegalChunk) -> str:
    return " ".join([_build_heading_text(chunk), _build_structure_text(chunk), _build_body_text(chunk)]).strip()


def _tokenize_bm25_field(text: str) -> list[str]:
    tokens = tokenize_for_bm25(text)
    return tokens if tokens else ["__empty__"]


def _normalize_field_scores(scores: list[float]) -> list[float]:
    positive_scores = [score for score in scores if score > 0]
    if not positive_scores:
        return [0.0 for _ in scores]
    ceiling = max(positive_scores)
    if ceiling <= 0:
        return [0.0 for _ in scores]
    return [score / ceiling if score > 0 else 0.0 for score in scores]


def _field_score_weights(query_type: QueryType, *, section_reference: str | None = None) -> dict[str, float]:
    if query_type is QueryType.DEFINITION:
        return {"body": 0.4, "heading": 0.35, "structure": 0.25}
    if query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP, QueryType.AMOUNT_LOOKUP, QueryType.DATE_LOOKUP, QueryType.DURATION_LOOKUP}:
        return {"body": 0.58, "heading": 0.14, "structure": 0.28}
    if query_type in {QueryType.COUNT_LOOKUP, QueryType.LIST_LOOKUP}:
        return {"body": 0.38, "heading": 0.24, "structure": 0.38}
    if query_type in {QueryType.COMPARISON, QueryType.SCENARIO_REASONING, QueryType.CROSS_SECTION_REASONING, QueryType.ELIGIBILITY}:
        return {"body": 0.46, "heading": 0.18, "structure": 0.36}
    if section_reference:
        return {"body": 0.34, "heading": 0.24, "structure": 0.42}
    if query_type is QueryType.MENTION_LOOKUP:
        return {"body": 0.62, "heading": 0.24, "structure": 0.14}
    return {"body": 0.5, "heading": 0.22, "structure": 0.28}


def _apply_section_and_type_boosts(
    chunk: LegalChunk,
    *,
    query_type: QueryType,
    section_reference: str | None,
    base_score: float,
    query_terms: set[str],
) -> float:
    score = base_score
    searchable_text = _build_searchable_text(chunk).lower()
    if section_reference:
        exact_heading_pattern = re.compile(
            SECTION_HEADING_PATTERN_TEMPLATE.format(section=re.escape(section_reference)),
            re.IGNORECASE,
        )
        has_exact_heading_match = bool(exact_heading_pattern.search(searchable_text))
        if chunk.section_number == section_reference:
            score += 3.2
            if has_exact_heading_match:
                score += 1.6
        elif chunk.subsection_number == section_reference:
            score += 2.1
        elif query_type is QueryType.SECTION_LOOKUP:
            score -= 1.6

        if chunk.chunk_variant == "anchor" and chunk.section_number == section_reference:
            score += 2.2

    if query_type is QueryType.DEFINITION:
        if chunk.chunk_type == "definition" or chunk.source_node_type.value == "definition":
            score += 2.4
        elif " means " in f" {searchable_text} ":
            score += 1.2
    if query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP}:
        if chunk.chunk_type == "table" or chunk.chunk_variant == "table_row":
            score += 2.0
    if query_type in {QueryType.COUNT_LOOKUP, QueryType.LIST_LOOKUP} and _looks_list_like(chunk.text):
        score += 1.6
    if query_type is QueryType.DATE_LOOKUP and any(term in searchable_text for term in ("date", "day", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")):
        score += 1.2
    if query_type is QueryType.DURATION_LOOKUP and any(term in searchable_text for term in ("year", "years", "month", "months", "day", "days", "successive")):
        score += 1.2
    if query_type is QueryType.AMOUNT_LOOKUP and any(term in searchable_text for term in ("taka", "lakh", "crore", "percent", "%")):
        score += 1.2

    if query_terms:
        searchable_terms = set(tokenize_for_bm25(searchable_text))
        overlap = len(query_terms & searchable_terms)
        score += min(overlap * 0.18, 1.5)
    return score


def _looks_list_like(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    marker_lines = sum(1 for line in lines if LIST_MARKER_PATTERN.match(line))
    return marker_lines >= 2


def _chunk_matches_filters(chunk: LegalChunk, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = getattr(chunk, key, None)
        if actual is None:
            actual = chunk.metadata.get(key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if operator == "$eq" and actual != operand:
                    return False
                if operator == "$in" and actual not in operand:
                    return False
                if operator == "$gte" and (actual is None or actual < operand):
                    return False
                if operator == "$lte" and (actual is None or actual > operand):
                    return False
            continue
        if actual != expected:
            return False
    return True
