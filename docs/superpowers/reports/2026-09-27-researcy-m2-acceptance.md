# Researcy M2 execution and acceptance evidence

## Execution authorization — 2026-09-28

The owner approved the M2 implementation plan and explicitly authorized proceeding while supplementing the M1 record separately. M2 is `Planned`; M1 is not promoted. Worktree `.omp/worktrees/m2-durable-processing`, branch `feat-m2-durable-processing`, implementation starting from `31d7b10`. No implementation task or M2 exit gate is complete.

## Task 1: sandbox feasibility preflight — 2026-09-28

### Environment and observed commands

`docker info --format '{{.Architecture}} {{.MemTotal}}'` returned `aarch64 4108828672`. The disposable probe uses official `python:3.12.13-slim`, resolved manifest digest `sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36`; Linux kernel `6.12.76-linuxkit`. No application service, volume, owner PDF, root environment or shared 9Router was mounted, started or modified.

The first actual unprivileged syscall probe:

```bash
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 python:3.12.13-slim python -c "import ctypes,os; c=ctypes.CDLL(None,use_errno=True); r=c.unshare(0x10000000); print({'uid':os.getuid(),'unshare_user_result':r,'errno':ctypes.get_errno()}); raise SystemExit(0 if r == 0 else 1)"
```

Observed: `{'uid': 65534, 'unshare_user_result': -1, 'errno': 1}`, exit 1. The requested flag is `CLONE_NEWUSER`. This is a new execution observation, not a rerun of an owner-reported failure.

Independent environment inspection in the same restricted image reported:

```text
/proc/sys/user/max_user_namespaces = 15665
CapEff: 0000000000000000
NoNewPrivs: 1
Seccomp: 2
```

The positive kernel namespace quota does not prove namespaces are available through Docker's filter. The failing syscall alone does not conclusively distinguish seccomp from other runtime restrictions.

A disposable image `researcy-m2-sandbox-probe:20260928` was built outside the repository with bubblewrap `0.12.0-1~deb13u1` and strace `6.13+ds-1`, both ARM64 Debian packages. It runs as UID/GID 65534 and contains no application secrets or PDFs. Actual bubblewrap startup was then traced:

```bash
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --entrypoint strace researcy-m2-sandbox-probe:20260928 -f -e trace=clone,clone3,unshare,setns,mount bwrap --unshare-user --unshare-pid --unshare-net --die-with-parent --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib --proc /proc --dev /dev /usr/bin/true
```

Observed:

```text
clone(child_stack=NULL, flags=CLONE_NEWNS|CLONE_NEWUSER|CLONE_NEWPID|CLONE_NEWNET|SIGCHLD) = -1 EPERM (Operation not permitted)
bwrap: No permissions to create a new namespace, likely because the kernel does not allow non-privileged user namespaces.
+++ exited with 1 +++
```

The child command was only `/usr/bin/true`; parsing did not start. This demonstrates that the default restricted container cannot currently launch the proposed sandbox. It is not a parser quality failure and does not justify an unsandboxed fallback.

### Next security decision

Candidate next diagnostic: derive a custom seccomp profile from the Docker/Moby default, permitting only the observed bubblewrap `clone` flag combination in a disposable non-root, no-network, no-host-mount probe while retaining all dropped capabilities and no-new-privileges. This can identify the next denied operation; it does not establish full sandbox functionality. No custom profile, capability grant, privileged mode, unconfined seccomp or production Compose security change has been applied.

Changing a permission boundary requires point-of-risk authorization. Task 1 remains incomplete while that diagnostic authorization is pending. The approved plan already anticipates a minimal measured profile, but no exact syscall exception had been selected at approval time. Do not implement dependent parser/worker code against an assumed passing sandbox.

## Gate ledger

| Gate | Status | Evidence |
|---|---|---|
| G1 golden import to ready | Not run | No worker implemented |
| G2 crash/lease recovery | Not run | No worker implemented |
| G3 duplicate-free index retry | Not run | No index implemented |
| G4 publication invariants | Not run | No publication implemented |
| G5 owned evidence geometry | Not run | No production canonical index implemented |
| G6 parser containment/resources | Not passed | Sandbox startup denied before child execution; no containment success claimed |

No application tests/build were rerun to confirm M1 observations. The only build was the disposable diagnostic image. Preserve the probe image temporarily for the authorized next diagnostic; it is not a production deliverable.

## Authorized clone diagnostic — 2026-09-28

The owner interactively selected “Cho phép probe giới hạn”: permit only the measured `clone` flags `0x70020011` in the disposable probe, retaining UID 65534, no network, all outer capabilities dropped, no-new-privileges, no host mounts/secrets and no production Compose change.

The installed engine reports Docker 29.4.1, commit `6c91b92`. Attempts to fetch its version-specific Moby module metadata returned HTTP 404. The current Moby `main` seccomp profile was therefore not assumed identical to the installed engine. Instead a restrictive allowlist was constructed from ordinary default-policy syscalls plus the exact new clone exception. This initially also blocked container-runtime bootstrap calls (`fstatfs`, `fcntl`, `statx`, `readlinkat`, futex and descriptor enumeration); those diagnostic failures did not establish anything about bubblewrap. Interpreter bootstrap required normal metadata/path calls as well. No mount/unmount/pivot-root/setns/unshare permission was added.

Actual direct AArch64 `clone` probe under the custom profile used syscall 220 with flags `0x70020011` and a child that exited immediately; parent waited for it. Observed exit 0:

```text
{'clone_result': 7, 'errno': 0}
{'clone_result': 0, 'errno': 0}
```

Actual bubblewrap under this restricted profile advanced past namespace creation, then failed with exit 1:

```text
bwrap: Failed to make / slave: Operation not permitted
```

Conclusion: the exact authorized clone exception enables namespace creation. Filesystem sandbox setup is still blocked; G6 has not passed. The next proposed diagnostic would permit mount-namespace setup syscalls only in the same disposable container, not deploy them in production. It requires a new point-of-risk authorization because those syscalls were excluded from the prior confirmation.

## Resumed Task 1 execution

The owner authorized the additional disposable `mount`, `umount2`, `pivot_root` probe, then authorized the restricted application test image, then explicitly approved checking in the measured deployment profile and configuring API/test security in this worktree. This does not authorize push/merge or consuming owner jobs.

Docker Desktop was stopped at resumption; `docker desktop start` started the required runtime. The original external temporary profile was absent and was recreated. The retained probe image was available. No owner stack/data was used.

Actual bubblewrap child `/usr/bin/true` exited 0 after removing the child `/proc` mount and devpts setup. Those facilities are not needed for Python screening; `/dev/null` and `/dev/urandom` are bound individually. No `unshare`/`setns` exception was added. Trace showed the exact namespace `clone`, namespace-private mount flags, `pivot_root`, and `umount2(...,MNT_DETACH)`. The checked-in AArch64 profile permits only that namespace clone combination and enumerated mount flag combinations; ordinary non-namespace process/thread creation remains permitted, and clone3 returns ENOSYS for libc fallback. No capability, privileged mode, unconfined seccomp or Docker socket is used.

Implemented the shared launcher, standalone screening child, hard limits, capped streaming output and process-group kill/reaping. Only interpreter/libraries/venv, child script and one read-only input are mounted. Child has no application source directory, service environment, parent temporary directory or proc filesystem. API/test run as UID/GID 65534 with read-only root, 512 MiB memory, 64-task cgroup, 64 MiB private container tmpfs and no-new-privileges. Screening CPU/wall/address-space limits are 10 seconds/15 seconds/256 MiB; child open-file/process caps are 64/16.

Observed RED: runtime-role tests failed in three distinct expected cases; Linux sandbox suite failed seven cases because the boundary did not exist. A later strict child-output regression failed four cases: boolean/over-cap pages, extra fields and non-string error. No mocked containment verdict was used.

Initial application image exposed missing library loader configuration: `libpython3.12.so.1.0` unavailable in the minimal root. Explicit fixed `LD_LIBRARY_PATH=/usr/local/lib` resolved it without exposing `/etc` or credentials.

Dependency-free focused run: **34 passed, 5 deselected**. Isolated storage-backed focused run: **39 passed** before the four new strict-response cases. Real standalone PDF screening returned page 1, title `M2 smoke`, and matching original byte count; low-text warning was retained.

Full-suite diagnostics initially exposed missing ordinary baseline syscalls rather than a valid passing deployment: `chmod`, DNS `sendmmsg`, init signal/process-group calls, and native thread `exit`. Omitting `exit` leaked terminated native threads until the 64-task cgroup filled; a temporary diagnostic observed `pids.current` rising while Python reported only its active threads. Allowing ordinary `exit` restored termination. The diagnostic was throwaway, not a production bypass or raised PID cap.

After baseline correction, actual command under the deployed restrictions:

```bash
docker compose --env-file /dev/null -p researcy-m2-test \
  -f compose.yaml -f compose.test.yaml -f /tmp/researcy-m2-isolated-compose.yaml \
  run --rm --no-deps api python -m pytest tests -q -p no:cacheprovider --tb=short
```

Observed **202 passed, 1 skipped** before the four strict-response cases. The skip is the existing opt-in real-arXiv network test, not a containment test. Isolated PostgreSQL/MinIO used separate Compose network and temporary memory-backed storage, with no host ports or owner volumes. Test migrations target the `postgres` maintenance database and create/drop their own UUID-named databases.

Production image build passed. Actual production API process under the same security/resource restrictions returned `/health` 200, and `/api/papers` without authentication returned 401 once connected to the isolated PostgreSQL dependency; process UID was 65534. A first no-network/no-database smoke returned health 200 and library 500 because the existing route opens its database connection before session resolution; that failed smoke is not presented as passing auth evidence.

The full suite must be rerun after the strict-response fix and review findings. Task 1 is not yet marked complete. G1–G6 remain unpassed: this proves the intake boundary, not worker geometry/resource acceptance or the complete M2 pipeline.

