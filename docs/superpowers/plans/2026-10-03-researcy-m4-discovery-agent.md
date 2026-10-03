# Researcy M4 DiscoveryAgent Recommendations and Explicit Add Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explicit Related papers search yields ≤3 verified arXiv metadata recommendations; explicit Add alone enters the existing import/processing pipeline and reaches ready.

**Architecture:** One acyclic request-scoped LangGraph inside FastAPI, with owner-bound metadata, one initial action pass, one official metadata search and at most one reasons pass. Reuse shared generation transport, arXiv safety policies, opaque-session security and current import. Next.js adds a compact Reader secondary section; PostgreSQL stores a small scoped quota/accounting ledger, not recommendation history or worker jobs.

**Tech Stack:** Existing Python 3.12/FastAPI/Pydantic/psycopg/Alembic/httpx2/LangGraph, PostgreSQL/MinIO/Qdrant/native ARM64 processing, Next.js 16/React 19/strict TypeScript, pytest/Vitest/Testing Library. Existing lockfiles authoritative; no new dependencies.

**Spec:** [M4 draft child](../specs/2026-10-03-researcy-m4-discovery-agent-design.md).

**Status:** Approved for isolated execution on 2026-10-03. Owner explicitly approved both documents and selected Gemini primary, schema-aware qualification, null/unavailable monetary provenance and M1 prerequisite exception. Isolated stack/native and at most twelve public-paper hosted attempts authorized. M4 Planned; no owner cutover/publication authorization. Draft proposal text below is retained as design history and resolved by master revision 2.3.

## Global constraints

- Only M4/AGENT-02. No M5 selections/ResearchAgent, automatic discovery/import, PDF search/download, generation worker job, hidden retry/fallback, broker/cache/framework/dependency.
- One initial pass, one reasons follow-up, one official search, ≤10 inspected unique records, ≤3 returned records. No output repair pass.
- Master architectural authority; map status authority; explicitly approve route, qualification composition and cost provenance changes before applying them.
- Proposed primary: `gemini-3.8-flash` at exact `https://generativelanguage.googleapis.com/v1beta/openai`, low reasoning/provider schema/streaming usage; 9Router alternative manual between runs only. Separate qualification for each selected route.
- Missing title produces actionable 409 before any model/search; owned usable-title unready paper produces PAPER_NOT_READY. No guessed title/query/abstract.
- Every private read/update owner-scoped; composite source constraints; 404 foreign/missing indistinguishable. CSRF/exact Origin/session before parsing attempted body/reserving quota/network.
- JSON search response exactly master fields, no usage/model diagnostics to readers. Full response validation before publication; reasons based only on supplied metadata/abstract, not PDF citations.
- Existing `POST /api/papers/arxiv` owns Add and idempotency/PDF/objects/jobs. Changed payload gets a new key; unknown-outcome retry of identical payload preserves key.
- 60-second generation pass, 5-second connect, 150-second request deadline; arXiv search stage ≤60 seconds including limiter/redirects; 1 MiB XML; inherited provider output ≤8192 tokens/256 KiB.
- One active Discovery run/owner; 20 accepted runs/trailing hour; 165-second lease; no late completion overwrites interrupted state; no durable generation continuation.
- Title ≤1000, abstract provider context ≤6000 code points, candidate authors ≤200 names ×200, reasons 1–1000. Strict JSON/Pydantic, unknown fields forbidden.
- Preserve main owner modifications/artifacts/private volumes/M3 worktree; no reset/stash/overwrite, owner migrations/worker/cutover, shared gateway restart, publishing/push/merge/prune/deletion.
- Controller owns schemas/migrations/interfaces/approval decisions/difficult races/review/integration. Default serial tasks. Delegate only independent mapped slices, not shared contract edits.
- RED→GREEN from plausible visible/security failure; environment failure is not RED. Focused actual smoke and review before next task; scoped local commit when authorized, never include owner files/private evidence.
- Relevant skills/Next installed guides read before implementation; LSP references if configured, otherwise scoped literal consumer inventory. Migrate every caller and remove obsolete aliases/defaults.
- No fabricated zero/free cost or controlled-as-provider claims. Draft §3 exception requires explicit M4 approval; otherwise missing monetary mapping blocks acceptance.

## 1. Entry gate and isolation

- [ ] Record exact owner approval of child, plan, route/qualification/cost amendment decisions, M1 prerequisite exception, and isolated services/hosted campaign/native-start permissions. No code before this gate. A chosen native/gateway operation requires point-of-risk approval where applicable.
- [ ] Read using-git-worktrees; inspect current refs/worktrees/owner changes, then create unoccupied `.omp/worktrees/m4-discovery-agent` / `feat-m4-discovery-agent` from verified current main. Never remove an occupied target. Preserve Phase A drafts by scoped committed documentation or copy only these requested files into the new worktree; do not copy untracked owner context/private runtime files indiscriminately.
- [ ] Apply the exact approved M4-only master amendment and M4 map text; link approved child/plan and set Designed/Planned per rules, not Implemented/Verified. If selected route differs from this draft, revise plan/spec first. Leave Q0/M1/M2/M3/M5 records unchanged.
- [ ] Prepare private ignored isolated Compose override/environment with unique project `researcy-m4-acceptance`, loopback web/API ports chosen after checking availability, unique DB/bucket/collections/volumes and exact same-origin settings. Do not mount main/M3 private override or owner data. Keep private settings outside Git and out of printed command arguments/logs.
- [ ] Install frozen dependencies using existing prescribed Python/Linux sandbox and Node 22.14 runtime. Capture baseline environment only; do not rerun historical owner tests to confirm handoff. Test fixtures retain `pg_conn`, private_bucket, selected_index and local HTTP faults; native runtime is not an ordinary deterministic-test dependency.

