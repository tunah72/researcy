# Researcy M1 acceptance — 2026-09-24

## M2 handoff evidence addendum — 2026-09-27

The owner explicitly confirmed successful testing with **two real Google accounts** and requested promotion of M1 to `Verified`. Treat this as owner-reported evidence, not an agent-observed OAuth journey. Account email addresses are intentionally omitted from tracked evidence; identity remains issuer + `sub`, not email. The owner also reaffirmed successful arXiv `2603.09689` import and the previous acceptance result.

This resolves the previously unknown availability/use of two real identities. The supplied handoff does not describe each §7 gate's observed result: cross-owner direct-ID denial with swapped owners, both imports and original integrity, Library persistence in a new session, and old-cookie replay after logout. The earlier local-session HTTP/DB/MinIO evidence below remains valid but is not relabelled as real-Google-user evidence.

**Gate reconciliation remains open; technical status stays `Implemented` pending that record or an explicitly approved acceptance-contract amendment.** Do not rerun owner-confirmed checks merely to confirm them. Close the record using retained owner results for the missing journeys; execute only genuinely untested probes with owner authorization. M2 specification work can proceed; M2 implementation requires the prerequisite decision plus separate spec and plan approvals.

Handoff inspection: `git fetch origin` succeeded; `main`, `origin/main`, `fix-m1-remediation`, and `origin/fix-m1-remediation` were at `c39cd1725ceed662612c1fb7c7d76ea83747818b`. `docker compose ps -a` showed the Researcy services stopped. No owner data, service, M1 worktree, or unrelated local file was changed. The deleted worktree guideline was not restored.

**Owner prerequisite exception — 2026-09-28:** The owner approved the M2 plan and explicitly permitted M2 implementation while supplementing the M1 record separately. The M1 documentation gap no longer blocks M2 execution. This is not a claim of new M1 probe results and does not change M1's technical status.

## Current owner acceptance — 2026-09-27

**Owner acceptance: PASSED.** After testing the remediated UI and successfully importing `2603.09689`, the owner explicitly requested marking M1 passed, committing by work item, merging into `main`, and synchronizing local/remote branches. The owner explicitly required preserving the remediation worktree. This records the owner's acceptance, not an invented agent-observed Google journey.

**Technical gate status: Implemented; complete Verified evidence remains outstanding.** The supplied confirmation establishes successful owner-side arXiv import. It does not supply the detailed two-real-Google-user isolation, both-import, new-session Library and logout-replay record required by the approved gate. Historical observations below are preserved. No M2 implementation is authorized by this acceptance/integration request.

### Requested-paper incident and recovery

The owner's first `2603.09689` attempt encountered metadata HTTP `406` from `export.arxiv.org`, before PDF download. A bounded diagnostic observed an empty body, no `Retry-After`, and `X-Cache: MISS, MISS`. The same query later returned `200` with both explicit Atom and default Accept headers; this does not establish a header defect or identify arXiv's internal rejection cause. No speculative header patch, hidden retry, mirror, or source fallback was introduced.

A separate local smoke identity then imported the exact URL through the running web proxy/API: `202`, request ID `cfa2fc49-17d5-4025-a788-e841669a6db6`, **AutoViVQA: A Large-Scale Automatically Constructed Dataset for Vietnamese Visual Question Answering**, source **v2**, original **3,276,158 bytes**, no screening warning. MinIO size and binary SHA-256 matched PostgreSQL. The smoke identity, relational records and original were removed afterward. The owner subsequently confirmed successful import in their own session; their data was not altered.

Upstream rejection remains an external availability risk. The application backs off and preserves explicit retry semantics; owner acceptance is not a guarantee that arXiv will never return `406` again.

### Integration authorization and pre-merge verification — 2026-09-27

The owner authorized committing by work item, pushing the remediation branch, merging/pushing `main`, and synchronizing local/remote state. The worktree and branch must remain; no prune/removal is authorized. Existing local assistant-context files are unrelated to this remediation and are excluded from commits.

