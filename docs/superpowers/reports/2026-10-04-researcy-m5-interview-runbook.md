# M5 isolated interview runbook — 2026-10-04

**Readiness is not qualification. M5 remains Implemented, not Verified.** The owner temporarily accepts conditional integration and authorizes M5 process shutdown/cleanup, commit/push/PR/merge to main, local-main sync, and main startup/manual testing including forward migrations/processing. This permission is not observed execution or closure of failed gates. All nine frozen sources are ready; historical failures remain preserved. Campaign accounting is18/36charged,16settled,0uncertain/0reserved, with a new manual Discovery run outside that ledger as recorded below. **No additional hosted calls are authorized.** Do not present persisted output as live generation or a synthetic session as Google login.

## Future main manual checklist — conditional integration

This is a **future checklist**, not evidence that the merged path has already been tested. Controller appends actual results after execution. The original isolated instructions below remain reproducibility/history guidance, not permission to restart a paid campaign.

1. Stop only M5-owned processes without deleting its volumes. Preserve the isolated worktree, ignored corpus/ledgers/private evidence and remote audit branch. During publication/local-main sync, preserve the user's main `apps/web/next-env.d.ts` modification and untracked web context files. Never force-prune or commit private originals, quotes, prompts, cookies or secrets.
2. Record actual commit/PR/merge/local-main revisions and confirm the runtime uses the merged source. Use the existing private main override `.omp/runtime/m3-main.private.yaml` and its actual project/env/origin, not isolated3305 values guessed from this runbook. Keep private values out of Git/output.
3. Under the owner's forward-migration/processing authorization, record actual migration head/replay and startup outcomes before declaring readiness. Preserve existing main paper/version/job identities and data; no reset or volume deletion. Worker startup may consume real queued processing and must be reported as such.
4. Record startup exit state, API `/health`, web reachability and dependency `/ready` separately, with safe request IDs. A catalog check is not a hosted generation test; warm/populated success is not a cold boot. An unavailable dependency or failed migration remains an observed failure, not a passing main gate.
5. Let the owner exercise genuine Google sign-in at the **actual main origin**. Preserve prior isolated callback400 `redirect_uri_mismatch` and label the subsequent configuration fix as owner-reported; neither alone establishes full G5. Distinguish the Google owner's Library from synthetic campaign ownership without moving private paper owners.
6. Without hosted generation, inspect Library preparation states, ready-only1–3 research selection/cap, immutable original Download/PDF identity, and any existing owned accepted Research result/citation reload. Verify displayed-source versus active Discussion separation, canonical jump/Return and focus/overflow only where actually exercised. Do not fabricate an existing result for a Google owner who has none.
7. Review existing outputs privately against the frozen rubric; human factual0/1/2 scores remain missing until recorded in a separate review overlay. R1/R8 require actual split-source factual support; R2 safe insufficiency is not a quality pass. Preserve all original outcomes.
8. **Stop before Ask, Related/Search or Generate.** Official Related→explicit Add→ready→Research remains unaccepted; a persisted-state smoke cannot close it. A later generating journey requires new explicit hosted permission **and** accounting reconciliation. Report unexercised paths honestly.

### Manual Discovery accounting outside the campaign

Campaign consumption remains **18/36 charged, 16 settled, 0 uncertain, 0 reserved**: Research8, Reader5, Discovery2, diagnostic3, demo0. Owner manual run **`9f0c5158-fc02-4ff1-b77a-d794b06d7d65`**, request **`0043e130-e0f9-4bf2-853b-e169c838ba51`**, completed **stop / 1 generation / 0 searches / 0 returns** outside the campaign ledger. Reconcile this dispatch before further paid activity; do not invent an allocation, ledger charge or revised total. Nominal remaining campaign slots are not new permission.


## Target and prerequisites

The original isolated reproduction target is worktree `.omp/worktrees/m5-research-agent`, branch `feat-m5-research-agent`. Current main integration/startup authority is described above; isolated defaults must not be reused as main settings.

- Project `researcy-m5-acceptance`; database `researcy_m5_acceptance`; bucket `researcy-m5-originals`.
- Private files `.omp/runtime/m5-acceptance.env` and `.omp/runtime/m5-acceptance.private.yaml`, permissions 600. They are local prerequisites, deliberately absent from Git. Never print or commit them.
- Browser origin `http://127.0.0.1:3305`. API 58005, PostgreSQL 56435, MinIO 59005/59006, Qdrant 56335, all isolated loopback mappings.
- Frozen Python 3.12 API/worker, Node 22.14.0 web, installed lockfiles authoritative.
- Native Ollama outside Docker; approved BGE-M3 digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`. Do not restart/reconfigure/unload the shared main runtime to manufacture a cold sample.
- Configured direct Gemini endpoint `https://generativelanguage.googleapis.com/v1beta/openai`, model `gemini-3.8-flash`; private key. No automatic provider/model fallback. Catalog uses `models/gemini-3.8-flash`, while generation requests use the configured short name.
- Actual memory limits: API 512 MiB; web 256 MiB; worker 1,024 MiB; PostgreSQL 384 MiB; MinIO 256 MiB; Qdrant 512 MiB. Short-lived bucket-init has no runtime cap requirement. These are enforced limits, not proof of available host capacity.

