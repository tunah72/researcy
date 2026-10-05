# M5 implementation and acceptance evidence — 2026-10-04

## Decision

M5 is **Implemented, not Verified**. The owner now temporarily accepts M5 for conditional integration despite unfinished quality and authorizes the operations below. This is an owner decision, not a passing acceptance-gate result, human factual rating or evidence that main has already been published, migrated, started or tested. Failed/missing frozen cases remain in denominators. Q0/M2/M3/M4 historical evidence is unchanged.

The original approval covered isolated startup, public intake/processing/native warm and at most 36 primary hosted attempts. The latest owner decision additionally authorizes stopping/cleaning M5 processes, commit, branch push, PR creation/merge into `main`, local-main synchronization, and main project startup/manual testing including forward migrations and processing. **No additional hosted calls are authorized.** Preserve the worktree, private corpus/evidence/ledgers, volumes and remote audit branch; process cleanup is not data deletion or worktree pruning. Actual integration/cutover results must be appended only after observation.

## Environment and implementation

- Worktree `.omp/worktrees/m5-research-agent`, base `74444f3`, branch `feat-m5-research-agent`.
- Compose project `researcy-m5-acceptance`; private env `.omp/runtime/m5-acceptance.env`; private override `.omp/runtime/m5-acceptance.private.yaml`. Every Compose operation includes all three.
- Origin `http://127.0.0.1:3305`; API `58005`, PostgreSQL `56435`, MinIO `59005/59006`, Qdrant `56335`. Database `researcy_m5_acceptance`; bucket `researcy-m5-originals`.
- Frozen Linux Python 3.12 API/worker and Node 22.14.0 production web builds; native Ollama 0.18.2, approved BGE-M3 digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
- `0008_m5_research`: immutable selected-source pins, owner-scoped run/idea/citation persistence, bounded owner reservation/lease and same-transaction accepted publication.
- Research graph retrieves only active plus 1–3 explicitly selected ready papers. Strict schema and exact canonical raw quote/page/boxes; one permitted pre-delta validator repair, no transport/action/scope repair, third pass, source widening or automatic fallback.
- UI restores persisted run state without generation, keeps active Discussion separate from displayed PDF, and exposes labelled hypotheses and accepted-only citations.
- Evaluator verifies frozen bytes and actual owner/paper/version/profile bindings, reserves attempts before dispatch, separates parser/retrieval/citation/role/product/cost metrics, and requires actual browser evidence and human ratings rather than inventing them.

## Automated verification

| Check | Observed |
|---|---|
| Full restricted Linux API suite, excluding separately executed host evaluator | 1,068 passed, 12 skipped, 1,351.32 s |
| Frozen host evaluator suite | 48 passed, 0.08 s; existing SWIG warnings |
| Real PostgreSQL/MinIO/Qdrant scientific-upload binding regression | 1 passed, 8 deselected, 3.74 s after reproduced source-identity RED |
| Full frozen Node 22.14.0 frontend suite | 149 passed, 14 files, 57.85 s; existing PDF.js Node warnings |
| Final readiness suite after canonical Gemini catalog ID correction | 28 passed, 6.14 s after one representative RED failure |
| API/web/worker production images | Built successfully by actual startup runs |

The Linux suite excludes host evaluator locking because the parser seccomp policy denies `flock`; the policy was not weakened. Host npm was not the installed Linux dependency platform and failed missing Darwin Rollup; checks use frozen Linux Node instead. No lint success is claimed.

Focused RED→GREEN defects include hidden forbidden suffixes before repair, delayed reservation clearing newer Discussion evidence, wrong citation source prefix/version acceptance, cancellation/restoration interaction, upload/arXiv edition binding and unsafe startup override/resource limits. Independent GPT 6.1 Sol reviews cover graph, UI, gold and metrics; source reviews are not human hosted-output ratings.

## Actual startup and readiness

Executed:

```bash
bash scripts/demo-up.sh --project researcy-m5-acceptance \
  --env-file .omp/runtime/m5-acceptance.env \
  --override .omp/runtime/m5-acceptance.private.yaml
```

The initial run built production images, quiesced only the isolated worker, applied migration twice, verified private object write/read/delete, Qdrant schema and Linux sandbox, warmed the approved native model/vector, and started API/web/worker. It exited nonzero on final readiness; private volumes were retained.

Actual health was HTTP 200 (`e899bda9-edd7-41d3-ae13-6ffa3fa4ee26`); web returned HTTP 200. Readiness was HTTP 503 (`38b93d1b-93e7-4491-a156-dc4ae2f9d6ef`) with all local dependencies verified but generation access unavailable. Safe catalog diagnosis returned HTTP 200, 61 records and the exact provider ID `models/gemini-3.8-flash`. Readiness had compared the short generation-request name; this was corrected only for the Gemini catalog representation, without changing configured route/model or adding fallback.