## 2. Ordered tasks and file boundaries

`T1 metadata/ledger → T2 strict role-neutral transport → T3 cancellable official metadata search → T4 secure bounded application graph/API → T5 Reader explicit search/Add UI → T6 real qualification/acceptance/review`.

No empty modules/config-only scaffolding. T1 delivers real DB metadata/reservation operations; T2 real transport validation; T3 real metadata adapter; T4 full API; T5 full browser journey. Contracts shared with downstream tasks are reviewed/frozen before those tasks. New files listed below are proposed paths, not claimed existing code.

| Task | Existing files | New files |
|---|---|---|
| T1 | `papers/arxiv.py`, `papers/intake.py`, `papers/routes.py`, `ingestion/preflight.py`, relevant tests | migration `0007_m4_discovery.py`; `discovery/models.py`, `discovery/repository.py`, package init; `test_discovery_repository.py` |
| T2 | `generation/client.py`, `generation/models.py`, `agents/reader.py`, `test_generation.py`, `test_reader_agent.py` and every literal/LSP-found consumer | `test_discovery_output.py` |
| T3 | `papers/arxiv.py`, `test_arxiv.py` | `test_arxiv_search.py` |
| T4 | `main.py`; shared helpers only if consumed | `agents/discovery.py`, `discovery/routes.py`, `test_discovery_api.py`, `test_discovery_agent.py` |
| T5 | `web/src/lib/api.ts`, `components/reader-workspace.tsx`, `components/discussion.tsx`, related existing CSS/tests | `components/related-papers.tsx`, `components/related-papers-interaction.test.tsx` |
| T6 | approved master/map links/status and only accurate setup documentation | `docs/superpowers/reports/2026-10-03-researcy-m4-acceptance.md` |

Keep types in their owning boundary: domain/Discovery action/API models in `discovery/models.py`; generation transport errors/events/JSON decoding in `generation/models.py`; official feed metadata in `papers/arxiv.py`; central browser payloads only `lib/api.ts`. No new universal agent/run/provider abstraction.

## 3. Shared interfaces to freeze

Signatures below are proposed contract, not pre-existing symbols:

```python
# discovery/models.py; frozen dataclasses / strict Pydantic models
@dataclass(frozen=True, slots=True)
class ActiveMetadata:
    owner_id: UUID
    paper_id: UUID
    document_version: UUID
    canonical_arxiv_id: str | None
    title: str
    abstract: str | None

@dataclass(frozen=True, slots=True)
class DiscoveryReservation:
    run_id: UUID
    source: ActiveMetadata
    request_id: str

class SearchArxivAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    next_action: Literal['search_arxiv_metadata']

class StopDiscoveryAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    next_action: Literal['stop']

class CandidateReason(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    arxiv_id: str
    reason: str = Field(min_length=1, max_length=1000)
    # Add safe/nonblank Unicode validators, not merely min_length.

class DiscoveryReasons(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    papers: list[CandidateReason] = Field(min_length=1, max_length=3)

class RelatedPaper(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    arxiv_id: str
    title: str = Field(min_length=1, max_length=1000)
    authors: list[str] = Field(max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    arxiv_url: str
    # Reuse safe text validators; ID/URL are constructed from verified candidates.

class RelatedSearchResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    papers: list[RelatedPaper] = Field(max_length=3)
    request_id: str

DISCOVERY_INITIAL_OUTPUT = TypeAdapter(SearchArxivAction | StopDiscoveryAction)
DISCOVERY_REASONS_OUTPUT = TypeAdapter(DiscoveryReasons)
# Existing Reader action models stay in generation/models.py:
READER_INITIAL_OUTPUT = TypeAdapter(AnswerAction | SearchAction)
READER_FINAL_OUTPUT = TypeAdapter(AnswerAction)

# generation/models.py; strict UTF8/JSON object decode then adapter validation
# No Reader-action switch in the shared transport.
def decode_output(raw: bytes, output: TypeAdapter) -> BaseModel: ...

# generation/client.py; output/schema_name REQUIRED, no follow_up/default Reader schema
GenerationClient.stream(messages: list[dict[str, str]], *, output: TypeAdapter,
    schema_name: str, deadline: float | None = None,
    on_metadata: Callable[[GenerationEvent | None], None] | None = None
) -> AsyncIterator[GenerationEvent]
# GenerationEvent: kind content/metadata/completed, text, output: BaseModel|None,
# usage, echoed_model, finish_reason. Migrate former .action consumers cleanly.

# papers/arxiv.py; frozen candidate record, abstracts transient for candidates
@dataclass(frozen=True, slots=True)
class ArxivCandidate:
    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    abstract: str | None

# T1 supplies shared title-term availability; T3 reuses it for query construction.
def related_title_terms(title: str | None) -> tuple[str, ...]: ...

@dataclass(frozen=True, slots=True)
class ArxivSearchResult:
    candidates: tuple[ArxivCandidate, ...]
    inspected_entries: int
    inspected_unique: int
    invalid_ids: int
    duplicates: int
    http_requests: int
    redirects: int

def build_related_query(title: str, abstract: str | None) -> str: ...
async def search_official_arxiv_metadata(query: str, *, deadline: float,
    request_id: str, transport: httpx2.AsyncBaseTransport | None = None
) -> ArxivSearchResult: ...
# Adapter validates ≤10 entry identities/fields and collapses duplicates.
# Graph excludes active/title and chooses ≤3; result counts are request-local.

# discovery/repository.py; get_conn caller, short transactions, scoped operations
load_active_metadata(conn, owner_id: UUID, paper_id: UUID) -> ActiveMetadata
reserve_discovery(conn, source: ActiveMetadata, request_id: str) -> DiscoveryReservation
record_discovery_attempt(conn, reservation: DiscoveryReservation, kind: str) -> None
finish_discovery(conn, reservation: DiscoveryReservation, *, state: str,
    metrics: dict, error_code: str | None = None) -> bool
# bool is CAS terminal outcome, false forbids response publication.

# agents/discovery.py; one whole result, no provisional browser events
async def run_discovery(reservation: DiscoveryReservation, settings: Settings,
    *, deadline: float) -> RelatedSearchResponse: ...
```

