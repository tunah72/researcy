# Researcy M4 execution and acceptance evidence

## Approval and isolation — 2026-10-03

Owner approved both documents, then explicitly selected Gemini primary, schema-aware qualification, null/unavailable monetary provenance, M1 prerequisite exception, and isolated stack/native runtime with at most twelve hosted attempts on public papers. Main database/worker/cutover, shared gateway restart and publication/push/merge/prune are not authorized. Master revision2.3 records the M4-only amendment. Final gate reconciliation below establishes M4 Verified on the isolated stack; M1 stays Implemented. This is not authorization or evidence for owner-stack cutover.

Worktree `.omp/worktrees/m4-discovery-agent`, branch `feat-m4-discovery-agent`, base `5abffbc`. Root modified next-env/context artifacts and all retained worktrees preserved. Only requested Phase A documents copied byte-identically into worktree.

Isolated Compose project `researcy-m4-acceptance`, private override `/tmp/researcy-m4.private.yaml`, `--env-file /dev/null`, ports PostgreSQL55434/MinIO19004/Qdrant16334/API8004/web3004. New project volumes, no owner mounts. Existing frozen test image `researcy-m3-api-test:local`, source directory mounts only. Initial whole-/app mount hid image .venv; `No module named pytest` was harness failure, not RED. Corrected mounts preserve frozen interpreter.

Baseline: `docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml run --rm --no-deps -T api python -m pytest tests/test_generation_config.py tests/test_schema.py -q -p no:cacheprovider`: **39 passed in1.27s**.

## T1 metadata and scoped ledger

RED same isolated command `tests/test_discovery_repository.py`: **9 failed in4.69s**; missing abstract column/Discovery package. Real temporary PostgreSQL and selected-index ready fixtures executed; no unavailable dependency disguised as RED.

GREEN `tests/test_discovery_repository.py tests/test_intake.py tests/test_preflight.py`: **47 passed in19.74s**. Missing/unusable title precedes readiness/reservation; foreign/random symmetry; attempt cap, terminal CAS, active slot/expiry and twenty/hour quota; unknown abstract remains null; affected import/preflight behavior preserved.

Actual throwaway callable smoke via isolated container `python -` created a uniquely named PostgreSQL database, applied Alembic head twice with source rows between, compared unchanged paper/version identities, reserved/counted initial attempt, interrupted, rejected late completed CAS, observed missing-metadata error. Result **PASS**, **3.65s** command wall time. Synthetic isolated source (not real ready ingestion), zero provider calls. Database removed in finally; no owner DB migration. This smoke is not Discovery real-provider or Add→ready acceptance.

## Gate ledger

Final G1–G7 reconciliation is recorded below. Actual Gemini qualification, official metadata/no-import integrity, explicit Add→ready, production browser observations, final suites/builds and targeted reviews are recorded with their environments. Synthetic identities and controlled faults do not establish Google OAuth acceptance or promote M1.

Hosted attempts: **8/12** — seven Discovery passes and one Reader regression pass. No further hosted request is planned for final safety verification.

### T1 additional required concurrent boundary

Two independent psycopg connections/barrier raced one owner reservation. Focused regression `tests/test_discovery_repository.py::test_concurrent_requests_reserve_one_owner_slot`: **1 passed in2.84s**; exactly one reservation and one DISCOVERY_RUN_ACTIVE, one active ledger row.

## T2 role/pass transport contracts

RED `tests/test_discovery_output.py tests/test_generation.py`: **48 failed,98 passed in35.93s**, absent decoder/output stream arguments; existing transport tests available. Controller authorized GREEN before agent production changes.

GREEN affected full transport/Reader suites `tests/test_discovery_output.py tests/test_generation.py tests/test_generation_config.py tests/test_reader_agent.py tests/test_reader_parser.py tests/test_reader_stream.py tests/test_reader_citation_publication.py`: **239 passed in118.20s**. Frozen test runtime as above.

