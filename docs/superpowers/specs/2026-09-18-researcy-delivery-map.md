# Researcy Delivery Map

**Status:** Active delivery control — revision 2.0 approved
**Date:** 2026-09-24
**Master specification:** [`2026-09-18-researcy-system-design.md`](./2026-09-18-researcy-system-design.md), approved revision 2.0

## 1. Purpose

This map tracks the approved reader-first revision 2.0 requirements through bounded vertical milestones and records delivery gates without duplicating normative product or architecture requirements.

The approved master specification remains authoritative. A child specification may add local detail but may not silently override a master decision. This delivery map does not assert that a new route or capability is implemented or verified.

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

**Approved child specification:** [`2026-09-24-researcy-m1-sign-in-library-import-design.md`](./2026-09-24-researcy-m1-sign-in-library-import-design.md) — owner-approved on 2026-09-24.
**Approved implementation plan:** [`2026-09-24-researcy-m1-sign-in-library-import.md`](../plans/2026-09-24-researcy-m1-sign-in-library-import.md) — owner-approved on 2026-09-24; implementation completed and focused validation recorded in the [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md). All four real two-user exit gates remain pending.

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

**Status:** Not started

### M3 — ReaderAgent and Evidence-Linked PDF Reader

**Outcome:** The first independently demoable product lets a user ask a question about the active paper, receive a streaming grounded answer or refusal, and open each accepted citation at its exact passage in that paper's original PDF.

**Scope:**

- conversations and messages;
- ReaderAgent invoked by the existing `POST /api/conversations/:conversationId/messages:stream` route for the active paper only;
- PostgreSQL lexical retrieval, Qdrant dense retrieval, and Reciprocal Rank Fusion;
- bounded multi-turn context and at most one model-directed extra search restricted to the active paper;
- the configured product-runtime route `ag/gemini-3.8-flash-low` through 9Router;
- streaming `answer.delta`, `citation.resolved`, `answer.completed`, and `answer.failed` events;
- deterministic citation validation and quote/source/geometry resolution;
- a citation source identity containing `paper_id`, `document_version`, and `source_ref`, plus verbatim `evidence_quote`, page, and exact PDF-space boxes;
- PDF.js reader and outline, fixed PDF/Discussion workspace, page and citation URL state, exact evidence overlays, and inline evidence card;
- keyboard, focus, overflow, reduced-motion, and complete Discussion visual states;
- request-level agent trace, latency, and cost evidence.

**Exit gate:**

- the existing route streams an answer grounded only in the active user-owned paper, or a grounded refusal;
- every accepted citation resolves the composite source identity, verbatim quote, page, and exact PDF-space boxes; clicking it opens the correct original PDF and highlights those boxes without a second `Go to page` action;
- structured next-action qualification is exercised through the actual configured `ag/gemini-3.8-flash-low` route via 9Router before M3 may be marked `Verified`; a mock or isolated qualification does not pass;
- the qualification evidence records the real route, request outcome, structured agent trace, measured latency, and cost with its source;
- insufficient evidence, cross-paper or foreign-user sources, invalid/unresolvable geometry, and rejected structured next actions do not produce accepted claims;
- provider timeout, rate limit, provider failure, and interrupted stream states are actionable and recorded;
- the first demo journey works with keyboard input at supported desktop widths and shows a citation jump to the exact passage.

**Status:** Not started

### M4 — DiscoveryAgent Recommendations and Explicit Add

**Outcome:** On request, a user receives a small set of metadata-grounded related arXiv papers and chooses explicitly whether to add any of them to their Library.

**Scope:**

- DiscoveryAgent invoked only when requested through `POST /api/papers/:paperId/related:search`;
- official arXiv metadata search using the current paper's title plus abstract when available;
- at most three distinct actual arXiv IDs, with title, authors, metadata/abstract-grounded reason, arXiv URL, and request ID;
- recommendation rationales remain metadata-only and are not full-text citations;
- explicit user selection reuses the existing Library import flow; recommendations never auto-import;
- structured next-action qualification through the configured `ag/gemini-3.8-flash-low` product route via 9Router;
- request-level agent trace, latency, and cost evidence.

