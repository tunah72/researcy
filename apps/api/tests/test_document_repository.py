from dataclasses import replace
import hashlib
from uuid import uuid4

import psycopg
from psycopg.pq import TransactionStatus
import pytest

from test_document_provenance import source_lines
from researcy.documents.canonical import (
    CanonicalRecord,
    CanonicalPage,
    CanonicalSection,
    CanonicalBlock,
    CanonicalSpan,
    SourceMapping,
    ChunkRecord,
)
from researcy.documents.normalize import normalize_records
from researcy.documents.repository import write_canonical_batch, write_chunk_batch
from researcy.documents.chunking import chunk_checksum
from researcy.ingestion.jobs import claim_due, seal_profile
from researcy.ingestion.models import (
    DocumentScope,
    ProcessingProfile,
    StageFailure,
    IntegrityFailure,
    LostLease,
    deterministic_id,
)



def expire_lease(conn: psycopg.Connection, job_id) -> None:
    conn.execute(
        """UPDATE ingestion_jobs SET heartbeat_at=clock_timestamp()-interval '100 seconds',
        lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s""",
        (job_id,),
    )
    conn.commit()


def fetch_canonical_rows(conn: psycopg.Connection, version_id):
    pages = conn.execute(
        """SELECT id, page_index, media_box, crop_box, rotation, width, height, transform
           FROM document_pages WHERE document_version_id=%s ORDER BY id""",
        (version_id,),
    ).fetchall()
    sections = conn.execute(
        """SELECT id, ordinal, title, source_reference
           FROM document_sections WHERE document_version_id=%s ORDER BY id""",
        (version_id,),
    ).fetchall()
    blocks = conn.execute(
        """SELECT id, page_id, section_id, ordinal, block_type, box, excluded
           FROM document_blocks WHERE document_version_id=%s ORDER BY id""",
        (version_id,),
    ).fetchall()
    spans = conn.execute(
        """SELECT id, block_id, page_id, ordinal, raw_text, boxes
           FROM document_spans WHERE document_version_id=%s ORDER BY id""",
        (version_id,),
    ).fetchall()
    conn.commit()
    return pages, sections, blocks, spans


def fetch_chunk_rows(conn: psycopg.Connection, version_id):
    chunks = conn.execute(
        """SELECT id, profile_hash, section_id, ordinal, text, checksum
           FROM document_chunks WHERE document_version_id=%s ORDER BY id""",
        (version_id,),
    ).fetchall()
    mappings = conn.execute(
        """SELECT chunk_id, ordinal, chunk_start, chunk_end, span_id, source_start, source_end, transformation, metadata
           FROM chunk_span_mappings WHERE document_version_id=%s ORDER BY chunk_id, ordinal""",
        (version_id,),
    ).fetchall()
    conn.commit()
    return chunks, mappings


def make_canonical_records(scope: DocumentScope, profile: ProcessingProfile, lines=None):
    if lines is None:
        lines = [
            [
                ("1 Introduction", 700, 0, "heading"),
                ("This is the main body paragraph text.", 650, 1, "text"),
            ]
        ]
    return list(normalize_records(source_lines(lines), profile, scope=scope))


def make_single_chunk(scope: DocumentScope, profile: ProcessingProfile, records: list[CanonicalRecord]):
    span = next(r for r in records if r.kind == "span")
    section = next(r for r in records if r.kind == "section" and r.id == span.section_id)
    text = span.normalized_text
    mapping = SourceMapping(
        start=0,
        end=len(text),
        span_id=span.id,
        source_start=0,
        source_end=len(span.raw_text),
        transformation="identity",
        section_id=section.id,
    )
    checksum = chunk_checksum(scope, profile.profile_hash, section.id, text, (mapping,))
    chunk_id = deterministic_id(scope, bytes(profile.profile_hash), "chunk", f"0/{checksum.hex()}")
    return ChunkRecord(
        id=chunk_id,
        scope=scope,
        profile_hash=profile.profile_hash,
        section_id=section.id,
        ordinal=0,
        text=text,
        checksum=checksum,
        source_mappings=(mapping,),
        overlap_characters=0,
    )


# -------------------------------------------------------------------------
# Canonical Batch Tests
# -------------------------------------------------------------------------