Fresh checks on the integration tree: `uv run --frozen pytest tests -q` — **193 passed, 1 skipped**, five existing SWIG deprecation warnings; `npm test` — **32 passed**; `npm run build` — production compilation, TypeScript and prerendering passed. The skipped case is the opt-in real-network pytest; the actual requested-paper success is recorded separately above.

Work-item commits: `8ef7193` arXiv coordination/acquisition failures; `7f0cfe5` proxy retry guidance; `9af99d0` reader-facing onboarding and Library. Specification amendments, owner acceptance and evidence are a separate documentation commit. The unrelated newer `main` change removing the Git-worktree guideline must be preserved, not restored from this older worktree.

## Historical result — 2026-09-24

M1 implementation is complete. M1 remains **Implemented, not Verified** because the required two-real-Google-user acceptance gate has not been executed. Owner OAuth values are configured locally, but two real approved Google test identities were not available to this session. Synthetic/local sessions below are smoke evidence only and do not replace the four exit gates.

## Historical focused validation — 2026-09-24

| Check | Observed |
|---|---|
| Schema upgrade twice | Passed in the running API container |
| API suite | `170 passed, 1 skipped` |
| Web consumer suite | `9 passed` |
| Web production build | Next.js 16.3.6 build passed, including bounded `/api/papers/arxiv` |
| Dependency audit | `npm audit`: zero vulnerabilities |
| Complete image build | `docker compose --profile web up -d --build`: API and web built and started healthy |
| Unauthenticated API | `/api/me` returns `401` in focused auth coverage |
| Private bucket | Anonymous HTTP access returned `403` |
| Real arXiv | Same-origin `POST /api/papers/arxiv` for `1706.03762` returned `202`, `queued`, resolved `v7`; object was 2,215,244 bytes with PDF magic and DB-matching SHA-256 |
| Real PDF through UI | Chromium upload returned `202`; one paper/version/queued job and one private object; byte count, PDF magic and binary SHA-256 matched DB |
| Final review remediation | Upload auth now precedes multipart parsing; the authenticated request body is capped before spooling; synchronous PDF/MinIO/PostgreSQL acceptance runs in Starlette's thread pool; the arXiv proxy caps JSON requests at 16 KiB; unversioned canonical races retain unversioned semantics; production startup requires a trusted HTTPS Google callback and all OAuth settings. Scoped re-review: CLEAN. |

Temporary smoke users, sessions, database rows, MinIO objects, browser cookies and generated PDFs were removed after observation. No credentials, cookies, tokens, full PDFs or private text are recorded here.

## Historical browser evidence — 2026-09-24

Real Chromium inspected landing, sign-in, empty Library, populated Library, Add paper and paper detail at 375, 768, 1024 and 1440 px.

- Exactly one `main#main-content` and a resolving skip target on every inspected surface.
- Focused skip link measured 198×48 px.
- No inspected non-inline control below 44×44 px.
- Zero page-level horizontal overflow at every width.
- Bundled Crimson Pro headings and Atkinson Hyperlegible body font loaded.
- Empty, query-empty, populated, accepted, warning and detail states rendered server-backed values.
- Queued DB stage rendered as “Waiting for processing”; no Reader, fake progress or processing retry appeared.
- Logout removed cookies; replaying the old local smoke cookie redirected to `/sign-in?expired=1`.

## Historical four exit gates — 2026-09-24

| Gate | Status | Evidence / blocker |
|---|---|---|
| 1. Two-user ownership isolation | BLOCKED | Requires two real approved Google identities in separate browser contexts. Owner-scoped API behavior is covered by tests and local smoke, but those do not satisfy the gate. |
| 2. Both imports and original PDF persistence | BLOCKED | Real arXiv and PDF persistence checks passed with temporary local sessions. Gate still requires those imports under the real two-user OAuth journey. |
| 3. Library matches committed database state | BLOCKED | Browser/DB cross-check passed for a local smoke identity at all required viewport widths. Gate still requires refresh/new-session observations under real Google authentication. |
| 4. Server-side logout revocation | BLOCKED | Local smoke proved cookie deletion and revoked-cookie rejection. Gate still requires proving user B remains valid during the real two-user journey. |

