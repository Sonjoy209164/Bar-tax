import numpy as np

from app.domain import CitationRelation, QueryType
from app.ingestion import (
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)
from app.retrieval import (
    ComparisonEvidencePack,
    CrossSectionEvidencePack,
    DefinitionEvidencePack,
    DeterministicTextEmbedder,
    EmbedderConfig,
    EmbeddingProvider,
    HybridRetriever,
    HybridSearchRequest,
    QueryTransformer,
    RateTableEvidencePack,
    ScenarioEvidencePack,
    SectionLookupEvidencePack,
    VectorRecord,
    VectorSearchMatch,
    VectorSearchResult,
    VectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    VectorStoreStats,
    build_bm25_index,
    build_evidence_pack,
)


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        super().__init__(VectorStoreConfig(provider=VectorStoreProvider.PINECONE, dimensions=32))
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        for record in records:
            effective_namespace = namespace or record.namespace
            self.records[record.record_id] = record.model_copy(update={"namespace": effective_namespace})

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        query_array = np.asarray(query_vector, dtype=np.float32)
        matches: list[VectorSearchMatch] = []
        for record in self.records.values():
            if namespace and record.namespace != namespace:
                continue
            if not _metadata_matches(record.metadata, filters or {}):
                continue
            score = float(np.dot(query_array, np.asarray(record.vector, dtype=np.float32)))
            matches.append(
                VectorSearchMatch(
                    record_id=record.record_id,
                    score=score,
                    metadata=record.metadata,
                    text=record.text,
                    namespace=record.namespace,
                )
            )
        ranked = sorted(matches, key=lambda item: item.score, reverse=True)[:top_k]
        return VectorSearchResult(provider=self.provider, matches=ranked, top_k=top_k, namespace=namespace)

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        for record_id in record_ids:
            self.records.pop(record_id, None)

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        count = sum(1 for record in self.records.values() if namespace is None or record.namespace == namespace)
        return VectorStoreStats(provider=self.provider, index_name="in-memory", total_vector_count=count, namespace=namespace)


def test_definition_evidence_pack_selects_definition_and_governing_context() -> None:
    result = _run_hybrid_result(
        _definition_document(),
        "What is the definition of Commissioner?",
        query_type=QueryType.DEFINITION,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, DefinitionEvidencePack)
    assert pack.definition_term == "commissioner"
    assert pack.definition_evidence
    assert pack.governing_evidence
    assert CitationRelation.DIRECT in {item.citation.relation for item in pack.definition_evidence}


def test_section_lookup_pack_prefers_anchor_evidence_for_target_section() -> None:
    result = _run_hybrid_result(
        _table_document(),
        "Show me section 23 on stock dividend.",
        query_type=QueryType.SECTION_LOOKUP,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, SectionLookupEvidencePack)
    assert pack.target_section_number == "23"
    assert pack.anchor_evidence
    assert not pack.missing_coverage
    assert CitationRelation.PARENT_CONTEXT in {item.citation.relation for item in pack.section_context_evidence}


def test_rate_table_pack_keeps_table_and_governing_rule_evidence() -> None:
    result = _run_hybrid_result(
        _table_document(),
        "What tax rate applies to stock dividend under section 23?",
        query_type=QueryType.RATE_LOOKUP,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, RateTableEvidencePack)
    assert pack.table_evidence
    assert pack.governing_rule_evidence
    assert any(item.metadata.get("node_type") == "table" for item in pack.table_evidence)


def test_bangla_rate_pack_prefers_requested_tax_year_section() -> None:
    result = _run_hybrid_result(
        _bangla_year_rate_document(),
        "২০২৫-২০২৬ করবর্ষে স্বাভাবিক ব্যক্তির করহার কী?",
        query_type=QueryType.RATE_LOOKUP,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, RateTableEvidencePack)
    assert pack.primary_evidence
    assert pack.primary_evidence[0].citation.section_number == "2.1"
    assert {item.citation.section_number for item in pack.all_evidence} == {"2.1"}


def test_scenario_pack_captures_exceptions_and_explanations() -> None:
    result = _run_hybrid_result(
        _scenario_document(),
        "If an employee receives a car benefit used wholly for official duty, what rule applies?",
        query_type=QueryType.SCENARIO_REASONING,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, ScenarioEvidencePack)
    assert pack.rule_evidence
    assert pack.exception_evidence
    assert {item.metadata.get("node_type") for item in pack.exception_evidence} >= {"proviso", "explanation"}
    assert not pack.missing_coverage


