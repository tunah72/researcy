# Researcy System Design

**Status:** Approved master specification
**Revision:** 2.0
**Approved:** 2026-09-24
**Baseline:** Revision 1.1 approved 2026-09-19
**Delivery:** Milestone-gated M1–M5; no calendar timebox
**Primary portfolio objective:** Demonstrate a trustworthy, reader-first research product with optional, bounded discovery and research-direction workflows
**Authority:** Normative source for product scope, system boundaries, cross-cutting contracts, and acceptance criteria. Child specifications may add local detail but may not silently override this document.
**Change control:** A conflicting child specification or implementation plan requires an explicit master-spec revision and approval.

## 1. Product thesis

Researcy is a reader-first, evidence-linked workspace. The product journey is:

```text
Google sign-in → Library → one-paper Reader + Discussion
                              → optional Related papers
                              → optional Research directions
```

The PDF Reader and one-paper Discussion remain the product's default view and visual focus. `ReaderAgent` answers from the active paper only. `DiscoveryAgent` is an explicit, on-demand search of arXiv metadata; a result is never imported automatically. `ResearchAgent` is an explicit, on-demand workflow over the active paper and one to three related papers that the user has added to their own Library and that are ready.

Substantive answer claims must be grounded in the permitted paper text and cite the verbatim passage in its immutable source PDF. A citation resolves only when its source identity and exact PDF-space evidence boxes validate. If evidence is insufficient or cannot be resolved exactly, the system refuses or reports unavailable evidence rather than presenting an approximate page location as a successful citation. Discovery rationales are metadata/abstract-based and are not full-text citations.

These three bounded roles run only for their corresponding user action. They do not create a general web-research assistant, run in the background, silently widen source scope, or make import decisions for the user.

## 2. Success criteria

The product journey starts with Google sign-in and a user-owned Library. Its first independently demoable product is the one-paper Reader: import and process arXiv `1706.03762`, open its PDF and Discussion, ask a supported question about Transformer parallelization, stream a grounded answer, and click a citation to open the exact original PDF passage with its exact boxes highlighted. Related-paper search and research directions are optional later actions, not prerequisites for reading.

The product is accepted only when the future milestone gates in §21 establish all of the following:

1. Google sign-in, opaque server-side sessions, and Library lookups preserve user ownership.
2. arXiv URL/ID import and supported born-digital PDF upload enter durable asynchronous processing with visible progress and failure states.
3. The Reader remains the default experience and `ReaderAgent` answers about the active paper only, with streaming, multi-turn context, and grounded abstention.
4. Every accepted Reader or ResearchAgent full-text citation persists `paper_id`, `document_version`, `source_ref`, the verbatim `evidence_quote`, page, and exact PDF-space boxes. Clicking it opens the cited paper/version and highlights those boxes; page-only or approximate resolution does not pass.
5. `DiscoveryAgent` is opt-in, searches the official arXiv metadata API, returns at most three unique arXiv papers with metadata-grounded rationales, and creates no Library item or ingestion job. The user must explicitly add a recommendation through the existing import flow.
6. `ResearchAgent` runs only after the user selects one to three ready, user-owned related papers. Supported factual premises cite the correct original paper and exact passage; proposed directions and methods are visibly labelled hypotheses rather than findings.
7. Missing metadata, empty results, insufficient evidence, unavailable or rate-limited dependencies, invalid selections, and interrupted streams produce safe, visible recovery states without fabricated results.
8. Each on-demand run has bounded model passes and records role, selected tool/action, permitted paper IDs, model-call count, token/cost totals, latency, and validation outcome without logging prompts, document text, or secrets.
9. M3 and M4 are not accepted until structured next-action output is qualified on the real configured product route and a validated response drives only the intended bounded LangGraph branch.
10. Evaluation separates parser, retrieval, exact citation, answer, agent-route, product, latency, and cost quality. Q0's verified findings remain historical evidence, not proof of these future agent behaviors.

This revision sets scope and gates only; it does not claim that any implementation milestone is complete.

## 3. Scope

Q0 remains `Verified` as documented in the read-only Q0.1 report. M1–M5 are all `Not started`. Approval of this specification makes no application-implementation or agent-qualification claim.

### 3.1 Product scope

- Google OAuth and opaque server-side sessions.
- A user-scoped Library with arXiv URL/ID import and born-digital scientific PDF upload.
- Durable asynchronous parsing, normalization, chunking, embedding, and indexing.
- A one-paper PDF Reader with multi-turn Discussion and exact, claim-level citation navigation.
- `ReaderAgent`, invoked by the existing Discussion composer for the active `paper_id` only: hybrid retrieval, at most one model-directed extra search constrained to that paper, streaming grounded answer, deterministic citation validation, and refusal when support is insufficient.
- `DiscoveryAgent`, invoked only when the user requests related papers: official arXiv metadata API search using the active paper's title and abstract when available; inspect at most 10 unique results, exclude the active paper and duplicates, and return at most three distinct arXiv IDs with metadata-grounded rationale and arXiv link. Missing title is an actionable metadata state, not a guessed query.
- An explicit `Add to Library` action for a recommendation, reusing the existing arXiv import path. Searching never downloads a PDF, creates a Library item, or queues ingestion.
- `ResearchAgent`, invoked only after the user selects one to three related papers already in their Library and `ready`: retrieve across the active paper and those selected papers and return a short `observed gap → proposed direction → possible method` list. Factual premises have exact citations to their own source; directions and methods are hypotheses, not claims of novelty or feasibility.
- Fixed evaluation and reproducible interview deployment; retain the Reader as default and visual focus.

