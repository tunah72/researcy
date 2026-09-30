import asyncio
from collections.abc import Coroutine
from threading import Event
from typing import Any,TypeVar

from .models import LostLease


T=TypeVar('T')


async def cancellable(operation: Coroutine[Any,Any,T],cancel: Event | None) -> T:
    if cancel is None:
        return await operation
    task=asyncio.create_task(operation)
    try:
        while not task.done():
            if cancel.is_set():
                raise LostLease()
            await asyncio.wait((task,),timeout=.05)
        if cancel.is_set():
            raise LostLease()
        return await task
    finally:
        if cancel.is_set() or not task.done():
            if not task.done():
                task.cancel()
            await asyncio.gather(task,return_exceptions=True)
