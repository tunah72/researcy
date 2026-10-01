"""Version-pinned conversations and bounded request-scoped Reader runs."""
from alembic import op

revision = "0005_m3_reader"
down_revision = "0004_m2_safe_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE conversations (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_id uuid NOT NULL,
      paper_id uuid NOT NULL, document_version uuid NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(owner_id,id,paper_id,document_version),
      FOREIGN KEY(owner_id,paper_id,document_version) REFERENCES document_versions(owner_id,paper_id,id));
    CREATE INDEX ix_conversations_owner_paper_created ON conversations(owner_id,paper_id,created_at DESC,id DESC);
    CREATE FUNCTION m3_pin_conversation_source() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (NEW.id,NEW.owner_id,NEW.paper_id,NEW.document_version,NEW.created_at)
          IS DISTINCT FROM (OLD.id,OLD.owner_id,OLD.paper_id,OLD.document_version,OLD.created_at) THEN
        RAISE EXCEPTION 'conversation source is immutable' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_conversation_source BEFORE UPDATE ON conversations
      FOR EACH ROW EXECUTE FUNCTION m3_pin_conversation_source();

    CREATE TABLE messages (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, conversation_id uuid NOT NULL,
      paper_id uuid NOT NULL, document_version uuid NOT NULL,
      sequence bigint NOT NULL CHECK(sequence>0), role text NOT NULL CHECK(role IN ('user','assistant')),
      text text NOT NULL, state text NOT NULL CHECK(state IN ('running','completed','refused','failed','interrupted')),
      error_code text, request_id uuid NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      CHECK(role<>'user' OR (state='completed' AND length(text) BETWEEN 1 AND 2400 AND length(btrim(text))>0)),
      CHECK((state IN ('failed','interrupted') AND error_code IS NOT NULL)
          OR (state NOT IN ('failed','interrupted') AND error_code IS NULL)),
      UNIQUE(owner_id,conversation_id,sequence),
      UNIQUE(owner_id,conversation_id,paper_id,document_version,id,role),
      FOREIGN KEY(owner_id,conversation_id,paper_id,document_version)
        REFERENCES conversations(owner_id,id,paper_id,document_version));

    CREATE TABLE reader_runs (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, conversation_id uuid NOT NULL,
      paper_id uuid NOT NULL, document_version uuid NOT NULL, client_message_id uuid NOT NULL,
      user_message_id uuid NOT NULL, assistant_message_id uuid NOT NULL,
      user_role text GENERATED ALWAYS AS ('user'::text) STORED,
      assistant_role text GENERATED ALWAYS AS ('assistant'::text) STORED,
      state text NOT NULL CHECK(state IN ('running','completed','refused','failed','interrupted')),
      request_id uuid NOT NULL, started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      lease_expires_at timestamptz NOT NULL, finished_at timestamptz,
      generation_calls smallint NOT NULL DEFAULT 0 CHECK(generation_calls BETWEEN 0 AND 2),
      validated_action jsonb CHECK(validated_action IS NULL OR jsonb_typeof(validated_action)='object'),
      usage jsonb CHECK(usage IS NULL OR jsonb_typeof(usage)='object'),
      cost_usd numeric CHECK(cost_usd IS NULL OR cost_usd>=0),
      cost_source text NOT NULL DEFAULT 'unavailable' CHECK(cost_source IN ('provider','documented_tariff','unavailable')),
      latency_ms bigint CHECK(latency_ms IS NULL OR latency_ms>=0),
      first_delta_ms bigint CHECK(first_delta_ms IS NULL OR first_delta_ms>=0),
      validation_outcome text,
      CHECK(lease_expires_at>=started_at AND lease_expires_at<=started_at+INTERVAL '165 seconds'),
      CHECK((state='running' AND finished_at IS NULL) OR (state<>'running' AND finished_at IS NOT NULL)),
      UNIQUE(owner_id,conversation_id,client_message_id),
      UNIQUE(owner_id,id), UNIQUE(owner_id,conversation_id,user_message_id), UNIQUE(owner_id,conversation_id,assistant_message_id),
      FOREIGN KEY(owner_id,conversation_id,paper_id,document_version)
        REFERENCES conversations(owner_id,id,paper_id,document_version),
      FOREIGN KEY(owner_id,conversation_id,paper_id,document_version,user_message_id,user_role)
        REFERENCES messages(owner_id,conversation_id,paper_id,document_version,id,role),
      FOREIGN KEY(owner_id,conversation_id,paper_id,document_version,assistant_message_id,assistant_role)
        REFERENCES messages(owner_id,conversation_id,paper_id,document_version,id,role));
    CREATE UNIQUE INDEX uq_reader_running_conversation ON reader_runs(conversation_id) WHERE state='running';
    CREATE UNIQUE INDEX uq_reader_running_owner ON reader_runs(owner_id) WHERE state='running';
    CREATE INDEX ix_reader_expired ON reader_runs(owner_id,lease_expires_at) WHERE state='running';

    CREATE TABLE reader_request_quota (
      owner_id uuid NOT NULL, run_id uuid PRIMARY KEY, accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      FOREIGN KEY(owner_id,run_id) REFERENCES reader_runs(owner_id,id));
    CREATE INDEX ix_reader_quota_owner_time ON reader_request_quota(owner_id,accepted_at);

    CREATE TABLE citations (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, conversation_id uuid NOT NULL,
      assistant_message_id uuid NOT NULL, assistant_role text GENERATED ALWAYS AS ('assistant'::text) STORED,
      paper_id uuid NOT NULL, document_version uuid NOT NULL,
      claim_index integer NOT NULL CHECK(claim_index BETWEEN 0 AND 11),
      source_ref text NOT NULL CHECK(length(source_ref)>0),
      evidence_quote text NOT NULL CHECK(length(evidence_quote) BETWEEN 1 AND 2000),
      page_id uuid NOT NULL, page integer NOT NULL CHECK(page>0),
      boxes jsonb NOT NULL CHECK(jsonb_typeof(boxes)='array' AND jsonb_array_length(boxes)>0
        AND m2_valid_boxes(boxes,jsonb_array_length(boxes))),
      raw_fragments jsonb NOT NULL CHECK(jsonb_typeof(raw_fragments)='array' AND jsonb_array_length(raw_fragments)>0),
      ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 23),
      section text, state text NOT NULL CHECK(state IN ('provisional','accepted')),
      UNIQUE(owner_id,assistant_message_id,ordinal),
      FOREIGN KEY(owner_id,conversation_id,paper_id,document_version,assistant_message_id,assistant_role)
        REFERENCES messages(owner_id,conversation_id,paper_id,document_version,id,role),
      FOREIGN KEY(owner_id,document_version,page_id) REFERENCES document_pages(owner_id,document_version_id,id));
    CREATE INDEX ix_citations_owned_message ON citations(owner_id,assistant_message_id,id);
    CREATE FUNCTION m3_guard_citation_page() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE original_page integer;
    BEGIN
      SELECT page_index+1 INTO original_page FROM document_pages
        WHERE id=NEW.page_id AND owner_id=NEW.owner_id AND document_version_id=NEW.document_version;
      IF original_page IS NOT NULL AND original_page<>NEW.page THEN
        RAISE EXCEPTION 'citation page mismatch' USING ERRCODE='check_violation';
      END IF;
      IF NEW.state='accepted' AND NOT EXISTS(SELECT 1 FROM messages
          WHERE id=NEW.assistant_message_id AND owner_id=NEW.owner_id AND conversation_id=NEW.conversation_id
          AND role='assistant' AND state='completed') THEN
        RAISE EXCEPTION 'accepted citation requires completed answer' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_citation_page BEFORE INSERT OR UPDATE ON citations
      FOR EACH ROW EXECUTE FUNCTION m3_guard_citation_page();
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE citations,reader_request_quota,reader_runs,messages,conversations;
    DROP FUNCTION m3_guard_citation_page(),m3_pin_conversation_source();
    """)