def test_cross_section_pack_groups_evidence_by_section() -> None:
    result = _run_hybrid_result(
        _comparison_document(),
        "How do sections 100 and 101 operate for tax day?",
        query_type=QueryType.CROSS_SECTION_REASONING,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, CrossSectionEvidencePack)
    assert len(pack.section_groups) >= 2
    assert {group.section_number for group in pack.section_groups} >= {"100", "101"}


def test_comparison_pack_creates_two_comparison_sides() -> None:
    result = _run_hybrid_result(
        _comparison_document(),
        "Compare the tax day for a company and a person other than a company.",
        query_type=QueryType.COMPARISON,
    )

    pack = build_evidence_pack(result)

    assert isinstance(pack, ComparisonEvidencePack)
    assert len(pack.comparison_groups) == 2
    assert {group.section_number for group in pack.comparison_groups} == {"100", "101"}


def _run_hybrid_result(parsed_document: ParsedDocument, question: str, *, query_type: QueryType):
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    retrieval_chunks = artifacts.retrieval_chunks

    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    vector_store = _vector_store_for_chunks(retrieval_chunks, embedder)
    retriever = HybridRetriever(
        linked_document=linked,
        chunks_or_artifacts=artifacts,
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=build_bm25_index(retrieval_chunks),
        query_transformer=QueryTransformer(),
    )
    return retriever.search(HybridSearchRequest(question=question, query_type=query_type))


def _definition_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        '(1) "Commissioner" means Commissioner of Taxes.',
                        "(a) Chief Commissioner of Taxes;",
                        "(b) Commissioner of Taxes (Appeals);",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
                    ]
                ),
            )
        ],
    )


def _table_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                10,
                "\n".join(
                    [
                        "23. Tax on stock dividend.—The tax shall be charged at the following rates:",
                        "Serial | Income | Rate",
                        "1 | Stock dividend | 10 percent",
                        "2 | Cash dividend | 20 percent",
                    ]
                ),
            )
        ],
    )


def _bangla_year_rate_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="Income-tax_Paripatra_2025-2026-1.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "১.১ স্বাভাবিক ব্যক্তি ও হিন্দু অবিভক্ত পরিবারের ২০২৬-২০২৭ ও ২০২৭-২০২৮ করবর্ষের জন্য করহার",
                        "আয়কর পরিপত্র ২০২৫-২০২৬ | ১",
                        "মোট আয় হার প্রথম ৩,৭৫,০০০ টাকা পর্যন্ত শূন্য।",
                        "২.১ স্বাভাবিক ব্যক্তি, হিন্দু অবিভক্ত পরিবার ও ফার্মের জন্য ২০২৫-২০২৬ করবর্ষের করহার",
                        "মোট আয় হার প্রথম ৩,৫০,০০০ টাকা পর্যন্ত শূন্য। পরবর্তী ১,০০,০০০ টাকা পর্যন্ত ৫%।",
                    ]
                ),
            )
        ],
    )


def _scenario_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                20,
                "\n".join(
                    [
                        "33. Perquisite valuation.— If an employee receives a car benefit, the value shall be included in income from employment.",
                        "Provided that no inclusion shall apply where the vehicle is used wholly for official duty.",
                        "Explanation 1.— Official duty must be certified by the employer.",
                    ]
                ),
            )
        ],
    )


def _comparison_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                30,
                "\n".join(
                    [
                        "100. Tax day for company.— Tax day for a company shall be 15 September.",
                        "101. Tax day for person other than company.— Tax day for an assessee other than a company shall be 30 November.",
                    ]
                ),
            )
        ],
    )


def _vector_store_for_chunks(chunks: list, embedder: DeterministicTextEmbedder) -> InMemoryVectorStore:
    vector_store = InMemoryVectorStore()
    batch = embedder.embed_texts([chunk.normalized_text for chunk in chunks])
    vector_store.upsert(
        [
            VectorRecord(
                record_id=chunk.chunk_id,
                vector=vector,
                metadata={
                    "section_number": chunk.section_number,
                    "chunk_type": chunk.chunk_type,
                    **chunk.metadata,
                },
                text=chunk.text,
            )
            for chunk, vector in zip(chunks, batch.vectors, strict=True)
        ]
    )
    return vector_store


def _metadata_matches(metadata: dict, filters: dict) -> bool:
    for key, expected in filters.items():
        actual = metadata.get(key)
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
