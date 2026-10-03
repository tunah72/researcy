# Researcy Delivery Map

**Status:** Active delivery control — revision 2.0 approved
**Date:** 2026-09-24
**Master specification:** [`2026-09-18-researcy-system-design.md`](./2026-09-18-researcy-system-design.md), approved revision 2.0

## 1. Purpose

This map tracks the approved reader-first revision 2.0 requirements through bounded vertical milestones and records delivery gates without duplicating normative product or architecture requirements.

The approved master specification remains authoritative. A child specification may add local detail but may not silently override a master decision. This delivery map does not assert that a new route or capability is implemented or verified.

**Source-of-truth rule:** The master specification controls product/architecture; an approved child specification controls its milestone's behavioral detail; this map controls current delivery status; acceptance reports record observations and blockers. Approval-time `Not started`/`Designed` wording in historical specifications and plans is not a current-status override. V4/The Moonlight visual references are design archives, not normative or pixel-perfect contracts. Preserve historical approvals and Q0 evidence.

## 2. Status model

| Status | Meaning |
|---|---|
| Not started | No approved child specification exists for the milestone. |
| Designed | The child specification is approved. |
| Planned | An implementation plan is approved and ready to execute. |
| Implemented | The planned code and configuration exist, but final acceptance evidence is incomplete. |
| Verified | The milestone's acceptance journey and required checks have passed with recorded evidence. |
| Blocked | Progress requires an external decision, credential, service, or unresolved architectural change. |

A percentage is never used as delivery status. A milestone reaches `Verified` only through observable behavior and recorded evidence.

## 3. Delivery sequence

```text
Q0 Technical Qualification (Verified)
        ↓
M1 Sign-in, Library, and Import
        ↓
M2 Durable PDF Processing and Owner-Scoped Index
        ↓
M3 ReaderAgent and Evidence-Linked PDF Reader (first independently demoable product)
        ↓
M4 DiscoveryAgent Recommendations and Explicit Add
        ↓
M5 ResearchAgent, End-to-End Evaluation, and Interview Demo
```

The sequence follows the reader-first product dependency: identity and a ready owner-scoped paper precede the ReaderAgent and exact-PDF citation journey; only then do on-demand related-paper discovery and research directions extend it. M3 is the first independently demoable product. Each later milestone depends on evidence from the earlier milestone; only the active milestone receives a detailed implementation plan.

## 4. Milestones

### Q0 — Technical Qualification

**Outcome:** The highest-risk technical choices are supported by measurements before production implementation begins.

**Scope:**

- Docling versus a PyMuPDF-based geometry-first parser on a two-paper representative corpus.
- Chunk-to-source-span-to-bounding-box feasibility.
- BGE-M3 versus Nomic Embed Text through native ARM64 Ollama on the M1 with 8 GB RAM.
- One pinned OpenAI-compatible generation path through a fixed 9Router version, provider connection, account, and exact model route, with fallback and prompt transformation disabled.
- One complete quote-to-PDF-highlight proof.
- Q0.1 remediation qualifies `bge-m3:567m` plus deterministic BM25 and RRF before executing the deferred generation and evidence-proof tracks.

**Exit gate:**

- parser decision recorded with corpus evidence;
- embedding model/runtime decision recorded with memory, latency, dimension, and retrieval evidence;
- generator contract qualified for streaming and structured citations;
- exact evidence resolution demonstrated on the golden paper;
- throwaway probe code is not treated as production foundation.

**Status:** Verified

