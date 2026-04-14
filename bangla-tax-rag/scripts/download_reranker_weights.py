from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from huggingface_hub import hf_hub_download


def main() -> None:
    repo_id = "BAAI/bge-reranker-v2-m3"
    for filename in ("pytorch_model.bin", "model.safetensors"):
        try:
            path = hf_hub_download(repo_id=repo_id, filename=filename)
            print({"status": "downloaded", "filename": filename, "path": path})
            return
        except Exception as exc:
            print({"status": "failed", "filename": filename, "error": str(exc)})
    raise SystemExit("Could not download reranker weight file.")


if __name__ == "__main__":
    main()
