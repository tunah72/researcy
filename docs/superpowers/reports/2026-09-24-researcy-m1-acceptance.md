# Researcy M1 acceptance — 2026-09-24

## Result

M1 implementation is complete. M1 remains **Implemented, not Verified** because the required two-real-Google-user acceptance gate has not been executed. Owner OAuth values are configured locally, but two real approved Google test identities were not available to this session. Synthetic/local sessions below are smoke evidence only and do not replace the four exit gates.

## Focused validation

| Check | Observed |
|---|---|
| Schema upgrade twice | Passed in the running API container |
| API suite | `161 passed, 1 skipped` |
| Web consumer suite | `8 passed` |
| Web production build | Next.js 16.3.6 build passed, including `/api/papers/arxiv` |
| Dependency audit | `npm audit`: zero vulnerabilities |
| Complete image build | `docker compose --profile web up -d --build`: API and web built and started healthy |
| Unauthenticated API | `/api/me` returns `401` in focused auth coverage |
| Private bucket | Anonymous HTTP access returned `403` |
| Real arXiv | Same-origin `POST /api/papers/arxiv` for `1706.03762` returned `202`, `queued`, resolved `v7`; object was 2,215,244 bytes with PDF magic and DB-matching SHA-256 |
| Real PDF through UI | Chromium upload returned `202`; one paper/version/queued job and one private object; byte count, PDF magic and binary SHA-256 matched DB |

Temporary smoke users, sessions, database rows, MinIO objects, browser cookies and generated PDFs were removed after observation. No credentials, cookies, tokens, full PDFs or private text are recorded here.

## Browser evidence

Real Chromium inspected landing, sign-in, empty Library, populated Library, Add paper and paper detail at 375, 768, 1024 and 1440 px.

- Exactly one `main#main-content` and a resolving skip target on every inspected surface.
- Focused skip link measured 198×48 px.
- No inspected non-inline control below 44×44 px.
- Zero page-level horizontal overflow at every width.
- Bundled Crimson Pro headings and Atkinson Hyperlegible body font loaded.
- Empty, query-empty, populated, accepted, warning and detail states rendered server-backed values.
- Queued DB stage rendered as “Waiting for processing”; no Reader, fake progress or processing retry appeared.
- Logout removed cookies; replaying the old local smoke cookie redirected to `/sign-in?expired=1`.

## Four exit gates

| Gate | Status | Evidence / blocker |
|---|---|---|
| 1. Two-user ownership isolation | BLOCKED | Requires two real approved Google identities in separate browser contexts. Owner-scoped API behavior is covered by tests and local smoke, but those do not satisfy the gate. |
| 2. Both imports and original PDF persistence | BLOCKED | Real arXiv and PDF persistence checks passed with temporary local sessions. Gate still requires those imports under the real two-user OAuth journey. |
| 3. Library matches committed database state | BLOCKED | Browser/DB cross-check passed for a local smoke identity at all required viewport widths. Gate still requires refresh/new-session observations under real Google authentication. |
| 4. Server-side logout revocation | BLOCKED | Local smoke proved cookie deletion and revoked-cookie rejection. Gate still requires proving user B remains valid during the real two-user journey. |

## Required owner action

Provide two approved Google test identities and complete sign-in for A and B in separate browser contexts at `http://localhost:3000/sign-in`. Do not share passwords, raw cookies or tokens. Once both contexts are authenticated, resume Task 8 to execute and record the four real gates. The delivery map must remain at `Implemented` until all four gates pass.
