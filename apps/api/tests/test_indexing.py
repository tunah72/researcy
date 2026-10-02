from uuid import uuid4

import pytest

from researcy.ingestion.models import ProcessingProfile, DocumentScope, IntegrityFailure
from researcy.retrieval.index import point_id,collection_name,validate_point_set


def point(scope,chunk_id,vector):
    profile=ProcessingProfile()
    return {'id':str(point_id(profile.index_version,chunk_id)),
        'payload':{'chunk_id':str(chunk_id),'owner_id':str(scope.owner_id),'paper_id':str(scope.paper_id),
            'document_version_id':str(scope.document_version_id),'section_type':'body'},'vector':vector}


@pytest.mark.parametrize('corruption',['equal-count-wrong-id','foreign-owner','wrong-vector','missing','extra'])
def test_equal_counts_are_not_proof_of_exact_owned_selected_points(corruption):
    scope=DocumentScope(uuid4(),uuid4(),uuid4());chunk=uuid4();vector=[1.0]+[0.0]*1023
    expected=[point(scope,chunk,vector)];observed=[point(scope,chunk,vector.copy())]
    if corruption=='equal-count-wrong-id':observed[0]['id']=str(uuid4())
    elif corruption=='foreign-owner':observed[0]['payload']['owner_id']=str(uuid4())
    elif corruption=='wrong-vector':observed[0]['vector']=[0.0,1.0]+[0.0]*1022
    elif corruption=='missing':observed=[]
    else:observed.append(point(scope,uuid4(),vector))
    with pytest.raises(IntegrityFailure):validate_point_set(expected,observed)



def test_real_selected_index_replay_publishes_exactly_once(selected_index):
    import time
    from researcy.retrieval.index import index_selected,verify_index,publish_ready
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;lease=fixture['lease'];conn=fixture['conn']
    index_selected(lease,time.monotonic()+60)
    first=fixture['client'].request('POST','/collections/'+fixture['collection']+'/points/scroll',
        {'limit':10,'with_payload':True,'with_vector':True})['result']['points']
    index_selected(lease,time.monotonic()+60)
    replay=fixture['client'].request('POST','/collections/'+fixture['collection']+'/points/scroll',
        {'limit':10,'with_payload':True,'with_vector':True})['result']['points']
    receipt=verify_index(lease,time.monotonic()+60)
    assert first==replay
    assert {item['id'] for item in replay}=={str(point_id(fixture['profile'].index_version,chunk.id)) for chunk in fixture['chunks']}
    with short_transaction(conn):
        assert conn.execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',(lease.scope.owner_id,)).fetchall()==[]
    publish_ready(conn,lease,receipt)
    with short_transaction(conn):
        assert conn.execute('SELECT stage,status FROM ingestion_jobs WHERE id=%s AND owner_id=%s',(lease.job_id,lease.scope.owner_id)).fetchone()==('ready','succeeded')
        published=conn.execute('SELECT point_count,embedding_manifest_hash FROM index_publications WHERE owner_id=%s AND document_version_id=%s',(lease.scope.owner_id,lease.scope.document_version_id)).fetchone()
    assert published==(len(fixture['chunks']),fixture['manifest'].content_hash)


@pytest.mark.parametrize('corruption',['equal-count-wrong-id','wrong-vector','missing','extra','foreign-owner'])
def test_real_corrupt_point_set_cannot_publish(selected_index,corruption):
    import time
    from researcy.retrieval.index import index_selected,verify_index,publish_ready
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;lease=fixture['lease'];client=fixture['client']
    index_selected(lease,time.monotonic()+60)
    observed=client.request('POST','/collections/'+fixture['collection']+'/points/scroll',
        {'limit':10,'with_payload':True,'with_vector':True})['result']['points'][0]
    original={key:observed[key] for key in ('id','payload','vector')}
    if corruption in ('missing','equal-count-wrong-id'):
        client.request('POST','/collections/'+fixture['collection']+'/points/delete?wait=true',{'points':[original['id']]})
    if corruption in ('equal-count-wrong-id','extra'):original['id']=str(uuid4())
    elif corruption=='wrong-vector':original['vector']=[0.0,1.0]+[0.0]*1022
    elif corruption=='foreign-owner':original['payload']['owner_id']=str(uuid4())
    if corruption!='missing':
        client.request('PUT','/collections/'+fixture['collection']+'/points?wait=true',{'points':[original]})
    with pytest.raises(IntegrityFailure):verify_index(lease,time.monotonic()+60)
    with short_transaction(fixture['conn']):
        assert fixture['conn'].execute('SELECT stage,status FROM ingestion_jobs WHERE id=%s',(lease.job_id,)).fetchone()==('indexing','running')
        assert fixture['conn'].execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',(lease.scope.owner_id,)).fetchall()==[]


