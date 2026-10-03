# Researcy M3 ReaderAgent and Evidence-Linked PDF Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the authorized original PDF in a real Reader, then deliver bounded active-paper conversations with streamed grounded answers/refusals and exact evidence-linked citations.

**Architecture:** Extend the existing FastAPI modular monolith and PostgreSQL authoritative state, reuse M2 private originals, native embeddings, Qdrant scope checks and exact provenance. Next.js owns PDF.js rendering and Discussion; one request-scoped LangGraph runs ReaderAgent through direct Gemini primary, with operator-selected 9Router for later runs only, never the document worker. Original execution/9Router results below are historical; the approved Gemini G1–G3 cutover is complete, with final evidence in the acceptance report and status controlled by the delivery map.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, psycopg/Alembic, existing HTTP transport and MinIO, PostgreSQL FTS, native ARM64 Ollama/BGE-M3, Qdrant, pinned LangGraph and ijson (Python backend), Next 16.3.6/React 19/strict TypeScript, pinned pdfjs-dist and its local matching worker, pytest/Vitest/Testing Library, actual production browser.

**Spec:** [Owner-approved M3 child specification](../specs/2026-10-01-researcy-m3-reader-agent-design.md), subordinate to [approved master](../specs/2026-09-18-researcy-system-design.md) and [delivery map](../specs/2026-09-18-researcy-delivery-map.md).

**Status:** Original plan approved by owner on 2026-10-01: “Tôi phê duyệt specification và implement plan.” T1–T9 and the subsequently approved G1–G3 cutover have recorded closure in isolated worktree `.omp/worktrees/m3-reader-agent`, branch `feat-m3-reader-agent`, base `cca8a9d`. The owner now reports successful manual M3 testing and authorizes publication/PR/merge, local-main synchronization and full main startup, explicitly including existing-database forward migrations and queued-paper worker processing. These permissions supersede the earlier pending execution/publication boundary, not historical evidence or M1's `Implemented` status.

## Global constraints

- Controller GPT 6.1 Sol owns shared contracts, difficult security/geometry/stream-budget decisions and final integration. Default implementation is serial. Agents may investigate/review independent boundaries after contracts freeze; never competing migrations or shared schema edits.
- Only M3. No unapproved model changes, scope reduction or acceptance weakening to conceal failure. Master revision 2.2 / amended child §8/G6 approve direct Gemini primary and manual 9Router selection; development tooling is separate.
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

- [x] Real provenance coverage: identity/whitespace/ligature/dehyphenation raw quote reconstruction, repeated ambiguity, missing mapping, foreign version, nonexistent quote, nonfinite/out-of-page geometry corruption, multipage page-local citations and provisional/foreign GET. Boundary-dehyphenation and expanded-raw-limit defects have explicit RED → GREEN regressions; some defensive coverage was added after implementation, not claimed failing-before.

```python
def test_quote_boxes_are_canonical_not_model_supplied(citation_source):
    result = citation_source.resolve_raw_quote()
    assert result[0].document_version == citation_source.version_id
    assert result[0].page == citation_source.page_index + 1
    assert result[0].boxes == citation_source.exact_character_boxes
    assert result[0].evidence_quote == citation_source.verbatim_quote
```

`citation_source` is a generated scientific PDF parsed/canonicalized through real M2 fixture contracts; expected characters/boxes known from fixture geometry, not taken from resolver result. Separate corruption fixtures use isolated DB only.

- [x] Restricted Linux harness RED: initial missing proposal imports and accepted GET 404; review defects subsequently reproduced with concrete failing behavior. Exact commands/outcomes recorded in acceptance report.
- [x] GREEN: bounded server-ref raw catalog, unique exact whitespace-equivalent lookup, complete canonical mapping validation through existing `resolve_range`, authoritative raw-offset slicing, strict page-local limits. Immutable raw fragment offsets and page-specific source identity; model extra geometry/scope forbidden; owner completed accepted GET.
- [x] Actual smoke: ready Transformer quote compared against PostgreSQL and original diagnostic PDF overlay. After boundary correction, actual deployed recorded dehyphenation selected at quote end on page 7 with 31 boxes. No box-tolerance changes or generation calls.
- [x] Review unicode/raw-normalized distinction, multipage/ambiguity and owner GET; both citation reviewers clean after corrections. Full backend 584 passed / 1 opt-in skip; production API build and actual deployed resolver/owned-read/two-user smoke passed. Scoped commit follows recorded evidence.

