# Researcy Q0 Balanced Technical Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select one parser and one native embedding configuration, qualify one pinned OpenAI-compatible generation path through 9Router, then prove one question-to-PDF-highlight path using a two-paper representative corpus.

**Architecture:** Build a throwaway Python probe under `experiments/q0/`. It keeps a thin `GenerationClient` domain contract around one `OpenAICompatibleGenerationClient`, evaluates a fixed 9Router route plus the parser and embedding candidates, writes six small durable result files, renders one self-contained HTML proof, produces a concise decision report, and is deleted.

**Tech Stack:** Python 3.12, uv, Pydantic 2, PyMuPDF, Docling, native ARM64 Ollama, Qdrant 1.19.0, httpx, OpenAI Python SDK, pinned local 9Router, pytest, static HTML/SVG.

**Spec:** `docs/superpowers/specs/2026-09-18-researcy-technical-qualification.md`, revision 1.2

## Global Constraints

- Hard timebox: 1.5–2 working days on Apple M1 arm64 with 8 GB physical RAM.
- Corpus: exactly arXiv `1706.03762` and `2005.11401`.
- Parser candidates: Docling and PyMuPDF geometry-first only.
- Embedding candidates: `bge-m3:567m` and `nomic-embed-text:137m-v1.5-fp16` through native Ollama only.
- Generation: one `OpenAICompatibleGenerationClient` against one pinned local 9Router version, one provider connection, one account, and one exact model route that is neither a combo nor a mutable alias.
- No account, provider, or model fallback, and no RTK, Caveman, prompt transformation, cloud sync, tunnel, or unredacted request-body logging.
- The configured account must already cover three bounded cases. Before new paid spend, stop for explicit approval of upstream, model, maximum spend, and run scope.
- PDFs, model weights, `.env`, API keys, and unredacted provider payloads are never committed.
- Stop on a failed gate; record the blocker instead of adding candidates or weakening thresholds.
- Delete `experiments/q0/` after durable evidence and the report are verified.
- Every measured artifact records the clean producer Git revision; commit inputs and probe code before running that measurement.

## Planned File Map

### Temporary probe — deleted in Task 5

```text
experiments/q0/
├── .env.example
├── compose.yml
├── pyproject.toml
├── uv.lock
├── src/q0/
│   ├── __init__.py
│   ├── cli.py
│   ├── models.py
│   ├── corpus.py
│   ├── parsers.py
│   ├── retrieval.py
│   ├── generation.py
│   └── proof.py
└── tests/
    ├── test_corpus.py
    ├── test_provenance.py
    ├── test_retrieval.py
    ├── test_generation.py
    └── test_proof.py
```

### Durable evidence

