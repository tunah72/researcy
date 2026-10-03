"""Immutable chunk lexical vector, ordinary PostgreSQL GIN."""
from alembic import op

revision = '0006_m3_lexical'
down_revision = '0005_m3_reader'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE document_chunks ADD COLUMN search_vector tsvector
      GENERATED ALWAYS AS (to_tsvector('simple'::regconfig,text)) STORED;
    CREATE INDEX ix_document_chunks_lexical ON document_chunks USING gin(search_vector);
    """)


def downgrade() -> None:
    op.execute('DROP INDEX ix_document_chunks_lexical; ALTER TABLE document_chunks DROP COLUMN search_vector;')
