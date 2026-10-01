from typing import Literal
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field

from researcy.errors import APIError
from .models import JobSnapshot
from .jobs import MAX_SAFE_INTEGER


ProcessingStage=Literal['queued','validating','parsing','normalizing','chunking','embedding','indexing','ready','failed']


class Preparation(BaseModel):
    state: Literal['waiting','preparing','delayed','failed','complete']
    reason: Literal['temporary','unsupported','resource_limit','integrity'] | None
    retryable: bool
    retry_after_seconds: int


class JobResponse(BaseModel):
    job_id: UUID
    paper_id: UUID
    document_version: UUID
    stage: ProcessingStage
    status: Literal['pending','running','succeeded','failed']
    failed_stage: ProcessingStage | None
    error_code: str | None
    retry_revision: int=Field(ge=0,le=MAX_SAFE_INTEGER)
    preparation: Preparation
    request_id: str


class RetryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    retry_revision: int=Field(strict=True,ge=0,le=MAX_SAFE_INTEGER)


def preparation(*,stage: str,status: str,attempts: int,retry_revision: int,lease_generation: int,failure_kind: str | None,retryable: bool,retry_after_seconds: int,published: bool) -> dict:
    if status=='succeeded':
        if stage!='ready' or not published:
            raise APIError(503,'PROCESSING_UNAVAILABLE','Preparation status is unavailable.')
        state='complete'
    elif status=='failed' and stage=='failed':
        state='failed'
    elif status=='running' and stage not in ('queued','ready','failed'):
        state='preparing'
    elif status=='pending' and stage not in ('ready','failed'):
        state='waiting' if attempts==0 and retry_revision==0 else 'delayed'
    else:
        raise APIError(503,'PROCESSING_UNAVAILABLE','Preparation status is unavailable.')
    return {'state':state,'reason':failure_kind if state in ('failed','delayed') else None,
        'retryable':status=='failed' and retryable and max(attempts,lease_generation,retry_revision)<MAX_SAFE_INTEGER,
        'retry_after_seconds':max(0,retry_after_seconds) if state in ('failed','delayed') else 0}


def job_payload(job: JobSnapshot,request_id: str) -> dict:
    return {'job_id':job.job_id,'paper_id':job.scope.paper_id,'document_version':job.scope.document_version_id,
        'stage':job.stage,'status':job.status,'failed_stage':job.failed_stage,'error_code':job.error_code,
        'retry_revision':job.retry_revision,'request_id':request_id,
        'preparation':preparation(stage=job.stage,status=job.status,attempts=job.attempts,retry_revision=job.retry_revision,lease_generation=job.lease_generation,
            failure_kind=job.failure_kind,retryable=job.retryable,retry_after_seconds=job.retry_after_seconds,published=job.published)}
