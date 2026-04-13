from pathlib import Path

from app.ingest.parser import parse_document as legacy_parse_document
from app.ingestion.parser_base import DocumentParser, ParsedDocument, ParserCapabilities


class FallbackDocumentParser(DocumentParser):
    provider_name = "fallback"
    capabilities = ParserCapabilities(
        provider_name="fallback",
        supports_markdown_output=False,
        supports_layout_hierarchy=False,
        supports_table_extraction=True,
        supports_page_level_output=True,
    )

    def parse(self, source_path: str | Path) -> ParsedDocument:
        source_path = Path(source_path)
        pages = legacy_parse_document(str(source_path))
        return ParsedDocument(
            source_path=str(source_path),
            parser_provider=self.provider_name,
            pages=pages,
            parser_metadata={
                "page_count": len(pages),
                "strategy": "legacy_fallback_parser",
            },
        )
