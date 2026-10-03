from uuid import uuid4

import httpx2
import pytest

from test_intake import client,private_bucket,arxiv_clock,_auth_headers,_insert_user,_make_pdf,_SAMPLE_ATOM_FEED


@pytest.mark.parametrize('summary,expected',[('  Sequence\n modeling   with attention.  ','Sequence modeling with attention.'),(None,None)])
def test_arxiv_atom_summary_is_persisted_atomically_and_replay_never_reacquires(client,pg_conn,private_bucket,tmp_path,monkeypatch,summary,expected):
    from researcy.papers import arxiv
    owner=_insert_user(pg_conn,str(uuid4()))
    headers={**_auth_headers(client,pg_conn,owner),'Idempotency-Key':'isolated-metadata-replay'}
    pdf=_make_pdf(tmp_path/'source.pdf').read_bytes()
    feed=_SAMPLE_ATOM_FEED if summary is None else _SAMPLE_ATOM_FEED.replace('</entry>',f'<summary>{summary}</summary></entry>')
    requests=[]
    original_client=httpx2.Client
    def handler(request):
        requests.append(str(request.url))
        if request.url.path=='/api/query':
            return httpx2.Response(200,text=feed)
        assert request.url.path=='/pdf/1706.03762v7'
        return httpx2.Response(200,content=pdf)
    def factory(*args,**kwargs):
        kwargs['transport']=httpx2.MockTransport(handler)
        return original_client(*args,**kwargs)
    monkeypatch.setattr(arxiv.httpx2,'Client',factory)
    first=client.post('/api/papers/arxiv',json={'arxiv_id_or_url':'1706.03762'},headers=headers)
    assert first.status_code==202
    identities={name:first.json()[name] for name in ('paper_id','document_version','job_id')}
    assert pg_conn.execute('SELECT abstract FROM papers WHERE owner_id=%s AND id=%s',(owner,identities['paper_id'])).fetchone()==(expected,)
    bucket_client,bucket=private_bucket
    objects={(obj.object_name,obj.etag) for obj in bucket_client.list_objects(bucket,recursive=True)}
    before=list(requests)
    replay=client.post('/api/papers/arxiv',json={'arxiv_id_or_url':'1706.03762'},headers=headers)
    assert replay.status_code==200
    assert {name:replay.json()[name] for name in identities}==identities
    assert requests==before and len(requests)==2
    assert {(obj.object_name,obj.etag) for obj in bucket_client.list_objects(bucket,recursive=True)}==objects
    assert pg_conn.execute('SELECT abstract FROM papers WHERE owner_id=%s AND id=%s',(owner,identities['paper_id'])).fetchone()==(expected,)
