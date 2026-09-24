import importlib
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from conftest import _database_url
from researcy.auth.sessions import SESSION_COOKIE, session_lookup
from researcy.errors import APIError
from researcy.main import api_error_handler, app


BASE_URL = "http://localhost:3000"
ISSUER = "https://accounts.google.com"
SESSION_LOOKUP_KEY = "library-test-session-lookup-key-at-least-32-bytes"


@pytest.fixture
def client(monkeypatch, pg_conn):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ORIGINS", BASE_URL)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_LOOKUP_KEY", SESSION_LOOKUP_KEY)
    monkeypatch.setenv("DATABASE_URL", _database_url(pg_conn.info.dbname))

    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


def _insert_user(conn, sub):
    return conn.execute(
        "INSERT INTO users (issuer, sub) VALUES (%s, %s) RETURNING id",
        (ISSUER, sub),
    ).fetchone()[0]


def _insert_paper(
    conn,
    owner_id,
    *,
    title,
    authors,
    year,
    source_version,
    screening_warning,
):
    paper_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()
    canonical_arxiv_id = f"1706.{uuid4().int % 100000:05d}"
    conn.execute(
        """
        INSERT INTO papers (
            id, owner_id, source, canonical_arxiv_id, title, authors, year,
            active_version_id
        ) VALUES (%s, %s, 'arxiv', %s, %s, %s, %s, %s)
        """,
        (paper_id, owner_id, canonical_arxiv_id, title, authors, year, version_id),
    )
    conn.execute(
        """
        INSERT INTO document_versions (
            id, owner_id, paper_id, sha256, byte_count, object_key,
            source_version, screening_warning
        ) VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
        """,
        (
            version_id,
            owner_id,
            paper_id,
            bytes(32),
            f"test/{owner_id}/{version_id}",
            source_version,
            screening_warning,
        ),
    )
    conn.execute(
        """
        INSERT INTO ingestion_jobs (id, owner_id, document_version_id, stage)
        VALUES (%s, %s, %s, 'queued')
        """,
        (job_id, owner_id, version_id),
    )
    return paper_id, version_id, job_id


def _authenticate(client, conn, owner_id):
    raw_token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO sessions (
            token_hash, owner_id, csrf_verifier, idle_expires_at, absolute_expires_at
        ) VALUES (
            %s, %s, %s,
            CURRENT_TIMESTAMP + INTERVAL '30 minutes',
            CURRENT_TIMESTAMP + INTERVAL '12 hours'
        )
        """,
        (session_lookup(raw_token, SESSION_LOOKUP_KEY.encode()), owner_id, bytes(32)),
    )
    conn.commit()
    client.cookies.set(SESSION_COOKIE, raw_token)


def _quota_repository():
    try:
        return importlib.import_module("researcy.papers.repository")
    except ModuleNotFoundError as error:
        pytest.fail(f"Task 3 quota repository is unavailable: {error.name}")


def test_library_list_is_owner_scoped_and_ignores_client_owner(client, pg_conn):
    owner_a = _insert_user(pg_conn, "list-owner-a")
    owner_b = _insert_user(pg_conn, "list-owner-b")
    _insert_paper(
        pg_conn,
        owner_a,
        title="A private paper",
        authors=["A Author"],
        year=2024,
        source_version="v1",
        screening_warning=None,
    )
    paper_b, version_b, _ = _insert_paper(
        pg_conn,
        owner_b,
        title="B private paper",
        authors=["B Author"],
        year=2025,
        source_version="v2",
        screening_warning=None,
    )
    pg_conn.commit()
    _authenticate(client, pg_conn, owner_b)

    response = client.get("/api/papers", params={"owner_id": str(owner_a)})

    assert response.status_code == 200
    payload = response.json()
    assert {paper["paper_id"] for paper in payload["papers"]} == {str(paper_b)}
    paper = payload["papers"][0]
    assert paper["title"] == "B private paper"
    assert paper["authors"] == ["B Author"]
    assert paper["year"] == 2025
    assert paper["stage"] == "queued"
    assert paper["active_version_id"] == str(version_b)
    assert paper["source_version"] == "v2"
    assert paper["screening_warning"] is None
    assert payload["request_id"]


def test_library_search_matches_owned_title_and_author_only(client, pg_conn):
    owner_a = _insert_user(pg_conn, "search-owner-a")
    owner_b = _insert_user(pg_conn, "search-owner-b")
    _insert_paper(
        pg_conn,
        owner_a,
        title="Foreign Quantum Index",
        authors=["Foreign Researcher"],
        year=2023,
        source_version="v1",
        screening_warning=None,
    )
    paper_b, _, _ = _insert_paper(
        pg_conn,
        owner_b,
        title="Owned Quantum Index",
        authors=["Owned Researcher"],
        year=2024,
        source_version="v2",
        screening_warning=None,
    )
    pg_conn.commit()
    _authenticate(client, pg_conn, owner_b)

    title_match = client.get("/api/papers", params={"search": "quantum"})
    author_match = client.get("/api/papers", params={"search": "owned researcher"})
    foreign_title = client.get("/api/papers", params={"search": "foreign quantum"})
    foreign_author = client.get("/api/papers", params={"search": "foreign researcher"})
    oversized_search = client.get("/api/papers", params={"search": "x" * 201})

    assert all(
        response.status_code == 200
        for response in (title_match, author_match, foreign_title, foreign_author)
    )
    assert {paper["paper_id"] for paper in title_match.json()["papers"]} == {str(paper_b)}
    assert {paper["paper_id"] for paper in author_match.json()["papers"]} == {str(paper_b)}
    assert foreign_title.json()["papers"] == []
    assert foreign_author.json()["papers"] == []
    assert oversized_search.status_code == 422
    assert oversized_search.json()["code"] == "INVALID_REQUEST"


def test_foreign_and_missing_paper_details_are_indistinguishable(client, pg_conn):
    owner_a = _insert_user(pg_conn, "detail-owner-a")
    owner_b = _insert_user(pg_conn, "detail-owner-b")
    paper_a, _, _ = _insert_paper(
        pg_conn,
        owner_a,
        title="Private detail",
        authors=["Private Author"],
        year=2024,
        source_version="v1",
        screening_warning=None,
    )
    pg_conn.commit()
    _authenticate(client, pg_conn, owner_b)

    foreign = client.get(f"/api/papers/{paper_a}")
    missing = client.get(f"/api/papers/{uuid4()}")
    _authenticate(client, pg_conn, owner_a)
    owned = client.get(f"/api/papers/{paper_a}")

    assert owned.status_code == 200

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["code"] == missing.json()["code"] == "NOT_FOUND"
    assert foreign.json()["message"] == missing.json()["message"]
    assert foreign.json().keys() == missing.json().keys()


def test_library_detail_preserves_unknown_metadata_and_persisted_version_state(
    client, pg_conn
):
    owner = _insert_user(pg_conn, "detail-owner-null-metadata")
    paper_id, version_id, _ = _insert_paper(
        pg_conn,
        owner,
        title=None,
        authors=None,
        year=None,
        source_version="v7",
        screening_warning="LOW_TEXT",
    )
    pg_conn.commit()
    _authenticate(client, pg_conn, owner)

    response = client.get(f"/api/papers/{paper_id}")
    listing = client.get("/api/papers")

    assert response.status_code == 200
    detail = response.json()
    assert detail["paper_id"] == str(paper_id)
    assert detail["title"] is None
    assert detail["authors"] is None
    assert detail["year"] is None
    assert detail["stage"] == "queued"
    assert detail["source"] == "arxiv"
    assert detail["active_version_id"] == str(version_id)
    assert detail["source_version"] == "v7"
    assert detail["screening_warning"] == "LOW_TEXT"
    listed = listing.json()["papers"][0]
    assert listed["title"] is None
    assert listed["authors"] is None
    assert listed["year"] is None
    assert detail["request_id"]
    assert "object_key" not in detail


def test_library_requires_an_authenticated_session(client):
    response = client.get("/api/papers")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_import_quota_persists_across_new_process_and_is_per_user(pg_conn):
    repository = _quota_repository()
    owner = _insert_user(pg_conn, "quota-persisted-owner")
    other_owner = _insert_user(pg_conn, "quota-independent-owner")
    pg_conn.commit()
    database_url = _database_url(pg_conn.info.dbname)

    with psycopg.connect(database_url) as conn:
        for _ in range(repository.IMPORT_QUOTA_LIMIT):
            repository.take_import_slot(conn, owner)
    with psycopg.connect(database_url) as conn:
        repository.take_import_slot(conn, other_owner)

    code = """
