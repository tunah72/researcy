# Researcy Q0.1 Hybrid Retrieval and Evidence Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify `bge-m3:567m + BM25 + RRF`, then qualify the pinned 9Router generation route and prove exact question-to-PDF highlight geometry without changing the immutable Q0 baseline.

**Architecture:** Build a second throwaway Python probe under `experiments/q0-1/`. It verifies and reuses the frozen Q0 corpus, PyMuPDF parser decision, and exact 93-chunk identity; evaluates one deterministic hybrid retrieval configuration; then conditionally runs the existing pinned generation and integrated-proof gates. Durable evidence is written to a new Q0.1 run directory while the original Q0 results remain byte-identical.

**Tech Stack:** Python 3.12, uv, Pydantic 2, PyMuPDF 1.28.x, native ARM64 Ollama 0.18.2, `bge-m3:567m`, Qdrant 1.19.0, deterministic in-process Okapi BM25, RRF, httpx, OpenAI Python SDK, 9Router 0.5.81, pytest, static HTML/SVG, real Chromium inspection.

**Spec:** `docs/superpowers/specs/2026-09-21-researcy-q0-1-hybrid-qualification.md`, revision 1.0

## Global Constraints

- Execute in a new isolated worktree and branch; never implement on `main`.
- The Q0 run `q0-20260920T124722Z-cd96df4` and all six inherited artifact hashes are immutable.
- Parser strategy is fixed: PyMuPDF 1.28.2, geometry-first, zero-based pages, bottom-left coordinates.
- Dense model is fixed: native Ollama `bge-m3:567m`, empty query/document prefixes, cosine distance, `truncate:false`, batch size `8`, concurrency `1`.
- Hybrid configuration is fixed: BGE-M3 dense top-10 + BM25 top-10 + RRF `k=60` → final top-5.
- BM25 is fixed: NFKC + case-fold, maximal Unicode alphanumeric tokens, no stemming/stopwords/synonyms, `k1=1.5`, `b=0.75`, exact approved IDF formula.
- No parameter tuning, reranker, query rewriting, third embedding model, learned sparse encoder, broader corpus, or threshold change.
- Track C runs only after Track B-H passes. Track D runs only after Track C passes and makes no additional generation request.
- Live generation is exactly one preflight plus three cases through 9Router 0.5.81, connection `2386766d-a7c1-4839-953c-deaeaa10e719`, route `gc/gemini-2.5-flash`.
- Creating/revoking the dedicated gateway key and changing provider-connection flags require explicit point-of-risk user confirmation during execution.
- New paid spend requires separate explicit approval naming Gemini, route, maximum spend, and four-request scope.
- PDFs, model weights, `.env`, keys, prompts, retrieved source text, raw provider bodies, screenshots, private chunks, and restore manifests are never committed.
- Commit probe code before every measurement. Every durable artifact names the clean producer Git revision.
- Delete `experiments/q0-1/`, private/cache data, temporary indexes, and credentials before the final gate transition.

---

## Planned File Map

### Temporary probe — deleted during finalization

```text
experiments/q0-1/
├── .env.example
├── compose.yml
├── pyproject.toml
├── uv.lock
├── src/q0/
│   ├── __init__.py
│   ├── baseline.py       # inherited hashes, exact corpus, PyMuPDF block/chunk regeneration
│   ├── cli.py            # q01 command surface only
│   ├── generation.py     # domain generation boundary and OpenAI-compatible transport
│   ├── hybrid.py         # deterministic BM25, RRF, BGE/Qdrant measurement and gate
│   ├── models.py         # strict domain/result models and durable atomic writes
│   └── proof.py          # citation/geometry validation and self-contained HTML
└── tests/
    ├── test_baseline.py
    ├── test_hybrid.py
    ├── test_generation.py
    └── test_proof.py
```

### Durable evidence

```text
qualification/results/<q0.1-run-id>/
├── environment.json
├── hybrid-retrieval.json
├── generation.json
├── integrated-proof.json
└── evidence-highlight.html

docs/superpowers/reports/2026-09-21-researcy-q0-1-hybrid-qualification-report.md
```

### Ignored private state

```text
qualification/.cache/pdfs/
qualification/private/q0-1-run-id.txt
qualification/private/<q0.1-run-id>/
├── parsed-blocks-pymupdf.jsonl
├── chunks.jsonl
├── bm25-index.json
├── hybrid-run.json
├── golden-retrieved-context.json
├── generation-restore-manifest.json
└── validated-generation.json
```

## Stable interfaces

Use `artifact_version="q0.1-hybrid-1"` and strict Pydantic models with `extra="forbid"`.

