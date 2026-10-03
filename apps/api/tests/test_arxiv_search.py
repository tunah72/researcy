import asyncio
from contextlib import asynccontextmanager
from email.utils import formatdate
import logging
import time
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

import httpx2
import pytest

from researcy.errors import APIError
from researcy.papers import arxiv


@pytest.fixture(autouse=True)
def _isolated_search_limiter(monkeypatch):
    monkeypatch.setattr(arxiv, "_GLOBAL_LIMITER", arxiv.ArxivLimiter(min_interval=0))


def _entry(identifier, title="Attention mechanisms", authors=(), abstract=None):
    fields = [f"<id>{escape(identifier)}</id>", f"<title>{escape(title)}</title>"]
    fields.extend(f"<author><name>{escape(name)}</name></author>" for name in authors)
    if abstract is not None:
        fields.append(f"<summary>{escape(abstract)}</summary>")
    fields.append('<link href="https://hostile.example/private.pdf" rel="related"/>')
    return "<entry>" + "".join(fields) + "</entry>"


def _feed(entries):
    return '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>"


async def _search(transport, seconds=2, query='(all:"attention")', request_id="search-test"):
    return await arxiv.search_official_arxiv_metadata(
        query, deadline=time.monotonic() + seconds, request_id=request_id, transport=transport,
    )


def _from_feed(feed):
    return asyncio.run(_search(httpx2.MockTransport(lambda request: httpx2.Response(200, text=feed))))


def test_related_query_uses_title_group_and_additional_abstract_group_only():
    query = arxiv.build_related_query(
        'Attention OR "all" cat:physics https://hostile.example q attention',
        'Attention and Transformers retrieval retrieval for language models',
    )
    assert query == (
        '(all:"attention" OR all:"cat" OR all:"physics" OR all:"https" OR '
        'all:"hostile" OR all:"example" OR all:"q") AND '
        '(abs:"transformers" OR abs:"retrieval" OR abs:"language" OR abs:"models")'
    )
    assert "cat:" not in query and "https://" not in query


def test_related_query_bounds_distinct_unicode_title_and_abstract_terms():
    title = "α " + " ".join(f"title{i}" for i in range(20)) + " " + "x" * 81
    abstract = "α title0 " + " ".join(f"abstract{i}" for i in range(20))
    query = arxiv.build_related_query(title, abstract)
    assert query.count('all:"') == 12
    assert query.count('abs:"') == 8
    assert 'all:"α"' in query and 'all:"title10"' in query
    assert 'all:"title11"' not in query and 'abs:"α"' not in query
    assert 'abs:"abstract7"' in query and 'abs:"abstract8"' not in query
    assert "x" * 81 not in query
    assert arxiv.build_related_query("Attention mechanisms", "and or attention mechanisms") == (
        '(all:"attention" OR all:"mechanisms")'
    )


@pytest.mark.parametrize("title", [None, "", "The and of", "untitled", "???", "x\x00y"])
def test_related_query_never_substitutes_abstract_for_missing_title(title):
    with pytest.raises(APIError) as caught:
        arxiv.build_related_query(title, "Useful attention abstract")
    assert caught.value.status_code == 409
    assert caught.value.code == "DISCOVERY_METADATA_MISSING"


