# Researcy Q0 Technical Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify one scientific PDF parser, one on-device embedding configuration, and one OpenRouter plus one Gemini generation configuration, then prove an exact question-to-PDF-highlight path without creating production application code.

**Architecture:** Build an isolated Python probe under `experiments/q0/` that writes durable, schema-validated corpus annotations and results under `qualification/`. The probe compares exactly two parsers and two embedding models, qualifies manually selected OpenRouter and Gemini providers, renders one integrated evidence artifact, writes a decision report, updates the delivery map, and is then deleted.

**Tech Stack:** Python 3.12, uv, Pydantic 2, PyMuPDF, Docling, native ARM64 Ollama, BGE-M3, Nomic Embed Text, Qdrant, httpx, Google Gen AI SDK, pytest, JSON Schema, static HTML/SVG evidence rendering.

**Spec:** `docs/superpowers/specs/2026-09-18-researcy-technical-qualification.md`

## Global Constraints

- Hard timebox: 2–3 working days.
- Qualification machine: Apple M1, arm64, 8 GB physical RAM.
- Corpus: exactly the five arXiv papers named in the Q0 specification.
- Parser candidates: Docling and PyMuPDF geometry-first only.
- Embedding candidates: `bge-m3:567m` and `nomic-embed-text:137m-v1.5-fp16` through native Ollama only.
- Generation providers: OpenRouter and Gemini; provider selection is manual configuration, never automatic per-request failover.
- Free model first. Before any paid call, stop and obtain explicit approval for the exact provider, model, maximum spend, and run scope.
- `openrouter/free` is forbidden because it randomly selects a model; pin one exact `:free` model.
- Raw PDFs, model weights, `.env` files, API keys, and unredacted provider payloads must never be committed.
- Probe code stays under `experiments/q0/` and is deleted after durable results and the report are verified.
- No M1 application scaffolding, authentication, production API, durable worker, or production database schema.
- Stop immediately on a Q0 stop condition; write the evidence-backed blocker report and mark the delivery map `Blocked` rather than widening scope.

## Planned File Map

### Temporary probe files — deleted in Task 9

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
│   ├── artifacts.py
│   ├── corpus.py
│   ├── normalization.py
│   ├── parsers.py
│   ├── parser_eval.py
│   ├── chunking.py
│   ├── ollama_client.py
│   ├── embedding_eval.py
│   ├── providers.py
│   ├── generation_eval.py
│   ├── integrated_proof.py
│   └── render_highlight.py
└── tests/
    ├── test_artifacts.py
    ├── test_corpus.py
    ├── test_normalization.py
    ├── test_parsers.py
    ├── test_embedding_eval.py
    ├── test_providers.py
    └── test_integrated_proof.py
```

### Durable qualification files

```text
.gitignore
qualification/
├── corpus/manifest.json
├── gold/evidence.jsonl
├── gold/reading-order.jsonl
├── schemas/environment.schema.json
├── schemas/parser-results.schema.json
├── schemas/embedding-results.schema.json
├── schemas/grounded-answer.schema.json
├── schemas/generation-results.schema.json
├── schemas/integrated-proof.schema.json
├── results/active-run.json
└── results/$RUN_ID/
    ├── environment.json
    ├── parser-results.json
    ├── embedding-results.json
    ├── generation-results.json
    ├── integrated-proof.json
    ├── evidence-highlight.html
    └── evidence-highlight.svg

docs/superpowers/reports/
└── 2026-09-18-researcy-technical-qualification-report.md
```

Task 1 assigns `$RUN_ID` from `q0 run-id --activate`, which combines a UTC `YYYYMMDDTHHMMSSZ` timestamp with the first seven characters of the Git SHA and writes `qualification/results/active-run.json`. Every later task restores the same value with `q0 active-run`.

---

### Task 1: Build the isolated probe and durable artifact contracts

**Files:**
- Create: `.gitignore`
- Create: `experiments/q0/.env.example`
- Create: `experiments/q0/compose.yml`
- Create: `experiments/q0/pyproject.toml`
- Create: `experiments/q0/uv.lock`
- Create: `experiments/q0/src/q0/__init__.py`
- Create: `experiments/q0/src/q0/cli.py`
- Create: `experiments/q0/src/q0/models.py`
- Create: `experiments/q0/src/q0/artifacts.py`
- Create: `experiments/q0/tests/test_artifacts.py`
- Create: `qualification/schemas/environment.schema.json`
- Create: `qualification/schemas/parser-results.schema.json`
- Create: `qualification/schemas/embedding-results.schema.json`
- Create: `qualification/schemas/grounded-answer.schema.json`
- Create: `qualification/schemas/generation-results.schema.json`
- Create: `qualification/schemas/integrated-proof.schema.json`

**Interfaces:**
- Produces: `q0.models.RunIdentity`, `EnvironmentRecord`, `BBox`, `SourceSpan`, `ParsedBlock`, `Citation`, `GroundedAnswer`, and typed result envelopes.
- Produces: `q0.artifacts.write_json(path: Path, model: BaseModel) -> None` and `load_json(path: Path, model_type: type[T]) -> T`.
- Produces CLI: `q0 run-id --activate --root PATH`, `q0 active-run --root PATH`, `q0 environment capture --run-id ID`, and `q0 artifacts validate --run-dir PATH`.
- Consumes: no project code; this is the root probe contract.

- [ ] **Step 1: Add ignore rules before creating secrets or PDFs**

`.gitignore` must include:

```gitignore
.env
.env.*
!*.env.example
qualification/.cache/
qualification/private/
experiments/q0/.venv/
experiments/q0/.pytest_cache/
**/__pycache__/
*.py[cod]
.DS_Store
```

- [ ] **Step 2: Create the failing artifact tests**

`test_artifacts.py` must first assert:

```python
from pathlib import Path