Delivery proceeds through acceptance gates, not a calendar promise:

| Milestone | Scope | Current status |
|---|---|---|
| M1 | Google sign-in, Library, and import entry points | Not started |
| M2 | Durable PDF processing and owner-scoped ready/indexed papers | Not started |
| M3 | ReaderAgent, Reader UI, exact PDF citation, and first independently demoable product | Not started |
| M4 | DiscoveryAgent and explicit recommendation import | Not started |
| M5 | ResearchAgent over the active paper plus one to three selected ready papers, with end-to-end evaluation | Not started |

M3 and M4 require the real-route structured next-action qualification gate in §§10 and 21. If the configured route fails qualification, the affected milestone stays blocked; a deterministic RAG path may remain usable but is not described as an Agent.

### 3.2 Explicit non-goals

- General web search or source corpora beyond the official arXiv metadata search for user-requested discovery and the papers explicitly selected for a ResearchAgent run.
- Background, unbounded, or self-initiated agent runs; automatic discovery on paper open; automatic downloading or importing; and model-controlled ownership, paper, or version filters.
- Discovery feeds, broad research-assistant functionality, and claims that generated directions are novel or feasible.
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

Tables, captions, and equations retain parser-provided position and text when available. A citation to a whole block is acceptable only when the verbatim quote maps to that block's exact PDF-space boxes. If exact source geometry cannot be established, the citation is unavailable and the claim must be repaired or refused; a page-only or approximate location is not an accepted citation.

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
  ├── Python LangGraph orchestration (inside this API; exactly three bounded roles)
  ├── Configured generation route through local 9Router
  └── Python worker → native self-hosted embedding runtime