@pytest.mark.parametrize('selected_index',[{
    'chunk_target':30,'chunk_maximum':60,'chunk_overlap':0,
    'source_texts':(
        'Attention weights compare query and key vectors.',
        'Residual connections retain a direct signal path.',
        'Position encodings represent token order explicitly.',
        'Decoder masking excludes future sequence tokens.',
        'Feedforward layers transform each position separately.',
        'Encoder outputs provide context to decoder attention.',
    ),
}],indirect=True)
def test_corrupt_provenance_outside_search_probe_cannot_publish(selected_index):
    import time
    from researcy.ingestion.jobs import short_transaction
    from researcy.retrieval.index import index_selected,verify_index,publish_ready

    fixture=selected_index;lease=fixture['lease'];conn=fixture['conn']
    index_selected(lease,time.monotonic()+60)
    hits=fixture['client'].request('POST','/collections/'+fixture['collection']+'/points/search',
        {'vector':[1.0]+[0.0]*1023,'limit':5,'with_payload':True})['result']
    probe_ids={hit['payload']['chunk_id'] for hit in hits}
    outside=next(chunk for chunk in fixture['chunks'] if str(chunk.id) not in probe_ids)
    with short_transaction(conn):
        conn.execute('ALTER TABLE chunk_span_mappings DISABLE TRIGGER USER')
        conn.execute('DELETE FROM chunk_span_mappings WHERE owner_id=%s AND chunk_id=%s',(lease.scope.owner_id,outside.id))
        conn.execute('ALTER TABLE chunk_span_mappings ENABLE TRIGGER USER')
    with pytest.raises(IntegrityFailure):
        receipt=verify_index(lease,time.monotonic()+60)
        publish_ready(conn,lease,receipt)
    with short_transaction(conn):
        assert conn.execute('SELECT stage,status FROM ingestion_jobs WHERE id=%s',(lease.job_id,)).fetchone()==('indexing','running')
        assert conn.execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',(lease.scope.owner_id,)).fetchall()==[]


def test_stale_verified_receipt_cannot_publish(selected_index,job_connections):
    import time
    from researcy.retrieval.index import index_selected,publish_ready
    from researcy.ingestion.jobs import claim_due,short_transaction
    from researcy.ingestion.models import LostLease
    from test_jobs import expire

    fixture=selected_index;lease=fixture['lease'];conn,new_conn=job_connections
    receipt=index_selected(lease,time.monotonic()+60)
    expire(new_conn,lease.job_id);replacement=claim_due(new_conn,'replacement-index-worker')
    assert replacement.generation>lease.generation
    with pytest.raises(LostLease):publish_ready(conn,lease,receipt)
    with short_transaction(conn):
        assert conn.execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',(lease.scope.owner_id,)).fetchall()==[]


def test_missing_prior_checkpoint_cannot_index_or_publish(selected_index,monkeypatch):
    import time
    from researcy.retrieval import index
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;lease=fixture['lease'];conn=fixture['conn']
    # Simulate a partially persisted checkpoint only in this disposable database.
    with short_transaction(conn):
        conn.execute('ALTER TABLE stage_manifests DISABLE TRIGGER trg_stage_manifests_immutable')
        conn.execute("DELETE FROM stage_manifests WHERE owner_id=%s AND document_version_id=%s AND stage='chunking'",
            (lease.scope.owner_id,lease.scope.document_version_id))
        conn.execute('ALTER TABLE stage_manifests ENABLE TRIGGER trg_stage_manifests_immutable')
    def forbidden_dependency(*args,**kwargs):
        raise AssertionError('A missing authoritative checkpoint must fail before Qdrant')
    with monkeypatch.context() as patched:
        patched.setattr(index,'QdrantClient',forbidden_dependency)
        with pytest.raises(IntegrityFailure):index.index_selected(lease,time.monotonic()+60)
    with short_transaction(conn):
        assert conn.execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',(lease.scope.owner_id,)).fetchall()==[]


@pytest.mark.parametrize('selected_index',[{'chunk_target':10,'chunk_maximum':20,'chunk_overlap':0}],indirect=True)
def test_prepublication_probe_reads_one_vector_from_a_multi_chunk_batch(selected_index):
    import time
    from researcy.retrieval.index import index_selected,publish_ready
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;conn=fixture['conn'];lease=fixture['lease']
    with short_transaction(conn):
        first_batch=conn.execute('SELECT chunk_ids,octet_length(selected_bytes) FROM embedding_batches WHERE owner_id=%s AND document_version_id=%s AND batch_ordinal=0',
            (lease.scope.owner_id,lease.scope.document_version_id)).fetchone()
    assert len(first_batch[0])>1 and first_batch[1]==len(first_batch[0])*1024*4
    receipt=index_selected(lease,time.monotonic()+60)
    publish_ready(conn,lease,receipt)
    with short_transaction(conn):
        assert conn.execute('SELECT stage,status FROM ingestion_jobs WHERE id=%s',(lease.job_id,)).fetchone()==('ready','succeeded')
        assert conn.execute('SELECT point_count FROM index_publications WHERE owner_id=%s AND document_version_id=%s',
            (lease.scope.owner_id,lease.scope.document_version_id)).fetchone()==(len(fixture['chunks']),)


