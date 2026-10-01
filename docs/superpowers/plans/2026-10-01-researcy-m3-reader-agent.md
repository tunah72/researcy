# Researcy M3 ReaderAgent and Evidence-Linked PDF Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the authorized original PDF in a real Reader, then deliver bounded active-paper conversations with streamed grounded answers/refusals and exact evidence-linked citations.

**Architecture:** Extend the existing FastAPI modular monolith and PostgreSQL authoritative state, reuse M2 private originals, native embeddings, Qdrant scope checks and exact provenance. Next.js owns PDF.js rendering and Discussion; one request-scoped LangGraph runs ReaderAgent through actual local 9Router, never the document worker.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, psycopg/Alembic, existing HTTP transport and MinIO, PostgreSQL FTS, native ARM64 Ollama/BGE-M3, Qdrant, pinned LangGraph and ijson (Python backend), Next 16.3.6/React 19/strict TypeScript, pinned pdfjs-dist and its local matching worker, pytest/Vitest/Testing Library, actual production browser.

**Spec:** [Owner-approved M3 child specification](../specs/2026-10-01-researcy-m3-reader-agent-design.md), subordinate to [approved master](../specs/2026-09-18-researcy-system-design.md) and [delivery map](../specs/2026-09-18-researcy-delivery-map.md).

**Status:** Approved by owner on 2026-10-01: “Tôi phê duyệt specification và implement plan.” Execution starts in isolated worktree `.omp/worktrees/m3-reader-agent`, branch `feat-m3-reader-agent`, base `cca8a9d`. Tasks below remain unchecked until their required evidence exists. Approval includes the named prerequisite decision to proceed while M1 remains `Implemented`; no M3 gate, owner-data action or publishing permission is inferred.

## Global constraints

- Controller GPT 6.1 Sol owns shared contracts, difficult security/geometry/stream-budget decisions and final integration. Default implementation is serial. Agents may investigate/review independent boundaries after contracts freeze; never competing migrations or shared schema edits.
- Only M3. No model changes, scope reduction or acceptance weakening to conceal failure. Product route `ag/gemini-3.8-flash-low` through local 9Router; development tooling is separate.
- Preserve root next-env.d.ts/AGENTS.md/CLAUDE.md artifacts and existing worktrees. No reset, stash, owner migration/worker startup, push, merge or prune.
- New feature work after approval uses isolated branch `feat-m3-reader-agent`, worktree `.omp/worktrees/m3-reader-agent` from `cca8a9d` or a separately verified later main. Read using-git-worktrees skill first. Do not create a branch/worktree by deleting an occupied target.
- RED → GREEN for consumer-visible boundaries, focused actual smoke, review/fix, scoped commit per task. Do not add wiring/source-text/incidental wording tests. Do not rerun owner-reported successful M2 tests merely to confirm handoff.
- Existing opaque sessions, session-bound CSRF, exact Origin, owner-filtered queries, safe request-ID errors and foreign/nonexistent 404 apply to all new routes. No raw prompts, document text, quotes, provider bodies or secrets in logs.
- Supported Reader width ≥1024px; fixed 65/35 split, independent scroll, non-overlapping composer, no splitter. Public citation/URL `page` is one-based; source `page_index` zero-based. Exact PDF geometry only.
- Conversation question/query ≤2400 Unicode code points; last 6 completed turns fitting 8000 code points; dense 5 + lexical 5 → fused 5, RRF k=60; packed normalized text ≤12000 plus raw quote text ≤12000 code points.
- Maximum one initial and one follow-up generation pass; search and repair share the second slot. No repair/new model call after emitted answer delta; no auto-retry after stream starts.
- PDF reads ≤64 KiB, 30-second deadline, eight concurrent PDF streams/process. Generation connect 5s, pass 60s, Reader run 150s, output ≤8192 tokens/256 KiB; bounded queue ≤16 transport chunks of ≤16 KiB and complete SSE event ≤256 KiB. Citation event may span chunks; never truncate quote boxes. Preserve existing service/native memory caps.
- 20 new runs/owner/rolling hour; one running run per owner and per conversation. All provisional values require owner acceptance with the draft; actual qualification cannot silently change them.
- `uv.lock` and package-lock authoritative; frozen installs. Pin only dependencies needed for actual delivered behavior. Read installed Next guides and vercel-react-best-practices before React implementation; actual browser evidence, not tests/build alone.

## 1. Ordered delivery and file responsibility

`T1 original PDF API → T2 real Reader → T3 conversations/runs → T4 hybrid retrieval → T5 exact citation resolver → T6 real GenerationClient/action qualification → T7 bounded graph/SSE → T8 Discussion/citation interaction → T9 full acceptance`.

T1/T2 deliberately make reading real before question answering. They do not close M3. Shared contracts make execution serial; T6 product-route prerequisite checks can be read-only early, but do not write dependent graph code assuming qualification.

