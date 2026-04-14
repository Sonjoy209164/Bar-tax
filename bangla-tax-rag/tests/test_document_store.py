from pathlib import Path

from app.domain import LegalNodeType
from app.ingestion import (
    ParsedDocument,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    load_linked_document,
    load_links_from_jsonl,
    load_nodes_from_jsonl,
    load_store_manifest,
    load_structured_document,
    persist_linked_document,
    persist_structured_document,
    tag_legal_metadata,
)


def _build_linked_sample_document():
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        "(1) “Commissioner” means Commissioner of Taxes.",
                        "(a) Chief Commissioner of Taxes;",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
                    ]
                ),
            ),
            build_parsed_page_from_text(
                10,
                "\n".join(
                    [
                        "163. Rate of tax.—The tax shall be charged at the following rates:",
                        "Rate | Amount | Note",
                        "10% | 100000 | sample",
                        "15% | 200000 | higher slab",
                    ]
                ),
            ),
        ],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    tagged = tag_legal_metadata(structured)
    return structured, link_parent_child_relationships(tagged)


def test_document_store_persists_and_reloads_structured_document(tmp_path: Path) -> None:
    structured, _ = _build_linked_sample_document()

    snapshot = persist_structured_document(structured, tmp_path / "structured-store")
    manifest = load_store_manifest(tmp_path / "structured-store")
    restored = load_structured_document(tmp_path / "structured-store")
    restored_nodes = load_nodes_from_jsonl(snapshot.nodes_path)

    assert Path(snapshot.graph_path).exists()
    assert Path(snapshot.manifest_path).exists()
    assert manifest.document_id == structured.document_id
    assert manifest.link_count == 0
    assert manifest.metadata["has_link_graph"] is False
    assert restored.document_id == structured.document_id
    assert restored.root_node_id == structured.root_node_id
    assert len(restored.nodes) == len(structured.nodes)
    assert len(restored_nodes) == len(structured.nodes)


def test_document_store_persists_link_graph_and_split_node_views(tmp_path: Path) -> None:
    _, linked = _build_linked_sample_document()

    snapshot = persist_linked_document(linked, tmp_path / "linked-store")
    manifest = load_store_manifest(tmp_path / "linked-store")
    restored = load_linked_document(tmp_path / "linked-store")
    parent_nodes = load_nodes_from_jsonl(Path(snapshot.parent_nodes_path))
    retrieval_nodes = load_nodes_from_jsonl(Path(snapshot.retrieval_nodes_path))
    links = load_links_from_jsonl(Path(snapshot.links_path))

    assert manifest.link_count == len(linked.links)
    assert manifest.metadata["has_link_graph"] is True
    assert restored.document_id == linked.document_id
    assert len(restored.nodes) == len(linked.nodes)
    assert len(restored.links) == len(linked.links)
    assert any(node.node_type is LegalNodeType.SECTION for node in parent_nodes)
    assert any(node.node_type is LegalNodeType.TABLE for node in retrieval_nodes)
    assert any(link.metadata.get("link_kind") == "attached_table" for link in links)


def test_document_store_separates_reasoning_and_retrieval_views(tmp_path: Path) -> None:
    _, linked = _build_linked_sample_document()

    snapshot = persist_linked_document(linked, tmp_path / "artifact-store")
    parent_nodes = load_nodes_from_jsonl(snapshot.parent_nodes_path)
    retrieval_nodes = load_nodes_from_jsonl(snapshot.retrieval_nodes_path)

    parent_node_ids = {node.node_id for node in parent_nodes}
    retrieval_node_ids = {node.node_id for node in retrieval_nodes}

    assert linked.root_node_id in parent_node_ids
    assert any(node.node_type is LegalNodeType.SUBSECTION for node in parent_nodes)
    assert any(node.node_type is LegalNodeType.PROVISO for node in retrieval_nodes)
    assert any(node.node_type is LegalNodeType.EXPLANATION for node in retrieval_nodes)
    assert retrieval_node_ids - parent_node_ids
