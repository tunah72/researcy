# Researcy M4 — DiscoveryAgent Recommendations and Explicit Add

**Status:** Approved child specification — owner approved both documents, Gemini primary, schema-aware gate, null/unavailable cost provenance and M1 prerequisite exception on 2026-10-03. Isolated stack/native and twelve hosted attempts authorized; no owner cutover/publication.
**Date:** 2026-10-03
**Authority:** [Master revision 2.2](./2026-09-18-researcy-system-design.md), especially §§3, 5, 10, 12, 15–17, 19, 21–23; [delivery map](./2026-09-18-researcy-delivery-map.md) controls milestone status.
**Plan:** [M4 implementation plan](../plans/2026-10-03-researcy-m4-discovery-agent.md).
**Predecessors:** [M2 design](./2026-09-27-researcy-m2-durable-processing-design.md), [plan](../plans/2026-09-27-researcy-m2-durable-processing.md), [acceptance](../reports/2026-09-27-researcy-m2-acceptance.md); [M3 design](./2026-10-01-researcy-m3-reader-agent-design.md), [plan](../plans/2026-10-01-researcy-m3-reader-agent.md), [acceptance](../reports/2026-10-01-researcy-m3-acceptance.md).

## 1. Outcome and authorization boundary

On explicit request from a ready active paper's Reader, return at most three actual related arXiv records with metadata-based reasons. Only an explicit `Add to Library` invokes existing arXiv import; processing must finish before the added paper is readable. Search never downloads PDFs, writes originals, creates papers/document versions/jobs/import-idempotency outcomes, or runs ResearchAgent.

M4 owns AGENT-02 and its compact Reader interaction; it does not reopen M1/M2/M3 gates or implement M5. No selection workflow, new service, broker, cache, provider framework, library dependency, background discovery, automatic retry, automatic fallback, or generated scientific title/abstract.

Phase A writes these two drafts only. Before Phase B: owner approves child, plan, and each requested amendment in §3. Approval must explicitly permit proceeding while M1 remains Implemented with its detailed gate record outstanding; prior M2/M3 exceptions are not silently inherited. Use an isolated `feat-m4-discovery-agent` branch/worktree. Do not start owner worker, migrate owner DB, restart/cut over owner stack, publish/push/merge/prune, remove owner artifacts or delete volumes. Isolated services and public-paper provider qualification require the agreed execution/hosted-call authorization; provider safety approvals remain interactive.

## 2. Observed baseline and inventory

The following are observed source/runtime facts, not proposed behavior or fresh acceptance results.

### 2.1 Handoff verification

- `git status --short --branch`, `git log -1`, `git branch -vv`, `git worktree list`, `git ls-remote origin refs/heads/main`: local main and remote main are `5abffbcc572820c8c295b5d9500e1198043423d1`. Local PR #3 merge object is `9664f29`; publication is recorded in M3 acceptance §Main publication and authorized owner-stack cutover.
- Root modified `apps/web/next-env.d.ts` and untracked `apps/web/AGENTS.md`/`CLAUDE.md` exist. Preserve them, other worktrees and retained M3 branch/worktree (`de89abc`). No reset/stash/overwrite performed.
- `docker ps -a --format '{{.Names}}\t{{.Status}}'`: all six main services exited; `ollama ps` could not connect. This proves native endpoint unavailability at inspection, not independently observed model unloading. M3 report records an earlier launchd unload; do not relabel it as fresh observation.
- `test -f .omp/runtime/m3-main.private.yaml`, worktree presence check, and `docker volume ls`: override, M3 worktree and main PostgreSQL/MinIO/Qdrant volumes remain. No private override or `.env` contents were read. Current paper/job contents were not queried because main DB is stopped.
- Delivery map: Q0 Verified; M1 Implemented; M2/M3 Verified; M4/M5 Not started. M2 acceptance §Task 11 final evidence reconciliation and M3 §Final amended M3 gate matrix supersede historical in-progress checkpoints. Their suites/build/browser/provider observations retain their original dates and environments.
- Delivery-map reconciliation gap: §5 requirement rows RET-01/GEN-01/CIT-01/AGENT-01/UX-02 still say Designed while the M3 milestone's Verified closure explicitly supersedes earlier checkpoints. Treat the latest M3 milestone closure as current status; these stale rows are a documentation inconsistency, not a reason to reopen gates or rewrite historical evidence. No Phase A status edit is made.
- Filename inventory under specs/plans/reports contained no existing M4 artifacts. Literal search for `related:search`, `DiscoveryAgent`, `search_arxiv_metadata`, `discovery_runs` in apps/Compose returned no matches. Behavioral `find` failed because its judge account returned 402; that failure was reported and is not absence evidence. LSP reported no configured server; known-file reads/literal searches supplied the inventory.

