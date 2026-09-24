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
