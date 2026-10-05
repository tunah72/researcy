import psycopg
import pytest

from test_research_repository import reserve


def test_completed_results_source_pins_and_terminal_winner_are_immutable(research_sources):
    from researcy.research.repository import finish_research
    f=research_sources;run=reserve(f);conn=f['conn']
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][0])
    finish_research(conn,run,ideas,citations,{})
    for statement,params in (
        ('UPDATE research_run_sources SET ordinal=3 WHERE run_id=%s',(run.run_id,)),
        ('DELETE FROM research_run_sources WHERE run_id=%s',(run.run_id,)),
        ("UPDATE research_runs SET state='failed',error_code='RESEARCH_FAILED' WHERE id=%s",(run.run_id,)),
        ("UPDATE research_ideas SET observed_gap='Changed source assertion' WHERE run_id=%s",(run.run_id,)),
        ('DELETE FROM research_citations WHERE run_id=%s',(run.run_id,)),
        ('INSERT INTO research_ideas SELECT owner_id,run_id,1,observed_gap,proposed_direction,possible_method '
            'FROM research_ideas WHERE run_id=%s AND idea_index=0',(run.run_id,)),
        ('INSERT INTO research_run_sources SELECT owner_id,run_id,paper_id,document_version,profile_hash,3,false '
            'FROM research_run_sources WHERE run_id=%s AND ordinal=0',(run.run_id,)),
    ):
        with pytest.raises(psycopg.Error):
            with conn.transaction():conn.execute(statement,params)
    assert conn.execute('SELECT state FROM research_runs WHERE id=%s',(run.run_id,)).fetchone()==('completed',)


def test_accepted_rows_require_completed_run_in_same_transaction(research_sources):
    f=research_sources;run=reserve(f);conn=f['conn']
    with pytest.raises(psycopg.Error):
        with conn.transaction():
            conn.execute('INSERT INTO research_ideas(owner_id,run_id,idea_index,observed_gap,proposed_direction,possible_method) '
                "VALUES(%s,%s,0,'Evidence','Hypothesis','Method')",(f['owner_id'],run.run_id))
    assert conn.execute('SELECT count(*) FROM research_ideas').fetchone()==(0,)


@pytest.mark.parametrize('pg_conn',['0007_m4_discovery'],indirect=True)
def test_populated_0007_upgrade_twice_preserves_all_original_intake_identities(research_sources):
    from alembic import command
    from conftest import alembic_config
    from researcy.research.repository import fail_research,get_owned_research,finish_research,record_research_attempt
    from researcy.errors import APIError
    from uuid import uuid4
    f=research_sources;conn=f['conn'];source=f['publications'][0];scope=source['scope']
    conn.execute('''INSERT INTO import_idempotency(owner_id,idempotency_key,operation,request_digest,
        paper_id,document_version_id,job_id) VALUES(%s,%s,'upload',%s,%s,%s,%s)''',
        (f['owner_id'],str(uuid4()),b'x'*32,scope.paper_id,scope.document_version_id,source['job']))
    tables=('papers','document_versions','ingestion_jobs','import_idempotency')
    before={table:conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() for table in tables}
    conn.commit()
    command.upgrade(alembic_config(conn.info.dbname),'head')
    command.upgrade(alembic_config(conn.info.dbname),'head')
    after={table:conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() for table in tables}
    assert after==before
    conn.commit()
    aborted=reserve(f);record_research_attempt(conn,aborted,'initial')
    fail_research(conn,aborted,'RESEARCH_INTERRUPTED',True,(),{'status':'unknown'})
    assert get_owned_research(conn,f['owner_id'],aborted.active_paper_id,aborted.run_id).state=='interrupted'
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][0])
    with pytest.raises(APIError):finish_research(conn,aborted,ideas,citations,{})
    completed=reserve(f);record_research_attempt(conn,completed,'initial')
    finish_research(conn,completed,ideas,citations,{})
    assert get_owned_research(conn,f['owner_id'],completed.active_paper_id,completed.run_id).state=='completed'