| Task | Existing files to modify | Proposed new files |
|---|---|---|
| T1 | papers/routes.py, papers/models.py, papers/objects.py, retrieval/repository.py, config.py, tests/test_library.py, tests/test_owned_retrieval.py | papers/pdf.py, tests/test_pdf_delivery.py |
| T2 | web/src/app/library/[paperId]/page.tsx, components/library-list.tsx, lib/api.ts, app/globals.css, web package/lock | components/reader-workspace.tsx, components/pdf-reader.tsx, lib/pdf-geometry.ts, reader-interaction.test.tsx, pdf-geometry.test.ts |
| T3 | API main.py, config.py, tests/conftest.py only for real shared fixtures | migration 0005_m3_reader.py, conversations/models.py, repository.py, routes.py, tests/test_conversations.py, test_reader_schema.py |
| T4 | retrieval/repository.py, tests/test_owned_retrieval.py, all search_owned callers; API migration new FTS definition in forward 0006_m3_lexical.py | retrieval/hybrid.py, tests/test_hybrid_retrieval.py |
| T5 | documents/provenance.py only if resolver needs a shared raw-interval helper, main.py | citations/models.py, resolver.py, repository.py, routes.py, tests/test_citations.py |
| T6 | config.py, .env.example, compose.yaml API environment only, API pyproject/uv.lock | generation/client.py, models.py, tests/test_generation.py |
| T7 | conversations/repository.py, routes.py, models.py, main.py, shared config where consumed | agents/reader.py, conversations/stream.py, tests/test_reader_agent.py, test_reader_stream.py |
| T8 | reader-workspace.tsx, central api.ts, global styles; affected honest-readiness interaction tests | components/discussion.tsx, components/evidence-card.tsx, lib/reader-state.ts, discussion-interaction.test.tsx, citation-interaction.test.tsx |
| T9 | delivery map, root AGENTS.md only implemented/setup boundary when accurate | docs/superpowers/reports/2026-10-01-researcy-m3-acceptance.md |

Python new subpackages get __init__.py only when actual modules exist. Do not add empty service modules. Use existing main router registration, get_conn, APIError, short_transaction and threadpool patterns. Source symbols changed at exported boundaries require LSP references first and caller migration; do not leave legacy aliases.

## 2. Shared interfaces and persistence contract

Freeze these interfaces after approval; fields refer to the spec, not a second convention.

```python
# papers/pdf.py
@dataclass(frozen=True, slots=True)
class ByteSelection:
    start: int
    length: int
    status: int  # 200 or 206

# parse_byte_range(header: str | None, total: int) -> ByteSelection
# open_owned_pdf(owner_id: UUID, paper_id: UUID, version_id: UUID,
#                range_header: str | None, if_range: str | None) -> PDFStream
# PDFStream: status, headers, body Iterator[bytes], close(); HEAD closes without consuming body.

# retrieval/repository.py
@dataclass(frozen=True, slots=True)
class ReadyDocument:
    scope: DocumentScope
    profile: ProcessingProfile
    collection: str
    profile_hash: bytes

# load_ready_document(conn, owner_id, paper_id, version_id) -> ReadyDocument; delivered in T1.
# search_dense(document: ReadyDocument, query: str, limit: int = 5) -> list[EvidenceHit]
# T1 extracts the shared ready-scope loader and makes existing search_owned use it.
# T4 replaces search_owned with search_dense and migrates all callers; no compatibility alias.
# Rehydration keeps M2 exact-set/profile/publication validation, not just these four fields.

# retrieval/hybrid.py
# retrieve_same_paper(document: ReadyDocument, query: str) -> tuple[EvidenceHit, ...]
# fuse_ranks(dense_ids: Sequence[UUID], lexical_ids: Sequence[UUID]) -> tuple[UUID, ...]

# citations/models.py and resolver.py
@dataclass(frozen=True, slots=True)
class ProposedCitation:
    source_ref: str
    evidence_quote: str

# EvidenceCatalog: bounded dict of server-assigned refs -> authorized chunk/raw interval metadata.
# make_evidence_catalog(hits: tuple[EvidenceHit, ...]) -> EvidenceCatalog
# resolve_proposal(conn, document: ReadyDocument, catalog: EvidenceCatalog,
#                  proposal: ProposedCitation) -> tuple[ResolvedCitation, ...]
# ResolvedCitation fields: citation_id, paper_id, document_version, source_ref,
# evidence_quote, page (one-based), boxes, section; exact raw fragment offsets stored internally.

# conversations/repository.py
# create_owned_conversation(conn, owner_id, document) -> Conversation
# reserve_run(conn, owner_id, conversation_id, client_message_id, question, request_id) -> RunReservation
# finish_run(conn, reservation, accepted_claims, citations, usage) -> CompletedAnswer
# fail_run(conn, reservation, safe_code, interrupted: bool, partial_text: str) -> None
# all perform bounded short transactions; state compare protects interruption/completion race.

# generation/client.py
# GenerationClient.generate(messages: list[dict], *, follow_up: bool,
#                           deadline: float) -> AsyncIterator[GenerationEvent]
# GenerationEvent: structured content bytes, terminal usage, or safe typed error; no vendor events to UI.
# validate_action(raw: bytes, *, follow_up: bool) -> AnswerAction | SearchAction

# agents/reader.py / conversations/stream.py
# run_reader(reservation: RunReservation, document: ReadyDocument,
#            question: str, history: tuple[Message, ...],
#            generation: GenerationClient) -> AsyncIterator[ReaderEvent]
# ReaderEvent discriminated by exact answer.delta/citation.resolved/answer.completed/answer.failed.
```

