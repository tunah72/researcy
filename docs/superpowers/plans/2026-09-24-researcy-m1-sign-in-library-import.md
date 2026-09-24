# Researcy M1 Sign-in, Library, and Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real Google user signs in, imports a supported arXiv paper or PDF into a private, database-backed Library, and cannot access another user's resources.

**Architecture:** Next.js renders the landing, sign-in and Library from one browser origin; `/auth/*` and `/api/*` reach the FastAPI modular monolith by same-origin proxy. PostgreSQL owns identity, sessions, imports and the initial `queued` intake row; a private MinIO bucket holds verified immutable original PDFs. M1 screens and accepts PDFs but does not process them to `ready`.

**Tech Stack:** Python 3.12, FastAPI/Pydantic 2, psycopg 3, Alembic migrations, Authlib/Google OIDC verification, PyMuPDF initial screening in an isolated subprocess, boto3 S3-compatible MinIO client, httpx, pytest, Next.js/React/TypeScript, Docker Compose, PostgreSQL, MinIO. Resolve compatible versions and commit lockfiles in Task 1; do not reuse the deleted Q0/Q0.1 probe as production code.

**Spec:** `docs/superpowers/specs/2026-09-24-researcy-m1-sign-in-library-import-design.md` (approved), subordinate to `docs/superpowers/specs/2026-09-18-researcy-system-design.md` revision 2.0; `docs/superpowers/specs/2026-09-18-researcy-delivery-map.md` controls gate/status changes.

## Global Constraints

- Work in the existing isolated `m1-sign-in-library-import-spec` worktree; do not edit Q0 evidence or implement M2–M5. A task is complete only after its own RED → GREEN, smoke check, review, and commit; reviewer is the gpt-6-sol coordinator, implementer is requested as gpt-6-luna when the agent interface supports that model selection. Do not falsely claim a model identity if the interface cannot select it.
- Keep implementation minimal: reuse stdlib and the selected stack; add no speculative abstraction, service, UI control or test unrelated to an observable M1 contract. Prefer one direct path and a small reviewable diff without weakening security, durability or the four gates.
- Human-only setup is a hard stop at first encounter: Google Cloud OAuth consent/client, authorized redirect URI, client secret, two real Google test accounts and access approvals must be configured by the project owner. Never create accounts, operate the owner's console, grant permissions or manufacture credentials on their behalf. State the exact prerequisite and concise manual steps, then wait for confirmation; do not substitute mocks for a real exit gate or continue execution while this setup is pending. Local Compose/database/MinIO startup and code/test work remain agent-owned unless their setup actually requires the owner's access.
- One browser origin; FastAPI alone owns OAuth, opaque cookie sessions, CSRF and owner authorization. Google issuer + `sub`, never email, defines identity. Cookie session is host-only `HttpOnly`, `SameSite=Lax`, `Path=/`, and `Secure` except in explicitly local HTTP development. No application JWT or client-side storage credentials.
- Authentication uses Authorization Code + PKCE + one-use `state` + `nonce` and validates issuer, signature, audience and expiry. Every cookie-authenticated mutation requires a session-bound CSRF cookie/header comparison in constant time and trusted `Origin`; logout revokes the PostgreSQL session. Reject foreign and nonexistent paper IDs identically.
- PostgreSQL transaction creates paper, immutable document version, screening warning, minimal `queued` job and owner-scoped idempotency outcome atomically. No worker, lease, retry, parsing provenance, embeddings, vector index, Reader UI, `ready` label or fake progress in M1.
- Configurable initial screening caps: **25 MiB and 100 pages**. Reject zero-text, corrupt, encrypted, excess-page or oversize PDFs; for nonzero text under **200 total characters** or fewer than half the pages having **40 characters**, persist/display a warning rather than reject. These are unqualified warning heuristics; check representative PDFs. Non-root PDF inspection process with memory and wall-time bounds; no PDF actions/JavaScript.
- arXiv intake accepts only a canonical ID or official `https://arxiv.org/abs/…` or `/pdf/…` URL (optional `vN`), constructs provider requests server-side and verifies final official destination/version. Unversioned repeat returns the owned stored version, explicit different version returns `409`. No silent replacement, recommendation or auto-import.
- Upload receives bytes into a bounded private sink regardless of `Content-Length`. Original bytes are verified by size and SHA-256 after private MinIO write and before DB commit; server-generated immutable object key only. Failed commit compensates with best-effort object deletion and safe cleanup marker. No DB-visible accepted item points to a missing/mismatched object.
- Per-user import rate limits persist in PostgreSQL. All JSON errors contain stable `code`, safe `message`, `request_id`; no secrets, PDF text, raw provider responses or owner existence leaks in logs/responses. Success contains `request_id`. An accepted M1 paper remains `queued` / “Waiting for processing”.
- Editorial UI: Crimson Pro display, Atkinson Hyperlegible UI, warm paper/ink, navy actions/focus and restrained ochre; check actual contrast. One Library list/search/Add paper action; Add paper offers exactly arXiv and PDF. Keyboard, visible focus, labelled errors, responsive landing/auth/Library, no page overflow or fake Reader.
- M1 `Verified` requires **all four** recorded real-stack gates: two-user isolation; both imports + verified original PDF; DB-backed Library states; server-side logout revocation. Tests and historical Q0 evidence do not replace these. Status stays `Designed` until plan approval; becomes `Planned` only with that approval, `Implemented` after code without full evidence, `Verified` only with all four gates.

