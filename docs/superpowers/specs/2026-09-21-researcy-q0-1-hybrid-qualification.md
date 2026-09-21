# Researcy Q0.1 Hybrid Retrieval and Evidence Qualification Specification

**Status:** Approved child remediation specification  
**Revision:** 1.0  
**Approved:** 2026-09-21  
**Parent:** [`2026-09-18-researcy-technical-qualification.md`](./2026-09-18-researcy-technical-qualification.md), revision 1.2  
**Blocked baseline:** [`2026-09-20-researcy-q0-technical-qualification-report.md`](../reports/2026-09-20-researcy-q0-technical-qualification-report.md)  
**Delivery control:** [`2026-09-18-researcy-delivery-map.md`](./2026-09-18-researcy-delivery-map.md)  
**Path:** Q0.1 bounded remediation spike

## 1. Purpose

Q0.1 resolves the single blocker left by Q0 and, only after that blocker is removed, completes the deferred hosted-generation and evidence-highlight tracks.

Q0 established that:

- PyMuPDF geometry-first satisfies the parser and reversible-provenance gate;
- both local embedding candidates fit the Apple M1 runtime budget;
- `bge-m3:567m` has the stronger scientific retrieval result, with Recall@5 `5/8`, MRR `0.604`, and all three misses at rank 6;
- dense-only cosine retrieval does not satisfy the required Recall@5 `6/8` gate;
- Track C generation and Track D proof remain `not_run`.

Q0.1 accepts `bge-m3:567m` as the dense embedding component. It does not retroactively convert the failed dense-only Q0 result into a pass. It qualifies one new retrieval configuration: BGE-M3 dense retrieval plus deterministic BM25 lexical retrieval fused by Reciprocal Rank Fusion (RRF).

## 2. Authority and amendment boundary

This specification changes only:

1. Track B candidate topology from two dense-only model candidates to one approved hybrid retrieval configuration;
2. the condition that unlocks the existing Track C and Track D requirements;
3. the durable artifact names for the supplemental run.

All unchanged corpus, provenance, generation, citation, security, cleanup, and evidence requirements from Q0 revision 1.2 remain binding. Where this specification conflicts with Q0 revision 1.2 on retrieval composition or downstream continuation, this specification controls.

The Q0 run `q0-20260920T124722Z-cd96df4` and its artifacts are immutable historical evidence. Q0.1 writes a new run directory and never edits, replaces, or deletes the original Q0 results.

## 3. Inherited evidence

Q0.1 must verify these exact inputs before rebuilding temporary state:

| Artifact | SHA-256 |
|---|---|
| `qualification/corpus/manifest.json` | `50e221e0a441607306ba0a6eb9adf517793660c720ca2f5facb41bf5f442b8f9` |
| `qualification/gold/evidence.jsonl` | `858d2547c8dd515eaaad35e8dd73a1597a0dfa9147658128f159d7dab2d820bd` |
| `qualification/gold/reading-order.jsonl` | `d1346420ee29220ebc6cb308fbcfb36a6b6cb680d49a9e01639e642ca3d647bb` |
| Q0 `environment.json` | `fbb995829a87a7eb8172fd0899de6280b2f597fbd9aa2ea9fe2906856eb4b93f` |
| Q0 `parser.json` | `820fb2a71f075570bf89872cf468b4ac23e18c373009e06de109b8086c096c61` |
| Q0 `embedding.json` | `28536767095569d87f136fe848f9842a310deb649eb08b588ede156fd5c714c1` |

Inherited decisions:

- corpus: exactly arXiv `1706.03762` and `2005.11401` with the existing PDF hashes and page counts;
- parser: PyMuPDF `1.28.2`, geometry-first, zero-based pages, bottom-left PDF coordinates;
- dense model: native ARM64 Ollama `bge-m3:567m`, empty query/document prefixes, cosine distance, `truncate:false`, batch size `8`, concurrency `1`;
- frozen chunk contract: `93` chunks, `max_chars=2000`, zero overlap, paragraph-boundary preference, no cross-section chunk, stable source IDs, complete block/source-span references;
- expected regenerated chunk-set SHA-256: `0aa4bbf11729158948230963930520c2cb52b04e5a292f03ba97c64d7c572cde`.

If any inherited artifact hash or regenerated chunk-set hash differs, Q0.1 stops. It does not rewrite gold truth or accept a new corpus/chunk identity.

