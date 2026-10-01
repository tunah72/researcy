import hashlib
import time
from uuid import uuid4

import pytest

from test_library import client, _authenticate
from researcy.papers import objects
from researcy.retrieval import index


@pytest.fixture
def pdf_case(selected_index, client, tmp_path):
    fixture = selected_index
    deadline = time.monotonic() + 60
    index.index_selected(fixture['lease'], deadline)
    receipt = index.verify_index(fixture['lease'], deadline)
    index.publish_ready(fixture['conn'], fixture['lease'], receipt)
    scope = fixture['scope']
    _authenticate(client, fixture['conn'], scope.owner_id)
    original = (tmp_path / 'original.pdf').read_bytes()
    return scope, original, f'/api/papers/{scope.paper_id}/versions/{scope.document_version_id}/pdf'


def test_full_pdf_and_download_preserve_original_bytes(pdf_case, client):
    scope, original, url = pdf_case
    for suffix, disposition in [('', 'inline'), ('?download=1', 'attachment')]:
        response = client.get(url + suffix)
        assert response.status_code == 200
        assert response.content == original
        assert response.headers['content-type'] == 'application/pdf'
        assert response.headers['content-length'] == str(len(original))
        assert response.headers['content-disposition'] == f'{disposition}; filename="paper.pdf"'
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['accept-ranges'] == 'bytes'
        assert response.headers['etag'] == f'"{hashlib.sha256(original).hexdigest()}"'
        assert response.headers['x-request-id']
    detail = client.get(f'/api/papers/{scope.paper_id}').json()
    assert detail['reader']['document_version'] == str(scope.document_version_id)
    assert detail['reader']['source_sha256'] == hashlib.sha256(original).hexdigest()
    assert detail['reader']['pdf_url'] == url
    assert detail['reader']['pages'][0]['page_index'] == 0
    assert 'object_key' not in detail['reader']


@pytest.mark.parametrize('range_header', ['bytes=10-29', 'bytes=10-', 'bytes=-20', 'bytes=0-999999'])
def test_range_returns_exact_original_slice(pdf_case, client, range_header):
    _, original, url = pdf_case
    if range_header == 'bytes=10-29':
        start, end = 10, 29
    elif range_header == 'bytes=10-':
        start, end = 10, len(original)-1
    elif range_header == 'bytes=-20':
        start, end = len(original)-20, len(original)-1
    else:
        start, end = 0, len(original)-1
    response = client.get(url, headers={'Range': range_header})
    assert response.status_code == 206
    assert response.headers['content-range'] == f'bytes {start}-{end}/{len(original)}'
    assert response.content == original[start:end+1]
    head = client.head(url, headers={'Range': range_header})
    assert head.status_code == 206
    assert head.content == b''
    assert head.headers['content-range'] == response.headers['content-range']
    assert head.headers['content-length'] == str(end-start+1)


@pytest.mark.parametrize('header', ['bytes=-0', 'bytes=20-10', 'bytes=0-1,4-5', 'bytes=999999-', 'items=0-9', 'bytes=' + '9'*257 + '-', 'bytes=-18446744073709551616', 'bytes=0-18446744073709551616'])
def test_invalid_range_has_safe_authorized_416(pdf_case, client, header):
    _, original, url = pdf_case
    response = client.get(url, headers={'Range': header})
    assert response.status_code == 416
    assert response.headers['content-range'] == f'bytes */{len(original)}'
    assert response.json()['code'] == 'PDF_RANGE_INVALID'
    assert response.json()['request_id']


def test_if_range_mismatch_returns_full_original(pdf_case, client):
    _, original, url = pdf_case
    response = client.get(url, headers={'Range': 'bytes=10-29', 'If-Range': '"wrong"'})
    assert response.status_code == 200
    assert response.content == original
    response = client.get(url, headers={'Range': 'bytes=10-29', 'If-Range': f'"{hashlib.sha256(original).hexdigest()}"'})
    assert response.status_code == 206
    assert response.content == original[10:30]