### Task 1 closeout

Two independent read-only reviews completed: runtime integration and sandbox security. Required findings were corrected and scoped re-reviews returned PASS. The test override now forces `APP_ENV=test`, `APP_ROLE=api`; an actual run with caller `APP_ENV=production` observed those test values. A bounded trusted interpreter readiness preamble distinguishes denied namespace setup (503 unavailable) from initialized-child resource failure without reading/logging stderr.

Resource proof now distinguishes CPU-limit termination from wall fallback, observes a live descendant tree in container `/proc`, asserts bounded timeout return and confirms sampled descendants disappear. Separate probes catch actual MemoryError under the address-space limit and file/descriptor denial. All **15 sandbox cases passed** with the checked-in restricted profile. A throwaway in-memory mutation removing CPU and address-space limits produced two expected failures; no production file was mutated.

Latest integrated Linux backend suite: **215 passed, 1 skipped** (includes initial Task 2 schema regression coverage; Task 2 review/closeout is not yet complete). Final production image build passed; actual valid-PDF screening smoke passed. An independently generated PDF with its xref removed was confirmed repaired by PyMuPDF, then safely rejected by production screening with `422 PDF_INVALID`.

Task 1 is complete; the earlier startup blocker and review-pending statements above are historical. M2 remains `Planned`, not implemented end-to-end or verified. No owner job was consumed; no push/merge/prune performed. Worker and G1–G6 final acceptance remain pending.

## Task 2 closeout — forward schema and frozen contracts

Migration `0003_m2_processing` preserves accepted M1 source/version/job/replay identity, adds scheduling/leases/counters, immutable profile and canonical relations, selected vector batches, manifests, publications and scoped transition/quota records. Composite constraints prevent cross-owner/version mappings and selected foreign chunks; source geometry cannot escape its page; selected-vector hashes must match exact bytes.

RED: foreign selected chunks were accepted (one failing case); page-escaping geometry and wrong selected-vector hash were accepted (two failing cases). Review identified mutable/nonbinary manifest members, unsupported profiles and operational resource caps incorrectly altering semantic index identity (12 failing cases/one already passing). A second review found a committed published job could be requeued or deleted (two failing cases).

GREEN: `tests/test_processing_schema.py tests/test_schema.py tests/test_processing_models.py -q --tb=short -p no:cacheprovider` in the restricted Linux test image: **28 passed**. Both schema and contract reviewers returned PASS after corrections. Succeeded jobs are now immutable; initial publication and ready still commit atomically. Semantic hashes exclude runtime resource caps; schema-1 model/parser contracts and immutable binary members are validated.

Actual throwaway psycopg/Alembic smoke against a disposable PostgreSQL database: populate at 0002, upgrade twice, read unchanged source bytes/key, select due job under a row lock, seal supported identity, and attempt original/config/ready invalid writes. Observed `source_unchanged=True`, `due_job_claimable=True`, three rejected writes, final `queued/pending`. Temporary database dropped; no migration on owner DB.

Task 2 is complete. Task 3 RED now demonstrates missing job/retry modules; those tests are not passing yet. No final M2 exit gate is claimed.

## Task 3 closeout — fencing and bounded retry cycles

Implemented idle-connection short transactions, SKIP LOCKED due/expired claims, independent guarded heartbeat, immutable profile selection, checkpoint comparison, final DB-time batch fencing, safe failure/release transitions, cycle exhaustion and owner-scoped explicit retry. Accepted retries serialize by job and owner, charge only new transitions to a rolling one-hour quota, preserve lifetime attempts/manifests and replay older accepted revisions without reset. Shared Settings contain bounded queue/deadline defaults; parser/storage configuration fields for the next task were integrated in the same configuration boundary.

RED: absent modules prevented collection; unsafe queue settings were accepted (four failing cases); provider cooldown 301 seconds was clamped into automatic retry (two failing cases). Read-only reviews identified the final safe retry revision being treated as claim overflow, raw provider failure metadata persistence (three failing cases), and the wrong shared Retry-After exception attribute.

GREEN: full Linux backend suite before final review corrections: **253 passed, 1 skipped**. Latest focused queue/retry/config suite after corrections, with exact current files mounted read-only under the deployed test profile: **38 passed**. Both lease and retry reviewers returned PASS on corrected boundaries. Unknown failure codes now map to terminal safe integrity metadata; claims guard only counters they increment. Actual shared API error-handler smoke returned `429`, `Retry-After: 30`.

Actual two-process throwaway harness through `get_conn` against a temporary migrated database: one exclusive claimant; connections IDLE between work; expiry/reclaim generation 1→2; stale heartbeat false/current heartbeat true; stale release rejected; current release returned `validating/pending`. Temporary database removed. The worker-only ready-publication consumer and its exact index verification remain T7, not a claim from this queue smoke.

Task 3 is complete. Task 4 parser and immutable-artifact work is in progress. No owner job processed, no owner migration, no final G1–G6 gate claimed.

## Task 4 implementation evidence — parser and immutable artifacts

Implemented bounded secret-free geometry parsing, strict schema-1 page/block/span interchange, original unrotated PDF geometry, ordered source-group paragraph cues, deterministic column/table ordering and immutable content-addressed artifact storage. Raw source text and per-code-point boxes are retained; no OCR, pixels, invented table semantics or approximate evidence boxes are added.

RED: actual malformed output exposed integer overflow, non-finite determinant acceptance, JSON recursion and duplicate-field acceptance. Corrected shared decoding and typed validation return terminal safe `PARSER_OUTPUT_INVALID`, with no published partial output. Review also verified that four earlier mutation fixtures now use actual JSONL newline terminators.

Actual MinIO smoke found a consumer-visible replay failure only at corpus size: a 3.2 MiB duplicate conditional PUT received an early rejection/reset while its request body was still streaming. The protocol now verifies an existing key first, permits conditional PUT only after 404, and performs exactly one post-PUT readback for success or uncertain ACK. All steps share one deadline; there is no unconditional overwrite, repeated upload, provider-body logging or generic retry loop. Large replay and concurrent-create regressions use real MinIO.

Observed verification in the isolated restricted ARM64 test project:

```bash
docker compose --env-file /dev/null -p researcy-m2-test \
  -f compose.yaml -f compose.test.yaml -f /tmp/researcy-m2-isolated-compose.yaml \
  build api
docker compose --env-file /dev/null -p researcy-m2-test \
  -f compose.yaml -f compose.test.yaml -f /tmp/researcy-m2-isolated-compose.yaml \
  run --rm --no-deps -T api python -m pytest tests -q --tb=short -p no:cacheprovider
```

Full current backend suite: **288 passed, 1 skipped**; the skip remains the opt-in real-arXiv network test. Focused parser/artifact/sandbox/screening checks with current package/tests bound read-only: **64 passed**.

Throwaway actual parse → private MinIO put → identical replay → verified download → typed read used both frozen public qualification PDFs, checked their original SHA-256 against the corpus, and removed only its unique temporary test bucket. Observed:

| Public paper | Pages / blocks / spans | Raw characters | Artifact bytes / SHA-256 | Gold order |
|---|---|---|---|---|
| `1706.03762` | 15 / 1,051 / 1,048 | 38,450 | 3,236,373 / `a63e514514cc38bf7c5310f43998254adb2118f61c9502e4199cba321a9b44bf` | 6/6 |
| `2005.11401` | 19 / 1,327 / 1,324 | 67,755 | 5,526,900 / `06550bf751ba7d768bc22ad20b271c4d163c89e20a46bcedcfc379d73ddf533c` | 6/6 |

Replay identity, SHA-256, byte counts and downloaded character counts matched exactly. Ordering comparison removed whitespace and expanded only the explicit `ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ` ligatures; artifact source text was not changed. Combined per-paper paths took 1.357 and 1.651 seconds; container cgroup peak was 89,513,984 bytes. This focused measurement ran without an embedding model and is not the full resource gate.

Runtime-config and interchange/security re-reviews returned PASS. Geometry and artifact review closeout remain pending at this checkpoint. No owner migration/job processing occurred; no final G1–G6 gate or stronger milestone status is claimed.

### Task 4 final review corrections

Geometry review exposed incorrect regex escapes, bold captions promoted to headings, unknown-glyph-only documents accepted as usable, and internally inconsistent transform/block geometry. RED reproduced each consumer-visible defect. Corrected captions/numbered headings, retained replacement glyphs in mixed usable text while rejecting marker-only input, required one span per text line, and checked exact character-box union and oriented transform corners with ≤1e-4 PDF-unit rounding tolerance. A reflected transform with the same crop envelope was separately demonstrated accepted before the ordered-corner fix.

Artifact review exposed transient 429/unlisted 5xx being terminal and truncated HTTP responses escaping as raw protocol exceptions. Deterministic local HTTP-server regressions reproduced the failures; all transport exceptions are now sanitized and dependency 429/5xx remains retryable.

Production image build succeeded. Full backend after those corrections but before the final ordered-corner change: **299 passed, 1 skipped**. Final parser/artifact/sandbox/screening checks after ordered-corner validation: **76 passed**. Artifact reviewer returned PASS; geometry re-review is pending at this checkpoint.

Repeated actual final corpus parse → immutable put/replay → verified download passed exact identity and all 12 ordering relations. Classification fixes changed artifact bytes (raw text, pages, blocks, spans and character counts unchanged):

| Public paper | Final artifact bytes / SHA-256 | Elapsed combined path |
|---|---|---|
| `1706.03762` | 3,236,445 / `746905ababf629f80af91fd3a14b3998a03abc3e378ee6d66a515d4b240c29a4` | 1.401 s |
| `2005.11401` | 5,526,951 / `7e8480c2a627d7fdfbaf02a8e12efafcc83d8e11962fd2d2119f005cb13e7b00` | 1.724 s |

