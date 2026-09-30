from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from researcy.auth.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    issue_session,
)
from researcy.ingestion.jobs import short_transaction
from researcy.main import app
from test_intake import BASE_URL, SESSION_LOOKUP_KEY, client, private_bucket
from test_jobs import snapshot


def terminal_state(conn, job, *, retryable=True, run_after_seconds=None):
    with short_transaction(conn):
        if run_after_seconds is not None:
            conn.execute(
                """UPDATE ingestion_jobs
                SET stage='failed', status='failed', failed_stage='validating',
                    error_code='DEPENDENCY_UNAVAILABLE', failure_kind='temporary',
                    retryable=%s, completed_at=clock_timestamp(),
                    run_after=clock_timestamp() + make_interval(secs => %s)
                WHERE id=%s""",
                (retryable, run_after_seconds, job),
            )
        else:
            conn.execute(
                """UPDATE ingestion_jobs
                SET stage='failed', status='failed', failed_stage='validating',
                    error_code='DEPENDENCY_UNAVAILABLE', failure_kind='temporary',
                    retryable=%s, completed_at=clock_timestamp(),
                    run_after=clock_timestamp() - interval '1 second'
                WHERE id=%s""",
                (retryable, job),
            )


def _make_auth_client(owner_id, conn):
    session_token, csrf_token = issue_session(conn, owner_id, SESSION_LOOKUP_KEY.encode())
    conn.commit()
    c = TestClient(app, base_url=BASE_URL)
    c.cookies.set(SESSION_COOKIE, session_token)
    c.cookies.set(CSRF_COOKIE, csrf_token)
    headers = {
        "Origin": BASE_URL,
        "x-csrf-token": csrf_token,
    }
    return c, headers, session_token


def test_concurrent_valid_retries_yield_one_accepted_and_one_replay(client, queued_job, pg_conn):
    scope, job = queued_job
    terminal_state(pg_conn, job, retryable=True)

    # Pre-create two distinct authenticated clients sequentially on the main thread before starting the pool
    c1, h1, _ = _make_auth_client(scope.owner_id, pg_conn)
    c2, h2, _ = _make_auth_client(scope.owner_id, pg_conn)

    try:
        def do_retry(cli, headers):
            return cli.post(
                f"/api/jobs/{job}/retry",
                headers=headers,
                json={"retry_revision": 0},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(do_retry, c1, h1)
            f2 = executor.submit(do_retry, c2, h2)
            r1, r2 = f1.result(), f2.result()
    finally:
        c1.close()
        c2.close()

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 202]

    accepted_resp = r1 if r1.status_code == 202 else r2
    replay_resp = r2 if r1.status_code == 202 else r1

    assert accepted_resp.json()["retry_revision"] == 1
    assert accepted_resp.json()["status"] == "pending"
    assert replay_resp.json()["retry_revision"] == 1

    # Exactly one rate limit entry recorded for this owner
    quota_count = pg_conn.execute(
        "SELECT coalesce(sum(request_count),0) FROM processing_retry_rate_limits WHERE owner_id=%s",
        (scope.owner_id,),
    ).fetchone()[0]
    assert quota_count == 1
    pg_conn.commit()


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_revoked_session_cookie_returns_401_before_body_or_job_lookup(client, queued_job, pg_conn, method):
    scope, job = queued_job
    terminal_state(pg_conn, job)

    client_instance, headers, session_token = _make_auth_client(scope.owner_id, pg_conn)
    with client_instance:
        # Revoke the session in database
        with short_transaction(pg_conn):
            pg_conn.execute("UPDATE sessions SET revoked = TRUE WHERE owner_id = %s", (scope.owner_id,))

        if method == "GET":
            resp = client_instance.get(f"/api/jobs/{job}")
        else:
            # POST with malformed / oversized body to ensure 401 happens before reading body
            resp = client_instance.post(
                f"/api/jobs/{job}/retry",
                headers=headers,
                content=b"oversized-or-malformed-" * 300,
            )

        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHENTICATED"

        # Quota table unpolluted
        assert pg_conn.execute("SELECT count(*) FROM processing_retry_rate_limits").fetchone()[0] == 0
        pg_conn.commit()