```python
class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class SourceSpan(BaseModel):
    text_start: int
    text_end: int
    page_index: int
    bbox: BBox


class ParsedBlock(BaseModel):
    paper_id: str
    page_index: int
    section_path: list[str]
    block_type: str
    reading_order: int
    normalized_text: str
    source_spans: list[SourceSpan]
    page_width: float
    page_height: float
    coordinate_origin: Literal["bottom-left"]


class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    section_path: list[str]
    heading: str | None
    page_indices: list[int]
    block_indices: list[int]
    text: str
    source_spans: list[SourceSpan]


class RankedHit(BaseModel):
    chunk_id: str
    score: float
    rank: int


class HybridCaseResult(BaseModel):
    case_id: str
    dense_top_10: list[RankedHit]
    bm25_top_10: list[RankedHit]
    fused_top_10: list[RankedHit]
    first_relevant_rank: int | None


class Citation(BaseModel):
    marker: int
    source_ref: str
    evidence_quote: str


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[Citation]


class RetrievedSource(BaseModel):
    source_ref: str
    chunk_id: str
    text: str


class GenerationRequest(BaseModel):
    case_id: str
    question: str
    answerable: bool
    sources: list[RetrievedSource]
    prior_answer: GroundedAnswer | None = None


class GenerationUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class AnswerDelta(BaseModel):
    type: Literal["answer.delta"] = "answer.delta"
    text: str


class AnswerCompleted(BaseModel):
    type: Literal["answer.completed"] = "answer.completed"
    answer: GroundedAnswer
    usage: GenerationUsage
    requested_model: str
    response_model: str
    upstream_identity: str | None = None


class AnswerFailed(BaseModel):
    type: Literal["answer.failed"] = "answer.failed"
    category: Literal[
        "authentication", "rate_limit", "timeout", "interrupted_stream",
        "malformed_output", "unavailable", "identity_mismatch",
    ]
    message: str


GenerationEvent = Annotated[
    AnswerDelta | AnswerCompleted | AnswerFailed,
    Field(discriminator="type"),
]


class GatewayIdentity(BaseModel):
    gateway: Literal["9router"]
    version: Literal["0.5.81"]
    connection_id: Literal["2386766d-a7c1-4839-953c-deaeaa10e719"]
    route: Literal["gc/gemini-2.5-flash"]
    requested_model: str
    response_model: str
    upstream_identity: str | None = None


class ProofIdentity(BaseModel):
    parser: Literal["pymupdf"]
    retrieval: Literal[
        "bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)"
    ]
    gateway_version: Literal["0.5.81"]
    connection_id: Literal["2386766d-a7c1-4839-953c-deaeaa10e719"]
    route: Literal["gc/gemini-2.5-flash"]
    requested_model: str
    response_model: str
    run_id: str
```

`GenerationClient` exposes only:

```python
class GenerationClient(Protocol):
    def stream_answer(
        self, request: GenerationRequest
    ) -> AsyncIterator[GenerationEvent]: ...
```

Domain events use only `answer.delta`, `answer.completed`, and `answer.failed`. `citation.resolved` is produced locally by proof orchestration, not by the transport client.

## Shared blocked-run finalization

When Track B-H, Track C, or Track D fails:

1. finish the current stage artifact with producer revision, measurements, threshold outcomes, and one concrete blocker;
2. do not run downstream commands; report every downstream stage as `not_run`;
3. if Track C changed 9Router, restore every connection flag exactly, verify the ID/flag set, revoke the dedicated Q0.1 key, and delete the private restore manifest;
4. write the Q0.1 report from durable JSON only and link the immutable Q0 baseline;
5. keep Q0 `Blocked` in the delivery map and link only artifacts that exist;
6. run `docker compose down -v`, stop `bge-m3:567m`, remove private/cache data, and delete `experiments/q0-1/`;
7. validate retained JSON/JSONL, links, forbidden-file absence, and clean service state;
8. commit the evidence-backed blocker and cleanup. Never fabricate downstream JSON or HTML.

---

### Task 1: Rebuild the exact inherited baseline and initialize Q0.1

**Files:**
- Modify: `.gitignore`
- Create: `experiments/q0-1/.env.example`
- Create: `experiments/q0-1/compose.yml`
- Create: `experiments/q0-1/pyproject.toml`
- Create: `experiments/q0-1/uv.lock`
- Create: `experiments/q0-1/src/q0/__init__.py`
- Create: `experiments/q0-1/src/q0/models.py`
- Create: `experiments/q0-1/src/q0/baseline.py`
- Create: `experiments/q0-1/src/q0/cli.py`
- Create: `experiments/q0-1/tests/test_baseline.py`
- Create: `qualification/results/<q0.1-run-id>/environment.json`

**Interfaces:**
- Consumes: the six approved Q0 artifact hashes, exact corpus manifest/gold, PyMuPDF decision, and historical reviewed probe at Git revision `772c132`.
- Produces: `q01 init-run`, `q01 run-id`, `q01 baseline prepare`, strict shared models, one new run ID, exact `parsed-blocks-pymupdf.jsonl`, exact `chunks.jsonl`, and a committed `environment.json`.

- [ ] **Step 1: Create the isolated execution branch and restore reviewed throwaway code as input**

Use the execution workflow to create branch `q0-1-hybrid-qualification` in a sibling worktree. Confirm tracked state is clean before changes. Restore the reviewed historical probe, move it to the Q0.1 path, then prune obsolete candidate code rather than reimplementing provenance from memory:

```bash
git restore --source=772c132 --worktree -- experiments/q0
mv experiments/q0 experiments/q0-1
rm experiments/q0-1/uv.lock
```

Keep the reviewed atomic-write, corpus validation, PyMuPDF normalization/provenance, chunking, and metric functions. Remove Docling, Nomic, dual-candidate selection, and their tests/dependencies. Rename the console command to `q01`, but keep the internal Python package `q0` to minimize throwaway-only churn.

- [ ] **Step 2: Define the isolated environment and ignore boundary**

Add temporary ignore entries:

```gitignore
experiments/q0-1/.venv/
experiments/q0-1/.pytest_cache/
experiments/q0-1/**/__pycache__/
```

`experiments/q0-1/.env.example` contains names only:

```dotenv
GENERATION_BASE_URL=
GENERATION_API_KEY=
GENERATION_MODEL=
Q0_9ROUTER_VERSION=
Q0_9ROUTER_CONNECTION_ID=
```

`compose.yml` contains only `qdrant/qdrant:v1.19.0`, bound to `127.0.0.1:6333`, with one Q0.1-named volume and `/healthz` health check.

Use Python `>=3.12,<3.13` and these direct dependency ranges:

```text
pydantic>=2,<3
httpx>=0.28,<1
pymupdf>=1.28,<1.29
qdrant-client>=1.15,<2
openai>=1,<2
psutil>=7,<8
pytest>=8,<9
```

Expose `q01 = "q0.cli:main"`. Run:

```bash
cd experiments/q0-1
uv lock
uv sync --locked
uv run q01 --help
```

Expected commands: `init-run`, `run-id`, `baseline`, `hybrid`, `generation`, and `proof`.

- [ ] **Step 3: Update strict shared models and Q0.1 run identity**

Set:

```python
ARTIFACT_VERSION = "q0.1-hybrid-1"
BASELINE_RUN_ID = "q0-20260920T124722Z-cd96df4"
EXPECTED_CHUNK_SHA256 = "0aa4bbf11729158948230963930520c2cb52b04e5a292f03ba97c64d7c572cde"
```

Add `EnvironmentResult`, `HybridRetrievalResult`, `GenerationResult`, and `IntegratedProofResult`. `EnvironmentResult` stores:

```python
class EnvironmentResult(QualificationResult):
    initialized_at_utc: datetime
    run_initialized_git_revision: str
    producer_git_revision: str
    tracked_tree_clean: bool
    baseline_run_id: Literal["q0-20260920T124722Z-cd96df4"]
    inherited_artifact_sha256: dict[str, str]
    regenerated_chunk_set_sha256: str | None = None
    os_version: str
    architecture: str
    physical_memory_bytes: int
    python_version: str
    ollama_version: str | None = None
    qdrant_version: str | None = None
    qdrant_container_image_id: str | None = None
```

Preserve sibling temporary file creation, file `fsync`, `os.replace`, and directory `fsync` for every durable JSON or text write.

`q01 init-run` must ignore the old `q0-*` directory, reject more than one `q0-1-*` environment, use `q0-1-<UTC>-<7-char-sha>`, atomically store it in `qualification/private/q0-1-run-id.txt`, and write only the new environment path.

- [ ] **Step 4: Write inherited-evidence and baseline tests first**

Add focused tests:

```python
def make_block(*, section_path: list[str], text: str, order: int) -> ParsedBlock:
    return ParsedBlock(
        paper_id="paper",
        page_index=0,
        section_path=section_path,
        block_type="text",
        reading_order=order,
        normalized_text=text,
        source_spans=[
            SourceSpan(
                text_start=0,
                text_end=len(text),
                page_index=0,
                bbox=BBox(x0=10, y0=10, x1=100, y1=20),
            )
        ],
        page_width=612,
        page_height=792,
        coordinate_origin="bottom-left",
    )


def test_inherited_artifact_hash_mismatch_stops_before_rebuild(tmp_path):
    artifact = tmp_path / "parser.json"
    artifact.write_text("changed", encoding="utf-8")
    with pytest.raises(BaselineValidationError, match="parser.json"):
        verify_file_hash(artifact, "0" * 64)


def test_q01_run_discovery_ignores_original_q0_environment(tmp_path):
    results = tmp_path / "qualification" / "results"
    for run_id in (
        "q0-20260920T124722Z-cd96df4",
        "q0-1-20260921T000000Z-abcdef0",
    ):
        path = results / run_id / "environment.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    assert discover_q01_run_id(tmp_path) == "q0-1-20260921T000000Z-abcdef0"


def test_chunk_regeneration_rejects_identity_drift():
    with pytest.raises(BaselineValidationError, match="chunk-set SHA-256"):
        require_chunk_identity(observed="f" * 64)


def test_chunking_never_crosses_section_boundaries():
    blocks = [
        make_block(section_path=["3.2.1"], text="scaled attention", order=0),
        make_block(section_path=["3.2.2"], text="multi-head attention", order=1),
    ]
    chunks = build_chunks(blocks, max_chars=2000)
    assert [chunk.section_path for chunk in chunks] == [["3.2.1"], ["3.2.2"]]
    assert all(chunk.source_spans for chunk in chunks)
```

