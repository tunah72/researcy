import hashlib
import json
import os
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from researcy.ingestion.models import LostLease

from ..config import get_settings
from ..documents.models import SandboxLimits
from ..documents.sandbox import SandboxError, run_pdf_child
from ..errors import APIError


_PDF_SIGNATURE = b"%PDF-"
_READ_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class ScreeningWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    sha256: str
    bytes: int
    pages: int
    title: str | None
    warning: ScreeningWarning | None




_ERROR_MESSAGES = {
    "PDF_UNSUPPORTED": "The uploaded file is not a supported PDF.",
    "PDF_TOO_LARGE": "The PDF exceeds the configured size limit.",
    "PDF_INVALID": "The PDF is corrupt or could not be safely inspected.",
    "PDF_ENCRYPTED": "Password-protected PDFs are not supported.",
    "PDF_TOO_MANY_PAGES": "The PDF exceeds the configured page limit.",
    "PDF_NO_TEXT": "The PDF contains no extractable text.",
    "PDF_SCREEN_TIMEOUT": "The PDF could not be screened within the time limit.",
    "PDF_SCREEN_RESOURCE_LIMIT": "The PDF could not be safely screened.",
    "PDF_SANDBOX_UNAVAILABLE": "PDF inspection is temporarily unavailable.",
}


def _error(status: int, code: str) -> APIError:
    return APIError(status, code, _ERROR_MESSAGES[code])


def _safe_title(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in value
    )
    title = " ".join(cleaned.split())[:500]
    return title or None


def _inspection_result(source_fd: int, page_limit: int, byte_limit: int, *, cancel: Event | None=None, deadline: float | None=None) -> dict:
    try:
        with tempfile.TemporaryDirectory(prefix="researcy-screen-") as directory:
            output = Path(directory) / "result.json"
            run_pdf_child(
                "screen", Path(f"/proc/self/fd/{source_fd}"), output,
                SandboxLimits(pages=page_limit, input_bytes=byte_limit),
                cancel=cancel,deadline=deadline,
            )
            result = json.loads(output.read_bytes())
    except SandboxError as error:
        status = 503 if error.code == "PDF_SANDBOX_UNAVAILABLE" else (413 if error.code == "PDF_TOO_LARGE" else 422)
        raise _error(status, error.code) from None
    except (OSError, ValueError):
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT") from None
    if not isinstance(result, dict):
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")
    if "error" in result:
        if set(result) != {"error"} or not isinstance(result["error"], str):
            raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")
    elif set(result) != {"pages", "title", "warning"}:
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")
    return result


def screen_pdf(path: str | os.PathLike[str], media_type: str | None, *, cancel: Event | None=None, deadline: float | None=None) -> ScreeningResult:
    """Hash and inspect a bounded PDF without returning its extracted text."""
    if media_type is not None and media_type.split(";", 1)[0].strip().lower() != "application/pdf":
        raise _error(415, "PDF_UNSUPPORTED")

    settings = get_settings()
    max_bytes = settings.max_upload_bytes
    max_pages = settings.max_pdf_pages
    digest = hashlib.sha256()
    try:
        source = open(Path(path), "rb")
    except (OSError, TypeError, ValueError):
        raise _error(422, "PDF_INVALID") from None

    with source:
        try:
            file_info = os.fstat(source.fileno())
        except OSError:
            raise _error(422, "PDF_INVALID") from None
        if file_info.st_size > max_bytes:
            raise _error(413, "PDF_TOO_LARGE")
        signature = source.read(len(_PDF_SIGNATURE))
        if signature != _PDF_SIGNATURE:
            raise _error(415, "PDF_UNSUPPORTED")
        digest.update(signature)
        byte_count = len(signature)
        while True:
            if cancel is not None and cancel.is_set():
                raise LostLease()
            chunk = source.read(_READ_SIZE)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > max_bytes:
                raise _error(413, "PDF_TOO_LARGE")
            digest.update(chunk)
        source.seek(0)
        inspected = _inspection_result(source.fileno(), max_pages, max_bytes,cancel=cancel,deadline=deadline)

    if "error" in inspected:
        code = inspected["error"]
        if code == "PDF_TOO_LARGE":
            raise _error(413, code)
        if code in {"PDF_ENCRYPTED", "PDF_TOO_MANY_PAGES", "PDF_NO_TEXT", "PDF_INVALID"}:
            raise _error(422, code)
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")

    pages = inspected.get("pages")
    title = inspected.get("title")
    warning = inspected.get("warning")
    if (
        type(pages) is not int or not 1 <= pages <= max_pages
        or type(warning) is not bool
        or (title is not None and (not isinstance(title, str) or len(title) > 2000))
    ):
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")
    safe_title = _safe_title(title if isinstance(title, str) else None)
    screening_warning = (
        ScreeningWarning(
            "LOW_TEXT",
            "This PDF contains little extractable text and may not be supported by later processing.",
        )
        if warning
        else None
    )
    return ScreeningResult(
        sha256=digest.hexdigest(),
        bytes=byte_count,
        pages=pages,
        title=safe_title,
        warning=screening_warning,
    )
