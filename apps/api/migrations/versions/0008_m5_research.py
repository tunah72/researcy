"""Pinned selected sources and atomically accepted Research premises."""
from alembic import op

revision='0008_m5_research'
down_revision='0007_m4_discovery'
branch_labels=None
depends_on=None


def upgrade() -> None:
    op.execute('''
    CREATE TABLE research_runs (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, active_paper_id uuid NOT NULL,
      document_version uuid NOT NULL, request_id uuid NOT NULL,
      source_count smallint NOT NULL CHECK(source_count BETWEEN 2 AND 4),
      state text NOT NULL CHECK(state IN ('running','completed','failed','interrupted')),
      started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      lease_expires_at timestamptz NOT NULL, finished_at timestamptz, publication_xid xid8,
      generation_calls smallint NOT NULL DEFAULT 0 CHECK(generation_calls BETWEEN 0 AND 2),
      repairs smallint NOT NULL DEFAULT 0 CHECK(repairs BETWEEN 0 AND 1 AND repairs<=generation_calls),
      error_code text, draft_ideas jsonb NOT NULL DEFAULT '[]'
        CHECK(jsonb_typeof(draft_ideas)='array' AND jsonb_array_length(draft_ideas)<=3 AND octet_length(draft_ideas::text)<=65536),
      metrics jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metrics)='object' AND octet_length(metrics::text)<=65536),
      UNIQUE(owner_id,id),
      FOREIGN KEY(owner_id,active_paper_id,document_version) REFERENCES document_versions(owner_id,paper_id,id),
      CHECK(lease_expires_at>=started_at AND lease_expires_at<=started_at+INTERVAL '165 seconds'),
      CHECK((state='running')=(finished_at IS NULL)),
      CHECK((state IN ('failed','interrupted'))=(error_code IS NOT NULL)),
      CHECK((state='completed')=(publication_xid IS NOT NULL)),
      CHECK(state IN ('failed','interrupted') OR draft_ideas='[]'::jsonb));
    CREATE UNIQUE INDEX uq_research_running_owner ON research_runs(owner_id) WHERE state='running';
    CREATE INDEX ix_research_owner_time ON research_runs(owner_id,started_at);
    CREATE INDEX ix_research_expired ON research_runs(owner_id,lease_expires_at) WHERE state='running';

    CREATE TABLE research_run_sources (
      owner_id uuid NOT NULL, run_id uuid NOT NULL, paper_id uuid NOT NULL,
      document_version uuid NOT NULL, profile_hash bytea NOT NULL CHECK(octet_length(profile_hash)=32),
      ordinal smallint NOT NULL CHECK(ordinal BETWEEN 0 AND 3), is_active boolean NOT NULL,
      PRIMARY KEY(owner_id,run_id,paper_id), UNIQUE(owner_id,run_id,ordinal),
      UNIQUE(owner_id,run_id,paper_id,document_version), CHECK(is_active=(ordinal=0)),
      FOREIGN KEY(owner_id,run_id) REFERENCES research_runs(owner_id,id),
      FOREIGN KEY(owner_id,paper_id,document_version) REFERENCES document_versions(owner_id,paper_id,id),
      FOREIGN KEY(owner_id,document_version,profile_hash) REFERENCES index_publications(owner_id,document_version_id,profile_hash));

    CREATE TABLE research_ideas (
      owner_id uuid NOT NULL, run_id uuid NOT NULL, idea_index smallint NOT NULL CHECK(idea_index BETWEEN 0 AND 2),
      observed_gap text NOT NULL CHECK(length(observed_gap) BETWEEN 1 AND 1200 AND length(btrim(observed_gap))>0),
      proposed_direction text NOT NULL CHECK(length(proposed_direction) BETWEEN 1 AND 1200 AND length(btrim(proposed_direction))>0),
      possible_method text NOT NULL CHECK(length(possible_method) BETWEEN 1 AND 1200 AND length(btrim(possible_method))>0),
      PRIMARY KEY(owner_id,run_id,idea_index), FOREIGN KEY(owner_id,run_id) REFERENCES research_runs(owner_id,id));

    CREATE TABLE research_citations (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, run_id uuid NOT NULL,
      idea_index smallint NOT NULL CHECK(idea_index BETWEEN 0 AND 2),
      paper_id uuid NOT NULL, document_version uuid NOT NULL,
      source_ref text NOT NULL CHECK(length(source_ref) BETWEEN 1 AND 64),
      evidence_quote text NOT NULL CHECK(length(evidence_quote) BETWEEN 1 AND 2000),
      page_id uuid NOT NULL, page integer NOT NULL CHECK(page>0), section text,
      boxes jsonb NOT NULL CHECK(jsonb_typeof(boxes)='array' AND jsonb_array_length(boxes)>0
        AND m2_valid_boxes(boxes,jsonb_array_length(boxes))),
      raw_fragments jsonb NOT NULL CHECK(jsonb_typeof(raw_fragments)='array' AND jsonb_array_length(raw_fragments)>0),
      ordinal smallint NOT NULL CHECK(ordinal BETWEEN 0 AND 23), UNIQUE(owner_id,run_id,ordinal),
      FOREIGN KEY(owner_id,run_id,idea_index) REFERENCES research_ideas(owner_id,run_id,idea_index),
      FOREIGN KEY(owner_id,run_id,paper_id,document_version) REFERENCES research_run_sources(owner_id,run_id,paper_id,document_version),
      FOREIGN KEY(owner_id,document_version,page_id) REFERENCES document_pages(owner_id,document_version_id,id));
    CREATE INDEX ix_research_citations_owned ON research_citations(owner_id,run_id,id);

    CREATE FUNCTION m5_pin_run() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (NEW.id,NEW.owner_id,NEW.active_paper_id,NEW.document_version,NEW.request_id,NEW.started_at,NEW.source_count)
          IS DISTINCT FROM (OLD.id,OLD.owner_id,OLD.active_paper_id,OLD.document_version,OLD.request_id,OLD.started_at,OLD.source_count)
          OR NEW.generation_calls<OLD.generation_calls OR NEW.repairs<OLD.repairs
          OR NEW.lease_expires_at>OLD.lease_expires_at THEN
        RAISE EXCEPTION 'research pins and accounting are immutable' USING ERRCODE='check_violation';
      END IF;
      IF OLD.state<>'running' AND (NEW.state,NEW.finished_at,NEW.error_code,NEW.draft_ideas,
          NEW.generation_calls,NEW.repairs,NEW.lease_expires_at,NEW.publication_xid) IS DISTINCT FROM
          (OLD.state,OLD.finished_at,OLD.error_code,OLD.draft_ideas,OLD.generation_calls,OLD.repairs,OLD.lease_expires_at,OLD.publication_xid) THEN
        RAISE EXCEPTION 'research terminal winner is immutable' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_research_pin_run BEFORE UPDATE ON research_runs FOR EACH ROW EXECUTE FUNCTION m5_pin_run();
    CREATE TRIGGER trg_research_run_delete BEFORE DELETE ON research_runs FOR EACH ROW EXECUTE FUNCTION m2_immutable_record();
    CREATE TRIGGER trg_research_sources_immutable BEFORE UPDATE OR DELETE ON research_run_sources FOR EACH ROW EXECUTE FUNCTION m2_immutable_record();
    CREATE TRIGGER trg_research_ideas_immutable BEFORE UPDATE OR DELETE ON research_ideas FOR EACH ROW EXECUTE FUNCTION m2_immutable_record();
    CREATE TRIGGER trg_research_citations_immutable BEFORE UPDATE OR DELETE ON research_citations FOR EACH ROW EXECUTE FUNCTION m2_immutable_record();

    CREATE FUNCTION m5_guard_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE run_state text; original_page integer; run_xid xid8;
    BEGIN
      SELECT state,publication_xid INTO run_state,run_xid FROM research_runs WHERE owner_id=NEW.owner_id AND id=NEW.run_id FOR UPDATE;
      IF (TG_TABLE_NAME='research_run_sources' AND run_state<>'running') OR
          (TG_TABLE_NAME<>'research_run_sources' AND (run_state<>'completed' OR run_xid IS DISTINCT FROM pg_current_xact_id())) THEN
        RAISE EXCEPTION 'research evidence requires its terminal transaction' USING ERRCODE='check_violation';
      END IF;
      IF TG_TABLE_NAME='research_citations' THEN
        SELECT page_index+1 INTO original_page FROM document_pages
          WHERE owner_id=NEW.owner_id AND paper_id=NEW.paper_id AND document_version_id=NEW.document_version AND id=NEW.page_id;
        IF original_page IS NULL OR original_page<>NEW.page THEN
          RAISE EXCEPTION 'research citation page mismatch' USING ERRCODE='check_violation';
        END IF;
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_research_source_insert BEFORE INSERT ON research_run_sources FOR EACH ROW EXECUTE FUNCTION m5_guard_insert();
    CREATE TRIGGER trg_research_idea_insert BEFORE INSERT ON research_ideas FOR EACH ROW EXECUTE FUNCTION m5_guard_insert();
    CREATE TRIGGER trg_research_citation_insert BEFORE INSERT ON research_citations FOR EACH ROW EXECUTE FUNCTION m5_guard_insert();

    CREATE FUNCTION m5_check_complete_set() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r research_runs; source_total integer; idea_total integer; citation_total integer;
    BEGIN
      IF TG_TABLE_NAME='research_runs' THEN
        SELECT * INTO r FROM research_runs WHERE owner_id=NEW.owner_id AND id=NEW.id;
      ELSE
        SELECT * INTO r FROM research_runs WHERE owner_id=NEW.owner_id AND id=NEW.run_id;
      END IF;
      SELECT count(*) INTO source_total FROM research_run_sources WHERE owner_id=r.owner_id AND run_id=r.id;
      IF source_total<>r.source_count OR NOT EXISTS(SELECT 1 FROM research_run_sources
          WHERE owner_id=r.owner_id AND run_id=r.id AND ordinal=0 AND paper_id=r.active_paper_id AND document_version=r.document_version)
          OR (SELECT max(ordinal) FROM research_run_sources WHERE owner_id=r.owner_id AND run_id=r.id)<>source_total-1 THEN
        RAISE EXCEPTION 'research source set mismatch' USING ERRCODE='check_violation';
      END IF;
      SELECT count(*) INTO idea_total FROM research_ideas WHERE owner_id=r.owner_id AND run_id=r.id;
      SELECT count(*) INTO citation_total FROM research_citations WHERE owner_id=r.owner_id AND run_id=r.id;
      IF (r.state='completed' AND (idea_total NOT BETWEEN 1 AND 3 OR citation_total NOT BETWEEN 1 AND 24
          OR (SELECT max(idea_index) FROM research_ideas WHERE owner_id=r.owner_id AND run_id=r.id)<>idea_total-1
          OR EXISTS(SELECT 1 FROM research_ideas i WHERE i.owner_id=r.owner_id AND i.run_id=r.id AND NOT EXISTS(
            SELECT 1 FROM research_citations c WHERE c.owner_id=i.owner_id AND c.run_id=i.run_id AND c.idea_index=i.idea_index))))
          OR (r.state<>'completed' AND (idea_total<>0 OR citation_total<>0)) THEN
        RAISE EXCEPTION 'research accepted set mismatch' USING ERRCODE='check_violation';
      END IF;
      RETURN NULL;
    END; $$;
    CREATE CONSTRAINT TRIGGER trg_research_run_set AFTER INSERT OR UPDATE ON research_runs
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m5_check_complete_set();
    CREATE CONSTRAINT TRIGGER trg_research_source_set AFTER INSERT ON research_run_sources
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m5_check_complete_set();
    CREATE CONSTRAINT TRIGGER trg_research_idea_set AFTER INSERT ON research_ideas
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m5_check_complete_set();
    CREATE CONSTRAINT TRIGGER trg_research_citation_set AFTER INSERT ON research_citations
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m5_check_complete_set();
    ''')


def downgrade() -> None:
    op.execute('''DROP TABLE research_citations,research_ideas,research_run_sources,research_runs;
        DROP FUNCTION m5_check_complete_set(),m5_guard_insert(),m5_pin_run();''')