`ArxivSearchResult` is the single adapter return contract, including when its candidate tuple is empty. No mutable counter argument or global per-run statistics. T4 consumes these exact fields. Add author/title/abstract/Unicode validators and final selected-ID set equality in T2/T4. This record makes measurements auditable; it is not a cache or alternate browser API contract.

`related_title_terms` applies the child's usable-title rules and shared token/stopword/length bounds, raising `APIError(409, 'DISCOVERY_METADATA_MISSING', ...)` when absent/unusable/no title terms. T1's metadata loader calls it before ready/quota checks; T3's query builder reuses it rather than implementing another title policy. Schema names are fixed caller-owned literals: `reader_action`, `discovery_action`, `discovery_reasons`; never client/model fields.

```ts
// web/src/lib/api.ts; API types remain centralized
export type RelatedPaper = {
  arxiv_id: string; title: string; authors: string[];
  reason: string; arxiv_url: string;
};
export type RelatedSearchResponse = { papers: RelatedPaper[]; request_id: string };
export function searchRelatedPapers(paperId: string, signal?: AbortSignal): Promise<RelatedSearchResponse>;
// Existing importArxiv(arxivIdOrUrl, idempotencyKey) remains unchanged.
```

## Task 1: Actual metadata persistence and owner-scoped quota ledger

**Meaning:** Supply title/abstract truthfully and enforce persistent request limits without hijacking Reader messages/jobs.
**Depends on:** Approved decisions/isolated entry gate.
**Files:** T1 map, plus `tests/test_intake.py`, `tests/test_preflight.py`, existing schema consumers found by search.
**Produces:** ActiveMetadata/DiscoveryReservation and scoped repository functions above; migration head `0007_m4_discovery`; import abstract captured in existing acceptance transaction.

- [ ] RED metadata test: extend existing real PostgreSQL/MinIO import case with an Atom `summary`, import through the existing path, and assert the stored abstract equals normalized supplied summary while replay preserves original/version/job IDs and makes no reacquisition. Pair with absent summary/upload null and legacy rows preserved. No test of copied schema wording.
- [ ] RED reservation tests with `reader_source` from `test_conversations`: real ready publication, set title/abstract with parameters, load source via owner predicate; concurrent committed connections produce one active reservation; 21st accepted request in trailing hour is 429; zero charge for foreign/missing-title/unready; stale run expiry terminalizes interrupted and late finish returns false. Check immutable source identity/composite ownership in the new table.

```python
# New repository test imports existing real fixture, not a fake source.
from test_conversations import reader_source

def test_interruption_cannot_be_overwritten_by_late_finish(reader_source):
    from researcy.discovery.repository import (
        load_active_metadata, reserve_discovery, finish_discovery,
    )
    conn, scope = reader_source['conn'], reader_source['scope']
    conn.execute('UPDATE papers SET title=%s WHERE owner_id=%s AND id=%s',
                 ('Attention mechanisms', scope.owner_id, scope.paper_id))
    conn.commit()
    source = load_active_metadata(conn, scope.owner_id, scope.paper_id)
    run = reserve_discovery(conn, source, str(uuid4()))
    assert finish_discovery(conn, run, state='interrupted', metrics={}) is True
    assert finish_discovery(conn, run, state='completed', metrics={}) is False
    assert conn.execute('SELECT state FROM discovery_runs WHERE owner_id=%s AND id=%s',
                        (scope.owner_id, run.run_id)).fetchone() == ('interrupted',)
```

