from uuid import UUID

from fastapi import APIRouter,Request

from researcy.auth.sessions import get_current_user
from researcy.db import get_conn
from .models import CitationResponse
from .repository import get_owned_citation

router = APIRouter()


@router.get('/api/citations/{citation_id}',response_model=CitationResponse)
def citation(request: Request,citation_id: UUID):
    with get_conn() as conn:
        owner_id = get_current_user(request,conn)
        conn.commit()
        resolved = get_owned_citation(conn,owner_id,citation_id)
    return {'citation':resolved,'request_id':request.state.request_id}
