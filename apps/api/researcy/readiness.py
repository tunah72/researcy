"""Read-only dependency access; never evidence of generation execution."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Literal
from urllib.parse import urlsplit
from xml.etree import ElementTree

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx2
from minio.credentials import Credentials
from minio.signer import sign_v4_s3
from pydantic import BaseModel, ConfigDict
from urllib3._collections import HTTPHeaderDict

from researcy.config import Settings, _validate_generation_endpoint
from researcy.db import get_async_conn
from researcy.generation.models import _reject_constant, _reject_duplicate_keys
from researcy.ingestion.models import ProcessingProfile
from researcy.ingestion.preflight import HEAD_REVISION
from researcy.retrieval.index import collection_name, _validate_collection_schema

DEADLINE_SECONDS = 15.0
BODY_LIMIT = 2 * 1024 * 1024
router = APIRouter()


class Readiness(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    status: Literal['ready', 'unavailable']
    postgres: Literal['verified', 'unavailable']
    private_bucket: Literal['verified', 'unavailable', 'unconfigured']
    qdrant: Literal['verified', 'unavailable']
    native_identity: Literal['verified', 'unavailable']
    native_model: Literal['loaded', 'cold', 'unavailable']
    generation_configuration: Literal['configured', 'unconfigured']
    generation_access: Literal['accessible', 'unavailable', 'unconfigured']
    generation_execution: Literal['unverified'] = 'unverified'
    request_id: str


async def _postgres(settings: Settings, deadline: float) -> str:
    # Async psycopg keeps cancellation inside the shared deadline; no owner-table query.
    remaining = max(1, int((deadline - time.monotonic()) * 1000))
    async with get_async_conn() as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            await conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(remaining),))
            rows = await (await conn.execute('SELECT version_num FROM alembic_version')).fetchall()
            if rows != [(HEAD_REVISION,)]:
                raise ValueError('revision mismatch')
    return 'verified'


async def _body(response: httpx2.Response) -> bytes:
    data = bytearray()
    async for part in response.aiter_bytes(chunk_size=65536):
        if len(data) + len(part) > BODY_LIMIT:
            raise ValueError('response bound')
        data.extend(part)
    return bytes(data)


async def _json(client: httpx2.AsyncClient, url: str, *, payload: dict | None = None,
    headers: dict | None = None) -> dict:
    async with client.stream('GET' if payload is None else 'POST', url, json=payload, headers=headers) as response:
        if response.status_code != 200:
            raise ValueError('dependency status')
        raw = await _body(response)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant)
    if type(value) is not dict:
        raise ValueError('dependency shape')
    return value


def _storage_headers(settings: Settings, method: str, url: str) -> dict:
    date = datetime.now(timezone.utc)
    digest = hashlib.sha256(b'').hexdigest()
    headers = HTTPHeaderDict({'Host': urlsplit(url).netloc,
        'X-Amz-Date': date.strftime('%Y%m%dT%H%M%SZ'), 'X-Amz-Content-Sha256': digest})
    signed = sign_v4_s3(method=method, url=urlsplit(url), region='us-east-1', headers=headers,
        credentials=Credentials(settings.storage_access_key, settings.storage_secret_key),
        content_sha256=digest, date=date)
    return dict(signed.items())


async def _private_bucket(settings: Settings, client: httpx2.AsyncClient) -> str:
    if not settings.storage_access_key or not settings.storage_secret_key:
        return 'unconfigured'
    scheme = 'https' if settings.storage_secure else 'http'
    url = f'{scheme}://{settings.storage_minio_endpoint}/{settings.storage_bucket}'
    async with client.stream('HEAD', url, headers=_storage_headers(settings, 'HEAD', url)) as response:
        if response.status_code != 200:
            raise ValueError('bucket inaccessible')
    # Conservative privacy check: the standard private bucket has no policy. Never list keys.
    policy_url = url + '?policy='
    async with client.stream('GET', policy_url, headers=_storage_headers(settings, 'GET', policy_url)) as response:
        raw = await _body(response)
        if response.status_code != 404:
            raise ValueError('bucket privacy not verified')
        root = ElementTree.fromstring(raw)
        if root.tag != 'Error' or root.findtext('Code') != 'NoSuchBucketPolicy':
            raise ValueError('bucket policy inaccessible')
    return 'verified'


async def _qdrant(settings: Settings, profile: ProcessingProfile, client: httpx2.AsyncClient) -> str:
    value = await _json(client, settings.qdrant_endpoint + '/collections/' + collection_name(profile))
    result = _validate_collection_schema(value, profile)
    schema = result['payload_schema']
    if any(schema.get(field, {}).get('data_type') != 'keyword' for field in
        ('owner_id', 'paper_id', 'document_version_id', 'section_type')):
        raise ValueError('payload schema mismatch')
    return 'verified'


async def _native(settings: Settings, profile: ProcessingProfile, client: httpx2.AsyncClient) -> tuple[str, str]:
    endpoint = settings.embedding_endpoint
    version = await _json(client, endpoint + '/api/version')
    tags = await _json(client, endpoint + '/api/tags')
    models = tags.get('models')
    if type(models) is not list:
        raise ValueError('native tags shape')
    matching = [model for model in models if type(model) is dict and model.get('name') == profile.model_tag]
    if len(matching) != 1 or matching[0].get('digest') != profile.model_digest:
        raise ValueError('native identity mismatch')
    # Ollama show is metadata-only. In particular it does not invoke /api/embed or load weights.
    show = await _json(client, endpoint + '/api/show', payload={'model': profile.model_tag, 'verbose': False})
    details, info, capabilities = show.get('details'), show.get('model_info'), show.get('capabilities')
    architecture = info.get('general.architecture') if type(info) is dict else None
    if (version.get('version') != '0.18.2' or type(details) is not dict
        or details.get('quantization_level') != profile.quantization or type(architecture) is not str
        or type(info.get(architecture + '.embedding_length')) is not int
        or info[architecture + '.embedding_length'] != profile.dimension
        or type(capabilities) is not list or 'embedding' not in capabilities):
        raise ValueError('native profile mismatch')
    running = (await _json(client, endpoint + '/api/ps')).get('models')
    if type(running) is not list or any(type(model) is not dict for model in running):
        raise ValueError('native loaded shape')
    loaded = [model for model in running if model.get('name') == profile.model_tag]
    if len(loaded) > 1 or any(model.get('digest') != profile.model_digest for model in loaded):
        raise ValueError('native loaded identity mismatch')
    return 'verified', 'loaded' if loaded else 'cold'


async def _catalog(settings: Settings, client: httpx2.AsyncClient) -> str:
    if not settings.generation_endpoint or not settings.generation_api_key:
        return 'unconfigured'
    endpoint = _validate_generation_endpoint(settings.generation_endpoint,
        settings.app_env == 'production', settings.generation_provider)
    value = await _json(client, endpoint + '/models',
        headers={'Authorization': 'Bearer ' + settings.generation_api_key})
    models = value.get('data')
    if (type(models) is not list or not models or len(models) > 10000
        or any(type(model) is not dict or type(model.get('id')) is not str or not model['id']
            or len(model['id']) > 512 for model in models)):
        raise ValueError('catalog shape')
    catalog_id = 'models/' + settings.generation_model if settings.generation_provider == 'gemini' else settings.generation_model
    if sum(model['id'] == catalog_id for model in models) != 1:
        raise ValueError('configured model inaccessible')
    return 'accessible'


async def collect_readiness(settings: Settings, request_id: str, *,
    transport: httpx2.AsyncBaseTransport | None = None) -> Readiness:
    deadline = time.monotonic() + DEADLINE_SECONDS
    profile = ProcessingProfile()
    states = {'postgres': 'unavailable', 'private_bucket': 'unavailable', 'qdrant': 'unavailable',
        'native_identity': 'unavailable', 'native_model': 'unavailable',
        'generation_configuration': 'configured' if settings.generation_endpoint and settings.generation_api_key else 'unconfigured',
        'generation_access': 'unavailable'}

    async def check(name, operation):
        try:
            value = await operation
            if name == 'native_identity':
                states['native_identity'], states['native_model'] = value
            else:
                states[name] = value
        except Exception:
            # No raw provider/database/storage exceptions enter output or logs.
            pass

    try:
        async with asyncio.timeout_at(deadline):
            async with httpx2.AsyncClient(timeout=DEADLINE_SECONDS, trust_env=False,
                follow_redirects=False, transport=transport) as client:
                await asyncio.gather(check('postgres', _postgres(settings, deadline)),
                    check('private_bucket', _private_bucket(settings, client)),
                    check('qdrant', _qdrant(settings, profile, client)),
                    check('native_identity', _native(settings, profile, client)),
                    check('generation_access', _catalog(settings, client)))
    except TimeoutError:
        pass
    ready = (all(states[name] == 'verified' for name in ('postgres', 'private_bucket', 'qdrant', 'native_identity'))
        and states['generation_access'] == 'accessible')
    return Readiness(status='ready' if ready else 'unavailable', request_id=request_id, **states)


@router.get('/ready', response_model=Readiness, responses={503: {'model': Readiness}})
async def ready(request: Request) -> JSONResponse:
    result = await collect_readiness(request.app.state.settings, request.state.request_id)
    return JSONResponse(result.model_dump(), status_code=200 if result.status == 'ready' else 503,
        headers={'Cache-Control': 'no-store'})
