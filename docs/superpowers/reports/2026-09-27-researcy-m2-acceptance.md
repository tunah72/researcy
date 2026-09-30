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
