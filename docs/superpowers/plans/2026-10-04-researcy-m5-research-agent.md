# Researcy M5 ResearchAgent, Evaluation, and Interview Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver selected-ready-paper research directions with exact cross-paper evidence, separated fixed-corpus evaluation and a reproducible real-stack interview demonstration.

**Architecture:** One request-scoped Research LangGraph in FastAPI; reuse per-source hybrid/RRF, canonical citation resolution and provider-neutral streaming. PostgreSQL stores Research runs/sources/ideas/citations separately from Reader messages. Next.js adds compact selection and separates displayed PDF identity from active Discussion. No new service, framework or dependency.

**Tech Stack:** Existing Python 3.12/FastAPI/Pydantic/psycopg/Alembic/httpx2/LangGraph/ijson, PostgreSQL/MinIO/Qdrant/native ARM64 Ollama BGE-M3, Next.js 16/React 19/strict TypeScript/PDF.js, pytest/Vitest/Testing Library and production browser. Existing frozen lockfiles.

**Spec:** [Approved M5 child](../specs/2026-10-04-researcy-m5-research-agent-design.md), subordinate to master revision 2.4 and delivery map.

**Status:** M5 **Implemented, not Verified**. Original design/plan approved2026-10-04: “Tôi phê duyệt.” Worktree `.omp/worktrees/m5-research-agent`, branch `feat-m5-research-agent`, base `74444f3`. Owner now temporarily accepts conditional integration and authorizes M5 process shutdown/cleanup, commit/push/PR/merge to main, local-main sync and main startup/manual testing including forward migrations/processing. This approval is not passing quality or observed cutover evidence. **No additional hosted calls are authorized.** Credential/OAuth/shared-native reconfiguration and worktree/data deletion are not implied.

## Global constraints

- IDs-only request with 1–3 unique owned ready related IDs, none active. Whole selection before embedding/provider/quota; body ≤2 KiB; session/CSRF/exact Origin before parsing.
- Pin 2–4 exact owner/paper/version/profile tuples. Every search/hydration/citation follows those tuples. No previous answers or Discovery metadata as full-text evidence; no model/client filters.
- Per source: dense5 + lexical5, RRF k=60, fused5; Research takes top2/source in first/second rounds, ≤8 whole chunks and ≤24,000 normalized +24,000 raw code points. Reader five/12,000+12,000 unchanged.
- Initial + at most one citation/output repair, total ≤2. No unsupported-action repair, transport retry, third pass, extra repair retrieval, repair after queued delta or fallback.
- Only direction.delta/citation.resolved/direction.completed/direction.failed. Completion 1–3 ideas; each text field 1–1200; 1–6 proposals/idea; ≤24 resolved page-local citations/run. Insufficiency is safe failure/refusal, not zero-idea completion.
- Each factual premise has exact allowed-source support; active-only, selected-only and split-source premises legal. No decorative citations. Cross-paper acceptance must actually demonstrate split-source support and jumps. Proposal/method visibly hypotheses, not novelty/feasibility proof.
- Gemini primary: exact Google OpenAI-compatible endpoint, gemini-3.8-flash, low reasoning/schema/usage. Manual 9Router alternative between runs only; separate qualification/authorization.
- Connect5s/pass60s/run150s/lease165s; output8192 tokens/256KiB; queue16×≤16KiB, event≤256KiB; DB statements5s/locks1s. Existing memory caps. One Research run/owner, twenty reserved runs/trailing hour.
- Accepted ideas/citations commit atomically; terminal CAS winner immutable. Failed/interrupted draft has no accepted citation. Run header/URL enables GET reload, no background resumption.
- Reader ≥1024px, fixed approximately65/35 split, independent scroll, visible composer, one main,44px controls, focus/Escape/wrapping/contrast/reduced motion. Related PDF does not repin Discussion.
- New raw annotations/PDFs/prompts/quotes/screenshots/secrets stay private; historical Q0 evidence read-only. Evidence classes never conflated.
- Preserve main owner files/data/override/volumes/worktrees/private evidence/ledgers/audit branches. Latest owner authority permits M5 process cleanup, commit/push/PR/merge, local-main sync and main forward migrations/worker/startup/manual testing; record actual outcomes separately. No reset/stash/down-v/force-prune/shared-native reconfiguration or private evidence publication.
- Before code: both documents, M1 exception, M5 cost/gate/cap decisions and isolated/36-attempt scope approved. M3/M4 exceptions and twelve-attempt budget do not carry over.
- RED→GREEN, focused actual smoke, review. No wiring/mock-echo/source-wording tests; no configured repository-wide lint. Commits were initially disabled; latest conditional-integration authority now permits commit/publication. No child executes checks/runtime/publication; the controller serializes them.

## 1. Entry gate

- [x] Owner approved both documents and child §12; exact M5-only monetary amendment recorded in master revision 2.4. Primary route unchanged.
- [x] M5 prerequisite exception recorded; M1 remains Implemented. Stale current M3 rows reconciled with existing closure, no historical rewrite.
- [x] Approved child/plan linked in map: M5 Planned, owned requirement rows Designed; no passing-gate claim.
- [x] Rechecked isolated feat-m5-research-agent/base74444f3; only two draft files at entry, owner files remain outside worktree. Skills/source read, LSP unavailable.
- [x] Ignored explicit isolated env/override prepared: researcy-m5-acceptance, loopback origin127.0.0.1:3305, unique project volumes/DB/bucket/Qdrant and free ports. Credentials privately copied only; no main override/volumes or printed secrets.
- [ ] Main uses localhost3000 and may be the only registered Google callback. Preserve main. Use an already registered free isolated callback or obtain separate point-of-risk authorization to add one. Until available, synthetic HTTP checks proceed but actual sign-in G5 remains blocked; do not steal main port or restart it.
- [x] Frozen Linux Python3.12 test image and Node22.14 npm ci completed; isolated real PG/MinIO/Qdrant ready. Existing canonical/owned-conversation baseline passed. Builds/tests/native sampling serialized by controller.

