"""Discovery metadata and request-scoped accounting; no document jobs."""
from alembic import op

revision = '0007_m4_discovery'
down_revision = '0006_m3_lexical'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('''
    ALTER TABLE papers ADD COLUMN abstract text;
    CREATE TABLE discovery_runs (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL, paper_id uuid NOT NULL,
      document_version uuid NOT NULL, request_id uuid NOT NULL,
      state text NOT NULL CHECK(state IN ('running','completed','failed','interrupted')),
      started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      lease_expires_at timestamptz NOT NULL, finished_at timestamptz,
      action text CHECK(action IN ('search_arxiv_metadata','stop')),
      generation_calls integer NOT NULL DEFAULT 0 CHECK(generation_calls BETWEEN 0 AND 2),
      metadata_searches integer NOT NULL DEFAULT 0 CHECK(metadata_searches BETWEEN 0 AND 1),
      inspected_unique integer NOT NULL DEFAULT 0 CHECK(inspected_unique BETWEEN 0 AND 10),
      eligible integer NOT NULL DEFAULT 0 CHECK(eligible BETWEEN 0 AND 10),
      returned integer NOT NULL DEFAULT 0 CHECK(returned BETWEEN 0 AND 3),
      error_code text, usage jsonb NOT NULL DEFAULT '{}', latency_ms bigint CHECK(latency_ms>=0),
      FOREIGN KEY(owner_id,paper_id,document_version)
        REFERENCES document_versions(owner_id,paper_id,id),
      CHECK((state='running')=(finished_at IS NULL)));
    CREATE UNIQUE INDEX uq_discovery_running_owner ON discovery_runs(owner_id) WHERE state='running';
    CREATE INDEX ix_discovery_owner_time ON discovery_runs(owner_id,started_at);
    ''')


def downgrade() -> None:
    op.execute('DROP TABLE discovery_runs; ALTER TABLE papers DROP COLUMN abstract;')
