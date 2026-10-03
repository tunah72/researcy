from dataclasses import dataclass
from typing import Literal
from uuid import UUID
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


@dataclass(frozen=True, slots=True)
class ActiveMetadata:
    owner_id: UUID
    paper_id: UUID
    document_version: UUID
    canonical_arxiv_id: str | None
    title: str
    abstract: str | None


@dataclass(frozen=True, slots=True)
class DiscoveryReservation:
    run_id: UUID
    source: ActiveMetadata
    request_id: str


def safe_text(value: str) -> str:
    if not value.strip() or any(unicodedata.category(c) in {'Cs','Cc'} and c not in '\n\r\t' for c in value):
        raise ValueError('Unsafe or empty text.')
    value.encode('utf-8')
    return value


class SearchArxivAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    next_action: Literal['search_arxiv_metadata']


class StopDiscoveryAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    next_action: Literal['stop']


class CandidateReason(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    arxiv_id: str
    reason: str = Field(min_length=1,max_length=1000)

    @field_validator('arxiv_id','reason')
    @classmethod
    def validate_text(cls,value: str) -> str:
        return safe_text(value)


class DiscoveryReasons(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    papers: list[CandidateReason] = Field(min_length=1,max_length=3)


class RelatedPaper(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    arxiv_id: str
    title: str = Field(min_length=1,max_length=1000)
    authors: list[str] = Field(max_length=200)
    reason: str = Field(min_length=1,max_length=1000)
    arxiv_url: str

    @field_validator('title','reason')
    @classmethod
    def validate_text(cls,value: str) -> str:
        return safe_text(value)


class RelatedSearchResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    papers: list[RelatedPaper] = Field(max_length=3)
    request_id: str


DISCOVERY_INITIAL_OUTPUT = TypeAdapter(SearchArxivAction | StopDiscoveryAction)
DISCOVERY_REASONS_OUTPUT = TypeAdapter(DiscoveryReasons)