**Evidence & Decisions:**
- Original report: [`docs/superpowers/reports/2026-09-20-researcy-q0-technical-qualification-report.md`](../reports/2026-09-20-researcy-q0-technical-qualification-report.md)
- Original run: [`qualification/results/q0-20260920T124722Z-cd96df4`](../../../qualification/results/q0-20260920T124722Z-cd96df4)
- Q0.1 technical report: [`docs/superpowers/reports/2026-09-22-researcy-q0-1-hybrid-qualification-report.md`](../reports/2026-09-22-researcy-q0-1-hybrid-qualification-report.md)
- Q0.1 run: [`qualification/results/q0-1-20260921T030640Z-36f32ae`](../../../qualification/results/q0-1-20260921T030640Z-36f32ae)
- Parser: PyMuPDF geometry-first parsing retained from the original Q0 decision.
- Retrieval: `bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)` passed fused Recall@5 at 6/8 without retroactively passing dense-only retrieval.
- Generation: the configured `ag/gemini-3.8-flash-low` route passed the answerable, bounded follow-up, and unanswerable refusal cases.
- Display: the answerable Evidence/Model/Result view passed the recorded Chromium and accessibility checks.

### M1 — Sign-in, Library, and Import

**Outcome:** A user signs in, imports a supported paper, and sees only their own library.

**Scope:**

- Next.js and FastAPI application foundation;
- PostgreSQL migrations;
- Google OAuth and opaque application sessions;
- CSRF and ownership enforcement;
- MinIO object storage;
- arXiv import and PDF upload entry;
- initial Library and Add Paper experience;
- initial PDF validation.

**Exit gate:**

- two-user ownership isolation verified;
- upload and arXiv import persist a valid paper and original PDF;
- Library states are backed by real database state;
- logout revokes the server-side session.

**Status:** Implemented