After correction, actual in-container `/ready` returned HTTP 200 (`0b2ff705-927c-4b85-b714-126cc72a63cc`) with native loaded and catalog accessible; generation execution explicitly remained unverified. A real isolated API/web restart reproduced immediate connection failures: Compose process startup is not HTTP readiness. Startup now waits at most 120 seconds for API health and web reachability, then performs one dependency check. A subsequent startup reached web/liveness but correctly failed unavailable catalog access rather than declaring qualification. A separate production `_catalog` diagnostic returned accessible in 0.662 seconds. These observations demonstrate variable access, not continuous availability or causal diagnosis of every transient failure.

## Real intake and resource limitations

Nine frozen originals remain private, with manifest digest `91e6f258dbcbe3023f3331b8a5794d55f8fc0160c6066f3bfa1dbc25ced92664` and annotation digest `9590fe3c24aa7ec8aece5cd18ad56c3435c284cbbe66c4262c341337efcd3147`. Gold was frozen before hosted output; independent AI raw-source review is labelled as such.

Eight explicit hash-identical uploads were accepted. Uploads do not fabricate arXiv metadata. External Attention upload returned HTTP 422 `PDF_SCREEN_TIMEOUT` (`fc65931f-2951-4c37-9843-68ec8fde1bf0`). A separate explicit official `2105.02358v2` acquisition timed out at the client; authoritative state subsequently proved it had persisted the exact frozen bytes as an arXiv paper. No duplicate retry was sent.

Authoritative outcomes:

- Seven sources ready/succeeded: two Q0 scientific papers and five labelled controls.
- `2105.02358v2`: failed parsing, `PDF_PARSE_TIMEOUT`, resource-limit failure, not retryable, two attempts.
- `2202.09741` upload: failed embedding, `PROCESSING_INTERRUPTED`, temporary/retryable, five attempts.

No parser deadline, worker attempt limit, model, seccomp policy or resource cap was relaxed to pass these inputs. Shared-host sample during ingestion: swap used **13,145.56 MiB / 14,336 MiB**, memory pressure level **2**. This is a point sample and disclosed host limitation, not attribution to one service or a renewed M2 capacity claim. These failures block six frozen Research cases and Discovery baselines; missing sources are not replaced or removed.

## Actual local measurements

The private throwaway observer used real canonical spans/geometry, native embedding, Qdrant, PostgreSQL FTS, production RRF/packing and production selected-source retrieval. Gold was applied after ranking, never injected into query/prompt. One earlier observation attempt failed at the lexical dependency boundary; it did not establish a metric. The completed observation retained the full frozen denominator:

- Resolvable parser regions **58/67**; text coverage **4,135/5,357** code points; sections **21/67**; reading-order relations **12/12**. Parser acceptance false.
- Q0 fresh dense/fused/packed Recall@5 **6/8**: the approved original-case fused nonregression floor is met. Fresh PostgreSQL FTS Recall@5 **1/8** is a weak lexical measurement, not a separately specified 6/8 lexical gate. Historical lexical was BM25: no equivalence claim.
- Paired packed premise recall **1/14**, with 12 missing sets because required sources were unavailable. Retrieval acceptance false.
- Actual observed hit tuple identity **138/138**, scope errors **0**. This does not waive missing cases or establish hosted factual support.

## Actual hosted qualification

Configured primary: direct Gemini OpenAI-compatible endpoint, `gemini-3.8-flash`. No 9Router/model fallback. Private application-endpoint evaluator performed five cases, serially. Attempt ledger: **7/36 charged attempts**, five settled reservations, terminal cleanup observed; no uncertain reservation outstanding at this checkpoint.

| Case | Actual terminal state | Calls | Accepted citations | Safe request ID |
|---|---|---:|---:|---|
| R5, controlled insufficient pair | failed safely, `RESEARCH_INSUFFICIENT_EVIDENCE` | 1 initial | 0 | `3b71fdb9-31cd-465f-ab65-c5f13b333a25` |
| R6, controlled hypothesis premise | completed, 1 idea | 1 initial | 1 | `0093ec85-0550-4b50-a1a5-da2a59a6cd6e` |
| E1, Reader answerable baseline | failed, `EVIDENCE_UNRESOLVED` | initial + repair | 0 | `6e5f5264-df4b-4309-9e26-fed9c995fe34` |
| E2, Reader unanswerable baseline | refused | 1 initial | 0 | `32294004-aac5-4861-a91e-be1f4f5a88a6` |
| E3, Reader answerable baseline | failed, `EVIDENCE_UNRESOLVED` | initial + follow-up | 0 | `ea601924-6327-4734-a41a-26c217ad2eb8` |

R5 usage 592 input / 47 completion / 639 total; R6 702 / 191 / 893. Research responses echoed the configured model, observed response/dispatch true, no repair. E1/E3 exact-evidence failures remain failures; no approximate/page-only fallback or gold tuning was introduced. All aggregate quality results remain unaccepted; every factual output still requires human 0/1/2 review. Monetary estimate stays null/unavailable; no claim of zero/free cost or authoritative account tariff mapping.