from q0.artifacts import load_json, write_json
from q0.models import EnvironmentRecord, RunIdentity


def test_json_round_trip_is_atomic_and_typed(tmp_path: Path) -> None:
    record = EnvironmentRecord(
        run=RunIdentity(run_id="20260918T120000Z-deadbee", git_revision="deadbeef"),
        platform="macOS",
        architecture="arm64",
        physical_memory_bytes=8_589_934_592,
        versions={"python": "3.12.0"},
    )
    path = tmp_path / "environment.json"

    write_json(path, record)

    assert load_json(path, EnvironmentRecord) == record
    assert not (tmp_path / "environment.json.tmp").exists()


def test_run_id_has_utc_timestamp_and_git_sha() -> None:
    run = RunIdentity.from_values("2026-09-18T12:00:00Z", "deadbeef")
    assert run.run_id == "20260918T120000Z-deadbee"
```

- [ ] **Step 3: Run the tests and verify the intended failure**

Run:

```bash
cd experiments/q0
uv run pytest tests/test_artifacts.py -q
```

Expected: collection fails because `q0.artifacts` and `q0.models` do not exist.

- [ ] **Step 4: Create and lock the isolated environment**

`pyproject.toml` must use `src` layout, Python `>=3.12,<3.13`, and direct dependencies for:

```text
pydantic >=2,<3
httpx >=0.28,<1
jsonschema >=4,<5
psutil >=7,<8
typer >=0.16,<1
pymupdf >=1.26,<2
docling >=2,<3
qdrant-client >=1.15,<2
google-genai >=1,<2
pytest >=8,<9
pytest-asyncio >=1,<2
```

Run:

```bash
cd experiments/q0
uv lock
uv sync --frozen
```

Expected: `uv.lock` is created and `uv sync --frozen` exits 0 on arm64 Python 3.12.

- [ ] **Step 5: Define the typed artifact core**

Use Pydantic models with `extra="forbid"`. The core declarations must match:

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunIdentity(StrictModel):
    run_id: str
    git_revision: str

    @classmethod
    def from_values(cls, timestamp: str, revision: str) -> "RunIdentity": ...


class BBox(StrictModel):
    x0: float
    y0: float
    x1: float
    y1: float
    coordinate_origin: Literal["bottom-left"]


class SourceSpan(StrictModel):
    text_start: int = Field(ge=0)
    text_end: int = Field(gt=0)
    bbox: BBox


class ParsedBlock(StrictModel):
    paper_id: str
    page_index: int = Field(ge=0)
    section_path: tuple[str, ...]
    block_type: str
    reading_order: int = Field(ge=0)
    text: str
    spans: tuple[SourceSpan, ...]


class Citation(StrictModel):
    marker: int = Field(ge=1)
    source_ref: str
    evidence_quote: str


class GroundedAnswer(StrictModel):
    answer: str
    citations: tuple[Citation, ...]
```

`write_json` must serialize to a sibling temporary file, `fsync`, then atomically replace the target. It must never leave a partially written durable result.

- [ ] **Step 6: Add exact JSON Schemas**

Generate schemas from the Pydantic result envelopes and commit the generated JSON, not handwritten divergent schemas. `q0 artifacts export-schemas` must be idempotent; running it twice produces no diff.

Run:

```bash
cd experiments/q0
uv run q0 artifacts export-schemas --output ../../qualification/schemas
uv run q0 artifacts export-schemas --output ../../qualification/schemas
```

Expected: both commands exit 0 and the second invocation changes no file.

- [ ] **Step 7: Capture the environment and pass targeted checks**

`EnvironmentRecord` must capture architecture, physical memory, Python/package versions, Git revision, and Ollama/Qdrant versions when reachable; unavailable optional services are recorded as typed `unavailable` entries rather than omitted.

Run:

```bash
cd experiments/q0
RUN_ID=$(uv run q0 run-id --activate --root ../..)
uv run q0 environment capture --run-id "$RUN_ID" --output "../../qualification/results/$RUN_ID/environment.json"
uv run pytest tests/test_artifacts.py -q
uv run q0 artifacts validate --run-dir "../../qualification/results/$RUN_ID"
```

Expected: tests pass; `environment.json` validates; output prints the generated run ID and no secret values.

- [ ] **Step 8: Commit the harness contract**

```bash
git add .gitignore experiments/q0 qualification/schemas qualification/results/*/environment.json
git commit -m "chore(q0): establish qualification artifact contracts"
```

---

### Task 2: Freeze the corpus and gold annotations before candidate runs

**Files:**
- Create: `experiments/q0/src/q0/corpus.py`
- Create: `experiments/q0/tests/test_corpus.py`
- Create: `qualification/corpus/manifest.json`
- Create: `qualification/gold/evidence.jsonl`
- Create: `qualification/gold/reading-order.jsonl`
- Modify: `experiments/q0/src/q0/cli.py`

**Interfaces:**
- Consumes: `RunIdentity` and atomic artifact helpers from Task 1.
- Produces: `CorpusEntry`, `EvidenceCase`, `EvidenceQuote`, and `ReadingOrderSample` Pydantic models.
- Produces CLI: `q0 corpus fetch`, `q0 corpus verify`, and `q0 gold validate`.
- Later tasks consume only the manifest and validated JSONL files, never ad hoc filenames.

- [ ] **Step 1: Write failing corpus and gold validation tests**

Tests must assert:

```python
def test_manifest_contains_exact_approved_arxiv_ids() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    assert [entry.arxiv_id for entry in manifest.papers] == [
        "1706.03762",
        "2005.11401",
        "1512.03385",
        "1703.06870",
        "1806.07366",
    ]
    assert all(len(entry.sha256) == 64 for entry in manifest.papers)


def test_gold_case_counts_are_fixed() -> None:
    cases = load_evidence_cases(EVIDENCE_PATH)
    assert len([case for case in cases if case.answerable]) == 20
    assert len([case for case in cases if not case.answerable]) == 5
    assert all(case.quotes for case in cases if case.answerable)


def test_reading_order_has_at_least_forty_manual_samples() -> None:
    samples = load_reading_order_samples(READING_ORDER_PATH)
    assert len(samples) >= 40
```

- [ ] **Step 2: Verify tests fail before corpus files exist**

Run:

```bash
cd experiments/q0
uv run pytest tests/test_corpus.py -q
```

Expected: FAIL because manifest and gold files are absent.

- [ ] **Step 3: Implement deterministic corpus download and hashing**

`q0 corpus fetch` must:

1. build each source URL as `f"https://arxiv.org/pdf/{entry.arxiv_id}"` for the five exact manifest entries;
2. reject non-PDF magic bytes;
3. write atomically to `qualification/.cache/pdfs/{entry.arxiv_id}.pdf`;
4. compute SHA-256 from final bytes;
5. write title, source URL, byte size, page count, and checksum to the manifest;
6. refuse to overwrite a different checksum unless `--new-corpus-version` is explicitly passed.

The source seed entries are hard-coded in `corpus.py` with the five exact IDs and titles from the approved spec; `manifest.json` is the generated locked output, not an input required before the first fetch.

Run:

```bash
cd experiments/q0
uv run q0 corpus fetch --root ../.. --manifest ../../qualification/corpus/manifest.json
uv run q0 corpus verify --root ../.. --manifest ../../qualification/corpus/manifest.json
```

Expected: exactly five cached PDFs; all checksums and page counts validate.

- [ ] **Step 4: Define the exact gold JSONL contract**

Each evidence line must contain:

```json
{
  "case_id": "1706.03762-a1",
  "paper_id": "1706.03762",
  "question": "Why does scaled dot-product attention divide by the square root of the key dimension?",
  "answerable": true,
  "quotes": [
    {
      "text": "For large values of dk, the dot products grow large in magnitude, pushing the softmax function into regions where it has extremely small gradients.",
      "page_number": 4,
      "section": "3.2.1 Scaled Dot-Product Attention"
    }
  ]
}
```

Unanswerable lines use `answerable: false` and an empty `quotes` list. Reading-order lines identify `paper_id`, `page_number`, `before_text`, `after_text`, and the human-checked relation `before`.

- [ ] **Step 5: Annotate `1706.03762` first and lock the integrated case**

Add four answerable questions, including the exact golden question above, one unanswerable question, at least eight reading-order samples, expected sections, verbatim quotes, and page numbers. Confirm quotes directly against the cached PDF text layer, not a web transcription.

Run:

```bash
cd experiments/q0
uv run q0 gold validate --allow-partial-paper 1706.03762 --root ../..
```

Expected: the paper has 4 answerable, 1 unanswerable, and at least 8 reading-order samples; every answerable quote is non-empty and page-bounded.