- [ ] Execute RED: `uv run --frozen pytest tests/test_discovery_repository.py tests/test_intake.py -q` in API directory or existing frozen restricted container `python -m pytest ...`; record exact failure/output, not guessed counts. Fixture creation failure is prerequisite failure, not RED.
- [ ] GREEN migration adds nullable abstract and ledger fields/checks/FKs/indexes specified in child §6; existing rows remain null, no network/backfill. Extend existing ArxivMetadata/IntakeMetadata and existing atomic INSERT, migrate all constructors intentionally; do not expose abstract unnecessarily on list responses. Update `ingestion/preflight.py` HEAD_REVISION to actual new head without compatibility aliases.
- [ ] GREEN repository uses get_conn caller + existing short transaction/owner lock conventions, shared ready loader outside owner transaction, snapshots owned active source and rechecks scope on reservation. Query usability check precedes ready/provider/quota. Reserve one owner active slot, count 20 accepted ledger rows/hour, commit expired-run reconciliation even on quota/active rejection. Persist counters just before dispatch and CAS terminalization with bounded metadata only.
- [ ] GREEN title/query usability normalization per spec before generating; no title-derived model fallback. Do not create route or graph placeholders in this task.
- [ ] Focused checks: named new tests plus `test_schema.py`, `test_processing_schema.py`, `test_reader_schema.py`, `test_preflight.py`, `test_intake.py` in isolated restricted environment.
- [ ] Actual smoke: apply forward migration twice to populated isolated pre-M4 database; compare original paper/version/job/replay identities and null legacy abstracts, call real reservation/attempt/interruption/CAS operations on a ready isolated scope; observe persisted rows and one active slot without any model calls.
- [ ] Review migration/security/short transactions/cleanup and record safe smoke evidence; scoped local commit only after authorization. No owner database migration.

## Task 2: Strict role/pass output contracts on one generation transport

**Meaning:** Make existing transport accept Discovery output without inheriting Reader actions/citations/repair or duplicating network code.
**Depends on:** T1 frozen models.
**Files:** T2 map plus all Reader output/event consumers identified through LSP or scoped literal search.
**Consumes:** Existing Settings/provider safety, bounded SSE parsing/usage accounting.
**Produces:** Required output/schema_name parameters, strict `decode_output`, output-typed GenerationEvent and four adapters; Reader unchanged behavior.

- [ ] RED new malformed/action/final-output cases: reject duplicate keys, trailing JSON, NaN, extra query/URL/owner fields, unsupported action, whitespace reasons, fourth result, wrong field types. Candidate selected-set equality belongs to graph tests, not a tautological serializer test.

```python
@pytest.mark.parametrize('raw', [
    b'{"next_action":"search_arxiv_metadata","url":"https://hostile.example"}',
    b'{"next_action":"search_arxiv_metadata","next_action":"stop"}',
    b'{"next_action":"import_paper"}',
])
def test_discovery_rejects_untrusted_tool_instructions(raw):
    from researcy.discovery.models import DISCOVERY_INITIAL_OUTPUT
    from researcy.generation.models import decode_output, InvalidModelOutput
    with pytest.raises(InvalidModelOutput):
        decode_output(raw, DISCOVERY_INITIAL_OUTPUT)
```

- [ ] RED controlled local HTTP stream sends valid Discovery action and reasons through actual transport; existing client currently decodes Reader output and fails. Assert completed typed output and real terminal usage preservation after malformed final output/truncation/timeout; guard ≤1 physical request/no fallback in that pass. Provider request schema tests must demonstrate prohibited action rejected/contained, not only copy expected JSON fields.
- [ ] Run RED: `uv run --frozen pytest tests/test_discovery_output.py tests/test_generation.py -q` in isolated API test runtime.
- [ ] GREEN retain strict UTF-8/duplicate-key/constants/trailing-data handling; validate caller-supplied adapter. Replace `_ACTION_SCHEMAS`/Reader-specific decoder in client with required explicit adapter and fixed schema name passed by role. Provider payload policies unchanged: schema sent for Gemini, not falsely claimed for 9Router. Keep generation client checks/deadline/limits/no retries/terminal callbacks intact.
- [ ] GREEN migrate Reader `follow_up` caller to READER_INITIAL_OUTPUT/READER_FINAL_OUTPUT selection and .action→.output; retain ClaimParser and Reader repair rules in Reader. Replace former `validate_action` call sites in tests with explicit adapters; remove obsolete decoder/export/event field rather than retain shims. Inventory all refs first; no LSP configured in Phase A, recheck at execution.
- [ ] Focused tests: generation/output/config plus Reader graph/schema/parser/citation-publication/stream. Do not add tests pinned to incidental wording/default field copies.
- [ ] Actual smoke: controlled local HTTP provider emits split UTF-8/SSE valid search/stop/reasons and invalid envelopes through actual GenerationClient; observe valid output/invalid rejection, deadlines and actual usage on failure. Separately smoke existing Reader answer/search in isolated application using controlled transport (labelled controlled, zero hosted calls).
- [ ] Review caller migration and usage/backpressure regression risk; record results and focused local commit. No product provider qualification claim yet.

## Task 3: Official metadata search with shared limiter and cancellation

**Meaning:** Search official arXiv without acquisition/import, safely handling untrusted query/feed data and cancellation.
**Depends on:** T1 metadata types, T2 strict models; ArxivSearchResult frozen above.
**Files:** `papers/arxiv.py`, `tests/test_arxiv.py`, new `tests/test_arxiv_search.py`.
**Produces:** `build_related_query` and cancellable `search_official_arxiv_metadata -> ArxivSearchResult`.

