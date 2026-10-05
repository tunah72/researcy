# Researcy M5 — ResearchAgent, Evaluation, and Interview Demo

**Status:** Approved by owner on 2026-10-04: “Tôi phê duyệt.” This approves both documents and §12 decisions, isolated execution and ≤36 primary hosted attempts; it does not establish gate evidence.
**Date:** 2026-10-04
**Authority:** [Master revision 2.4](./2026-09-18-researcy-system-design.md), especially §§3–5, 9–17, 19–21; [delivery map](./2026-09-18-researcy-delivery-map.md) controls current status.
**Companion:** [M5 implementation plan](../plans/2026-10-04-researcy-m5-research-agent.md).
**Predecessors:** [M2 design](./2026-09-27-researcy-m2-durable-processing-design.md), [plan](../plans/2026-09-27-researcy-m2-durable-processing.md), [acceptance](../reports/2026-09-27-researcy-m2-acceptance.md); [M3 design](./2026-10-01-researcy-m3-reader-agent-design.md), [plan](../plans/2026-10-01-researcy-m3-reader-agent.md), [acceptance](../reports/2026-10-01-researcy-m3-acceptance.md); [M4 design](./2026-10-03-researcy-m4-discovery-agent-design.md), [plan](../plans/2026-10-03-researcy-m4-discovery-agent.md), [acceptance](../reports/2026-10-03-researcy-m4-acceptance.md).

## 1. Deliverable and authorization

M5 owns AGENT-03, EVAL-01 and OPS-01: explicit selected-paper research directions, exact cross-paper premise citations, fixed separated evaluation, and a reproducible interview startup/journey. Reader remains the default and visual center. This is not a general scientific assistant, novelty detector, feasibility verifier, new source connector, metadata editor, report destination or background agent.

Owner approval on 2026-10-04 authorizes implementation in isolated `.omp/worktrees/m5-research-agent`, branch `feat-m5-research-agent`, base `74444f3`, including §12 prerequisite, gate, cost and isolated/36-attempt decisions. It does not authorize main-data migrations/worker/cutover, credential or OAuth-permission changes, shared-native reconfiguration, commit/push/PR/merge/prune or historical evidence edits. Fresh verification remains required; approval is not passing gate evidence.

## 2. Evidence-backed baseline and prerequisites

### 2.1 Current inspection

- `git status --short --branch`, `git rev-parse HEAD origin/main`, `git log -3 --oneline`, `git worktree list`: main/local tracking ref at `74444f36a04c63fcd08f4525f7e073e05e66359b`; merge `5a1fef6` remains in history. Read-only `git ls-remote origin refs/heads/main` independently returned the same full main hash.
- Owner changes: modified `apps/web/next-env.d.ts`, untracked `apps/web/AGENTS.md` and `apps/web/CLAUDE.md`. Preserved, not included in this worktree or committed. Existing worktrees/audit branches remain.
- `docker compose -f compose.yaml -f .omp/runtime/m3-main.private.yaml --profile web --profile processing ps`: API/web/worker/PostgreSQL/MinIO/Qdrant running; API/PostgreSQL/Qdrant healthy. Read-only `/health` returned 200 (`4e37435a-d299-465c-bf63-1e99313a6d53`), web returned 200. No restart or mutable preflight ran.
- Native `/api/version` returned `0.18.2`; `/api/ps` returned `models: []`. This is a reachable idle runtime, not unavailable Ollama and not proven warm embedding readiness. Do not load a shared model implicitly.
- Live `/openapi.json` contains Reader stream and Discovery route, no research-directions route. Literal source search for `ResearchAgent`, `research-directions`, `direction.delta`, `research_runs`, `research_ideas` under apps/Compose returned no matches.
- No current private paper/job inventory, provider catalog, billing account or hosted generation was queried. Eight preserved succeeded jobs and the cutover suites/build/preflight are historical observations in M4 acceptance §§Merged-main cutover evidence, not fresh M5 measurements.
- Descriptive `find` failed every judge request because its provider account was rejected; reported to the tool issue channel. Inventory/literal searches, direct reads and scoped read-only research supplied the source evidence. LSP status: no language servers configured; recheck before implementation refactors.

### 2.2 Existing boundaries and actual gaps

