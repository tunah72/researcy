from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from typing import Any

import httpx2
import psycopg
import pymupdf

from researcy.config import Settings, get_settings
from researcy.db import get_conn
from researcy.documents.artifacts import _get_minio_client
from researcy.documents.sandbox import SandboxError
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.ingestion.models import IntegrityFailure, ProcessingProfile, StageFailure
from researcy.papers.screening import screen_pdf
from researcy.retrieval import embedding, index

HEAD_REVISION = "0003_m2_processing"


class PreflightFailure(Exception):
    def __init__(self, dependency: str, message: str = ""):
        self.dependency = dependency
        self.message = message
        super().__init__(f"Preflight check failed for dependency: {dependency}")


def check_migrations(conn: psycopg.Connection | None = None, settings: Settings | None = None) -> None:
    @contextmanager
    def _connection():
        if conn is not None:
            yield conn
        else:
            with get_conn() as c:
                yield c

    try:
        with _connection() as c:
            with short_transaction(c):
                row = c.execute("SELECT version_num FROM alembic_version").fetchone()
                if not row or row[0] != HEAD_REVISION:
                    raise PreflightFailure("postgres")
    except PreflightFailure:
        raise
    except Exception:
        raise PreflightFailure("postgres") from None


def check_storage(settings: Settings | None = None, *, timeout: float = 30.0) -> None:
    if settings is None:
        settings = get_settings()

    try:
        client = _get_minio_client(settings)
    except Exception:
        raise PreflightFailure("storage") from None

    probe_key = f"preflight-probes/{secrets.token_hex(16)}"
    probe_payload = secrets.token_bytes(64)
    probe_hash = hashlib.sha256(probe_payload).digest()

    delete_url = None
    try:
        put_url = client.presigned_put_object(settings.storage_bucket, probe_key)
        get_url = client.presigned_get_object(settings.storage_bucket, probe_key)
        delete_url = client.get_presigned_url("DELETE", settings.storage_bucket, probe_key)
    except Exception:
        raise PreflightFailure("storage") from None

    async def _run_probe():
        async with httpx2.AsyncClient(timeout=timeout, trust_env=False) as http_client:
            async with asyncio.timeout(timeout):
                # 1. PUT probe payload without buffering body
                async with http_client.stream(
                    "PUT",
                    put_url,
                    content=probe_payload,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(len(probe_payload)),
                    },
                ) as put_resp:
                    if not (200 <= put_resp.status_code < 300):
                        raise PreflightFailure("storage")

                # 2. GET readback with strict cap 64 + 1
                async with http_client.stream("GET", get_url) as get_resp:
                    if get_resp.status_code != 200:
                        raise PreflightFailure("storage")
                    total_bytes = 0
                    hasher = hashlib.sha256()
                    async for chunk in get_resp.aiter_raw(chunk_size=1024):
                        total_bytes += len(chunk)
                        if total_bytes > len(probe_payload) + 1:
                            raise PreflightFailure("storage")
                        hasher.update(chunk)

                    if total_bytes != len(probe_payload) or hasher.digest() != probe_hash:
                        raise PreflightFailure("storage")

    probe_err = None
    try:
        asyncio.run(_run_probe())
    except PreflightFailure as err:
        probe_err = err
    except (TimeoutError, asyncio.TimeoutError, httpx2.TimeoutException):
        probe_err = PreflightFailure("storage")
    except Exception:
        probe_err = PreflightFailure("storage")

    cleanup_timeout = min(timeout, 5.0)

    async def _run_cleanup():
        if delete_url is not None:
            async with httpx2.AsyncClient(timeout=cleanup_timeout, trust_env=False) as http_client:
                async with asyncio.timeout(cleanup_timeout):
                    async with http_client.stream("DELETE", delete_url) as del_resp:
                        if not (200 <= del_resp.status_code < 300 or del_resp.status_code == 204):
                            raise PreflightFailure("storage")
        else:
            client.remove_object(settings.storage_bucket, probe_key)

    cleanup_err = None
    try:
        asyncio.run(_run_cleanup())
    except PreflightFailure as err:
        cleanup_err = err
    except (TimeoutError, asyncio.TimeoutError, httpx2.TimeoutException):
        cleanup_err = PreflightFailure("storage")
    except Exception:
        cleanup_err = PreflightFailure("storage")

    if probe_err is not None:
        raise probe_err
    if cleanup_err is not None:
        raise cleanup_err


