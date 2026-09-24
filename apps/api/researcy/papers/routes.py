import hashlib
from uuid import UUID

from fastapi import APIRouter, File, Header, Query, Request, Response, UploadFile

from ..auth.sessions import get_current_user, require_csrf
from ..db import get_conn
from ..errors import APIError
from . import intake
from .models import (
    MAX_SEARCH_LENGTH,
    ArxivImportRequest,
    IntakeResponse,
    PaperDetailResponse,
    PaperListResponse,
)
from .repository import get_paper, list_papers, take_import_slot

router = APIRouter()


@router.get("/api/papers", response_model=PaperListResponse)
def papers(
    request: Request,
    search: str | None = Query(default=None, max_length=MAX_SEARCH_LENGTH),
):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        rows = list_papers(conn, owner_id, search)
    return {"papers": rows, "request_id": request.state.request_id}


@router.get("/api/papers/{paper_id}", response_model=PaperDetailResponse)
def paper_detail(request: Request, paper_id: UUID):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        paper = get_paper(conn, owner_id, paper_id)
    if paper is None:
        raise APIError(404, "NOT_FOUND", "The requested resource was not found.")
    return {**paper, "request_id": request.state.request_id}


@router.post("/api/papers/upload", response_model=IntakeResponse, status_code=202)
async def upload_paper(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        require_csrf(request, conn, owner_id)

    validated_key = intake.validate_idempotency_key(idempotency_key)
    max_bytes = request.app.state.settings.max_upload_bytes
    temp_path, request_digest, byte_count = await intake.stream_upload_to_temp(file, max_bytes)

    try:
        with intake.serialize_key(owner_id, validated_key):
            with get_conn() as conn:
                existing = intake.check_idempotency(
                    conn, owner_id, validated_key, "upload", request_digest
                )
            if existing is not None:
                response.status_code = 200
                return {
                    "paper_id": existing.paper_id,
                    "document_version": existing.document_version_id,
                    "job_id": existing.job_id,
                    "stage": existing.stage,
                    "screening_warning": existing.screening_warning,
                    "source_version": existing.source_version,
                    "arxiv_version": existing.source_version,
                    "document_version_id": existing.document_version_id,
                    "request_id": request.state.request_id,
                }

            with get_conn() as conn:
                take_import_slot(conn, owner_id)
                conn.commit()

            with get_conn() as conn:
                result = intake.accept_pdf(
                    conn=conn,
                    owner_id=owner_id,
                    key=validated_key,
                    operation="upload",
                    request_digest=request_digest,
                    source="upload",
                    metadata=intake.IntakeMetadata(
                        fallback_title=intake.sanitize_filename_title(file.filename),
                        source_media_type=file.content_type,
                    ),
                    screened_path=temp_path,
                )
                conn.commit()
    finally:
        temp_path.unlink(missing_ok=True)

    response.status_code = 200 if result.is_replay else 202
    return {
        "paper_id": result.paper_id,
        "document_version": result.document_version_id,
        "job_id": result.job_id,
        "stage": result.stage,
        "screening_warning": result.screening_warning,
        "source_version": result.source_version,
        "arxiv_version": result.source_version,
        "document_version_id": result.document_version_id,
        "request_id": request.state.request_id,
    }


@router.post("/api/papers/arxiv", response_model=IntakeResponse, status_code=202)
def import_arxiv(
    request: Request,
    response: Response,
    body: ArxivImportRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        require_csrf(request, conn, owner_id)

    validated_key = intake.validate_idempotency_key(idempotency_key)
    canonical_id, explicit_version = intake.parse_arxiv_reference(body.arxiv_id_or_url)
    request_digest = hashlib.sha256(body.arxiv_id_or_url.strip().encode("utf-8")).digest()

    with intake.serialize_key(owner_id, validated_key):
        with get_conn() as conn:
            existing = intake.check_idempotency(
                conn, owner_id, validated_key, "arxiv", request_digest
            )
        if existing is not None:
            response.status_code = 200
            return {
                "paper_id": existing.paper_id,
                "document_version": existing.document_version_id,
                "job_id": existing.job_id,
                "stage": existing.stage,
                "screening_warning": existing.screening_warning,
                "source_version": existing.source_version,
                "arxiv_version": existing.source_version,
                "document_version_id": existing.document_version_id,
                "request_id": request.state.request_id,
            }

        with get_conn() as conn:
            owned = intake.check_owned_arxiv(conn, owner_id, canonical_id, explicit_version)
        if owned is not None:
            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO import_idempotency (
                        owner_id, idempotency_key, operation, request_digest,
                        paper_id, document_version_id, job_id
                    ) VALUES (%s, %s, 'arxiv', %s, %s, %s, %s)
                    ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                    """,
                    (
                        owner_id,
                        validated_key,
                        request_digest,
                        owned.paper_id,
                        owned.document_version_id,
                        owned.job_id,
                    ),
                )
                conn.commit()
            response.status_code = 200
            return {
                "paper_id": owned.paper_id,
                "document_version": owned.document_version_id,
                "job_id": owned.job_id,
                "stage": owned.stage,
                "screening_warning": owned.screening_warning,
                "source_version": owned.source_version,
                "arxiv_version": owned.source_version,
                "document_version_id": owned.document_version_id,
                "request_id": request.state.request_id,
            }

        with get_conn() as conn:
            take_import_slot(conn, owner_id)
            conn.commit()

        acquisition = intake.fetch_official_arxiv(
            canonical_id,
            explicit_version=explicit_version,
            byte_limit=request.app.state.settings.max_upload_bytes,
        )
        try:
            with get_conn() as conn:
                result = intake.accept_pdf(
                    conn=conn,
                    owner_id=owner_id,
                    key=validated_key,
                    operation="arxiv",
                    request_digest=request_digest,
                    source="arxiv",
                    metadata=intake.IntakeMetadata(
                        title=acquisition.metadata.title,
                        authors=acquisition.metadata.authors,
                        year=acquisition.metadata.year,
                        source_version=acquisition.source_version,
                        canonical_arxiv_id=canonical_id,
                        source_url=acquisition.source_url,
                    ),
                    screened_path=acquisition.pdf_path,
                )
                conn.commit()
        finally:
            acquisition.pdf_path.unlink(missing_ok=True)

    response.status_code = 200 if result.is_replay else 202
    return {
        "paper_id": result.paper_id,
        "document_version": result.document_version_id,
        "job_id": result.job_id,
        "stage": result.stage,
        "screening_warning": result.screening_warning,
        "source_version": result.source_version,
        "arxiv_version": result.source_version,
        "document_version_id": result.document_version_id,
        "request_id": request.state.request_id,
    }
