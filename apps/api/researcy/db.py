from contextlib import contextmanager
from typing import Iterator

import psycopg

from .config import get_settings


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield the application's managed PostgreSQL connection."""
    with psycopg.connect(get_settings().database_url) as conn:
        yield conn