### 2.2 Source evidence and reuse/gaps

| Boundary | Observed source/symbol | Reuse / M4 gap |
|---|---|---|
| Authentication | `auth/sessions.py:35–90`, `get_current_user`, `require_csrf`; `papers/routes.py:30–35`, `_authenticate_mutation` | Reuse opaque session, exact Origin and session-bound cookie/header checks before external work; no new auth layer |
| Private lookup | `papers/repository.py:88–93`, `get_paper`; `retrieval/repository.py`, `load_ready_document` | Reuse owner predicates and shared ready-version authorization; missing/foreign same 404 |
| Stored metadata | `papers/models.py:12–24`; migration `0001_m1.py:80–110`; `arxiv.py:152–157,399–427`; `intake.py:105–116,216–243` | Title/authors/year exist; abstract absent throughout import and persistence. Add nullable abstract, no invented/backfilled text |
| Title limitations | `intake.py:53–65,216`; upload path `papers/routes.py:189–203` | Stored title may be PDF metadata or filename fallback. Nonempty title is not proof of scientific-title provenance; do not claim extraction quality |
| arXiv identity | `arxiv.py:183–237`, `parse_arxiv_reference` | Modern/legacy IDs, versions and official URLs; canonical versionless identity for exclusion/dedup/Add |
| Upstream safety | `arxiv.py:57–108,240–275,278–427`, `ArxivLimiter`, destination/retry helpers | 3-second pacing, shared process cooldown, 3 redirects, 1 MiB XML, manual official-host validation; add metadata-only search and aggregate cancellation/deadline |
| Import | `papers/routes.py:224–342`, `fetch_official_arxiv`; `intake.py:119–199,202–317` | Existing import downloads/screens PDF and atomically writes paper/version/job/idempotency. Never invoke it from search; explicit Add reuses it unchanged |
| Generation | `generation/client.py:139–265,404–423`, `GenerationClient.stream`; `generation/models.py:83–147` | Reuse bounded streaming/terminal metadata/deadline/transport. Current schemas, event action type and final decoder are Reader-specific; make schema/decoder explicit without copying the client |
| Bounded role | `agents/reader.py:160–234,292–302` | Installed LangGraph pattern; new acyclic Discovery graph, no Reader claim parser/citations/history/repair |
| Quota/accounting | `conversations/repository.py:149–199,344–361`; `agents/reader.py:77–89,348–354` | Short owner-lock reservation/attempt accounting pattern. Reader tables/messages are not Discovery persistence; add small Discovery run ledger. Reader null-cost exception cannot qualify M4 |
| Errors/correlation | `main.py:74–113`, `APIError`, `error_payload` | Reuse safe JSON envelope, generated request ID and Retry-After. No raw provider text in logs/UI |
| Browser/API | `web/src/lib/api.ts:193–326,359–373`, `mutate`, `parseResponse`, `importArxiv` | Reuse same-origin CSRF/errors/idempotency; new central response types/helper only |
| Reader surface | `reader-workspace.tsx:157–180`, `discussion.tsx:56–151`; `reader.css`, `discussion.css` | Existing 1024px boundary, abort/stale/focus patterns. Add compact sibling research action, preserve PDF/Discussion focus and composer |
| Explicit-add UI | `add-paper.tsx:115–165,301–347`; `paper-preparation.tsx`; detail page ready branch | Reuse importer/helper and honest saved-vs-ready detail journey; no duplicate import form or hidden polling per result |

M3 transport terminal accounting may be retained even when final decoding fails. Preserve that invariant for both roles. The existing Reader metric implementation hardcodes null/unavailable monetary cost; it is not a reusable numeric cost calculator or M4 approval.

## 3. Decisions and proposed master amendment — NOT APPROVED

### 3.1 Route alternatives

1. **Recommended:** explicitly extend direct Gemini primary to M4; reuse current Settings and transport, manual between-run 9Router alternative only. Avoids a second per-role endpoint/key configuration while preserving Reader primary. Requires the amendment below and fresh Discovery qualification, not M3 inheritance.
2. **Retain current M4 9Router contract:** qualify `ag/gemini-3.8-flash-low` on a pinned gateway/provider/account with no fallback/transformation. Reader still needs Gemini primary; isolate M4 route selection instead of globally switching owner Reader configuration. Gateway readiness, terminal usage semantics, tariff mapping and actual invalid/unsupported-action evidence are unproved for M4. Route failure is a blocker, not permission to change it.
3. Deterministic metadata recommendations without structured model actions are rejected: this would not implement the approved DiscoveryAgent contract. A new provider service/framework is also rejected.

### 3.2 Exact amendment proposed for owner approval

