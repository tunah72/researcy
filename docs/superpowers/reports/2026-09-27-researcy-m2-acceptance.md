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
