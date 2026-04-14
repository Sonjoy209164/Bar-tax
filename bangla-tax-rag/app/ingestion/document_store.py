from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.domain import LegalNode, LegalNodeType
from app.ingestion.parent_child_linker import LegalNodeLink, LinkedLegalDocument
from app.ingestion.structure_builder import StructuredLegalDocument


class DocumentStoreManifest(BaseModel):
    document_id: str
    act_title: str
    parser_provider: str
    source_path: str
    root_node_id: str
    node_count: int
    link_count: int = 0
    store_version: str = "1"
    graph_filename: str = "legal_graph.json"
    manifest_filename: str = "manifest.json"
    nodes_filename: str = "nodes.jsonl"
    parent_nodes_filename: str = "parent_nodes.jsonl"
    retrieval_nodes_filename: str = "retrieval_nodes.jsonl"
    links_filename: str | None = "links.jsonl"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentStoreSnapshot(BaseModel):
    manifest_path: str
    graph_path: str
    nodes_path: str
    parent_nodes_path: str
    retrieval_nodes_path: str
    links_path: str | None = None


def persist_structured_document(
    structured_document: StructuredLegalDocument,
    output_dir: str | Path,
) -> DocumentStoreSnapshot:
    return _persist_document(
        structured_document=structured_document,
        linked_document=None,
        output_dir=output_dir,
    )


def persist_linked_document(
    linked_document: LinkedLegalDocument,
    output_dir: str | Path,
) -> DocumentStoreSnapshot:
    structured_document = StructuredLegalDocument(
        document_id=linked_document.document_id,
        act_title=linked_document.act_title,
        source_path=linked_document.source_path,
        parser_provider=linked_document.parser_provider,
        root_node_id=linked_document.root_node_id,
        nodes=linked_document.nodes,
    )
    return _persist_document(
        structured_document=structured_document,
        linked_document=linked_document,
        output_dir=output_dir,
    )


def load_structured_document(store_dir: str | Path) -> StructuredLegalDocument:
    store_dir = Path(store_dir)
    graph_payload = json.loads((store_dir / "legal_graph.json").read_text(encoding="utf-8"))
    if "links" in graph_payload:
        graph_payload.pop("links", None)
    return StructuredLegalDocument.model_validate(graph_payload)


def load_linked_document(store_dir: str | Path) -> LinkedLegalDocument:
    store_dir = Path(store_dir)
    graph_payload = json.loads((store_dir / "legal_graph.json").read_text(encoding="utf-8"))
    return LinkedLegalDocument.model_validate(graph_payload)


def load_store_manifest(store_dir: str | Path) -> DocumentStoreManifest:
    store_dir = Path(store_dir)
    return DocumentStoreManifest.model_validate_json((store_dir / "manifest.json").read_text(encoding="utf-8"))


def load_nodes_from_jsonl(jsonl_path: str | Path) -> list[LegalNode]:
    jsonl_path = Path(jsonl_path)
    nodes: list[LegalNode] = []
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            nodes.append(LegalNode.model_validate_json(line))
    return nodes


def load_links_from_jsonl(jsonl_path: str | Path) -> list[LegalNodeLink]:
    jsonl_path = Path(jsonl_path)
    links: list[LegalNodeLink] = []
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            links.append(LegalNodeLink.model_validate_json(line))
    return links


def _persist_document(
    *,
    structured_document: StructuredLegalDocument,
    linked_document: LinkedLegalDocument | None,
    output_dir: str | Path,
) -> DocumentStoreSnapshot:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = DocumentStoreManifest(
        document_id=structured_document.document_id,
        act_title=structured_document.act_title,
        parser_provider=structured_document.parser_provider,
        source_path=structured_document.source_path,
        root_node_id=structured_document.root_node_id,
        node_count=len(structured_document.nodes),
        link_count=len(linked_document.links) if linked_document else 0,
        links_filename="links.jsonl" if linked_document else None,
        metadata={
            "parent_node_count": len(_select_parent_nodes(structured_document.nodes)),
            "retrieval_node_count": len(_select_retrieval_nodes(structured_document.nodes)),
            "has_link_graph": linked_document is not None,
        },
    )

    graph_payload: dict[str, Any]
    if linked_document is not None:
        graph_payload = linked_document.model_dump(mode="json")
    else:
        graph_payload = structured_document.model_dump(mode="json")

    graph_path = output_dir / manifest.graph_filename
    manifest_path = output_dir / manifest.manifest_filename
    nodes_path = output_dir / manifest.nodes_filename
    parent_nodes_path = output_dir / manifest.parent_nodes_filename
    retrieval_nodes_path = output_dir / manifest.retrieval_nodes_filename
    links_path = output_dir / manifest.links_filename if manifest.links_filename else None

    graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    _write_jsonl(nodes_path, structured_document.nodes)
    _write_jsonl(parent_nodes_path, _select_parent_nodes(structured_document.nodes))
    _write_jsonl(retrieval_nodes_path, _select_retrieval_nodes(structured_document.nodes))
    if links_path and linked_document is not None:
        _write_jsonl(links_path, linked_document.links)

    return DocumentStoreSnapshot(
        manifest_path=str(manifest_path),
        graph_path=str(graph_path),
        nodes_path=str(nodes_path),
        parent_nodes_path=str(parent_nodes_path),
        retrieval_nodes_path=str(retrieval_nodes_path),
        links_path=str(links_path) if links_path else None,
    )


def _write_jsonl(path: Path, items: list[BaseModel]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(item.model_dump_json())
            handle.write("\n")


def _select_parent_nodes(nodes: list[LegalNode]) -> list[LegalNode]:
    return [
        node
        for node in nodes
        if node.node_type in {
            LegalNodeType.ACT,
            LegalNodeType.PART,
            LegalNodeType.CHAPTER,
            LegalNodeType.SECTION,
            LegalNodeType.SUBSECTION,
        }
        or bool(node.child_ids)
    ]


def _select_retrieval_nodes(nodes: list[LegalNode]) -> list[LegalNode]:
    retrieval_types = {
        LegalNodeType.SECTION,
        LegalNodeType.SUBSECTION,
        LegalNodeType.CLAUSE,
        LegalNodeType.PROVISO,
        LegalNodeType.EXPLANATION,
        LegalNodeType.TABLE,
        LegalNodeType.DEFINITION,
        LegalNodeType.ILLUSTRATION,
    }
    return [node for node in nodes if node.node_type in retrieval_types]
