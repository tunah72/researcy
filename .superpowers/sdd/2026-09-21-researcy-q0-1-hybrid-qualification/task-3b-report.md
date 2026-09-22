# Track C rerun report

## Status

The bounded Track C rerun is complete. The durable artifact satisfies the minimal `Evidence` / `Model` / `Result` contract, but the qualification result is `passed: false` because the single authorized generation request did not yield a valid grounded answer. No retry was sent.

## Frozen evidence regeneration

The committed PyMuPDF parser and chunker regenerated the committed two-paper corpus before any generation traffic. The regenerated stream contained exactly 93 chunks and matched the inherited chunk-set SHA-256:

```text
0aa4bbf11729158948230963930520c2cb52b04e5a292f03ba97c64d7c572cde
```

The five selected evidence IDs were resolved from that regenerated stream in the required rank order:

```text
chunk-0007, chunk-0008, chunk-0006, chunk-0027, chunk-0009
```

No embedding, Qdrant, Ollama, BM25, RRF, or Track B measurement was run.

## Live request

Before generation traffic, a harmless unauthenticated `GET /v1/models` returned HTTP 200 and confirmed that the configured route was present.

One OpenAI-compatible request was sent to the configured local 9Router endpoint with route `ag/gemini-3.8-flash-low`. Response-model metadata was not enforced. The one-shot runner reported:

```text
{"chunk_count":93,"chunk_sha256":"0aa4bbf11729158948230963930520c2cb52b04e5a292f03ba97c64d7c572cde","live_request_count":1,"passed":false}
```

Live generation request count: **1**. The request was not retried. The transient runner was removed after producing the artifact, and no prompt, raw gateway envelope, token usage, timing, identity metadata, credential, email, or private gateway state was persisted.

## Durable artifact

`qualification/results/q0-1-20260921T030640Z-36f32ae/generation.json` is compact JSON with top-level keys in the exact order `Evidence`, `Model`, `Result`. Each evidence item contains only `source_id` and `text`; `Model` is the configured route; `Result` contains only `question`, `answer`, `citations`, and `passed`.

Because the only live request failed to produce an accepted grounded answer, `Result` records the concise failure `Generation request failed.`, an empty citation list, and `passed: false`. This reflects the observed outcome without inventing an answer or citing unsupported sources.

## Verification

Exact command:

```sh
uv run python -c 'import json; from pathlib import Path; p=Path("../../qualification/results/q0-1-20260921T030640Z-36f32ae/generation.json"); raw=p.read_text(); d=json.loads(raw); ids=["chunk-0007","chunk-0008","chunk-0006","chunk-0027","chunk-0009"]; assert list(d)==["Evidence","Model","Result"]; assert [e["source_id"] for e in d["Evidence"]]==ids; assert all(list(e)==["source_id","text"] and isinstance(e["text"],str) and e["text"] for e in d["Evidence"]); assert d["Model"]=="ag/gemini-3.8-flash-low"; r=d["Result"]; assert list(r)==["question","answer","citations","passed"]; assert r["question"]=="Why does scaled dot-product attention divide by the square root of the key dimension?"; assert r["answer"]=="Generation request failed." and r["citations"]==[] and r["passed"] is False; assert raw==json.dumps(d,ensure_ascii=False,separators=(",",":"))+"\n"; print("PASS: compact Evidence/Model/Result artifact; frozen evidence order; configured route; failed single-request result")'
```

Exact output:

```text
PASS: compact Evidence/Model/Result artifact; frozen evidence order; configured route; failed single-request result
```

## Self-review

The artifact contains no extra top-level or nested report metadata, uses the five frozen IDs in order, names only the configured route, and correctly leaves citations empty for the failed request. Track B artifacts and measurements were not modified.

## Concern

The single-request constraint is exhausted without a grounded answer, so Track C does not qualify despite the artifact itself satisfying the rerun contract.
