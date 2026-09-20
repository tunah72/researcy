# Researcy System Design

**Status:** Approved master specification  
**Revision:** 1.1  
**Approved:** 2026-09-19  
**Timebox:** 4–6 weeks  
**Primary portfolio objective:** Demonstrate a complete, trustworthy end-to-end AI product  
**Authority:** Normative source for product scope, system boundaries, cross-cutting contracts, and acceptance criteria. Child specifications may add local detail but may not silently override this document.

Any architectural change that conflicts with this baseline requires an explicit master-spec revision and approval before its child specification or implementation plan changes.

## 1. Product thesis

Researcy is an evidence-first workspace for reading and discussing one scientific paper at a time. Its core loop is:

```text
Paper → Question → Grounded Answer → Evidence → Original PDF
```

The paper is the only knowledge source for an answer. Researcy must make each substantive claim traceable to evidence inside the paper and must abstain when the paper does not provide sufficient support.

Researcy is not a reduced clone of The Moonlight. It deliberately removes broad research-assistant features to make one loop reliable, explainable, and polished.

## 2. Success criteria

The primary demonstration imports arXiv `1706.03762`, processes it, opens the reader, asks a question, streams a grounded answer with inline citations, and lets the user click a citation to jump to and highlight the exact evidence in the PDF.

The MVP is successful when it proves all of the following:

1. A user can sign in with Google and see only their own library.
2. A user can import an arXiv paper or upload a supported PDF.
3. Ingestion runs asynchronously and exposes useful stage and failure states.
4. A user can ask multi-turn questions about one paper.
5. Answers contain claim-level citations to the current paper.
6. Clicking a citation immediately navigates to and highlights its evidence.
7. Approximate evidence resolution is labelled honestly.
8. Questions unsupported by the paper produce a grounded refusal.
9. The application can be started reproducibly for an interview demonstration.
10. Evaluation separates parsing, retrieval, citation, answer, product, and cost quality.

## 3. Scope

### 3.1 MVP

- Google OAuth and opaque server-side sessions.
- User-scoped paper library.
- arXiv URL/ID import.
- Direct upload of born-digital scientific PDFs with a text layer.
- Asynchronous parsing, normalization, chunking, embedding, and indexing.
- Scientific-document retrieval scoped to one paper.
- Streaming, multi-turn discussion.
- Inline citations with exact evidence navigation when possible.
- Transparent page/block fallback when exact resolution is not reliable.
- Fixed evaluation corpus and reproducible interview deployment.

### 3.2 Explicit non-goals

- Agents or autonomous tool loops.
- Web search or answers from sources outside the current paper.
- Multi-paper reasoning.
- Recommendations or discovery feeds.
- Translation, summaries, equation explanation, or image explanation as separate tools.
- Collaboration, sharing, notes, ratings, or reading-state management.
- OCR for scanned PDFs.
- Arbitrary publisher connectors.
- Mobile paper reader.
- Multiple model selectors in the UI.
- Microservices, autoscaling, multi-region deployment, or enterprise observability.

## 4. Supported document boundary

The MVP supports born-digital scientific PDFs with an extractable text layer. Common one-column and two-column papers are in scope.

The system rejects or clearly warns about:

- scanned or image-only PDFs;
- encrypted or password-protected PDFs;
- corrupt files;
- files exceeding configured size or page limits;
- documents with text coverage below the supported threshold.

Tables, captions, and equations retain parser-provided position and text when available. The MVP does not promise visual table understanding or mathematical interpretation. A citation may point to a whole table, equation block, or surrounding explanatory text when finer evidence is unavailable.

## 5. System architecture

```text
Browser
  ↓
Next.js experience layer
  ↓
FastAPI modular monolith
  ├── PostgreSQL relational data + durable jobs
  ├── Qdrant
  ├── S3-compatible object storage
  ├── Hosted generation API
  └── Python worker → self-hosted embedding runtime
```

### 5.1 Next.js

Next.js owns:

