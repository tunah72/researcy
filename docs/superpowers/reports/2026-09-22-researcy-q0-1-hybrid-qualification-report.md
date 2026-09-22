## Evidence

Track B passed with selected `bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)`.

Frozen top-5 retrieval chunk IDs:
- `chunk-0007`
- `chunk-0008`
- `chunk-0006`
- `chunk-0027`
- `chunk-0009`

Durable artifacts:
- [Hybrid Retrieval (Track B)](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/hybrid-retrieval.json)
- [Generation (Track C)](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/generation.json)
- [Evidence Highlight Proof (Track D)](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/evidence-highlight.html)

## Model

Configured generator route: `ag/gemini-3.8-flash-low` through local 9Router/Antigravity.

This records the configured route, not backend identity echoed by the response.

## Result

- Track B: `Passed`.
- Track C: `Passed` — one HTTP 200 generation request produced a grounded answer satisfying the semantic gate with citations `chunk-0007` and `chunk-0008`.
- Track D: `Passed` — Chromium at 375/768/1024/1440 had zero horizontal overflow, one main and one h1, the exact Evidence/Model/Result sections, visible Qualified status/citations, and axe-core 4.13.0 found 0 violations.
- Final Q0 status: `Qualified` because Tracks B, C, and D passed.