On approval, append a clearly dated **M4-only generation/qualification amendment** to the master and update only M4 route/gate text in the delivery map:

> For M4, the primary product generation route is direct Gemini at `https://generativelanguage.googleapis.com/v1beta/openai`, exact model `gemini-3.8-flash`, low reasoning, provider JSON Schema derived from the strict role/pass schema and streaming usage. An operator may explicitly select `9Router → ag/gemini-3.8-flash-low` for a subsequent run only. There is no automatic retry, same-run switch or fallback. Discovery retains at most one initial action pass and one metadata-reason follow-up, one official metadata search, at most ten unique inspected records and three recommendations. Each selected route requires its own Discovery qualification; M3 or Q0 evidence does not qualify M4 or an untested alternative.
>
> M4 qualification must observe actual primary application transport and LangGraph search→validated-reasons, actual stop, adversarial action/URL/filter containment and a valid subsequent run. Malformed/unsupported output rejection is separately exercised using explicitly labelled controlled HTTP provider-stream→production-decoder→graph cases proving zero tool execution; these are not natural Gemini outputs. Naturally observed invalid outputs are recorded honestly if encountered, never sought through unbounded attempts. Schema enforcement does not replace backend validation or prove semantic relevance.
>
> For M4 only, unavailable applicable monetary tariff/billing-unit mapping may be recorded as `estimated_cost: null`, `cost_source: unavailable`, with documented reason/source investigation, actual attempts/latency and known/partial/unknown usage provenance. Do not infer zero/free cost, substitute unrelated tariffs or hide missing usage. If an applicable tariff is established, report a documented estimate separately from billed cost. Other M4 gates, M5 and historical evidence are unchanged.

These are three explicit approval items: route/manual-alternative policy; schema-aware qualification composition; monetary-cost provenance exception. None is activated by writing this draft. If cost exception is denied, authoritative route tariff/billing mapping is a prerequisite for the cost gate. If qualification composition is denied, retain the existing real malformed/unsupported gate rather than equate adversarial containment or mocks with that evidence. If route amendment is denied, revise/freeze the 9Router plan before implementation; no covert configuration substitution.

### 3.3 Other local decisions

- One JSON browser response, not SSE. Stream internally only to reuse provider bounds/accounting; publish no partial recommendations.
- Backend selects the first three eligible records in official arXiv relevance order; model writes reasons, not identities/ranking/metadata. A deterministic selection is not a deterministic replacement for the model-directed search/stop branch.
- Store only run/quota/measurement metadata, not recommendation history/abstract snapshots in a new table. Existing paper abstract belongs to paper metadata, not a new recommendation cache.
- UI is ready-Reader-only per master §12.3. Owned unready source returns PAPER_NOT_READY; API still validates missing title before any generation/search. No discovery on unready preparation pages or <1024px Reader.

## 4. API and strict action/output contracts

### 4.1 Browser endpoint

`POST /api/papers/{paper_id}/related:search`, no query parameters and no request body. Reject a nonempty body or unknown query parameter after auth/owner checks with `422 INVALID_REQUEST`; never accept client title/query/owner/model/filter. Bound any attempted body to 1 KiB. Cookie mutation security applies even though no import occurs. Response is private `Cache-Control: no-store` and uses existing `X-Request-ID`.

Authorize owner and source; snapshot stored metadata in a short transaction; verify title usability; require active immutable ready document using shared loader; check provider configuration; reserve quota; then release DB before network. Missing/nonowned source is `404 RESOURCE_NOT_FOUND`. Missing title is `409 DISCOVERY_METADATA_MISSING` and zero generation/arXiv calls, including when its owned paper is unready. Owned usable-title unready source is `409 PAPER_NOT_READY`. Provider unconfigured is `503 GENERATION_UNCONFIGURED`, not empty success.

Successful search or stop returns exactly the master shape:

```json
{"papers":[{"arxiv_id":"2005.11401","title":"Actual official title","authors":["Actual author"],"reason":"Metadata-based reason","arxiv_url":"https://arxiv.org/abs/2005.11401"}],"request_id":"..."}
```

The ID above illustrates the schema, NOT a fixed recommendation or promised relevance. Stop or no eligible candidates returns `{"papers":[],"request_id":"..."}`. Errors use `{code,message,request_id}`; do not disguise missing metadata or outages as empty results. Abstracts, versions, provider/usage diagnostics and run IDs are not added to this public response.

### 4.2 Initial generation

Only these whole objects validate; strict Pydantic models with unknown fields forbidden, no type coercion, duplicate JSON keys/constants/trailing bytes rejected:

```json
{"next_action":"search_arxiv_metadata"}
```

```json
{"next_action":"stop"}
```