## Task 6: Actual product GenerationClient and structured-action prerequisite

**Meaning:** Establish that the configured product route can produce and stream required validated choices; avoids building an Agent on an unqualified model assumption.
**Dependencies:** T4/T5 for actual source context. Exact local gateway endpoint/authorized credential/route reachability and usage/pricing source must be available; do not change product route to overcome failure.
**Scope/files:** T6 file map, API-only Settings/env; frozen pins for LangGraph and ijson (Python backend) consumed in T7. No provider SDK retry or universal model abstraction.
**Consumes/produces:** GenerationClient, strict AnswerAction/SearchAction, GenerationEvent and typed safe failures.

- [x] Read-only actual endpoint/authenticated model catalog; subsequent explicit product-client qualification separates configured route from echoed backend. No automatic paid health probe.
- [x] Restricted-harness RED followed by concrete controller/review RED regressions for diagnostics, incremental transport, deadline suspension, terminal order, malformed accounting and protocol. Actual local HTTP fault server; unsupported action executes no tool. Detailed outcomes in acceptance report.

```python
def test_model_cannot_supply_scope_filters():
    raw = b'{"next_action":"search_same_paper","query":"attention","owner_id":"forged"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)
```

`InvalidModelOutput` is typed safe domain error in generation/models.py. Follow-up `search_same_paper` is rejected. Do not mock complete final deliverable for gate evidence.

- [x] Initial restricted Linux harness RED: two missing-module failures; later defects reproduced as concrete behavior failures. Frozen suite final 671 passed / one opt-in skip.
- [x] GREEN: bounded async existing HTTP transport, operation-scoped deadlines, terminal metadata before action validation, strict action/claim/refusal schema, fixed API-only route/configuration and frozen LangGraph/ijson pins. No SDK retry/native tool assumption.
- [x] Real-route prerequisite closed by the explicitly owner-approved revision 2.2 / G1–G3 addendum: actual Gemini client/graph answer, bounded search, adversarial containment and valid subsequent output; separately labelled controlled rejection. Usage/calls/latency and unavailable monetary-cost reason recorded. Original gateway probe notes below remain historical; they are not natural Google negatives or current tariff blockers.
  - Actual answer/search/negative and valid-after-negative output exercised through product client; nine explicit requests including initial client defects and final safe timeout, not nine successful calls. Usage/latency recorded. **Pricing portion remains blocked:** no documented applicable Antigravity tariff; estimated cost unknown. Google Developer API rates not substituted.
- [x] Controller reviewed fixed route/API-only secret boundaries, transport/parser/deadline/metadata limits and consumer migration; scoped software commit `e450143`. Independent reviewer provider failures are disclosed, not clean-review evidence. Tariff prerequisite remains blocked.

## Task 7: Bounded ReaderAgent, claim-level SSE and atomic terminal state

**Meaning:** Execute only permitted request-scoped branches and make streamed completion truthful under validation, provider failure and disconnect.
**Dependencies:** T3–T6. Real-route prerequisite must be recorded; a failed gate stays blocked, not hidden behind mock graph.
**Scope/files:** T7 file map and actual master messages:stream route. No worker jobs for chat.
**Consumes/produces:** run_reader, ReaderEvent, reserve/finish/fail state transitions; strict event names and payloads.

- [x] RED: real DB state + controlled transport reproduced 1-pass answer, 2-pass search, 2-pass pre-delta repair and no third call; unsupported/follow-up/forged action, late invalid claims, provider faults, interruption and both publication/cancellation CAS winners. Exact outcomes recorded in acceptance report.

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

