from pathlib import Path

from app.domain import LegalNodeType
from app.domain.query_taxonomy import QueryType
from app.ingestion.chunker import ChunkingArtifacts, LegalChunk
from app.retrieval import BM25SearchRequest, build_bm25_index, load_bm25_index, save_bm25_index


def _chunk(
    chunk_id: str,
    *,
    text: str,
    normalized_text: str | None = None,
    chunk_scope: str = "retrieval_child",
    chunk_variant: str = "body",
    chunk_type: str = "rule",
    section_number: str | None = None,
    subsection_number: str | None = None,
    title: str | None = None,
    label: str | None = None,
    source_node_type: LegalNodeType = LegalNodeType.CLAUSE,
    metadata: dict | None = None,
) -> LegalChunk:
    normalized = normalized_text or text.lower()
    section_value = section_number or "1"
    return LegalChunk(
        chunk_id=chunk_id,
        document_id="income-tax-act-2023",
        act_title="Income Tax Act 2023",
        chunk_scope=chunk_scope,
        chunk_variant=chunk_variant,
        source_node_id=f"node-{chunk_id}",
        source_node_type=source_node_type,
        reasoning_parent_id=f"section-{section_value}",
        parent_node_id=f"section-{section_value}",
        chunk_type=chunk_type,
        text=text,
        normalized_text=normalized,
        token_count=max(20, len(normalized.split())),
        page_start=1,
        page_end=1,
        page_numbers=[1],
        section_number=section_value,
        subsection_number=subsection_number,
        citability_label=label or f"Section {section_value}",
        label=label or f"Section {section_value}",
        title=title,
        linked_node_ids=[f"node-{chunk_id}"],
        metadata=metadata or {},
    )


def test_build_bm25_index_uses_only_retrieval_child_chunks() -> None:
    artifacts = ChunkingArtifacts(
        document_id="income-tax-act-2023",
        act_title="Income Tax Act 2023",
        retrieval_chunks=[_chunk("retrieval-1", text="Commissioner means Commissioner of Taxes.", chunk_type="definition")],
        reasoning_chunks=[_chunk("reasoning-1", text="Long reasoning context.", chunk_scope="reasoning_parent")],
    )

    index = build_bm25_index(artifacts)

    assert len(index.chunks) == 1
    assert index.chunks[0].chunk_id == "retrieval-1"
    assert index.describe().chunk_count == 1


def test_bm25_definition_query_prefers_definition_chunk() -> None:
    chunks = [
        _chunk(
            "definition-1",
            text='"Commissioner" means Commissioner of Taxes or Commissioner of Taxes (Large Assessee Unit).',
            chunk_type="definition",
            section_number="2",
            title="Definitions",
            label="Section 2",
            source_node_type=LegalNodeType.DEFINITION,
        ),
        _chunk(
            "general-1",
            text="The Commissioner may issue administrative directions under this Chapter.",
            chunk_type="rule",
            section_number="10",
            title="Commissioner powers",
            label="Section 10",
            source_node_type=LegalNodeType.SECTION,
        ),
    ]

    index = build_bm25_index(chunks)
    result = index.search(
        BM25SearchRequest(
            query="What is the definition of Commissioner?",
            query_type=QueryType.DEFINITION,
            top_k=2,
        )
    )

    assert result.matches[0].chunk.chunk_id == "definition-1"
    assert result.matches[0].score > result.matches[1].score


def test_bm25_section_aware_weighting_prefers_matching_anchor_chunk() -> None:
    chunks = [
        _chunk(
            "section-4-anchor",
            text="Section 4\nIncome tax authorities",
            chunk_type="rule",
            chunk_variant="anchor",
            section_number="4",
            title="Income tax authorities",
            label="Section 4",
            source_node_type=LegalNodeType.SECTION,
        ),
        _chunk(
            "section-40-body",
            text="Section 40 income from agriculture. 40 percent shall be deemed business income and 60 percent agricultural income.",
            chunk_type="rule",
            section_number="40",
            title="Income from agriculture",
            label="Section 40",
            source_node_type=LegalNodeType.SECTION,
        ),
    ]

    index = build_bm25_index(chunks)
    result = index.search(
        BM25SearchRequest(
            query="What are the income tax authorities under section 4?",
            query_type=QueryType.SECTION_LOOKUP,
            top_k=2,
        )
    )

    assert result.section_reference == "4"
    assert result.matches[0].chunk.chunk_id == "section-4-anchor"
    assert len(result.matches) >= 1


def test_bm25_filters_and_persistence_round_trip(tmp_path: Path) -> None:
    chunks = [
        _chunk(
            "table-1",
            text="Serial | Rate\n1 | 10 percent",
            chunk_type="table",
            chunk_variant="table_row",
            section_number="23",
            title="Dividend rates",
            metadata={"tax_year": "2025-2026"},
            source_node_type=LegalNodeType.TABLE,
        ),
        _chunk(
            "table-2",
            text="Serial | Rate\n1 | 15 percent",
            chunk_type="table",
            chunk_variant="table_row",
            section_number="23",
            title="Dividend rates",
            metadata={"tax_year": "2024-2025"},
            source_node_type=LegalNodeType.TABLE,
        ),
    ]

    index = build_bm25_index(chunks)
    saved_dir = save_bm25_index(index, tmp_path / "bm25")
    reloaded = load_bm25_index(saved_dir)

    result = reloaded.search(
        BM25SearchRequest(
            query="What tax rate applies to stock dividend under section 23?",
            query_type=QueryType.RATE_LOOKUP,
            top_k=2,
            filters={"tax_year": {"$eq": "2025-2026"}},
        )
    )

    assert result.matches[0].chunk.chunk_id == "table-1"
    assert len(result.matches) == 1