- [ ] RED query tests: title/abstract containing arXiv syntax (`OR`, quote, URL) cannot introduce client/model URL/filter or raw query clause; no usable title terms yields missing metadata before external calls. Assert selected scientific token predicates, not source wording snapshots.
- [ ] RED Atom tests through existing httpx2 MockTransport/local server patterns: modern/legacy ID normalization, absent summary/authors, duplicate versions/conflicts/invalid IDs, >10 entries, malformed XML/error entry, missing title/unsafe fields. Verify no `/pdf/` request and no per-candidate requests; at most first 10 entries inspected, canonical candidates bounded.
- [ ] RED async real local HTTP faults: stalled headers/body, drip feed, split redirects exhausting aggregate time, unsafe redirect blocked before destination request, >1MiB XML, 406/429/503 shared cooldown. Interleave sync importer and async search: enforce shared 3-second start spacing/exclusion; cancel queued/active search, then successful search proves lease released with no late calls. Avoid long sleeps by injectable clock/limiter time where appropriate; use actual stalled sockets for cancellation proof.
- [ ] Run RED: `uv run --frozen pytest tests/test_arxiv_search.py tests/test_arxiv.py -q`.
- [ ] GREEN build backend-fixed token groups/encoded params exactly child §5; first 12 title terms and first 8 additional abstract terms, no second query/pagination/fallback.

```python
# Production query request ownership; backend-derived values only.
params = {
    'search_query': build_related_query(source.title, source.abstract),
    'start': 0, 'max_results': 10,
    'sortBy': 'relevance', 'sortOrder': 'descending',
}
# Initial URL is fixed https://export.arxiv.org/api/query.
# Do not dispatch this snippet until the whole initial action validates.
```

- [ ] GREEN async driver uses existing httpx2, trust_env=False, explicit manual redirects, overall timeout/cancellation and aclosing. Reuse existing destination/retry/status/Atom normalization policies through focused functions; migrate single-record importer to shared metadata parsing/status helpers where applicable. Preserve import acquisition semantics and no retry. Never copy importer PDF path into search.
- [ ] GREEN replace request-held RLock with non-reentrant request exclusion plus separately protected cooldown/start state in ArxivLimiter; preserve sync public acquire API and make async acquire cancellation-aware via nonblocking request lock + short async waits. No RLock held across await, no to_thread lock lease lacking guaranteed release. Both sync and async paths share same global limiter/pacing/state. Prove reentrancy-dependent cooldown calls no longer deadlock.
- [ ] GREEN bound stream/XML; examine first 10 Atom entries, normalize/dedup and fail conflicting metadata safely, return explicit counters. No URLs from feed are followed; canonical link constructed later. Missing authors=[], abstract=null; no invented metadata.
- [ ] Focused tests rerun new tests, existing arXiv/intake/io-cancellation. Actual smoke local fault server through adapter confirms deadline/abort/cooldown with one later healthy request; separately one official search is permitted only if authorized, reported real-network not deterministic suite evidence. No call if authorization/service prerequisite missing.
- [ ] Review importer safety regressions and actual release evidence, record safe counts; commit focused changes locally if authorized.

## Task 4: Secure bounded DiscoveryAgent and application endpoint

**Meaning:** Complete application action→tool→reasons behavior, with identity containment and no search-time imports.
**Depends on:** T1–T3 reviewed; do not parallelize shared ledger/schema/transport work.
**Files:** `agents/discovery.py`, `discovery/routes.py`, `main.py`, new `test_discovery_api.py`, `test_discovery_agent.py`; existing DB cancellation helpers reused, no independent policy copy.
**Consumes:** metadata/reservation repository, explicit generation adapters, ArxivSearchResult.
**Produces:** master JSON endpoint and complete one-response run.

- [ ] RED route tests use existing `reader_source`/`reader_client` fixture patterns and actual scoped sessions/CSRF (from test_conversations/test_library). Set stored title/abstract with SQL parameters, no owner URL/body input. Foreign/random 404 same safe envelope; unsigned/revoked/CSRF/Origin fail before model/search; missing/blank/unusable title returns actionable 409 with zero dispatches/ledger reservations. Not-ready/request-body/query/config/quota precedence explicit.
- [ ] RED graph via controlled local HTTP SSE generator (existing `local_fault_server`), real ledger and injected official metadata HTTP: stop=1 call/0 search; search+eligible=2 calls/1 search; empty=1 call/1 search; initial malformed/extra URL/filter=1 call/0 search; final mismatched/duplicate/missing IDs rejects all results after two calls. Observe real physical HTTP requests and persisted accounting; no mocks-as-real-provider claim.
- [ ] RED no-import security regression: compare owner-scoped paper/version/job/import-idempotency row identities and bucket object key/hash sets before/after successful search; intercept outbound metadata/PDF boundaries to prove metadata-only, no embedding/Qdrant execution. Compare exact sets, not only count growth.
- [ ] RED concurrency/deadline/cancel: abort in initial stream, limiter wait, arXiv body and follow-up; CAS completion racing interruption; API expiry reconciliation; healthy new explicit run after abort releases slot. Retain usage observed before failure and unknown missing usage, never zeros.
- [ ] Execute RED: `uv run --frozen pytest tests/test_discovery_api.py tests/test_discovery_agent.py -q`.
- [ ] GREEN route authenticates/CSRF/authorizes before attempted body read; consumes empty body with 1KiB ceiling through one receive owner, authorizes metadata/ready/config, reserves persistent quota, races graph against absolute entry deadline/disconnect, closes every task/transport. Registration through main existing router convention; JSON no-store/error/request-ID behavior reused.
- [ ] GREEN acyclic graph: initial→stop or metadata search→select→reasons→validate→terminal. Entire initial validates before search. Select canonical active exclusion/title alias conservative exclusion/first three eligible official relevance order; no second search/repair/hidden retry. Count attempts before dispatch, one search marker before network, record physical requests separately.

