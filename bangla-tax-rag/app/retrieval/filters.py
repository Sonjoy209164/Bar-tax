def deduplicate_results(results: list[dict[str, str | float]]) -> list[dict[str, str | float]]:
    seen_chunk_ids: set[str] = set()
    unique_results: list[dict[str, str | float]] = []
    for result in results:
        chunk_id = str(result["chunk_id"])
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        unique_results.append(result)
    return unique_results
