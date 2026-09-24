import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url


DEFAULT_TEST_ADMIN_URL = (
    "postgresql://researcy:local-postgres-password@127.0.0.1:55432/postgres"
)
TEST_ADMIN_URL = make_url(
    os.getenv("TEST_DATABASE_ADMIN_URL", DEFAULT_TEST_ADMIN_URL)
)
if TEST_ADMIN_URL.drivername not in {"postgresql", "postgresql+psycopg"}:
    raise ValueError("TEST_DATABASE_ADMIN_URL must use PostgreSQL")
if TEST_ADMIN_URL.database not in {"postgres", "template1"}:
    raise ValueError("TEST_DATABASE_ADMIN_URL must target the postgres maintenance database")
API_ROOT = Path(__file__).resolve().parents[1]


def _database_url(database: str, drivername: str = "postgresql") -> str:
    return TEST_ADMIN_URL.set(drivername=drivername, database=database).render_as_string(
        hide_password=False
    )


def alembic_config(database: str) -> Config:
    database_url = _database_url(database, "postgresql+psycopg")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture
def pg_conn():
    database = f"researcy_test_{uuid4().hex}"
    admin_conn = psycopg.connect(
        _database_url(TEST_ADMIN_URL.database), autocommit=True
    )
    test_conn = None
    created = False
    try:
        admin_conn.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
        )
        created = True
        test_conn = psycopg.connect(_database_url(database))
        command.upgrade(alembic_config(database), "head")
        yield test_conn
    finally:
        if test_conn is not None:
            test_conn.rollback()
            test_conn.close()
        if created:
            admin_conn.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))
            )
        admin_conn.close()
