import argparse
import csv
import json
import re
import shlex
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.utils import extract_section_ids, normalize_text, normalize_whitespace

BANGLA_PATTERN = re.compile(r"[\u0980-\u09FF]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
NUMBER_PATTERN = re.compile(r"\d")
PERCENT_PATTERN = re.compile(r"(?:%|শতাংশ|percent)", re.IGNORECASE)
MONEY_PATTERN = re.compile(r"(?:টাকা|taka|lakh|crore|কোটি|লক্ষ)", re.IGNORECASE)
TABLE_SIGNAL_PATTERN = re.compile(
    r"(?:করহার|হার|মোট আয়|এইচ\s*এস|H\.?\s*S\.?\s*Code|ক্রমিক|বিবরণ|বর্ণনা|slab|rate|amount|tax)",
    re.IGNORECASE,
)
FOOTER_PATTERN = re.compile(
    r"^(?:\d+\s*\|\s*)?(?:আ\s*য়\s*ক\s*র|আয়কর)\s+(?:পরিপত্র|পতরপত্র|পররপত্র).{0,40}\d{4}\s*-\s*\d{4}\s*$"
)
PAGE_ONLY_PATTERN = re.compile(r"^(?:পৃষ্ঠা\s*)?\d{1,4}$", re.IGNORECASE)
SECTION_LIKE_PATTERN = re.compile(r"^(?:ধারা\s*)?\d+[A-Za-z]?(?:\.\d+)*$")
SHORT_NOISE_TOKENS = {
    "haifa",
    "ft",
    "as",
    "ga]",
    "ga",
    "wl",
    "wit",
    "wa",
    "ala",
    "|",
}


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Clean and structure Pilot14 parsed chunks into canonical research artifacts. "
            "Raw OCR/non-OCR parses are preserved; outputs are written to data/processed/btax14/structured by default."
        )
    )
    parser.add_argument("--manifest", default="data/metadata/corpus_manifest_btax14.csv")
    parser.add_argument("--source-dir", default="data/processed/btax14/ocr_per_doc")
    parser.add_argument("--fallback-dir", default="data/processed/btax14/per_doc")
    parser.add_argument("--output-dir", default="data/processed/btax14/structured")
    parser.add_argument("--publish-dir", default="data/processed/btax14")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--results-dir", default="results/pilot14")
    parser.add_argument("--source-label", default="ocr")
    parser.add_argument("--min-clean-chars", type=int, default=20)
    parser.add_argument("--keep-noise", action="store_true", help="Keep noise chunks in canonical chunks.jsonl.")
    return parser


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    return {row["doc_id"]: row for row in csv.DictReader(path.open(encoding="utf-8"))}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_heading_path(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        text = clean_text(str(value))
        if not text or is_noise_line(text):
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


def clean_text(text: str) -> str:
    lines = []
    for raw_line in text.replace("\u00a0", " ").splitlines():
        line = normalize_whitespace(raw_line.strip())
        if not line:
            continue
        if is_noise_line(line):
            continue
        lines.append(line)
    return normalize_whitespace("\n".join(lines))


def is_noise_line(line: str) -> bool:
    normalized = normalize_text(line).strip()
    lowered = normalized.lower()
    if not normalized:
        return True
    if lowered in SHORT_NOISE_TOKENS:
        return True
    if FOOTER_PATTERN.match(normalized):
        return True
    if PAGE_ONLY_PATTERN.match(normalized):
        return True
    if len(normalized) <= 2 and not NUMBER_PATTERN.search(normalized):
        return True
    if len(normalized) <= 6 and not BANGLA_PATTERN.search(normalized) and not NUMBER_PATTERN.search(normalized):
        return True
    return False


def looks_table_like(text: str, chunk_type: str, heading_path: list[str]) -> bool:
    if chunk_type == "table":
        return True
    combined = f"{' '.join(heading_path)}\n{text}"
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    numeric_lines = sum(1 for line in lines if len(NUMBER_PATTERN.findall(line)) >= 2)
    signal = bool(TABLE_SIGNAL_PATTERN.search(combined))
    has_money_or_percent = bool(MONEY_PATTERN.search(combined) or PERCENT_PATTERN.search(combined))
    has_spacing_table = any(re.search(r"\S\s{3,}\S", line) for line in lines)
    return signal and (has_money_or_percent or numeric_lines >= 2 or has_spacing_table)


def text_quality(text: str) -> dict[str, Any]:
    total = max(len(text), 1)
    bangla_count = len(BANGLA_PATTERN.findall(text))
    latin_count = len(LATIN_PATTERN.findall(text))
    digit_count = len(NUMBER_PATTERN.findall(text))
    return {
        "char_count": len(text),
        "bangla_ratio": bangla_count / total,
        "latin_ratio": latin_count / total,
        "digit_count": digit_count,
        "line_count": len([line for line in text.splitlines() if line.strip()]),
    }


def infer_noise_reason(cleaned_text: str, row: dict[str, Any], *, min_clean_chars: int) -> str | None:
    if len(cleaned_text.strip()) < min_clean_chars:
        if not SECTION_LIKE_PATTERN.search(cleaned_text) and not MONEY_PATTERN.search(cleaned_text):
            return "too_short_after_cleanup"
    if not cleaned_text.strip():
        return "empty_after_cleanup"
    return None


def chunk_record_fields(row: dict[str, Any], *, clean_original_text: str, clean_normalized_text: str, heading_path: list[str], chunk_type: str) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "doc_title": row["doc_title"],
        "doc_type": row["doc_type"],
        "authority_level": row["authority_level"],
        "tax_year": row.get("tax_year"),
        "effective_start": row.get("effective_start"),
        "effective_end": row.get("effective_end"),
        "page_no": row["page_no"],
        "section_id": row.get("section_id"),
        "subsection_id": row.get("subsection_id"),
        "appendix_id": row.get("appendix_id"),
        "sro_id": row.get("sro_id"),
        "chunk_type": chunk_type,
        "heading_path": heading_path,
        "original_text": clean_original_text,
        "normalized_text": clean_normalized_text,
        "cross_refs": row.get("cross_refs", []),
    }