## 4. Track B-H — Hybrid retrieval qualification

### 4.1 Configuration under test

Q0.1 evaluates one configuration, not a new model search:

```text
BGE-M3 dense top-10
        +
BM25 lexical top-10
        ↓
RRF(k=60)
        ↓
final top-5
```

Dense retrieval uses the inherited Q0 BGE-M3 configuration and a new Qdrant collection tied to the Q0.1 run.

BM25 is deterministic and in-process for the throwaway probe. It uses the same 93 chunk texts as dense retrieval and the following fixed semantics:

- Unicode NFKC normalization followed by Unicode case-folding;
- tokens are maximal Unicode alphanumeric runs;
- no stemming, language-specific segmentation, synonym expansion, or stop-word removal;
- Okapi BM25 with `k1=1.5` and `b=0.75`;
- inverse document frequency is `ln(1 + (N - df + 0.5) / (df + 0.5))`;
- query term frequency does not multiply repeated query tokens.

RRF uses one-based ranks and:

```text
score(document) = Σ 1 / (60 + rank_channel(document))
```

A document absent from a channel contributes zero for that channel. Final ordering is deterministic by:

1. fused score descending;
2. best dense rank ascending;
3. best BM25 rank ascending;
4. stable source ID ascending.

Q0.1 excludes weighted score blending, query rewriting, reranking, a third embedding model, learned sparse encoders, and parameter tuning against individual gold cases.

### 4.2 Measurements

Use the same eight answerable gold questions and record:

- regenerated parser-block and chunk-set identities;
- BGE-M3 tag, digest, dimension, quantization, runtime placement, and vector checks;
- BM25 tokenizer identity, formula, parameters, corpus size, and index hash;
- dense top-10, BM25 top-10, fused top-10, and first relevant rank for every case;
- Recall@1, Recall@5, and MRR for dense-only, BM25-only, and fused retrieval;
- one unmeasured warm-up followed by three measured fused queries for each question;
- fused end-to-end p50/p95 latency, including both retrieval channels and fusion;
- dense indexing time, lexical indexing time, total indexing time, and peak memory;
- error analysis for every miss and the three prior BGE-M3 rank-6 cases;
- selected golden top-5 context with stable source IDs, text, spans, retrieval-channel ranks, and fused scores in ignored private storage.

### 4.3 Gate

The hybrid configuration qualifies only when:

- regenerated chunks match the inherited 93-chunk SHA-256 exactly;
- BGE-M3 remains stable, finite, non-zero, dimension-consistent, and untruncated;
- fused Recall@5 is at least `0.75` (`6/8` cases);
- fused Recall@5 is not lower than dense-only Recall@5 from the same run;
- the golden case `1706.03762-answer-1` is present in the fused top-5 with complete source-span provenance;
- fused warm p95 latency is below one second;
- total indexing completes within five minutes;
- no crash, OOM, malformed rank, duplicate source ID, corpus drift, or provenance loss occurs.

Passing this gate selects the exact retrieval configuration `bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)` and unlocks Track C. Failure leaves Q0 `Blocked`; Track C and Track D remain `not_run`.

## 5. Track C — Pinned hosted generation

Track C runs only after Track B-H passes and freezes its golden top-5 context.

The qualified path remains exactly:

- base URL: `http://127.0.0.1:20128/v1`;
- 9Router version: `0.5.81`;
- provider connection: `2386766d-a7c1-4839-953c-deaeaa10e719`;
- direct route: `gc/gemini-2.5-flash`;
- one selected account, no combo, mutable alias, fallback, RTK, Caveman, prompt transformation, cloud sync, tunnel, or unredacted body logging.

Before live traffic, Q0.1 must pass network-disabled Chat Completions SSE fixture tests for request shape, event ordering, strict `GroundedAnswer` validation, citations, refusal, usage, identity mismatch, and typed failures.

Live scope is exactly:

1. one schema-constrained streaming preflight;
2. golden case `1706.03762-answer-1` using the frozen hybrid top-5 context;
3. immediate follow-up `What failure mode would occur without that scaling?`;
4. unanswerable case `1706.03762-unanswerable`.

The Track C gate remains Q0 revision 1.2 §8.4 without relaxation: first-attempt schema validity, typed terminal events, claim-marker coverage `1.0`, valid supplied source IDs and exact evidence quotes, correct follow-up referent, grounded refusal with empty citations, provider-reported usage, and stable configured/requested/response identities.