Run:

```bash
cd experiments/q0-1
uv run pytest tests/test_baseline.py -q
```

Expected: FAIL because Q0.1 hash verification, run discovery, and baseline preparation are not implemented.

- [ ] **Step 5: Implement exact inherited verification and baseline regeneration**

Hard-code the six approved hashes from the Q0.1 specification. `baseline prepare` must:

1. verify all six tracked artifacts before network or parsing;
2. download only the two manifest URLs into ignored `qualification/.cache/pdfs/` when absent;
3. reject non-PDF bytes and require the manifest SHA-256 and page count exactly;
4. run only the reviewed PyMuPDF adapter and validate every `ParsedBlock`;
5. write `parsed-blocks-pymupdf.jsonl` under the Q0.1 private run directory;
6. rebuild chunks with `max_chars=2000`, zero overlap, paragraph preference, and no cross-section chunk;
7. require exactly 93 chunks and SHA-256 `0aa4bbf11729158948230963930520c2cb52b04e5a292f03ba97c64d7c572cde`;
8. update `environment.json.regenerated_chunk_set_sha256` and baseline measurements without changing `run_initialized_git_revision`.

Candidate output must never alter manifest, gold evidence, reading-order truth, or the original Q0 results.

- [ ] **Step 6: Pass tests and commit the baseline producer before measurement**

```bash
cd experiments/q0-1
uv run pytest tests/test_baseline.py -q
uv run q01 --help
cd ../..
git add .gitignore experiments/q0-1
git commit -m "experiment(q0.1): add exact inherited baseline probe"
```

- [ ] **Step 7: Initialize and prepare one Q0.1 run from the clean producer**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0-1
RUN_ID=$(uv run q01 init-run --root ../..)
uv run q01 baseline prepare --run-id "$RUN_ID" --root ../..
uv run q01 run-id --root ../..
printf '%s\n' "$RUN_ID"
```

Verify the new environment records the clean producer revision, six exact inherited hashes, 93 chunks, the exact chunk hash, two exact PDFs, PyMuPDF 1.28.2, bottom-left coordinates, and `tracked_tree_clean: true`. Commit only the durable environment result:

```bash
cd ../..
git add "qualification/results/$RUN_ID/environment.json"
git commit -m "experiment(q0.1): initialize hybrid qualification run"
```

---

### Task 2: Qualify BGE-M3 + BM25 + RRF

**Files:**
- Create: `experiments/q0-1/src/q0/hybrid.py`
- Modify: `experiments/q0-1/src/q0/cli.py`
- Create: `experiments/q0-1/tests/test_hybrid.py`
- Modify: `qualification/results/<q0.1-run-id>/environment.json`
- Create: `qualification/results/<q0.1-run-id>/hybrid-retrieval.json`

**Interfaces:**
- Consumes: exact private `chunks.jsonl`, eight answerable cases, BGE-M3 through native Ollama, Qdrant 1.19.0.
- Produces: `tokenize_bm25`, `Bm25Index`, `reciprocal_rank_fusion`, `run_hybrid_preflight`, `run_hybrid_measurement`, `evaluate_hybrid_gate`, one selected retrieval configuration, and private `golden-retrieved-context.json`.

- [ ] **Step 1: Start only the required local runtimes**

```bash
cd experiments/q0-1
docker compose up -d --wait
```

Use the `read` tool on `http://127.0.0.1:6333/healthz` and `http://127.0.0.1:11434/api/version`. Confirm Qdrant reports 1.19.0 and Ollama reports 0.18.2. Pull `bge-m3:567m` only if `/api/show` says it is absent. Do not start PostgreSQL, MinIO, another embedding model, or a reranker.

- [ ] **Step 2: Write deterministic BM25 and RRF tests first**

```python
def test_tokenizer_is_nfkc_casefolded_unicode_alphanumeric():
    assert tokenize_bm25("Scaled DOT-product d_k café!") == [
        "scaled", "dot", "product", "d", "k", "café"
    ]


def test_repeated_query_terms_do_not_multiply_bm25_score():
    index = Bm25Index.from_documents({"A": "attention scaling", "B": "attention"})
    assert index.rank("attention attention") == index.rank("attention")


def test_bm25_prefers_exact_scientific_terms():
    index = Bm25Index.from_documents({
        "A": "dot products grow large and softmax gradients become small",
        "B": "multi head attention representation subspaces",
    })
    assert index.rank("large dot products softmax gradients")[0].chunk_id == "A"


def test_rrf_uses_one_based_ranks_and_stable_tie_breaks():
    fused = reciprocal_rank_fusion(
        dense_ids=["B", "A", "C"],
        bm25_ids=["A", "B", "C"],
        k=60,
    )
    assert [hit.chunk_id for hit in fused] == ["B", "A", "C"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)


def test_hybrid_gate_requires_six_of_eight_recall_at_five():
    assert evaluate_recall_gate(6, total=8).passed
    assert not evaluate_recall_gate(5, total=8).passed
```