```

### 5.1 Next.js

Next.js owns:

- landing, authentication entry, Library, Reader, Discussion, and the compact in-Reader related-paper/research-direction controls;
- PDF rendering and exact evidence overlays;
- streaming answer and research-direction presentation;
- URL state for paper, page, selected citation, search, and supported filters;
- short-lived client interaction state.

Next.js does not own retrieval, prompt logic, authorization rules, agent tool execution, or ingestion business logic.

### 5.2 FastAPI modular monolith

The backend remains one deployable application divided into domain modules:

- `auth`
- `papers`
- `ingestion`
- `documents`
- `conversations`
- `retrieval`
- `generation`
- `citations`
- in-process Python LangGraph orchestration for `ReaderAgent`, `DiscoveryAgent`, and `ResearchAgent`

Each explicit user action starts one bounded graph run in the existing FastAPI service. Graph nodes call existing backend services through explicit Python boundaries. They are not separate network services, and the design adds no agent server or second agent framework. Backend tools derive ownership and paper/version filters; model output never supplies them.

### 5.3 Python worker

The existing worker continues to process document jobs only. It uses the same domain package and schema as the API and performs:

1. source acquisition and validation;
2. parsing and structure extraction;
3. canonical normalization and provenance mapping;
4. structure-aware chunking;
5. embedding;
6. Qdrant indexing;
7. invariant checks and publication of the ready state.

Each stage is idempotent by `document_version` and deterministic artifact keys. Agent runs are request-scoped API work, not durable document-processing jobs or a new worker service.

### 5.4 Data ownership

**PostgreSQL is authoritative for:**

- users and sessions;
- papers and immutable document versions;
- ingestion jobs, stage progress, attempts, and errors;
- pages, sections, blocks, spans, chunks, and provenance mappings;
- conversations, messages, answers, claims, and citations, including ResearchAgent premise citations with their composite source identities;

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

Each ReaderAgent request is restricted to the authenticated user's active `paper_id` and immutable `document_version`:

```text
Current question + bounded conversation context
→ lexical retrieval + dense retrieval
→ Reciprocal Rank Fusion
→ deterministic context packing
→ structured next action: answer OR one extra search on the same paper
→ grounded answer and exact citation validation
```

The extra search is optional, occurs at most once, and can only change the query. Server code fixes the authorized paper, version, and owner filters. A model cannot widen scope or choose a different paper.

ResearchAgent retrieval uses the same hybrid lexical/dense retrieval and RRF over a server-validated allowlist containing the active paper and one to three explicitly selected related papers. Selected IDs must be unique, owned by the authenticated user, distinct from the active paper, and `ready`; each retrieved chunk retains its own paper, version, source reference, and geometry. DiscoveryAgent searches official arXiv metadata, not the full-text retrieval index.

### 9.1 Dense retrieval

- An on-device self-hosted embedding model of at most approximately 0.8B parameters produces query and chunk vectors on the interview MacBook.
- Qdrant search is always filtered by backend-generated `owner_id`, `paper_id`, and `document_version`. For ResearchAgent, the backend allowlist is exactly the active paper plus the validated selected papers.
- BGE-M3 is the initial model candidate. Q0.1 used `bge-m3:567m`; it remains the configured retrieval model only while native ARM64 benchmarks show acceptable memory, latency, and retrieval quality on the evaluation set.
- A native Ollama runtime is the default serving candidate. FastAPI and the worker access the single loaded model through an internal HTTP client; containers reach the host runtime through the configured host address.
- Model identity, runtime packaging, quantization, vector dimension, and embedding version are recorded separately. Changing the embedding model creates a new index version; vectors from different models are never mixed.

### 9.2 Lexical retrieval

PostgreSQL full-text search preserves exact terms, acronyms, method names, and phrases that dense retrieval can miss.

### 9.3 Fusion and reranking

Reciprocal Rank Fusion combines lexical and dense ranks without pretending their raw scores are calibrated. A reranker is not in the baseline. A small local cross-encoder is added only when evaluation shows a material retrieval gain within the memory and latency budget.

### 9.4 Multi-turn behavior

- Full messages are persisted.
- ReaderAgent retrieval receives the current question and a bounded conversation window, scoped to the active paper. Follow-ups may use the one permitted same-paper search.
- The raw user question is preserved for generation.
- Previous answers are context, never evidence.
- ResearchAgent does not use previous answers as evidence and can retrieve only from the active paper and the explicitly selected, ready papers for that run.
- No agent memory or open-ended planning loop is introduced.

## 10. Generation and citation grounding

ReaderAgent and ResearchAgent produce evidence-grounded results through the provider-neutral model-output contract. A model may propose `source_ref` and a verbatim `evidence_quote` from its supplied context; it never supplies authoritative ownership, paper/version identity, page, or geometry. FastAPI binds each accepted citation to its authorized retrieval context and resolves it through the canonical `ChunkSpanMapping`.

The stable Reader stream events remain:

- `answer.delta`
- `citation.resolved`
- `answer.completed`
- `answer.failed`

ResearchAgent uses the corresponding `direction.delta`, `citation.resolved`, `direction.completed`, and `direction.failed` events in §15. Provider-specific event shapes never reach the frontend.

### 10.1 Model route, structured actions, and request budget

Researcy distinguishes three request types:

1. **Application API request:** the browser calls FastAPI. This is not a model request.
2. **Internal embedding request:** FastAPI or the worker calls the on-device self-hosted embedding runtime. It does not leave the machine and has no per-token vendor charge.
3. **Generation pass:** FastAPI uses the configured product route `ag/gemini-3.8-flash-low` through local 9Router, as recorded for Q0.1. Retain this product route; a development-agent model choice is separate and must not change the product runtime configuration. Q0.1 recorded the configured route, not response-echoed backend identity.

Ingestion uses local deterministic parsing and chunking, batched internal embedding requests, and local Qdrant indexing; it makes zero external paid model requests. The worker remains for document jobs, not model-agent work.

The bounded LangGraph workflows are:

- **ReaderAgent:** after same-paper hybrid retrieval, one structured model pass returns either `next_action: "answer"` with a final answer and citations or `next_action: "search_same_paper"` with a query. If it requests a search, server code retrieves once more using the same active paper/version filters, then one follow-up pass generates the answer. No model-supplied filter or source identity is accepted.
- **DiscoveryAgent:** after active-paper metadata is loaded and a usable title is present, the initial structured pass returns `next_action: "search_arxiv_metadata"` or `next_action: "stop"`. It supplies no URL or paper filters; server code constructs the query from that title and the abstract when available, calls only the official arXiv metadata API, deduplicates and inspects at most 10 results, excludes the active paper, and gives at most three distinct results to a follow-up pass for metadata/abstract-grounded `reason` text. With no usable title, it stops before model/API search and returns an actionable missing-metadata state. It does not retrieve full-text evidence or import papers.
- **ResearchAgent:** after validation of the active paper and one to three ready, user-owned selected papers, hybrid retrieval runs across only that allowlist. A structured generation pass returns the direction list with factual premise references; one optional follow-up may repair citation/output validation. Proposed directions and methods are hypotheses, not findings.

These are structured model outputs validated and branched on by LangGraph; the design does not assume provider-native tool calling. Backend code owns every tool invocation and filter.

Q0.1 demonstrated structured answer output, not structured next-action/tool selection. Before M3 or M4 can be accepted as `Verified`, qualify the configured route through the real 9Router product path: demonstrate schema-valid next-action output for the role's allowed branch, show that validation selects only its bounded backend branch, and show malformed/unsupported action output is rejected without tool execution. A mock or a development-agent route is not evidence for this gate. If qualification fails, mark the affected milestone blocked and preserve the deterministic RAG baseline without calling it an Agent.

Cap each on-demand role run at one initial and at most one follow-up generation pass. The second slot may be used to finish a requested bounded workflow or make one validator-requested repair; it is not an additional unbounded retry. If citation repair is needed after the cap, or the repaired output remains invalid, refuse or return a safe failure. A stream is never blindly retried after it has begun.

| Flow | Maximum generation passes |
|---|---:|
| Paper ingestion | 0 |
| ReaderAgent without extra retrieval or repair | 1 |
| ReaderAgent with one extra same-paper retrieval | 2 |
| ReaderAgent with one citation repair | 2 total |
| DiscoveryAgent with metadata search and reason generation | 2 |
| ResearchAgent with one citation/output repair | 2 total |

These are ceilings, not a one-call-per-question promise. Record the actual per-run call count, token usage, estimated cost, role, selected action/tool, latency, and validation result. arXiv API requests are not generation passes and never supply full-text citations. The configured generator receives grounding instructions, bounded conversation context where relevant, and selected chunks with stable source IDs—not the complete PDF. It must support streaming, structured output, token usage metadata, and clear timeout/error behavior. There is no automatic multi-provider fallback.

Hosted credentials remain server-side. Input context and output tokens are bounded. Usage and estimated cost are recorded without prompt contents, paper text, or secrets. The backend keeps separate `EmbeddingClient` and `GenerationClient` interfaces because their batching, lifecycle, failure, privacy, and cost semantics differ; it does not introduce a universal model-provider abstraction.

### 10.2 Runtime citation validation

For each proposed full-text citation:

1. `source_ref` must be part of the retrieved context for that request.
2. Its `paper_id` must be in the server-authorized set: only the active paper for ReaderAgent, or the active paper plus selected ready related papers for ResearchAgent. The backend supplies this identity; model output cannot assign it.
3. `evidence_quote` must match the supplied source after the explicitly permitted normalization.
4. Quote offsets must map through the canonical `ChunkSpanMapping` to source spans in the same `document_version`.
5. Resolution must return the exact source page and exact PDF-space boxes from those spans. Persist `paper_id`, `document_version`, `source_ref`, the verbatim `evidence_quote`, page, and boxes with the citation.
6. A citation is accepted only if its source and exact geometry resolve unambiguously. A page-only, approximate, or guessed block location is not a successful citation.
7. The validator may request at most one repair within the two-pass run ceiling. A still-unresolvable or unsupported substantive claim is removed and the answer is refused when support is insufficient.

Clicking a resolved citation opens the cited paper's exact immutable document version and highlights its exact PDF-space boxes. This applies when ResearchAgent cites a selected related paper as well as when ReaderAgent cites the active paper. The citation must remain within the authenticated user's ownership boundary.

Runtime validation proves the quote exists in the authorized source and resolves exactly. It does not claim perfect semantic entailment; citation correctness and answer support are measured separately.

### 10.3 Abstention and metadata rationales

When calibrated retrieval and deterministic citation checks do not establish enough evidence, the system states that it could not find sufficient support. It does not fill gaps with model knowledge. For ResearchAgent, source-supported factual premises require full-text citations; proposed directions and methods are labelled hypotheses and make no novelty or feasibility claim.

DiscoveryAgent's `reason` is grounded only in arXiv metadata and the returned abstract. It links to the arXiv record and is presented as a metadata rationale, not as a full-text citation or verified claim from the PDF. An absent abstract limits the available metadata basis and must not be disguised as full-text support.

## 11. Evaluation

The evaluation corpus retains the qualified single-paper cases and includes supported scientific PDFs with varied layouts, answerable questions with annotated evidence, unanswerable questions, and follow-ups. M5 adds paired current/related-paper cases so source ownership, citation identity, and the boundary between observed evidence and a proposed hypothesis are measured rather than inferred.

| Layer | Measurements |
|---|---|
| Parsing | text coverage, reading order, section quality, span-to-box resolution |
| Retrieval | Recall@K, MRR, contribution of lexical/dense fusion, and correct owner/paper/version scope |
| Citation | source precision, citation completeness, quote-to-span mapping, exact-page/box accuracy, and correct paper/version on click |
| Answer | correctness rubric, groundedness, abstention accuracy, and cross-paper premise support |
| DiscoveryAgent | API result count/uniqueness, active-paper exclusion, metadata-grounded rationale, no implicit import, empty/error behavior |
| ResearchAgent | factual-premise support from the proper paper, exact citations, hypothesis labeling, selected-source boundaries |
| Agent route | live structured next-action schema validation, permitted branch selection, rejection of invalid actions |
| Product | ingest latency, time to first token, successful exact citation jumps, and completion/refusal/error states |
| Cost | actual generation passes, hosted tokens, estimated cost, and latency per role/run |

Q0 remains `Verified` and read-only. The Q0.1 report gate decision was `Qualified`; fused Recall@5 was 6/8, and Track D browser-checked only one answerable case. Q0.1 did not qualify structured next-action/tool use, discovery, or generalized multi-paper quality. It recorded `ag/gemini-3.8-flash-low` through local 9Router 0.5.81 as the configured route, not a response-echoed backend identity.

Parser, chunker, embedding, retrieval, and prompt changes run against the same dataset. Agent changes are evaluated on the same fixed evidence and recorded model route. A component is not declared better without measured improvement or a documented product trade-off; a small evaluation set does not support claims of generalized multi-paper quality.

## 12. Information architecture and UX

### 12.1 Product surfaces

```text
Landing → Google sign-in → Library → one-paper Reader + Discussion
                                      → optional Related papers
                                      → optional Research directions