import os
import sys
from uuid import UUID
import psycopg
from researcy.papers.repository import ImportQuotaExceeded, take_import_slot
try:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        take_import_slot(conn, UUID(sys.argv[1]))
except ImportQuotaExceeded:
    print("LIMITED")
else:
    print("ACCEPTED")
"""
    process = subprocess.run(
        [sys.executable, "-c", code, str(owner)],
        cwd=Path(__file__).resolve().parents[1],
        env={"DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert process.returncode == 0
    assert process.stdout.strip() == "LIMITED"
    assert pg_conn.execute(
        "SELECT request_count FROM import_rate_limits WHERE owner_id = %s",
        (owner,),
    ).fetchone()[0] == repository.IMPORT_QUOTA_LIMIT
    assert pg_conn.execute(
        "SELECT request_count FROM import_rate_limits WHERE owner_id = %s",
        (other_owner,),
    ).fetchone()[0] == 1


def test_import_quota_error_returns_safe_429_with_retry_after():
    repository = _quota_repository()
    test_app = FastAPI()
    test_app.add_exception_handler(APIError, api_error_handler)

    @test_app.get("/quota")
    def quota(request: Request):
        request.state.request_id = "task3-test-request"
        raise repository.ImportQuotaExceeded(17)

    with TestClient(test_app) as test_client:
        response = test_client.get("/quota")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert response.json() == {
        "code": "IMPORT_RATE_LIMITED",
        "message": "The import limit was reached. Try again after the indicated interval.",
        "request_id": "task3-test-request",
    }


def test_import_quota_is_atomic_under_concurrent_requests(monkeypatch, pg_conn):
    repository = _quota_repository()
    monkeypatch.setattr(repository, "IMPORT_QUOTA_LIMIT", 3)
    owner = _insert_user(pg_conn, "quota-concurrent-owner")
    pg_conn.commit()
    database_url = _database_url(pg_conn.info.dbname)
    request_count = 12
    barrier = Barrier(request_count)

    def reserve_slot(_):
        barrier.wait(timeout=10)
        try:
            with psycopg.connect(database_url) as conn:
                repository.take_import_slot(conn, owner)
        except repository.ImportQuotaExceeded as error:
            return "limited", error.retry_after
        return "accepted", None

    with ThreadPoolExecutor(max_workers=request_count) as executor:
        results = list(executor.map(reserve_slot, range(request_count)))

    accepted = [result for result in results if result[0] == "accepted"]
    limited = [result for result in results if result[0] == "limited"]
    assert len(accepted) == 3
    assert len(limited) == request_count - 3
    assert all(retry_after > 0 for _, retry_after in limited)
    count = pg_conn.execute(
        "SELECT request_count FROM import_rate_limits WHERE owner_id = %s",
        (owner,),
    ).fetchone()[0]
    assert count == 3