## Actual same-origin security and browser

Two real opaque-cookie sessions for synthetic isolated users were issued through existing session code. They are **not Google OAuth evidence**. Anonymous Library returned 401; foreign and nonexistent private papers returned indistinguishable 404/code `NOT_FOUND`. Empty/self/duplicate Research selection returned 422, nonexistent selected resource 404. Authoritative Research reservation count was zero after those invalid-selection requests, before hosted cases.

Later actual missing-CSRF and untrusted `http://localhost:3305` Origin mutations returned403 `CSRF_REJECTED` (requests `5ba94852-ab39-4436-8b63-acf4f0e5acad`, `e2c449e3-fa47-418c-a94a-162c9d9788a7`). Research run count remained2, the two intentional hosted cases. The unused second session naturally expired; it first returned401, not an ownership verdict. A fresh synthetic session for the same isolated owner then received404 `RESOURCE_NOT_FOUND` for both the foreign accepted citation and Research run (requests `c15c6e4b-4dcc-4465-8438-c3c11cadfd45`, `6df30b3f-1e17-44fc-ae18-3d07562e50fc`). Owned citation GET returned200 (request `7a1b744a-ddb1-4e21-a901-ef3e16054f8d`), page1/273boxes.

Production Chromium, no request interception:

- Real Library and Reader originals loaded from persisted server state.
- Citation-free related-PDF URL restored Attention page 2 while Discussion remained RAG; header/download identified the exact related immutable version. Return-active removed related hints, restored RAG, preserved unsent composer and focused H1.
- R6 result GET/reload restored the persisted accepted idea without generation. Actual citation GET rendered **273 exact character boxes**, restrained ochre highlight on page 1, and the matching Evidence quote. Fresh screenshot visually inspected after waiting for `.pdf-evidence-box`.
- Escape removed evidence, retained page 1 and the unsent composer, and returned focus to Premise citation 1.
- Real Library selection displayed failed sources disabled, allowed keyboard Space to select ready papers, capped at three, and disabled a fourth. Selection labels measured 69–126 px high in the observed state.
- Widths 375/768/1023/1024/1280/1440: one main landmark and no horizontal overflow; below 1024 no hidden Reader action buttons. Observed desktop buttons were 44 px high. Reduced-motion emulation used.
- One earlier browser operation hung and the managed tab was killed; later distinct persisted-citation/selection journeys succeeded. Managed successful tabs were closed. No claim of full browser gate, contrast audit, both-source accepted jump, rotation/crop qualification or live full product journey.

## Gate reconciliation and remaining prerequisites

| Gate | Status |
|---|---|
| G1 security/state | Recorded synthetic two-owner selection/security plus actual TCP quota/active/expiry/late-publication/recovery checks passed; genuine Google remains G5, not implied |
| G2 scoped canonical evidence | All9frozen sources ready and exact native tuples; five new hosted results/seven exact accepted citations reload verified; required split-source quality/journey still unestablished |
| G3 bounded hosted route | 18/36attempts,16settled,0uncertain; all8Research/3Reader/2Discovery primary cases observed, but Reader failures, R2insufficiency, missing split-source support/human ratings and Discovery0recommendations keep qualification failed |
| G4 failure/recovery | Controlled actual TCP six fault→same-owner-valid pairs plus bounded transport/schema/repair/CAS evidence passed; no hosted fault fabrication |
| G5 Google/product/browser | Genuine Google callback previously failed400 `redirect_uri_mismatch`; owner subsequently reports a configuration fix, not full G5 acceptance. Official Related→explicit Add→ready→Research remains unaccepted; restored selection/result/canonical navigation/reload does not establish the full journey |
| G6 separate metrics/cost/demo | Parser and Q0 floors pass; paired2/14 fails; human ratings missing. Four warm/populated startups succeeded, historical failure preserved; approved monetary-null provenance remains a limitation, not a blocker |
| G7 suites/build/review | Retained-source API/web/worker production build/startup passed; final backend247passed/20host-ledger-seccomp failures, documented host evaluator61passed, frozen Linux frontend149passed. Targeted source/evaluator reviews recorded; mixed-environment limitation explicit, not a fabricated all-green container suite |

No missing gate is converted to partial credit. Paired retrieval failure, actual Reader evidence failures, missing split-source factual support/Discovery result journey and human/OAuth evidence remain explicit blockers. Further paid retries, source replacement, limit changes or main-stack operations are not an acceptance remedy implicit in this report.

## Final runtime and reproducible scoring checkpoint

The final populated entrypoint run built images, applied migration twice and passed sandbox/storage/Qdrant/native warm, then failed at Compose API/web/worker startup after298.03s. Safe authoritative Compose state showed API/worker running and web created, not running. The transient startup cause is not established; host pressure is not asserted as the cause. Explicit same-project/env/override web-only `up -d --no-deps --wait --wait-timeout 120 web` completed successfully. After that recovery, actual API health200 request `28275c9f-d203-4a0b-980f-b4051209735e`, internal production web200, readiness200 request `2213ed58-a253-4a54-b815-36de644351d4`. Native was naturally cold at this later observation; identity verified, catalog accessible, generation execution still unverified. No shared-native unload/reconfiguration was performed. A successful read-only checkpoint does not retrospectively turn the failed startup command into success.