```

Library is the only top-level product destination. The Reader is the default view and visual focus. Related-paper discovery and research directions are explicit secondary actions inside the Reader, not separate report pages or automatic workflows.

### 12.2 Library

The Library contains:

- Researcy brand and account access;
- one primary `Add paper` action;
- search by title or author;
- a single list of papers.

`Add paper` presents exactly two options: arXiv URL/ID and PDF upload. A recommendation is added only when the user explicitly chooses `Add to Library`; this action reuses the existing arXiv import path and shows the normal processing state.

List/grid switching and source/year/sort filters are excluded from the MVP. A row shows title, authors, year, and source. Processing or failed papers additionally show the current stage and an actionable detail/retry control. Ready papers do not carry redundant status badges.

### 12.3 Reader

Desktop layout:

```text
Top bar: Back · Paper title · Download

[ collapsible outline ] [ PDF about 65% ] [ Discussion + compact research actions about 35% ]
```

- The PDF is the visual center.
- The outline collapses when space is constrained.
- The split ratio is fixed in the MVP; no draggable splitter.
- PDF and Discussion have independent scrolling.
- The composer remains visible without covering messages.
- Discussion and research actions are disabled with useful stage information until the active paper is ready.
- `Related papers` and `Research directions` are compact, explicit actions in the secondary panel. Opening a paper never starts either workflow.
- Discovery results show their metadata/abstract-grounded `reason` and arXiv link, plus an explicit `Add to Library` action. Searching does not download or import.
- Research directions require the user to select one to three related papers already in their own Library and `ready`. Otherwise, explain which paper must be added or processed first; do not call the model.
- Landing, authentication, and Library remain responsive.
- Below the supported desktop width, Reader explains that a larger screen is required.

### 12.4 Citation interaction

Clicking a resolved citation performs one atomic interaction:

1. update URL state with the cited paper, immutable document version, page, and citation;
2. open that exact paper/version in the PDF pane;
3. navigate to the cited page and highlight its exact PDF-space boxes;
4. open an inline evidence card under the answer.

The card shows the cited paper, page, section when available, and verbatim quote. It is a labelled non-modal region, not a dialog; there is no second `Go to page` action. A ResearchAgent citation to a selected related paper opens that paper's own PDF version without changing the evidence source or treating it as the active Discussion paper. An unresolved citation is visibly unavailable and cannot pass as a page-only or approximate success.

`Escape` closes the evidence card and returns focus to the citation. The PDF remains on the selected evidence page. Selecting another citation replaces the current card and highlight.

### 12.5 Discussion and secondary-action states

The UI explicitly supports:

- empty conversation with a small set of active-paper-derived suggested questions;
- retrieval in progress;
- streaming answer;
- completed answer with exact citations;
- grounded refusal for insufficient evidence;
- provider, rate-limit, or structured-output error with safe retry;
- interrupted stream;
- exact or unavailable full-text citation resolution;
- related-paper idle, searching, metadata-missing, empty-results, result, explicit-import/processing, and retriable-error states;
- research-direction selection, streaming, completion with premise citations and visibly labelled hypotheses, insufficient-evidence refusal, and retriable/interrupted states.

The interface discloses:

> Reader answers are grounded in the active paper. Research directions are hypotheses; verify factual premises against the cited paper passages. Related-paper rationales are based on arXiv metadata and abstracts.

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
POST   /api/papers/:paperId/related:search
POST   /api/papers/:paperId/research-directions:stream

GET    /api/citations/:citationId
```

