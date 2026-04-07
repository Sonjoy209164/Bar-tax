from app.retrieval.dense import dense_search
from app.retrieval.filters import deduplicate_results
from app.retrieval.sparse import sparse_search


def hybrid_search(query: str, top_k: int = 5) -> list[dict[str, str | float]]:
    combined_results = sparse_search(query, top_k=top_k) + dense_search(query, top_k=top_k)
    unique_results = deduplicate_results(combined_results)
    return unique_results[:top_k]
