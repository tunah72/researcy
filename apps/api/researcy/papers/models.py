from uuid import UUID

from pydantic import BaseModel


MAX_SEARCH_LENGTH = 200


class Paper(BaseModel):
    paper_id: UUID
    title: str | None
    authors: list[str] | None
    year: int | None
    source: str
    stage: str
    active_version_id: UUID
    source_version: str | None
    screening_warning: str | None


class PaperListResponse(BaseModel):
    papers: list[Paper]
    request_id: str


class PaperDetailResponse(Paper):
    request_id: str


class ArxivImportRequest(BaseModel):
    arxiv_id_or_url: str


class IntakeResponse(BaseModel):
    paper_id: UUID
    document_version: UUID
    job_id: UUID
    stage: str
    screening_warning: str | None = None
    source_version: str | None = None
    arxiv_version: str | None = None
    document_version_id: UUID | None = None
    request_id: str