The existing `/api/conversations/:conversationId/messages:stream` invokes ReaderAgent for the conversation's active `paper_id` only and keeps `answer.delta`, `citation.resolved`, `answer.completed`, and `answer.failed`. A resolved full-text citation carries its backend-bound `paper_id`, `document_version`, `source_ref`, verbatim `evidence_quote`, page, and exact PDF-space boxes.

`POST /api/papers/:paperId/related:search` invokes DiscoveryAgent only on explicit user request. It derives its query from the current paper's title and abstract when available, inspects at most 10 unique official arXiv metadata results, excludes the current paper and duplicates, and returns at most three results:

```json
{
  "papers": [
    {
      "arxiv_id": "2005.11401",
      "title": "Example title",
      "authors": ["Example Author"],
      "reason": "A metadata/abstract-grounded relevance rationale.",
      "arxiv_url": "https://arxiv.org/abs/2005.11401"
    }
  ],
  "request_id": "..."
}
```

An empty successful search returns `{"papers":[],"request_id":"..."}`. Each `reason` is grounded only in returned metadata/abstract; it is not a full-text citation. No search result creates a Library item, downloads a PDF, or starts ingestion.

`POST /api/papers/:paperId/research-directions:stream` invokes ResearchAgent. Its request body is `{"related_paper_ids":["..."]}` with one to three distinct paper IDs: all must already belong to the user, be `ready`, and differ from the active `paperId`. The entire selection is rejected before generation if any ID is invalid.

