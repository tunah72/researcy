import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from itertools import islice
import logging
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import unicodedata
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

import httpx2

from ..config import get_settings
from ..errors import APIError

_CURRENT_RE = re.compile(r"^(\d{2}(?:0[1-9]|1[0-2])\.\d{4,5})(?:v([1-9]\d*))?$")
_LEGACY_RE = re.compile(
    r"^([a-zA-Z\-]+(?:\.[a-zA-Z\-]+)?/\d{2}(?:0[1-9]|1[0-2])\d{3})(?:v([1-9]\d*))?$"
)
_ALLOWED_HOSTS = frozenset({"arxiv.org", "www.arxiv.org"})
_OFFICIAL_DESTINATION_HOSTS = frozenset({"arxiv.org", "export.arxiv.org", "www.arxiv.org"})
_PDF_MAGIC = b"%PDF-"
_MAX_REDIRECTS = 3
_DEFAULT_TIMEOUT = 15.0
_MAX_RESPONSE_SECONDS = 60.0
_MAX_METADATA_BYTES = 1024 * 1024
_USER_AGENT = "Researcy/0.1 (https://github.com/tunah72/researcy)"
_DEFAULT_HEADERS = {"User-Agent": _USER_AGENT}
_ATOM_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

logger = logging.getLogger(__name__)


def _log_upstream(host: str, status: int | None, request_id: str | None) -> None:
    if status is not None and 200 <= status < 400:
        logger.info(
            "arxiv_upstream host=%s status=%s request_id=%s",
            host,
            status,
            request_id,
            extra={"upstream_host": host, "upstream_status": status, "request_id": request_id},
        )
    else:
        logger.warning(
            "arxiv_upstream host=%s status=%s request_id=%s",
            host,
            status,
            request_id,
            extra={"upstream_host": host, "upstream_status": status, "request_id": request_id},
        )


class ArxivLimiter:
    """Process-wide request exclusion, pacing and cooldown for sync/async arXiv I/O."""

    def __init__(
        self,
        min_interval: float = 3.0,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        async_sleep: Callable[[float], Awaitable[None]] | None = None,
    ):
        self._min_interval = min_interval
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._async_sleep = async_sleep or asyncio.sleep
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._last_request_started_at: float | None = None
        self._cooldown_until = 0.0

    def set_cooldown(self, seconds: float) -> None:
        with self._state_lock:
            expiry = self._clock() + max(0.0, float(seconds))
            self._cooldown_until = max(self._cooldown_until, expiry)

    def _check_cooldown(self, now: float) -> None:
        # Caller holds only the state lock, never while sleeping or doing I/O.
        if now < self._cooldown_until:
            raise ArxivUpstreamError(
                "arXiv is temporarily unavailable. Please try again after the indicated interval.",
                status_code=503,
                retry_after=max(1, math.ceil(self._cooldown_until - now)),
            )

    def _spacing_delay(self) -> float:
        with self._state_lock:
            now = self._clock()
            self._check_cooldown(now)
            if self._last_request_started_at is None:
                return 0.0
            return max(0.0, self._min_interval - (now - self._last_request_started_at))

    def _mark_started(self) -> None:
        with self._state_lock:
            now = self._clock()
            self._check_cooldown(now)
            self._last_request_started_at = now

    @contextmanager
    def acquire(self) -> Iterator[None]:
        if not self._request_lock.acquire(timeout=_MAX_RESPONSE_SECONDS):
            raise ArxivUpstreamError("arXiv is busy. Please wait before trying again.")
        try:
            delay = self._spacing_delay()
            if delay:
                self._sleep(delay)
            self._mark_started()
            yield
        finally:
            self._request_lock.release()

    @asynccontextmanager
    async def acquire_async(self, *, deadline: float) -> AsyncIterator[None]:
        # Nonblocking polling gives cancellation no detached thread or pending lease.
        while True:
            remaining = _search_remaining(deadline)
            if self._request_lock.acquire(blocking=False):
                break
            await self._async_sleep(min(0.05, remaining))
        try:
            while True:
                remaining = _search_remaining(deadline)
                delay = self._spacing_delay()
                if not delay:
                    break
                await self._async_sleep(min(delay, remaining))
            _search_remaining(deadline)
            self._mark_started()
            yield
        finally:
            self._request_lock.release()