Historical isolated prerequisite: a successful registered Google callback was initially unobserved, and the owner's genuine attempt later failed400 `redirect_uri_mismatch`. The owner now reports a configuration fix; full G5 official product acceptance remains missing. Use the actual target origin/client and owner sign-in; do not infer registration or a successful full journey from copied credentials or the configuration report.

## Startup

From the worktree root:

```bash
bash -n scripts/demo-up.sh
bash scripts/demo-up.sh --project researcy-m5-acceptance \
  --env-file .omp/runtime/m5-acceptance.env \
  --override .omp/runtime/m5-acceptance.private.yaml
```

The entrypoint validates isolated namespaces/private volume ownership/resource limits/actual Settings, builds frozen API/web/worker images, quiesces the isolated worker, starts dependencies, waits for MinIO before bucket init, applies migration twice, checks private object read/write/delete and Qdrant/sandbox, performs authorized native warm/vector verification, then starts API/web/worker. It waits at most 120 seconds for application health/web before one read-only dependency check. It does **not** seed/import papers, pull/switch models or send a paid generation ping.

Cold native state was naturally observed before the first authorized warm. Repeated startup observes warm state only; do not label it a cold boot. Starting the worker consumes this isolated project's queued imports. Main services/volumes remain untouched.

## Read the three separate signals

```bash
curl -fsS http://127.0.0.1:58005/health
curl -sS -i http://127.0.0.1:58005/ready
```

1. `/health` 200: process liveness only.
2. `/ready` 200: DB/head, private bucket, Qdrant schema, native identity and configured provider catalog access. Native loaded/cold is reported separately; a cold identity check is not a warm embedding measurement. It always reports `generation_execution: unverified`, including after prior successful generation.
3. Fresh accepted application run plus gate evidence: role qualification. Neither catalog success nor historical runs establish the full journey.

A 503 or startup nonzero exit retains private volumes. Inspect the safe per-dependency state/request ID, preserve the failed observation, and address the actual unavailable prerequisite. Do not silently retry generation, weaken validators, replace frozen gold, reroute to another model or declare readiness from configuration. Actual catalog access has been variable. Initial HTTP startup also raced running processes; bounded health waiting addresses that race, not provider outages.

Historical populated startup failed at Compose service startup and required a web-only recovery. Subsequent complete populated entrypoint runs exited0 in38.94s and42.50s without hosted generation; failed observations remain preserved. These are repeated warm/populated successes, not a newly observed cold boot.

## Live journey — prerequisite-gated, not yet demonstrated end to end

The following generating journey is a future gated acceptance path, **not executable under the latest no-extra-hosted decision**. It requires new hosted permission, reconciled campaign/manual accounting, owner Google sign-in and all required sources actually ready:

1. Library → open a ready paper. Verify Download/header identify the displayed immutable original.
2. Ask a question in Discussion. A failed draft is not a cited answer; only completed accepted citations can be opened.
3. Explicitly click Related papers. Recommendations are title/abstract metadata, not PDF evidence. No automatic import.
4. Choose a genuinely relevant unowned returned recommendation and explicitly Add. Preserve its idempotency key for identical input; wait for persisted processing `ready`, not a fabricated progress timer.
5. Return to the active Reader. Explicitly open Select research papers; choose 1–3 ready papers. Failed/unready papers remain disabled with their actual preparation state. Keyboard Space toggles checkboxes; a fourth selection is disabled.
6. Explicitly Generate directions. Review factual premises against exact citations. Proposed direction/method remain labelled hypotheses, never novelty/feasibility proof.
7. Open current and selected-source accepted citations. Header/download/PDF must identify the exact shown source/version; Discussion and its unsent composer remain scoped to the active paper.
8. Escape closes evidence, retains shown page/source and restores citation focus. Return to active paper changes only displayed PDF and focuses the active title.
9. Reload a persisted result: GET restoration only, no generation or background resumption. An interrupted/failed run has no accepted citations; a new retry is a separate explicit request and must fit the existing attempt/owner quotas.