## Historical required owner action — 2026-09-24

Provide two approved Google test identities and complete sign-in for A and B in separate browser contexts at `http://localhost:3000/sign-in`. Do not share passwords, raw cookies or tokens. Once both contexts are authenticated, resume Task 8 to execute and record the four real gates. The delivery map must remain at `Implemented` until all four gates pass.

## 2026-09-27 remediation scope and visual target

The owner authorized M1 remediation and delegated design choices on 2026-09-27. This section is the implementation/verification checklist, not a claim that its acceptance checks have passed.

### Authority

- Master specification: product and architecture authority; historical approval-time statuses remain unchanged.
- Approved M1 child specification: behavioral contract.
- Delivery map: current milestone and requirement status.
- This report: observed evidence, including explicit limitations.
- V4 and The Moonlight references: design archives/inspiration, not pixel-perfect or normative contracts.

### Chosen implementation

1. `apps/api/researcy/papers/arxiv.py`: serialize official metadata/PDF requests in the existing single-process API, enforce at least three seconds between requests (including redirects), and respect upstream cooldown. Identify the application rather than impersonating a browser. Treat upstream 406/429 as a retriable `503 ARXIV_UPSTREAM_ERROR` with `Retry-After`; do not automatically retry or fall back to another provider. Correlate safe host/status-only diagnostics with the application request ID. Preserve bounded acquisition and the existing atomic intake boundary.
2. `apps/api/tests/test_arxiv.py` and `test_intake.py`: demonstrate 406, pacing/cooldown and failure-atomicity regressions before implementation; verify failed acquisition creates no paper/version/job/object and the same key can subsequently succeed.
3. `apps/web/src/lib/api.ts` and M1 components: preserve `Retry-After`, show actionable errors with a secondary request ID and a manual retry countdown; same payload keeps its key, changed payload receives a fresh key. Keep pending copy honest about the synchronous API rather than inventing timed sub-stages.
4. M1 visual target: warm paper/ink, restrained navy actions, Crimson Pro limited to wordmark/editorial display, Atkinson Hyperlegible for UI and metadata. Landing/sign-in explain the current private-library capability. Library has one clear Add paper action, title/author search and a compact, readable list. Add Paper is an inline panel with exactly arXiv and PDF choices, keyboard navigation and managed focus. Queued detail, loading/empty/query-empty/error, accepted/warning, and logout pending/failure use the same visual vocabulary. No list/grid toggle, extra filters, Reader, worker, `ready`, or fabricated processing progress.
5. Parent verification: run affected suites and the production build; rebuild the running stack; exercise actual `2303.09833` acquisition, same-key replay, and PostgreSQL/MinIO SHA-256/size equality. Browser-check all M1 surfaces at 375/768/1024/1440 px for one resolving main landmark, focus/keyboard behavior, 44px non-inline targets, reduced motion and no horizontal overflow.
6. Evidence reconciliation: recover historical A/B evidence where available and record new probes separately. Do not promote M1 or SYS-01/AUTH-01/AUTH-02/LIB-01/UX-01 to `Verified` without the real two-Google-user gate record. Leave M2-owned SEC-01/JOB-01 unchanged.