```python
# Identity publication invariant in graph, after strict reasons decoding:
by_id = {item.arxiv_id: item.reason for item in reasons.papers}
if len(by_id) != len(reasons.papers) or set(by_id) != {c.arxiv_id for c in selected}:
    raise GenerationFailure('GENERATION_INVALID_OUTPUT')
# Build response from selected authoritative metadata, not from model metadata:
papers = [RelatedPaper(
    arxiv_id=c.arxiv_id, title=c.title, authors=list(c.authors),
    reason=by_id[c.arxiv_id], arxiv_url='https://arxiv.org/abs/' + c.arxiv_id,
) for c in selected]
```

- [ ] GREEN initial/reasons prompts delimit untrusted metadata as JSON and prohibit instructions in abstracts, PDF-reading/citations and invented results. No document text/previous Discussion answers/private owner data beyond approved source metadata. Strict selected-ID equality and full Pydantic response validate before CAS completed state/HTTP publication; CAS failure publishes no recommendations.
- [ ] GREEN persist safe metrics/counters/terminal usage and logger fields from child §7; failed/interrupted accounting and lease reconciliation; no title/abstract/reason/provider response logging. Monetary null remains honest measurement and is not unapproved gate closure.
- [ ] Focused tests new endpoint/graph plus repository/transport/arXiv and affected auth/Reader/import suites.
- [ ] Actual smoke isolated API through real HTTP: authenticated POST completes controlled search→reasons, stop/empty, missing-title, foreign/random, malformed action zero tools and client disconnect→interrupted→new explicit success; compare real DB/object sets. No browser or actual provider gate closure inferred from this controlled smoke.
- [ ] Review security/branch counts/receive ownership/CAS/usage provenance; fix findings, record exact evidence, scoped local commit if authorized.

## Task 5: Reader secondary Related papers and explicit Add

**Meaning:** Deliver explicit user intent, metadata-only reasons and existing persisted Add/preparation journey without displacing Reader.
**Depends on:** T4 frozen API; T1 importer abstract contracts reviewed.
**Files:** T5 map, affected interaction tests only; no new frontend API route/proxy unless actual existing same-origin rewrite fails.
**Consumes:** centralized search/import helpers, paper/ready source and existing unauthorized callback.
**Produces:** complete idle/loading/results/empty/missing/error/cancel/Add UI and link to actual preparation/ready Reader.

- [ ] Read web AGENTS.md, relevant installed Next guides, React/UI skills before code. Preserve existing fonts/tokens/styles; no design-system rewrite or new UI library.
- [ ] RED role/label-driven new interaction tests: mount/reload/deep link/citation selection make zero related requests; explicit button yields results; loading Cancel and stale response on A→B paper or retry cannot overwrite new state; errors/missing/empty safe and retry explicit; keyboard focus/labelled region/one main; <1024px creates no hidden search.
- [ ] RED Add tests with real consumer API mock boundary: search alone never invokes import; clicking one candidate calls existing import path with identical canonical payload/key across unknown outcome retry; selecting a different candidate gets distinct key; returned IntakeResponse shows saved/link not ready; already-owned response opens existing ID. Treat these as browser consumer tests, not backend/provider/processing proof.

```tsx
// Example consumer-visible RED shape; reuse test setup/central helpers.
it('keeps import separate from explicit related search', async () => {
  const user = userEvent.setup();
  render(<RelatedPapers paperId={paperId} onUnauthorized={onUnauthorized} />);
  expect(importArxiv).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Related papers' }));
  await screen.findByRole('link', { name: /arXiv/i });
  expect(importArxiv).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Add to Library' }));
  await screen.findByRole('link', { name: 'View in Library' });
  expect(importArxiv).toHaveBeenCalledTimes(1);
});
```

Fixture response is a valid single RelatedPaper and successful IntakeResponse using existing type fixtures; assertions expanded to payload/key and saved-vs-ready state in the actual test. Do not permanently test helper forwarding/copied fetch options/schema wording; use throwaway transport smoke for forwarding.