**Exit gate:**

- a real request through the route and configured 9Router path returns no more than three distinct, valid arXiv recommendations, with each rationale grounded only in returned arXiv metadata/abstract;
- structured next-action qualification is exercised on the real route before M4 may be marked `Verified`; the record contains the route, outcome, agent trace, measured latency, and cost with its source;
- no recommendation enters the user's Library until the user explicitly adds it through the existing import flow;
- no results produce `papers: []`; a missing title produces no invented recommendation; an unavailable arXiv API produces a retriable error and no fabricated result;
- invalid or duplicate IDs, provider failure, interrupted work, and rejected structured next actions are handled without displaying unsupported recommendations or importing papers.

**Status:** Not started

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
| SEC-01 | Untrusted PDF validation and bounded parser execution | 4, 17 | M2 | Not started | M1 provides validated-import prerequisites; M2 owns parser bounds and final security acceptance |
| JOB-01 | PostgreSQL durable jobs with claim leases and recovery | 8 | M2 | Not started | — |
| DOC-01 | Canonical document model with reversible provenance | 6 | M2 | Not started | — |
| PARSE-01 | Qualified scientific PDF parser | 7 | M2 | Designed | Q0 report; Q0.1 report; final delivery remains M2 |
| EMB-01 | On-device self-hosted embedding within the M1 budget | 9, 10, 20 | M2 | Designed | Q0.1 report: `bge-m3:567m` selected as hybrid dense component; final delivery remains M2 |
| IDX-01 | User- and paper-scoped Qdrant index | 5, 9 | M2 | Not started | — |
| RET-01 | Lexical + dense retrieval with RRF | 9 | M3 | Designed | Q0.1 report: hybrid Recall@5 6/8; final delivery remains M3 |
| GEN-01 | Vendor-hosted streaming grounded generation | 10 | M3 | Designed | Q0.1 report: three generation cases passed; final delivery remains M3 |
| CIT-01 | Citation validation and quote-to-geometry resolution | 10 | M3 | Designed | Q0.1 report and one-case display evidence; final exact-PDF delivery remains M3 |
| AGENT-01 | ReaderAgent — `POST /api/conversations/:conversationId/messages:stream` | 15 | M3 | Not started | Real-route structured next-action qualification, exact-PDF reader journey, agent trace, cost, and latency |
| AGENT-02 | DiscoveryAgent — `POST /api/papers/:paperId/related:search` | 15 | M4 | Not started | Real-route structured next-action qualification, metadata-only rationales, explicit add, agent trace, cost, and latency |
| AGENT-03 | ResearchAgent — `POST /api/papers/:paperId/research-directions:stream` | 15 | M5 | Not started | Selected-ready-paper citation journey, hypothesis labeling, agent trace, cost, latency, and evaluation |
| UX-01 | Simplified editorial Library experience | 12, 13 | M1 | Implemented | [M1 acceptance report](../reports/2026-09-24-researcy-m1-acceptance.md); Chromium responsive/state checks passed; real OAuth gate pending |
| UX-02 | Evidence-linked PDF and Discussion workspace | 12–14 | M3 | Not started | Reader UI and exact PDF citation acceptance remain M3 |
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

Master specification revision 2.0 and this delivery map were approved on 2026-09-24. Q0 remains `Verified` with its original and Q0.1 report/run links above. Q0.1 measured fused Recall@5 at 6/8, passed the three recorded generation cases, and browser-checked only one answerable case on Track D; it is not evidence of generalized multi-paper or production-agent quality. M1 and its M1-owned requirements are `Implemented`: planned code, focused suites, full-stack build, real arXiv/PDF local-session smoke, private-object integrity, responsive Chromium checks and local logout revocation are recorded in the M1 acceptance report. M1 is not `Verified` because the required two-real-Google-user four-gate journey has not run; M2–M5 retain their previous statuses. The configured product-runtime route remains `ag/gemini-3.8-flash-low` through 9Router; development-agent model selection is separate and does not change the product contract.