---

## Planned file map and interfaces

```
compose.yaml                         # M1 web, api, postgres, minio, private bucket init; no worker/Qdrant
.env.example                         # names and safe defaults, no live secrets
apps/api/{Dockerfile,pyproject.toml,uv.lock,alembic.ini}
apps/api/migrations/env.py
apps/api/migrations/versions/0001_m1.py
apps/api/researcy/{config,db,main,errors}.py
apps/api/researcy/auth/{oauth,sessions,routes}.py
apps/api/researcy/papers/{models,repository,routes,arxiv,screening,objects,intake}.py
apps/api/tests/{conftest,test_schema,test_auth,test_library,test_screening,test_arxiv,test_intake}.py
apps/web/{Dockerfile,package.json,package-lock.json,next.config.ts,tsconfig.json}
apps/web/src/app/{layout,page,sign-in/page,library/page,library/[paperId]/page}.tsx
apps/web/src/app/globals.css
apps/web/src/lib/api.ts              # browser API contract; no session-cookie read
apps/web/src/components/{add-paper,library-list}.tsx
apps/web/src/app/library/loading.tsx, apps/web/src/app/library/error.tsx
apps/web/src/components/library-interaction.test.tsx
apps/web/public/fonts/              # bundled licensed display/UI font assets
```

Paths in this map name ownership, not a demand for empty files: create only the files actually needed. Backend public interfaces (names and shapes used across tasks): `get_current_user(request, conn) -> UUID`, `require_csrf(request, conn, user_id) -> None`, `get_paper(conn, owner_id, paper_id) -> dict | None`, `list_papers(conn, owner_id, search) -> list[dict]`, `screen_pdf(path, media_type) -> ScreeningResult`, `put_original(owner_id, version_id, path, sha256) -> str`, `get_owned_original(conn, owner_id, paper_id, version_id) -> Iterator[bytes]` (internal authorization probe; never a public URL), `accept_pdf(conn, owner_id, key, operation, request_digest, source, metadata, screened_path) -> IntakeResult`. `IntakeResult` has paper_id, document_version, job_id, persisted stage/warning/version and created flag. Keep the body of an existing-item response authoritative from DB. Use UUIDs for resource IDs and opaque idempotency keys of bounded length. `request_id` is allocated by middleware for every request; cookies are named `researcy_session`, `researcy_csrf`, and `researcy_oauth` (the OAuth correlation cookie).

Task boundaries share the same DB schema and above contracts; execute serially. Each task implements and checks only its own surface; run whole-suite/lint/build once after Task 7, then the real-stack gate task. Tests must fail for a plausible behavior regression, not assert plumbing or source wording. All credentials/PDFs and test-state snapshots remain untracked; add safe ignore entries in Task 1.

### Task 1: Reproducible stack and M1 schema

