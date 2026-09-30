import itertools
from typing import Iterable, Sequence

import psycopg
from psycopg.types.json import Jsonb

from researcy.ingestion.jobs import fenced_transaction, short_transaction, require_owned
from researcy.ingestion.models import IntegrityFailure, Lease, deterministic_id
from .canonical import (
    CanonicalBlock,
    CanonicalPage,
    CanonicalRecord,
    CanonicalSection,
    CanonicalSpan,
    ChunkRecord,
)
from .chunking import chunk_checksum
from .provenance import validate_source_mapping




def _numbers_match(actual, expected) -> bool:
    if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
        return False
    return tuple(actual)==tuple(expected)


def _span_boxes_match(actual, expected) -> bool:
    if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
        return False
    return all(_numbers_match(a, e) for a, e in zip(actual, expected))


def _insert(conn,statement,parameters):
    try:
        return conn.execute(statement,parameters)
    except psycopg.IntegrityError:
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE') from None


def write_canonical_batch(
    conn: psycopg.Connection,
    lease: Lease,
    records: Sequence[CanonicalRecord] | Iterable[CanonicalRecord],
) -> None:
    """Persist up to 500 canonical records in a single fenced transaction."""
    if not isinstance(records, list):
        records = list(itertools.islice(records,501))
    if not records:
        return
    if len(records) > 500:
        raise ValueError("canonical batch exceeds 500 records")

    for record in records:
        if record.scope != lease.scope:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    pages: list[CanonicalPage] = [r for r in records if r.kind == "page"]
    sections: list[CanonicalSection] = [r for r in records if r.kind == "section"]
    blocks: list[CanonicalBlock] = [r for r in records if r.kind == "block"]
    spans: list[CanonicalSpan] = [r for r in records if r.kind == "span"]

    with fenced_transaction(conn, lease):
        row = conn.execute(
            """SELECT profile_hash FROM document_processing
               WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s""",
            (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id),
        ).fetchone()
        if row is None:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        expected_profile_hash = bytes(row[0])
        for record in records:
            position=record.source.page_index if record.kind=='page' else record.ordinal
            if record.id!=deterministic_id(lease.scope,expected_profile_hash,record.kind,str(position)):
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')

        for sec in sections:
            if bytes(sec.profile_hash) != expected_profile_hash:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        for span in spans:
            if bytes(span.profile_hash) != expected_profile_hash:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        # 1. Pages
        for page in pages:
            src = page.source
            res = _insert(conn,
                """INSERT INTO document_pages
                   (id, owner_id, paper_id, document_version_id, page_index, media_box, crop_box, rotation, width, height, transform)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING
                   RETURNING id""",
                (
                    page.id,
                    lease.scope.owner_id,
                    lease.scope.paper_id,
                    lease.scope.document_version_id,
                    src.page_index,
                    Jsonb(list(src.media_box)),
                    Jsonb(list(src.crop_box)),
                    src.rotation,
                    float(src.width),
                    float(src.height),
                    Jsonb(list(src.transform)),
                ),
            ).fetchone()
            if res is None:
                existing = conn.execute(
                    """SELECT owner_id, paper_id, document_version_id, page_index, media_box, crop_box, rotation, width, height, transform
                       FROM document_pages WHERE id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                    (page.id,lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id),
                ).fetchone()
                if existing is None:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                (
                    ex_owner,
                    ex_paper,
                    ex_version,
                    ex_page_idx,
                    ex_media,
                    ex_crop,
                    ex_rot,
                    ex_width,
                    ex_height,
                    ex_transform,
                ) = existing
                if (
                    ex_owner != lease.scope.owner_id
                    or ex_paper != lease.scope.paper_id
                    or ex_version != lease.scope.document_version_id
                    or ex_page_idx != src.page_index
                    or not _numbers_match(ex_media, src.media_box)
                    or not _numbers_match(ex_crop, src.crop_box)
                    or ex_rot != src.rotation
                    or ex_width != src.width
                    or ex_height != src.height
                    or not _numbers_match(ex_transform, src.transform)
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        # 2. Sections
        for sec in sections:
            src_ref = list(sec.source_reference) if sec.source_reference is not None else None
            res = _insert(conn,
                """INSERT INTO document_sections
                   (id, owner_id, paper_id, document_version_id, parent_id, ordinal, title, source_reference)
                   VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING
                   RETURNING id""",
                (
                    sec.id,
                    lease.scope.owner_id,
                    lease.scope.paper_id,
                    lease.scope.document_version_id,
                    sec.ordinal,
                    sec.title,
                    Jsonb(src_ref) if src_ref is not None else None,
                ),
            ).fetchone()
            if res is None:
                existing = conn.execute(
                    """SELECT owner_id, paper_id, document_version_id, parent_id, ordinal, title, source_reference
                       FROM document_sections WHERE id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                    (sec.id,lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id),
                ).fetchone()
                if existing is None:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                ex_owner, ex_paper, ex_version, ex_parent, ex_ord, ex_title, ex_ref = existing
                if (
                    ex_owner != lease.scope.owner_id
                    or ex_paper != lease.scope.paper_id
                    or ex_version != lease.scope.document_version_id
                    or ex_parent is not None
                    or ex_ord != sec.ordinal
                    or ex_title != sec.title
                    or ex_ref != src_ref
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        # 3. Blocks
        for blk in blocks:
            res = _insert(conn,
                """INSERT INTO document_blocks
                   (id, owner_id, paper_id, document_version_id, page_id, section_id, ordinal, block_type, box, excluded)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING
                   RETURNING id""",
                (
                    blk.id,
                    lease.scope.owner_id,
                    lease.scope.paper_id,
                    lease.scope.document_version_id,
                    blk.page_id,
                    blk.section_id,
                    blk.ordinal,
                    blk.block_type,
                    Jsonb(list(blk.box)),
                    blk.excluded,
                ),
            ).fetchone()
            if res is None:
                existing = conn.execute(
                    """SELECT owner_id, paper_id, document_version_id, page_id, section_id, ordinal, block_type, box, excluded
                       FROM document_blocks WHERE id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                    (blk.id,lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id),
                ).fetchone()
                if existing is None:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                ex_owner, ex_paper, ex_version, ex_page, ex_sec, ex_ord, ex_type, ex_box, ex_excl = existing
                if (
                    ex_owner != lease.scope.owner_id
                    or ex_paper != lease.scope.paper_id
                    or ex_version != lease.scope.document_version_id
                    or ex_page != blk.page_id
                    or ex_sec != blk.section_id
                    or ex_ord != blk.ordinal
                    or ex_type != blk.block_type
                    or not _numbers_match(ex_box, blk.box)
                    or ex_excl != blk.excluded
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        # 4. Spans
        for span in spans:
            boxes = [list(box) for box in span.character_boxes]
            res = _insert(conn,
                """INSERT INTO document_spans
                   (id, owner_id, paper_id, document_version_id, block_id, page_id, ordinal, raw_text, boxes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING
                   RETURNING id""",
                (
                    span.id,
                    lease.scope.owner_id,
                    lease.scope.paper_id,
                    lease.scope.document_version_id,
                    span.block_id,
                    span.page_id,
                    span.ordinal,
                    span.raw_text,
                    Jsonb(boxes),
                ),
            ).fetchone()
            if res is None:
                existing = conn.execute(
                    """SELECT owner_id, paper_id, document_version_id, block_id, page_id, ordinal, raw_text, boxes
                       FROM document_spans WHERE id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                    (span.id,lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id),
                ).fetchone()
                if existing is None:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                ex_owner, ex_paper, ex_version, ex_block, ex_page, ex_ord, ex_raw, ex_boxes = existing
                if (
                    ex_owner != lease.scope.owner_id
                    or ex_paper != lease.scope.paper_id
                    or ex_version != lease.scope.document_version_id
                    or ex_block != span.block_id
                    or ex_page != span.page_id
                    or ex_ord != span.ordinal
                    or ex_raw != span.raw_text
                    or not _span_boxes_match(ex_boxes, boxes)
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")


def _flatten_chunk_items(chunks: list[ChunkRecord]):
    for chunk in chunks:
        yield ("chunk", chunk, None, None)
        for ordinal, mapping in enumerate(chunk.source_mappings):
            yield ("mapping", chunk, ordinal, mapping)


def write_chunk_batch(
    conn: psycopg.Connection,
    lease: Lease,
    chunks: Sequence[ChunkRecord] | Iterable[ChunkRecord],
) -> None:
    """Persist chunks and mappings in batches of <=500 actual rows per fenced transaction."""
    if not isinstance(chunks, list):
        chunks = list(itertools.islice(chunks,501))
    if not chunks:
        return
    if len(chunks) > 500:
        raise ValueError("chunk batch exceeds 500 records")


    # Pre-validate chunk identity, bounds, coverage and checksum outside SQL tx
    for chunk in chunks:
        if chunk.scope != lease.scope:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if not (0 < len(chunk.text) <= 2400):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if len(chunk.source_mappings) > 4801:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        cursor = 0
        for m in chunk.source_mappings:
            if m.start != cursor or m.end < m.start or m.section_id != chunk.section_id:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if m.transformation == "separator":
                if (
                    m.span_id is not None
                    or m.source_start is not None
                    or m.source_end is not None
                    or m.end <= m.start
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            else:
                if (
                    m.span_id is None
                    or m.source_start is None
                    or m.source_end is None
                    or m.source_end <= m.source_start
                    or m.source_start < 0
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                if m.transformation == "identity" and (m.end - m.start) != (m.source_end - m.source_start):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            cursor = m.end
        if cursor != len(chunk.text):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        expected_checksum = chunk_checksum(
            chunk.scope,
            chunk.profile_hash,
            chunk.section_id,
            chunk.text,
            chunk.source_mappings,
        )
        if bytes(chunk.checksum) != expected_checksum:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        ids=list({mapping.span_id for mapping in chunk.source_mappings if mapping.span_id is not None})
        sources={}
        for id_batch in itertools.batched(ids,500):
            with short_transaction(conn):
                require_owned(conn,lease)
                rows=conn.execute("""SELECT s.id,s.raw_text,b.section_id,b.excluded FROM document_spans s
                    JOIN document_blocks b ON b.id=s.block_id AND b.owner_id=s.owner_id
                        AND b.document_version_id=s.document_version_id
                    WHERE s.owner_id=%s AND s.paper_id=%s AND s.document_version_id=%s AND s.id=ANY(%s)""",
                    (lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id,list(id_batch))).fetchall()
            sources.update((row[0],row[1:]) for row in rows)
        for mapping in chunk.source_mappings:
            if mapping.transformation=='separator':
                validate_source_mapping(mapping,chunk.text,None)
                continue
            source=sources.get(mapping.span_id)
            if source is None or source[1]!=chunk.section_id or source[2]:
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            validate_source_mapping(mapping,chunk.text,source[0])

    # Insert chunk headers and mappings in batches of <= 500 actual rows
    for batch_items in itertools.batched(_flatten_chunk_items(chunks), 500):
        with fenced_transaction(conn, lease):
            row = conn.execute(
                """SELECT profile_hash FROM document_processing
                   WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id),
            ).fetchone()
            if row is None:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            expected_profile_hash = bytes(row[0])

            for kind, chunk, mapping_ordinal, mapping in batch_items:
                if bytes(chunk.profile_hash) != expected_profile_hash:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

                if kind == "chunk":
                    res = _insert(conn,
                        """INSERT INTO document_chunks
                           (id, owner_id, paper_id, document_version_id, profile_hash, section_id, ordinal, text, checksum)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (id) DO NOTHING
                           RETURNING id""",
                        (
                            chunk.id,
                            lease.scope.owner_id,
                            lease.scope.paper_id,
                            lease.scope.document_version_id,
                            chunk.profile_hash,
                            chunk.section_id,
                            chunk.ordinal,
                            chunk.text,
                            chunk.checksum,
                        ),
                    ).fetchone()
                    if res is None:
                        existing = conn.execute(
                            """SELECT owner_id, paper_id, document_version_id, profile_hash, section_id, ordinal, text, checksum
                               FROM document_chunks WHERE id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                            (chunk.id,lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id),
                        ).fetchone()
                        if existing is None:
                            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                        ex_owner, ex_paper, ex_version, ex_prof, ex_sec, ex_ord, ex_text, ex_chk = existing
                        if (
                            ex_owner != lease.scope.owner_id
                            or ex_paper != lease.scope.paper_id
                            or ex_version != lease.scope.document_version_id
                            or bytes(ex_prof) != bytes(chunk.profile_hash)
                            or ex_sec != chunk.section_id
                            or ex_ord != chunk.ordinal
                            or ex_text != chunk.text
                            or bytes(ex_chk) != bytes(chunk.checksum)
                        ):
                            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

                elif kind == "mapping":
                    res = _insert(conn,
                        """INSERT INTO chunk_span_mappings
                           (owner_id, paper_id, document_version_id, chunk_id, ordinal, chunk_start, chunk_end, span_id, source_start, source_end, transformation, metadata)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
                           ON CONFLICT (chunk_id, ordinal) DO NOTHING
                           RETURNING chunk_id, ordinal""",
                        (
                            lease.scope.owner_id,
                            lease.scope.paper_id,
                            lease.scope.document_version_id,
                            chunk.id,
                            mapping_ordinal,
                            mapping.start,
                            mapping.end,
                            mapping.span_id,
                            mapping.source_start,
                            mapping.source_end,
                            mapping.transformation,
                        ),
                    ).fetchone()
                    if res is None:
                        existing = conn.execute(
                            """SELECT owner_id, paper_id, document_version_id, chunk_start, chunk_end, span_id, source_start, source_end, transformation, metadata
                               FROM chunk_span_mappings WHERE chunk_id=%s AND ordinal=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                            (chunk.id,mapping_ordinal,lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id),
                        ).fetchone()
                        if existing is None:
                            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                        (
                            ex_owner,
                            ex_paper,
                            ex_version,
                            ex_start,
                            ex_end,
                            ex_span,
                            ex_src_start,
                            ex_src_end,
                            ex_trans,
                            ex_meta,
                        ) = existing
                        if (
                            ex_owner != lease.scope.owner_id
                            or ex_paper != lease.scope.paper_id
                            or ex_version != lease.scope.document_version_id
                            or ex_start != mapping.start
                            or ex_end != mapping.end
                            or ex_span != mapping.span_id
                            or ex_src_start != mapping.source_start
                            or ex_src_end != mapping.source_end
                            or ex_trans != mapping.transformation
                            or ex_meta != {}
                        ):
                            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