Container peak: 90,939,392 bytes. Temporary test bucket was removed. No final resource/evidence gate is inferred from this focused smoke.

All four scoped reviews are closed: geometry, typed interchange/security, artifact writes and runtime configuration returned PASS on corrected boundaries. Task 4 is complete. Task 5 RED now demonstrates absent normalization/chunking modules; its implementation and isolated canonical/provenance smoke remain pending. M2 and final gates are not promoted.

## Task 5 outage recovery checkpoint

The owner reported an internet outage and requested state verification and continuation. Fresh worktree inspection confirmed `feat-m2-durable-processing`, latest committed `2ef1eb7`, unchanged Tasks 1–4 and only uncommitted Task 5 files/local plan clarification. No staged changes, reset, deletion, owner migration or owner job processing.

Two implementation agents and the normalization reviewer had terminated with provider DNS `ENOTFOUND`; the first provenance review returned an invalid schema without findings/coverage. These failures are not PASS or completion evidence. Resumed the same scoped jobs after connectivity returned.

Observed Task 5 RED before the outage: normalization/chunking/provenance modules absent; repository suite **14 failed** on its unimplemented functions. The repository and chunking implementations remain unfinished at this checkpoint. Corrected normalization after separate RED cases for dropped typographic-heading source text and separate numbered/title blocks.

After resumption, actual restricted Linux verification: **9 normalization cases passed**, plus the explicitly selected resource-bound case **1 passed**. Source overflow fails before emitting a partial canonical record. Earlier actual two-corpus normalization retained 38,450/67,755 raw code points; an exact normalized lookup of the frozen annotated page-three quote found one occurrence under the expected section. No approximate PDF search was used.

Resumed provenance security review returned a valid static PASS; integrated PostgreSQL checks and the original-PDF overlay remain pending. No Task 5 closeout or final M2 gate is claimed.

### Task 5 integrated canonical/provenance evidence

After the chunking provider request aborted again, parent inspection confirmed its file was still absent. The parent implemented the bounded streaming chunker inline; no missing-code compatibility fallback was accepted. Repository integration removed a duplicate checksum fallback and demonstrated RED for a 1e-6 immutable geometry change being accepted, an iterable being consumed beyond its 500-record limit, wrong-profile page IDs, and three invalid mappings after the first 500-row transaction leaving an immutable prefix.

Corrections: exact replay equality; bounded `islice(...,501)` input checks; fixed integrity failures instead of raw PostgreSQL constraint detail; all canonical IDs recomputed against the sealed profile; and every complete chunk mapping checked against owned persisted source text/bounds/section/exclusion before its first header insert. Preflight and range resolution reuse the same source-transformation predicate. Actual inserted headers plus mappings still use at most 500 rows per short fenced transaction. Chunk exhaustion now persists a non-retryable resource failure rather than a false integrity label.

Observed restricted Linux focused command (`tests/test_chunking.py tests/test_document_provenance.py tests/test_document_repository.py tests/test_jobs.py`): **51 passed**. All four final read-only reviews returned PASS: normalization, chunking, repository and provenance/security. Static PASS is not substituted for runtime acceptance.

Actual throwaway original upload → owner-scoped original streaming/hash verification → deployed parser → canonical writes → chunks/mappings → full replay → exact range resolution used a unique test PostgreSQL database and private MinIO bucket. Source hashes match the unchanged frozen corpus. Expected versus observed row sets were compared using all stored row content (ordered table snapshots), not only counts; identical replay preserved IDs, checksums and mappings exactly.

| Public paper | Pages / sections / blocks / spans | Chunks / mappings | Raw code points | Combined path |
|---|---|---|---|---|
| `1706.03762` | 15 / 62 / 1,051 / 1,048 | 68 / 12,176 | 38,450 | 13.848 s |
| `2005.11401` | 19 / 111 / 1,327 / 1,324 | 126 / 19,930 | 67,755 | 22.036 s |

The frozen annotated scaled-attention quote had one exact normalized occurrence. PostgreSQL offset resolution returned five source fragments, page index 3, and 225 exact character boxes. The generated original-PDF overlay was visually inspected: boxes cover the requested paragraph and fraction, not adjacent body text. Exact box area within the unchanged rounded gold regions was 0.99999595; the tiny difference is annotation rounding, not a stretched/approximate source box. Container peak was 152,961,024 bytes. This was not a native-model/resource acceptance run.

The unique database and bucket were removed by the harness. No owner database, job or collection was modified. The first combined build/suite command timed out at 300 seconds after both image builds succeeded and a 217-second frozen Pygments download consumed most of the deadline; its incomplete test progress is not a full-suite PASS. Final build/full-suite closeout remains pending.

### Task 5 closeout

Final production image build passed. Full current backend suite under the deployed restricted test profile with the exact current package/tests mounted read-only: **338 passed, 1 skipped in 55.41 seconds**. The skip remains the existing opt-in real-arXiv network case. This standalone run avoided another test-dependency download; no dependency versions or security limits changed.

```bash
docker build --target production -t researcy-m2-api:local -f apps/api/Dockerfile apps/api
docker compose --env-file /dev/null -p researcy-m2-test \
  -f compose.yaml -f compose.test.yaml -f /tmp/researcy-m2-isolated-compose.yaml \
  run --rm --no-deps -T \
  -v /Users/tuananhduong/Projects/researcy/.omp/worktrees/m2-durable-processing/apps/api/researcy:/app/researcy:ro \
  -v /Users/tuananhduong/Projects/researcy/.omp/worktrees/m2-durable-processing/apps/api/tests:/app/tests:ro \
  api python -m pytest tests -q --tb=short -p no:cacheprovider
```

Generated overlay PNG/JSON were removed after inspection and safe measurement recording. Temporary original/parser files were inside removed disposable containers. All scoped reviews and the full affected suite/build are complete; Task 5 is complete. Embeddings, Qdrant, worker/API/UI integration and the six final real-stack gates remain Tasks 6–11. No stronger M2 milestone status is claimed.

## Task 6 implementation evidence — native embeddings and first selection