**Files:** Create `compose.yaml`, `.env.example`, `apps/api/{Dockerfile,pyproject.toml,uv.lock,alembic.ini}`, `apps/api/migrations/env.py`, `apps/api/migrations/versions/0001_m1.py`, `apps/api/researcy/{config,db,main,errors}.py`, `apps/api/tests/{conftest,test_schema}.py`; modify `.gitignore` for local credentials, build outputs and private evidence. Web package, Dockerfile and routes belong to Task 7, not this database task.

**Interfaces:** Produce `get_conn()` managed PostgreSQL connection, request-ID/safe-error middleware, application `app`, configured 25 MiB/100 page limits, origin/TLS mode validation, and schema. `get_conn` is the only DB connection source for later tasks. Compose defines `web` for later but Task 1 starts only `api`, `postgres`, `minio` and private-bucket init; worker and Qdrant are M2+/later integration, not phantom M1 services.

- [ ] **Step 1 — RED:** Write migration integration checks against temporary PostgreSQL: double migration leaves schema unchanged; issuer+sub unique even with duplicate email; `(owner, canonical_arxiv_id)` and `(owner, idempotency_key)` unique; a job cannot point at another owner's document version; two jobs cannot point at one version; a paper cannot point at another paper's version. Example assertion:
  ```python
  with pytest.raises(psycopg.errors.ForeignKeyViolation):
      conn.execute(
          'INSERT INTO ingestion_jobs (owner_id, document_version_id, stage) VALUES (%s, %s, %s)',
          (owner_b, version_owned_by_a, 'queued'),
      )
  ```
  Run `uv run pytest tests/test_schema.py -q` with `cwd=apps/api`; expected RED because migrations/constraints are absent.
- [ ] **Step 2 — GREEN:** Create one forward Alembic migration: `users` (`UNIQUE(issuer,sub)`), `sessions` (keyed token hash, owner, CSRF verifier, issued/idle/absolute expiry, revoked), one-use `oauth_transactions`, `papers` (owner, source, canonical arXiv ID, active version), `document_versions` (owner+paper, SHA-256, byte count, private object key, source URL/version, warning and pending config), `ingestion_jobs` (`queued`, unique document version), `import_idempotency` (unique owner/key, operation, request digest and result IDs), `import_rate_limits` (owner/window/count). Use composite owner FKs/uniques, partial owner+canonical-ID uniqueness, deferred active-version FK as needed for the acceptance transaction. Explicitly constrain `queued` in M1; M2 migration extends stages. Compose private bucket has no anonymous read. Fail startup on missing production secrets or insecure cookie/origin config.
  ```sql
  UNIQUE (owner_id, idempotency_key);
  UNIQUE (document_version_id);
  FOREIGN KEY (owner_id, document_version_id)
    REFERENCES document_versions(owner_id, id);
  ```
- [ ] **Step 3 — CHECK:** Re-run migration tests, run `docker compose up -d --build postgres minio api`, `docker compose exec -T api alembic upgrade head`, `docker compose exec -T api alembic upgrade head`; expect API health response with request ID, but `/api/me` remains unregistered until Task 2 and the web service is not started before Task 7. Record exact commands/output in task report; do not mistake this for an M1 exit gate. Commit foundation and lockfiles.

### Task 2: Google OAuth, opaque sessions, CSRF and logout

**Files:** Create `apps/api/researcy/auth/{oauth,sessions,routes}.py`, `apps/api/tests/test_auth.py`; modify `apps/api/researcy/main.py` to register auth routes. No UI login simulation or fake production account.

**Interfaces:** Produce `get_current_user(request, conn) -> UUID`, `require_csrf(request, conn, user_id) -> None`; `GET /auth/google/start`, `GET /auth/google/callback`, `POST /auth/logout`, `GET /api/me`. Session lookup uses `HMAC-SHA256(server_lookup_key, raw_token)` with constant-time CSRF verifier, idle and absolute expiry checks, owner FK and revocation. One-use transaction state and correlation cookie are tied to a DB transaction and deleted/marked consumed before session issuance; callback redirect fixed to `/library`.

