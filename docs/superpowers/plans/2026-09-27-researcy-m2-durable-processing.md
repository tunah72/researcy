# Researcy M2 Durable PDF Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process existing and new accepted immutable PDFs into a recoverable, provenance-preserving, owner-scoped ready index, with honest preparation/failure/retry UI.

**Architecture:** Extend PostgreSQL's existing one-job-per-version ledger with fenced leases and sealed stage manifests. A single Python worker uses the same domain package as FastAPI, a bounded no-network parser sandbox, private MinIO artifacts, native ARM64 Ollama and Qdrant. Only a fenced PostgreSQL publication transaction can advertise ready after exact canonical/vector verification.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, psycopg, Alembic, PyMuPDF, Linux bubblewrap, existing boto3/httpx clients, native ARM64 Ollama, Qdrant, PostgreSQL, private MinIO, Docker Compose, Next.js/React/strict TypeScript, pytest and Vitest/Testing Library. Use existing dependencies where sufficient; Qdrant REST can use httpx without adding a second client SDK. Pin reproducible dependency/image revisions when each runtime is introduced.

**Spec:** [Owner-approved M2 child specification](../specs/2026-09-27-researcy-m2-durable-processing-design.md), approved 2026-09-27, subordinate to [master revision 2.0](../specs/2026-09-18-researcy-system-design.md). [Delivery map](../specs/2026-09-18-researcy-delivery-map.md) is authoritative.

**Plan status:** Approved by owner on 2026-09-28. The owner explicitly permits M2 implementation while the M1 acceptance record is completed separately. M2 is `Planned`; Tasks 1–10 are complete with recorded backend, native-worker, owned-API and production browser preparation/retry evidence; Task 11 is in progress. Final exit-gate completion is pending. This permission does not promote M1 to `Verified`.

## Global constraints

- Stay in `.omp/worktrees/m2-durable-processing`, branch `feat-m2-durable-processing`; base implementation `c39cd17`, design draft commit `c72282b`. Preserve all owner data, root local files and existing worktrees. No push, merge, prune, reset, stash, `down -v`, or restoration of the deleted workflow guideline.
- Before Task 1 implementation: obtain plan approval and close the M1 prerequisite record or record an explicit owner exception. Owner confirmation of two Google accounts is accepted evidence; do not rerun it merely to confirm. An exception permits work, not fabricated `Verified` evidence.
- **Prerequisite decision — 2026-09-28:** “Tôi duyệt plan và cho phép triển khai M2 trong khi bổ sung hồ sơ M1.” This satisfies the execution entry gate by explicit exception; no need to repeat the approval question. All security and milestone verification gates remain binding.
- No Reader, PDF serving, conversations, citations from generated answers, agents, product hybrid search/RRF, discovery/import automation, deletion or new-source-version UI. No Redis/broker, hosted embedding fallback, universal model-provider abstraction or change to `ag/gemini-3.8-flash-low`/shared 9Router.
- Preserve existing source/version/job IDs and import-idempotency outcomes. Retain `0002_m1_source_guards` source and active-version triggers; retry reuses the same version/profile/job.
- One worker, one document, one native model, one embedding request at a time. No SQL transaction across parsing, embedding, object storage or Qdrant I/O. Use `get_conn()` for application connections; composite owner/paper/version constraints and predicates throughout.
- Lease 90 seconds; heartbeat 15 seconds; idle poll 1–5 seconds; five claims per automatic cycle; retry delays 5/15/45/120 seconds; dependency cooldown at most 300 seconds before ending the automatic cycle. Manual retry cap five accepted transitions/owner/hour.
- Stage wall deadlines: validating 60, parsing 60, normalizing 120, chunking 120, embedding 900, indexing/verification 300 seconds; claim deadline 30 minutes. MinIO/Qdrant total request 30 seconds; embedding 60 seconds; SQL statement 5 seconds/lock 1 second. Canonical/vector batches at most 500 records.
- Input 25 MiB/100 pages. Full parser CPU 45 seconds, wall 60 seconds, address space 768 MiB, output 128 MiB, 64 descriptors, 16 child processes; maximum 2,000,000 Unicode characters and 10,000 chunks. Intake sandbox CPU 10 seconds/wall 15 seconds/address space 256 MiB. Fail closed if isolation cannot run.
- Chunk target 1,600 Unicode code points, maximum 2,400, whole-sentence overlap at most 200; no section crossing or silent truncation. Exact unrotated bottom-left PDF-space coordinates, crop/media boxes and rotation; half-open code-point offsets and reversible transformations.
- Embedding `bge-m3:567m`, F16, digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`, 1024 dimensions, cosine, empty prefixes, `truncate: false`, batch four. Record actual native runtime version separately. Model/runtime drift requires requalification.
- Runtime ceilings MiB: worker 1024, Qdrant 512, PostgreSQL 384, MinIO 256, API including intake child 512, web 256. Native model target ≤2 GiB. No OOM/restarts, non-critical host pressure, warm two-paper swap growth ≤512 MiB, recorded status request latency <2 seconds. These approved provisional limits remain subject to real measurement; failure blocks acceptance instead of authorizing silent relaxation.
- API retains safe diagnostic stages/codes/request IDs; UI never renders raw stage/code/provider messages or job/version/request UUIDs. No fake percentages or Reader controls. Preserve warnings, unknown metadata, same-origin helpers, exact Origin and session-bound CSRF.
- RED → GREEN → focused live smoke → inline review → task commit. Run focused checks during implementation; run full affected suites/build after integration. Tests assert behavior, boundaries and races, not wiring or exact incidental wording. Existing obsolete queued-only/wiring tests are removed or replaced with behavioral coverage, never blindly re-pinned.
- Each task adds its observed commands/outcomes/blockers to `docs/superpowers/reports/2026-09-27-researcy-m2-acceptance.md` only after execution; no prefilled PASS. Keep private evidence/fixtures outside Git. Source text and tokens never go in logs.

## 1. Execution order, ownership and file map

One integration owner controls migrations, contracts, Compose and final review. Default execution is serial:

`T1 sandbox → T2 schema → T3 queue → T4 parser → T5 canonical/chunks → T6 embeddings → T7 index/publication → T8 worker → T9 API → T10 UI → T11 acceptance`.

T4 and T3 have separable implementation concerns only after T2 contracts freeze, but the default remains serial on the 8 GB machine. Do not run competing migrations, shared-file edits or resource checks concurrently. If delegated, give one implementer a complete task and keep integration/review with the controller; no task is complete merely because an agent reports success.

### Planned files and responsibility

Paths below are relative to the worktree. New paths are proposed ownership, not existing files or instructions to create empty modules.

| Area | Files | Responsibility |
|---|---|---|
| Sandbox | `apps/api/researcy/documents/{sandbox,parser_child,models}.py`; existing `papers/screening.py`; `apps/api/Dockerfile`; `deploy/parser-seccomp.json` if the default profile cannot support the approved isolation | Shared bounded child boundary and typed interchange, no secrets/network; minimal justified seccomp profile only if required |
| Schema | `apps/api/migrations/versions/0003_m2_processing.py`; `apps/api/tests/test_processing_schema.py` | Ledger/profile/canonical/checkpoint/publication constraints and populated M1 migration |
| Jobs | `apps/api/researcy/ingestion/{models,jobs,retry,worker,stages}.py` | Typed lease, claims, fenced commits, retry transitions and real stage dispatch |
| Documents | `apps/api/researcy/documents/{parser,normalize,chunking,provenance,repository,artifacts}.py` | Deterministic source geometry, transformations, canonical persistence and immutable objects |
| Embedding/index | `apps/api/researcy/retrieval/{embedding,index,repository}.py` | Native HTTP embedding, selected vectors, exact Qdrant verification and owned dense lookup only |
| API | `apps/api/researcy/ingestion/routes.py`; existing `papers/{models,repository,intake,routes}.py`, `main.py`, `config.py`, `db.py` only as needed | Owner-scoped status/retry and persisted projections; keep existing connection/auth boundaries |
| UI | Existing `apps/web/src/lib/api.ts`, `app/library/page.tsx`, `app/library/[paperId]/page.tsx`, `components/{library-list,add-paper}.tsx`; new `components/paper-preparation.tsx` | Central types, quiet status polling, safe retry; shared presentation only, no new transport stack |
| Runtime | `compose.yaml`, `.env.example`, API dependency lockfiles; `apps/api/researcy/ingestion/preflight.py` | Worker/Qdrant with limits, credential-minimal process config, dependency/sandbox/model preflight |
| Evidence | New M2 acceptance report; delivery map; existing root `AGENTS.md` only after implemented boundaries change | Exact task/gate evidence and honest status, no historical Q0 edits |

All new Python packages get `__init__.py` only when actual code uses them. Configuration stays in `researcy.config.Settings`; no parallel environment reader. Runtime role validation must allow the worker to use DB/storage/model settings without Google/session secrets while retaining existing production API checks.

Use `APP_ROLE=api|worker` in Settings, default `api`; reject unknown roles. The FastAPI lifespan explicitly rejects a non-API role, so setting the worker role cannot bypass API production OAuth/session validation. Worker startup explicitly requires `worker`. Both roles require production DB/storage secrets and bounded resource settings; only the API role requires Google/session configuration. Test these composition-root guards before changing production validation.

## 2. Shared contracts to freeze before implementation

### 2.1 Domain types

Define in `ingestion/models.py`, with document-specific output types in `documents/models.py`. Use frozen dataclasses or strict Pydantic models consistently at each boundary; binary hashes are 32-byte SHA-256, JSON representation lower-case hex.

```python
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True, slots=True)
class DocumentScope:
    owner_id: UUID
    paper_id: UUID
    document_version_id: UUID