def test_search_normalizes_identity_and_unknown_metadata_without_following_feed_links(caplog):
    requests = []
    feed = _feed([
        _entry("http://arxiv.org/abs/1706.03762v7", " Attention\n mechanisms ",
               (" Ada\n Lovelace ",), " Supplied\n abstract "),
        _entry("https://arxiv.org/abs/hep-th/9901001v2", "Legacy quantum theory"),
        _entry("https://arxiv.org/abs/1706.03762v3", "Attention mechanisms",
               ("Ada Lovelace",), "Supplied abstract"),
        _entry("https://hostile.example/abs/2301.00001", "Invalid identity"),
        _entry("2301.00002", "Sparse metadata", abstract=" \n "),
    ])
    def handler(request):
        requests.append(request)
        return httpx2.Response(200, text=feed)
    with caplog.at_level(logging.INFO, logger="researcy.papers.arxiv"):
        result = asyncio.run(_search(httpx2.MockTransport(handler), request_id="official-search-42"))
    assert [item.arxiv_id for item in result.candidates] == ["1706.03762", "hep-th/9901001", "2301.00002"]
    first, legacy, sparse = result.candidates
    assert (first.title, first.authors, first.abstract) == (
        "Attention mechanisms", ("Ada Lovelace",), "Supplied abstract",
    )
    assert legacy.authors == () and legacy.abstract is None and sparse.abstract is None
    assert (result.inspected_entries, result.inspected_unique, result.invalid_ids, result.duplicates) == (5, 3, 1, 1)
    assert (result.http_requests, result.redirects) == (1, 0)
    assert len(requests) == 1
    request = requests[0]
    assert (request.method, request.url.scheme, request.url.host, request.url.path) == (
        "GET", "https", "export.arxiv.org", "/api/query",
    )
    assert dict(request.url.params) == {
        "search_query": '(all:"attention")', "start": "0", "max_results": "10",
        "sortBy": "relevance", "sortOrder": "descending",
    }
    assert "Researcy/" in request.headers["User-Agent"]
    assert "official-search-42" in caplog.text
    assert "Supplied abstract" not in caplog.text and "search_query=" not in caplog.text


def test_search_inspects_only_first_ten_entries_including_invalid_and_duplicates():
    entries = [_entry("2301.00001v1"), _entry("2301.00001v2"), _entry("invalid")]
    entries += [_entry(f"2301.{i:05d}") for i in range(2, 9)]
    entries += [_entry("2301.00001v3", "Conflicting eleventh entry")]
    result = _from_feed(_feed(entries))
    assert len(result.candidates) == 8
    assert [item.arxiv_id for item in result.candidates] == [f"2301.{i:05d}" for i in range(1, 9)]
    assert (result.inspected_entries, result.inspected_unique, result.invalid_ids, result.duplicates) == (10, 8, 1, 1)


def test_search_discards_unrepresentable_version_identifier_safely():
    result = _from_feed(_feed([_entry("2301.00001v" + "9" * 5000), _entry("2301.00002")]))
    assert [item.arxiv_id for item in result.candidates] == ["2301.00002"]
    assert result.inspected_entries == 2 and result.invalid_ids == 1


@pytest.mark.parametrize("second", [
    _entry("2301.00001v2", "Different title", ("First author",), "Abstract"),
    _entry("2301.00001v2", "Attention mechanisms", ("Different author",), "Abstract"),
    _entry("2301.00001v2", "Attention mechanisms", ("First author",), "Changed abstract"),
    _entry("2301.00001v2", "Attention mechanisms", (), "Abstract"),
])
def test_search_fails_whole_response_on_conflicting_canonical_metadata(second):
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        _from_feed(_feed([
            _entry("2301.00001v1", authors=("First author",), abstract="Abstract"), second,
        ]))
    assert caught.value.status_code == 502 and caught.value.code == "ARXIV_UPSTREAM_ERROR"


def test_conflicting_duplicate_is_not_hidden_by_skipping_its_first_missing_title():
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        _from_feed(_feed([_entry("2301.00001v1", ""), _entry("2301.00001v2", "Supplied title")]))
    assert caught.value.status_code == 502


def test_search_compares_full_abstracts_before_provider_context_truncation():
    prefix = "metadata " * 900
    with pytest.raises(arxiv.ArxivUpstreamError):
        _from_feed(_feed([
            _entry("2301.00001v1", abstract=prefix + "first ending"),
            _entry("2301.00001v2", abstract=prefix + "second ending"),
        ]))
    result = _from_feed(_feed([_entry("2301.00002", abstract=prefix + "retained ending")]))
    assert result.candidates[0].abstract.endswith("retained ending")
    assert len(result.candidates[0].abstract) > 6000


@pytest.mark.parametrize("feed", [
    "<feed>", "<html>not an Atom feed</html>",
    _feed([_entry("http://arxiv.org/api/errors#bad_query", "Error")]),
    '<!DOCTYPE feed [<!ENTITY secret "private-entity-marker">]>'
    '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>2301.00001</id>'
    '<title>&secret;</title></entry></feed>',
])
def test_search_malformed_or_error_feed_is_not_empty_success(feed):
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        _from_feed(feed)
    assert caught.value.status_code == 502
    assert "private-entity-marker" not in caught.value.message