- landing, authentication entry, Library, Reader, and Discussion UI;
- PDF rendering and evidence overlays;
- streaming answer presentation;
- URL state for paper, page, selected citation, search, and supported filters;
- short-lived client interaction state.

Next.js does not own retrieval, prompt logic, authorization rules, or ingestion business logic.

### 5.2 FastAPI modular monolith

The backend is one deployable application divided into domain modules:

- `auth`
- `papers`
- `ingestion`
- `documents`
- `conversations`
- `retrieval`
- `generation`
- `citations`

Modules communicate through explicit Python service boundaries inside the same codebase. They are not separate network services.

### 5.3 Python worker

The worker uses the same domain package and schema as the API but runs separately. It performs:

1. source acquisition and validation;
2. parsing and structure extraction;
3. canonical normalization and provenance mapping;
4. structure-aware chunking;
5. embedding;
6. Qdrant indexing;
7. invariant checks and publication of the ready state.

Each stage is idempotent by `document_version` and deterministic artifact keys.

### 5.4 Data ownership

**PostgreSQL is authoritative for:**

- users and sessions;
- papers and immutable document versions;
- ingestion jobs, stage progress, attempts, and errors;
- pages, sections, blocks, spans, chunks, and provenance mappings;
- conversations, messages, answers, claims, and citations;

**Object storage is authoritative for:**

- original PDFs;
- immutable parser artifacts;
- optional page thumbnails and diagnostic overlays.

**Qdrant stores:**

- embedding vectors;
- `chunk_id`;
- minimal filter payload: `owner_id`, `paper_id`, `document_version`, and `section_type`.

Qdrant never becomes the authoritative store for paper text, conversations, job state, or provenance.

## 6. Canonical document model

```text
Paper
└── DocumentVersion
    ├── Pages
    │   └── Blocks
    │       └── TextSpans
    ├── Sections
    └── Chunks
        └── ChunkSpanMappings
```

### 6.1 Entities

- **Paper:** logical library item with title, authors, source, and active version.
- **DocumentVersion:** immutable PDF hash plus parser and configuration versions.
- **Page:** page index, dimensions, and rotation.
- **Block:** heading, paragraph, list, caption, table text, header, or footer.
- **TextSpan:** smallest retained text-and-geometry unit with reading order and bounding box.
- **Section:** logical document hierarchy and ordered blocks.
- **Chunk:** retrieval unit derived from contiguous content within one section.
- **ChunkSpanMapping:** maps normalized chunk character ranges to source spans.

Bounding boxes use PDF coordinate space and retain page dimensions and rotation. They are never stored as viewport pixels. PDF.js applies the final viewport transform.

### 6.2 Chunk invariants

Every chunk must:

1. belong to exactly one document version;
2. stay within one logical section;
3. reference at least one source span;
4. map evidence text back to source geometry;
5. have a deterministic checksum;
6. exclude detected repeating headers and footers from retrieval text.

Chunk size and overlap are selected by evaluation. Boundaries prefer paragraphs and never cross sections. Section headings are included as contextual metadata.

## 7. Ingestion

### 7.1 State machine

```text
queued
→ validating
→ parsing
→ normalizing
→ chunking
→ embedding
→ indexing
→ ready
          ↘ failed(stage, code, actionable_message)
```

The paper becomes `ready` only after PostgreSQL and Qdrant invariants pass. A failed new document version does not corrupt a previously ready version.

### 7.2 Parser qualification

The canonical model is parser-independent. A bounded spike compares:

1. Docling as a structure- and layout-aware parser;
2. a PyMuPDF-based geometry-first pipeline with explicit reading-order and section heuristics.

Q0 uses a representative two-paper subset: arXiv `1706.03762` plus one table/caption-heavy two-column paper. Broader evaluation before production acceptance adds one-column, figure-heavy, and alternative publication layouts.

The decision uses:

- reading-order correctness;
- section detection;
- header/footer removal;
- text coverage;
- chunk-to-bounding-box resolution rate;
- click-to-highlight correctness;
- parse latency;
- peak memory on the Apple M1 with 8 GB RAM.

