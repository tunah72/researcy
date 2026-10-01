# Researcy M3 execution and acceptance evidence

## Authorization and isolation — 2026-10-01

Owner approval: “Tôi phê duyệt specification và implement plan.” Both approved documents include the named decision permitting M3 work while M1 remains Implemented. M3 is Planned; no gate is claimed passed.

Controller: GPT 6.1 Sol. Execution worktree `.omp/worktrees/m3-reader-agent`, branch `feat-m3-reader-agent`, starting commit `cca8a9d`. Root modified Next-generated artifacts and untracked draft copies remain untouched. No reset/stash/push/merge/prune or owner-data cutover.

Actual setup command: `git check-ignore .omp/worktrees/m3-reader-agent && git worktree add .omp/worktrees/m3-reader-agent -b feat-m3-reader-agent cca8a9d`. Worktree created. Git reported clonefile optimization fallback to plain checkout; this did not prevent creation.

LSP status: no language servers configured. Source discovery/references will therefore use scoped literal searches until a server is available.

Private Compose project `researcy-m3-acceptance`, override `/tmp/researcy-m3-private.yaml`, explicit `--env-file /dev/null`. Fresh project-labelled network and PostgreSQL/MinIO/Qdrant volumes were created; only postgres, minio, minio-init and qdrant started. Private ports PostgreSQL 55435, MinIO 9003/9013; API/web not yet started. Owner/root projects and workers remain untouched.

Focused test harness reuses M2 restricted test image with current worktree source/tests/migrations mounted read-only. This is a test execution optimization, not evidence of a rebuilt M3 production image. Host/runtime constraints and exact deployed profile remain inherited.

## Execution order and contract review

Tasks T1–T9 execute serially per approved plan. Shared ready-scope loader belongs to T1 and is consumed by T3/T4/T5/T7; T4 performs final search_owned caller cutover. T2 geometry utility is consumed by T8 exact overlays. T3 schema is shared by citation/run/stream tasks. T6 supplies strict product transport to T7. No parallel shared-file/schema edits.

No interpretation changes the master, model, two-pass ceiling or any real-route gate. Actual generation endpoint/credentials/usage/tariff remain unverified prerequisites; Reader work is reachable independently.

## Current gate ledger

G1–G7: not run. No M3 gate is passed by document approval, M2 evidence or this setup. Historical Q0/Q0.1 and M1 technical status unchanged.
