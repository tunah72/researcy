"""Require accepted papers to pin an immutable source version."""

from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_m1_source_guards"
down_revision = "0001_m1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "papers",
        "active_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        nullable=False,
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


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_papers_active_version_immutable ON papers")
    op.execute("DROP FUNCTION m1_guard_paper_active_version()")
    op.execute("DROP TRIGGER trg_document_versions_immutable ON document_versions")
    op.execute("DROP FUNCTION m1_guard_document_versions()")
    op.alter_column(
        "papers",
        "active_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        nullable=True,
    )
