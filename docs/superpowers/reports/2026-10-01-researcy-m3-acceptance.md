# Researcy M3 execution and acceptance evidence

## Authorization and isolation — 2026-10-01

Owner approval: “Tôi phê duyệt specification và implement plan.” Both approved documents include the named decision permitting M3 work while M1 remains Implemented. M3 is Planned; no gate is claimed passed.

Controller: GPT 6.1 Sol. Execution worktree `.omp/worktrees/m3-reader-agent`, branch `feat-m3-reader-agent`, starting commit `cca8a9d`. Root modified Next-generated artifacts and untracked draft copies remain untouched. No reset/stash/push/merge/prune or owner-data cutover.

Actual setup command: `git check-ignore .omp/worktrees/m3-reader-agent && git worktree add .omp/worktrees/m3-reader-agent -b feat-m3-reader-agent cca8a9d`. Worktree created. Git reported clonefile optimization fallback to plain checkout; this did not prevent creation.

LSP status: no language servers configured. Source discovery/references will therefore use scoped literal searches until a server is available.

Private Compose project `researcy-m3-acceptance`, override `/tmp/researcy-m3-private.yaml`, explicit `--env-file /dev/null`. Fresh project-labelled network and PostgreSQL/MinIO/Qdrant volumes were created; only postgres, minio, minio-init and qdrant started. Private ports PostgreSQL 55435, MinIO 9003/9013; API/web not yet started. Owner/root projects and workers remain untouched.

Focused test harness reuses M2 restricted test image with current worktree source/tests/migrations mounted read-only. This is a test execution optimization, not evidence of a rebuilt M3 production image. Host/runtime constraints and exact deployed profile remain inherited.

## Execution order and contract review

Tasks T1–T9 execute serially per approved plan. Shared ready-scope loader belongs to T1 and is consumed by T3/T4/T5/T7; T4 performs final search_owned caller cutover. T2 geometry utility is consumed by T8 exact overlays. T3 schema is shared by citation/run/stream tasks. T6 supplies strict product transport to T7. No parallel shared-file/schema edits.

No interpretation changes the master, model, two-pass ceiling or any real-route gate. Actual generation endpoint/credentials/usage/tariff remain unverified prerequisites; Reader work is reachable independently.

## Current gate ledger

G1: Reader path partially exercised during T2, not yet a complete gate pass. G2–G7: not run. Historical Q0/Q0.1 and M1 technical status unchanged.

## T1 implementation evidence

The isolated API now runs on `127.0.0.1:8003`. No owner-stack service or worker was started. Test credentials are confined to private `/tmp` files; no session/CSRF values are included here.