Add tests for finite/non-zero stable BGE vectors, unique chunk IDs, fused ordering determinism, exact 24-sample latency count, golden-case presence, and rejection of a changed chunk hash.

Run:

```bash
cd experiments/q0-1
uv run pytest tests/test_hybrid.py -q
```

Expected: FAIL because the BM25 index, RRF, and hybrid gate do not exist.

- [ ] **Step 3: Implement fixed BM25 and RRF without a new dependency**

Tokenization:

```python
def tokenize_bm25(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
```

Deduplicate query tokens while preserving order:

```python
query_terms = list(dict.fromkeys(tokenize_bm25(query)))
```

For each query term, compute exactly:

```python
idf = math.log(1 + (document_count - document_frequency + 0.5) /
                    (document_frequency + 0.5))
score += idf * (term_frequency * (k1 + 1)) / (
    term_frequency + k1 * (1 - b + b * document_length / average_document_length)
)
```

Use `k1=1.5`, `b=0.75`. Serialize the sorted source-ID/token-list index to ignored `bm25-index.json` and record its SHA-256.

RRF must use ranks 1–10 and `1/(60+rank)`. Sort by fused score descending, best dense rank ascending, best BM25 rank ascending, then source ID ascending. Reject duplicate IDs within either input list.

- [ ] **Step 4: Implement BGE/Qdrant preflight and hybrid measurement**

`hybrid preflight` verifies:

- exact BGE tag/digest from `/api/show` and `/api/tags`;
- native ARM64 Ollama placement;
- empty prefixes;
- cosine metric;
- `truncate:false`;
- one finite non-zero document vector and one query vector with identical dimension;
- Qdrant health/version and new collection identity;
- exact private chunks and chunk hash.

`hybrid run` must:

1. build one BM25 index over the 93 chunk texts;
2. embed/index every chunk in BGE batches of 8 with concurrency 1;
3. run one unmeasured warm-up query;
4. for each of eight questions, run dense top-10 and BM25 top-10, then RRF top-10;
5. collect three measured fused repetitions for all eight questions, exactly 24 end-to-end samples;
6. record dense-only, BM25-only, and fused Recall@1/5 and MRR;
7. record per-case ranks/lists/scores, index times, p50/p95, peak memory, identities, and failures;
8. persist the selected golden fused top-5 with source IDs, text, spans, dense/BM25 ranks, and fused scores to ignored `golden-retrieved-context.json`.

No gold quote or answer may influence BM25 indexing, ranking, fusion, or tie-breaking. Gold is used only after ranking to compute metrics.

- [ ] **Step 5: Pass tests and commit the clean hybrid producer**

```bash
cd experiments/q0-1
uv run pytest tests/test_baseline.py tests/test_hybrid.py -q
cd ../..
git add experiments/q0-1/src/q0 experiments/q0-1/tests/test_hybrid.py
git commit -m "experiment(q0.1): add deterministic hybrid retrieval probe"
```

- [ ] **Step 6: Measure and apply the complete Track B-H gate**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0-1
RUN_ID=$(uv run q01 run-id --root ../..)
uv run q01 hybrid preflight --run-id "$RUN_ID" --root ../..
uv run q01 hybrid run --run-id "$RUN_ID" --root ../..
uv run q01 hybrid evaluate --run-id "$RUN_ID" --root ../..
```

`hybrid-retrieval.json` must record the clean producer revision, inherited and regenerated identities, BGE configuration, BM25 formula/config/index hash, RRF configuration, all channel rankings, all metrics, exact 24 samples, gate outcomes, and selected configuration only on pass.

Pass requires exact chunk identity, stable BGE vectors, fused Recall@5 at least 6/8 and not below same-run dense Recall@5, golden fused top-5 with complete provenance, p95 below one second, total indexing below five minutes, and no identity/provenance/stability defect.

Commit environment and hybrid result together:

```bash
cd ../..
git add "qualification/results/$RUN_ID/environment.json" \
        "qualification/results/$RUN_ID/hybrid-retrieval.json"
git commit -m "experiment(q0.1): record hybrid retrieval decision"
```

If the gate fails, execute shared blocked-run finalization immediately. Do not begin Task 3.

---

### Task 3: Qualify the pinned 9Router generation path

**Files:**
- Create: `experiments/q0-1/src/q0/generation.py`
- Modify: `experiments/q0-1/src/q0/cli.py`
- Create: `experiments/q0-1/tests/test_generation.py`
- Create: `qualification/results/<q0.1-run-id>/generation.json`

**Interfaces:**
- Consumes: passing `hybrid-retrieval.json`, frozen private golden top-5, golden case, immediate follow-up, unanswerable case, and pinned 9Router identities.
- Produces: `GenerationRequest`, `GenerationClient`, typed `GenerationEvent`, `GenerationError`, `GatewayIdentity`, `OpenAICompatibleGenerationClient`, private validated outputs, and sanitized `generation.json`.

- [ ] **Step 1: Freeze exact inputs and request parameters before traffic**

Use this sequence:

```text
1706.03762-answer-1
What failure mode would occur without that scaling?
1706.03762-unanswerable
```

The follow-up receives only the bounded prior turn. Freeze hybrid source IDs/text, system instructions, strict response schema, and:

```python
TEMPERATURE = 0
TOP_P = 1
MAX_TOKENS = 800
TIMEOUT_SECONDS = 60
MAX_RETRIES = 0
STREAM_OPTIONS = {"include_usage": True}
```

The model receives selected context only, never a complete PDF.

- [ ] **Step 2: Write network-disabled SSE fixture tests first**

Tests must prove:

```python
async def test_request_uses_exact_model_schema_stream_and_usage(fake_server):
    client = configured_client(fake_server.url)
    await collect(client.stream_answer(golden_request()))
    request = fake_server.only_request
    assert request["model"] == "gc/gemini-2.5-flash"
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert request["response_format"]["json_schema"]["strict"] is True