GROBID is not part of the MVP baseline because it adds another runtime and does not directly remove the need for geometry reconciliation.

## 8. Queue and job reliability

PostgreSQL is both the authoritative job ledger and the durable queue. The MVP does not add Redis or a separate broker.

### 8.1 Dispatch flow

```text
Database transaction
  ├── create paper/document version
  └── insert queued ingestion job
          ↓
Worker claims one due job
  SELECT ... FOR UPDATE SKIP LOCKED
          ↓
Worker executes idempotent stages
          ↓
PostgreSQL stage/progress/result
```

The API commits the paper, document version, and job atomically. It can then return `202 Accepted`; ingestion does not depend on the HTTP connection remaining open.

### 8.2 Claim and recovery contract

- One worker polls for due jobs with bounded backoff.
- Claiming uses a short transaction and `FOR UPDATE SKIP LOCKED` so two workers cannot claim the same available row concurrently.
- A claimed job records `locked_by`, `lease_expires_at`, `heartbeat_at`, `attempts`, and the current stage.
- The worker commits the claim before performing expensive work; it never holds a database transaction open while parsing or embedding.
- Heartbeats extend the lease during long stages.
- A worker crash leaves durable stage state. After lease expiry, the job becomes claimable again.
- Retry sets `run_after` using bounded backoff and preserves a safe error code.
- Execution remains at least once, so every stage uses deterministic artifact keys and idempotent writes.
- One worker is the default on the 8 GB interview machine. The schema still permits multiple workers without changing the claim contract.

This design removes Redis, a transactional outbox, and cross-system queue consistency. A dedicated broker can be introduced only if measured queue throughput, scheduling, or worker distribution requirements outgrow PostgreSQL.

## 9. Retrieval

Each question follows a fixed workflow:

```text
Current question + bounded conversation context
→ standalone retrieval query when required
→ lexical retrieval + dense retrieval
→ Reciprocal Rank Fusion
→ deterministic context packing
→ grounded generation
```

### 9.1 Dense retrieval

- An on-device self-hosted embedding model of at most approximately 0.8B parameters produces query and chunk vectors on the interview MacBook.
- Qdrant search is always filtered by backend-generated `owner_id`, `paper_id`, and `document_version`.
- BGE-M3 is the initial model candidate. It is retained only if native ARM64 benchmarks show acceptable memory, latency, and retrieval quality on the fixed evaluation set.
- A native Ollama runtime is the default serving candidate. FastAPI and the worker access the single loaded model through an internal HTTP client; containers reach the host runtime through the configured host address.
- Model identity, runtime packaging, quantization, vector dimension, and embedding version are recorded separately. Changing the embedding model creates a new index version; vectors from different models are never mixed.

### 9.2 Lexical retrieval

PostgreSQL full-text search preserves exact terms, acronyms, method names, and phrases that dense retrieval can miss.

### 9.3 Fusion and reranking

Reciprocal Rank Fusion combines lexical and dense ranks without pretending their raw scores are calibrated. A reranker is not in the baseline. A small local cross-encoder is added only when evaluation shows a material retrieval gain within the memory and latency budget.

### 9.4 Multi-turn behavior

- Full messages are persisted.
- Retrieval receives the current question and a bounded conversation window.
- Follow-ups may be rewritten into one standalone retrieval query.
- The raw user question is preserved for generation.
- Previous answers are context, never evidence.
- There is no agent memory, planning loop, or autonomous tool selection.

## 10. Generation and citation grounding

The hosted generation provider must support streaming and structured output reliably enough to implement the following provider-neutral contract:

```json
{
  "answer": "A supported claim [1].",
  "citations": [
    {
      "marker": 1,
      "source_ref": "S1",
      "evidence_quote": "verbatim text from the retrieved source"
    }
  ]
}
```

The backend exposes stable stream events:

- `answer.delta`
- `citation.resolved`
- `answer.completed`
- `answer.failed`

Provider-specific event shapes never reach the frontend.

