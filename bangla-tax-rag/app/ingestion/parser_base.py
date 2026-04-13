from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.schemas import ParsedPage
from app.core.settings import get_settings
from app.core.utils import extract_section_ids, extract_sro_ids, extract_tax_years, normalize_text


class ParserCapabilities(BaseModel):
    provider_name: str
    supports_markdown_output: bool = False
    supports_layout_hierarchy: bool = False
    supports_table_extraction: bool = False
    supports_page_level_output: bool = True


class ParsedDocument(BaseModel):
    source_path: str
    parser_provider: str
    pages: list[ParsedPage] = Field(default_factory=list)
    raw_markdown: str | None = None
    parser_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentParser(ABC):
    provider_name: str = "base"
    capabilities: ParserCapabilities = ParserCapabilities(provider_name="base")

    @property
    def is_available(self) -> bool:
        return True

    @abstractmethod
    def parse(self, source_path: str | Path) -> ParsedDocument:
        raise NotImplementedError


def build_parsed_page_from_text(page_no: int, raw_text: str) -> ParsedPage:
    from app.ingest.parser import _detect_headings, _is_appendix_page, _looks_like_table

    normalized_text = normalize_text(raw_text)
    headings = _detect_headings(raw_text)
    return ParsedPage(
        page_no=page_no,
        raw_text=raw_text,
        normalized_text=normalized_text,
        headings=headings,
        section_markers=extract_section_ids(raw_text),
        tax_years=extract_tax_years(raw_text),
        sro_ids=extract_sro_ids(raw_text),
        is_appendix=_is_appendix_page(raw_text, headings),
        is_example=any("example" in heading.lower() or "উদাহরণ" in heading for heading in headings)
        or "example" in normalized_text.lower()
        or "উদাহরণ" in normalized_text,
        is_table_like=_looks_like_table(raw_text),
        line_count=len([line for line in raw_text.splitlines() if line.strip()]),
    )


def build_parser(
    provider: str | None = None,
    *,
    allow_fallback: bool = True,
    **kwargs: Any,
) -> DocumentParser:
    from app.ingestion.fallback_parser import FallbackDocumentParser
    from app.ingestion.llamaparse_parser import LlamaParseDocumentParser

    settings = get_settings()
    selected_provider = (provider or settings.parser_provider).strip().lower()

    if selected_provider == "llamaparse":
        parser = LlamaParseDocumentParser(
            api_key=kwargs.get("api_key") or settings.llama_cloud_api_key,
            result_type=kwargs.get("result_type") or settings.llama_parse_result_type,
            verbose=kwargs.get("verbose", False),
        )
        if parser.is_available or not allow_fallback:
            return parser
        return FallbackDocumentParser()

    if selected_provider == "fallback":
        return FallbackDocumentParser()

    raise ValueError(f"Unsupported parser provider: {selected_provider}")
