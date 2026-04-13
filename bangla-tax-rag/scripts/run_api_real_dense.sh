#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-transformers}"
export EMBEDDING_MODEL_NAME="${EMBEDDING_MODEL_NAME:-BAAI/bge-m3}"
export RERANKER_PROVIDER="${RERANKER_PROVIDER:-transformers}"
export RERANKER_MODEL_NAME="${RERANKER_MODEL_NAME:-BAAI/bge-reranker-v2-m3}"

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