def test_canonical_batch_identical_replay(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    write_canonical_batch(conn, lease, records)
    assert conn.info.transaction_status == TransactionStatus.IDLE

    pages_1, sections_1, blocks_1, spans_1 = fetch_canonical_rows(conn, scope.document_version_id)
    assert len(pages_1) > 0 and len(sections_1) > 0 and len(blocks_1) > 0 and len(spans_1) > 0

    # Verify exact set of IDs matches input canonical records
    assert {p[0] for p in pages_1} == {r.id for r in records if r.kind == "page"}
    assert {s[0] for s in sections_1} == {r.id for r in records if r.kind == "section"}
    assert {b[0] for b in blocks_1} == {r.id for r in records if r.kind == "block"}
    assert {sp[0] for sp in spans_1} == {r.id for r in records if r.kind == "span"}

    # Identical replay must succeed and preserve exact row sets without duplicate rows
    write_canonical_batch(conn, lease, records)
    assert conn.info.transaction_status == TransactionStatus.IDLE

    pages_2, sections_2, blocks_2, spans_2 = fetch_canonical_rows(conn, scope.document_version_id)
    assert (pages_1, sections_1, blocks_1, spans_1) == (pages_2, sections_2, blocks_2, spans_2)


def test_canonical_batch_divergent_section_conflict(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    write_canonical_batch(conn, lease, records)

    section = next(r for r in records if r.kind == "section")
    divergent_section = replace(section, title="Divergent Section Title")
    with pytest.raises(IntegrityFailure):
        write_canonical_batch(conn, lease, [divergent_section])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_canonical_batch_divergent_block_conflict(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    write_canonical_batch(conn, lease, records)

    block = next(r for r in records if r.kind == "block")
    divergent_block = replace(block, block_type="caption")
    with pytest.raises(IntegrityFailure):
        write_canonical_batch(conn, lease, [divergent_block])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_canonical_batch_divergent_span_conflict(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    write_canonical_batch(conn, lease, records)

    span = next(r for r in records if r.kind == "span")
    divergent_span = replace(span, raw_text="Completely different raw text")
    with pytest.raises(IntegrityFailure):
        write_canonical_batch(conn, lease, [divergent_span])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_canonical_batch_divergent_page_conflict(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    write_canonical_batch(conn, lease, records)

    page = next(r for r in records if r.kind == "page")
    divergent_source = replace(page.source, rotation=90)
    divergent_page = replace(page, source=divergent_source)
    with pytest.raises(IntegrityFailure):
        write_canonical_batch(conn, lease, [divergent_page])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_canonical_batch_foreign_scope_rejected(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())

    foreign_scope = DocumentScope(uuid4(), uuid4(), uuid4())
    foreign_records = make_canonical_records(foreign_scope, profile)

    with pytest.raises((IntegrityFailure, StageFailure)):
        write_canonical_batch(conn, lease, foreign_records)
    assert conn.info.transaction_status == TransactionStatus.IDLE

    pages_foreign, _, _, _ = fetch_canonical_rows(conn, foreign_scope.document_version_id)
    pages_real, _, _, _ = fetch_canonical_rows(conn, scope.document_version_id)
    assert len(pages_foreign) == 0
    assert len(pages_real) == 0


def test_canonical_batch_stale_lease_rolls_back(queued_job, job_connections):
    scope, job = queued_job
    a, b = job_connections
    lease = claim_due(a, "repo-test-worker")
    profile = seal_profile(a, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    expire_lease(b, job)

    with pytest.raises(LostLease):
        write_canonical_batch(a, lease, records)
    assert a.info.transaction_status == TransactionStatus.IDLE

    pages, sections, blocks, spans = fetch_canonical_rows(a, scope.document_version_id)
    assert (len(pages), len(sections), len(blocks), len(spans)) == (0, 0, 0, 0)


def test_canonical_batch_batch_size_cap(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)

    excess = records + [records[-1]] * (501 - len(records))
    with pytest.raises(ValueError):
        write_canonical_batch(conn, lease, excess)
    assert conn.info.transaction_status == TransactionStatus.IDLE


# -------------------------------------------------------------------------
# Chunk Batch Tests
# -------------------------------------------------------------------------


def test_chunk_batch_identical_replay(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)
    write_canonical_batch(conn, lease, records)

    chunk = make_single_chunk(scope, profile, records)
    write_chunk_batch(conn, lease, [chunk])
    assert conn.info.transaction_status == TransactionStatus.IDLE

    chunks_1, mappings_1 = fetch_chunk_rows(conn, scope.document_version_id)
    assert len(chunks_1) == 1 and len(mappings_1) == 1
    assert chunks_1[0][0] == chunk.id
    assert chunks_1[0][4] == chunk.text
    assert bytes(chunks_1[0][5]) == bytes(chunk.checksum)
    assert mappings_1[0][0] == chunk.id
    assert mappings_1[0][1] == 0
    assert mappings_1[0][2] == 0
    assert mappings_1[0][3] == len(chunk.text)

    # Identical replay succeeds and matches exact stored rows
    write_chunk_batch(conn, lease, [chunk])
    assert conn.info.transaction_status == TransactionStatus.IDLE

    chunks_2, mappings_2 = fetch_chunk_rows(conn, scope.document_version_id)
    assert (chunks_1, mappings_1) == (chunks_2, mappings_2)


def test_chunk_batch_divergent_chunk_conflict(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)
    write_canonical_batch(conn, lease, records)

    chunk = make_single_chunk(scope, profile, records)
    write_chunk_batch(conn, lease, [chunk])

    divergent_text = replace(chunk, text="Divergent chunk text")
    with pytest.raises(IntegrityFailure):
        write_chunk_batch(conn, lease, [divergent_text])
    assert conn.info.transaction_status == TransactionStatus.IDLE

    divergent_checksum = replace(chunk, checksum=bytes([99] * 32))
    with pytest.raises(IntegrityFailure):
        write_chunk_batch(conn, lease, [divergent_checksum])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_chunk_batch_divergent_mapping_conflict(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)
    write_canonical_batch(conn, lease, records)

    chunk = make_single_chunk(scope, profile, records)
    write_chunk_batch(conn, lease, [chunk])

    divergent_mapping = replace(chunk.source_mappings[0], transformation="whitespace")
    divergent_chunk = replace(chunk, source_mappings=(divergent_mapping,))
    with pytest.raises(IntegrityFailure):
        write_chunk_batch(conn, lease, [divergent_chunk])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_chunk_batch_foreign_scope_rejected(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)
    write_canonical_batch(conn, lease, records)

    foreign_scope = DocumentScope(uuid4(), uuid4(), uuid4())
    chunk = make_single_chunk(scope, profile, records)
    foreign_chunk = replace(chunk, scope=foreign_scope)

    with pytest.raises((IntegrityFailure, StageFailure)):
        write_chunk_batch(conn, lease, [foreign_chunk])
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_chunk_batch_stale_lease_rolls_back(queued_job, job_connections):
    scope, job = queued_job
    a, b = job_connections
    lease = claim_due(a, "repo-test-worker")
    profile = seal_profile(a, lease, ProcessingProfile())
    records = make_canonical_records(scope, profile)
    write_canonical_batch(a, lease, records)

    chunk = make_single_chunk(scope, profile, records)
    expire_lease(b, job)

    with pytest.raises(LostLease):
        write_chunk_batch(a, lease, [chunk])
    assert a.info.transaction_status == TransactionStatus.IDLE

    chunks, mappings = fetch_chunk_rows(a, scope.document_version_id)
    assert len(chunks) == 0 and len(mappings) == 0


def test_chunk_batch_supports_over_499_mappings(queued_job, job_connections):
    scope, _ = queued_job
    conn, _ = job_connections
    lease = claim_due(conn, "repo-test-worker")
    profile = seal_profile(conn, lease, ProcessingProfile())

    char_count = 520
    text = "A" * char_count
    records = make_canonical_records(scope, profile, lines=[[(text, 650, 0, "text")]])
    records=[replace(record,source=replace(record.source,width=3000,
        media_box=(0,0,3000,800),crop_box=(0,0,3000,800))) if record.kind=='page' else record for record in records]
    write_canonical_batch(conn, lease, records)

    span = next(r for r in records if r.kind == "span")
    section = next(r for r in records if r.kind == "section" and r.id == span.section_id)

    mappings = tuple(
        SourceMapping(
            start=i,
            end=i + 1,
            span_id=span.id,
            source_start=i,
            source_end=i + 1,
            transformation="identity",
            section_id=section.id,
        )
        for i in range(char_count)
    )
    assert len(mappings) == 520

    checksum = chunk_checksum(scope, profile.profile_hash, section.id, text, mappings)
    chunk_id = deterministic_id(scope, bytes(profile.profile_hash), "chunk", f"0/{checksum.hex()}")
    large_chunk = ChunkRecord(
        id=chunk_id,
        scope=scope,
        profile_hash=profile.profile_hash,
        section_id=section.id,
        ordinal=0,
        text=text,
        checksum=checksum,
        source_mappings=mappings,
        overlap_characters=0,
    )

    write_chunk_batch(conn, lease, [large_chunk])
    assert conn.info.transaction_status == TransactionStatus.IDLE

    chunks_db, mappings_db = fetch_chunk_rows(conn, scope.document_version_id)
    assert len(chunks_db) == 1
    assert len(mappings_db) == 520

    # Verify semantic coverage across all 520 mappings
    cursor = 0
    for idx, m_row in enumerate(mappings_db):
        assert m_row[0] == large_chunk.id
        assert m_row[1] == idx
        assert m_row[2] == cursor
        assert m_row[3] == cursor + 1
        assert m_row[4] == span.id
        assert m_row[5] == cursor
        assert m_row[6] == cursor + 1
        assert m_row[7] == "identity"
        cursor = m_row[3]
    assert cursor == 520

    # Replay of the large chunk also succeeds identically
    write_chunk_batch(conn, lease, [large_chunk])
    assert conn.info.transaction_status == TransactionStatus.IDLE

    chunks_replay, mappings_replay = fetch_chunk_rows(conn, scope.document_version_id)
    assert (chunks_db, mappings_db) == (chunks_replay, mappings_replay)


def test_immutable_replay_rejects_even_small_geometry_changes(queued_job,job_connections):
    scope,_=queued_job;conn,_=job_connections
    lease=claim_due(conn,'exact-replay-test');profile=seal_profile(conn,lease,ProcessingProfile())
    records=make_canonical_records(scope,profile)
    write_canonical_batch(conn,lease,records)
    page=next(record for record in records if record.kind=='page')
    changed=replace(page,source=replace(page.source,width=page.source.width+1e-6))
    with pytest.raises(IntegrityFailure):
        write_canonical_batch(conn,lease,(changed,))


def test_iterable_batch_limit_is_checked_before_consuming_an_unbounded_source(queued_job,job_connections):
    scope,_=queued_job;conn,_=job_connections
    lease=claim_due(conn,'bounded-batch-test');profile=seal_profile(conn,lease,ProcessingProfile())
    page=next(record for record in make_canonical_records(scope,profile) if record.kind=='page')
    def unbounded_source():
        for _ in range(600):
            yield page
        raise AssertionError('The writer consumed beyond its bounded batch input.')
    with pytest.raises(ValueError):
        write_canonical_batch(conn,lease,unbounded_source())
    assert fetch_canonical_rows(conn,scope.document_version_id)==([],[],[],[])


def test_page_from_a_different_profile_cannot_poison_the_sealed_version(queued_job,job_connections):
    scope,_=queued_job;conn,_=job_connections
    lease=claim_due(conn,'profile-identity-test');profile=seal_profile(conn,lease,ProcessingProfile())
    other_profile=replace(profile,chunk_target=1500)
    page=next(record for record in make_canonical_records(scope,other_profile) if record.kind=='page')
    with pytest.raises(IntegrityFailure):
        write_canonical_batch(conn,lease,(page,))
    assert fetch_canonical_rows(conn,scope.document_version_id)==([],[],[],[])
    write_canonical_batch(conn,lease,make_canonical_records(scope,profile))


@pytest.mark.parametrize("invalid",["source-bounds","unknown-transform","missing-span"])
def test_bad_late_mapping_is_rejected_before_any_immutable_prefix(queued_job,job_connections,invalid):
    scope,_=queued_job;conn,_=job_connections
    lease=claim_due(conn,'preflight-map-test');profile=seal_profile(conn,lease,ProcessingProfile())
    text='A'*520
    records=make_canonical_records(scope,profile,lines=[[(text,650,0,'text')]])
    records=[replace(record,source=replace(record.source,width=3000,
        media_box=(0,0,3000,800),crop_box=(0,0,3000,800))) if record.kind=='page' else record for record in records]
    write_canonical_batch(conn,lease,records)
    span=next(record for record in records if record.kind=='span')
    mappings=tuple(SourceMapping(index,index+1,span.id,index,index+1,'identity',span.section_id) for index in range(520))
    base=ChunkRecord(deterministic_id(scope,profile.profile_hash,'chunk','preflight-test'),
        scope,profile.profile_hash,span.section_id,0,text,
        chunk_checksum(scope,profile.profile_hash,span.section_id,text,mappings),mappings,0)
    tail=mappings[-1]
    if invalid=='source-bounds':tail=replace(tail,source_start=520,source_end=521)
    elif invalid=='unknown-transform':tail=replace(tail,transformation='unknown')
    else:tail=replace(tail,span_id=uuid4())
    wrong=mappings[:-1]+(tail,)
    poisoned=replace(base,source_mappings=wrong,
        checksum=chunk_checksum(scope,profile.profile_hash,span.section_id,text,wrong))
    with pytest.raises(IntegrityFailure):
        write_chunk_batch(conn,lease,(poisoned,))
    assert fetch_chunk_rows(conn,scope.document_version_id)==([],[])
    write_chunk_batch(conn,lease,(base,))
    chunks_db,mappings_db=fetch_chunk_rows(conn,scope.document_version_id)
    assert chunks_db[0][0]==base.id and len(mappings_db)==520
