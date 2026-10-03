from uuid import uuid4

from alembic import command
import psycopg
import pytest

from conftest import alembic_config
from test_schema import insert_user,insert_paper


@pytest.mark.parametrize('pg_conn',['0004_m2_safe_counters'],indirect=True)
def test_reader_upgrade_preserves_existing_source_and_is_idempotent(pg_conn):
    owner = insert_user(pg_conn,str(uuid4()),None)
    paper, version = insert_paper(pg_conn,owner,None)
    pg_conn.commit()
    before = pg_conn.execute('SELECT row_to_json(v)::text FROM document_versions v WHERE id=%s',(version,)).fetchone()[0]
    pg_conn.commit()
    command.upgrade(alembic_config(pg_conn.info.dbname),'head')
    command.upgrade(alembic_config(pg_conn.info.dbname),'head')
    after = pg_conn.execute('SELECT row_to_json(v)::text FROM document_versions v WHERE id=%s',(version,)).fetchone()[0]
    assert before==after
    assert pg_conn.execute('SELECT active_version_id FROM papers WHERE owner_id=%s AND id=%s',(owner,paper)).fetchone()[0]==version
    assert pg_conn.execute("SELECT to_regclass('reader_runs'),to_regclass('reader_request_quota')").fetchone()==('reader_runs','reader_request_quota')


def test_conversation_cannot_cross_owner_paper_version_or_repin(pg_conn):
    owner_a = insert_user(pg_conn,str(uuid4()),None)
    owner_b = insert_user(pg_conn,str(uuid4()),None)
    paper_a, version_a = insert_paper(pg_conn,owner_a,None)
    paper_b, version_b = insert_paper(pg_conn,owner_b,None)
    pg_conn.commit()
    for owner,paper,version in ((owner_a,paper_b,version_b),(owner_a,paper_a,version_b),(owner_b,paper_a,version_a)):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with pg_conn.transaction():
                pg_conn.execute('INSERT INTO conversations(owner_id,paper_id,document_version) VALUES(%s,%s,%s)',(owner,paper,version))
    conversation = pg_conn.execute('INSERT INTO conversations(owner_id,paper_id,document_version) VALUES(%s,%s,%s) RETURNING id',
        (owner_a,paper_a,version_a)).fetchone()[0]
    pg_conn.commit()
    with pytest.raises(psycopg.errors.CheckViolation):
        with pg_conn.transaction():
            pg_conn.execute('UPDATE conversations SET document_version=%s WHERE id=%s',(version_b,conversation))
    pg_conn.commit()