@dataclass(frozen=True, slots=True)
class Lease:
    scope: DocumentScope
    job_id: UUID
    locked_by: str
    generation: int
    stage: str

@dataclass(frozen=True, slots=True)
class ArtifactRef:
    key: str                 # server-only; never API output
    sha256: bytes
    byte_count: int

@dataclass(frozen=True, slots=True)
class StageManifest:
    stage: str
    profile_hash: bytes
    content_hash: bytes
    record_count: int
    artifacts: tuple[ArtifactRef, ...]
```

`ProcessingProfile` stores schema/parser/adapter/normalization/chunker versions, all semantic chunk parameters, model digest/tag/quantization/dimension/distance/prefixes and vector serialization version. Compute `profile_hash` over canonical JSON with sorted keys, explicit separators and no NaN. Index identity is the same semantic contract hash; runtime patch version/batch size are recorded operational metadata and cannot silently change semantics. UUID5 identities use a fixed project namespace and profile/version plus logical position; owner isolation comes from version/scope, never only source SHA.

Document interchange schema version `1`: ordered `PageRecord` (index, media/crop boxes, rotation, transform), `BlockRecord` (page/order/type/section cues) and `SpanRecord` (raw text, per-code-point boxes/order). `MappingRecord` contains chunk interval, source span/interval or explicit synthetic separator, and transformation `identity | whitespace | ligature | dehyphenation | separator`. Each removed source character remains represented in transformation metadata. `EvidenceLocation` contains scope, source reference, raw quote, zero-based page index, boxes; public acceptance reports use one-based page labels explicitly.

`LostLease`, `StageFailure(code, failure_kind, retryable, retry_after_seconds)` and `IntegrityFailure` are typed internal outcomes; translate to safe codes without including exception/provider text. Use `time.monotonic()` for deadlines and PostgreSQL `clock_timestamp()` for leases. No caller supplies wall-clock lease values.

### 2.2 Module APIs

All connection arguments below use the existing psycopg connection type; each function documents whether it opens a short `conn.transaction()` block. Expensive work happens outside those blocks.

```python
# ingestion/jobs.py
claim_due(conn, worker_id: str) -> Lease | None
heartbeat(conn, lease: Lease) -> bool
seal_profile(conn, lease: Lease, profile: ProcessingProfile) -> ProcessingProfile
commit_stage(conn, lease: Lease, manifest: StageManifest, next_stage: str) -> None
record_failure(conn, lease: Lease, failure: StageFailure) -> None
release_owned(conn, lease: Lease) -> None

# documents/sandbox.py; Path is pathlib.Path
run_pdf_child(mode: str, source: Path, output: Path, limits: SandboxLimits) -> None
# documents/parser.py / normalize.py / chunking.py
parse_pdf(source: Path, output: Path, limits: SandboxLimits) -> ArtifactSummary
normalize_records(records: Iterable[ParserRecord], profile: ProcessingProfile, *, scope: DocumentScope) -> Iterator[CanonicalRecord]
chunk_section(section: CanonicalSection, profile: ProcessingProfile) -> Iterator[ChunkRecord]
# documents/provenance.py
resolve_range(conn, scope: DocumentScope, chunk_id: UUID, start: int, end: int) -> tuple[EvidenceLocation, ...]
# documents/artifacts.py
put_artifact(scope: DocumentScope, profile_hash: bytes, stage: str, source: Path) -> ArtifactRef
verify_artifact(ref: ArtifactRef, destination: Path) -> None
# documents/repository.py
write_canonical_batch(conn, lease: Lease, records: Sequence[CanonicalRecord]) -> None
write_chunk_batch(conn, lease: Lease, records: Sequence[ChunkRecord]) -> None

