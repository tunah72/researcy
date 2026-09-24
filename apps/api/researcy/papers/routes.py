from uuid import UUID

from fastapi import APIRouter, Query, Request

from ..auth.sessions import get_current_user
from ..db import get_conn
from ..errors import APIError
from .models import MAX_SEARCH_LENGTH, PaperDetailResponse, PaperListResponse
from .repository import get_paper, list_papers


router = APIRouter()


@router.get("/api/papers", response_model=PaperListResponse)
def papers(
    request: Request,
    search: str | None = Query(default=None, max_length=MAX_SEARCH_LENGTH),
):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        rows = list_papers(conn, owner_id, search)
    return {"papers": rows, "request_id": request.state.request_id}


@router.get("/api/papers/{paper_id}", response_model=PaperDetailResponse)
def paper_detail(request: Request, paper_id: UUID):
    with get_conn() as conn:
        owner_id = get_current_user(request, conn)
        paper = get_paper(conn, owner_id, paper_id)
    if paper is None:
        raise APIError(404, "NOT_FOUND", "The requested resource was not found.")
    return {**paper, "request_id": request.state.request_id}