- RED: restricted test image with current source mounted read-only, `python -m pytest tests/test_pdf_delivery.py -q --tb=short -p no:cacheprovider`: 15 failed in 22.14s because the PDF/Reader contract was absent. An earlier `uv run --no-sync` invocation failed to create its read-only home cache; that environment failure is not RED evidence.
- GREEN: same harness, `python -m pytest tests/test_pdf_delivery.py tests/test_library.py tests/test_owned_retrieval.py -q --tb=short -p no:cacheprovider`: 45 passed in 63.88s. These tests cover storage, byte ranges, ownership and M2 ready-index invariants; deterministic test vectors do not qualify native retrieval.
- Production: `docker compose --env-file /dev/null -p researcy-m3-acceptance -f compose.yaml -f /tmp/researcy-m3-private.yaml build api`, followed by `up -d --no-deps api` and two `exec -T api alembic upgrade head` invocations: successful. Private database reached existing M2 migration head; no owner database was migrated.
- Native prerequisite: the same project with `--profile processing run --rm --no-deps worker python -m researcy.ingestion.preflight --check`: `OK: preflight passed`, 7.80s.
- Original fixture: `/tmp/researcy-m2-1706.03762.pdf`, SHA-256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`, matches the frozen public corpus original. Actual multipart upload returned `202 queued`, request `87bed7e7-af94-419a-aaab-ea4dbac722ab`. This is upload of the frozen original, not a fresh arXiv acquisition claim.
- Actual one-shot native processing: private worker `python -c "from researcy.ingestion.worker import run_once; print('claimed:', run_once('m3-public-reader-fixture'))"` returned `claimed: True` in 25.84s. Subsequent actual paper detail returned `ready`, matching source SHA and 15 canonical pages.

Production HTTP smoke used actual opaque sessions issued only for isolated synthetic owners A/B:

| Request | Expected / observed | Safe request ID |
| --- | --- | --- |
| GET original | 200, all 2,215,244 original bytes identical | `a4e946a6-4ca9-4d60-8135-5d52608253f3` |
| GET `Range: bytes=10-29` | 206, exact 20-byte slice | `886f3040-b70e-49d3-946a-bdf0eecca019` |
| HEAD same range | 206, empty body | `2dbc0b6a-c006-473e-a03c-bc2130565075` |
| GET range with mismatching If-Range | 200, full original | `febff730-b7be-4846-9fa1-c1bdc39c90ed` |
| GET `Range: bytes=-0` | 416, `PDF_RANGE_INVALID` | `88d7fd83-8eca-462a-9981-703f097a5529` |
| Unsigned GET with invalid range | 401, `UNAUTHENTICATED` before range parsing | `5721be0e-f69d-4878-afbe-c216fa725848` |
| Foreign owner GET with invalid range | 404, `RESOURCE_NOT_FOUND` before range parsing | `e6651dfc-7aa3-46d0-9f8a-e596ee08e042` |
| Owner download | exact bytes; attachment `paper.pdf` | `2c6d76f7-8154-4f90-8868-8c8d5a2ba4de` |

Twelve early client closes followed by a valid 206 range succeeded. This is disconnect smoke, not deterministic proof of the eight-slot/deadline invariants. Independent PDF-resource and ready-scope reviews remain pending; T1 is not complete. G1–G7 still await their full approved journeys.

### T1 review-driven hardening and additional proof

Ready-scope review returned correct with no blocking defects. PDF-resource review identified six concrete gaps: active buffered-read interruption, request-entry/pre-header deadline, uint64 overflow, ephemeral Minio destruction clearing a shared pool, duplicate Range fields, and stalled downstream sends/midstream error handling. The controller reproduced drip-fed body timeout failure and three range protocol failures before correcting them; no requirement was weakened.

The implementation now owns each transport pool, retains its Minio client through stream cleanup, interrupts socket header/body reads at the absolute deadline, cancels deadline-expired DB queries, starts the deadline at route entry, bounds ASGI send completion, retains capacity until response cleanup, and logs only safe failure code/request ID after headers. HEAD uses the same bounded response lifecycle. Numeric overflow and duplicate Range fields produce authorized 416.

Latest focused command in the restricted Linux harness: `python -m pytest tests/test_pdf_delivery.py tests/test_library.py tests/test_owned_retrieval.py -q --tb=short -p no:cacheprovider`: **55 passed in 77.80s**. Additional regressions cover real drip-fed header/body sockets, real ASGI backpressure, safe short-original failure under ASGI 2.3 and 2.4, revoked cookies and eight actual open original streams. Two transient ASGI test failures were caused by constructing preloaded urllib3 responses rather than unread bodies; fixture corrected to `preload_content=False`. A partial header could initially return at deadline without raising; the delivery pool now rejects every response returned after deadline.

Rebuilt production full/range/HEAD smoke: full 200 exact 2,215,244 bytes (`8ad6adc2-452c-4315-b04d-f9ce28297f6c`), HEAD 206 empty (`2b76d2a4-d475-472c-baf6-78f49d9070ec`), GET 206 exact slice (`57a4e0f2-bd58-4b98-9278-24a02871a70e`). Generated OpenAPI now advertises binary application/pdf for 200/206 and the 416 outcome, rather than its initially observed generic JSON response.

Two actual HTTP ranges (`bytes=0-1107621`, `bytes=1107622-`) concatenated to the frozen original SHA; safe request IDs `bfb4f101-bdd2-4086-ac4b-b284fd329d99`, `25884137-aedc-4c2d-850b-53f0332e50ef`. Actual logout returned 204 (`2709c806-37fc-4d99-8d42-4172c7513432`); replaying the revoked cookie for a subsequent range returned 401 `UNAUTHENTICATED` (`432175be-9929-4130-8869-bb3e88f9f6a5`). A fresh isolated fixture session was issued for later browser acceptance.

Actual slow-client proof used the rebuilt production application and real private storage on a finite second Uvicorn listener inside the isolated API container. Listener socket send buffer 8192 bytes and eight actual client receive buffers 1024 bytes forced downstream backpressure; each client stopped reading after original PDF headers. Ninth actual GET returned 503 `PDF_STREAM_BUSY`. The eight responses logged safe deadline failures after the 30-second wall bound; after 32 seconds a real 206 exact ten-byte range succeeded (`7f150b9e-b238-484d-8f6e-fb6c5422d3b6`). After a 0.2-second post-response cleanup barrier the process semaphore held all eight available slots; script exited 0 after 32.47 seconds. An initial assertion immediately upon receiving bytes ran before ASGI final cleanup and failed; the corrected observation uses the explicit cleanup barrier, not a production workaround. The finite server stopped and the temporary credentialed script was removed. Updated independent review is pending.

### T1 PostgreSQL deadline review correction

Updated database review identified a one-shot cancellation idle gap and a race returning generic 500 after a deadline-cancelled query. The controller demonstrated the gap on real private PostgreSQL: a 0.1-second cancel timer expired while idle; a subsequent `pg_sleep(.5)` still ran for 0.53 seconds.

`bounded_database` now owns a duplicate of the connection socket and shuts down that transport at expiry, preventing later commands as well as interrupting active waits. Timer cancellation/join and duplicate-socket close occur before managed connection exit. Only expired `psycopg.Error` results map to the PDF's safe 503; pre-deadline database errors retain existing handling. A real database regression rejects `pg_sleep(5)` after idle expiry immediately; an actual authenticated PDF request blocked on a sessions-table lock returns 503 within its reduced test deadline. Focused check: two passed in 3.73s. The first idle regression invocation used a credential-omitting `conn.info.dsn`; its environment failure was corrected by using the existing test database URL helper.

Latest complete affected suite: **57 passed in 93.97s**. Rebuilt final production range returned 206 with the exact first 64 KiB of the original (`195cda47-036f-4e48-a64b-a4d3e33e8c94`). ReadyScopeReview's focused follow-up returned correct, no findings, confirming both DB deadline corrections. Updated transport review remains pending.

### T1 final checkpoint

Final transport review found active upstream reads were not interrupted promptly by downstream disconnect and cleanup could queue behind shared request workers. The controller corrected both ASGI-version disconnect paths, uses a dedicated bounded eight-token cleanup limiter, and applies the same cleanup path to pre-header expiry. The stream-slot watchdog is armed immediately after acquisition, before storage opening; an expired late opener cannot attach or publish a response. Reconnect socket timeouts refresh against the remaining absolute budget.

Real drip-fed socket disconnect tests for ASGI 2.3/2.4 and saturated-worker cleanup passed, together with deadline/midstream cases: seven passed in 2.28s. A delayed real Minio open remained pending after its deadline while a new actual range request succeeded; the late opener failed safely: one passed in 3.55s. An initial limiter-saturation test accidentally made the response task its own token borrower; fixture corrected to represent a separate borrower.

The hard guarantee is the request wall deadline and stream capacity/cleanup, not forcibly terminating Python threads inside libc DNS. Abandoned connection attempts remain bounded by the existing application threadpool and normal connection timeouts; pending-open expiry independently releases its stream reservation and rejects late results. No subprocess DNS service or alternative DB connection authority was added.

Final affected suite: **61 passed in 97.50s**; final production API build/start successful. Repeated actual backpressured HTTP proof on the final production implementation: eight stalled clients, ninth safe 503, eight safe deadline logs, subsequent 206 exact ten bytes (`18ea669d-cfca-4f6f-abcc-ea362b0eaba7`), all eight slots restored after the cleanup barrier; finite script exited 0 at 32.40s. Temporary listener stopped.

Final ReadyScopeReview and PdfBoundaryReview verdicts: correct, no findings. The transport review briefly returned a stale finding alongside a correct verdict; its corrected payload explicitly removed the stale finding and confirmed the latest dedicated pre-header cleanup. T1 complete; T2 can start. This is not a complete Reader or M3 gate pass: M3 remains Planned and G1–G7 remain open.

## T2 execution — complete

Restored the same worktree without reset/stash or owner-stack changes. T1 remains committed at `521dcd6`; T2 is uncommitted. Pinned `pdfjs-dist@6.3.289` using Node 22.14.0 Alpine and updated the authoritative npm lockfile. Build/dev preparation packages its matching worker, CMaps, fonts, WASM and license under version-specific same-origin public assets; generated assets are ignored.

RED: `npm test -- src/components/reader-interaction.test.tsx` initially failed because a ready Paper had no Download/Reader controls. The geometry contract was initially absent (unresolved module, zero executed tests); that is not a claim of ten failing mathematical tests. Implemented independent rotation/negative-origin/invalid-input geometry cases.

Initial focused Reader/geometry/preparation check: **23 passed**. Initial `npm run build` and isolated production Compose web build/start succeeded. Actual source remains the frozen public original processed through the private native M2 pipeline.

Actual Chromium at `http://localhost:3003/library/93b8811f-43b5-4f39-9578-72aceadf1afb`:

- Original canvas and selectable text rendered; next-page control changed page 1→2 with three page canvases, exact-page outline changed to page 4, and 150% zoom kept zero document-level overflow.
- PDF.js worker requested `/pdfjs/6.3.289/pdf.worker.min.mjs`, 200. PDF requests travelled through the existing Next rewrite: full metadata request 200, `bytes=0-65535` returned 206 / `bytes 0-65535/2215244`; later ranges likewise returned 206. No direct Minio URL appeared. No binary passthrough handler was added because the experiment showed the existing rewrite works.
- Actual download URL returned 200, attachment `paper.pdf`, 2,215,244 bytes, SHA-256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`; request ID `01a4f8a1-7c37-4ff6-8ded-cc0692c70b36`.
- At widths 375/768/1024/1280/1440: one resolving `main#main-content`, zero document horizontal overflow. Small widths show the explanatory boundary/Back/Download and no canvases; supported widths show the 65/35 Reader. At 1280 the panes measured 832/448 pixels. Measured visible controls met 44×44; the focused skip link measured 198×48 and resolved to main.
- Browser text selection returned verbatim original text. The page worker count was one while open and zero after crossing below the supported boundary; page canvas counts remained two or three, then zero below the boundary.
- A controlled browser network abort of original PDF requests produced the safe load failure with Reload PDF and one main. Removing the fault and clicking Reload PDF recovered actual original rendering; this is network-fault UI proof, not a claim of a real provider/storage outage.

