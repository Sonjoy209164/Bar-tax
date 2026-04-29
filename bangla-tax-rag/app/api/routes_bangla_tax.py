from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.bangla_tax import BanglaTaxIngestPathRequest, BanglaTaxUploadResponse, get_bangla_tax_bot_service
from app.services.query_service import QueryRequest, QueryResponse
from app.services.runtime_service import AgenticRuntimeStatus

router = APIRouter(prefix="/bangla-tax", tags=["bangla-tax"])


@router.get("/status", response_model=AgenticRuntimeStatus)
async def get_bangla_tax_status() -> AgenticRuntimeStatus:
    return get_bangla_tax_bot_service().status()


@router.post("/upload", response_model=BanglaTaxUploadResponse)
async def upload_bangla_tax_pdf(
    file: UploadFile = File(...),
    document_id: str | None = Form(default=None),
    act_title: str | None = Form(default=None),
    ocr_enabled: bool | None = Form(default=None),
    ocr_language: str = Form(default="ben+eng"),
    ocr_force: bool = Form(default=True),
) -> BanglaTaxUploadResponse:
    try:
        return await get_bangla_tax_bot_service().ingest_upload(
            file,
            document_id=document_id,
            act_title=act_title,
            ocr_enabled=ocr_enabled,
            ocr_language=ocr_language,
            ocr_force=ocr_force,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_pdf_upload", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "bangla_tax_ingest_failed", "message": str(exc)},
        ) from exc


@router.post("/ingest", response_model=BanglaTaxUploadResponse)
async def ingest_bangla_tax_path(request: BanglaTaxIngestPathRequest) -> BanglaTaxUploadResponse:
    try:
        return get_bangla_tax_bot_service().ingest_path(
            request.source_path,
            document_id=request.document_id,
            act_title=request.act_title,
            ocr_enabled=request.ocr_enabled,
            ocr_language=request.ocr_language,
            ocr_force=request.ocr_force,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_pdf", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "bangla_tax_ingest_failed", "message": str(exc)},
        ) from exc


@router.post("/query", response_model=QueryResponse)
async def query_bangla_tax_bot(request: QueryRequest) -> QueryResponse:
    try:
        return get_bangla_tax_bot_service().query(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "bangla_tax_runtime_not_ready", "message": str(exc)},
        ) from exc
