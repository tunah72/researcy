import asyncio
from threading import Event
import time

from researcy.db import get_conn
from researcy.papers.pdf import bounded_database


async def database(operation,*args,deadline: float,cancel: Event | None=None,**kwargs):
    def execute():
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError()
        with get_conn() as conn:
            with bounded_database(conn,min(deadline,time.monotonic()+5)):
                if cancel is not None and cancel.is_set():
                    raise asyncio.CancelledError()
                return operation(conn,*args,**kwargs)
    task=asyncio.create_task(asyncio.to_thread(execute))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Join the bounded operation before cleanup; a late reservation cannot be abandoned.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise
