"""Durable jobs, immutable processing identity and owner-scoped provenance."""
from alembic import op

revision = "0003_m2_processing"
down_revision = "0002_m1_source_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE document_versions ADD CONSTRAINT uq_version_source_hash UNIQUE(owner_id,id,sha256);
    ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ingestion_jobs_m1_stage;
    ALTER TABLE ingestion_jobs
      ADD COLUMN status text NOT NULL DEFAULT 'pending',
      ADD COLUMN locked_by text,
      ADD COLUMN lease_generation bigint NOT NULL DEFAULT 0,
      ADD COLUMN lease_expires_at timestamptz,
      ADD COLUMN heartbeat_at timestamptz,
      ADD COLUMN attempts bigint NOT NULL DEFAULT 0,
      ADD COLUMN cycle_attempts integer NOT NULL DEFAULT 0,
      ADD COLUMN retry_revision bigint NOT NULL DEFAULT 0,
      ADD COLUMN run_after timestamptz NOT NULL DEFAULT clock_timestamp(),
      ADD COLUMN updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      ADD COLUMN completed_at timestamptz,
      ADD COLUMN failed_stage text,
      ADD COLUMN error_code text,
      ADD COLUMN failure_kind text,
      ADD COLUMN retryable boolean NOT NULL DEFAULT false,
      ADD COLUMN profile_hash bytea,
      ADD CONSTRAINT ck_jobs_stage CHECK(stage IN ('queued','validating','parsing','normalizing','chunking','embedding','indexing','ready','failed')),
      ADD CONSTRAINT ck_jobs_status CHECK(status IN ('pending','running','succeeded','failed')),
      ADD CONSTRAINT ck_jobs_counters CHECK(lease_generation>=0 AND attempts>=0 AND cycle_attempts BETWEEN 0 AND 5 AND retry_revision>=0 AND cycle_attempts<=attempts),
      ADD CONSTRAINT ck_jobs_profile_hash CHECK(profile_hash IS NULL OR octet_length(profile_hash)=32),
      ADD CONSTRAINT ck_jobs_lease CHECK(
        (status='running' AND locked_by IS NOT NULL AND length(locked_by)>0 AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND lease_expires_at>heartbeat_at)
        OR (status<>'running' AND locked_by IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL)),
      ADD CONSTRAINT ck_jobs_terminal CHECK(
        (status='succeeded' AND stage='ready' AND completed_at IS NOT NULL AND error_code IS NULL AND NOT retryable)
        OR (status='failed' AND stage='failed' AND completed_at IS NOT NULL AND failed_stage IS NOT NULL AND error_code IS NOT NULL AND failure_kind IS NOT NULL)
        OR (status IN ('pending','running') AND stage NOT IN ('ready','failed') AND completed_at IS NULL)),
      ADD CONSTRAINT ck_jobs_failed_stage CHECK(failed_stage IS NULL OR failed_stage IN ('validating','parsing','normalizing','chunking','embedding','indexing')),
      ADD CONSTRAINT ck_jobs_failure_kind CHECK(failure_kind IS NULL OR failure_kind IN ('temporary','unsupported','resource_limit','integrity'));
    CREATE INDEX ix_jobs_due ON ingestion_jobs(run_after,created_at,id) WHERE status='pending';
    CREATE INDEX ix_jobs_expired ON ingestion_jobs(lease_expires_at,created_at,id) WHERE status='running';

    CREATE TABLE document_processing (
      owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid PRIMARY KEY,
      original_sha256 bytea NOT NULL CHECK(octet_length(original_sha256)=32),
      profile_hash bytea NOT NULL CHECK(octet_length(profile_hash)=32),
      profile jsonb NOT NULL CHECK(jsonb_typeof(profile)='object'),
      index_version bytea NOT NULL CHECK(octet_length(index_version)=32 AND index_version=profile_hash),
      sealed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(owner_id,document_version_id,profile_hash),
      UNIQUE(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_versions(owner_id,paper_id,id),
      FOREIGN KEY(owner_id,document_version_id,original_sha256) REFERENCES document_versions(owner_id,id,sha256));
    CREATE FUNCTION m2_lock_profile_source() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM 1 FROM document_versions WHERE id=NEW.document_version_id
        AND owner_id=NEW.owner_id AND paper_id=NEW.paper_id FOR UPDATE;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_profile_source_lock BEFORE INSERT ON document_processing
      FOR EACH ROW EXECUTE FUNCTION m2_lock_profile_source();
    ALTER TABLE ingestion_jobs ADD CONSTRAINT fk_jobs_processing
      FOREIGN KEY(owner_id,document_version_id,profile_hash)
      REFERENCES document_processing(owner_id,document_version_id,profile_hash);

    CREATE FUNCTION m2_numeric_array(value jsonb, expected integer) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE AS $$
    BEGIN
      IF jsonb_typeof(value) IS DISTINCT FROM 'array' THEN RETURN false; END IF;
      IF jsonb_array_length(value)<>expected THEN RETURN false; END IF;
      RETURN NOT EXISTS(SELECT 1 FROM jsonb_array_elements(value) x
        WHERE CASE WHEN jsonb_typeof(x)='number'
          THEN abs((x #>> '{}')::numeric)>=1e308::numeric ELSE true END);
    END; $$;
    CREATE FUNCTION m2_valid_box(value jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE AS $$
    BEGIN
      IF NOT m2_numeric_array(value,4) THEN RETURN false; END IF;
      RETURN (value->>0)::numeric<=(value->>2)::numeric AND (value->>1)::numeric<=(value->>3)::numeric;
    END; $$;
    CREATE FUNCTION m2_valid_boxes(value jsonb, expected integer) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE AS $$
    BEGIN
      IF jsonb_typeof(value) IS DISTINCT FROM 'array' THEN RETURN false; END IF;
      IF jsonb_array_length(value)<>expected THEN RETURN false; END IF;
      RETURN NOT EXISTS(SELECT 1 FROM jsonb_array_elements(value) x WHERE NOT m2_valid_box(x));
    END; $$;

    CREATE TABLE document_pages (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL,
      page_index integer NOT NULL CHECK(page_index>=0), media_box jsonb NOT NULL CHECK(m2_valid_box(media_box)),
      crop_box jsonb NOT NULL CHECK(m2_valid_box(crop_box)), rotation integer NOT NULL CHECK(rotation IN (0,90,180,270)),
      width double precision NOT NULL CHECK(width>0 AND width<'Infinity'::float8),
      height double precision NOT NULL CHECK(height>0 AND height<'Infinity'::float8),
      transform jsonb NOT NULL CHECK(m2_numeric_array(transform,6)),
      UNIQUE(owner_id,document_version_id,id), UNIQUE(document_version_id,page_index),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id));
    CREATE TABLE document_sections (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL,
      parent_id uuid, ordinal integer NOT NULL CHECK(ordinal>=0), title text, source_reference jsonb,
      UNIQUE(owner_id,document_version_id,id), UNIQUE(document_version_id,ordinal),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,parent_id) REFERENCES document_sections(owner_id,document_version_id,id) DEFERRABLE INITIALLY DEFERRED);
    CREATE TABLE document_blocks (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL,
      page_id uuid NOT NULL, section_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
      block_type text NOT NULL CHECK(block_type IN ('text','heading','caption','table','equation','image')),
      box jsonb NOT NULL CHECK(m2_valid_box(box)), excluded boolean NOT NULL DEFAULT false,
      UNIQUE(owner_id,document_version_id,id), UNIQUE(document_version_id,ordinal),
      UNIQUE(owner_id,document_version_id,id,page_id),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,page_id) REFERENCES document_pages(owner_id,document_version_id,id),
      FOREIGN KEY(owner_id,document_version_id,section_id) REFERENCES document_sections(owner_id,document_version_id,id));
    CREATE TABLE document_spans (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL,
      block_id uuid NOT NULL, page_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
      raw_text text NOT NULL CHECK(length(raw_text)>0), boxes jsonb NOT NULL CHECK(m2_valid_boxes(boxes,length(raw_text))),
      UNIQUE(owner_id,document_version_id,id), UNIQUE(document_version_id,ordinal),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,block_id,page_id) REFERENCES document_blocks(owner_id,document_version_id,id,page_id),
      FOREIGN KEY(owner_id,document_version_id,page_id) REFERENCES document_pages(owner_id,document_version_id,id));
    CREATE FUNCTION m2_guard_page_geometry() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE page_bounds jsonb; rectangles jsonb;
    BEGIN
      SELECT media_box INTO page_bounds FROM document_pages WHERE id=NEW.page_id
        AND owner_id=NEW.owner_id AND document_version_id=NEW.document_version_id;
      IF page_bounds IS NULL THEN RETURN NEW; END IF;
      IF TG_TABLE_NAME='document_spans' THEN
        IF NOT m2_valid_boxes(NEW.boxes,length(NEW.raw_text)) THEN
          RAISE EXCEPTION 'invalid source geometry' USING ERRCODE='check_violation';
        END IF;
        rectangles=NEW.boxes;
      ELSE
        IF NOT m2_valid_box(NEW.box) THEN
          RAISE EXCEPTION 'invalid source geometry' USING ERRCODE='check_violation';
        END IF;
        rectangles=jsonb_build_array(NEW.box);
      END IF;
      IF EXISTS(SELECT 1 FROM jsonb_array_elements(rectangles) r WHERE
        NOT m2_valid_box(r) OR (r->>0)::numeric<(page_bounds->>0)::numeric
        OR (r->>1)::numeric<(page_bounds->>1)::numeric
        OR (r->>2)::numeric>(page_bounds->>2)::numeric
        OR (r->>3)::numeric>(page_bounds->>3)::numeric) THEN
        RAISE EXCEPTION 'source geometry exceeds page' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_block_geometry BEFORE INSERT ON document_blocks
      FOR EACH ROW EXECUTE FUNCTION m2_guard_page_geometry();
    CREATE TRIGGER trg_span_geometry BEFORE INSERT ON document_spans
      FOR EACH ROW EXECUTE FUNCTION m2_guard_page_geometry();
    CREATE TABLE document_chunks (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL,
      profile_hash bytea NOT NULL, section_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
      text text NOT NULL CHECK(length(text)>0 AND length(text)<=2400),
      checksum bytea NOT NULL CHECK(octet_length(checksum)=32),
      UNIQUE(owner_id,document_version_id,id), UNIQUE(document_version_id,profile_hash,ordinal),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,profile_hash) REFERENCES document_processing(owner_id,document_version_id,profile_hash),
      FOREIGN KEY(owner_id,document_version_id,section_id) REFERENCES document_sections(owner_id,document_version_id,id));
    CREATE TABLE chunk_span_mappings (
      owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL,
      chunk_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
      chunk_start integer NOT NULL CHECK(chunk_start>=0), chunk_end integer NOT NULL CHECK(chunk_end>=chunk_start),
      span_id uuid, source_start integer, source_end integer,
      transformation text NOT NULL CHECK(transformation IN ('identity','whitespace','ligature','dehyphenation','separator')),
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(metadata)='object'),
      PRIMARY KEY(chunk_id,ordinal),
      CHECK((transformation='separator' AND span_id IS NULL AND source_start IS NULL AND source_end IS NULL AND chunk_end>chunk_start)
        OR (transformation<>'separator' AND span_id IS NOT NULL AND source_start>=0 AND source_end>source_start)),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,chunk_id) REFERENCES document_chunks(owner_id,document_version_id,id),
      FOREIGN KEY(owner_id,document_version_id,span_id) REFERENCES document_spans(owner_id,document_version_id,id));
    CREATE FUNCTION m2_guard_mapping_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE chunk_length integer; span_length integer;
    BEGIN
      SELECT length(text) INTO chunk_length FROM document_chunks WHERE id=NEW.chunk_id AND owner_id=NEW.owner_id AND document_version_id=NEW.document_version_id;
      IF chunk_length IS NOT NULL AND NEW.chunk_end>chunk_length THEN
        RAISE EXCEPTION 'chunk mapping exceeds text' USING ERRCODE='check_violation';
      END IF;
      IF NEW.span_id IS NOT NULL THEN
        SELECT length(raw_text) INTO span_length FROM document_spans WHERE id=NEW.span_id AND owner_id=NEW.owner_id AND document_version_id=NEW.document_version_id;
        IF span_length IS NOT NULL AND NEW.source_end>span_length THEN
          RAISE EXCEPTION 'source mapping exceeds text' USING ERRCODE='check_violation';
        END IF;
      END IF;
      IF NEW.transformation='identity' AND NEW.chunk_end-NEW.chunk_start<>NEW.source_end-NEW.source_start THEN
        RAISE EXCEPTION 'identity mapping length mismatch' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_mapping_bounds BEFORE INSERT ON chunk_span_mappings FOR EACH ROW EXECUTE FUNCTION m2_guard_mapping_bounds();

    CREATE TABLE stage_manifests (
      owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL, profile_hash bytea NOT NULL,
      stage text NOT NULL CHECK(stage IN ('validating','parsing','normalizing','chunking','embedding','indexing')),
      schema_version integer NOT NULL CHECK(schema_version=1), content_hash bytea NOT NULL CHECK(octet_length(content_hash)=32),
      record_count integer NOT NULL CHECK(record_count>=0), artifacts jsonb NOT NULL CHECK(jsonb_typeof(artifacts)='array'),
      completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(document_version_id,profile_hash,stage),
      UNIQUE(owner_id,document_version_id,profile_hash,stage,content_hash),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,profile_hash) REFERENCES document_processing(owner_id,document_version_id,profile_hash));
    CREATE TABLE embedding_batches (
      owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid NOT NULL, profile_hash bytea NOT NULL,
      batch_ordinal integer NOT NULL CHECK(batch_ordinal>=0), chunk_ids uuid[] NOT NULL CHECK(cardinality(chunk_ids) BETWEEN 1 AND 500),
      selected_bytes bytea NOT NULL, content_hash bytea NOT NULL CHECK(octet_length(content_hash)=32),
      artifact jsonb NOT NULL CHECK(jsonb_typeof(artifact)='object'), runtime_identity jsonb NOT NULL CHECK(jsonb_typeof(runtime_identity)='object'),
      selected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(document_version_id,profile_hash,batch_ordinal),
      CHECK(octet_length(selected_bytes)=cardinality(chunk_ids)*1024*4 AND sha256(selected_bytes)=content_hash),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,profile_hash) REFERENCES document_processing(owner_id,document_version_id,profile_hash));
    CREATE FUNCTION m2_guard_embedding_chunks() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM 1 FROM document_processing WHERE owner_id=NEW.owner_id
        AND document_version_id=NEW.document_version_id AND profile_hash=NEW.profile_hash FOR UPDATE;
      IF cardinality(NEW.chunk_ids)<>(SELECT count(*) FROM document_chunks
        WHERE owner_id=NEW.owner_id AND document_version_id=NEW.document_version_id
          AND profile_hash=NEW.profile_hash AND id=ANY(NEW.chunk_ids)) THEN
        RAISE EXCEPTION 'selected chunks do not match document' USING ERRCODE='foreign_key_violation';
      END IF;
      IF EXISTS(SELECT 1 FROM embedding_batches WHERE document_version_id=NEW.document_version_id
        AND profile_hash=NEW.profile_hash AND batch_ordinal<>NEW.batch_ordinal AND chunk_ids && NEW.chunk_ids) THEN
        RAISE EXCEPTION 'chunk already selected in another batch' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_embedding_chunks BEFORE INSERT ON embedding_batches
      FOR EACH ROW EXECUTE FUNCTION m2_guard_embedding_chunks();
    CREATE TABLE index_publications (
      owner_id uuid NOT NULL, paper_id uuid NOT NULL, document_version_id uuid PRIMARY KEY, profile_hash bytea NOT NULL,
      index_version bytea NOT NULL CHECK(octet_length(index_version)=32 AND index_version=profile_hash),
      chunk_set_hash bytea NOT NULL CHECK(octet_length(chunk_set_hash)=32),
      embedding_manifest_hash bytea NOT NULL CHECK(octet_length(embedding_manifest_hash)=32),
      embedding_stage text NOT NULL DEFAULT 'embedding' CHECK(embedding_stage='embedding'),
      collection text NOT NULL CHECK(length(collection)>0), point_count integer NOT NULL CHECK(point_count>0),
      point_set_hash bytea NOT NULL CHECK(octet_length(point_set_hash)=32),
      published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(owner_id,document_version_id,profile_hash),
      FOREIGN KEY(owner_id,paper_id,document_version_id) REFERENCES document_processing(owner_id,paper_id,document_version_id),
      FOREIGN KEY(owner_id,document_version_id,profile_hash) REFERENCES document_processing(owner_id,document_version_id,profile_hash),
      FOREIGN KEY(owner_id,document_version_id,profile_hash,embedding_stage,embedding_manifest_hash)
        REFERENCES stage_manifests(owner_id,document_version_id,profile_hash,stage,content_hash));
    CREATE TABLE ingestion_transitions (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      owner_id uuid NOT NULL, document_version_id uuid NOT NULL, job_id uuid NOT NULL,
      stage text NOT NULL CHECK(stage IN ('queued','validating','parsing','normalizing','chunking','embedding','indexing','ready','failed')),
      status text NOT NULL CHECK(status IN ('pending','running','succeeded','failed')), lease_generation bigint NOT NULL CHECK(lease_generation>=0),
      attempt bigint NOT NULL CHECK(attempt>=0), error_code text, occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      FOREIGN KEY(owner_id,document_version_id,job_id) REFERENCES ingestion_jobs(owner_id,document_version_id,id));
    CREATE INDEX ix_transitions_job ON ingestion_transitions(owner_id,job_id,id);
    CREATE TABLE processing_retry_rate_limits (
      owner_id uuid NOT NULL REFERENCES users(id), window_start timestamptz NOT NULL,
      request_count integer NOT NULL CHECK(request_count BETWEEN 0 AND 5), PRIMARY KEY(owner_id,window_start));

    CREATE FUNCTION m2_immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'sealed processing record is immutable' USING ERRCODE='check_violation';
    END; $$;
    CREATE TRIGGER trg_succeeded_job_immutable BEFORE UPDATE OR DELETE ON ingestion_jobs
      FOR EACH ROW WHEN (OLD.status='succeeded') EXECUTE FUNCTION m2_immutable_record();
    CREATE FUNCTION m2_guard_pending_configuration() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.pending_config IS DISTINCT FROM OLD.pending_config AND EXISTS(
        SELECT 1 FROM document_processing WHERE document_version_id=OLD.id) THEN
        RAISE EXCEPTION 'sealed configuration is immutable' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER trg_sealed_pending_configuration BEFORE UPDATE ON document_versions
      FOR EACH ROW EXECUTE FUNCTION m2_guard_pending_configuration();
    CREATE FUNCTION m2_require_publication() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE job ingestion_jobs; publication index_publications;
    BEGIN
      SELECT * INTO job FROM ingestion_jobs WHERE document_version_id=NEW.document_version_id;
      IF job.status='succeeded' THEN
        SELECT * INTO publication FROM index_publications WHERE document_version_id=NEW.document_version_id;
        IF publication.document_version_id IS NULL OR publication.owner_id<>job.owner_id
          OR publication.profile_hash IS DISTINCT FROM job.profile_hash THEN
          RAISE EXCEPTION 'ready requires matching publication' USING ERRCODE='check_violation';
        END IF;
      ELSIF TG_TABLE_NAME='index_publications' THEN
        RAISE EXCEPTION 'publication requires ready job' USING ERRCODE='check_violation';
      END IF;
      RETURN NULL;
    END; $$;
    CREATE CONSTRAINT TRIGGER trg_ready_publication AFTER INSERT OR UPDATE ON ingestion_jobs
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m2_require_publication();
    CREATE CONSTRAINT TRIGGER trg_publication_ready AFTER INSERT ON index_publications
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m2_require_publication();
    """)
    for table in (
        "document_processing", "document_pages", "document_sections", "document_blocks",
        "document_spans", "document_chunks", "chunk_span_mappings", "stage_manifests",
        "embedding_batches", "index_publications", "ingestion_transitions",
    ):
        op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION m2_immutable_record()")


def downgrade() -> None:
    # Disposable schema tests may reverse an unused migration; never erase sealed work.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM document_processing) OR EXISTS(SELECT 1 FROM ingestion_jobs WHERE stage<>'queued' OR status<>'pending') THEN
        RAISE EXCEPTION 'cannot downgrade processed documents' USING ERRCODE='check_violation';
      END IF;
    END; $$;
    DROP TRIGGER trg_ready_publication ON ingestion_jobs;
    DROP TRIGGER trg_succeeded_job_immutable ON ingestion_jobs;
    DROP TRIGGER trg_sealed_pending_configuration ON document_versions;
    ALTER TABLE ingestion_jobs DROP CONSTRAINT fk_jobs_processing;
    DROP TABLE processing_retry_rate_limits,ingestion_transitions,index_publications,embedding_batches,
      stage_manifests,chunk_span_mappings,document_chunks,document_spans,document_blocks,
      document_sections,document_pages,document_processing CASCADE;
    DROP FUNCTION m2_require_publication(),m2_guard_pending_configuration(),m2_guard_mapping_bounds(),m2_immutable_record(),
      m2_valid_boxes(jsonb,integer),m2_valid_box(jsonb),m2_numeric_array(jsonb,integer),m2_lock_profile_source(),
      m2_guard_embedding_chunks(),m2_guard_page_geometry();
    ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_jobs_stage, DROP CONSTRAINT ck_jobs_status,
      DROP CONSTRAINT ck_jobs_counters, DROP CONSTRAINT ck_jobs_profile_hash, DROP CONSTRAINT ck_jobs_lease,
      DROP CONSTRAINT ck_jobs_terminal, DROP CONSTRAINT ck_jobs_failed_stage, DROP CONSTRAINT ck_jobs_failure_kind;
    ALTER TABLE ingestion_jobs DROP COLUMN status,DROP COLUMN locked_by,DROP COLUMN lease_generation,
      DROP COLUMN lease_expires_at,DROP COLUMN heartbeat_at,DROP COLUMN attempts,DROP COLUMN cycle_attempts,
      DROP COLUMN retry_revision,DROP COLUMN run_after,DROP COLUMN updated_at,DROP COLUMN completed_at,
      DROP COLUMN failed_stage,DROP COLUMN error_code,DROP COLUMN failure_kind,DROP COLUMN retryable,DROP COLUMN profile_hash;
    ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ingestion_jobs_m1_stage CHECK(stage='queued');
    ALTER TABLE document_versions DROP CONSTRAINT uq_version_source_hash;
    """)
