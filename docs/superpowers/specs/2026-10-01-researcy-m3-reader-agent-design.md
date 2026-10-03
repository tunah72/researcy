# Researcy M3 — ReaderAgent and Evidence-Linked PDF Reader

**Status:** Approved child specification — owner approved specification and implementation plan on 2026-10-01. Approval is not implementation or qualification evidence.
**Date:** 2026-10-01
**Authority:** [Master revision 2.0](./2026-09-18-researcy-system-design.md), especially §§6, 9–10, 12–19 and 21; [delivery map](./2026-09-18-researcy-delivery-map.md) controls current status.
**Predecessors:** [M2 approved design](./2026-09-27-researcy-m2-durable-processing-design.md), [plan](../plans/2026-09-27-researcy-m2-durable-processing.md), [acceptance](../reports/2026-09-27-researcy-m2-acceptance.md).
**Companion approved plan:** [Implementation plan](../plans/2026-10-01-researcy-m3-reader-agent.md).

## 1. Outcome and approval boundary

A user opens the original immutable PDF of a ready Library paper, reads/navigates/downloads it, asks an active-paper question, receives a streamed grounded answer or refusal, and activates a citation once to reach its exact original-PDF passage, boxes and inline evidence card. This is the complete M3 deliverable, not PDF-only delivery.

M3 owns RET-01, GEN-01, CIT-01, AGENT-01 and UX-02. Implement reading first, then conversations/retrieval/generation/citations. DiscoveryAgent, ResearchAgent, discovery controls and research-direction workflows remain M4/M5; do not introduce fake or disabled future controls as if implemented. No broker, agent service, reranker, agent memory, OCR, automatic import or provider fallback.

This draft changes neither master nor delivery status. Owner approval of specification and plan is required before implementation. Do not migrate/start workers on owner data, publish, push, merge or prune without corresponding authorization. M2's M1 prerequisite exception does not promote M1 or automatically establish a new M3 exception; owner approval must explicitly permit M3 to proceed while the M1 detailed gate record remains outstanding.

## 2. Observed baseline and gap analysis