Observed actual native Ollama `/api/version` and CLI version: 0.18.2. Inventory contains the approved `bge-m3:567m`, F16, digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`; `/api/show` reports `bert.embedding_length=1024`, embedding capability. No model was pulled or substituted.

RED: absent retrieval module and absent first-selection functions. Implemented bounded native HTTP requests, exact runtime/model preflight, streamed response cap, `truncate:false`, finite unit float32 little-endian serialization, fenced first selection and complete ordered embedding manifests. Deterministic HTTP boundary tests plus actual PostgreSQL/MinIO changed-recomputation test: **12 passed**. A second valid candidate cannot replace the first selected bytes/artifact.

Actual container-to-native preflight and one real vector passed, 4,096 bytes, SHA-256 `c1e30094218d4028ba24c4756c77044030900550187a54adaa70216f0902e072`. Native `ollama ps` observed 1.2 GB, 100% GPU, context 4,096; this is a runtime display observation, not total host-resource gate evidence.

Actual isolated golden-paper pipeline embedded all 68 sealed chunks in 17 batches of four. The harness uploaded private immutable vector artifacts, selected each batch under the current lease, validated the complete manifest, downloaded every selected artifact and replayed selection without another embedding call. Embedding phase: 16.033 seconds. Complete harness: 35.671 seconds; container peak 115,912,704 bytes. Selected manifest hash: `3f20d5876d63c960c82acaf3de27dad612c98ccf18195f3173ae146991e51cd6`; all 17 batch hashes were observed in the throwaway harness output. The unchanged source hash, canonical replay and annotated quote geometry also remained valid.

Unique temporary database, private bucket and generated diagnostics were removed. Embedding/client and first-selection reviews, final affected suites/build and runtime-stage orchestration remain pending at this checkpoint. No final M2 gate is claimed.

Task 6 later checks: focused embedding/config/repository **51 passed**; embedding/config/jobs **45 passed**; latest embedding module including stale-worker denial, partial non-final batch rejection and configured-origin guards **19 passed**. RED demonstrated a short first batch could permanently occupy its immutable slot; selection now loads the full expected quartet/final remainder before comparing IDs. Safe embedding error codes are explicitly preserved by the job failure allowlist.

Production build and full backend after the partial-batch fix: **352 passed, 1 skipped**. The later stale-worker/origin cases passed focused verification; full final review closeout is still pending. First-selection review reports the partial-batch defect resolved with no remaining contract defect.

Independent next-task prerequisite: inspected the portable Qdrant 1.19.0 registry manifest and ARM64 platform digest. Added a private-network-only, 512 MiB, `processing`-profile service; the isolated project overrides storage to temporary memory and has no owner volume/host port. `compose config --quiet` passed and isolated Qdrant became healthy; actual restricted API container observed Qdrant version 1.19.0. No index/retrieval/publication behavior is claimed from service startup.

### Task 6 closeout

Client review reproduced malformed compressed HTTP responses escaping as raw decoding errors and arbitrary embed 400 responses mislabeled as context overflow. Both RED cases were corrected: sanitize HTTP request/decoding failures; inspect only the bounded error JSON and recognize the exact pinned context-limit error. No provider error text is stored or exposed.

Both embedding-client and first-selection re-reviews returned PASS. Latest focused embedding suite: **21 passed**. Final production build passed; full current affected backend: **359 passed, 1 skipped in 74.50 seconds**. Actual corrected client preflight plus real model embedding again produced the same valid 4,096-byte test vector/hash. The corpus's selected-byte replay proof above remains the Task 6 runtime evidence.

Task 6 is complete. Task 7's index identity/exact-membership RED cases are being added; its production index and publication are not implemented yet. No final G1–G6 gate or stronger M2 status is claimed.

## Task 7 implementation checkpoint — exact selected index and owned evidence

Implemented bounded Qdrant transport, full-profile UUID5 point identity, selected-byte artifact readback, acknowledged upsert, paginated exact owned point membership/payload/vector comparison, prepublication selected-vector source rehydration, and a frozen verification receipt. Publication rechecks current lease, active version, original/profile identity, all five prior manifest hashes, canonical counts and exact chunk/point hashes before the short atomic `ready/succeeded` transaction. Owned lookup authorizes and checks readiness/publication in PostgreSQL before embedding or Qdrant.

Consumer-visible failures observed and corrected during integration:

- Immutable artifact download rejects an already-existing destination: use a private temporary directory with a new destination, not `NamedTemporaryFile`.
- Provenance resolution owns its short transactions: end metadata reads before calling it, never nest the idle-connection boundary.
- The native golden paper exposed a multi-vector first-batch bug missed by the one-chunk fixture: prepublication search now decodes only the first validated 4,096-byte vector, not an entire four-vector batch as one vector. A permanent real PostgreSQL/MinIO/Qdrant multi-chunk regression exercises publication.

Latest focused command used the restricted isolated API test container with read-only `researcy` and `tests` mounts:

```text
python -m pytest tests/test_indexing.py tests/test_index_transport.py tests/test_owned_retrieval.py -q --tb=short -p no:cacheprovider
45 passed in 88.88s
```

The fixture exercises a real born-digital PDF, private original upload/readback, sandbox parser, canonical rows/chunks, all five prior manifests, private selected vector artifacts and a uniquely named real Qdrant collection. Tests cover wrong IDs despite equal counts, wrong vectors, missing/extra/foreign points, stale publication, incomplete checkpoints, denied foreign/unready lookup, poisoned payloads, canonical source rehydration and an actual HTTP 503 search dependency. Automated query vectors are deterministic; native model evidence is separate.

Actual native golden-paper smoke, exit 0: verified frozen `1706.03762` original SHA, 15 pages, 68 chunks, 17 native batches; selected vectors written privately and exact sets verified. Publication was deliberately withheld after Qdrant acknowledgement, then indexing was replayed in the same throwaway process with an identical selected-point set before atomic `ready/succeeded`. This proves the prepublication replay path, not a killed/restarted worker. The frozen scaled-attention question returned five real dense hits and included the exact expected gold phrase with original-source geometry on zero-based page 3. Observed top hit: page 3, cosine score `0.6891066`; second hit pages 3–4, `0.6525763`. Whole smoke: **38.903 seconds**. Foreign owner lookup returned indistinguishable `404`.

Observed selected manifest hash `106e616ca9824621e66eb5d441f3256dafa627365b786ef01262fbd2035b01ea`; exact point-set hash `e1626ddaef56b9e98f13ff4e1033c0bd7f6050aa95e130d6e4334a8cf2b68a7e`; chunk-set hash `3e9e4997c95d81652cd97f4e258a14c227fcc76c5e062d5fb3601fd05ff41144`. These are scoped smoke outputs, not identities for owner papers.

The smoke's unique database, private bucket and Qdrant collection were removed in `finally`; no owner source/session/job was changed. Final Task 7 reviews and full affected backend/build closeout remain pending. This checkpoint does not close final G1–G6 or promote M2 status.

Task 7 review checkpoint: owned lookup's publication point-set hash, canonical payload UUID, successful search envelope and cosine-score range gaps were reproduced RED and corrected. An additional JSON integer overflow (`10**400`) was reproduced, then safely rejected; the noncanonical UUID regression uses deterministic hyphenless text. Latest owned suite: **20 passed**; scoped re-review PASS.

The index-publication review remains open. Actual RED checks observed **11 failures, 2 passes** for incomplete parser artifact, unbound embedding manifest, concurrent equivalent collection creation, malformed nested Qdrant results, uncompleted payload-index acknowledgement and missing remaining-deadline propagation to storage. Fixes are being implemented; earlier 404-pass full-suite/build and native-golden success do not supersede these open contract failures. Task 7 is not complete.

Later Task 7 checks after index review fixes: **78 passed in 43.51 seconds** across indexing, transport, owned retrieval and immutable artifact suites. Real equivalent collection-create races replay safely; payload indexes wait for completed acknowledgement and are re-read; malformed nested responses fail safely; missing parser artifacts/unbound selected manifest hashes fail before indexing; actual slow-storage streaming aborts on its remaining deadline without a partial file.

The actual native golden-paper pipeline was re-exercised after these fixes, exit 0, **26.533 seconds**, same 68-chunk result and gold page-3 hit at score `0.6891066`; selected point replay then atomic publication and foreign-owner `404` all passed. Selected manifest `6cb8010ef50016c4ad836f9f6328c6807a9037bba864da9775bfb75959967b79`, point-set `2fb89e1c4d31e481753609af60ed16e3f8c9b17f64e6cebea6dd86e44153e684`, chunk-set `64445660a3390dd445342205c52a62143cc5add4ed3c1e65fd1f4597351c6c67`. Disposable resources were removed.

Final current production API build passed; full affected backend **424 passed, 1 skipped in 130.42 seconds**. Index-publication scoped re-review is still pending; these passing commands do not replace that review or the later real-worker/API/UI gates.

### Task 7 final scoped review and runtime proof

The exact-index review subsequently found three missing fail-closed checks: strict bounded prepublication hits, a local four-point scroll-page cap, and a fresh non-mutating collection schema check. These are implemented; a real collection regression removes a required payload index after upsert and confirms verification refuses publication. Strict hit validation rejects noncanonical IDs, foreign/malformed payloads, duplicate points, nonfinite/out-of-range scores and integer-to-float overflow. Regression UUIDs use guaranteed noncanonical hyphenless strings rather than probabilistic uppercase text.

Final review found two remaining malformed-envelope paths: non-OK search status and non-list terminal scroll points. Both were demonstrated with real selected-index/Qdrant setup: **2 failed, 18 deselected**, each failed because verification incorrectly accepted the corrupt envelope. After the four-line fail-closed correction, the final focused indexing/transport/owned/artifact suites returned **97 passed in 36.85 seconds**. The scoped index-publication re-review returned PASS, confidence 0.995; owned-evidence re-review also passed.

The actual native golden-paper path was rerun after the final corrections, exit 0, **26.361 seconds**: 68 chunks, 17 batches from pinned native Ollama 0.18.2/BGE-M3 F16, exact acknowledged selected-point replay, atomic `ready/succeeded`, exact frozen gold phrase/source boxes on original zero-based page 3 with top score `0.6891066`, and foreign-owner `404`. Selected manifest `14638d5a3e4e6215dc1810921dc2f94d9aa4baead65e95a031270026e98f2b56`; point-set `44f1360567fa7b93ac218064885eb59a662bd7280fc40865aec8c629df281672`; chunk-set `b59b94f305b3dc2e5ac35e1495774e8f7e9d75640cfa08a18743f3117e7baceb`. Disposable database, bucket and collection cleanup completed. This is same-process prepublication replay, not final worker kill/restart evidence.

Final reviewed production API build passed; full affected backend **443 passed, 1 skipped in 131.34 seconds**. Task 7 is complete. No G1–G6 acceptance gate or M2 status promotion is claimed; Task 8 starts with the real worker and bounded preflight.

## Task 8 implementation and real worker checkpoint

Implemented direct six-stage dispatch, a single-claim process loop, separate-connection heartbeat, stage/claim watchdogs, SIGTERM recovery, and credential-minimal `processing`-profile worker Compose service. Canonical/chunk writes remain bounded; embedding reads four chunks per page and fully selected replay performs no model call. Active lease cancellation terminates silent parser children and cancels asynchronous embedding, Qdrant and storage requests; private partial downloads are removed even on `CancelledError`.

Actual silent HTTP cancellation regressions were demonstrated RED for the absent client cancellation contract, then passed against real loopback HTTP servers. The native/Qdrant pair returned **2 passed in 1.18 seconds**; the later storage case also passed integrated checks. The real silent-child regression passed alongside parser/screening checks. Safe storage-probe cleanup was exercised against a stalled DELETE response, demonstrated RED before bounded presigned DELETE implementation.

The first actual default preflight failed safely with `FAIL: sandbox`: its default probe generator was missing, although supplied-probe unit checks passed. Added a default-journey regression, observed its failure, implemented the trusted one-page probe directly, and verified **15 preflight tests passed in 4.80 seconds**. Replaced an ineffective mocked-vector test with the existing real embedding HTTP fixture so malformed probe vectors actually reach the native-client boundary.

Actual isolated native-worker smoke after that correction, exit 0:

- Healthy `python -m researcy.ingestion.preflight --check` passed without changing queued job state; an unreachable native embedding origin returned only `FAIL: embedding`, also without changing the job.
- Launched the actual `python -m researcy.ingestion.worker` process over the frozen 15-page `1706.03762` original. Killed it with SIGKILL after the actual chunk checkpoint entered embedding.
- Started a replacement immediately; waited for actual PostgreSQL-time lease expiry without any expiry SQL mutation. It reclaimed generation 2/attempt 2 and reached `ready/succeeded`.
- Exact 68 chunk IDs/checksums, already sealed pre-embedding manifests, and original SHA remained unchanged. Actual native dense evidence returned the gold page-3 hit at cosine score `0.6891066`; foreign-owner lookup returned `404`.
- Replacement SIGTERM exited 0 without stderr. Recovery after replacement startup: **94.834 seconds**; whole smoke: **108.625 seconds**.

The disposable database, private bucket and only this smoke's scoped Qdrant points were removed; no shared collection or owner data was deleted. This is Task 8 worker recovery proof, not complete G1–G6 acceptance: HTTP intake, owner API/UI journeys and full resource/gold gates are still pending.

Independent worker/stage reviews then identified cancellation gaps during normalization input/sealing, unverifiable selected-artifact replay, old-stage deadline transition races, dependency-timeout classification and post-shutdown claim initiation. All eight corresponding regression cases were observed RED before the corrections. Focused post-fix verification/re-reviews and full affected build/suite closeout remain in progress; Task 8 is not yet complete.

### Task 8 closeout

All eight worker/stage review regressions passed in the final focused run: **58 passed in 36.80 seconds** across stage, worker, preflight, active-I/O cancellation and embedding suites. Scoped worker review PASS (0.98), stage review PASS (0.99), and preflight/Compose review PASS (0.98). `docker compose --env-file /dev/null -f compose.yaml config --quiet` and production API build passed. Full affected backend: **481 passed, 1 skipped in 125.67 seconds**.

The real native-worker kill/reclaim smoke was repeated after all review fixes, exit 0: healthy/default preflight and safe unavailable embedding did not mutate the queued job; SIGKILL after sealed chunks recovered only after actual database-time lease expiry; generation 2/attempt 2 reached `ready/succeeded` with unchanged 68 chunk IDs/checksums, pre-embedding manifests and original SHA. The same exact gold page-3 evidence scored `0.6891066`, foreign-owner lookup returned `404`, and SIGTERM exited cleanly. Replacement recovery **100.907 seconds**, whole smoke **113.056 seconds**; all disposable scoped resources were removed.

Task 8 is complete. Task 9 owner-scoped status/retry API remains pending; no HTTP-intake/UI gate, final G1–G6 completion or M2 status promotion is claimed.

Task 8 composition-root correction: the approved plan requires explicit worker-role startup, but the initial worker entry lacked that guard. An API-role startup regression demonstrated claim initiation before refusal; the entry now rejects any non-worker role before installing handlers or claiming. Focused worker suite **8 passed in 2.91 seconds**. The actual native-worker smoke above already used the credential-minimal worker role; its exercised processing behavior is intentionally unchanged.

## Task 9 owner-scoped API and persisted preparation

Implemented `GET /api/jobs/{job_id}` and revision-based `POST /api/jobs/{job_id}/retry`, shared safe preparation projection, and Library/detail job identity/revision/preparation. Existing intake replay continues returning the persisted current stage. Session, exact trusted Origin, CSRF and owned-job authorization precede bounded retry JSON parsing and quota mutation. Accepted retry returns 202; an old-revision replay returns the current snapshot with 200. SQL snapshots check owned publication identity before reporting complete.

Initial consumer RED: **17 failures in 4.46 seconds**, missing status/retry routes and paper preparation. Focused checks initially found test fixtures violating existing publication, lease and terminal-state constraints; fixtures were corrected rather than weakening production invariants. The inconsistent-ready projection case explicitly bypasses the deferred publication trigger only in its disposable test database, restores it, and verifies safe 503 responses. The normal complete case uses real selected embedding/index publication.

Actual same-origin HTTP journey: isolated Next.js at `http://localhost:4000`, private test API at `127.0.0.1:18001`, two explicitly labelled smoke identities with opaque sessions in a disposable database. Owned job GET 200; foreign and nonexistent jobs 404 with the same stable code; unauthenticated GET 401; malformed retry body without CSRF 403 before JSON parsing; first revision-0 retry 202/revision 1; exact revision replay 200/revision 1; owned paper detail 200 with matching job identity. No Google acceptance is inferred from these test-created identities.