async def test_stream_has_deltas_then_exactly_one_terminal_event(fake_server):
    events = await collect(configured_client(fake_server.url).stream_answer(golden_request()))
    assert any(event.type == "answer.delta" for event in events)
    assert [event.type for event in events].count("answer.completed") == 1
    assert events[-1].type == "answer.completed"


def test_unknown_source_or_mismatched_quote_is_rejected():
    with pytest.raises(GenerationValidationError):
        validate_grounded_answer(answer_with_unknown_source(), supplied_sources())


def test_unanswerable_requires_insufficient_context_and_no_citations():
    validate_refusal(GroundedAnswer(
        answer="The supplied paper context is insufficient to answer this question.",
        citations=[],
    ))
```

Also cover duplicate/non-positive/answer-absent markers, claim-marker coverage, follow-up referent, usage, configured/requested/response/upstream identity mismatch, malformed schema with no retry, interrupted stream, auth, rate-limit, timeout, unavailable, and SDK-type confinement.

Run with network disabled:

```bash
cd experiments/q0-1
uv run pytest tests/test_generation.py -q
```

Expected: FAIL before transport and validation implementation, then PASS using fixtures only.

- [ ] **Step 3: Implement the thin domain/transport boundary**

`OpenAICompatibleGenerationClient` alone owns OpenAI SDK request/response/SSE/error shapes. It emits only domain events and validates the final payload once with `GroundedAnswer`; no format or citation retry exists.

Fail closed unless:

```text
GENERATION_BASE_URL=http://127.0.0.1:20128/v1
GENERATION_MODEL=gc/gemini-2.5-flash
Q0_9ROUTER_VERSION=0.5.81
Q0_9ROUTER_CONNECTION_ID=2386766d-a7c1-4839-953c-deaeaa10e719
GENERATION_API_KEY=<present only in ignored .env>
```

Never persist the key, selected source text, complete prompt, request/response body, raw SDK chunks, email, or provider auth material.

- [ ] **Step 4: Pass fixtures and commit generation code before live traffic**

```bash
cd experiments/q0-1
uv run pytest tests/test_generation.py -q
cd ../..
git add experiments/q0-1/src/q0 experiments/q0-1/tests/test_generation.py \
        experiments/q0-1/.env.example experiments/q0-1/pyproject.toml experiments/q0-1/uv.lock
git commit -m "experiment(q0.1): add pinned generation probe"
```

- [ ] **Step 5: Obtain point-of-risk confirmation and pin 9Router safely**

Immediately before creating/revoking the Q0.1 key or changing active connection flags, ask the user to confirm those exact security-sensitive mutations. If the dashboard is locked, the user unlocks it directly; never request, read, log, or store the password.

Before mutation, write ignored `generation-restore-manifest.json` containing only every connection ID and its current `isActive` flag. In the authenticated dashboard:

1. create a dedicated local API key named `researcy-q0-1` and place it only in ignored `.env`;
2. deactivate every provider connection except `2386766d-a7c1-4839-953c-deaeaa10e719` without deleting connections;
3. verify exactly one active connection, one selected account, literal direct route `gc/gemini-2.5-flash`, no combo/alias/fallback, and disabled RTK/Caveman/prompt transforms/cloud sync/tunnel/body logging;
4. verify existing quota covers exactly one preflight plus three cases. If new paid spend is needed, request the separate approval required by the spec.

Never edit 9Router SQLite directly.

- [ ] **Step 6: Run one preflight and exactly three cases from the clean producer**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0-1
RUN_ID=$(uv run q01 run-id --root ../..)
uv run q01 generation preflight --run-id "$RUN_ID" --root ../..
uv run q01 generation run --run-id "$RUN_ID" --root ../..
```

Preflight authenticates, verifies `/api/version.currentVersion == "0.5.81"`, verifies the literal route in `/v1/models`, verifies the sanitized single-account/single-model assertion, and sends one schema-constrained stream.

The three cases must satisfy every Q0 §8.4 gate. Persist validated domain outputs and normalized event/usage records to ignored `validated-generation.json`. Durable `generation.json` contains only hashes, checks, metrics, typed errors, and non-sensitive identities.

- [ ] **Step 7: Restore gateway state before committing evidence**

Immediately after traffic or any Track C failure:

1. restore every connection flag exactly from the private manifest;
2. verify the restored ID/flag set matches byte-for-byte;
3. delete the restore manifest;
4. revoke `researcy-q0-1` and remove `.env`;
5. report any restoration mismatch as a blocking cleanup defect.

Scan `generation.json` for key prefixes, emails, source text, prompts, raw bodies, and credential material. Commit only sanitized evidence:

```bash
cd ../..
git add "qualification/results/$RUN_ID/generation.json"
git commit -m "experiment(q0.1): record pinned generation decision"
```

If the generation gate fails, execute shared blocked-run finalization. Do not begin Task 4.

---

### Task 4: Prove exact evidence geometry in Chromium

**Files:**
- Create: `experiments/q0-1/src/q0/proof.py`
- Modify: `experiments/q0-1/src/q0/cli.py`
- Create: `experiments/q0-1/tests/test_proof.py`
- Create: `qualification/results/<q0.1-run-id>/integrated-proof.json`
- Create: `qualification/results/<q0.1-run-id>/evidence-highlight.html`

**Interfaces:**
- Consumes: passing hybrid and generation results, private golden top-5, private validated golden answer, exact PyMuPDF blocks/spans, and independent gold boxes.
- Produces: `ProofIdentity`, `ProofValidationError`, exact quote resolution, claim/citation validation, self-contained HTML, and browser inspection fields. Makes no generation call.

- [ ] **Step 1: Write exact proof tests first**

```python
def test_page_only_resolution_is_rejected():
    with pytest.raises(ProofValidationError, match="boxes"):
        validate_resolution(page_index=3, boxes=[], page_width=612, page_height=792)


def test_resolved_boxes_are_inside_page_and_correct_column():
    validate_resolution(
        page_index=3,
        boxes=[BBox(x0=72, y0=180, x1=265, y1=198)],
        page_width=612,
        page_height=792,
        golden_boxes=[BBox(x0=70, y0=178, x1=267, y1=200)],
    )


def test_uncited_substantive_claim_is_rejected():
    answer = GroundedAnswer(
        answer="Scaled attention prevents small gradients.",
        citations=[Citation(marker=1, source_ref="S1", evidence_quote="verbatim evidence")],
    )
    with pytest.raises(ProofValidationError, match="marker"):
        validate_claim_marker_coverage(answer)


def test_proof_identity_requires_exact_hybrid_configuration():
    expected = ProofIdentity(
        parser="pymupdf",
        retrieval="bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)",
        gateway_version="0.5.81",
        connection_id="2386766d-a7c1-4839-953c-deaeaa10e719",
        route="gc/gemini-2.5-flash",
        requested_model="gc/gemini-2.5-flash",
        response_model="gc/gemini-2.5-flash",
        run_id="q0-1-20260921T000000Z-abcdef0",
    )
    with pytest.raises(ProofValidationError, match="retrieval"):
        validate_proof_identity(expected, expected.model_copy(update={"retrieval": "dense-only"}))
```

Also test unknown sources, mismatched quote, duplicate markers, boxes crossing columns, wrong page, HTML external assets, and hash mismatch across hybrid/generation/private inputs.

Run:

```bash
cd experiments/q0-1
uv run pytest tests/test_proof.py -q
```

Expected: FAIL because proof orchestration does not exist.

- [ ] **Step 2: Implement grounding, geometry, and self-contained rendering**

Validate every substantive claim and marker, supplied source ID, exact normalized evidence quote, retrieval/generation hash, and selected identity. Resolve the quote through reversible offsets to source spans; require page 3, independent-region overlap, non-empty boxes, and correct column.

Render the PDF page at 144 DPI to an embedded PNG data URI. Scale bottom-left PDF boxes into image coordinates and overlay translucent SVG/HTML rectangles. The document must contain semantic `<main>`, one `<h1>`, labeled answer and citation sections, `<figure>/<figcaption>`, high-contrast text, and a compact identity footer. Use no external JavaScript, font, image, stylesheet, animation, or probe asset.

- [ ] **Step 3: Pass tests and commit proof code before measurement**

```bash
cd experiments/q0-1
uv run pytest tests/test_proof.py -q
cd ../..
git add experiments/q0-1/src/q0 experiments/q0-1/tests/test_proof.py
git commit -m "experiment(q0.1): add exact evidence proof"
```

