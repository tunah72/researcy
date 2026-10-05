import asyncio
from dataclasses import replace
from pathlib import Path
import os
import subprocess
import sys
import time
from fastapi.testclient import TestClient
import httpx2
import pytest

from researcy.main import app


def test_unconfigured_generation_is_not_dependency_ready(monkeypatch):
    monkeypatch.setenv('GENERATION_ENDPOINT', '')
    monkeypatch.setenv('GENERATION_API_KEY', '')
    with TestClient(app) as client:
        response = client.get('/ready')
    assert response.status_code == 503
    result = response.json()
    assert result['generation_execution'] == 'unverified'
    assert result['request_id']
    assert result['request_id'] == response.headers['X-Request-ID']


@pytest.fixture
def dependency_scenario(monkeypatch):
    from researcy import readiness
    from researcy import db
    from researcy.config import get_settings
    from researcy.ingestion.models import ProcessingProfile

    settings = replace(get_settings(), generation_endpoint='https://generativelanguage.googleapis.com/v1beta/openai',
        generation_api_key='never-expose-provider-key', storage_access_key='test-access', storage_secret_key='test-secret')
    profile = ProcessingProfile()
    faults = {}
    seen = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def transaction(self):
            return self

        async def execute(self, sql, parameters=None):
            assert 'owner_id' not in sql and 'papers' not in sql
            if sql.startswith('SELECT') and 'set_config' not in sql:
                assert sql == 'SELECT version_num FROM alembic_version'
            return self
        async def fetchall(self):
            return [(faults.get('revision', readiness.HEAD_REVISION),)]

    async def connect(*args, **kwargs):
        if faults.get('postgres'):
            raise OSError('private database address and credential')
        return Connection()

    monkeypatch.setattr(db.psycopg.AsyncConnection, 'connect', connect)

    def handler(request):
        seen.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith('/models'):
            assert request.headers['Authorization'] == 'Bearer never-expose-provider-key'
            fault = faults.get('catalog')
            if fault == 'denied':
                return httpx2.Response(403, text='private provider error and key')
            if fault == 'malformed':
                return httpx2.Response(200, json={'data': [{'id': 123}]})
            if fault == 'missing':
                return httpx2.Response(200, json={'data': [{'id': 'another-model'}]})
            if fault == 'duplicate':
                return httpx2.Response(200, content=b'{"data":[],"data":[{"id":"gemini-3.8-flash"}]}')
            if fault == 'oversized':
                return httpx2.Response(200, content=b'x' * (readiness.BODY_LIMIT + 1))
            if fault == 'timeout':
                raise httpx2.ReadTimeout('private provider timeout')
            model_id = 'models/' + settings.generation_model if settings.generation_provider == 'gemini' else settings.generation_model
            return httpx2.Response(200, json={'object': 'list', 'data': [{'id': model_id}]})
        if path.startswith('/collections/'):
            if faults.get('qdrant') == 'absent':
                return httpx2.Response(404)
            return httpx2.Response(200, json={'status': 'ok', 'result': {
                'config': {'params': {'vectors': {'size': 7 if faults.get('qdrant') else profile.dimension,
                    'distance': profile.distance}}},
                'payload_schema': {name: {'data_type': 'keyword'} for name in
                    ('owner_id', 'paper_id', 'document_version_id', 'section_type')}}})
        if path == '/api/version':
            return httpx2.Response(200, json={'version': '0.18.2'})
        if path == '/api/tags':
            return httpx2.Response(200, json={'models': [{'name': profile.model_tag,
                'digest': 'wrong' if faults.get('identity') else profile.model_digest}]})
        if path == '/api/show':
            return httpx2.Response(200, json={'details': {'quantization_level': profile.quantization},
                'model_info': {'general.architecture': 'bert', 'bert.embedding_length': profile.dimension},
                'capabilities': ['embedding']})
        if path == '/api/ps':
            models = [] if faults.get('cold') else [{'name': profile.model_tag, 'digest': profile.model_digest}]
            return httpx2.Response(200, json={'models': models})
        if request.method == 'HEAD':
            return httpx2.Response(403 if faults.get('storage') == 'denied' else 200)
        if request.url.query == b'policy=':
            if faults.get('storage') == 'public':
                return httpx2.Response(200, content=b'{}')
            return httpx2.Response(404, content=b'<Error><Code>NoSuchBucketPolicy</Code></Error>')
        raise AssertionError(f'Unexpected readiness operation: {request.method} {path}')

    async def run():
        return await readiness.collect_readiness(settings, 'safe-request-id', transport=httpx2.MockTransport(handler))

    def http():
        from fastapi import FastAPI
        from researcy.main import RequestIdMiddleware
        test_app = FastAPI()
        test_app.state.settings = settings
        test_app.add_middleware(RequestIdMiddleware)
        test_app.include_router(readiness.router)
        original = httpx2.AsyncClient

        def client(**kwargs):
            kwargs['transport'] = httpx2.MockTransport(handler)
            return original(**kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(readiness.httpx2, 'AsyncClient', client)
            with TestClient(test_app) as client:
                return client.get('/ready')

    run.http = http

    return faults, seen, run


def test_catalog_access_is_not_generation_execution(dependency_scenario):
    faults, seen, run = dependency_scenario
    result = asyncio.run(run())
    assert result.status == 'ready'
    assert result.generation_access == 'accessible'
    assert result.generation_execution == 'unverified'
    assert result.native_model == 'loaded'
    assert all(method == 'GET' or method == 'HEAD' or (method, path) == ('POST', '/api/show')
        for method, path in seen)
    assert not any(path in ('/api/embed', '/chat/completions') for _, path in seen)


@pytest.mark.parametrize(('key', 'fault', 'state'), [
    ('postgres', True, 'postgres'), ('revision', '0007_m4_discovery', 'postgres'),
    ('storage', 'denied', 'private_bucket'), ('storage', 'public', 'private_bucket'),
    ('qdrant', 'absent', 'qdrant'), ('qdrant', 'wrong', 'qdrant'),
    ('identity', True, 'native_identity'),
    ('catalog', 'denied', 'generation_access'), ('catalog', 'malformed', 'generation_access'),
    ('catalog', 'missing', 'generation_access'), ('catalog', 'duplicate', 'generation_access'),
    ('catalog', 'oversized', 'generation_access'), ('catalog', 'timeout', 'generation_access'),
])
def test_dependency_failure_is_safe_not_green(dependency_scenario, key, fault, state):
    faults, _, run = dependency_scenario
    faults[key] = fault
    response = run.http()
    assert response.status_code == 503
    result = response.json()
    assert result['status'] == 'unavailable'
    assert result[state] == 'unavailable'
    assert result['generation_execution'] == 'unverified'
    assert result['request_id'] == response.headers['X-Request-ID']
    serialized = response.text
    assert 'private' not in serialized.replace('private_bucket', '')
    assert 'never-expose' not in serialized


def test_cold_identity_does_not_load_model(dependency_scenario):
    faults, seen, run = dependency_scenario
    faults['cold'] = True
    result = asyncio.run(run())
    assert result.native_identity == 'verified'
    assert result.native_model == 'cold'
    assert result.status == 'ready'
    assert ('POST', '/api/embed') not in seen


def test_all_dependency_checks_share_deadline(monkeypatch, dependency_scenario):
    from researcy import readiness

    async def blocked(*args, **kwargs):
        await asyncio.sleep(1)
        return 'verified'

    monkeypatch.setattr(readiness, 'DEADLINE_SECONDS', 0.03)
    monkeypatch.setattr(readiness, '_postgres', blocked)
    started = time.monotonic()
    result = asyncio.run(dependency_scenario[2]())
    assert time.monotonic() - started < 0.5
    assert result.status == 'unavailable'
    assert result.postgres == 'unavailable'
    assert result.generation_execution == 'unverified'


@pytest.fixture
def demo_script():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / 'scripts/demo-up.sh'
        if candidate.is_file():
            return candidate
    pytest.skip('Startup rejection tests require the complete worktree on the host, not the API-only image.')


@pytest.mark.parametrize('project', ['researcy', 'researcy-main', 'main', 'other-project', 'researcy-m5-../main'])
def test_startup_rejects_owner_or_invalid_namespace(tmp_path, project, demo_script):
    script = demo_script
    response = subprocess.run(['bash', str(script), '--project', project,
        '--env-file', str(tmp_path / 'm5-test.env'), '--override', str(tmp_path / 'm5-test.private.yaml')],
        capture_output=True, text=True)
    assert response.returncode != 0
    assert 'isolated project' in response.stderr


def test_startup_rejects_main_override_before_docker(tmp_path, demo_script):
    script = demo_script
    response = subprocess.run(['bash', str(script), '--project', 'researcy-m5-test',
        '--env-file', str(tmp_path / 'm5-test.env'), '--override', str(tmp_path / 'compose.main.private.yaml')],
        capture_output=True, text=True)
    assert response.returncode != 0
    assert 'private override' in response.stderr


@pytest.mark.parametrize('defect', ['shared_name', 'external', 'driver_opts', 'dependency_alias', 'missing_cap'])
def test_startup_rejects_unsafe_override_before_mutation(tmp_path, defect, demo_script):
    import json
    script = demo_script
    env_file = tmp_path / 'm5-test.env'
    override = tmp_path / 'm5-test.private.yaml'
    env_file.write_text('GENERATION_API_KEY=private-key-never-print\n'
        'APP_ORIGINS=http://localhost:33019\nGOOGLE_REDIRECT_URI=http://localhost:33019/auth/google/callback\n'
        'GOOGLE_CLIENT_ID=controlled-client\nGOOGLE_CLIENT_SECRET=controlled-secret\n'
        'SESSION_LOOKUP_KEY=controlled-session-key-at-least-32-bytes\n'
        'POSTGRES_PORT=55499\nMINIO_API_PORT=19009\nMINIO_CONSOLE_PORT=19010\nAPI_PORT=18019\n')
    override.write_text('services:\n  web:\n    ports: !override\n      - \"127.0.0.1:33019:3000\"\n')
    env_file.chmod(0o600)
    override.chmod(0o600)
    rendered = subprocess.run(['docker', 'compose', '--project-name', 'researcy-m5-test',
        '--project-directory', str(script.parent.parent), '--env-file', str(env_file),
        '-f', str(script.parent.parent / 'compose.yaml'), '-f', str(override),
        '--profile', 'web', '--profile', 'processing', 'config', '--format', 'json'],
        env={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']}, capture_output=True, text=True)
    assert rendered.returncode == 0, 'Controlled isolation fixture must render successfully'
    config = json.loads(rendered.stdout)
    fake = tmp_path / 'docker'
    marker = tmp_path / 'mutated'
    config_file = tmp_path / 'rendered.json'
    config_file.write_text(json.dumps(config))
    fake.write_text(f'#!{sys.executable}\nimport sys, pathlib\n'
        f'if \"config\" in sys.argv: print(pathlib.Path({str(config_file)!r}).read_text())\n'
        f'else: pathlib.Path({str(marker)!r}).write_text(\"mutation\"); sys.exit(99)\n')
    fake.chmod(0o700)
    command = ['bash', str(script), '--project', 'researcy-m5-test',
        '--env-file', str(env_file), '--override', str(override)]
    environment = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']}
    baseline = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert marker.exists(), 'Valid baseline must reach the first isolated build before the controlled fault'
    marker.unlink()
    if defect == 'dependency_alias':
        config['services']['minio-init']['extra_hosts'] = ['minio=host-gateway']
    elif defect == 'missing_cap':
        del config['services']['api']['mem_limit']
    else:
        config['volumes']['postgres-data'] = {
            'shared_name': {'name': 'researcy_postgres-data'},
            'external': {'name': 'researcy-m5-test_postgres-data', 'external': True},
            'driver_opts': {'name': 'researcy-m5-test_postgres-data', 'driver_opts': {'device': '/owner/data'}},
        }[defect]
    config_file.write_text(json.dumps(config))
    response = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert response.returncode != 0
    assert not marker.exists()
    assert 'private-key-never-print' not in response.stdout + response.stderr