- [ ] **Step 6: Annotate the remaining four papers one paper at a time**

Repeat the same 4-answerable, 1-unanswerable, and 8-reading-order minimum for each exact paper in manifest order. After annotating a paper, set `ARXIV_ID` to its exact manifest ID and run `uv run q0 gold validate --allow-partial-paper \"$ARXIV_ID\" --root ../..`; fix invalid quotes before moving to the next paper.

- [ ] **Step 7: Lock and validate the complete corpus**

Run:

```bash
cd experiments/q0
uv run q0 corpus verify --root ../..
uv run q0 gold validate --root ../..
uv run pytest tests/test_corpus.py -q
```

Expected: 5 papers, 20 answerable cases, 5 unanswerable cases, at least 40 reading-order samples, and all tests pass.

- [ ] **Step 8: Commit only durable corpus metadata and gold annotations**

```bash
git add qualification/corpus/manifest.json qualification/gold experiments/q0/src/q0/corpus.py experiments/q0/src/q0/cli.py experiments/q0/tests/test_corpus.py
git commit -m "data(q0): freeze qualification corpus and gold evidence"
```

Verify `git status --short` does not list any PDF or `.env` file before committing.

---

### Task 3: Implement and verify the common parser/provenance harness

**Files:**
- Create: `experiments/q0/src/q0/normalization.py`
- Create: `experiments/q0/src/q0/parsers.py`
- Create: `experiments/q0/src/q0/parser_eval.py`
- Create: `experiments/q0/tests/test_normalization.py`
- Create: `experiments/q0/tests/test_parsers.py`
- Modify: `experiments/q0/src/q0/cli.py`

**Interfaces:**
- Consumes: corpus manifest, cached PDFs, gold evidence, and `ParsedBlock` from Tasks 1–2.
- Produces: `ParserAdapter.parse(pdf: Path, paper_id: str) -> Iterator[ParsedBlock]`.
- Produces: `normalize_with_map(spans: Sequence[RawSpan]) -> NormalizedText` where `NormalizedText.map_range(start, end) -> tuple[SourceSpan, ...]`.
- Produces CLI: `q0 parser run --candidate {docling,pymupdf}` and `q0 parser evaluate`.

- [ ] **Step 1: Write failing reversible-normalization tests**

Cover whitespace collapse, line joining, dehyphenation, Unicode normalization, and multi-span quote mapping. The central test must assert that normalized offsets for `"scaled dot-product"` map back to both source line boxes after a line break.

Run:

```bash
cd experiments/q0
uv run pytest tests/test_normalization.py -q
```

Expected: FAIL because `normalize_with_map` does not exist.

- [ ] **Step 2: Implement reversible normalization minimally**

Represent normalized text as characters plus source references during transformation, then compact adjacent references into `SourceSpan` ranges. Never reconstruct provenance by fuzzy searching after normalization.

Run the targeted tests until they pass:

```bash
cd experiments/q0
uv run pytest tests/test_normalization.py -q
```

- [ ] **Step 3: Write adapter conformance tests**

For both adapters, tests must assert:

- page indices are zero-based and non-negative;
- output reading order is strictly increasing within a paper;
- every non-empty block has at least one source span;
- every box has `x0 < x1`, `y0 < y1`, and `bottom-left` origin;
- span ranges stay within normalized block text;
- the golden evidence quote resolves to at least one box.

Use the cached golden PDF as an integration fixture; do not mock parser outputs.

- [ ] **Step 4: Implement the PyMuPDF geometry-first adapter**

Use `TextPage` RAWDICT/spans/characters as the provenance source. Treat `sort=True` as a heuristic input, not proof of natural reading order. Remove repeating header/footer blocks only after recurrence is observed across pages. Convert PyMuPDF coordinates into the common bottom-left convention with the page height recorded from the source page.

- [ ] **Step 5: Implement the Docling adapter**

Map Docling document items and `ProvenanceItem` bounding boxes into the same `ParsedBlock` contract. Preserve original item labels and section paths in candidate-specific raw artifacts; convert only the common comparison output.

- [ ] **Step 6: Run adapter conformance and targeted parser tests**

Run:

```bash
cd experiments/q0
uv run pytest tests/test_normalization.py tests/test_parsers.py -q
```

Expected: PASS for both candidates on the golden PDF.

