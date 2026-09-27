# Researcy M2 — Durable PDF Processing and Owner-Scoped Index

- **Status:** Approved child specification — owner-approved on 2026-09-27; design authority, not implementation evidence.
- **Date:** 2026-09-27.
- **Authority:** [Master revision 2.0](./2026-09-18-researcy-system-design.md), including the approved reader-facing presentation amendment; [delivery map](./2026-09-18-researcy-delivery-map.md) controls status.
- **Baseline:** `c39cd1725ceed662612c1fb7c7d76ea83747818b`; branch `feat-m2-durable-processing`, worktree `.omp/worktrees/m2-durable-processing`.
- **Approval sequence:** specification approved → write and approve a separate implementation plan → implement → collect all exit-gate evidence. M2 is `Designed`; plan approval and the M1 prerequisite decision remain separate.

## 1. Outcome, scope and prerequisites

An accepted, owner-scoped immutable PDF is processed after the import request ends. PostgreSQL drives bounded, recoverable execution through `validating → parsing → normalizing → chunking → embedding → indexing → ready`. Failures retain the original and an actionable, safe recovery state. A published index retrieves evidence whose text maps back to the original PDF's exact geometry.

M2 owns JOB-01, SEC-01, DOC-01, PARSE-01, EMB-01 and IDX-01. It extends existing Library/detail views only for preparation, failure and explicit retry. It does not implement Reader/PDF delivery, conversations, citations persisted from model answers, ReaderAgent, DiscoveryAgent, ResearchAgent, product hybrid retrieval/RRF, automatic discovery/import, deletion, new-source-version import, or model-driven processing. The gold retrieval probe is an acceptance use of the internal owner-scoped dense index, not a new product search endpoint. M3 retains RET-01 and CIT-01.

### 1.1 Observed baseline versus proposals

| Evidence | Observed fact / consequence |
|---|---|
| `git fetch origin`, `git status --short --branch`, `git worktree list` | Main and both M1 remediation refs remain at the baseline; root `next-env.d.ts` and untracked local context files are unrelated and preserved. M1 worktrees remain intact. |
| `docker compose ps -a` | Researcy services are stopped. This is not a fresh database/object inventory. No services were started for design research. |
| `docker compose config --quiet` in the new worktree | Checked-in Compose syntax resolves; this does not validate OAuth secrets or service reachability. |
| `docker info --format '{{.Architecture}} {{.MemTotal}}'` | Docker reports `aarch64`, 4,108,828,672 bytes of VM memory. Full-stack runtime fit remains unmeasured. |
| M1 migration `0001_m1.py`, job schema | One job per document version; only `queued` is allowed. No leases, heartbeat, attempts, scheduler or checkpoints. |
| M1 child specification §§3–6 and acceptance report | Original PDF identity, private storage and atomic accepted paper/version/job/idempotency result are established. Processing configuration is pending, not a fabricated parser identity. |
| Owner handoff | Real two-Google-account testing and `2603.09689` import passed; prior backend 193 passed/1 skipped, frontend 32 passed and production build passed. These are accepted reports, not rerun or relabelled as observations from this design session. |

