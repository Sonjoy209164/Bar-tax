def dense_search(query: str, top_k: int) -> list[dict[str, str | float]]:
    return [
        {
            "chunk_id": f"dense-{index}",
            "content": f"Dense match {index + 1} for: {query}",
            "score": round(0.85 - (index * 0.08), 3),
        }
        for index in range(top_k)
    ]