- [ ] **Step 7: Run both candidates over the fixed corpus**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run q0 parser run --candidate pymupdf --run-id "$RUN_ID" --root ../..
uv run q0 parser run --candidate docling --run-id "$RUN_ID" --root ../..
uv run q0 parser evaluate --run-id "$RUN_ID" --root ../..
uv run q0 artifacts validate --run-dir "../../qualification/results/$RUN_ID"
```

Expected: `parser-results.json` contains candidate metrics, every threshold outcome, per-case failures, latency, peak memory, and the deterministic winner or a typed `no_candidate_qualified` blocker.

- [ ] **Step 8: Apply the parser stop gate**

If no candidate qualifies, stop all later tasks. Write the blocker report, set Q0 `Blocked`, commit the evidence, and do not weaken thresholds. If one or both qualify, persist the selected parser identity for Task 4.

- [ ] **Step 9: Commit parser harness and results**

```bash
git add experiments/q0/src/q0 experiments/q0/tests qualification/results/*/parser-results.json
git commit -m "experiment(q0): qualify parser provenance"
```

---

### Task 4: Qualify native Ollama embeddings and Qdrant retrieval

**Files:**
- Create: `experiments/q0/src/q0/chunking.py`
- Create: `experiments/q0/src/q0/ollama_client.py`
- Create: `experiments/q0/src/q0/embedding_eval.py`
- Create: `experiments/q0/tests/test_embedding_eval.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Modify: `experiments/q0/compose.yml`
- Create: `qualification/results/$RUN_ID/embedding-results.json`

**Interfaces:**
- Consumes: selected parser output and 20 answerable gold cases from Task 3.
- Produces: deterministic `Chunk` records with chunk-to-source mappings.
- Produces: `OllamaEmbeddingClient.embed(texts: Sequence[str], *, truncate: bool = False) -> EmbeddingBatch`.
- Produces CLI: `q0 embedding preflight`, `q0 embedding run --model MODEL`, and `q0 embedding evaluate`.

- [ ] **Step 1: Create Qdrant-only temporary Compose configuration**

`compose.yml` exposes Qdrant only to localhost, pins the resolved image digest in the committed file, uses a named temporary volume, and defines the official health endpoint. It must not introduce PostgreSQL, MinIO, API, or web services.

Run:

```bash
cd experiments/q0
docker compose config --quiet
docker compose up -d --wait qdrant
```

Expected: Compose config validates and Qdrant reports healthy.

- [ ] **Step 2: Write failing embedding guard and metric tests**

Tests must cover:

```python
def test_rejects_dimension_drift() -> None: ...
def test_rejects_non_finite_or_zero_vectors() -> None: ...
def test_recall_at_k_uses_gold_chunk_ids() -> None: ...
def test_selection_prefers_nomic_within_five_points() -> None: ...
def test_selection_uses_bge_for_material_gain() -> None: ...
```

Run:

```bash
cd experiments/q0
uv run pytest tests/test_embedding_eval.py -q
```

Expected: FAIL because evaluation functions do not exist.

- [ ] **Step 3: Implement deterministic structure-aware chunks**

Use the selected parser blocks. Keep chunks within one section, prefer paragraph boundaries, include the section heading as metadata, and retain exact block/span references. Freeze the resulting chunk set before running either model; both models must embed byte-identical chunk text.

- [ ] **Step 4: Implement the native Ollama client and preflight**

The client must call `/api/show` and `/api/embed`, record actual architecture metadata, send `truncate: false`, verify finite non-zero vectors, and reject dimension drift. Do not infer the embedding-dimension field name from the model name; inspect the real `/api/show` payload.

Run the host preflight for each exact model:

```bash
ollama pull bge-m3:567m
ollama pull nomic-embed-text:137m-v1.5-fp16
cd experiments/q0
uv run q0 embedding preflight --model bge-m3:567m
uv run q0 embedding preflight --model nomic-embed-text:137m-v1.5-fp16
```

Expected: each preflight prints exact model identity, digest, dimension, quantization, one finite non-zero vector, and runtime placement. A missing tag is a typed blocker; no substitute tag is pulled.

- [ ] **Step 5: Run the BGE-M3 candidate**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run q0 embedding run --model bge-m3:567m --run-id "$RUN_ID" --root ../..
```

Expected: separate Qdrant collection, complete corpus indexing, 20-query result set, warm p50/p95, Recall@1/5, MRR, throughput, peak memory, and no silent truncation.

- [ ] **Step 6: Unload, then run the Nomic candidate under the same conditions**

Unload the first model before measuring the second so resident weights do not bias memory. Use the identical chunk set and query cases:

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
ollama stop bge-m3:567m
cd experiments/q0
uv run q0 embedding run --model nomic-embed-text:137m-v1.5-fp16 --run-id "$RUN_ID" --root ../..
```

- [ ] **Step 7: Select the winner exactly as specified**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run q0 embedding evaluate --run-id "$RUN_ID" --root ../..
uv run pytest tests/test_embedding_eval.py -q
uv run q0 artifacts validate --run-dir "../../qualification/results/$RUN_ID"
```

Expected: `embedding-results.json` pins model tag/digest, runtime, quantization, dimension, metric, prefixes, max input, truncation behavior, batch size, concurrency, collection identity, all thresholds, and selection rationale.

- [ ] **Step 8: Apply the embedding stop gate**

If neither model qualifies, stop. Record the blocker and do not switch to vendor embeddings. Otherwise persist the selected configuration for Task 6.

- [ ] **Step 9: Commit embedding harness and results**

```bash
git add experiments/q0 qualification/results/*/embedding-results.json
git commit -m "experiment(q0): qualify native embedding retrieval"
```

---

### Task 5: Implement and run OpenRouter and Gemini generation qualification

**Files:**
- Create: `experiments/q0/src/q0/providers.py`
- Create: `experiments/q0/src/q0/generation_eval.py`
- Create: `experiments/q0/tests/test_providers.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Modify: `experiments/q0/.env.example`
- Create: `qualification/results/$RUN_ID/generation-results.json`