def test_cooldown_and_quota_return_429_retry_after_with_safe_diagnostic_preparation(client, queued_job, pg_conn):
    scope, job = queued_job
    terminal_state(pg_conn, job, retryable=True, run_after_seconds=30)

    client_instance, headers, _ = _make_auth_client(scope.owner_id, pg_conn)
    with client_instance:
        resp = client_instance.post(
            f"/api/jobs/{job}/retry",
            headers=headers,
            json={"retry_revision": 0},
        )
        assert resp.status_code == 429
        assert resp.json()["code"] == "PROCESSING_RETRY_LIMITED"
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert 1 <= retry_after <= 30

        # Now test GET during cooldown: returns safe preparation, no internal secrets/keys/locked_by
        get_resp = client_instance.get(f"/api/jobs/{job}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert set(data) == {
            "job_id",
            "paper_id",
            "document_version",
            "stage",
            "status",
            "failed_stage",
            "error_code",
            "retry_revision",
            "preparation",
            "request_id",
        }
        prep = data["preparation"]
        assert set(prep) == {"state", "reason", "retryable", "retry_after_seconds"}
        assert prep["state"] == "failed"
        assert prep["retryable"] is True
        assert prep["reason"] == "temporary"
        assert 1 <= prep["retry_after_seconds"] <= 30
        for forbidden in ("locked_by", "object_key", "profile_hash", "token_hash", "lease_generation"):
            assert forbidden not in data
            assert forbidden not in prep

        # Exhaust owner quota to test quota-based 429
        terminal_state(pg_conn, job, retryable=True, run_after_seconds=None)
        with short_transaction(pg_conn):
            pg_conn.execute(
                """INSERT INTO processing_retry_rate_limits (owner_id, window_start, request_count)
                VALUES (%s, clock_timestamp(), 5)""",
                (scope.owner_id,),
            )

        quota_resp = client_instance.post(
            f"/api/jobs/{job}/retry",
            headers=headers,
            json={"retry_revision": 0},
        )
        assert quota_resp.status_code == 429
        assert quota_resp.json()["code"] == "PROCESSING_RETRY_LIMITED"
        assert int(quota_resp.headers["Retry-After"]) >= 1
        pg_conn.commit()


def test_future_revision_conflict_vs_non_retryable_discrimination(client, queued_job, pg_conn):
    scope, job = queued_job

    # 1. Non-retryable terminal job: revision matches current (0), but job is non-retryable
    terminal_state(pg_conn, job, retryable=False)
    client_instance, headers, _ = _make_auth_client(scope.owner_id, pg_conn)
    with client_instance:
        res_non_retryable = client_instance.post(
            f"/api/jobs/{job}/retry",
            headers=headers,
            json={"retry_revision": 0},
        )
        assert res_non_retryable.status_code == 409
        assert res_non_retryable.json()["code"] == "JOB_NOT_RETRYABLE"

        # 2. Future revision on retryable job: revision > row.retry_revision
        terminal_state(pg_conn, job, retryable=True)
        res_future = client_instance.post(
            f"/api/jobs/{job}/retry",
            headers=headers,
            json={"retry_revision": 5},
        )
        assert res_future.status_code == 409
        assert res_future.json()["code"] == "RETRY_REVISION_CONFLICT"

        # State remained untouched
        assert snapshot(pg_conn, job)[:2] == ("failed", "failed")
        # Quota unpolluted
        assert pg_conn.execute(
            "SELECT coalesce(sum(request_count),0) FROM processing_retry_rate_limits WHERE owner_id=%s",
            (scope.owner_id,),
        ).fetchone()[0] == 0
        pg_conn.commit()


def test_oversized_body_returns_413_request_too_large_without_quota_consumption(client, queued_job, pg_conn):
    scope, job = queued_job
    terminal_state(pg_conn, job, retryable=True)

    client_instance, headers, _ = _make_auth_client(scope.owner_id, pg_conn)
    with client_instance:
        # > 4096 bytes
        large_payload = b'{"retry_revision": 0, "pad": "' + b"x" * 5000 + b'"}'
        resp = client_instance.post(
            f"/api/jobs/{job}/retry",
            headers=headers,
            content=large_payload,
        )
        assert resp.status_code == 413
        assert resp.json()["code"] == "REQUEST_TOO_LARGE"

        # Job state is not modified, quota is not consumed
        assert snapshot(pg_conn, job)[:2] == ("failed", "failed")
        quota_count = pg_conn.execute(
            "SELECT count(*) FROM processing_retry_rate_limits WHERE owner_id=%s",
            (scope.owner_id,),
        ).fetchone()[0]
        assert quota_count == 0
        pg_conn.commit()


def test_malformed_json_with_valid_csrf_returns_422_without_quota_consumption(client, queued_job, pg_conn):
    scope, job = queued_job
    terminal_state(pg_conn, job, retryable=True)

    client_instance, headers, _ = _make_auth_client(scope.owner_id, pg_conn)
    with client_instance:
        # Valid CSRF + Origin, but body is malformed JSON (< 4KiB)
        resp = client_instance.post(
            f"/api/jobs/{job}/retry",
            headers=headers,
            content=b"{not a json}",
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "INVALID_REQUEST"

        # Job not restarted, no quota charged
        assert snapshot(pg_conn, job)[:2] == ("failed", "failed")
        quota_count = pg_conn.execute(
            "SELECT count(*) FROM processing_retry_rate_limits WHERE owner_id=%s",
            (scope.owner_id,),
        ).fetchone()[0]
        assert quota_count == 0
        pg_conn.commit()
