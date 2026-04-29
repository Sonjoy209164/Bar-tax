from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable

from fastapi import UploadFile

from app.bangla_tax.document_profile import (
    derive_document_id,
    derive_document_title,
    sanitize_document_id,
    validate_pdf_upload,
)
from app.bangla_tax.models import BanglaTaxUploadResponse
from app.core.settings import Settings, get_settings
from app.ingest.parser import prepare_pdf_for_ingestion
from app.services.ingest_service import IngestServiceResult
from app.services.query_service import QueryRequest, QueryResponse
from app.services.runtime_service import AgenticRuntime, AgenticRuntimeStatus

RuntimeFactory = Callable[[], AgenticRuntime]


class BanglaTaxBotService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._runtime_factory = runtime_factory
        self._runtime: AgenticRuntime | None = None

    def runtime(self) -> AgenticRuntime:
        if self._runtime_factory is not None:
            return self._runtime_factory()
        if self._runtime is None:
            store_dir = Path(self.settings.agentic_store_dir) / "bangla_tax"
            self._runtime = AgenticRuntime(
                store_dir=store_dir,
                vector_namespace="bangla-tax",
                local_vector_store_path=store_dir / "local_vectors.jsonl",
                trace_dir=Path(self.settings.trace_dir) / "bangla_tax",
                query_top_k=12,
            )
        return self._runtime

    def status(self) -> AgenticRuntimeStatus:
        return self.runtime().status()

    def query(self, request: QueryRequest) -> QueryResponse:
        return self.runtime().query(request)

    async def ingest_upload(
        self,
        upload: UploadFile,
        *,
        document_id: str | None = None,
        act_title: str | None = None,
        ocr_enabled: bool | None = None,
        ocr_language: str = "ben+eng",
        ocr_force: bool = True,
    ) -> BanglaTaxUploadResponse:
        validate_pdf_upload(upload.filename, upload.content_type)
        resolved_document_id = self._resolve_document_id(document_id, upload.filename)
        source_path = await self._persist_upload(upload, document_id=resolved_document_id)
        resolved_title = act_title or derive_document_title(
            upload.filename,
            default_title=self.settings.bangla_tax_default_title,
        )
        return self.ingest_path(
            source_path,
            document_id=resolved_document_id,
            act_title=resolved_title,
            ocr_enabled=ocr_enabled,
            ocr_language=ocr_language,
            ocr_force=ocr_force,
        )

    def ingest_path(
        self,
        source_path: str | Path,
        *,
        document_id: str | None = None,
        act_title: str | None = None,
        ocr_enabled: bool | None = None,
        ocr_language: str = "ben+eng",
        ocr_force: bool = True,
    ) -> BanglaTaxUploadResponse:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"File not found: {source}")
        if source.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported for Bangla tax ingestion.")

        resolved_document_id = self._resolve_document_id(document_id, source.name)
        resolved_title = act_title or derive_document_title(
            source.name,
            default_title=self.settings.bangla_tax_default_title,
        )
        should_ocr = self.settings.bangla_tax_ocr_enabled if ocr_enabled is None else ocr_enabled
        parse_path, ocr_output_path = self._prepare_source_pdf(
            source,
            document_id=resolved_document_id,
            ocr_enabled=should_ocr,
            ocr_language=ocr_language,
            ocr_force=ocr_force,
        )
        result = self.runtime().ingest(
            parse_path,
            document_id=resolved_document_id,
            act_title=resolved_title,
        )
        return self._build_response(
            result,
            source_path=source,
            ocr_applied=should_ocr,
            ocr_output_path=ocr_output_path,
        )

    def _resolve_document_id(self, document_id: str | None, filename: str | None) -> str:
        if document_id:
            return sanitize_document_id(document_id, fallback=self.settings.bangla_tax_default_document_id)
        return derive_document_id(filename, fallback=self.settings.bangla_tax_default_document_id)

    async def _persist_upload(self, upload: UploadFile, *, document_id: str) -> Path:
        upload_dir = Path(self.settings.bangla_tax_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        target_path = upload_dir / f"{document_id}.pdf"
        with target_path.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if target_path.stat().st_size == 0:
            target_path.unlink(missing_ok=True)
            raise ValueError("Uploaded PDF is empty.")
        return target_path

    def _prepare_source_pdf(
        self,
        source_path: Path,
        *,
        document_id: str,
        ocr_enabled: bool,
        ocr_language: str,
        ocr_force: bool,
    ) -> tuple[Path, Path | None]:
        if not ocr_enabled:
            return source_path, None
        processed_dir = Path(self.settings.processed_data_dir)
        processed_dir.mkdir(parents=True, exist_ok=True)
        ocr_output_path = processed_dir / f"{document_id}.ocr.pdf"
        return prepare_pdf_for_ingestion(
            str(source_path),
            ocr_enabled=True,
            ocr_language=ocr_language,
            ocr_force=ocr_force,
            ocr_output_pdf_path=str(ocr_output_path),
        )

    def _build_response(
        self,
        result: IngestServiceResult,
        *,
        source_path: Path,
        ocr_applied: bool,
        ocr_output_path: Path | None,
    ) -> BanglaTaxUploadResponse:
        return BanglaTaxUploadResponse(
            status="success",
            document_id=result.document_id,
            act_title=result.act_title,
            parser_provider=result.parser_provider,
            source_path=str(source_path),
            graph_path=result.document_store.graph_path,
            bm25_index_dir=result.bm25_index_dir,
            retrieval_chunk_count=result.retrieval_chunk_count,
            reasoning_chunk_count=result.reasoning_chunk_count,
            vector_record_count=result.vector_record_count,
            ocr_applied=ocr_applied,
            ocr_output_pdf_path=str(ocr_output_path) if ocr_output_path else None,
            message="Bangla tax PDF parsed, structured, indexed, and loaded for chatbot queries.",
        )


@lru_cache(maxsize=1)
def get_bangla_tax_bot_service() -> BanglaTaxBotService:
    return BanglaTaxBotService()
