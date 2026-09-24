import os
from pathlib import Path
import re
import tempfile
from dataclasses import dataclass
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
_READ_SIZE = 64 * 1024
_MAX_METADATA_BYTES = 1024 * 1024
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Researcy/0.1)"
)
_DEFAULT_HEADERS = {"User-Agent": _USER_AGENT}

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
        retry_after: int | None = None,
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
    try:
        val = int(value.strip())
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _fetch_metadata(client: httpx2.Client, canonical_id: str) -> tuple[ArxivMetadata, int]:
    metadata_url = f"https://export.arxiv.org/api/query?id_list={canonical_id}"
    current_url = metadata_url
    redirect_count = 0

    while True:
        _validate_destination_url(current_url)
        req_headers = {"User-Agent": _USER_AGENT}
        with client.stream(
            "GET", current_url, follow_redirects=False, headers=req_headers
        ) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                redirect_count += 1
                if redirect_count > _MAX_REDIRECTS:
                    raise ArxivUpstreamError(
                        "Too many redirects from official arXiv metadata service.",
                        status_code=502,
                    )
                location = response.headers.get("Location")
                if not location:
                    raise ArxivUpstreamError(
                        "Redirect missing Location header from official arXiv service.",
                        status_code=502,
                    )
                current_url = urljoin(current_url, location)
                continue

            if response.status_code == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                raise ArxivUpstreamError(
                    "The official arXiv service is currently rate-limited.",
                    status_code=503,
                    retry_after=retry_after or 60,
                )
            if response.status_code == 404:
                raise ArxivNotFound(f"The arXiv paper {canonical_id} was not found.")
            if response.status_code >= 500:
                raise ArxivUpstreamError(
                    "The official arXiv metadata service returned a server error.",
                    status_code=502,
                )
            if response.status_code != 200:
                raise ArxivUpstreamError(
                    f"The official arXiv metadata service returned HTTP {response.status_code}.",
                    status_code=502,
                )

            xml_content = bytearray()
            for chunk in response.iter_bytes(chunk_size=_READ_SIZE):
                if len(xml_content) + len(chunk) > _MAX_METADATA_BYTES:
                    raise ArxivUpstreamError(
                        "The official arXiv metadata response exceeded the safe size limit.",
                        status_code=502,
                    )
                xml_content.extend(chunk)
            break

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        raise ArxivUpstreamError(
            "Failed to parse official arXiv metadata response.", status_code=502
        ) from None

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    }

    total_results_elem = root.find("opensearch:totalResults", ns)
    if total_results_elem is not None and total_results_elem.text == "0":
        raise ArxivNotFound(f"The arXiv paper {canonical_id} was not found.")

    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ArxivNotFound(f"The arXiv paper {canonical_id} was not found.")

    id_elem = entry.find("atom:id", ns)
    if id_elem is None or not id_elem.text:
        raise ArxivUpstreamError(
            "Official arXiv metadata entry is missing an ID.", status_code=502
        )

    entry_id_str = id_elem.text.strip().replace("http://", "https://")
    try:
        entry_canonical_id, entry_version = parse_arxiv_reference(entry_id_str)
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

    title_elem = entry.find("atom:title", ns)
    title = None
    if title_elem is not None and title_elem.text:
        cleaned = " ".join(title_elem.text.split())
        if cleaned and cleaned.lower() != "error":
            title = cleaned

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

    return ArxivMetadata(title=title, authors=authors or None, year=year), latest_version


def _stream_pdf_to_sink(
    client: httpx2.Client,
    pdf_url: str,
    max_bytes: int,
    temp_dir: str | Path | None,
) -> Path:
    current_url = pdf_url
    redirect_count = 0

    fd, temp_file_path = tempfile.mkstemp(prefix="arxiv_", suffix=".pdf", dir=temp_dir)
    os.close(fd)
    os.chmod(temp_file_path, 0o600)
    path = Path(temp_file_path)

    try:
        while True:
            _validate_destination_url(current_url)
            req_headers = {"User-Agent": _USER_AGENT}
            with client.stream(
                "GET", current_url, follow_redirects=False, headers=req_headers
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    redirect_count += 1
                    if redirect_count > _MAX_REDIRECTS:
                        raise ArxivUpstreamError(
                            "Too many redirects from official arXiv PDF service.",
                            status_code=502,
                        )
                    location = response.headers.get("Location")
                    if not location:
                        raise ArxivUpstreamError(
                            "Redirect missing Location header from official arXiv service.",
                            status_code=502,
                        )
                    current_url = urljoin(current_url, location)
                    continue

                if response.status_code == 429:
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                    raise ArxivUpstreamError(
                        "The official arXiv service is currently rate-limited.",
                        status_code=503,
                        retry_after=retry_after or 60,
                    )
                if response.status_code == 404:
                    raise ArxivVersionNotFound("The requested arXiv PDF version was not found.")
                if response.status_code >= 500:
                    raise ArxivUpstreamError(
                        "The official arXiv PDF service returned a server error.",
                        status_code=502,
                    )
                if response.status_code != 200:
                    raise ArxivUpstreamError(
                        f"The official arXiv PDF service returned HTTP {response.status_code}.",
                        status_code=502,
                    )

                total_bytes = 0
                with open(path, "wb") as sink:
                    for chunk in response.iter_bytes(chunk_size=_READ_SIZE):
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
            metadata, latest_version = _fetch_metadata(client, canonical_id)
        except (
            ArxivNotFound,
            ArxivVersionNotFound,
            ArxivUpstreamError,
            InvalidArxivReference,
        ):
            raise
        except httpx2.TimeoutException:
            raise ArxivUpstreamError(
                "The request to the official arXiv service timed out.",
                status_code=504,
            ) from None
        except httpx2.HTTPError:
            raise ArxivUpstreamError(
                "Failed to communicate with the official arXiv service.",
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
            pdf_path = _stream_pdf_to_sink(client, pdf_url, max_bytes, temp_dir)
        except (
            ArxivVersionNotFound,
            ArxivUpstreamError,
            ArxivPdfTooLarge,
            ArxivInvalidPdf,
        ):
            raise
        except httpx2.TimeoutException:
            raise ArxivUpstreamError(
                "The PDF download from official arXiv timed out.",
                status_code=504,
            ) from None
        except httpx2.HTTPError:
            raise ArxivUpstreamError(
                "Failed to stream PDF from official arXiv service.",
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
