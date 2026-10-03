from array import array
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading

import pytest

from researcy.ingestion.models import ProcessingProfile,StageFailure
from researcy.retrieval.embedding import EmbeddingClient


@pytest.fixture
def embedding_endpoint():
    profile=ProcessingProfile();state={'mode':'valid','requests':[]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/api/version':payload={'version':'0.18.2'}
            elif self.path=='/api/tags':
                payload={'models':[{'name':profile.model_tag,'digest':('0'*64 if state['mode']=='wrong-digest' else profile.model_digest)}]}
            else:self.send_error(404);return
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(payload).encode())
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append((self.path,body))
            if self.path=='/api/show':
                payload={'details':{'quantization_level':'Q4_0' if state['mode']=='wrong-quantization' else 'F16'},
                    'model_info':{'general.architecture':'bert','bert.embedding_length':512 if state['mode']=='wrong-dimension' else 1024},'capabilities':['embedding']}
            elif self.path=='/api/embed':
                if state['mode']=='overflow':
                    self.send_response(400);self.end_headers();self.wfile.write(b'{"error":"input length exceeds maximum context length"}');return
                if state['mode']=='bad-gzip':
                    self.send_response(200);self.send_header('Content-Encoding','gzip');self.end_headers();self.wfile.write(b'Not a gzip stream');return
                if state['mode']=='tokenization-error':
                    self.send_response(400);self.end_headers();self.wfile.write(b'{"error":"embedding tokenization failed"}');return
                vectors=[[3.0,4.0]+[0.0]*1022 for _ in body['input']]
                if state['mode']=='cardinality':vectors=vectors[:-1]
                elif state['mode']=='dimension':vectors[0]=vectors[0][:-1]
                elif state['mode']=='zero':vectors[0]=[0.0]*1024
                elif state['mode']=='nan':vectors[0][0]=float('nan')
                elif state['mode']=='infinity':vectors[0][0]=float('inf')
                elif state['mode']=='boolean':vectors[0][0]=True
                payload={'model':profile.model_tag,'embeddings':vectors}
            else:self.send_error(404);return
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(payload).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',state
    finally:server.shutdown();server.server_close();thread.join()


def test_selected_serialization_is_finite_unit_float32_with_order_preserved(embedding_endpoint):
    endpoint,state=embedding_endpoint;client=EmbeddingClient(ProcessingProfile(),endpoint=endpoint)
    identity=client.preflight();encoded=client.embed(('First text','Second text'))
    values=array('f');values.frombytes(encoded)
    assert len(encoded)==2*1024*4
    assert values[0]==pytest.approx(.6,abs=1e-7) and values[1]==pytest.approx(.8,abs=1e-7)
    assert sum(float(value)**2 for value in values[:1024])==pytest.approx(1,abs=1e-6)
    assert identity['version']=='0.18.2' and identity['model_digest']==ProcessingProfile().model_digest
    requests=[body for path,body in state['requests'] if path=='/api/embed']
    assert requests[-1]['input']==['First text','Second text'] and requests[-1]['truncate'] is False


@pytest.mark.parametrize('mode',['wrong-digest','wrong-quantization','wrong-dimension'])
def test_preflight_rejects_a_model_different_from_the_sealed_profile(embedding_endpoint,mode):
    endpoint,state=embedding_endpoint;state['mode']=mode
    with pytest.raises(StageFailure) as exc:
        EmbeddingClient(ProcessingProfile(),endpoint=endpoint).preflight()
    assert exc.value.code=='EMBEDDING_MODEL_MISMATCH' and exc.value.retryable is False
    assert not any(path=='/api/embed' for path,_ in state['requests'])


@pytest.mark.parametrize('mode',['cardinality','dimension','zero','nan','infinity','boolean'])
def test_malformed_vectors_fail_before_any_bytes_are_selected(embedding_endpoint,mode):
    endpoint,state=embedding_endpoint;client=EmbeddingClient(ProcessingProfile(),endpoint=endpoint)
    client.preflight();state['mode']=mode
    with pytest.raises(StageFailure) as exc:
        client.embed(('Consumer-visible boundary',))
    assert exc.value.code=='EMBEDDING_OUTPUT_INVALID' and exc.value.retryable is False