# retrieval/embedding.py
EmbeddingClient(profile: ProcessingProfile, *, endpoint: str | None = None)
EmbeddingClient.preflight() -> dict[str, object]
EmbeddingClient.embed(texts: Sequence[str]) -> bytes
# retrieval/index.py
ensure_collection(profile: ProcessingProfile) -> None
index_selected(lease: Lease, deadline: float) -> IndexReceipt
verify_index(lease: Lease, deadline: float) -> IndexReceipt
publish_ready(conn, lease: Lease, receipt: IndexReceipt) -> None
# retrieval/repository.py
search_owned(owner_id: UUID, paper_id: UUID, query: str, limit: int = 5) -> list[EvidenceHit]
# ingestion/retry.py
retry_owned(conn, owner_id: UUID, job_id: UUID, revision: int) -> RetryResult
# ingestion/worker.py
run_once(worker_id: str) -> bool
```

`ArtifactSummary` = schema version/counts/hash/bytes; `SandboxLimits` = CPU/wall/address-space/output/FD/PID caps; `RuntimeIdentity` = observed model/runtime metadata; `IndexReceipt` = scope/profile/collection/chunk-set/embedding-manifest/point-set hashes and verified count. `RetryResult` = job snapshot plus `accepted: bool`; accepted selects 202, replay 200. `EvidenceHit` = chunk identity/text/source references plus mapped locations, never Qdrant-supplied text. Iterables are streamed/batched; do not materialize a whole maximum-size document merely for a convenient interface.

### 2.3 HTTP and TypeScript contract

Keep the master job routes. JSON integers for revisions/attempts are nonnegative; counters exposed to JavaScript must stay within safe integer range. Unknown fields in the retry body are rejected after auth/ownership checks.

```typescript
export type ProcessingStage =
  | 'queued' | 'validating' | 'parsing' | 'normalizing'
  | 'chunking' | 'embedding' | 'indexing' | 'ready' | 'failed';
export type JobStatus = 'pending' | 'running' | 'succeeded' | 'failed';
export interface Preparation {
  state: 'waiting' | 'preparing' | 'delayed' | 'failed' | 'complete';
  reason: 'temporary' | 'unsupported' | 'resource_limit' | 'integrity' | null;
  retryable: boolean;
  retry_after_seconds: number;
}
export interface JobResponse {
  job_id: string;
  paper_id: string;
  document_version: string;
  stage: ProcessingStage;
  status: JobStatus;
  failed_stage: ProcessingStage | null;
  error_code: string | null;
  retry_revision: number;
  preparation: Preparation;
  request_id: string;
}
// Paper keeps all existing fields and adds:
// job_id: string; retry_revision: number; preparation: Preparation;
// stage becomes ProcessingStage. IntakeResponse preserves IDs and current stage.
// POST /api/jobs/:jobId/retry body: { retry_revision: number }
```

Pydantic response models mirror this contract; `failed_stage` cannot be `ready`/`failed`/`queued` once a processing stage began. API snapshots derive from one consistent SQL read, not independently loaded stale fields. `preparation.retryable` denotes an allowed manual retry only for terminal retryable failures, not pending automatic recovery. `retry_after_seconds` is a server-computed remaining cooldown; browser uses a local deadline and does not announce each tick. Unknown response state renders safe unavailable status, never complete.

## Task 1: Prove the sandbox and migrate intake onto it

**Dependencies:** plan approval and explicit M1 prerequisite resolution. This is the first execution gate because an unavailable sandbox invalidates later parser assumptions.

**Files:** create `documents/sandbox.py`, `documents/parser_child.py`, `documents/models.py`, `tests/test_parser_sandbox.py`; modify `papers/screening.py`, `config.py`, API `Dockerfile`, `compose.yaml`, `.env.example`, `tests/test_screening.py`, `tests/test_config.py`; create a narrowly scoped seccomp profile only if required and proven. Do not add privileged mode or Docker socket access.

**Interfaces:** implement `SandboxLimits`, `run_pdf_child`; child `screen` mode preserves existing `ScreeningResult` and error codes. `parse` mode is introduced in T4, not as a fake successful stub. Credential-free runtime-role validation reuses Settings and preserves API production validation.

- [x] **RED:** create a PDF fixture in a private temporary directory; run a controlled child under the same launcher that attempts network connection, parent-environment secret access and reading a marker outside its permitted root. Assert each denied operation and valid PDF screening success separately. Add actual output-flood, fork/PID, CPU, memory and wall-bound tests. Example assertion shape:

```python
def test_sandbox_cannot_read_parent_secret(sandbox_probe):
    result = sandbox_probe(secret='not-a-production-secret', operation='read-parent-environment')
    assert result.secret_visible is False
    assert result.exit_class == 'denied'
```

`sandbox_probe` is a test-only fixture implemented in this task using the real launcher and a finite controlled child, not a mocked verdict. Malicious-child tests prove containment; real invalid-PDF tests prove parser policy.

- [x] **Run RED:** `uv run --frozen pytest tests/test_parser_sandbox.py tests/test_screening.py -q` in `apps/api`, in the deployed Linux test image for isolation tests. Record failure caused by missing containment; no passing skip counts as sandbox proof.
- [x] **GREEN:** install bubblewrap in the pinned ARM64 Python image; run API as an unprivileged UID with read-only runtime, private tmp and no-new-privileges. Construct fixed launcher arguments, never a shell string from input:

```python
args = ['bwrap', '--unshare-user', '--unshare-pid', '--unshare-net',
        '--die-with-parent', '--new-session', '--ro-bind', runtime_root, '/runtime',
        '--ro-bind', str(source), '/input/document.pdf', '--tmpfs', '/tmp',
        '--proc', '/proc', '--dev', '/dev', '--clearenv',
        '--setenv', 'PATH', '/runtime/.venv/bin',
        '/runtime/.venv/bin/python', '-I', '/runtime/parser_child.py', mode]