No query/URL/tool arguments, owner/filter/candidate IDs, recommendations or reasons are accepted in initial output. Validate the entire terminal JSON before any tool. Invalid/unsupported action fails immediately, no repair/search/follow-up. Initial prompt provides bounded active metadata as untrusted JSON data, instructs search only for meaningful related scholarly metadata, otherwise stop; no provider-native tools.

### 4.3 Follow-up generation and publication

Only after backend candidate verification/selection, supply active metadata and at most three records with canonical ID, authoritative title/authors and abstract-or-null. Output schema:

```json
{"papers":[{"arxiv_id":"2005.11401","reason":"Metadata/abstract-grounded relevance reason."}]}
```

Require exactly the selected canonical ID set, once each, no additional fields, no changed IDs/versions, nonblank safe reason of 1–1000 Unicode code points. Reorder to backend candidate order. Missing/extra/duplicate IDs, empty reasons, forbidden metadata/URL/action fields, malformed envelope or overflow reject the whole response with `GENERATION_INVALID_OUTPUT`; no partial results or third repair pass. The backend constructs title/authors/arXiv URL exclusively from verified records. Without candidates, skip follow-up and return empty.

Reasons are metadata-based rationale, not PDF evidence. Prompt prohibits claims of having read PDFs, full-text citations, fabricated experiments/results/metrics, or invented missing abstract content. Structural validation cannot prove semantic entailment; real acceptance manually checks every returned reason against the exact supplied metadata/abstract. No claim of automated semantic proof or generalized scientific quality.

## 5. Metadata, query, candidates and import policies

### 5.1 Metadata availability

Add nullable `papers.abstract` in a forward migration; extract official Atom `summary` into `ArxivMetadata`/`IntakeMetadata` and persist it in the existing atomic import. Uploaded PDFs retain null abstract: no LLM extraction, full-text scraping or new metadata editor. Old rows remain null; no migration network backfill, reimport, source-version alteration or search-time metadata mutation. New arXiv imports use summary from their existing metadata request, not an extra request. Historical import metadata is latest-record metadata even for a requested old PDF version; do not describe it as immutable PDF evidence.

Usable title: whitespace-normalized stored value, at least one letter/number, length 1–1000 code points, no NUL/invalid Unicode or unsafe controls; reject literal placeholders `untitled`, `untitled document`, `unknown`, `unknown title`, `error` case-insensitively. No UI fallback label, current question, PDF text or arXiv ID substituted for absent title. Filename/PDF metadata quality is a disclosed input limitation, not silently inferred provenance. Missing-metadata UI explains no title is available and offers Back/explicit arXiv import when known, not a nonexistent edit action; metadata editor remains out of scope.

Bound active/candidate abstract sent to provider to first 6000 code points on a whitespace boundary; indicate truncation in internal context. Empty summary becomes null. This is bounded metadata context, not verbatim citation. Candidate title ≤1000; authors ≤200 names, each ≤200; reject oversized/unsafe candidate fields rather than inventing or partially rewriting authoritative metadata. Absent authors are `[]`, not fabricated names.

### 5.2 Backend query

Pure deterministic query from title and abstract if present; no model-provided string. Tokenize Unicode letter/number words, casefold, deduplicate in source order; exclude the explicit stopword set `a an and are as at be by for from in is it of on or that the this to was were with all you need`. Use first twelve distinct title tokens and first eight additional abstract tokens, each ≤80 characters. If title produces no usable term, return missing metadata before initial generation. Do not broaden to abstract alone.

Title group is an OR of `all:"term"`; with abstract terms, AND a second OR of `abs:"term"`. No raw title/abstract inserted as arXiv query syntax. Encode as HTTP parameters `search_query`, `start=0`, `max_results=10`, `sortBy=relevance`, `sortOrder=descending`. The quotation/punctuation syntax is backend-fixed. No pagination, second query, semantic keyword-generation pass or hidden broadening if empty. This deliberately small query policy may return empty/weak matches; measure actual relevance, revise only with evidence and approval rather than building a ranker.

### 5.3 Official metadata adapter and containment

New metadata-only search in `papers/arxiv.py`, never `fetch_official_arxiv`/screening/object operations. Reuse official HTTPS destination allowlist, User-Agent, ID parsing, redirect validation (≤3), 3-second process-wide pacing/cooldown, 406/429/503 Retry-After and 1 MiB decoded XML bound. Reject malformed XML/arXiv error entries as upstream failure, not empty success. Never follow Atom links or external DTD/entities; entry ID is validated data, not an outbound URL.