| Boundary | Existing source evidence | M5 change required |
|---|---|---|
| Owned immutable publication | `retrieval/repository.py:50–134`, `load_ready_document`; `EvidenceHit.scope` | Validate the entire selection before embedding/provider dispatch; retain 2–4 exact source tuples |
| Hybrid retrieval | `retrieval/hybrid.py:14–75`, simple FTS, dense five + lexical five, RRF k=60, fused five, bounded whole chunks | Add selected-source orchestration, not an unrestricted index query or new ranker |
| Exact quote resolver | `citations/resolver.py:28–42,114–152`, same-scope catalog, raw unique matching, canonical re-resolution, page-local boxes | Build prefixed per-source catalogs and resolve each against its own pinned ReadyDocument; do not pass mixed hits to the existing same-paper builder |
| Citation publication/read | `citations/repository.py:12–28` joins accepted citations to completed Reader messages and same-paper conversations | Research citations need their own run/idea/source constraints; current Reader rows cannot represent cross-paper premises |
| Provider transport | `generation/client.py:134–155,333–384`, explicit output adapter/schema, metadata callbacks and bounded producer | Add Research schemas/parser only; reuse transport, no new provider abstraction |
| Bounded graph | `agents/reader.py:163–235,258–306`, initial/follow-up accounting, pre-delta repair, atomic publication | Separate small Research graph without Reader history or model-directed search |
| Reader navigation | `reader-workspace.tsx:29–80,102–123,148–183` rejects citations outside open paper/version and restores through Reader messages | Separate active Discussion source from displayed PDF; validate research-run membership on restore |
| Secondary actions | Reader injects RelatedPapers into Discussion; imported papers use existing preparation path | Add explicit owned Library selection and Research controls, no automatic selection/import/generation |
| Startup | `ingestion/preflight.py:30–58,61–148,151–172` checks migration/storage/index; storage probe writes and removes a private object | Reuse only inside approved isolated environment; not a read-only main inspection. Add one demo entrypoint and honest route-readiness classification |
| Historical gold | `qualification/corpus/manifest.json`; `qualification/gold/evidence.jsonl` | Preserve two hash-pinned sources, eight answerable/two unanswerable cases; add separately versioned multi-paper gold and broader layout evidence |

### 2.3 Gaps and conflicts, not retroactive acceptance

1. **M1 record:** map says Implemented, owner reported successful real-account testing, detailed two-real-Google-user four-gate record still outstanding. Previous M2/M3/M4 exceptions do not automatically permit M5. Recommended: explicit M5 implementation prerequisite exception; preserve M1 state and record the new M5 real sign-in journey without calling it M1 reconciliation.
2. **Map consistency:** RET-01/GEN-01/CIT-01/AGENT-01/UX-02 rows still say Designed despite the latest M3 Verified closure. Latest milestone closure controls status. Correct those current rows by linking existing closure only when document reconciliation is approved; do not rerun gates or rewrite historical sections. M5 draft creation changes no map status.
3. **Cost:** M3/M4 monetary-null amendments explicitly exclude M5. Public tariff is available, but account tier and compatibility usage-to-billable-unit mapping are not established. §10 proposes a narrow M5-only exception if numeric estimation remains ungrounded. Without approval or a valid numeric mapping, G6 cost is blocked.
4. **Route qualification:** master globally selects direct Gemini primary/manual 9Router alternative; no new route amendment is needed to retain it. M3/M4 role qualification is not M5 evidence. M5's own gate in §11 requires real Research transport/graph and separately labelled controlled rejection; it does not inherit or pretend to observe natural malformed Gemini output.
5. **Readiness/resources:** current health/idle native runtime and prior shared-host pressure do not prove current generation entitlement, warm-model fit or end-to-end capacity. Isolated runtime authorization, sufficient host resources, official arXiv acquisition and an owner-completed Google sign-in remain execution prerequisites. Main's configured origin is localhost3000; another isolated registered callback has not been inspected. Preserve main and use an already registered free origin, or request separately authorized callback registration. Do not stop unrelated apps or weaken caps to conceal a failure.

## 3. Smallest design and alternatives

**Chosen proposal:** one request-scoped Research LangGraph; reuse existing per-source hybrid retrieval, raw catalogs, resolver, generation transport, SQL reservation/cancellation patterns and PDF renderer. Add a small Research domain, four relational tables and one compact secondary UI. Preserve Reader contracts.

- Reusing fake Reader conversations/messages for related-paper premises is rejected: current same-paper constraints encode an important Reader invariant.
- A generic polymorphic agent persistence framework or weakening Reader citation FKs is rejected: separate research tables and one citation-read branch are smaller and safer.
- Global dense/lexical rankings can starve a selected paper. Use source-balanced per-source RRF over exactly the pinned allowlist. No reranker, extra model search, cache, agent service, worker job or new dependency.

## 4. API, selection and version pinning

### 4.1 Request

`POST /api/papers/{paper_id}/research-directions:stream`

```json
{"related_paper_ids":["owned-ready-paper-uuid"]}
```

Only that field is accepted. JSON body ≤2 KiB, one to three canonical UUID strings, distinct after UUID parsing and different from active ID. Reject unknown query parameters/fields, duplicate JSON keys, non-JSON/non-object values, non-string IDs, empty/oversized selections; no owner/version/query/model/filter fields. Pydantic/OpenAPI declares the field's array and bounds; duplicate/distinct/ownership checks are backend semantic validation.

Order: authenticate opaque session and require session-bound CSRF/exact Origin → authorize active owner → bounded body/shape validation → batch owner lookup of **all** related IDs → foreign/missing identical 404 → validate readiness/publications for active and all selected → check generation configuration → persistent reservation. Foreign/missing check precedes reporting owned readiness failures for mixed selections; reject the whole set, never silently filter it. No embedding, Qdrant, provider or quota reservation until selection validation succeeds.

Load the active-version pointers together in a short owner-scoped database snapshot; resolve each ready immutable publication, then recheck unchanged pointers and readiness at reservation. A changed snapshot returns `409 RESEARCH_SOURCE_CHANGED`, zero generation; explicit resubmit loads a new snapshot. Store `owner_id, paper_id, document_version, profile_hash` for active and each selection. Canonical source order is active first then selected UUID order; browser selection order does not become evidence priority. All subsequent retrieval/resolution uses these exact tuples, never reloads an unpinned active version. Revalidate authorization/publication before terminal commit; a failed recheck publishes nothing.