That journey exposed a pending manual retry incorrectly projected as initial waiting when lifetime attempts were still zero. A focused assertion demonstrated RED (**1 failure in 1.47 seconds**); initial waiting now requires both zero attempts and zero retry revision. After restarting the isolated API, actual job and detail GETs through the Next.js proxy both reported **delayed**, revision 1. This fixture proves status/retry HTTP behavior only: its placeholder original was not processed and is not corpus or ingestion evidence.

Final focused job/security/Library/intake command: **57 passed in 21.11 seconds**. Production API Docker build passed; full affected backend: **509 passed, 1 skipped in 132.16 seconds**. The skipped opt-in real-network test is not ordinary network coverage. Scoped review remains in progress; no Task 9 completion, UI acceptance, G1–G6 completion or M2 milestone promotion is claimed yet.

Scoped projection review found two lifetime-boundary defects: persisted retryability still advertised an action rejected at exhausted attempts/generation/revision, and SQL did not bound the newly browser-exposed revision to an exact JavaScript integer. Four consumer/database regressions demonstrated RED (**4 failures in 1.70 seconds**). The shared preparation projection now uses the same three-counter eligibility predicate as retry admission. Forward migration `0004_m2_safe_counters` bounds all three bigint lifetime counters to `9007199254740991`; response revisions carry matching bounds, and preflight requires the new head. Historical `0003` migration is unchanged. Scoped re-review PASS (0.99).

After both test and production images were rebuilt, full affected backend: **513 passed, 1 skipped in 133.47 seconds**. The new migration was applied only to the disposable HTTP smoke database. Through the actual Next.js proxy, the exhausted-attempts terminal job, paper detail and Library all returned 200/failed/non-retryable; retry returned 409 `JOB_NOT_RETRYABLE` (`5585d86b-b7cd-4d8c-b674-872fc1793592`). Additional proxy probes: foreign-owner malformed retry 404 (`d2e63811-7a1a-43d4-882c-4cf7315c0e7a`), untrusted-Origin malformed retry 403 (`42be76b7-b018-4216-9238-57efe28a6a06`), exact accepted-revision replay 200/delayed (`651be758-be0c-4281-9cb8-583a4777a530`). Owner API/security review is still pending; UI and final milestone gates remain unclaimed.

### Task 9 closeout

Owner API review identified a PostgreSQL READ COMMITTED race: a retry's waited `FOR UPDATE` refreshed the job tuple after publication commit but retained the older publication subquery snapshot. A deterministic real-publication/HTTP-replay regression demonstrated **503 instead of 200** (1 failed in 3.59 seconds). Retry now locks the owned job first and projects job/publication in the following statement snapshot. Nonlocking GET still uses one consistent read. Scoped re-review PASS (0.97).

Final focused API/projection/security checks: **62 passed in 19.81 seconds**. Final production API build passed; full affected backend: **514 passed, 1 skipped in 140.63 seconds**. The disposable HTTP database and both smoke identities were removed, then only the isolated HTTP API was stopped; owner data and sessions remained untouched. Task 9 is complete. Task 10 UI and Task 11 six-gate acceptance remain pending; M2 remains `Planned`.

## Task 10 preparation UI — execution evidence, not closeout

Initial Library interaction RED: **5 failed in 193 ms** before processing controls/polling existed. Implemented central typed job/preparation contracts, shared coarse preparation copy and existing Library/detail integration. Background status reads preserve metadata, stop for completed rows, avoid identity polling, and use visibility/single-flight/revision guards. Scoped reviews subsequently found additional timer, foreground/search, logout and deferred-conflict races; Task 10 remains in progress until those corrections are reviewed and exercised.

Actual browser intake in a fresh disposable database/bucket, two labelled smoke identities: uploaded both frozen originals through the existing form and real same-origin HTTP boundary. Each persisted `queued`/`waiting`; unknown authors/year remained unknown. Source hashes later matched:

- `1706.03762`: `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`.
- `2005.11401`: `23e3249e9a1e75418d82efecab0ea8c4d033b89c93742f63208d47ce01f21233`.

Built and served Next.js 16.3.6 production at `localhost:4000` with API rewrite `127.0.0.1:18001` baked into the build. The first production launch lacked that build-time override and returned the safe initial Library error; no successful proxy journey is attributed to that launch. Rebuild with `API_INTERNAL_URL` produced the observed real surface.

Started the actual constrained worker only against the disposable UI database/private bucket, deliberately configured an unreachable native embedding origin, and observed real `preparing`, automatic `delayed`, then terminal temporary failures after five attempts. Both cooldowns were server-derived; one detail retry measured **112.1875×44 px**, disabled during cooldown, with per-second text `aria-live="off"`.

After actual cooldown expiry, keyboard-only Library retry (title → Tab → Enter) advanced revision 1 and displayed server-confirmed delayed state; the removed control restored focus to that paper's link, while the other paper retained its own failed action. A detail keyboard retry advanced the second paper similarly and restored heading focus. Restored the real pinned native dependency and restarted the same private worker: both reached `ready`/`complete`, **68/126 chunks**, **one publication each**, **six lifetime attempts**, **retry revision 1**. Dense attention top-five evidence included the expected page-3 phrase, score `0.6891066`. Original identities/checkpoints were not reset.

Observed production UI at **375/768/1024/1440**: Library waiting/failure and detail delayed states had one resolving main, zero horizontal overflow and no undersized measured non-prose controls. Screenshots were visually inspected. Navy 2 px keyboard focus appeared on retry; focused title/navigation survived actual status polling. Completed Library had no preparation status or Reader controls and made **zero API requests over 6.2 seconds**; completed detail still stated reading unavailable. Actual worker was stopped after both publications.

Visibility evidence is explicitly bounded: headless foregrounding of a spare tab left the document visible, so it is not native hidden-tab acceptance. Actual Chromium frozen lifecycle produced zero requests. Separately labelled **controlled main-world CDP visibility events** produced zero hidden status requests and immediate visible refresh. Initial isolated-world property injection did not affect React's document and was discarded as an invalid probe, not a production failure.

Intermediate frontend **53 passed across five files** after polite status and deferred visible-detail fixes; this is not the final affected-suite outcome. Subsequent consumer RED: **four Library recovery failures in 140 ms**, **three further Library recovery failures in 166 ms**, and **two detail conflict-recovery failures in 128 ms**. Independent corrections are in progress; final production rebuild, scoped re-review and browser checks remain required. No Task 10 completion or final six-gate/resource/security acceptance is claimed.

Further recovery review closed the timer/foreground/conflict/logout issues with consumer regressions; final affected frontend at this checkpoint: **65 passed across six files in 2.15 seconds**, production Next.js build passed (**7.45 seconds** combined test/build command). Two final logout regressions were observed RED (**2 failures in 119 ms**) before correction: a retry response suppressed during a subsequently failed logout left the row stale/busy, and logout-only disabling falsely labelled unsent retries as running. Suppressed responses now retain the existing canonical-refresh intent; failed logout reconciles that intent. Logout disabling is separate from actual retry request state. No additional retry API or polling abstraction was added.