def test_foreign_and_random_version_share_404_before_storage(pdf_case, selected_index, client, monkeypatch):
    scope, _, url = pdf_case
    def forbidden():
        pytest.fail('Unauthorized request touched private storage')
    monkeypatch.setattr(objects, '_client', forbidden)
    paths = [
        f'/api/papers/{scope.paper_id}/versions/{uuid4()}/pdf',
        f'/api/papers/{uuid4()}/versions/{scope.document_version_id}/pdf',
    ]
    for path in paths:
        response = client.get(path, headers={'Range': 'broken'})
        assert response.status_code == 404
        assert response.json()['code'] == 'RESOURCE_NOT_FOUND'
    conn = selected_index['conn']
    foreign = conn.execute(
        'INSERT INTO users(issuer,sub) VALUES (%s,%s) RETURNING id',
        ('https://accounts.google.com', str(uuid4())),
    ).fetchone()[0]
    _authenticate(client, conn, foreign)
    for path in (url, paths[1]):
        response = client.get(path, headers={'Range': 'broken'})
        assert response.status_code == 404
        assert response.json()['code'] == 'RESOURCE_NOT_FOUND'
    client.cookies.clear()
    response = client.get(url)
    assert response.status_code == 401


def test_unready_pdf_is_rejected_before_storage(selected_index, client, monkeypatch):
    fixture = selected_index
    scope = fixture['scope']
    _authenticate(client, fixture['conn'], scope.owner_id)
    def forbidden():
        pytest.fail('Unready request touched private storage')
    monkeypatch.setattr(objects, '_client', forbidden)
    response = client.get(f'/api/papers/{scope.paper_id}/versions/{scope.document_version_id}/pdf')
    assert response.status_code == 409
    assert response.json()['code'] == 'PAPER_NOT_READY'


def test_storage_failure_before_headers_is_safe_json(pdf_case, client, monkeypatch):
    _, _, url = pdf_case
    def failed():
        raise RuntimeError('private credential and provider body')
    monkeypatch.setattr(objects, '_client', failed)
    response = client.get(url)
    assert response.status_code == 503
    assert response.json()['code'] == 'ORIGINAL_STORAGE_UNAVAILABLE'
    assert 'credential' not in response.text
    assert response.json()['request_id']


@pytest.fixture
def drip_original():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Event, Thread
    import urllib3

    stop = Event()

    class DripOriginal(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '65536')
            self.end_headers()
            self.close_connection = True
            try:
                while not stop.wait(0.02):
                    self.wfile.write(b'x')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), DripOriginal)
    server.daemon_threads = True
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    pool = urllib3.PoolManager(timeout=urllib3.Timeout(connect=1, read=1), retries=False)
    response = pool.request('GET', f'http://127.0.0.1:{server.server_port}/', preload_content=False)
    try:
        yield response
    finally:
        stop.set()
        objects._close_response(response)
        pool.clear()
        server.shutdown()
        server.server_close()


def test_deadline_interrupts_drip_fed_original_body(drip_original):
    from threading import Event, Thread
    from researcy.papers.pdf import PDFStream, ByteSelection, _STREAM_SLOTS

    finished = Event()
    failures = []
    assert _STREAM_SLOTS.acquire(blocking=False)
    stream = PDFStream(drip_original, ByteSelection(0, 65536, 200), {}, time.monotonic()+0.15)

    def consume():
        try:
            list(stream.body())
        except objects.OriginalStorageError as error:
            failures.append(error)
        finally:
            finished.set()

    consuming = Thread(target=consume, daemon=True)
    consuming.start()
    try:
        assert finished.wait(0.75), 'PDF deadline did not interrupt an active drip-fed read'
        assert len(failures) == 1
    finally:
        consuming.join(timeout=2)
        stream.close()


def test_revoked_cookie_cannot_request_subsequent_pdf_range(pdf_case, selected_index, client, monkeypatch):
    scope, original, url = pdf_case
    assert client.get(url, headers={'Range': 'bytes=0-9'}).content == original[:10]
    conn = selected_index['conn']
    conn.execute('UPDATE sessions SET revoked=TRUE WHERE owner_id=%s', (scope.owner_id,))
    conn.commit()

    def forbidden():
        pytest.fail('Revoked session touched private storage')

    monkeypatch.setattr(objects, '_client', forbidden)
    response = client.get(url, headers={'Range': 'bytes=10-19'})
    assert response.status_code == 401
    assert response.json()['code'] == 'UNAUTHENTICATED'


def test_eight_open_original_streams_bound_capacity_and_close_releases_it(pdf_case, client):
    from researcy.papers.pdf import open_owned_pdf

    scope, original, url = pdf_case
    streams = []
    try:
        for _ in range(8):
            streams.append(open_owned_pdf(scope.owner_id, scope.paper_id,
                                          scope.document_version_id, None, None))
        response = client.get(url, headers={'Range': 'bytes=0-9'})
        assert response.status_code == 503
        assert response.json()['code'] == 'PDF_STREAM_BUSY'
    finally:
        for stream in streams:
            stream.close()
    response = client.get(url, headers={'Range': 'bytes=0-9'})
    assert response.status_code == 206
    assert response.content == original[:10]