- [x] Initial RED and subsequent concrete regressions executed in the restricted Linux harness; focused generation/config/parser/graph/SSE checks passed with warnings treated as errors. Exact commands/outcomes recorded in the acceptance report.
- [x] GREEN: finite LangGraph, immutable scope, maintained incremental JSON parser, whole-envelope strict validation, one search-or-pre-delta-repair budget and no retry after first delta. Accepted citation events follow atomic publication; direct bounded SSE sends and disconnect cleanup preserve durable terminal winners.
- [x] Usage/logging: actual attempted pass count, initial/follow-up/repair/search counters, provenance-bearing terminal usage, explicit unknown/partial totals, content-free structured logs and observed monotonic latency. Cost remains null because the applicable tariff is blocked, not invented.
- [x] Focused checks and actual same-origin HTTP smoke on isolated production API/web completed through G2–G3 below: real primary answer/search, live deltas before committed citations/completion, pinned persisted citations, controlled production-Reader interruption, browser reload and explicit successful Gemini resubmission. Controlled HTTP provider faults remain separate from actual Google outputs; Next observed the real live submission, not artificial streaming replay.
  - Owner-requested requalification 2026-10-02 now observed actual graph search in two runs: one follow-up safely failed, one completed as a validated refusal after exactly two calls/one search/zero repairs. Three separate cited answers succeeded. Search → supported cited answer remains unobserved; full G6 negative interpretation/tariff still open. Exact six-case/eight-attempt evidence appended to the acceptance report.
  - Subsequent follow-up diagnosis 2026-10-02 observed actual production graph search → supported two-claim cited answer, two calls/one search/zero repairs (`2d029bb6-3b3e-4f00-b410-d50104a85920`), same-origin evidence reload and original-PDF browser interaction. Two new initial-pass failures are premature provider-stream EOF before final action validation; upstream cause is not established. Separate live same-origin HTTP case completed directly with three citations, not two-pass search. The full combined criterion remains unchecked; no speculative Generator fix, gateway mutation or G6/tariff/review closure. Evidence and observer-caused interruption are recorded in the acceptance report.
- [x] Controller reviewed graph/pass/parser/privacy/queue/terminal races and committed verified software `3fb1dcb`. Independent backend review aborted after provider retries and is not a clean report. The separate real two-pass search/negative G6 gate remains open.

## Task 8: Discussion, atomic exact citation jump and keyboard lifecycle

**Meaning:** Complete the product journey from question to evidence on the original PDF, with honest failure/refusal/reload UI.
**Dependencies:** T2 Reader and T3/T5/T7 concrete contracts.
**Scope/files:** T8 map; central types/helpers only, no duplicate payload definitions. No M4/M5 controls.
**Consumes/produces:** paginated conversations/messages, streamMessage, citation GET → Reader URL/page/overlay/card state.

- [x] Consumer RED/GREEN: explicit pinned creation/submission, provisional/terminal/refusal/error/retry states, reload/pagination, duplicate blocking, revoked private state and stale scope/stream results. Failed retry pairs remain separate; approved URL uses `document_version` and the requested conversation.
- [x] Citation RED/GREEN: authoritative version/page/quote/boxes, single inline region, replacement, deep-link membership/disagreement, stale fetch guards and Escape restoration including refreshed/remounted source controls. Actual original-PDF geometry remains separately recorded browser evidence.

```tsx
await user.click(screen.getByRole('button', { name: /citation 1/i }));
expect(screen.getByRole('region', { name: /evidence/i })).toBeVisible();
await user.keyboard('{Escape}');
expect(screen.queryByRole('region', { name: /evidence/i })).toBeNull();
expect(screen.getByRole('button', { name: /citation 1/i })).toHaveFocus();
```

Use actual Discussion/evidence component and controlled API boundaries, not expected-state copies. Geometry/original rendering remains actual-browser proof.

- [x] Initial missing transport/Discussion RED and subsequent URL/placement/focus regressions executed; precise failures and commands recorded in the acceptance report.
- [x] GREEN: central same-origin CSRF POST stream, bounded UTF-8/SSE validation, abort lifecycle, explicit new retry UUID, honest durable/provisional states, requested-conversation pagination, accepted citation URL/card and stale render cancellation. No model call or conversation creation on GET.
- [x] Final pinned Node 22.14 frontend suite: 113 passed; strict TypeScript/Next production build passed. Migrated obsolete URL callers and removed unused former sidebar styles. Test/resource-run failures are retained in the report rather than hidden by weakening assertions.
- [x] Actual production-browser evidence recorded for ready original, grounded/refused/failed/interrupted/reloaded Discussion, exact citation keyboard/mouse/refresh/back/Escape, all supported/narrow widths, zoom/rotation/crop, independent pane scrolling/composer, one main/overflow/contrast/reduced motion. Private screenshots remain outside Git; managed tab closed.
- [x] Static independent UI review plus controller actual-surface and substantive claim/quote review completed; scoped software commit `706c29d`. Real model semantic support reviewed separately from canonical geometry; no broad accuracy claim.