Final detail scoped recovery review PASS (0.99). Final Library scoped review remains pending. On rebuilt production surface, a separately labelled controlled logout HTTP 503 retained both actual completed papers and rendered only safe sign-out guidance with one main. A later controlled failed-row injection did not complete its selector/browser sequence and is **not** acceptance evidence; no persisted job mutation or successful UI outcome is attributed to it.

### Task 10 closeout

Final quota boundary RED: one consumer failure in 110 ms showed a 429 deadline lost during failed logout. Existing 429 handling now runs before logout suppression; no extra state or abstraction was introduced. A separate two-job conflict regression passed **before** any production change: the newer retry start invalidates the older canonical read, which cannot consume the newer intent. That review hypothesis was rejected with observed evidence rather than adding unnecessary generation bookkeeping.

Final affected frontend: **67 passed across six files in 1.91 seconds**; isolated-origin production build passed (combined test/build **6.91 seconds**). Final scoped Library review PASS (0.96), detail review PASS (0.99). Rebuilt production surface retained two real completed papers with one main. A labelled controlled **main-world fetch-response probe**, not persisted processing evidence, exercised retry quota 429 during pending sign-out followed by logout 503: the retry remained disabled with its server-response cooldown, showed honest “Try again,” and safe wait guidance. Original fetch was restored and the actual persisted Library reloaded; screenshot inspected.

Task 10 is complete. Task 11 final six-gate, resource, containment and traceability acceptance remains pending; M2 remains `Planned`. Actual worker/HTTP/native/UI evidence above does not substitute for those remaining gates.

## Task 11 actual-stack acceptance — in progress

### Official arXiv intake and durable stage journey

Actual official `1706.03762` intake through production Next.js same-origin proxy returned **202**, edition `v7`, request `c673e5dc-0432-4bdd-ba03-8abb2fa6187b`, paper `4d1bb529-53e4-46c5-bb7a-d89720f9e76d`, document version `01c86577-f843-44c6-a6f2-7bc452ef0f48`, job `5f68bf26-3530-48aa-be49-74ef4ca71417`, persisted queued. The HTTP response was closed before worker startup; this proves independence after accepted intake, not a mid-upload disconnect experiment.

Started the actual constrained worker only on the disposable database/bucket. Observed all stages through actual status HTTP reads: `queued/pending → validating/running → parsing/running → normalizing/running → chunking/running → embedding/running → indexing/running → ready/succeeded`. Run elapsed **49.975 seconds**, 24 status reads, maximum latency **0.176633 seconds**. PostgreSQL afterward reported original SHA `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`, **2,215,244 bytes**, pinned model digest, **five sealed stage manifests**, **68 chunks**, **one publication**. Exact point/artifact-set and populated M1 upgrade acceptance are still pending.

Resource sampling during this run, with no concurrent test/build, recorded host swap **8350.19→8817.25 MiB** (growth **467.06 MiB**) and actual Docker memory/PID samples. This is not full resource acceptance: native allocation, host pressure, OOM/restart flags, cold loading and the prescribed warm two-corpus-paper/bounded-intake scenario remain unmeasured. Host RAM is 8 GiB; Docker VM reports 4,108,828,672 bytes.

### Owned frozen-gold dense evidence and exact source geometry

The known-hash frozen uploaded original produced actual native top-five attention evidence at zero-based **`page_index=3`**, physical one-based page **4** (printed footer **4**, no PDF page-label entry), bottom-left PDF user-space points. The earlier “page label 3” description was a reporting error, corrected after inspecting the unchanged frozen PDF; no gold record or source geometry was shifted. PostgreSQL range resolution yielded five verbatim source fragments with zero-based half-open Unicode offsets; each fragment satisfied `source_end − source_start = quote code points = character boxes`. Grouped source-line unions:

1. `[366.239105, 198.408936, 504.000000, 208.396423]`.
2. `[108.000000, 186.894409, 503.998383, 197.699036]`.
3. `[108.000000, 171.332947, 459.462646, 188.376282]`, including the fraction/equation fragments.

The annotated gold's first line rectangle extends approximately **1.499 points** below the exact returned character union; remaining grouped rectangles differ by less than **0.005 points**. A first naive fragment-only comparison omitted fraction fragments and was rejected as an invalid comparison rather than changing geometry. Private red-gold/blue-source rendering on the unchanged frozen PDF was visually inspected: correct region/column and complete quoted sentence, with raw per-character boxes preserved rather than stretched to match an annotation rectangle.

Actual foreign-owner and nonexistent-paper internal lookups both returned **404 `RESOURCE_NOT_FOUND`**; instrumentation observed **zero native-client constructions** for those denied calls. No Reader citation, dense Recall@5 qualification or answer-quality acceptance is inferred.

Remaining G2/G3/G4/G6 and full resource/traceability checks are pending. Private crash and selected-index fault harnesses are being prepared without execution or production changes; parent execution remains serial to preserve resource evidence.

### G6 containment defect found and corrected during actual smoke

The actual malicious-child `sandbox.run_pdf_child` probe under the deployed ARM64 Compose profile confirmed UID 65534, no service environment/parent private marker, no `/proc`, and no connection to a verified live parent listener. It also exposed a real gap: an invented child could write `/escape` inside the namespace's writable root. This was isolated namespace storage, not a demonstrated host-write escape; it nevertheless violated the bounded-scratch write boundary.

Permanent regression `test_child_writes_only_to_bounded_scratch_mount` was **RED**: `/escape=True`, `/tmp/scratch=True`. Minimal fix: `bwrap --remount-ro /` after mounting dependencies/devices and the separately size-limited `/tmp`. No parser/output fallback or fault flag was added. The same actual malicious-child smoke then observed outside-write **false**. CPU/output/memory limits returned `PDF_SCREEN_RESOURCE_LIMIT` at **1.007/0.089/0.099 seconds**; wall limit returned `PDF_SCREEN_TIMEOUT` at **0.302 seconds**; every failure removed partial parent output.

Affected deployed suites (`tests/test_parser_sandbox.py tests/test_screening.py tests/test_parser.py`, read-only source/test mounts, `-p no:cacheprovider`) passed **65 tests in 18.59 seconds**. An earlier command incorrectly named `test_document_parser.py` and ran no tests; it is not verification evidence. Production rebuild, total affected suite and remaining G6 intake/reaping/cleanup assertions are still pending.

### G6 actual same-origin invalid intake and proxy truncation correction

The production Next.js `:4000 /api/papers/upload` → isolated API `:18001` route rejected real corrupt/encrypted/image-only/101-page fixtures with safe JSON 422s. A **25 MiB + 10 bytes** PDF-prefixed body instead returned **500**, no JSON content type, 21-byte response. Actual production web log confirmed Next.js's default **10 MB** request-body buffering truncated the rewrite and the upstream connection reset. This was a real end-to-end boundary defect, not a mocked status response.

Installed Next 16.3.6 documentation specifies `experimental.proxyClientMaxBodySize`; set it to **26 MiB**, preserving the existing default API's 25 MiB PDF cap plus multipart overhead, without moving authentication/intake validation into Next.js. This is a transport buffer limit, not a second accepted-upload limit. Production rebuild and restart changed only the private port-4000 preview.

Repeated smoke initially hit the honest import quota on the prior UI fixture; no quota rows or owner policy were weakened. A distinct disposable fixture identity in the same private database then exercised all five actual cases:

| Input | HTTP / safe code | Safe request ID |
|---|---|---|
| Corrupt PDF-prefixed bytes | 422 `PDF_INVALID` | `1dc8620a-a4bb-4190-8e04-a0464dd46784` |
| AES-256 encrypted PDF | 422 `PDF_ENCRYPTED` | `1bbd67e3-ab93-44f4-a125-903585a71582` |
| Actual image-only PDF | 422 `PDF_NO_TEXT` | `00bffa0d-12f5-4046-bf42-48d80689f2cc` |
| Actual 101-page PDF | 422 `PDF_TOO_MANY_PAGES` | `a6b98a73-ff1a-4a2f-ae8a-ad1035bdb8ea` |
| PDF-prefixed bytes exceeding 25 MiB | 413 `PDF_TOO_LARGE` | `a55d77ff-a75c-43ea-84ab-383d6f4fcb43` |

Persisted document versions changed by **zero** across the successful rejection smoke. The result does not claim worker-entry corruption, full G6 cleanup/reaping or arbitrary larger-than-proxy-buffer safe handling.

Final post-sandbox-fix Linux affected suite passed **515 tests, 1 opt-in skip in 133.76 seconds**. Genuine production API target and production worker both rebuilt; the separately tagged test image was also rebuilt. Frontend suite passed **67 tests in six files** and production Next/TypeScript build passed (combined command **6.70 seconds**) after the body-buffer fix. Actual same-origin intake confirms the changed transport path independently of these suites.

### Resumed Task 11: populated M1, actual Compose crash and stale worker

Worktree recovery confirmed branch `feat-m2-durable-processing`, Task 1–10 commits through `e4eda60`, and uncommitted acceptance fixes; no reset, push, merge or owner-stack worker startup. Both delegated harness agents failed provider DNS (`daily-cloudcode-pa.googleapis.com`) without delivered gate evidence; their output is not counted.

Private fixtures copied and SHA-verified the already accepted official original from private storage, seeded an actual `0002_m1_source_guards` schema with paper/version/job/idempotency outcome, applied `head` twice, and checked unchanged identity/hash/byte count/private key/outcome and `queued/pending`. No owner database was upgraded.

