from uuid import UUID

from pydantic import BaseModel, Field

from ..ingestion.presentation import Preparation, ProcessingStage
from ..ingestion.jobs import MAX_SAFE_INTEGER


MAX_SEARCH_LENGTH = 200


class Paper(BaseModel):
    paper_id: UUID
    title: str | None
    authors: list[str] | None
    year: int | None
    source: str
    stage: ProcessingStage
    active_version_id: UUID
    source_version: str | None
    screening_warning: str | None
    job_id: UUID
    retry_revision: int=Field(ge=0,le=MAX_SAFE_INTEGER)
    preparation: Preparation

class PaperListResponse(BaseModel):
    papers: list[Paper]
    request_id: str


class ReaderPage(BaseModel):
    page_index: int
    media_box: tuple[float, float, float, float]
    crop_box: tuple[float, float, float, float]
    rotation: int


class ReaderOutlineEntry(BaseModel):
    title: str
    page: int


class ReaderDocument(BaseModel):
    document_version: UUID
    source_sha256: str
    pdf_url: str
    pages: list[ReaderPage]
    outline: list[ReaderOutlineEntry]


class PaperDetailResponse(Paper):
    request_id: str
    reader: ReaderDocument | None = None


class ArxivImportRequest(BaseModel):
    arxiv_id_or_url: str


class IntakeResponse(BaseModel):
    paper_id: UUID
    document_version: UUID
    job_id: UUID
    stage: ProcessingStage
    screening_warning: str | None = None
    source_version: str | None = None
    arxiv_version: str | None = None
    document_version_id: UUID | None = None
    request_id: str
