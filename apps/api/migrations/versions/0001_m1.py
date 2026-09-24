"""Initial M1 identity, library, intake, and rate-limit schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_m1"
down_revision = None
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_NOW = sa.text("CURRENT_TIMESTAMP")
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", _UUID, nullable=False, server_default=_UUID_DEFAULT),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("length(btrim(issuer)) > 0", name="ck_users_issuer_nonempty"),
        sa.CheckConstraint("length(btrim(sub)) > 0", name="ck_users_sub_nonempty"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("issuer", "sub", name="uq_users_issuer_sub"),
    )

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("csrf_verifier", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32 AND octet_length(csrf_verifier) = 32",
            name="ck_sessions_secret_hashes_sha256",
        ),
        sa.CheckConstraint(
            "idle_expires_at > issued_at AND absolute_expires_at > issued_at "
            "AND idle_expires_at <= absolute_expires_at",
            name="ck_sessions_expiries_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_sessions_owner_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("token_hash", name="pk_sessions"),
    )
    op.create_index("ix_sessions_owner_id", "sessions", ["owner_id"])

    op.create_table(
        "oauth_transactions",
        sa.Column("state_hash", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("pkce_verifier", sa.Text(), nullable=False),
        sa.Column("correlation_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(state_hash) = 32 AND octet_length(correlation_hash) = 32",
            name="ck_oauth_transactions_secret_hashes_sha256",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_oauth_transactions_expiry_ordered"),
        sa.PrimaryKeyConstraint("state_hash", name="pk_oauth_transactions"),
    )
    op.create_index("ix_oauth_transactions_expires_at", "oauth_transactions", ["expires_at"])

    op.create_table(
        "papers",
        sa.Column("id", _UUID, nullable=False, server_default=_UUID_DEFAULT),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("canonical_arxiv_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("active_version_id", _UUID, nullable=False),
        sa.Column(
            "acceptance_state", sa.Text(), nullable=False, server_default=sa.text("'accepted'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("source IN ('arxiv', 'upload')", name="ck_papers_source"),
        sa.CheckConstraint(
            "(source = 'arxiv' AND canonical_arxiv_id IS NOT NULL) OR "
            "(source = 'upload' AND canonical_arxiv_id IS NULL)",
            name="ck_papers_source_arxiv_id",
        ),
        sa.CheckConstraint("acceptance_state = 'accepted'", name="ck_papers_acceptance_state"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_papers_owner_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_papers"),
        sa.UniqueConstraint("owner_id", "id", name="uq_papers_owner_id_id"),
    )
    op.create_index("ix_papers_owner_created_at", "papers", ["owner_id", "created_at"])
    op.create_index(
        "uq_papers_owner_canonical_arxiv_id",
        "papers",
        ["owner_id", "canonical_arxiv_id"],
        unique=True,
        postgresql_where=sa.text("canonical_arxiv_id IS NOT NULL"),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", _UUID, nullable=False, server_default=_UUID_DEFAULT),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("paper_id", _UUID, nullable=False),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("screening_warning", sa.Text(), nullable=True),
        sa.Column("pending_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("octet_length(sha256) = 32", name="ck_document_versions_sha256_length"),
        sa.CheckConstraint("byte_count > 0", name="ck_document_versions_byte_count_positive"),
        sa.CheckConstraint("length(btrim(object_key)) > 0", name="ck_document_versions_object_key_nonempty"),
        sa.ForeignKeyConstraint(
            ["owner_id", "paper_id"],
            ["papers.owner_id", "papers.id"],
            name="fk_document_versions_owner_paper_papers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint("object_key", name="uq_document_versions_object_key"),
        sa.UniqueConstraint("owner_id", "id", name="uq_document_versions_owner_id_id"),
        sa.UniqueConstraint(
            "owner_id", "paper_id", "id", name="uq_document_versions_owner_paper_id"
        ),
    )
    op.create_index(
        "ix_document_versions_owner_paper", "document_versions", ["owner_id", "paper_id"]
    )
    op.create_foreign_key(
        "papers_active_version_fk",
        "papers",
        "document_versions",
        ["owner_id", "id", "active_version_id"],
        ["owner_id", "paper_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.execute(
        """
        CREATE FUNCTION m1_guard_document_versions() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.id, NEW.owner_id, NEW.paper_id, NEW.sha256, NEW.byte_count,
                NEW.object_key, NEW.source_url, NEW.source_version,
                NEW.screening_warning, NEW.created_at
            ) IS DISTINCT FROM ROW(
                OLD.id, OLD.owner_id, OLD.paper_id, OLD.sha256, OLD.byte_count,
                OLD.object_key, OLD.source_url, OLD.source_version,
                OLD.screening_warning, OLD.created_at
            ) THEN
                RAISE EXCEPTION 'document version source facts are immutable'
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'ck_document_versions_source_immutable';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_versions_immutable
        BEFORE UPDATE ON document_versions
        FOR EACH ROW EXECUTE FUNCTION m1_guard_document_versions()
        """
    )
    op.execute(
        """
        CREATE FUNCTION m1_guard_paper_active_version() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.active_version_id IS DISTINCT FROM OLD.active_version_id THEN
                RAISE EXCEPTION 'paper active version is immutable in M1'
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'ck_papers_active_version_immutable';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_papers_active_version_immutable
        BEFORE UPDATE ON papers
        FOR EACH ROW EXECUTE FUNCTION m1_guard_paper_active_version()
        """
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", _UUID, nullable=False, server_default=_UUID_DEFAULT),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("document_version_id", _UUID, nullable=False),
        sa.Column("stage", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("stage = 'queued'", name="ck_ingestion_jobs_m1_stage"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_ingestion_jobs_owner_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "document_version_id"],
            ["document_versions.owner_id", "document_versions.id"],
            name="fk_ingestion_jobs_owner_version_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        sa.UniqueConstraint("document_version_id", name="uq_ingestion_jobs_document_version"),
        sa.UniqueConstraint("owner_id", "id", name="uq_ingestion_jobs_owner_id_id"),
        sa.UniqueConstraint(
            "owner_id",
            "document_version_id",
            "id",
            name="uq_ingestion_jobs_owner_version_id",
        ),
    )
    op.create_index("ix_ingestion_jobs_owner_stage", "ingestion_jobs", ["owner_id", "stage"])

    op.create_table(
        "import_idempotency",
        sa.Column("id", _UUID, nullable=False, server_default=_UUID_DEFAULT),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.LargeBinary(), nullable=False),
        sa.Column("paper_id", _UUID, nullable=False),
        sa.Column("document_version_id", _UUID, nullable=False),
        sa.Column("job_id", _UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("length(btrim(idempotency_key)) > 0", name="ck_import_idempotency_key_nonempty"),
        sa.CheckConstraint("operation IN ('arxiv', 'upload')", name="ck_import_idempotency_operation"),
        sa.CheckConstraint("octet_length(request_digest) = 32", name="ck_import_idempotency_digest_length"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_import_idempotency_owner_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "paper_id", "document_version_id"],
            ["document_versions.owner_id", "document_versions.paper_id", "document_versions.id"],
            name="fk_import_idempotency_owner_paper_version_document_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "document_version_id", "job_id"],
            ["ingestion_jobs.owner_id", "ingestion_jobs.document_version_id", "ingestion_jobs.id"],
            name="fk_import_idempotency_owner_version_job_ingestion_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_idempotency"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_import_idempotency_owner_key"),
        sa.UniqueConstraint("owner_id", "id", name="uq_import_idempotency_owner_id_id"),
    )
    op.create_index(
        "ix_import_idempotency_owner_created_at",
        "import_idempotency",
        ["owner_id", "created_at"],
    )

    op.create_table(
        "import_rate_limits",
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("request_count >= 0", name="ck_import_rate_limits_count_nonnegative"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_import_rate_limits_owner_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("owner_id", "window_start", name="pk_import_rate_limits"),
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_papers_active_version_immutable ON papers")
    op.execute("DROP FUNCTION m1_guard_paper_active_version()")
    op.execute("DROP TRIGGER trg_document_versions_immutable ON document_versions")
    op.execute("DROP FUNCTION m1_guard_document_versions()")
    op.drop_table("import_rate_limits")
    op.drop_index("ix_import_idempotency_owner_created_at", table_name="import_idempotency")
    op.drop_table("import_idempotency")
    op.drop_index("ix_ingestion_jobs_owner_stage", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_constraint("papers_active_version_fk", "papers", type_="foreignkey")
    op.drop_index("ix_document_versions_owner_paper", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("uq_papers_owner_canonical_arxiv_id", table_name="papers")
    op.drop_index("ix_papers_owner_created_at", table_name="papers")
    op.drop_table("papers")
    op.drop_index("ix_oauth_transactions_expires_at", table_name="oauth_transactions")
    op.drop_table("oauth_transactions")
    op.drop_index("ix_sessions_owner_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
