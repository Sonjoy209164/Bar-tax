def sparse_search(query: str, top_k: int) -> list[dict[str, str | float]]:
    return [
        {
            "chunk_id": f"sparse-{index}",
            "content": f"Sparse match {index + 1} for: {query}",
            "score": round(0.9 - (index * 0.1), 3),
        }
        for index in range(top_k)
    ]
