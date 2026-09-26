# AGENTS.md

## Scope and authority

This file applies to the entire repository.

Read these sources before changing behavior:

1. `docs/superpowers/specs/2026-09-18-researcy-system-design.md` — approved master specification and architectural authority.
2. `docs/superpowers/specs/2026-09-18-researcy-delivery-map.md` — milestone ownership, status, exit gates, and evidence rules.
3. The approved child specification and implementation plan for the active milestone under `docs/superpowers/specs/` and `docs/superpowers/plans/`.
4. `docs/guidelines/git-worktree-remote-workflow.md` — branch, worktree, and archival workflow.

A child specification or plan may add local detail but must not silently override the master specification. The delivery map is authoritative for current status; do not infer milestone status from code or this file. Do not rewrite historical Q0 evidence.

## Architecture notes

Researcy is a reader-first, evidence-linked research workspace:

```text
Browser
  -> Next.js experience layer
  -> FastAPI modular monolith
       -> PostgreSQL: authoritative relational state and durable jobs
       -> MinIO/S3: immutable original PDFs and parser artifacts
       -> Qdrant: vectors plus minimal owner/paper/version filters
       -> bounded in-process LangGraph roles
  -> Python document worker
  -> native ARM64 embedding runtime
  -> local 9Router -> configured hosted generation route
```

Repository layout:

- `apps/web/`: Next.js 16, React 19, strict TypeScript, Vitest/Testing Library.
- `apps/api/`: Python 3.12, FastAPI, Pydantic, psycopg, Alembic, pytest.
- `compose.yaml`: current local M1 stack (`web`, `api`, PostgreSQL, MinIO, bucket init). Later services must be added only by their owning milestone.
- `qualification/`: immutable qualification corpora/results; evidence, not production code.
- `docs/superpowers/`: approved specifications, plans, and acceptance reports.

Core boundaries:

- Next.js owns presentation, browser interaction state, and same-origin `/api/*` and `/auth/*` access. It does not own authorization, retrieval, prompts, ingestion, or sessions.
- FastAPI owns OAuth, opaque sessions, CSRF, authorization, paper intake, business rules, safe errors, and future bounded agent orchestration.
- PostgreSQL is authoritative for users, sessions, papers, immutable document versions, job state, provenance, conversations, claims, and citations.
- MinIO objects are private. Never derive object keys from client filenames or expose storage credentials/public object URLs.
- Qdrant is never authoritative for text, ownership, provenance, or job state.
- The document worker performs durable, idempotent ingestion stages. Request-scoped agent runs do not become worker jobs.
- Backend code derives owner, paper, version, and retrieval filters. Never trust client- or model-supplied ownership/filter values.
- Product model configuration is separate from development-agent tooling. Keep the approved product route unless an approved specification changes it.

Current implemented boundary is M1: sign-in, owner-scoped Library, and PDF/arXiv intake ending in persisted `queued` state. Do not present M2+ behavior such as processing, `ready`, Reader, retrieval, or citations unless its milestone is implemented and accepted.

## Non-negotiable contracts

- One browser origin; FastAPI is the only authentication authority. No second Next.js auth system and no application JWT for browser sessions.
- Google identity is issuer + stable `sub`, never email.
- Cookie-authenticated mutations require the opaque session, session-bound CSRF cookie/header check, and trusted exact Origin.
- Every private query includes authenticated `owner_id`; foreign and nonexistent private resources return indistinguishable `404` responses.
- Import retries preserve an idempotency key only for identical payload bytes/meaning. Changed input gets a new key.
- New accepted imports atomically persist paper, immutable document version, warning, queued job, and idempotency outcome after private object verification.
- JSON errors use stable `code`, safe `message`, and `request_id`. Do not leak provider responses, ownership existence, credentials, prompts, document text, session/CSRF values, or object keys.
- Supported input is born-digital PDF with extractable text. Enforce configured byte/page limits and reject corrupt, encrypted, image-only, or unsupported inputs safely.
- Exact citations require paper ID, immutable document version, source reference, verbatim quote, page, and exact PDF-space boxes. Page-only or approximate fallback is not accepted.
- No automatic paper discovery/import, unbounded agent loop, hidden source widening, or fabricated metadata/evidence.

## Code standards

### General

- Prefer the smallest direct implementation that preserves security, durability, ownership, and milestone gates. Do not add speculative services, abstractions, controls, fallbacks, or dependencies.
- Reuse existing module boundaries and conventions. Remove obsolete paths on cutover; do not add compatibility shims unless an approved contract requires them.
- Keep secrets and private evidence out of Git. Use `.env` from `.env.example`; never commit OAuth credentials, cookies, tokens, PDFs, private text, or generated evidence under ignored private paths.
- Keep lockfiles authoritative: `apps/api/uv.lock` and `apps/web/package-lock.json`. Use frozen/reproducible installs.
- Comments explain invariants or non-obvious risks, not syntax. Do not leave placeholders, fake states, or `TODO` implementations.
- No repository-wide formatter or linter command is currently configured. Preserve existing style and do not claim lint success without adding and running an approved tool.

### Python / FastAPI