Prestream failures: `422 INVALID_REQUEST`; `404 RESOURCE_NOT_FOUND` for any foreign/missing private source; `409 PAPER_NOT_READY` for active, `409 RESEARCH_SELECTION_NOT_READY` for an owned selected source; `409 RESEARCH_SOURCE_CHANGED`; `409 RESEARCH_RUN_ACTIVE`; `429 RESEARCH_RATE_LIMITED` with Retry-After; `503 GENERATION_UNCONFIGURED`. Existing authentication/CSRF codes unchanged. After headers, provider/dependency/output faults become safe `direction.failed` without changing HTTP status; interruption may prevent delivery.

### 4.2 Minimal reload contract

Add `GET /api/papers/{paper_id}/research-directions/{run_id}`. Both active paper and run must belong to the requester and match each other; foreign/missing returns 404. Response:

```text
{run_id, active_paper_id, document_version, sources:[{paper_id,document_version}],
 state: running|completed|failed|interrupted, ideas: accepted ideas only,
 draft_ideas: provisional text fields only for failed/interrupted,
 error: null|{code,message}, request_id}
```

No provider diagnostics, quotes in draft data, object keys or credentials. Completed ideas contain accepted exact citations. Read reconciles expired running leases to interrupted; no background scheduler/resumption. UI uses this GET to restore the run named by `research_run` URL state; no extra history destination/list UI. SSE response sets `X-Research-Run-ID` after reservation so the browser can retain a reload pointer before the first delta. This identifier grants no access by itself. Prestream errors remain ordinary safe JSON/status responses without a run header.

### 4.3 SSE contract

UTF-8 POST fetch with AbortController, no-store, existing same-origin proxy. Exactly these event names; all carry `run_id` and `request_id`:

| Event | Additional data |
|---|---|
| `direction.delta` | `sequence` positive monotonic integer; `idea_index` 0–2; `idea:{observed_gap,proposed_direction,possible_method}`. One fully shaped, evidence-resolved but provisional idea per delta; no raw tokens/JSON/clickable draft citation |
| `citation.resolved` | `idea_index`; `citation` with existing ResolvedCitation shape |
| `direction.completed` | `ideas` of length 1–3, each exact fields `observed_gap,proposed_direction,possible_method,premise_citations`; only after atomic persistence |
| `direction.failed` | stable `code`, safe `message`; no accepted ideas/citations |

Resolved citation fields remain `citation_id,paper_id,document_version,source_ref,evidence_quote,page,boxes,section`. Geometry is backend-bound, physical page is one-based, boxes are exact bottom-left unrotated PDF-space with canonical crop/media/rotation. Multipage quotes split into page-local citations, never a guessed single page.

One terminal event if writable; disconnect may prevent terminal delivery. EOF without terminal is interruption, not completion. If database completion won the race before downstream failure, GET may legitimately return completed; the browser must not infer the durable outcome from an unread terminal event. No new `direction.refused`/`started` event. Insufficient evidence uses safe `direction.failed` code `RESEARCH_INSUFFICIENT_EVIDENCE`, persisted failed with no accepted ideas; UI presents this as refusal rather than provider outage. Successful completion never has zero ideas.

## 5. Selected-source retrieval and exact premises

`retrieve_research_evidence(sources, deadline, cancel)` orchestrates existing `retrieve_same_paper` for 2–4 pinned ReadyDocuments, serially under the same run deadline. For each document, query is its stored title (up to 1000 code points, if present) plus fixed `limitations future work evaluation methods experiments`; with no usable title use available canonical section headings within the same 1000-character bound, otherwise the fixed terms alone. This query is navigation context, not factual evidence or title extraction. No Discovery abstract/reason or previous answer enters retrieval/generation evidence. Per-source queries may differ; up to four dense/embedding calls are a measured latency tradeoff, not one globally pooled RRF ranking.

Each source retains existing dense5 + lexical5 → RRF k=60 → fused5 behavior; take only its first two fused/packed hits. Pack in two rounds (first candidate per source, then second), immutable source order, max eight whole chunks, ≤24,000 normalized plus ≤24,000 raw code points. Do not truncate evidence or backfill rank-three after an oversized candidate. If any selected source cannot supply its first mappable whole chunk within budget, fail safely rather than quietly drop that source. These Research-specific caps do not change Reader's five/12,000+12,000 limits. Measure per-source Recall@2/5 and packed recall; balanced coverage is not claimed globally optimal.

Dense calls continue to use exact owner+paper+version+collection/profile constraints; lexical/hydration likewise. Never use independent `paper_id IN (...) AND version IN (...)` predicates that admit a cross-product. Any returned hit outside the tuple set fails closed. Existing empty dense response from a nonempty ready publication stays an integrity/dependency failure, not scientific abstention.

