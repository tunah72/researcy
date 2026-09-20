# Researcy Q0 Technical Qualification Specification

**Status:** Approved child specification  
**Revision:** 1.2  
**Approved:** 2026-09-19  
**Parent:** [`2026-09-18-researcy-system-design.md`](./2026-09-18-researcy-system-design.md), revision 1.1  
**Delivery control:** [`2026-09-18-researcy-delivery-map.md`](./2026-09-18-researcy-delivery-map.md)  
**Path:** Balanced spike  
**Hard timebox:** 1.5–2 working days

## 1. Purpose

Q0 removes four implementation risks before production work begins:

1. select one scientific PDF parser that preserves enough structure and geometry for evidence navigation;
2. select one on-device embedding configuration that runs on the Apple M1 with 8 GB RAM and retrieves representative gold evidence;
3. qualify one pinned OpenAI-compatible generation path through 9Router against the grounded-generation contract;
4. prove one complete `question → answer → quote → PDF highlight` path.

Q0 produces bounded decisions and evidence, not a reusable evaluation framework or production foundation. Probe code is throwaway.

## 2. Master requirements covered

| Requirement | Q0 responsibility |
|---|---|
| PARSE-01 | Select Docling or a PyMuPDF geometry-first strategy from representative evidence. |
| EMB-01 | Select BGE-M3 or Nomic Embed Text with measured retrieval, latency, and stability on the qualification machine. |
| GEN-01 | Qualify one exact OpenAI-compatible route through a pinned 9Router version, account, and model without fallback. |
| CIT-01 | Demonstrate exact quote-to-page-to-bounding-box resolution on the golden paper. |

Q0 is an early risk-reduction subset. M2–M5 remain responsible for production implementation and broader layout, retrieval, and product acceptance coverage.

## 3. Decision questions

Q0 must answer only these questions:

1. Which parser provides the more reliable reversible quote/page/geometry path on the representative corpus?
2. Does the smaller Nomic model retrieve as well as BGE-M3, or does BGE-M3 recover at least one additional gold case or show a material scientific-retrieval advantage?
3. Can one pinned 9Router route stream grounded structured answers with valid citations, refusal, usage, and stable model identity through an OpenAI-compatible client?
4. Can the selected stack highlight the exact evidence sentence for the golden question?

## 4. Fixed representative corpus

Q0 uses exactly two born-digital PDFs with extractable text:

| arXiv ID | Paper | Qualification stress |
|---|---|---|
| `1706.03762` | Attention Is All You Need | Golden journey, equations, two-column reading order, exact highlight geometry |
| `2005.11401` | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | Dense technical prose, tables, captions, and two-column reading order |

Each PDF is downloaded from `https://arxiv.org/pdf/<arxiv-id>`, cached outside Git, and identified by SHA-256 plus page count. A changed PDF is a different corpus version.

This two-paper set is deliberately not a statistically representative parser benchmark. Broader one-column, figure-heavy, and alternative-layout coverage belongs to later evaluation work.

### 4.1 Gold annotations

Gold annotations are written before candidate comparison and contain:

- four answerable questions per paper;
- one unanswerable question per paper;
- at least one verbatim evidence quote and expected page for every answerable question;
- the expected section for every answerable question;
- at least six manually checked reading-order relations per paper;
- manually accepted visible reference text for one fixed coverage page per paper;
- manually checked page dimensions and bounding regions for the golden integrated-proof sentence.

Totals:

- 8 answerable retrieval cases;
- 2 unanswerable generation cases;
- at least 8 quote/page annotations;
- at least 12 reading-order relations.

Candidate output never determines gold truth.

Each reading-order relation stores `relation_id`, `paper_id`, zero-based `page_index`, `before_anchor`, and `after_anchor`. Anchors are verbatim snippets that each resolve uniquely on the annotated PDF page after allowed normalization. A candidate passes the relation only when both anchors resolve to candidate spans and the `before_anchor` block precedes the `after_anchor` block. Candidate output never defines or changes anchors.

## 5. Reproducibility envelope

Each run records:

- run ID, UTC timestamp, exact producer Git revision, clean tracked-tree state, macOS version, architecture, and physical memory;
- corpus manifest hash and each PDF SHA-256;
- parser package version and exact configuration;
- Ollama and Qdrant versions;
- embedding tag, digest, quantization, dimension, prefixes, batch size, and truncation setting;
- generation provider, requested model ID, response model ID, parameters, and structured-output schema version;
- latency and peak process memory where measured;
- pass/fail outcome and concrete failure reason for every threshold.