def test_empty_atom_feed_is_honest_empty_search():
    result = _from_feed(_feed([]))
    assert result.candidates == ()
    assert (result.inspected_entries, result.inspected_unique, result.invalid_ids, result.duplicates) == (0, 0, 0, 0)
    assert result.http_requests == 1


@pytest.mark.parametrize("title", ["", " \n ", "Unknown title", "!!!"])
def test_search_skips_unusable_title_without_inventing_metadata(title):
    result = _from_feed(_feed([_entry("2301.00001", title), _entry("2301.00002", "Valid title")]))
    assert [item.arxiv_id for item in result.candidates] == ["2301.00002"]
    assert result.inspected_entries == 2 and result.inspected_unique == 2


@pytest.mark.parametrize("entry", [
    _entry("2301.00001", "x" * 1001),
    _entry("2301.00001", authors=("a" * 201,)),
    _entry("2301.00001", authors=tuple(f"Author {i}" for i in range(201))),
    _entry("2301.00001", "Unsafe\u202etitle"),
    _entry("2301.00001", authors=("Unsafe\u202eauthor",)),
    _entry("2301.00001", abstract="Unsafe\u202eabstract"),
    '<entry><id>2301.00001</id><title>Partial <span>hidden title</span></title></entry>',
    '<entry><id>2301.00001</id><title>Safe title</title><summary>Partial <span>abstract</span></summary></entry>',
    '<entry><id>2301.00001</id><title>Safe title</title><author><name>Partial <span>author</span></name></author></entry>',
])
def test_search_rejects_oversized_or_unsafe_authoritative_metadata(entry):
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        _from_feed(_feed([entry]))
    assert caught.value.status_code == 502


def test_search_oversized_stream_stops_reading_and_releases_limiter():
    class OversizedStream(httpx2.AsyncByteStream):
        def __init__(self):
            self.chunks = 0
            self.closed = False
        async def __aiter__(self):
            for _ in range(40):
                self.chunks += 1
                yield b"x" * (64 * 1024)
        async def aclose(self):
            self.closed = True
    stream = OversizedStream()
    async def exercise():
        with pytest.raises(arxiv.ArxivUpstreamError) as caught:
            await _search(httpx2.MockTransport(lambda request: httpx2.Response(200, stream=stream)))
        assert caught.value.status_code == 502
        assert stream.chunks == 17 and stream.closed
        return await _search(httpx2.MockTransport(lambda request: httpx2.Response(200, text=_feed([]))))
    assert asyncio.run(exercise()).candidates == ()


@pytest.mark.parametrize("location", [
    "https://hostile.example/api/query", "http://export.arxiv.org/api/query",
    "https://user@arxiv.org/api/query", "https://arxiv.org:443/api/query",
    "https://arxiv.org/pdf/2301.00001", "https://arxiv.org/abs/2301.00001",
    "https://export.arxiv.org/api/query?search_query=all:changed&start=0&max_results=10&sortBy=relevance&sortOrder=descending",
])
def test_search_redirect_cannot_change_destination_or_search_arguments(location):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx2.Response(302, headers={"Location": location})
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        asyncio.run(_search(httpx2.MockTransport(handler)))
    assert caught.value.status_code == 502
    assert len(requests) == 1


def test_search_counts_physical_redirect_hops_without_second_search():
    requests = []
    def handler(request):
        requests.append(request)
        if len(requests) < 3:
            url = request.url.copy_with(host="arxiv.org" if len(requests) == 1 else "export.arxiv.org")
            return httpx2.Response(307, headers={"Location": str(url)})
        return httpx2.Response(200, text=_feed([]))
    result = asyncio.run(_search(httpx2.MockTransport(handler)))
    assert result.http_requests == 3 and result.redirects == 2
    assert all(request.url.path == "/api/query" for request in requests)
    assert all(dict(request.url.params) == dict(requests[0].url.params) for request in requests)