## Task 9: Full isolated real-stack acceptance and status reconciliation

**Meaning:** Prove complete M3, not just compiling components or isolated route qualification.
**Dependencies:** All T1–T8 reviewed/committed; actual generation prerequisites and no hidden unresolved gate. No publishing authorization assumed.
**Files:** New actual M3 acceptance report, delivery map and root setup/implemented boundaries only when accurate. No fabricated passing template.

### Safe environment setup

- [x] Isolated Compose project `researcy-m3-acceptance` and private override; separate databases/buckets/Qdrant collections and localhost API 8003/web 3003/PostgreSQL 55435/MinIO 9003. Production Next reaches internal API and exact trusted origin `http://localhost:3003`; opaque fixture sessions are not claimed as real OAuth acceptance.
- [x] Private override and project/network/storage labels reviewed; restricted UID/seccomp/caps preserved. API-only gateway credentials restored into an additional mode-0600 private override after Eval state loss; no credential committed or sent to worker/web.
- [x] Isolated services, twice-applied migrations and dependency preflight exercised. Actual worker processed only the explicitly guarded public/geometry fixtures and stopped; no owner queued job consumed or permanent worker started.
- [x] Accepted public original copied through provenance-preserving isolated intake with observed immutable source SHA/version and real worker publication; not claimed as a fresh arXiv-network acquisition. Actual production API/web used for Reader journeys.

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

- [x] G1 recorded original hash/download, GET/HEAD/206/416/If-Range, stalled/disconnected cleanup and actual same-origin canvas/text/page/outline controls; T1/T2 final production evidence plus T8 original-PDF checks.
- [x] G2 actual product parallelization deltas preceded committed terminal/citations; exact accepted GET/one-click original page/boxes/card and bounded-history follow-up recorded. Substantive claims reviewed against quotes separately from geometry.
- [x] G3 actual unsupported-carbon refusal plus isolated real-DB canonical foreign/raw/ambiguity/ligature/multipage/missing-geometry failures and actual HTTP graph search/repair ceilings. Controlled negative cases are explicitly not natural provider output.
- [x] G4 isolated two-session owner/private-resource/random equivalence; real DB/API tests for pre-body auth/CSRF/Origin/unready/quota/concurrent/duplicate/revocation boundaries and latest same-origin two-owner smoke. No M1 real-Google promotion.
- [x] G5 actual same-origin disconnect/interrupted reload plus controlled real HTTP generation/SSE timeout/429/5xx/EOF/backpressure/CAS boundaries; explicit browser retry preserves failed pair and completed new pair. No hidden retry or false completion.
- [x] G6 closed under explicitly owner-approved master revision 2.2 / amended child G6: actual Gemini application graph answer/search, adversarial action/source containment and valid subsequent output, plus separately labelled malformed/unsupported local HTTP provider-stream/graph rejection. Record selected/echoed identity, physical calls, trace, first-delta/total latency, truthful usage and null/unavailable cost reason. No manufactured natural malformed Google output or inferred fallback verification.
- [x] G7 final backend 719 passed/one opt-in skip; pinned Node 22.14 frontend 113 passed; production builds and recorded actual keyboard/focus/width/zoom/crop/rotation/contrast/reduced-motion/scroll/composer/state journeys. Original boxes compared individually against authoritative geometry, not page-only screenshots.
- [x] No-build/no-test finite Reader resource observation recorded: API/web within preserved caps, no OOM/restarts; native process RSS and host swap/pressure measured with limitations explicit. No M2 evidence rewrite, model change or owner-application shutdown.
- [x] Request code review and resolve blocking findings. Independent final targeted backend review is clean; current backend 756 passed/one opt-in skip, final production build and actual path smokes recorded. Throwaway processes/exact temporary test settings removed; owner data/historical evidence preserved. G6 is still open; no publication/prune/volume deletion.
- [x] Safe evidence report records exact executed environment/commands, outcomes, request IDs, original hash/version and measurement provenance; private text/screenshots/secrets remain outside Git.
- [x] Delivery map reconciled to Implemented only. M1/M2/historical Q0 unchanged; G6 remains blocked, while unavailable monetary cost is an owner-approved documented limitation. No owner cutover, push, merge or prune.

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