A result without corpus identity, exact model identity, or configuration identity is invalid.

## 6. Track A — Parser and provenance

### 6.1 Candidates

Only two candidates are evaluated:

1. **Docling:** document items and provenance records.
2. **PyMuPDF geometry-first:** `TextPage` blocks, spans, and characters with explicit reading-order and normalization logic.

No third parser is introduced.

### 6.2 Common output

Both adapters emit temporary records containing:

```text
paper_id
page_index                  # zero-based
section_path
block_type
reading_order
normalized_text
source_spans[]              # normalized offsets + source bbox
page_width
page_height
coordinate_origin           # bottom-left
```

Coordinates are converted to one bottom-left PDF convention. Normalized character ranges must resolve back to source spans; fuzzy reconstruction after normalization is forbidden.

Allowed normalization is limited to Unicode normalization, reversible whitespace collapse, reversible line joining, reversible dehyphenation, and removal of empirically recurring headers or footers. Paraphrasing, model reconstruction, and column merging without source-order evidence are forbidden.

### 6.3 Measurements and gate

Measure:

- gold quote recovery and expected-page correctness;
- non-empty geometry resolution;
- normalized text coverage against the two manually accepted coverage pages;
- 12 reading-order relations;
- expected section recovery;
- header/footer leakage;
- parse latency and peak memory.

Text coverage uses one deterministic formula. Apply the same allowed normalization and Unicode case-folding to candidate and reference text, split on normalized whitespace, compute the longest common subsequence of the two token sequences, and divide its length by the number of reference tokens. Empty reference text is invalid. The score is ordered token recall, not edit similarity or set overlap.

A parser qualifies only when:

- all 8 answerable gold quotes resolve to the expected page;
- every recovered gold quote resolves to non-empty source boxes;
- normalized text coverage is at least `0.90` on each fixed coverage page;
- at least 10 of 12 reading-order relations are correct;
- the golden evidence maps to boxes inside the manually annotated region and correct column;
- normalization preserves reversible offsets;
- neither corpus paper crashes or exceeds the machine budget.

If both qualify, choose by: provenance correctness, sampled text coverage, reading order/sections, implementation simplicity, peak memory, then latency. M2 receives one parser strategy, not a permanent dual-parser abstraction.

## 7. Track B — On-device embedding and retrieval

### 7.1 Candidates and shared setup

Both candidates run through native ARM64 Ollama:

1. `bge-m3:567m`;
2. `nomic-embed-text:137m-v1.5-fp16`.

Use the selected parser output, one frozen structure-aware chunk set, separate Qdrant collections, and cosine distance unless model metadata requires another metric. Both candidates embed byte-identical chunk text. Silent truncation is forbidden. Lexical fusion and reranking are excluded.

### 7.2 Measurements and gate

Measure:

- resolved tag, digest, quantization, dimension, and runtime placement;
- cold startup success;
- finite non-zero vectors with stable dimensions;
- indexing stability and peak memory;
- warm p50/p95 query latency over repeated runs;
- Recall@1, Recall@5, and MRR over the 8 answerable cases.

A candidate qualifies only when:

- it does not crash, become OOM-killed, or emit malformed vectors;
- document and query dimensions remain identical;
- no input is silently truncated;
- Recall@5 is at least `0.75` (6 of 8 cases);
- warm query p95 is below 1 second;
- the golden paper indexes within 5 minutes.

Choose Nomic when both models recover the same number of Recall@5 cases and error analysis shows no material disadvantage. Choose BGE-M3 when it recovers at least one additional gold case or its ranking/error analysis shows a material scientific-retrieval advantage. Record the selected tag, digest, runtime, quantization, dimension, metric, prefixes, maximum input, truncation behavior, batch size, concurrency, and collection identity.

## 8. Track C — Hosted generation

### 8.1 Application and transport boundary

Q0 keeps the application contract separate from the transport protocol:

```text
GenerationClient
└── OpenAICompatibleGenerationClient
    └── POST /v1/chat/completions
        └── pinned 9Router
            └── one account and one exact non-combo model route
```

`GenerationClient` exposes only Researcy domain requests, typed stream events, grounded answers, usage, and normalized failures. `OpenAICompatibleGenerationClient` is its only Q0 implementation and is the only code that may depend on OpenAI request, SSE, response, or error shapes.

OpenAI compatibility is a transport convention, not proof of semantic portability. Q0 qualifies only the exact base URL, 9Router version, route, account, and upstream model recorded in the result. A different endpoint or model requires a new compatibility run.