The runbook offline command was actually exercised from `apps/api` with `--root ../..`:10local observations, exit1/acceptedfalse. Consolidated local+hosted scoring retained14distinct cases, exit1/acceptedfalse. Text-free public evidence is [qualification summary](../../../qualification/m5/results/2026-10-04-isolated-summary.json); private originals, responses, bindings, sessions and ledger remain ignored. The result preserves missing cases and monetary-null/human/OAuth limitations rather than claiming acceptance.

## Owner-requested gate remediation

The subsequent populated entrypoint (`bash scripts/demo-up.sh --project researcy-m5-acceptance --env-file .omp/runtime/m5-acceptance.env --override .omp/runtime/m5-acceptance.private.yaml`, bg60) exited **0 in38.94s**. Production images, migration twice, private storage verification, Qdrant/sandbox, approved native identity/warm vector, production web/API liveness and final dependency readiness passed. Generation catalog was accessible; no hosted generation ran. This supersedes the earlier unsuccessful entrypoint as the latest observation, but one success does not erase the historical startup failure or establish cold/warm reproducibility. Compose5.1.3 also successfully waited for the existing API/web/worker services with the worker healthcheck disabled; a healthcheck workaround was therefore not introduced.

Reader's producer exposed normalized text beside raw excerpts in the same source records, although exact citation resolution accepts only raw substrings. Replaying captured production rankings, without hosted/native calls or database writes, demonstrated ten normalized-prefix rejections and29raw-span-join resolutions. An independent real-HTTP/canonical-consumer regression failed all three initial/repair/follow-up branches before the fix (**3failed10.21s**). The producer now preserves normalized retrieval text as separate navigation and offers only raw excerpts as citeable sources. Exact resolution, provenance, retrieval, geometry, transport and budgets are unchanged. Focused verification passed **4tests8.47s**. Historical failed proposed quotes were not captured: this proves a producer-contract defect, not the exact historical rejected E1/E3 quote or hosted quality acceptance.

The original scientific2105 production parser, without monkeypatches, now succeeds in the unchanged restricted Linux sandbox: **1.40153s**,11pages,1829spans,2006blocks,49669codepoints,45CPU/60wall/768MiB limits. Original screening passes in **0.54488s**,10CPU/15wall/256MiB. Instrumented and plain canonical/text/geometry hashes match; `image_info` accounts for23ms, not a demonstrated bottleneck. No speculative parser optimization, limit increase or seccomp change was applied. These read-only direct probes do not restore the failed durable job or identify which historical whole-stage deadline boundary expired.

Further actual remediation:

- Combined Reader/shared citation and Research retrieval/API/repository/graph/stream suites: **132passed422.83s** (bg61). Existing real TCP post-commit reload, cross-source citation, reservation-disconnect, early-header abort, controlled provider429/EOF and publication-CAS cases are included; complete G4 consolidation remains separate.
- A second complete populated entrypoint exited **0 in42.50s** (bg62). Together with bg60 this establishes two consecutive warm/populated startup successes, not a fresh cold boot or new provider qualification.
- Visual Attention Network's genuine failed job resumed through owned public Retry: HTTP202 request `a3f19d21-a1db-4531-9e27-c41d73c5b8bb`, retry revision1, original job/version unchanged. Subsequent owned GET returned ready/succeeded, request `2f6235a1-f072-4ab9-bf9b-4bd6efd87daa`. Previously selected19embedding batches/76chunks were available for replay; no ad-hoc ledger reset or resource increase.
- Scientific2105 was accepted through a separate supported multipart upload of the identical frozen SHA: HTTP202 request `225963b0-3928-475a-a13d-d9933e86e0f2`. Owned GET returned ready/succeeded, request `057662ea-0da5-4d0e-b5ef-aa93622756e3`. Its source is honestly upload with unknown metadata; the permanently failed arXiv paper/job remains preserved. An earlier controller raw-body request was rejected422/FILE_REQUIRED before intake; correcting the transport retained the operation key. No failed-job retry guard was bypassed.
- All9frozen source bindings now verify exact SHA/owner/version/profile and ready publication; four are real scientific PDFs. Manifest/gold hashes are unchanged; new private bindings preserve the earlier seven-source artifact.
- Restored measurement: parser **67/67**, coverage **5357/5357**, reading order **12/12** accepted; sections **21/67** disclosed. Q0fusedRecall@5 **6/8** meets the existing floor; pairedfused/packed **2/14** fails75%, with **273/273** exact tuples,0scopeerrors and0missing sets. The new observer initially misread frozen reading fragments as block/line coordinates; a separate zero-native parser measurement corrected them to page-line index/start/end, preserving original evidence and all actual rankings. No gold/ranking adjustment was made to improve results.
- X1-E1 charged1attempt and failedREADER_FAILED because private observer fsync was denied by unchanged seccomp. The ignored observer alone was corrected to atomic0600 non-durable capture; controlled real-HTTP transparency regression went3RED9.34s→3GREEN7.79s. X2-E1 then charged1attempt and failedEVIDENCE_UNRESOLVED after2validated claims: the captured216-codepoint quote omitted exactly oneU+FFFD replacement glyph from a217-codepoint raw window. Raw catalog/provenance were intact; exact rejection and no post-delta repair are correct. Total **9/36**, seven settled runs, no uncertain reservation. Generic lossless Unicode JSON presentation is now being qualified; deterministic Unicode decoder/parser/canonical-resolution checks passed5tests12.91s, not proof of model obedience.
- Evaluator review found audited pre-reservation Research errors incorrectly charged uncertain dispatches. A narrow strict bounded status/code/request-identity recognizer now settles only503/GENERATION_UNCONFIGURED and429/RESEARCH_RATE_LIMITED at0attempts; unknown/transport/post-reservation failures remain conservative. Actual RED2failed6passed; full host evaluator **61passed0.19s**. A throwaway actual FastAPI process against isolated PostgreSQL/current synthetic session produced2genuine pre-reservation errors,0newruns/0hosted/0charge and reached the next case; live configuration remained unchanged. Read-only re-review found no further actionable issue0.99.

