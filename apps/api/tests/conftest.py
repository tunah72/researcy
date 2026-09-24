import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config


DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql://researcy:local-postgres-password@127.0.0.1:55432/researcy",
    ),
)
API_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["database_url"] = DATABASE_URL
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return config


@pytest.fixture
def pg_conn():
    conn = psycopg.connect(DATABASE_URL)
    try:
        if (API_ROOT / "alembic.ini").is_file():
            command.upgrade(alembic_config(), "head")
        yield conn
    finally:
        conn.rollback()
        conn.close()
