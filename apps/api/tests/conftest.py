import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url


DEFAULT_TEST_ADMIN_URL = (
    "postgresql://researcy:local-postgres-password@127.0.0.1:55432/postgres"
)
TEST_ADMIN_URL = make_url(
    os.getenv("TEST_DATABASE_ADMIN_URL", DEFAULT_TEST_ADMIN_URL)
)
if TEST_ADMIN_URL.drivername not in {"postgresql", "postgresql+psycopg"}:
    raise ValueError("TEST_DATABASE_ADMIN_URL must use PostgreSQL")
if TEST_ADMIN_URL.database not in {"postgres", "template1"}:
    raise ValueError("TEST_DATABASE_ADMIN_URL must target the postgres maintenance database")
API_ROOT = Path(__file__).resolve().parents[1]


def _database_url(database: str, drivername: str = "postgresql") -> str:
    return TEST_ADMIN_URL.set(drivername=drivername, database=database).render_as_string(
        hide_password=False
    )


def alembic_config(database: str) -> Config:
    database_url = _database_url(database, "postgresql+psycopg")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture
def pg_conn(request):
    database = f"researcy_test_{uuid4().hex}"
    admin_conn = psycopg.connect(
        _database_url(TEST_ADMIN_URL.database), autocommit=True
    )
    test_conn = None
    created = False
    try:
        admin_conn.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
        )
        created = True
        test_conn = psycopg.connect(_database_url(database))
        command.upgrade(alembic_config(database), getattr(request, "param", "head"))
        yield test_conn
    finally:
        if test_conn is not None:
            test_conn.rollback()
            test_conn.close()
        if created:
            admin_conn.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))
            )
        admin_conn.close()


@pytest.fixture
def queued_job(pg_conn):
    from test_schema import insert_user, insert_paper, insert_job
    from researcy.ingestion.models import DocumentScope

    owner = insert_user(pg_conn, f"queue-{uuid4()}", None)
    paper, version = insert_paper(pg_conn, owner, None)
    job = insert_job(pg_conn, owner, version)
    pg_conn.commit()
    return DocumentScope(owner, paper, version), job


@pytest.fixture
def job_connections(pg_conn):
    with psycopg.connect(_database_url(pg_conn.info.dbname)) as first:
        with psycopg.connect(_database_url(pg_conn.info.dbname)) as second:
            yield first, second


from test_screening import private_bucket


@pytest.fixture
def selected_index(pg_conn,job_connections,tmp_path,monkeypatch,private_bucket,request):
    from array import array
    from dataclasses import replace
    from contextlib import contextmanager
    from itertools import batched
    from researcy.documents.normalize import normalize_records
    from researcy.documents.chunking import iter_sections,chunk_section
    from researcy.documents.repository import write_canonical_batch,write_chunk_batch,select_embedding_batch,seal_embedding_manifest
    from researcy.documents.artifacts import put_artifact
    from researcy.ingestion.jobs import claim_due,seal_profile,commit_stage,short_transaction
    from researcy.ingestion.models import ProcessingProfile,DocumentScope,StageManifest,ArtifactRef
    from researcy.retrieval import index
    from test_screening import _pdf,_insert_owned_version
    from test_schema import insert_job
    from researcy.papers.objects import put_original,get_owned_original
    from researcy.papers.screening import screen_pdf
    from researcy.documents.parser import parse_pdf
    from researcy.documents.models import SandboxLimits,read_parser_records
    import hashlib
    import time

    options=dict(getattr(request,'param',{}))
    texts=options.pop('source_texts',('Owned exact source for indexed evidence.',))
    conn,_=job_connections;profile=ProcessingProfile(**options)
    scope=DocumentScope(uuid4(),uuid4(),uuid4())
    original=_pdf(tmp_path/'original.pdf',texts=texts)
    screen_pdf(original,'application/pdf');source_bytes=original.read_bytes();source_hash=hashlib.sha256(source_bytes).digest()
    key=put_original(scope.owner_id,scope.document_version_id,original,source_hash.hex())
    _insert_owned_version(conn,scope.owner_id,scope.paper_id,scope.document_version_id,key,source_hash.hex(),len(source_bytes))
    job=insert_job(conn,scope.owner_id,scope.document_version_id);conn.commit()
    assert b''.join(get_owned_original(conn,scope.owner_id,scope.paper_id,scope.document_version_id))==source_bytes
    conn.commit()
    lease=claim_due(conn,'index-test');seal_profile(conn,lease,profile)
    original_ref=ArtifactRef(key,source_hash,len(source_bytes))
    commit_stage(conn,lease,StageManifest('validating',profile.profile_hash,source_hash,1,(original_ref,)),'parsing')
    lease=replace(lease,stage='parsing')
    parsed=tmp_path/'parser.jsonl';limits=SandboxLimits.full_parser();parse_pdf(original,parsed,limits)
    parser_records=list(read_parser_records(parsed,limits));parser_ref=put_artifact(scope,profile.profile_hash,'parsing',parsed)
    commit_stage(conn,lease,StageManifest('parsing',profile.profile_hash,parser_ref.sha256,len(parser_records),(parser_ref,)),'normalizing')
    lease=replace(lease,stage='normalizing')
    records=list(normalize_records(parser_records,profile,scope=scope));write_canonical_batch(conn,lease,records)
    canonical_hash=hashlib.sha256(b''.join(record.id.bytes for record in records)).digest()
    commit_stage(conn,lease,StageManifest('normalizing',profile.profile_hash,canonical_hash,len(records),(parser_ref,)),'chunking')
    lease=replace(lease,stage='chunking')
    chunks=[]
    for section in iter_sections(records):chunks.extend(chunk_section(section,profile,start_ordinal=len(chunks)))
    write_chunk_batch(conn,lease,chunks)
    chunk_hash=hashlib.sha256(b''.join(chunk.checksum for chunk in chunks)).digest()
    commit_stage(conn,lease,StageManifest('chunking',profile.profile_hash,chunk_hash,len(chunks),()),'embedding')
    lease=replace(lease,stage='embedding')
    identity={'runtime':'ollama','version':'0.18.2','model_tag':profile.model_tag,'model_digest':profile.model_digest,'dimension':1024,'quantization':'F16'}
    for ordinal,batch in enumerate(batched(chunks,4)):
        vectors=array('f',([1.0]+[0.0]*1023)*len(batch)).tobytes()
        path=tmp_path/f'selected-{ordinal}.bin';path.write_bytes(vectors)
        artifact=put_artifact(scope,profile.profile_hash,'embedding',path)
        select_embedding_batch(conn,lease,ordinal,artifact,tuple(chunk.id for chunk in batch),selected_bytes=vectors,runtime_identity=identity)
    manifest=seal_embedding_manifest(conn,lease);commit_stage(conn,lease,manifest,'indexing');lease=replace(lease,stage='indexing')
    collection='m2_test_'+uuid4().hex
    monkeypatch.setattr(index,'collection_name',lambda profile:collection)
    @contextmanager
    def scoped_connection():
        with psycopg.connect(_database_url(conn.info.dbname)) as connection:yield connection
    monkeypatch.setattr(index,'get_conn',scoped_connection)
    client=index.QdrantClient(deadline=time.monotonic()+60)
    try:
        index.ensure_collection(profile,client=client)
        yield {'scope':scope,'job':job,'lease':lease,'profile':profile,'chunks':chunks,'collection':collection,
            'client':client,'conn':conn,'get_conn':scoped_connection,'manifest':manifest}
    finally:
        client.deadline=time.monotonic()+30
        client.request('DELETE','/collections/'+collection)