Actual callable smoke used four controlled real loopback HTTP SSE requests: Discovery search, stop, reasons and Reader refusal. Production GenerationClient decoded each caller adapter into the expected output type, retained usage total18, exactly one physical local request per case. **PASS**, command4.78s; hosted calls zero. This is transport smoke, not application graph/natural provider/semantic acceptance. Controller review checked required schema/adapter, strict whole-object decoder with per-model strictness and preserved Reader JSON-array→tuple behavior, terminal accounting/deadline/backpressure boundaries unchanged; no compatibility alias retained. Language server unavailable; agent literal/AST consumer inventory migrated all consumers.

## T3 RED evidence

`tests/test_arxiv_search.py tests/test_arxiv.py`: **66 failed,115 passed,1 skipped in5.63s**. Missing metadata query/search/async limiter plus observed held-request cooldown-state and zero-origin pacing bugs. Existing real-network test opt-in skipped. Controller authorized GREEN; completed implementation evidence follows in the T3 section below.

## Native prerequisite observation

Started authorized native Ollama port11434; existing approved bge-m3:567m package digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`, F16. Public synthetic readiness input returned dimension1024, L2norm1.0000003406892946,13prompt tokens. `ollama ps`:100% GPU,1.2GB,context4096. No pull; startup unused cleanup reported zero removed blobs. This is native readiness only, not container connectivity/processing/resource acceptance.

Frontend frozen dependency install through node:22.14.0-alpine3.21 `npm ci`:178packages,0auditvulnerabilities. Later suite/build evidence is recorded below.

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

## T5 explicit Reader interaction and review

RED Node22.14 container command `npm test -- src/components/related-papers-interaction.test.tsx --maxWorkers=1`: **6 failed**, absent Related control. Implemented typed same-origin bodyless search helper, metadata-only region/cards, explicit canonical Add with per-payload retained keys and serialization, cooldown/cancel/unmount handling, historical/unready gate, and existing Library preparation link. The first focused combined run had **20 passed,1 failed** because the test asked for the whole page's single alert while the independent PDF load-error alert was present; scoped the assertion to the labelled Related region. No product error concealed.

First full web suite: **119 passed in40.90s**. Three additional cooldown/pending-Add-navigation/unready boundaries: focused **9 passed in1.42s**.

Independent Reader review identified source eligibility changing without remount/abort, omitted PAPER_NOT_READY guidance, and lost keyboard focus after a focused Cancel control disappears on error. New consumer regressions reproduced gate abort=false and misleading not-ready fallback (**2 failed,9 passed**). Reader keys now include active version and stage; cleanup aborts and clears stale discovery on gate change. Added safe processing guidance; error/missing restores trigger focus only when focus has fallen to body, preserving a user working in the composer. Final full web suite through `node:22.14.0-alpine3.21 npm test -- --maxWorkers=1`: **124 passed in37.80s**,12files. Existing PDF.js Node legacy-build warning remains; no lint configured or claimed.

Actual production browser and Add→ready proof is recorded below. All earlier test discovery/import responses are controlled consumer boundaries, not hosted/provider/public-PDF processing evidence.

## Actual isolated production and approved primary qualification

Production build: `docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml -f /tmp/researcy-m4.production.yaml --profile web --profile processing build api web worker`: **PASS**,93.44s. Frozen uv production install; Node22.14 / Next16.3.6 `npm run build` compiled, TypeScript and generated routes passed. Image manifest lists: API `d54dd114db6b99cd8cf281fa7bba49c671411e5632ed73ce60ee00020c9d07e1`, worker `f17237d289302b5cd3de9e3123cdef13e393340872f2c08b26e510e07d1d851c`, web `1a6cc8a679f03cc307a63ceec824fc0cf3c8e7c412298fe95e9df55d58454c26`. These identify the pre-final-review snapshot, not later fixes.

Started only isolated API/web; ran Alembic head twice. Synthetic A/B identities issued with existing `issue_session`; no real Google sign-in claimed. The authorized generation credential was passed opaquely as one child-process environment variable, no owner .env inheritance/expanded Compose output. Product route direct HTTPS Google OpenAI-compatible endpoint, configured and echoed `gemini-3.8-flash`, existing low reasoning/schema-aware policy; no gateway/fallback/standalone generation probe.

Imported public source `1706.03762` via actual same-origin web intake:202,7.44s, request `681e0711-0582-4cb8-8075-8b6292c5dd65`; original v7, paper `25d2ae5e-7e61-4623-97e8-ea3ffdaf0bde`, immutable version `4d238dad-30ce-4dfd-bfdc-aeb5a5cea848`. Isolated worker native preflight **OK**; real worker advanced queued→indexing→ready. No owner worker/database touched.

Actual primary campaign, sequential application POSTs with a conservative remaining-call guard before each dispatch:

| Case and evidence class | Safe request ID | Generation / metadata-search / returned | Latency ms | Prompt / completion / total terminal tokens |
|---|---|---|---:|---|
| Public original metadata, actual Reader keyboard Related → actual Gemini search/reasons | `8cf4889b-3097-4aa7-ba8d-dab75bd3df19` | 2 / 1 / 3 | 5791 | 1835 / 148 / 2052 |
| Actual Gemini stop, explicitly controlled nonscientific stored metadata (restored afterward) | `e2d5e7cd-d2b4-4293-9fad-92e1f499429c` | 1 / 0 / 0 | 3030 | 164 / 13 / 328 |
| Actual Gemini schema-aware containment, explicitly controlled hostile instructions appended to official abstract (restored) | `676aaaa8-d69c-454a-88dd-bf025c7dc332` | 2 / 1 / 3 | 5333 | 1967 / 129 / 2209 |
| Subsequent actual Gemini valid run with original public metadata | `c78998b7-077c-474a-ac02-696618890482` | 2 / 1 / 3 | 5551 | 1835 / 154 / 2088 |

All completed; configured and echoed primary identity match. Every successful metadata branch:10 inspected/10 unique/0 invalid/0 duplicate, one physical official query/no redirect,3 returned canonical IDs `2202.09741`, `2105.02358`, `2601.15305`; active ID not among returned ten. No prohibited import/query/URL/owner/filter branch, no repair/automatic retry. Adversarial input is a controlled fixture with actual provider outputs, not a naturally malformed provider-negative claim. Controlled invalid-output negatives remain separate T4 evidence. Exact owner-scoped paper/version/job/import-idempotency rows and private original/artifact object-key-hash + ETag + content-SHA256 sets unchanged before explicit Add and again during hostile/subsequent qualification.

Manual semantic review of all nine reasons against official supplied abstracts (fresh official id-list XML): title-topic connection and abstract support **PASS** for each; no invented numerical result/experiment, fabricated missing abstract, PDF-reading/full-text citation claim. First two candidates are attention-related vision extensions, not language-model papers; third is directly related long-context attention. This is the approved bounded relevance rubric, not a universal quality/ranking claim. Compatible total_tokens may include dimensions not equal to prompt+completion; terminal values recorded unchanged. Monetary remains null: documented tariff known, project billing and billable-unit attribution unverified under approved exception.

Owner explicitly selected `2601.15305` in the choice UI. Keyboard Add in its actual returned card made one real intake POST202 (35.099s); UI showed **Saved to Library · Waiting for processing**, then View in Library. New paper `4fcd41cc-7659-4db8-9fb0-d3804e2ec48f`, version `b17ac0ec-400c-49aa-8d7a-bf9ee62d9813`, job `11ebfe21-8051-4604-982f-6323b7822f88`, original v1. Actual private PDF + worker/native embedding/Qdrant publication reached ready; request `d55349d1-27aa-444c-b791-ed38aedec904` observed ready, real15-page PDF rendered in Reader (three canvases). Same exact browser key/payload replay200 preserved all authoritative rows and object hashes; fresh-key canonical-existing Add200 preserved same paper/version/job and object hashes. No second PDF/version/job created.

Actual web HTTP boundaries: foreign/random indistinguishable404, hostileOrigin403 before work, unsigned401, body/query422, controlled missing-title409 with no new hosted call. Request IDs include foreign `440c51dd-cbb5-4caf-8bc6-16eba782e5d8`, random `aaa95b73-fe16-4ea2-b0fe-cabdbe0cf48c`, hostile `df0c638a-56ff-46d0-88bc-9e3a164e3b0a`; private errors no-store. Missing-title live UI showed safe usable-title guidance, trigger focus restored; metadata restored afterward.

Actual browser widths375/768/1023:one resolving main,0 page overflow, no composer/Related mounted, honest size boundary. Widths1024/1280/1440:one main/one composer/Related,0 page overflow; measured Related/card/link targets44px minimum height, visible focus, metadata wrapping and separate scroll/composer. Actual Add result measured all controls44px tall at1280. Reload/navigation never generated: persisted M4 attempts stayed7. Controlled browser-network empty/error/cancel states each required an explicit action, three intercepted requests, zero backend/hosted dispatch; safe error hid injected raw diagnostics and Cancel returned focus to Search again. These remain controlled UI evidence, not natural empty/provider failure.

Additional actual Reader regression within the same authorized hosted ceiling: one hosted initial-answer pass, no follow-up/repair, persisted completed and terminal usage3777/74/3851. Keyboard Citation1 opened exact accepted quote/page1/PDF overlay; Escape closed evidence and restored Citation1 focus; one main/composer preserved. Total hosted campaign **8/12**:7 Discovery +1 Reader regression. Conservative reserved upper bound11; no further hosted call authorized beyond the original twelve. Browser session is synthetic; no Google OAuth gate inferred.

Disclosed environment/tool issues: first original-PDF browser GET503 during shared load; an actual later GET returned PDF and explicit Reload PDF rendered canvases. No product suppression or automatic retry added. Browser cookie helper failed despite partial mutation and dropped HttpOnly; corrected using raw browser cookie API and inspected names/attributes only. Browser wait helper imposed30s despite larger requested waits; pending Add/Reader were observed to finish later, not re-submitted. Initial manifest script used nonexistent `metrics` column and then attempted JSON UUID serialization; read actual ledger `usage`, scoped by owner and serialized UUID safely. Harness errors are not production/provider failures or gate proof.

## Full backend checkpoint and final-review regression work

First full frozen backend suite: **932 passed,1 skipped,1 failed in1061.17s**. Failure existing normalizing-stage regression: sandbox parser `PDF_PARSE_TIMEOUT` under30-second test deadline during concurrent build/native processing. No code/test timeout was weakened. Fresh host observation afterward:27%free,12072.44MiBswap used. Shared pressure is a plausible contributing cause, not proven sole cause. With builds/qualification/real processing finished, exact failed test **1 passed in6.70s**. A started full rerun was intentionally cancelled when new backend review defects arrived; its container was observed absent, and it is not full-suite evidence.

Independent backend review raised cancellation after committed attempt/search/completion, loss of disconnect monitoring during publication, response-header/failed-arXiv measurement gaps, unsafe bidi reasons, request-shape precedence and declared-body bounds, and missing safe attribution log fields. Four new boundary regressions reproduced4failures, including unexpected500 after disconnect and success publication during disconnected send; committed markers were missing from in-memory metrics. These were repaired and final verification is recorded below; the earlier primary campaign remains actual evidence for its explicitly identified snapshot.

### Final safety checkpoint — 2026-10-04

Second targeted backend review reproduced six failures: duplicate response-start after a post-header publication timeout; pre-header arXiv connect failure reported as known physical request; missing partial duplicate/inspection counts; unsafe bidi abstracts accepted by import (two cases); and crash-expired ledger usage missing explicit unknown provenance. Fixed at publication, producer, and measurement boundaries. Callback-only tests were removed in favor of failed-run ledger and import/no-PDF consumer regressions.

Focused final candidate command `tests/test_discovery_api.py tests/test_discovery_agent.py tests/test_discovery_repository.py tests/test_arxiv_search.py tests/test_discovery_output.py`: **185 passed,2 failed in151.67s**. All new review regressions passed. The two failures were real-socket fixtures with a150ms whole-client budget: header case never reached server request observation; redirect case timed out after only its first hop. Fixtures now give1s aggregate test budget (production60s limit unchanged); redirect responds immediately at first hop and blocks second hop, so timeout still proves the parent deadline spans redirects. Exact four socket variants then **4 passed in4.38s**.

Final review requests on the original reviewer model failed with usage-limit errors and provide no review verdict. Targeted review resumed on the active parent model. Isolated worker stopped, preserving volumes, before the final full backend suite; no owner services or native runtime were stopped. Final suite/build/smoke results remain pending and are not inferred from previous images.

## Final amended M4 gate reconciliation — 2026-10-04

Final full frozen backend command: `docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml run --rm --no-deps -T api python -m pytest tests -q -p no:cacheprovider` — **963 passed,1 skipped in465.69s**. Isolated worker was stopped during this run; no builds or new processing ran concurrently. The skipped test is opt-in real-network arXiv coverage, not a failed gate. Final frontend source is unchanged since the recorded full **124passed** run.

Metadata review correctly noted that an immediate first redirect did not distinguish budget reset. Strengthened the local socket fixture: each of two hops responds after0.6s, each individually within the1s test budget, together exceeding it. It must timeout504 rather than complete after a reset. Combined strengthened regression plus throwaway actual Uvicorn/HTTP graph smoke: **2 passed in4.91s**. Smoke observed bodyless search→three exact selected IDs and stop→empty, response/header request-ID equality, no-store, ledger completed2/1/3 and1/0/0,3real local generation requests/1controlled official metadata request, unchanged authoritative paper/version/job/idempotency rows. Hosted0. Safe search request ID `f6136e84-020c-4c27-82c8-4708e95b8188`.

Final throwaway Uvicorn actual HTTP/TCP fault/security matrix: **1 passed in5.54s**. Observed unsupported fetch-PDF action rejected with zero tools, upstream503/429 safe failure, socket disconnect→interrupted→explicit successful stop, aggregate timeout504, missing-title409, owned queued-paper409 PAPER_NOT_READY, random404, hostileOrigin403, wrongCSRF403, persisted twenty/hour quota429 and revoked synthetic session401;6real local generation requests,0metadata searches,0hosted. No-import exact authoritative row comparison passed before fixture-only queued-paper/quota setup. First matrix run used an incorrect503 expectation for unready; actual409 matched the approved spec/shared loader. Corrected the throwaway assertion, not production behavior. Both smoke files were removed; temporary fixture databases clean up through existing isolated fixtures.

Independent final PublicationSafetyReview and MetadataSafetyReview both returned **no actionable findings** on the active parent model. Static reviews did not run tests or provider calls. Original reviewer-model quota failures are not verdicts.

Final production build (same three-file Compose invocation recorded above): **PASS**,15.80s; web layers reused the already successful identical-source production compilation, API/worker rebuilt final source. Manifest lists: API `f0b9be526ac99797b107fa92b526e4ad4e4744ac7e8add732057a71de1e57281`, worker `ce8b5389d9fcab1b7fd4700f021f6edd8c32e51c40256e1b703d9d9e3b02ac1f`, web `6f52d08597df3496a99ce9c7a43acc031be882a2e49714ef7bd5d5c7922df5e9`. Restarted only isolated API/web using the retained opaque credential; no environment/expanded Compose secret output.

Final production browser reload at1280: original public PDF rendered3canvases; one main/one composer/no horizontal overflow; persisted prior cited answer and idle Related control remained visible. No Related search or Ask generation was submitted. Same-origin malformed query422 INVALID_REQUEST and wrongCSRF403 CSRF_REJECTED both no-store, safe request IDs `25aba69b-3ec7-4f71-bd06-d990d095f971` and `b0392f28-7674-40ab-86dc-8330e37ac286`. Discovery persisted totals stayed7generation calls/4runs before and after. Fresh screenshot observed; proof tab closed. Harness initially used nonexistent `/papers/` web route and unsupported locator.count; corrected to declared `/library/` route and DOM inspection without production changes.

Final rebuilt-worker native preflight `python -m researcy.ingestion.preflight --check`: **OK**. Restored only isolated worker with preserved volumes. Full isolated API/web/processing stack remains available; owner services/data unchanged.

| Gate | Outcome and evidence scope |
|---|---|
| G1 security/metadata/limits | PASS: actual same-origin A/B/foreign/random/Origin/unsigned/body/query/missing-title probes; final real HTTP unready/CSRF/quota/revocation; deterministic concurrent-slot/expiry and cancellation-boundary coverage. Synthetic identities only. |
| G2 approved primary role | PASS: actual direct Gemini search/reasons, stop, controlled hostile-metadata containment and subsequent valid output;7Discovery physical hosted calls. Controlled malformed rejection separately observed through actual local HTTP transport/graph; no natural malformed-provider claim. |
| G3 official metadata/no import | PASS: actual official10entry/10unique/≤3selected responses,9reason manual review, exact Library/provenance/object-set integrity. Controlled empty-feed and malformed/conflicting metadata coverage remains labelled controlled. |
| G4 explicit Add→ready | PASS: owner-selected actual returned2601.15305, keyboard Add, real immutable PDF/job/native worker/Qdrant ready, persisted Reader; same-key and existing-canonical replay preserved identities. |
| G5 production browser | PASS: recorded actual supported/small widths, keyboard/focus/citation regression, actual Add/saved/processing/ready; controlled empty/error/cancel distinguished; final rebuilt production reload/no-dispatch/security/visual proof. |
| G6 failure/accounting | PASS: final actual local HTTP malformed/503/429/timeout/TCP disconnect/slot release; arXiv real-socket header/body/drip/redirect deadlines and cancellation, conflict/partial-count/unsafe-Unicode regressions; approved-primary actual usage/latency with monetary-null provenance. |
| G7 suites/build/review | PASS: full963passed/1opt-in skip backend,124passed frontend, final production3image build, native preflight, actual changed HTTP/browser paths and two final targeted no-finding reviews. |

**M4 Verified in the authorized isolated environment.** This closure supersedes earlier in-progress checkpoints, not their historical observations. Limits remain: no real Google OAuth acceptance/M1 promotion, no natural empty or naturally malformed schema-enforced provider claim, no 9Router hosted alternative qualification, no billed-cost attribution, no new resource-capacity gate, no owner cutover/publish/push/merge/prune. Primary hosted evidence belongs to the recorded pre-final-review image; final safety changes are proved by focused regressions/full suites/local HTTP/final production smoke, not a second paid campaign. Hosted total remains **8/12**. No secrets, private source evidence or temporary smoke code are committed.

Additional final accessibility observation on the actual1280px Reader: visible header/main button/link/heading/paragraph/label foreground-versus-effective-background contrast scan had no ratio below4.5; disabled-state exceptions were not used to conceal a failure. Chromium native `emulateMediaFeatures` observed `prefers-reduced-motion: reduce` true,0active animations and1main. High-level media emulation returned accepted options but did not change matchMedia; reported tool inconsistency and used native browser emulation instead. Proof tabs closed; no generation action.
