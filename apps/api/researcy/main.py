from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth.routes import router as auth_router
from .config import get_settings
from .errors import APIError, error_payload
from .papers.routes import router as papers_router


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = get_settings()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware)
app.include_router(auth_router)
app.include_router(papers_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except UploadBodyTooLarge:
        response = JSONResponse(
            status_code=413,
            content=error_payload(
                "PDF_TOO_LARGE",
                "The PDF exceeds the configured size limit.",
                request_id,
            ),
        )
    except Exception:
        response = JSONResponse(
            status_code=500,
            content=error_payload(
                "INTERNAL_ERROR", "An unexpected error occurred.", request_id
            ),
        )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    headers = {}
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
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