The stream emits exactly these event names:

- `direction.delta`
- `citation.resolved`
- `direction.completed`
- `direction.failed`

`direction.completed` carries a `request_id` and one to three `ideas`, each with `observed_gap`, `proposed_direction`, `possible_method`, and `premise_citations`. Each full-text premise citation carries `paper_id`, `document_version`, `source_ref`, the verbatim `evidence_quote`, page, and exact PDF-space `boxes`. `proposed_direction` and `possible_method` are visibly labelled hypotheses, not findings. `citation.resolved` carries the same composite source identity and exact location; `direction.failed` carries a stable error code, safe message, and request ID.

Both new routes use the existing opaque-session and CSRF boundary, backend ownership checks, per-user rate limits, and request IDs. Foreign and nonexistent resources both return `404`; a not-ready selected paper is rejected before any generation pass. Clients never send an owner ID or authoritative source filter. Mutating import requests accept an idempotency key. All errors contain a stable code, safe user message, and request ID. The exact OpenAPI schema is produced during implementation planning from these behavior contracts.

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
| Active paper has no usable title | Do not guess a DiscoveryAgent query; show actionable missing-metadata state | Correct the paper metadata, then request search |
| arXiv API returns no matches | Return success with `papers:[]`; show the empty state and no invented recommendations | User may review metadata and explicitly search again |
| arXiv API is unavailable or rate-limited | Return a safe retriable error; show no fabricated results | Retry after the dependency is available |
| Related-paper selection is empty, malformed, duplicated, includes the active paper, or outside the 1–3 range | Reject before running ResearchAgent; make no generation call | Select one to three distinct ready related papers |
| Selected paper is foreign or nonexistent | Return the same `404` behavior; disclose no ownership information and make no model call | Choose a paper visible in the user's Library |
| Selected paper belongs to the user but is not `ready` | Reject before any generation pass and show its processing state | Wait for readiness, then request directions |
| Configured route times out or rate-limits | Do not save a completed answer or directions; emit a safe role-specific failure | User may explicitly retry |
| Structured next-action output is invalid or unsupported | Reject it without executing a tool or widening scope | Show safe retry state; M3/M4 remain blocked if the real-route gate fails |
| Stream disconnect | Mark the run interrupted; do not mark partial output complete | Reload persisted state and let the user explicitly retry |
| Insufficient evidence or citation cannot resolve to exact boxes | Repair once within the run cap, then refuse or report unavailable evidence; never accept a page-only fallback | Ask a narrower question or improve source parsing |
| Per-user rate limit exceeded | Return a safe rate-limit error with request ID | Retry after the permitted interval |

All routes use stable error codes, safe user messages, and request IDs. Errors never expose foreign-resource existence, prompts, paper text, credentials, or internal provider details.

## 19. Observability

Structured logs use a request ID and, for on-demand runs, record:

- role (`ReaderAgent`, `DiscoveryAgent`, or `ResearchAgent`);
- request/run correlation ID, active and selected paper IDs, and document versions where applicable;
- validated action/tool chosen, result count, and source references returned by retrieval;
- per-role model-call count, token usage, estimated cost, and end-to-end latency;
- citation/output validation outcome, safe error code, and completion/refusal/interruption status.

Logs must not contain raw prompts, document text, evidence quotes, session/CSRF values, or API keys. Do not add distributed tracing, Grafana, or an agent-specific monitoring service for this proposal; use the existing structured application logs.

Health endpoints separate liveness from readiness for PostgreSQL, Qdrant, object storage, the embedding runtime, and the configured generation route.

## 20. Deployment

The interview environment continues to use Docker Compose for:

- `web`
- `api`
- `worker`
- `postgres`
- `qdrant`
- `minio`

Python LangGraph runs in the existing API deployment; it adds no service, agent server, or second worker. The existing worker remains for document processing. The embedding runtime runs natively on ARM64 on the interview MacBook, with Ollama as the default serving candidate. This avoids loading model weights in both API and worker processes and avoids Docker architecture emulation. Containerized API and worker processes use the same internal HTTP contract to reach the host embedding runtime.

The product generator remains the configured `ag/gemini-3.8-flash-low` route through local 9Router. A development-agent model selection is separate tooling and never changes this product runtime route.

A single demo entry point must:

1. validate configuration and secrets;
2. start dependencies with health checks;
3. apply database migrations;
4. verify PostgreSQL, Qdrant, object storage, the embedding runtime, and configured generation-route access;
5. warm the on-device self-hosted embedding model;
6. print the application URL and readiness result.

The separate M3/M4 real-route structured next-action qualification in §21 must pass before those milestones can be claimed `Verified`. No always-on public deployment is required.

## 21. Verification

Q0 remains `Verified` as read-only historical evidence; M1–M5 are all `Not started`. The following are approved future acceptance gates, not claims about implemented behavior.

### 21.1 Contract and integration checks

- Session cookie, CSRF behavior, private-resource ownership, and Qdrant owner/paper/version filters.
- Exclusive durable-job claim, expired-lease recovery, idempotent retry, and the PostgreSQL-to-Qdrant readiness invariant.
- Existing routes remain, and each new route matches §15 response/event shapes. `related:search` never imports or queues a paper; a successful no-result response is exactly an empty `papers` list.
- Reader citations and ResearchAgent premise citations persist `paper_id`, `document_version`, `source_ref`, verbatim `evidence_quote`, page, and exact PDF-space boxes resolved by `ChunkSpanMapping`. Unresolvable geometry is unavailable, never a page-only success.
- DiscoveryAgent excludes the active arXiv ID and duplicates, examines no more than 10 unique results, returns no more than three, and grounds `reason` only in returned arXiv metadata/abstract.
- ResearchAgent accepts only one to three unique related-paper IDs, all ready and owned by the requesting user, none equal to the active paper. Empty/malformed selections, duplicates, foreign/nonexistent IDs, and not-ready IDs are rejected before generation.
- ReaderAgent is constrained to the active paper even if a model action includes other IDs or filters. No client or model supplies authoritative ownership/version filters.
- Each run obeys the two-generation-pass ceiling; logs contain per-role call count, latency, token/cost estimate, selected action/tool, result count, source references, and validation state, but no prompts, document text, evidence quotes, or secrets.
- M3 and M4 real-route qualification uses `ag/gemini-3.8-flash-low` through local 9Router, not mocks or a development-agent route. Demonstrate valid role-specific structured actions reaching only their bounded LangGraph branch and malformed/unsupported actions reaching no tool. A failed gate leaves the milestone blocked.

### 21.2 Milestone and browser acceptance journey

All steps below are future gates:

1. **M1 — sign-in, Library, import:** Sign in with Google, observe only the signed-in user's Library, and start arXiv import or a supported PDF upload. M1 is currently `Not started`.
2. **M2 — durable processing:** Observe ingestion stages, verify the paper becomes `ready` only after PostgreSQL/Qdrant invariants pass, and confirm a second user cannot access it. M2 is currently `Not started`.
3. **M3 — first independently demoable Reader:** Open ready arXiv `1706.03762` with PDF as the visual focus. Ask a supported question about Transformer parallelization and observe a streaming ReaderAgent answer. Each supported substantive claim has an exact citation to that paper/version; clicking it opens the original PDF at the cited page and highlights the exact quote boxes. Ask an unsupported question and confirm a grounded refusal. Verify active-paper-only scope, ownership isolation, stream interruption, and the real-route structured-action gate. M3 is currently `Not started`.
4. **M4 — explicit discovery and import:** Only after a user activates `Related papers`, request a search for the current paper. Return at most three distinct actual arXiv IDs from no more than 10 inspected unique results; exclude the active ID and duplicates; show metadata/abstract-based rationales and arXiv links. Confirm no Library item, PDF download, or job exists until the user explicitly selects `Add to Library`, which uses the existing `POST /api/papers/arxiv` path. Process an actually relevant result (for example `2005.11401` only if the returned metadata supports its relevance) before it can be selected for ResearchAgent. Exercise the real-route structured-action gate. M4 is currently `Not started`.
5. **M5 — selected-paper research and evaluation:** On the active paper, explicitly select one to three related papers that are both user-owned and `ready`, then request research directions. Observe one to three short ideas with `observed_gap`, `proposed_direction`, `possible_method`, and `premise_citations`. Each factual premise cites the correct current or selected original paper with the composite identity and exact boxes; clicking each citation opens that paper/version and highlights the passage. Proposed directions and methods are visibly labelled hypotheses, not claims of novelty or feasibility. Record answer quality, abstention, exact citation quality, model calls, token/cost totals, and latency for the route.

### 21.3 Required future error cases

- No arXiv results return `papers:[]` with a visible empty state and zero imports.
- Missing active-paper title yields actionable missing-metadata state without guessing or querying.
- arXiv unavailability/rate limiting yields a safe retriable error and no invented recommendations.
- A selected foreign or nonexistent paper behaves as `404` without leaking ownership; a user-owned non-ready paper shows processing and invokes no generation.
- Empty, duplicate, active-paper, or out-of-range selections invoke no generation.
- Insufficient ReaderAgent or ResearchAgent evidence produces refusal/unavailable citation, not fabricated factual support or an unlabeled hypothesis.
- Unresolvable or foreign-source citations fail exact validation after at most one repair; no approximate fallback is accepted.
- Invalid structured action, model timeout/rate limit, and interrupted stream produce a safe role-specific failure and no false completion.
- Per-user rate limit and second-user access controls remain enforced for all new routes.