The browser caught a real defect absent from component tests: after narrowing below 1024 and restoring desktop, selected page 6 persisted while scrollTop reset to 0, leaving visible page 1 blank. A layout synchronization on width/zoom now preserves the selected page offset without snapping normal scrolling. Rebuilt production verification: select page 6, narrow to 768, return to 1440; observed page 6, scrollTop 5868, selected top = viewport top = 147, three page canvases, zero overflow, and screenshot of actual page 6 content.

Full frontend suite initially failed one new test because it assumed the ambient viewport and queried the Reader before responsive state settled. The test now explicitly sets its supported width and awaits the landmark. Latest full suite: **79 passed in 10.88s**, followed by successful isolated production web rebuild/start. The SDK emits a Node-only legacy-build warning in jsdom; the product uses its browser build, verified in Chromium.

Tool limitations: documented `setCookies` array imports failed with both URL and domain/path cookie objects; private fixture cookies were installed through Chromium's underlying API without logging values. An outline role selector did not match its visible accessible label; the observed text control was then clicked successfully. Neither issue was treated as application evidence.

ReaderGeometryUxReview returned correct, no findings. ReaderLifecycleReview identified three defects: failed documents retained their loading task/worker, retry could lose the selected page offset, and text extraction completed before a cancellable TextLayer existed. Failure now clears the opened document and destroys its loading task; the failure-to-pages transition realigns the retained page; TextLayer consumes `streamTextContent()` and cancels the stream on unmount. Its focused follow-up returned correct, no findings.

Actual RED/GREEN lifecycle proof used the real original PDF with a controlled browser response changing canonical page count from 15 to 14: safe load failure retained **one worker before** the correction and **zero after**. The fault interceptor was removed; reloading the unmodified production response restored selectable text, two page canvases and one active worker. Attempts to induce a renderer error by monkeypatching canvas methods did not produce the intended failure and are not acceptance evidence; the subsequent full page reload removed those temporary patches.

Final full frontend suite: **79 passed in 13.43s**; final isolated production build/start succeeded with strict TypeScript. T2 complete. No conversation mutation or generation request is implemented or triggered by opening Reader. G1–G7 remain open pending complete M3 acceptance; M3 remains Planned.
