from alembic import op

revision = "0004_m2_safe_counters"
down_revision = "0003_m2_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_jobs_safe_counters
        CHECK(attempts<=9007199254740991 AND lease_generation<=9007199254740991
              AND retry_revision<=9007199254740991)""")


def downgrade() -> None:
    op.execute("ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_jobs_safe_counters")