- [ ] **Step 4: Generate proof without another live answer call**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0-1
RUN_ID=$(uv run q01 run-id --root ../..)
uv run q01 proof run --run-id "$RUN_ID" --root ../..
```

`integrated-proof.json` records clean producer revision, all identities and hashes, supplied sources, marker coverage, quote validation, expected-page/golden overlap, correct-column boxes, and HTML SHA-256.

- [ ] **Step 5: Inspect the actual HTML in Chromium**

Open the committed-path candidate directly with real Chromium at `1440×1000`. Capture a fresh accessibility snapshot and screenshot for inspection only. Verify:

- the scaled-dot-product sentence is visibly highlighted;
- boxes stay inside the correct column;
- every substantive claim has a visible supported marker;
- `<main>`, one `<h1>`, figure, caption, answer, and citation landmarks exist;
- footer matches PyMuPDF, BGE-M3 + BM25 + RRF, 9Router 0.5.81, connection, route, requested/response model, corpus, and run.

Persist inspection time, viewport, highlight result, unsupported-claim result, accessibility result, and notes in `integrated-proof.json`; never persist the screenshot path. Any failure uses shared blocked-run finalization.

---

### Task 5: Report, clean up, and set the final gate

**Files:**
- Create: `docs/superpowers/reports/2026-09-21-researcy-q0-1-hybrid-qualification-report.md`
- Modify: `docs/superpowers/specs/2026-09-18-researcy-delivery-map.md`
- Delete: `experiments/q0-1/`
- Delete: Q0.1 temporary ignore lines from `.gitignore`
- Delete: `qualification/private/<q0.1-run-id>/`
- Delete: `qualification/private/q0-1-run-id.txt`
- Delete: `qualification/.cache/`

**Interfaces:**
- Consumes: all durable Q0.1 JSON/HTML, immutable Q0 artifacts, browser observations, and cleanup checks.
- Produces: concise Q0.1 report, final delivery-map state, verified durable links, and a repository with no probe/private/credential artifact.

- [ ] **Step 1: Write the report strictly from durable evidence**

Include:

- new run and clean producer revisions;
- immutable Q0 run/artifact hashes;
- machine/runtime identities;
- dense-only baseline versus dense, BM25, and fused Q0.1 tables;
- all eight fused case ranks and the three prior rank-6 outcomes;
- exact selected hybrid configuration;
- all three generation outcomes, usage, identities, and typed errors;
- proof HTML link, quote/page/boxes, browser viewport/outcomes;
- limitations: two-paper corpus, one gateway/route/account, in-process BM25 is not production code, broader layouts remain M5;
- conclusion `No master revision required` unless observed evidence contradicts master revision 1.1.

Do not claim a metric absent from durable JSON.

- [ ] **Step 2: Commit measured evidence while Q0 remains Blocked**

Before cleanup, keep delivery status `Blocked`:

```bash
git add qualification/results docs/superpowers/reports
git commit -m "docs(q0.1): record hybrid qualification evidence"
```

- [ ] **Step 3: Verify security state and stop Q0.1 runtimes**

Confirm original 9Router flags are restored and `researcy-q0-1` is revoked. Then:

```bash
cd experiments/q0-1
docker compose down -v
ollama stop bge-m3:567m
```

Confirm port 6333 is no longer served by the Q0.1 container and Ollama has no Q0.1 model resident in memory. Stop only services started by Q0.1.

Scan tracked candidates for `.env`, PDFs, model weights, `qualification/private/`, `qualification/.cache/`, secret prefixes, prompts, source text, raw bodies, screenshots, and `experiments/q0-1/`. Any match is a blocking cleanup defect.

- [ ] **Step 4: Remove all throwaway and private state**

Delete the complete probe, Q0.1 private directory/run-ID file, PDF cache, and the three Q0.1-specific ignore entries. Do not delete or modify the original Q0 durable results.

- [ ] **Step 5: Validate durable evidence after cleanup**

Validate every retained JSON/JSONL file, local Markdown link, and HTML hash. Reopen `evidence-highlight.html` directly after probe deletion and repeat the key visible-highlight check.

Success state must show:

```text
original Q0 artifacts byte-identical
experiments/q0-1/ absent
qualification/private/ Q0.1 state absent
qualification/.cache/ absent
2 manifest entries
8 answerable + 2 unanswerable gold cases
93-chunk inherited hash recorded
new run: 4 JSON + 1 HTML
hybrid Recall@5 >= 6/8
3 valid generation terminal outcomes
exact golden-region highlight
report and delivery-map links resolve
no forbidden tracked artifact
```

On a blocked path, validate only artifacts that exist, require every downstream stage to say `not_run`, and require absent downstream JSON/HTML rather than fabricated placeholders.

- [ ] **Step 6: Set the final gate and commit cleanup**

Only after Step 5 succeeds:

- change Q0 from `Blocked` to `Verified`;
- link the Q0.1 report and exact new run directory;
- preserve links to the original blocked Q0 evidence;
- append Q0.1 evidence to EMB-01, RET-01, GEN-01, and CIT-01 while leaving final-owner responsibilities intact;
- authorize M1 brainstorming.

Commit:

```bash
git add -A .gitignore experiments/q0-1 qualification docs/superpowers
git commit -m "chore(q0.1): finalize hybrid qualification gate"
```

If any gate or cleanup check failed, keep Q0 `Blocked`, name the smallest next decision in the report, and use the same cleanup commit boundary without claiming success.

- [ ] **Step 7: Perform branch-wide verification and hand off**

Verify clean Git status, exact artifact counts, JSON/JSONL parsing, resolved links, reopened HTML, absent forbidden files, stopped services, and unchanged original Q0 hashes. Use `finishing-a-development-branch`; present merge/PR/keep/discard choices and do not merge, push, or delete the worktree without explicit user selection.