Use existing httpx2 async client for cancellable search. Share policy/parsing helpers with sync import; do not duplicate safety policy or create a second limiter. Extend limiter safely to support sync import and async search with separate request-exclusion and cooldown-state locks: non-reentrant request lock plus state lock, sync acquire behavior retained, async cancellation-aware nonblocking acquisition/sleep. Avoid holding a thread-owned RLock across async tasks/await. Cancellation cannot leave a lease held or advance a late request. Tests must prove shared search/import spacing and cooldown, no deadlocks and release on abort. Limiter remains process-local, fitting the current single API process; no distributed cache/limiter service.

Whole arXiv search stage ≤60 seconds including limiter waits, redirects, connect and body; shared overall run deadline additionally applies. No redirect resets aggregate deadline. No retry on 406/429/503. Redirect hops are separately counted physical metadata HTTP requests, not another search/model pass. Abort closes active async response/client; no detached thread continues metadata work after request cancellation.

### 5.4 Candidate identity and selection

Request/inspect no more than ten returned Atom entries; if upstream ignores max_results, do not evaluate extra records. Thus no more than ten unique candidates can be inspected even with duplicates. Normalize IDs via existing modern/legacy parser; versions collapse to canonical identity. Invalid-ID entries are discarded and counted; never exposed/fetched. Collapse repeated canonical IDs preserving first relevance position. Conflicting authoritative metadata for the same canonical ID in this response fails safely as upstream inconsistency instead of arbitrarily mixing records; differing edition suffix alone is not a distinct paper.

Exclude active canonical arXiv ID in every version. For uploads lacking canonical ID, exclude exact normalized title matches conservatively; without authoritative ID, do not claim complete alias/duplicate detection. No guessed arXiv mapping. Skip unusable-title records. Already-owned other papers may be recommended: explicit Add resolves through existing owner/canonical dedup and returns the existing paper; no recommendation must disappear because another user owns it. No owner-wide prefetch/filter is needed.

Select first three remaining candidates in official relevance order. Final identity/metadata/URL are backend-bound. Canonical URL is `https://arxiv.org/abs/{canonical_id}`; no Atom/model URL is used. Explicit Add sends the canonical unversioned ID: new imports use current official edition, already-owned imports keep their stored immutable version. Recommendation metadata is not an edition pin. Existing importer revalidates acquisition and supported-PDF bounds; a metadata result may still fail import safely.

## 6. Bounded graph, reservation, timeout and cancellation

```text
owner/metadata/ready checks → persistent reservation
  → initial generation → whole action validation
      stop → empty completion
      search → official metadata search → validate/dedup/select
          none → empty completion
          candidates → follow-up reasons → identity/output validation → completion
```

Compile an acyclic in-process LangGraph in `agents/discovery.py`; recursion limit fixed to cover only these nodes. Defense-in-depth counts: initial ≤1, follow-up ≤1, search ≤1, total calls ≤2. No Reader answer/citation repair, messages/history/retrieval, Qdrant query or embedding request during search.

One forward migration `0007_m4_discovery` adds abstract and `discovery_runs` ledger. Minimal fields: UUID id, authenticated owner/paper/active-version composite FK, request ID, state (`running/completed/failed/interrupted`), started/lease-expires/finished timestamps, validated action, generation_calls constrained 0–2, metadata_searches constrained 0–1, inspected/eligible/returned counts constrained 0–10/0–10/0–3, safe error code, usage JSON containing per-attempt route/terminal metadata provenance, latency and cost provenance. No prompts, titles, abstracts, reasons, object keys or credentials in this ledger. Index owner/start for quota and unique running owner; scope every read/update by owner. This is request accounting, not a document job or result cache.

Reserve under existing short transaction/owner-lock pattern; at most one active Discovery run per owner and twenty accepted runs in trailing hour. Completed/failed/interrupted runs all count; missing title/auth/ready/config failures before reservation do not. Per-role quota is separate from Reader/import, not a new shared agent framework. Explicit retry is a new request/run and counts quota; no search idempotency/replay/result-history API. Duplicate double-click/in-flight browser submissions are guarded; cross-client overlap is `409 DISCOVERY_RUN_ACTIVE`.

Pass ceiling 60 seconds, connect 5 seconds, run 150 seconds from request entry (including authorize, limiter waits and all passes); use existing bounded DB cancellation/5s statements/1s locks and threadpool for synchronous DB work. Keep existing provider ceiling 8192 output tokens/256 KiB and bounded transport queues; input metadata limits above bound prompt size. A lease is 150 seconds plus 15-second cleanup grace; reclaim expired ledger entries lazily on next owned reservation as interrupted with unknown final usage where process died. No scheduler/model resumption. CAS terminalization prevents late completion overwriting failed/interrupted state. Persist an attempt counter immediately before dispatch; distinguish reserved/attempted from observed physical HTTP requests when interruption occurs before send.