- [ ] **Step 1 — RED:** Tests use a local OIDC key set/token exchange boundary (not actual Google in the automated suite) and real PostgreSQL rows: valid code+state+PKCE+nonce yields a user/session; replayed/expired state or wrong nonce/issuer/audience/signature/expiry yields none; same email/different `sub` yields two users. Old cookie returns `401` after logout even when replayed; wrong/missing CSRF or hostile Origin returns `403` and keeps session. Example:
  ```python
  assert client.get('/api/me', cookies={'researcy_session': old}).status_code == 401
  assert client.post('/auth/logout', cookies=cookies, headers={'X-CSRF-Token': 'wrong', 'Origin': origin}).status_code == 403
  ```
  Run `uv run pytest tests/test_auth.py -q` in `apps/api`; expected RED on missing routes.
- [ ] **Step 2 — GREEN:** Use Authlib's OIDC/JWKS validation for Google ID token and explicit issuer/audience/expiry/nonce checks; authorization endpoint sends PKCE S256/state/nonce, token endpoint uses exact registered callback, OAuth transaction and correlation cookie are short-lived, one-use and `HttpOnly`. Generate separate CSPRNG session/CSRF secrets; store only keyed session lookup hash and CSRF verifier; host-only cookies with HTTPS `Secure` and local-only HTTP exception. `get_current_user` resolves DB state, not Google tokens; `require_csrf` checks header/cookie/session binding in constant time plus trusted Origin. Revoke in DB before clearing both cookies. JSON safe error envelope and request ID on API failures; callback safely redirects to `/sign-in?error=…` without raw provider text.
  ```python
  def session_lookup(raw: str, key: bytes) -> bytes:
      return hmac.digest(key, raw.encode(), 'sha256')
  ```
- [ ] **Step 3 — CHECK:** Re-run auth tests; start the service and confirm unauthenticated `/api/me` is `401`. If real Google OAuth client/redirect credentials are already configured by the owner, inspect `/auth/google/start` for PKCE challenge and host-only correlation cookie without exposing secrets; otherwise stop, give the owner the exact Google Cloud consent/client/redirect setup steps and wait before continuing. The **real Google two-account** journey remains Task 8. Commit auth after the check.

### Task 3: Owner-scoped Library reads and durable import quota

**Files:** Create `apps/api/researcy/papers/{models,repository,routes}.py`, `apps/api/tests/test_library.py`; register router in `main.py`.

**Interfaces:** Produce `get_paper(conn, owner_id, paper_id) -> dict | None`, `list_papers(conn, owner_id, search) -> list[dict]`, `take_import_slot(conn, owner_id) -> None`; GET list and detail with persisted stage/version/warning. Quota is reserved per authenticated user using atomic PostgreSQL row lock/window/accounting and yields safe `429` plus Retry-After; it is never the only in-process check. Task 6 calls `take_import_slot` after authentication/CSRF, before external acquisition.

- [ ] **Step 1 — RED:** In real DB insert two users and their queued papers; assert B list/search never contains A; B detail and nonexistent detail both `404` with same stable code/body shape; title/author search matches owned records only; null authors/year remain null; rate limit survives a new API process and cannot double-spend under concurrent requests. Example:
  ```python
  assert {p['paper_id'] for p in client_b.get('/api/papers?search=transformer').json()['papers']} == set()
  assert client_b.get(f'/api/papers/{paper_a}').json()['code'] == client_b.get(f'/api/papers/{uuid4()}').json()['code']
  ```
  Run `uv run pytest tests/test_library.py -q`; expected RED on missing owner-scoped repository.
- [ ] **Step 2 — GREEN:** Every query joins on `owner_id` and resource ID, never ID alone; search title/author server-side with bounded input, deterministic order, parameterized SQL and safe response serialization. Detail checks owner before any object-key lookup. Persist quota row/window and lock it before increment; reject at configured limit, return request ID and Retry-After. Use `get_current_user` dependency for all reads. No public object URL or speculative `ready` status.
  ```sql
  SELECT p.id, p.title, p.authors, j.stage, v.source_version, v.screening_warning
    FROM papers p JOIN document_versions v ON (v.id=p.active_version_id AND v.owner_id=p.owner_id)
    JOIN ingestion_jobs j ON (j.document_version_id=v.id AND j.owner_id=p.owner_id)
   WHERE p.owner_id=%(owner_id)s AND p.id=%(paper_id)s;
  ```
