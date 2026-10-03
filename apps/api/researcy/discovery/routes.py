import asyncio
import time
from uuid import UUID

from fastapi import APIRouter,Request
from starlette.requests import ClientDisconnect

from researcy.auth.sessions import get_current_user,require_csrf
from researcy.config import get_settings
from researcy.errors import APIError
from .models import RelatedSearchResponse
from .repository import RUN_SECONDS,load_active_metadata
from .response import DiscoveryJSONResponse
from .runtime import database


router=APIRouter()


@router.post('/api/papers/{paper_id}/related:search',response_model=RelatedSearchResponse)
async def search_related(request: Request,paper_id: UUID):
    started=time.monotonic()
    deadline=started+RUN_SECONDS
    def check_owner_paper(conn):
        owner=get_current_user(request,conn)
        require_csrf(request,conn,owner)
        conn.commit()
        row=conn.execute('SELECT 1 FROM papers WHERE owner_id=%s AND id=%s',(owner,paper_id)).fetchone()
        if row is None:
            raise APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')
        return owner
    try:
        async with asyncio.timeout_at(deadline):
            owner=await database(check_owner_paper,deadline=deadline)
            if request.query_params:
                raise APIError(422,'INVALID_REQUEST','Related-paper search accepts no query parameters or body.')
            content_length=request.headers.get('content-length')
            if content_length is not None:
                try:
                    declared=int(content_length)
                except ValueError:
                    raise APIError(422,'INVALID_REQUEST','Related-paper search accepts no query parameters or body.') from None
                if declared<0 or declared>1024:
                    raise APIError(422,'INVALID_REQUEST','Related-paper search accepts no query parameters or body.')
            async for chunk in request.stream():
                if chunk:
                    raise APIError(422,'INVALID_REQUEST','Related-paper search accepts no query parameters or body.')
            source=await database(lambda conn: load_active_metadata(conn,owner,paper_id),deadline=deadline)
            settings=get_settings()
            if not settings.generation_endpoint or not settings.generation_api_key:
                raise APIError(503,'GENERATION_UNCONFIGURED','Related-paper search is not configured.')
    except (APIError,TimeoutError) as error:
        failure=error if isinstance(error,APIError) else APIError(504,'DISCOVERY_TIMEOUT','The related-paper search exceeded its time limit.')
        response=await request.app.exception_handlers[APIError](request,failure)
        response.headers['Cache-Control']='no-store'
        return response
    except ClientDisconnect:
        raise asyncio.CancelledError() from None
    return DiscoveryJSONResponse(request,source,settings,started=started,deadline=deadline)
