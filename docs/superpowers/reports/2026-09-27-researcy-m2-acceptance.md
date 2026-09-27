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