def test_search_stops_after_three_redirects_and_never_retries():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(302, headers={"Location": str(request.url)})
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        asyncio.run(_search(httpx2.MockTransport(handler)))
    assert caught.value.status_code == 502 and len(calls) == 4


@pytest.mark.parametrize("status", [406, 429, 503])
@pytest.mark.parametrize("retry_after", ["45", "date", "9" * 5000, None])
def test_search_and_sync_import_share_cooldown_without_hidden_retry(status, retry_after, monkeypatch, tmp_path):
    monkeypatch.setattr(arxiv.time, "time", lambda: 1_800_000_000)
    header = formatdate(1_800_000_045, usegmt=True) if retry_after == "date" else retry_after
    headers = {} if header is None else {"Retry-After": header}
    requests = []
    def handler(request):
        requests.append(request)
        return httpx2.Response(status, headers=headers, text="private-upstream-marker")
    transport = httpx2.MockTransport(handler)
    async def exercise():
        with pytest.raises(arxiv.ArxivUpstreamError) as first:
            await _search(transport)
        expected = 45 if retry_after in {"45", "date"} else 60
        assert first.value.retry_after == expected
        assert "private-upstream-marker" not in first.value.message
        with pytest.raises(arxiv.ArxivUpstreamError) as second:
            await asyncio.to_thread(arxiv.fetch_official_arxiv, "1706.03762", transport=transport, temp_dir=tmp_path)
        assert second.value.retry_after == expected
        with pytest.raises(arxiv.ArxivUpstreamError):
            await _search(transport)
    asyncio.run(exercise())
    assert len(requests) == 1 and list(tmp_path.iterdir()) == []