These comments describe required implementation interfaces, not production stubs. Dataclasses/Pydantic model definitions are implemented with real behavior in the owning tasks. ReadyDocument must carry or fetch all needed immutable publication/manifest checks without losing M2 invariants. No model-supplied source identity enters it.

Central TypeScript types in `src/lib/api.ts`: `ReaderDocument` (paper/version/source hash/page metadata/PDF URL), `Conversation`, `Message`, `ResolvedCitation`, `ReaderEvent`. Add `fetchReaderDocument(paperId, versionId?)`, `fetchConversations(paperId, cursor?)`, `createConversation(paperId)`, `fetchMessages(conversationId, cursor?)`, `fetchCitation(citationId)` and `streamMessage(conversationId, clientMessageId, question, signal): AsyncIterable<ReaderEvent>`. All URLs same-origin; only mutations use central mutate/CSRF. PDF.js uses generated same-origin binary URL directly, not JSON parseResponse. Extend mutate with optional AbortSignal and migrate callers rather than duplicate CSRF code.

Reader document metadata: extend owner-scoped paper detail with optional `document_version` selection for an owned ready immutable version; return `reader` only when ready, containing canonical pages `{page_index,media_box,crop_box,rotation}`, source SHA and server-generated relative PDF URL. Do not expose storage key. Unready detail retains existing preparation contract. Validate selected version ownership before body/network; pin conversations separately from viewed page.

Exact HTTP bodies/status/pagination/SSE payloads and URL semantics are in spec §§4, 6, 8–9. Generate OpenAPI and inspect those concrete types during T1/T3/T5/T7; no speculative route name changes.

## Task 1: Authorized immutable original delivery

**Meaning:** Establish the security/bytes boundary that every rendered page and citation depends on.
**Dependencies:** Owner approves both drafts and explicit M3/M1 prerequisite decision; isolated worktree. No generation dependency.
**Scope/files:** T1 file map, extend detail metadata contract. No parsing/reindexing or owner cutover.
**Produces:** PDF route, Ready Reader metadata and ByteSelection/PDFStream.

- [x] RED: real temporary PostgreSQL version + unique private MinIO bucket, supported PDF bytes. Using authenticated TestClient requests prove foreign/random paper/version both 404 and never touch storage, owned unready 409, full/download bytes exactly equal original, HEAD empty, Range exact subset, suffix/open-ended/If-Range and 416 envelope. Revoked session rejects subsequent Range. Assert no object keys/MinIO URLs in successful JSON/header/error payloads.

```python
def test_range_returns_exact_original_slice(pdf_client, owned_pdf):
    response = pdf_client.get(owned_pdf.url, headers={"Range": "bytes=10-29"})
    assert response.status_code == 206
    assert response.headers["Content-Range"] == f"bytes 10-29/{len(owned_pdf.original)}"
    assert response.content == owned_pdf.original[10:30]
```

`owned_pdf` fixture is created in this task through real persisted source/version/job/publication fixtures and unique MinIO data, with url/original fields; no mocked original echo. `pdf_client` has a real application-issued opaque test session. Add separate zero-suffix/multi-range/overlong-header/storage-early-failure and actual disconnected-response closure cases.

- [x] Run RED: `uv run --frozen pytest tests/test_pdf_delivery.py tests/test_library.py -q` in isolated Linux test image; observe consumer contract missing/failing, not an unrelated environment failure. Actual execution used the image's already-frozen installed environment via `python -m pytest`; exact commands/outcomes are in the M3 report.
- [x] GREEN: implement bounded Range parsing, scoped DB lookup/metadata, MinIO offset/length access and resource cleanup; stream reads ≤64 KiB under total deadline/capacity limit. Reuse original storage client rather than second credential mechanism. Close object/DB on every route exit and HEAD; get metadata before headers. Add Content-Type/Length/Disposition/Range/ETag/cache/nosniff and safe request-ID errors. Blocking work uses existing threadpool path.
- [x] Focused check: rerun named tests; inspect actual generated OpenAPI types and owner/nonexistent outcomes.
- [x] Actual smoke: start only isolated API/storage, read original through real HTTP full/HEAD/single-range/download; SHA-256 full/download match accepted source, concatenated ranges reconstruct exact bytes. Abort slow client, observe open stream count/resources released; store safe observations in new acceptance report.
- [x] Review security/resource/contract, correct findings, commit only T1 files and accurate evidence.

## Task 2: Real PDF Reader before chat

**Meaning:** Make a ready paper genuinely readable, instead of merely exposing a download endpoint.
**Dependencies:** T1 reviewed. No model call or conversation mutation on open.
**Scope/files:** T2 file map; use existing ready detail route. Install/pin actual supported pdfjs-dist version at execution, matching local worker; update package-lock. Read relevant installed Next guides and React skill first.
**Consumes/produces:** ReaderDocument → ReaderWorkspace/PdfReader; geometry transform utility later reused by citations.