def build_pages(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        grouped[(chunk["doc_id"], chunk["page_no"])].append(chunk)
    pages: list[dict[str, Any]] = []
    for (doc_id, page_no), page_chunks in sorted(grouped.items()):
        text = "\n\n".join(chunk["original_text"] for chunk in page_chunks if chunk["original_text"])
        sections = sorted({chunk.get("section_id") for chunk in page_chunks if chunk.get("section_id")})
        pages.append(
            {
                "page_id": f"{doc_id}:page:{page_no}",
                "doc_id": doc_id,
                "page_no": page_no,
                "chunk_ids": [chunk["chunk_id"] for chunk in page_chunks],
                "section_ids": sections,
                "text": text,
                "normalized_text": normalize_text(text),
                "quality": text_quality(text),
            }
        )
    return pages


def build_table_records(chunks: list[dict[str, Any]], enriched_by_chunk_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for chunk in chunks:
        enriched = enriched_by_chunk_id[chunk["chunk_id"]]
        if not enriched["structure"]["is_table_candidate"]:
            continue
        tables.append(
            {
                "table_id": f"{chunk['chunk_id']}:table",
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "page_no": chunk["page_no"],
                "section_id": chunk.get("section_id"),
                "tax_year": chunk.get("tax_year"),
                "heading_path": chunk.get("heading_path", []),
                "text": chunk["original_text"],
                "normalized_text": chunk["normalized_text"],
                "quality": enriched["quality"],
            }
        )
    return tables


def add_node(nodes: dict[str, dict[str, Any]], node_id: str, **payload: Any) -> None:
    if node_id in nodes:
        nodes[node_id].update({key: value for key, value in payload.items() if value not in (None, "", [])})
        return
    nodes[node_id] = {"node_id": node_id, **payload}


def add_link(links: list[dict[str, Any]], seen: set[tuple[str, str, str]], source: str, target: str, relation: str, **metadata: Any) -> None:
    key = (source, target, relation)
    if key in seen:
        return
    seen.add(key)
    links.append({"source_node_id": source, "target_node_id": target, "relation": relation, "metadata": metadata})


def build_graph(
    *,
    manifest: dict[str, dict[str, str]],
    chunks: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    seen_links: set[tuple[str, str, str]] = set()

    for doc_id, row in sorted(manifest.items()):
        doc_node_id = f"{doc_id}:doc"
        add_node(
            nodes,
            doc_node_id,
            node_type="document",
            doc_id=doc_id,
            title=row.get("title"),
            title_bn=row.get("title_bn"),
            authority_type=row.get("authority_type"),
            tax_year=row.get("tax_year"),
            source_url=row.get("source_url"),
        )

    for page in pages:
        doc_node_id = f"{page['doc_id']}:doc"
        page_node_id = page["page_id"]
        add_node(
            nodes,
            page_node_id,
            node_type="page",
            doc_id=page["doc_id"],
            page_no=page["page_no"],
            section_ids=page["section_ids"],
            quality=page["quality"],
        )
        add_link(links, seen_links, doc_node_id, page_node_id, "contains_page")

    for chunk in chunks:
        doc_id = chunk["doc_id"]
        doc_node_id = f"{doc_id}:doc"
        page_node_id = f"{doc_id}:page:{chunk['page_no']}"
        chunk_node_id = f"{chunk['chunk_id']}:chunk"
        add_node(
            nodes,
            chunk_node_id,
            node_type="chunk",
            chunk_id=chunk["chunk_id"],
            doc_id=doc_id,
            page_no=chunk["page_no"],
            section_id=chunk.get("section_id"),
            subsection_id=chunk.get("subsection_id"),
            chunk_type=chunk.get("chunk_type"),
            tax_year=chunk.get("tax_year"),
        )
        add_link(links, seen_links, page_node_id, chunk_node_id, "contains_chunk")
        add_link(links, seen_links, doc_node_id, chunk_node_id, "contains_chunk")

        section_id = chunk.get("section_id")
        if section_id:
            section_node_id = f"{doc_id}:section:{section_id}"
            add_node(nodes, section_node_id, node_type="section", doc_id=doc_id, section_id=section_id)
            add_link(links, seen_links, doc_node_id, section_node_id, "contains_section")
            add_link(links, seen_links, section_node_id, chunk_node_id, "section_contains_chunk")

        for cross_ref in chunk.get("cross_refs", []):
            add_link(links, seen_links, chunk_node_id, f"{doc_id}:ref:{cross_ref}", "mentions_reference", reference=cross_ref)

    for table in tables:
        table_node_id = f"{table['table_id']}:node"
        chunk_node_id = f"{table['chunk_id']}:chunk"
        add_node(
            nodes,
            table_node_id,
            node_type="table",
            table_id=table["table_id"],
            chunk_id=table["chunk_id"],
            doc_id=table["doc_id"],
            page_no=table["page_no"],
            section_id=table.get("section_id"),
        )
        add_link(links, seen_links, chunk_node_id, table_node_id, "has_table_candidate")

    graph_events: list[dict[str, Any]] = []
    graph_events.extend({"record_type": "node", **node} for node in nodes.values())
    graph_events.extend({"record_type": "link", **link} for link in links)
    return list(nodes.values()), links, graph_events


def write_command_provenance(results_dir: Path, args: argparse.Namespace) -> None:
    command = ["python", "scripts/structure_pilot14_corpus.py", *sys.argv[1:]]
    shell_path = results_dir / "pilot14_structure_command.sh"
    json_path = results_dir / "pilot14_structure_command.json"
    shell_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'cd "/home/sonjoy/Bar tax/bangla-tax-rag"\n\n'
        + " ".join(shlex.quote(part) for part in command)
        + "\n",
        encoding="utf-8",
    )
    write_json(
        json_path,
        {
            "command": command,
            "created_at": datetime.now(UTC).isoformat(),
            "args": vars(args),
        },
    )


def write_artifacts(
    artifact_dir: Path,
    *,
    canonical_chunks: list[dict[str, Any]],
    enriched_chunks: list[dict[str, Any]],
    rejected_chunks: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    graph_events: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(artifact_dir / "chunks.jsonl", canonical_chunks)
    write_jsonl(artifact_dir / "chunks_enriched.jsonl", enriched_chunks)
    write_jsonl(artifact_dir / "chunks_rejected.jsonl", rejected_chunks)
    write_jsonl(artifact_dir / "pages.jsonl", pages)
    write_jsonl(artifact_dir / "tables.jsonl", tables)
    write_jsonl(artifact_dir / "legal_graph_nodes.jsonl", nodes)
    write_jsonl(artifact_dir / "legal_graph_links.jsonl", links)
    write_jsonl(artifact_dir / "legal_graph.jsonl", graph_events)
    write_json(artifact_dir / "extraction_report.json", report)


def main() -> None:
    args = build_argument_parser().parse_args()
    manifest_path = Path(args.manifest)
    source_dir = Path(args.source_dir)
    fallback_dir = Path(args.fallback_dir)
    output_dir = Path(args.output_dir)
    publish_dir = Path(args.publish_dir)
    results_dir = Path(args.results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_publish:
        publish_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(manifest_path)
    write_command_provenance(results_dir, args)

    canonical_chunks: list[dict[str, Any]] = []
    enriched_chunks: list[dict[str, Any]] = []
    rejected_chunks: list[dict[str, Any]] = []
    source_report: dict[str, Any] = {}

    for doc_id, manifest_row in sorted(manifest.items()):
        source_path = source_dir / f"{doc_id}.jsonl"
        source_used = args.source_label
        if not source_path.exists():
            source_path = fallback_dir / f"{doc_id}.jsonl"
            source_used = "fallback_non_ocr"
        rows = read_jsonl(source_path)
        source_report[doc_id] = {
            "source_path": str(source_path),
            "source_used": source_used,
            "input_chunks": len(rows),
            "kept_chunks": 0,
            "rejected_chunks": 0,
            "table_candidates": 0,
        }

        for row in rows:
            cleaned_original = clean_text(row.get("original_text") or "")
            cleaned_normalized = normalize_text(cleaned_original)
            heading_path = clean_heading_path(row.get("heading_path", []))
            chunk_type = row.get("chunk_type") or "text"
            is_table_candidate = looks_table_like(cleaned_original, chunk_type, heading_path)
            if is_table_candidate and chunk_type == "text":
                chunk_type = "table"
            noise_reason = infer_noise_reason(cleaned_original, row, min_clean_chars=args.min_clean_chars)
            quality = text_quality(cleaned_original)
            section_candidates = extract_section_ids(cleaned_original)

            clean_record = chunk_record_fields(
                row,
                clean_original_text=cleaned_original,
                clean_normalized_text=cleaned_normalized,
                heading_path=heading_path,
                chunk_type=chunk_type,
            )
            if not clean_record.get("section_id") and section_candidates:
                clean_record["section_id"] = section_candidates[0]
            clean_record["cross_refs"] = list(dict.fromkeys([*clean_record.get("cross_refs", []), *section_candidates]))

            enriched = {
                **clean_record,
                "source": {
                    "parse_source": source_used,
                    "source_jsonl": str(source_path),
                    "source_url": manifest_row.get("source_url"),
                    "pdf_file_name": manifest_row.get("file_name"),
                },
                "quality": quality,
                "structure": {
                    "is_table_candidate": is_table_candidate,
                    "section_candidates": section_candidates,
                    "noise_reason": noise_reason,
                },
            }

            if noise_reason and not args.keep_noise:
                rejected_chunks.append(enriched)
                source_report[doc_id]["rejected_chunks"] += 1
                continue

            canonical_chunks.append(clean_record)
            enriched_chunks.append(enriched)
            source_report[doc_id]["kept_chunks"] += 1
            if is_table_candidate:
                source_report[doc_id]["table_candidates"] += 1

    enriched_by_chunk_id = {chunk["chunk_id"]: chunk for chunk in enriched_chunks}
    pages = build_pages(canonical_chunks)
    tables = build_table_records(canonical_chunks, enriched_by_chunk_id)
    nodes, links, graph_events = build_graph(manifest=manifest, chunks=canonical_chunks, pages=pages, tables=tables)

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "source_dir": str(source_dir),
        "fallback_dir": str(fallback_dir),
        "output_dir": str(output_dir),
        "publish_dir": None if args.no_publish else str(publish_dir),
        "document_count": len(manifest),
        "kept_chunk_count": len(canonical_chunks),
        "rejected_chunk_count": len(rejected_chunks),
        "page_count": len(pages),
        "table_candidate_count": len(tables),
        "graph_node_count": len(nodes),
        "graph_link_count": len(links),
        "source_report": source_report,
        "chunk_type_counts": Counter(chunk["chunk_type"] for chunk in canonical_chunks),
    }
    write_artifacts(
        output_dir,
        canonical_chunks=canonical_chunks,
        enriched_chunks=enriched_chunks,
        rejected_chunks=rejected_chunks,
        pages=pages,
        tables=tables,
        nodes=nodes,
        links=links,
        graph_events=graph_events,
        report=report,
    )
    if not args.no_publish:
        write_artifacts(
            publish_dir,
            canonical_chunks=canonical_chunks,
            enriched_chunks=enriched_chunks,
            rejected_chunks=rejected_chunks,
            pages=pages,
            tables=tables,
            nodes=nodes,
            links=links,
            graph_events=graph_events,
            report=report,
        )
    write_json(results_dir / "pilot14_structure_summary.json", report)

    markdown_lines = [
        "# Pilot14 Structure Summary",
        "",
        f"- Documents: {report['document_count']}",
        f"- Kept chunks: {report['kept_chunk_count']}",
        f"- Rejected chunks: {report['rejected_chunk_count']}",
        f"- Pages: {report['page_count']}",
        f"- Table candidates: {report['table_candidate_count']}",
        f"- Graph nodes: {report['graph_node_count']}",
        f"- Graph links: {report['graph_link_count']}",
        "",
        "## Per Document",
        "",
        "| doc_id | source | input | kept | rejected | table candidates |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for doc_id, item in sorted(source_report.items()):
        markdown_lines.append(
            f"| {doc_id} | {item['source_used']} | {item['input_chunks']} | {item['kept_chunks']} | {item['rejected_chunks']} | {item['table_candidates']} |"
        )
    (results_dir / "pilot14_structure_summary.md").write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2, default=dict))


if __name__ == "__main__":
    main()