## Owner-approved closure clarification — 2026-10-02

The owner retained G6's actual graph negative/valid-after-negative gate and approved monetary cost `null` / `unavailable` with documented reason, actual per-attempt usage, calls and latency. Master revision 2.1 and child §10 record the limited approval. Historical tariff-blocked checkpoints above remain historical; the unavailable applicable tariff is now a measurement limitation, not an M3 acceptance blocker. No tariff calculator, alternate route/model, free-cost assertion or weakened G6 interpretation is authorized.

Task 9 final backend review is complete: demonstrated RED → GREEN corrections and independent final targeted clean verdict are recorded in the acceptance report. G6 remains unchecked; the approved cost clarification is not permission to infer Verified.

Final backend verification after closure corrections: **756 passed, 1 opt-in arXiv skipped in 497.28s**, production API build and observed same-origin/live-client plus final local-provider-stall/cancellation/malformed-accounting smokes recorded in the report. Frontend remained unchanged; its previous 113-pass/build/browser evidence is retained, not relabelled as a new run. G6 stays unchecked.

## Gemini primary cutover addendum — owner approved

**Goal:** Requalify the implemented M3 application graph on direct `gemini-3.8-flash`, retaining explicitly configured 9Router for subsequent runs and preserving all ownership/citation/stream bounds.

**Authority:** Master revision 2.2, amended child §§8/11/12 and delivery-map M3. The owner approved manual switching and schema-aware G6, then explicitly approved implementation G1–G3: “Tôi phê duyệt addendum triển khai G1–G3. Hãy thực hiện theo workflow approved spec/plan của repository.” This authorizes isolated implementation/requalification, not automatic failover, owner-service startup, publishing or Verified status without evidence.

### Task G1: Fixed provider configuration, streaming contract and truthful accounting

**Files:** Modify `apps/api/researcy/config.py`, `apps/api/researcy/generation/client.py`, `apps/api/researcy/agents/reader.py`, `apps/api/tests/test_generation_config.py`, `apps/api/tests/test_generation.py`, `apps/api/tests/test_reader_agent.py`, root `.env.example` and `compose.yaml`. Reuse `apps/api/researcy/generation/models.py` action types; no new provider package, SDK or dependency.

**Interfaces:** Preserve `GenerationClient.stream(messages, follow_up=False, deadline=None, on_metadata=...)` and browser/API contracts. Add `Settings.generation_provider` with exactly `gemini`/`9router`; preserve the existing endpoint/key/model settings. Validate exact HTTPS Google base/model for Gemini; retain the existing safe `/v1` endpoint and fixed Antigravity model for 9Router. Worker settings continue excluding generation endpoint/key. Do not add a production alias for `GEMINI_PROBE_API_KEY`.

- [x] RED: Add configuration boundary cases using the existing monkeypatch convention. The following valid-primary case fails before cutover because `/v1beta/openai` and the new model are rejected:

```python
def test_google_primary_accepts_its_exact_endpoint_and_model(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "gemini")
    monkeypatch.setenv("GENERATION_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setenv("GENERATION_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("GENERATION_API_KEY", "isolated-test-only")
    settings = Settings.from_env()
    assert settings.generation_endpoint == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert "isolated-test-only" not in repr(settings)
```

Pair with parameterized rejection of an attacker host, HTTP Google URL, query/userinfo, invalid provider and provider/model mismatch; assert `ValueError`, not error-message wording. Retain credential isolation, TLS, limit and cancellation tests. Migrate existing local gateway fixtures to explicit `9router` selection rather than weakening Google's endpoint rule to accommodate fixtures.