def test_context_overflow_is_explicit_and_never_silently_truncated(embedding_endpoint):
    endpoint,state=embedding_endpoint;client=EmbeddingClient(ProcessingProfile(),endpoint=endpoint)
    client.preflight();state['mode']='overflow'
    with pytest.raises(StageFailure) as exc:client.embed(('Too much context',))
    assert exc.value.code=='EMBEDDING_CONTEXT_LIMIT' and exc.value.retryable is False


def test_first_selected_batch_wins_even_when_recomputation_changes_bytes(queued_job,job_connections,tmp_path):
    from researcy.documents.repository import write_canonical_batch,write_chunk_batch,select_embedding_batch,seal_embedding_manifest
    from researcy.documents.normalize import normalize_records
    from researcy.documents.chunking import iter_sections,chunk_section
    from researcy.documents.artifacts import put_artifact
    from researcy.ingestion.jobs import claim_due,seal_profile,short_transaction
    from test_document_provenance import source_lines
    from dataclasses import replace
    import hashlib

    scope,_=queued_job;conn,_=job_connections
    lease=claim_due(conn,'embedding-selection-test');profile=seal_profile(conn,lease,ProcessingProfile())
    records=list(normalize_records(source_lines([[('Mapped source.',600,0,'text')]]),profile,scope=scope))
    write_canonical_batch(conn,lease,records)
    chunks=[chunk for section in iter_sections(records) for chunk in chunk_section(section,profile)]
    write_chunk_batch(conn,lease,chunks)
    with short_transaction(conn):conn.execute("UPDATE ingestion_jobs SET stage='embedding' WHERE id=%s AND owner_id=%s",(lease.job_id,scope.owner_id))
    lease=replace(lease,stage='embedding')
    first=array('f',[1.0]+[0.0]*1023).tobytes();second=array('f',[0.0,1.0]+[0.0]*1022).tobytes()
    path=tmp_path/'first.bin';path.write_bytes(first);ref=put_artifact(scope,profile.profile_hash,'embedding',path)
    identity={'runtime':'ollama','version':'0.18.2','model_tag':profile.model_tag,'model_digest':profile.model_digest,'dimension':1024,'quantization':'F16'}
    selected=select_embedding_batch(conn,lease,0,ref,(chunks[0].id,),selected_bytes=first,runtime_identity=identity)
    path=tmp_path/'second.bin';path.write_bytes(second);candidate=put_artifact(scope,profile.profile_hash,'embedding',path)
    replay=select_embedding_batch(conn,lease,0,candidate,(chunks[0].id,),selected_bytes=second,runtime_identity=identity)
    assert selected==replay==ref and candidate.sha256!=ref.sha256
    with short_transaction(conn):
        observed=conn.execute('SELECT selected_bytes,content_hash FROM embedding_batches WHERE owner_id=%s AND document_version_id=%s AND batch_ordinal=0',(scope.owner_id,scope.document_version_id)).fetchone()
    assert observed==(first,hashlib.sha256(first).digest())
    manifest=seal_embedding_manifest(conn,lease)
    assert manifest.artifacts==(ref,) and manifest.record_count==1


def test_embedding_failures_keep_their_safe_persisted_classification(queued_job,job_connections):
    from researcy.ingestion.jobs import claim_due,record_failure

    scope,job=queued_job;conn,_=job_connections;lease=claim_due(conn,'embedding-failure-test')
    record_failure(conn,lease,StageFailure('EMBEDDING_MODEL_MISMATCH','integrity',False))
    observed=conn.execute('SELECT error_code,failure_kind,retryable FROM ingestion_jobs WHERE id=%s AND owner_id=%s',(job,scope.owner_id)).fetchone()
    assert observed==('EMBEDDING_MODEL_MISMATCH','integrity',False)