Request-scoped run is raced against browser disconnect and absolute deadline. One owner of ASGI receive consumes the bounded empty-body contract and disconnect signal; do not independently poll/consume `Request.is_disconnected` in competing tasks. On disconnect: cancel graph/provider/arXiv await, close transports, terminalize interrupted with measurements obtained so far; no follow-up or response publication after abort. On timeout: safe failure and release run slot; cancellation of synchronous DB work uses existing bounded database mechanism, not abandoned work that can later reserve/publish. On API death the expiry reconciliation handles slot release; no durable generation continuation.

## 7. Failure and observability contract

| Condition | Response / state | Recovery and zero-work invariant |
|---|---|---|
| Missing/revoked session | 401 existing auth code | Clear private UI; zero generation/search |
| CSRF/Origin failure | 403 existing code | Existing sign-in/reload handling; zero generation/search |
| Foreign/nonexistent source | 404 RESOURCE_NOT_FOUND | Identical envelope/status; zero external calls |
| Missing/unusable title | 409 DISCOVERY_METADATA_MISSING | Explain title absence/limitation; zero generation/search; no invented query |
| Owned source not ready | 409 PAPER_NOT_READY | Existing preparation journey; zero generation/search |
| Run active / quota | 409 DISCOVERY_RUN_ACTIVE / 429 DISCOVERY_RATE_LIMITED + Retry-After | Wait/explicit retry, no new model pass |
| Invalid initial action | 502 GENERATION_INVALID_ACTION | No tool/follow-up/import; explicit new run |
| Invalid follow-up / identity | 502 GENERATION_INVALID_OUTPUT | Publish no recommendations; no repair |
| arXiv outage/oversize/XML/inconsistency | Existing ARXIV_UPSTREAM_ERROR 502/503; Retry-After when applicable | No fabricated/partial results; no follow-up on failed search |
| Provider timeout/429/5xx/unconfigured | Existing safe GENERATION_* failures, 504/503 as appropriate | No fallback/retry/false completion; explicit new run |
| Aggregate deadline | 504 DISCOVERY_TIMEOUT | Failed ledger, no late tool/publication; explicit retry |
| Browser cancel/navigation | Interrupted ledger; no writable response promise | Clear/discard stale result; never replay automatically |
| Valid stop/empty | 200 papers:[] | Honest empty UI; explicit Search again only |
| Add failure/unknown outcome | Existing import errors/idempotency | Keep results; same payload/key retry after cooldown; do not claim not imported on unknown outcome |

Use existing structured `researcy` logger and request IDs. Record `role: discovery`, request/run ID, authorized paper/version, selected configured provider/model and echoed identity if supplied, validated action, tool/redirect/HTTP counts, inspected/excluded/dedup/returned counts, initial/follow-up/repair(0) counters, per-attempt terminal usage/status/source, aggregate completeness, latency, validation outcome and terminal state. No public telemetry UI or monitoring service. A model echo alone is not proof of backend model identity. Partial/missing usage stays partial/unknown; sum only complete supported dimensions. Safe code/metadata only for failure diagnostics; never raw provider bodies/metadata prompts/reasons/cookies.

Cost report follows separately approved §3 amendment or unchanged numeric-cost gate. Runtime ledger may honestly contain null without claiming gate acceptance. Investigate applicable selected-route tariff/billing mapping at qualification; when available, compute an offline report estimate using documented currency/date/units/cached/reasoning mapping, not an unsupported runtime billing engine. Provider readiness is actual qualification, not health 200/catalog presence. Phase A made zero product generation/arXiv requests.

## 8. Reader UI and explicit-add journey

Integrate one compact labelled `Related papers` section with the Discussion secondary pane, not a separate page/tab replacing Discussion. Reuse editorial tokens and 44px targets, text-only escaped rendering, fixed PDF 65% / secondary 35%, independent scrolling and a composer never obscured. Discussion accepts a small secondary-actions node from ReaderWorkspace; no Discovery business logic inside Discussion. No Research directions placeholder or M5 selection controls.
When Reader displays a historical immutable version rather than the active version, show the compact action disabled with an explanation to return to the active version. Do not silently bind a historical view to another source. This restriction is UI-local; the POST authorizes the stored active source.