Build an existing same-paper catalog per source (at most two hits), prefix refs `P0:S1`, `P1:S1`, etc., then merge ≤8 entries. A server map binds each prefixed ref to its ReadyDocument. Resolve proposals through existing `resolve_proposal` using **that entry's** document; raw unique/whitespace-preserving quote rules, canonical raw-fragment re-resolution and exact geometry remain unchanged. Model supplies only `source_ref,evidence_quote`. It never supplies authoritative paper/version/page/boxes.

**Reader evidence/navigation contract clarification:** Initial, repair and same-paper follow-up inputs retain normalized retrieval text in a separate `navigation:{source_ref:normalized_text}` map. Citeable `sources` contain only `{source_ref,raw_excerpt}`; the model must copy quotes from the matching raw excerpt, not navigation. Canonical raw fragments can meet without recorded whitespace: do not insert normalized span separators, expand ligatures or remove recorded hyphens when quoting. Retrieval budgets, immutable provenance, unique raw matching and exact page/character-box validation are unchanged. This producer distinction is not proof that a historical hosted failure had a particular rejected quote, nor a substitute for fresh hosted qualification and human factual assessment.

**Failed Unicode presentation experiment:** A named natural Reader diagnostic using ASCII Unicode escapes and an exact escape-preservation instruction failed with `GENERATION_INVALID_OUTPUT`: the provider invented null characters in quotes after two validated provisional claims. The input/raw catalog contained no nulls. This presentation change was reverted; no remedy or passing provider qualification is established. The independent evidence/navigation separation remains. Exact validation continues to reject altered or unsafe quotes; no resolver cleaning, source/gold changes, additional retries, budget increase or model fallback was introduced.

Every accepted idea requires at least one exact premise citation from the authorized current/selected source set. Cite only papers that support its factual assertions; active-only, selected-only and split-source premises are all legal. Never force decorative citations to every selected paper. Each factual assertion within `observed_gap` must be supported by its premise citation set. A comparison does not prove a missing technique never exists elsewhere. Prompt forbids absence/novelty/feasibility assertions based on retrieval silence. Deterministic validation proves source/quote/geometry, not semantic entailment; evaluation separately assesses every factual assertion and requires actual split-source ideas/citation jumps for the cross-paper acceptance journey.

## 6. Output, bounded graph and interruption

Strict role models forbid unknown fields, unsafe/blank text, duplicate JSON keys/constants/trailing bytes and coercion. Provider schema and backend validator share the models. Initial and repair permit the same supported-output or refusal envelope:

```text
{next_action:"directions", ideas:[
 {observed_gap:string, proposed_direction:string, possible_method:string,
  premise_citations:[{source_ref:string,evidence_quote:string}]}], refusal:null}
OR
{next_action:"directions", ideas:[], refusal:nonblank string}
```

Ideas 1–3 when refusal is null; each text field 1–1200 Unicode code points, each proposed citation existing quote bound 1–2000, 1–6 proposals/idea; at most 24 resolved page-local citations/run after splitting. Refusal 1–1200, mutually exclusive with ideas. Unknown actions such as search/import or model scope/geometry fields fail without any tool/repair. Refusal text is untrusted; reader presentation uses curated insufficiency copy rather than unchecked provider details.

```text
validated pinned reservation → selected-source retrieval/catalog
 → initial generation/whole-unit validation
    valid ideas → atomic publish
    insufficient evidence → safe refusal
    repairable output/citation failure, no delta yet → one repair → publish/refuse/fail
    unsupported action, transport failure or failure after first delta → fail
```

Acyclic explicit initial/repair graph, fixed recursion bound. Initial ≤1, repair ≤1, total ≤2; repair uses exactly the original catalog/allowlist and contains only a safe validation category, not an extra retrieval, provider switch or previous answer as evidence. Do not retry timeout/429/EOF or malformed unsupported action. Citation/output repair is validator-directed and permitted only before any direction delta has been queued for publication. After first delta: no repair/replay/new model call. An invalid later idea/envelope makes all visible drafts failed/interrupted, never accepted.

Use a Research incremental idea parser with the established ijson lifecycle pattern, not Reader claim-shaped decoding or a new library. Validate completed idea and its citations before delta. Hold ideas until `next_action` and `refusal` compatibility are known; reconcile parsed units with the strict final envelope before persistence. Withhold all `citation.resolved` events until accepted terminal commit. Pre-encode every final citation/completion event and enforce 256 KiB/event before commit; never drop boxes to fit.

Reuse existing limits: connect5s, pass60s, request150s from entry, provider8192 output tokens/256KiB, producer queue16×≤16KiB, ASGI send fragments≤16KiB, SQL statements5s/locks1s. Preserve existing Compose/native memory ceilings. One owner of ASGI receive reads the bounded body then disconnect notifications; no competing consumers. Cancel graph/provider/retrieval with existing cancellation Event and joined bounded DB work; abandoned operations must not later reserve/publish. Close parser/transports on every path. Request-scoped work never becomes a durable generation job.

## 7. Persistence, quota and publication

Forward revision `0008_m5_research`, down_revision `0007_m4_discovery`; no historical migration edits. Four tables keep Reader same-paper constraints unchanged:

| Table | Minimal data/invariants |
|---|---|
| `research_runs` | UUID id, owner, active paper/version, request ID, running/completed/failed/interrupted, timestamps/165s lease, generation_calls0–2, repairs0–1, safe error, bounded draft JSON, per-attempt usage/route/cost/latency/validation metadata; owner/active/version FK; owner/start quota index and one running/owner partial unique index |
| `research_run_sources` | owner/run/paper/version/profile_hash, ordinal0–3, active flag; unique run/paper and run/ordinal; composite source-version FK; exactly one active and 1–3 related enforced by reserve/publication validation; rows immutable |
| `research_ideas` | owner/run/idea_index0–2, three nonblank text fields; composite run FK; accepted rows only inserted with completed terminal transaction |
| `research_citations` | UUID id, owner/run/idea_index, source paper/version/ref, verbatim quote, canonical page_id/page≥1, nonempty finite exact boxes, section, canonical raw-fragment provenance; FK to owned run/idea, exact run-source tuple and owned version/page; accepted rows only |

Reuse source-provenance validation by extracting only the canonical verification currently used for Reader publication, with all callers migrated; do not trust HTTP/model citation payloads. New research citations do not need provisional DB rows: validated drafts stay non-clickable and accepted citations are inserted only at terminal commit.

Database guards preserve run-source pins and completed ideas/citations as immutable evidence; terminal run outcome cannot revert to running. Metrics may acquire final known accounting without changing accepted text/source/geometry or overwriting a terminal winner.

Reserve under the existing short owner-lock transaction pattern. One active Research run/owner and twenty accepted Research runs/trailing hour, persistent and separate from existing Reader/Discovery quotas. All reserved outcomes count; invalid selections/configuration do not. Browser serializes generation actions in this Reader to avoid unnecessary competing work; cross-role quotas remain the current independent policy, not a new global agent scheduler. Explicit retry makes a new run; there is no hidden reconnect, replay or idempotency shim.

Terminal transaction locks run, checks still-running/unexpired state, revalidates exact source membership/canonical raw fragments, inserts all ideas/citations and completes atomically. Compare-and-set failure means no publication. Failure/interruption saves only bounded provisional text and acquired usage; no accepted ideas/citations. Lazy expiry on the owned GET/new reservation marks interrupted with unknown unobserved usage, releases slot, never resumes generation. Completion and interruption races have one durable winner; a later callback cannot overwrite it.

Extend existing `GET /api/citations/{citation_id}` with one Research lookup path, while retaining Reader accepted/completed-message checks. Research lookup requires authenticated owner, completed run, accepted idea, exact run-source tuple and ready immutable publication. Foreign/random/uncommitted IDs all 404. If a UUID were found in both stores, fail safely rather than pick an arbitrary citation. Shared public shape and PDF endpoint unchanged; no public object URL.

## 8. Reader selection and cross-paper evidence UX

Compact Research directions section lives beside existing Related action in Discussion secondary pane; no replacement tab/report page. Opening it fetches the existing owner Library, no generation. Show native labelled checkboxes for eligible ready non-active papers; owned unready items are disabled with waiting/processing/failure guidance and existing Library link, not technical stages. One to three selections; fourth selection prevented with associated guidance. Nothing preselected from Discovery or Add. Refresh the Library once on explicit selection-panel open; no polling fanout. Backend is authoritative if status changes after selection.

Research trigger enabled only for active ready Reader version and valid selection; historical active-paper view explains return-to-active requirement. Showing a selected paper's PDF after a citation does not redefine active Discussion/research source. Explicit submit freezes selection for the run, loading offers Cancel; changing selected sources requires cancel/new explicit request. No generation on mount/reload/GET/citation/popstate/selection itself. On stale response, paper/version change, logout, unsupported width or unmount: abort and ignore late results.

UI states: idle, selection, no eligible sources, loading/retrieving, provisional streamed ideas, committed ideas, insufficient-evidence refusal, provider/quota/source error, interrupted, citation loading/exact/unavailable. `Proposed direction — hypothesis` and `Possible method — hypothesis` labels appear on drafts and completed ideas. No novelty/feasibility badge or hidden reasoning/model/provider diagnostics. Preserve actual failed vs interrupted state; diagnostics stay in safe reports/API, not reader copy.

### Cross-paper navigation

Keep path `/library/{activePaperId}` and existing `document_version`/`conversation` for Discussion. Add `research_run={uuid}` and separate `pdf_paper={uuid}&pdf_version={uuid}` for displayed original, plus existing page/citation. These values are hints, never authority or quote/geometry storage.

On citation activation: GET accepted citation → prove membership in the displayed Reader message or accepted Research run → fetch owned exact cited-paper detail/version → validate page/canonical metadata → atomically update URL and displayed PDF → reveal exact boxes → open inline labelled non-modal evidence card under the relevant answer/idea. Card shows actual cited title/page/section/quote, not active title. Existing PdfReader/viewport transformation is reused; no fuzzy search. Stale fetch/render cannot override newer selection. Failed PDF/source validation shows unavailable evidence with no old highlight masquerading as success.

Discussion and its composer remain pinned to the original active source throughout related-paper PDF navigation. Header clearly identifies displayed paper and offers explicit Return to active paper; Download points to the displayed original. Escape closes card/highlight, retains displayed paper/version/page, returns focus to triggering citation. Back/forward/reload restores by authenticated run/message membership; tampered paper/version/page/citation combinations are unavailable, not silently corrected or source-widened. Cross-paper PDF URL without a citation still requires ordinary owned version lookup and cannot trigger generation.

