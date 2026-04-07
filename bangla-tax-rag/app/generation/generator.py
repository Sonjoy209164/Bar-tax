def generate_answer(query: str, retrieved_chunks: list[dict[str, str | float]]) -> str:
    if not retrieved_chunks:
        return f"No evidence retrieved for query: {query}"
    top_chunk = retrieved_chunks[0]
    return f"Placeholder answer for '{query}' based on {top_chunk['chunk_id']}."