- [x] RED: role-driven navigation from ready Library item opens Reader page controls and Download; unready remains preparation/retry; too-small Reader offers clear larger-screen message/Back, not crushed panes; unavailable PDF gives safe reload. Delete obsolete ready-has-no-Reader wording/incidental absence tests rather than re-pin them; retain unready honest-state regressions.
- [x] Geometry RED: transform all four corners using viewport matrix; test actual mathematical expected rectangles for rotations and crop offsets, independent of utility output. Initial failure was the absent module, not executed mathematical assertions; see the acceptance report.

```ts
it('applies a rotated viewport to all evidence corners', () => {
  const viewport = { transform: [0, 2, 2, 0, -40, -20] };
  expect(pdfBoxToViewport([10, 20, 30, 40], viewport.transform))
    .toEqual({ left: 0, top: 0, width: 40, height: 40 });
});
```

Define `pdfBoxToViewport(box: readonly [number,number,number,number], transform: readonly number[]): {left:number;top:number;width:number;height:number}` in lib/pdf-geometry.ts. Additional tests reject nonfinite/out-of-order geometry, and cover negative MediaBox origin/zoom; no DOM snapshot copy.

- [x] Run RED: `npm test -- src/components/reader-interaction.test.tsx src/lib/pdf-geometry.test.ts`.
- [x] GREEN: client PDF.js pane with local worker, selectable text, fit-width/zoom/page controls, intrinsic outline or canonical exact-page outline, visible+adjacent canvas bounds and cancellation. Fixed 65/35 split, independent scroll and blank honest Discussion introduction; do not fake chat. Existing page shows Reader only from actual ready metadata. Reuse tokens/focus/44px targets and one main; no PDF JS/actions/external fetch.
- [x] Focused check + `npm run build`; verify strict types and worker asset packaged locally.
- [x] Actual browser smoke on isolated production web/API: original `1706.03762` ready fixture via isolated M2 pipeline; inspect canvas and text selection, next/page input, outline, Download hash, scroll separation, 1024/1280/1440 and small widths. Network evidence proves Range headers/status through Next rewrite, worker URL local and no direct MinIO request. If rewrite demonstrably fails, add only scoped passthrough with cancellation/header allowlist and repeat; report initial failure.
- [x] Review actual screenshots/keyboard/geometry/cleanup; commit focused files/evidence. Reader-only success is not M3 Verified.

## Task 3: Version-pinned conversations, run reservation and reload

**Meaning:** Durable question/history state and explicit interrupted/failed behavior; prevents duplicate paid calls and cross-owner source linkage.
**Dependencies:** T1/T2; shared source identity frozen. Migration never applied to owner DB.
**Scope/files:** T3 file map. Composite owner/paper/version FKs, run-state and citation tables per spec; T5 adds citation repository behavior, not a second schema convention.
**Consumes/produces:** ReadyDocument; Conversation/Message/RunReservation and owned paginated read/create routes.

- [x] Initial RED: actual authenticated production create expected 201 but returned 404. Real DB/API regressions cover pinned version, indistinguishable ownership, security/readiness precedence, duplicate/changed UUID, concurrency, quota and expiry; see acceptance report for the distinction between initial HTTP RED and later GREEN regressions.

```python
def test_duplicate_submission_does_not_reserve_second_run(run_db):
    first = run_db.reserve(client_message_id=run_db.message_id, question="Why parallelize?")
    replay = run_db.reserve(client_message_id=run_db.message_id, question="Why parallelize?")
    assert replay.run_id == first.run_id
    assert run_db.count_new_run_quota() == 1
```

`run_db` is a test-local real-DB helper constructed in T3, calls actual reserve_run with distinct committed connections; count queries authoritative quota table. Add different-payload and state-transition tests, not helper forwarding assertions.

- [x] RED evidence recorded: actual production HTTP assertion before implementation; NUL/canonical-publication review regressions failed before fixes. The planned `test_reader_schema`/`test_conversations` pytest RED command was not run before implementation; no such result is claimed.
- [x] GREEN: `0005_m3_reader` migration with scoped relations/state checks/partial uniqueness, repositories and paginated GET/create routes; bounded question body parsed only after auth; no network in transaction. Persist run lease expiry and lazy interrupted reconciliation. Central Pydantic responses/request IDs.
- [x] Focused checks: upgrade disposable populated M2 DB twice, verify original IDs/hash/profile/canonical row fingerprints unchanged; attempt cross-owner/version FK violations and observe rejection. Check OpenAPI.
- [x] Actual HTTP smoke: create/list/read history with two opaque sessions against isolated API, reload expired run and observe interrupted state; database dropped only by exact test identity.
- [x] Review transaction/races/security, scoped commit and evidence. Stream route delivered in T7, not a stub here.

## Task 4: Active-version hybrid retrieval and deterministic packing

**Meaning:** Find exact terms and semantic evidence together without letting client/model choose another source.
**Dependencies:** T3 source pinning and T1 Ready metadata.
**Scope/files:** T4 file map plus references of exported search_owned. No BM25 extension/reranker/index model change.
**Consumes/produces:** `load_ready_document`, `search_dense`, `retrieve_same_paper`, catalog-ready EvidenceHit sequence.