Observed subsets: actual original-PDF related page-2 URL restoration, active composer/title focus, persisted R6 accepted result reload, exact 273-character-box overlay/Escape, keyboard ready-only selection/cap, responsive landmark/overflow checks. The R6 premise used a labelled controlled document; this is not a natural split-paper quality demonstration. Do not invent a recommendation or substitute a fixture for official Add→ready.

## Frozen qualification and attempt ledger

Public frozen manifest: `qualification/m5/manifest.json`; digest `91e6f258dbcbe3023f3331b8a5794d55f8fc0160c6066f3bfa1dbc25ced92664`. Private originals/annotations/bindings/observations/ledger remain under `.omp/runtime/m5-gold/`, never committed. Original Q0 gold is unchanged.

The private evaluator uses only application endpoints and process-environment `M5_SESSION`/`M5_CSRF`, not direct SDK generation. Session issuance used for automated security checks is synthetic and must remain labelled. Budget36: Research16, Reader6, Discovery4, actual browser journey6, named diagnostics4. Current charge18,16settled runs,0uncertain/0reserved; allocation consumption Research8,Reader5,Discovery2,demo0,diagnostic3. Unknown dispatch retains conservative reservation; never restart a campaign to erase it. Only audited pre-reservation Research503/GENERATION_UNCONFIGURED and429/RESEARCH_RATE_LIMITED, with strict matching request identity and no run header, settle at zero attempts. Endpoint mode rejects browser-primary cases; those slots require actual browser/manual controller evidence. Remaining Reader1/diagnostic1 cannot reserve the required two-attempt run; any reallocation or additional named campaign requires explicit approval.

Offline scoring entrypoint:

```bash
# Private observation/binding paths must exist and output must be new.
# This command does not dispatch generation.
cd apps/api
uv run --frozen python -m researcy.evaluation.m5 \
  --root ../.. --manifest qualification/m5/manifest.json \
  --observations .omp/runtime/m5-gold/local-observations.json \
  --bindings .omp/runtime/m5-gold/application-bindings.json \
  --output .omp/runtime/m5-gold/offline-reconciliation.json
```

Run the command from the worktree root; it changes to `apps/api`. Expected incomplete/failed qualification exits nonzero; do not mistake a written report for a passing gate. New restored measurements use `local-observations-restored-corrected.json` and `application-bindings-restored.json`; original artifacts remain unchanged. Paid `--run` additionally requires explicit budget/ledger/base URL/exact trusted origin/isolated project and private live session; use the existing ledger, never overwrite observations or retry blindly.

Human reviewers must rate factual assertion support 0/1/2 and motivation/abstention according to the frozen rubric. AI gold/source review is not a substitute. Monetary cost remains null/unavailable until authoritative account-model tariff mapping exists; known tokens/calls are not zero/free cost.

### Owner-only sign-in and factual review checkpoint

Owner selected manual Google sign-in/human scoring and **no additional hosted calls** at the remediation checkpoint, retained by the latest temporary-acceptance decision. Historical isolated callback is `http://127.0.0.1:3305/auth/google/callback`; the prior400 and owner-reported configuration fix are distinct evidence. Use the actual target OAuth request/origin for future owner checks. Main startup is now authorized, but Google account/security changes or provider permission grants are not implicit.

1. In your own browser, open `http://127.0.0.1:3305`, follow Sign in with Google, and record expected versus observed callback/session/Library plus safe request ID if shown. Never share cookies, tokens, OAuth codes or screenshots containing account information. If callback is rejected, record it; do not modify account settings implicitly.
2. Synthetic campaign ownership is not your Google ownership. An empty Google Library is not evidence that synthetic campaign papers disappeared. Review the existing private `.omp/runtime/m5-gold/combined-restored-primary-observations.json` against frozen PDFs/annotations locally, or use a deliberately labelled synthetic browser session; do not reassign paper owners or call that session a Google acceptance.
3. For every completed Research idea, separate each factual assertion from its hypothesis. Rate each assertion0unsupported/1partial/2fully entailed by its exact cited quote; list supporting accepted citation IDs. Rate observed-gap motivation0/1/2; check hypothesis labels and any unsupported claim of proven novelty/feasibility. R1/R8 require actual supported premises spanning both sources, not merely two displayed titles. R2failed/R5insufficient and Readerfailed cannot be upgraded by ratings; preserve missing/failed state.
4. Record reviewer identity, per-idea `assertions`, `motivation_score`, `hypothesis_labelled`, `claims_proven_novelty`, `claims_proven_feasibility` in a separate private review overlay; exact accepted shape is `_apply_reviews` in `researcy/evaluation/m5.py`. The overlay root includes unchanged manifest SHA and `cases`. Never edit original observations/gold or ask AI to invent scores. Reader review additionally rates factual correctness/support and abstention; Discovery stop with no results is not a metadata-rationale/Add pass.
5. **Stop before Ask, Related search, Generate or Add-for-demo generation.** No new hosted invocation is approved at this checkpoint. Existing result/PDF/citation GET and local review do not consume attempts. The original browser journey remains prerequisite-gated; a later generating journey requires explicit budget/ledger reconciliation first.