The three-second minimum follows the [official arXiv API manual](https://info.arxiv.org/help/api/user-manual.html#_start_and_max_results_paging). Process-local pacing matches the checked-in single-process Uvicorn/Compose deployment; multiple API replicas/processes would require shared coordination before deployment.

### Historical evidence reconciliation

Reviewed the previous implementation transcript, [merged PR #1](https://github.com/tunah72/researcy/pull/1), this report, the delivery map, and the available local artifact directories. The owner's historical confirmation was “Tôi đã kiểm thử xong. Kết quả ổn.” The merged PR explicitly records that manual smoke passed and the real two-account gates remained blocked. No retained A/B request-ID, DB ownership, or old-cookie replay record was found. The current remediation request reports that gates passed; that attestation is retained, but missing measurements cannot be reconstructed as observed facts.

Before creating remediation smoke fixtures, read-only inspection of the running `researcy` database found one Google-issuer user with a numeric subject, one unrevoked active session, and one uploaded paper. This is an environment inventory, not proof of a previous two-user journey. Existing user data and that session are not remediation fixtures and must not be altered.

### Current observed evidence — 2026-09-27

Worktree: `.omp/worktrees/m1-remediation`, branch `fix-m1-remediation`, base `c3ed3f4`. Runtime: macOS arm64, Docker Compose project `researcy`, real PostgreSQL and private MinIO, container Node 22.14.0 / Next.js 16.3.6, Python 3.12. Host frontend checks used Node 25.8.1 and npm 11.11.0. No migration/schema change, M2 service, Reader, processing worker or model-route change is included.

The following observations use two explicitly labelled **local smoke identities**, not Google identities. The browser requests go through `http://localhost:3000` and the real Next.js proxy/FastAPI/DB/MinIO stack.

#### Real `2303.09833` acquisition

- Two initial attempts returned safe `503 ARXIV_UPSTREAM_ERROR`, request IDs `41205bf7-be18-407f-8098-1c4b18a2d650` and `e23b9c3e-25d7-4f38-a70b-446b63d738d2`. Metadata resolved `v1`; the official PDF response announced 13,901,281 bytes but closed after 2,097,152. No arXiv paper/version/job/idempotency outcome or object was accepted. This transient transport failure is retained as observed evidence, not described as a deterministic arXiv outage.
- A host diagnostic subsequently received all 13,901,281 bytes from the same official `https://arxiv.org/pdf/2303.09833v1` endpoint. A **manual Retry in the existing browser form**, with no URL/provider fallback, then returned `202`, request ID `37c427ea-f63c-4f06-b1e6-6d88ea87f5af`.
- Persisted paper `66dc0476-d6be-4824-b4ea-955e8cfa8438`, immutable version `82529f39-1fb5-4d05-8214-6b982d72adfe`, queued job `1e796cd5-4026-4366-9625-33be903cdd6b`. Source `2303.09833`, version `v1`; actual metadata title “FreeDoM: Training-Free Energy-Guided Conditional Diffusion Model.”
- Owner/paper/version foreign-key relationships matched. MinIO bytes and DB byte size both **13,901,281**; streamed MinIO SHA-256 and DB SHA-256 both **`ef82614c0587eb9c0d269672c29ca65072fea8497e2c3d3a50102085c818440f`**; `%PDF-` magic present; anonymous object access `403`; foreign-owner internal original lookup denied. Object keys are deliberately omitted.
- Same-key/same-payload replay returned `200`, request ID `3a61887b-eefa-484c-b4a6-73e68b3e39a8`; changed payload with that key returned `409 IDEMPOTENCY_CONFLICT`, request ID `08099f7b-2d0f-4ac8-ad95-fc90588e00d5`. Paper/version/job/idempotency counts did not change.
- Library refresh, a fresh same-owner session, and the queued detail all displayed the committed record, version `v1`, and “Waiting for processing,” never `ready`.

#### PDF, ownership, CSRF and logout probes

| Probe | Observed result |
|---|---|
| Supported PDF through browser | `202`, request ID `d0717053-b55e-4269-ac41-2c1cf1b29ecd`; 1,002 bytes; SHA-256 `cdd80726aad5f64eaf334a014abfca04dc44f37357e158b1864b6d84b405154d`; MinIO and DB agree |
| Low-text PDF through browser | `202`, request ID `e5d24713-eaad-4779-9775-531c7da56d4f`; persisted `LOW_TEXT`, 890 bytes; SHA-256 `b5a4595475bf8f82c9eafafd8ad004a1e97e0aeb5e965608a864aa236a0f72db`; warning survives reload/detail |
| Image-only PDF | `422 PDF_NO_TEXT`, request ID `538b0417-0592-4070-8f29-fa16816baa77`; actionable field-associated error, no acceptance |
| B reuses A's upload idempotency key | Own paper accepted `202`, replay `200`; no cross-owner outcome returned |
| A/B API isolation | Lists disjoint; foreign detail and random nonexistent detail both indistinguishable `404` apart from request ID; cross-owner title search empty |
| A/B browser contexts | An explicitly isolated Chromium context with B's local session displayed only B's committed paper; A displayed only A's papers |
| CSRF | Missing and incorrect tokens for both import routes, for both local identities: eight `403`; anonymous `/api/me`: `401`; counts unchanged |
| Actual browser logout | A returned to `/sign-in`; database session row revoked |
| Old A cookie replay | `/api/me` and `/api/papers`: `401`, request IDs `8c950ca5-b0b1-4373-814f-e19ffadcb320` and `c20024e5-39df-422d-a2db-4d20a4c73887`; mutation `401`, request ID `87362d95-e9ba-4a79-8682-a50f63108121`; counts unchanged |
| B remains valid after A logout | `200`, request ID `00ec0b44-3c41-4871-b05d-95b67dc0c478` |

These exercise the ownership and revocation mechanisms, but **do not substitute for Google OAuth/provider consent or the required two-real-Google-user journey**.

#### Browser measurements

Chromium checked 375/768/1024/1440 px on landing, sign-in, upstream-error Add Paper, accepted upload, accepted warning, persisted Library, query-empty, queued detail (including actual arXiv), route loading, Library dependency error and logout failure. Exactly one resolving `main#main-content`, zero page-level horizontal overflow, and no inspected non-inline control below 44×44 px. Screenshots visually inspected at desktop and narrow mobile sizes. Focused skip link measured 198.156×48 px with visible outline; native reduced-motion emulation reduced transitions to 0.000001 s.

Library dependency failures, logout failures and the three-second arXiv cooldown were **controlled browser response injections**, not real upstream events. The cooldown scenario showed safe application copy and request ID rather than raw `406`, disabled Retry during the countdown, then enabled it. Actual pending acquisition copy describes one synchronous request, without fabricated progress percentages or timed download/validation steps.

Additional controlled pending-response checks at all four widths covered arXiv submission, PDF submission and logout: one resolving main, zero overflow, disabled submit/logout and locked import tabs/close while requests were outstanding. Visible copy was “Importing from arXiv...” / “Uploading PDF...” / “Signing out...”, not fabricated sub-stage progress. ArrowLeft/ArrowRight/Home/End moved focus and selection between the two import tabs; a selected PDF remained selected after a round trip. Sign-in expired/error query states were also measured at all four widths without contacting Google or granting consent.

### Current gate decision

**M1 remains Implemented, not Verified.** SYS-01, AUTH-01, AUTH-02, LIB-01 and UX-01 remain at their evidence-supported `Implemented` status. SEC-01/JOB-01 remain unchanged and M2-owned. Real `2303.09833`, DB/MinIO integrity, both import mechanisms, local A/B ownership and revocation now have direct evidence above. The only authentication acceptance prerequisite still unavailable is a retained or newly executed **two-real-Google-user four-gate record**; owner attestation is recorded, not replaced with invented observations. No historical approval or Q0 evidence is rewritten.

## 2026-09-27 approved reader-facing revision

The owner approved the remediation design and explicitly required a reader-facing UI without system terminology or internal states. This revision supersedes the earlier inline-panel/request-ID presentation target above; earlier observations remain historical. Master §12.2 and the M1 child specification record the approved presentation amendment without changing API/security/persistence contracts.

Work continues in `.omp/worktrees/m1-remediation` on `fix-m1-remediation`, preserving the prior uncommitted changes. No merge/push is implied. The original V3 specifies Google sign-in as a small modal; V4 supplies Library hierarchy, excluding its filters/list-grid and future Reader controls. The saved Moonlight screenshots and live `https://www.themoonlight.io/en` were inspected; its Get Started opens an overlay. Researcy keeps its own editorial visual system and Google-only authentication.

### Backend verification in this revision

- `uv run --frozen pytest tests/test_arxiv.py -q -k http_date_retry_after`: RED, two failing cases proved that metadata/PDF `503` discarded an upstream HTTP-date cooldown. After the fix, `uv run --frozen pytest tests/test_arxiv.py -q`: **111 passed, 1 skipped**.
- `uv run --frozen pytest tests -q`: **189 passed, 1 skipped**, with five PyMuPDF/SWIG deprecation warnings. The optional real-network pytest remains skipped; the explicit live import below is separate evidence.
- `docker compose --env-file ../../../.env -p researcy up -d api` uses the owner's root configuration without copying or displaying secrets. Existing PostgreSQL/MinIO volumes were preserved; the API image was rebuilt from this worktree. `docker compose -p researcy exec -T api uv run --no-sync alembic upgrade head` succeeded.
- Live API import of official arXiv `1706.03762` using a separate local smoke identity returned `202`, request ID `3854deaa-725f-4067-9e59-15fa5640e4da`, source `v7`, persisted `queued`. Paper `5b6349dd-8202-4822-8082-4d8dc5482618`; document version `e03dda64-9dde-404c-9203-72c48251e574`; job `c653163b-cbb7-4031-95ce-3526d93aa86e`.
- Original PDF: **2,215,244 bytes**, SHA-256 **`bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`**. Streamed MinIO bytes/hash match PostgreSQL; PDF magic and source edition verified. Object keys and tokens are omitted.
- Same-key replay returned `200` and the same paper; changed payload with that key returned `409`. A second local identity received `404` for both that paper and a nonexistent ID with the same error code. Invalid CSRF returned `403`.
- The limiter remains intentionally scoped to the checked-in single-process Uvicorn deployment. It is not cross-process/cross-machine coordination; additional API processes or independent arXiv callers require shared coordination before deployment. `406` is described as a temporary rejection, not proof of rate limiting. `406`, `429`, and `503` back off without hidden retries; upstream `Retry-After` applies to subsequent callers.

These local-session probes do not establish the two-real-Google-user gate.

### Reader-facing implementation and verification

- Landing → Get Started / Sign in → native Google-only dialog; direct `/sign-in`, expired and failed callbacks reuse that surface. The landing illustration is a static Library preview, not a working Reader or invented citation. Library uses compact divided rows and one persistent Add Paper trigger; the desktop panel is anchored at 440px, stacking on narrow screens.
- Reader-facing errors are selected from safe, useful messages rather than provider `message`/codes/request IDs. Unknown PDF warnings never render raw diagnostic text. Saved-item feedback does not expose job/stage/version UUIDs. Missing metadata remains unknown; the details view states that reading is unavailable.
- Behavioral RED before implementation covered modal open/close/focus and navigation, stale-search ownership of results, raw error suppression, keyboard tabs, idempotency and cooldown boundaries. The browser additionally exposed a skinny desktop panel and an unexplained opposite-tab account cooldown; both were corrected. The latter has a two-direction failing-before/passing-after regression. The obsolete alternate empty-state trigger and its callback-only test were removed.
- Final `npm test` in `apps/web`: **32 passed across 3 files**. Native modal interactions, direct-entry errors, bfcache recovery, latest search responses, changed/same-payload retries, arXiv-only versus account-wide cooldowns, pending dismissal, auth errors, and safe feedback are covered.
- `docker compose --env-file ../../../.env -p researcy --profile web build web` succeeded on the pinned **Node 22.14.0** image, including Next.js production compilation, strict TypeScript and prerendering. `docker compose --env-file ../../../.env -p researcy --profile web up -d --no-build web` served the built application at `http://localhost:3000`; no development preview is required.

### Real browser and storage observations

Chromium was exercised against the production web/API/PostgreSQL/MinIO stack with two clearly identified local smoke accounts, not real Google identities:

- The second identity initially saw an empty Library. Importing `1706.03762` through the actual browser `/api/papers/arxiv` path succeeded and displayed the persisted paper. No intercepted or synthetic provider result was used for this successful acquisition.
- Browser uploads accepted the generated readable PDF and the low-text PDF; the latter's useful warning survived refresh and navigation to its details. An image-only PDF was rejected with a selectable-text instruction and no raw backend diagnostics.
- All three originals for the first identity matched PostgreSQL's binary SHA-256: arXiv **2,215,244 bytes**, readable upload **1,198 bytes**, low-text upload **897 bytes**. The first throwaway comparison incorrectly compared a hex string with `bytea`; comparing digest bytes corrected the probe, not application data. Anonymous MinIO access returned `403`; cross-owner original access was denied.
- Title search, no-match state and clearing the query were exercised. One skip link and one resolving `main` were observed. Landing, dialog and Library/import were measured at **375, 768, 1024 and 1440px** with no horizontal overflow. Desktop and mobile screenshots were visually inspected; screenshots containing smoke-account state were not added to Git.
- Arrow keys switched import tabs; Escape dismissed the idle panel and restored Add Paper focus. Native dialog exposed only its own controls while open; Escape returned focus to Get Started. Direct failed/expired sign-in links showed safe prompts; dismissing direct entry returned home.
- Clicking Continue with Google reached **`accounts.google.com/v3/signin/identifier`** through the real same-origin auth path. No Google credentials, account selection, consent, or provider safety prompt was submitted.
- Real browser logout revoked the second local session: replay returned `401`, while the first identity remained authenticated (`200`). The browser then displayed the sign-in dialog.

**Gate boundary:** the four-gate detailed journey with two real Google accounts remains unrecorded. These checks strengthen remediation evidence but do not promote M1 beyond **Implemented**.

Controlled browser response probes (explicitly not live arXiv acceptance) verified that an upstream cooldown survives a changed identifier without disabling PDF upload, while an account-wide quota disables and explains both tabs. The corrected production image displayed the opposite-tab countdown. Reduced-motion emulation reported `scroll-behavior: auto` and a `0.000001s` button transition. The mobile wordmark wrap found visually was corrected and rechecked in the rebuilt image at 375px: one-line brand, 44px control height, no overflow.

Cleanup removed only this run's two local smoke users and their cascading relational records, four private originals (each confirmed absent), and the three generated PDF fixtures/temp directory. Existing user data and Docker volumes were preserved. The production stack remains running for owner inspection; no commit, merge, push, or branch removal was performed.

### Final review and restart

Independent review found oversized numeric `Retry-After` could escape as an exception and a trickling response could monopolize the limiter. Four RED regressions demonstrated these failures. Numeric parsing now rejects unrepresentable values into the existing 60-second backoff; limiter acquisition waits at most 60 seconds, and response streaming checks a 60-second elapsed deadline between chunks without fixed-size buffering. Socket inactivity timeout remains 15 seconds; this is not a hard cancellation guarantee for arbitrary header trickles.

Frontend review corrections retain the authenticated profile when only paper loading fails (so Sign Out remains available), keep ticking countdowns outside assertive alerts, describe upload transport failures without blaming the PDF, and disable retry without the required input.

After these corrections: backend **193 passed, 1 skipped, 5 existing SWIG warnings**; frontend **32 passed**. Full `docker compose --env-file ../../../.env -p researcy --profile web up -d --build` succeeded, including production TypeScript/build. Compose reports API/PostgreSQL healthy, web running on localhost:3000, and MinIO running. A controlled production-browser paper-list failure preserved enabled Sign Out and safe feedback. A fresh live acquisition inside the rebuilt API retrieved `1706.03762v7`, **2,215,244 bytes**; its temporary PDF was removed. Existing persisted user data remains intact.