_GLOBAL_LIMITER = ArxivLimiter()



class InvalidArxivReference(APIError):
    def __init__(self, message: str = "Invalid arXiv reference."):
        super().__init__(400, "INVALID_ARXIV_REFERENCE", message)


class ArxivNotFound(APIError):
    def __init__(self, message: str = "The requested arXiv paper was not found."):
        super().__init__(404, "ARXIV_NOT_FOUND", message)


class ArxivVersionNotFound(APIError):
    def __init__(self, message: str = "The requested arXiv version was not found."):
        super().__init__(404, "ARXIV_VERSION_NOT_FOUND", message)


class ArxivUpstreamError(APIError):
    __slots__ = ("retry_after",)

    def __init__(
        self,
        message: str = "The official arXiv service is currently unavailable.",
        *,
        status_code: int = 503,
        code: str = "ARXIV_UPSTREAM_ERROR",
        retry_after: int | None = 60,
    ):
        super().__init__(status_code, code, message)
        self.retry_after = retry_after


class ArxivPdfTooLarge(APIError):
    def __init__(self, message: str = "The PDF exceeds the configured size limit."):
        super().__init__(413, "PDF_TOO_LARGE", message)


class ArxivInvalidPdf(APIError):
    def __init__(self, message: str = "The downloaded file is not a valid PDF."):
        super().__init__(422, "PDF_INVALID", message)


@dataclass(frozen=True, slots=True)
class ArxivMetadata:
    title: str | None
    authors: list[str] | None
    year: int | None
    abstract: str | None = None


@dataclass(frozen=True, slots=True)
class ArxivCandidate:
    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    abstract: str | None


@dataclass(frozen=True, slots=True)
class ArxivSearchResult:
    candidates: tuple[ArxivCandidate, ...]
    inspected_entries: int
    inspected_unique: int
    invalid_ids: int
    duplicates: int
    http_requests: int
    redirects: int


@dataclass(frozen=True, slots=True)
class ArxivAcquisition:
    metadata: ArxivMetadata
    resolved_version: int
    source_url: str
    pdf_path: Path

    @property
    def title(self) -> str | None:
        return self.metadata.title

    @property
    def authors(self) -> list[str] | None:
        return self.metadata.authors

    @property
    def year(self) -> int | None:
        return self.metadata.year

    @property
    def source_version(self) -> str:
        return f"v{self.resolved_version}"


def parse_arxiv_reference(value: str) -> tuple[str, int | None]:
    """Parse and normalize an arXiv identifier or official abs/pdf URL into (canonical_id, version)."""
    if not isinstance(value, str):
        raise InvalidArxivReference("arXiv reference must be a string.")
    val = value.strip()
    if not val:
        raise InvalidArxivReference("arXiv reference cannot be empty.")

    if "?" in val or "#" in val or "@" in val or "\\" in val:
        raise InvalidArxivReference("arXiv reference contains invalid characters.")

    if "://" in val:
        try:
            parsed = urlsplit(val)
        except Exception:
            raise InvalidArxivReference("Malformed URL.") from None
        if parsed.scheme != "https":
            raise InvalidArxivReference("Only HTTPS arXiv URLs are permitted.")
        if parsed.netloc not in _ALLOWED_HOSTS:
            raise InvalidArxivReference("Host is not an official arXiv host.")
        if parsed.username or parsed.password or parsed.port:
            raise InvalidArxivReference("Credentials and custom ports are not permitted.")
        if parsed.query or parsed.fragment:
            raise InvalidArxivReference("URL query parameters and fragments are not permitted.")

        path = parsed.path
        if path.startswith("/abs/"):
            raw_id = path[len("/abs/"):]
        elif path.startswith("/pdf/"):
            raw_id = path[len("/pdf/"):]
            if raw_id.endswith(".pdf"):
                raw_id = raw_id[:-4]
        else:
            raise InvalidArxivReference("Unapproved URL path.")
    else:
        if val.lower().startswith("arxiv:") and not val.lower().startswith("arxiv://"):
            val = val[6:].strip()
        raw_id = val

    if "//" in raw_id or ".." in raw_id or not raw_id:
        raise InvalidArxivReference("Invalid path or traversal in arXiv reference.")

    m_curr = _CURRENT_RE.match(raw_id)
    if m_curr:
        canonical_id = m_curr.group(1)
        version = int(m_curr.group(2)) if m_curr.group(2) else None
        return canonical_id, version

    m_leg = _LEGACY_RE.match(raw_id)
    if m_leg:
        canonical_id = m_leg.group(1)
        version = int(m_leg.group(2)) if m_leg.group(2) else None
        return canonical_id, version

    raise InvalidArxivReference(f"Malformed arXiv identifier: {raw_id}")


