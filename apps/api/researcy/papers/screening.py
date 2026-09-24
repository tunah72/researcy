import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from ..errors import APIError


_PDF_SIGNATURE = b"%PDF-"
_READ_SIZE = 64 * 1024
_WORKER_MEMORY_BYTES = 1024 * 1024 * 1024
_WORKER_CPU_SECONDS = 10
_WORKER_WALL_SECONDS = 15


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


_WORKER = r'''import json
import os
import pwd
import resource
import sys
import tempfile

source_fd = int(sys.argv[1])
page_limit = int(sys.argv[2])
byte_limit = int(sys.argv[3])
memory_limit = int(sys.argv[4])
cpu_limit = int(sys.argv[5])


def emit(**result):
    print(json.dumps(result, separators=(",", ":")))


def constrained(limit, maximum):
    return limit != resource.RLIM_INFINITY and limit <= maximum


limits_applied = False
try:
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    resource.setrlimit(resource.RLIMIT_FSIZE, (byte_limit, byte_limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if os.geteuid() == 0:
        account = pwd.getpwnam("nobody")
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    if os.geteuid() == 0:
        raise RuntimeError
    cpu_limits = resource.getrlimit(resource.RLIMIT_CPU)
    if any(not constrained(limit, cpu_limit) for limit in cpu_limits):
        raise RuntimeError
    if sys.platform == "linux":
        address_limits = resource.getrlimit(resource.RLIMIT_AS)
        if any(not constrained(limit, memory_limit) for limit in address_limits):
            raise RuntimeError
    limits_applied = True

    with tempfile.TemporaryDirectory(prefix="researcy-pdf-screen-") as directory:
        filename = os.path.join(directory, "original.pdf")
        byte_count = 0
        with os.fdopen(os.dup(source_fd), "rb") as source, open(filename, "wb") as target:
            while True:
                chunk = source.read(65536)
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > byte_limit:
                    emit(error="PDF_TOO_LARGE")
                    sys.exit(0)
                target.write(chunk)

        import pymupdf

        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
        try:
            document = pymupdf.open(filename)
        except Exception:
            emit(error="PDF_INVALID")
            sys.exit(0)
        with document:
            if document.is_encrypted:
                emit(error="PDF_ENCRYPTED")
                sys.exit(0)
            if document.is_repaired:
                emit(error="PDF_INVALID")
                sys.exit(0)
            page_count = len(document)
            if page_count > page_limit:
                emit(error="PDF_TOO_MANY_PAGES")
                sys.exit(0)
            total_chars = 0
            pages_with_40_chars = 0
            for page in document:
                chars = sum(not character.isspace() for character in page.get_text("text"))
                total_chars += chars
                pages_with_40_chars += chars >= 40
            if total_chars == 0:
                emit(error="PDF_NO_TEXT")
                sys.exit(0)
            metadata = document.metadata or {}
            title = metadata.get("title") if isinstance(metadata, dict) else None
            if not isinstance(title, str):
                title = None
            warning = total_chars < 200 or pages_with_40_chars * 2 < page_count
            emit(
                pages=page_count,
                title=title,
                warning=warning,
            )
except MemoryError:
    emit(error="PDF_SCREEN_RESOURCE_LIMIT")
except Exception:
    emit(error="PDF_INVALID" if limits_applied else "PDF_SCREEN_RESOURCE_LIMIT")
'''


_ERROR_MESSAGES = {
    "PDF_UNSUPPORTED": "The uploaded file is not a supported PDF.",
    "PDF_TOO_LARGE": "The PDF exceeds the configured size limit.",
    "PDF_INVALID": "The PDF is corrupt or could not be safely inspected.",
    "PDF_ENCRYPTED": "Password-protected PDFs are not supported.",
    "PDF_TOO_MANY_PAGES": "The PDF exceeds the configured page limit.",
    "PDF_NO_TEXT": "The PDF contains no extractable text.",
    "PDF_SCREEN_TIMEOUT": "The PDF could not be screened within the time limit.",
    "PDF_SCREEN_RESOURCE_LIMIT": "The PDF could not be safely screened.",
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


def _inspection_result(source_fd: int, page_limit: int, byte_limit: int) -> dict:
    command = [
        sys.executable,
        "-I",
        "-c",
        _WORKER,
        str(source_fd),
        str(page_limit),
        str(byte_limit),
        str(_WORKER_MEMORY_BYTES),
        str(_WORKER_CPU_SECONDS),
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_WORKER_WALL_SECONDS,
            check=False,
            pass_fds=(source_fd,),
            cwd="/tmp",
            env={"HOME": "/nonexistent", "TMPDIR": "/tmp"},
        )
    except subprocess.TimeoutExpired as error:
        raise _error(422, "PDF_SCREEN_TIMEOUT") from error
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT") from error
    if completed.returncode != 0:
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")
    try:
        result = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT") from None
    if not isinstance(result, dict):
        raise _error(422, "PDF_SCREEN_RESOURCE_LIMIT")
    return result


def screen_pdf(path: str | os.PathLike[str], media_type: str | None) -> ScreeningResult:
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
            chunk = source.read(_READ_SIZE)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > max_bytes:
                raise _error(413, "PDF_TOO_LARGE")
            digest.update(chunk)
        source.seek(0)
        inspected = _inspection_result(source.fileno(), max_pages, max_bytes)

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
    if not isinstance(pages, int) or pages < 1 or not isinstance(warning, bool):
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