Additional controlled socket verification used one temporary PostgreSQL/source fixture, genuine Uvicorn TCP endpoints and a local provider, not hosted Gemini or native retrieval. The ignored probe was mounted over an existing read-only test filename only inside the disposable runner; no repository test file was overwritten. The initial nested-new-mountpoint attempt failed before execution on read-only filesystem; the corrected existing mountpoint ran successfully.

Six fault→same-owner explicit-valid-request pairs passed (**1probe134.37s**, bg66): provider503/429, provider header stall, post-delta body stall, EOF and downstream TCP disconnect after a validated delta. Each faulty run dispatched exactly1local provider request,0repairs,0accepted citations and persisted failed/interrupted state. Provider header/body stalls closed at the existing60s deadline (60.205s/60.202s observed cleanup); the disconnect closed provider socket and persisted interruption in0.109s. Each subsequent explicit POST completed through unchanged graph/resolver/publication and accepted citation GET; total12local requests,0hosted/0native. Shared transport fault suite additionally passed **98tests29.40s** (bg64). Existing controlled CAS/no-third-pass tests remain supporting evidence.

The pre-registered lexical-only OR diagnostic reused actual dense ranks, unchanged frozen gold, tuple filters/RRF60/fused5/top2 and source budgets. Actual current scientific FTS queries had6AND operators/0OR and0matching scoped chunks; all four numeric-filename titles were mandatory terms. Fixed navigation alternatives returned5lexical candidates per scientific source, but pairedfused/packed recall remained **2/14**. Q0fused stayed6/8. This hypothesis was rejected as a quality remedy: no production query, index, bounds or gold changed.

### Retained-source checkpoint after failed presentation experiment

- Generic ASCII-escaped JSON presentation did not qualify: X1-E3 charged1attempt, emitted two valid claims then proposed invented U+0000 absent from catalog/input and failed GENERATION_INVALID_OUTPUT. It was reverted; the independent navigation/raw-source fix and Unicode consumer regressions remain. No fuzzy citation cleanup, deleted-glyph acceptance, post-delta repair or fallback was added.
- D1/D2 each completed with the permitted `stop` action,1attempt,0recommendations/0inspected results. Their ready scientific uploads have honestly unknown metadata. This is **not** a Discovery quality pass or an official arXiv Add journey.
- The retained source, with the private capture override removed, completed the normal guarded entrypoint again (**bg67exit0,51.18s**). No generation call was sent. Combined with prior populated successes, this strengthens warm/populated reproducibility only.
- Actual public selection/auth negative checks recorded0new Research reservations: zero/four/duplicate/active selection422; foreign/nonexistent404; missing CSRF/wrong Origin403; missing/revoked synthetic session401; owned permanently unready409 and mixed unready/foreign404. This is two-owner synthetic-session security evidence, **not** Google sign-in acceptance.
- Controlled genuine TCP quota smoke completed20requests, rejected21st with429/RESEARCH_RATE_LIMITED and positive Retry-After, and dispatched no21st provider call (bg68). The companion lease probe initially violated a database check, then incorrectly named a nonexistent fixture column; neither is a production failure. Reusing the existing `lease_expires_at=started_at` fixture convention preserved immutable pins/165s constraint. The corrected probe passed **1test10.26s** (bg70): concurrent same-owner POST409 with no second dispatch; GET reaped expiry to interrupted; late valid provider output could not publish; next explicit request completed. All provider requests in these probes were local,0hosted/0native; no owner-stack DB rows were manipulated.
- Remaining authorized primary Research cases were executed exactly once: R1/R3/R4/R7/R8 completed; R2 failed safely with RESEARCH_INSUFFICIENT_EVIDENCE. Each used1hosted attempt,0additional retry. Current campaign ledger is **18/36charged**,18remaining,0uncertain/0reserved; allocation consumption Research8,Reader5,Discovery2,diagnostic3,demo0. Human assertion-support/direction-quality ratings remain absent; completed state alone does not establish G3 quality. Frozen primary observations and earlier failures are preserved.

