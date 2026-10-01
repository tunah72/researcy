"""Authorized original-byte delivery; no object location crosses this boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import logging
import re
import os
import socket
from threading import BoundedSemaphore, Lock, Timer
import time
from uuid import UUID

import urllib3
import anyio
from starlette.concurrency import iterate_in_threadpool
from starlette.responses import StreamingResponse

from researcy.config import get_settings
from researcy.db import get_conn
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.retrieval.repository import load_ready_document
from . import objects


_STREAM_SLOTS = BoundedSemaphore(8)
_CLEANUP_LIMIT = anyio.CapacityLimiter(8)
logger = logging.getLogger(__name__)


@contextmanager
def bounded_database(conn, deadline: float) -> Iterator[None]:
    # A cancel request issued between SQL commands is lost. Shutting down a
    # duplicate socket also prevents later commands from starting after expiry.
    transport = socket.socket(fileno=os.dup(conn.fileno()))

    def interrupt():
        try:
            transport.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    timer = Timer(max(0, deadline-time.monotonic()), interrupt)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        timer.join()
        transport.close()


def deadline_pool(deadline: float) -> urllib3.PoolManager:
    """Own one transport pool per delivery; interrupt header and body reads."""
    class DeadlineConnection:
        def connect(self):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise objects.OriginalStorageError()
            self.timeout = min(5, remaining)
            super().connect()
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                self.close()
                raise objects.OriginalStorageError()
            sock = self.sock

            def interrupt():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            self._deadline_timer = Timer(remaining, interrupt)
            self._deadline_timer.daemon = True
            self._deadline_timer.start()

        def close(self):
            timer = getattr(self, '_deadline_timer', None)
            if timer is not None:
                timer.cancel()
            super().close()

    class HTTPConnection(DeadlineConnection, urllib3.connection.HTTPConnection):
        pass

    class HTTPSConnection(DeadlineConnection, urllib3.connection.HTTPSConnection):
        pass

    class HTTPPool(urllib3.HTTPConnectionPool):
        ConnectionCls = HTTPConnection

    class HTTPSPool(urllib3.HTTPSConnectionPool):
        ConnectionCls = HTTPSConnection

    class DeliveryPool(urllib3.PoolManager):
        def urlopen(self, *args, **kwargs):
            response = super().urlopen(*args, **kwargs)
            if time.monotonic() >= deadline:
                objects._close_response(response)
                raise objects.OriginalStorageError()
            return response

    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise objects.OriginalStorageError()
    pool = DeliveryPool(
        timeout=urllib3.Timeout(connect=min(5, remaining), read=min(5, remaining)),
        retries=False,
    )
    pool.pool_classes_by_scheme = {'http': HTTPPool, 'https': HTTPSPool}
    return pool


@dataclass(frozen=True, slots=True)
class ByteSelection:
    start: int
    length: int
    status: int


class InvalidRange(APIError):
    def __init__(self, total: int):
        super().__init__(416, 'PDF_RANGE_INVALID', 'The requested PDF range is invalid.')
        self.content_range = f'bytes */{total}'


def parse_byte_range(header: str | None, total: int) -> ByteSelection:
    if header is None:
        return ByteSelection(0, total, 200)
    if len(header.encode('utf-8')) > 256:
        raise InvalidRange(total)
    match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', header)
    if not match or not any(match.groups()):
        raise InvalidRange(total)
    left, right = match.groups()
    # A decimal field longer than uint64 cannot be a supported document range.
    if len(left) > 20 or len(right) > 20:
        raise InvalidRange(total)
    if any(int(field) > 2**64-1 for field in (left, right) if field):
        raise InvalidRange(total)
    if not left:
        suffix = int(right)
        if suffix == 0:
            raise InvalidRange(total)
        start, end = max(0, total-suffix), total-1
    else:
        start = int(left)
        end = int(right) if right else total-1
        if start >= total or end < start:
            raise InvalidRange(total)
        end = min(end, total-1)
    return ByteSelection(start, end-start+1, 206)


class PDFStream:
    def __init__(self, response, selection: ByteSelection, headers: dict[str, str], deadline: float,
                 storage=None):
        self.response = response
        self.selection = selection
        self.headers = headers
        self.status = selection.status
        self.deadline = deadline
        self.storage = storage
        self.managed = False
        self._closed = False
        self._lock = Lock()
        self._timer = Timer(max(0, deadline-time.monotonic()), self.abort)
        self._timer.daemon = True
        self._timer.start()

    def attach(self, response, storage) -> None:
        with self._lock:
            if self._closed or time.monotonic() >= self.deadline:
                raise objects.OriginalStorageError()
            self.response = response
            self.storage = storage

    def abort(self) -> None:
        if not self.managed:
            self.close()
        elif self.response is not None:
            try:
                self.response.shutdown()
            except (ValueError, RuntimeError, OSError):
                pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._timer.cancel()
        try:
            if self.response is not None:
                # Closing a buffered reader can wait on its active read lock.
                # Shutdown wakes a drip-fed read before closing/releasing it.
                try:
                    self.response.shutdown()
                except (ValueError, RuntimeError, OSError):
                    pass
                objects._close_response(self.response)
            self.storage = None
        finally:
            _STREAM_SLOTS.release()

    async def aclose(self) -> None:
        self.abort()
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(self.close, limiter=_CLEANUP_LIMIT)

    def body(self) -> Iterator[bytes]:
        remaining = self.selection.length
        try:
            while remaining:
                if self._closed or time.monotonic() >= self.deadline:
                    raise objects.OriginalStorageError()
                try:
                    chunk = self.response.read(min(64*1024, remaining))
                except Exception:
                    raise objects.OriginalStorageError() from None
                if not chunk:
                    raise objects.OriginalStorageError()
                remaining -= len(chunk)
                yield chunk
        finally:
            if not self.managed:
                self.close()


class PDFResponse(StreamingResponse):
    def __init__(self, stream: PDFStream, request_id: str):
        self.stream = stream
        self.request_id = request_id
        stream.managed = True
        content = stream.body() if stream.response is not None else iter(())
        super().__init__(iterate_in_threadpool(content), status_code=stream.status,
                         headers=stream.headers, media_type='application/pdf')

    async def __call__(self, scope, receive, send) -> None:
        try:
            with anyio.fail_after(max(0, self.stream.deadline-time.monotonic())):
                async with anyio.create_task_group() as group:
                    async def disconnected():
                        while True:
                            if (await receive())['type'] == 'http.disconnect':
                                self.stream.abort()
                                group.cancel_scope.cancel()
                                return

                    group.start_soon(disconnected)
                    try:
                        await self.stream_response(send)
                    finally:
                        group.cancel_scope.cancel()
        except* (TimeoutError, objects.OriginalStorageError, OSError):
            # Headers may already be sent: truncate, never re-enter JSON handling.
            logger.warning('pdf_stream_failed code=ORIGINAL_STORAGE_UNAVAILABLE request_id=%s',
                           self.request_id)
        finally:
            await self.stream.aclose()


def reader_document(conn, owner_id: UUID, paper_id: UUID, version_id: UUID | None) -> dict:
    document = load_ready_document(conn, owner_id, paper_id, version_id)
    scope = document.scope
    with short_transaction(conn):
        original = conn.execute(
            'SELECT sha256 FROM document_versions WHERE id=%s AND owner_id=%s AND paper_id=%s',
            (scope.document_version_id, owner_id, paper_id),
        ).fetchone()
        pages = conn.execute(
            '''SELECT page_index,media_box,crop_box,rotation FROM document_pages
               WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s ORDER BY page_index''',
            (owner_id, paper_id, scope.document_version_id),
        ).fetchall()
        outline = conn.execute(
            '''SELECT s.title,MIN(p.page_index) FROM document_sections s
               JOIN document_blocks b ON b.section_id=s.id AND b.owner_id=s.owner_id
                 AND b.paper_id=s.paper_id AND b.document_version_id=s.document_version_id
               JOIN document_pages p ON p.id=b.page_id AND p.owner_id=b.owner_id
                 AND p.paper_id=b.paper_id AND p.document_version_id=b.document_version_id
               WHERE s.owner_id=%s AND s.paper_id=%s AND s.document_version_id=%s
                 AND s.title IS NOT NULL AND NOT b.excluded
               GROUP BY s.id,s.title,s.ordinal ORDER BY s.ordinal''',
            (owner_id, paper_id, scope.document_version_id),
        ).fetchall()
    return {
        'document_version': scope.document_version_id,
        'source_sha256': bytes(original[0]).hex(),
        'pdf_url': f'/api/papers/{paper_id}/versions/{scope.document_version_id}/pdf',
        'pages': [dict(zip(('page_index','media_box','crop_box','rotation'), row)) for row in pages],
        'outline': [{'title': row[0], 'page': row[1]+1} for row in outline],
    }


def open_owned_pdf(owner_id: UUID, paper_id: UUID, version_id: UUID,
                   range_header: str | None, if_range: str | None, *, download: bool = False,
                   head: bool = False, deadline: float | None = None) -> PDFStream:
    deadline = time.monotonic()+30 if deadline is None else deadline
    with get_conn() as conn:
        with bounded_database(conn, deadline):
            load_ready_document(conn, owner_id, paper_id, version_id)
            with short_transaction(conn):
                original = conn.execute(
                    '''SELECT object_key,byte_count,sha256 FROM document_versions
                       WHERE id=%s AND owner_id=%s AND paper_id=%s''',
                    (version_id, owner_id, paper_id),
                ).fetchone()
    key, total, digest = original
    if not 0 < total <= get_settings().max_upload_bytes:
        raise objects.OriginalStorageError()
    etag = f'"{bytes(digest).hex()}"'
    selection = parse_byte_range(range_header if if_range is None or if_range == etag else None, total)
    if not _STREAM_SLOTS.acquire(blocking=False):
        raise APIError(503, 'PDF_STREAM_BUSY', 'The PDF is temporarily unavailable. Please retry.')
    stream = PDFStream(None, selection, {}, deadline)
    response = None
    try:
        storage = objects._client(http_client=deadline_pool(deadline))
        metadata = storage.stat_object(objects._bucket(), key)
        if metadata.size != total or time.monotonic() >= deadline:
            raise objects.OriginalStorageError()
        if not head:
            response = storage.get_object(objects._bucket(), key, offset=selection.start,
                                          length=selection.length)
        if time.monotonic() >= deadline:
            raise objects.OriginalStorageError()
        headers = {
            'Content-Length': str(selection.length), 'Accept-Ranges': 'bytes', 'ETag': etag,
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Disposition': f'{"attachment" if download else "inline"}; filename="paper.pdf"',
        }
        if selection.status == 206:
            headers['Content-Range'] = f'bytes {selection.start}-{selection.start+selection.length-1}/{total}'
        stream.attach(response, storage)
        stream.headers = headers
        return stream
    except Exception:
        if response is not None:
            objects._close_response(response)
        stream.close()
        raise objects.OriginalStorageError() from None
