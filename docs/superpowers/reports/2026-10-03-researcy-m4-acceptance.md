# Researcy M4 execution and acceptance evidence

## Approval and isolation — 2026-10-03

Owner approved both documents, then explicitly selected Gemini primary, schema-aware qualification, null/unavailable monetary provenance, M1 prerequisite exception, and isolated stack/native runtime with at most twelve hosted attempts on public papers. Main database/worker/cutover, shared gateway restart and publication/push/merge/prune are not authorized. Master revision 2.3 records M4-only amendment. M4 is Planned, not Verified; M1 stays Implemented.

Worktree `.omp/worktrees/m4-discovery-agent`, branch `feat-m4-discovery-agent`, base `5abffbc`. Root modified next-env/context artifacts and all retained worktrees preserved. Only requested Phase A documents copied byte-identically into worktree.

Isolated Compose project `researcy-m4-acceptance`, private override `/tmp/researcy-m4.private.yaml`, `--env-file /dev/null`, ports PostgreSQL55434/MinIO19004/Qdrant16334/API8004/web3004. New project volumes, no owner mounts. Existing frozen test image `researcy-m3-api-test:local`, source directory mounts only. Initial whole-/app mount hid image .venv; `No module named pytest` was harness failure, not RED. Corrected mounts preserve frozen interpreter.

Baseline: `docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml run --rm --no-deps -T api python -m pytest tests/test_generation_config.py tests/test_schema.py -q -p no:cacheprovider`: **39 passed in1.27s**.

## T1 metadata and scoped ledger

RED same isolated command `tests/test_discovery_repository.py`: **9 failed in4.69s**; missing abstract column/Discovery package. Real temporary PostgreSQL and selected-index ready fixtures executed; no unavailable dependency disguised as RED.

GREEN `tests/test_discovery_repository.py tests/test_intake.py tests/test_preflight.py`: **47 passed in19.74s**. Missing/unusable title precedes readiness/reservation; foreign/random symmetry; attempt cap, terminal CAS, active slot/expiry and twenty/hour quota; unknown abstract remains null; affected import/preflight behavior preserved.

Actual throwaway callable smoke via isolated container `python -` created a uniquely named PostgreSQL database, applied Alembic head twice with source rows between, compared unchanged paper/version identities, reserved/counted initial attempt, interrupted, rejected late completed CAS, observed missing-metadata error. Result **PASS**, **3.65s** command wall time. Synthetic isolated source (not real ready ingestion), zero provider calls. Database removed in finally; no owner DB migration. This smoke is not Discovery real-provider or Add→ready acceptance.

## Gate ledger

G1–G7 not yet closed. T2/T3 implementation follows T1 frozen contracts; controller owns T4 integration. Controlled outputs will remain labelled; no provider acceptance claimed by deterministic tests.

Hosted attempts: **0/12**. No actual provider/model availability, usage/tariff, semantic recommendation relevance, browser Discovery journey or explicit recommendation Add→ready observed yet.

### T1 additional required concurrent boundary

Two independent psycopg connections/barrier raced one owner reservation. Focused regression `tests/test_discovery_repository.py::test_concurrent_requests_reserve_one_owner_slot`: **1 passed in2.84s**; exactly one reservation and one DISCOVERY_RUN_ACTIVE, one active ledger row.

## T2 role/pass transport contracts

RED `tests/test_discovery_output.py tests/test_generation.py`: **48 failed,98 passed in35.93s**, absent decoder/output stream arguments; existing transport tests available. Controller authorized GREEN before agent production changes.

GREEN affected full transport/Reader suites `tests/test_discovery_output.py tests/test_generation.py tests/test_generation_config.py tests/test_reader_agent.py tests/test_reader_parser.py tests/test_reader_stream.py tests/test_reader_citation_publication.py`: **239 passed in118.20s**. Frozen test runtime as above.

Actual callable smoke used four controlled real loopback HTTP SSE requests: Discovery search, stop, reasons and Reader refusal. Production GenerationClient decoded each caller adapter into the expected output type, retained usage total18, exactly one physical local request per case. **PASS**, command4.78s; hosted calls zero. This is transport smoke, not application graph/natural provider/semantic acceptance. Controller review checked required schema/adapter, strict whole-object decoder with per-model strictness and preserved Reader JSON-array→tuple behavior, terminal accounting/deadline/backpressure boundaries unchanged; no compatibility alias retained. Language server unavailable; agent literal/AST consumer inventory migrated all consumers.

## T3 RED evidence

`tests/test_arxiv_search.py tests/test_arxiv.py`: **66 failed,115 passed,1 skipped in5.63s**. Missing metadata query/search/async limiter plus observed held-request cooldown-state and zero-origin pacing bugs. Existing real-network test opt-in skipped. Controller authorized GREEN; implementation/checks pending.

## Native prerequisite observation

Started authorized native Ollama port11434; existing approved bge-m3:567m package digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`, F16. Public synthetic readiness input returned dimension1024, L2norm1.0000003406892946,13prompt tokens. `ollama ps`:100% GPU,1.2GB,context4096. No pull; startup unused cleanup reported zero removed blobs. This is native readiness only, not container connectivity/processing/resource acceptance.

Frontend frozen dependency install through node:22.14.0-alpine3.21 `npm ci`:178packages,0auditvulnerabilities. No frontend suite/build yet.