- [ ] Execute RED: `npm test -- src/components/related-papers-interaction.test.tsx` in prescribed web runtime.
- [ ] GREEN central `RelatedPaper`/`RelatedSearchResponse` and `searchRelatedPapers` use mutate/parseResponse, same-origin POST with no body and AbortSignal. Add safe code mappings to userErrorMessage; raw diagnostics/provider identifiers remain hidden. Existing import helper remains the only import API.
- [ ] GREEN RelatedPapers has idle/loading/results/empty/missing/error/cancel state, per-run controller+identity, unmount/source/logout cancellation and explicit retry. One browser request for whole backend graph, no browser initial/follow-up choreography. No model request inside effect/render/GET/deep-link restore.
- [ ] GREEN ReaderWorkspace injects secondary actions into Discussion via a typed ReactNode slot only when supported active ready version; keep PDF ratio/independent scroll/sticky composer/citation focus. For historical-version Reader, discovery is active-paper metadata, so disable action with an explanation until active version is displayed rather than silently use a different source. No unready preparation-page search or M5 placeholders.
- [ ] GREEN result cards plain text title/authors/reason with metadata-based label/canonical arXiv link, explicit Add; no full-text citation decoration. Store per-canonical exact payload idempotency keys in component memory, preserve on unknown retry; serialize Add submissions, honor Retry-After and existing import safe errors. Added/existing response creates View in Library link, no automatic navigate/ready claim/research call/job-poll fanout. Existing detail page handles preparation/processing/ready and honest failure.
- [ ] Focused new interaction tests plus discussion/citation/Reader/library/recovery suites. Delete obsolete incidental absence/wording tests rather than repin them. Production build after integration; do not claim lint (none configured).
- [ ] Actual production-browser smoke isolated web/API: inspect live Related control + result labels/arXiv/Add/accepted link and missing/empty/error/cancel controlled states; focus/keyboard/Escape citation preserved, long metadata wraps/no overflow at 1024/1280/1440 and small boundary 375/768/1023; fresh screenshots/accessibility evidence, close proof tab. Tests/build alone insufficient. Controlled discovery transport remains labelled controlled until T6.
- [ ] Review actual UI/data states/unknown import outcome/cancellation, record observations and scoped commit if authorized.

## Task 6: Approved-route qualification, actual Add→ready and delivery evidence

**Meaning:** Close the milestone only with actual product route, official metadata, real processing and browser proof, not mocked action outputs.
**Depends on:** T1–T5 reviewed and approved route/cost/qualification policy + explicit runtime/hosted authorization.
**Files:** safe M4 acceptance report, master/map approval/status links, accurate setup docs only where changed. Private scripts/screenshots/provider metadata/settings kept ignored/outside Git; never commit paper text, prompts, cookies or keys.

### Reproducible isolated commands

Commands below are planned, not executed evidence. Private file paths/project names are intentionally explicit; prepare overrides with unique volumes/ports/database/bucket/collections and no root .env inheritance. If chosen existing test harness requires private fixture configuration, record its exact actual invocation rather than pretending host commands ran.

```bash
# API directory, isolated test services already reachable:
uv sync --frozen
uv run --frozen pytest tests -q
# Optional real arXiv suite only if authorized; report separately:
ARXIV_REAL_NETWORK=true uv run --frozen pytest tests/test_arxiv.py -q
# Web directory, pinned Node 22.14:
npm ci
npm test -- --maxWorkers=1
npm run build
# Isolated worktree root only:
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml --profile web --profile processing build api web worker
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml up -d postgres minio
# MinIO health ready before init; no bucket-init DNS race:
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml up -d minio-init api
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml exec -T api alembic upgrade head
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml exec -T api alembic upgrade head
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml --profile processing up -d qdrant
# Requires separately authorized native runtime available/configured:
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml --profile processing run --rm --no-deps worker python -m researcy.ingestion.preflight --check
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml --profile web up -d web
# Only isolated worker; consumes isolated fixtures, NEVER owner queued jobs:
docker compose --env-file /dev/null -p researcy-m4-acceptance -f compose.yaml -f /tmp/researcy-m4.private.yaml --profile processing up -d worker
```

Private override must include all settings needed with /dev/null env and must not reuse owner bindings/resources. Native preflight is a real request/load of configured embedding runtime; run only after authorized start/load. Existing preflight proves processing readiness, not generation readiness. Do not inspect expanded Compose config because it exposes secrets. Actual provider calls must go through the application POST; standalone catalog/transport probes do not close graph gate.

### Acceptance steps

