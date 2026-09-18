# Researcy Q0 Technical Qualification Specification

**Status:** Approved child specification  
**Revision:** 1.0  
**Approved:** 2026-09-18  
**Parent:** [`2026-09-18-researcy-system-design.md`](./2026-09-18-researcy-system-design.md), revision 1.0  
**Delivery control:** [`2026-09-18-researcy-delivery-map.md`](./2026-09-18-researcy-delivery-map.md)  
**Path:** Spike  
**Hard timebox:** 2–3 working days

## 1. Purpose

Q0 removes the highest-risk assumptions before Researcy production implementation begins:

1. a scientific PDF parser can preserve enough logical structure and geometry for evidence navigation;
2. an embedding model can run natively on the Apple M1 with 8 GB RAM and retrieve gold evidence accurately enough;
3. OpenRouter and Gemini can satisfy the streaming structured-generation contract through manually selected adapters;
4. one generated citation can be validated and mapped back to visible PDF coordinates.

Q0 produces decisions and evidence, not a reusable application foundation. Probe code is throwaway unless a later implementation plan independently justifies rewriting the behavior as production code.

## 2. Master requirements covered

| Requirement | Q0 responsibility |
|---|---|
| PARSE-01 | Select one parser strategy using measured structure and provenance quality. |
| EMB-01 | Select one on-device embedding model/runtime configuration within the M1 budget. |
| GEN-01 | Qualify OpenRouter and Gemini adapters; select a primary development model and manual fallback. |
| CIT-01 | Prove one complete quote-to-page-to-bounding-box path. |

Q0 qualifies these requirements. M2, M3, and M4 remain responsible for production implementation and final verification.

## 3. Questions Q0 must answer

### 3.1 Parser

- Does Docling or a PyMuPDF geometry-first pipeline preserve scientific-paper reading order more reliably?
- Can normalized evidence quotes map back to source pages and boxes without fabricated precision?
- Which transformations preserve reversible text offsets?
- What parser latency and peak memory should M2 design around?

### 3.2 Embedding

- Can BGE-M3 run stably through native ARM64 Ollama with enough memory headroom?
- Does BGE-M3 materially outperform the smaller Nomic Embed Text baseline on the fixed retrieval set?
- What vector dimension, distance metric, query/document instruction convention, batch size, and truncation policy must M2 pin?

### 3.3 Generation

- Can a specifically pinned OpenRouter model stream schema-conforming grounded answers?
- Can a specifically pinned Gemini model satisfy the same adapter contract?
- Do free models pass the blocking citation and refusal contract?
- If no free model passes, what exact failure requires separate approval for a low-cost paid candidate?

### 3.4 Integrated evidence

- Can one question about arXiv `1706.03762` produce a validated evidence quote that resolves to the correct PDF page and visible bounding boxes?

## 4. Fixed qualification corpus

Q0 uses five born-digital scientific PDFs with extractable text. The corpus is fixed before running comparisons.

| arXiv ID | Paper | Primary stress |
|---|---|---|
| `1706.03762` | Attention Is All You Need | Golden journey, equations, two-column layout |
| `2005.11401` | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | Dense technical prose, tables, two-column layout |
| `1512.03385` | Deep Residual Learning for Image Recognition | Figures, tables, captions, two-column layout |
| `1703.06870` | Mask R-CNN | Figures, equations, captions, multi-column reading order |
| `1806.07366` | Neural Ordinary Differential Equations | Equation-heavy paper with a different publication layout |

Each file is identified by SHA-256. A changed PDF is a different corpus version and cannot be mixed into the same result set.

### 4.1 Gold annotations

The durable gold set contains:

- four answerable questions per paper;
- one unanswerable question per paper;
- one or more verbatim evidence quotes for each answerable question;
- expected page number for every evidence quote;
- manually checked bounding region for the integrated-proof evidence;
- manually checked section headings and reading-order samples.

This yields:

- 20 answerable retrieval cases;
- 5 unanswerable cases;
- at least 20 quote/page annotations;
- at least 40 reading-order samples across the corpus.

Gold annotations are written before comparing candidates. Candidate output must not determine the expected answer.

## 5. Reproducibility envelope

Every run records:

- timestamp and run ID;
- Git revision;
- macOS and architecture;
- total physical memory;
- Python, parser, Ollama, and Qdrant versions;
- exact parser configuration;
- exact embedding model tag, digest, quantization, dimension, and runtime;
- exact generation provider, requested model ID, and response model ID;
- generation parameters and structured-output schema version;
- corpus manifest hash;
- warm/cold state;
- wall-clock latency and peak process memory where measurable.

Results missing model identity, corpus hash, or configuration identity are invalid.

## 6. Track A — Parser and provenance qualification

### 6.1 Candidates

Only two candidates are evaluated:

1. **Docling:** structure-aware conversion using document items and provenance records.
2. **PyMuPDF geometry-first:** blocks/spans/characters from `TextPage`, explicit reading-order logic, and reversible normalization.

Q0 does not add GROBID or a third parser.

### 6.2 Common candidate output

Each candidate adapter emits the same temporary JSONL shape:

```json
{
  "paper_id": "1706.03762",
  "page_index": 3,
  "section_path": ["3.2.1 Scaled Dot-Product Attention"],
  "block_type": "paragraph",
  "reading_order": 42,
  "text": "...",
  "spans": [
    {
      "text_start": 0,
      "text_end": 31,
      "bbox": [72.1, 180.3, 265.4, 197.2],
      "coordinate_origin": "bottom-left"
    }
  ]
}
```

Coordinates are transformed into one documented PDF coordinate convention before comparison. Candidate-native coordinates remain available in raw artifacts for diagnosis.

### 6.3 Normalization constraints

Allowed normalization:

- Unicode normalization;
- line-break joining when the source mapping remains explicit;
- whitespace collapse with retained offset mapping;
- dehyphenation only when both source segments remain addressable;
- removal of repeating headers and footers after recurrence is established.

Forbidden normalization:

- paraphrasing;
- model-generated reconstruction;
- dropping text without a recorded reason;
- merging columns without source-order evidence;
- transformations that cannot map normalized character ranges back to source spans.

### 6.4 Measurements

| Measurement | Method |
|---|---|
| Text coverage | Normalized extracted characters divided by the manually accepted text reference for sampled pages |
| Reading order | Human pass/fail on at least 40 ordered block transitions |
| Section accuracy | Expected headings found and assigned to the correct following content |
| Quote recovery | Gold quote found after allowed normalization |
| Page accuracy | Recovered quote resolves to the annotated page |
| Geometry resolution | Quote offsets resolve to one or more non-empty boxes |
| Header/footer leakage | Repeating page furniture present in retrieval text |
| Latency | Wall-clock parse time per paper and corpus |
| Peak memory | Maximum resident memory attributable to the parser process |

### 6.5 Blocking thresholds

A parser candidate is disqualified when any of the following occurs:

- less than 95% of gold evidence quotes resolve to the correct page;
- any integrated-proof quote cannot resolve to non-empty geometry;
- more than 10% of sampled reading-order transitions are materially incorrect;
- normalization cannot preserve reversible offsets;
- it crashes or exceeds the machine memory budget on a corpus paper.

If both candidates qualify, choose by this priority:

1. quote/page/geometry correctness;
2. reading order and section structure;
3. implementation complexity and debuggability;
4. peak memory;
5. latency.

Q0 selects one production parser strategy. M2 does not retain a permanent dual-parser abstraction.

## 7. Track B — On-device embedding qualification

### 7.1 Candidates

Both candidates run through native ARM64 Ollama:

1. `bge-m3:567m`;
2. `nomic-embed-text:137m-v1.5-fp16`.

Exact tags and digests are recorded. An unavailable tag blocks that candidate rather than silently substituting another model.

### 7.2 Shared retrieval setup

- Use the parser winner's output.
- Use one fixed structure-aware chunking configuration for both candidates.
- Index candidate vectors in separate Qdrant collections.
- Use cosine distance unless the runtime/model documentation requires and justifies another metric.
- Disable silent truncation.
- Record the complete query and document instruction/prefix convention.
- Do not add lexical fusion or a reranker to the embedding comparison.

### 7.3 Measurements

| Measurement | Method |
|---|---|
| Startup | Cold model load success and time |
| Identity | Requested tag, resolved digest, architecture, dimension, quantization |
| Stability | No crash, OOM, or malformed vector during corpus indexing |
| Dimension | Constant non-zero dimension for documents and queries |
| Vector quality guard | Finite values and non-zero L2 norm |
| Index throughput | Chunks embedded per second using recorded batch size |
| Query latency | Warm p50 and p95 over the fixed query set |
| Retrieval | Recall@1, Recall@5, MRR over 20 answerable cases |
| Memory | Peak runtime memory while indexing and querying |

### 7.4 Blocking thresholds

A candidate is disqualified when:

- the runtime crashes, is OOM-killed, or produces malformed vectors;
- any document/query dimension differs;
- any input is silently truncated;
- Recall@5 is below 0.85;
- warm query p95 exceeds 1 second on the qualification machine;
- the golden paper cannot be embedded within 5 minutes.

### 7.5 Selection rule

Choose Nomic Embed Text when it passes every blocking threshold and its Recall@5 is within five percentage points of BGE-M3. Choose BGE-M3 only when its retrieval gain exceeds that margin or its error analysis demonstrates a material scientific-retrieval advantage that the aggregate threshold hides.