### 10.1 Model locations and request budget

Researcy distinguishes three request types:

1. **Application API request:** the browser calls FastAPI. This is not a model request.
2. **Internal embedding request:** FastAPI or the worker calls the on-device self-hosted embedding runtime. It does not leave the machine and has no per-token vendor charge.
3. **External paid generation request:** FastAPI calls the vendor-hosted generator over HTTPS with server-side credentials.

Ingestion uses local deterministic parsing and chunking, batched internal embedding requests, and local Qdrant indexing. It makes zero external paid model requests.

For an independent question, the baseline performs one internal query-embedding request, lexical and dense retrieval, and one external generation request. A short or anaphoric follow-up may add one external query-rewrite request before retrieval. Citation validation is local deterministic computation; only failed validation may add one external repair request, attempted at most once.

| Flow | External paid model requests |
|---|---:|
| Paper ingestion | 0 |
| Independent question | 1 |
| Follow-up requiring query rewrite | 2 |
| Citation repair | Adds at most 1 |
| Worst case for one turn | 3 |

The normal path is one paid request per question; the worst case is not the target operating mode. Rewrite and repair rates are recorded so repeated extra calls reveal a pipeline defect rather than becoming accepted cost.

The vendor-hosted generator receives only grounding instructions, bounded conversation context, and selected chunks with stable source IDs—not the complete PDF. It must support streaming, structured citation output, token usage metadata, and clear timeout/error behavior. The MVP configures one qualified generator and does not implement automatic multi-provider fallback.

Hosted credentials remain server-side. Input context and output tokens are bounded, usage and estimated cost are recorded without prompt contents, and a request is not blindly retried after streaming has begun.

The backend keeps separate `EmbeddingClient` and `GenerationClient` interfaces because their batching, lifecycle, failure, privacy, and cost semantics differ. It does not introduce a universal model-provider abstraction.

### 10.2 Runtime citation validation

For each citation:

1. `source_ref` must be part of the retrieved context for that request.
2. `evidence_quote` must match the source after allowed normalization.
3. Quote offsets map through `ChunkSpanMapping` to source spans.
4. Successful resolution returns page and exact boxes.
5. Ambiguous same-page resolution returns a labelled page/block fallback.
6. Unreliable resolution rejects the citation.
7. The backend attempts at most one repair.
8. An answer still lacking support for a substantive claim becomes a grounded refusal.

Runtime validation proves that cited text exists in the current paper and can be located. It does not claim to prove perfect semantic entailment; citation correctness is measured separately.

### 10.3 Abstention

When calibrated retrieval and citation checks do not establish enough evidence, the system states that it could not find sufficient support in the paper. It does not fill gaps with model knowledge.

## 11. Evaluation

The fixed evaluation corpus contains 5–8 supported scientific PDFs with varied layouts. It includes answerable questions with annotated evidence, unanswerable questions, and follow-up questions.

| Layer | Measurements |
|---|---|
| Parsing | text coverage, reading order, section quality, span-to-box resolution |
| Retrieval | Recall@K, MRR, contribution of lexical/dense fusion |
| Citation | source precision, citation completeness, page accuracy |
| Answer | correctness rubric, groundedness, abstention accuracy |
| Product | ingest latency, time to first token, successful citation jumps |
| Cost | hosted tokens and estimated cost per question |

Parser, chunker, embedding, retrieval, and prompt changes run against the same dataset. A component is not declared better without measured improvement or a documented product trade-off.

## 12. Information architecture and UX

### 12.1 Product surfaces

```text
Landing → Google sign-in → Library → Paper Reader + Discussion
```

There is one top-level product destination: Library. The MVP does not need breadcrumbs or a persistent navigation rail with one item.

### 12.2 Library

The Library contains:

- Researcy brand and account access;
- one primary `Add paper` action;
- search by title or author;
- a single list of papers.

`Add paper` presents exactly two options: arXiv URL/ID and PDF upload.