Readonly repeatable-read canonical candidate-coverage diagnosis subsequently verified all24scientific premise groups (12sets × production/lexical-OR captures) have at least one fully covering published chunk. No needed region is excluded; none of the captured candidate stages has partial required-region coverage either. Thus the measured scientific failure is candidate recall/ranking before the frozen cutoff, not missing parser text, excluded margins, partial chunk boundaries or exact-citation cleanup. This is0native/0hosted/0DBwrites and does not qualify a new query design. An earlier script invocation lacked explicit application PYTHONPATH and executed no diagnostic.

All22primary/local observations were reconciled into a new private artifact with unchanged manifest hash; local retrieval fields complement, never overwrite, original hosted terminal outcomes. Offline scorer exited1/acceptedfalse. R1/R3/R4/R7/R8 actual result reload and seven authoritative citation GETs preserve exact paper/version/verbatim quote/page/boxes. Current production browser displayed R1, visibly jumped from active1706 to selected2105page4 and retained the persisted result on reload; one main/no overflow and Hypothesis label were observed. No Generate click or new model call occurred. A guessed close-dialog selector timed out because this surface uses an inline source jump/Return control, not a modal; no modal/ Escape-return/box-count claim is made from that attempt.

Final mixed-environment verification: correctly located backend selection ran **247passed/20failed650.61s** (bg72); all20failures were host-only evaluator ledger `flock` denied by the existing restricted API seccomp. No application boundary failure appeared. The full evaluator suite then passed on the documented host runner **61passed0.14s**, warnings disclosed. Do not report a single all-green container suite, remove locking, relax seccomp or introduce a test skip. The preceding nonexistent `test_generation_transport.py` invocation ran0tests, not a failed application test. Native-macOS frontend test invocation failed before tests because ignored node_modules contains Linux Rollup optional binaries; lockfile/dependencies/source remain unchanged and verification uses the existing frozen Linux Node22.14 runner instead.

Frozen Linux frontend verification completed **14files/149tests passed35.61s** with Node22.14.0, capped512MiB/1CPU, network-disabled runner (bg74). PDF.js Node legacy-build warnings remain disclosed; no lockfile deletion, dependency substitution or app behavior change. The runner image was fetched before execution. Final actual isolated liveness: API health200/request `4a75a3c4-791c-4bae-97fe-02d689c9ec1e`, web200. Liveness is not provider readiness. Newly owned disposable TCP/coverage probe scripts were removed after preserving safe results/private coverage evidence; primary artifacts, diagnostic failures, ledger, raw corpus, volumes and audit history remain intact.

### Approved bounded local query spike — rejected

Owner approved a query-revision proposal/local spike, retained existing hosted allocation with **no additional hosted calls**, and selected manual Google sign-in/human ratings. Owner then approved this exact bounded spike: fixed dense question `What limitations, assumptions, evaluation findings and future work does this paper report?`; compare new dense + original lexical and new dense + previously captured lexical OR. No gold/query injection, variant search, top-k change or production deployment.

The throwaway diagnostic executed6native embedding/search calls total, one per distinct required source, serially (scientific source times3.759/0.773/1.033/0.556s; controlled0.385/0.669s). Both variants retained **dense/fused/packed2/14**, scorerexit1/retrievalacceptedfalse; Q0 branch was explicitly unchanged cached baseline. Exact native source pins, candidate caps/RRF/packing and frozen hashes were unchanged. This rejects the proposed simple semantic-question/dual-query remedy; do not amend the approved production contract or ship it. Hosted charge remains18/36; no DBwrites/hosted calls/gold or production changes. New private diagnostic/observation/metric artifacts preserve the failed comparison, and the owned throwaway script was removed afterward.

The owner checklist now distinguishes genuine Google from synthetic campaign ownership, requires exact factual0/1/2 reviews without overwriting primary evidence, and stops before any generation control. Configured isolated callback `http://127.0.0.1:3305/auth/google/callback` was read directly; registration and owner sign-in are still unobserved. Query/ranking quality remains unresolved, not “fixed pending acceptance.” Additional query variants or architectural changes need a new evidence-led design decision; no blind query loop was performed.