def test_partial_selected_batch_cannot_claim_complete_chunk_coverage(queued_job,job_connections,tmp_path):
    from dataclasses import replace
    from researcy.documents.normalize import normalize_records
    from researcy.documents.chunking import iter_sections,chunk_section
    from researcy.documents.repository import write_canonical_batch,write_chunk_batch,select_embedding_batch
    from researcy.documents.artifacts import put_artifact
    from researcy.ingestion.jobs import claim_due,seal_profile,short_transaction
    from test_document_provenance import source_lines

    scope,_=queued_job;conn,_=job_connections;lease=claim_due(conn,'embedding-partial-test')
    profile=seal_profile(conn,lease,ProcessingProfile(chunk_target=10,chunk_maximum=20,chunk_overlap=0))
    records=list(normalize_records(source_lines([[('A'*80,600,0,'text')]]),profile,scope=scope))
    write_canonical_batch(conn,lease,records)
    chunks=[chunk for section in iter_sections(records) for chunk in chunk_section(section,profile)]
    write_chunk_batch(conn,lease,chunks)
    with short_transaction(conn):conn.execute("UPDATE ingestion_jobs SET stage='embedding' WHERE id=%s",(lease.job_id,))
    lease=replace(lease,stage='embedding')
    encoded=array('f',[1.0]+[0.0]*1023).tobytes();path=tmp_path/'partial.bin';path.write_bytes(encoded)
    ref=put_artifact(scope,profile.profile_hash,'embedding',path)
    identity={'runtime':'ollama','version':'0.18.2','model_tag':profile.model_tag,'model_digest':profile.model_digest,'dimension':1024,'quantization':'F16'}
    with pytest.raises(StageFailure):
        select_embedding_batch(conn,lease,0,ref,(chunks[0].id,),selected_bytes=encoded,runtime_identity=identity)
    with short_transaction(conn):
        assert conn.execute('SELECT chunk_ids FROM embedding_batches WHERE owner_id=%s AND document_version_id=%s',(scope.owner_id,scope.document_version_id)).fetchall()==[]


def test_stale_worker_cannot_select_any_embedding_batch(queued_job,job_connections,tmp_path):
    from researcy.documents.repository import select_embedding_batch
    from researcy.documents.artifacts import put_artifact
    from researcy.ingestion.jobs import claim_due
    from researcy.ingestion.models import LostLease
    from test_jobs import expire

    scope,job=queued_job;old_conn,new_conn=job_connections
    stale=claim_due(old_conn,'old-embedding-worker')
    expire(new_conn,job);current=claim_due(new_conn,'new-embedding-worker')
    assert current.generation>stale.generation
    data=array('f',[1.0]+[0.0]*1023).tobytes();path=tmp_path/'candidate.bin';path.write_bytes(data)
    artifact=put_artifact(scope,ProcessingProfile().profile_hash,'embedding',path)
    with pytest.raises(LostLease):
        select_embedding_batch(old_conn,stale,0,artifact,(job,),selected_bytes=data,runtime_identity={})
    assert old_conn.execute('SELECT chunk_ids FROM embedding_batches WHERE owner_id=%s AND document_version_id=%s',(scope.owner_id,scope.document_version_id)).fetchall()==[]


@pytest.mark.parametrize('endpoint',['http://user:secret@localhost:11434','http://localhost:11434/path','http://localhost:bad','http://local host:11434'])
def test_native_runtime_origin_rejects_credentials_and_invalid_hosts(endpoint,monkeypatch):
    from researcy.config import Settings

    monkeypatch.setenv('OLLAMA_BASE_URL',endpoint)
    with pytest.raises(ValueError):Settings.from_env()


@pytest.mark.parametrize('mode,code,retryable',[('bad-gzip','DEPENDENCY_UNAVAILABLE',True),
    ('tokenization-error','EMBEDDING_OUTPUT_INVALID',False)])
def test_provider_protocol_failures_are_not_misreported_as_context_overflow(embedding_endpoint,mode,code,retryable):
    endpoint,state=embedding_endpoint;client=EmbeddingClient(ProcessingProfile(),endpoint=endpoint)
    client.preflight();state['mode']=mode
    with pytest.raises(StageFailure) as exc:client.embed(('Exact failure contract',))
    assert exc.value.code==code and exc.value.retryable is retryable


def test_cancelled_embedding_waiter_releases_before_busy_slot_finishes(monkeypatch):
    from researcy.ingestion.models import LostLease
    from researcy.retrieval import embedding
    cancel,done = threading.Event(),threading.Event()
    failures = []
    client = EmbeddingClient(ProcessingProfile(),cancel=cancel)
    async def preflight():
        return {}
    monkeypatch.setattr(client,'_preflight',preflight)
    def wait_for_slot():
        try:
            client.preflight()
        except LostLease:
            failures.append('cancelled')
        finally:
            done.set()
    embedding._EMBED_LOCK.acquire()
    thread = threading.Thread(target=wait_for_slot,daemon=True)
    try:
        thread.start()
        cancel.set()
        assert done.wait(1)
        assert failures==['cancelled']
    finally:
        embedding._EMBED_LOCK.release()
        thread.join(timeout=2)