```text
.gitignore
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

`q0 init-run --root ../..` creates a UTC timestamp plus seven-character Git SHA run ID, creates the result directory, writes `environment.json`, stores the ID in ignored `qualification/private/run-id.txt`, and prints it. Later tasks restore it with `q0 run-id --root ../..` and still pass the explicit `--run-id`.

## Shared blocked-run finalization

When any parser, embedding, gateway, or proof gate says stop:

1. finish the current stage artifact with its producer revision, measurements, threshold failures, and one blocker;
2. do not execute downstream candidate or proof commands;
3. write the report from available artifacts and mark every downstream stage `not_run`;
4. set Q0 `Blocked` in the delivery map and link the report plus available run artifacts;
5. commit the blocker evidence, scan for forbidden tracked files, stop Qdrant with `docker compose down -v` when started, and delete `experiments/q0/`;
6. validate every artifact and link that exists, skip HTML checks when proof was not run, and commit cleanup.

This branch is the required completion path for an early stop; a blocked run never leaves the throwaway probe behind.

---

### Task 1: Build the minimal probe and freeze the two-paper corpus

**Files:**
- Create: `.gitignore`
- Create: `experiments/q0/pyproject.toml`
- Create: `experiments/q0/uv.lock`
- Create: `experiments/q0/.env.example`
- Create: `experiments/q0/compose.yml`
- Create: `experiments/q0/src/q0/__init__.py`
- Create: `experiments/q0/src/q0/models.py`
- Create: `experiments/q0/src/q0/cli.py`
- Create: `experiments/q0/src/q0/corpus.py`
- Create: `experiments/q0/tests/test_corpus.py`
- Create: `qualification/corpus/manifest.json`
- Create: `qualification/gold/evidence.jsonl`
- Create: `qualification/gold/reading-order.jsonl`

**Interfaces:**
- Produces `BBox`, `SourceSpan`, `ParsedBlock`, `EvidenceCase`, `ReadingOrderRelation`, `Citation`, `GroundedAnswer`, `CorpusValidationError`, `GoldValidationError`, and focused result models with `extra="forbid"`.
- Produces `q0 init-run`, `q0 run-id`, `q0 corpus fetch`, and `q0 gold validate`.
- Later tasks consume the manifest, cached PDFs, gold JSONL, result models, and explicit run ID.

- [ ] **Step 1: Add ignore and environment boundaries**

`.gitignore` must contain:

```gitignore
.env
experiments/q0/.venv/
experiments/q0/.pytest_cache/
experiments/q0/**/__pycache__/
qualification/.cache/
qualification/private/
*.pdf
.DS_Store
```

`.env.example` contains names only:

```dotenv
GENERATION_BASE_URL=http://127.0.0.1:20128/v1
GENERATION_API_KEY=
GENERATION_MODEL=
Q0_9ROUTER_VERSION=
Q0_9ROUTER_CONNECTION_ID=
OLLAMA_BASE_URL=http://127.0.0.1:11434
QDRANT_URL=http://127.0.0.1:6333
```

`compose.yml` contains only Qdrant `qdrant/qdrant:v1.19.0`, bound to `127.0.0.1:6333`, with one named temporary volume and the `/healthz` health check. Record the resolved container image ID in `environment.json` at run time.

- [ ] **Step 2: Create and lock the isolated Python environment**

Use Python `>=3.12,<3.13`, a `src` layout, and these direct dependencies:

```text
pydantic>=2,<3
httpx>=0.28,<1
pymupdf>=1.26,<2
docling>=2,<3
qdrant-client>=1.15,<2
openai>=1,<2
psutil>=7,<8
pytest>=8,<9
```

Expose `q0 = "q0.cli:main"`, then run:

```bash
cd experiments/q0
uv lock
uv sync --frozen
uv run q0 --help
```

Expected: dependency lock succeeds on arm64 Python 3.12 and the CLI lists `init-run`, `run-id`, `corpus`, `gold`, `parser`, `embedding`, `generation`, and `proof`.

- [ ] **Step 3: Define the minimal typed contracts**

Implement these stable declarations in `models.py`:

```python
class BBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x0: float
    y0: float
    x1: float
    y1: float

class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_start: int
    text_end: int
    page_index: int
    bbox: BBox

class ParsedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
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

class EvidenceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    paper_id: str
    answerable: bool
    page_index: int | None
    quotes: list[str]
    expected_section: str | None
    expected_boxes: list[BBox] = Field(default_factory=list)
    expected_page_width: float | None = None
    expected_page_height: float | None = None
    coordinate_origin: Literal["bottom-left"] | None = None
    coverage_reference_text: str | None = None

class ReadingOrderRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relation_id: str
    paper_id: str
    page_index: int
    before_anchor: str
    after_anchor: str

class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marker: int
    source_ref: str
    evidence_quote: str

class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    citations: list[Citation]
```

Add focused result models for the five durable JSON files. Each has `artifact_version="q0-balanced-1"`, `run_id`, identity fields, measurements, threshold outcomes, and failure reasons. Write JSON via a sibling temporary file, `fsync`, then atomic replace. Do not add JSON Schema generation.

- [ ] **Step 4: Write corpus validation tests first**

`test_corpus.py` must prove observable contract failures:

```python
def test_gold_rejects_quote_absent_from_annotated_page():
    case = EvidenceCase(
        case_id="1706.03762-answer-1",
        paper_id="1706.03762",
        answerable=True,
        page_index=0,
        quotes=["not present"],
        expected_section="3.2.1 Scaled Dot-Product Attention",
    )
    with pytest.raises(GoldValidationError, match="quote not found"):
        validate_evidence_case(case, page_text="different text")


def test_gold_requires_exact_balanced_case_counts():
    counts = {
        "1706.03762": {"answerable": 4, "unanswerable": 1},
        "2005.11401": {"answerable": 3, "unanswerable": 1},
    }
    with pytest.raises(GoldValidationError, match="4 answerable"):
        validate_gold_counts(counts)