Owner's subsequent genuine Google attempt returned HTTP400 `redirect_uri_mismatch`; G5 sign-in is now an observed failure, not merely unattempted. Controller inspected only local `/auth/google/start` without following Google: HTTP302/request `99689730-dd6b-4ef1-917e-64a49d5e0685`, actual outgoing `redirect_uri=http://127.0.0.1:3305/auth/google/callback`, Google authorization host and client-ID presence verified without disclosing client/state/PKCE/cookies. Exact registration for that client remains unavailable to repository tools. No account settings, callback registration, application config, main origin or hosted generation were changed; do not rerun the owner's failure just to confirm it.

## Temporary owner acceptance and resume backlog — 2026-10-05

**Conditional integration is authorized; unfinished quality is not waived or Verified.** The owner-reported Google configuration fix supersedes the unresolved-configuration prerequisite, not the preserved genuine callback400 or the missing full G5 evidence. Do not rerun the historical failure merely to confirm it. The parent controller will append actual shutdown/publication/merge/local-sync/main-startup/manual-test observations separately; none is claimed here.

### Accounting boundary before any further paid call

- The preserved campaign ledger records **18/36 charged attempts, 16 settled runs, 0 uncertain, 0 reserved**. Consumption is **Research8 / Reader5 / Discovery2 / diagnostic3 / demo0**. This is campaign accounting, not a claim about every application invocation.
- A new owner manual Discovery run **`9f0c5158-fc02-4ff1-b77a-d794b06d7d65`**, request **`0043e130-e0f9-4bf2-853b-e169c838ba51`**, completed with **stop, 1 generation, 0 searches, 0 returns**. It exists **outside the campaign ledger**. Preserve that observation and reconcile its dispatch/accounting before any further paid invocation; no campaign allocation or revised total is invented here.
- The latest decision permits **no extra hosted calls**. Neither unused nominal campaign slots nor main startup authorizes Ask, Related/Search or Generate. Further paid activity requires both new explicit hosted permission and accounting reconciliation. Known usage is not a zero/free-cost claim; approved monetary-null provenance remains unchanged.

### Unfinished quality and safe resume

1. **Retrieval:** paired fused/packed recall **2/14 fails the required75% floor**. Required scientific premises exist in published chunks, but the measured candidate stages miss them. Parser regions **67/67**, coverage **5357/5357**, reading order **12/12** and Q0 fused **6/8** pass their stated floors; section agreement **21/67** remains disclosed, not silently upgraded. Both bounded query spikes were rejected: lexical OR and the semantic dense-question comparison failed to improve2/14. No production query revision was retained; gold, retrieval bounds, provider/model and exact citation validation remain unchanged. Resume requires an evidence-led design decision, not more blind variants or paid retries.
2. **Reader:** historical answerable failures remain failures. The model deleted a raw **U+FFFD** glyph; exact rejection was correct. The escaped-Unicode presentation experiment invented **U+0000** and was reverted. Keep the independently proven normalized-navigation/raw-citeable separation; no fuzzy cleanup, deleted-glyph acceptance, fallback or post-delta repair.
3. **Discovery:** scientific uploads have filename titles and no abstract, honestly unknown metadata. The model selected `stop` **before arXiv search**; no returned recommendations or official Add journey were established. Current UI conflates a model stop with true search-zero-results. Resume must distinguish those states without claiming an unexecuted arXiv search or fabricated metadata.
4. **Research/human support:** R1/R8 required split-source factual support and human0/1/2 ratings remain missing; completed state and exact citation reload alone are insufficient. R2 safely returned insufficient evidence and must not be upgraded. Preserve all original hosted outcomes and use a separate private human-review overlay.
5. **Google/product:** preserve the genuine prior400 and separately label the owner's configuration-fix report. Full official **Google → Reader → Related → explicit Add → ready → Research** remains unaccepted. A no-hosted main smoke can exercise persisted state, but cannot close the generating journey.
6. **Verification provenance:** the historical mixed-container selection was **247passed / 20failed**, with20 host-ledger `flock` failures under unchanged container seccomp; documented host evaluator was **61passed**, frozen Linux frontend **149passed**. The fresh, correctly separated integration checks below supersede that selection for code verification, not for quality acceptance. No locking removal, seccomp relaxation or hidden test skip.

### Future main manual checklist — not yet exercised by this addendum

