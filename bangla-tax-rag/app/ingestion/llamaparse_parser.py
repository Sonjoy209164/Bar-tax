from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.ingestion.parser_base import (
    DocumentParser,
    ParsedDocument,
    ParserCapabilities,
    build_parsed_page_from_text,
)


def _load_llamaparse_class():  # type: ignore[no-untyped-def]
    try:
        from llama_parse import LlamaParse
    except Exception:
        return None
    return LlamaParse


class LlamaParseDocumentParser(DocumentParser):
    provider_name = "llamaparse"
    capabilities = ParserCapabilities(
        provider_name="llamaparse",
        supports_markdown_output=True,
        supports_layout_hierarchy=True,
        supports_table_extraction=True,
        supports_page_level_output=True,
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        result_type: str = "markdown",
        verbose: bool = False,
    ) -> None:
        self.api_key = api_key or os.getenv("LLAMA_CLOUD_API_KEY")
        self.result_type = result_type
        self.verbose = verbose

    @property
    def is_available(self) -> bool:
        return bool(self.api_key) and _load_llamaparse_class() is not None

    def parse(self, source_path: str | Path) -> ParsedDocument:
        if not self.api_key:
            raise RuntimeError("LLAMA_CLOUD_API_KEY is required for the llamaparse provider")
        parser_cls = _load_llamaparse_class()
        if parser_cls is None:
            raise RuntimeError("llama_parse is not installed")

        source_path = Path(source_path)
        parser = parser_cls(
            api_key=self.api_key,
            result_type=self.result_type,
            verbose=self.verbose,
        )
        documents = parser.load_data(str(source_path))
        pages, raw_markdown = self._convert_documents_to_pages(documents)
        return ParsedDocument(
            source_path=str(source_path),
            parser_provider=self.provider_name,
            pages=pages,
            raw_markdown=raw_markdown,
            parser_metadata={
                "page_count": len(pages),
                "strategy": "llamaparse",
                "result_type": self.result_type,
            },
        )

    def _convert_documents_to_pages(self, documents: list[Any]) -> tuple[list, str]:
        ordered_pages: dict[int, str] = {}
        markdown_segments: list[str] = []
        for index, document in enumerate(documents, start=1):
            text = getattr(document, "text", None)
            if text is None and hasattr(document, "get_content"):
                text = document.get_content()  # type: ignore[no-untyped-call]
            metadata = getattr(document, "metadata", None) or {}
            page_no = (
                metadata.get("page_number")
                or metadata.get("page")
                or metadata.get("page_label")
                or index
            )
            try:
                page_no = int(page_no)
            except (TypeError, ValueError):
                page_no = index
            raw_text = str(text or "").strip()
            if not raw_text:
                continue
            ordered_pages[page_no] = raw_text
            markdown_segments.append(raw_text)

        pages = [
            build_parsed_page_from_text(page_no=page_no, raw_text=raw_text)
            for page_no, raw_text in sorted(ordered_pages.items())
        ]
        return pages, "\n\n".join(markdown_segments)