- [ ] **Step 3 — CHECK:** Re-run owner/quota tests; with two local DB fixtures request `/api/papers` and each detail via app client and compare persisted stage/version; `401` without session. Commit Library API.

### Task 4: Bounded PDF screening and private original-object boundary

**Files:** Create `apps/api/researcy/papers/{screening,objects}.py`, `apps/api/tests/test_screening.py`; use existing approved Q0 corpus only as representative *input* where locally available, not production parser code.

**Interfaces:** `screen_pdf(path, media_type) -> ScreeningResult(sha256, bytes, pages, title, warning)`; `put_original(owner_id, version_id, path, sha256) -> str`; `get_owned_original(conn, owner_id, paper_id, version_id) -> Iterator[bytes]` internal only. Screening receives a bounded private temporary file from the caller; errors carry safe status/code, not PDF text. `put_original` generates a fresh unguessable private key and verifies read-back byte count/hash (S3 ETag is not a content hash); `get_owned_original` performs owner+paper+version lookup before streaming object content.

- [ ] **Step 1 — RED:** Minimal PDFs exercise born-digital accept, zero-text `422`, encrypted/corrupt `422`, wrong signature/MIME `415`, 101 pages `422`, >25 MiB `413` and nonzero low-text warning; a subprocess timeout/memory exhaustion yields safe reject without an object/job. Store/read a PDF in private MinIO; read-back hash matches source; foreign owner/internal wrong paper cannot read, direct anonymous read fails. Example:
  ```python
  assert screen_pdf(low_text_path, 'application/pdf').warning.code == 'LOW_TEXT'
  with pytest.raises(PrivateResourceNotFound):
      get_owned_original(conn, owner_b, paper_a, version_a)
  ```
  Run `uv run pytest tests/test_screening.py -q`; expected RED on absent boundary.
- [ ] **Step 2 — GREEN:** Stream/measure bytes and SHA-256 with 25 MiB cap, verify magic and compatible reported MIME. Invoke only PyMuPDF extraction in a dedicated non-root child with OS-enforced memory/CPU/wall-time limits; open with no embedded actions/JavaScript, count all pages/text without structural parsing. Cap 100 pages; zero-text rejects; nonzero <200 chars or fewer than half pages ≥40 chars warns. Store under a version-derived server-generated non-filename path in private MinIO, prevent overwrite, verify *streamed read-back* hash and length; reject mismatches and delete orphan best-effort, logging a safe cleanup marker on delete failure. Owner lookup remains internal; do not add PDF-serving endpoint.
  ```python
  low_text = total_chars > 0 and (total_chars < 200 or pages_with_40_chars * 2 < page_count)
  ```
- [ ] **Step 3 — CHECK:** Re-run screening tests and a real MinIO round trip; inspect representative one- and two-column Q0 papers against the warning signals and record measured chars/pages without logging text. Confirm no accepted record exists for rejected examples. Commit boundary.

### Task 5: Official arXiv resolver and bounded acquisition

**Files:** Create `apps/api/researcy/papers/arxiv.py`, `apps/api/tests/test_arxiv.py`.

**Interfaces:** `parse_arxiv_reference(value: str) -> tuple[str, int | None]`; `fetch_official_arxiv(canonical_id: str, requested_version: int | None) -> ArxivAcquisition` carrying metadata, resolved version, source URL and private PDF path with bounded streaming to the Task 4 sink. No request uses a user-submitted URL as the HTTP destination. Task 6 checks existing owned ID/version before invoking fetch.

- [ ] **Step 1 — RED:** Parameterize canonical ID/official abs/pdf URL with and without `vN`; reject non-HTTPS/foreign host, host lookalike, credential/query/fragment, unapproved path, malformed/traversal/ambiguous IDs. Fake upstream transport exercises current version resolution, explicit old version confirmed by official metadata, mismatched/unavailable version, redirect to third-party, provider 429/timeout and byte overflow; failure leaves no accepted row. Example:
  ```python
  assert parse_arxiv_reference('https://arxiv.org/abs/1706.03762v5') == ('1706.03762', 5)
  with pytest.raises(InvalidArxivReference):
      parse_arxiv_reference('https://arxiv.org.evil.test/abs/1706.03762')
  ```
  Run `uv run pytest tests/test_arxiv.py -q`; expected RED on resolver absence.