Preserve ≥1024px Reader, fixed approximately65/35 split, independent scroll, composer visibility, one main,44px controls, wrapping, visible focus, citation aria-expanded/controls, restrained announcements, no trap, reduced motion and contrast. Verify 1024/1280/1440 and375/768/1023 boundary in real browser. Keep Crimson Pro/Atkinson/warm paper/navy/ochre/red roles; no frontend system rewrite.

## 9. Fixed evaluation corpus, annotation and rubric

Evaluation artifacts are a new M5 version, never modifications to Q0 files/results. Safe manifest/checksums/case IDs/configuration/aggregate results may enter Git. New PDFs, raw evidence quotes, prompts, account data and screenshots stay private/ignored; the manifest references source hashes, offsets and private annotation artifact hashes without exposing text. A licensed public annotation is not permission to log private runtime evidence. Preserve the existing qualified public gold exactly as historical input.

### Freeze before hosted evaluation

1. Retain both Q0 hash-pinned sources and all eight answerable/two unanswerable cases; retain12 reading-order relations and original page-index conventions. Independently supplement exact geometry annotations for cases with no frozen boxes in a separate M5 annotation, not by filling Q0 records.
2. Add at least two supported public scientific PDFs, giving at least four distinct sources for active+three-selected. Initial acquisition candidates are the M4 actually returned `2202.09741` and `2105.02358`; these are candidates, not assumed relevant/layout-qualified papers. Inspect actual originals and metadata locally. If unsuitable, choose a replacement from the explicitly reviewed official result set before freeze and record rationale/source/hash; never force a positive premise from a weak paper.
3. Include actual one-column, two-column, figure/table-caption-heavy and alternative publication layout evidence. If four sources do not cover those categories, add up to two public layout-only sources; controlled rotated/cropped parser fixtures supplement geometry boundaries but do not count as real scientific-layout quality evidence. Record layout classification from actual PDFs, not arXiv ID inference.
4. Freeze manifest and annotation checksums after independent raw-PDF reading, before looking at generated ideas. Gold includes source edition/SHA/page/media/crop/rotation, exact raw offsets/character boxes, admissible factual premise sets and forbidden/unsupported assertions. Expected gaps are human-annotated source limitations/comparisons; there is no gold claim of novel discovery. Retrieval gold is used after ranking, not in query/prompt.

Eight new Research cases, no user question/query added to API:

| Case | Selection/input and expected boundary |
|---|---|
| R1 | Active A+one ready B, supported paired premises; at least one idea using both |
| R2 | Active B+one A, reversed identities and an annotated selected-only premise; no source/version confusion or forced active citation |
| R3 | Active A+two ready related sources and an annotated active-only premise; useful supported idea, every retrieved hit allowlisted, no forced selected citation |
| R4 | Active A+three ready related sources; coverage without invented all-source citations |
| R5 | Hash-pinned negative case independently annotated insufficient for any supported requested research-direction premise; safe refusal/omission, no fabricated premise. May use a clearly labelled supported-text controlled fixture when natural scientific PDFs do not justify an insufficiency label |
| R6 | Controlled source limitation case where proposed novelty/feasibility is not established; accept only source-supported gap and labelled hypotheses or refusal |
| R7 | Newly processed isolated supported-PDF fixture containing hostile instructions, actual provider run; no edits to sealed canonical data, scope/action widening or fabricated accepted evidence |
| R8 | Fresh valid paired run after R7 through the same validators; normal supported result |

R5/R6 gold must be independently reviewed before execution; if a supposedly negative pair actually supports a defensible idea, correct gold before freeze, not reject a valid model by arbitrary wording. Controlled source fixture cases are explicitly separate from natural scientific PDFs. Include local-only invalid-selection, wrong-version, unrelated-unselected-source, ambiguous-quote, missing-box, multipage, transport and interruption cases; these consume zero hosted calls.

### Measurements and proposed acceptance criteria

| Layer | Report separately; proposed gate |
|---|---|
| Parsing | Text coverage,12 preserved order relations, section correctness, span/box mapping and added layout-region counts.100% resolvability for regions used as accepted gold; broader layout errors disclosed, not generalized parser accuracy |
| Retrieval | Dense/lexical/fused Recall@5 and MRR on unchanged8 answerable cases; source-balanced Recall@2/5 and packed recall on paired premise sets. Original-case fused≥6/8 under production FTS is a proposed nonregression floor, not comparability to historical BM25; paired per-source Recall@5≥75%, report exact numerator/denominator. Scope leakage0, tuple identity100% |
| Citation | Source precision/completeness, unique raw mapping, exact page/boxes and click identity. Every accepted citation exact and allowed; zero page-only fallback. Gold rounded-region overlap is supplementary, not exact-box equality |
| Reader answer | Reuse qualified supported/refusal/follow-up cases and report fresh vs historical subsets; human factual correctness/support scores0/1/2, abstention confusion counts |
| Discovery | Fresh explicit search/Add journey:≤10 unique inspected,≤3 distinct, active excluded, manual metadata rationale assessment and zero implicit imports. Empty/error fixtures labelled controlled |
| Research | Per factual assertion entailment0 unsupported,1 partial,2 fully supported; per idea source coverage, cross-paper support and hypothesis labels. Positive R1–R4/R8 each produce≥1 fully supported idea; accepted factual assertions score2, scope errors0, labels100%. R5 insufficiency handled safely; R6 cannot claim proven novelty/feasibility |
| Route | Actual configured Research transport/graph supported/refusal/hostile/subsequent valid paths. Controlled malformed/unsupported production-HTTP decoder/graph rejection proves no unauthorized publication, not natural Gemini rejection |
| Product | Import-to-ready time, header/first validated delta/terminal latency separately, successful exact citation jumps/attempts, cancel/reload/retry states. No fake token animation or promised latency inferred from one run |
| Cost | Actual attempts/physical-response observations, per-pass usage completeness, estimate and source/mapping/currency/date, missing costs/usage counts. Unknown is never0; no generalized monetary efficiency claim |

