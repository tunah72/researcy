from uuid import uuid4

import psycopg
import pytest
from alembic import command

from conftest import alembic_config


M1_TABLES = {
    "users",
    "sessions",
    "oauth_transactions",
    "papers",
    "document_versions",
    "ingestion_jobs",
    "import_idempotency",
    "import_rate_limits",
    "alembic_version",
}


def schema_snapshot(conn):
    tables = tuple(
        conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ).fetchall()
    )
    columns = tuple(
        conn.execute(
            """
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                   a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
              FROM pg_attribute a
              JOIN pg_class c ON c.oid = a.attrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
              LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
               AND a.attnum > 0 AND NOT a.attisdropped
             ORDER BY c.relname, a.attnum
            """
        ).fetchall()
    )
    constraints = tuple(
        conn.execute(
            """
            SELECT c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid),
                   con.condeferrable, con.condeferred
              FROM pg_constraint con
              JOIN pg_class c ON c.oid = con.conrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public'
             ORDER BY c.relname, con.conname
            """
        ).fetchall()
    )
    indexes = tuple(
        conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY indexname"
        ).fetchall()
    )
    return tables, columns, constraints, indexes


def expect_constraint(conn, error_type, statement, params):
    with pytest.raises(error_type):
        with conn.transaction():
            conn.execute(statement, params)


def insert_user(conn, sub, email):
    return conn.execute(
        "INSERT INTO users (issuer, sub, email) VALUES (%s, %s, %s) RETURNING id",
        ("https://accounts.google.com", sub, email),
    ).fetchone()[0]


def insert_paper(conn, owner_id, canonical_arxiv_id):
    return conn.execute(
        """
        INSERT INTO papers (owner_id, source, canonical_arxiv_id)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (owner_id, "arxiv" if canonical_arxiv_id else "upload", canonical_arxiv_id),
    ).fetchone()[0]


def insert_version(conn, owner_id, paper_id):
    version_id = uuid4()
    conn.execute(
        """
        INSERT INTO document_versions
          (id, owner_id, paper_id, sha256, byte_count, object_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (version_id, owner_id, paper_id, bytes(range(32)), 1, f"test/{version_id}"),
    )
    return version_id


def insert_job(conn, owner_id, version_id, stage="queued"):
    return conn.execute(
        """
        INSERT INTO ingestion_jobs (owner_id, document_version_id, stage)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (owner_id, version_id, stage),
    ).fetchone()[0]


def test_m1_migration_is_rerunnable_and_enforces_owner_constraints(pg_conn):
    existing = {
        row[0]
        for row in pg_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    }
    missing = M1_TABLES - existing
    assert not missing, f"M1 migration is missing tables: {sorted(missing)}"

    before = schema_snapshot(pg_conn)
    command.upgrade(alembic_config(), "head")
    after = schema_snapshot(pg_conn)
    assert after == before, "re-running the M1 migration changed the schema"

    email = "same@example.test"
    subject_a, subject_b = f"subject-a-{uuid4()}", f"subject-b-{uuid4()}"
    owner_a = insert_user(pg_conn, subject_a, email)
    owner_b = insert_user(pg_conn, subject_b, email)
    expect_constraint(
        pg_conn,
        psycopg.errors.UniqueViolation,
        "INSERT INTO users (issuer, sub, email) VALUES (%s, %s, %s)",
        ("https://accounts.google.com", subject_a, email),
    )
    # The same email with distinct provider subjects is intentionally allowed.
    assert owner_a != owner_b

    paper_a = insert_paper(pg_conn, owner_a, "1706.03762")
    paper_b = insert_paper(pg_conn, owner_b, "1706.03762")
    expect_constraint(
        pg_conn,
        psycopg.errors.UniqueViolation,
        "INSERT INTO papers (owner_id, source, canonical_arxiv_id) VALUES (%s, 'arxiv', %s)",
        (owner_a, "1706.03762"),
    )

    version_a = insert_version(pg_conn, owner_a, paper_a)
    version_b = insert_version(pg_conn, owner_b, paper_b)
    expect_constraint(
        pg_conn,
        psycopg.errors.ForeignKeyViolation,
        "INSERT INTO ingestion_jobs (owner_id, document_version_id, stage) VALUES (%s, %s, 'queued')",
        (owner_b, version_a),
    )
    job_a = insert_job(pg_conn, owner_a, version_a)
    expect_constraint(
        pg_conn,
        psycopg.errors.UniqueViolation,
        "INSERT INTO ingestion_jobs (owner_id, document_version_id, stage) VALUES (%s, %s, 'queued')",
        (owner_a, version_a),
    )
    job_b = insert_job(pg_conn, owner_b, version_b)
    expect_constraint(
        pg_conn,
        psycopg.errors.CheckViolation,
        "INSERT INTO ingestion_jobs (owner_id, document_version_id, stage) VALUES (%s, %s, 'processing')",
        (owner_b, version_b),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with pg_conn.transaction():
            pg_conn.execute(
                "UPDATE papers SET active_version_id = %s WHERE id = %s",
                (version_a, paper_b),
            )
            pg_conn.execute("SET CONSTRAINTS papers_active_version_fk IMMEDIATE")

    key = f"same-key-{uuid4()}"
    idempotency = """
        INSERT INTO import_idempotency
          (owner_id, idempotency_key, operation, request_digest, paper_id,
           document_version_id, job_id)
        VALUES (%s, %s, 'upload', %s, %s, %s, %s)
    """
    digest = bytes(range(32))
    pg_conn.execute(idempotency, (owner_a, key, digest, paper_a, version_a, job_a))
    expect_constraint(
        pg_conn,
        psycopg.errors.UniqueViolation,
        idempotency,
        (owner_a, key, digest, paper_a, version_a, job_a),
    )
    # Idempotency keys are scoped to an owner, not globally reserved.
    pg_conn.execute(idempotency, (owner_b, key, digest, paper_b, version_b, job_b))