**Owner acceptance:** **PASSED — 2026-09-27.** The owner confirmed successful `2603.09689` import after remediation and authorized task-based commits, merge/push to `main`, local/remote synchronization, and retention of the worktree. See [current owner acceptance](../reports/2026-09-24-researcy-m1-acceptance.md#current-owner-acceptance--2026-09-27). This acceptance is recorded separately from `Verified`: the detailed two-real-Google-user four-gate evidence is still outstanding. M2 remains Not started.

**M2 handoff update — 2026-09-27:** The owner now explicitly confirms testing with two real Google accounts and requests `Verified`. This is accepted as owner-reported evidence; the remaining issue is the per-gate record, not the availability of real identities. See the [handoff evidence addendum](../reports/2026-09-24-researcy-m1-acceptance.md#m2-handoff-evidence-addendum--2026-09-27). Until that record or an explicit acceptance-contract amendment closes the gap, the technical status above is unchanged; no owner-confirmed check is rerun just for confirmation.

**Approved child specification:** [`2026-09-24-researcy-m1-sign-in-library-import-design.md`](./2026-09-24-researcy-m1-sign-in-library-import-design.md) — owner-approved on 2026-09-24.
**Approved implementation plan:** [`2026-09-24-researcy-m1-sign-in-library-import.md`](../plans/2026-09-24-researcy-m1-sign-in-library-import.md) — owner-approved on 2026-09-24; implementation and the 2026-09-27 remediation evidence are recorded in the [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md). The later owner-approved reader-facing revision adds Landing → Google modal → Library, compact import controls, safe nontechnical feedback, `406`/`429`/`503` cooldowns, real `1706.03762v7` API/browser imports, PDF integrity, four-width production-browser checks, and local A/B ownership/logout replay. The owner's historical gate-pass attestation is retained, but the detailed real two-Google-user four-gate record is still unavailable; no `Verified` promotion is justified.

### M2 — Durable PDF Processing and Owner-Scoped Index

**Outcome:** An accepted paper is processed asynchronously into a searchable, provenance-preserving index scoped to its owner.

**Scope:**

- PostgreSQL durable jobs;
- `FOR UPDATE SKIP LOCKED`, leases, heartbeats, and retry;
- production parser adapter selected by Q0, with untrusted-input validation and bounded execution;
- canonical pages, sections, blocks, spans, chunks, and mappings;
- structure-aware chunking;
- on-device self-hosted embedding;
- user- and paper-scoped Qdrant indexing;
- processing, failure, and retry UI states.

**Exit gate:**

- arXiv `1706.03762` reaches `ready` through observable stages;
- worker interruption recovers after lease expiry;
- indexing retry creates no duplicate chunks or vectors;
- paper becomes ready only after PostgreSQL and Qdrant invariants pass;
- a gold query retrieves evidence that maps back to page geometry;
- parser resource-bound and invalid-input cases have recorded security evidence.

**Status:** Verified

**Approved specification and plan:** [M2 child specification](./2026-09-27-researcy-m2-durable-processing-design.md) approved 2026-09-27; [implementation plan](../plans/2026-09-27-researcy-m2-durable-processing.md) approved 2026-09-28. The owner explicitly authorizes implementation while completing the M1 record separately. This is a prerequisite exception, not M1 verification or a passing M2 exit gate.

**Verification evidence — 2026-10-01:** Tasks 1–11, including acceptance-discovered containment, proxy-body and full-set provenance fixes, are complete in the isolated M2 worktree. The [final acceptance reconciliation](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation) records all G1–G6, resource and browser gates PASS, full ordered canonical/mapping replay, 516 backend passes/one opt-in skip, 67 frontend passes, production API/worker/web builds and two independent reviews without blocking findings. The initial resource FAIL (+1,258.69 MiB swap) is retained; the [complete rerun](../reports/2026-09-27-researcy-m2-acceptance.md#resource-prerequisite-remediation-and-complete-rerun--2026-10-01) passed unchanged warm criteria (+260.25 MiB, all 147 status/Library requests below 2 seconds, no OOM/restarts). Cold-load peak swap increase +1,531.31 MiB remains separate. M1 technical status and historical Q0 evidence are unchanged. No owner-stack cutover, model/budget change, owner-application shutdown, push, merge or prune was performed.

### M3 — ReaderAgent and Evidence-Linked PDF Reader

**Outcome:** The first independently demoable product lets a user ask a question about the active paper, receive a streaming grounded answer or refusal, and open each accepted citation at its exact passage in that paper's original PDF.

**Scope:**

- conversations and messages;
- ReaderAgent invoked by the existing `POST /api/conversations/:conversationId/messages:stream` route for the active paper only;
- PostgreSQL lexical retrieval, Qdrant dense retrieval, and Reciprocal Rank Fusion;
- bounded multi-turn context and at most one model-directed extra search restricted to the active paper;
- direct Gemini `gemini-3.8-flash` primary, with operator-selected `ag/gemini-3.8-flash-low` through 9Router for subsequent runs only; no automatic fallback;
- streaming `answer.delta`, `citation.resolved`, `answer.completed`, and `answer.failed` events;
- deterministic citation validation and quote/source/geometry resolution;
- a citation source identity containing `paper_id`, `document_version`, and `source_ref`, plus verbatim `evidence_quote`, page, and exact PDF-space boxes;
- PDF.js reader and outline, fixed PDF/Discussion workspace, page and citation URL state, exact evidence overlays, and inline evidence card;
- keyboard, focus, overflow, reduced-motion, and complete Discussion visual states;
- request-level agent trace, latency, and cost evidence.

**Exit gate:**

- the existing route streams an answer grounded only in the active user-owned paper, or a grounded refusal;
- every accepted citation resolves the composite source identity, verbatim quote, page, and exact PDF-space boxes; clicking it opens the correct original PDF and highlights those boxes without a second `Go to page` action;
- schema-aware next-action qualification follows master revision 2.2 / child G6 through actual Gemini application transport and graph before M3 may be marked `Verified`; controlled negatives are explicitly labelled and do not substitute for real answer/search/containment branch evidence;
- the qualification evidence records the real route, request outcome, structured agent trace, measured latency, and cost with its source;
- insufficient evidence, cross-paper or foreign-user sources, invalid/unresolvable geometry, and rejected structured next actions do not produce accepted claims;
- provider timeout, rate limit, provider failure, and interrupted stream states are actionable and recorded;
- the first demo journey works with keyboard input at supported desktop widths and shows a citation jump to the exact passage.

**Status:** Verified

**Owner approval — 2026-10-01:** The owner approved the [M3 child specification](./2026-10-01-researcy-m3-reader-agent-design.md) and [implementation plan](../plans/2026-10-01-researcy-m3-reader-agent.md): “Tôi phê duyệt specification và implement plan.” M3 execution is authorized in an isolated worktree, including the presented prerequisite exception while M1 remains `Implemented`. Approval establishes design/planning, not passing implementation/real-route/browser evidence. Owner-data cutover and publishing/integration require separate authorization.

**Implementation evidence — 2026-10-02:** The isolated M3 worktree implements immutable PDF delivery/Reader, pinned conversations, owner-scoped FTS+dense RRF, exact raw quote resolution, bounded fixed-route generation/LangGraph, committed-only citation events, claim-level SSE and the Discussion/keyboard evidence journey. See the [M3 execution report](../reports/2026-10-01-researcy-m3-acceptance.md#final-productionbrowser-corrections-and-awake-host-verification--2026-10-02) for production builds, affected suites, real answer/refusal/reload and exact original-PDF geometry/browser evidence. **Not Verified:** applicable documented Antigravity tariff/cost evidence and actual two-pass `search_same_paper` graph qualification remain open; controlled branches and standalone client qualification do not substitute. Independent backend review also failed to complete. M1/M2 and historical Q0 statuses/evidence are unchanged. No owner-stack cutover, publishing, push, merge or prune performed.

**Owner-requested requalification — 2026-10-02:** [Six fresh actual-route cases](../reports/2026-10-01-researcy-m3-acceptance.md#owner-requested-antigravity-requalification--2026-10-02t113908z), eight attempts: three cited answers, one successful actual `search_same_paper` → follow-up validated refusal, two safe failures. Actual graph search is now observed; the earlier “unproven search” statement above is superseded for branch execution/refusal termination only. Search → supported cited answer was not observed. Complete G6 negative interpretation and applicable tariff/cost source remain open; no Verified promotion or route/criteria change.

**Follow-up diagnosis — 2026-10-02:** [Actual transport and cited-search evidence](../reports/2026-10-01-researcy-m3-acceptance.md#follow-up-transport-diagnosis-and-supported-cited-answer--2026-10-02) now records actual production graph `search_same_paper` → supported cited answer: two calls/one search/zero repairs, accepted citation API reload and real Chromium original-PDF interaction. This supersedes the earlier unobserved supported-search result, not the remaining gates. Two new initial-pass failures were traced to provider-stream EOF before terminal stop/final action validation; gateway/upstream cause and the historical follow-up failure remain unproven. A separate same-origin HTTP case completed directly, not with two passes. No Generator change or stability/Verified claim; complete G6 negative interpretation, applicable tariff/cost and independent backend review remain open.

**Owner-approved cost clarification and backend closure — 2026-10-02:** The owner retained G6 unchanged and approved unavailable monetary-cost provenance as `null` with documented reason, actual per-attempt usage, calls and latency. Master revision 2.1 / child §10 apply to M3 only. Missing applicable tariff is a documented measurement limitation, not a gate blocker; no zero/free-price inference or unrelated tariff is accepted. [Backend closure evidence](../reports/2026-10-01-researcy-m3-acceptance.md#backend-closure-corrections-and-acceptance-decision--2026-10-02) records demonstrated fixes, **756 backend passes / one opt-in skip**, clean independent final targeted review, final production API build/smokes and a fresh completed actual same-origin answer with two exact accepted citation reloads. G6 actual graph negative/valid-after-negative remains open; M3 stays `Implemented`. Upstream EOF/timeout internal cause and generalized route stability are not established.

**Owner-approved Gemini requalification — historical prerequisite checkpoint:** The owner requests a paid Gemini key primary, selects manual switching between runs for 9Router and approves schema-aware G6. Master revision 2.2 and the amended child specification record the exact change; prior fixed-route/natural-negative decisions above are historical. Read-only catalog and isolated-fixture retrieval checks alone did not establish new-primary generation or gate acceptance. The previously pending addendum review and implementation are superseded by the explicit G1–G3 approval and recorded closure below.

**Verified closure — 2026-10-03:** The owner explicitly approved the G1–G3 addendum. The [final amended gate matrix and production/browser evidence](../reports/2026-10-01-researcy-m3-acceptance.md#final-amended-m3-gate-matrix) close M3 on the isolated `feat-m3-reader-agent` branch under master revision 2.2. Fixed direct `gemini-3.8-flash` completed actual supported search-to-cited-answer, refusal, adversarial containment and subsequent valid output; the campaign used **11/12 authorized hosted attempts**, with no pending attempts. Seven explicitly controlled rejection/failure cases used zero hosted calls and are not labelled natural Gemini failures. Final affected suites: **772 backend passes / one opt-in real-network skip; 113 frontend passes**; production builds, original-PDF citation/keyboard/reload journeys and final targeted review are recorded. Source commits `47d8357` and `a8848f0` include truthful provider accounting and the reproduced/fixed one-shot citation reveal regression. Monetary cost remains approved `null/unavailable` with documented provenance; optional manual 9Router runtime smoke lacks authorized credentials/mapping and is not claimed. Shared-host swap pressure is disclosed; these observations do not renew M2 capacity acceptance. Historical unaffected gates retain their original evidence. Owner-stack cutover, publishing and integration remain separately unauthorized; M1/M2 and later milestone statuses are unchanged.

**Owner manual acceptance and integration authorization — 2026-10-03:** The owner reports: “Tôi đã thực hiện kiểm thử xong. Kết quả công việc đều đạt chất lượng.” The owner explicitly requests shutdown, worktree preparation/commit, branch push, PR creation/merge into `main`, local/remote-main synchronization and a new main-stack manual test. The owner separately approves preserving the two local draft copies outside Git, leaving generated/context artifacts intact, and applying forward migrations to the existing main database before starting the full processing stack/worker. This is owner-reported manual acceptance and execution permission; subsequent publication/cutover commands must supply their own observed evidence. No database reset, volume deletion or unrelated worktree cleanup is authorized.


### M4 — DiscoveryAgent Recommendations and Explicit Add

**Outcome:** On request, a user receives a small set of metadata-grounded related arXiv papers and chooses explicitly whether to add any of them to their Library.

**Scope:**

- DiscoveryAgent invoked only when requested through `POST /api/papers/:paperId/related:search`;
- official arXiv metadata search using the current paper's title plus abstract when available;
- at most three distinct actual arXiv IDs, with title, authors, metadata/abstract-grounded reason, arXiv URL, and request ID;
- recommendation rationales remain metadata-only and are not full-text citations;
- explicit user selection reuses the existing Library import flow; recommendations never auto-import;
- structured next-action qualification through direct `gemini-3.8-flash` primary; manual between-run 9Router alternative only, separately qualified;
- request-level agent trace, latency, and cost evidence.

**Exit gate:**

- a real request through the approved primary path returns no more than three distinct, valid arXiv recommendations, with each rationale grounded only in returned arXiv metadata/abstract;
- master revision 2.3 schema-aware qualification observes actual search/reasons, stop, adversarial containment and subsequent valid output; controlled malformed/unsupported rejection is separately labelled. Record route, outcome, agent trace, measured latency and actual usage/cost provenance, including approved null/unavailable monetary mapping;
- no recommendation enters the user's Library until the user explicitly adds it through the existing import flow;
- no results produce `papers: []`; a missing title produces no invented recommendation; an unavailable arXiv API produces a retriable error and no fabricated result;
- invalid or duplicate IDs, provider failure, interrupted work, and rejected structured next actions are handled without displaying unsupported recommendations or importing papers.

**Status:** Verified

**Owner approval — 2026-10-03:** Both [M4 child specification](./2026-10-03-researcy-m4-discovery-agent-design.md) and [implementation plan](../plans/2026-10-03-researcy-m4-discovery-agent.md) approved; the owner explicitly approved the three master revision 2.3 amendment items and M1 prerequisite exception. M1 remains Implemented. Implementation uses isolated `feat-m4-discovery-agent`; owner permits isolated stack/native runtime and at most twelve public-paper hosted attempts, not owner-data migration/worker/cutover or publishing/push/merge/prune. Approval is not gate evidence.

**Final isolated verification — 2026-10-04:** [M4 acceptance](../reports/2026-10-03-researcy-m4-acceptance.md#final-amended-m4-gate-reconciliation--2026-10-04) records G1–G7: actual direct Gemini search/reasons/stop/hostile-metadata containment/subsequent valid qualification, official metadata and exact no-import integrity, owner-selected explicit Add→real processing ready, production browser, controlled real HTTP/TCP failure/security/quota/revocation, final963passed/1opt-in skip backend and124passed frontend, three-image production build and final no-finding reviews. Hosted total8/12. Synthetic identities do not promote M1 or establish Google OAuth acceptance; approved monetary-null billing-attribution limitation remains. Verification is isolated only, not owner cutover or publishing authorization.

**Owner acceptance/integration authorization — 2026-10-04:** Owner reports all M4 manual checks meet the quality gate and authorizes document update, M4 process cleanup, commit/push/PR/merge, local-main synchronization and main-stack startup. [Acceptance record](../reports/2026-10-03-researcy-m4-acceptance.md#owner-acceptance-and-integration-authorization--2026-10-04) distinguishes owner observations, preserved upload-metadata/upstream-acquisition limitations and pending actual main cutover evidence. M4 remains Verified. Preserve volumes/worktrees/private artifacts; M1/Q0 history unchanged.

### M5 — ResearchAgent, Evaluation, and Interview Demo

**Outcome:** A user requests research directions grounded in the current paper and one to three explicitly selected, ready related papers; the end-to-end journey and its quality, security, reliability, and cost claims are reproducible.

**Scope:**

- ResearchAgent invoked through `POST /api/papers/:paperId/research-directions:stream`;
- accept one to three selected, ready, user-owned related papers in addition to the current paper;
- stream directions with factual premises cited to their source papers and proposed methods clearly labelled as hypotheses;
- preserve exact citation identity, verbatim evidence quote, page, and PDF-space boxes for each supported factual claim;
- fixed annotated evaluation corpus and separated parsing, retrieval, citation, answer, product, and cost metrics;
- Compose stack and native embedding startup; health and readiness checks;
- end-to-end security and ownership probes, failure recovery checks, browser acceptance journey, and interview demo runbook;
- request-level agent trace, latency, and cost evidence for the real ResearchAgent route.

**Exit gate:**

- an unready or foreign related-paper ID is rejected, and no model call occurs unless one to three selected related papers are ready and owned by the current user;
- factual premises cite the appropriate current or selected paper with exact PDF-resolvable evidence; proposed methods are labelled hypotheses and unsupported premises are refused or omitted;
- provider failure, insufficient evidence, and interrupted streams have actionable outcomes;
- the full sign-in-to-reader-to-explicit-add-to-research-directions journey and its evaluation report are reproducible;
- security, ownership, and recovery checks retain recorded evidence in their owning milestones and are exercised end to end;
- each ResearchAgent run records the configured route, agent trace, measured latency, and cost with its source; the interview demo reports limits rather than extrapolating beyond the evaluated cases.

**Status:** Not started

## 5. Master requirement coverage

| ID | Master requirement | Master section | Delivery owner | Status | Verification evidence |
|---|---|---:|---|---|---|
| SYS-01 | Next.js + FastAPI modular monolith with one worker | 5 | M1 | Implemented | [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md); full-stack build and focused validation passed; real two-user gates pending |
| AUTH-01 | Google OAuth followed by opaque server-side sessions | 16 | M1 | Implemented | [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md); implementation/tests passed; two-real-Google-user journey pending |
| AUTH-02 | CSRF protection and user-scoped resource access | 16 | M1 | Implemented | [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md); implementation/tests passed; two-user ownership gate pending |
| LIB-01 | User library with arXiv import and supported PDF upload | 3, 12 | M1 | Implemented | [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md); real local-session arXiv/PDF persistence passed; real OAuth gate pending |
| SEC-01 | Untrusted PDF validation and bounded parser execution | 4, 17 | M2 | Verified | [M2 acceptance](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation): G6 actual intake/worker and sandbox containment/resource failure/reaping |
| JOB-01 | PostgreSQL durable jobs with claim leases and recovery | 8 | M2 | Verified | [M2 acceptance](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation): G1/G2 actual stages, 90-second crash/stale recovery and G3 revision replay |
| DOC-01 | Canonical document model with reversible provenance | 6 | M2 | Verified | [M2 acceptance](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation): full canonical/mapping replay, populated M1 upgrade and G5 scoped exact offsets/boxes |
| PARSE-01 | Qualified scientific PDF parser | 7 | M2 | Verified | Q0/Q0.1 unchanged; [M2 acceptance](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation): frozen native gold and actual rotated/cropped/invalid inputs |
| EMB-01 | On-device self-hosted embedding within the M1 budget | 9, 10, 20 | M2 | Verified | Q0.1 unchanged; [M2 acceptance](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation): exact qualified native identity, warm resource PASS and separately recorded cold load |
| IDX-01 | User- and paper-scoped Qdrant index | 5, 9 | M2 | Verified | [M2 acceptance](../reports/2026-09-27-researcy-m2-acceptance.md#task-11-final-evidence-reconciliation): G3/G4 exact-set replay/terminal integrity and G5 pre-search ownership denial |
| RET-01 | Lexical + dense retrieval with RRF | 9 | M3 | Designed | Q0.1 report: hybrid Recall@5 6/8; final delivery remains M3 |
| GEN-01 | Vendor-hosted streaming grounded generation | 10 | M3 | Designed | Q0.1 report: three generation cases passed; final delivery remains M3 |
| CIT-01 | Citation validation and quote-to-geometry resolution | 10 | M3 | Designed | Q0.1 report and one-case display evidence; final exact-PDF delivery remains M3 |
| AGENT-01 | ReaderAgent — `POST /api/conversations/:conversationId/messages:stream` | 15 | M3 | Designed | [Approved M3 specification](./2026-10-01-researcy-m3-reader-agent-design.md); real-route structured-action, exact-PDF, trace/cost/latency gates remain required |
| AGENT-02 | DiscoveryAgent — `POST /api/papers/:paperId/related:search` | 15 | M4 | Verified | [M4 final acceptance](../reports/2026-10-03-researcy-m4-acceptance.md#final-amended-m4-gate-reconciliation--2026-10-04): isolated G1–G7, actual direct Gemini/schema-aware qualification, metadata/no-import integrity, explicit Add→ready and production browser; approved monetary-null attribution limitation,8/12 hosted attempts; no owner cutover |
| AGENT-03 | ResearchAgent — `POST /api/papers/:paperId/research-directions:stream` | 15 | M5 | Not started | Selected-ready-paper citation journey, hypothesis labeling, agent trace, cost, latency, and evaluation |
| UX-01 | Simplified editorial Library experience | 12, 13 | M1 | Implemented | [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md); Chromium responsive/state checks passed; real OAuth gate pending |
| UX-02 | Evidence-linked PDF and Discussion workspace | 12–14 | M3 | Designed | [Approved M3 specification](./2026-10-01-researcy-m3-reader-agent-design.md); Reader and exact-PDF browser acceptance not yet performed |
| EVAL-01 | Fixed corpus and separated quality metrics | 11 | M5 | Not started | — |
| OPS-01 | Reproducible interview deployment and health checks | 19–21 | M5 | Not started | — |

A requirement has one delivery owner. Any earlier milestone is a prerequisite or qualification dependency, not a second owner; later end-to-end security and recovery probes exercise the guarantees but do not move ownership away from M1/M2. Q0 evidence remains linked as historical qualification and does not mark any implementation milestone complete.

## 6. Gate update rules

1. Approving a child specification changes its milestone and covered requirements to `Designed`.
2. Approving its implementation plan changes the milestone to `Planned`.
3. Completing implementation without acceptance evidence changes it to `Implemented`.
4. Passing the exit gate and recording evidence changes it to `Verified`.
5. A failed check keeps the prior status and records the blocker; it never becomes partial credit.
6. A master-level conflict blocks the milestone until the master revision is approved.
7. Verification evidence must name the command, report, browser journey, or security probe that established the claim.

## 7. Current control point

Master specification revision 2.0 and this delivery map were approved on 2026-09-24. Q0 remains `Verified` with its original and Q0.1 report/run links above. Q0.1 measured fused Recall@5 at 6/8, passed the three recorded generation cases, and browser-checked only one answerable case on Track D; it is not evidence of generalized multi-paper or production-agent quality. M1 and SYS-01/AUTH-01/AUTH-02/LIB-01/UX-01 remain `Implemented`. The M1 acceptance report separates historical evidence from the 2026-09-27 arXiv pacing/406 and UI remediation, real `2303.09833v1` acceptance with DB/MinIO hash/size equality, four-width Chromium checks, and local A/B isolation/revocation probes. M1 is not `Verified`: the owner's gate-pass attestation has no recoverable detailed two-real-Google-user four-gate record, and synthetic sessions cannot establish that missing OAuth journey. SEC-01/JOB-01 remain M2-owned; M2–M5 retain their previous statuses. The configured product-runtime route remains `ag/gemini-3.8-flash-low` through 9Router; development-agent model selection is separate and does not change the product contract.

**Current M2 control update — 2026-09-27:** The owner approved the M2 child specification and authorized planning. M2 and its six owned requirements are `Designed`, superseding the M2 status in the preceding historical control narrative. M1 remains `Implemented` pending its recorded prerequisite resolution; M3–M5 and historical Q0 evidence are unchanged. A draft plan does not advance M2 to `Planned`.

**Execution authorization — 2026-09-28:** The owner approved the M2 implementation plan and explicitly permits implementation while the M1 record is supplemented separately. M2 is `Planned`; its requirement rows retain design evidence until implementation/verification evidence exists. The prior prerequisite documentation gap no longer blocks starting M2. M1 technical status and all M2 exit gates remain unchanged.

**M2 final verification — 2026-10-01:** M2 and SEC-01/JOB-01/DOC-01/PARSE-01/EMB-01/IDX-01 are `Verified` based on the isolated worktree's complete recorded G1–G6/resource/browser gates and final reviews. This supersedes the earlier M2 control statuses, not historical evidence. Owner-stack migration/worker startup and publishing/integration still require separate authorization. M1 remains `Implemented`; M3–M5, product generation route and Q0 evidence are unchanged.

**M3 execution authorization — 2026-10-01:** M3 is `Planned` following owner approval of both documents and their named decisions. M1 remains `Implemented`, M2 `Verified`, M4/M5 unchanged. All M3 acceptance gates, product route and historical Q0 evidence are unchanged.