- [ ] Build and affected full suites as above; report actual environment/commands/counts/skip reason and production image/commit identities. No reported failures rerun merely to confirm; diagnose first. Do not build/test concurrently with shared-host resource observations.
- [ ] Create isolated A/B identities using existing session fixtures, label synthetic/local sessions accurately; use actual Google only if separately authorized/available. Import a public active source (`1706.03762` suitable when real metadata/PDF supports it) through actual endpoint and observe existing real processing ready. No private owner PDF/metadata sent to provider.
- [ ] G1 actual auth/CSRF/Origin/ownership/missing-title/unready/quota/active-slot HTTP checks; store safe request IDs, no session contents; malformed JSON body never bypasses authorization. Missing metadata has zero provider/search calls measured, not merely hidden UI button.
- [ ] G2 real approved primary application graph search→reasons, stop, adversarial action/filter/URL containment and subsequent valid run. Proposed cap 12 physical hosted attempts, including follow-ups/any expressly approved alternative; sequential, maintain remaining-call guard before dispatch, no hidden retries. Stop on diagnosed blocker/budget ceiling; do not change route/gate to get green. Natural malformed/unsupported outputs, if any, stay natural; controlled stream corruption stays controlled.
- [ ] G2 controlled malformed/unsupported local HTTP SSE through production transport/decoder/graph, zero arXiv calls/import/publication and useful failure. Do not equate these with natural provider-invalid output. If schema-aware amendment denied, unchanged qualification requirement remains blocking.
- [ ] G3 actual official metadata search counters/≤10 entries/unique, ≤3 actual distinct IDs/active exclusion; inspect exact public metadata/abstract privately and manually assess every reason with a small rubric: title-topic relation, abstract-supported rationale, no invented metric/result, no PDF-read claim, missing-abstract limitation respected. Record safe case IDs/verdicts only. Weak relevance/identity unsupported output is failure, not acceptance by schema alone.
- [ ] G3 before explicit Add compare exact scoped paper/version/job/import-idempotency rows and isolated bucket object set/hash; search requests contain metadata only (no PDF/object/embedding/Qdrant operations). Record unchanged identity sets; don't confuse existing processing objects with search side effects. Actual empty success only reported if observed; controlled empty-feed/error states labelled.
- [ ] G4 owner explicitly chooses one actually relevant returned ID absent from isolated Library. Add via UI existing import endpoint/Idempotency-Key; verify real PDF/original hash/private object/version/job and complete real processing to ready/publication. Repeat identical request/key and canonical-existing Add preserves IDs/object/job. Open persisted Library/detail/Reader after reload. If API/PDF/import/provider/native outage prevents this, finish reachable gates and record exact blocker; no fixed fake discovery IDs.
- [ ] G5 actual production browser at widths/states from child, keyboard Related→results→arXiv→Add→View in Library→ready Reader, visible focus/one-main/no overflow/reduced motion/contrast and preserved Discussion composer/citation Escape behavior. No model call on reload/deep links/navigation/render, stale A result cannot replace B, abort never followed by hidden retry. Fresh visual/accessibility proof then close managed tab.
- [ ] G6 actual disconnect and controlled local HTTP provider/arXiv failures: malformed/action/identity/429/503/timeout/drip/redirect/abort; interrupted ledger/usage retention/slot release, no late tool/follow-up/completion. Label controlled cases explicitly, zero hosted calls for local fault campaign.
- [ ] Record route/provider configured/echoed identity with truthful provenance, per-pass physical call/attempt counts, actions/tools, unique/eligible/result counts, monotonic latency, usage known/partial/unknown and cost source. Investigate applicable tariff/units privately; null/unavailable is a disclosed limitation only under separately approved M4 exception. No zero/free assertion/unrelated API price. Optional 9Router is unqualified unless an authorized actual M4 campaign observes it.
- [ ] Request targeted code review after full smoke; controller checks security/source identity/call ceilings/cancellation/limiter/schema caller migration and real UI. Resolve blocking findings, run affected regression/smoke once after final edits. Review feedback verification does not become an unrelated refactor.
- [ ] After smoke, update requested acceptance report and existing docs/setup boundary accurately; remove only newly created throwaway scripts/private test scaffolds when authorized, preserve owner and retained audit artifacts. Stop isolated services without deleting volumes if shutdown authorized; native/shared service teardown separately scoped. No push/merge/prune.
- [ ] Reconcile M4 status: Implemented for complete code without all evidence; Verified only approved G1–G7 have recorded actual observations. Failed/unobserved gates retain prior status + exact blocker; do not rewrite Q0/M2/M3 history or promote M1/M5.

### Evidence record template

```text
case / gate / evidence class: actual provider | actual official API | controlled HTTP | browser | deterministic test | owner-reported
commit/image/runtime and exact invoked command/journey
expected → observed; safe request/run IDs
configured provider/model/endpoint (no credential), echoed identity + source
initial/follow-up physical calls vs reserved attempts; action/tool/redirect counts
inspected entries/unique/invalid/duplicates/active-excluded/eligible/returned
latency and per-pass terminal usage; aggregate completeness
monetary estimate/null, currency/tariff date/billing-unit source or unavailable reason
before/after source/import/object identity checks and explicit Add→ready observations
limitations, safe report references, blockers; no prompts/text/secrets in Git
```

## 4. Coverage and controller review checkpoint

| Child sections | Tasks | Gates |
|---|---|---|
| §§1–3 authority/status/amendment/isolation | Entry/T6 | Approved decisions, no unapproved implementation |
| §4 API/actions/output | T2/T4/T5 | G1/G2/G5/G6 |
| §5 metadata/query/identity/upstream/add policies | T1/T3/T4/T5 | G1/G3/G4 |
| §6 graph/ledger/call/time/cancel | T1/T2/T3/T4 | G1/G2/G6 |
| §7 errors/accounting/privacy/cost | T1/T2/T4/T6 | G1/G2/G6 |
| §8 Reader/states/accessibility/Add | T5/T6 | G4/G5 |
| §§9–10 matrices/prerequisites/status | all/T6 | G1–G7 |

Controller self-review must cover: ready-only vs missing-title precedence, no new metadata editor/backfill, canonical versionless Add tradeoff, ≤10 upstream entries not pagination over duplicates, authoritative candidate identity vs semantic reason review, sync/async shared limiter lock ownership, one ASGI receive owner, DB work not abandoned on timeout, CAS before response, no third repair, Reader decoder clean migration, null cost not automatically approved, actual provider vs controlled labels and hosted budget. Documents remain drafts until owner approval; their creation does not advance milestone status.

**Approval checkpoint:** Review child and plan together, choose/approve the three §3 M4-only amendment items and M1 prerequisite exception. Approve isolated/native/hosted campaign scope separately as needed. Recommended execution is serial controller-led task→RED/GREEN→actual smoke→review; independent read-only review or genuinely separate edits may be delegated only after interfaces freeze. No implementation, main startup, provider calls or publication is authorized by this checkpoint submission.
