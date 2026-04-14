import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging
from app.retrieval.dense import dense_search
from app.retrieval.hybrid import run_hybrid_retrieval
from app.retrieval.sparse import load_sparse_index, search_sparse_index


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a demo query against sparse, dense, or hybrid retrieval.")
    parser.add_argument("--index-dir", default="indexes/sparse")
    parser.add_argument("--dense-index-dir", default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", choices=["sparse", "dense", "hybrid"], default="sparse")
    parser.add_argument("--tax-year", default=None)
    parser.add_argument("--doc-type", default=None)
    parser.add_argument("--authority-level-min", default=None)
    parser.add_argument("--chunk-type", default=None)
    return parser


def _print_hits(label: str, hits: list[object]) -> None:
    print(f"\n{label}")
    if not hits:
        print("No hits found.")
        return
    for position, hit in enumerate(hits, start=1):
        print(f"\n[{position}] score={hit.score} chunk_id={hit.chunk_id}")
        print(f"doc={hit.doc_title} page={hit.page_no} authority={hit.authority_level} tax_year={hit.tax_year}")
        print(f"section={hit.section_id} subsection={hit.subsection_id} chunk_type={hit.chunk_type}")
        print(f"headings={' > '.join(hit.heading_path) if hit.heading_path else '-'}")
        print(hit.original_text[:400])


def main() -> None:
    configure_logging()
    args = build_argument_parser().parse_args()
    dense_index_dir = args.dense_index_dir or (
        args.index_dir.replace("sparse", "dense") if args.index_dir.endswith("sparse") else args.index_dir
    )
    if args.mode == "sparse":
        index = load_sparse_index(args.index_dir)
        response = search_sparse_index(
            query=args.query,
            index=index,
            top_k=args.top_k,
            tax_year=args.tax_year,
            doc_type=args.doc_type,
            authority_level_min=args.authority_level_min,
            chunk_type=args.chunk_type,
        )
        print(f"Mode: sparse")
        print(f"Query: {response.query}")
        print(f"Normalized: {response.signals.normalized_query}")
        _print_hits("Sparse Hits", response.hits)
        return
    if args.mode == "dense":
        dense_hits = [
            type("DenseHit", (), hit)
            for hit in dense_search(
                args.query,
                top_k=args.top_k,
                tax_year=args.tax_year,
                doc_type=args.doc_type,
                authority_level_min=args.authority_level_min,
                chunk_type=args.chunk_type,
                index_dir=dense_index_dir,
            )
        ]
        print("Mode: dense")
        print(f"Query: {args.query}")
        _print_hits("Dense Hits", dense_hits)
        return

    response = run_hybrid_retrieval(
        query=args.query,
        sparse_top_k=max(args.top_k * 2, 10),
        dense_top_k=max(args.top_k * 2, 10),
        final_top_k=args.top_k,
        tax_year=args.tax_year,
        doc_type=args.doc_type,
        authority_level_min=args.authority_level_min,
        chunk_type=args.chunk_type,
        index_dir=args.index_dir,
        dense_index_dir=dense_index_dir,
    )
    print("Mode: hybrid")
    print(f"Query: {response.query_text}")
    print(f"Analyzed Query: {response.analyzed_query.model_dump()}")
    _print_hits("Sparse Top Hits", response.sparse_hits[:args.top_k])
    _print_hits("Dense Top Hits", response.dense_hits[:args.top_k])
    _print_hits("Hybrid Final Hits", response.final_hits)
    if response.conflict_notes:
        print("\nConflict Notes")
        for note in response.conflict_notes:
            print(f"- {note}")
    print(f"\nEvidence Summary: {response.evidence_summary}")


if __name__ == "__main__":
    main()