```

Mount only runtime libraries/interpreter needed by the chosen image; do not bind the whole application/environment as `runtime_root`. Child sets hard resource limits before opening input. Parent streams capped output to its own private sink, enforces total deadline and kills/reaps the process group. Sanitize stderr. Namespace denial yields safe unavailable failure, not an unsandboxed fallback. Adapt the mount paths to actual image layout during implementation and prove it, rather than assuming the illustrative paths exist.
- [x] **GREEN check:** run the focused suite; valid, low-text, encrypted, corrupt, repaired, no-text and boundary inputs retain M1 outcomes. Production config still rejects missing OAuth/session settings for API; worker role does not need those secrets.
- [x] **Smoke:** build API image, run actual valid screening and malicious probes under deployed Compose security/cgroup settings; record UID, restrictions and termination. If default seccomp rejects namespace setup, investigate the denied syscall and permit only the measured necessary namespace operations in a checked-in profile; never `seccomp=unconfined` as the deliverable. If safe isolation cannot work, stop for spec revision.
- [x] **Review/commit:** review containment and intact atomic intake; record evidence; commit `feat(security): sandbox PDF screening with bounded execution`.

## Task 2: Forward schema and immutable processing contracts

**Files:** create `0003_m2_processing.py`, `ingestion/models.py`, `tests/test_processing_schema.py`; extend `tests/conftest.py` only with reusable real-DB fixtures; update affected behavioral assertions in `tests/test_schema.py`.

**Interfaces:** domain types in §2; tables `document_processing`, `ingestion_transitions`, `stage_manifests`, `embedding_batches`, `document_pages`, `document_sections`, `document_blocks`, `document_spans`, `document_chunks`, `chunk_span_mappings`, `index_publications`, `processing_retry_rate_limits`; extend existing `ingestion_jobs` fields exactly as spec §4. Use the existing owner/version/job uniqueness, not a new job per stage.

- [x] **RED:** populate a database at Alembic `0002_m1_source_guards` with upload/arXiv versions, warning and idempotency outcome; upgrade to head; assert original/version/job identities survive, due queued row can be claimed, source mutation rejected, profile cannot change after seal, cross-owner/version mapping rejected and ready without publication rejected. Remove the obsolete assertion that all non-queued stages are forbidden; replace it with transition/publication integrity tests.
- [x] **Run RED:** `uv run --frozen pytest tests/test_processing_schema.py tests/test_schema.py -q`.
- [x] **GREEN:** add compatible defaults, backfill no network calls, replace queued-only constraint, add composite FKs/checks and indexes. Required relation skeleton:

```sql
ALTER TABLE ingestion_jobs ADD COLUMN lease_generation bigint NOT NULL DEFAULT 0;
ALTER TABLE ingestion_jobs ADD COLUMN status text NOT NULL DEFAULT 'pending';
ALTER TABLE ingestion_jobs ADD COLUMN run_after timestamptz NOT NULL DEFAULT clock_timestamp();
CREATE INDEX ix_jobs_due ON ingestion_jobs(run_after, created_at, id) WHERE status = 'pending';
CREATE INDEX ix_jobs_expired ON ingestion_jobs(lease_expires_at, created_at, id) WHERE status = 'running';
```

Add all remaining spec fields in the same migration, not a partially runnable ledger. Section parent FKs include owner/version; chunk mappings include owner/version/chunk/span identities. Page bounds/finite numbers and mapping intervals have DB checks plus domain validation. Trigger-guard sealed rows/manifests and profile from update; a ready job must have a matching publication using a deferred constraint trigger so publication and ready can commit together. Preserve original source/active-pointer guards. Immutable manifests refer to content hashes and selected artifacts, not mutable object paths. Embedding batch uniqueness is `(version, profile, batch_ordinal)` with exact selected bytes/hash.
- [x] **GREEN check/smoke:** run the focused suite and migrate a disposable populated DB twice, inspect actual rows, then attempt invalid inserts/updates through psycopg and observe constraint failures. No migration on owner DB yet.
- [x] **Review/commit:** review preservation, FK scope and sealed mutation guards; commit `feat(ingestion): add durable processing and provenance schema`.

## Task 3: Claims, fencing, bounded retries and manual replay semantics

**Files:** create `ingestion/jobs.py`, `ingestion/retry.py`, `tests/test_jobs.py`, `tests/test_processing_retry.py`; extend Settings with validated queue/deadline defaults.

**Interfaces:** §2 `claim_due`, `heartbeat`, `seal_profile`, `commit_stage`, `record_failure`, `release_owned`, `retry_owned`. Real get_conn connections; fixtures `queued_job` and `job_connections` create committed scoped jobs and independent connections to the temporary test database.

- [x] **RED:** two independent claimers cannot own one job; set a test lease expired using SQL in the disposable database, reclaim, then exercise stale heartbeat/checkpoint/release/publication attempts. Preserve the new claimant's state. Test fifth-crash terminalization, failure backoff and old retry revision replay after a completed cycle.

```python
def test_expired_owner_cannot_heartbeat(job_connections, queued_job):
    a, b = job_connections
    old = claim_due(a, 'worker-a')
    b.execute('UPDATE ingestion_jobs SET lease_expires_at = clock_timestamp() - interval \'1 second\' WHERE id = %s', (old.job_id,))
    b.commit()
    new = claim_due(b, 'worker-b')
    assert new.generation > old.generation
    assert heartbeat(a, old) is False
    assert heartbeat(b, new) is True
```

- [x] **Run RED:** `uv run --frozen pytest tests/test_jobs.py tests/test_processing_retry.py -q`.
- [x] **GREEN:** claim under short transaction with `FOR UPDATE SKIP LOCKED`; DB-time predicates in every write. Lock and validate the job before canonical/manifest writes in the same short transaction, with a final lease guard before commit; losing the guard rolls back the whole batch. Never perform child/network work while the row is locked. Expired exhausted rows terminalize atomically instead of being skipped indefinitely.

```sql
SELECT id FROM ingestion_jobs
WHERE (status = 'pending' AND run_after <= clock_timestamp())
   OR (status = 'running' AND lease_expires_at <= clock_timestamp())
ORDER BY CASE WHEN status = 'running' THEN lease_expires_at ELSE run_after END, created_at, id
FOR UPDATE SKIP LOCKED LIMIT 1;
```

Claim increments generation/attempt counters and sets lease. Heartbeat predicate includes owner/job/worker/generation/running/unexpired. `record_failure` maps fixed safe classifications, clears lease, preserves completed manifests, sets bounded run_after or terminal failure; transition events use safe codes. Explicit retry checks replay revision before rate-limit/state rejection: any previously accepted nonnegative revision returns current snapshot without reset; equal current revision may start a valid new cycle; future revision conflicts. Under one transaction lock job and owner quota, increment revision once, reset only cycle attempts and resume earliest incomplete stage. Lifetime attempt exhaustion cannot wrap counters.
- [x] **GREEN check/smoke:** run both suites; a throwaway two-process harness against temporary PostgreSQL claims real jobs, expires/reclaims one and prints only generation/stage/status outcomes. Confirm connection transactions are closed while the harness waits. Remove harness afterward.
- [x] **Review/commit:** review ordering, rollback fencing, stale writer and replay race; commit `feat(ingestion): fence job leases and bound retry cycles`.

## Task 4: Geometry-first production parser and immutable artifacts

**Files:** implement `documents/parser.py`, extend `parser_child.py`/`models.py`; create `documents/artifacts.py`, `tests/test_parser.py`, `tests/test_artifacts.py`; reuse existing `papers/objects.py` owner-original access without changing source keys.

**Interfaces:** `parse_pdf`, `put_artifact`, `verify_artifact`; schema-versioned streamed records. `parser_fixture` creates actual supported/rotated/cropped/one-/two-column PDFs at runtime; public corpus hashes and gold come from existing qualification data, never copied probe implementation.

- [x] **RED:** extract a known text run from a rotated page with nonzero crop origin and assert its inverse-transformed exact character boxes; reject malformed child records and oversize outputs; identical bytes/profile produce identical artifact key/hash; existing key with wrong bytes is rejected, never overwritten.

```python
def test_parser_retains_crop_rotation_geometry(parser_fixture, tmp_path):
    source, expected = parser_fixture(rotation=90, crop_offset=(20, 30))
    output = tmp_path / 'records.jsonl'
    parse_pdf(source, output, SandboxLimits.full_parser())
    records = list(read_parser_records(output))
    page = next(r for r in records if r.kind == 'page' and r.page_index == 0)
    span = next(r for r in records if r.kind == 'span' and r.span_id == expected.span_id)
    assert page.rotation == 90
    assert span.raw_text == expected.raw_text
    assert span.character_boxes == expected.pdf_boxes
