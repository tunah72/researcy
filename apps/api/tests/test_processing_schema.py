from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg.types.json import Jsonb

from conftest import alembic_config
from test_schema import insert_user, insert_paper, insert_job, expect_constraint


@pytest.mark.parametrize("pg_conn", ["0002_m1_source_guards"], indirect=True)
def test_upgrade_preserves_accepted_sources_and_due_jobs(pg_conn):
    owner = insert_user(pg_conn, "m2-upgrade", "m2-test@example.test")
    preserved = []
    for arxiv in (None, "1706.03762"):
        paper, version = uuid4(), uuid4()
        pg_conn.execute("""INSERT INTO papers
            (id,owner_id,source,canonical_arxiv_id,active_version_id)
            VALUES (%s,%s,%s,%s,%s)""", (paper,owner,"arxiv" if arxiv else "upload",arxiv,version))
        pg_conn.execute("""INSERT INTO document_versions
            (id,owner_id,paper_id,sha256,byte_count,object_key,screening_warning)
            VALUES (%s,%s,%s,%s,1,%s,'LOW_TEXT')""", (version,owner,paper,bytes(range(32)),f"test/{version}"))
        job = insert_job(pg_conn, owner, version)
        key = uuid4().hex
        pg_conn.execute("""INSERT INTO import_idempotency
            (owner_id,idempotency_key,operation,request_digest,paper_id,document_version_id,job_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""", (owner, key, "arxiv" if arxiv else "upload", bytes(range(32)), paper, version, job))
        preserved.append((paper, version, job, key))
    pg_conn.commit()
    before = pg_conn.execute("SELECT id,sha256,object_key,screening_warning FROM document_versions ORDER BY id").fetchall()
    pg_conn.commit()
    database = pg_conn.info.dbname
    command.upgrade(alembic_config(database), "head")
    command.upgrade(alembic_config(database), "head")
    assert pg_conn.execute("SELECT id,sha256,object_key,screening_warning FROM document_versions ORDER BY id").fetchall() == before
    for paper, version, job, key in preserved:
        row = pg_conn.execute("""SELECT status,stage,attempts,cycle_attempts,retry_revision,
            locked_by,run_after<=clock_timestamp() FROM ingestion_jobs WHERE id=%s""", (job,)).fetchone()
        assert row == ("pending", "queued", 0, 0, 0, None, True)
        assert pg_conn.execute("SELECT paper_id,document_version_id,job_id FROM import_idempotency WHERE owner_id=%s AND idempotency_key=%s", (owner,key)).fetchone() == (paper,version,job)


def test_ready_requires_publication_in_same_commit(pg_conn):
    owner = insert_user(pg_conn, "ready-invariant", None)
    _, version = insert_paper(pg_conn, owner, None)
    job = insert_job(pg_conn, owner, version)
    with pytest.raises(psycopg.errors.CheckViolation):
        with pg_conn.transaction():
            pg_conn.execute("UPDATE ingestion_jobs SET stage='ready',status='succeeded',completed_at=clock_timestamp() WHERE id=%s", (job,))
            pg_conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_sealed_profile_and_pending_configuration_are_immutable(pg_conn):
    owner = insert_user(pg_conn, "sealed-profile", None)
    paper, version = insert_paper(pg_conn, owner, None)
    pg_conn.execute("""INSERT INTO document_processing
        (owner_id,paper_id,document_version_id,original_sha256,profile_hash,profile,index_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""", (owner,paper,version,bytes(range(32)),b'p'*32,Jsonb({"schema_version":1}),b'p'*32))
    expect_constraint(pg_conn, psycopg.errors.CheckViolation,
        "UPDATE document_processing SET profile=%s WHERE document_version_id=%s", (Jsonb({"schema_version":2}),version))
    expect_constraint(pg_conn, psycopg.errors.CheckViolation,
        "UPDATE document_versions SET pending_config=%s WHERE id=%s", (Jsonb({"parser":"changed"}),version))
    expect_constraint(pg_conn, psycopg.errors.CheckViolation,
        "DELETE FROM document_processing WHERE document_version_id=%s", (version,))