| State | Visible behavior |
|---|---|
| Idle | Compact explicit Related papers button + metadata-based explanation; zero calls from mount/render/GET/reload/deep link |
| Loading | Restrained status, button guard and Cancel; no invented progress or candidate previews |
| Results | ≤3 distinct titles, authors when known, `Based on arXiv metadata and abstracts` reason label, canonical arXiv link, explicit Add to Library per item |
| Empty / stop | No related papers returned; Search again is explicit, no automatic widening |
| Missing metadata | Explain no usable title; Back/known arXiv record or normal import path, not a fake editor or fabricated query |
| Error/cooldown | Curated safe message and explicit retry after Retry-After; no raw codes/request IDs/provider names |
| Cancelled | Search stopped/idle; no hidden reconnect or stale result publication |
| Add submitting | Disable that Add and prevent concurrent intake; preserve results and reason |
| Added/existing | Saved/already available acknowledgment backed by intake response, View in Library link; no ready claim from 202 |
| Add unknown/error | Honest unable-to-confirm feedback, keep identical payload idempotency key, retry explicitly after cooldown |

One browser search request encompasses backend initial/search/follow-up; browser never orchestrates model passes. Per-search AbortController and request generation identity reject late results on cancellation, paper/version change, logout, rerun and unmount. Hide/clear old results when starting a new run, not after an old request completes. On 401 clear private state; security failures follow existing reauthentication behavior. No recommendation persistence in localStorage/URL or auto-restore that triggers model work.

Keep focus on the explicit trigger during loading and restrained announcements; results are a labelled region reachable next by Tab, not an automatic focus trap. Cancel/error removal returns focus to live search trigger; rerender/polling never repeatedly moves focus. arXiv links are normal safe links (`noopener noreferrer` if new tab). Long titles/URLs/IDs wrap. Supported widths 1024/1280/1440; existing 375/768/1023 larger-screen boundary remains, no hidden discovery when unsupported. Respect reduced motion/contrast and one main landmark; preserve citation Escape focus behavior.

Add calls central `importArxiv(canonical_id, key)` only in click handler. One key per unchanged exact canonical payload, retained across unknown-outcome retry; a different candidate/payload gets a new key. Existing owner canonical-ID uniqueness and same-key idempotency handle duplicates/concurrency; no client ownership truth. A completed Add does not automatically navigate, download again, start research, or make new generation calls. View in Library opens existing server-backed preparation/poll/retry and eventual Reader once ready; no per-result job polling fanout.

## 9. Requirement → component → verification/evidence matrix

| Requirement | Component / plan task | Automated consumer-visible boundary | Required real evidence |
|---|---|---|---|
| AUTH-02 / master §§15–16 | Discovery route/repository, T1/T4 | Auth/CSRF/Origin before external work; random/foreign same 404; revocation | G1 actual two-owner HTTP/security probes |
| Missing metadata / §§3,10,18 | Metadata/query loader, T1/T4 | Null/blank/placeholder/no-title-term: zero generation and search; no quota reservation | G1 HTTP missing-metadata state + counters, G5 UI |
| Structured action / AGENT-02 | Transport models + graph, T2/T4 | Whole malformed/unsupported/extra URL/filter rejected before search; stop zero tools; follow-up cannot branch | G2 actual approved-route branches/containment/subsequent valid run; controlled negatives distinctly labelled |
| ≤10 inspected / ≤3 distinct | Official adapter/selection, T3/T4 | Upstream excess, duplicate editions, invalid/active IDs; authoritative metadata and IDs immutable | G3 actual official results/counts and manual reason audit |
| Metadata-only query/reasons | Query + prompts/output validation, T3/T4 | Query cannot inject arbitrary hosts/syntax; absent abstracts not filled; swapped/missing IDs rejected | G3 supplied-metadata reason review; note semantic limits |
| No implicit import | Graph/route, T4 | Unchanged paper/version/job/import rows and MinIO object set; no PDF request, no embedding/Qdrant | G3 before/after authoritative DB/object and metadata HTTP observations |
| Explicit Add / idempotency | Existing import + related UI, T1/T5 | Click-only import, same-payload key replay, changed-candidate key, unknown-outcome retry; existing item reuse | G4 one actually relevant returned ID → explicit Add → real processing ready |
| Timeouts/cancellation/quotas | Ledger/route/arXiv/provider, T1–T4 | Concurrent reservations, 20/hour, expiry, late completion CAS, stalled receive/header/body/redirect/abort, slot release | G1/G6 actual isolated HTTP faults/disconnect and subsequent usable request |
| UI states/accessibility | Related/Discussion/Reader, T5 | Idle/no render calls, all states, stale responses, explicit retry, Add saved vs ready | G5 production browser widths/keyboard/focus/overflow; persisted Library state |
| Observability/cost | Ledger/logger/report, T1/T4/T6 | Call ceilings and known/partial usage retained on invalid/timeout; no wrong aggregate zeros | G2/G6 real per-attempt usage/latency/cost provenance and safe logs |
| Clean cutover / no M5 | Shared decoder callers/import/preflight, T1/T2/T6 | Existing Reader/import/retrieval suites unaffected; migration preserves immutable identities | G7 affected suites, production API/web/worker builds, review |