```

`SandboxLimits.full_parser()` resolves the approved Settings values. `read_parser_records(path: Path) -> Iterator[ParserRecord]` in `documents/models.py` validates and streams records; only these bounded test fixtures collect them into a list. Compare coordinates with an explicit ≤1e-4 PDF-unit tolerance if float transforms require it, not viewport/fuzzy matching.
- [x] **Run RED:** `uv run --frozen pytest tests/test_parser.py tests/test_artifacts.py -q`.
- [x] **GREEN:** use PyMuPDF raw character extraction, inverse page transformation, deterministic reading order and section cues. No JavaScript, raster OCR or external calls. Parent validates record types/counts/text/geometry. Artifact key is `processing/{owner}/{version}/{profile_hex}/{stage}/{content_hex}`; create immutably, verify streamed readback hash/length. Use supported conditional object creation; if a key already exists verify identical content. Never overwrite a conflicting key. Successful upload is not a checkpoint until the fenced database selection commits.
- [x] **GREEN check/smoke:** parse both frozen public corpus PDFs under the deployed sandbox; record page count, hash, time/memory and compare reading-order gold, without logging source text. Generate separate single-column, figure-heavy, alternative-layout and rotated/cropped fixtures. Missing frozen PDFs are an acquisition prerequisite: retrieve the matching official version and verify hash, not an invented substitute.
- [x] **Review/commit:** review geometry, input/output bounds and immutable write race; commit `feat(documents): parse immutable PDFs into exact source geometry`.

## Task 5: Canonical normalization, section chunks and reversible evidence

**Files:** create `documents/{canonical,normalize,chunking,provenance,repository}.py`, `tests/test_document_provenance.py`, `tests/test_chunking.py`, `tests/test_document_repository.py`. Scoped canonical records live in `canonical.py`, separate from the secret-free parser interchange types in `models.py`. No product citation endpoint.

**Interfaces:** `normalize_records`, `chunk_section`, `write_canonical_batch`, `write_chunk_batch`, `resolve_range`. Canonical writes require T3 lease; `resolve_range` requires explicit scope and chunk offset, not a fuzzy quote search. `normalize_records` receives mandatory keyword `scope` derived by the trusted worker: the secret-free parser cannot provide authoritative owner/version identity. Define `read_parser_records` streaming production iterator in T4 models and consume it here.

- [x] **RED:** exact quote mapping across normalized whitespace, ligature expansion and dehyphenation returns original raw characters and boxes; foreign version fails. Header/footer detection retains source blocks but excludes repeating margin text; body repetitions remain. Oversized paragraphs split without loss or section crossing; overlap never loops or duplicates spans.

```python
def test_chunking_never_crosses_section(two_section_document, profile):
    chunks = [c for section in two_section_document.sections for c in chunk_section(section, profile)]
    for chunk in chunks:
        assert len(chunk.text) <= 2400
        assert {m.section_id for m in chunk.source_mappings} == {chunk.section_id}
    assert reconstruct_nonoverlap_text(chunks) == two_section_document.retrieval_text
```

Fixtures and `reconstruct_nonoverlap_text` are test-local helpers comparing actual interval coverage, not a second chunker. Add negative reconstruction tests for a removed mapping and wrong source box.
- [x] **Run RED:** `uv run --frozen pytest tests/test_chunking.py tests/test_document_provenance.py -q`.
- [x] **GREEN:** implement approved normalization and explicit transformation map; detect repeating margin strings on ≥3 and ≥60% pages within 8% bands, normalize page-number digits only for detection. Section parser recognizes bounded numbered/typographic headings, preserving unknown sections. Chunk at paragraph/sentence/whitespace boundaries with target/max/overlap; require advancing non-overlap cursor. Hash text plus ordered mappings/profile/scope. Insert ≤500 rows per short fenced transaction; identical conflict is replay, divergent conflict fails. Seal full counts/hash only after all rows validate.

```python
for batch in batched(canonical_records, 500):
    with get_conn() as conn:
        write_canonical_batch(conn, lease, batch)
# No source text is published by these partial rows; readers require publication.
```

Use standard `itertools.batched`; no custom batching abstraction. Range resolution includes actual source offset and rejects partial ambiguous expansions rather than inventing exact sub-character boxes.

`chunk_section(section, profile, *, start_ordinal=0)` receives the trusted worker's running global chunk count when processing subsequent sections; replay uses the same deterministic order. `chunk_checksum(scope, profile_hash, section_id, text, mappings)` is reused for persisted provenance validation. Original heading text remains mapped source exactly once; section metadata is never prepended as synthetic evidence. `write_chunk_batch` internally batches chunk headers plus mapping rows into at most 500 actual inserts per fenced transaction, allowing private incomplete rows to resume safely before stage selection.
- [x] **GREEN check/smoke:** write real corpus canonical rows/chunks into isolated PostgreSQL, replay all batches, compare exact ID/checksum/mapping sets, resolve the annotated page-3 quote and render a private diagnostic overlay on the original PDF for human inspection. Overlay is acceptance evidence, not Reader UI; delete generated private artifacts after recording safe measurements.
- [x] **Review/commit:** review Unicode offsets, deletion mapping, section bounds and geometry; commit `feat(documents): persist reversible section-aware chunks`.

## Task 6: Native embedding identity and selected vector manifests

**Files:** create `retrieval/embedding.py`, `tests/test_embedding.py`, extend `documents/artifacts.py` and embedding-manifest repository functions; modify Settings/.env.example and dependency lockfiles only if required.

**Interfaces:** `EmbeddingClient.preflight`, `EmbeddingClient.embed`; `select_embedding_batch(conn, lease, batch_ordinal, artifact, chunk_ids) -> ArtifactRef` in `documents/repository.py` is a fenced first-selection operation, returning the already-selected artifact on replay. `seal_embedding_manifest(conn, lease) -> StageManifest` verifies every ordered chunk exactly once.

`select_embedding_batch` also requires keyword `selected_bytes` and `runtime_identity`: validated little-endian float32 bytes and observed secret-free runtime/model metadata are supplied after immutable artifact upload/readback, never fetched over the network inside the transaction. The production batch is four ordered chunks, with only the final remainder shorter. `EmbeddingClient.embed` returns validated serialized bytes directly; this avoids reserializing model floats before selection. The request timeout is resolved from Settings (maximum 60 seconds); the worker owns the enclosing 15-minute stage deadline.

- [x] **RED:** malformed dimension, cardinality, NaN/Inf/zero vectors and wrong model identity fail; lost lease cannot select a batch; competing recomputations cannot replace selected bytes. Inject HTTP fixtures only for deterministic error boundaries; real runtime proof remains separate.

```python
def test_selected_batch_is_immutable(embedding_batch_fixture):
    first, candidate = embedding_batch_fixture(two_different_valid_vectors=True)
    assert first.selected_hash != candidate.content_hash
    assert candidate.replay_selected_hash == first.selected_hash
    assert candidate.index_input_hash == first.selected_hash