Actual isolated Compose worker was killed with `kill -s SIGKILL worker` after four sealed prior manifests and 68 chunks. Heartbeat `2026-10-01 02:32:26.550987+00:00`, expiry `02:33:56.550977+00:00`: exactly the production 90-second interval. Replacement claim was observed only after that database-time expiry, generation/attempts **1→2**, then `ready/succeeded`, **one publication**. Ordered chunk ID/checksum hash and prior manifest hashes remained identical. The first reclaim sample was 53.541 seconds after replacement observation began, not a shortened lease: startup/command interval had already consumed part of the original 90 seconds.

Separate actual Compose pause/resume run kept A paused past its unmodified expiry. Initial B harness mistakenly inherited only the partial override and started Uvicorn; that interval is a harness failure, not worker evidence. B was corrected using the fully rendered production worker command/UID/read-only root/seccomp/capability/PID/memory/tmpfs profile. Actual B then reclaimed generation 2 and completed. A's saved generation-1 heartbeat returned false and `fenced_transaction` raised `LostLease` before admitting a statement. After unpausing A and observing 16 seconds, publication remained one and exact selected-content fingerprint was unchanged:

`03be977605970ce7fd96ba75fc2c1ac834d61593a590bd192df2979f028d94a5`.

Readback verified original SHA, five sealed manifests, **19 unique stored artifacts**, **17 selected batches**, exact ordered **68 chunks**, and actual Qdrant IDs/payload/normalized vectors. Each private gate database/bucket and only its three-key scoped points was removed after observation. Stopped run-owned `worker_b` container was removed explicitly; no orphan-wide prune.

### G3/G4 real selected-index fault replay and publication defect

A private process-boundary harness intercepted actual Qdrant requests only after they completed: first four-point upsert and final upsert acknowledgement. Replaying the sealed selected bytes produced the same receipt and exact 68-point vector/payload fingerprint; no publication existed before final verification. There are no committed production fault switches.

Initial fault run correctly kept missing/wrong-ID/extra/wrong-payload/wrong-vector cases terminal, but deleting a mapping from a chunk outside the top-five publication probe incorrectly reached **`ready/succeeded`**. Permanent real-store regression `test_corrupt_provenance_outside_search_probe_cannot_publish` was **RED**, `DID NOT RAISE IntegrityFailure`. Root cause: readback validated provenance only for search-probe hits, not the complete selected chunk set.

Minimal fix reuses `resolve_range` for each exact readback point, with one reused PostgreSQL connection and short per-chunk transactions; removed the now-redundant probe-hit provenance pass. No second validator, fallback, compatibility path or dependency was introduced. Affected index/transport suites passed **65 tests in 18.00 seconds**.

Actual post-fix worker `run_once` and separate real FastAPI HTTP service observed **seven** terminal integrity/non-ready cases: missing point, equal-count wrong ID, extra point, wrong payload, wrong vector, corrupted non-probe mapping and corrupted manifest. Each returned safe `PROCESSING_INTEGRITY_FAILURE`, no publication, and public retry **409 `JOB_NOT_RETRYABLE`**. Mapping/manifest injection temporarily disabled user triggers only in the disposable database; explicit operator restoration isolated each scenario, never public retry.

Actual unreachable Qdrant endpoint produced `indexing/pending`, `DEPENDENCY_UNAVAILABLE` (request `c44f7931-743f-4f84-b44b-a8026f2a1ca3`). Restoring the endpoint and waiting actual DB `run_after` allowed supported automatic retry to complete with one publication and unchanged selected point fingerprint. Explicit retry revision replay remains a separate outstanding G3 check; automatic recovery is not substituted for it.

### G6 worker entry and complete rotated/cropped processing

Privileged queued fixtures in a separate disposable database/bucket exercised the real worker entry independently of accepted intake: corrupt/encrypted/image-only/101-page/26-MiB inputs each ended terminal with the respective safe code, non-retryable, **zero chunks/publications**. Production `put_original` correctly rejected the oversize fixture before the worker; direct private-storage injection was explicitly used only to test worker defense, not treated as accepted intake.

Actual readable three-page PDF with rotations **90/180/270** and non-zero crop offset completed the entire native pipeline with one publication; each resolved fragment satisfied exact quote/source-offset/character-box cardinality. Final malicious-child smoke separately observed fork denial and reaped direct child/launcher, no network/secret/parent-file/outside-root write, bounded CPU/wall/output/memory failure and no partial output. A body exceeding the new 26-MiB proxy buffer also returned actual safe JSON **413 `PDF_TOO_LARGE`**, request `c5ef1018-6b5d-4567-8a09-98f4bcf0686f`.

All fault/security fixtures above were cleaned by exact private identity. Full post-publication-fix suite/build, final resource/browser checks and explicit-retry replay are still outstanding; M2 is not `Verified`.

### Explicit retry revision replay after actual terminal outage

Repeated private selected-index run exhausted all five real unreachable-Qdrant attempts using unchanged production backoffs and actual DB `run_after`; waited the final cooldown without mutating timestamps. Actual HTTP retry returned **202** for revision 0, **200** for its immediate duplicate, and **200** for delayed replay after the recovered job completed. Stored revision **1**, total attempts **6**, cycle attempts **1**, one publication, unchanged vector/payload fingerprint; no new cycle was created by either replay. Safe request IDs: `8b1dc021-fb4c-4e9b-8e95-aede91bb1050`, `35506357-bc6b-473e-93ab-c25bb6bb4d5b`, `9f22b49e-23f2-445b-819d-0ef14c4295e3`. All seven integrity cases also remained terminal/non-retryable in this run.

Fresh actual persisted Library screenshot after backend acceptance showed honest complete rows with no Reader action or preparation badge. At **375/768/1024/1440**, one main, no horizontal overflow, and reduced-motion media query true. This refresh does not replace the earlier actual keyboard/failure/retry journeys.

### Final production build and resource acceptance blocker

Post-publication-fix complete deployed Linux suite: **516 passed, 1 opt-in skip in 144.37 seconds** (149.09-second command). Production API, worker and web container builds passed, total **92.76 seconds**. No test/build ran concurrently with the subsequent measurement.

Actual inspection exposed missing PostgreSQL/MinIO/web memory ceilings in Compose. Applied the approved provisional **384/256/256 MiB** caps; existing API/worker/Qdrant remain **512/1024/512 MiB**. Applied caps only to the running private PostgreSQL/MinIO without restart and started private production API/web (`:4001`). Root owner ports/services were untouched.

Warm sequential actual corpus processing used the production worker profile and frozen original hashes:

| Original | Observed completion | Elapsed |
|---|---|---|
| `1706.03762`, `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697` | `ready/succeeded`, first attempt | 26.056 s |
| `2005.11401`, `23e3249e9a1e75418d82efecab0ea8c4d033b89c93742f63208d47ce01f21233` | `ready/succeeded`, first attempt | 36.478 s |

Concurrent actual bounded PDF intake through the capped production web returned **202 in 1.681 seconds**. Sixteen samples recorded host swap/pressure, Docker service usage, native `/api/ps` allocation, native process RSS and authenticated actual Library HTTP latency. Host RAM **8,589,934,592 bytes**; Docker VM allocation **4,108,828,672 bytes**, 8 vCPUs. Native pinned F16 model reported unified/model allocation **1,209,536,512 bytes**; peak sampled server/runner RSS total **232,592 KiB**, which does not establish unswapped physical allocation.

**RESOURCE FAIL:** baseline swap **8,413.31 MiB**, peak **9,672.00 MiB**, growth **1,258.69 MiB**, exceeding **512 MiB**. Recorded host pressure level **2** throughout; no critical-pressure claim is inferred beyond these sampled numeric values. Maximum authenticated Library latency **0.247077 seconds**. Post-run PostgreSQL/MinIO/API/Qdrant/web inspection: OOM false, restart count zero. Sampled maximum cgroup usage percentages: **52.44/93.94/11.80/80.73/24.27** respectively.

Measurement limitations: worker one-shot container name did not match the sampler's service-name filter, so worker+child peak/OOM flag was not retained; native cold load was not performed because the shared model was already loaded and no unload/restart was authorized. These remain missing evidence, not implied passes. No shared 9Router/model/owner application was stopped; no model/parser change or declared-machine increase was attempted.

Read-only audit of the actual official arXiv accepted version additionally verified original SHA, **19 unique stored artifacts**, **five manifests**, **17 selected batches**, ordered **68 chunks** and exact actual Qdrant IDs/payload/selected vectors. Its point fingerprint was `d7dbb2b45c5d8438c73c458e9e0a9e7d8440968384379548128ff26f6cd22253`.

**Delivery decision:** code/configuration is `Implemented`; M2 is **not Verified**. Task 11 remains blocked on resource prerequisite/acceptance and missing cold/worker-peak evidence. A later resource run requires a host environment meeting the approved prerequisite; this report does not authorize closing owner applications, changing the qualified model, or weakening the limit.

### Cleanup and blocked acceptance handoff

Stopped only private production API/web and the port-4000 host preview after recording evidence. Cleanup verified the exact acceptance database and bucket absent, removed **145 private objects**, and deleted only the **seven** document scopes' three-key-filtered Qdrant points. Labels were checked against run-owned fixture prefixes before removal; root owner resources were not accessed/mutated. No `down -v`, owner migration, publishing, merge, push or branch/worktree deletion.

The plan's Task 11 remains open: resource failure and incomplete worker-peak/cold-load measurement prevent final acceptance. Recorded successful fault/security journeys are not promoted into blanket gate or six-gate/resource acceptance. The approved model/runtime, M1 technical evidence and historical Q0 evidence are unchanged.

### Resource prerequisite remediation and complete rerun — 2026-10-01

