from pathlib import Path


def parse_document(source_path: str) -> dict[str, str]:
    path = Path(source_path)
    content = f"Placeholder content parsed from {path.name}"
    return {"document_name": path.name, "content": content}