def check_qdrant(
    profile: ProcessingProfile | None = None,
    settings: Settings | None = None,
    *,
    timeout: float = 30.0,
) -> None:
    if profile is None:
        profile = ProcessingProfile()
    if settings is None:
        settings = get_settings()

    deadline = time.monotonic() + timeout
    try:
        with index.QdrantClient(endpoint=settings.qdrant_endpoint, deadline=deadline) as client:
            index.ensure_collection(profile, client=client)
            coll_name = index.collection_name(profile)
            res = client.request("GET", f"/collections/{coll_name}")
            validated = index._validate_collection_schema(res, profile)
            payload_schema = validated.get("payload_schema", {})
            for field in ("owner_id", "paper_id", "document_version_id", "section_type"):
                if field not in payload_schema or payload_schema[field].get("data_type") != "keyword":
                    raise PreflightFailure("qdrant")
    except PreflightFailure:
        raise
    except (IntegrityFailure, StageFailure):
        raise PreflightFailure("qdrant") from None
    except Exception:
        raise PreflightFailure("qdrant") from None


def check_embedding(
    profile: ProcessingProfile | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if profile is None:
        profile = ProcessingProfile()
    if settings is None:
        settings = get_settings()

    try:
        client = embedding.EmbeddingClient(profile, endpoint=settings.embedding_endpoint)
        identity = client.preflight()
        return identity
    except (PreflightFailure, StageFailure):
        raise PreflightFailure("embedding") from None
    except Exception:
        raise PreflightFailure("embedding") from None


def check_sandbox(
    settings: Settings | None = None,
    *,
    tmp_dir: Path | str | None = None,
    probe_pdf: Path | None = None,
) -> Any:
    if sys.platform != "linux":
        raise PreflightFailure("sandbox", "PDF sandbox requires Linux namespace isolation")

    if probe_pdf is not None:
        try:
            result = screen_pdf(probe_pdf, "application/pdf")
            if result.pages != 1 or not result.sha256 or result.bytes <= 0:
                raise PreflightFailure("sandbox")
            return result
        except PreflightFailure:
            raise
        except (SandboxError, APIError):
            raise PreflightFailure("sandbox") from None
        except Exception:
            raise PreflightFailure("sandbox") from None

    with tempfile.TemporaryDirectory(prefix="researcy-preflight-", dir=tmp_dir) as temp_dir:
        probe_file = Path(temp_dir) / "preflight_probe.pdf"
        try:
            with pymupdf.open() as document:
                page=document.new_page(width=300,height=400)
                page.insert_text((72,72),'Researcy sandbox readiness probe.')
                document.save(probe_file)
            result = screen_pdf(probe_file, "application/pdf")
            if result.pages != 1 or not result.sha256 or result.bytes <= 0:
                raise PreflightFailure("sandbox")
            return result
        except PreflightFailure:
            raise
        except (SandboxError, APIError):
            raise PreflightFailure("sandbox") from None
        except Exception:
            raise PreflightFailure("sandbox") from None


def run_preflight(
    conn: psycopg.Connection | None = None,
    settings: Settings | None = None,
    profile: ProcessingProfile | None = None,
) -> dict[str, Any]:
    if settings is None:
        settings = get_settings()
    if profile is None:
        profile = ProcessingProfile()

    check_migrations(conn=conn, settings=settings)
    check_storage(settings=settings)
    check_qdrant(profile=profile, settings=settings)
    identity = check_embedding(profile=profile, settings=settings)
    check_sandbox(settings=settings)

    return {
        "status": "ok",
        "embedding": identity,
    }


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="python -m researcy.ingestion.preflight",
        description="Verify runtime readiness and dependencies for Researcy M2 worker.",
        add_help=False,
    )
    parser.add_argument("--check", action="store_true", help="Run bounded non-mutating preflight checks")

    try:
        args, extra = parser.parse_known_args(argv)
        if extra or not args.check:
            print("Usage: python -m researcy.ingestion.preflight --check", file=sys.stderr)
            return 2
    except Exception:
        print("Usage: python -m researcy.ingestion.preflight --check", file=sys.stderr)
        return 2

    try:
        run_preflight()
        print("OK: preflight passed")
        return 0
    except PreflightFailure as err:
        print(f"FAIL: {err.dependency}", file=sys.stderr)
        return 1
    except Exception:
        print("FAIL: unknown", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