@pytest.mark.parametrize('corruption',['missing-parser-artifact','unbound-embedding-hash'])
def test_incomplete_or_unbound_stage_manifest_cannot_index(selected_index,corruption,monkeypatch):
    import time
    from researcy.retrieval import index
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;conn=fixture['conn'];lease=fixture['lease']
    with short_transaction(conn):
        conn.execute('ALTER TABLE stage_manifests DISABLE TRIGGER trg_stage_manifests_immutable')
        if corruption=='missing-parser-artifact':
            conn.execute("UPDATE stage_manifests SET artifacts='[]'::jsonb WHERE owner_id=%s AND document_version_id=%s AND stage='parsing'",
                (lease.scope.owner_id,lease.scope.document_version_id))
        else:
            conn.execute("UPDATE stage_manifests SET content_hash=%s WHERE owner_id=%s AND document_version_id=%s AND stage='embedding'",
                (b'x'*32,lease.scope.owner_id,lease.scope.document_version_id))
        conn.execute('ALTER TABLE stage_manifests ENABLE TRIGGER trg_stage_manifests_immutable')
    def forbidden(*args,**kwargs):
        raise AssertionError('Incomplete immutable evidence must fail before external indexing')
    with monkeypatch.context() as patched:
        patched.setattr(index,'QdrantClient',forbidden)
        with pytest.raises(IntegrityFailure):index.index_selected(lease,time.monotonic()+60)
    with short_transaction(conn):
        assert conn.execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',(lease.scope.owner_id,)).fetchall()==[]


def test_equivalent_collection_creation_race_preserves_current_worker_contract(selected_index):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from researcy.retrieval import index
    from researcy.ingestion.models import StageFailure

    fixture=selected_index;client=fixture['client'];collection=fixture['collection']
    client.request('DELETE','/collections/'+collection)
    gate=threading.Barrier(2)
    class RacingClient(index.QdrantClient):
        def __init__(self):
            super().__init__();self.first=True
        def request(self,method,path,payload=None):
            result=super().request(method,path,payload)
            if method=='GET' and path=='/collections/'+collection and self.first:
                self.first=False;gate.wait(timeout=10)
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(index.ensure_collection,fixture['profile'],client=RacingClient()) for _ in range(2)]
        completed = 0
        for future in futures:
            try:
                future.result()
            except StageFailure as failure:
                # Qdrant may return a transient 5xx during concurrent creation.
                # The worker retries this fenced stage, not this HTTP call.
                assert (failure.code,failure.failure_kind,failure.retryable)==(
                    'DEPENDENCY_UNAVAILABLE','temporary',True)
            else:
                completed += 1
        assert completed>=1
    observed=client.request('GET','/collections/'+collection)['result']
    assert observed['config']['params']['vectors']['size']==1024
    assert observed['config']['params']['vectors']['distance']=='Cosine'
    assert {key:observed['payload_schema'][key]['data_type'] for key in
        ('owner_id','paper_id','document_version_id','section_type')}=={
        'owner_id':'keyword','paper_id':'keyword','document_version_id':'keyword','section_type':'keyword'}


def test_verify_rejects_collection_missing_a_required_payload_index(selected_index):
    import time
    from researcy.retrieval import index
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;lease=fixture['lease']
    index.index_selected(lease,time.monotonic()+60)
    response=fixture['client'].request('DELETE','/collections/'+fixture['collection']+'/index/owner_id?wait=true')
    assert response['result']['status']=='completed'
    with pytest.raises(IntegrityFailure):index.verify_index(lease,time.monotonic()+60)
    with short_transaction(fixture['conn']):
        assert fixture['conn'].execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',
            (lease.scope.owner_id,)).fetchall()==[]

@pytest.mark.parametrize('corruption',['search-status','scroll-type'])
def test_malformed_provider_envelope_cannot_verify_publication(selected_index,monkeypatch,corruption):
    import time
    from researcy.retrieval import index
    from researcy.ingestion.jobs import short_transaction

    fixture=selected_index;lease=fixture['lease']
    index.index_selected(lease,time.monotonic()+60)
    class CorruptEnvelopeClient(index.QdrantClient):
        def request(self,method,path,payload=None):
            if corruption=='scroll-type' and path.endswith('/points/scroll') and payload.get('offset')=='malformed-terminal-page':
                return {'status':'ok','result':{'points':{},'next_page_offset':None}}
            result=super().request(method,path,payload)
            if corruption=='search-status' and path.endswith('/points/search'):
                result['status']='error'
            if corruption=='scroll-type' and path.endswith('/points/scroll'):
                if result['result']['next_page_offset'] is None:
                    result['result']['next_page_offset']='malformed-terminal-page'
            return result
    with monkeypatch.context() as patched:
        patched.setattr(index,'QdrantClient',CorruptEnvelopeClient)
        with pytest.raises(IntegrityFailure):index.verify_index(lease,time.monotonic()+60)
    with short_transaction(fixture['conn']):
        assert fixture['conn'].execute('SELECT document_version_id FROM index_publications WHERE owner_id=%s',
            (lease.scope.owner_id,)).fetchall()==[]
