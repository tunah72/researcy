from pathlib import Path
from tempfile import TemporaryDirectory
import httpx2
import pytest

from researcy.errors import APIError
from researcy.papers.arxiv import (
    ArxivAcquisition,
    ArxivInvalidPdf,
    ArxivMetadata,
    ArxivNotFound,
    ArxivPdfTooLarge,
    ArxivUpstreamError,
    ArxivVersionNotFound,
    InvalidArxivReference,
    fetch_official_arxiv,
    parse_arxiv_reference,
)
from researcy.papers import arxiv

ArxivLimiter = arxiv.ArxivLimiter


@pytest.fixture(autouse=True)
def _isolated_arxiv_limiter(monkeypatch, request):
    if request.node.name == "test_fetch_official_arxiv_real_network_if_enabled":
        return
    now = [1000.0]
    def advance(seconds):
        now[0] += seconds
    monkeypatch.setattr(arxiv, "_GLOBAL_LIMITER", ArxivLimiter(clock=lambda: now[0], sleep=advance))


_SAMPLE_ATOM_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <id>https://arxiv.org/api/test</id>
  <title>arXiv Query: id_list=1706.03762</title>
  <updated>2023-08-02T00:41:18Z</updated>
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title> Attention Is All You Need \n  </title>
    <published>2017-06-12T17:57:34Z</published>
    <updated>2023-08-02T00:41:18Z</updated>
    <author>
      <name>Ashish Vaswani</name>
    </author>
    <author>
      <name>Noam Shazeer</name>
    </author>
  </entry>