The selected decision pins:

- model tag and digest;
- runtime and quantization;
- vector dimension;
- distance metric;
- query/document prefixes;
- maximum input length and explicit truncation behavior;
- batch size and concurrency;
- Qdrant collection version identity.

## 8. Track C — Hosted generation qualification

### 8.1 Adapter boundary

Q0 implements two throwaway adapters behind one qualification contract:

```text
OpenRouterGenerationClient
GeminiGenerationClient
```

Each adapter must expose:

```text
stream_grounded_answer(request) → typed stream events
rewrite_query(request)          → standalone query
repair_citations(request)       → repaired structured answer
```

The production interfaces will be designed independently in M3; Q0 only proves provider feasibility.

### 8.2 Provider selection

Provider selection is manual and environment-controlled:

```text
GENERATION_PROVIDER=openrouter
```

or:

```text
GENERATION_PROVIDER=gemini
```

There is no per-request automatic failover. A provider change requires a new process configuration and is recorded as a separate run.

### 8.3 OpenRouter qualification

- Discover currently available free variants from the model catalog at execution time.
- Pin one exact model ID with its `:free` variant; do not use the random `openrouter/free` router.
- Require endpoint support for the structured-output parameters rather than allowing routing to an incompatible endpoint.
- Record the requested model and actual response model.
- Record rate-limit and provider error responses encountered during the run.

### 8.4 Gemini qualification

- Pin one exact model ID available to the configured Google project.
- Use JSON-schema structured output and streaming through the official Gemini API.
- Record the model and project-visible free-tier limits from AI Studio at execution time.
- Do not hard-code a presumed free quota into product behavior.
- Record rate-limit and provider error responses encountered during the run.

### 8.5 Free-first policy

For each adapter:

1. qualify one exact free model first;
2. stop when it passes the blocking contract;
3. do not benchmark additional models without a recorded failure reason;
4. if no free model passes, report the blocking failure and request explicit approval plus a spend ceiling before calling one low-cost paid candidate.

Q0 cannot silently spend paid credits.

### 8.6 Evaluation cases

Use 12 bounded generation cases derived from the fixed corpus:

- 6 answerable questions;
- 3 unanswerable questions;
- 3 context-dependent follow-ups.

Every case supplies stable source IDs and retrieved text. The provider never receives the complete PDF.

### 8.7 Measurements

| Measurement | Method |
|---|---|
| Stream contract | First delta, ordered deltas, terminal completion or typed failure |
| Schema validity | Final answer conforms to the qualification JSON schema |
| Source validity | Every citation references a supplied source ID |
| Quote validity | Evidence quote matches its cited source after allowed normalization |
| Citation coverage | Substantive answer claims carry citations |
| Refusal | Unanswerable cases refuse without external knowledge |
| Follow-up | Rewritten query and answer preserve the intended referent |
| Repair | One invalid-citation fixture is repaired once or returns typed failure |
| Latency | Time to first token and total completion time |
| Usage | Provider-reported tokens when available; documented absence otherwise |
| Cost | Actual reported cost or zero/free-tier classification with model identity |

### 8.8 Blocking contract

An adapter/model pair qualifies only when:

- all 12 cases produce a valid terminal event rather than an unclassified exception;
- at least 11 of 12 final outputs conform to the schema on the first attempt;
- no citation references a source that was not supplied;
- all accepted evidence quotes match their cited source after allowed normalization;
- all three unanswerable cases produce grounded refusal;
- the invalid-citation fixture is repaired at most once or returns a typed failure;
- stream interruptions, rate limits, and provider errors map to explicit error categories.

The selected primary development model is the qualifying free model with the best citation/refusal correctness. The other qualifying adapter/model is the manual fallback. Latency breaks a correctness tie; popularity does not.

## 9. Track D — Integrated evidence proof

### 9.1 Golden question

Paper: arXiv `1706.03762`  
Question: `Why does scaled dot-product attention divide by the square root of the key dimension?`

Expected evidence includes the paper's explanation that large dot products push softmax into regions with very small gradients and scaling counteracts that effect.

### 9.2 Proof flow

```text
question
→ selected embedding model
→ Qdrant retrieval
→ selected generation adapter/model
→ structured answer and evidence quote
→ local quote validation
→ normalized offsets
→ source spans
→ page and bounding boxes
→ rendered highlight artifact
```

### 9.3 Pass conditions

- the answer addresses the question using only supplied paper context;
- every substantive claim has a valid source marker;
- the evidence quote exists in the cited chunk;
- the quote maps to the annotated PDF page;
- resolved boxes cover the expected visible sentence without crossing into another column;
- the artifact records parser, embedding, provider, model, corpus, and run identities;
- a reviewer can visually compare the highlight with the original PDF.