def _canonical(conn, owner, ordinal=0):
    paper, version = insert_paper(conn, owner, None)
    page, section, block, span, chunk = (uuid4() for _ in range(5))
    conn.execute("""INSERT INTO document_processing
        (owner_id,paper_id,document_version_id,original_sha256,profile_hash,profile,index_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""", (owner,paper,version,bytes(range(32)),b'p'*32,Jsonb({"schema_version":1}),b'p'*32))
    conn.execute("""INSERT INTO document_pages
        (id,owner_id,paper_id,document_version_id,page_index,media_box,crop_box,rotation,width,height,transform)
        VALUES (%s,%s,%s,%s,0,%s,%s,0,100,100,%s)""",
        (page,owner,paper,version,Jsonb([0,0,100,100]),Jsonb([0,0,100,100]),Jsonb([1,0,0,1,0,0])))
    conn.execute("""INSERT INTO document_sections(id,owner_id,paper_id,document_version_id,ordinal)
        VALUES (%s,%s,%s,%s,0)""", (section,owner,paper,version))
    conn.execute("""INSERT INTO document_blocks
        (id,owner_id,paper_id,document_version_id,page_id,section_id,ordinal,block_type,box)
        VALUES (%s,%s,%s,%s,%s,%s,0,'text',%s)""",
        (block,owner,paper,version,page,section,Jsonb([10,10,20,20])))
    conn.execute("""INSERT INTO document_spans
        (id,owner_id,paper_id,document_version_id,block_id,page_id,ordinal,raw_text,boxes)
        VALUES (%s,%s,%s,%s,%s,%s,0,'A',%s)""",
        (span,owner,paper,version,block,page,Jsonb([[10,10,20,20]])))
    conn.execute("""INSERT INTO document_chunks
        (id,owner_id,paper_id,document_version_id,profile_hash,section_id,ordinal,text,checksum)
        VALUES (%s,%s,%s,%s,%s,%s,0,'A',%s)""",
        (chunk,owner,paper,version,b'p'*32,section,b'c'*32))
    return paper, version, chunk, span


@pytest.mark.parametrize("foreign_owner", [False, True], ids=["different-version","different-owner"])
def test_mapping_cannot_attach_a_foreign_source_span(pg_conn, foreign_owner):
    owner = insert_user(pg_conn, f"mapping-{uuid4()}", None)
    other = insert_user(pg_conn, f"mapping-other-{uuid4()}", None) if foreign_owner else owner
    paper, version, chunk, span = _canonical(pg_conn, owner)
    _, _, _, foreign_span = _canonical(pg_conn, other)
    statement = """INSERT INTO chunk_span_mappings
        (owner_id,paper_id,document_version_id,chunk_id,ordinal,chunk_start,chunk_end,span_id,source_start,source_end,transformation)
        VALUES (%s,%s,%s,%s,0,0,1,%s,0,1,'identity')"""
    expect_constraint(pg_conn, psycopg.errors.ForeignKeyViolation, statement, (owner,paper,version,chunk,foreign_span))
    pg_conn.execute(statement, (owner,paper,version,chunk,span))
    assert pg_conn.execute("SELECT span_id FROM chunk_span_mappings WHERE chunk_id=%s", (chunk,)).fetchone() == (span,)
    expect_constraint(pg_conn, psycopg.errors.CheckViolation, """INSERT INTO chunk_span_mappings
        (owner_id,paper_id,document_version_id,chunk_id,ordinal,chunk_start,chunk_end,span_id,source_start,source_end,transformation)
        VALUES (%s,%s,%s,%s,1,0,2,%s,0,2,'identity')""", (owner,paper,version,chunk,span))