</feed>"""

_SAMPLE_PDF_BYTES = b"%PDF-1.5\nfake pdf payload for testing\n%%EOF"


@pytest.mark.parametrize(
    ("value", "expected_id", "expected_version"),
    [
        ("1706.03762", "1706.03762", None),
        ("1706.03762v5", "1706.03762", 5),
        ("0704.0001", "0704.0001", None),
        ("0704.0001v1", "0704.0001", 1),
        ("2301.12345", "2301.12345", None),
        ("2301.12345v10", "2301.12345", 10),
        ("arXiv:1706.03762", "1706.03762", None),
        ("arXiv:1706.03762v5", "1706.03762", 5),
        ("https://arxiv.org/abs/1706.03762", "1706.03762", None),
        ("https://arxiv.org/abs/1706.03762v5", "1706.03762", 5),
        ("https://arxiv.org/pdf/1706.03762", "1706.03762", None),
        ("https://arxiv.org/pdf/1706.03762v5", "1706.03762", 5),
        ("https://arxiv.org/pdf/1706.03762.pdf", "1706.03762", None),
        ("https://arxiv.org/pdf/1706.03762v5.pdf", "1706.03762", 5),
        ("math/0309136", "math/0309136", None),
        ("math/0309136v1", "math/0309136", 1),
        ("math.GT/0309136", "math.GT/0309136", None),
        ("math.GT/0309136v2", "math.GT/0309136", 2),
        ("hep-th/9901001", "hep-th/9901001", None),
        ("hep-th/9901001v2", "hep-th/9901001", 2),
        ("https://arxiv.org/abs/math/0309136v1", "math/0309136", 1),
        ("https://arxiv.org/pdf/math/0309136.pdf", "math/0309136", None),
        ("https://arxiv.org/pdf/math/0309136v2.pdf", "math/0309136", 2),
        ("https://www.arxiv.org/abs/1706.03762", "1706.03762", None),
        ("https://www.arxiv.org/pdf/1706.03762v3", "1706.03762", 3),
    ],
)
def test_parse_arxiv_reference_valid(value, expected_id, expected_version):
    canonical_id, version = parse_arxiv_reference(value)
    assert canonical_id == expected_id
    assert version == expected_version


@pytest.mark.parametrize(
    "invalid_value",
    [
        "https://arxiv.org.evil.test/abs/1706.03762",
        "https://evil-arxiv.org/abs/1706.03762",
        "https://arxiv.org@evil.com/abs/1706.03762",
        "https://notarxiv.org/abs/1706.03762",
        "https://google.com/abs/1706.03762",
        "http://arxiv.org/abs/1706.03762",
        "http://arxiv.org/pdf/1706.03762",
        "ftp://arxiv.org/abs/1706.03762",
        "file:///abs/1706.03762",
        "javascript:alert(1)",
        "https://user:pass@arxiv.org/abs/1706.03762",
        "https://user@arxiv.org/abs/1706.03762",
        "https://arxiv.org:8080/abs/1706.03762",
        "https://arxiv.org:443/abs/1706.03762",
        "https://arxiv.org/abs/1706.03762?foo=bar",
        "https://arxiv.org/abs/1706.03762?",
        "https://arxiv.org/abs/1706.03762#frag",
        "https://arxiv.org/abs/1706.03762#",
        "1706.03762?foo=bar",
        "1706.03762#frag",
        "https://arxiv.org/html/1706.03762",
        "https://arxiv.org/format/1706.03762",
        "https://arxiv.org/show-email/1706.03762",
        "https://arxiv.org/abs/",
        "https://arxiv.org/pdf/",
        "https://arxiv.org/",
        "https://arxiv.org",
        "https://arxiv.org/abs/../1706.03762",
        "https://arxiv.org/abs/1706.03762/..",
        "1706.03762/../1706.03762",
        "../1706.03762",
        "1706.03762/",
        "//1706.03762",
        "\\\\1706.03762",
        "1706.03762/foo",
        "https://arxiv.org/abs/1706.03762/foo",
        "https://arxiv.org/abs/1706.03762.pdf",
        "https://arxiv.org/pdf/1706.03762.pdf.pdf",
        "",
        "   ",
        "1706.03762v",
        "1706.03762v0",
        "1706.03762v-1",
        "1706.03762v01",
        "1706.03762v1v2",
        "1706",
        "1706.123",
        "1713.03762",
        "1700.03762",
        "math/",
        "math/9900001",
        "math/9913001",
        "not-an-arxiv-id",
        "1706. 03762",
    ],
)
def test_parse_arxiv_reference_rejects_invalid(invalid_value):
    with pytest.raises(InvalidArxivReference) as raised:
        parse_arxiv_reference(invalid_value)
    assert raised.value.status_code == 400
    assert raised.value.code == "INVALID_ARXIV_REFERENCE"


def test_fetch_official_arxiv_unversioned_resolves_current_version(tmp_path):
    recorded_urls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        recorded_urls.append(url_str)
        if url_str == "https://export.arxiv.org/api/query?id_list=1706.03762":
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        if url_str == "https://arxiv.org/pdf/1706.03762v7":
            return httpx2.Response(200, content=_SAMPLE_PDF_BYTES, headers={"Content-Type": "application/pdf"})
        return httpx2.Response(404)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        acquisition = fetch_official_arxiv("1706.03762", requested_version=None, client=client, temp_dir=tmp_path)
        assert acquisition.resolved_version == 7
        assert acquisition.source_url == "https://arxiv.org/pdf/1706.03762v7"
        assert acquisition.metadata.title == "Attention Is All You Need"
        assert acquisition.metadata.authors == ["Ashish Vaswani", "Noam Shazeer"]
        assert acquisition.metadata.year == 2017
        assert acquisition.pdf_path.is_file()
        assert acquisition.pdf_path.read_bytes() == _SAMPLE_PDF_BYTES
    finally:
        if "acquisition" in locals() and acquisition.pdf_path.is_file():
            acquisition.pdf_path.unlink()

    assert recorded_urls == [
        "https://export.arxiv.org/api/query?id_list=1706.03762",
        "https://arxiv.org/pdf/1706.03762v7",
    ]


def test_fetch_official_arxiv_explicit_old_version_confirmed_by_metadata(tmp_path):
    recorded_urls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        recorded_urls.append(url_str)
        if url_str == "https://export.arxiv.org/api/query?id_list=1706.03762":
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        if url_str == "https://arxiv.org/pdf/1706.03762v5":
            return httpx2.Response(200, content=_SAMPLE_PDF_BYTES)
        return httpx2.Response(404)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        acquisition = fetch_official_arxiv("1706.03762", requested_version=5, client=client, temp_dir=tmp_path)
        assert acquisition.resolved_version == 5
        assert acquisition.source_url == "https://arxiv.org/pdf/1706.03762v5"
        assert acquisition.metadata.title == "Attention Is All You Need"
    finally:
        if "acquisition" in locals() and acquisition.pdf_path.is_file():
            acquisition.pdf_path.unlink()

    assert recorded_urls == [
        "https://export.arxiv.org/api/query?id_list=1706.03762",
        "https://arxiv.org/pdf/1706.03762v5",
    ]


def test_fetch_official_arxiv_rejects_version_beyond_metadata_history(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivVersionNotFound) as raised:
        fetch_official_arxiv("1706.03762", requested_version=99, client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 404
    assert raised.value.code == "ARXIV_VERSION_NOT_FOUND"
    assert not list(tmp_path.glob("*.pdf"))



def test_fetch_official_arxiv_stops_reading_oversized_metadata(tmp_path):
    class OversizedMetadataStream(httpx2.SyncByteStream):
        def __init__(self):
            self.chunks_read = 0

        def __iter__(self):
            for _ in range(40):
                self.chunks_read += 1
                yield b"x" * (64 * 1024)

    stream = OversizedMetadataStream()

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, stream=stream)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 502
    assert stream.chunks_read < 40
    assert not list(tmp_path.glob("*.pdf"))

def test_fetch_official_arxiv_rejects_empty_or_mismatched_metadata(tmp_path):
    empty_feed = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>0</opensearch:totalResults>
</feed>"""

    def handler_empty(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=empty_feed)

    client = httpx2.Client(transport=httpx2.MockTransport(handler_empty))
    with pytest.raises(ArxivNotFound) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)
    assert raised.value.status_code == 404
    assert raised.value.code == "ARXIV_NOT_FOUND"

    mismatch_feed = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2005.11401v2</id>
    <title>Wrong Paper</title>
  </entry>