List/grid switching and source/year/sort filters are excluded from the MVP. A row shows title, authors, year, and source. Processing or failed papers additionally show the current stage and an actionable detail/retry control. Ready papers do not carry redundant status badges.

### 12.3 Reader

Desktop layout:

```text
Top bar: Back · Paper title · Download

[ collapsible outline ] [ PDF approximately 65% ] [ Discussion approximately 35% ]
```

- The PDF is the visual center.
- The outline collapses when space is constrained.
- The split ratio is fixed in the MVP; no draggable splitter.
- PDF and Discussion have independent scrolling.
- The composer remains visible without covering messages.
- Discussion is disabled with useful stage information until the paper is ready.
- Landing, authentication, and Library remain responsive.
- Below the supported desktop width, Reader explains that a larger screen is required.

### 12.4 Citation interaction

Clicking `[n]` performs one atomic interaction:

1. update URL state with page and citation;
2. navigate the PDF to the evidence page;
3. highlight exact spans or the labelled fallback region;
4. open an inline evidence card under the answer.

The card shows page, section, a short quote, and `Approximate location` when applicable. It is a labelled non-modal region, not a dialog. There is no second `Go to page` action.

`Escape` closes the evidence card and returns focus to the citation. The PDF remains on the selected page. Selecting another citation replaces the current card and highlight.

### 12.5 Discussion states

The UI explicitly supports:

- empty conversation with a small set of paper-derived suggested questions;
- retrieval in progress;
- streaming answer;
- completed answer with citations;
- grounded refusal;
- hosted-provider or rate-limit error with retry;
- interrupted stream;
- exact, approximate, and unavailable citation resolution.

The interface discloses:

> Answers are generated from this paper. Verify important claims against the highlighted source.

The UI does not show vector scores, chunk IDs, provider names, model names, or hidden reasoning.

## 13. Visual system

The visual direction is editorial, restrained, and content-first. The existing V4 exploration is the baseline, with the changes in this specification.

### 13.1 Typography

- Crimson Pro for the wordmark, landing headline, and limited editorial moments.
- Atkinson Hyperlegible for controls, body UI, metadata, and Discussion.
- The PDF retains its original typography.

### 13.2 Color roles

- Warm paper and ink dominate the interface.
- Scholarly navy identifies actions, links, and focus.
- Muted ochre/gold is reserved for citations and evidence highlights.
- Red is reserved for destructive actions and errors.
- Final token values must pass contrast checks before implementation.

### 13.3 Motion and craft

- CSS transitions of approximately 150–200 ms for hover, focus, and small state changes.
- No decorative scroll choreography in the workspace.
- `prefers-reduced-motion` removes non-essential movement.
- Icons use one SVG icon family and always have accessible names when interactive.
- No gradient AI motifs, purple glow, glassmorphism, or emoji icons.

## 14. Accessibility

- Every action is keyboard reachable.
- Tab order follows visual order.
- Every focused control has a visible focus indicator.
- Sticky UI and source cards do not obscure focused elements.
- Long titles, URLs, and technical tokens wrap without breaking the split layout.
- Citation controls expose `aria-expanded` and `aria-controls`.
- Evidence cards do not trap focus.
- Streaming status uses restrained live-region announcements.
- Form errors are associated with their fields and summarized when necessary.

## 15. API contract

```text
GET    /api/me
GET    /api/papers
POST   /api/papers/arxiv
POST   /api/papers/upload
GET    /api/papers/:paperId
DELETE /api/papers/:paperId

GET    /api/jobs/:jobId
POST   /api/jobs/:jobId/retry

GET    /api/papers/:paperId/conversations
POST   /api/papers/:paperId/conversations
POST   /api/conversations/:conversationId/messages:stream

GET    /api/citations/:citationId
```

- Mutating import requests accept an idempotency key.
- Clients never send an owner ID.
- Errors contain a stable code, safe user message, and request ID.
- The exact OpenAPI schema is produced during implementation planning from these behavior contracts.

## 16. Authentication and authorization

FastAPI owns Google OAuth and opaque sessions. Next.js does not create a second authentication system.