- [x] Before changing search_owned, use LSP references and migrate every test/internal caller, including publication probe dependencies if present; keep prepublication internal index verifier separate from ready-only user boundary. LSP unavailable; known-symbol search used and no obsolete caller remains.
- [x] RED: absent hybrid implementation plus review-driven failing RRF/top-five/poisoned-empty/DB-outage regressions; existing scope and canonical poisoning cases retained. See acceptance report for exact commands/failures, not an inferred suite RED.

```python
def test_rrf_overlap_can_outrank_single_branch_top_hit():
    a, b, c = UUID(int=1), UUID(int=2), UUID(int=3)
    assert fuse_ranks([a, b], [c, b]) == (b, a, c)
```

- [x] Run RED in restricted frozen Linux harness: hybrid tests initially failed on absent module; review regressions then failed on concrete behavior. `test_hybrid_retrieval`/`test_owned_retrieval`/`test_stages` final suite passed.
- [x] GREEN: one authorized ready/version boundary preserves full M2 checks; pure rank fusion; PostgreSQL parameterized FTS with `simple` generated vector and plain GIN in `0006_m3_lexical`; SQL owner/version/profile predicates before rank. Existing dense HTTP/native contract reused; hydrate IDs via PostgreSQL. No silent source widening on missing dense result. Pack whole bounded chunks and raw provenance catalog, history separate.
- [x] Focused check: migration twice on isolated M2 populated DB; all caller tests and negative publication poisoning pass.
- [x] Actual native/Qdrant/PostgreSQL smoke: fixed public Transformer parallelization + scaled-attention questions, record lexical/dense/fused refs, source identity and original hash; source-qualified evidence check, not invented recall claim. Foreign/unready run yields zero embedding/search calls. Native preflight must confirm exact digest/1024 dimensions/container reachability, not tags alone.
- [x] Review ownership/profile/ranking and measured resource buffers; commit.

## Task 5: Exact raw quote resolution and accepted citation reads

**Meaning:** Convert model-proposed quotes to authenticated immutable PDF locations, never model coordinates or page-only approximations.
**Dependencies:** T3 schema and T4 catalog/scoped retrieval.
**Scope/files:** T5 file map, central ResolvedCitation API type; no generation required to exercise resolver.
**Consumes/produces:** ProposedCitation/EvidenceCatalog → page-local ResolvedCitation tuples; accepted owner-scoped citation GET.

- [ ] RED real provenance fixtures: identity/whitespace/ligature/dehyphenation raw quote reconstruction, repeated ambiguous occurrence, missing mapping, foreign catalog ref/version, nonexistent quote, nonfinite/out-of-page geometry and partial expansion all behave exactly per spec. Multi-page raw quote produces separate page-local citations, never one page with mixed boxes. Provisional/foreign citation GET is 404.

```python
def test_quote_boxes_are_canonical_not_model_supplied(citation_source):
    result = citation_source.resolve_raw_quote()
    assert result[0].document_version == citation_source.version_id
    assert result[0].page == citation_source.page_index + 1
    assert result[0].boxes == citation_source.exact_character_boxes
    assert result[0].evidence_quote == citation_source.verbatim_quote
```

`citation_source` is a generated scientific PDF parsed/canonicalized through real M2 fixture contracts; expected characters/boxes known from fixture geometry, not taken from resolver result. Separate corruption fixtures use isolated DB only.

- [ ] Run RED: `uv run --frozen pytest tests/test_citations.py tests/test_document_provenance.py -q`.
- [ ] GREEN: build bounded server ref catalog with raw excerpt/normalized mapping; unique exact quote lookup mapped to code-point interval, existing resolve_range final authority; strict normalization preserving original characters. Persist immutable raw fragment offsets plus page-specific quote/boxes/source identity. Reject model extra ownership/page/geometry fields. GET includes only completed accepted citation owned by current user.
- [ ] Actual smoke: resolver on actual ready Transformer retrieved raw quote; compare every fragment's span offsets/raw characters/boxes to PostgreSQL and original source. Render private diagnostic PDF overlay for comparison, not a substitute for T8 browser. Zero citations accepted for wrong version or invalid mapping; preserve M2 box tolerance, never stretch to gold annotation.
- [ ] Review unicode/raw-normalized distinction, multipage/ambiguity and owner GET; commit.

## Task 6: Actual product GenerationClient and structured-action prerequisite

**Meaning:** Establish that the configured product route can produce and stream required validated choices; avoids building an Agent on an unqualified model assumption.
**Dependencies:** T4/T5 for actual source context. Exact local gateway endpoint/authorized credential/route reachability and usage/pricing source must be available; do not change product route to overcome failure.
**Scope/files:** T6 file map, API-only Settings/env; frozen pins for LangGraph and ijson (Python backend) consumed in T7. No provider SDK retry or universal model abstraction.
**Consumes/produces:** GenerationClient, strict AnswerAction/SearchAction, GenerationEvent and typed safe failures.

- [ ] Read-only prerequisite check using actual configuration without printing secret: bounded route metadata/connectivity and permission; record origin/configured route separately from provider-echoed backend identity. No paid generation health probe on automatic startup.
- [ ] RED transport boundary tests with deterministic local HTTP fault server: streamed UTF-8 fragmented JSON, duplicate keys/trailing data/unknown fields/unsupported action, output cap, inactivity vs total deadline, 429/5xx/aborted transport and missing usage. No network/tool execution from partial/malformed action.

