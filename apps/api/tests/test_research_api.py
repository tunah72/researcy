from fastapi.testclient import TestClient

from researcy.main import app


def test_research_requires_session_before_reading_invalid_body():
    with TestClient(app) as client:
        response = client.post(
            '/api/papers/00000000-0000-0000-0000-000000000001/research-directions:stream',
            content=b'{invalid',
        )
    assert response.status_code == 401
    assert response.json()['code'] == 'UNAUTHENTICATED'


import json
from uuid import uuid4
import pytest
from test_library import BASE_URL,SESSION_LOOKUP_KEY,_authenticate
from test_reader_stream import _setup_csrf,_parse_sse
from conftest import _database_url


@pytest.fixture
def research_client(research_sources,monkeypatch):
    f=research_sources
    monkeypatch.setenv('APP_ENV','test')
    monkeypatch.setenv('APP_ORIGINS',BASE_URL)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('SESSION_LOOKUP_KEY',SESSION_LOOKUP_KEY)
    monkeypatch.setenv('DATABASE_URL',_database_url(f['conn'].info.dbname))
    monkeypatch.setenv('GENERATION_ENDPOINT','')
    monkeypatch.setenv('GENERATION_API_KEY','')
    with TestClient(app,base_url=BASE_URL) as client:
        _authenticate(client,f['conn'],f['owner_id'])
        _setup_csrf(f['conn'],client,f['owner_id'])
        yield client


def headers(client):
    return {'Origin':BASE_URL,'X-CSRF-Token':client.cookies.get('researcy_csrf')}


def path(f,active=None):
    return f"/api/papers/{active or f['paper_ids'][0]}/research-directions:stream"


@pytest.mark.parametrize('mode',['csrf','origin','foreign'])
def test_auth_source_precedence_before_malformed_body(research_sources,research_client,mode):
    f=research_sources;h=headers(research_client);target=path(f)
    if mode=='csrf':h['X-CSRF-Token']='wrong'
    elif mode=='origin':h['Origin']='https://hostile.example'
    else:target=path(f,f['foreign_id'])
    response=research_client.post(target,content=b'{bad',headers=h)
    assert response.status_code==(404 if mode=='foreign' else 403)
    if mode=='foreign':assert response.json()['code']=='RESOURCE_NOT_FOUND'
    assert f['conn'].execute('SELECT count(*) FROM research_runs').fetchone()==(0,)


@pytest.mark.parametrize('body,query',[
    ({'related_paper_ids':[]},''),({'related_paper_ids':['x']},''),
    ({'related_paper_ids':[1]},''),({'related_paper_ids':[str(uuid4())]*2},''),
    ({'related_paper_ids':[str(uuid4())]*4},''),({'owner_id':'x','related_paper_ids':[str(uuid4())]},''),
    ({'related_paper_ids':[str(uuid4())]},'?model=x'),
])
def test_malformed_selection_never_reserves_or_dispatches(research_sources,research_client,body,query):
    f=research_sources
    response=research_client.post(path(f)+query,json=body,headers=headers(research_client))
    assert response.status_code==422 and response.json()['code']=='INVALID_REQUEST'
    assert f['conn'].execute('SELECT count(*) FROM research_runs').fetchone()==(0,)


def test_active_duplicate_key_and_body_byte_cap_are_invalid(research_sources,research_client):
    f=research_sources;active=str(f['paper_ids'][0])
    for body in (json.dumps({'related_paper_ids':[active]}).encode(),
        b'{"related_paper_ids":[],"related_paper_ids":[]}',b' '*2049):
        response=research_client.post(path(f),content=body,headers=headers(research_client))
        assert response.status_code==422 and response.json()['code']=='INVALID_REQUEST'
    assert f['conn'].execute('SELECT count(*) FROM research_runs').fetchone()==(0,)


def test_whole_selection_owner_checks_before_readiness_or_configuration(research_sources,research_client):
    f=research_sources
    for missing in (f['foreign_id'],uuid4()):
        response=research_client.post(path(f),json={'related_paper_ids':[str(missing),str(f['queued_id'])]},
            headers=headers(research_client))
        assert response.status_code==404 and response.json()['code']=='RESOURCE_NOT_FOUND'
    response=research_client.post(path(f),json={'related_paper_ids':[str(f['queued_id'])]},headers=headers(research_client))
    assert response.status_code==409 and response.json()['code']=='RESEARCH_SELECTION_NOT_READY'
    response=research_client.post(path(f),json={'related_paper_ids':[str(f['paper_ids'][1])]},headers=headers(research_client))
    assert response.status_code==503 and response.json()['code']=='GENERATION_UNCONFIGURED'
    assert 'x-research-run-id' not in response.headers
    assert f['conn'].execute('SELECT count(*) FROM research_runs').fetchone()==(0,)


def test_owned_snapshot_and_completed_research_citation_are_private(research_sources,research_client):
    from test_research_repository import reserve
    from researcy.research.repository import finish_research
    f=research_sources;run=reserve(f)
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][1])
    finish_research(f['conn'],run,ideas,citations,{})
    snapshot_path=f"/api/papers/{run.active_paper_id}/research-directions/{run.run_id}"
    snapshot=research_client.get(snapshot_path)
    assert snapshot.status_code==200 and snapshot.json()['state']=='completed'
    assert snapshot.json()['sources'][1]['paper_id']==str(f['paper_ids'][1])
    citation=research_client.get(f'/api/citations/{citations[0].citation.citation_id}')
    assert citation.status_code==200
    assert citation.json()['citation']['evidence_quote']=='Source 1 evaluates exact experimental evidence and limitations.'
    assert citation.json()['citation']['paper_id']==str(f['paper_ids'][1])
    _authenticate(research_client,f['conn'],f['publications'][-1]['scope'].owner_id)
    for target in (snapshot_path,f'/api/citations/{citations[0].citation.citation_id}',f'/api/citations/{uuid4()}'):
        response=research_client.get(target)
        assert response.status_code==404 and response.json()['code']=='RESOURCE_NOT_FOUND'