### 21.4 UI quality checks

- Actual browser verification at supported desktop widths; no horizontal overflow or clipped controls.
- Complete keyboard journey; focus remains visible with evidence cards and the sticky composer.
- Contrast and reduced-motion checks.
- Verify visible idle, loading, empty, missing-metadata, processing, explicit-import, streaming, completed, refusal, error, interruption, and exact/unavailable citation states for their corresponding surfaces.

## 22. Principal risks and mitigations

### 22.1 Exact evidence mapping fails after normalization

Keep explicit character-range mappings through every normalization step and reject transformations that cannot preserve provenance. If a verbatim quote does not map unambiguously to its immutable document version and exact PDF-space boxes, mark the citation unavailable, repair once within the model-pass ceiling, and otherwise refuse the claim. Do not use a page/block fallback as an accepted citation; approximate geometry may be retained only as internal diagnostic information.

### 22.2 Parser quality varies across scientific layouts

Qualify two bounded parser pipelines against a fixed corpus before committing. Keep parser outputs behind the canonical document model.

### 22.3 On-device embedding exceeds the 8 GB memory budget

Run one worker concurrently, serve one native model instance, benchmark peak memory alongside the Compose stack, and select a smaller embedding model when BGE-M3 does not produce enough retrieval improvement to justify its memory cost. Do not silently switch to a vendor embedding API because that changes cost, privacy, and vector-space contracts.

### 22.4 Hosted generation produces invalid or unsupported citations

Constrain sources with stable IDs, require verbatim evidence quotes, validate every citation, allow one repair, and otherwise abstain.

### 22.5 Long-running jobs become stuck

Use short claim transactions, explicit leases, heartbeats, stage checkpoints, bounded retry backoff, and a recovery query for expired leases. Never hold a database transaction open during parsing, embedding, or indexing.

### 22.6 Scope grows toward The Moonlight feature breadth

Use the reader-first journey and the three explicitly bounded roles as the scope filter. Keep Reader and Discussion central; include discovery and research directions only through their specified user-initiated flows and acceptance gates. Exclude broad web research, background activity, automatic import, and unrelated research-assistant features.

## 23. Decisions and rejected alternatives

- **Chosen:** evidence-first FastAPI modular monolith plus one document-processing worker, with exactly three bounded in-process LangGraph roles (`ReaderAgent`, `DiscoveryAgent`, `ResearchAgent`).
  **Rejected:** demo-only chat-with-PDF pipeline and a research-heavy multi-service architecture; these on-demand roles do not justify a separate agent service.

- **Chosen:** Qdrant for vector retrieval.
  **Rejected:** pgvector, by explicit project decision.

- **Chosen:** PostgreSQL-backed durable jobs claimed with `FOR UPDATE SKIP LOCKED`, leases, and heartbeats.
  **Rejected:** Redis/Dramatiq plus transactional outbox because one low-concurrency worker does not justify the additional service and consistency boundary.

- **Chosen:** hybrid lexical and dense retrieval with RRF.
  **Rejected:** dense-only baseline and mandatory reranker.

- **Chosen:** inline evidence card with immediate navigation to the exact cited paper/version and box highlight.
  **Rejected:** V4 floating citation dialog, a second `Go to page` action, and page-only/approximate citation success.

- **Chosen:** simplified Library and fixed Reader split with compact, user-initiated related-paper and research-direction actions in the secondary panel.
  **Rejected:** premature filters, list/grid switching, draggable panels, and a separate research-report destination.

- **Chosen:** on-device self-hosted embedding through a native ARM64 runtime plus the configured product generation route `ag/gemini-3.8-flash-low` through local 9Router.
  **Rejected:** vendor-hosted embeddings, duplicated in-process model loads, a fully local generator on the 8 GB interview machine, and changing the product route because of a development-agent model choice.

- **Chosen:** Google OAuth followed by an opaque server-side application session.
  **Rejected:** application JWT for the browser because the product benefits from revocation and has no portable-token consumer.

## 24. Design approval history

Revision 1.1 approvals remain historical; revision 2.0 was approved by the project owner on 2026-09-24. Approval changes the normative product direction, not Q0's historical status or the `Not started` state of M1–M5.

1. system boundaries and Qdrant data ownership;
2. canonical document model and ingestion contract;
3. retrieval, generation, citation, and evaluation design;
4. V4-derived product UX and visual direction using `ui-ux-pro-max` guidance;
5. reliability, security, verification, and the final PostgreSQL-only job decision.
6. on-device self-hosted embedding terminology and external model request budget.
7. balanced Q0 qualification scope using a two-paper representative subset before broader M5 evaluation.