The [M1 handoff addendum](../reports/2026-09-24-researcy-m1-acceptance.md#m2-handoff-evidence-addendum--2026-09-27) records the new owner evidence. M1's detailed four-gate record remains incomplete; technical status is not promoted by inference. Before M2 implementation, close that record using retained owner results or explicitly approve an amendment/exception to the prerequisite. Specification work is not blocked by this documentation gap. An exception permits work; it does not fabricate a `Verified` result.

Do not restore the deleted Git-worktree guideline, alter owner originals/sessions, copy secrets into the worktree, reset/stash unrelated files, remove existing worktrees, or stop/reconfigure shared 9Router. No push, merge or prune is authorized. Later stack commands must explicitly select the intended Compose project and root environment file without printing it; do not accidentally create a second owner stack under a worktree-derived project name.

### 1.2 Qualification inherited, not generalized

- [Q0 parser report](../reports/2026-09-20-researcy-q0-technical-qualification-report.md): PyMuPDF geometry-first selected; 8/8 expected-page/geometry cases, 12/12 reading-order relations; parser artifact peak memory 271,319,040 bytes. This is two-paper qualification, not arbitrary-layout support.
- [Q0.1 report](../reports/2026-09-22-researcy-q0-1-hybrid-qualification-report.md): fused Recall@5 6/8 with BGE-M3 + BM25 + RRF. Dense-only did not pass that quality threshold. M2 must not claim it did.
- [Q0.1 machine-readable identity](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/hybrid-retrieval.json): PyMuPDF 1.28.2, bottom-left coordinates; `bge-m3:567m`, F16, 1024 dimensions, cosine, empty document/query prefixes, `truncate: false`; native ARM64 Ollama 0.18.2. Model digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
- Q0.1's 176,308,224-byte memory measurement covers only probe-process RSS sampled at batch boundaries. It excludes total model/VM/browser memory. Historical prose and JSON measurements are not silently reconciled or rewritten.
- Qualification probe code is not the production adapter. The original gold corpus and reports stay read-only. Production parser/chunker changes must be measured against the same gold plus additional one-column, figure-heavy and alternative-layout fixtures.

## 2. Decisions and alternatives

| Decision | Recommended choice | Alternative and cost |
|---|---|---|
| Queue | Extend the existing job row; one worker; explicit stage checkpoints and leases | Separate job per stage increases scheduling/state coordination without a current throughput need; Redis/broker is outside the approved architecture |
| Recovery | Reuse sealed immutable outputs; fence every ledger mutation | Restart all stages is simpler initially but repeats expensive embedding and makes partial failures harder to explain |
| External write fencing | Select immutable manifests in PostgreSQL before Qdrant writes; all retries send identical sealed vector bytes | A pre-write lease check alone cannot prevent a paused stale worker writing after lease expiry; distributed locks do not make PostgreSQL/Qdrant atomic |
| Parser isolation | Short-lived non-root, no-network sandbox inside the existing worker container | Ordinary subprocess limits alone do not protect credentials/network/filesystem; privileged container or Docker socket access is rejected |
| Versions | Seal a processing profile once for an unprocessed source version; use the same profile for retries | Mutating parser/model configuration in place corrupts provenance. User-facing reprocessing/new editions are not needed for this milestone |
| UI | Reuse Library/detail; coarse persisted preparation state, truthful warnings and explicit retry | Exposing the job ledger, technical stages or fake percentages conflicts with the presentation amendment |

Approval accepts these choices and the provisional operating caps below. Caps are design limits, not claimed measurements. If the sandbox or resource envelope cannot pass on the real machine, stop and revise the design with owner approval; do not weaken isolation or switch models silently.

## 3. Components and trust boundaries

- **API:** existing opaque-session/CSRF/Origin authority; owner-scoped paper/job reads and retry transitions. It does not parse documents synchronously for M2 or load model weights.
- **Worker:** same Python domain package, separate process, one claimed job at a time. It reads database-bound owner/paper/version and verified private original; performs local stages; owns leases and bounded dependency calls. No OAuth credentials or generation credentials are needed in its environment.
- **Parser child:** gets only a bounded, read-only input PDF and a private output channel. No DB/MinIO/Ollama credentials, inherited connection handles, network, owner-supplied paths or host mounts. Its output remains untrusted until parent schema/geometry/size checks pass.
- **PostgreSQL:** sole authority for identity, processing profile, canonical text/geometry, manifests, checkpoints, job state and publication.
- **MinIO:** existing immutable originals and private content-addressed parser/embedding artifacts. No public URLs, filename-derived keys or credentials reach the browser. Artifacts are never a replacement for canonical PostgreSQL records.
- **Native Ollama:** one model instance reached over the configured internal host address. No model download, provider fallback or generation request from a document job.
- **Qdrant:** vectors, chunk ID and the master's minimal owner/paper/document-version/section-type payload. No source text, quotes, filenames, email, object keys, model prompts or job errors. Collection identity carries embedding/index version.

All private relational joins include `owner_id` and the relevant paper/version identity. Composite foreign keys prevent cross-owner and cross-version mappings. Internal trusted workers still use the composite identity, not ID-only writes. Browser/model inputs never provide authoritative filters.

## 4. Schema and migration contract

Use forward Alembic migrations, not edits to historical migrations or ad-hoc production SQL. Preserve all existing UUIDs, owner relations, source hashes/keys, warnings, active versions and import-idempotency outcomes.

### 4.1 Extend ingestion jobs

Keep the existing unique job per document version and the `stage` field. Replace its queued-only check with the master stages plus `failed`. Add:

- `status`: `pending | running | succeeded | failed`; separates scheduling from document stage.
- `locked_by`, monotonically increasing `lease_generation`, `lease_expires_at`, `heartbeat_at`.
- `attempts` (lifetime claims, including crashed claims), `cycle_attempts` (claims in the current bounded automatic retry cycle), `retry_revision` (increments once per accepted explicit retry).
- `run_after`, `updated_at`, `completed_at`, `failed_stage`, safe `error_code`, `failure_kind` and `retryable`.
- Reference to the sealed processing profile and selected checkpoint manifests.

Checks enforce: lease fields exist only for running jobs; `ready` pairs only with succeeded; terminal failure has no active lease and identifies its failed stage; counters are nonnegative. Index pending due time and running lease expiry separately. A small append-only job-transition table records stage/status, generation, timestamp, safe failure code and attempt; never store heartbeat spam, document text or provider responses. This makes fast stages observable without polling luck.

### 4.2 Processing identity and canonical relations

A one-to-one processing record for a document version stores a write-once profile: original SHA-256, parser package/adapter version, normalization/chunker version and configuration checksum, embedding model/digest/quantization/runtime contract, dimension, distance and index version. Resolve the M1 `pending_config` at first claim; seal it atomically before artifact work. An unknown nonempty legacy configuration fails safely for operator reconciliation, never gets silently ignored. Once sealed, source identity and processing identity are immutable. Enforce write-once source fields/profile at the database boundary as well as in application code.

The existing `0002_m1_source_guards.py` already rejects changes to source facts and `papers.active_version_id`, while deliberately allowing `pending_config` updates. Retain those source/pointer guards for M2; no active-version switch is needed by same-version processing/retry. Add write-once protection to the selected profile and prevent changing pending configuration after sealing, rather than weakening the original-source trigger. A future version-replacement feature requires its own explicit pointer-transition design.

Canonical entities:

| Entity | Required identity and content |
|---|---|
| Pages | Owner/paper/version, zero-based page index, MediaBox/CropBox, dimensions, rotation and PDF coordinate transform |
| Sections | Same version, deterministic ID, parent section, ordered title/source references; unknown heading remains unknown |
| Blocks | Page, section, ordered position, type and exact source geometry; retained excluded headers/footers are marked, not erased |
| Spans | Block, raw Unicode text, reading order, per-character source offsets/boxes; exact source identity |
| Chunks | Version/profile/section, deterministic ID/ordinal, normalized retrieval text, checksum and section metadata |
| Chunk-span mappings | Chunk code-point interval, span raw interval, transformation kind; ordered many-to-many mapping, including explicit synthetic whitespace |
| Stage manifests | Unique version/profile/stage, schema version, ordered artifact/checksum/count manifest, completion timestamp |
| Index publication | Version/profile/index identity, chunk-set hash, selected embedding manifest, Qdrant collection, verified point count/set hash, publication timestamp |

Use composite uniqueness/FKs through page/block/span/chunk/mapping relationships so a valid UUID from a different version cannot be attached. A chunk must refer to a section in that same version; mappings cannot jump to another owner's span. Large canonical writes use bounded batches with replay-safe uniqueness; a stage is invisible as completed until its final manifest is sealed. Conflicting content for the same deterministic ID fails, rather than overwriting silently.

### 4.3 Existing queued M1 jobs

Backfill existing jobs to pending/queued, counters and revision zero, no lease/profile/publication, `run_after` due. Preserve their job UUIDs so old idempotency replay continues to resolve. Migration does no parsing, downloads or network calls. Starting the approved worker processes existing queued jobs as well as new ones; explicitly announce that cutover before starting against owner data. Invalid/missing originals fail that job without replacing its source or deleting its paper.

Migration verification uses a populated M1 test database with accepted upload/arXiv rows, warnings and replay outcomes; migrate twice, confirm identities and bytes unchanged, then process those same rows. Rollback by dropping production tables/data is not an operational recovery mechanism. Do not start an old queued-only application against the new worker lifecycle.

## 5. Durable execution, lease fencing and retries

### 5.1 Claim and heartbeat

Default polling backs off from 1 to 5 seconds when idle. Claim one due pending row or expired running row ordered by due/expiry time then creation/ID, using `FOR UPDATE SKIP LOCKED`. In a short transaction increment generation, lifetime/cycle attempts; set running, process-unique `locked_by`, a 90-second lease and heartbeat timestamp using database time. Commit before network, parser, normalization or embedding work.

An independent heartbeat path extends the lease every 15 seconds using a separate short connection. Every heartbeat, batch commit, manifest selection, stage advance, retry/failure and ready publication must match owner/job, `locked_by`, generation, running status and an unexpired lease. Use database wall-clock time for expiry, not a worker clock or stale transaction-start timestamp. A zero-row guarded update means lost ownership: cancel local work and perform no new stage or publication writes. Never revive an expired lease, even if no replacement has claimed yet.

SIGTERM stops new claims, cancels bounded child/network work and relinquishes only a still-owned lease. SIGKILL/crash recovery requires no graceful cleanup: expiry makes the job claimable. An exhausted expired claim becomes terminal failed under row lock instead of remaining stuck forever. A stale worker cannot release another worker's lease or record its error over newer progress.

Heartbeats are not permission to run forever. Enforce monotonic stage wall deadlines: validation 60 seconds, parsing 60, normalization 120, chunking 120, embedding 900, indexing/verification 300; cap a whole claim at 30 minutes. MinIO/Qdrant requests have a 30-second total deadline, embedding requests 60 seconds, with bounded responses and cancellation rather than inactivity-only timeouts. Database batch/lease transactions have a five-second statement timeout and a one-second lock timeout. Canonical/vector batches contain at most 500 rows/points and stay within the memory envelope. A deadline cancels remaining work and follows the recorded failure class; a hung stage cannot keep extending its lease indefinitely.

### 5.2 Bounded retry policy

At most five claims per automatic cycle, including the first and crashed claims. Transient failure releases the lease and sets pending with preserved stage/checkpoints and `run_after` delays 5, 15, 45, 120 seconds for subsequent attempts. An upstream cooldown may extend the delay up to 300 seconds; a greater required cooldown ends the cycle with safe delayed explicit retry guidance rather than violating it. No inner unbounded HTTP retry loops.

| Class | Examples | Action |
|---|---|---|
| Transient dependency | Bounded timeout, connection failure, dependency 429/5xx | Retry current incomplete stage within the cycle |
| Worker interruption | Missing heartbeat/expired lease | Reclaim with new generation, reuse sealed stages; consumes attempt |
| Unsupported/resource-limited PDF | Encrypted/corrupt/image-only, output/time/memory limit | Terminal safe failure; do not invite identical-input retry |
| Integrity/configuration | Original hash mismatch, conflicting deterministic output, malformed vector, wrong model/dimension/collection schema | Terminal failure, no publication; operator remediation required |
| Exhausted transient | Fifth claim fails | Terminal failed with explicit retry available after cooldown |

Explicit retry reuses the same original, version, profile and job. Under row lock it checks owner, failed/retryable state, cooldown and `retry_revision`; increments revision, resets cycle attempts only, preserves lifetime attempts/checkpoints, and queues the earliest incomplete stage. Repeated submission with the already-accepted revision returns the current job without re-enqueueing, even if the first retry has already finished or failed. Future/invalid revisions conflict. This prevents a delayed duplicate request starting another cycle. Rate-limit accepted explicit retries persistently per owner (initial cap five/hour); count only newly accepted transitions, not replay. There is no automatic retry after cycle exhaustion and no manual bypass of unsupported-input/integrity failure.

## 6. Stage idempotency and cross-store consistency

Artifact keys derive only from server-bound owner/version, sealed profile, stage/schema version and content hash. Canonical IDs derive from version/profile plus stable page/order/section/offset identity; Qdrant point UUIDs derive from index identity and chunk UUID. No random new chunk/vector IDs on retry; identical PDFs owned by different people still have separate identities.

| Stage | Durable success boundary and recovery |
|---|---|
| Validating | Fetch the existing original with bounded streaming; confirm source byte count/hash and supported PDF screening in the sandbox. No arXiv refetch. Seal validation result. |
| Parsing | Bounded geometry-first output stored privately and hash/size verified; select manifest with fenced DB commit. Crash after upload leaves an unreferenced private artifact, not completed parsing. |
| Normalizing | Insert replay-safe canonical pages/sections/blocks/spans in bounded transactions, validate order/geometry/mappings and seal counts/hash. |
| Chunking | Insert deterministic section-contained chunks/mappings; validate every included character and seal ordered chunk manifest. Partial rows are not searchable/published. |
| Embedding | Process bounded batches; validate vectors, write immutable private vector artifacts, then select each batch under fence. Seal an ordered embedding manifest only after all selected batches are verified. |
| Indexing | Read only the PostgreSQL-selected embedding manifest; upsert its exact vectors and minimal payload by deterministic point ID, with acknowledgement. Repeating after uncertain acknowledgement is safe. Verify full set/content and publish under fence. |

**External stale-write rule:** PostgreSQL fencing does not fence an already-in-flight MinIO/Qdrant request. Content-addressed artifact writes are immutable; a stale worker's unselected candidate is never authoritative. Qdrant writes may begin only from the sealed selected embedding manifest, and every writer uses those exact serialized float32 values/payload/point IDs. A resumed stale write therefore repeats the selected content instead of overwriting it with newly computed embeddings. Do not recompute vectors inline during indexing. A different profile/index uses a different collection identity and cannot overwrite the published index. Workers do not delete collections, points or originals during retry.

No cross-store transaction is claimed. Upload/acknowledgement precedes selection/checkpoint; a lost DB commit is recovered by verification and replay. Partial indexing remains unready. Content-addressed unreferenced artifacts are private storage leaks, not accepted output; record a safe orphan marker. Cleanup is conservative, reference-checked and restricted to known test artifacts during acceptance; automatic production garbage collection/deletion is not introduced here.

## 7. Parser sandbox and supported-input contract

Implement a new production PyMuPDF geometry-first adapter behind a typed, versioned interchange schema, not imported qualification code. Retain original bytes and raw source text. No OCR, JavaScript/action execution, attachment execution, remote plugins, external fonts fetched over the network, LLM parsing or Docling fallback.

M1 intake already opens untrusted PDFs in `papers/screening.py` before accepting them. Its current isolated subprocess strips secrets and applies resource limits but has no network/filesystem sandbox. SEC-01 therefore also moves that existing screening path onto the same sandbox launcher, preserving its initial-screening policy and tighter 10-second CPU/15-second wall limits. Do not leave an unsandboxed pre-queue PyMuPDF path while claiming production parser containment. Verify valid/rejected intake behavior and atomic acceptance remain unchanged.

### 7.1 Isolation boundary

Run the parser as an unprivileged child inside the worker's Linux container, using an explicit namespace/filesystem sandbox (recommended mechanism: bubblewrap). It gets a private network namespace, a minimal read-only runtime and single read-only input, private bounded temporary storage, no host/home/secret mounts and only the output channel required by the parent. Close unrelated descriptors and pass an allowlisted environment. Drop capabilities, enforce no-new-privileges, PID/file limits and hard process-group cancellation. Do not expose the Docker socket or grant privileged mode to launch it.

The deployed ARM64 Docker security profile must allow the required unprivileged isolation while still denying network/filesystem escape; prove this with the actual deployment profile. If user namespaces are unavailable, parsing fails closed. A subprocess with `RLIMIT` alone is not an approved fallback. This is an implementation feasibility gate, not a claim that bubblewrap already works in the current image.

Proposed default bounds: original 25 MiB/100 pages (existing M1 caps); parser wall deadline 60 seconds, CPU 45 seconds, address space 768 MiB, output 128 MiB, 64 open files, 16 child processes. Worker process tree has a 1 GiB cgroup limit. Parent limits child output while streaming, not after buffering it all; wall timeout terminates the entire process group and reaps it. Persist no partial successful parser artifact. Cap 2,000,000 extracted Unicode characters and 10,000 chunks per document; exceeded bounds fail safely rather than truncating. Limits are versioned configuration and tested at boundaries.

Validate byte count/hash, magic/MIME where applicable, page count, encryption, corruption and extractable text again from the accepted immutable object. Zero usable body text, non-finite/out-of-page geometry or no mappable retrieval content fails. Nonzero low text retains the existing warning rather than becoming an invented universal threshold: it may become ready only if every included body character and all index invariants pass. A warning is not proof of completeness, and excluded/unmappable substantive text cannot be silently dropped to manufacture readiness.

The parent treats parser output as untrusted: bounded decoding, strict types/counts, supported schema/profile, finite coordinates, source page identity, interval bounds and ordered mappings. Malformed output becomes a safe parser failure, never arbitrary SQL/path/network data.

### 7.2 Layout and provenance

- Canonical geometry uses unrotated PDF user space, bottom-left origin, with original MediaBox/CropBox coordinates, units and rotation retained. Do not assume MediaBox starts at `(0,0)` or use only `height - y`; record/apply the inverse PyMuPDF page transformation and test crop offsets and 90/180/270-degree rotations. PDF.js viewport transformation belongs to M3.
- Retain PyMuPDF raw character boxes. A span is an ordered text run with per-character geometry, not only a paragraph rectangle. Stable source references bind owner/paper/version/page/span and offsets; the caller never resolves arbitrary foreign span IDs.
- Determine reading order with explicit one-/two-column geometry rules and deterministic tie-breaking; spanning headings/captions retain their placement. Infer sections from supported heading/numbering/typographic cues; an unrecognized area belongs to an explicit untitled section, not a fabricated named heading.
- Detect repeating headers/footers conservatively: normalized repeated margin text on at least three pages and at least 60% of pages, in the top/bottom 8% bands; standalone page numbers normalize digit runs for matching and use the same positional/repetition constraint. Keep those blocks in canonical source data, mark exclusion from retrieval, and measure false removal on gold layouts. No removal solely because text is short or contains a number.
- Tables/captions/equations retain available text and source geometry. Do not invent table semantics or evidence from pixels. Unsupported reading order/geometry in a claimed evidence region is a recorded parser failure, not a page-only fallback.

## 8. Normalization, chunks and exact mapping

Offsets are zero-based, half-open Unicode code-point ranges, never UTF-8 byte or JavaScript UTF-16 offsets. Preserve raw source text. Allowed retrieval normalization is versioned: line-ending/whitespace normalization, explicit ligature expansion with many-to-one source mapping, and deterministic line-wrap dehyphenation only when the original characters and transformation are recorded. No case folding, accent removal or semantic rewriting of evidence text. Synthetic separator whitespace is represented explicitly without fabricated boxes.

For any resolvable chunk substring, mappings reconstruct the original source characters and the corresponding exact character/line boxes. Ambiguous occurrence requires an explicit source offset or reports unresolved; never search the PDF fuzzily or stretch a block box to make the quote pass. Removed headers/footers remain available as source data, not retrieval text. The future citation layer must distinguish normalized retrieval text from a verbatim source quote; M2 supplies that reversible contract but does not implement model citation acceptance.

Initial chunk profile: target 1,600 Unicode characters, hard maximum 2,400, trailing whole-sentence overlap at most 200. Prefer paragraph boundaries, split oversized paragraphs at sentence/whitespace boundaries and finally mapped character boundaries; never cross a section, and always advance the non-overlap cursor. Section title is metadata rather than unmapped text prepended into a chunk. Overlap references the same source spans, not duplicate canonical spans. Retain all supported substantive body text.

These are provisional production parameters, not Q0-selected optimal values. Freeze them in the profile; evaluate gold geometry/retrieval before acceptance. Ollama `truncate: false` is mandatory regardless of character cap; context overflow fails explicitly, never silently truncates or changes an already-sealed chunk set. Chunk checksum includes normalized UTF-8 text, source/profile identity, section and ordered mapping ranges/transformations. Validate map coverage and source bounds before sealing the chunk stage.

## 9. Embedding and owner-scoped index

### 9.1 Identity and bounds

Use native ARM64 Ollama and the qualified `bge-m3:567m` F16 digest in §1.2, dimension 1024, cosine, empty prefixes, no silent truncation. Record actual runtime version separately from model identity. Before work, query runtime/model metadata, verify digest/dimension/quantization and perform a bounded vector-shape probe. A missing/mismatched model fails readiness; the worker does not pull models or switch tags automatically. Runtime/package upgrades require recorded requalification rather than a changed tag silently reusing an index.

One embedding request at a time, initial batch size four, maximum request timeout 60 seconds and embedding stage deadline 15 minutes. Require exact vector cardinality, 1024 finite values per vector, nonzero finite norm and stable input ordering. Normalize to float32 unit vectors before sealing; validate conversion did not produce NaN/Inf/zero. Preserve selected bytes for retries. Batch size is operational metadata; semantic chunk/model/profile identity determines the index.

Index version is a deterministic hash of parser/normalizer/chunker profile, model digest, dimension, distance, prefixes and vector serialization/normalization contract. A collection name derives from that identity; never mix embeddings from different models/profiles. Verify collection dimension/distance and required keyword payload indexes before using it; mismatch fails closed without deleting/recreating an existing collection. Bind Qdrant to the private Compose network (optional loopback diagnostics only), not a public unauthenticated listener.

### 9.2 Retrieval boundary and publication

Internal dense lookup accepts authenticated owner context, paper ID and bounded query, resolves the owned published version/profile from PostgreSQL, embeds using that exact identity, and builds owner + paper + document-version filters itself. It also fixes collection and result limit (gold probe: top five). Reject unready/foreign papers before embedding/search. Rehydrate result IDs through owner/version-scoped PostgreSQL joins and discard foreign/stale/unknown IDs, even if Qdrant returns them. Qdrant text or ownership claims are never trusted. No browser endpoint or hybrid ranking is added in M2.

`ready` publication requires all of the following:

1. Verified immutable original and sealed processing identity still match the version.
2. All prior stage manifests are complete; canonical counts, sections, finite geometry, chunk checksums and character mappings validate; at least one usable chunk exists.
3. The selected embedding manifest covers the exact chunk set once, with valid selected vectors.
4. Qdrant has acknowledged writes. Bounded pagination/read-back under the exact filters finds the exact expected point-ID set and payload, not merely an equal count; vector comparison matches selected normalized float32 values within a documented numeric tolerance of `1e-5` per component. No missing, extra or mismatched point is accepted.
5. The collection's model/index contract matches PostgreSQL. A worker-only prepublication search using a selected chunk vector can rehydrate the candidate's owned chunks and map source geometry under its sealed manifest. This is not the ready-only retrieval entry point and exposes no unpublished data to a user.
6. A final short transaction under a current lease rechecks unchanged sealed manifests and active version, inserts immutable publication evidence, records job succeeded/ready and clears the lease atomically.

No successful external read and PostgreSQL commit can be globally atomic. The contract establishes correctness at publication and makes all concurrent worker writes immutable/replay-equivalent. Operational deletion/corruption after publication is not made impossible: subsequent retrieval fails safely on missing/inconsistent data; it does not fabricate evidence or silently broaden sources. Future reprocessing must stage a new immutable version/publication and must not disturb a previously ready version. M2 retry never changes the current source/profile or resets a succeeded job.

## 10. API and reader-facing UI

Keep master routes and central API types. `GET /api/jobs/:jobId` is owner-scoped; `POST /api/jobs/:jobId/retry` requires opaque session, trusted exact Origin and session-bound CSRF before parsing the retry body or reserving quota. Foreign and nonexistent IDs return indistinguishable `404`; revoked sessions return `401`. Retry input is only the observed `retry_revision`; no stage, owner, version, attempt limit, artifact or Qdrant filter is accepted from the client.

Job response exposes persisted diagnostic stage/status, safe error code, retryability/cooldown/revision and request ID, but not raw provider messages, stack traces, credentials, object keys or `locked_by`. Transition history for acceptance is inspected through worker/DB evidence; do not add an operator dashboard. `202` acknowledges a new retry transition; replay returns current state with `200`; non-retryable/future-revision conflict returns `409`; cooldown/quota uses `429` with `Retry-After`. Exact OpenAPI fields/types are finalized in the approved implementation plan.

Paper list/detail and import replay report actual persisted stage, never a literal queued-only type. Include a compact backend-derived preparation projection and job/retry identity for UI controls, without a separate client-side source of truth. No percentage is exposed because the pipeline lacks a measured denominator.

Reuse `apps/web/src/lib/api.ts` for payload types, `mutate`, `parseResponse` and allowlisted reader-error translation; extend `library-list.tsx`, the Library page, paper detail page and import-success presentation rather than creating another status client or dashboard. Existing TypeScript `stage` fields are strings, but the database is queued-only; the contract change must cover both sides. Retain technical stage fields in authenticated API responses as permitted by the master amendment; suppress them at presentation, not by silently changing the diagnostic API contract. `202` import means saved/queued, not proof the worker has started.

| Persisted condition | Reader presentation |
|---|---|
| Accepted/pending | Paper is saved; preparation will begin. No claim of readability. |
| Running | Quiet inline “Preparing this paper…” status; no raw stage list or timed fake steps. |
| Pending automatic recovery | Plain language that preparation is delayed and will retry; no manual retry while work is already scheduled. |
| Failed, retryable | Explain temporary preparation failure; explicit “Try again” after cooldown. Keep paper and warnings visible. |
| Failed, unsupported/resource bound | Explain that this PDF could not be prepared and suggest a supported/selectable-text or smaller PDF as appropriate. Do not offer a retry guaranteed to repeat failure. |
| Ready | Remove preparation status from Library; no redundant ready badge. Detail may confirm preparation completed but still states reading is not available in this milestone. No fake Reader link or disabled chat scaffold. |
| Status refresh fails | Keep last confirmed metadata; say the latest preparation status could not be checked. Do not translate network failure into document failure/success. |

Use bounded polling through existing same-origin helpers: one list/detail request every five seconds only while visible and at least one item is pending/running; avoid request-per-row fanout and overlapping requests. Pause while hidden, stop on terminal state/unmount/401, refresh on returning visible, and back off to 30 seconds on network errors. An in-flight older response cannot overwrite a newer retry result; cancel/discard stale requests. Pending status remains honest when the worker is stopped; do not invent automatic start estimates.

Preserve the approved editorial styles, compact Library and import controls, unknown metadata and low-text warnings. Retry is keyboard reachable with a visible focus indicator and at least 44×44 px target. Disable only the relevant action while submitting; no disruptive focus reset on polling. Use one resolving main landmark, one restrained live region for meaningful transitions, no repeated announcements each poll, reduced motion and no overflow at 375/768/1024/1440 px. Never render job/version IDs, raw codes/stages, request IDs or provider/model diagnostics as reader copy.

## 11. Apple M1 8 GB resource envelope

One document at a time; parser and embedding stages run serially; one loaded native model, never weights in API/worker. No building web images or running full test suites concurrently with resource acceptance measurements.

Provisional runtime cgroup ceilings: worker including sandbox 1,024 MiB; Qdrant 512 MiB; PostgreSQL 384 MiB; MinIO 256 MiB; API including intake-screening child 512 MiB; production web 256 MiB. Total 2,944 MiB, leaving approximately 974 MiB inside the observed Docker VM for OS/cache/init overhead. These are caps to validate, not existing configuration or proof the services fit. Intake screening uses a 256 MiB child address-space cap under that API envelope and must preserve supported-input acceptance in the real security tests; the existing Linux 1 GiB child limit cannot be treated as compatible with a smaller parent cgroup. Measure concurrent accepted intake plus background processing, not only an idle API. Native Ollama/model target is at most 2 GiB measured resident/unified allocation, with the remaining host memory needed by macOS, browser and shared services. Do not sum cgroup RSS and VM RSS as independent physical allocations.

Acceptance records host memory pressure/swap before and during processing, Docker VM allocation, per-service peaks/OOM flags, worker+child peak, native server/model allocation, batch size and elapsed stages. Sample during execution rather than only after it. Required outcome: no OOM/restarts or parser-bound escape, host pressure remains non-critical, swap growth at most 512 MiB across a warm two-paper sequential run, and API/Library remains responsive (each recorded status request under two seconds). Record cold-model loading separately. A host already above these bounds is a prerequisite blocker, not permission to stop shared 9Router or owner applications.

If memory limits fail, first reduce batching/bounded buffers while retaining model and semantic contracts. Changing parser/model, disabling sandbox or increasing the declared machine budget requires explicit design revision. Q0 numbers are baseline evidence only; runtime capacity and latency are newly measured M2 claims.

## 12. Requirement-to-test and exit-gate traceability

Permanent tests follow RED → GREEN and existing real PostgreSQL/MinIO isolation conventions. Use deterministic boundary/failure tests for consumer-visible invariants, not copied wiring or wording. Automated tests support but do not replace the six actual-stack gates.

| Requirement | Test contract | Real acceptance / gate |
|---|---|---|
| JOB-01; master §8 | Concurrent claim exclusion; DB-time expiry; heartbeat failure; stale generation cannot commit/release/publish; cycle exhaustion and duplicate retry revision | G1 stage ledger; G2 crash/reclaim; G3 replay |
| DOC-01; §§6–7 | Composite ownership/version FKs; deterministic canonical IDs; section boundaries; repeated headers retained/excluded; reversible ligature/dehyphenation/whitespace; rotated/cropped PDF geometry | G1 source/manifests; G3 stable chunk set; G5 exact gold boxes |
| SEC-01; §§4,17 | Invalid/encrypted/image-only/oversized/excess-page PDFs; huge streams/output; CPU/wall/memory/PID bounds; malformed child output; no network/credentials/host-file access | G6 actual sandbox/resource probes with safe errors |
| PARSE-01; §7 | Qualified corpus geometry and reading order; broader one-column/figure-heavy/alternative-layout fixtures; low-text warning semantics | G5 gold evidence, G6 unsupported cases; no general-quality claim |
| EMB-01; §§9,10,20 | Wrong digest/dimension, NaN/Inf/zero vectors, cardinality/order mismatch, truncate disabled, sealed-byte replay | G1 native runtime identity/measurements; G3 same vector set; G4 mismatch rejection |
| IDX-01; §§5,9 | Mandatory backend owner/paper/version filters; foreign/stale rehydration rejection; exact-set verification (including equal-count wrong IDs); partial upsert/ack loss | G3 idempotency, G4 no premature ready, G5 owned evidence and second-user denial |
| M2 API/UI; §§12,14–16 | Retry auth/CSRF/Origin, foreign/nonexistent symmetry, cooldown/replay races, unknown metadata, refresh failure does not claim document failure | G1 live Library/detail; G2 delayed preparation; G4 failure/retry UI; real browser widths/keyboard/focus |
| Existing M1 contract | Migrate populated M1 rows, unchanged original/version/job/replay identity, immutable source guards, both intake paths | Existing queued jobs process without re-import; affected M1 suites and build remain passing |

### G1 — Golden paper reaches ready

Through the actual API import `1706.03762`; observe version/hash and queued acceptance, disconnect/reload independently of processing. Run the real worker with private MinIO, PostgreSQL, native model and Qdrant. Record persisted transitions for all seven processing stages, manifest hashes/counts, model/index identity, final publication transaction and reader-facing Library/detail state. Confirm API status is backed by the same DB record. Record actual upstream failures if encountered; do not replace an unsuccessful import with an undisclosed mock.

### G2 — Worker interruption and lease recovery

Stop only the M2 worker mid-stage after a recorded checkpoint, using an ungraceful interruption so expiry is genuinely exercised. Observe lease generation/heartbeat stop, restart the worker, and record claim after the 90-second expiry and completion with a higher generation. Also pause/resume an old worker after another claimant takes over; demonstrate rejected old DB updates and replay-equivalent external writes. Do not stop shared services or delete volumes.

### G3 — No duplicate chunks or vectors

Interrupt indexing after a real partial upsert and separately after acknowledgement but before DB checkpoint. Retry from the same selected embedding manifest. Compare exact chunk IDs/checksums/mappings and Qdrant point IDs/payload/vector checksums before/after, not only counts. Assert one publication and no duplicate chunks/vectors. Submit the same explicit retry revision twice, including a delayed replay after the retry reaches terminal state; no extra cycle is created.

### G4 — No premature ready

Withhold/fail Qdrant writes/read-back, remove a point in an isolated test collection, insert an extra/wrong point with the same total count, and inject a canonical/mapping or vector-manifest mismatch in an isolated test database. The real worker/API must remain non-ready or fail safely in every case. Restore the isolated dependency/data and demonstrate supported retry reaches ready only after complete verification. Never corrupt an owner collection/paper for this probe. Browser must show the corresponding safe state, not technical diagnostics.

### G5 — Owned gold query resolves exact geometry

Use the frozen scaled-dot-product-attention question from the public gold corpus. The internal real-model dense top-five query for the published owned paper must contain evidence resolving to the annotated page 3 region in the correct column, with exact source-character boxes through PostgreSQL mappings. Check original PDF hash first: if the live arXiv edition differs from the frozen hash, use the matching supported source edition or separately annotated source; do not apply stale page gold to different bytes. Record expected/actual page, source references, offsets and geometric overlap; no fuzzy/page-only success. Repeat access as another owner and with a foreign paper/version candidate; no evidence or embedding/search call on unauthorized access. This gate is not a new dense Recall@5 benchmark or M3 citation/browser-highlight acceptance.

### G6 — Parser security and resource evidence

Execute actual malformed/encrypted/image-only/oversized/excess-page and adversarial resource fixtures against the deployed sandbox. Exercise CPU/wall/memory/output limits and prove the process group terminates, heartbeat/recovery remains bounded, no publication occurs and errors are safe. A controlled sandbox probe must be denied outbound networking, credential/environment access, host-file reads and writes outside its output area. Separate malicious-child containment probes from actual invalid-PDF parser tests in the report; neither alone substitutes for the other. Record applied UID/capabilities/limits, child outcome and cgroup measurements without payload text/secrets. Verify valid gold and rotated/cropped fixtures still work under the same security profile.

## 13. Verification evidence and approval boundary

The later acceptance report must identify commit/worktree, runtime/image/model versions, configuration limits, exact commands or browser journeys, source hashes, safe request/job correlation IDs, expected versus observed state, failures, resource measurement scope and cleanup limited to its own fixtures. Private PDFs/text, screenshots with owner account data, cookies, tokens, object keys and credentials stay out of Git. Use aliases A/B rather than publishing account emails. Do not create a passing report before running gates.

Implementation completion requires affected backend/frontend suites, production build, real worker/API/UI journeys, security/ownership probes and all G1–G6. Preserve historical Q0/Q0.1 evidence; acceptance belongs in a new M2 report. Spec approval advances M2/owned requirements to `Designed`; plan approval to `Planned`; code alone to `Implemented`; all recorded gates to `Verified`.

**Draft self-review:** reconciled the existing immutable-source/active-version triggers, pre-queue screening exposure, at-least-once external stale-write race, ready-only retrieval versus private publication verification, and the presentation amendment's distinction between API diagnostics and visible UI. All six required gates have dedicated procedures and requirement mappings. Sandbox feasibility and full-stack resource fit remain unverified execution prerequisites, not passing claims. No implementation tests or owner-confirmed journeys were rerun during design.

### Owner approval — 2026-09-27

The owner explicitly approved this M2 child specification and authorized implementation planning: “Tôi phê duyệt child spec M2 hãy bắt đầu lập implementation plan.”

This accepts the design and provisional operating bounds, with real-machine qualification still required. It does not approve an implementation plan, authorize production implementation, waive the M1 prerequisite record, or claim any M2 gate has passed. The [implementation plan draft](../plans/2026-09-27-researcy-m2-durable-processing.md) is subject to its own review gate.
