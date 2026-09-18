# Researcy Delivery Map

**Status:** Active delivery control  
**Date:** 2026-09-18  
**Master specification:** [`2026-09-18-researcy-system-design.md`](./2026-09-18-researcy-system-design.md), revision 1.0

## 1. Purpose

This document maps the approved master specification to bounded vertical milestones. It tracks delivery gates and verification evidence without duplicating normative product or architecture requirements.

The master specification remains authoritative. A child specification may add local detail but may not silently override a master decision. A conflicting discovery pauses the milestone until the master specification is explicitly revised and approved.

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
Q0 Technical Qualification
        ↓
M1 Identity and Personal Library
        ↓
M2 Durable Paper Processing and Index
        ↓
M3 Grounded Conversation
        ↓
M4 Evidence-Linked Reader
        ↓
M5 Evaluation and Interview Readiness
```

The sequence is dependency-ordered for one developer. Only the active milestone receives a detailed implementation plan. Later plans are written after earlier evidence has removed their assumptions.

## 4. Milestones

### Q0 — Technical Qualification

**Outcome:** The highest-risk technical choices are supported by measurements before production implementation begins.

**Scope:**

- Docling versus a PyMuPDF-based geometry-first parser.
- Chunk-to-source-span-to-bounding-box feasibility.
- BGE-M3 through a native ARM64 Ollama runtime on the M1 with 8 GB RAM.
- Vendor-hosted streaming generation with structured citations.
- One complete quote-to-PDF-highlight proof.

**Exit gate:**

- parser decision recorded with corpus evidence;
- embedding model/runtime decision recorded with memory, latency, dimension, and retrieval evidence;
- generator contract qualified for streaming and structured citations;
- exact evidence resolution demonstrated on the golden paper;
- throwaway probe code is not treated as production foundation.

**Status:** Not started

### M1 — Identity and Personal Library

**Outcome:** A user signs in, adds a supported paper, and sees only their own library.

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

**Status:** Not started

### M2 — Durable Paper Processing and Index

**Outcome:** An accepted paper is processed asynchronously into a searchable, provenance-preserving index.

**Scope:**

- PostgreSQL durable jobs;
- `FOR UPDATE SKIP LOCKED`, leases, heartbeats, and retry;
- production parser adapter selected by Q0;
- canonical pages, sections, blocks, spans, chunks, and mappings;
- structure-aware chunking;
- on-device self-hosted embedding;
- Qdrant indexing;
- processing, failure, and retry UI states.

**Exit gate:**

- arXiv `1706.03762` reaches `ready` through observable stages;
- worker interruption recovers after lease expiry;
- indexing retry creates no duplicate chunks or vectors;
- paper becomes ready only after PostgreSQL and Qdrant invariants pass;
- a gold query retrieves evidence that maps back to page geometry.

**Status:** Not started

### M3 — Grounded Conversation

**Outcome:** A user asks the current paper a question and receives a streaming, validated answer or a grounded refusal.

**Scope:**

- conversations and messages;
- PostgreSQL lexical retrieval;
- Qdrant dense retrieval;
- Reciprocal Rank Fusion;
- bounded multi-turn context and conditional query rewrite;
- one vendor-hosted generator;
- stable streaming events;
- citation validation and one repair attempt;
- abstention, token use, latency, and cost records.

**Exit gate:**

- the normal question path uses one external paid generation request;
- follow-up retrieval uses bounded conversation context;
- every accepted citation refers to retrieved context from the current paper;
- unsupported questions produce grounded refusal;
- provider timeout, rate limit, and interrupted stream states are actionable.

**Status:** Not started

### M4 — Evidence-Linked Reader

**Outcome:** A user can move from a generated claim to its source evidence in one interaction.

**Scope:**

- PDF.js reader and outline;
- fixed PDF/Discussion workspace;
- page and citation URL state;
- exact evidence overlays;
- labelled approximate fallback;
- inline evidence card;
- keyboard, focus, overflow, and reduced-motion behavior;
- complete Discussion visual states.

**Exit gate:**

- clicking `[n]` navigates and highlights evidence immediately;
- no second `Go to page` action is required;
- `Escape` closes the evidence card and returns focus;
- a citation deep link restores page and citation state;
- the complete reader journey works with keyboard input at supported desktop widths.

**Status:** Not started

### M5 — Evaluation and Interview Readiness

**Outcome:** The north-star journey is reproducible and its AI, security, reliability, and cost claims are supported by evidence.

**Scope:**

- fixed annotated evaluation corpus;
- parsing, retrieval, citation, answer, product, and cost metrics;
- Compose stack and native embedding startup;
- health and readiness checks;
- security and ownership probes;
- failure recovery checks;
- browser acceptance journey;
- interview demo runbook.

**Exit gate:**

- one entry point reaches demo-ready state;
- the golden journey runs from Google login through exact evidence highlight;
- the evaluation report is reproducible;
- user isolation is verified with two accounts;
- critical failure and recovery paths have recorded evidence.

**Status:** Not started

## 5. Master requirement coverage

| ID | Master requirement | Master section | Delivery owner | Status | Verification evidence |
|---|---|---:|---|---|---|
| SYS-01 | Next.js + FastAPI modular monolith with one worker | 5 | M1 | Not started | — |
| AUTH-01 | Google OAuth followed by opaque server-side sessions | 16 | M1 | Not started | — |
| AUTH-02 | CSRF protection and user-scoped resource access | 16 | M1 | Not started | — |
| LIB-01 | User library with arXiv import and supported PDF upload | 3, 12 | M1 | Not started | — |
| SEC-01 | Untrusted PDF validation and bounded parser execution | 4, 17 | M1, M2 | Not started | — |
| JOB-01 | PostgreSQL durable jobs with claim leases and recovery | 8 | M2 | Not started | — |
| DOC-01 | Canonical document model with reversible provenance | 6 | M2 | Not started | — |
| PARSE-01 | Qualified scientific PDF parser | 7 | Q0, M2 | Not started | — |
| EMB-01 | On-device self-hosted embedding within the M1 budget | 9, 10, 20 | Q0, M2 | Not started | — |
| IDX-01 | User- and paper-scoped Qdrant index | 5, 9 | M2 | Not started | — |
| RET-01 | Lexical + dense retrieval with RRF | 9 | M3 | Not started | — |
| GEN-01 | Vendor-hosted streaming grounded generation | 10 | Q0, M3 | Not started | — |
| CIT-01 | Citation validation and quote-to-geometry resolution | 10 | Q0, M3, M4 | Not started | — |
| UX-01 | Simplified editorial Library experience | 12, 13 | M1 | Not started | — |
| UX-02 | Evidence-linked PDF and Discussion workspace | 12–14 | M4 | Not started | — |
| EVAL-01 | Fixed corpus and separated quality metrics | 11 | M5 | Not started | — |
| OPS-01 | Reproducible interview deployment and health checks | 19–21 | M5 | Not started | — |

A requirement with multiple milestones has one delivery owner and earlier qualification or dependency coverage. The final owner is responsible for recording verification evidence.

## 6. Gate update rules

1. Approving a child specification changes its milestone and covered requirements to `Designed`.
2. Approving its implementation plan changes the milestone to `Planned`.
3. Completing implementation without acceptance evidence changes it to `Implemented`.
4. Passing the exit gate and recording evidence changes it to `Verified`.
5. A failed check keeps the prior status and records the blocker; it never becomes partial credit.
6. A master-level conflict blocks the milestone until the master revision is approved.
7. Verification evidence must name the command, report, browser journey, or security probe that established the claim.

## 7. Current control point

The master specification is approved at revision 1.0. Q0 Technical Qualification is the next child specification to design. No production implementation plan is authorized before Q0 is approved and its bounded probe plan is written.