```

Fixture executes actual database selection and private artifact writes, not mock-return equality.
- [x] **Run RED:** `uv run --frozen pytest tests/test_embedding.py -q`.
- [x] **GREEN:** POST native `/api/show` and inspect model metadata plus digest from runtime model inventory; reject mismatches. POST `/api/embed` with exact tag, ordered batch of ≤4 texts and `truncate: false`. Enforce total deadline/response size, finite float32 unit normalization, then write immutable selected artifacts. No model pulling or tag fallback. Store observed runtime identity alongside job/profile diagnostics without secrets.

```python
payload = {'model': profile.model_tag, 'input': list(texts), 'truncate': False}
# Bound the response while streaming; check cardinality and 1024 values before sealing.
```

- [x] **GREEN check/smoke:** preflight actual native ARM64 runtime, inspect model identity/dimension/quantization and one real batch, then embed the isolated golden paper's sealed chunks. Record time, selected batch hashes and native model memory; verify retry reads selected bytes without a second embedding request. Runtime unavailability is a blocker/retry outcome, not a fake vector fallback.
- [x] **Review/commit:** review float serialization and first-selection race; commit `feat(retrieval): seal native embedding batches for replay`.

## Task 7: Qdrant exact-set indexing, publication and owned lookup

**Files:** create `retrieval/{index,repository}.py`, `tests/test_indexing.py`, `tests/test_owned_retrieval.py`; add Qdrant service/volume/health and 512 MiB ceiling to Compose, Settings/.env.example. Pin the qualified Qdrant 1.19.0 ARM64 image by verified manifest digest; do not treat Q0's local image ID as a portable registry digest.

**Interfaces:** `ensure_collection`, `index_selected`, `verify_index`, `publish_ready`, `search_owned`; implement `IndexReceipt`/`EvidenceHit` from §2. Point ID = UUID5(index identity, chunk UUID); payload exactly chunk ID + owner/paper/document_version/section_type.

- [x] **RED:** equal count with wrong point IDs fails; missing/extra/mismatched vectors fail; partial upsert and lost acknowledgement replay creates identical exact set; stale lease cannot publish; Qdrant poisoned foreign chunk ID cannot rehydrate. Foreign/unready lookup must not call embedding or Qdrant.

```python
def test_equal_count_wrong_identity_cannot_publish(index_fixture):
    lease, expected_ids = index_fixture.index_selected()
    index_fixture.replace_one_point_with_wrong_id()
    with pytest.raises(IntegrityFailure):
        verify_index(lease, index_fixture.deadline())
    assert index_fixture.job_stage() != 'ready'
    assert index_fixture.publication_count() == 0
```

`index_fixture` uses real temporary PostgreSQL, private MinIO artifacts and a uniquely named real Qdrant collection; cleanup is limited to its namespace.
- [x] **Run RED:** `uv run --frozen pytest tests/test_indexing.py tests/test_owned_retrieval.py -q`.
- [x] **GREEN:** collection identity includes profile/index hash; verify cosine/1024 and required payload keyword indexes. Upsert only selected manifest float32 values with acknowledged completion. Read back paginated IDs/payload/vectors, exact membership and component tolerance `1e-5`, reject unexpected points, run worker-only selected-vector search, rehydrate scoped canonical records and verify mapping. Final ready transaction rechecks lease and unchanged manifest hashes, inserts publication and updates stage/status atomically. Network work finishes before that transaction.

```python
receipt = verify_index(lease, deadline)
with get_conn() as conn:
    publish_ready(conn, lease, receipt)
```

Owned lookup validates owner/paper/readiness in PostgreSQL before embedding, fixes collection/filter/limit, validates point membership against publication and rehydrates by owner/version. Bound query to 2,400 code points and limit to 1–5 for this internal M2 probe; no HTTP retrieval route. Post-publication mismatch returns safe unavailable evidence, not hidden reindex/source widening.
- [x] **GREEN check/smoke:** index real selected vectors, interrupt between Qdrant acknowledgement and publication in a throwaway harness, replay, verify stable point/chunk sets and actual gold dense query. No live owner data corruption. Record collection/model identity and scope-denial outcomes.
- [x] **Review/commit:** review external stale-write equivalence and publication TOCTOU assumptions; commit `feat(retrieval): verify owner-scoped index before ready publication`.

## Task 8: Wire the real worker and bounded runtime preflight

**Files:** create `ingestion/{worker,stages,preflight}.py`, `tests/test_worker.py`; modify Compose, Settings, `.env.example`, API Dockerfile as required for shared code/runtime. Add no fake stage or production fault-injection endpoint.

**Interfaces:** `run_once`, module entry point `python -m researcy.ingestion.worker`; preflight `python -m researcy.ingestion.preflight --check` returns nonzero with safe dependency names on failure. `stages.py` directly dispatches the six actual stage functions from T4–T7; no generic workflow framework.

- [x] **RED:** accepted M1 row processes without source refetch, worker crash resumes selected checkpoints, lost heartbeat cancels child/new writes, stage timeout cannot heartbeat forever, shutdown preserves recoverability. Use real DB/storage for transition behavior; controlled dependency failures for deterministic timeout classification.

```python
def test_worker_resumes_sealed_chunks(worker_fixture):
    before = worker_fixture.stop_after_chunk_checkpoint()
    worker_fixture.expire_lease_in_test_database()
    assert run_once('replacement') is True
    after = worker_fixture.snapshot()
    assert after.chunk_ids == before.chunk_ids
    assert after.original_hash == before.original_hash
    assert after.stage == 'ready'
```

The fixture drives the real stage functions and may use a deterministic embedding HTTP server for automated lifecycle coverage only; G1/G5 require the native model.
- [x] **Run RED:** `uv run --frozen pytest tests/test_worker.py -q`.
- [x] **GREEN:** one claim loop, separate heartbeat connection/thread, process-unique worker ID, cancellation event and total monotonic stage/claim deadlines. No blocking stage work in the heartbeat thread. On SQL lease loss stop new work, terminate active child and do not record stale errors. On SIGTERM stop claiming and relinquish only owned lease; SIGKILL relies on expiry. Worker validates original bytes from DB-bound MinIO object, never refetches arXiv. Fresh source profile sealed once; null M1 pending_config adopts approved profile, unknown nonempty config fails safely.
- [x] **Wire runtime:** add worker profile `processing` so ordinary `compose up` cannot accidentally start consuming owner queued rows before cutover. Worker shares API build, runs without OAuth/session/generation secrets, default concurrency one, cgroup/PID/tmp limits; dependencies ordered without changing bucket-init behavior. Add native host address and Qdrant internal endpoint. Preflight checks DB migrations, private storage access with an isolated probe key, Qdrant schema, native digest/vector shape and sandbox containment; report no credential values. Keep `/health` liveness independent of downstream outage; no M5 all-in-one demo launcher.
- [x] **GREEN check/smoke:** start real worker only on explicitly selected isolated resources, observe transitions, kill/restart after an actual stage checkpoint and wait real lease expiry. Verify preflight failure is safe and does not consume owner jobs. Then run a healthy actual-stack processing path. API startup must not require embedding availability just to sign in/read Library.
- [x] **Review/commit:** review cancellation, dependency timeouts and credential-minimal role validation; commit `feat(ingestion): run bounded recoverable PDF processing worker`.

## Task 9: Owner-scoped job API and persisted preparation projection

**Files:** create `ingestion/routes.py`, `tests/test_job_routes.py`; modify `main.py`, `papers/{models,repository,intake,routes}.py`, existing `tests/test_library.py` and `tests/test_intake.py` where contracts change.

**Interfaces:** HTTP contract §2.3. Reuse `get_current_user`, `require_csrf`, `APIError` and threadpool conventions from existing routes. Do not introduce auth decorators or another session system.

- [x] **RED:** foreign/random job indistinguishable 404; unauthenticated 401; missing/incorrect CSRF and hostile Origin 403 before body/quota; two concurrent valid retry requests yield one new cycle; delayed replay after another terminal failure does not retry again. Import replay and paper list/detail show persisted current stage/preparation, not queued constants.

```python
def test_retry_replay_after_terminal_state_does_not_start_cycle(job_api_fixture):
    first = job_api_fixture.retry(revision=0)
    assert first.status_code == 202
    job_api_fixture.finish_retry_as_failed()
    replay = job_api_fixture.retry(revision=0)
    assert replay.status_code == 200
    assert replay.json()['retry_revision'] == 1
    assert replay.json()['status'] == 'failed'
