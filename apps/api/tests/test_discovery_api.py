from uuid import uuid4

import pytest

from test_conversations import reader_source, reader_client
from test_library import BASE_URL, SESSION_LOOKUP_KEY, _authenticate, _insert_paper


@pytest.fixture
def related_source(reader_source, reader_client):
    from researcy.auth.sessions import _csrf_verifier
    conn,scope=reader_source['conn'],reader_source['scope']
    csrf='isolated-discovery-csrf'
    conn.execute('UPDATE sessions SET csrf_verifier=%s WHERE owner_id=%s',(_csrf_verifier(csrf,SESSION_LOOKUP_KEY.encode()),scope.owner_id))
    conn.execute('UPDATE papers SET title=%s,abstract=%s WHERE owner_id=%s AND id=%s',('Attention mechanisms','Sequence modeling with attention.',scope.owner_id,scope.paper_id))
    conn.commit()
    reader_client.cookies.set('researcy_csrf',csrf)
    return reader_source,reader_client,{'Origin':BASE_URL,'X-CSRF-Token':csrf}


def _path(source):
    return f"/api/papers/{source['scope'].paper_id}/related:search"


def _runs(source):
    return source['conn'].execute('SELECT count(*) FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()[0]


@pytest.mark.parametrize('headers',[{}, {'Origin':'https://hostile.example'}, {'Origin':BASE_URL,'X-CSRF-Token':'wrong'}])
def test_csrf_precedes_body_and_provider(related_source,headers):
    source,client,_=related_source
    response=client.post(_path(source),content=b'{invalid',headers=headers)
    assert response.status_code==403
    assert _runs(source)==0


@pytest.mark.parametrize('query,body',[('?owner_id=forged',b''),('?query=attention',b''),('',b'{}'),('',b'{'),('',b'x'*1025)])
def test_client_cannot_supply_discovery_context(related_source,query,body):
    source,client,headers=related_source
    response=client.post(_path(source)+query,content=body,headers=headers)
    assert response.status_code==422
    assert response.json()['code']=='INVALID_REQUEST'
    assert _runs(source)==0


def test_missing_title_precedes_ready_and_quota(related_source):
    source,client,headers=related_source
    conn,scope=source['conn'],source['scope']
    conn.execute('UPDATE papers SET title=NULL WHERE owner_id=%s AND id=%s',(scope.owner_id,scope.paper_id))
    conn.commit()
    response=client.post(_path(source),headers=headers)
    assert response.status_code==409
    assert response.json()['code']=='DISCOVERY_METADATA_MISSING'
    assert response.headers.get('cache-control')=='no-store'
    assert _runs(source)==0

@pytest.mark.parametrize('query,body,content_length', [
    ('?query=unexpected', b'', None),
    ('', b'{"extra": 1}', None),
    ('', b'', '1025'),
    ('', b'', '-1'),
    ('', b'', 'not-an-int'),
])
def test_malformed_query_or_body_precedes_missing_title_and_unready(related_source, query, body, content_length):
    source, client, headers = related_source
    conn, scope = source['conn'], source['scope']
    # Paper with missing title
    conn.execute('UPDATE papers SET title=NULL WHERE owner_id=%s AND id=%s', (scope.owner_id, scope.paper_id))
    conn.commit()
    req_headers = dict(headers)
    if content_length is not None:
        req_headers['Content-Length'] = content_length
    response = client.post(_path(source) + query, content=body, headers=req_headers)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert _runs(source) == 0

    # A separately accepted queued paper; active versions and sealed jobs are immutable.
    pending_paper,_,_=_insert_paper(conn,scope.owner_id,title='Attention mechanisms',
        authors=[],year=None,source_version=None,screening_warning=None)
    conn.commit()
    response = client.post(f'/api/papers/{pending_paper}/related:search' + query, content=body, headers=req_headers)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert _runs(source) == 0


def test_oversized_declared_content_length_rejected(related_source):
    source, client, headers = related_source
    req_headers = {**headers, 'Content-Length': '2048'}
    response = client.post(_path(source), headers=req_headers)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert _runs(source) == 0


def test_invalid_content_length_header_rejected(related_source):
    source, client, headers = related_source
    req_headers = {**headers, 'Content-Length': 'invalid'}
    response = client.post(_path(source), headers=req_headers)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert _runs(source) == 0


def test_unauthenticated_request_rejected_before_body_or_ownership(related_source):
    source, client, _ = related_source
    client.cookies.clear()
    response = client.post(_path(source), content=b'malformed body')
    assert response.status_code == 401
    assert _runs(source) == 0

def test_foreign_and_absent_sources_are_indistinguishable(related_source):
    from researcy.auth.sessions import _csrf_verifier
    source,client,headers=related_source
    conn=source['conn']
    stranger=conn.execute('INSERT INTO users(issuer,sub) VALUES(%s,%s) RETURNING id',('https://accounts.google.com',str(uuid4()))).fetchone()[0]
    conn.commit()
    _authenticate(client,conn,stranger)
    csrf=headers['X-CSRF-Token']
    conn.execute('UPDATE sessions SET csrf_verifier=%s WHERE owner_id=%s',(_csrf_verifier(csrf,SESSION_LOOKUP_KEY.encode()),stranger));conn.commit()
    client.cookies.set('researcy_csrf',csrf)
    observed=[client.post(path,content=b'{invalid',headers=headers) for path in (_path(source),f'/api/papers/{uuid4()}/related:search')]
    assert [response.status_code for response in observed]==[404,404]
    assert [response.json()['code'] for response in observed]==['RESOURCE_NOT_FOUND','RESOURCE_NOT_FOUND']
    assert observed[0].json()['message']==observed[1].json()['message']
    assert _runs(source)==0


def test_unconfigured_provider_consumes_no_discovery_quota(related_source,monkeypatch):
    source,client,headers=related_source
    monkeypatch.setenv('GENERATION_ENDPOINT','')
    monkeypatch.setenv('GENERATION_API_KEY','')
    response=client.post(_path(source),headers=headers)
    assert response.status_code==503
    assert response.json()['code']=='GENERATION_UNCONFIGURED'
    assert _runs(source)==0