def test_sync_import_cooldown_blocks_async_search_before_dispatch(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(429, headers={"Retry-After": "30"})
    transport = httpx2.MockTransport(handler)
    with pytest.raises(arxiv.ArxivUpstreamError):
        arxiv.fetch_official_arxiv("1706.03762", transport=transport, temp_dir=tmp_path)
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        asyncio.run(_search(transport))
    assert 29 <= caught.value.retry_after <= 30
    assert len(calls) == 1


def test_async_search_and_sync_import_share_three_second_start_spacing(monkeypatch, tmp_path):
    now = [1000.0]
    def advance(seconds):
        now[0] += seconds
    async def advance_async(seconds):
        advance(seconds)
        await asyncio.sleep(0)
    limiter = arxiv.ArxivLimiter(clock=lambda: now[0], sleep=advance, async_sleep=advance_async)
    monkeypatch.setattr(arxiv, "_GLOBAL_LIMITER", limiter)
    starts = []
    def handler(request):
        starts.append((request.url.path, now[0]))
        if request.url.path.startswith("/pdf/"):
            return httpx2.Response(200, content=b"%PDF-1.7\nfixture")
        return httpx2.Response(200, text=_feed([_entry("1706.03762v7")]))
    transport = httpx2.MockTransport(handler)
    async def exercise():
        await _search(transport)
        acquisition = await asyncio.to_thread(arxiv.fetch_official_arxiv, "1706.03762", transport=transport, temp_dir=tmp_path)
        acquisition.pdf_path.unlink()
        await _search(transport)
    asyncio.run(exercise())
    assert starts == [("/api/query", 1000.0), ("/api/query", 1003.0), ("/pdf/1706.03762v7", 1006.0), ("/api/query", 1009.0)]


def test_cancel_queued_search_does_not_escape_sync_exclusion_or_dispatch_late(monkeypatch):
    limiter = arxiv.ArxivLimiter(min_interval=0)
    monkeypatch.setattr(arxiv, "_GLOBAL_LIMITER", limiter)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx2.Response(200, text=_feed([]))
    transport = httpx2.MockTransport(handler)
    async def exercise():
        with limiter.acquire():
            task = asyncio.create_task(_search(transport))
            try:
                await asyncio.sleep(0.05)
                assert requests == [] and not task.done()
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        await asyncio.sleep(0.05)
        assert requests == []
        return await _search(transport)
    assert asyncio.run(exercise()).http_requests == 1
    assert len(requests) == 1


def test_cancel_pacing_wait_releases_lease_without_advancing_late_request(monkeypatch):
    now = [1000.0]
    waiting = None
    async def blocked_sleep(seconds):
        waiting.set()
        await asyncio.Event().wait()
    limiter = arxiv.ArxivLimiter(clock=lambda: now[0], async_sleep=blocked_sleep)
    monkeypatch.setattr(arxiv, "_GLOBAL_LIMITER", limiter)
    with limiter.acquire():
        pass
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(200, text=_feed([]))
    async def exercise():
        nonlocal waiting
        waiting = asyncio.Event()
        task = asyncio.create_task(_search(httpx2.MockTransport(handler)))
        await asyncio.wait_for(waiting.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == []
        now[0] = 1003.0
        return await _search(httpx2.MockTransport(handler))
    assert asyncio.run(exercise()).http_requests == 1 and len(calls) == 1


class _LoopbackTransport(httpx2.AsyncBaseTransport):
    """Exercise real sockets without weakening production official-host validation."""
    def __init__(self, port):
        self.port = port
        self.inner = httpx2.AsyncHTTPTransport(retries=0)
    async def handle_async_request(self, request):
        local_url = request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        local_request = httpx2.Request(request.method, local_url, headers=request.headers, extensions=request.extensions)
        return await self.inner.handle_async_request(local_request)
    async def aclose(self):
        await self.inner.aclose()


@asynccontextmanager
async def _local_metadata_server(respond):
    tasks = set()
    paths = []
    async def accept(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            path = headers.split(b"\r\n", 1)[0].split(b" ")[1].decode()
            paths.append(path)
            await respond(reader, writer, path, len(paths))
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            tasks.discard(task)
    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1], paths
    finally:
        server.close()
        await server.wait_closed()
        for task in tuple(tasks):
            task.cancel()
        await asyncio.gather(*tuple(tasks), return_exceptions=True)


async def _send_feed(writer):
    payload = _feed([]).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/atom+xml\r\nContent-Length: " +
                 str(len(payload)).encode() + b"\r\nConnection: close\r\n\r\n" + payload)
    await writer.drain()


@pytest.mark.parametrize("fault", ["headers", "body", "drip"])
def test_real_socket_deadline_covers_headers_body_and_drip_and_releases_lease(fault):
    async def exercise():
        closed = asyncio.Event()
        async def respond(reader, writer, path, number):
            if number > 1:
                await _send_feed(writer)
                return
            if fault != "headers":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n<")
                await writer.drain()
            eof = asyncio.create_task(reader.read())
            try:
                if fault == "drip":
                    while not eof.done():
                        writer.write(b" ")
                        await writer.drain()
                        await asyncio.sleep(0.02)
                await eof
                closed.set()
            except ConnectionError:
                closed.set()
            finally:
                eof.cancel()
                await asyncio.gather(eof, return_exceptions=True)
        async with _local_metadata_server(respond) as (port, paths):
            started = time.monotonic()
            with pytest.raises(arxiv.ArxivUpstreamError) as caught:
                await _search(_LoopbackTransport(port), seconds=0.15)
            assert caught.value.status_code == 504
            assert time.monotonic() - started < 1
            await asyncio.wait_for(closed.wait(), 1)
            result = await _search(_LoopbackTransport(port))
            assert result.candidates == () and result.http_requests == 1 and len(paths) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_real_socket_cancellation_closes_active_response_and_allows_next_search(phase):
    async def exercise():
        entered, closed = asyncio.Event(), asyncio.Event()
        async def respond(reader, writer, path, number):
            if number > 1:
                await _send_feed(writer)
                return
            if phase == "body":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 10000\r\n\r\n<feed>")
                await writer.drain()
            entered.set()
            await reader.read()
            closed.set()
        async with _local_metadata_server(respond) as (port, paths):
            task = asyncio.create_task(_search(_LoopbackTransport(port)))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(closed.wait(), 1)
            assert len(paths) == 1
            result = await _search(_LoopbackTransport(port))
            assert result.http_requests == 1 and len(paths) == 2
    asyncio.run(exercise())


def test_real_socket_redirects_share_one_aggregate_deadline():
    async def exercise():
        async def respond(reader, writer, path, number):
            await asyncio.sleep(0.09)
            writer.write(b"HTTP/1.1 307 Temporary Redirect\r\nLocation: https://export.arxiv.org" +
                         path.encode() + b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        async with _local_metadata_server(respond) as (port, paths):
            with pytest.raises(arxiv.ArxivUpstreamError) as caught:
                await _search(_LoopbackTransport(port), seconds=0.15)
            assert caught.value.status_code == 504 and len(paths) == 2
            assert parse_qs(paths[0].split("?", 1)[1]) == parse_qs(paths[1].split("?", 1)[1])
    asyncio.run(exercise())


def test_deadline_expired_or_exhausted_in_limiter_has_zero_outbound_requests(monkeypatch):
    limiter = arxiv.ArxivLimiter(min_interval=0)
    monkeypatch.setattr(arxiv, "_GLOBAL_LIMITER", limiter)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(200, text=_feed([]))
    async def exercise():
        for seconds in [-1, 0.05]:
            with limiter.acquire():
                with pytest.raises(arxiv.ArxivUpstreamError) as caught:
                    await _search(httpx2.MockTransport(handler), seconds=seconds)
                assert caught.value.status_code == 504
        assert calls == []
    asyncio.run(exercise())


def test_search_retains_legitimate_joiners_in_official_unicode_names():
    result = _from_feed(_feed([_entry("2301.00001", "Unicode attention", ("Zoe\u200dName",))]))
    assert result.candidates[0].authors == ("Zoe\u200dName",)


def test_search_rejects_utf16_dtd_before_entity_expansion():
    feed = ('<?xml version="1.0" encoding="UTF-16"?>'
            '<!DOCTYPE feed [<!ENTITY secret "private-entity-marker">]>'
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>2301.00001</id>'
            '<title>&secret;</title></entry></feed>').encode("utf-16")
    with pytest.raises(arxiv.ArxivUpstreamError) as caught:
        asyncio.run(_search(httpx2.MockTransport(lambda request: httpx2.Response(200, content=feed))))
    assert caught.value.status_code == 502 and "private-entity-marker" not in caught.value.message


def test_sync_import_cannot_overlap_active_async_search(tmp_path):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def search_handler(request):
            calls.append("search")
            entered.set()
            await release.wait()
            return httpx2.Response(200, text=_feed([]))
        def import_handler(request):
            calls.append("pdf" if request.url.path.startswith("/pdf/") else "import metadata")
            if request.url.path.startswith("/pdf/"):
                return httpx2.Response(200, content=b"%PDF-1.7\nfixture")
            return httpx2.Response(200, text=_feed([_entry("1706.03762v7")]))
        search = asyncio.create_task(_search(httpx2.MockTransport(search_handler)))
        await asyncio.wait_for(entered.wait(), 1)
        intake = asyncio.create_task(asyncio.to_thread(
            arxiv.fetch_official_arxiv, "1706.03762",
            transport=httpx2.MockTransport(import_handler), temp_dir=tmp_path,
        ))
        try:
            await asyncio.sleep(0.05)
            assert calls == ["search"] and not intake.done()
        finally:
            release.set()
            await search
        acquisition = await asyncio.wait_for(intake, 1)
        acquisition.pdf_path.unlink()
        assert calls == ["search", "import metadata", "pdf"]
    asyncio.run(exercise())


def test_search_stage_ceiling_applies_even_with_longer_parent_deadline(monkeypatch):
    monkeypatch.setattr(arxiv, "_MAX_RESPONSE_SECONDS", 0.1)
    async def exercise():
        async def respond(reader, writer, path, number):
            await reader.read()
        async with _local_metadata_server(respond) as (port, paths):
            started = time.monotonic()
            with pytest.raises(arxiv.ArxivUpstreamError) as caught:
                await _search(_LoopbackTransport(port), seconds=2)
            assert caught.value.status_code == 504 and len(paths) == 1
            assert time.monotonic() - started < 1
    asyncio.run(exercise())