The client must emit the master contract exactly:

```json
{
  "answer": "A supported claim [1].",
  "citations": [
    {
      "marker": 1,
      "source_ref": "S1",
      "evidence_quote": "verbatim text from the retrieved source"
    }
  ]
}
```

Markers are unique positive integers, appear in the answer, and map one-to-one to citations. `source_ref` must be one of the supplied source IDs. Grounded refusal uses an answer explaining that the supplied paper context is insufficient and an empty `citations` list; it does not add a Q0-only output field.

### 8.2 Pinned gateway configuration

The qualification path uses:

- one pinned 9Router version;
- one local OpenAI-compatible base URL;
- one provider connection and one account;
- one exact model route that is neither a combo nor a mutable alias;
- no account, provider, or model fallback;
- no RTK, Caveman, prompt rewriting, or other prompt transformation;
- no cloud sync or tunnel;
- request-body logging disabled or redacted.

The run records the pinned gateway version, configured connection and route, requested model, response model, and upstream provider/model identity when 9Router exposes it. Qualification evidence includes a sanitized configuration assertion that no alternate account, combo, alias target, or fallback model was available during the run.

9Router does not remove upstream quota dependence. The configured account must already have sufficient subscription or paid quota for the three bounded cases. Any new paid spend requires explicit approval naming the upstream, model, maximum spend, and exact run scope.

### 8.3 Evaluation cases

The pinned route receives exactly three cases:

1. golden answerable case `1706.03762-answer-1`;
2. one immediate contextual follow-up: `What failure mode would occur without that scaling?`;
3. unanswerable case `1706.03762-unanswerable`.

Every case supplies stable source IDs and selected text only; the gateway and upstream model never receive complete PDFs. The follow-up must preserve the scaled-dot-product-attention referent.

### 8.4 Measurements and gate

Measure:

- ordered stream deltas and one terminal event;
- first-attempt schema validity;
- source ID validity;
- exact evidence quote validity after allowed normalization;
- citation coverage for substantive claims;
- grounded refusal;
- follow-up referent preservation;
- time to first token and total latency;
- provider-reported input and output token usage for every completed case;
- configured connection and route, requested and response model, plus exposed upstream identity when available;
- typed authentication, rate-limit, timeout, interrupted-stream, malformed-output, and unavailable errors.

The pinned path qualifies only when:

- all 3 cases end in a typed terminal event, never an unclassified exception;
- all 3 cases are schema-valid on the first attempt; Q0 performs no format or citation repair;
- the golden answer and follow-up produce grounded answers rather than refusals;
- every substantive claim in those two answers carries a valid marker, giving claim-marker coverage of `1.0`;
- the follow-up preserves its referent and passes the same grounding checks;
- no citation references an unknown source and every evidence quote matches that source;
- the unanswerable case states that supplied context is insufficient and returns an empty citation list;
- every completed case includes provider-reported input and output token usage;
- the sanitized configuration assertion shows a single account/model candidate, and requested/response identities remain stable across the run;
- external failures map to explicit application error categories.

Q0 selects no primary/fallback pair and makes no claim that another OpenAI-compatible endpoint will behave identically.

## 9. Track D — Integrated evidence proof

Golden case:

- Paper: arXiv `1706.03762`.
- Question: `Why does scaled dot-product attention divide by the square root of the key dimension?`
- Expected evidence: large dot products push softmax into regions with very small gradients, and scaling counteracts that effect.

Flow:

```text
question
→ selected embedding model
→ Qdrant retrieval
→ pinned OpenAI-compatible generation route
→ structured answer and evidence quote
→ local quote validation
→ normalized offsets
→ source spans
→ page and bounding boxes
→ self-contained HTML highlight
```

The proof passes only when:

- the answer uses only supplied paper context;
- every substantive claim carries a marker present in the answer;
- markers are unique and map one-to-one to citations;
- every `source_ref` is supplied to the model;
- every `evidence_quote` exists in its cited chunk;
- the selected evidence quote maps to the annotated page and overlaps the manually checked region with non-empty boxes;
- boxes cover the expected sentence without crossing columns;
- `integrated-proof.json` records claim-marker coverage and context-grounding review outcomes;
- the HTML records parser, embedding, 9Router version, configured route, requested and response model, corpus, and run identities;
- a browser inspection confirms the visible highlight and finds no unsupported substantive claim.

A page-only result does not pass.

