def format_citations(retrieved_chunks: list[dict[str, str | float]]) -> list[str]:
    return [str(chunk["chunk_id"]) for chunk in retrieved_chunks]