Report every case including failures and denominators; no rerun-until-pass selection or headline generalized accuracy from this small corpus. If a quality floor fails, diagnose with the frozen corpus; a proposed retrieval/prompt change needs measured comparison on the same cases, never changed gold to improve scores. Case/model/configuration changes create a new named campaign, retain failed evidence, and require additional call authorization when budget is exhausted.

## 10. Route, budget, cost provenance and demo readiness

Retain primary `GENERATION_PROVIDER=gemini`, exact `https://generativelanguage.googleapis.com/v1beta/openai`, `gemini-3.8-flash`, low reasoning/provider JSON Schema/streaming usage. Reuse provider-neutral transport. Alternative9Router `ag/gemini-3.8-flash-low` is operator-selected between runs only; no automatic fallback. Optional alternative needs separate authorization/Research qualification, not this primary campaign budget.

### Owner-approved hosted campaign — 2026-10-04

Ceiling **36 hosted generation attempts**, public/explicitly controlled isolated sources only:

- 16: eight Research cases, worst-case initial + repair each;
- 6: three retained Reader supported/refusal/follow-up runs, max two each;
- 4: two Discovery qualification/evaluation runs, max two each;
- 6: one complete browser demo journey (Reader ≤2, Discovery ≤2, Research ≤2);
- 4: diagnostic reserve, only named failed/prerequisite cases, no indefinite gate seeking.

A pass counts against the ceiling immediately before dispatch; cancellation/uncertain send still consumes the reservation conservatively. Maintain one serial campaign ledger and remaining-attempt guard; reserve two slots before a potentially two-pass run, release unused slot after terminal cleanup. No automatic extra requests or standalone paid readiness probes. Reuse the first successful approved application run as provider readiness evidence. Controlled HTTP faults/local parsing/retrieval/ingestion use0hosted calls. Owner manual runs are separately attributed and not invented agent evidence; explicit owner use may incur charges.

