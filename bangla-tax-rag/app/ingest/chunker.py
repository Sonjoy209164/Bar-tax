def chunk_text(content: str, chunk_size: int) -> list[str]:
    if not content:
        return []
    return [content[index:index + chunk_size] for index in range(0, len(content), chunk_size)]