The browser authentication mechanism does not use an application JWT. Google ID and access tokens are validated only as part of the OAuth callback and are not reused as Researcy session credentials. FastAPI issues its own random opaque session after login. JWT can be reconsidered only if Researcy later adds a native client, third-party public API, or independently deployed services that need portable signed access tokens.

- OAuth uses Authorization Code with PKCE, `state`, and `nonce`.
- Raw session tokens are CSPRNG values stored only in an `HttpOnly`, `SameSite=Lax`, `Path=/` cookie with `Secure` under HTTPS.
- PostgreSQL stores only a keyed lookup hash of the session token.
- Logout revokes the session server-side.
- State-changing cookie-authenticated requests require a readable CSRF cookie copied into `X-CSRF-Token` and compared in constant time.
- Import and generation endpoints are rate-limited per authenticated user with persistent state.

Every private lookup includes both the resource identifier and the authenticated user identifier. Foreign and nonexistent resources both return `404`. Client-provided ownership and Qdrant filters are never trusted.

## 17. Untrusted PDF handling

- Validate file signature, MIME, size, page count, encryption, and minimum text coverage.
- Never derive object-storage paths directly from filenames.
- Run parsing as a non-root process with time and memory bounds.
- Do not execute embedded PDF actions or JavaScript.
- Do not log document text, prompts, session values, CSRF values, or API keys.
- Deletion starts an observable cleanup job for object storage and Qdrant.

## 18. Error and recovery behavior

| Failure | Product behavior | Recovery |
|---|---|---|
| Invalid or scanned PDF | Explain the unsupported condition before queueing | Upload a supported paper |
| Parser failure | Show failed stage and request ID | Retry version or reprocess |
| Embedding runtime unavailable | Preserve paper and job state | Restore runtime; retry embedding |
| Qdrant unavailable | Do not publish `ready` | Retry idempotent indexing |
| Worker crashes or stops heartbeating | Preserve durable stage state | Reclaim after lease expiry and resume idempotently |
| Concurrent or repeated claim | Only one active lease; no duplicate chunks or vectors | `SKIP LOCKED` plus idempotent stage execution |
| Hosted LLM timeout or rate limit | Do not save a completed answer | Retry turn |
| Stream disconnect | Mark turn interrupted | Reload state and retry |
| Citation validation failure | Repair once | Grounded refusal |

## 19. Observability

Structured logs include:

- request, job, paper, and document-version correlation IDs;
- ingestion stage durations;
- parser and embedding configuration versions;
- retrieval and generation latency;
- token usage and estimated hosted cost;
- safe error codes.

Health endpoints separate liveness from readiness for PostgreSQL, Qdrant, object storage, and the embedding runtime. Grafana, distributed tracing, and a custom admin dashboard are outside the MVP.

## 20. Deployment

The interview environment uses Docker Compose for:

- `web`
- `api`
- `worker`
- `postgres`
- `qdrant`
- `minio`

The embedding runtime runs natively on ARM64 on the interview MacBook, with Ollama as the default serving candidate. This avoids loading model weights in both API and worker processes and avoids Docker architecture emulation. Containerized API and worker processes use the same internal HTTP contract to reach the host runtime.

A single demo entry point must:

1. validate configuration and secrets;
2. start dependencies with health checks;
3. apply database migrations;
4. verify Qdrant, object storage, embedding, and hosted generation access;
5. warm the on-device self-hosted embedding model;
6. print the application URL and readiness result.

No always-on public deployment is required.

## 21. Verification

### 21.1 Contract and integration checks

- session cookie and CSRF behavior;
- ownership isolation for SQL resources and Qdrant searches;
- exclusive job claim under concurrent workers;
- expired-lease recovery after worker interruption;
- idempotent retry from persisted stage state;
- PostgreSQL-to-Qdrant readiness invariant;
- citation quote-to-span-to-box resolution.

### 21.2 Browser acceptance journey