### Acceptance gates

- **G1 Security/metadata/limits:** actual same-origin route plus two isolated identities; missing title, unready, foreign/nonexistent, revoked session, CSRF/Origin, persistent quota/active-slot boundaries. Controlled fault records are not real OAuth acceptance or M1 promotion.
- **G2 Real product role qualification:** proposed amended Gemini route observes search→reasons, stop, adversarial containment and subsequent valid run, actual physical call counts/validated graph actions. Separately labelled malformed/unsupported local HTTP production-transport/graph rejection shows zero tools. If amendment denied, unchanged route/gate applies and failure blocks closure.
- **G3 Official metadata/no-import integrity:** actual official search, ≤10 inspected unique results, ≤3 valid distinct IDs, exclusion, metadata identity, every reason manually reviewed. Before/after owned Library/version/job/idempotency row sets and private bucket object set unchanged; search upstream log contains metadata only. Actual empty success only claimed when naturally observed; controlled empty-feed test is labelled separately.
- **G4 Explicit Add→ready:** owner chooses one genuinely relevant returned paper not already in isolated Library, imports via existing endpoint/key, verifies immutable original/version/job then observed real worker stages/publication to ready and persisted Library/Reader. Repeat same payload/key and existing-canonical Add preserves identities. If no relevant unowned result or upstream acquisition fails, record blocker; do not substitute a fixed recommended ID.
- **G5 Real browser:** actual production app journey with idle/loading/results/empty/missing/error/cancel/Add/processing/ready, supported widths + small-screen boundary, keyboard/focus/one-main/overflow/contrast/reduced motion, stale-response rejection and no render/reload/deep-link model requests. Controlled UI states retain their labels; real network/provider observations are distinguished.
- **G6 Failure/accounting:** controlled isolated arXiv/provider malformed/unsupported/429/5xx/timeout/interruption/metadata identity faults and real browser disconnect, no hidden retry or late follow-up/completion, slot released for explicit new request; actual approved-provider usage/cost/latency provenance. No fake zero/free cost.
- **G7 Suites/build/review:** focused RED→GREEN, complete affected backend/frontend suites, production builds, actual changed path, independent targeted review where justified, no unresolved blocking finding, safe acceptance report. Update delivery map only with recorded gates; code without all gates is Implemented.

## 10. Prerequisites, blockers, tradeoffs and approval checklist

Observed: owner stack stopped; native embedding endpoint unavailable; M4 not implemented; no real-route qualification attempted. Provider credential entitlement/route availability/billing cannot be inferred from `.env` existence or M3 history. Do not read/log private settings to speculate.

Decisions blocking implementation: §3 route/qualification/cost amendment; child/plan approval; explicit M1 prerequisite exception. Later execution prerequisites: isolated ports/DB/bucket/Qdrant project and same-origin settings, authorized public-paper hosted call budget, valid provider configuration, actual official API availability, native approved processing runtime for G4 and adequate shared-host resources. Native start/load and any shared gateway restart require their own authorization; do not stop owner applications to make capacity tests pass.

Proposed hosted campaign ceiling: twelve physical generation attempts across initial/follow-up and any expressly requested alternative qualification; no calls beyond that budget or indefinite gate-seeking retries. Controlled transport cases use zero hosted calls. If a gate is unobserved at the ceiling, report the exact blocker and retain status, request a separate campaign authorization. Natural malformed output cannot be promised from a schema-enforced provider.

Tradeoffs: deterministic small query and first-three official relevance order avoid a ranking model/cache but may yield weak/empty results; canonical unversioned Add preserves existing import semantics rather than edition-pinning discovery; nullable abstract supports new imports while old rows remain title-only; request ledger makes persistent quotas/accounting correct without persisting recommendations or making graph work durable; async metadata search requires careful shared limiter work to prevent regressions in existing acquisition.

Owner checkpoint: approve or revise both documents, separately approve/reject §3's three amendment items, explicitly allow M4 while M1 remains Implemented, and define isolated runtime/native-start and hosted campaign authorization. Draft creation does not advance delivery-map status and does not authorize owner cutover or publication.

## Owner execution approval — 2026-10-03

Owner approval of both documents was followed by explicit interactive choices: “Duyệt Gemini primary”, “Duyệt schema-aware gate”, “Duyệt null/unavailable”, “Duyệt M1 exception”, and “Isolated stack + native + 12 calls”. The proposed amendment above is now approved as master revision 2.3; draft wording is retained as proposal history, not a pending gate. Implementation is authorized in the isolated feature worktree. M1 remains Implemented; hosted attempts capped at twelve on public papers, no automatic fallback, owner database/worker/cutover, gateway restart or publication.
