from contextlib import asynccontextmanager
import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.datastructures import MutableHeaders

from .auth.routes import router as auth_router
from .config import get_settings
from .errors import APIError, error_payload
from .papers.routes import router as papers_router
from .ingestion.routes import router as jobs_router
from .conversations.routes import router as conversations_router
from .citations.routes import router as citations_router
from .discovery.routes import router as discovery_router
from .research.routes import router as research_router
from .readiness import router as readiness_router


class UploadBodyTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/api/papers/upload"
        ):
            await self.app(scope, receive, send)
            return
        limit = scope["app"].state.settings.max_upload_request_bytes
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise UploadBodyTooLarge()
            return message

        await self.app(scope, limited_receive, send)


class RequestIdMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_request_id(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            # Do not create a competing receive task or require a response after disconnect.
            await self.app(scope, receive, send_with_request_id)
        except Exception as error:
            if started:
                raise
            oversized = isinstance(error, UploadBodyTooLarge)
            response = JSONResponse(
                status_code=413 if oversized else 500,
                content=error_payload(
                    "PDF_TOO_LARGE" if oversized else "INTERNAL_ERROR",
                    "The PDF exceeds the configured size limit." if oversized else "An unexpected error occurred.",
                    request_id,
                ),
            )
            await response(scope, receive, send_with_request_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enable application diagnostics without exposing third-party HTTP request logs.
    logger = logging.getLogger("researcy")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)
    settings = get_settings()
    if settings.app_role != "api":
        raise ValueError(f"cannot boot api with APP_ROLE={settings.app_role}")
    app.state.settings = settings
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.include_router(auth_router)
app.include_router(papers_router)
app.include_router(jobs_router)
app.include_router(conversations_router)
app.include_router(citations_router)
app.include_router(discovery_router)
app.include_router(research_router)
app.include_router(readiness_router)




@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    headers = {}
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    content_range = getattr(exc, "content_range", None)
    if content_range is not None:
        headers["Content-Range"] = content_range
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, request.state.request_id),
        headers=headers or None,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "INVALID_REQUEST", "The request was invalid.", request.state.request_id
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    messages = {
        404: ("NOT_FOUND", "The requested resource was not found."),
        405: ("METHOD_NOT_ALLOWED", "The request method is not allowed."),
    }
    code, message = messages.get(
        exc.status_code, ("HTTP_ERROR", "The request could not be completed.")
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, message, request.state.request_id),
    )


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "request_id": request.state.request_id}