- Python 3.12; four-space indentation, type annotations on public boundaries, small domain modules under `apps/api/researcy/`.
- Use `get_conn()` as the application PostgreSQL connection boundary and parameterized psycopg SQL. Keep transactions short; never hold one open during network, parsing, embedding, or other expensive work.
- Use Pydantic response models and the shared `APIError`/request-ID envelope. Return safe, stable errors.
- Authenticate and authorize before parsing request bodies, reserving quota, making network calls, or writing objects whenever the contract permits.
- Blocking PDF, MinIO, or psycopg work invoked from an async route must not block the event loop; follow the existing thread-pool boundary.
- Migrations are forward Alembic revisions. Preserve owner-scoped composite constraints and cross-table invariants; never patch production schema ad hoc.
- Configuration comes from environment through `researcy.config.Settings`; production must fail closed on invalid origin, TLS, callback, or secret configuration.

### TypeScript / React / Next.js

- Keep `strict` TypeScript and the `@/*` alias. Define API payload types in `apps/web/src/lib/api.ts`; do not duplicate contracts across components.
- Use server components by default and add `'use client'` only where browser state/events require it.
- Browser calls stay same-origin and use the central API helpers. Never read the HttpOnly session cookie or send owner IDs/storage credentials.
- Preserve accessible semantics: one resolving `main` landmark, keyboard reachability, visible focus, labelled fields/errors, restrained live regions, reduced-motion behavior, and no horizontal overflow.
- Render persisted backend state honestly. Unknown metadata stays unknown; `queued` means “Waiting for processing,” not progress or readiness.
- Keep the approved editorial visual system: Crimson Pro for limited editorial display, Atkinson Hyperlegible for UI, warm paper/ink, navy actions/focus, restrained ochre citations, red only for errors/destructive actions. No gradient-AI, glow, glassmorphism, or emoji icons.

### Tests

- Behavior changes use RED -> GREEN: first demonstrate a plausible consumer-visible failure, then implement the smallest fix.
- Backend integration tests use temporary PostgreSQL databases and real MinIO where the storage boundary matters. Preserve deterministic cleanup and isolation.
- Frontend tests use Vitest and Testing Library through roles, labels, and user behavior.
- Test security and state boundaries: ownership, CSRF, revocation, idempotency, atomicity, bounded inputs, safe failures, and honest UI states.
- Do not add tests for wiring, helper forwarding, source wording, mock echoes, incidental defaults, or “does not throw.”
- Automated tests support acceptance but do not replace required real-stack, browser, real-provider, or two-user gates.

## Workflow

1. Identify the active milestone and read its master requirements, approved child spec, plan, and delivery-map gate.
2. Keep work inside that milestone. A master conflict requires an explicit master-spec revision and owner approval before implementation.
3. For feature work, use an isolated worktree and repository branch conventions: `feat-<topic>`, `plan-<N>-<topic>`, `fix-<topic>`, or `q<N>-<description>`.
4. Implement plan tasks serially when they share schema/contracts. For each task: RED test, GREEN implementation, focused smoke, review, then commit.
5. Run focused checks while iterating. Before completion, run affected suites, a production build, and the actual changed path against the running stack.
6. Record acceptance evidence with exact commands/journeys, environment, expected versus observed state, request IDs where safe, and blockers. Never manufacture gate evidence.
7. Update delivery status only by the map rules: approved child spec -> `Designed`; approved plan -> `Planned`; code without complete gate evidence -> `Implemented`; all exit gates with recorded evidence -> `Verified`.
8. Follow push-before-prune: commit clean work, push the feature/worktree branch, merge to `main`, push `main`, then remove the local worktree/branch. Keep the remote branch as audit history. Publishing, merging, pushing, or deleting still requires explicit user authorization.

Definition of done:

- All affected callers, migrations, tests, API/UI contracts, and documentation are updated.
- Focused tests pass; full affected suites and production build pass.
- The running changed path is exercised and observed.
- Security/ownership failure paths are checked where affected.
- No temporary scripts, private evidence, generated PDFs, credentials, or stale compatibility paths remain.
- Milestone status is no stronger than the recorded acceptance evidence.

## Setup, build, and verification commands

Prerequisites: Docker with Compose, Python 3.12 with `uv`, and Node.js 22.14 with npm.

### Environment and full stack

```bash
test -e .env || cp .env.example .env
# Fill local OAuth values only when exercising real Google sign-in; never commit .env.

docker compose up -d --build postgres minio api
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic upgrade head  # migration idempotency check
docker compose --profile web up -d --build

curl -fsS http://127.0.0.1:8000/health
```

The application is available at `http://localhost:3000`. The API is bound to `127.0.0.1:8000` by default. Stop the stack without deleting persisted volumes:

```bash
docker compose --profile web down
```

Do not add `-v` unless the user explicitly intends to delete local PostgreSQL and MinIO data.

### Backend

Start PostgreSQL and MinIO before the integration suite:

```bash
docker compose up -d postgres minio minio-init
cd apps/api
uv sync --frozen
uv run pytest tests -q
```

Focused test:

```bash
cd apps/api
uv run pytest tests/test_auth.py -q
```

Apply migrations inside the running API container:

```bash
docker compose exec -T api alembic upgrade head
```

The real-network arXiv test is opt-in and must not be treated as ordinary deterministic suite coverage:

```bash
cd apps/api
ARXIV_REAL_NETWORK=true uv run pytest tests/test_arxiv.py -q
```

### Frontend

```bash
cd apps/web
npm ci
npm test
npm run build
```

Local frontend development, with the API reachable at `127.0.0.1:8000`:

```bash
cd apps/web
npm run dev
```

### Container production build

```bash
docker compose --profile web build
docker compose --profile web up -d
```

For UI changes, tests and `npm run build` are insufficient: inspect the running application in a real browser at the affected widths/states and verify landmarks, keyboard/focus behavior, overflow, errors, and persisted server-backed state.
