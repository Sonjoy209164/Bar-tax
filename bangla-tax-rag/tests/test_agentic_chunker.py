from app.domain import LegalNodeType
from app.ingestion import (
    ChunkingConfig,
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    estimate_token_count,
    link_parent_child_relationships,
    tag_legal_metadata,
)


def _build_linked_document(*pages: str):
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[build_parsed_page_from_text(index + 1, page_text) for index, page_text in enumerate(pages)],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    tagged = tag_legal_metadata(structured)
    return link_parent_child_relationships(tagged)


def test_agentic_chunker_builds_retrieval_and_reasoning_chunks_with_legal_roles() -> None:
    linked = _build_linked_document(
        "\n".join(
            [
                "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                "(1) “Commissioner” means Commissioner of Taxes.",
                "(a) Chief Commissioner of Taxes;",
                "Provided that this definition applies only where the context so requires.",
                "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
            ]
        )
    )

    artifacts = build_legal_chunks(
        linked,
        config=ChunkingConfig(
            retrieval_min_tokens=10,
            retrieval_target_tokens=20,
            retrieval_max_tokens=40,
            reasoning_min_tokens=20,
            reasoning_target_tokens=40,
            reasoning_max_tokens=120,
        ),
    )

    assert artifacts.retrieval_chunks
    assert artifacts.reasoning_chunks
    assert any(chunk.chunk_variant == "anchor" for chunk in artifacts.retrieval_chunks)
    assert any(chunk.chunk_type == "definition" for chunk in artifacts.retrieval_chunks)
    assert any(chunk.chunk_type == "proviso" for chunk in artifacts.retrieval_chunks)
    assert any(chunk.chunk_type == "explanation" for chunk in artifacts.retrieval_chunks)

    reasoning_chunk = artifacts.reasoning_chunks[0]
    assert reasoning_chunk.chunk_scope == "reasoning_parent"
    assert "Provided that this definition applies only where the context so requires." in reasoning_chunk.text
    assert "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit." in reasoning_chunk.text


def test_agentic_chunker_keeps_clause_units_intact_for_retrieval() -> None:
    linked = _build_linked_document(
        "\n".join(
            [
                "32. Income from employment.—The following shall be included in income from employment:—",
                "(1) The following receipts shall be deemed to be income from employment:—",
                "(a) any monetary receipts from the employer;",
                "(b) income earned from employee share schemes;",
                "(c) untaxed arrear salary;",
            ]
        )
    )

    artifacts = build_legal_chunks(
        linked,
        config=ChunkingConfig(
            retrieval_min_tokens=5,
            retrieval_target_tokens=15,
            retrieval_max_tokens=30,
            reasoning_min_tokens=20,
            reasoning_target_tokens=60,
            reasoning_max_tokens=140,
        ),
    )

    clause_chunks = [
        chunk
        for chunk in artifacts.retrieval_chunks
        if chunk.source_node_type is LegalNodeType.CLAUSE and chunk.chunk_variant == "body"
    ]

    assert len(clause_chunks) == 3
    assert any(chunk.text.startswith("(a)") for chunk in clause_chunks)
    assert any(chunk.text.startswith("(b)") for chunk in clause_chunks)
    assert any(chunk.text.startswith("(c)") for chunk in clause_chunks)
    assert all(not chunk.text.startswith("income earned from employee share schemes;") for chunk in clause_chunks)


def test_agentic_chunker_preserves_table_rows_and_token_targets() -> None:
    linked = _build_linked_document(
        "\n".join(
            [
                "163. Rate of tax.—The tax shall be charged at the following rates:",
                "Rate | Amount | Note",
                "10% | 100000 | sample",
                "15% | 200000 | higher slab",
            ]
        )
    )

    artifacts = build_legal_chunks(
        linked,
        config=ChunkingConfig(
            retrieval_min_tokens=5,
            retrieval_target_tokens=10,
            retrieval_max_tokens=25,
            reasoning_min_tokens=10,
            reasoning_target_tokens=30,
            reasoning_max_tokens=80,
        ),
    )

    table_chunks = [chunk for chunk in artifacts.retrieval_chunks if chunk.source_node_type is LegalNodeType.TABLE]
    assert len(table_chunks) == 2
    assert all(chunk.chunk_variant == "table_row" for chunk in table_chunks)
    assert all("Rate | Amount | Note" in chunk.text for chunk in table_chunks)
    assert all(chunk.chunk_type == "table" for chunk in table_chunks)
    assert all(chunk.token_count == estimate_token_count(chunk.text) for chunk in table_chunks)