def _validate_destination_url(url_str: str) -> None:
    try:
        parsed = urlsplit(url_str)
    except Exception:
        raise ArxivUpstreamError("Invalid destination URL.", status_code=502) from None
    if parsed.scheme != "https":
        raise ArxivUpstreamError("Official arXiv request must use HTTPS.", status_code=502)
    if parsed.netloc not in _OFFICIAL_DESTINATION_HOSTS:
        raise ArxivUpstreamError(
            "Official arXiv request redirected to an unauthorized destination.",
            status_code=502,
        )
    if parsed.username or parsed.password or parsed.port:
        raise ArxivUpstreamError(
            "Official arXiv destination must not contain credentials or custom ports.",
            status_code=502,
        )


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdigit():
            # Reject unrepresentable provider values without disabling cooldown.
            seconds = int(value)
            if not math.isfinite(float(seconds)):
                return None
            return seconds if seconds > 0 else None
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(1, math.ceil(date.timestamp() - time.time()))
    except (ValueError, TypeError, OverflowError):
        return None


def _redirect_destination(
    response: httpx2.Response, current_url: str, redirects: int, service: str,
) -> str | None:
    if response.status_code not in {301, 302, 303, 307, 308}:
        return None
    if redirects >= _MAX_REDIRECTS:
        raise ArxivUpstreamError(
            f"Too many redirects from official arXiv {service} service.", status_code=502,
        )
    location = response.headers.get("Location")
    if not location:
        raise ArxivUpstreamError(
            "Redirect missing Location header from official arXiv service.", status_code=502,
        )
    destination = urljoin(current_url, location)
    _validate_destination_url(destination)
    return destination


def _check_upstream_status(
    response: httpx2.Response, limiter: ArxivLimiter, service: str,
    *, canonical_id: str | None = None,
) -> None:
    # 406 is a rejection, not proof of rate limiting; establish cooldown, never retry.
    if response.status_code in {406, 429, 503}:
        cooldown = _parse_retry_after(response.headers.get("Retry-After")) or 60
        limiter.set_cooldown(cooldown)
        raise ArxivUpstreamError(
            "arXiv could not complete this request. Please wait before trying again.",
            status_code=503, retry_after=cooldown,
        )
    if response.status_code == 404:
        if service == "PDF":
            raise ArxivVersionNotFound("The requested arXiv PDF version was not found.")
        if canonical_id is not None:
            raise ArxivNotFound(f"The arXiv paper {canonical_id} was not found.")
    if response.status_code != 200:
        raise ArxivUpstreamError(
            f"The official arXiv {service} service is temporarily unavailable. Please try again later.",
            status_code=502,
        )