Inspection was read-only on `main`, commit `cca8a9d` (PR #2 merge). `git status --short --branch`, `git worktree list`, `git log -3 --oneline` confirmed the base. Preserve root modified `apps/web/next-env.d.ts` and untracked `apps/web/AGENTS.md`/`CLAUDE.md`, plus all existing worktrees. No reset/stash/removal was performed.

| Area | Implementation actually found | M3 gap |
|---|---|---|
| Authentication | `auth/sessions.py`; paper/job routes use opaque sessions, CSRF and Origin | Apply same boundary to every new resource/mutation and streaming request |
| Original bytes | `papers/objects.py:88–105,157–169`: owner/paper/version SQL lookup, 64-KiB private MinIO iterator | No HTTP PDF read/download endpoint; no Range/HEAD contract or browser reader |
| Ready source | `retrieval/repository.py:42–176`: owned active version, job/profile/publication/manifest checks before external calls | Freeze this scope once for a conversation/run; distinguish unready from insufficient evidence |
| Dense retrieval | `search_owned(owner_id, paper_id, query, limit=5) -> list[EvidenceHit]`; server filters and PostgreSQL rehydration | No production lexical retrieval, RRF or packed conversation context |
| Provenance | `documents/provenance.py:51–119`: `resolve_range(conn, scope, chunk_id, start, end)`; exact raw fragments and character boxes | No model quote validation, persisted answer citations or citation HTTP route |
| Relational state | Migrations through `0004_m2_safe_counters`; canonical chunks/pages/spans, mappings, publications | No conversations/messages/answer-run/citation tables or FTS index found |
| API inventory | `main.py` registers auth/papers/jobs; paper routes list/detail/upload/arXiv | Master conversation/message/citation routes are specified, not implemented despite historical wording “existing route” |
| Web | `library-list.tsx` links `/library/{paperId}`; detail page presents metadata/preparation and reading unavailable | No Reader/PDF.js/conversation/stream/citation implementation |
| Proxy | `next.config.ts` same-origin API/auth rewrites; arXiv-specific bounded JSON Route Handler | Binary Range and SSE cancellation/flush/header behavior not yet exercised |
| Product generation | No GenerationClient, LangGraph integration or generation Settings found in production application | Add actual 9Router route, strict action validation, bounded graph and real qualification |

Evidence: application filename inventory and route/schema/dependency literal search, controller reads and two independent read-only API/web research slices. The descriptive `find` tool failed all judgments due to provider account rejection; this was reported and replaced with filename inventory/literal searches and source reads. Tool failure is not absence evidence.

### 2.1 Runtime observations, not M3 gate results

- `docker compose ps -a`: root API/web/PostgreSQL/MinIO stopped; `docker ps --format ...`: no running containers at inspection. No stack started and no owner database queried.
- Docker engine `29.4.1`; Node `v25.8.1`, npm `11.11.0`, uv `0.11.0`. Host Node differs from repository prerequisite Node `22.14`; use reproducible container builds or the prescribed runtime during execution, not an unrecorded host substitution.
- Ollama `/api/version`: `0.18.2`; `/api/ps`: no loaded models. `/api/tags` confirms `bge-m3:567m`, F16, digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`. This is metadata presence, not embedding/container-connectivity preflight.
- A GET health probe at `127.0.0.1:20128` failed to connect. That candidate address is not established as current gateway configuration; this does not prove 9Router is unavailable at every address. Listener inventory did not identify a gateway. Application Settings/.env.example contain no product-generation endpoint. Actual endpoint, credential availability, route permissions, usage metadata and pricing source remain execution prerequisites. Do not read/print secrets or change shared tooling settings to infer them.
- M2 report's 516 backend passes / one opt-in skip, 67 frontend passes and builds are historical handoff evidence, not rerun or M3 verification. M2 `Verified`; M1 `Implemented`; M3 `Not started` per delivery map. Q0/Q0.1 remain immutable historical evidence.

## 3. Decisions and alternatives requiring approval

| Concern | Proposed decision | Alternative / reason not selected |
|---|---|---|
| Architecture | Existing FastAPI modular monolith, one in-process bounded LangGraph; existing worker only for documents | Separate agent service/broker adds no required capability |
| PDF transport | Authenticated version-specific same-origin GET/HEAD; bounded single HTTP byte Range | Public/presigned MinIO URLs violate source/privacy boundary; full-PDF buffering wastes memory |
| UI | Reuse `/library/{paperId}` as Reader when ready; preserve preparation/retry when unready | Second metadata destination duplicates navigation/state |
| Width | Reader supported at CSS viewport width ≥1024px; fixed 65/35 PDF/Discussion split, collapsible outline | Mobile PDF/chat product and draggable splitter are outside master baseline |
| Conversation version | Pin conversation to immutable ready document version at creation | Silently rebinding messages/citations to future versions breaks provenance |
| Lexical | PostgreSQL `simple` FTS, `websearch_to_tsquery`, `ts_rank_cd`, RRF k=60, dense top five + lexical top five, fused top five | Q0 BM25 is historical, not a production PostgreSQL BM25 promise; no extension or reranker |
| Streaming | Provider structured stream; emit complete evidence-validated claim units as `answer.delta`, never raw JSON or unchecked tokens | Raw passthrough exposes invalid claims; full-response buffering delays all visible progress |
| Run budget | One initial generation plus at most one search-follow-up OR validation repair; no third pass | Independent search + repair budgets violate master cap |
| Evaluation | Actual route/stack/browser, with failures retained and safe per-run measurements | Mocks/Q0/demo-only app cannot satisfy M3 gates |

Streaming choice trades token-level immediacy for claim-level correctness. Final schema validation still gates completed status; emitted units are visibly provisional until completion. This is not a promise of a token on every provider chunk. No artificial delays, timed replay or buffered-token animation may be used as evidence of live streaming. If the configured provider cannot support this stream contract, record a blocker; do not silently replace it with full-buffer display and call the gate passed.

## 4. PDF delivery contract

New local-detail route, not a change to master conversation routes:

`GET|HEAD /api/papers/{paper_id}/versions/{document_version}/pdf?download=1`

`download` is absent for inline and `1` for attachment; no arbitrary filename, object key, owner or URL accepted. Authenticate before storage access; resolve the exact composite owner/paper/version in PostgreSQL. Foreign/nonexistent paper or version returns identical `404 RESOURCE_NOT_FOUND`. An owned unready version returns `409 PAPER_NOT_READY` before object access. Retain existing metadata/preparation route for that state. No generation is triggered by opening/downloading.

Read original object metadata before committing response headers; verify stored length agrees with immutable version byte count and supported cap. The original is immutable and M2 verified its hash; do not hash the whole PDF on each Range request. ETag derives from original SHA-256. Do not expose object keys, MinIO headers, storage credentials or object URLs.

- `200` full original, `206` satisfiable single range (`bytes=start-end`, `start-`, `-suffix`), exact Content-Length/Content-Range and `Accept-Ranges: bytes`.
- Invalid, zero-suffix, multi-range or unsatisfiable Range: `416`, `Content-Range: bytes */{length}`, safe request-ID JSON envelope after authorization. No multipart implementation.
- Clamp valid end to object length; reject numeric overflow/overlong header before parsing. Limit Range header to 256 bytes.
- If-Range matching strong ETag honors Range; mismatch returns full `200`. HEAD mirrors selected status/headers without body. Conditional `304` is unnecessary with no-store and is not introduced.
- `Content-Type: application/pdf`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, sanitized server filename `paper.pdf` and inline/attachment Content-Disposition. Errors remain JSON.
- At most 64-KiB reads, original total ≤ configured upload cap (currently 25 MiB), 30-second request wall deadline, 8 concurrent PDF streams per API process, released on completion/disconnect/error; safe `503` when capacity unavailable. No accumulating entire original in API/web memory. Blocking MinIO/psycopg access uses existing threadpool conventions; release DB before streaming.
- Midstream storage failure after headers closes the stream; cannot replace already-sent PDF bytes with JSON. Browser displays safe load failure/retry; logs use safe code/request ID only. Re-authenticate each new Range; revocation prevents subsequent requests, but cannot retract bytes already delivered.

Use existing Next rewrites first. Actual production-browser/network smoke must prove forwarding of cookies, Range/If-Range, binary status/headers, no cross-user cache and incremental body delivery. Add a narrowly scoped streaming Route Handler only if that experiment demonstrates a rewrite limitation; it forwards only needed headers, propagates cancellation and never owns authorization. Do not modify the arXiv JSON proxy to serve PDFs.

## 5. Reader UX and geometry

Ready `/library/{paperId}` opens Reader; unready stays honest preparation with Discussion unavailable. Top bar: Back, paper title, Download. PDF occupies approximately 65% of workspace; Discussion approximately 35%, separate vertical scroll containers and visible non-overlapping composer. Outline collapses; built-in PDF bookmarks from `getOutline()` when present, otherwise canonical section headings only when their exact source page is known. Empty outline is explicit, not invented. Handle named/explicit PDF destinations without executing PDF actions, JavaScript or external embedded attachments.

Use directly pinned `pdfjs-dist`, locally bundled worker of the same version, canvas plus selectable text layer and accessible page controls. No CDN worker/font request, PDF JavaScript, XFA or auto-followed embedded external URL. Render visible page and adjacent pages only, cancel stale render tasks and release canvases/workers on navigation/logout. Fit-width default, bounded zoom controls, previous/next and labelled page input. Page count/rotation/crop must come from the opened original and match canonical version metadata. A mismatch is unavailable evidence, not a correction by guess.

At <1024px show explicit larger-screen requirement plus Back/Download; do not render a crushed split or issue hidden model/conversation mutations. Library/auth remain responsive. Test 375/768/1023 boundary and 1024/1280/1440 supported widths, long titles and technical tokens. Retain existing Crimson Pro/Atkinson, warm paper/ink, navy actions/focus and restrained ochre evidence, no emoji icons/AI gradients.

Geometry invariants:

- Canonical pages and raw boxes: zero-based `page_index`, unrotated PDF user space, bottom-left origin, original MediaBox/CropBox offsets and rotation retained. Python offsets are zero-based half-open Unicode code points, not JavaScript UTF-16.
- Public citation `page` and URL page are one-based physical page numbers; PDF.js `getPage(page)` uses that value. Display PDF page label separately if present. Convert exactly once at boundary. M2 gold index 3 is physical page 4; do not rewrite Q0 annotations.
- Each box is `[x0,y0,x1,y1]` in canonical PDF space. Transform all four corners using the exact PDF.js viewport for original page rotation plus user rotation, scale and crop; calculate overlay viewport bounds from those transformed corners. No `height-y` shortcut, fuzzy PDF text search, whole-page/block approximation or annotation-envelope inflation.
- Keep exact boxes authoritative; any merged display outline must not add source area. Browser overlays are derived, never persisted as viewport pixels. Exercise 0/90/180/270 degrees, nonzero crop/media origins, zoom and high-DPI scaling against original bytes.

## 6. Conversations, runs and persistence

Forward migration `0005_m3_reader` leaves existing originals/profiles/jobs/mappings/publications untouched. New tables use composite owner/paper/version constraints:

- `conversations`: id, owner_id, paper_id, document_version, created_at, updated_at.
- `messages`: id, owner/conversation/source identity, sequence, role user/assistant, full text, state `running|completed|refused|failed|interrupted`, safe error code, request ID and timestamps. User text is persisted exactly. Assistant completed text is only accepted validated claims or refusal.
- `reader_runs`: id, owner/conversation, user_message_id/assistant_message_id, state, lease deadline, actual generation-call count, validated action, usage/cost measurement fields, timing and validation outcome. A partial unique index permits one running run per conversation; no DB transaction spans network work.
- `citations`: id, owner/conversation/assistant/source identity, source_ref, verbatim evidence_quote, one-based page, exact boxes and raw fragment offsets, section metadata and provisional/accepted state. Never persist model geometry. Only accepted completed-message citations can be fetched via public citation GET.
- Per-owner persistent request quota rows; apply existing DB reservation style, 20 accepted message runs per rolling hour, one active generation run per owner. Duplicates do not charge or start another run.

API details, supplementing master §15:

- `GET /api/papers/{paperId}/conversations?before=...`: newest first, 20 records, owner-scoped pagination, pinned document_version and last message summary; no document text in list.
- `POST /api/papers/{paperId}/conversations`: empty JSON body after session/CSRF/Origin/ownership/ready checks; `201 {conversation,request_id}`. Pin active ready version server-side.
- `GET /api/conversations/{conversationId}/messages?after=...`: additional owner-scoped read needed for reload/interruption; 50 chronological messages per page, includes persisted run state and accepted citations. No provider diagnostics.
- `POST /api/conversations/{conversationId}/messages:stream`: `{client_message_id: UUID, question: string}` only, unknown fields forbidden. Question 1–2400 code points after nonblank validation, request body ≤16 KiB. Authenticate, CSRF/Origin, ownership and pinned-version readiness before body parsing/reserving quota/network. A new client message UUID represents an explicit user submission; duplicate same UUID/bytes returns persisted state without re-generation; changed question with same UUID returns `409 MESSAGE_CONFLICT`. Explicit retry uses new UUID, never reconnect/retry automatically.
- `GET /api/citations/{citationId}` returns accepted resolved citation plus request_id after owner/completed-message/version checks. Foreign/random/provisional IDs are indistinguishable 404.

Concurrency: reserve run/messages/quota in one short transaction. Running lease lasts at most run deadline plus 15 seconds; request cancellation marks interrupted and removes active reservation in a short transaction. If API dies, subsequent owned read/reservation lazily terminalizes expired runs as interrupted; no scheduler/broker/background model resumption. Compare run state under lock so completion cannot overwrite interruption and duplicate clients cannot start extra calls.

Bound conversation input to last 6 completed user/assistant turns, newest whole turns fitting 8,000 code points, preserving chronological order. Exclude failed/interrupted assistant text and never treat past answers as evidence. Raw current question remains separate. No generated memory summary or extra summarization pass. Display full persisted history through pagination.

## 7. Same-paper hybrid retrieval and context

Resolve authenticated pinned ready source/profile/publication once before retrieval, then carry immutable server scope throughout initial query, optional extra search, hydration and citations. Extract current `search_owned` authorization/publication logic into the shared ready-scope boundary rather than implement a weaker duplicate; migrate all internal callers cleanly. Existing M2 integrity behavior remains tested. Lexical and dense may not disagree about source version.

Add generated FTS vector `to_tsvector('simple', text)` and ordinary GIN index on that vector; keep existing relational owner/paper/version B-tree scoping. No UUID multicolumn GIN requiring an unapproved extension. Apply owner/paper/version/profile constraints before lexical ranking; parse query with `websearch_to_tsquery('simple', query)` and parameters. Empty lexemes produce empty lexical results, not SQL errors. Rank by `ts_rank_cd` descending then chunk UUID for stable ties.

Dense preserves native qualified embedding identity, server-built owner/paper/version filters, published collection validation and PostgreSQL rehydration; never trust Qdrant text. Fetch top five from each branch, union by chunk UUID, score `sum(1/(60+rank))` with ranks starting at 1, deterministic UUID tie break. Pack fused top five as whole chunks within 12,000 normalized code points plus ≤12,000 source-quote code points; headings are metadata, not unmapped evidence. Do not silently truncate chunks or add a reranker. Current question is retrieval query; bounded prior turns accompany it as generation context and support model's one optional follow-up query.

Empty/inconsistent source or dependency outage is not evidence that a scientific answer is false. Distinguish safe dependency failure from genuinely insufficient support. No raw-score universal refusal threshold from the tiny Q0 corpus. Require grounded claim output and exact citations, then manually measure answer support separately; geometry validation does not prove semantic entailment.

## 8. Generation, graph and claim streaming

Retain `ag/gemini-3.8-flash-low` through actual local 9Router. Add Settings for endpoint/key, fixed route, generation limits and optional documented tariff; API owns credentials, worker does not load generation credentials. No development-agent route, silent model switch, automatic fallback or SDK retry. Use existing HTTP dependency for GenerationClient, separate from EmbeddingClient. Pin LangGraph and `ijson` only for this required streamed structured-output boundary; use its supported Python backend rather than introduce an unnecessary native build dependency. No second agent framework.

Strict Pydantic discriminated output, unknown fields forbidden:

```json
{"next_action":"search_same_paper","query":"bounded query"}
```

or

```json
{"next_action":"answer","claims":[{"text":"One supported claim.","citations":[{"source_ref":"server-supplied ref","evidence_quote":"verbatim supplied raw excerpt"}]}],"refusal":null}
```

A refusal uses `claims: []` and a nonempty safe refusal explanation; no citations. A supported answer uses 1–12 claims, each 1–2000 code points and 1–4 citations; no contradictory refusal. Quote length 1–2000 code points, total citations ≤24; search query 1–2400 code points. Model supplies neither owner/paper/version/page/boxes nor authoritative filters. Evidence refs are assigned from packed canonical sources, not arbitrary model IDs.

Graph: authorized context → hybrid retrieval → initial generation → strict action validation → answer validation OR one same-paper search → follow-up answer validation → complete/refuse/fail. Search executes only after the entire initial action object validates. Follow-up schema allows answer only. The second pass can instead repair an invalid citation/output from the answer branch before any deltas have been emitted. If initial search consumed the second slot, no repair remains. Malformed/unsupported next action immediately fails without tool execution; do not repair a malicious action into a tool. No tool starts from a partial JSON object.

Provider stream is parsed incrementally with a bounded parser. As a complete claim object arrives, validate its shape and every citation against the supplied server evidence; emit only that evidence-resolved claim as a delta. Accumulate complete output for final strict schema/duplicate-key/trailing-data validation. If action arrives after claims, hold bounded pending claims until action is known. Refusal text is emitted only after final refusal validation. Never execute tool/action from incremental parsing.

Once the first answer delta is emitted, no new generation/repair/replay: a later invalid claim, envelope, timeout or disconnect fails/interrupts the run, previous deltas remain marked provisional and are not persisted as a completed answer. Withhold citation.resolved events until final validation and accepted citation/message transaction; this prevents provisional source links being mistaken for an accepted answer. Failed draft can be collapsed but may not be relabelled completed. Persist partial assistant text with failed/interrupted state for honest reload, excluded from future grounding.

Proposed bounds: provider output ≤8,192 tokens and decoded stream ≤256 KiB; connect deadline 5 seconds, provider pass total 60 seconds, total Reader run 150 seconds including retrieval; DB statement/lock limits reuse existing 5s/1s short-transaction boundary. Record actual latency rather than assert an invented performance SLO. Cancel provider and parsing on browser disconnect/deadline. Bounded queue/backpressure ≤16 pending transport chunks of ≤16 KiB; an SSE event may span chunks and is bounded to 256 KiB, including citation boxes. Client decoding handles split UTF-8 and split SSE records. Oversize evidence events fail safely, never truncate boxes. No unbounded task spawning.

SSE UTF-8, `Cache-Control: no-store`, disabled proxy buffering where applicable; fetch POST with AbortController, not browser EventSource:

| Event | Data contract |
|---|---|
| `answer.delta` | `{run_id,message_id,sequence,text,request_id}`; provisional validated claim text, monotonic sequence |
| `citation.resolved` | `{run_id,message_id,citation,request_id}`; accepted persisted exact citation |
| `answer.completed` | `{run_id,message_id,state:"completed"|"refused",citations:[...],request_id}`; emitted only after DB commit |
| `answer.failed` | `{run_id,message_id,code,message,request_id}`; safe terminal failure |

Exactly one terminal event if transport remains writable. Disconnect can have no terminal event; reload uses persisted interrupted state. Heartbeat comments may keep connection alive but are not answer deltas. Prestream auth/input/ready/quota failures use ordinary JSON/status envelopes. An EOF without terminal completion is interrupted, not successful. Never send token usage/provider/model names to reader UI.

## 9. Citation resolution and interaction

Each model citation ref must exist in that run's packed evidence. Build a server-held evidence catalog from normalized chunk intervals AND raw `resolve_range` fragments; provide model actual raw excerpts alongside normalized retrieval text. Do not request verbatim quotes exclusively from dehyphenated/ligature-expanded text.

Match quote only against supplied raw source characters, with recorded line-ending/whitespace equivalence when mapping preserves all original characters. No case folding, accent removal, fuzzy search, invented separators or semantic rewrite. Map unique raw match back to exact code-point chunk interval, call existing `resolve_range`, compare reconstructed original characters/offsets and boxes. Ambiguity or partial ligature mapping is unresolved. An optional server catalog ref can identify an exact raw fragment/interval to disambiguate repeated text; it grants no new source scope.

Persist raw fragment text/offsets in order. `evidence_quote` is the verbatim concatenation of selected raw fragments; presentation may show line breaks separately but cannot rewrite the persisted quote. A citation crossing pages is represented as distinct page-local citations/quotes with distinct IDs and exact boxes, all linked to the same supported claim; never collapse multipage boxes into one page field. If exact quote identity cannot be maintained, request a narrower quote within the available repair slot or refuse; no accepted page-only fallback.

Resolved citation: `{citation_id,paper_id,document_version,source_ref,evidence_quote,page,boxes,section}`. `document_version` is the immutable UUID, not an edition label. Geometry comes from PostgreSQL only; include canonical page metadata in Reader document response to validate transforms. Citation GET rechecks ownership/accepted state; browser never trusts URL geometry.

URL for Reader: `/library/{discussionPaperId}?document_version={uuid}&page={oneBased}&citation={uuid}&conversation={uuid}`. `discussionPaperId` stays active; M3 citation paper must equal it. Citation GET is authoritative for version/page/source; supplied URL disagreements show unavailable evidence, not another source. Bare version URL requires owned ready version and metadata. Invalid page/version/citation cannot trigger a model call. No quote, box array, private text or storage key in URL. Refresh/back/forward restores authenticated state; no automatic conversation creation from a GET/deep link.

Citation activation loads validated citation, updates URL atomically, opens exact PDF/version, navigates and transforms exact boxes, then opens one labelled non-modal evidence region under the answer with paper/page/section/quote. No second Go-to-page. Controls have aria-expanded/aria-controls. Escape closes card/highlight, removes citation URL state, retains page/version, restores focus to triggering citation. Switching citation replaces card/highlight; focus waits for valid rendered target and stale request/render results cannot overwrite new selection. PDF selection and conversation completion never execute Discovery/Research.

## 10. Security, failure and observability

Every new private query includes authenticated owner; foreign and nonexistent paper/version/conversation/message/citation behave identically. Cookie mutations require opaque session, exact trusted Origin and session-bound CSRF before parsing body or external work. Read errors hide storage/provider/source existence. Bound all inputs and reject client ownership/filter fields. Paper/user/model text is untrusted content: no tools from PDF instructions, model geometry or hidden URLs; render text safely, not raw HTML. No PDF-derived executable UI.

Safe failures distinguish unready, unavailable original, invalid action/output, unresolvable evidence, embedding/Qdrant unavailable, generation timeout/429/failure, local rate limit and interruption. Provider timeout/429/failure cannot save completed output. Retry is explicit and starts new run; show existing persisted question/draft and avoid duplicate pending submissions. Revoked sessions clear private UI and reject subsequent requests.

Reuse structured `researcy` logs/request IDs; do not add tracing services. Per run record role, scope/version, chosen validated action/tool, retrieval source refs/counts, initial/follow-up/repair counters, actual generation attempts, validation outcome, end state and monotonic latency. Usage from provider stream usage metadata with source/provenance, not string-length token estimates. If stream ends without usage, record unknown/partial, never zero. Estimated cost requires documented route tariff and currency/version/date; distinguish reported billed cost from estimate and free/subscription marginal cost. Missing usage/tariff is a measurement blocker, not permission to invent prices. Store metadata only, never prompts/document text/evidence quotes/provider bodies/credentials/session/CSRF values in logs.

**Owner-approved cost clarification — 2026-10-02:** Master revision 2.1 permits M3 monetary cost to remain `null` / `unavailable` when the applicable account tariff/billing-unit mapping cannot be established, provided the reason/source investigation and actual per-attempt usage, calls and latency are recorded. Missing tariff is then a documented measurement limitation, not an M3 acceptance blocker; missing usage is still unknown/partial, never zero. No inferred free price or unrelated API tariff is accepted.

Health separates process liveness from dependency readiness; checks are read-only and bounded, never generate billable traffic or claim jobs automatically. Real generation readiness is established by explicit qualification, not `/health` 200.

## 11. Acceptance gates and evidence

All gates below are new M3 evidence. Fixtures use isolated databases, buckets and scoped Qdrant collections; preserved owner/manual stack is not the fault laboratory. Real requests that disclose public paper excerpts to the configured hosted route are part of approved implementation/qualification; no private owner paper is sent without explicit permission.

| Gate | Required actual observation |
|---|---|
| G1 Reading | Actual ready `1706.03762` original hash/version; production same-origin Reader canvas/text, navigation, outline, Download hash equality, GET/HEAD/206/416/If-Range behavior and bounded disconnect cleanup |
| G2 Grounded streaming | Transformer parallelization question, live validated claim deltas before terminal event, original paper-only support; actual citation GET + one-click correct paper/version/page/exact boxes and inline card; follow-up respects bounded context |
| G3 Refusal/integrity | Carbon-footprint unsupported question refused without fabricated citations; cross-paper refs, repeated ambiguous quote, invented quote, wrong version, invalid/missing geometry rejected, repair ≤1 and total passes ≤2 |
| G4 Boundaries | Two user contexts for paper/PDF/conversation/messages/citation; foreign/random identical 404, unready no storage/model/retrieval call, CSRF/Origin/revocation/quota/concurrent submission boundaries; URL cannot widen scope |
| G5 Recovery | Actual stream interruption and persisted interrupted state; provider timeout/429/failure exercises production transport with controlled fault harness labelled separately; no false completion, no hidden retry, reload + explicit new submission |
| G6 Real structured actions | Actual `ag/gemini-3.8-flash-low` via 9Router through application GenerationClient/graph: answer and search_same_paper outputs reach only allowed bounded branch; malformed/unsupported actual route outputs rejected with zero tool calls, followed by valid output through same validator; trace/latency/usage/cost source recorded |
| G7 UI/suites | Full affected backend/frontend suites, production API/web build; actual browser keyboard/citation/Escape/focus return, independent scroll/composer, one main, contrast/reduced motion/overflow/width-boundary and all M3 Discussion states |

G6 cannot be passed by isolated qualification unrelated to application graph, mock outputs, Q0 results, development model, or post-response fabricated corruption labelled as actual provider output. Negative controlled parser fixtures supplement real-route evidence only. Use a bounded set of actual qualification prompts to elicit unsupported/malformed actions through the same configured route and record what actually occurs; if real negative output cannot be obtained or provider schema enforcement only yields an upstream rejection, record precisely that limitation and seek owner review of gate interpretation rather than claiming it met. No action/criteria/model change to conceal failure.

Record run source hash, immutable version, question/case identifiers, safe request IDs, environment/image/library/route configuration, expected vs observed, call count and action, first-delta/total latency, token usage/cost source, browser journey and exact geometry comparison. Keep private screenshots/text/cookies/evidence outside Git; commit only safe report/measurements. Do not claim generalized semantic accuracy from few cases. Geometry correctness and substantive answer support are separately reviewed.

Only all exit gates with recorded evidence advance M3 to Verified. Failed gates retain prior status and blockers; code without complete acceptance is Implemented. Do not alter historical Q0 or M1 statuses. M2 resource evidence is inherited baseline, not a new M3 capacity promise; measure API/web/native memory during Reader/generation and preserve existing caps/no OOM. Do not build/test concurrently with resource sampling or stop unrelated owner applications.

## 12. Approval decisions and known prerequisites

Owner review requested for: complete scope; PDF/Range contract and width; version-pinned persistence/reload/idempotent submission; simple-FTS/RRF limits; claim-level structured streaming and repair semantics; provisional operating caps; explicit M3 prerequisite exception while M1 record stays Implemented.

Implementation can deliver Reader first without generation availability, but M3 cannot close until actual gateway endpoint/authorized credentials/route are reachable, usage and monetary-cost provenance follow §10 (including the approved unavailable-cost case), real structured actions qualify, and full journeys pass. Native cold load/container connectivity and isolated stack setup remain execution checks. No additional runtime proof is claimed by this design session.

Self-review: source-vs-normalized quote distinction, multipage citations, page 3 index vs physical page 4, incremental output vs whole-envelope acceptance, no repair after emitted delta, one search-or-repair budget, stream interruption vs persistence race, no invented cost, source-pinned ownership, no M4/M5 UI claims and immutable historical status reconciled. Both documents remain drafts; no implementation authorized by their creation.

### Owner approval — 2026-10-01

The owner stated: “Tôi phê duyệt specification và implement plan.” This approves both documents and the named decisions presented for review, including proceeding with M3 while M1 remains `Implemented`. All M3 gates and product model routes remain unchanged. Implementation is authorized in the isolated M3 worktree; owner-data cutover, publishing, push, merge and prune are not authorized.

### Owner acceptance decision — 2026-10-02

The owner selected “Giữ gate hiện tại” for G6: actual graph malformed/unsupported rejection and valid-after-negative remain required; controlled graph negatives plus standalone client negatives do not close that gate. The owner selected “Duyệt cost unavailable”: apply the limited master revision 2.1 / §10 monetary-cost clarification. This is not approval to change the model/route, retry automatically, restart the gateway, publish or mark M3 Verified.
