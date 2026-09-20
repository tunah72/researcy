# Researcy Q0 Technical Qualification Report

- Date: 2026-09-20
- Worktree: `/Users/tuananhduong/Projects/researcy-q0-technical-qualification`
- Branch: `q0-technical-qualification`
- Run ID: `q0-20260920T124722Z-cd96df4`
- Final Gate State: **Blocked**
- Blocker Stage: **Track B (On-device embedding and retrieval)**
- Initialized Revision: `cd96df403a0b3c451647879bf0b0fa7f8295bf77`
- Environment / Retrieval Producer Revision: `62251fe28aefb4931a852fae7e84261c4c6cfebf`
- Parser Producer Revision: `5486028474dca62c3de6232579663a3c7d6e2ec5`
- Hardware / Platform: Apple M1 (arm64), 8 GB RAM, macOS 26.6, Python 3.12.13
- Services: native Ollama 0.18.2 (`127.0.0.1:11434`), Qdrant 1.19.0 (`127.0.0.1:6333`, container image `sha256:057ee3a8da769fe7310dd3537b4dc7583bf87a95ce8ac43c0af5a46bc580d1fc`)

---

## 1. Executive Decision Summary

Under specification revision 1.2 (§§6, 7, 13) and the approved implementation plan:

1. **Track A (Parser & Provenance): Qualified & Selected**
   - Candidate: `pymupdf` (geometry-first).
   - Passed all binding §6.3 criteria: 8/8 expected-page cases, 8/8 quote geometry resolutions, fixed-page LCS coverage 0.9859 (`1706.03762` p. 3) and 0.9632 (`2005.11401` p. 5), 12/12 reading-order relations, golden-region resolution in the correct column, and deterministic character-to-box reversible provenance without fuzzy recovery.
   - Candidate `docling` (v2, no OCR, table structure enabled) failed the gate (5/8 expected-page/geometry cases, 0.8267 coverage on RAG page 5, 7/12 reading order, no golden-region resolution).
   - Artifact: [`qualification/results/q0-20260920T124722Z-cd96df4/parser.json`](./qualification/results/q0-20260920T124722Z-cd96df4/parser.json).

2. **Track B (On-Device Embedding & Retrieval): Blocked (§13 Stop Condition)**
   - Neither candidate met the Recall@5 $\ge 0.75$ (6/8 cases) qualification threshold in §7.2.
   - `bge-m3:567m`: Recall@5 = **0.625** (5/8 hits), Recall@1 = 0.500 (4/8), MRR = 0.604, indexing time = 86.4s, p50 warm latency = 0.236s, p95 warm latency = 0.445s, peak memory = 1,466,695,680 B.
   - `nomic-embed-text:137m-v1.5-fp16`: Recall@5 = **0.500** (4/8 hits), Recall@1 = 0.250 (2/8), MRR = 0.341, indexing time = 10.5s, p50 warm latency = 0.053s, p95 warm latency = 0.120s, peak memory = 813,678,592 B.
   - Root Cause: Pure dense cosine retrieval without lexical keyword matching (BM25) or cross-encoder reranking placed 3 answerable scientific cases at rank 6 for BGE-M3 (just outside the top-5 cutoff).
   - Stop Condition: In accordance with §13, the spike was halted immediately without weakening thresholds, adding unapproved candidates, or executing downstream live traffic.
   - Artifact: [`qualification/results/q0-20260920T124722Z-cd96df4/embedding.json`](./qualification/results/q0-20260920T124722Z-cd96df4/embedding.json).

3. **Track C (Hosted Generation via 9Router): not_run**
   - Reason: Gate stopped at Track B. Per shared blocked-run finalization, downstream gateway traffic was not run to prevent unnecessary external account mutation and invalid data fabrication.

4. **Track D (Integrated Evidence Proof): not_run**
   - Reason: Gate stopped at Track B; no HTML proof was fabricated.

---

## 2. Representative Corpus & Independent Gold Baseline

- **arXiv 1706.03762** ("Attention Is All You Need", 15 pages, SHA-256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`)
- **arXiv 2005.11401** ("Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", 19 pages, SHA-256 `23e3249e9a1e75418d82efecab0ea8c4d033b89c93742f63208d47ce01f21233`)
- Gold cases: 8 answerable, 2 unanswerable.
- Independent coverage reference pages: page 3 of `1706.03762` and page 5 of `2005.11401`.
- Independent golden boxes: 3 boxes covering the scaled dot-product attention sentence on page 3 of `1706.03762` in bottom-left coordinates.
- Reading-order relations: 12 relations across column, table, and caption boundaries.

---

## 3. Detailed Gate Outcomes

### Track A: Parser Gate

| Criterion | Requirement (§6.3) | PyMuPDF geometry-first | Docling v2 (no OCR, table structure) |
|---|---|---|---|
| All answerable quotes resolve to expected page | 8/8 (1.0) | **8/8 (1.0)** (Pass) | 5/8 (0.625) (Fail) |
| Non-empty geometry for every quote | 8/8 (1.0) | **8/8 (1.0)** (Pass) | 5/8 (0.625) (Fail) |
| Fixed-page token LCS coverage | $\ge 0.90$ both pages | **0.9859** (p3), **0.9632** (p5) (Pass) | 0.9238 (p3), 0.8267 (p5) (Fail) |
| Reading-order relation correctness | $\ge 10/12$ | **12/12 (1.0)** (Pass) | 7/12 (0.5833) (Fail) |
| Golden region overlap in correct column | Required | **Resolved (Pass)** | Not resolved (Fail) |
| Reversible offsets | Required | **True (Pass)** | True (Pass) |
| Successful parsing of both PDFs | Required | **True (Pass)** | True (Pass) |
| Elapsed time / Peak memory | Measured | 2.73s / 263.4 MB | 36.88s / 874.5 MB |
| **Status** | | **Qualified (Selected)** | **Failed gate** |

### Track B: Embedding Gate

| Criterion | Requirement (§7.2) | `bge-m3:567m` | `nomic-embed-text:137m-v1.5-fp16` |
|---|---|---|---|
| Stability (no crash/OOM/malformed vectors) | Required | **Passed** (dim 1024) | **Passed** (dim 768) |
| Truncation | No silent truncation | **Passed** (`truncate: false`) | **Passed** (`truncate: false`) |
| Golden paper indexing time | $\le 300\text{s}$ | **86.4s** (Pass) | **10.5s** (Pass) |
| Latency p95 (24 warm samples) | $< 1.0\text{s}$ | **0.445s** (Pass) | **0.120s** (Pass) |
| Recall@5 | $\ge 6/8$ (0.75) | **5/8 (0.625)** (Fail) | **4/8 (0.500)** (Fail) |
| MRR | Measured | 0.604 | 0.341 |
| Peak memory | Measured | 1.47 GB | 813.7 MB |
| **Status** | | **Failed gate** | **Failed gate** |

---

## 4. Next Actions for Unblocking

Per specification §13 and §14:

1. **Do not weaken Q0 thresholds** or manufacture a passing result.
2. **Authorize Hybrid Retrieval Architecture for M2/M3**:
   - The root cause is the exclusion of sparse lexical search (BM25) and reciprocal rank fusion (RRF) in the Q0 probe.
   - BGE-M3 placed the 3 missing cases at rank 6; combining sparse lexical tokens with dense embeddings will unblock the retrieval quality bar for scientific papers.
3. Keep Q0 recorded as `Blocked` until this architectural direction is confirmed.
