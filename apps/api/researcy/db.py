from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

import psycopg

from .config import get_settings


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield the application's managed PostgreSQL connection."""
    with psycopg.connect(get_settings().database_url,connect_timeout=5) as conn:
        yield conn


@asynccontextmanager
async def get_async_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    """Cancellable counterpart using the same managed database policy."""
    async with await psycopg.AsyncConnection.connect(get_settings().database_url, connect_timeout=5) as conn:
        yield conn