```python
def test_model_cannot_supply_scope_filters():
    raw = b'{"next_action":"search_same_paper","query":"attention","owner_id":"forged"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)
```

`InvalidModelOutput` is typed safe domain error in generation/models.py. Follow-up `search_same_paper` is rejected. Do not mock complete final deliverable for gate evidence.

- [ ] Run RED: `uv run --frozen pytest tests/test_generation.py -q`.
- [ ] GREEN: async actual existing HTTP transport, strict decoded-stream bounds and total deadlines, terminal usage extraction/source recording, no raw provider logging; fixed route, credentials server-side only, settings fail closed when generation invoked without prerequisite. Strict discriminated action/claim/refusal validation; no provider-native tools assumed.
- [ ] Actual route probe: public evidence through actual product client, answer and bounded search cases, provider stream/structured output/usage; record latency/calls and price source. Probe outcome is prerequisite evidence only; final G6 requires actual LangGraph branch in T7/T9. Obtain actual negative route outputs with bounded qualification cases; fixture corruption is not labelled provider output. If unavailable/unsupported/malformed gate cannot be established, record blocker precisely, continue reachable Reader work without claiming M3 complete.
- [ ] Review route isolation/secret safety/limits, scoped commit. Never change model, fabricate usage/cost, alter gate or stop shared gateway.

## Task 7: Bounded ReaderAgent, claim-level SSE and atomic terminal state

**Meaning:** Execute only permitted request-scoped branches and make streamed completion truthful under validation, provider failure and disconnect.
**Dependencies:** T3–T6. Real-route prerequisite must be recorded; a failed gate stays blocked, not hidden behind mock graph.
**Scope/files:** T7 file map and actual master messages:stream route. No worker jobs for chat.
**Consumes/produces:** run_reader, ReaderEvent, reserve/finish/fail state transitions; strict event names and payloads.

- [ ] RED: real DB state + controlled transport for consumer boundaries: 1-pass answer, 2-pass search answer, 2-pass pre-delta repair; search+repair would require third call and must fail/refuse. Unsupported action executes no tool; follow-up search rejected; server filters immutable even with hostile question/provider fields. Invalid quote before delta may use single repair; invalid late claim after delta never retries or completes. Provider timeout/429/failure/interrupted stream leaves failed/interrupted durable state; racing completion/cancel cannot overwrite terminal state.

```python
@pytest.mark.anyio
async def test_search_then_bad_citation_has_no_third_call(reader_run):
    events = await reader_run.execute_case("search_then_unresolvable_quote")
    assert reader_run.actual_generation_calls == 2
    assert reader_run.actual_same_paper_searches == 1
    assert events[-1].event == "answer.failed"
    assert reader_run.persisted_assistant_state == "failed"
```

`reader_run` is test-local actual graph + PostgreSQL reservation helper; controlled HTTP server supplies ordered responses, call counter counts requests received, not expected mock list length. Additional tests consume real HTTP SSE stream and disconnect mid-output.

- [ ] Run RED: `uv run --frozen pytest tests/test_reader_agent.py tests/test_reader_stream.py -q`.
- [ ] GREEN: small LangGraph with explicit immutable state and generation counter; initial/hybrid/action/one-search-or-repair/final-validation branches. Incremental maintained JSON parser validates complete claim units and quote locations before delta; final entire envelope strict-check includes duplicate-key/trailing output protection. Search only after whole action document validation. Citation events only accepted committed rows; complete only after atomic message/run/citation commit. Emit exactly one writable terminal event; safe errors before SSE headers otherwise answer.failed. Cancellation closes provider/DB/queues; lazy expired-run interruption survives API death.
- [ ] Usage/logging implementation: increment actual paid call count before attempting transport, aggregate known usage with source, unknown partial values explicit, estimate cost only from documented tariff. Separate initial/follow-up/repair/search counts and first-delta/total latency. Content-free structured logs only.
- [ ] Focused checks and actual same-origin HTTP smoke on isolated production API/web: real product answer/search branch, live deltas before completion, citations persisted, explicit interruption and reload. Use controlled fault transport separately for timeout/429/failure; no production fault switches or artificial streaming replay. Verify Next flush/cancellation and post-disconnect state with DB observation.
- [ ] Review graph bound, stream parser/security, concurrency and privacy; commit. G6 real malformed/unsupported rejection still requires actual route evidence, not this test fixture.

## Task 8: Discussion, atomic exact citation jump and keyboard lifecycle

**Meaning:** Complete the product journey from question to evidence on the original PDF, with honest failure/refusal/reload UI.
**Dependencies:** T2 Reader and T3/T5/T7 concrete contracts.
**Scope/files:** T8 map; central types/helpers only, no duplicate payload definitions. No M4/M5 controls.
**Consumes/produces:** paginated conversations/messages, streamMessage, citation GET → Reader URL/page/overlay/card state.

