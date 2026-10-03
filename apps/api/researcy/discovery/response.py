import asyncio
from threading import Event
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.types import Receive,Scope,Send

from researcy.agents.discovery import run_discovery
from researcy.config import Settings
from researcy.errors import APIError
from .models import ActiveMetadata,DiscoveryReservation
from .repository import reserve_discovery,finish_discovery
from .runtime import database


class DiscoveryJSONResponse(Response):
    def __init__(self,request: Request,source: ActiveMetadata,settings: Settings,*,started: float,deadline: float) -> None:
        super().__init__(media_type='application/json',headers={'Cache-Control':'no-store'})
        self.request=request
        self.source=source
        self.settings=settings
        self.started=started
        self.deadline=deadline
        self.cancel=Event()
        self.reservation: DiscoveryReservation | None=None
        self.graph_started=False

    async def __call__(self,scope: Scope,receive: Receive,send: Send) -> None:
        def reserve(conn):
            # Bind inside the joined worker even if its awaiting task is cancelled.
            self.reservation=reserve_discovery(conn,self.source,str(self.request.state.request_id))
            return self.reservation
        async def produce():
            reservation=await database(reserve,deadline=self.deadline,cancel=self.cancel)
            if self.cancel.is_set():
                raise asyncio.CancelledError()
            if time.monotonic()>=self.deadline:
                raise APIError(504,'DISCOVERY_TIMEOUT','The related-paper search exceeded its time limit.')
            self.graph_started=True
            return await run_discovery(reservation,self.settings,started=self.started,deadline=self.deadline,cancel=self.cancel)
        async def disconnect():
            while True:
                if (await receive())['type']=='http.disconnect':
                    self.cancel.set()
                    return
        listener=asyncio.create_task(disconnect())
        producer=asyncio.create_task(produce())
        interrupted=False
        timed_out=False
        response=None
        try:
            done,_=await asyncio.wait({listener,producer},timeout=max(0,self.deadline-time.monotonic()),return_when=asyncio.FIRST_COMPLETED)
            if listener in done:
                interrupted=True
                self.cancel.set()
                producer.cancel()
            elif producer in done:
                try:
                    value=await producer
                    response=JSONResponse(value.model_dump(mode='json'),headers={'Cache-Control':'no-store'})
                except APIError as error:
                    response=await self.request.app.exception_handlers[APIError](self.request,error)
            else:
                timed_out=True
                producer.cancel()
                error=APIError(504,'DISCOVERY_TIMEOUT','The related-paper search exceeded its time limit.')
                response=await self.request.app.exception_handlers[APIError](self.request,error)
        except asyncio.CancelledError:
            interrupted=True
            self.cancel.set()
            producer.cancel()
            raise
        finally:
            listener.cancel()
            if not producer.done():
                producer.cancel()
            await asyncio.gather(listener,producer,return_exceptions=True)
            if self.reservation is not None and not self.graph_started:
                state='interrupted' if interrupted else 'failed'
                code='DISCOVERY_INTERRUPTED' if interrupted else 'DISCOVERY_TIMEOUT' if timed_out else 'INTERNAL_ERROR'
                await database(finish_discovery,self.reservation,state=state,metrics={'latency_ms':round((time.monotonic()-self.started)*1000)},error_code=code,deadline=self.deadline+15)
        if response is not None and not interrupted:
            response.headers['Cache-Control']='no-store'
            await response(scope,receive,send)
