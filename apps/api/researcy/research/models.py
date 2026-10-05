from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import unicodedata
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field,TypeAdapter,field_validator,model_validator

from researcy.citations.models import ProposedCitation,ResolvedCitation
from researcy.retrieval.repository import ReadyDocument


def safe_text(value: str) -> str:
    if not value.strip() or any(unicodedata.category(c) in ('Cc','Cf','Cs') and c not in '\t\n\r' for c in value):
        raise ValueError('Invalid text.')
    value.encode('utf-8')
    return value


class _Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)


@dataclass(frozen=True,slots=True)
class ResearchSource:
    ordinal: int
    document: ReadyDocument
    title: str | None
    headings: tuple[str,...]


@dataclass(frozen=True,slots=True)
class ResearchReservation:
    run_id: UUID
    owner_id: UUID
    active_paper_id: UUID
    request_id: UUID
    sources: tuple[ResearchSource,...]
    lease_expires_at: datetime


class ProposedIdea(_Strict):
    observed_gap: str=Field(min_length=1,max_length=1200)
    proposed_direction: str=Field(min_length=1,max_length=1200)
    possible_method: str=Field(min_length=1,max_length=1200)
    premise_citations: list[ProposedCitation]=Field(min_length=1,max_length=6)

    @field_validator('observed_gap','proposed_direction','possible_method')
    @classmethod
    def validate_text(cls,value: str) -> str:
        return safe_text(value)

    @model_validator(mode='after')
    def validate_citations(self) -> 'ProposedIdea':
        for citation in self.premise_citations:
            safe_text(citation.source_ref)
            safe_text(citation.evidence_quote)
        return self


class ResearchOutput(_Strict):
    next_action: Literal['directions']
    ideas: list[ProposedIdea]=Field(max_length=3)
    refusal: str | None=Field(max_length=1200)

    @model_validator(mode='after')
    def validate_envelope(self) -> 'ResearchOutput':
        if self.refusal is None:
            if not 1<=len(self.ideas)<=3:
                raise ValueError('Supported output requires ideas.')
        elif self.ideas:
            raise ValueError('Refusal cannot contain ideas.')
        else:
            safe_text(self.refusal)
        return self


class ResearchDraft(_Strict):
    observed_gap: str=Field(min_length=1,max_length=1200)
    proposed_direction: str=Field(min_length=1,max_length=1200)
    possible_method: str=Field(min_length=1,max_length=1200)

    @field_validator('observed_gap','proposed_direction','possible_method')
    @classmethod
    def validate_text(cls,value: str) -> str:
        return safe_text(value)


class AcceptedIdea(ResearchDraft):
    premise_citations: tuple[ResolvedCitation,...]=Field(min_length=1,max_length=24)

    @model_validator(mode='after')
    def validate_citations(self) -> 'AcceptedIdea':
        for citation in self.premise_citations:
            safe_text(citation.source_ref)
            safe_text(citation.evidence_quote)
        return self


class ResearchSourceIdentity(_Strict):
    paper_id: UUID
    document_version: UUID


class ResearchSafeError(_Strict):
    code: str=Field(min_length=1,max_length=64)
    message: str=Field(min_length=1,max_length=1200)

    @field_validator('code','message')
    @classmethod
    def validate_text(cls,value: str) -> str:
        return safe_text(value)


class ResearchSnapshot(_Strict):
    run_id: UUID
    active_paper_id: UUID
    document_version: UUID
    sources: tuple[ResearchSourceIdentity,...]=Field(min_length=2,max_length=4)
    state: Literal['running','completed','failed','interrupted']
    ideas: tuple[AcceptedIdea,...]=Field(max_length=3)
    draft_ideas: tuple[ResearchDraft,...]=Field(max_length=3)
    error: ResearchSafeError | None
    request_id: UUID

    @model_validator(mode='after')
    def validate_state(self) -> 'ResearchSnapshot':
        identities={(s.paper_id,s.document_version) for s in self.sources}
        if (len({s.paper_id for s in self.sources})!=len(self.sources)
            or self.sources[0].paper_id!=self.active_paper_id or self.sources[0].document_version!=self.document_version):
            raise ValueError('Invalid source pins.')
        if self.state=='completed':
            if not self.ideas or self.error is not None or self.draft_ideas:
                raise ValueError('Invalid completed state.')
        elif self.ideas or (self.state=='running' and (self.error is not None or self.draft_ideas)):
            raise ValueError('Invalid unaccepted state.')
        elif self.state!='running' and self.error is None:
            raise ValueError('Failed state requires a safe error.')
        citations=[c for idea in self.ideas for c in idea.premise_citations]
        if len(citations)>24 or len({c.citation_id for c in citations})!=len(citations) or any(
            (c.paper_id,c.document_version) not in identities for c in citations):
            raise ValueError('Invalid accepted citation membership.')
        return self


class ResearchRequest(_Strict):
    related_paper_ids: list[str]=Field(min_length=1,max_length=3)

    @field_validator('related_paper_ids')
    @classmethod
    def validate_ids(cls,values: list[str]) -> list[str]:
        parsed=[UUID(value) for value in values]
        if any(str(value)!=raw for value,raw in zip(parsed,values)) or len(set(parsed))!=len(parsed):
            raise ValueError('Distinct canonical UUID strings are required.')
        return values


@dataclass(frozen=True,slots=True)
class ResearchEvent:
    event: str
    data: dict


RESEARCH_OUTPUT=TypeAdapter(ResearchOutput)