def test_manifest_rejects_changed_pdf_hash():
    with pytest.raises(CorpusValidationError, match="SHA-256"):
        validate_pdf_hash(expected="0" * 64, actual_bytes=b"%PDF-changed")
```

Run:

```bash
cd experiments/q0
uv run pytest tests/test_corpus.py -q
```

Expected: FAIL because corpus validation is not implemented.

- [ ] **Step 5: Implement deterministic fetch and gold validation**

Hard-code only these source entries in `corpus.py`:

```python
CORPUS = {
    "1706.03762": "Attention Is All You Need",
    "2005.11401": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
}
```

`q0 corpus fetch --root ../..` must download `https://arxiv.org/pdf/<id>` into `qualification/.cache/pdfs/`, reject non-PDF responses, compute SHA-256 and page count, and write the sorted manifest. A second run reuses only a cache entry whose hash matches the manifest.

`q0 gold validate --root ../..` must verify:

- exactly 4 answerable and 1 unanswerable case per paper;
- every answerable quote is verbatim on the annotated page after allowed normalization;
- every answerable case has an expected section;
- unanswerable cases have no quotes;
- at least 6 reading-order relations per paper;
- every relation has stable verbatim `before_anchor` and `after_anchor` snippets that each resolve exactly once on the annotated PDF page after allowed normalization;
- exactly one fixed coverage page per paper has manually accepted visible reference text;
- the golden case has bottom-left coordinate origin, page dimensions, and non-empty expected boxes inside that page;
- all referenced papers and pages exist in the manifest.

- [ ] **Step 6: Freeze the gold questions before candidate execution**

Use these question identities; copy evidence quotes and pages directly from cached PDFs rather than web transcriptions:

```text
1706.03762-answer-1  Why does scaled dot-product attention divide by the square root of the key dimension?
1706.03762-answer-2  Why does multi-head attention use several attention heads instead of one?
1706.03762-answer-3  How does the model represent token order without recurrence or convolution?
1706.03762-answer-4  How does decoder self-attention prevent access to later output positions?
1706.03762-unanswerable  What carbon footprint did the authors report for training the Transformer?

2005.11401-answer-1  How does RAG combine parametric and non-parametric memory?
2005.11401-answer-2  What is the difference between RAG-Sequence and RAG-Token generation?
2005.11401-answer-3  How are retrieved documents used when generating an output sequence?
2005.11401-answer-4  On which kinds of knowledge-intensive tasks is RAG evaluated?
2005.11401-unanswerable  What carbon footprint did the authors report for training RAG?
```

Manually add at least six `ReadingOrderRelation` records per paper, including a column transition and one table/caption boundary for `2005.11401`. Resolve and validate both anchors against the cached PDF text layer before any candidate runs; candidate blocks only determine whether the frozen `before_anchor` precedes the frozen `after_anchor`.

Before any parser runs, store the manually accepted visible text for the golden evidence page and one `2005.11401` table/caption page in `evidence.jsonl`. On the golden case, store page width, page height, and manually checked boxes around the expected sentence. These are independent gold annotations; parser output must not create or revise them.

Run:

```bash
cd experiments/q0
uv run q0 corpus fetch --root ../..
uv run q0 gold validate --root ../..
uv run pytest tests/test_corpus.py -q
```

Expected: 2 PDFs, 8 answerable cases, 2 unanswerable cases, at least 12 reading-order relations, 2 fixed coverage-page references, independent golden boxes, passing tests, and no tracked PDF or `.env`.

- [ ] **Step 7: Commit the frozen evaluation inputs**

```bash
git add .gitignore experiments/q0 qualification/corpus qualification/gold
git commit -m "experiment(q0): freeze balanced qualification corpus"
```

- [ ] **Step 8: Initialize the run from the committed clean revision**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0
RUN_ID=$(uv run q0 init-run --root ../..)
printf '%s\n' "$RUN_ID"
```

Expected: one result directory contains `environment.json` with the current committed Git revision and `tracked_tree_clean: true`.

---

### Task 2: Select the parser with reversible provenance

**Files:**
- Create: `experiments/q0/src/q0/parsers.py`
- Create: `experiments/q0/tests/test_provenance.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Create: `qualification/results/<run-id>/parser.json`