- [x] Execute the configuration boundary RED in the existing restricted Python 3.12 pytest harness; record the actual pre-cutover valid-Google failure. This is the isolated execution equivalent of the planned host `uv run pytest` command, not a claimed host invocation.
- [x] GREEN: Make provider selection immutable per Settings/client instance. Default API configuration targets Gemini; `9router` requires explicit operator selection and its existing route. Update direct-constructor checks as well as `from_env`, and all affected tests/callers. No automatic retry or provider switch. Add provider-specific Gemini request fields to the existing payload:

```python
# In the existing payload construction; use imported existing action models.
if self.settings.generation_provider == "gemini":
    action_type = AnswerAction if follow_up else AnswerAction | SearchAction
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": "reader_action",
            "strict": True,
            "schema": TypeAdapter(action_type).json_schema(),
        },
    }
    payload["reasoning_effort"] = "low"
    payload["stream_options"] = {"include_usage": True}
```

Retain the already-qualified 9Router payload; do not assume native schema support there. Backend validation remains authoritative on both paths. Do not change terminal stop/DONE/EOF semantics or publish provisional citations.

- [x] Replace the hardcoded metrics source with selected-provider terminal provenance and attach configured provider/model to each actual attempted pass before network I/O. Keep echoed model distinct from configured identity. Preserve paid-attempt reservation/checkpointing, cancellation propagation, malformed metadata invalidation, unknown/partial totals and null/unavailable monetary cost.
- [x] Inspect actual Gemini terminal usage in the private protocol smoke before adopting any provider-specific arithmetic rule. Existing `_usage` reasoning-versus-prompt comparison is a gateway assumption. Retain nonnegative integer and applicable cache/detail invariants, but validate reasoning/total relationships against the documented and observed provider mapping; do not silently repair inconsistent counters or invent counts. Add permanent regression cases only for actual plausible usage failures, including cancellation after metadata and contradictory usage.
- [x] Execute the five affected pytest files (`test_generation_config.py`, `test_generation.py`, `test_reader_agent.py`, `test_reader_stream.py`, `test_reader_citation_publication.py`) in the restricted Python 3.12 harness — 171 passed in 137.05s. The container wrapper replaces host `uv run`, without changing test contracts.
- [x] Build/recreate the isolated API only, using private override input; preserve its database/objects and do not run migrations or workers. Map the root preparation key into `GENERATION_API_KEY` privately, without argv/output. Confirm effective provider/model via a sanitized probe; never print complete environment. Use a throwaway protocol capture against the real GenerationClient to inspect initial/follow-up schema, usage request, reasoning setting and shared deadline; remove capture after smoke. Request-shape inspection is diagnostic, not a permanent forwarding/source-text test.
- [x] Review the integrated diff and commit only intended code/tests/public configuration after focused smoke; never stage private overrides, root `.env` or generated evidence. No push/merge permission inferred.

### Task G2: Bounded real Gemini graph qualification and controlled safety evidence

**Files:** Record sanitized evidence in `docs/superpowers/reports/2026-10-01-researcy-m3-acceptance.md`; use existing live message route, claim/citation resolver, hybrid retrieval and generation transport. Controlled harnesses remain private throwaway files, not production branches.

**Consumes:** Task G1's real primary configuration, bounded GenerationClient and truthful per-attempt metrics. **Produces:** Separately labelled actual-provider and controlled-fault evidence for amended G3/G5/G6, with run/request IDs and persisted state.