def test_duplicate_range_fields_are_rejected_after_ownership(pdf_case, client):
    _, _, url = pdf_case
    response = client.get(url, headers=[('Range', 'bytes=0-9'), ('Range', 'bytes=10-19')])
    assert response.status_code == 416
    assert response.json()['code'] == 'PDF_RANGE_INVALID'


def test_stalled_downstream_send_expires_and_releases_capacity(caplog):
    import asyncio
    import io
    import urllib3
    from researcy.papers.pdf import PDFStream, PDFResponse, ByteSelection, _STREAM_SLOTS

    async def exercise():
        assert _STREAM_SLOTS.acquire(blocking=False)
        stream = PDFStream(urllib3.HTTPResponse(body=io.BytesIO(b'x'*65536), preload_content=False),
                           ByteSelection(0, 65536, 200), {}, time.monotonic()+0.15)
        response = PDFResponse(stream, 'safe-deadline-request')
        sending = asyncio.Event()

        async def send(message):
            if message['type'] == 'http.response.body':
                sending.set()
                await asyncio.Event().wait()

        async def receive():
            await asyncio.Event().wait()

        task = asyncio.create_task(response({'type': 'http', 'asgi': {'spec_version': '2.4'}},
                                            receive, send))
        await asyncio.wait_for(sending.wait(), 0.75)
        held = []
        try:
            for _ in range(7):
                assert _STREAM_SLOTS.acquire(blocking=False)
                held.append(True)
            assert not _STREAM_SLOTS.acquire(blocking=False)
            await asyncio.wait_for(task, 0.75)
            assert _STREAM_SLOTS.acquire(blocking=False)
            held.append(True)
        finally:
            task.cancel()
            for _ in held:
                _STREAM_SLOTS.release()
            stream.close()

    asyncio.run(exercise())
    assert 'safe-deadline-request' in caplog.text
    assert 'ORIGINAL_STORAGE_UNAVAILABLE' in caplog.text


@pytest.mark.parametrize('asgi_version', ['2.3', '2.4'])
def test_midstream_short_original_logs_safe_failure_without_json_handler(caplog, asgi_version):
    import asyncio
    import io
    import urllib3
    from researcy.papers.pdf import PDFStream, PDFResponse, ByteSelection, _STREAM_SLOTS

    async def exercise():
        assert _STREAM_SLOTS.acquire(blocking=False)
        stream = PDFStream(urllib3.HTTPResponse(body=io.BytesIO(b'abc'), preload_content=False),
                           ByteSelection(0, 10, 200), {}, time.monotonic()+1)
        response = PDFResponse(stream, 'safe-short-request')
        messages = []

        async def send(message):
            messages.append(message)

        async def receive():
            await asyncio.Event().wait()

        await response({'type': 'http', 'asgi': {'spec_version': asgi_version}}, receive, send)
        assert messages[0]['type'] == 'http.response.start'
        assert messages[-1]['body'] == b'abc'
        assert messages[-1]['more_body'] is True

    asyncio.run(exercise())
    assert 'safe-short-request' in caplog.text
    assert 'ORIGINAL_STORAGE_UNAVAILABLE' in caplog.text


def test_storage_header_drip_is_interrupted_at_absolute_deadline():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Event, Thread
    import urllib3
    from researcy.papers.pdf import deadline_pool

    stop = Event()

    class DripHeaders(BaseHTTPRequestHandler):
        def do_GET(self):
            self.close_connection = True
            try:
                self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                self.wfile.flush()
                while not stop.wait(0.02):
                    self.wfile.write(b'x')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), DripHeaders)
    server.daemon_threads = True
    Thread(target=server.serve_forever, daemon=True).start()
    started = time.monotonic()
    pool = deadline_pool(started+0.15)
    try:
        with pytest.raises((urllib3.exceptions.HTTPError, objects.OriginalStorageError)):
            pool.request('GET', f'http://127.0.0.1:{server.server_port}/', preload_content=False)
        assert time.monotonic()-started < 0.75
    finally:
        stop.set()
        pool.clear()
        server.shutdown()
        server.server_close()


def test_database_deadline_prevents_commands_after_idle_expiry(pg_conn):
    import psycopg
    from conftest import _database_url
    from threading import Event
    from researcy.papers.pdf import bounded_database

    with psycopg.connect(_database_url(pg_conn.info.dbname)) as conn:
        with bounded_database(conn, time.monotonic()+0.1):
            Event().wait(0.2)
            started = time.monotonic()
            with pytest.raises(psycopg.Error):
                conn.execute('SELECT pg_sleep(5)')
            assert time.monotonic()-started < 0.75