</feed>"""

    def handler_mismatch(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=mismatch_feed)

    client_mismatch = httpx2.Client(transport=httpx2.MockTransport(handler_mismatch))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client_mismatch, temp_dir=tmp_path)
    assert raised.value.status_code == 502
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"


def test_fetch_official_arxiv_redirect_allowlist_rejects_third_party(tmp_path):
    requests_sent = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests_sent.append(str(request.url))
        if str(request.url) == "https://export.arxiv.org/api/query?id_list=1706.03762":
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        if str(request.url) == "https://arxiv.org/pdf/1706.03762v7":
            return httpx2.Response(302, headers={"Location": "https://evil.com/fake.pdf"})
        return httpx2.Response(200, content=_SAMPLE_PDF_BYTES)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 502
    assert "https://evil.com/fake.pdf" not in requests_sent
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_official_arxiv_redirect_allowlist_rejects_non_https(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == "https://export.arxiv.org/api/query?id_list=1706.03762":
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(302, headers={"Location": "http://arxiv.org/pdf/1706.03762v7"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 502
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_official_arxiv_follows_allowlisted_redirect(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        if url_str == "https://export.arxiv.org/api/query?id_list=1706.03762":
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        if url_str == "https://arxiv.org/pdf/1706.03762v7":
            return httpx2.Response(302, headers={"Location": "https://export.arxiv.org/pdf/1706.03762v7"})
        if url_str == "https://export.arxiv.org/pdf/1706.03762v7":
            return httpx2.Response(200, content=_SAMPLE_PDF_BYTES)
        return httpx2.Response(404)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        acquisition = fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)
        assert acquisition.resolved_version == 7
        assert acquisition.pdf_path.read_bytes() == _SAMPLE_PDF_BYTES
    finally:
        if "acquisition" in locals() and acquisition.pdf_path.is_file():
            acquisition.pdf_path.unlink()


def test_fetch_official_arxiv_handles_upstream_429(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, headers={"Retry-After": "60"}, text="rate limited")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 503
    assert raised.value.retry_after == 60
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"
    assert "rate limited" not in raised.value.message


def test_fetch_official_arxiv_handles_timeout(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("connection timed out")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 504
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"


def test_fetch_official_arxiv_handles_server_outage(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, text="Internal Server Error")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 502
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"


def test_fetch_official_arxiv_stream_byte_overflow_aborts_and_cleans_up(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "api/query" in str(request.url):
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(200, content=b"%PDF-" + b"x" * 2000)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(APIError) as raised:
        fetch_official_arxiv("1706.03762", max_bytes=100, client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 413
    assert raised.value.code == "PDF_TOO_LARGE"
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_official_arxiv_invalid_pdf_magic_aborts_and_cleans_up(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "api/query" in str(request.url):
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(200, content=b"<html><body>Not a PDF</body></html>")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(APIError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 422
    assert raised.value.code == "PDF_INVALID"
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_official_arxiv_too_many_redirects(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        if "api/query" in url_str:
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(302, headers={"Location": "https://arxiv.org/pdf/redirected"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 502
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_official_arxiv_rejects_version_in_canonical_id():
    with pytest.raises(InvalidArxivReference):
        fetch_official_arxiv("1706.03762v5")


def test_fetch_official_arxiv_rejects_nonpositive_version():
    with pytest.raises(InvalidArxivReference):
        fetch_official_arxiv("1706.03762", requested_version=0)
    with pytest.raises(InvalidArxivReference):
        fetch_official_arxiv("1706.03762", requested_version=-1)


def test_fetch_official_arxiv_real_network_if_enabled(tmp_path):
    import os
    if os.environ.get("ARXIV_REAL_NETWORK") != "true":
        pytest.skip("ARXIV_REAL_NETWORK=true is not set")

    acquisition = fetch_official_arxiv("1706.03762", requested_version=None, temp_dir=tmp_path)
    try:
        assert acquisition.resolved_version >= 1
        assert acquisition.source_url == f"https://arxiv.org/pdf/1706.03762v{acquisition.resolved_version}"
        assert acquisition.metadata.title == "Attention Is All You Need"
        assert acquisition.pdf_path.is_file()
        assert acquisition.pdf_path.read_bytes()[:5] == b"%PDF-"
    finally:
        if acquisition.pdf_path.is_file():
            acquisition.pdf_path.unlink()


def test_fetch_official_arxiv_user_agent_identifies_application(tmp_path):
    recorded_user_agents = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        recorded_user_agents.append(request.headers.get("user-agent"))
        url_str = str(request.url)
        if "api/query" in url_str:
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(200, content=_SAMPLE_PDF_BYTES)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    acquisition = fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)
    acquisition.pdf_path.unlink()

    assert len(recorded_user_agents) == 2
    for ua in recorded_user_agents:
        assert ua is not None
        assert "Researcy" in ua
        assert "Mozilla" not in ua
        assert "Chrome" not in ua
        assert "Safari" not in ua

def test_fetch_official_arxiv_handles_upstream_406_metadata(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(406, headers={"Retry-After": "45"}, text="406 Not Acceptable")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 503
    assert raised.value.retry_after == 45
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"
    assert "406" not in raised.value.message
    assert "Not Acceptable" not in raised.value.message


def test_fetch_official_arxiv_handles_upstream_406_pdf(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        if "api/query" in url_str:
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(406, headers={"Retry-After": "90"}, text="406 Not Acceptable")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 503
    assert raised.value.retry_after == 90
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"
    assert "406" not in raised.value.message
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_official_arxiv_406_default_retry_after(tmp_path):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(406, text="Blocked")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with pytest.raises(ArxivUpstreamError) as raised:
        fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)

    assert raised.value.status_code == 503
    assert raised.value.retry_after == 60
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"


def test_arxiv_limiter_pacing_deterministic():
    assert ArxivLimiter is not None, "ArxivLimiter must be implemented"
    current_time = 1000.0
    sleep_calls = []

    def fake_clock():
        nonlocal current_time
        return current_time

    def fake_sleep(duration):
        nonlocal current_time
        sleep_calls.append(duration)
        current_time += duration

    limiter = ArxivLimiter(min_interval=3.0, clock=fake_clock, sleep=fake_sleep)
    with limiter.acquire():
        pass
    assert sleep_calls == []

    current_time = 1000.8
    with limiter.acquire():
        pass
    assert len(sleep_calls) == 1
    assert pytest.approx(sleep_calls[0]) == 2.2
    assert pytest.approx(current_time) == 1003.0


def test_arxiv_limiter_cooldown_deterministic():
    assert ArxivLimiter is not None, "ArxivLimiter must be implemented"
    current_time = 1000.0

    def fake_clock():
        return current_time

    def fake_sleep(duration):
        pass

    limiter = ArxivLimiter(min_interval=3.0, clock=fake_clock, sleep=fake_sleep)
    limiter.set_cooldown(60.0)

    current_time = 1020.0
    with pytest.raises(ArxivUpstreamError) as raised:
        with limiter.acquire():
            pass
    assert raised.value.status_code == 503
    assert raised.value.retry_after == 40
    assert raised.value.code == "ARXIV_UPSTREAM_ERROR"

    current_time = 1061.0
    with limiter.acquire():
        pass


def test_arxiv_limiter_concurrency_no_overlap():
    import threading

    assert ArxivLimiter is not None, "ArxivLimiter must be implemented"
    limiter = ArxivLimiter(min_interval=0.0)
    t1_inside = threading.Event()
    t1_release = threading.Event()
    t2_entered = threading.Event()
    t2_blocked = True

    def worker1():
        with limiter.acquire():
            t1_inside.set()
            t1_release.wait()

    def worker2():
        t1_inside.wait()
        nonlocal t2_blocked
        with limiter.acquire():
            t2_entered.set()
            t2_blocked = False

    t1 = threading.Thread(target=worker1)
    t2 = threading.Thread(target=worker2)
    t1.start()
    t2.start()

    t1_inside.wait()
    assert not t2_entered.is_set()
    assert t2_blocked

    t1_release.set()
    t1.join()
    t2.join()

    assert t2_entered.is_set()
    assert not t2_blocked


def test_fetch_official_arxiv_pacing_with_redirect(tmp_path, monkeypatch):
    import researcy.papers.arxiv as arxiv_mod

    current_time = 1000.0
    sleep_calls = []

    def fake_clock():
        nonlocal current_time
        return current_time

    def fake_sleep(duration):
        nonlocal current_time
        sleep_calls.append(duration)
        current_time += duration

    monkeypatch.setattr(arxiv_mod, "_GLOBAL_LIMITER", ArxivLimiter(clock=fake_clock, sleep=fake_sleep))

    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        if "api/query" in url_str and "redirected=1" not in url_str:
            return httpx2.Response(
                302,
                headers={"Location": "https://export.arxiv.org/api/query?id_list=1706.03762&redirected=1"},
            )
        if "redirected=1" in url_str:
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(200, content=_SAMPLE_PDF_BYTES)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    acq = fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)
    acq.pdf_path.unlink()

    assert len(sleep_calls) >= 2
    for delay in sleep_calls:
        assert delay >= 2.9


def test_fetch_official_arxiv_logs_safe_diagnostics(tmp_path, caplog):
    import logging

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(406, headers={"Retry-After": "60"}, text="Blocked")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with caplog.at_level(logging.WARNING, logger="researcy.papers.arxiv"):
        with pytest.raises(ArxivUpstreamError):
            fetch_official_arxiv(
                "1706.03762",
                client=client,
                temp_dir=tmp_path,
                request_id="test-safe-req-999",
            )

    warning_records = [
        r for r in caplog.records
        if r.name == "researcy.papers.arxiv" and r.levelno >= logging.WARNING
    ]
    assert len(warning_records) >= 1
    rec = warning_records[0]
    assert "export.arxiv.org" in rec.getMessage()
    assert "406" in rec.getMessage()
    assert "test-safe-req-999" in rec.getMessage()
    assert "id_list=" not in rec.getMessage()
    assert "Blocked" not in rec.getMessage()


@pytest.mark.parametrize("status", [406, 429, 503])
@pytest.mark.parametrize("phase", ["metadata", "pdf"])
def test_http_date_retry_after_prevents_early_upstream_retry(tmp_path, monkeypatch, status, phase):
    from email.utils import formatdate

    monkeypatch.setattr(arxiv.time, "time", lambda: 1_800_000_000)
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if phase == "pdf" and "api/query" in str(request.url):
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(
            status,
            headers={"Retry-After": formatdate(1_800_000_120, usegmt=True)},
        )

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ArxivUpstreamError) as error:
            fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)
        assert error.value.retry_after == 120
        sent_before_retry = len(requests)
        with pytest.raises(ArxivUpstreamError) as retry:
            fetch_official_arxiv("2303.09833", client=client, temp_dir=tmp_path)
        assert retry.value.retry_after == 120
        assert len(requests) == sent_before_retry
    assert not list(tmp_path.iterdir())


def test_truncated_pdf_has_retry_guidance_and_removes_partial_file(tmp_path):
    class TruncatedStream(httpx2.SyncByteStream):
        def __iter__(self):
            yield b"%PDF-1.7\npartial"
            raise httpx2.RemoteProtocolError("upstream incomplete body")
    def handler(request):
        if "api/query" in str(request.url):
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(200, stream=TruncatedStream())
    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ArxivUpstreamError) as error:
            fetch_official_arxiv("1706.03762", client=client, temp_dir=tmp_path)
    assert error.value.status_code == 503
    assert error.value.retry_after and error.value.retry_after > 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("digits", [400, 5000])
def test_oversized_retry_after_stays_retriable_and_blocks_next_request(digits, tmp_path):
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx2.Response(503, headers={"Retry-After": "9" * digits})

    with pytest.raises(ArxivUpstreamError) as error:
        fetch_official_arxiv("1706.03762", transport=httpx2.MockTransport(handler), temp_dir=tmp_path)
    assert error.value.status_code == 503
    assert error.value.retry_after == 60
    with pytest.raises(ArxivUpstreamError):
        fetch_official_arxiv("2303.09833", transport=httpx2.MockTransport(handler), temp_dir=tmp_path)
    assert len(calls) == 1


@pytest.mark.parametrize("phase", ["metadata", "pdf"])
def test_trickling_stream_releases_lease_and_removes_partial_file(phase, tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(arxiv.time, "monotonic", lambda: now[0])
    closed = []
    class SlowStream(httpx2.SyncByteStream):
        def __iter__(self):
            yield b"%PDF-" if phase == "pdf" else b"<feed>"
            now[0] += 61
            yield b"still arriving"
        def close(self):
            closed.append(True)

    def handler(request):
        if "api/query" in str(request.url) and phase == "pdf":
            return httpx2.Response(200, text=_SAMPLE_ATOM_FEED)
        return httpx2.Response(200, stream=SlowStream())

    with pytest.raises(ArxivUpstreamError) as error:
        fetch_official_arxiv("1706.03762", transport=httpx2.MockTransport(handler), temp_dir=tmp_path)
    assert error.value.status_code == 504
    assert closed == [True]
    assert list(tmp_path.iterdir()) == []
    def healthy(request):
        return httpx2.Response(200, text=_SAMPLE_ATOM_FEED) if "api/query" in str(request.url) else httpx2.Response(200, content=_SAMPLE_PDF_BYTES)
    result = fetch_official_arxiv("1706.03762", transport=httpx2.MockTransport(healthy), temp_dir=tmp_path)
    assert result.pdf_path.read_bytes() == _SAMPLE_PDF_BYTES