After ratings, controller reruns the existing offline scorer with `--reviews` into a new output artifact, zero hosted calls. Unsupported assertions remain failures; human scores cannot repair paired2/14, provider failures or absent official Add evidence.

Owner's genuine attempt subsequently failed Google400 `redirect_uri_mismatch`. Local start was inspected without provider navigation and sends exactly `http://127.0.0.1:3305/auth/google/callback` (302/request `99689730-dd6b-4ef1-917e-64a49d5e0685`). The owner must compare this exact URI against **Authorized redirect URIs of the same OAuth client**, not only Authorized JavaScript origins. If adding the isolated callback, preserve existing main callbacks; changing provider OAuth settings remains owner-only or separately authorized. `localhost` and `127.0.0.1`, ports, paths and trailing slash are different exact values. G5 remains failed until a new owner sign-in actually succeeds.

**Latest owner update — 2026-10-05:** The owner reports fixing Google configuration. Preserve the above400 and local-start inspection as historical evidence, not an instruction to repeat the failure. Full G5 official Related→Add→ready→Research is still unaccepted. No successful full journey is fabricated from the reported fix.


## Current blockers and safe shutdown

- All9frozen sources are ready. Visual Attention Network resumed its same job/version through public Retry revision1; scientific2105 was separately uploaded with identical frozen SHA and honest unknown metadata. The permanently failed original arXiv job remains unchanged; no administrative requeue or limit increase.
- Restored parser regions67/67, coverage5357/5357 and reading order12/12 pass. Section agreement21/67 remains a disclosed measurement. Q0fusedRecall@5=6/8 meets its floor; pairedfused/packed2/14 fails the75% floor despite exacttuples273/273 andscopeerrors0.
- E1/E3 baseline Reader failures remain. X1-E1 failed due to private observer fsync denied by unchanged seccomp; controlled RED/GREEN corrected only the observer. X2-E1 captured actual model deletion of one rawU+FFFD glyph after two validated claims; exact rejection is correct. The generic escaped-Unicode experiment then invented U+0000 in X1-E3 and failed GENERATION_INVALID_OUTPUT. It was reverted; only the independently proven navigation/raw separation remains. No provider failure is declared fixed.
- All eight primary Research cases now have preserved observations: R1/R3/R4/R7/R8 completed, R2/R5 safe insufficient evidence, R6 completed. Five new completed runs and seven canonical citations were verified through owned result/citation GET reload. R1/R8 do not yet establish required split-source factual support; absent human ratings remain a gate blocker. DiscoveryD1/D2 returned permitted stop with zero recommendations, not successful discovery/Add acceptance.
- Controlled real TCP six fault→valid pairs,20/21st quota, concurrent owner slot, expiry→interrupted and rejected late publication passed with local provider only. Normal retained-source warm/populated startup succeeded again51.18s, with the private capture override removed. These checks do not establish genuine isolated Google or full browser-provider journeys.
- Full genuine Google/product journey and human factual ratings are not accepted. Prior callback400 and owner-reported configuration fix remain separate evidence. Shared-host pressure/swap is disclosed in acceptance evidence.
- Both bounded query spikes were rejected; no production query revision was retained. Required scientific premise regions exist in published chunks, but measured candidates miss them. Gold, bounds and provider/model are unchanged; resume needs an evidence-led design decision, not a paid query loop.
- Discovery uploads have filename titles/no abstract; the model stops before arXiv search. Current UI conflates that stop with genuine search-zero-results. Preserve this distinction and the new outside-ledger manual run; no fabricated recommendation or official Add evidence.
- Latest suite provenance is mixed: backend247passed/20host-ledger `flock` failures under unchanged container seccomp; host evaluator61passed; frozen Linux frontend149passed. These do not establish a fresh all-green main-path suite.

Shutdown preserves data:

```bash
docker compose --env-file .omp/runtime/m5-acceptance.env -p researcy-m5-acceptance \
  -f compose.yaml -f .omp/runtime/m5-acceptance.private.yaml \
  --profile web --profile processing down
```

Never add `-v`; this shutdown command targets only the isolated project/override. The owner now authorizes publication, integration, local-main sync and main migration/worker startup, with actual results to be recorded separately. Worktree pruning/data deletion are not authorized: preserve private evidence, corpus, ledgers, volumes and remote audit branch.