**Execution checkpoint — 2026-10-04:** Code/configuration exist; M5 is `Implemented`, not `Verified`. [Actual acceptance](../reports/2026-10-04-researcy-m5-acceptance.md) and [runbook](../reports/2026-10-04-researcy-m5-interview-runbook.md) record actual security/controlled-TCP failure→recovery, all9ready frozen sources, parser/Q0 floors, repeated warm/populated startup and primary hosted/application/browser subsets. Paired retrieval2/14, actual Reader exact-copy failures, Discovery stop without recommendations, missing human ratings and genuine Google/browser journey remain unresolved. Hosted charge18/36,16settled,0uncertain/0reserved; all8Researchprimary cases now observed, but completed is not factual-quality acceptance. No automatic retry/fallback or main operation; no diagnostic substitution. Unchecked acceptance actions below must not be inferred complete from implementation or approval.

### Temporary acceptance and resume checkpoint — 2026-10-05

The owner temporarily accepts M5 **without closing acceptance gates**. Stop/clean M5 processes while preserving volumes/worktree/private corpus/ledgers/remote audit branch; conditional publication/merge/local-main sync and main forward migration/processing/startup/manual testing are authorized. Preserve the user's main `next-env.d.ts` modification and untracked web context files. Future main checks are in the [runbook checklist](../reports/2026-10-04-researcy-m5-interview-runbook.md#future-main-manual-checklist--conditional-integration); no merged-path operation or test result is claimed by this plan update.

Resume backlog, retaining all historical observations:

- Pairedfused/packed **2/14 fails required75%**. Required scientific premises exist in published chunks, but captured candidates miss them. Parser67/67, coverage5357/5357, reading12/12 and Q0fused6/8 pass stated floors; sections21/67 remain disclosed. Both bounded query spikes were rejected; no production query revision or gold/bounds/provider change was retained.
- Reader's actual rawU+FFFD deletion was rejected correctly; escaped-Unicode presentation invented U+0000 and was reverted. Keep only the proven normalized-navigation/raw-citeable separation, not fuzzy cleanup or provider-success claims.
- Discovery filename-title/no-abstract uploads selected stop before arXiv search. UI conflates this with genuine search-zero-results; recommendations/official Add are not accepted.
- R1/R8 required split-source factual support and human0/1/2 ratings remain missing. R2 safely returned insufficient evidence and must remain so. Preserve original observations and put any human ratings in a separate private overlay.
- Genuine Google callback previously failed400; owner reports a configuration fix, not acceptance of full G5 official Related→explicit Add→ready→Research. Keep owner report distinct from runtime/browser evidence.
- Verification remains mixed: backend247passed/20host-ledger `flock` failures under unchanged container seccomp, host evaluator61passed, frozen Linux frontend149passed. No all-green container or fresh main-path claim.

