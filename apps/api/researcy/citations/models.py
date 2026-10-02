from dataclasses import dataclass
import math
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from researcy.documents.canonical import EvidenceLocation
from researcy.documents.models import Box


class ProposedCitation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    source_ref: str = Field(min_length=1, max_length=64)
    evidence_quote: str = Field(min_length=1, max_length=2000)


class ResolvedCitation(BaseModel):
    model_config = ConfigDict(extra='forbid')

    citation_id: UUID
    paper_id: UUID
    document_version: UUID
    source_ref: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1, max_length=2000)
    page: int = Field(ge=1)
    boxes: tuple[Box, ...] = Field(min_length=1)
    section: str | None = None
    _raw_fragments: tuple[EvidenceLocation, ...] = PrivateAttr(default=())

    @property
    def raw_fragments(self) -> tuple[EvidenceLocation, ...]:
        """Internal resolver provenance; absent from HTTP schemas and serialization."""
        return self._raw_fragments

    @field_validator('boxes')
    @classmethod
    def exact_boxes(cls, boxes: tuple[Box, ...]) -> tuple[Box, ...]:
        if any(not all(math.isfinite(value) for value in box) or box[0]>box[2] or box[1]>box[3] for box in boxes):
            raise ValueError('Invalid source geometry.')
        return boxes


@dataclass(frozen=True, slots=True)
class StoredCitation:
    """Server-resolved provenance; never constructed from provider geometry."""
    citation: ResolvedCitation
    claim_index: int
    raw_fragments: tuple[EvidenceLocation, ...]


class CitationResponse(BaseModel):
    citation: ResolvedCitation
    request_id: UUID