- [ ] RED user interactions: empty conversation/paper-derived suggestion (uses actual title, no invented metadata); explicit submit creates/selects pinned conversation, displays streamed provisional claim and terminal completion/refusal; EOF/429/provider failure show actionable explicit retry not completion; refresh restores persisted history; duplicate submit blocked, 401 clears private state. Old stream/page/citation request cannot overwrite newer selection.
- [ ] Citation RED: one keyboard activation triggers correct URL/version/page/boxes + inline labelled region; Escape closes and restores triggering button focus while page remains; second selection replaces card/highlight; deep-link invalid/foreign/provisional citations remain unavailable, no model call; browser back/refresh rehydrate owned state. Card nonmodal aria-controls/expanded, no extra Go-to-page action.

```tsx
await user.click(screen.getByRole('button', { name: /citation 1/i }));
expect(screen.getByRole('region', { name: /evidence/i })).toBeVisible();
await user.keyboard('{Escape}');
expect(screen.queryByRole('region', { name: /evidence/i })).toBeNull();
expect(screen.getByRole('button', { name: /citation 1/i })).toHaveFocus();
```

Use actual Discussion/evidence component and controlled API boundaries, not expected-state copies. Geometry/original rendering remains actual-browser proof.

- [ ] Run RED: `npm test -- src/components/discussion-interaction.test.tsx src/components/citation-interaction.test.tsx`.
- [ ] GREEN: POST fetch stream with central CSRF, AbortSignal and bounded SSE decoding; immutable event/type validation, nonterminal draft styling, complete/refusal/error/interrupted states and reload pagination. Explicit new submission UUID for retry, no automatic reconnect. Suggested prompt only from known active title/section, no model pass on open. Layout/focus/live region follow spec. URL state uses backend accepted citation, transforms exact boxes via T2 utility; wait/cancel stale render, card one-click update.
- [ ] Focused check + frontend suite/build. Remove obsolete ready-unavailable copy/tests; retain unready/retry tests and migrate all affected callers.
- [ ] Actual production browser smoke: sign in/session in isolated stack, ready 1706.03762, parallelization question and unsupported carbon-footprint question, citation mouse/keyboard, exact overlays vs canonical boxes on original, zoom/rotation/crop fixtures, Escape/focus and independent scroll/composer. Observe all loading/streaming/completion/refusal/unavailable/error/interruption states. Verify no overflow and visible focus at 1024/1280/1440, clear boundary at 375/768/1023, reduced motion/contrast/one main; close browser tabs afterward.
- [ ] Review actual surface and semantic answer support separately from geometry; scoped commit/evidence.

## Task 9: Full isolated real-stack acceptance and status reconciliation

**Meaning:** Prove complete M3, not just compiling components or isolated route qualification.
**Dependencies:** All T1–T8 reviewed/committed; actual generation prerequisites and no hidden unresolved gate. No publishing authorization assumed.
**Files:** New actual M3 acceptance report, delivery map and root setup/implemented boundaries only when accurate. No fabricated passing template.

### Safe environment setup

- [ ] Read using-git-worktrees/start-stack/browser verification skills relevant at execution. Isolated Compose project `researcy-m3-acceptance`; explicit private overrides for separate PostgreSQL/MinIO/Qdrant volumes and localhost ports (API 8003, web 3003, PostgreSQL 55435, MinIO 9003). Production web must get API_INTERNAL_URL=http://api:8000 in network, trusted origin exactly http://localhost:3003 and correct callback for explicit real OAuth if exercised. No root default .env database/bucket/volume accidentally inherited.
- [ ] Compose override is throwaway private acceptance harness, not a new product stack convention. Render/review configuration without dumping secrets; verify project labels/network/volume names and original source intake identity before mutations. Container API embedding endpoint reaches native Ollama via host.docker.internal; generation endpoint uses actual approved gateway address, not guessed port. Existing restricted seccomp/UID/caps inherited.
- [ ] Start isolated PostgreSQL/MinIO/bucket init/API, migrate twice, Qdrant and dependency preflight. Only after explicit isolated-fixture scope is established start its document worker to process public accepted originals; no preserved owner queued job consumed. Actual worker stops after required fixtures. Do not use a test-generated ready flag or manually seeded vectors as G1/G2 source.
- [ ] Actual `1706.03762` import or explicit provenance-preserving copy of already accepted public original into isolated intake; if copied, record source/hash/version and do not claim fresh arXiv-network acquisition. Golden annotation version/hash must match original; annotate actual edition separately if necessary. Exercise actual production web/API, not a fake acceptance app.

### Commands delivered and exercised at execution

Use worktree cwd and private overrides; commands below are future acceptance procedures, NOT executed in this design session. Never run them against root owner project by omission.

```bash
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f /tmp/researcy-m3-private.yaml up -d postgres minio minio-init api qdrant
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f /tmp/researcy-m3-private.yaml exec -T api alembic upgrade head
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f /tmp/researcy-m3-private.yaml exec -T api alembic upgrade head
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f /tmp/researcy-m3-private.yaml --profile processing run --rm --no-deps worker python -m researcy.ingestion.preflight --check
```

Private override must supply approved secret/configuration securely; /dev/null prevents accidentally loading root .env. This named override is created only during authorized execution, inspected and removed afterward. The worker preflight does not claim jobs; actual worker startup is a separately announced isolated-fixture step.

