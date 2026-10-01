from ..config import get_settings
from ..errors import APIError
from ..ingestion.presentation import preparation
from .models import MAX_SEARCH_LENGTH
class ImportQuotaExceeded(APIError):
    __slots__ = ("retry_after",)

    def __init__(self, retry_after: int):
        super().__init__(
            429,
            "IMPORT_RATE_LIMITED",
            "The import limit was reached. Try again after the indicated interval.",
        )
        self.retry_after = retry_after


_PAPER_SELECT = """
SELECT p.id, p.title, p.authors, p.year, p.source, j.stage,
       v.id, v.source_version, v.screening_warning,
       j.id AS job_id, j.status, j.attempts, j.failure_kind, j.retryable, j.retry_revision,
       GREATEST(0, ceil(extract(epoch FROM j.run_after - clock_timestamp())))::bigint AS retry_after_seconds,
       EXISTS(
           SELECT 1 FROM index_publications ip
           WHERE ip.owner_id = j.owner_id
             AND ip.paper_id = p.id
             AND ip.document_version_id = j.document_version_id
             AND ip.profile_hash = j.profile_hash
       ) AS published, j.lease_generation
FROM papers AS p
JOIN document_versions AS v
  ON v.owner_id = p.owner_id
 AND v.paper_id = p.id
 AND v.id = p.active_version_id
JOIN ingestion_jobs AS j
  ON j.owner_id = v.owner_id
 AND j.document_version_id = v.id
"""
_PAPER_FIELDS = (
    "paper_id",
    "title",
    "authors",
    "year",
    "source",
    "stage",
    "active_version_id",
    "source_version",
    "screening_warning",
    "job_id",
    "status",
    "attempts",
    "failure_kind",
    "retryable",
    "retry_revision",
    "retry_after_seconds",
    "published",
    "lease_generation",
)


def _paper(row) -> dict:
    raw = dict(zip(_PAPER_FIELDS, row, strict=True))
    prep = preparation(
        stage=raw["stage"],
        status=raw["status"],
        attempts=raw["attempts"],
        retry_revision=raw["retry_revision"],
        lease_generation=raw["lease_generation"],
        failure_kind=raw["failure_kind"],
        retryable=raw["retryable"],
        retry_after_seconds=raw["retry_after_seconds"],
        published=raw["published"],
    )
    return {
        "paper_id": raw["paper_id"],
        "title": raw["title"],
        "authors": raw["authors"],
        "year": raw["year"],
        "source": raw["source"],
        "stage": raw["stage"],
        "active_version_id": raw["active_version_id"],
        "source_version": raw["source_version"],
        "screening_warning": raw["screening_warning"],
        "job_id": raw["job_id"],
        "retry_revision": raw["retry_revision"],
        "preparation": prep,
    }

def get_paper(conn, owner_id, paper_id) -> dict | None:
    row = conn.execute(
        _PAPER_SELECT + "WHERE p.owner_id = %s AND p.id = %s",
        (owner_id, paper_id),
    ).fetchone()
    return _paper(row) if row is not None else None


def list_papers(conn, owner_id, search) -> list[dict]:
    search = search.strip() if search is not None else ""
    if len(search) > MAX_SEARCH_LENGTH:
        raise ValueError(f"search must be at most {MAX_SEARCH_LENGTH} characters")

    query = _PAPER_SELECT + "WHERE p.owner_id = %s"
    params = [owner_id]
    if search:
        query += """
          AND (
              strpos(lower(coalesce(p.title, '')), lower(%s)) > 0
              OR EXISTS (
                  SELECT 1
                  FROM unnest(coalesce(p.authors, ARRAY[]::text[])) AS a(author)
                  WHERE strpos(lower(a.author), lower(%s)) > 0
              )
          )
        """
        params.extend((search, search))
    query += " ORDER BY p.created_at DESC, p.id ASC"
    return [_paper(row) for row in conn.execute(query, params).fetchall()]


def take_import_slot(conn, owner_id, *, import_limit: int | None = None) -> None:
    if import_limit is None:
        import_limit = get_settings().import_quota_limit
    if import_limit <= 0:
        raise ValueError("import_limit must be a positive integer")
    window_start, retry_after = conn.execute(
        """
        SELECT date_trunc('hour', statement_timestamp()),
               GREATEST(
                   1,
                   ceil(extract(epoch FROM (
                       date_trunc('hour', statement_timestamp())
                       + INTERVAL '1 hour' - clock_timestamp()
                   )))::integer
               )
        """
    ).fetchone()
    conn.execute(
        """
        INSERT INTO import_rate_limits (owner_id, window_start, request_count)
        VALUES (%s, %s, 0)
        ON CONFLICT (owner_id, window_start) DO NOTHING
        """,
        (owner_id, window_start),
    )
    row = conn.execute(
        """
        SELECT request_count
        FROM import_rate_limits
        WHERE owner_id = %s AND window_start = %s
        FOR UPDATE
        """,
        (owner_id, window_start),
    ).fetchone()
    if row[0] >= import_limit:
        raise ImportQuotaExceeded(retry_after)
    conn.execute(
        """
        UPDATE import_rate_limits
        SET request_count = request_count + 1
        WHERE owner_id = %s AND window_start = %s
        """,
        (owner_id, window_start),
    )