## 10. 9Router boundary

9Router is the only generation gateway qualified by Q0. It provides the OpenAI-compatible transport and upstream translation, while Researcy owns the thin `GenerationClient` domain boundary, grounded-answer validation, citation validation, and frontend event contract.

Gateway routing features remain outside Q0. A combo, alias retarget, additional account, fallback, prompt transformation, or different OpenAI-compatible endpoint changes the qualified path and requires separate evidence in M3.

## 11. Durable outputs

Q0 retains only:

```text
qualification/
├── corpus/manifest.json
├── gold/evidence.jsonl
├── gold/reading-order.jsonl
└── results/<run-id>/
    ├── environment.json
    ├── parser.json
    ├── embedding.json
    ├── generation.json
    ├── integrated-proof.json
    └── evidence-highlight.html

docs/superpowers/reports/
└── 2026-09-18-researcy-technical-qualification-report.md
```

Temporary Pydantic models validate result files while the probe exists. Q0 does not build a permanent schema-generation or report-verification framework. The final report contains the candidate outcomes, selected configurations, integrated proof, known limitations of the two-paper corpus, and implications for later milestones.

For a blocked run, retain only artifacts produced before the failed gate; downstream result files and HTML are omitted rather than fabricated. The blocker report and delivery map name each downstream stage `not_run`, preserve available evidence, and remain the durable completion record.

Raw PDFs, model weights, `.env` files, API keys, and unredacted provider payloads are never committed.

## 12. Throwaway boundary and non-goals

Probe code lives only under `experiments/q0/`, is never imported by production packages, and is removed after results and the report are verified.

Q0 does not implement:

- production API, database, jobs, authentication, or UI;
- production parser or multi-provider generation frameworks;
- a reusable evaluation framework;
- OCR or scanned-PDF support;
- broad layout coverage or statistical benchmarking;
- lexical fusion, reranking, or multi-paper reasoning;
- automatic account/provider/model fallback;
- citation-repair orchestration;
- cross-endpoint portability claims;
- prompt or token optimization.

## 13. Stop conditions

Stop and write an evidence-backed blocker when:

- neither parser passes the provenance gate;
- neither embedding candidate passes stability and retrieval gates;
- the pinned 9Router route cannot complete all three cases without switching account or model;
- exact golden geometry cannot be proven;
- the probe requires widening scope or changing another master decision;
- the two-day hard timebox expires.

A stopped spike is a valid result but leaves Q0 `Blocked`. Do not weaken thresholds or add candidates.

## 14. Exit gate

Q0 is `Verified` only when:

1. both PDFs and all gold annotations are fixed and hashed;
2. one parser is selected with recorded representative evidence;
3. one embedding configuration is selected within the machine budget;
4. one pinned OpenAI-compatible 9Router route qualifies with exact gateway, account, route, and model identities;
5. the golden proof resolves to exact visible evidence;
6. durable results and the concise report agree;
7. the report states that broader corpus and endpoint coverage remains for later evaluation;
8. `experiments/q0/` is removed and no forbidden artifact is tracked;
9. the delivery map links the evidence and authorizes M1 planning.

Passing Q0 authorizes M1 design and planning. It does not authorize promotion of probe code into production.

## 15. Verification method

The implementation plan must include:

- deterministic PDF download, SHA-256, and page-count verification;
- local tests only for reversible normalization, OpenAI-compatible stream/schema parsing, and exact proof geometry;
- repeated warm retrieval latency measurements;
- one pinned-gateway preflight before three bounded network cases;
- browser inspection of the integrated HTML;
- a direct result-to-report review;
- cleanup verification after deleting `experiments/q0/`.

Permanent tests are not added solely to preserve the throwaway harness.

## 16. Official capability references

- PyMuPDF text extraction and reading-order caveats: <https://pymupdf.readthedocs.io/en/latest/app1.html>
- Docling provenance and bounding boxes: <https://docling-project.github.io/docling/reference/docling_document/>
- Ollama BGE-M3: <https://ollama.com/library/bge-m3>
- Ollama Nomic Embed Text: <https://ollama.com/library/nomic-embed-text>
- OpenAI Chat Completions API: <https://platform.openai.com/docs/api-reference/chat>
- OpenAI Structured Outputs: <https://platform.openai.com/docs/guides/structured-outputs>
- 9Router documentation: <https://docs.9router.com/>
- 9Router architecture and compatibility routes: <https://github.com/decolua/9router/blob/master/docs/ARCHITECTURE.md>
