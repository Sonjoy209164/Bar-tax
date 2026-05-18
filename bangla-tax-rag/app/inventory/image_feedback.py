from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


CorrectionType = Literal["exact_product", "same_design", "similar", "no_match"]

_FAILURE_PATH = Path("data/feedback/image_search_failures.jsonl")
_CORRECTION_PATH = Path("data/feedback/image_search_corrections.jsonl")
_LOCK = threading.Lock()


@dataclass(frozen=True)
class ImageSearchFailure:
    query_text: str
    session_id: str | None
    query_image_id: str | None
    decision_label: str | None
    primary_product_id: str | None
    top_product_ids: list[str]
    reason: str
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class ImageSearchCorrection:
    query_image_id: str
    correction_type: CorrectionType
    correct_product_id: str | None = None
    wrong_product_id: str | None = None
    notes: str = ""
    session_id: str | None = None
    query_text: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def save_image_search_failure(failure: ImageSearchFailure) -> None:
    append_jsonl(_FAILURE_PATH, asdict(failure))


def save_image_search_correction(correction: ImageSearchCorrection) -> None:
    append_jsonl(_CORRECTION_PATH, asdict(correction))


def list_image_search_failures(limit: int = 50) -> list[dict[str, Any]]:
    return read_jsonl_tail(_FAILURE_PATH, limit=limit)


def list_image_search_corrections(limit: int = 50) -> list[dict[str, Any]]:
    return read_jsonl_tail(_CORRECTION_PATH, limit=limit)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_jsonl_tail(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return entries[-max(1, limit):]
