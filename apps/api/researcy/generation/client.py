import asyncio
import codecs
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, aclosing
from io import StringIO
import json
import re
import time
from typing import Any

from pydantic import TypeAdapter

import httpx2

from researcy.config import GENERATION_MODELS, Settings, _validate_generation_endpoint
from .models import (
    GenerationEvent, GenerationFailure, InvalidModelOutput, decode_output,
    _reject_constant, _reject_duplicate_keys,
)


_LINE_END = re.compile(r'\r\n|\r|\n')
_COUNT_FIELDS = ('prompt_tokens','completion_tokens','total_tokens','cached_tokens','cache_creation_input_tokens')
_DETAIL_FIELDS = {
    'prompt_tokens_details': ('cached_tokens','audio_tokens'),
    'completion_tokens_details': ('reasoning_tokens','audio_tokens','accepted_prediction_tokens','rejected_prediction_tokens'),
}


def _usage(value: Any,provider: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise GenerationFailure('INVALID_RESPONSE')
    result: dict[str, Any] = {}
    for name in _COUNT_FIELDS:
        if name in value:
            count = value[name]
            if type(count) is not int or count<0:
                raise GenerationFailure('INVALID_RESPONSE')
            result[name] = count
    for name,fields in _DETAIL_FIELDS.items():
        if name not in value:
            continue
        details = value[name]
        if type(details) is not dict:
            raise GenerationFailure('INVALID_RESPONSE')
        selected = {}
        for field in fields:
            if field in details:
                count = details[field]
                if type(count) is not int or count<0:
                    raise GenerationFailure('INVALID_RESPONSE')
                selected[field] = count
        if selected:
            result[name] = selected
    if all(name in result for name in ('prompt_tokens','completion_tokens','total_tokens')):
        visible_total = result['prompt_tokens']+result['completion_tokens']
        # Google total includes thoughts even when compatibility usage omits their count.
        if (result['total_tokens']<visible_total
            or provider=='9router' and result['total_tokens']!=visible_total):
            raise GenerationFailure('INVALID_RESPONSE')
    for detail_name,total_name in (('prompt_tokens_details','prompt_tokens'),('completion_tokens_details','completion_tokens')):
        if total_name in result and any(count>result[total_name]
            for field,count in result.get(detail_name,{}).items() if field!='reasoning_tokens'):
            raise GenerationFailure('INVALID_RESPONSE')
    # Only the qualified gateway maps reasoning into prompt tokens.
    reasoning = result.get('completion_tokens_details',{}).get('reasoning_tokens')
    if provider=='9router' and reasoning is not None and 'prompt_tokens' in result and reasoning>result['prompt_tokens']:
        raise GenerationFailure('INVALID_RESPONSE')
    if 'cached_tokens' in result:
        if 'prompt_tokens' in result and result['cached_tokens']>result['prompt_tokens']:
            raise GenerationFailure('INVALID_RESPONSE')
        nested = result.get('prompt_tokens_details',{}).get('cached_tokens')
        if nested is not None and nested!=result['cached_tokens']:
            raise GenerationFailure('INVALID_RESPONSE')
    return result or None


def _check_deadline(deadline: float) -> None:
    if time.monotonic()>=deadline:
        raise GenerationFailure('GENERATION_TIMEOUT')


async def _bounded_chunks(response: httpx2.Response,limit: int,deadline: float) -> AsyncIterator[memoryview]:
    total = 0
    iterator = response.aiter_bytes().__aiter__()
    while True:
        # A timeout must never remain attached to the consumer task across a yield.
        async with asyncio.timeout_at(deadline):
            try:
                chunk = await anext(iterator)
            except StopAsyncIteration:
                return
        total += len(chunk)
        if total>limit:
            raise GenerationFailure('PAYLOAD_TOO_LARGE')
        view = memoryview(chunk)
        for start in range(0,len(view),16384):
            _check_deadline(deadline)
            yield view[start:start+16384]


async def _sse_lines(chunks: AsyncIterator[memoryview]) -> AsyncIterator[str]:
    decoder = codecs.getincrementaldecoder('utf-8-sig')('strict')
    buffer = StringIO()
    skip_lf = False
    async for chunk in chunks:
        text = decoder.decode(chunk,final=False)
        if not text:
            continue
        cursor = 1 if skip_lf and text.startswith('\n') else 0
        skip_lf = False
        for match in _LINE_END.finditer(text,cursor):
            buffer.write(text[cursor:match.start()])
            line = buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            cursor = match.end()
            skip_lf = match.group()=='\r' and cursor==len(text)
            yield line
        if cursor<len(text):
            buffer.write(text[cursor:])
    decoder.decode(b'',final=True)
    if buffer.tell():
        raise GenerationFailure('INVALID_RESPONSE')


class GenerationClient:
    def __init__(self,settings: Settings,*,transport: httpx2.AsyncBaseTransport | None=None) -> None:
        self.settings = settings
        self._transport = transport

    async def stream(self,messages: list[dict[str,str]],*,output: TypeAdapter,schema_name: str,
        deadline: float | None=None,
        on_metadata: Callable[[GenerationEvent | None], None] | None=None) -> AsyncIterator[GenerationEvent]:
        pass_deadline = time.monotonic()+self.settings.generation_pass_seconds
        if deadline is not None:
            pass_deadline = min(pass_deadline,deadline)
        queue: asyncio.Queue = asyncio.Queue(maxsize=16)
        finished = object()
        timed_out = False
        terminal_metadata: GenerationEvent | None = None
        metadata_delivered = False
        def checkpoint_terminal(event: GenerationEvent | None) -> None:
            nonlocal terminal_metadata
            terminal_metadata = event
            if on_metadata is not None:
                on_metadata(event)
        async def produce():
            nonlocal timed_out,terminal_metadata
            try:
                async with asyncio.timeout_at(pass_deadline):
                    async with aclosing(self._stream_events(messages,output=output,schema_name=schema_name,deadline=pass_deadline,
                        checkpoint_terminal=checkpoint_terminal)) as source:
                        async for event in source:
                            if event.kind=='content':
                                encoded = event.text.encode('utf-8')
                                decoder = codecs.getincrementaldecoder('utf-8')()
                                # Reserve space for up to three UTF-8 carry bytes from the prior slice.
                                for offset in range(0,len(encoded),16380):
                                    text = decoder.decode(encoded[offset:offset+16380],final=offset+16380>=len(encoded))
                                    if text:
                                        await queue.put(GenerationEvent(kind='content',text=text))
                            elif event.kind=='metadata':
                                if timed_out:
                                    raise GenerationFailure('GENERATION_TIMEOUT')
                                if terminal_metadata is None:
                                    continue
                                terminal_metadata = event
                                await queue.put(event)
                            else:
                                if timed_out or time.monotonic()>=pass_deadline:
                                    timed_out = True
                                    raise GenerationFailure('GENERATION_TIMEOUT')
                                await queue.put(event)
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                timed_out = True
                await queue.put(GenerationFailure('GENERATION_TIMEOUT'))
            except (GenerationFailure,InvalidModelOutput) as error:
                timed_out = isinstance(error,GenerationFailure) and error.code=='GENERATION_TIMEOUT'
                await queue.put(error)
            finally:
                if not asyncio.current_task().cancelling():
                    await queue.put(finished)
        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is finished:
                    await task
                    if timed_out:
                        raise GenerationFailure('GENERATION_TIMEOUT')
                    return
                if isinstance(item,Exception):
                    if terminal_metadata is not None and not metadata_delivered:
                        metadata_delivered = True
                        yield terminal_metadata
                    raise item from None
                if item.kind=='content':
                    if timed_out or time.monotonic()>=pass_deadline:
                        continue
                    yield item
                elif item.kind=='completed':
                    if timed_out or time.monotonic()>=pass_deadline:
                        raise GenerationFailure('GENERATION_TIMEOUT')
                    yield item
                elif item.kind=='metadata':
                    if terminal_metadata is None:
                        continue
                    metadata_delivered = True
                    yield item
                    if timed_out or time.monotonic()>=pass_deadline:
                        raise GenerationFailure('GENERATION_TIMEOUT')
                else:
                    yield item
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _stream_events(self,messages: list[dict[str,str]],*,output: TypeAdapter,schema_name: str,
        deadline: float | None=None,
        checkpoint_terminal: Callable[[GenerationEvent | None], None] | None=None) -> AsyncIterator[GenerationEvent]:
        def notify_terminal(event: GenerationEvent | None) -> None:
            if checkpoint_terminal is not None:
                checkpoint_terminal(event)
        if not self.settings.generation_endpoint or not self.settings.generation_api_key:
            raise GenerationFailure('GENERATION_UNCONFIGURED')
        try:
            endpoint = _validate_generation_endpoint(self.settings.generation_endpoint,
                self.settings.app_env=='production',self.settings.generation_provider)
        except ValueError:
            raise GenerationFailure('INVALID_ENDPOINT') from None
        if self.settings.generation_provider not in GENERATION_MODELS:
            raise GenerationFailure('INVALID_PROVIDER')
        if self.settings.generation_model!=GENERATION_MODELS[self.settings.generation_provider]:
            raise GenerationFailure('INVALID_MODEL')
        if not messages:
            raise GenerationFailure('INVALID_REQUEST')
        pass_deadline = time.monotonic()+self.settings.generation_pass_seconds
        if deadline is not None:
            pass_deadline = min(pass_deadline,deadline)
        _check_deadline(pass_deadline)
        timeout = httpx2.Timeout(self.settings.generation_pass_seconds,
            connect=self.settings.generation_connect_seconds)
        payload = {'model':self.settings.generation_model,'messages':messages,'stream':True,
            'max_tokens':self.settings.generation_max_output_tokens}
        if self.settings.generation_provider=='gemini':
            payload.update(
                reasoning_effort='low',
                stream_options={'include_usage':True},
                response_format={'type':'json_schema','json_schema':{
                    'name':schema_name,'strict':True,'schema':output.json_schema()}},
            )
        headers = {'Authorization':'Bearer '+self.settings.generation_api_key,'Accept':'text/event-stream'}
        content_parts: list[str] = []
        content_bytes = 0
        pending: list[str] = []
        usage: dict[str,Any] | None = None
        echoed_model: str | None = None
        stopped = False
        stopped_at: float | None = None
        marked_done = False
        truncated: str | None = None
        try:
            async with httpx2.AsyncClient(timeout=timeout,transport=self._transport,trust_env=False) as client:
                async with AsyncExitStack() as stack:
                    async with asyncio.timeout_at(pass_deadline):
                        response = await stack.enter_async_context(client.stream('POST',endpoint+'/chat/completions',
                            headers=headers,json=payload))
                    if response.status_code==429:
                        raise GenerationFailure('GENERATION_RATE_LIMITED')
                    if 500<=response.status_code<600:
                        raise GenerationFailure('GENERATION_UNAVAILABLE')
                    if response.status_code!=200:
                        raise GenerationFailure('GENERATION_FAILED')
                    media_type = response.headers.get('content-type','').split(';',1)[0].strip().lower()
                    if media_type!='text/event-stream':
                        raise GenerationFailure('INVALID_RESPONSE')
                    lines = _sse_lines(_bounded_chunks(response,self.settings.generation_max_output_bytes,pass_deadline))
                    async with aclosing(lines):
                        async for line in lines:
                            _check_deadline(pass_deadline)
                            if line:
                                if line.startswith('data:'):
                                    value = line[5:]
                                    pending.append(value[1:] if value.startswith(' ') else value)
                                continue
                            if not pending:
                                continue
                            data = '\n'.join(pending)
                            pending.clear()
                            if data.strip()=='[DONE]':
                                if not stopped:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                marked_done = True
                                break
                            try:
                                frame = json.loads(data,object_pairs_hook=_reject_duplicate_keys,parse_constant=_reject_constant)
                            except (ValueError,RecursionError):
                                notify_terminal(None)
                                raise GenerationFailure('INVALID_RESPONSE') from None
                            if type(frame) is not dict or 'error' in frame:
                                notify_terminal(None)
                                raise GenerationFailure('INVALID_RESPONSE')
                            if 'model' in frame:
                                if type(frame['model']) is not str:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                if '\x00' in frame['model']:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                try:
                                    frame['model'].encode('utf-8')
                                except UnicodeError:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE') from None
                                if echoed_model is not None and frame['model']!=echoed_model:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                echoed_model = frame['model']
                            if 'usage' in frame:
                                try:
                                    reported = _usage(frame['usage'],self.settings.generation_provider)
                                except GenerationFailure:
                                    notify_terminal(None)
                                    raise
                                if reported is not None and reported.get('completion_tokens',0)>self.settings.generation_max_output_tokens:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                if usage is not None and reported is not None and reported!=usage:
                                    # Gemini emits cumulative usage before its terminal frame.
                                    cumulative = self.settings.generation_provider=='gemini' and not stopped
                                    if cumulative:
                                        for name in _COUNT_FIELDS:
                                            if name in usage and (name not in reported or reported[name]<usage[name]):
                                                cumulative = False
                                                break
                                        for name in _DETAIL_FIELDS:
                                            if any(field not in reported.get(name,{}) or reported[name][field]<count
                                                for field,count in usage.get(name,{}).items()):
                                                cumulative = False
                                                break
                                    if not cumulative:
                                        notify_terminal(None)
                                        raise GenerationFailure('INVALID_RESPONSE')
                                if reported is not None:
                                    usage = reported
                            choices = frame.get('choices')
                            if choices==[] or choices is None and 'usage' in frame:
                                if stopped and stopped_at is not None and stopped_at<=pass_deadline:
                                    notify_terminal(GenerationEvent(kind='metadata',usage=usage,echoed_model=echoed_model,finish_reason=truncated or 'stop'))
                                continue
                            if type(choices) is not list or len(choices)!=1 or stopped:
                                notify_terminal(None)
                                raise GenerationFailure('INVALID_RESPONSE')
                            choice = choices[0]
                            if type(choice) is not dict:
                                notify_terminal(None)
                                raise GenerationFailure('INVALID_RESPONSE')
                            finish = choice.get('finish_reason')
                            if finish in ('length','max_tokens'):
                                truncated = finish
                                stopped = True
                                stopped_at = time.monotonic()
                            elif finish is not None:
                                if finish!='stop':
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                stopped = True
                                stopped_at = time.monotonic()
                            if stopped and stopped_at is not None and stopped_at<=pass_deadline:
                                notify_terminal(GenerationEvent(kind='metadata',usage=usage,echoed_model=echoed_model,finish_reason=truncated or 'stop'))
                            delta = choice.get('delta',{})
                            if type(delta) is not dict or any(name in delta for name in ('tool_calls','tool_call','function_call')):
                                notify_terminal(None)
                                raise GenerationFailure('INVALID_RESPONSE')
                            content = delta.get('content')
                            if content is not None:
                                if type(content) is not str:
                                    notify_terminal(None)
                                    raise GenerationFailure('INVALID_RESPONSE')
                                content_bytes += len(content.encode('utf-8'))
                                if content_bytes>self.settings.generation_max_output_bytes:
                                    raise GenerationFailure('PAYLOAD_TOO_LARGE')
                                if content:
                                    content_parts.append(content)
                                    yield GenerationEvent(kind='content',text=content)
                    if not marked_done and pending:
                        notify_terminal(None)
                        raise GenerationFailure('INVALID_RESPONSE')
        except (TimeoutError,httpx2.TimeoutException):
            raise GenerationFailure('GENERATION_TIMEOUT') from None
        except (httpx2.TransportError,OSError):
            raise GenerationFailure('GENERATION_UNAVAILABLE') from None
        except httpx2.DecodingError:
            raise GenerationFailure('INVALID_RESPONSE') from None
        except UnicodeError:
            raise GenerationFailure('INVALID_RESPONSE') from None
        _check_deadline(pass_deadline)
        if not stopped:
            notify_terminal(None)
            raise GenerationFailure('INVALID_RESPONSE')
        if truncated is not None:
            yield GenerationEvent(kind='metadata',usage=usage,echoed_model=echoed_model,finish_reason=truncated)
            raise GenerationFailure('PAYLOAD_TOO_LARGE')
        yield GenerationEvent(kind='metadata',usage=usage,echoed_model=echoed_model,finish_reason='stop')
        _check_deadline(pass_deadline)
        decoded = decode_output(''.join(content_parts).encode('utf-8'),output)
        _check_deadline(pass_deadline)
        yield GenerationEvent(kind='completed',output=decoded)