**Interfaces:**
- Consumes: 12 bounded generation cases derived from validated gold evidence.
- Produces: `GenerationRequest`, `StreamEvent`, `ProviderError`, and `GenerationClient` protocol.
- Produces adapters: `OpenRouterGenerationClient` and `GeminiGenerationClient`.
- Produces CLI: `q0 provider discover`, `q0 provider preflight`, `q0 generation run`, and `q0 generation evaluate`.

The common protocol must be:

```python
from collections.abc import AsyncIterator
from typing import Protocol


class GenerationClient(Protocol):
    async def stream_grounded_answer(
        self, request: GenerationRequest
    ) -> AsyncIterator[StreamEvent]: ...

    async def rewrite_query(self, request: RewriteRequest) -> RewriteResult: ...

    async def repair_citations(
        self, request: RepairRequest
    ) -> GroundedAnswer: ...
```

- [ ] **Step 1: Define environment names without secrets**

`.env.example` contains names only:

```dotenv
GENERATION_PROVIDER=openrouter
OPENROUTER_API_KEY=
Q0_OPENROUTER_MODEL=
GEMINI_API_KEY=
Q0_GEMINI_MODEL=
```

The loader must fail closed when a selected provider lacks its key or exact model ID. It must never print secret values.

- [ ] **Step 2: Write failing provider contract tests using local fixtures**

Tests must cover:

- ordered SSE deltas and one terminal event;
- JSON-schema answer parsing;
- unknown source ID rejection;
- exact evidence quote validation;
- typed authentication, rate-limit, timeout, malformed-schema, interrupted-stream, and provider-unavailable errors;
- exactly one citation-repair call;
- no adapter invocation for the unselected provider;
- no automatic failover.

Run:

```bash
cd experiments/q0
uv run pytest tests/test_providers.py -q
```

Expected: FAIL because adapters are absent.

- [ ] **Step 3: Implement the provider-neutral types and local validators**

`StreamEvent` is a discriminated union with exact event types:

```text
answer.delta
citation.resolved
answer.completed
answer.failed
```

Only `answer.completed` carries the final validated `GroundedAnswer`. Provider payloads are translated at the adapter boundary and are not written verbatim to durable results.

- [ ] **Step 4: Implement OpenRouter discovery and adapter behavior**

Discovery must fetch the current model catalog, filter exact free variants, exclude `openrouter/free`, and record capability metadata. The selected request must use the exact configured `Q0_OPENROUTER_MODEL` and require endpoints compatible with structured-output parameters. Capture the actual response model; mismatch is a failed case.

- [ ] **Step 5: Implement Gemini discovery and adapter behavior**

Use the official Google Gen AI SDK to list project-visible models and filter models supporting generation. The selected request must use the exact configured `Q0_GEMINI_MODEL`, streaming, and JSON-schema output. Preflight records project-visible rate-limit information entered from AI Studio as run metadata; product behavior must not assume a fixed free quota.

- [ ] **Step 6: Pass all local provider tests before network calls**

```bash
cd experiments/q0
uv run pytest tests/test_providers.py -q
```

Expected: PASS with network disabled because tests use fixed local response fixtures.

- [ ] **Step 7: Discover and pin exactly one free candidate per provider**

Run:

```bash
cd experiments/q0
uv run q0 provider discover --provider openrouter --output ../../qualification/private/openrouter-candidates.json
uv run q0 provider discover --provider gemini --output ../../qualification/private/gemini-candidates.json
```

Inspect each generated capability record using the spec's criteria. Set one exact model ID per provider in the uncommitted `.env`; record only selected IDs and capability metadata in the sanitized result artifact.

- [ ] **Step 8: Run provider preflight before consuming all cases**

```bash
cd experiments/q0
uv run q0 provider preflight --provider openrouter
uv run q0 provider preflight --provider gemini
```

Expected for each: authentication succeeds, exact model identity is returned, one structured response validates, streaming yields a delta and terminal event, and errors are typed. If a free model fails, record the failure before considering another model.

- [ ] **Step 9: Enforce the paid-call confirmation boundary**

If no free candidate for either adapter passes, stop and request explicit confirmation naming the provider, model, maximum spend, and exact 12-case scope. Do not execute a paid request based only on this plan.

