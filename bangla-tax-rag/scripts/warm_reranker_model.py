from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from huggingface_hub import snapshot_download

from app.core.settings import get_settings
from app.retrieval.reranker import _load_reranker_bundle


def main() -> None:
    settings = get_settings()
    model_name = settings.reranker_model_name
    snapshot_path = snapshot_download(model_name)
    tokenizer, model, device = _load_reranker_bundle(model_name)
    print(
        {
            "status": "ready",
            "model_name": model_name,
            "snapshot_path": snapshot_path,
            "tokenizer": type(tokenizer).__name__,
            "model": type(model).__name__,
            "device": device,
            "provider": settings.reranker_provider,
        }
    )


if __name__ == "__main__":
    main()