def test_embedding_batch_cannot_select_a_foreign_chunk(pg_conn):
    import hashlib
    import struct

    owner = insert_user(pg_conn, f"batch-{uuid4()}", None)
    other = insert_user(pg_conn, f"batch-other-{uuid4()}", None)
    paper, version, chunk, _ = _canonical(pg_conn, owner)
    _, _, foreign_chunk, _ = _canonical(pg_conn, other)
    vector = struct.pack("<1024f", 1, *([0] * 1023))
    statement = """INSERT INTO embedding_batches
        (owner_id,paper_id,document_version_id,profile_hash,batch_ordinal,chunk_ids,selected_bytes,content_hash,artifact,runtime_identity)
        VALUES (%s,%s,%s,%s,0,%s,%s,%s,%s,%s)"""
    params = (owner,paper,version,b'p'*32,[foreign_chunk],vector,hashlib.sha256(vector).digest(),Jsonb({}),Jsonb({}))
    expect_constraint(pg_conn, psycopg.errors.ForeignKeyViolation, statement, params)
    pg_conn.execute(statement, (owner,paper,version,b'p'*32,[chunk],vector,hashlib.sha256(vector).digest(),Jsonb({}),Jsonb({})))


def test_source_geometry_cannot_escape_its_page(pg_conn):
    owner = insert_user(pg_conn, f"geometry-{uuid4()}", None)
    paper, version, _, span = _canonical(pg_conn, owner)
    block, page = pg_conn.execute("SELECT block_id,page_id FROM document_spans WHERE id=%s", (span,)).fetchone()
    expect_constraint(pg_conn, psycopg.errors.CheckViolation, """INSERT INTO document_spans
        (id,owner_id,paper_id,document_version_id,block_id,page_id,ordinal,raw_text,boxes)
        VALUES (%s,%s,%s,%s,%s,%s,1,'B',%s)""",
        (uuid4(),owner,paper,version,block,page,Jsonb([[-1,10,20,20]])))


def test_selected_vector_hash_must_match_its_bytes(pg_conn):
    import struct

    owner = insert_user(pg_conn, f"vector-hash-{uuid4()}", None)
    paper, version, chunk, _ = _canonical(pg_conn, owner)
    vector = struct.pack("<1024f", 1, *([0] * 1023))
    expect_constraint(pg_conn, psycopg.errors.CheckViolation, """INSERT INTO embedding_batches
        (owner_id,paper_id,document_version_id,profile_hash,batch_ordinal,chunk_ids,selected_bytes,content_hash,artifact,runtime_identity)
        VALUES (%s,%s,%s,%s,0,%s,%s,%s,%s,%s)""",
        (owner,paper,version,b'p'*32,[chunk],vector,b'?'*32,Jsonb({}),Jsonb({})))


@pytest.mark.parametrize("mutation", ["requeue", "delete"])
def test_published_job_cannot_be_reset_or_deleted(pg_conn, mutation):
    owner = insert_user(pg_conn, f"published-{uuid4()}", None)
    paper, version, _, _ = _canonical(pg_conn, owner)
    job = insert_job(pg_conn, owner, version)
    pg_conn.execute("""INSERT INTO stage_manifests
        (owner_id,paper_id,document_version_id,profile_hash,stage,schema_version,content_hash,record_count,artifacts)
        VALUES(%s,%s,%s,%s,'embedding',1,%s,1,'[]')""", (owner,paper,version,b'p'*32,b'e'*32))
    pg_conn.execute("""INSERT INTO index_publications
        (owner_id,paper_id,document_version_id,profile_hash,index_version,chunk_set_hash,embedding_manifest_hash,
        collection,point_count,point_set_hash)
        VALUES(%s,%s,%s,%s,%s,%s,%s,'schema-test',1,%s)""", (owner,paper,version,b'p'*32,b'p'*32,b'c'*32,b'e'*32,b'q'*32))
    pg_conn.execute("""UPDATE ingestion_jobs SET stage='ready',status='succeeded',
        completed_at=clock_timestamp(),profile_hash=%s WHERE id=%s""", (b'p'*32,job))
    pg_conn.commit()
    statement = ("DELETE FROM ingestion_jobs WHERE id=%s" if mutation == "delete" else
        "UPDATE ingestion_jobs SET stage='queued',status='pending',completed_at=NULL WHERE id=%s")
    expect_constraint(pg_conn, psycopg.errors.CheckViolation, statement, (job,))
    assert pg_conn.execute("SELECT stage,status FROM ingestion_jobs WHERE id=%s", (job,)).fetchone() == ('ready','succeeded')