- [ ] **Step 10: Run the 12 bounded cases for both qualified adapters**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run q0 generation run --provider openrouter --run-id "$RUN_ID" --root ../..
uv run q0 generation run --provider gemini --run-id "$RUN_ID" --root ../..
uv run q0 generation evaluate --run-id "$RUN_ID" --root ../..
uv run q0 artifacts validate --run-dir "../../qualification/results/$RUN_ID"
```

Expected: `generation-results.json` includes schema/source/quote/refusal/follow-up/repair outcomes, TTFT, total latency, usage availability, cost classification, exact requested and response model IDs, typed provider errors, and deterministic primary/fallback selection.

- [ ] **Step 11: Apply the generation stop gate**

Both adapters need a qualifying pinned model. If either lacks one, set Q0 `Blocked`; do not weaken the contract or mark the other adapter sufficient.

- [ ] **Step 12: Commit sanitized provider harness and results**

Before staging, scan tracked candidates and results for key prefixes and unredacted request/response bodies. Then commit:

```bash
git add experiments/q0/src/q0 experiments/q0/tests experiments/q0/.env.example qualification/results/*/generation-results.json
git commit -m "experiment(q0): qualify hosted generation adapters"
```

---

### Task 6: Produce the integrated question-to-highlight proof

**Files:**
- Create: `experiments/q0/src/q0/integrated_proof.py`
- Create: `experiments/q0/src/q0/render_highlight.py`
- Create: `experiments/q0/tests/test_integrated_proof.py`
- Modify: `experiments/q0/src/q0/cli.py`
- Create: `qualification/results/$RUN_ID/integrated-proof.json`
- Create: `qualification/results/$RUN_ID/evidence-highlight.html`
- Create: `qualification/results/$RUN_ID/evidence-highlight.svg`

**Interfaces:**
- Consumes: selected parser, embedding configuration, primary generation configuration, golden question, and gold geometry.
- Produces: `IntegratedProof` containing exact identities, retrieved chunk IDs, answer, citations, quote offsets, page, boxes, and artifact paths.
- Produces CLI: `q0 proof run` and `q0 proof validate`.

- [ ] **Step 1: Write failing geometry and proof-invariant tests**

Tests must assert:

```python
def test_pdf_box_transforms_to_svg_without_crossing_columns() -> None: ...
def test_page_only_resolution_does_not_pass_exact_proof() -> None: ...
def test_every_answer_claim_has_a_valid_citation() -> None: ...
def test_integrated_artifact_identity_matches_component_results() -> None: ...
```

Run:

```bash
cd experiments/q0
uv run pytest tests/test_integrated_proof.py -q
```

Expected: FAIL because proof functions do not exist.

- [ ] **Step 2: Implement exact proof orchestration**

Use the exact golden question from the spec. The orchestrator must:

1. embed the query with the selected embedding model;
2. retrieve from the selected candidate collection;
3. call the selected primary generator once;
4. validate source IDs and evidence quote locally;
5. map quote offsets through chunk-to-span mappings;
6. require exact non-empty boxes on the annotated page;
7. reject page-only or fuzzy cross-page fallback;
8. write `IntegratedProof` atomically.

- [ ] **Step 3: Render a self-contained visual artifact**

Generate static HTML and SVG containing the rendered PDF page image or page-sized representation, translucent evidence boxes, the question, answer, evidence quote, and identity footer. The artifact must work without a running server or external JavaScript.

- [ ] **Step 4: Run the proof and machine validation**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run q0 proof run --run-id "$RUN_ID" --root ../..
uv run q0 proof validate --run-id "$RUN_ID" --root ../..
uv run pytest tests/test_integrated_proof.py -q
uv run q0 artifacts validate --run-dir "../../qualification/results/$RUN_ID"
```

Expected: exact page and boxes pass; page-only resolution fails; identity matches parser/embedding/generation results.

- [ ] **Step 5: Perform browser visual inspection**

Open `evidence-highlight.html` in a real browser. Verify the highlighted sentence is the expected scaled-dot-product-attention evidence, remains inside the correct column, and the identity footer is readable. Save the browser inspection result and screenshot path in `integrated-proof.json`; do not infer visual correctness from coordinates alone.

- [ ] **Step 6: Commit the integrated evidence**

```bash
git add experiments/q0 qualification/results/*/integrated-proof.json qualification/results/*/evidence-highlight.html qualification/results/*/evidence-highlight.svg
git commit -m "experiment(q0): prove exact evidence highlighting"
```

---

### Task 7: Write the decision report and reconcile every control artifact

**Files:**
- Create: `docs/superpowers/reports/2026-09-18-researcy-technical-qualification-report.md`
- Modify: `docs/superpowers/specs/2026-09-18-researcy-delivery-map.md`
- Modify only if evidence requires an approved architecture change: `docs/superpowers/specs/2026-09-18-researcy-system-design.md`
- Modify: `experiments/q0/src/q0/artifacts.py`
- Modify: `experiments/q0/src/q0/cli.py`

**Interfaces:**
- Consumes: every schema-validated result in the selected run directory.
- Produces: one human-readable report whose decisions are mechanically cross-checked against result identities and threshold outcomes.
- Produces CLI: `q0 report verify --report PATH --run-dir PATH`.

- [ ] **Step 1: Write a failing report-consistency check**

The verifier must fail when the report names a parser, embedding model, provider model, threshold outcome, or run ID different from machine-readable results. Add a fixture with a deliberate BGE/Nomic mismatch and verify rejection.

- [ ] **Step 2: Draft the report entirely from observed results**

The report must contain:

- run/environment and corpus identities;
- parser comparison and selected strategy;
- embedding comparison and selected complete configuration;
- OpenRouter and Gemini exact model IDs;
- primary and manual fallback selection;
- integrated proof link and visual review result;
- every failure and limitation;
- impact on M1–M4;
- paid spend, including zero;
- final `Verified` or `Blocked` recommendation.

Do not claim a metric not present in result JSON.

- [ ] **Step 3: Verify report/result consistency**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run q0 report verify \
  --report ../../docs/superpowers/reports/2026-09-18-researcy-technical-qualification-report.md \
  --run-dir "../../qualification/results/$RUN_ID"
```