Backend full affected suite runs in existing test-image override with disposable DB/buckets, not production API replacement:

```bash
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f compose.test.yaml -f /tmp/researcy-m3-private.yaml build api
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f compose.test.yaml -f /tmp/researcy-m3-private.yaml run --rm --no-deps api uv run --frozen pytest tests -q
```

Keep test build tag distinct from production images. Test override must preserve sandbox restrictions and unique database fixtures. A failed environment cannot be recorded as test RED or skip-as-pass. Existing arXiv opt-in remains separately labelled.

```bash
# apps/web, reproducible prescribed Node/container runtime
npm ci
npm test
npm run build
# worktree root, separate from resource sampling
docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f /tmp/researcy-m3-private.yaml --profile web --profile processing build api web worker
```

### Complete gate checklist

- [ ] G1 actual PDF reading/download/Range/HEAD/hash/bounded cleanup through production same-origin surface, supported outline and page controls.
- [ ] G2 actual product parallelization answer with live deltas, substantive claim support, exact original-version citations and one-click page/boxes/card; bounded follow-up.
- [ ] G3 actual unsupported question refusal; isolated actual invalid/missing/foreign/raw-normalized/multipage provenance failures and repair/pass ceiling. Report injected fixtures separately from natural model output.
- [ ] G4 two authenticated owner contexts across every private resource, random/foreign equivalence, unready no expensive work, CSRF/Origin/revocation/quota and duplicate/concurrent submission. Synthetic opaque sessions establish new authorization boundaries, not missing M1 two-real-Google acceptance; no M1 promotion.
- [ ] G5 actual browser abort/network disconnect/API interruption reload; controlled real-HTTP transport timeout/429/5xx/provider-stream failure through product client with zero false completion/hidden retries. Fault harness identity disclosed; no claim upstream naturally returned a failure it did not.
- [ ] G6 actual 9Router product output through actual graph for answer/search branches and real malformed/unsupported output rejected without tool. Record route config, validated action/tool trace, model-call count, usage source, first-delta/total latency, estimated/billed cost distinction and tariff source. Bounded attempts that do not elicit required negative output leave specific gate interpretation blocker; never replace with mock/corrupted payload or relax criteria.
- [ ] G7 full suites/production builds and browser journeys: supported and below-boundary widths, keyboard/Escape/focus, zoom/rotations/crop, independent scrolling, composer, one main, overflow/contrast/reduced motion, complete M3 visible states. Compare actual rendered overlay with exact viewport transforms, not page-only screenshots.
- [ ] Measure native/service/API/web memory/OOM/restarts during actual Reader/streaming with existing limits; no tests/builds concurrently. M2 warm-resource pass is not a substitute for current workload observation. Record cold-load separately; no model/budget change or owner-app shutdown.
- [ ] Request code review and resolve blocking findings. Remove throwaway fault/measurement scripts and exact run-owned resources, preserve owner data/all historical evidence. No broad prune or volume deletion.
- [ ] Report exact command/environment/expected-vs-observed/request ID/journey/source hash and measurement source. Private text/screenshots/secrets stay ignored/private; safe evidence only in Git.
- [ ] Advance map only by rules: draft no change; approved spec Designed; approved plan Planned; code without all gate evidence Implemented; all observed M3 gates Verified. RET-01/GEN-01/CIT-01 historical Designed evidence does not imply production ready. Root AGENTS says Reader implemented only when true. No push/merge/prune without new authorization.

## 3. Coverage and review checkpoint

| Spec sections / requirements | Tasks | Required evidence |
|---|---|---|
| §§1–3 full scope/history/approval | all/T9 | No implementation before approval, status record |
| §4 private original transport | T1/T2/T9 | G1/G4 |
| §5 Reader/PDF.js/geometry/width | T2/T8/T9 | G1/G2/G7 |
| §6 persistence/version/context/races | T3/T7/T8/T9 | G4/G5 |
| §7 RET-01 same-paper FTS/dense/RRF | T4/T9 | G2/G3/G4 |
| §8 GEN-01/AGENT-01 bounded structured graph/stream | T6/T7/T9 | G2/G5/G6 |
| §9 CIT-01 exact raw quote and interaction | T5/T8/T9 | G2/G3/G4/G7 |
| §10 security/errors/privacy/measurement | T1/T3–T9 | G4/G5/G6 |
| §§11–12 acceptance/prerequisites | T9 | G1–G7, full evidence and blockers |

Self-review completed at draft level: reading-first order preserves complete M3; forward migrations do not alter M2 immutable source; source/version/quote/page conventions consistent; existing exported search callers must migrate with references; HTTP SSE and DB terminal races explicit; no third pass, fake stream, fabricated tariffs, Q0 qualification substitution or automatic owner cutover. Actual module versions/compatibility are verified when frozen dependencies are installed, not invented here.

**Approval checkpoint:** Owner reviews both complete drafts and named decisions before implementation. Recommended execution is serial controller-led task → RED/GREEN → real smoke → review → scoped commit. Approval must specify whether M3 may proceed while M1's detailed record remains incomplete; all actual M3 exit gates remain unchanged. Publication/owner-data actions require separate authorization.