- [ ] **Step 2 — GREEN:** Parse strict canonical IDs (include legacy `category/number` if officially supported by normalization), extract only canonical ID/version, request official arXiv metadata and version-specific PDF using server-built URLs. Verify metadata ID, version history and final HTTPS allowlisted official host at every redirect; cap redirects/time and streamed body bytes. Fetch title/authors/year from official metadata only; persist source URL/version later via intake; surface safe retriable upstream error for outage/429, never invent metadata or fallback to another host/version.
  ```python
  canonical_id, requested_version = parse_arxiv_reference(value)
  pdf_url = f'https://arxiv.org/pdf/{canonical_id}v{resolved_version}'
  ```
- [ ] **Step 3 — CHECK:** Re-run resolver tests; perform a bounded real fetch of official `1706.03762` where network permits, verify returned canonical ID/version and PDF magic, and remove throwaway bytes. If unavailable, record explicit prerequisite rather than substituting a fake provider result for the real M1 gate. Commit resolver.

### Task 6: Atomic upload and arXiv acceptance, idempotency and compensation

**Files:** Create `apps/api/researcy/papers/intake.py`, `apps/api/tests/test_intake.py`; modify `apps/api/researcy/papers/routes.py` to add the two POST routes; connect Tasks 3–5 interfaces.

**Interfaces:** `accept_pdf(conn, owner_id, key, operation, request_digest, source, metadata, screened_path) -> IntakeResult`; POST `/api/papers/upload` multipart `file`, POST `/api/papers/arxiv` JSON `arxiv_id_or_url`, both `Idempotency-Key`, cookie+CSRF+Origin, quota, safe statuses. Client-supplied owner/stage/key ignored. Exact same owner/key/request returns saved identifiers without new object or job; changed operation/content returns `409`; identical arXiv canonical ID (even new key, unversioned) returns existing stored version; explicit different version returns `409` *before* download. Concurrent claims serialize on owner/key and owner/arXiv uniqueness; do not expose a second job.

- [ ] **Step 1 — RED:** DB+MinIO integration exercises each path `202` with single owned paper/version/job and verified object; disconnect-after-commit key replay `200` with unchanged IDs/counts; same key changed upload bytes/operation `409`; same arXiv ID unversioned new key `200` with stored version; explicit different `vN` `409` with zero fetch; concurrent same-key calls yield one job/object; upload beyond cap rejected while streaming even with false `Content-Length`; CSRF rejects with no new object/job. DB commit failure after write triggers object compensation and no accepted row. Example:
  ```python
  first = post_upload(owner_a, key='same', pdf=valid_pdf)
  replay = post_upload(owner_a, key='same', pdf=valid_pdf)
  assert (first.status_code, replay.status_code) == (202, 200)
  assert first.json()['job_id'] == replay.json()['job_id']
  assert count_jobs(owner_a) == 1
  ```
  Run `uv run pytest tests/test_intake.py -q`; expected RED on missing routes.
- [ ] **Step 2 — GREEN:** Authenticate/CSRF before any sink/network/quota side effect; parse/validate bounded idempotency key and determine operation/content digest (stream uploads once into private temp file). Lock and check an existing owner/key outcome **before** reserving a rate-limit slot or making a network request; identical replay returns the original identity and does not spend another slot. Reserve persistent user quota for genuinely new requests. Check existing canonical arXiv owner before fetching; explicit different version fails immediately. The successful path calls shared `screen_pdf`, writes/verifies MinIO object, then inserts paper+version+warning+`queued` job+idempotency result and commits in one PostgreSQL transaction. Serialize in-flight identical keys without holding a PostgreSQL transaction open during external I/O (session advisory lock released in `finally` is one option); owner/arXiv uniqueness plus losing-object compensation handles different-key races. On DB failure remove the orphan object best-effort and log a cleanup fault if needed. New `202` returns only authoritative identifiers, warning, stored arXiv version and request ID; `200` replay uses actual persisted stage. Errors `400/401/403/409/413/415/422/429/502/503` follow safe envelope and cannot create a phantom accepted item.
  ```sql
  INSERT INTO ingestion_jobs (owner_id, document_version_id, stage)
  VALUES (%(owner_id)s, %(document_version_id)s, 'queued')
  RETURNING id;
  ```