def test_blocked_authentication_expires_as_safe_pdf_503(pdf_case, selected_index, client, monkeypatch):
    from researcy.papers import routes

    _, _, url = pdf_case
    conn = selected_index['conn']
    conn.execute('LOCK TABLE sessions IN ACCESS EXCLUSIVE MODE')
    monkeypatch.setattr(routes, 'PDF_WALL_SECONDS', 0.15)
    started = time.monotonic()
    try:
        response = client.get(url)
        assert response.status_code == 503
        assert response.json()['code'] == 'ORIGINAL_STORAGE_UNAVAILABLE'
        assert response.json()['request_id']
        assert time.monotonic()-started < 0.75
    finally:
        conn.rollback()


@pytest.mark.parametrize('asgi_version', ['2.3', '2.4'])
def test_disconnect_interrupts_active_original_read(drip_original, monkeypatch, asgi_version):
    import asyncio
    from researcy.papers.pdf import PDFStream, PDFResponse, ByteSelection, _STREAM_SLOTS

    async def exercise():
        loop = asyncio.get_running_loop()
        reading = asyncio.Event()
        original_read = drip_original.read

        def read(*args, **kwargs):
            loop.call_soon_threadsafe(reading.set)
            return original_read(*args, **kwargs)

        monkeypatch.setattr(drip_original, 'read', read)
        assert _STREAM_SLOTS.acquire(blocking=False)
        stream = PDFStream(drip_original, ByteSelection(0, 65536, 200), {}, time.monotonic()+5)
        response = PDFResponse(stream, 'safe-disconnect-request')

        async def send(message):
            pass

        async def receive():
            await reading.wait()
            return {'type': 'http.disconnect'}

        started = time.monotonic()
        await asyncio.wait_for(response({'type': 'http', 'asgi': {'spec_version': asgi_version}},
                                        receive, send), 0.75)
        assert time.monotonic()-started < 0.75
        assert stream._closed

    asyncio.run(exercise())


def test_cleanup_does_not_wait_for_shared_worker_capacity():
    import asyncio
    import anyio
    from researcy.papers.pdf import PDFStream, PDFResponse, ByteSelection, _STREAM_SLOTS

    async def exercise():
        shared = anyio.to_thread.current_default_thread_limiter()
        previous = shared.total_tokens
        shared.total_tokens = 1
        assert _STREAM_SLOTS.acquire(blocking=False)
        stream = PDFStream(None, ByteSelection(0, 10, 200), {}, time.monotonic()+0.15)
        response = PDFResponse(stream, 'safe-cleanup-request')

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            pass

        borrower = object()
        await shared.acquire_on_behalf_of(borrower)
        try:
            await asyncio.wait_for(response({'type': 'http', 'asgi': {'spec_version': '2.4'}},
                                            receive, send), 0.75)
            assert stream._closed
        finally:
            shared.release_on_behalf_of(borrower)
            shared.total_tokens = previous
            stream.close()

    asyncio.run(exercise())


def test_expired_storage_open_does_not_pin_pdf_capacity(pdf_case, client, monkeypatch):
    from threading import Event, Thread
    from researcy.papers.pdf import open_owned_pdf

    scope, original, url = pdf_case
    entered = Event()
    release = Event()
    finished = Event()
    failures = []
    create_client = objects._client

    def delayed_client(**kwargs):
        storage = create_client(**kwargs)
        stat = storage.stat_object

        def delayed_stat(*args, **options):
            if not entered.is_set():
                entered.set()
                release.wait(2)
            return stat(*args, **options)

        storage.stat_object = delayed_stat
        return storage

    monkeypatch.setattr(objects, '_client', delayed_client)

    def opening():
        try:
            stream = open_owned_pdf(scope.owner_id, scope.paper_id, scope.document_version_id,
                                    None, None, deadline=time.monotonic()+0.3)
            stream.close()
        except objects.OriginalStorageError as error:
            failures.append(error)
        finally:
            finished.set()

    thread = Thread(target=opening, daemon=True)
    thread.start()
    try:
        assert entered.wait(1)
        Event().wait(0.4)
        assert not finished.is_set()
        response = client.get(url, headers={'Range': 'bytes=0-9'})
        assert response.status_code == 206
        assert response.content == original[:10]
    finally:
        release.set()
        thread.join(timeout=3)
    assert finished.is_set()
    assert len(failures) == 1