**Monetary decision:** read-only official [Google pricing](https://ai.google.dev/gemini-api/docs/pricing) on2026-10-04 lists Standard paid Gemini3.8 Flash USD/1M input0.75/output including thinking3.75/cached input0.075 through2026-12-31; later prices/tier/batch/flex/priority differ. This is public pricing, not this account's billed tariff. `generation/client.py:57–70` permits Google total tokens above prompt+visible completion; M4 report documents observed compatibility thought/cached attribution gaps. Do not infer billing output simply from token-count differences without authoritative mapping.

Owner-approved monetary amendment, **M5 only**, recorded in master revision 2.4:

> For M5, when the applicable account tariff or provider compatibility usage-to-billable-unit mapping cannot be established, monetary `estimated_cost` may remain null with `cost_source: unavailable`, reason, investigated official source/date and actual per-attempt calls/known-partial-unknown usage/latency. A known public tariff must still be reported, never described as missing. Where mapping is authoritative compute an offline estimate separately from billed cost. Unknown cost is not zero/free or a numeric spend guarantee. No other exit gate, provider route or historical evidence is waived.

The approved amendment closes only the monetary-provenance prerequisite, not fresh G6 measurements. The 36-attempt ceiling bounds calls, not dollar spend; do not present an unsupported monetary ceiling. No billing-account access, purchase or permission changes authorized.

### Reproducible startup and interview

One new `scripts/demo-up.sh` entrypoint invokes existing Compose/preflight through an explicit approved isolated project/private override and environment file; rejects main/owner project for this milestone. Validate Settings/configuration privately without printing secrets; build pinned API/web/worker, start PostgreSQL/MinIO and wait before minio-init, start Qdrant, apply forward migrations twice **before worker**, run native processing preflight/warm, then start API/web/isolated worker with health checks and print URL/readiness results. It must not pull/switch embedding models, seed private data, auto-generate, auto-import or claim owner jobs.

Keep `/health` process liveness; add a small read-only `GET /ready` in the existing API for master §19, never a new service. Response contains only safe dependency states and request_id: PostgreSQL revision/connectivity, private bucket accessibility, Qdrant schema, native runtime/model identity and loaded/cold state, generation configuration/catalog-access status. Checks share one ≤15-second deadline, no prompts, owner queries, model loading, collection creation, storage writes or paid generation; catalog access is a bounded authorized non-generation request to the configured validated route. Return 503 for a failed/unconfigured required dependency and 200 for successful dependency/access checks. Explicit `generation_execution:"unverified"` remains in either response: HTTP200/readiness access is not fresh hosted generation qualification. No endpoint promises that a subsequent paid call will succeed.

The startup CLI separately runs the approved mutating processing preflight/storage probe and warm embedding/vector check, then prints each result and whether a fresh approved application qualification has actually been observed. No config/catalog/health success is substituted for that evidence; a startup without fresh role evidence prints qualification pending. The first approved application case supplies provider execution evidence without an extra paid ping. Observe cold loading only when naturally cold or on a separately authorized isolated instance; never unload/reconfigure the shared main model to manufacture cold evidence.

Runbook has cold/warm prerequisites, exact project/override/ports/source hashes/model identity, public source preparation and expected journey, failure/cooldown recovery, safe shutdown without-v, existing caps and shared-host limits. Interview journey: real sign-in→Reader supported citation→explicit Related search→explicit Add of actually relevant unowned returned result→real processing ready→return to active Reader→select1–3→directions→active and selected-paper exact jumps→Escape/reload. If no relevant result/import/provider is available, show honest limitation and preserved last evaluated result only as replay, never call a cached fixture a live successful journey.

## 11. Exit gates and evidence classes

| Gate | Required evidence; automated checks are supporting only |
|---|---|
| G1 Selection/security | Automated real temporary-PostgreSQL tests and actual isolated HTTP A/B sessions: auth/CSRF/Origin/revocation, empty/duplicate/active/overrange/foreign/random/unready/mixed selections, zero dispatch until entire selection valid, quota/concurrency/lease boundaries. Synthetic sessions not real Google acceptance |
| G2 Retrieval/citation/persistence | Real native/PG/Qdrant/MinIO source-pinned retrieval; exact tuple sets, raw fragments/page/box equality, accepted result/citation GET and reload; selected source/current identity, wrong-version/cross-product/ambiguity/multipage negative checks. Controlled corruptions never touch main |
| G3 Real Research route | Approved primary application POST→transport→graph R1–R8; supported results/refusal/adversarial containment/subsequent valid, actual counters/usage/latency; separately labelled local HTTP malformed/unsupported/repair/exhaustion. No demand to manufacture naturally malformed provider output |
| G4 Failure/recovery | Actual controlled socket503/429/header/body/EOF/timeouts and downstream disconnect; no post-delta repair/third pass/fallback/late completion, persisted winner/draft/no accepted failed citations, slot released, explicit subsequent request usable |
| G5 Production browser/end-to-end | Real owner-completed Google sign-in plus actual official Discovery→explicit Add→worker ready→selection→Research→exact current/selected PDF/version jumps. Keyboard/Escape/focus/reload/popstate/return-active, widths/states/one-main/overflow/contrast/reduced-motion; recorded visual and authenticated server-backed state. Owner sign-in/manual portions attributed separately |
| G6 Evaluation/cost/demo | Frozen corpus/annotation hashes, separated metrics/rubrics/full case ledger and limits,36attempt budget compliance, applicable numeric estimate OR separately approved M5-null amendment, startup/runbook actually exercised cold/warm and safe recovery. Missing account mapping not disguised |
| G7 Suites/build/review | All affected backend/frontend suites, production API/web/worker build, migration twice on populated isolated0007 with source/import identities preserved, final changed-path smoke and targeted review without blocking findings |

Evidence labels: automated test; controlled fixture/local HTTP; agent-observed actual runtime; actual hosted provider with controlled input; actual official API; browser observation; owner-reported manual acceptance. Record safe request/run IDs, command/journey, source/image/commit/runtime/model identities, expected→observed, counts, usage source/completeness, latency/cost provenance and blockers. Never log prompts, quotes, paper text, credentials, cookies, object keys or private screenshots to Git.

All G1–G7 and owner review must be evidenced to claim Verified. Approval changes only design/planning status by map rules; implementation without complete gates stays Implemented. No M1 promotion or Q0 rewriting; no silent exception propagation. Main migration/worker/cutover/publication require a later independent authorization.

## 12. Approved owner decisions — 2026-10-04

1. Both documents approved: version pinning, source-balanced RRF/8chunk24k+24k caps, safe insufficiency failure, incremental provisional ideas, four-table persistence/reload and PDF-vs-Discussion URL separation.
2. Explicit M5 prerequisite exception while M1 remains Implemented; detailed M1 record stays separate. Stale current M3 coverage rows may be corrected by existing closure evidence only.
3. M5's own real Research plus controlled-negative qualification/evaluation composition and small-corpus quality floors approved. M3/M4 gates and product route unchanged.
4. Exact M5-only monetary-null amendment approved; unknown account/billing mapping remains a disclosed measurement limitation, not numeric billed-cost evidence.
5. Isolated stack/migrations/public-paper intake/processing/native warm checks and **36-hosted-attempt primary campaign** authorized, no main mutation or shared-runtime reconfiguration. M4 budget does not carry over; shared-native restart requires separately scoped approval.

Choices derivable from repository conventions need no additional approval. Owner approval establishes design/planning and bounded isolated execution, not passing gate evidence or authorization to commit/publish.