A page-only result does not pass Q0's exact-evidence proof, although it remains a documented product fallback for later milestones.

## 10. Durable outputs

Q0 retains:

```text
qualification/
├── corpus/manifest.json
├── gold/evidence.jsonl
├── gold/reading-order.jsonl
├── schemas/grounded-answer.schema.json
└── results/<run-id>/
    ├── environment.json
    ├── parser-results.json
    ├── embedding-results.json
    ├── generation-results.json
    └── integrated-proof.json

docs/superpowers/reports/
└── <date>-researcy-technical-qualification-report.md
```

The final report contains:

- candidate table;
- failures and disqualifications;
- selected parser and rationale;
- selected embedding configuration and rationale;
- primary and fallback generation configurations;
- integrated proof evidence;
- implications for M1–M4;
- any proposed master-spec revision.

Raw PDFs, model weights, secrets, and provider response bodies containing sensitive content are not committed.

## 11. Throwaway probe boundary

Probe code may exist under `experiments/q0/` while Q0 runs. It must be:

- isolated from future production packages;
- explicit about hard-coded corpus assumptions;
- excluded from application imports;
- removed after durable results and the final report are verified.

Durable corpus annotations, schemas, machine-readable results, and the report remain. Probe implementation is not promoted into production by moving or renaming files.

## 12. Non-goals

Q0 does not implement:

- Google OAuth, sessions, or user ownership;
- Library UI or production Reader UI;
- production FastAPI endpoints;
- PostgreSQL durable jobs;
- production database schema;
- production Qdrant collections;
- multi-paper reasoning;
- lexical fusion or reranking;
- prompt optimization beyond satisfying the qualification contract;
- automatic provider failover;
- broad model benchmarking;
- OCR or scanned-PDF support.

## 13. Stop conditions

Stop the spike and report the blocker when:

- neither parser meets the provenance threshold;
- neither embedding candidate meets stability and retrieval thresholds;
- neither provider adapter has an available free model that passes and paid-model approval has not been granted;
- exact evidence geometry cannot be proven on the golden question;
- completing the probe requires changing a master-spec decision;
- the three-day hard timebox is exhausted.

A stop condition is a valid evidence-backed Q0 result, but it does not pass the exit gate. The delivery map becomes `Blocked`, and the report must identify the failed assumption and smallest decision needed next rather than widening scope.

## 14. Exit gate

Q0 is `Verified` only when:

1. the corpus and gold annotations are fixed and hashed;
2. one parser strategy is selected by recorded evidence;
3. one embedding model/runtime configuration is selected within the machine budget;
4. OpenRouter and Gemini adapters both complete contract qualification with exact pinned model IDs;
5. one qualifying model is pinned as the primary development generator and the other adapter has a qualifying model pinned as the manual fallback;
6. the integrated golden proof resolves to exact visible evidence;
7. machine-readable results and the qualification report agree;
8. throwaway probe code is removed;
9. the delivery map contains links to verification evidence;
10. any required master revision is approved before M1 begins.

If every free candidate for an adapter fails and paid-model approval has not been granted, Q0 remains `Blocked`; it cannot be marked `Verified` through an exception to this gate.

Passing Q0 authorizes design and planning for M1. It does not authorize reuse of probe code as production implementation.

## 15. Verification method

The Q0 implementation plan must include:

- deterministic corpus download and hash verification;
- schema validation for every machine-readable artifact;
- repeated warm query measurements rather than a single latency sample;
- provider preflight before consuming the bounded evaluation cases;
- visual inspection of the integrated highlight artifact;
- cleanup verification proving `experiments/q0/` is removed;
- a final consistency check between raw results, report decisions, master spec, and delivery map.

No permanent test is added solely to prove the throwaway harness. Durable validation belongs to result schemas, corpus hashes, and the later production milestones.

## 16. Official capability references

- PyMuPDF text extraction structures and reading-order caveats: <https://pymupdf.readthedocs.io/en/latest/app1.html>
- Docling document provenance and bounding boxes: <https://docling-project.github.io/docling/reference/docling_document/>
- Ollama BGE-M3 package: <https://ollama.com/library/bge-m3>
- Ollama Nomic Embed Text package: <https://ollama.com/library/nomic-embed-text>
- OpenRouter structured outputs: <https://openrouter.ai/docs/features/structured-outputs>
- OpenRouter streaming: <https://openrouter.ai/docs/api/reference/streaming>
- OpenRouter free router behavior: <https://openrouter.ai/docs/guides/routing/routers/free-router>
- OpenRouter free model variants: <https://openrouter.ai/docs/guides/routing/model-variants/free>
- Gemini structured outputs: <https://ai.google.dev/gemini-api/docs/structured-output>
- Gemini rate limits: <https://ai.google.dev/gemini-api/docs/rate-limits>
