import hashlib
from functools import partial
from uuid import UUID
import time

from fastapi import APIRouter, Header, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
import anyio
import psycopg

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
from .pdf import reader_document, open_owned_pdf, PDFResponse, bounded_database

router = APIRouter()
PDF_WALL_SECONDS = 30


def _authenticate_mutation(request: Request) -> UUID:
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        require_csrf(request, conn, owner_id)
        return owner_id


def _accept_uploaded_pdf(
    *,
    owner_id: UUID,
    key: str,
    request_digest: bytes,
    fallback_title: str,
    source_media_type: str | None,
    temp_path,
):
    with intake.serialize_key(owner_id, key):
        with get_conn() as conn:
            existing = intake.check_idempotency(
                conn, owner_id, key, "upload", request_digest
            )
        if existing is not None:
            return existing

        with get_conn() as conn:
            take_import_slot(conn, owner_id)
            conn.commit()

        with get_conn() as conn:
            result = intake.accept_pdf(
                conn=conn,
                owner_id=owner_id,
                key=key,
                operation="upload",
                request_digest=request_digest,
                source="upload",
                metadata=intake.IntakeMetadata(
                    fallback_title=fallback_title,
                    source_media_type=source_media_type,
                ),
                screened_path=temp_path,
            )
            conn.commit()
            return result


async def _parse_upload(request: Request) -> UploadFile:
    max_body_bytes = request.app.state.settings.max_upload_request_bytes
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > max_body_bytes
        except ValueError as exc:
            raise APIError(
                400, "INVALID_MULTIPART", "Content-Length must be a valid integer."
            ) from exc
        if too_large:
            raise APIError(
                413,
                "PDF_TOO_LARGE",
                "The PDF exceeds the configured size limit.",
            )

    form = await request.form(max_files=1, max_fields=1)
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise APIError(422, "FILE_REQUIRED", "A PDF file is required.")
    return file


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
def paper_detail(request: Request, paper_id: UUID, document_version: UUID | None = None):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        paper = get_paper(conn, owner_id, paper_id)
        if paper is None:
            raise APIError(404, "NOT_FOUND", "The requested resource was not found.")
        conn.commit()
        reader = None
        if document_version is not None or paper["stage"] == "ready":
            reader = reader_document(conn, owner_id, paper_id, document_version)
    return {**paper, "reader": reader, "request_id": request.state.request_id}


@router.head(
    "/api/papers/{paper_id}/versions/{document_version}/pdf",
    response_class=Response,
    responses={200: {"description": "Authorized original PDF metadata"},
               206: {"description": "Authorized single-range PDF metadata"},
               416: {"description": "Invalid or unsatisfiable PDF range"}},
)
@router.get(
    "/api/papers/{paper_id}/versions/{document_version}/pdf",
    response_class=Response,
    responses={
        200: {"description": "Authorized original PDF",
              "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
        206: {"description": "Authorized single range of the original PDF",
              "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
        416: {"description": "Invalid or unsatisfiable PDF range"},
    },
)
async def paper_pdf(request: Request, paper_id: UUID, document_version: UUID,
                    download: str | None = None):
    deadline = time.monotonic()+PDF_WALL_SECONDS

    def authorize():
        with get_conn() as conn:
            with bounded_database(conn, deadline):
                owner_id = get_current_user(request, conn)
                conn.commit()
                return owner_id

    try:
        with anyio.fail_after(max(0, deadline-time.monotonic())):
            owner_id = await anyio.to_thread.run_sync(authorize, abandon_on_cancel=True)
            if download not in (None, "1"):
                raise APIError(422, "INVALID_REQUEST", "The download option is invalid.")
            ranges = request.headers.getlist("range")
            validators = request.headers.getlist("if-range")
            stream = await anyio.to_thread.run_sync(
                partial(open_owned_pdf, owner_id, paper_id, document_version,
                        ",".join(ranges) if ranges else None,
                        validators[0] if len(validators) == 1 else ('"invalid"' if validators else None),
                        download=download == "1", head=request.method == "HEAD", deadline=deadline),
                abandon_on_cancel=True,
            )
        if time.monotonic() >= deadline:
            await stream.aclose()
            raise TimeoutError()
    except TimeoutError:
        raise APIError(503, "ORIGINAL_STORAGE_UNAVAILABLE", "The original PDF is unavailable.") from None
    except psycopg.Error:
        if time.monotonic() >= deadline:
            raise APIError(503, "ORIGINAL_STORAGE_UNAVAILABLE", "The original PDF is unavailable.") from None
        raise
    return PDFResponse(stream, request.state.request_id)


@router.post("/api/papers/upload", response_model=IntakeResponse, status_code=202)
async def upload_paper(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    owner_id = await run_in_threadpool(_authenticate_mutation, request)
    validated_key = intake.validate_idempotency_key(idempotency_key)
    file = await _parse_upload(request)
    filename = intake.sanitize_filename_title(file.filename)
    source_media_type = file.content_type
    temp_path = None
    try:
        temp_path, request_digest, _ = await intake.stream_upload_to_temp(
            file, request.app.state.settings.max_upload_bytes
        )
        result = await run_in_threadpool(
            _accept_uploaded_pdf,
            owner_id=owner_id,
            key=validated_key,
            request_digest=request_digest,
            fallback_title=filename,
            source_media_type=source_media_type,
            temp_path=temp_path,
        )
    finally:
        await file.close()
        if temp_path is not None:
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
    request_digest = hashlib.sha256(
        body.arxiv_id_or_url.strip().encode("utf-8")
    ).digest()

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
            owned = intake.check_owned_arxiv(
                conn, owner_id, canonical_id, explicit_version
            )
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
            requested_version=explicit_version,
            max_bytes=request.app.state.settings.max_upload_bytes,
            request_id=request.state.request_id,
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
                        requested_version=explicit_version,
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