Creating or revoking the dedicated Q0.1 9Router key and temporarily changing provider-connection activation flags are security-sensitive external mutations. They require explicit point-of-risk user confirmation. Original connection flags must be restored exactly before finalization. New paid spend requires separate explicit approval naming Gemini, the exact route, maximum spend, and four-request scope.

Failure leaves Q0 `Blocked`, records Track C evidence and blocker, and leaves Track D `not_run`.

## 6. Track D — Integrated evidence proof

Track D runs only after Track C passes. It makes no additional live generation request.

Use the validated golden `GroundedAnswer` and the exact supplied hybrid top-5 context to resolve:

```text
evidence quote
→ selected source ID
→ normalized character offsets
→ PyMuPDF source spans
→ page and bottom-left bounding boxes
→ self-contained HTML highlight
```

The proof gate remains Q0 revision 1.2 §9:

- all substantive claims have visible valid markers;
- markers map one-to-one to citations;
- every citation uses a supplied source ID and a locally verified evidence quote;
- the selected quote resolves to page 3 of `1706.03762` and overlaps the independent golden region;
- non-empty boxes cover the expected scaled-dot-product sentence without crossing columns;
- the HTML has no external JavaScript or asset;
- Chromium inspection at `1440×1000` confirms the highlight, semantic structure, claim support, and complete identity footer.

A page-only resolution does not pass.

## 7. Durable outputs and privacy boundary

Q0.1 writes a new `qualification/results/<q0.1-run-id>/` directory. A successful run retains exactly:

```text
environment.json
hybrid-retrieval.json
generation.json
integrated-proof.json
evidence-highlight.html
```

The Q0.1 report is stored under `docs/superpowers/reports/` and links both the immutable Q0 baseline and the Q0.1 run.

A blocked run retains only artifacts completed before the failed gate. Every downstream stage is reported as `not_run`; absent results and HTML are not fabricated.

Temporary parser blocks, chunks, BM25 index state, retrieved text, validated generation payloads, screenshots, PDFs, model weights, `.env`, API keys, restore manifests, raw SDK chunks, prompts, and provider bodies remain ignored and are deleted during cleanup.

The complete Q0.1 probe remains throwaway code under `experiments/q0-1/` and is removed before the final gate transition.

## 8. Stop conditions

Stop and finalize an evidence-backed blocker when:

- any inherited artifact or regenerated chunk identity differs;
- hybrid retrieval fails any Track B-H gate;
- the pinned 9Router route cannot complete all three cases without identity drift, fallback, missing usage, schema/citation failure, or account/model switching;
- exact golden geometry or browser-visible highlight cannot be proven;
- 9Router connection flags cannot be restored exactly;
- the probe requires parameter tuning, a reranker, another embedding model, a broader corpus, or a changed threshold;
- the bounded execution timebox expires.

A stopped Q0.1 run is valid evidence but leaves Q0 `Blocked`.

## 9. Exit gate

Q0 changes from `Blocked` to `Verified` only when:

1. all inherited Q0 artifact hashes and the regenerated chunk-set hash match;
2. the BGE-M3 + BM25 + RRF configuration passes Track B-H;
3. the pinned 9Router path passes Track C with all three cases;
4. Track D proves exact visible evidence in Chromium;
5. durable Q0.1 artifacts and the report agree;
6. 9Router state is restored, the dedicated key is revoked, services/models are stopped, and temporary/private data is deleted;
7. `experiments/q0-1/` and every forbidden artifact are absent from Git;
8. the delivery map links both the original blocked Q0 evidence and the successful Q0.1 evidence.

Passing Q0.1 authorizes M1 design and planning. It does not promote probe code or the in-process BM25 implementation into production. Production retrieval backend design remains owned by M3, and broader corpus evaluation remains owned by M5.

## 10. Non-goals

Q0.1 does not:

- revise the original Q0 result or gold annotations;
- compare additional embedding or generation models;
- tune BM25 or RRF parameters against the eight gold questions;
- add reranking, query expansion, lexical synonyms, or learned sparse vectors;
- define the production PostgreSQL/Qdrant retrieval implementation;
- build production API, jobs, authentication, UI, or persistent schemas;
- claim statistical generality beyond the fixed two-paper corpus;
- qualify any 9Router route, account, endpoint, or model other than the pinned path above.