Campaign accounting is **18/36charged,16settled,0uncertain/0reserved**, consumption **Research8/Reader5/Discovery2/diagnostic3/demo0**. New owner manual Discovery run **`9f0c5158-fc02-4ff1-b77a-d794b06d7d65`**, request **`0043e130-e0f9-4bf2-853b-e169c838ba51`**, completed **stop/1generation/0searches/0returns outside the campaign ledger**. Reconcile before further paid invocation; do not invent allocation or revised total. Latest decision allows **no extra hosted calls**: stop before Ask/Search/Generate until new hosted permission and accounting reconciliation. Nominal unused budget does not override that decision. [Acceptance/backlog](../reports/2026-10-04-researcy-m5-acceptance.md#temporary-owner-acceptance-and-resume-backlog--2026-10-05) controls observed evidence; controller appends actual cutover results later.


## 2. Ordered tasks and file ownership

`T1 selection/persistence → T2 scoped evidence → T3 strict parser → T4 graph/API/SSE → T5 Reader UI → T6 evaluation → T7 demo startup → T8 full acceptance`.

T1–T5 share contracts and remain serial. T6/T7 can be independent after contracts freeze, without competing builds/native measurements. One integration owner controls migration, budget and evidence. New paths below are proposed, not existing implementation.

| Task | Existing files | New files |
|---|---|---|
| T1 | API ingestion/preflight.py, conversations/repository.py for narrow provenance extraction, existing schema/fixture tests | migrations/versions/0008_m5_research.py; research/{__init__,models,repository}.py; citations/persistence.py; tests/test_research_{schema,repository}.py |
| T2 | Existing hybrid/resolver/retrieval tests unchanged except actual regressions | research/evidence.py; tests/test_research_retrieval.py |
| T3 | GenerationClient reused unchanged; existing generation/Reader/Discovery tests | agents/research_parser.py; tests/test_research_output.py, test_research_parser.py; models in Research domain |
| T4 | main.py, citations/repository.py, tests/test_citations.py | agents/research.py; research/{routes,stream}.py; tests/test_research_{api,agent,stream}.py |
| T5 | Web lib/api.ts; components/reader-workspace.tsx; app/library/[paperId]/page.tsx; existing CSS/citation/Reader tests; Discussion slots only as needed | components/research-directions.tsx, research-directions-interaction.test.tsx |
| T6 | Historical corpus/gold/results READ ONLY | qualification/m5/{manifest,cases,rubric}.json; API evaluation/{__init__,m5}.py; tests/test_m5_evaluation.py |
| T7 | API main.py/health mounting, existing Compose/Settings/preflight; current setup docs after actual proof | researcy/readiness.py; tests/test_readiness.py; scripts/demo-up.sh; docs/superpowers/reports/2026-10-04-researcy-m5-interview-runbook.md |
| T8 | Approved master/map/current setup links/status only | docs/superpowers/reports/2026-10-04-researcy-m5-acceptance.md; safe M5 results |

No generic agent repository, new provider transport or UI design system. Shared citation extraction only verifies canonical raw provenance; it does not redesign Reader state.

## 3. Frozen interfaces and schema

Names below define implementation contracts, not no-op files to create.

```python
# research/models.py; imports existing ReadyDocument/ProposedCitation/ResolvedCitation/StoredCitation
@dataclass(frozen=True, slots=True)
class ResearchSource:
    ordinal: int
    document: ReadyDocument
    title: str | None
    headings: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ResearchReservation:
    run_id: UUID
    owner_id: UUID
    active_paper_id: UUID
    request_id: UUID
    sources: tuple[ResearchSource, ...]
    lease_expires_at: datetime

class ProposedIdea(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    observed_gap: str = Field(min_length=1, max_length=1200)
    proposed_direction: str = Field(min_length=1, max_length=1200)
    possible_method: str = Field(min_length=1, max_length=1200)
    premise_citations: list[ProposedCitation] = Field(min_length=1, max_length=6)

class ResearchOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    next_action: Literal['directions']
    ideas: list[ProposedIdea] = Field(max_length=3)
    refusal: str | None

# JSON-native lists deliberately match decode_output's validate_python(json.loads(...))
# under strict=True; convert accepted/pinned collections to tuples at internal boundaries.

class AcceptedIdea(BaseModel):
    observed_gap: str
    proposed_direction: str
    possible_method: str
    premise_citations: tuple[ResolvedCitation, ...]

class ResearchSourceIdentity(BaseModel):
    paper_id: UUID
    document_version: UUID

class ResearchDraft(BaseModel):
    observed_gap: str
    proposed_direction: str
    possible_method: str

class ResearchSafeError(BaseModel):
    code: str
    message: str

class ResearchSnapshot(BaseModel):
    run_id: UUID
    active_paper_id: UUID
    document_version: UUID
    sources: tuple[ResearchSourceIdentity, ...]
    state: Literal['running','completed','failed','interrupted']
    ideas: tuple[AcceptedIdea, ...]
    draft_ideas: tuple[ResearchDraft, ...]
    error: ResearchSafeError | None
    request_id: UUID

@dataclass(frozen=True, slots=True)
class ResearchEvent:
    event: str
    data: dict

RESEARCH_OUTPUT = TypeAdapter(ResearchOutput)
```

All public/output models use strict/frozen/extra-forbid configuration. Add nonblank valid-Unicode/control validators and output model validator: exactly 1–3 ideas +null refusal OR zero ideas +nonblank refusal ≤1200. Strict JSON decoder rejects duplicate keys/constants/trailing bytes. ProposedCitation shape unchanged; decoder prevents coercion before model acceptance. Snapshot validates terminal/idea/error consistency; draft never contains citations.

Repository API, with caller-owned get_conn and short transactions:

```text
load_selection(conn, owner_id:UUID, active_id:UUID, selected:tuple[UUID,...]) -> tuple[ResearchSource,...]
reserve_research(conn, owner_id:UUID, sources:tuple[ResearchSource,...], request_id:UUID) -> ResearchReservation
record_research_attempt(conn, reservation:ResearchReservation, kind:Literal['initial','repair']) -> None
finish_research(conn, reservation:ResearchReservation, ideas:tuple[AcceptedIdea,...],
    citations:tuple[StoredCitation,...], metrics:dict) -> ResearchSnapshot
fail_research(conn, reservation:ResearchReservation, code:str, interrupted:bool,
    drafts:tuple[ResearchDraft,...], metrics:dict) -> None
get_owned_research(conn, owner_id:UUID, active_id:UUID, run_id:UUID) -> ResearchSnapshot
```

Shared canonical helper:

```python
# citations/persistence.py: no network or transaction ownership
@dataclass(frozen=True, slots=True)
class CanonicalCitation:
    page_id: UUID
    evidence_quote: str
    boxes: tuple[Box, ...]
    raw_fragments: tuple[dict, ...]
# validate_stored_citation(conn, scope:DocumentScope, stored:StoredCitation) -> CanonicalCitation
```

Extract canonical page/span/offset/raw-quote/box checks from current conversations._persist_citations; Reader and Research retain their own INSERTs and source-membership checks. StoredCitation.claim_index is the idea index only in Research; no fake Reader message.

Evidence/parser/graph APIs:

```python
@dataclass(frozen=True, slots=True)
class ResearchEvidence:
    catalog: EvidenceCatalog
    documents_by_ref: dict[str, ReadyDocument]
# research/evidence.py:
# build_research_query(source:ResearchSource) -> str
# retrieve_research_evidence(sources:tuple[ResearchSource,...], *, deadline:float,
#     cancel:threading.Event) -> ResearchEvidence
# resolve_idea(conn, reservation:ResearchReservation, evidence:ResearchEvidence,
#     idea:ProposedIdea, idea_index:int) -> tuple[StoredCitation,...]
# agents/research_parser.py:
# IdeaParser.feed(fragment:bytes) -> tuple[ProposedIdea,...]
# IdeaParser.finish(output:ResearchOutput) -> None; close() -> None
# agents/research.py:
# run_research(reservation:ResearchReservation, settings:Settings, *, deadline:float)
#     -> AsyncIterator[ResearchEvent]
```

`GenerationClient.stream(output=RESEARCH_OUTPUT,schema_name='research_directions',deadline=...,on_metadata=...,on_response=...)` remains the single transport. Resolve every ref against documents_by_ref; check permitted identity and at most24 resolved citations, not forced active+selected citations for every idea.

Central browser contract in lib/api.ts:

```ts
export type ResearchIdea = {
  observed_gap: string; proposed_direction: string; possible_method: string;
  premise_citations: ResolvedCitation[];
};
export type ResearchEvent =
  | {event:'direction.delta';data:{run_id:string;request_id:string;sequence:number;idea_index:number;
      idea:Omit<ResearchIdea,'premise_citations'>}}
  | {event:'citation.resolved';data:{run_id:string;request_id:string;idea_index:number;citation:ResolvedCitation}}
  | {event:'direction.completed';data:{run_id:string;request_id:string;ideas:ResearchIdea[]}}
  | {event:'direction.failed';data:{run_id:string;request_id:string;code:string;message:string}};
// ResearchSnapshot matches the Python public snapshot above.
// streamResearchDirections(paperId:string, relatedIds:string[], onEvent:(e:ResearchEvent)=>void,
//     onReserved:(runId:string)=>void, signal:AbortSignal):Promise<void>
// getResearchDirections(paperId:string, runId:string, signal?:AbortSignal):Promise<ResearchSnapshot>
```

Actual existing browser helpers: `fetchPapers(search?)`, `fetchPaperDetail(paperId,version?)`, `getCitation`, `importArxiv`. Library currently has no pagination; reuse explicit all-owned fetch rather than introduce a pagination subsystem. Browser decoder enforces run/request identity, sequence/index/cardinality, citation geometry, terminal ordering/EOF; header callback before first delta. Restore membership from authenticated snapshot/message, never URL geometry.

## Task 1: Selection, pinned ledger and atomic canonical persistence

**Depends on:** entry approval. **Files:** T1 map. **Produces:** migration0008 and real reservation/finish/fail/GET operations.

- [ ] Read0005/0007, immutable source/page triggers, load_ready_document, owner locks and current citation persistence; inventory references before extraction. Create reusable test factory from existing real ready-source fixtures: four owned ready publications, another owner and one queued source. Deterministic vectors are controlled fixtures, not native qualification.
- [ ] RED schema/repository cases: mixed owned+foreign404; pointer race→source-changed; concurrent reservations→one active;21st/hour429; expired run→interrupted and late finish rejected; unselected citation rejected; invalid raw fragment rolls back all ideas/citations/terminal state; completed pins/results immutable.

```python
def test_unselected_citation_cannot_be_published(research_sources):
    conn, owner = research_sources['conn'], research_sources['owner_id']
    active, selected, unselected = research_sources['paper_ids'][:3]
    run = reserve_research(conn, owner, load_selection(conn, owner, active, (selected,)), uuid4())
    ideas, citations = research_sources['resolved_idea_for'](unselected)
    with pytest.raises(APIError) as failure:
        finish_research(conn, run, ideas, citations, {})
    assert failure.value.code == 'EVIDENCE_UNRESOLVED'
    assert conn.execute('SELECT state FROM research_runs WHERE owner_id=%s AND id=%s',
                        (owner,run.run_id)).fetchone() == ('running',)
    assert conn.execute('SELECT count(*) FROM research_citations WHERE owner_id=%s AND run_id=%s',
                        (owner,run.run_id)).fetchone() == (0,)
```

Fixture resolves real raw spans and returns mutually consistent AcceptedIdea/StoredCitation; this isolates run-source membership, not malformed test wiring.

- [ ] Run RED: API directory `uv run --frozen pytest tests/test_research_schema.py tests/test_research_repository.py -q` in restricted isolated environment. Fixture/env errors are not RED.
- [ ] GREEN0008 with research_runs/run_sources/ideas/citations per child§7: owner/source/idea/canonical-page composite FKs, constraints/indexes/immutable pins/terminal evidence. Existing Reader FKs unchanged; preflight head updated. No historical migration/network backfill.
- [ ] GREEN batch owner check before readiness; snapshot/recheck active pointers; DB-time quota/lease/owner-first locks; attempt before dispatch; CAS/lazy expiry/unknown accounting. Extract canonical verification and migrate Reader caller without behavior change. Research completion inserts all accepted rows in one transaction; failed drafts have text only.
- [ ] Focused new tests plus existing conversations/citation publication/schema/citation/preflight. Actual populated isolated0007→0008 twice: unchanged original/version/job/idempotency identities; reserve/attempt/interrupt/GET/late-finish rejection then valid paired publication/reload. Zero hosted calls. Review transaction/immutability/security; no unauthorized commit.

## Task 2: Selected-source RRF and exact prefixed catalog

**Depends on:** T1 sources. **Files:** T2 map. **Produces:** ResearchEvidence/resolve_idea.

- [ ] RED with at least two ready scopes: localS1 refs cannot collide; wrong owner/version/tuple hit rejected; source first-hit coverage or safe failure; deterministic RRF/top-two/round packing/budget; no rank-three backfill; valid active-only/selected-only/split-source citations; ambiguous/invented/raw-normalized quote rejected; multipage splits exact.

```python
def test_ref_binding_preserves_each_pinned_version(research_sources):
    sources = load_selection(research_sources['conn'], research_sources['owner_id'],
        research_sources['paper_ids'][0], (research_sources['paper_ids'][1],))
    evidence = retrieve_research_evidence(sources, deadline=time.monotonic()+30, cancel=Event())
    assert {entry.hit.scope for entry in evidence.catalog.values()} == {
        source.document.scope for source in sources}
    for ref, entry in evidence.catalog.items():
        assert evidence.documents_by_ref[ref].scope == entry.hit.scope
    # Add quote/page/box checks against independent canonical fixture annotations.
```

- [ ] Run RED: `uv run --frozen pytest tests/test_research_retrieval.py tests/test_hybrid_retrieval.py -q`.
- [ ] GREEN backend source title/section/fixed-term query ≤2400; serial existing per-source retrieve_same_paper, source first/second-round packing8/24k+24k, fail lost first source. This is source-balanced per-paper RRF, not globally calibrated ranks. Query may differ per source, up to four dense/embedding calls measured.

```python
catalog, documents_by_ref = {}, {}
for source, hits in packed_by_source:
    for local_ref, entry in make_evidence_catalog(tuple(hits)).items():
        ref = f'P{source.ordinal}:{local_ref}'
        catalog[ref], documents_by_ref[ref] = entry, source.document
```

- [ ] GREEN resolve each proposal with its ref's document; raw/canonical geometry unchanged. No mixed-scope catalog builder, scope relaxation or extra retrieval in repair.
- [ ] Focused owned-retrieval/provenance/citation regressions. Actual authorized isolated native A/B ready retrieval/resolution compared with independent raw annotations and exact source filters; record elapsed time and call counts. Zero hosted calls; review leakage/caps.

## Task 3: Strict output and bounded incremental ideas

**Depends on:** T1 models/T2 evidence. **Files:** T3 map. **Produces:** strict Research adapter/IdeaParser.

- [ ] RED decoder: unsupported action/scope/geometry,zero ideas+null refusal,four ideas,blank/unsafe text,duplicate keys/types/trailing bytes,contradictory refusal,oversized citations. Parser: splitUTF-8/JSON, held ideas before action/refusal, nested complete citation before idea, later envelope mismatch, cancellation/oversize closes lifecycle. Both valid key orders work.

```python
@pytest.mark.parametrize('raw', [
    b'{"next_action":"search_arxiv_metadata","ideas":[],"refusal":null}',
    b'{"next_action":"directions","ideas":[],"refusal":null}',
    b'{"next_action":"directions","ideas":[],"refusal":"No evidence","owner_id":"x"}',
])
def test_research_rejects_unsupported_or_contradictory_output(raw):
    with pytest.raises(InvalidModelOutput):
        decode_output(raw, RESEARCH_OUTPUT)
```

- [ ] Run RED: `uv run --frozen pytest tests/test_research_output.py tests/test_research_parser.py -q`.
- [ ] GREEN strict models/Unicode/envelope validators and ijson lifecycle parser. Whole-unit equality reconciled with strict final output. Existing GenerationClient remains unchanged, no Reader grammar reuse or transport copy.
- [ ] Actual local HTTP SSE through GenerationClient/parser: valid live unit before terminal and malformed/truncated/unsupported rejection, terminal usage retained on final decode failure, one physical request/pass. Supporting generation/Reader/Discovery regressions; zero hosted calls, no Gemini qualification claim. Review byte/deadline/lifecycle boundaries.

## Task 4: Complete Research graph/API/SSE/citation GET

**Depends on:** T1–T3. **Files:** T4 map. **Produces:** POST, owned run GET, accepted citation lookup and full bounded workflow.

- [ ] RED request precedence: session/CSRF/Origin before bad body; active foreign404; mixed foreign+unready404; foreign/random symmetric; owned selected-unready409; duplicate parsed UUID/active/0/4/unknown fields/query/body cap422; unconfigured503 before reservation. All rejected selections have zero provider/embedding/Qdrant calls.
- [ ] RED graph via real controlled HTTP transport and canonical DB: valid1pass; first-citation error→one pre-delta repair; invalid later idea→no repair; second failure→no third; unsupported action→no repair/tool; refusal→safe insufficiency/no accepted citations; repaired result cannot widen catalog. Research creates no paper/job/object.
- [ ] RED real socket/SSE races: abort during reservation/retrieval/pass/repair/publication/send, bounded backpressure/deadline, oversized final event before commit, interrupted winner cannot become completed, commit winner remains completed on GET, run header supports abort before first delta.

```python
async def test_later_invalid_idea_does_not_trigger_repair(research_http):
    response = await research_http.submit_controlled_stream(
        first='supported_pair', second='invented_quote')
    assert response.events[0].event == 'direction.delta'
    assert response.events[-1].event == 'direction.failed'
    snapshot = await research_http.get_run(response.run_id)
    assert snapshot.state == 'failed' and snapshot.ideas == ()
    assert research_http.provider_requests == 1
    assert await research_http.accepted_citation_count(response.run_id) == 0
```

Fixture templates contain production-resolved canonical quotes privately; labels select controlled templates, not mock-as-provider evidence.

- [ ] Run RED: `uv run --frozen pytest tests/test_research_api.py tests/test_research_agent.py tests/test_research_stream.py -q`.
- [ ] GREEN manual body loader/security then selection/config/reservation, exact OpenAPI request declaration without pre-handler body parsing. Prestream codes:422INVALID_REQUEST,404RESOURCE_NOT_FOUND,409PAPER_NOT_READY(active),409RESEARCH_SELECTION_NOT_READY(selected),409RESEARCH_SOURCE_CHANGED,409RESEARCH_RUN_ACTIVE,429RESEARCH_RATE_LIMITED+Retry-After,503GENERATION_UNCONFIGURED. Existing auth codes unchanged.
- [ ] GREEN explicit acyclic initial/repair graph; evidence-resolved whole ideas before provisional delta; strict final envelope before finish. No tool branch. Safe insufficiency code RESEARCH_INSUFFICIENT_EVIDENCE; no repaired timeout/429/EOF/unsupported action; no repair after first queued delta.
- [ ] GREEN one receive owner/direct awaited send≤16KiB/absolute deadline/cancellation Event/joined DB work; no-store/request-ID/run-ID header. Pre-encode final event≤256KiB before atomic commit; only then resolved citations/completion. Failed/interrupted persistence text/usage only; lazy expiry. Preserve durable CAS vs delivery race truth.
- [ ] GREEN citation GET Research branch requires owner/completed run/accepted idea/exact run source/page/publication; Reader branch unchanged. Collision fails closed; no approximate geometry.
- [ ] Focused new backend plus Reader/Discovery/auth/citation. Actual isolated Uvicorn and same-origin controlled POST→persisted GET/citation, invalid0dispatch/two-owner404, delta→disconnect→GET→new explicit success and commit-winning race. Safe counts/IDs/accounting; zero hosted calls. Review before UI.

## Task 5: Compact selection and cross-paper evidence navigation

**Depends on:** T4 API. **Files:** T5 map. **Produces:** real browser consumer, no change to active Discussion source.

- [ ] Read apps/web/AGENTS.md/relevant installed Next guides and React/UI/browser skills. Use actual fetchPapers/fetchPaperDetail/getCitation signatures and central SSE validator; LSP refs if available.
- [ ] RED consumer decoding: split frames/UTF-8, wrong run/citation identity, sequence/index/terminal errors, EOF, cap/abort, run header callback before delta. Do not test copied forwarding options.
- [ ] RED roles/labels: panel open fetches owned Library only; ready/nonactive1–3explicit selections; fourth disabled/no preselection/no automatic Add/generation; hypothesis labels in draft/final; error/refusal/interrupted distinct; stale selection/paper/logout/unmount/width abort; GET restore never generates.
- [ ] RED cross-paper: Research B/version citation while activeA loads exactB/title/page/boxes; Discussion/composer/conversation stillA; DownloadB; Returnactive PDF-only; Escape retainsB/page and citationfocus; reselect/remount/popstate/reload/membership/tampered tuple all safe.

```tsx
it('retains the active Discussion when opening related evidence', async () => {
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={activePaper} source={activeReader} />);
  await user.click(await screen.findByRole('button', {name:'Premise citation 2'}));
  await screen.findByRole('region', {name:/Evidence/});
  expect(screen.getByRole('heading', {name:relatedPaper.title})).toBeVisible();
  await user.keyboard('{Escape}');
  expect(screen.getByRole('button', {name:'Premise citation 2'})).toHaveFocus();
  // Submit through existing Discussion consumer and assert activeA conversation scope,
  // not the displayed B/version. Use existing interaction fixture/API setup.
});
```

- [ ] Run RED: `npm test -- src/lib/api-consumer.test.ts src/components/research-directions-interaction.test.tsx src/components/citation-interaction.test.tsx src/components/reader-interaction.test.tsx`.
- [ ] GREEN central Research types/strict stream helper/header callback/GET and safe error mappings; ResearchDirections uses checkbox/controller/state/runURL. Existing all-owned Library fetch on explicit open only, no polling fanout; owned unready disabled with existing preparation link. Submit freezes selection; new selection after cancel is new request.
- [ ] GREEN ReaderWorkspace activeSource vs displayedSource; authoritative citation+message/run membership then fetchPaperDetail exact version. document_version/conversation stay active; pdf_paper/pdf_version/page/citation/research_run for evidence. Restore owned plain PDF hints without generation; failed source removes stale overlay. Evidence under originating idea, shared renderer/card/focus, no modal fork.
- [ ] GREEN header/download identify shown PDF, Returnactive explicit; Discussion and Related remain original active source.401clears private state,≤1023mounts no hidden actions. Existing M4 Add/idempotency unchanged. Remove obsolete incidental absence/wording tests, not re-pin.
- [ ] Focused frontend tests; actual production controlled-HTTP browser at approved widths/states: keyboard/1main/overflow/focus/hypotheses/exact B PDF/reload. Fresh AX/screenshots and server-backed result GET; close tab. Controlled provider not hosted quality/sign-in. Review actual surface.

## Task 6: Freeze gold and implement separate metric evaluator

**Depends on:** T2/T4 contracts. **Files:** T6 map. **Produces:** frozen M5manifest/cases/rubric and reproducible evaluation, no paid calls yet.

- [ ] Preserve Q0 file hashes/two originals/eight answerable/two unanswerable/12order relations. Matching public bytes privately; changed edition gets separately named gold. Supplement missing geometry only in new M5 annotation.
- [ ] Inspect extension candidates2202.09741/2105.02358 locally; suitable four-source minimum for active+three. Up to two layout-only papers if needed. Record actual one/two-column, table/caption/figure/alternative layout from original PDFs, not IDs. Annotate premise support/raw offsets/page/boxes independently; new text/PDFs private.
- [ ] Freeze R1–R8 and hashes before generated output; active-only/selected-only/split-source/insufficient/hypothesis/hostile/subsequent-valid coverage. Controlled negative/hostile inputs labelled; hostile PDF is newly processed, never edits sealed owner data. Gold used after ranking, not in query/prompt.
- [ ] RED scoring: wrong hash/version refuses scoring; right-page/wrong-box fails exact citation; unselected-source fails; unsupported assertion cannot pass merely labelled hypothesis; partialusage never becomes complete zero; missing case retained denominator.

```python
def test_missing_case_prevents_campaign_acceptance(frozen_m5_cases):
    result = score_campaign(frozen_m5_cases['manifest'],
                            frozen_m5_cases['observations_without_R4'])
    assert result['research']['expected_cases'] == 8
    assert result['research']['missing_case_ids'] == ['R4']
    assert result['accepted'] is False
```

- [ ] Run RED: `uv run --frozen pytest tests/test_m5_evaluation.py -q`.
- [ ] GREEN `python -m researcy.evaluation.m5 --manifest qualification/m5/manifest.json --observations <private-path> --output <safe-path>` verifies hashes/case coverage and produces separate parser/retrieval/citation/Reader/Discovery/Research/route/product/cost objects, with exact numerators/denominators and missing cases. Human support0/1/2/abstention annotations explicit, no paid LLM judge.
- [ ] GREEN explicit `--run --attempt-budget 36` mode uses application endpoints and a private process-environment session, serial conservative attempt ledger and remaining-slot guard. No direct SDK calls/automatic retries. Per child budget allocations; observation files private, safe result text-free. Hypotheses assessed for labeling/motivation, not truth/novelty.
- [ ] Local parse/native retrieval/citation and controlled-negative scoring smoke,0hosted; safe output audit and independent gold/metric review. Fresh productionFTS≥6/8 proposed floor distinguished from historicalBM25, paired sourceRecall@5≥75%; frozen failures retained. Paid evaluation onlyT8.

## Task 7: Single isolated demo entrypoint and actual runbook

**Depends on:** reviewed schema/API and approved isolated operations. **Files:** T7 map. **Produces:** working startup and read-only `/ready` in the existing API, no new service.

- [ ] Demonstrate RED through a throwaway local scenario: API health200 but wrong migration/native mismatch/private object probe failure or only configured generation must not report full readiness. This is actual operational behavior, not a permanent test of shell command order/source text.
- [ ] RED dependency readiness tests: disconnected DB/wrong revision, inaccessible private bucket, absent/wrong Qdrant schema, native identity mismatch, catalog denied or malformed/timeout all yield safe503; configured-only generation cannot be labelled executed/qualified. Run `uv run --frozen pytest tests/test_readiness.py -q`.
- [ ] GREEN `readiness.py` implements bounded read-only dependency checks with one ≤15s deadline, mounted GET/ready; no owner data, secrets, model loading, collection creation, object writes or paid generation. Safe per-dependency states/request_id,503failure/unconfigured and200successful dependencies/catalog access; always explicit generation_execution=unverified. Authorized catalog GET uses validated configured provider route, bounded body and safe error. No cached historical provider success becomes a fresh claim. Exercise both actual success and controlled failed dependency via HTTP.
- [ ] GREEN scripts/demo-up.sh requires envfile/override/project; rejects ownerproject researcy/mainprivateoverride. Every Compose operation same explicit prefix. Privately validate Settings, build frozen images, start PostgreSQL/MinIO and wait before init, start Qdrant, migrate twice before worker, native preflight/warm, start API/web/isolatedworker. No paid ping/import/seed/model pull or switch.

```bash
# Planned command, after approval:
bash scripts/demo-up.sh --project researcy-m5-acceptance \
  --env-file .omp/runtime/m5-acceptance.env \
  --override .omp/runtime/m5-acceptance.private.yaml
bash -n scripts/demo-up.sh
```

- [ ] GREEN print separate liveness/DBrevision/private-object-probe/Qdrant/native digest+warm/generation configuration+access+qualification statuses. Preflight storage writes/deletes a probe and Qdrant may ensure schema: isolated approved side effects, not read-only main check. Configuration/catalog alone prints qualification pending; T8first approved application call supplies fresh qualification, no extra paid probe.
- [ ] Actual isolated startup twice with populated sources, migration/preflight/warm and production web. Observe cold loading only on a naturally unloaded or separately approved isolated native instance; never unload/reconfigure the shared main model to manufacture a cold sample. Inject one controlled readiness failure, restore and rerun; no owner/shared-service stop. Failure preserves volumes/no destructive rollback. Record actual dependency outcomes.
- [ ] Runbook written after proof: exact versions/limits/ports/callback/sourcehashes/project/override, cold/warm commands, real Google owner step, Reader→Related→Add→ready→selection→directions→current/related jumps, cooldown/interruption/retry/replay labels and shutdown without-v. No cached/fixture replay presented live. Review readiness honesty.

## Task 8: Hosted qualification, full browser journey and gate reconciliation

**Depends on:** T1–T7 and explicit hosted/runtime approvals. **Files:** T8 map. **Produces:** actual evidence/status only.

Planned package commands (not executed evidence):

```bash
# API in restricted Linux environment with isolated PG/MinIO:
uv sync --frozen
uv run --frozen pytest tests -q
# Web, Node22.14:
npm ci
npm test -- --maxWorkers=1
npm run build
# Isolated worktree root:
docker compose --env-file .omp/runtime/m5-acceptance.env -p researcy-m5-acceptance \
  -f compose.yaml -f .omp/runtime/m5-acceptance.private.yaml \
  --profile web --profile processing build api web worker
```

Same project/env/override required for every up/run/exec/down; startup ordered by script. Opt-in ARXIV_REAL_NETWORK test separate, never ordinary deterministic coverage. Main operations outside this plan; any later authorized main command retains main ignored override and original volumes.

- [ ] G7full affected backend/frontend and API/web/worker production build, migration twice populated0007 with exact existing source/job/replay identities unchanged. Record actual commands/images/versions/counts/skips, no lint claim. Tests do not replace changed-path smoke.
- [x] G1actual same-origin syntheticA/B security and whole invalid-selection/quota/active/expiry checks, zero external calls; retain M1 OAuth gap. Evidence: actual invalid HTTP0reservations, controlled TCP20/21st quota/concurrent409/expiry→interrupted/no late publication/subsequent success; see acceptance.
- [ ] G2real native/PG/Qdrant/MinIO tuple-scoped retrieval/persist/reload/citationGET, independently annotated raw/page/boxes; wrong/unselected/foreign/ambiguous/unresolvable/page-only faults isolated.
- [ ] G3serial primary campaign≤36: Research8cases≤16, Reader3runs≤6, Discovery2runs≤4, fulljourney≤6, named diagnostics≤4. Guard/reserve before dispatch including uncertain sends; record physical-response uncertainty separately. Optional alternative requires new permission, no budget inheritance.
- [ ] Actual Research supported/refusal/hostile/subsequent-valid through application graph; human review every factual assertion. Pre-delta repair/exhaustion/post-delta refusal of repair controlled localHTTP separately; natural repair only if actually observed. No manufactured Gemini corruption.
- [x] G4controlled provider503/429/stalls/EOF/invalidschema plus actual disconnect: bounded cleanup/no late work/third pass/fallback, persisted CAS winner/draft/no failed citations, slot released, explicit subsequent request successful. Evidence: six genuine TCP fault→valid pairs, unchanged deadlines, canonical reload plus controlled schema/repair/post-delta/CAS suite; not hosted fault fabrication.
- [ ] G5owner real Google on approved isolated origin; observed callback/session only when available, attribute owner-only steps. Actual public Reader→explicit Related→explicit Add of genuinely relevant unowned returned result→real processing ready→returnactive→select1–3→Research→exact both-source jumps. No fixed invented recommendation/processing fixture substitute; exact blocker if upstream/auth/provider prevents journey.
- [ ] Production browser1024/1280/1440 and375/768/1023boundary; all states with controlled labels, keyboardcheckbox/submit/citation/Escape/returnactive, visible exactbox/zoom/crop/rotation, unchanged Discussion/composer, reload/popstate/tampering/stale response,1main/44px/nooverflow/contrast/reducedmotion. Fresh private screenshot/AXproof; close managed tabs.
- [ ] G6fixed fullcase metric report, hash/denominator/route/configured-vs-echoed provenance, actual calls/usage completeness/latency, public tariff/date plus authoritative mapping or approvedM5nullreason. Unknown never zero/free; no account access. Resource point samples/cold-warm/shared pressure disclosed, no renewedM2capacity claim.
- [ ] Actual demo cold/warm entrypoint and one readiness recovery; generation-qualified evidence linked to approved applicationrun, not health/catalog. Owner manual acceptance kept separate from agent/browser/tests.
- [ ] Final targeted review scope/quotas/canonical evidence/parser/cancellation/PDF-vs-Discussion/budget/privacy. Reproduce valid findings, focused regression and actual changed-path smoke after fix; affected full suites/build after integration. No unrelated refactor.
- [ ] After smoke update safe acceptance/runbook/current setup docs, remove only newly owned throwaways/private harnesses safely; preserve volumes/owner/audit artifacts. Commit/publication/main cutover still need new approval.
- [ ] Map status by evidence: approved→Designed/Planned; complete code without allG1–G7→Implemented; all approved gates recorded→Verified. Missing/failed gate keeps prior state/blocker. No M1promotion/Q0rewrite.

### Safe evidence row

```text
case_id / gate / evidence_class / environment / source+annotation hashes
actual command/journey / expected -> observed / safe request+run IDs
configured route/model and echoed identity provenance, no credential
pinned source identities/private aliases, source refs/count trace
initial/repair attempts vs observed responses/uncertainty, no hidden retries
header/first validated delta/terminal latency, per-pass usage/completeness
estimate+currency/tariff/mapping/date OR approved null+reason
premise support/source/page/box/hypothesis/scope verdicts
failures/missing cases/limits/status; no prompts/text/cookies/object keys
```

## 4. Coverage and handoff

| Child sections | Tasks | Gates |
|---|---|---|
| §§1–3authority/prerequisites/minimaldesign | Entry/T8 | approval/history preservation |
| §4selection/pins/GET/SSE | T1/T4/T5 | G1/G2/G4/G5 |
| §5selectedRRF/rawcatalog/premises | T2/T4 | G2/G3/G6 |
| §6strictoutput/units/two-pass/abort | T3/T4/T5 | G3/G4/G5 |
| §7schema/quota/CAS/citationGET | T1/T4 | G1/G2/G4/G7 |
| §8selection/hypotheses/PDFnavigation/a11y | T5/T8 | G5 |
| §9corpus/separate metrics/rubric | T6/T8 | G6 |
| §10route/cost/36attempts/startup | Entry/T6/T7/T8 | G3/G6 |
| §§11–12gates/evidence/status/decisions | all/T8 | G1–G7 |

Self-review: mixed-scope catalogs forbidden; local balanced RRF not global; exact source/page FKs; no forced decorative citations; unsupported action never repairs into a tool; no post-delta repair/failed accepted evidence; early run ID/durable commit race; active Discussion separate from displayed PDF; isolated callback cannot steal main; negative gold independently justified; known tariff vs unknown account mapping; FTS vs historicalBM25 caveat;36attempt allocation/unknown usage; health not generation; no inherited main/publication permission.

**Execution handoff:** Owner approved both documents and child§12 on2026-10-04. Initial isolated approval did not authorize publication/main cutover; the2026-10-05 temporary-acceptance checkpoint above now authorizes those operations without changing failed gates or permitting more hosted calls. Controller records actual integration/startup/manual-test outcomes separately. Approval is not runtime evidence; M5 stays Implemented, not Verified.
