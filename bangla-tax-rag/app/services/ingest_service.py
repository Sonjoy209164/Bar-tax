from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.ingestion import (
    ChunkingArtifacts,
    ChunkingConfig,
    DocumentParser,
    DocumentStoreSnapshot,
    LinkedLegalDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parser,
    link_parent_child_relationships,
    persist_linked_document,
    tag_legal_metadata,
    validate_linked_document,
    validate_tagged_document,
)
from app.retrieval.bm25_index import BM25IndexStats, build_bm25_index, save_bm25_index
from app.retrieval.embedder import TextEmbedder
from app.retrieval.vector_store_base import VectorRecord, VectorStore


class IngestServiceConfig(BaseModel):
    output_root: str = "data/agentic_store"
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    persist_chunk_artifacts: bool = True
    vector_namespace: str | None = None


class IngestServiceResult(BaseModel):
    document_id: str
    act_title: str
    parser_provider: str
    document_store: DocumentStoreSnapshot
    bm25_index_dir: str
    retrieval_chunk_count: int
    reasoning_chunk_count: int
    vector_record_count: int
    bm25_stats: BM25IndexStats


class IngestService:
    def __init__(
        self,
        *,
        parser: DocumentParser | None = None,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        config: IngestServiceConfig | None = None,
    ) -> None:
        self.parser = parser or build_parser()
        self.embedder = embedder
        self.vector_store = vector_store
        self.config = config or IngestServiceConfig()

    def ingest(
        self,
        source_path: str | Path,
        *,
        document_id: str | None = None,
        act_title: str | None = None,
        output_dir: str | Path | None = None,
    ) -> IngestServiceResult:
        parsed_document = self.parser.parse(source_path)
        structured_document = build_legal_structure(parsed_document, document_id=document_id, act_title=act_title)
        tagged_document = tag_legal_metadata(structured_document)
        validate_tagged_document(tagged_document)
        linked_document = link_parent_child_relationships(tagged_document)
        validate_linked_document(linked_document)
        chunking_artifacts = build_legal_chunks(linked_document, config=self.config.chunking)

        document_output_dir = Path(output_dir or Path(self.config.output_root) / linked_document.document_id)
        document_output_dir.mkdir(parents=True, exist_ok=True)
        document_store = persist_linked_document(linked_document, document_output_dir / "graph")

        bm25_index = build_bm25_index(chunking_artifacts)
        bm25_index_dir = save_bm25_index(bm25_index, document_output_dir / "bm25")

        if self.config.persist_chunk_artifacts:
            _persist_chunk_artifacts(chunking_artifacts, document_output_dir / "chunks")

        vector_records = _build_vector_records(
            chunking_artifacts=chunking_artifacts,
            embedder=self.embedder,
            namespace=self.config.vector_namespace or self.vector_store.config.namespace,
        )
        self.vector_store.upsert(vector_records, namespace=self.config.vector_namespace or self.vector_store.config.namespace)

        return IngestServiceResult(
            document_id=linked_document.document_id,
            act_title=linked_document.act_title,
            parser_provider=linked_document.parser_provider,
            document_store=document_store,
            bm25_index_dir=str(bm25_index_dir),
            retrieval_chunk_count=len(chunking_artifacts.retrieval_chunks),
            reasoning_chunk_count=len(chunking_artifacts.reasoning_chunks),
            vector_record_count=len(vector_records),
            bm25_stats=bm25_index.describe(),
        )


def _build_vector_records(
    *,
    chunking_artifacts: ChunkingArtifacts,
    embedder: TextEmbedder,
    namespace: str | None,
) -> list[VectorRecord]:
    chunks = chunking_artifacts.retrieval_chunks
    batch = embedder.embed_texts([chunk.normalized_text for chunk in chunks])
    return [
        VectorRecord(
            record_id=chunk.chunk_id,
            vector=vector,
            metadata={
                "document_id": chunk.document_id,
                "section_number": chunk.section_number,
                "chunk_type": chunk.chunk_type,
                "source_node_type": chunk.source_node_type.value,
                **chunk.metadata,
            },
            text=chunk.text,
            namespace=namespace,
        )
        for chunk, vector in zip(chunks, batch.vectors, strict=True)
    ]


def _persist_chunk_artifacts(chunking_artifacts: ChunkingArtifacts, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieval_path = output_dir / "retrieval_chunks.jsonl"
    reasoning_path = output_dir / "reasoning_chunks.jsonl"
    metadata_path = output_dir / "metadata.json"

    with retrieval_path.open("w", encoding="utf-8") as handle:
        for chunk in chunking_artifacts.retrieval_chunks:
            handle.write(chunk.model_dump_json())
            handle.write("\n")

    with reasoning_path.open("w", encoding="utf-8") as handle:
        for chunk in chunking_artifacts.reasoning_chunks:
            handle.write(chunk.model_dump_json())
            handle.write("\n")

    metadata_path.write_text(
        json.dumps(
            {
                "document_id": chunking_artifacts.document_id,
                "act_title": chunking_artifacts.act_title,
                "retrieval_chunk_count": len(chunking_artifacts.retrieval_chunks),
                "reasoning_chunk_count": len(chunking_artifacts.reasoning_chunks),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
