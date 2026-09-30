from dataclasses import dataclass
from typing import Iterable, Literal
from uuid import UUID

from researcy.ingestion.models import DocumentScope
from .models import Box, PageRecord


@dataclass(frozen=True, slots=True)
class SourceMapping:
    start: int
    end: int
    span_id: UUID | None
    source_start: int | None
    source_end: int | None
    transformation: str
    section_id: UUID


@dataclass(frozen=True, slots=True)
class CanonicalPage:
    id: UUID
    scope: DocumentScope
    source: PageRecord
    kind: Literal['page']='page'


@dataclass(frozen=True, slots=True)
class CanonicalSection:
    id: UUID
    scope: DocumentScope
    profile_hash: bytes
    ordinal: int
    title: str | None
    source_reference: tuple[int, int] | None
    kind: Literal['section']='section'


@dataclass(frozen=True, slots=True)
class CanonicalBlock:
    id: UUID
    scope: DocumentScope
    page_id: UUID
    section_id: UUID
    ordinal: int
    block_type: str
    box: Box
    excluded: bool
    kind: Literal['block']='block'


@dataclass(frozen=True, slots=True)
class CanonicalSpan:
    id: UUID
    scope: DocumentScope
    profile_hash: bytes
    block_id: UUID
    page_id: UUID
    section_id: UUID
    ordinal: int
    raw_text: str
    character_boxes: tuple[Box, ...]
    normalized_text: str
    mappings: tuple[SourceMapping, ...]
    separator_before: str
    retrieval: bool
    kind: Literal['span']='span'


CanonicalRecord=CanonicalPage | CanonicalSection | CanonicalBlock | CanonicalSpan


@dataclass(frozen=True, slots=True)
class SectionContent:
    section: CanonicalSection
    spans: Iterable[CanonicalSpan]


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    id: UUID
    scope: DocumentScope
    profile_hash: bytes
    section_id: UUID
    ordinal: int
    text: str
    checksum: bytes
    source_mappings: tuple[SourceMapping, ...]
    overlap_characters: int


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    span_id: UUID
    page_index: int
    source_start: int
    source_end: int
    quote: str
    boxes: tuple[Box, ...]
