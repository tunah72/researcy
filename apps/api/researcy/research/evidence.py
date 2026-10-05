from dataclasses import dataclass
from threading import Event
import time

import psycopg

from researcy.citations.models import StoredCitation
from researcy.citations.resolver import EvidenceCatalog,make_evidence_catalog,resolve_proposal
from researcy.errors import APIError
from researcy.ingestion.models import LostLease
from researcy.retrieval import hybrid
from researcy.retrieval.repository import ReadyDocument
from .models import ProposedIdea,ResearchReservation,ResearchSource

_FIXED_QUERY='limitations future work evaluation methods experiments'


@dataclass(frozen=True,slots=True)
class ResearchEvidence:
    catalog: EvidenceCatalog
    documents_by_ref: dict[str,ReadyDocument]


def build_research_query(source: ResearchSource) -> str:
    title=' '.join(source.title.split()) if source.title else ''
    context=(title or ' '.join(' '.join(heading.split()) for heading in source.headings))[:1000]
    return (context+' ' if context else '')+_FIXED_QUERY


def _check_budget(deadline: float,cancel: Event) -> None:
    if cancel.is_set():raise LostLease()
    if time.monotonic()>=deadline:
        raise APIError(503,'RESEARCH_DEADLINE_EXCEEDED','The research directions exceeded their time limit.')


def retrieve_research_evidence(sources: tuple[ResearchSource,...],*,deadline: float,cancel: Event) -> ResearchEvidence:
    if not 2<=len(sources)<=4 or tuple(s.ordinal for s in sources)!=tuple(range(len(sources))):
        raise ValueError('Research requires two to four ordered pinned sources.')
    candidates=[]
    for source in sources:
        _check_budget(deadline,cancel)
        hits=hybrid.retrieve_same_paper(source.document,build_research_query(source),deadline=deadline,cancel=cancel)
        _check_budget(deadline,cancel)
        if (len(hits)>5 or len({hit.chunk_id for hit in hits})!=len(hits) or any(
            hit.scope!=source.document.scope or hit.chunk_id not in source.document.chunk_ids
            or not hit.text or not hit.locations for hit in hits)):
            raise APIError(503,'EVIDENCE_UNAVAILABLE','The selected evidence is unavailable.')
        candidates.append(hits[:2])
    packed=[[] for _ in sources];normalized=raw=0
    for rank in range(2):
        for index,hits in enumerate(candidates):
            if len(hits)<=rank:
                if rank==0:
                    raise APIError(422,'RESEARCH_INSUFFICIENT_EVIDENCE','The selected evidence is insufficient.')
                continue
            hit=hits[rank];raw_size=sum(len(location.quote) for location in hit.locations)
            if not raw_size or normalized+len(hit.text)>24000 or raw+raw_size>24000:
                if rank==0:
                    raise APIError(422,'RESEARCH_INSUFFICIENT_EVIDENCE','The selected evidence is insufficient.')
                continue
            packed[index].append(hit);normalized+=len(hit.text);raw+=raw_size
    catalog={};documents={}
    for source,hits in zip(sources,packed):
        for local_ref,entry in make_evidence_catalog(tuple(hits)).items():
            ref=f'P{source.ordinal}:{local_ref}'
            catalog[ref]=entry;documents[ref]=source.document
    _check_budget(deadline,cancel)
    return ResearchEvidence(catalog,documents)


def resolve_idea(conn: psycopg.Connection,reservation: ResearchReservation,evidence: ResearchEvidence,
    idea: ProposedIdea,idea_index: int) -> tuple[StoredCitation,...]:
    unresolved=APIError(422,'EVIDENCE_UNRESOLVED','The research evidence cannot be resolved exactly.')
    if type(idea_index) is not int or not 0<=idea_index<=2:raise unresolved
    permitted={(s.document.scope,s.document.profile_hash,s.document.collection) for s in reservation.sources}
    citations=[]
    for proposal in idea.premise_citations:
        document=evidence.documents_by_ref.get(proposal.source_ref)
        entry=evidence.catalog.get(proposal.source_ref)
        if (document is None or entry is None or entry.hit.scope!=document.scope
            or (document.scope,document.profile_hash,document.collection) not in permitted):
            raise unresolved
        citations.extend(StoredCitation(citation,idea_index,citation.raw_fragments)
            for citation in resolve_proposal(conn,document,evidence.catalog,proposal))
        if len(citations)>24:raise unresolved
    if not citations:raise unresolved
    return tuple(citations)