**Interfaces:**
- Consumes corpus manifest, cached PDFs, gold evidence, reading-order relations, and `ParsedBlock`.
- Produces `normalize_with_map(text_runs) -> tuple[str, list[SourceSpan]]`, `parse_pymupdf(path)`, `parse_docling(path)`, and selected parser identity in `parser.json`.

- [ ] **Step 1: Write the provenance tests first**

Cover reversible whitespace collapse, line joining, dehyphenation, and multi-box quote resolution. The central test uses two source runs for `scaled dot-` and `product` and asserts the normalized quote `scaled dot-product` resolves to both original boxes. Add a real-PDF integration assertion that the golden quote resolves to the annotated page and boxes inside page bounds.

Run:

```bash
cd experiments/q0
uv run pytest tests/test_provenance.py -q
```

Expected: FAIL because parser and normalization functions are absent.

- [ ] **Step 2: Implement reversible normalization and both adapters**

During normalization, carry a source reference with every output character and compact adjacent references only after transformation. Never recover provenance with fuzzy search.

PyMuPDF must use `TextPage` raw spans/characters; `sort=True` may inform but cannot prove reading order. Docling must map document items and provenance boxes into the same `ParsedBlock` shape. Both adapters must emit zero-based pages and bottom-left coordinates and reject boxes outside page bounds.

For each coverage page, apply allowed normalization plus Unicode case-folding to reference and candidate text, split on normalized whitespace, compute token-sequence longest common subsequence length, and divide by reference-token count. Reject an empty reference. Record numerator, denominator, and score.

- [ ] **Step 3: Pass tests and commit the parser probe before measuring**

```bash
cd experiments/q0
uv run pytest tests/test_provenance.py -q
cd ../..
git add experiments/q0/src/q0 experiments/q0/tests/test_provenance.py
git commit -m "experiment(q0): add reversible parser probe"
```

- [ ] **Step 4: Run both candidates and apply the complete gate**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0
RUN_ID=$(uv run q0 run-id --root ../..)
uv run q0 parser run --candidate pymupdf --run-id "$RUN_ID" --root ../..
uv run q0 parser run --candidate docling --run-id "$RUN_ID" --root ../..
uv run q0 parser evaluate --run-id "$RUN_ID" --root ../..
```

Expected: `parser.json` records the producer Git revision; per-candidate quote/page/geometry results; coverage on both fixed pages; overlap with the independent golden region and correct-column outcome; 12 reading-order outcomes; expected sections; leakage; latency; peak memory; and the winner.

Stop and report `Blocked` if neither candidate achieves 8/8 page correctness, geometry for every gold quote, at least 0.90 coverage on each fixed page, at least 10/12 reading-order correctness, golden-region overlap inside the correct column, reversible offsets, and successful parsing of both PDFs.

- [ ] **Step 5: Commit parser evidence**

```bash
git add qualification/results/*/parser.json
git commit -m "experiment(q0): record balanced parser decision"
```

---

### Task 3: Select the native embedding configuration

**Files:**
- Create: `experiments/q0/src/q0/retrieval.py`
- Create: `experiments/q0/tests/test_retrieval.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Create: `qualification/results/<run-id>/embedding.json`

**Interfaces:**
- Consumes selected parser blocks and 8 answerable gold cases.
- Produces one frozen chunk set; `VectorValidationError`, `validate_vector`, `retrieval_metrics`, and `build_chunks`; Ollama `/api/show` and `/api/embed` clients; retrieval metrics; and selected embedding identity.

- [ ] **Step 1: Start only Qdrant and verify native Ollama**

```bash
cd experiments/q0
docker compose config -q
docker compose up -d --wait qdrant
curl --fail http://127.0.0.1:6333/healthz
curl --fail http://127.0.0.1:11434/api/version
```

Expected: Qdrant 1.19.0 is healthy and native Ollama responds. Do not add PostgreSQL, MinIO, API, or web services.

- [ ] **Step 2: Write retrieval invariant tests first**

`test_retrieval.py` must cover:

```python
def test_dimension_drift_is_rejected():
    with pytest.raises(VectorValidationError, match="dimension"):
        validate_vector([0.1, 0.2], expected_dimension=3)


@pytest.mark.parametrize("vector", [[0.0, 0.0], [float("nan"), 1.0]])
def test_zero_or_non_finite_vector_is_rejected(vector):
    with pytest.raises(VectorValidationError):
        validate_vector(vector, expected_dimension=2)


def test_recall_and_mrr_use_first_relevant_rank():
    metrics = retrieval_metrics(
        ranked_source_ids=[["wrong", "gold"], ["gold", "other"]],
        relevant_source_ids=[{"gold"}, {"gold"}],
        k_values=(1, 5),
    )
    assert metrics.recall_at_1 == 0.5
    assert metrics.recall_at_5 == 1.0
    assert metrics.mrr == 0.75


def block(section_path: list[str], text: str) -> ParsedBlock:
    return ParsedBlock(
        paper_id="paper",
        page_index=0,
        section_path=section_path,
        block_type="paragraph",
        reading_order=0,
        normalized_text=text,
        source_spans=[],
        page_width=612,
        page_height=792,
        coordinate_origin="bottom-left",
    )


def test_chunk_never_crosses_section_boundary():
    chunks = build_chunks(
        [
            block(section_path=["A"], text="first"),
            block(section_path=["B"], text="second"),
        ],
        max_chars=100,
    )
    assert [chunk.section_path for chunk in chunks] == [["A"], ["B"]]
```

Run:

```bash
cd experiments/q0
uv run pytest tests/test_retrieval.py -q
```

Expected: FAIL because chunking and metric functions are absent.

- [ ] **Step 3: Implement the frozen chunk set and Ollama preflight**

Create chunks from selected parser blocks, remain inside one section, prefer paragraph boundaries, include section heading metadata, and retain block/source-span references. Persist the temporary frozen chunk set under `qualification/private/<run-id>/chunks.jsonl`; both models read this byte-identical file.

For each exact tag, call `/api/show` and `/api/embed` with `truncate:false`, then verify one finite non-zero vector and stable dimension. `embedding.json` records producer Git revision, resolved digest, architecture, quantization, dimension, distance metric, query/document prefixes, maximum input metadata, explicit truncation behavior, batch size, concurrency, collection identity, and runtime placement. `environment.json` records the Ollama version plus Qdrant version and resolved container image ID.

- [ ] **Step 4: Pass tests and commit the retrieval probe before measuring**

```bash
cd experiments/q0
uv run pytest tests/test_retrieval.py -q
cd ../..
git add experiments/q0/src/q0 experiments/q0/tests/test_retrieval.py experiments/q0/compose.yml
git commit -m "experiment(q0): add native retrieval probe"
```

- [ ] **Step 5: Install exact tags, run candidates sequentially, and select**

```bash
ollama pull bge-m3:567m
ollama pull nomic-embed-text:137m-v1.5-fp16
git diff --quiet && git diff --cached --quiet
cd experiments/q0
RUN_ID=$(uv run q0 run-id --root ../..)
uv run q0 embedding preflight --model bge-m3:567m --run-id "$RUN_ID" --root ../..
uv run q0 embedding run --model bge-m3:567m --run-id "$RUN_ID" --root ../..
ollama stop bge-m3:567m
uv run q0 embedding preflight --model nomic-embed-text:137m-v1.5-fp16 --run-id "$RUN_ID" --root ../..
uv run q0 embedding run --model nomic-embed-text:137m-v1.5-fp16 --run-id "$RUN_ID" --root ../..
uv run q0 embedding evaluate --run-id "$RUN_ID" --root ../..
```

Expected: both exact tags and digests are captured, separate Qdrant collections contain the identical chunk set, repeated warm latency samples and Recall@1/5 plus MRR cover 8 questions, peak memory is recorded, all required runtime/configuration identity fields are present, and `embedding.json` names the selected model.

An exact-tag pull failure blocks that candidate. A candidate also fails on crash/OOM, malformed or drifting vectors, truncation, Recall@5 below 6/8, p95 at or above 1 second, or golden-paper indexing above 5 minutes. Choose Nomic on equal Recall@5 hits without a material error-analysis disadvantage; otherwise choose BGE-M3 when it recovers an extra case or materially ranks scientific evidence better.

- [ ] **Step 6: Commit embedding evidence**

```bash
git add qualification/results/*/environment.json qualification/results/*/embedding.json
git commit -m "experiment(q0): record native embedding decision"
```

---

### Task 4: Qualify one pinned OpenAI-compatible 9Router path

**Files:**
- Create: `experiments/q0/src/q0/generation.py`
- Create: `experiments/q0/tests/test_generation.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Create: `qualification/results/<run-id>/generation.json`

**Interfaces:**
- Consumes the golden case, its selected retrieval context, one immediate follow-up, one unanswerable case, and the pinned 9Router configuration.
- Produces `GenerationRequest`, `GenerationClient`, typed stream events, `GenerationError`, `GatewayIdentity`, `OpenAICompatibleGenerationClient`, and one qualified gateway-route identity.

- [ ] **Step 1: Freeze the three generation cases**

Use this exact sequence:

```text
1706.03762-answer-1
What failure mode would occur without that scaling?
1706.03762-unanswerable
```

The follow-up runs immediately after the golden answer and receives the bounded prior turn. Freeze source IDs, retrieved text, system instructions, response schema, and generation parameters before the gateway runs. The model receives selected context only, never a complete PDF.

- [ ] **Step 2: Write OpenAI-compatible fixture tests before network calls**

Use local Chat Completions SSE fixtures to assert:

- requests contain the exact configured model, JSON schema, `stream=true`, and streamed usage request;
- ordered deltas end with exactly one `answer.completed` or `answer.failed` event;
- OpenAI SDK request, response, chunk, and exception types never escape `OpenAICompatibleGenerationClient`;
- exact master `GroundedAnswer` validation uses `marker`, `source_ref`, and `evidence_quote`;
- missing, duplicate, non-positive, or answer-absent markers are rejected;
- unknown `source_ref` and mismatched `evidence_quote` are rejected;
- answerable and follow-up outputs cannot pass as empty-citation refusals;
- the follow-up preserves the scaled-dot-product-attention referent;
- the unanswerable case requires an insufficient-context answer and empty citations;
- provider-reported input and output token usage is preserved;
- authentication, rate-limit, timeout, malformed-output, interrupted-stream, and unavailable responses become typed `GenerationError` values;
- malformed schema fails immediately with no format or citation retry;
- configured, requested, or response identity mismatch fails qualification; an exposed upstream identity must also match when present.

Run with network disabled:

```bash
cd experiments/q0
uv run pytest tests/test_generation.py -q
```

Expected: FAIL before implementation, then PASS using fixtures only after the thin client, stream mapper, and validators are complete.

- [ ] **Step 3: Implement the thin domain and transport boundary**

`GenerationClient` exposes only `stream_answer(request) -> AsyncIterator[GenerationEvent]`. `OpenAICompatibleGenerationClient` owns the OpenAI SDK, custom `base_url`, API key, model, Chat Completions request, SSE parsing, usage extraction, and external-error mapping. It emits only Researcy domain events and validates the final payload with `GroundedAnswer`.

The loader fails closed when the base URL is not local HTTP for this Q0 run, or when the API key, exact model, expected 9Router version, or non-secret connection identity is absent. Never persist the API key, raw request body, raw response body, selected source text, or complete prompts.

- [ ] **Step 4: Pass fixture tests and commit the generation probe before traffic**

```bash
cd experiments/q0
uv run pytest tests/test_generation.py -q
cd ../..
git add experiments/q0/src/q0 experiments/q0/tests/test_generation.py experiments/q0/.env.example experiments/q0/pyproject.toml experiments/q0/uv.lock
git commit -m "experiment(q0): add pinned gateway generation probe"
```

- [ ] **Step 5: Pin, inspect, and preflight 9Router**

In the local 9Router dashboard, configure exactly one active provider connection, one account, and one exact model route. Ensure no alternate account or model is available, and confirm the route is not a combo or mutable alias. Disable RTK, Caveman, prompt transformations, cloud sync, tunnel, and request-body logging. Put only the exact version, non-secret connection ID, model route, base URL, and local API key in the uncommitted `.env`.

Run from the clean probe revision:

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0
RUN_ID=$(uv run q0 run-id --root ../..)
uv run q0 generation preflight --run-id "$RUN_ID" --root ../..
```

The preflight must authenticate, verify the pinned 9Router version and connection declaration, persist a sanitized assertion of the inspected single-account/single-model configuration, send one schema-constrained streaming request, observe at least one delta and one terminal event, receive provider-reported input/output usage, and record configured, requested, and response model identities plus upstream identity when exposed. Any identity mismatch, route switch, missing usage, or alternate configured candidate uses Shared blocked-run finalization.

- [ ] **Step 6: Run the three cases and commit sanitized evidence**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0
RUN_ID=$(uv run q0 run-id --root ../..)
uv run q0 generation run --run-id "$RUN_ID" --root ../..
```

Expected: `generation.json` records the producer Git revision; pinned 9Router version and non-secret connection ID; sanitized single-account/single-model configuration assertion; configured route; requested and response identities; exposed upstream identity when available; three outcomes; first-attempt schema validity; marker/source-ref/evidence-quote/refusal/follow-up correctness; claim-marker coverage; TTFT; latency; provider-reported input/output usage; and typed errors.

All three cases require typed terminal events and first-attempt schema-valid outputs. The golden answer and follow-up require claim-marker coverage `1.0`, valid source IDs, exact accepted quotes, and correct follow-up referent. The unanswerable case must state insufficient context with empty citations. Every case requires usage and stable requested/response identities; an exposed upstream identity must match when present. The configuration assertion must show no alternate account, route, or model. Any failure uses Shared blocked-run finalization.

Inspect staged content for key prefixes, source text, prompts, raw bodies, and local credential material, then commit only the sanitized result:

```bash
git add qualification/results/*/generation.json
git commit -m "experiment(q0): record pinned gateway decision"
```

---

### Task 5: Prove the highlight path, report decisions, and remove the probe

**Files:**
- Create: `experiments/q0/src/q0/proof.py`
- Create: `experiments/q0/tests/test_proof.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Create: `qualification/results/<run-id>/integrated-proof.json`
- Create: `qualification/results/<run-id>/evidence-highlight.html`
- Create: `docs/superpowers/reports/2026-09-18-researcy-technical-qualification-report.md`
- Modify: `docs/superpowers/specs/2026-09-18-researcy-delivery-map.md`
- Delete: `experiments/q0/`

**Interfaces:**
- Consumes selected parser, embedding configuration, qualified pinned gateway-route result, golden question, and annotated geometry.
- Produces `ProofIdentity`, `ProofValidationError`, `validate_resolution`, `validate_proof_identity`, one self-contained visual proof, the final report, and Q0 delivery state.

- [ ] **Step 1: Write exact-proof tests first**

`test_proof.py` must assert:

```python
def test_page_only_resolution_is_rejected():
    with pytest.raises(ProofValidationError, match="boxes"):
        validate_resolution(page_index=3, boxes=[], page_width=612, page_height=792)


def test_resolved_boxes_are_non_empty_and_inside_page():
    validate_resolution(
        page_index=3,
        boxes=[BBox(x0=72, y0=180, x1=265, y1=198)],
        page_width=612,
        page_height=792,
    )


def test_proof_identity_matches_selected_results():
    expected = ProofIdentity(
        parser="pymupdf",
        embedding="nomic-embed-text:137m-v1.5-fp16",
        gateway="9router",
        gateway_version="pinned-version",
        route="exact-non-combo-route",
        requested_model="exact-model",
        response_model="exact-model",
        run_id="20260919T000000Z-abcdef0",
    )
    with pytest.raises(ProofValidationError, match="response_model"):
        validate_proof_identity(
            expected,
            expected.model_copy(update={"response_model": "other"}),
        )


def test_uncited_substantive_claim_is_rejected():
    answer = GroundedAnswer(
        answer="Scaled attention prevents small gradients.",
        citations=[
            Citation(marker=1, source_ref="S1", evidence_quote="verbatim evidence")
        ],
    )
    with pytest.raises(ProofValidationError, match="marker"):
        validate_claim_marker_coverage(answer)
```

Run:

```bash
cd experiments/q0
uv run pytest tests/test_proof.py -q
```

Expected: FAIL because proof orchestration is absent.

- [ ] **Step 2: Implement grounding, geometry, and rendering**

The proof validator must enforce the exact master citation schema, require every substantive claim to carry an answer marker, map markers one-to-one to supplied sources, verify every evidence quote locally, and reject unsupported `source_ref` values. It must resolve the selected quote through normalized offsets to source spans, require overlap with the independent golden region inside the correct column, and render a self-contained HTML page with translucent boxes, question, answer, citations, and identity footer.

Run tests and commit the proof probe before measuring:

```bash
cd experiments/q0
uv run pytest tests/test_proof.py -q
cd ../..
git add experiments/q0/src/q0 experiments/q0/tests/test_proof.py
git commit -m "experiment(q0): add integrated evidence probe"
```

- [ ] **Step 3: Run the golden proof from the clean revision**

```bash
git diff --quiet && git diff --cached --quiet
cd experiments/q0
RUN_ID=$(uv run q0 run-id --root ../..)
uv run q0 proof run --run-id "$RUN_ID" --root ../..
```

Expected: `integrated-proof.json` records the producer Git revision, supplied source IDs, claim-marker coverage, quote validation, expected-page and golden-region overlap, non-empty correct-column boxes, and selected identities. Page-only resolution fails. `evidence-highlight.html` uses no external JavaScript or probe asset.

- [ ] **Step 4: Perform browser inspection**

Open the HTML directly in a real browser. Confirm the highlighted sentence is the scaled-dot-product-attention evidence, boxes do not cross columns, every substantive answer claim has a visible valid marker supported by supplied context, and the identity footer matches parser, embedding, 9Router version, configured route, requested and response model, corpus, and run. Record `browser_inspected_at`, viewport, highlight outcome, unsupported-claim review outcome, and notes directly in `integrated-proof.json`; do not store a non-durable screenshot path.

- [ ] **Step 5: Write the concise report from observed results**

The report must include:

- run, producer revisions, machine, and two-paper corpus identities;
- parser and embedding candidate tables with complete gate outcomes;
- the single pinned gateway-route outcome and all three case results;
- selected parser, embedding, 9Router version, connection ID, route, and model identities;
- link to the integrated HTML and browser inspection fields;
- concrete failures and limitations, including that no other OpenAI-compatible endpoint is qualified;
- explicit statement that broader layout coverage remains for M5;
- `No master revision required` if results do not contradict revision 1.1, otherwise the exact blocker.

Do not claim a metric absent from durable JSON.

- [ ] **Step 6: Commit durable evidence without changing the Q0 gate**

Keep Q0 `Planned` while cleanup remains unfinished. Commit the report and measured artifacts, but do not authorize M1 yet:

```bash
git add qualification/results docs/superpowers/reports
git commit -m "docs(q0): record balanced qualification evidence"
```

- [ ] **Step 7: Verify no forbidden tracked artifacts**

Check tracked candidates for `.env`, PDF, model-weight, `qualification/private/`, `qualification/.cache/`, and secret-prefix paths. Any match is a blocking security defect and must be removed from the index before cleanup.

- [ ] **Step 8: Delete the complete throwaway probe**

Delete `experiments/q0/` in one change. Do not move or rename its modules into production packages.

- [ ] **Step 9: Validate durable evidence after cleanup**

Run JSON syntax validation over every durable JSON/JSONL file and verify all report and delivery-map links exist. On the success-candidate branch, open the committed HTML directly again and confirm:

```text
experiments/q0/ absent
2 manifest entries
8 answerable gold cases
2 unanswerable gold cases
2 coverage-page references
independent golden boxes present
>=12 reading-order relations
5 JSON results + 1 HTML proof
report links resolve
HTML renders without probe files
```

On the `Blocked` branch, validate only artifacts that exist, confirm every skipped downstream stage is explicitly `not_run`, confirm no downstream artifact was fabricated, and open HTML only when proof produced it. Both branches require `experiments/q0/` to be absent.

- [ ] **Step 10: Set the final gate, commit cleanup, and hand off**

Only after Step 9 succeeds, set Q0 to `Verified`, link the report and run directory in the delivery map, re-run link validation, and authorize M1 brainstorming. If any gate or cleanup validation failed, use Shared blocked-run finalization and set Q0 to `Blocked`; never commit `Verified` first.

```bash
git add -A experiments/q0 qualification docs/superpowers
git commit -m "chore(q0): finalize balanced qualification gate"
```

If Q0 is `Verified`, the next allowed work is M1 Identity and Personal Library brainstorming. If Q0 is `Blocked`, the next allowed work is only the smallest decision named in the report.
