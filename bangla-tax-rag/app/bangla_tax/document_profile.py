from __future__ import annotations

import re
from pathlib import Path

from app.core.utils import normalize_bangla_digits, normalize_whitespace

PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "binary/octet-stream",
}


def sanitize_document_id(value: str, *, fallback: str = "bangla-tax-document") -> str:
    normalized = normalize_bangla_digits(value).strip().lower()
    normalized = Path(normalized).stem if normalized.endswith(".pdf") else normalized
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or fallback


def derive_document_id(filename: str | None, *, fallback: str) -> str:
    if not filename:
        return sanitize_document_id(fallback, fallback=fallback)
    return sanitize_document_id(Path(filename).name, fallback=fallback)


def derive_document_title(filename: str | None, *, default_title: str) -> str:
    if not filename:
        return default_title
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    title = normalize_whitespace(stem)
    return title or default_title


def validate_pdf_upload(filename: str | None, content_type: str | None) -> None:
    if not filename or not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported for Bangla tax ingestion.")
    if content_type and content_type.lower() not in PDF_CONTENT_TYPES:
        raise ValueError(f"Unsupported upload content type: {content_type}")