Use the [main checklist in the runbook](./2026-10-04-researcy-m5-interview-runbook.md#future-main-manual-checklist--conditional-integration). Record actual merged revision, private main override/project/origin, forward-migration/processing outcomes and request IDs. Preserve main owner modifications and data. Check liveness/readiness separately; inspect owner Library, original PDF, selection restrictions and any already persisted accepted results/citations without regeneration. Owner sign-in and human review must be labelled by evidence source. Stop before Ask/Search/Generate until new hosted permission and reconciled accounting exist. Do not delete volumes, force-prune worktrees or publish private evidence.

## Conditional integration execution — 2026-10-05

### Pre-publication verification and isolated shutdown

These checks precede the four new integration-review corrections; corrected-source checks will be recorded separately before publication.

- Runtime backend: `docker compose --env-file .omp/runtime/m5-acceptance.env -p researcy-m5-acceptance -f compose.yaml -f .omp/runtime/m5-acceptance.private.yaml -f .omp/runtime/m5-test.private.yaml run --rm --no-deps -T api python -m pytest tests --ignore=tests/test_m5_evaluation.py -q -p no:cacheprovider` — **1075passed / 12skipped,1060.03s**. The host-only evaluator is deliberately executed separately, not omitted overall.
- Host evaluator, from `apps/api`: `uv run --frozen pytest tests/test_m5_evaluation.py -q` — **61passed,0.12s**, five existing PyMuPDF/SWIG deprecation warnings.
- Frontend: frozen Node22.14.0 Linux runner,512MiB/1CPU/network disabled, `npm test` — **14files / 149tests passed,36.84s**; existing PDF.js legacy-build warnings disclosed.
- API/web/worker production-image build succeeded with the isolated private override; cached layers were reused. A separate Node22.14.0 Linux,1GiB/2CPU/network-disabled `npm run build` actually compiled Next16.3.6 (**33.5s**) and strict TypeScript (**11.4s**), total58.36s; all configured routes emitted.
- Read-only review found four additional correctness issues requiring correction before publication: fresh-ledger campaign-budget bypass, unsynced ledger-directory rename, offline allocation-ceiling acceptance, and cross-source PDF restoration after ordinary page navigation. These are not reclassified as the owner's accepted quality backlog.
- The full isolated stack was stopped without `-v`. Verification-only PostgreSQL/MinIO/Qdrant were subsequently stopped with the same guarded project/overrides and `--remove-orphans`; the final project-labelled running-container query returned no rows. All three volumes remain: `researcy-m5-acceptance_postgres-data`, `researcy-m5-acceptance_minio-data`, `researcy-m5-acceptance_qdrant-data`. No M5 host runtime or managed browser tab remained; the shared native runtime was retained.
- No hosted generation, owner-stack database repair, private-artifact deletion, worktree pruning or quality-gate promotion occurred in these checks. Publication, local-main synchronization and main runtime cutover are not yet claimed.

### Post-review implementation and verified gate checks

The four integration-review correctness issues were corrected on the feature branch with RED -> GREEN TDD proof before commit:

1. **Canonical campaign ledger identity:** `_git_main_repository(root)` resolves the exact git checkout root and detects main repository ancestry for both main checkouts and linked worktrees without running mutating git commands. `--run` enforces the campaign ledger path strictly at `<main_repo>/.omp/runtime/m5-campaigns/<campaign_id>/attempt-ledger.json` and fails closed before client creation if the canonical ledger has not been adopted (`CANONICAL_LEDGER_ADOPTION_REQUIRED`) or if an alternate path is supplied (`CANONICAL_LEDGER_PATH_REQUIRED`).
2. **Directory durability before dispatch:** `_atomic_json` now acquires a directory file descriptor and executes `os.fsync(parent_fd)` after `os.replace`. Controlled directory fsync failure blocks endpoint dispatch and preserves the active reservation.
3. **Offline allocation ceiling and case validation:** `_score_cost(observations, cases)` now tracks attempts by frozen allocation (`research: 16`, `reader: 6`, `discovery: 4`, `demo: 6`, `diagnostic: 4`), rejecting individual allocation overruns even when total attempts stay <= 36. Missing accounting counts are tracked per allocation and unsupported case accounting raises `INVALID_CASE_ACCOUNTING`.
4. **Cross-source PDF navigation and popstate restoration:** `ReaderWorkspace.navigate` clears stale citation selection/highlights and URL parameter when paging away from the citation's page while preserving the selected immutable PDF tuple, research run and page state. `restore` no longer prematurely flashes the active paper before document resolution. Three permanent tests cover previous-page, page-number and scroll browsing across unmount/reload/popstate and return-to-active paper focus.

Verified check results:
- Host evaluator suite (`apps/api`): `uv run --frozen pytest tests/test_m5_evaluation.py -q` — **90 passed, 0.22s**, 5 deprecation warnings.
- Frontend suite (`apps/web`): Node 22.14.0 Linux runner, network disabled — **14 files / 152 passed, 36.81s**; PDF.js legacy-build warnings disclosed.
- Frontend production build: Next.js 16.3.6 compilation and TypeScript typecheck — **30.59s**, all routes emitted cleanly.
- Container backend suite: `docker compose ... run --rm --no-deps -T api python -m pytest tests --ignore=tests/test_m5_evaluation.py -q -p no:cacheprovider` — **1075 passed / 12 skipped, 953.97s**.
- Canonical ledger adoption: Original private ledger `.omp/runtime/m5-gold/attempt-ledger.json` was safely adopted to `/Users/tuananhduong/Projects/researcy/.omp/runtime/m5-campaigns/m5-20261004-frozen-1/attempt-ledger.json` under exclusive lock without overwrite via hardlink; verified matching SHA256 `0e0242a046b136fe1b11dae4d86663a99f6a4ec71e92523a01e55ae2dd460059`, 18 charged attempts, 16 runs, 0 unsettled.
