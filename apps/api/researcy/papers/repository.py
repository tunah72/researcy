from ..errors import APIError
from .models import MAX_SEARCH_LENGTH


IMPORT_QUOTA_LIMIT = 10  # Per user per fixed one-hour window.


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
       v.id, v.source_version, v.screening_warning
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
)


def _paper(row) -> dict:
    return dict(zip(_PAPER_FIELDS, row, strict=True))


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


def take_import_slot(conn, owner_id) -> None:
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
    if row[0] >= IMPORT_QUOTA_LIMIT:
        raise ImportQuotaExceeded(retry_after)
    conn.execute(
        """
        UPDATE import_rate_limits
        SET request_count = request_count + 1
        WHERE owner_id = %s AND window_start = %s
        """,
        (owner_id, window_start),
    )