- [ ] **Step 3 — CHECK:** Re-run intake tests, use actual app HTTP against local PostgreSQL+MinIO for one supported PDF upload and replay; inspect DB rows and object hash. Exercise safe upstream error via controlled transport outage. Remove temporary test rows/objects without deleting other users' data. Commit intake.

### Task 7: Landing, sign-in, Library and two-option Add paper UI

**Files:** Create `apps/web/{Dockerfile,package.json,package-lock.json,next.config.ts,tsconfig.json}`, `apps/web/src/app/{layout,page,sign-in/page,library/page,library/[paperId]/page,library/loading,library/error}.tsx`, `apps/web/src/app/globals.css`, `apps/web/src/lib/api.ts`, `apps/web/src/components/{add-paper,library-list}.tsx`, `apps/web/src/components/library-interaction.test.tsx`, and bundled licensed Crimson Pro/Atkinson Hyperlegible WOFF2 assets under `apps/web/public/fonts/`. Resolve/lock Next.js and Vitest/jsdom/Testing Library versions, set `npm test` to `vitest run`, and implement same-origin `/api/*` and `/auth/*` rewrites in `next.config.ts`.

**Interfaces:** Browser calls same-origin `/api/me`, `/api/papers`, `/api/papers/{id}`, `/api/papers/arxiv`, `/api/papers/upload`, `/auth/logout` and `/auth/google/start`. For mutations, send `credentials:'same-origin'`, CSRF cookie in `X-CSRF-Token`, Origin supplied naturally by browser, and payload-bound `Idempotency-Key`; retry preserves key only when payload is unchanged. A `401` clears the authenticated view and navigates to sign-in. No frontend owner parameter or session cookie read.

- [ ] **Step 1 — RED:** With Vitest/Testing Library write a small consumer-level interaction check: empty Library offers Add paper; queued response renders “Waiting for processing”, warning survives refresh, unknown author/year display stays honest; submission failure keeps field-associated error/request ID and retry, logout failure never claims signed-out, `401` redirects. Do not assert helper forwarding or mock echo; where component tests cannot establish database truth, leave that to browser gates. Run `npm test` in `apps/web`; expected RED on absent views.
- [ ] **Step 2 — GREEN:** Implement restrained editorial landing/auth/Library with Crimson Pro/Atkinson Hyperlegible, actual contrast-checked tokens, semantic `main`, visible focus, labelled controls and errors, one primary Add paper action and exactly two import forms. List title, optional authors/year, source, stored arXiv version, persisted warning and DB stage; detail offers no Reader/retry as if functional. Implement loading, empty, query-empty, populated, error/retry, submitting, accepted and accepted-with-warning, expired and logout-pending states. Block duplicate submits, use safe request IDs, make long titles wrap; reduced-motion CSS. No source/year/sort controls, list/grid toggle or phantom progression.
  ```ts
  export async function mutate(path: string, body?: BodyInit, key?: string) {
    const csrf = decodeURIComponent(document.cookie.match(/(?:^|; )researcy_csrf=([^;]+)/)?.[1] ?? '');
    return fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf, ...(key ? { 'Idempotency-Key': key } : {}), ...(typeof body === 'string' ? { 'Content-Type': 'application/json' } : {}) }, body });
  }
  ```
  Leave the multipart boundary to the browser, send JSON only for arXiv, call logout without a body/key. Use a fresh key for a changed payload, keep the key for retry of identical bytes/ID.
- [ ] **Step 3 — CHECK:** Run focused UI checks and `npm run build`; launch actual same-origin stack. In a real Chromium tab inspect landing/auth/empty/populated/detail/Add paper/logout at 375, 768, 1024 and 1440 px: one main landmark, keyboard order/focus, 44px controls, labels, contrast/reduced motion and zero page overflow. Confirm `401` clears stale Library and no fake reader link. Record measured browser evidence; commit UI.

### Task 8: Real-stack four-gate M1 acceptance and delivery-map transition

**Files:** Create `scripts/m1-smoke.py` only if it adds repeatability to real observations; create `docs/superpowers/reports/2026-09-24-researcy-m1-acceptance.md` as the expressly required gate record; modify `docs/superpowers/specs/2026-09-18-researcy-delivery-map.md` only in its M1 status/evidence rows *after* the proper gate, never pre-mark `Verified`.