Expected: PASS with every pinned identity and decision matching source results.

- [ ] **Step 4: Update the delivery map according to evidence**

If every exit-gate condition passes:

- set Q0 status to `Verified`;
- set PARSE-01, EMB-01, GEN-01, and CIT-01 qualification coverage to `Verified` while retaining later production owners;
- link the report and selected run directory in verification evidence;
- set the current control point to M1 brainstorming.

If any stop condition remains:

- set Q0 status to `Blocked`;
- keep unmet requirements at `Designed` or `Blocked` as appropriate;
- link the blocker evidence;
- do not authorize M1.

- [ ] **Step 5: Handle a required master-spec change before proceeding**

If evidence contradicts revision 1.0, stop. Propose the exact master diff and obtain user approval before editing the master spec. If no conflict exists, record `No master revision required` in the report.

- [ ] **Step 6: Commit report and control-state update**

```bash
git add docs/superpowers/reports/2026-09-18-researcy-technical-qualification-report.md docs/superpowers/specs/2026-09-18-researcy-delivery-map.md qualification/results
git commit -m "docs(q0): record technical qualification decisions"
```

---

### Task 8: Remove the throwaway harness and close Q0 cleanly

**Files:**
- Delete: `experiments/q0/`
- Modify: `.gitignore` only to remove rules that refer exclusively to deleted temporary paths; retain secret, cache, and Python artifact protection that future milestones need.
- Verify: all durable `qualification/` results, report, master spec, and delivery map remain.

**Interfaces:**
- Consumes: verified report and delivery-state update from Task 7.
- Produces: a repository containing evidence and decisions but no Q0 probe application code.

- [ ] **Step 1: Run the final probe checks before deletion**

```bash
RUN_ID=$(cd experiments/q0 && uv run q0 active-run --root ../..)
cd experiments/q0
uv run pytest tests -q
uv run q0 artifacts validate --run-dir "../../qualification/results/$RUN_ID"
uv run q0 report verify \
  --report ../../docs/superpowers/reports/2026-09-18-researcy-technical-qualification-report.md \
  --run-dir "../../qualification/results/$RUN_ID"
```

Expected: all transient tests and durable validation pass.

- [ ] **Step 2: Verify no forbidden files are tracked**

Confirm Git tracks no PDF, `.env`, API key, model weights, `qualification/private/`, or `qualification/.cache/` path. Any match is removed from the index and treated as a blocking security defect before continuing.

- [ ] **Step 3: Delete the complete throwaway probe**

Delete `experiments/q0/` in one change. Do not move its modules into an application package.

- [ ] **Step 4: Validate durable artifacts without the deleted harness**

Use a disposable `uvx` JSON Schema validator against every result schema and run a static link/path check over the report and delivery map. Open the committed evidence HTML directly and verify it still renders without probe assets.

Expected:

```text
experiments/q0 does not exist
qualification/corpus exists
qualification/gold exists
qualification/schemas exists
qualification/results/$RUN_ID exists
qualification report exists
all JSON validates
all report evidence links resolve
```

- [ ] **Step 5: Commit cleanup**

```bash
git add -A experiments/q0 .gitignore qualification docs/superpowers
git commit -m "chore(q0): remove qualification probe harness"
```

- [ ] **Step 6: Record the final execution handoff**

If Q0 is `Verified`, the next allowed work is M1 Identity and Personal Library brainstorming. If Q0 is `Blocked`, the next allowed work is only the smallest decision named in the report. Do not begin M1 implementation from this plan.