The owner requested prerequisite remediation and a complete unchanged resource rerun. No product code, model, batching, sandbox, limits or machine budget was changed. Native desktop inspection/launch failed to address Activity Monitor (`BackgroundUnavailable`/`InputFailed`); read-only binary measurements were then used. No owner application was closed. Managed-browser cleanup found zero remaining managed tabs. Only the run-owned PostgreSQL/MinIO/Qdrant containers were restarted **before** measurement, reducing sampled idle memory from **151.8/195.6/409.2 MiB** to **65.36/105.1/206.7 MiB**. This released accumulated test-service memory; it does not establish sole causation for the later swap difference. All earlier failed runs remain historical evidence.

Frozen `/tmp` corpus copies were SHA-verified against the unchanged hashes above. A fresh private database/bucket and production API/web/worker images were used without build/test overlap. Web listener was restricted to private `:4001`; no owner-stack cutover. Observed Ollama `/api/ps` initially reported **`models: []`**: cold loading was natural, not forced unload/restart.

**Cold-load observation, reported separately:** exact `bge-m3:567m` embedding request with `truncate=false` returned 1,024 dimensions in **5.041280 seconds**, reported model-load duration **4.415989 seconds**. Five resource samples; swap baseline **10,257.44 MiB**, sampled peak **11,788.75 MiB**, increase **1,531.31 MiB**. An intermediate after-load sample alone would have understated the peak at 11,667.38 MiB; the retained maximum is used. Cold-start overhead is substantial and is not represented as a ≤512-MiB warm result.

**Warm gate: PASS against the unchanged approved criteria.** Warm baseline was taken after cold load and queued intake preparation. Actual production worker `run_once` processed the two queued frozen corpus papers serially; authenticated HTTP samples observed every processing stage and final `ready/succeeded`. Elapsed worker claims: **50.813667 / 73.291480 seconds**. Concurrent third PDF intake returned **202 in 2.206255 seconds**, request `1a2116ae-d38d-4c22-bc03-1114035af092`; it is intake latency, not a status-request measurement.

| Criterion | Observed |
|---|---|
| Warm swap growth ≤512 MiB | **11,786.00→12,046.25 MiB; +260.25 MiB** |
| Every recorded status/Library request <2 seconds | **147 requests; maximum 1.751655 seconds** |
| Native model identity unchanged | `bge-m3:567m`, F16, digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`; checked in all model samples |
| Native reported allocation / process resident target ≤2 GiB | **1,209,536,512 bytes** reported model allocation; sampled aggregate native server/runner RSS **710,688 KiB**; not summed as independent physical allocations |
| Non-critical host pressure | Numeric level **2** in every cold/warm sample; Apple's [XNU memorystatus documentation](https://github.com/apple-oss-distributions/xnu/blob/main/doc/vm/memorystatus_notify.md) describes 2 as Urgent/synonymous with Warning, below Critical 3; not claimed Normal |
| No warm OOM/restart | All six inspected containers: OOM false, restart count zero; existing service start times predate warm baseline; worker exited 0; native server/runner PID set remained unchanged |
| Worker-inclusive and service measurements | **50 warm snapshots**, worker present in **47**; fixed explicit worker-name filter |
| Same machine envelope | Host 8 GiB; Docker VM **4,108,828,672 bytes**, 8 vCPUs |

Sampled cgroup memory maxima (worker includes its sandbox descendants), not continuous instantaneous peaks:

| Service | Sampled MiB | Cap MiB |
|---|---:|---:|
| Worker + children | 76.46 | 1,024 |
| PostgreSQL | 151.40 | 384 |
| MinIO | 145.90 | 256 |
| Qdrant | 305.40 | 512 |
| API + intake child | 74.60 | 512 |
| Production web | 62.35 | 256 |

Command mechanism: `docker compose --env-file /dev/null -p researcy-m2-test` with the existing isolated override and task-private resource/ports overrides; production images only, `up -d --no-deps api web`; named one-shot worker `run --no-deps -T --name m2-resource-worker-rerun worker python -` executes two real worker claims. Sampler uses `sysctl kern.memorystatus_vm_pressure_level vm.swapusage`, native process RSS, `docker stats --no-stream --format '{{json .}}'`, native `/api/ps`, and actual same-origin proxy `/api/jobs/{id}` / `/api/papers`; final `docker inspect` checks caps/OOM/restarts/start times/exit status. No forced swap purge, reboot, service stop during measurement, synthetic model response, hidden failed-request exclusion or threshold change.

A preparation attempt lacking the CSRF cookie returned 403 before the warm baseline; corrected harness sent both session-bound CSRF cookie and header. This was a harness-auth failure, not a passing intake or a relaxed application boundary.

Cleanup verified the new private database and bucket absent, removed **54 objects** and only its **three** document scopes' filtered Qdrant points; stopped private API/web and removed the exited measurement worker and private overrides. Owner applications, 9Router, native server/model and owner data were untouched.

The prior resource blocker is resolved for the recorded warm-run criterion and missing cold/worker sampling evidence. Absolute swap remains high and cold-load cost remains recorded; this is not a claim of a pristine host or universally guaranteed fit. M2 remains `Implemented` pending full Task 11 gate/traceability closeout; this resource-only rerun does not silently promote every other checklist item to Verified.

### Task 11 final evidence reconciliation

Final explicit replay smoke compared ordered full JSON row snapshots for pages **15**, sections **62**, blocks **1,051**, spans **1,048**, chunks **68**, and chunk-span mappings **12,176** before/after actual selected-index replay and after publication. All six row hashes were unchanged; normalized actual Qdrant payload/vector fingerprint was unchanged. Original document-version UUID/SHA remained stable and publication count was exactly one. Native top-five gold retrieval and foreign-owner 404 were also observed in this final actual run. Its uniquely created DB/bucket/collection were removed in `finally`; the added throwaway script was removed.

This actual smoke completed in **42.225 seconds**. Ordered chunk-row SHA `b929fa20b7cf053834c19d6c6bbe69d8e6a53da9d8e3d616ab0a1d08ad794f20`, mapping-row SHA `7e757b5ddedef5ca3499d59249d88689c44be413e4a9fe1f968e459a3d723897`, and normalized Qdrant fingerprint `0ff2e4b4fd0bf525f82e8b32e5acc6c1256248a141ccd4652829f69ffad4546a` were stable across replay. These are isolated-scope fingerprints, not replacements for historical corpus results.

This closes the explicit full mapping comparison gap rather than inferring it from point counts. It supplements the actual partial-upsert/final-ack-loss and delayed explicit-retry-revision replay evidence above, not substitutes a same-process replay for crash/lease recovery.

Source page convention is now explicit: gold `page_index=3` is zero-based and refers to physical/printed page **4**. Master/child shorthand “page 3 region” is interpreted as the frozen gold index, not a reason to shift offsets/boxes or rewrite historical Q0 evidence. The first annotation rectangle's 1.499-point excess remains recorded; exact source-character boxes were not widened to match an annotation envelope.

Final independent publication/security review and resource-evidence review both **PASS**, no blocking findings. Reviewers verified full-set scoped provenance, short transactions/fencing/deadlines, bounded writable scratch, exact resource threshold semantics and source measurements. They ran no additional tests/builds or host actions.

| Final gate | Observed result / evidence above |
|---|---|
| G1 | PASS: official 202 intake, every durable stage to ready, immutable original/artifact audit, populated M1 schema upgrade twice unchanged |
| G2 | PASS: actual SIGKILL and actual pause/reclaim/resume; unchanged 90-second lease, generation fencing, one publication, selected external bytes stable |
| G3 | PASS: actual partial/final-ack faults, full ordered canonical/mapping and normalized vector comparison, explicit revision replay after completed retry without new cycle |
| G4 | PASS: seven actual integrity failures terminal/non-ready/non-retryable; transient outage recovers via supported retries |
| G5 | PASS: frozen-hash native top-five gold evidence, exact scoped offsets/character boxes and correct indexed page/column; annotation-envelope difference and page-index correction explicitly retained |
| G6 | PASS: actual intake and worker invalid/resource inputs, containment probes, bounded failure/reaping/no partial publication, native rotated/cropped success |
| Resource | PASS for unchanged warm criteria; separate cold-load cost retained, sampled peaks not continuous maxima, pressure Warning/Urgent not Normal |
| Browser | PASS: persisted states and keyboard/retry journeys, four widths, one main/no overflow, reduced motion; controlled injections labelled separately |
| Suites/build | 516 backend passed / 1 opt-in skip; 67 frontend passed; production API/worker/web builds passed |

**Current delivery decision: M2 `Verified` in the isolated implementation worktree.** All preceding in-progress/blocker statements are dated checkpoint history, superseded by this reconciliation; historical failed measurements remain visible. No owner schema/data/worker action was executed: every mutable gate fixture used uniquely named private databases/buckets and scoped collections/points, subsequently cleaned. This is technical milestone verification, not owner-stack cutover or M1/OAuth verification. No push, merge, prune or Reader/public-retrieval/citation claim is included.

### Owner manual acceptance and publication authorization

The owner reported completing manual testing with all results good, then explicitly requested project shutdown, cleanup, commit, push, PR creation and merge into `main`. This is an owner-reported acceptance outcome; no additional per-case IDs/screenshots are invented. The manual `researcy-m2-manual` stack was stopped without deleting volumes or its accepted paper data. Shared native Ollama/9Router and unrelated projects were not stopped.

Fresh pre-publication verification on the feature worktree: deployed Linux backend **516 passed, 1 opt-in skip in 156.04 seconds**; frontend **67 passed**, production Next.js/TypeScript build passed (**7.75 seconds** combined frontend command). `git diff --check main...HEAD` passed. Temporary test infrastructure is separate from preserved manual/owner storage and will be stopped after merged-tree verification.

Next.js-generated untracked `apps/web/AGENTS.md`/`CLAUDE.md` and the main checkout's pre-existing `next-env.d.ts` change are retained rather than silently deleted, stashed or folded into M2. Feature/remote audit history and worktree artifacts remain preserved. Prior “not authorized/published” statements above describe their checkpoints; this explicit authorization supersedes the publication restriction, not owner-stack cutover or M3 scope.
