# Q0.1 Hybrid Qualification Technical Report

## Objective

Q0.1 qualifies the local end-to-end path from the frozen corpus and parser through hybrid retrieval, evidence-grounded Gemini generation through local 9Router, and one-case display.

## Configuration

- Run ID: `q0-1-20260921T030640Z-36f32ae`.
- Corpus: frozen public papers and golden cases, parsed into 93 PyMuPDF-derived chunks.
- Retrieval: `bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)`.
- Generator: configured route `ag/gemini-3.8-flash-low` through local 9Router 0.5.81. The configured route is recorded; response-echoed backend identity was not required.
- Generation: temperature 0, no retries, and the same frozen top-5 evidence for every case.

## Method

- Track B evaluates hybrid retrieval on eight answerable golden cases.
- Track C performs exactly three sequential one-shot cases: an answerable case; a bounded follow-up receiving only the prior answerable exchange; and an independent unanswerable case requiring refusal with zero citations.
- Track D renders only the answerable case and its five evidence items.

## Evidence

- [Track B hybrid retrieval results](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/hybrid-retrieval.json)
- [Track C generation results](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/generation.json)
- [Track D one-case display](../../../qualification/results/q0-1-20260921T030640Z-36f32ae/evidence-highlight.html)

The frozen top-5 chunk IDs, in rank order, are `chunk-0007`, `chunk-0008`, `chunk-0006`, `chunk-0027`, and `chunk-0009`.

## Results

| Track | Result | Evidence |
| --- | --- | --- |
| B | Passed | Fused Recall@5 was 6/8; the hybrid configuration was selected. |
| C | Passed | Three requests returned HTTP 200/200/200 with no retries. The answerable case passed with grounded supplied-source citations; the follow-up passed and correctly identified softmax saturation and the resulting extremely small gradients; the unanswerable case passed by refusing because the evidence was insufficient and returned citations `[]`. |
| D | Passed for one answerable case | Chromium at widths 375/768/1024/1440 showed zero horizontal overflow, one `main`, one `h1`, exact `Evidence`/`Model`/`Result` sections, five evidence disclosures, and visible `Qualified` status; follow-up and unanswerable cases were absent. axe-core 4.13.0 reported 0 violations and 0 incomplete. |

## Gate Decision

Q0.1: Qualified.

Feasibility is demonstrated for the selected hybrid retriever, the configured Gemini route, the three-case generation behavior, and the one-case display. This is not a broad model benchmark or proof of backend identity.
