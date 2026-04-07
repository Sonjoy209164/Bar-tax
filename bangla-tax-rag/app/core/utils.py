from pathlib import Path


def ensure_directory(path_value: str) -> Path:
    path = Path(path_value)
    path.mkdir(parents=True, exist_ok=True)
    return path
