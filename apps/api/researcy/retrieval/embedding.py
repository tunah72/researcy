from array import array
import asyncio
import json
import math
import sys
import threading
from urllib.parse import urlsplit

import httpx2

from researcy.config import get_settings
from researcy.ingestion.models import ProcessingProfile, StageFailure


_EMBED_LOCK=threading.Lock()


def _failure(code,temporary=False):
    return StageFailure(code,'temporary' if temporary else 'resource_limit' if code=='EMBEDDING_CONTEXT_LIMIT' else 'integrity',temporary)


def validate_vectors(data: bytes, count: int, dimension: int=1024) -> None:
    if type(data) is not bytes or len(data)!=count*dimension*4:
        raise _failure('EMBEDDING_OUTPUT_INVALID')
    values=array('f');values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    for index in range(count):
        vector=values[index*dimension:(index+1)*dimension]
        if any(not math.isfinite(value) for value in vector) or not math.isclose(sum(value*value for value in vector),1,rel_tol=0,abs_tol=1e-5):
            raise _failure('EMBEDDING_OUTPUT_INVALID')

class EmbeddingClient:
    def __init__(self,profile: ProcessingProfile,*,endpoint: str | None=None):
        endpoint=endpoint or get_settings().embedding_endpoint
        parsed=urlsplit(endpoint)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise ValueError('embedding endpoint must be a plain HTTP origin')
        self.profile=profile;self.endpoint=endpoint.rstrip('/');self.runtime_identity=None
        self.timeout=get_settings().worker_embedding_request_seconds

    async def _request(self,client,path,payload=None):
        async with client.stream('GET' if payload is None else 'POST',self.endpoint+path,json=payload) as response:
            if response.status_code==429 or response.status_code>=500:
                raise _failure('DEPENDENCY_UNAVAILABLE',True)
            if response.status_code!=200 and not (path=='/api/embed' and response.status_code==400):
                raise _failure('EMBEDDING_MODEL_MISMATCH')
            data=bytearray()
            async for part in response.aiter_bytes(chunk_size=65536):
                if len(data)+len(part)>2*1024*1024:
                    raise _failure('EMBEDDING_OUTPUT_INVALID')
                data.extend(part)
            try:value=json.loads(data)
            except (ValueError,UnicodeError,RecursionError):raise _failure('EMBEDDING_OUTPUT_INVALID') from None
            if type(value) is not dict:raise _failure('EMBEDDING_OUTPUT_INVALID')
            if response.status_code==400:
                context_limit=value.get('error')=='input length exceeds maximum context length'
                raise _failure('EMBEDDING_CONTEXT_LIMIT' if context_limit else 'EMBEDDING_OUTPUT_INVALID')
            return value

    def _run(self,operation):
        try:return asyncio.run(operation)
        except (httpx2.RequestError,TimeoutError,OSError):
            raise _failure('DEPENDENCY_UNAVAILABLE',True) from None

    async def _preflight(self):
        async with asyncio.timeout(self.timeout),httpx2.AsyncClient(timeout=self.timeout,trust_env=False) as client:
            version=await self._request(client,'/api/version')
            tags=await self._request(client,'/api/tags')
            candidates=tags.get('models')
            if type(candidates) is not list:raise _failure('EMBEDDING_MODEL_MISMATCH')
            matching=[model for model in candidates if type(model) is dict and model.get('name')==self.profile.model_tag]
            if len(matching)!=1 or matching[0].get('digest')!=self.profile.model_digest:
                raise _failure('EMBEDDING_MODEL_MISMATCH')
            show=await self._request(client,'/api/show',{'model':self.profile.model_tag,'verbose':False})
            details=show.get('details');info=show.get('model_info');capabilities=show.get('capabilities')
            architecture=info.get('general.architecture') if type(info) is dict else None
            if (version.get('version')!='0.18.2' or type(details) is not dict or details.get('quantization_level')!=self.profile.quantization or
                type(architecture) is not str or type(info.get(architecture+'.embedding_length')) is not int or info.get(architecture+'.embedding_length')!=self.profile.dimension or
                type(capabilities) is not list or 'embedding' not in capabilities):
                raise _failure('EMBEDDING_MODEL_MISMATCH')
            encoded=await self._embed(client,('Embedding readiness probe.',))
            validate_vectors(encoded,1)
            return {'runtime':'ollama','version':version['version'],'model_tag':self.profile.model_tag,
                'model_digest':self.profile.model_digest,'dimension':self.profile.dimension,'quantization':self.profile.quantization}

    def preflight(self) -> dict:
        with _EMBED_LOCK:
            identity=self._run(self._preflight());self.runtime_identity=identity
        return dict(identity)

    async def _embed(self,client,texts):
        response=await self._request(client,'/api/embed',{'model':self.profile.model_tag,'input':list(texts),'truncate':False})
        vectors=response.get('embeddings')
        if response.get('model')!=self.profile.model_tag or type(vectors) is not list or len(vectors)!=len(texts):
            raise _failure('EMBEDDING_OUTPUT_INVALID')
        output=array('f')
        for vector in vectors:
            if type(vector) is not list or len(vector)!=self.profile.dimension or any(type(value) not in (int,float) for value in vector):
                raise _failure('EMBEDDING_OUTPUT_INVALID')
            try:
                values=[float(value) for value in vector]
                if any(not math.isfinite(value) for value in values):raise ValueError
                norm=math.hypot(*values)
                if not math.isfinite(norm) or norm==0:raise ValueError
                converted=array('f',(value/norm for value in values))
            except (ValueError,OverflowError):raise _failure('EMBEDDING_OUTPUT_INVALID') from None
            output.extend(converted)
        if sys.byteorder!='little':output.byteswap()
        encoded=output.tobytes();validate_vectors(encoded,len(texts),self.profile.dimension)
        return encoded

    async def _embed_request(self,texts):
        async with asyncio.timeout(self.timeout),httpx2.AsyncClient(timeout=self.timeout,trust_env=False) as client:
            return await self._embed(client,texts)

    def embed(self,texts: tuple[str,...] | list[str]) -> bytes:
        if self.runtime_identity is None:raise _failure('EMBEDDING_MODEL_MISMATCH')
        if not isinstance(texts,(tuple,list)) or not 1<=len(texts)<=4 or any(type(text) is not str or not text or len(text)>self.profile.chunk_maximum for text in texts):
            raise ValueError('embedding requires one to four bounded texts')
        with _EMBED_LOCK:return self._run(self._embed_request(texts))
