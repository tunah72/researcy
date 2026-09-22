# Researcy Q0.1 Hybrid Qualification Report

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

- Track B: `Passed`
- Track C: `Not qualified`; one authorized request produced no valid grounded answer, no retry was sent.
- Track D: `Passed` for displaying the actual Evidence/Model/Result, including the failed Track C state. Browser verification across 375, 768, 1024, and 1440 viewport widths observed zero horizontal overflow, exactly one main landmark, one h1, exactly Evidence/Model/Result sections, first evidence disclosure opened, and axe-core 4.13.0 reported 0 violations and 0 incomplete checks.
- Final Q0 status: `Not qualified`
