#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Runtime /config ==="
curl -s http://127.0.0.1:8000/config | .venv/bin/python -m json.tool

echo
echo "=== Dense metadata ==="
.venv/bin/python - <<'PY'
import json
from pathlib import Path

import numpy as np

meta = json.loads(Path("indexes/dense/metadata.json").read_text())
embeddings = np.load("indexes/dense/embeddings.npy")

print(json.dumps(meta, indent=2))
print()
print(
    json.dumps(
        {
            "embedding_shape": list(embeddings.shape),
            "embedding_dtype": str(embeddings.dtype),
            "first_vector_norm": float(np.linalg.norm(embeddings[0])) if len(embeddings) else None,
        },
        indent=2,
    )
)
PY
