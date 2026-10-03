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

## Monetary source investigation — fresh official documentation

[Google Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing), fetched2026-10-03, explicitly lists gemini-3.8-flash. Standard paid USD per1M tokens through2026-12-31: input0.75, output including thinking3.75, cached input0.075; paid/free/batch/flex/priority differ. The applicable model tariff is therefore **documented**, not unavailable. Project billing tier and per-request billable-unit attribution have not been observed; no billing-account access is authorized. Terminal compatible usage and actual charge must not be conflated. Retain monetary null with that precise provenance unless fresh campaign evidence supports a scoped estimate; never assert zero/free or use an unrelated model tariff.

Populated pre-M4 smoke: initial throwaway script used a nonexistent guessed predecessor name; Alembic rejected before population, temporary database still removed in finally. Read actual migration down_revision `0006_m3_lexical`, corrected script. Actual upgrade0006→0007 twice with populated original source/version/job/import-idempotency rows: **PASS**,3.18s; exact identity rows unchanged and legacy abstract null. No owner migration/network/provider. Additional Atom-summary import/replay regression prepared; runs after T3 source stabilizes.

Shared-host prerequisite observation, not resource acceptance: `memory_pressure -Q && sysctl vm.swapusage`:29%free,12314.62MiBswap used. Earlier M2/shared-host limitations retained; no new capacity gate claimed.

## T3 implementation and observed runtime boundaries

Affected search/arXiv/intake/io-cancellation plus new summary test checkpoint: `tests/test_arxiv_search.py tests/test_arxiv.py tests/test_intake.py tests/test_discovery_metadata.py tests/test_io_cancellation.py`: **215 passed,1 skipped,2 failed in17.44s**. Both failures were controller's newly written summary fixture, not product error: acquisition passes transport=None to client factory; test factory also supplied transport=MockTransport, duplicate keyword caused safe500. Replaced that fixture's transport entry, retaining other actual arguments. Focused summary tests then **2 passed in2.01s**, present normalized Atom summary/absent-null atomically persisted through real import/PostgreSQL/MinIO; exact replay IDs/object set preserved and no second acquisition. This is controlled external HTTP + real intake storage, not actual arXiv PDF/provider qualification.

Controller review checked separate nonreentrant request/state locks, cancelled queued lease ownership,3-second shared pacing/cooldown, same aggregate deadline across redirects, fixed host/path/query containment, bounded1MiB/XML and first-ten-entry inspection/conflicts, full official summary comparison and no PDF/feed-link calls. Import regression cases above passed; process-local limiter matches single API process contract.

Actual throwaway local-socket driver smoke: stalled body timed out504 and cancellation closed the active response; each followed by one healthy explicit request, same production limiter, no late extra request. **PASS**,7.97s; controlled remapping transport preserves official-host validation, hosted0.

Actual official API smoke, public title `Attention Is All You Need`, abstract absent/title-only query (not scientific-reason acceptance): **10 inspected entries/10 unique/0 invalid/0 duplicate/1 physical request/0 redirect**,2.31s. Observed canonical IDs `2202.09741`, `2105.02358`, `2601.15305`, `2306.05427`, `2508.17807`, `2209.10464`, `2212.08151`, `2609.08574`, `2302.04542`, `2406.13770`. No provider/PDF/import; no relevance verdict inferred from the ID list.

## T4 bounded application graph

RED endpoint cases: **11 failed in18.63s** against missing route404;12 graph fixture-dependency errors excluded from RED. Imported the required existing fixture dependencies into graph test module; separate graph run **12 failed in18.11s**, genuinely missing implementation after real ready fixtures setup.

Implemented bodyless owner/CSRF/Origin-protected POST, source/ready/config checks before reservation, one ASGI receive owner, bounded joined database operations, acyclic initial→search→reasons graph, authoritative first-three identity equality, no repair/fallback, terminal CAS and safe partial/unknown usage with physical-count uncertainty rather than zeros.

Initial scoped integration **33 passed in49.23s**. New aggregate deadline regression reproduced **500/interrupted**, while both real initial/follow-up provider-socket disconnect tests passed; root cause timeout cancellation classified as user interruption and its cancel flag suppressed JSON. Corrected deadline-vs-client distinction and timeout publication guard. Scoped API/graph/repository suite **36 passed in57.18s**.

Private pre-reservation error cache test then reproduced missing no-store header (**1 failed in2.57s**). Route now reuses existing APIError handler and adds no-store for its errors without changing global conventions. Focused private-error + separate-role quota/history-scope regressions **2 passed in4.85s**; running Reader reservation does not block Discovery or forward its private turn into generation context.

Actual throwaway Uvicorn HTTP application smoke, synthetic session and controlled real HTTP generator + controlled metadata transport with real PostgreSQL/MinIO/Qdrant-ready fixture: search→three authoritative results, stop/empty, missing-title no charge/no-store, random404, hostileOrigin403 before body, invalid URL action zero tools, actual TCP disconnect→interrupted→new explicit success. Exact owner paper/version/job/import-idempotency rows and original/artifact object-key-hash+ETag sets unchanged. **PASS**, final command6.92s;6physical local generator requests,1controlled metadata request,hosted0. Safe search request ID `87af4757-ebec-4d05-80ea-03eef807fe89`,2passes/1search/3results,78ms; cancel request `cfadc5cc-ca9d-46b8-803a-1a889f9c2ab2`,1pass/0search/interrupted,41ms. First smoke scaffold incorrectly encoded the already-bytes Settings.session_lookup_key; diagnosed actual type and corrected scaffold, not product. Temporary DB/bucket/collection/server cleaned in finally. No natural provider, browser or actual native-processing gate inferred.

Controller review: ownership precedes body/provider/quota; source snapshot/version rechecked; strict initial completed output gates tool; selected canonical ID set/order gates publication; no Reader history/retrieval/import in graph; DB operations joined under socket deadline even on repeated cancellation; terminal accounting persists before response; actual socket cancellation releases owner slot; known/partial/unknown usage and monetary-null provenance honest. Remaining full-stack/provider/UI/fault-matrix acceptance belongs T6.