```

- [x] **Run RED:** 17 consumer failures demonstrated; isolated Docker test runner used for reproducible PostgreSQL/MinIO/Qdrant checks (exact recorded commands/results in acceptance report).
- [x] **GREEN:** authenticate/authorize before parsing retry JSON; validate exact revision body with forbidden extras. Offload blocking SQL using the established route threadpool pattern. Stable failures `JOB_NOT_RETRYABLE`, `RETRY_REVISION_CONFLICT`, `PROCESSING_RETRY_LIMITED`; 429 carries Retry-After. Serialize only safe job fields. Projection derives pending initial→waiting, pending retry→delayed, running→preparing, terminal failure→failed and published succeeded→complete; inconsistent publication fails safe rather than displaying complete.
- [x] **GREEN check/smoke:** HTTP through actual Next.js same-origin proxy with two explicitly labelled smoke identities exercised GET/retry/403/404/401 and persisted replay. These identities prove M2 ownership mechanisms, not missing real Google M1 acceptance. Owner sessions preserved; disposable HTTP identities/database removed.
- [x] **Review/commit:** owner API and projection reviews passed after demonstrated counter and publication-snapshot regressions were fixed; commit `feat(api): expose owned processing status and safe retry`.

## Task 10: Reader-facing preparation and retry in existing Library

**Files:** modify central `src/lib/api.ts`, Library/list/detail/import files in the file map; create `components/paper-preparation.tsx`, `components/processing-interaction.test.tsx`; update existing interaction tests only where consumer contract changes. Preserve existing visual tokens; no redesign or new status dashboard.

**Interfaces:** §2.3 types in central API file, `fetchJob(jobId: string): Promise<JobResponse>` and `retryJob(jobId: string, revision: number): Promise<JobResponse>` through existing helpers. `PaperPreparation` receives persisted `Preparation`, retry state and callback, not owner IDs or arbitrary backend text.

- [x] **RED:** user retries terminal failure and sees server-backed pending state; countdown disables only relevant retry; stale poll cannot overwrite newer retry/search; refresh failure retains metadata; hidden tab stops requests; 401 clears private state; complete item has no preparation badge or fake Reader. Test accessible behavior, not exact copy.

```tsx
it('keeps confirmed metadata when a status refresh fails', async () => {
  const screenState = await renderProcessingLibrary();
  await screenState.failNextStatusRefresh();
  expect(screen.getByRole('link', { name: 'Attention Is All You Need' })).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent(/check|status/i);
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});
```

`renderProcessingLibrary` is a local test helper rendering the real Library component with the existing fetch-mocking convention; it controls only HTTP responses and timer advancement, not component state or expected outputs.
- [x] **Run RED:** `npm test -- src/components/processing-interaction.test.tsx` demonstrated five initial failures; further recovery regressions and exact results are recorded in the acceptance report.
- [x] **GREEN:** allowlisted status/reason copy, no raw diagnostics; bounded visible single-flight polling, metadata preservation, network backoff, request sequence guards, revision-based per-job retry/cooldowns and polite meaningful status updates.

```tsx
const seq = ++requestSeqRef.current;
const result = await fetchPapers(activeSearch);
if (seq === requestSeqRef.current) setPapers(result.papers);
// Background failures keep papers; initial-load failures retain the existing error surface.
```

Server alone decides preparation success; accepted import says saved/queued, not processing started. Detail explains reading is not yet available even when preparation complete. Retry controls ≥44×44, visible focus, one main, polite meaningful announcements and reduced motion.
- [x] **GREEN check/smoke:** affected frontend suite and production build passed. Real Chromium production surface exercised actual imported/worker waiting, preparing, exhausted dependency failure, cooldown, keyboard retry and native completion; four-width landmark/target/overflow checks passed. Controlled network/visibility/fetch probes are separately labelled; native hidden-tab behavior is not inferred from headless foregrounding.
- [x] **Review/commit:** Library and detail scoped reviews passed after demonstrated recovery regressions were fixed; commit `feat(web): show honest paper preparation and retry states`.

## Task 11: Full-stack six-gate acceptance and delivery evidence

**Files:** complete new M2 acceptance report; update delivery map and root `AGENTS.md` implemented-boundary/setup text only when accurate. Temporary fault/measurement harnesses remain private and are removed after evidence. No standalone fake acceptance app or permanent production fault switch.

**Dependencies:** T1–T10 reviewed/committed; plan and M1 prerequisite decisions recorded; native runtime and private storage available. Announce that starting the worker on owner stack consumes pre-existing queued jobs before cutover. Do not migrate/start that worker without the owner's recorded execution authorization.

### Reproducible commands

From the M2 worktree, use the root environment explicitly without copying or displaying it:

```bash
docker compose --env-file ../../../.env -p researcy config --quiet
docker compose --env-file ../../../.env -p researcy up -d postgres minio minio-init
docker compose --env-file ../../../.env -p researcy --profile web --profile processing build
# Only after cutover authorization; worker remains stopped until migrations/preflight finish.
docker compose --env-file ../../../.env -p researcy up -d api
docker compose --env-file ../../../.env -p researcy exec -T api alembic upgrade head
docker compose --env-file ../../../.env -p researcy exec -T api alembic upgrade head
docker compose --env-file ../../../.env -p researcy --profile processing up -d qdrant
docker compose --env-file ../../../.env -p researcy --profile processing run --rm --no-deps worker python -m researcy.ingestion.preflight --check
docker compose --env-file ../../../.env -p researcy --profile web --profile processing up -d web worker
curl -fsS http://127.0.0.1:8000/health
```

`preflight --check` validates only; it does not claim jobs. On a partially implemented tree these commands are not runnable; they are the contract T8 must deliver, not commands reported as executed now. For tests use existing unique PostgreSQL DB and MinIO bucket fixtures, plus unique Qdrant collections; never override them with owner schema/bucket/collection. Pass secrets through environment without echo.

```bash
# apps/api
uv sync --frozen
uv run --frozen pytest tests -q
# apps/web
npm ci
npm test
npm run build
```

Run Linux containment tests under the exact deployed image/security profile as well as the ordinary host suite; document any platform skips and show separate real security evidence, not a skip-as-pass. Do not run resource acceptance while tests/builds consume memory. Existing arXiv network test remains opt-in; G1 is a separate actual import.

T1 must also make Linux tests reproducible: split the API Dockerfile into a shared runtime base, a `test` target with frozen development dependencies plus `tests/`, and a final production target without test tooling. A test-only `compose.test.yaml` override changes the API build target to `test` and sets maintenance test DB/MinIO/Qdrant endpoints on the existing Compose network; it inherits production UID, seccomp, capabilities, PID and memory restrictions. It defines no additional production service. The override uses `APP_ENV=test`, `APP_ROLE=api`, never bypasses `run_pdf_child`, and is used only with `run --rm --no-deps api`; it must not replace the running production API. Add both files to T1's file scope. Build and run the security-focused target explicitly:

```bash
docker compose --env-file ../../../.env -p researcy -f compose.yaml -f compose.test.yaml build api
docker compose --env-file ../../../.env -p researcy -f compose.yaml -f compose.test.yaml run --rm --no-deps api uv run --frozen pytest tests/test_parser_sandbox.py tests/test_screening.py -q
```

Use a distinct test-image tag in the override so building it cannot retag the production API image. Test database credentials are passed via environment without printing; the existing fixture creates only uniquely named disposable databases. Host parser tests may use pure record/geometry fixtures; host execution must never become an unsandboxed production parsing fallback.

### Gate execution checklist

- [ ] **G1 actual import/stages:** import `1706.03762` through actual API, record 202/IDs/source hash, disconnect client and observe DB transitions validating/parsing/normalizing/chunking/embedding/indexing/ready. Verify original integrity, sealed profile/manifests, exact canonical/vector sets and UI. Include one existing M1 queued fixture upgraded unchanged. Record arXiv failures honestly; no hidden mirror/mock.
- [ ] **G2 crash and stale worker:** use only a test-owned job/worker instance. After checkpoint, `docker compose ... kill -s SIGKILL worker`, record heartbeat/expiry, restart and observe actual reclaim after 90 seconds. In an isolated second run, pause worker A, allow worker B to claim after expiry, resume A and prove stale DB writes rejected and external writes remain selected-content-equivalent. No production 90-second gate replaced with test SQL expiry.
- [ ] **G3 indexing replay:** interrupt after partial real upsert and after acknowledgement before checkpoint. Replay selected manifests; compare exact ordered chunk/mapping/point IDs and normalized vector fingerprints, one publication, stable original identity. Replay same explicit retry revision after a completed/failed cycle and observe no new cycle. Use a private harness/debugger boundary, not committed production sleeps or fault flags.
- [ ] **G4 no premature ready:** in isolated test collection/database exercise dependency outage, missing vector, equal-count wrong ID, extra vector, wrong payload/vector and corrupted mapping/manifest. Real worker/API remain non-ready. Transient outage recovers through supported retry. Integrity cases remain terminal and non-retryable: restore isolated data only for a fresh test scenario or explicit operator repair; do not weaken the contract by making public retry bypass integrity failures. Observe safe failure/retry UI for the appropriate class.
- [ ] **G5 evidence geometry:** verify frozen PDF hash; actual dense top-five query for scaled-dot-product attention retrieves expected page-3 region/column. Rehydrate text from scoped PostgreSQL, resolve exact source offsets/boxes and compare annotated gold. Record one-based page labels and coordinate convention. Foreign/nonexistent owner lookup returns same failure before any embedding/search. Do not claim dense Recall@5 qualification, hybrid search, answer quality or Reader citation acceptance.
- [ ] **G6 security:** actual invalid PDF/resource fixtures plus separately labelled malicious-child containment probes run under the same deployment security profile. Record wall/CPU/memory/output/PID enforcement, UID, no network/secret/host-file escape, child reaping, no partial publication and valid gold/rotated/cropped success. Test both intake and worker entry points; no unsandboxed pre-queue escape remains.
- [ ] **Resource evidence:** warm two public papers sequentially while exercising one bounded intake request; sample service/process peaks, OOM flags, VM allocation, native model allocation, host pressure/swap and API latency. Cold load separately. No service/model restart, pressure non-critical, swap growth ≤512 MiB and all recorded status requests <2 seconds. A failed cap is a blocker, not permission to stop shared 9Router or change model.
- [ ] **Browser evidence:** real persisted queued/preparing/failed/retry/complete states at all four widths, keyboard/focus, one main, target size, no overflow and reduced motion. Keep technical diagnostics in API/DB evidence only. Label controlled network response injections separately from actual dependency failures.
- [ ] **Closeout:** record full affected-suite/build outcomes, exact environment and safe request IDs, expected/observed gate results and blockers. Remove only run-owned fixtures/temporary probes; verify owner records unchanged. Update `Implemented` only after complete code; `Verified` only if all G1–G6 and resource/UI/security checks pass. Commit `test(m2): record real processing acceptance evidence` with docs and legitimate permanent behavioral regressions only. Never push/merge/prune without separate authorization.

## 3. Self-review and acceptance ownership

| Approved spec section | Implementing tasks | Evidence |
|---|---|---|
| §1 scope, prerequisite, Q0 boundary | T1 entry gate; T11 | Owner decisions, immutable Q0 links, no model/agent scope expansion |
| §§2–3 architecture/trust | T1–T9 | Same auth/DB boundary, credential-minimal worker and sandbox |
| §4 migration/immutable canonical model | T2, T4–T5 | Populated M1 migration, composite guards and exact provenance |
| §5 leases/retries/deadlines | T3, T8–T9 | Concurrent/stale claim tests; G2/G3; HTTP revision replay |
| §6 idempotency/cross-store consistency | T4–T8 | Immutable selected artifacts, exact-set replay and fenced publication |
| §7 parser/security | T1, T4–T5 | Actual parser/gold/layout tests and G6 containment |
| §8 normalization/chunk contracts | T5 | Unicode/transformation coverage and gold geometry |
| §9 embeddings/index/publication | T6–T8 | Native identity, no truncation, exact point set, G3–G5 |
| §10 API/UI | T9–T10 | 401/403/404/retry races, actual browser states |
| §11 8 GB resource bounds | T1, T6, T8, T11 | Cgroup/native/host measurements, no assumed fit |
| §§12–13 traceability and status | T11 | G1–G6, safe evidence, affected suites/build and owner approval boundaries |

The plan deliberately resolves two execution ambiguities without changing the spec: use a private prepublication vector probe rather than the ready-only user lookup; recover transient index outages by public retry but keep integrity failures terminal. No requirement is satisfied by a mocked final deliverable. Helper/fixture snippets describe behavior and interface intent; implementation must deliver complete real modules, not retain example-only scaffolds.

**Review gate:** owner approves this plan before implementation begins. Recommended execution is the existing serial task → RED/GREEN → live smoke → review/fix → commit loop with one integration owner. Independent work may be delegated only after shared contracts freeze and without competing resource checks. M1 prerequisite resolution is still required before T1; this plan does not silently waive it.