class _MetadataTreeBuilder(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        # Reject DTDs before entity expansion, including UTF-16 encoded declarations.
        raise ArxivUpstreamError(
            "Official arXiv metadata must not contain document type declarations.", status_code=502,
        )


def _parse_atom_feed(content: bytes | bytearray) -> ET.Element:
    try:
        root = ET.fromstring(content, parser=ET.XMLParser(target=_MetadataTreeBuilder()))
    except ET.ParseError:
        raise ArxivUpstreamError(
            "Failed to parse official arXiv metadata response.", status_code=502,
        ) from None
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ArxivUpstreamError("Invalid official arXiv metadata feed.", status_code=502)
    return root


def _entry_reference(entry: ET.Element) -> tuple[str, int | None]:
    element = entry.find("atom:id", _ATOM_NAMESPACES)
    if element is None or len(element):
        raise InvalidArxivReference()
    identifier = (element.text or "").strip()
    # Atom's historical HTTP IDs are data; their URLs are never requested.
    if identifier.startswith("http://"):
        identifier = "https://" + identifier[len("http://"):]
    try:
        parsed = urlsplit(identifier)
    except ValueError:
        raise InvalidArxivReference() from None
    if parsed.netloc in _OFFICIAL_DESTINATION_HOSTS and parsed.path == "/api/errors":
        raise ArxivUpstreamError("The official arXiv metadata service returned an error.", status_code=502)
    try:
        return parse_arxiv_reference(identifier)
    except ValueError:
        raise InvalidArxivReference() from None


def _normalized_atom_text(element: ET.Element | None) -> str | None:
    if element is None or not element.text:
        return None
    return " ".join(element.text.split()) or None


def _entry_abstract(entry: ET.Element) -> str | None:
    return _normalized_atom_text(entry.find("atom:summary", _ATOM_NAMESPACES))


def _fetch_metadata(
    client: httpx2.Client,
    canonical_id: str,
    *,
    limiter: ArxivLimiter | None = None,
    request_id: str | None = None,
) -> tuple[ArxivMetadata, int]:
    metadata_url = f"https://export.arxiv.org/api/query?id_list={canonical_id}"
    current_url = metadata_url
    redirect_count = 0
    active_limiter = limiter or _GLOBAL_LIMITER

    while True:
        _validate_destination_url(current_url)
        host = urlsplit(current_url).netloc
        try:
            with active_limiter.acquire():
                deadline = time.monotonic() + _MAX_RESPONSE_SECONDS
                req_headers = {"User-Agent": _USER_AGENT}
                with client.stream(
                    "GET", current_url, follow_redirects=False, headers=req_headers
                ) as response:
                    _log_upstream(host, response.status_code, request_id)
                    destination = _redirect_destination(response, current_url, redirect_count, "metadata")
                    if destination is not None:
                        redirect_count += 1
                        current_url = destination
                        continue
                    _check_upstream_status(response, active_limiter, "metadata", canonical_id=canonical_id)

                    xml_content = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise httpx2.ReadTimeout("arXiv metadata response deadline exceeded")
                        if len(xml_content) + len(chunk) > _MAX_METADATA_BYTES:
                            raise ArxivUpstreamError(
                                "The official arXiv metadata response exceeded the safe size limit.",
                                status_code=502,
                            )
                        xml_content.extend(chunk)
                    break
        except (APIError, httpx2.HTTPError):
            raise
        except Exception:
            _log_upstream(host, None, request_id)
            raise

    root = _parse_atom_feed(xml_content)
    ns = _ATOM_NAMESPACES

    total_results_elem = root.find("opensearch:totalResults", ns)
    if total_results_elem is not None and total_results_elem.text == "0":
        raise ArxivNotFound(f"The arXiv paper {canonical_id} was not found.")

    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ArxivNotFound(f"The arXiv paper {canonical_id} was not found.")

    try:
        entry_canonical_id, entry_version = _entry_reference(entry)
    except InvalidArxivReference:
        raise ArxivUpstreamError(
            "Official arXiv metadata contains an invalid entry identifier.",
            status_code=502,
        ) from None

    if entry_canonical_id != canonical_id:
        raise ArxivUpstreamError(
            "The official arXiv service returned mismatched metadata.", status_code=502
        )

    latest_version = entry_version if entry_version is not None else 1

    title = _normalized_atom_text(entry.find("atom:title", ns))
    if title is not None and title.casefold() == "error":
        title = None

    authors = [
        " ".join(name_elem.text.split())
        for name_elem in entry.findall("atom:author/atom:name", ns)
        if name_elem.text and name_elem.text.strip()
    ]

    year = None
    pub_elem = entry.find("atom:published", ns)
    if pub_elem is not None and pub_elem.text:
        try:
            year = int(pub_elem.text.strip()[:4])
        except (ValueError, IndexError):
            pass
    if year is None:
        updated_elem = entry.find("atom:updated", ns)
        if updated_elem is not None and updated_elem.text:
            try:
                year = int(updated_elem.text.strip()[:4])
            except (ValueError, IndexError):
                pass

    return ArxivMetadata(
        title=title, authors=authors or None, year=year, abstract=_entry_abstract(entry),
    ), latest_version


def _stream_pdf_to_sink(
    client: httpx2.Client,
    pdf_url: str,
    max_bytes: int,
    temp_dir: str | Path | None,
    *,
    limiter: ArxivLimiter | None = None,
    request_id: str | None = None,
) -> Path:
    current_url = pdf_url
    redirect_count = 0
    active_limiter = limiter or _GLOBAL_LIMITER

    fd, temp_file_path = tempfile.mkstemp(prefix="arxiv_", suffix=".pdf", dir=temp_dir)
    os.close(fd)
    os.chmod(temp_file_path, 0o600)
    path = Path(temp_file_path)

    try:
        while True:
            _validate_destination_url(current_url)
            host = urlsplit(current_url).netloc
            with active_limiter.acquire():
                deadline = time.monotonic() + _MAX_RESPONSE_SECONDS
                req_headers = {"User-Agent": _USER_AGENT}
                with client.stream(
                    "GET", current_url, follow_redirects=False, headers=req_headers
                ) as response:
                    _log_upstream(host, response.status_code, request_id)
                    destination = _redirect_destination(response, current_url, redirect_count, "PDF")
                    if destination is not None:
                        redirect_count += 1
                        current_url = destination
                        continue
                    _check_upstream_status(response, active_limiter, "PDF")

                    total_bytes = 0
                    with open(path, "wb") as sink:
                        # Do not buffer to a fixed chunk size: trickles must reach the deadline check.
                        for chunk in response.iter_bytes():
                            if time.monotonic() >= deadline:
                                raise httpx2.ReadTimeout("arXiv PDF response deadline exceeded")
                            if chunk:
                                total_bytes += len(chunk)
                                if total_bytes > max_bytes:
                                    raise ArxivPdfTooLarge(
                                        "The PDF exceeds the configured size limit."
                                    )
                                sink.write(chunk)
                    break

        if total_bytes == 0:
            raise ArxivInvalidPdf("The downloaded PDF is empty.")

        with open(path, "rb") as source:
            header = source.read(len(_PDF_MAGIC))
            if header != _PDF_MAGIC:
                raise ArxivInvalidPdf("The downloaded file is not a valid PDF.")

        return path
    except Exception:
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        raise


def fetch_official_arxiv(
    canonical_id: str,
    requested_version: int | None = None,
    *,
    client: httpx2.Client | None = None,
    transport: httpx2.BaseTransport | None = None,
    max_bytes: int | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    temp_dir: str | Path | None = None,
    limiter: ArxivLimiter | None = None,
    request_id: str | None = None,
) -> ArxivAcquisition:
    """Fetch official arXiv metadata and version-specific PDF using server-constructed URLs."""
    parsed_id, parsed_version = parse_arxiv_reference(canonical_id)
    if parsed_id != canonical_id or parsed_version is not None:
        raise InvalidArxivReference(f"Input is not a canonical unversioned ID: {canonical_id}")

    if requested_version is not None and requested_version < 1:
        raise InvalidArxivReference("Requested version must be a positive integer.")

    if max_bytes is None:
        try:
            max_bytes = get_settings().max_upload_bytes
        except Exception:
            max_bytes = 25 * 1024 * 1024

    owned_client = False
    if client is None:
        client = httpx2.Client(
            transport=transport, timeout=timeout, headers=_DEFAULT_HEADERS
        )
        owned_client = True

    try:
        try:
            metadata, latest_version = _fetch_metadata(
                client, canonical_id, limiter=limiter, request_id=request_id
            )
        except (
            ArxivNotFound,
            ArxivVersionNotFound,
            ArxivUpstreamError,
            InvalidArxivReference,
        ):
            raise
        except httpx2.TimeoutException:
            _log_upstream("export.arxiv.org", None, request_id)
            raise ArxivUpstreamError(
                "arXiv did not respond in time. Please wait and retry.",
                status_code=504,
            ) from None
        except httpx2.HTTPError:
            _log_upstream("export.arxiv.org", None, request_id)
            raise ArxivUpstreamError(
                "arXiv could not be reached. Please wait and retry.",
                status_code=503,
            ) from None

        if requested_version is None:
            resolved_version = latest_version
        else:
            if requested_version > latest_version:
                raise ArxivVersionNotFound(
                    f"Version v{requested_version} of arXiv paper {canonical_id} does not exist in official metadata history."
                )
            resolved_version = requested_version

        pdf_url = f"https://arxiv.org/pdf/{canonical_id}v{resolved_version}"

        try:
            pdf_path = _stream_pdf_to_sink(
                client,
                pdf_url,
                max_bytes,
                temp_dir,
                limiter=limiter,
                request_id=request_id,
            )
        except (
            ArxivVersionNotFound,
            ArxivUpstreamError,
            ArxivPdfTooLarge,
            ArxivInvalidPdf,
        ):
            raise
        except httpx2.TimeoutException:
            _log_upstream("arxiv.org", None, request_id)
            raise ArxivUpstreamError(
                "The arXiv PDF download timed out. Please wait and retry.",
                status_code=504,
            ) from None
        except httpx2.HTTPError:
            _log_upstream("arxiv.org", None, request_id)
            raise ArxivUpstreamError(
                "arXiv could not complete the PDF download. Please wait and retry.",
                status_code=503,
            ) from None

        return ArxivAcquisition(
            metadata=metadata,
            resolved_version=resolved_version,
            source_url=pdf_url,
            pdf_path=pdf_path,
        )
    finally:
        if owned_client:
            client.close()


_RELATED_STOPWORDS = frozenset('a an and are as at be by for from in is it of on or that the this to was were with all you need'.split())
_TITLE_PLACEHOLDERS = frozenset({"untitled", "untitled document", "unknown", "unknown title", "error"})


def _related_terms(text: str, exclude: tuple[str, ...] = ()) -> Iterator[str]:
    seen = set(exclude)
    for match in re.finditer(r"[^\W_]+", text):
        term = match.group().casefold()
        if len(term) <= 80 and term not in _RELATED_STOPWORDS and term not in seen:
            seen.add(term)
            yield term


def _unsafe_metadata_unicode(text: str) -> bool:
    # Directional overrides/isolates can disguise identities; legitimate ZWJ names remain valid.
    return any(
        (unicodedata.category(char) in {"Cc", "Cs"} and char not in "\r\n\t")
        or unicodedata.bidirectional(char) in {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"}
        for char in text
    )


def _usable_title(title: str | None) -> bool:
    return (
        title is not None and 1 <= len(title) <= 1000
        and title.casefold() not in _TITLE_PLACEHOLDERS
        and any(char.isalnum() for char in title)
    )


def related_title_terms(title: str | None) -> tuple[str, ...]:
    if not isinstance(title,str):
        raise APIError(409,'DISCOVERY_METADATA_MISSING','This paper needs a usable title before related-paper search.')
    cleaned = ' '.join(title.split())
    if not _usable_title(cleaned) or _unsafe_metadata_unicode(title):
        raise APIError(409,'DISCOVERY_METADATA_MISSING','This paper needs a usable title before related-paper search.')
    terms = tuple(islice(_related_terms(cleaned), 12))
    if not terms:
        raise APIError(409,'DISCOVERY_METADATA_MISSING','This paper needs a usable title before related-paper search.')
    return terms


def build_related_query(title: str, abstract: str | None) -> str:
    title_terms = related_title_terms(title)
    title_group = "(" + " OR ".join(f'all:"{term}"' for term in title_terms) + ")"
    abstract_terms = tuple(islice(_related_terms(abstract, title_terms), 8)) if abstract else ()
    if not abstract_terms:
        return title_group
    abstract_group = "(" + " OR ".join(f'abs:"{term}"' for term in abstract_terms) + ")"
    return title_group + " AND " + abstract_group


def _candidate_text(element: ET.Element | None, max_length: int | None = None) -> str | None:
    if element is not None and len(element):
        raise ArxivUpstreamError("Official arXiv metadata contains unsupported structured text.", status_code=502)
    if element is not None and element.text and _unsafe_metadata_unicode(element.text):
        raise ArxivUpstreamError("Official arXiv metadata contains unsafe text.", status_code=502)
    text = _normalized_atom_text(element)
    if text is not None and max_length is not None and len(text) > max_length:
        raise ArxivUpstreamError("Official arXiv metadata exceeds the safe field limits.", status_code=502)
    return text


def _search_candidates(content: bytearray, *, http_requests: int, redirects: int) -> ArxivSearchResult:
    root = _parse_atom_feed(content)
    seen: dict[str, tuple[str | None, tuple[str, ...], str | None]] = {}
    candidates = []
    inspected_entries = invalid_ids = duplicates = 0
    for entry in islice(root.iterfind("atom:entry", _ATOM_NAMESPACES), 10):
        inspected_entries += 1
        try:
            canonical_id, _ = _entry_reference(entry)
        except InvalidArxivReference:
            invalid_ids += 1
            continue
        title = _candidate_text(entry.find("atom:title", _ATOM_NAMESPACES), 1000)
        authors = tuple(
            name for element in entry.iterfind("atom:author/atom:name", _ATOM_NAMESPACES)
            if (name := _candidate_text(element, 200)) is not None
        )
        if len(authors) > 200:
            raise ArxivUpstreamError("Official arXiv metadata exceeds the safe author limit.", status_code=502)
        abstract = _candidate_text(entry.find("atom:summary", _ATOM_NAMESPACES))
        metadata = (title, authors, abstract)
        if canonical_id in seen:
            duplicates += 1
            if seen[canonical_id] != metadata:
                raise ArxivUpstreamError(
                    "The official arXiv service returned inconsistent metadata.", status_code=502,
                )
            continue
        seen[canonical_id] = metadata
        if _usable_title(title):
            candidates.append(ArxivCandidate(canonical_id, title, authors, abstract))
    return ArxivSearchResult(
        candidates=tuple(candidates), inspected_entries=inspected_entries, inspected_unique=len(seen),
        invalid_ids=invalid_ids, duplicates=duplicates, http_requests=http_requests, redirects=redirects,
    )


def _search_remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("arXiv metadata search deadline exceeded")
    return remaining


def _validate_search_destination(current_url: str, initial_url: httpx2.URL) -> None:
    _validate_destination_url(current_url)
    try:
        parsed = httpx2.URL(current_url)
    except (ValueError, httpx2.InvalidURL):
        raise ArxivUpstreamError("Invalid official arXiv metadata destination.", status_code=502) from None
    if (
        parsed.path != "/api/query" or parsed.fragment
        or sorted(parsed.params.multi_items()) != sorted(initial_url.params.multi_items())
    ):
        raise ArxivUpstreamError(
            "Official arXiv metadata search redirected outside the requested query.", status_code=502,
        )


async def search_official_arxiv_metadata(
    query: str, *, deadline: float, request_id: str,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> ArxivSearchResult:
    """Run exactly one bounded official metadata query, without fetching Atom links or PDFs."""
    stage_deadline = min(deadline, time.monotonic() + _MAX_RESPONSE_SECONDS)
    initial_url = httpx2.URL(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": query, "start": 0, "max_results": 10,
            "sortBy": "relevance", "sortOrder": "descending",
        },
    )
    current_url = str(initial_url)
    limiter = _GLOBAL_LIMITER
    http_requests = redirects = 0
    host = initial_url.host
    try:
        _search_remaining(stage_deadline)
        async with asyncio.timeout_at(stage_deadline):
            async with httpx2.AsyncClient(
                transport=transport, trust_env=False, follow_redirects=False, headers=_DEFAULT_HEADERS,
            ) as client:
                while True:
                    _validate_search_destination(current_url, initial_url)
                    host = urlsplit(current_url).netloc
                    async with limiter.acquire_async(deadline=stage_deadline):
                        remaining = _search_remaining(stage_deadline)
                        timeout = httpx2.Timeout(min(_DEFAULT_TIMEOUT, remaining), connect=min(5.0, remaining))
                        http_requests += 1
                        async with client.stream("GET", current_url, timeout=timeout) as response:
                            _log_upstream(host, response.status_code, request_id)
                            destination = _redirect_destination(response, current_url, redirects, "metadata")
                            if destination is not None:
                                _validate_search_destination(destination, initial_url)
                                redirects += 1
                                current_url = destination
                                continue
                            _check_upstream_status(response, limiter, "metadata")
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                _search_remaining(stage_deadline)
                                if len(content) + len(chunk) > _MAX_METADATA_BYTES:
                                    raise ArxivUpstreamError(
                                        "The official arXiv metadata response exceeded the safe size limit.",
                                        status_code=502,
                                    )
                                content.extend(chunk)
                            break
            _search_remaining(stage_deadline)
            result = _search_candidates(content, http_requests=http_requests, redirects=redirects)
            _search_remaining(stage_deadline)
            return result
    except (TimeoutError, httpx2.TimeoutException):
        _log_upstream(host, None, request_id)
        raise ArxivUpstreamError(
            "arXiv did not respond in time. Please wait and retry.", status_code=504,
        ) from None
    except httpx2.HTTPError:
        _log_upstream(host, None, request_id)
        raise ArxivUpstreamError("arXiv could not be reached. Please wait and retry.", status_code=503) from None
