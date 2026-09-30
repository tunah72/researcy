from uuid import UUID

from fastapi import APIRouter,Request,Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from researcy.auth.sessions import get_current_user,require_csrf
from researcy.db import get_conn
from researcy.errors import APIError
from .presentation import JobResponse,RetryRequest,job_payload
from .retry import get_owned_job,retry_owned


router=APIRouter()


def _read_job(request: Request,job_id: UUID,*,mutation: bool=False):
    with get_conn() as conn:
        owner=get_current_user(request,conn)
        if mutation:
            require_csrf(request,conn,owner)
        conn.commit()
        job=get_owned_job(conn,owner,job_id)
        return owner,job


@router.get('/api/jobs/{job_id}',response_model=JobResponse)
def job_status(request: Request,job_id: UUID):
    _,job=_read_job(request,job_id)
    return job_payload(job,request.state.request_id)


def _retry(owner: UUID,job_id: UUID,revision: int):
    with get_conn() as conn:
        return retry_owned(conn,owner,job_id,revision)


@router.post('/api/jobs/{job_id}/retry',response_model=JobResponse)
async def retry_job(request: Request,response: Response,job_id: UUID):
    owner,_=await run_in_threadpool(_read_job,request,job_id,mutation=True)
    data=bytearray()
    async for part in request.stream():
        if len(data)+len(part)>4096:
            raise APIError(413,'REQUEST_TOO_LARGE','The request body is too large.')
        data.extend(part)
    try:
        body=RetryRequest.model_validate_json(data)
    except (ValidationError,ValueError):
        raise APIError(422,'INVALID_REQUEST','The request is invalid.') from None
    result=await run_in_threadpool(_retry,owner,job_id,body.retry_revision)
    response.status_code=202 if result.accepted else 200
    return job_payload(result.job,request.state.request_id)