- [x] Verify the isolated public fixture before billing: paper `93b8811f-43b5-4f39-9578-72aceadf1afb`, immutable version `81492edc-6d44-4602-840f-124f4504cdf9`, original SHA-256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`. Recheck ready owner scope and hybrid retrieval; never substitute private owner data or a standalone text-only probe.
- [x] Execute sequential actual same-origin submissions via the production graph: (1) paper architecture supported answer; (2) carbon-footprint unsupported refusal; (3) bounded extra-search question that can yield a supported cited answer; (4) adversarial question requesting an unsupported action/foreign scope, followed by (5) valid supported question through the same validator. Maximum 12 hosted attempts across all cases, follow-ups/repairs and optional manual-route smoke. Count actual attempts before each request; stop rather than exceed the cap. Do not force a branch by editing prompts/outputs and describe it as natural model selection. If actual search is not observed, leave that criterion open.
- [x] For every accepted answer fetch persisted message/citations and compare verbatim quote, immutable version, page and exact boxes against authoritative provenance. Review substantive support independently from successful quote matching. Record safe first-delta/total latency, physical calls/search/repair counts, provider/model identity, terminal usage source/completeness and cost reason. No raw private text/provider body/key in the public report.
- [x] Exercise controlled production-stream malformed JSON, unsupported action, follow-up search, invalid citation, 429, stalled timeout and disconnect. Observe zero unauthorized tools/accepted citations, safe persisted failed/interrupted state, retained truthful paid metadata and explicit successful subsequent submission. Label faults controlled; do not report them as natural Google output. Keep valid graph/provider cases separate.
- [x] Optional alternative availability checked: authorized root settings and existing base override provide no legacy endpoint/credential/model mapping for a live 9Router smoke. Record that prerequisite; no owner gateway startup, automatic fallback or newly verified alternative runtime is claimed.
- [x] Record observed outcomes and any blockers immediately; M3 remains Implemented when any required new-primary criterion is unproven. Paid credit does not justify unbounded generation or guarantee quota.

### Task G3: Full affected verification, browser proof and evidence reconciliation

**Files:** Existing backend/frontend suites, production images, acceptance report, amended plan and M3 delivery-map entry; no UI redesign or database migration.

- [x] Run full affected pytest coverage in the restricted isolated Python 3.12 harness against temporary databases/real storage: `python -m pytest tests -q --tb=short -p no:cacheprovider` — 772 passed, 1 opt-in real-arXiv skipped in 468.27s. This is the recorded container equivalent of host `uv run pytest`, not a claimed host run.
- [x] Run existing web suite and production build with qualified Node 22.14.0: final `npm test -- --maxWorkers=1` — 113 passed in 20.59s; Docker production `npm run build` and API build passed. Exercise actual generation; do not sample resources during simultaneous builds/tests.
- [x] Open isolated `http://localhost:3003` in a real browser: supported Gemini answer, citation activation/original PDF exact highlight, Escape/focus return, refusal, stream interruption/reload and explicit resubmission. Observe fresh screenshot/landmark/overflow evidence; close the tab. Retain unaffected historical width/ownership/provenance checks as historical, not fresh Gemini observations.
- [x] Review final code/evidence, remove private throwaway captures/harnesses, and update ledger/report/map only from observed results. Final one-shot citation reveal passed production-browser RED→GREEN, including virtualized remount, explicit reselection and 1024px keyboard/reduced-motion checks; independent re-review found no P1/P2. Preserve owner stack/worktrees; no publishing, merge, migrations or worker/gateway startup.

**Self-review:** G1 covers route, secret isolation, schema distinction, unchanged stream bounds and provider-aware usage; G2 covers actual graph answer/search/refusal/containment, separate controlled rejection and recovery, exact persisted citations and bounded spend; G3 covers full affected verification and browser evidence. Existing schema/ownership/provenance contracts remain unchanged. No new dependency, provider abstraction, automatic fallback, tariff guess, native tool or manufactured natural negative is introduced.

### G1–G3 execution closure — 2026-10-03

Core cutover commit `47d8357`; citation reveal correction `a8848f0`. Actual campaign stopped at **11/12 hosted attempts**, no outstanding run; six terminal Gemini graph cases plus two earlier accounting diagnostics. Actual searches yielded supported citations, adversarial action/foreign-scope instructions yielded a refusal, and subsequent real submissions completed. Seven local HTTP provider-stream/graph faults were labelled controlled, with zero hosted calls. Existing G1/G4 provenance/ownership evidence retains its original environment/date; unavailable cost and optional unconfigured 9Router runtime are documented limitations, not fabricated passes. The acceptance report records fresh browser/build/suite/resource observations and the final gate matrix. This dated closure supersedes original Task 6/7/9 prerequisite and G6 blockers; historical notes above remain historical. No owner-data cutover or publication permission is inferred.