**Interfaces:** Inputs are owner-configured Google OAuth client/secret and approved callback URI, **two real Google test identities**, private MinIO and real stack. Never record raw cookies, tokens, full PDFs or private text. This task contains no fake acceptance data. At the first absent human-only prerequisite, stop and instruct the owner to configure it; resume only after confirmation. Do not replace real gates with mock results, and do not change M1 to `Verified` without all four recorded gates.

- [ ] **Step 1 — focused validation:** Run migrations twice; run `uv run pytest tests -q` in `apps/api`, `npm test` and `npm run build` in `apps/web`; start `docker compose up -d --build`, verify `/api/me` unauthenticated `401`, private bucket anonymous access denied, real arXiv fetch, and one accepted supported PDF through HTTP. Record commands/outcomes and any blockers. No re-running checks already reported by the user as failed; investigate their report instead.
- [ ] **Step 2 — Gate 1, two-user isolation:** In separate browser contexts sign in as real A/B; A imports arXiv+PDF; B list/search hides both, foreign detail matches nonexistent `404`, cross-owner key does not reveal A, and repeat with owners reversed. `401` without session and `403` missing/mismatched CSRF for both imports make no row/object/job. Verify DB owner FKs, private bucket anonymous denial and internal owner+paper+version object guard. Record redacted request IDs/codes and evidence.
- [ ] **Step 3 — Gate 2, persisted imports:** For official `1706.03762` (or documented available supported ID) and supported born-digital upload, observe `202`, matching owner paper/version/queued-job plus private original whose magic/size/SHA-256 match DB. Replays create no second job/version/object. Check image-only, encrypted, corrupt, oversize and upstream failure leave none; low-text warning persists and is not ready; unversioned arXiv re-import reports stored version and explicit different version yields `409` without fetch/job. Record redacted hash/identity and observed statuses.
- [ ] **Step 4 — Gate 3, Library truth:** Observe loading→empty→accepted queued, title/author search and query-empty, refresh/new session persistence, unknown metadata, dependency failure/retry and no phantom row after failed upload. Cross-check displayed stage/title/version/warning with committed PostgreSQL rows; browser keyboard/focus/responsive/overflow checks on all M1 surfaces.
- [ ] **Step 5 — Gate 4, revocation:** Securely retain old cookie solely for local probe; CSRF logout revokes DB row; replay old cookie to `/api/me` and `/api/papers` returns `401`, old-cookie mutation creates no paper, B session remains valid. Never commit/provide the cookie. Record redacted statuses/request IDs and row state.
- [ ] **Step 6 — status and review:** Report each gate as PASS/FAIL with command or browser journey, environment, expected versus observed DB/object/API state and blocker. Only when all four pass, change M1 and M1-owned SYS-01/AUTH-01/AUTH-02/LIB-01/UX-01 rows to `Verified` with links; otherwise retain the status justified by delivery-map rules and note failed gates. Request whole-branch code review, resolve findings, re-run covering checks, commit report/map changes, and use the development-branch finishing workflow without merging/pushing/removing user artifacts without explicit authorization.

## Plan self-review and approval gate

- Coverage: Task 1 SYS-01/schema; Task 2 AUTH-01/AUTH-02 logout; Task 3 owner-scoped Library/rate limit; Tasks 4–6 LIB-01 and M1 initial PDF prerequisite to SEC-01 (final SEC-01 owned by M2); Task 7 UX-01; Task 8 exactly four M1 exit gates. JOB-01 remains M2 despite the minimal queued row.
- The accepted original precedes the atomic DB acceptance commit; `ready`, worker claims/retries, parser canonical model, Reader/Discovery/Research, Qdrant, 9Router generation and full M5 deployment are explicitly excluded.
- Approval gate: this document is a **proposal**, not an approved plan. Do not edit the delivery map to `Planned` or start Task 1 until the project owner approves this exact plan. Upon approval, record the plan approval and set only M1/M1-owned rows to `Planned`, then run the sequential SDD task/review loop. User's requested model roles are not equivalent to the product's fixed 9Router model route.