1. Sign in with Google.
2. Import arXiv `1706.03762`.
3. Observe useful ingestion stages.
4. Open the ready paper.
5. Ask the golden question.
6. Observe a streaming answer with citations.
7. Click a citation.
8. Confirm page navigation and exact evidence highlight.
9. Ask an unsupported question and observe abstention.
10. Verify a second user cannot access the paper.

### 21.3 UI quality checks

- actual browser verification at supported desktop widths;
- no horizontal overflow or clipped controls;
- complete keyboard journey;
- focus remains visible when evidence cards and sticky composer are present;
- contrast checks for text, actions, focus, errors, and evidence;
- reduced-motion behavior;
- all empty, processing, failure, streaming, refusal, and citation states.

## 22. Principal risks and mitigations

### 22.1 Exact evidence mapping fails after normalization

Keep explicit character-range mappings during every normalization step. Reject transformations that cannot preserve provenance. Use a labelled page/block fallback rather than fabricated precision.

### 22.2 Parser quality varies across scientific layouts

Qualify two bounded parser pipelines against a fixed corpus before committing. Keep parser outputs behind the canonical document model.

### 22.3 On-device embedding exceeds the 8 GB memory budget

Run one worker concurrently, serve one native model instance, benchmark peak memory alongside the Compose stack, and select a smaller embedding model when BGE-M3 does not produce enough retrieval improvement to justify its memory cost. Do not silently switch to a vendor embedding API because that changes cost, privacy, and vector-space contracts.

### 22.4 Hosted generation produces invalid or unsupported citations

Constrain sources with stable IDs, require verbatim evidence quotes, validate every citation, allow one repair, and otherwise abstain.

### 22.5 Long-running jobs become stuck

Use short claim transactions, explicit leases, heartbeats, stage checkpoints, bounded retry backoff, and a recovery query for expired leases. Never hold a database transaction open during parsing, embedding, or indexing.

### 22.6 Scope grows toward The Moonlight feature breadth

Use the north-star loop and explicit non-goals as the acceptance filter. A feature belongs in the MVP only when it materially improves import, questioning, grounded answers, evidence navigation, or trust.

## 23. Decisions and rejected alternatives

- **Chosen:** evidence-first modular monolith plus worker.  
  **Rejected:** demo-only chat-with-PDF pipeline and research-heavy multi-service system.

- **Chosen:** Qdrant for vector retrieval.  
  **Rejected:** pgvector, by explicit project decision.

- **Chosen:** PostgreSQL-backed durable jobs claimed with `FOR UPDATE SKIP LOCKED`, leases, and heartbeats.  
  **Rejected:** Redis/Dramatiq plus transactional outbox because one low-concurrency worker does not justify the additional service and consistency boundary.

- **Chosen:** hybrid lexical and dense retrieval with RRF.  
  **Rejected:** dense-only baseline and mandatory reranker.

- **Chosen:** inline evidence card with immediate jump/highlight.  
  **Rejected:** V4 floating citation dialog and second `Go to page` action.

- **Chosen:** simplified Library and fixed Reader split.  
  **Rejected:** premature filters, list/grid switching, and draggable panels.

- **Chosen:** on-device self-hosted embedding through a native ARM64 runtime plus one vendor-hosted generation API.  
  **Rejected:** vendor-hosted embeddings, duplicated in-process model loads, and a fully local generator on the 8 GB interview machine.

- **Chosen:** Google OAuth followed by an opaque server-side application session.  
  **Rejected:** application JWT for the browser because the MVP benefits from revocation and has no portable-token consumer.

## 24. Design approval history

The following sections were reviewed and approved in conversation:

1. system boundaries and Qdrant data ownership;
2. canonical document model and ingestion contract;
3. retrieval, generation, citation, and evaluation design;
4. V4-derived product UX and visual direction using `ui-ux-pro-max` guidance;
5. reliability, security, verification, and the final PostgreSQL-only job decision.
6. on-device self-hosted embedding terminology and external model request budget.
7. balanced Q0 qualification scope using a two-paper representative subset before broader M5 evaluation.
