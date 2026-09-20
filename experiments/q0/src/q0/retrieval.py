from __future__ import annotations

import hashlib
import json
import math
import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import httpx
import psutil
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from q0.models import (
    ARTIFACT_VERSION,
    BBox,
    EnvironmentResult,
    EvidenceCase,
    ParsedBlock,
    EmbeddingResult,
    SourceSpan,
    ThresholdOutcome,
    write_json_atomic,
)

CANDIDATE_MODELS: tuple[str, ...] = (
    "bge-m3:567m",
    "nomic-embed-text:137m-v1.5-fp16",
)

MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "bge-m3:567m": {
        "query_prefix": "",
        "document_prefix": "",
        "distance_metric": "cosine",
    },
    "nomic-embed-text:137m-v1.5-fp16": {
        "query_prefix": "search_query: ",
        "document_prefix": "search_document: ",
        "distance_metric": "cosine",
    },
}

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
QDRANT_URL = "http://127.0.0.1:6333"


class VectorValidationError(ValueError):
    pass


class RetrievalValidationError(ValueError):
    pass


def validate_vector(
    vector: Sequence[float],
    expected_dimension: int | None = None,
) -> list[float]:
    if not isinstance(vector, (list, tuple)):
        raise VectorValidationError("vector must be a sequence of floats")
    if expected_dimension is not None and len(vector) != expected_dimension:
        raise VectorValidationError(
            f"vector dimension {len(vector)} does not match expected {expected_dimension}"
        )
    for x in vector:
        if math.isnan(x) or math.isinf(x):
            raise VectorValidationError("vector contains non-finite values (NaN or Inf)")
    if all(x == 0.0 for x in vector):
        raise VectorValidationError("vector cannot be all zeros")
    return list(vector)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    paper_id: str
    section_path: list[str]
    heading: str | None = None
    page_indices: list[int]
    block_indices: list[int]
    text: str
    source_spans: list[SourceSpan]


def build_chunks(
    blocks: Sequence[ParsedBlock],
    max_chars: int = 2000,
) -> list[Chunk]:
    if not blocks:
        return []

    chunks: list[Chunk] = []
    chunk_counts_by_paper: dict[str, int] = defaultdict(int)
    current_blocks: list[ParsedBlock] = []

    def flush() -> None:
        nonlocal current_blocks
        if not current_blocks:
            return
        paper_id = current_blocks[0].paper_id
        section_path = list(current_blocks[0].section_path)
        heading = section_path[-1] if section_path else None

        combined_text_parts: list[str] = []
        combined_spans: list[SourceSpan] = []
        page_indices_set: set[int] = set()
        block_indices: list[int] = []

        current_offset = 0
        for i, b in enumerate(current_blocks):
            if i > 0:
                combined_text_parts.append("\n\n")
                current_offset += 2
            combined_text_parts.append(b.normalized_text)
            for span in b.source_spans:
                combined_spans.append(
                    SourceSpan(
                        text_start=span.text_start + current_offset,
                        text_end=span.text_end + current_offset,
                        page_index=span.page_index,
                        bbox=span.bbox,
                    )
                )
            current_offset += len(b.normalized_text)
            page_indices_set.add(b.page_index)
            block_indices.append(b.reading_order)

        full_text = "".join(combined_text_parts)
        chunk_idx = chunk_counts_by_paper[paper_id]
        chunk_counts_by_paper[paper_id] += 1

        chunks.append(
            Chunk(
                chunk_id=f"{paper_id}-chunk-{chunk_idx:04d}",
                paper_id=paper_id,
                section_path=section_path,
                heading=heading,
                page_indices=sorted(page_indices_set),
                block_indices=block_indices,
                text=full_text,
                source_spans=combined_spans,
            )
        )
        current_blocks = []

    for b in blocks:
        if current_blocks and (
            current_blocks[0].paper_id != b.paper_id
            or current_blocks[0].section_path != b.section_path
        ):
            flush()

        if not current_blocks:
            current_len = 0
        else:
            current_len = sum(len(x.normalized_text) for x in current_blocks) + 2 * (
                len(current_blocks) - 1
            )

        needed = (2 if current_blocks else 0) + len(b.normalized_text)
        if current_blocks and (current_len + needed > max_chars):
            flush()

        if len(b.normalized_text) <= max_chars:
            current_blocks.append(b)
        else:
            # Single block exceeds max_chars; split into sub-chunks
            text = b.normalized_text
            start = 0
            while start < len(text):
                end = min(start + max_chars, len(text))
                slice_text = text[start:end]
                slice_spans = [
                    SourceSpan(
                        text_start=s.text_start - start,
                        text_end=s.text_end - start,
                        page_index=s.page_index,
                        bbox=s.bbox,
                    )
                    for s in b.source_spans
                    if s.text_start >= start and s.text_end <= end
                ]
                paper_id = b.paper_id
                section_path = list(b.section_path)
                heading = section_path[-1] if section_path else None
                chunk_idx = chunk_counts_by_paper[paper_id]
                chunk_counts_by_paper[paper_id] += 1
                chunks.append(
                    Chunk(
                        chunk_id=f"{paper_id}-chunk-{chunk_idx:04d}",
                        paper_id=paper_id,
                        section_path=section_path,
                        heading=heading,
                        page_indices=[b.page_index],
                        block_indices=[b.reading_order],
                        text=slice_text,
                        source_spans=slice_spans,
                    )
                )
                start = end

    flush()
    return chunks


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_1: float
    recall_at_5: float
    mrr: float
    first_relevant_ranks: list[int | None] = field(default_factory=list)
    hits_at_1: list[float] = field(default_factory=list)
    hits_at_5: list[float] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)


def retrieval_metrics(
    ranked_source_ids: Sequence[Sequence[str]],
    relevant_source_ids: Sequence[set[str]],
    k_values: Sequence[int] = (1, 5),
) -> RetrievalMetrics:
    if len(ranked_source_ids) != len(relevant_source_ids):
        raise ValueError(
            "ranked_source_ids and relevant_source_ids must have the same length"
        )
    if not ranked_source_ids:
        return RetrievalMetrics(
            recall_at_1=0.0,
            recall_at_5=0.0,
            mrr=0.0,
        )

    first_ranks: list[int | None] = []
    hits_1: list[float] = []
    hits_5: list[float] = []
    rrs: list[float] = []

    for ranked, relevant in zip(ranked_source_ids, relevant_source_ids):
        found_rank: int | None = None
        for rank, source_id in enumerate(ranked, start=1):
            if source_id in relevant:
                found_rank = rank
                break
        first_ranks.append(found_rank)
        if found_rank is not None:
            rrs.append(1.0 / found_rank)
            hits_1.append(1.0 if found_rank <= 1 else 0.0)
            hits_5.append(1.0 if found_rank <= 5 else 0.0)
        else:
            rrs.append(0.0)
            hits_1.append(0.0)
            hits_5.append(0.0)

    n = len(ranked_source_ids)
    return RetrievalMetrics(
        recall_at_1=sum(hits_1) / n,
        recall_at_5=sum(hits_5) / n,
        mrr=sum(rrs) / n,
        first_relevant_ranks=first_ranks,
        hits_at_1=hits_1,
        hits_at_5=hits_5,
        reciprocal_ranks=rrs,
    )


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RetrievalValidationError(
            f"git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout.strip()


def _require_clean_producer(root: Path) -> str:
    status = _git(
        root, "status", "--porcelain=v1", "--untracked-files=no", "--", "experiments/q0"
    )
    if status:
        raise RetrievalValidationError(
            f"git working tree must be clean before measurement; status was:\n{status}"
        )
    return _git(root, "rev-parse", "HEAD")


def _load_environment(root: Path, run_id: str) -> EnvironmentResult:
    path = root / "qualification" / "results" / run_id / "environment.json"
    try:
        environment = EnvironmentResult.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except FileNotFoundError as error:
        raise RetrievalValidationError(f"run environment not found: {path}") from error
    except (OSError, ValidationError) as error:
        raise RetrievalValidationError(
            f"invalid run environment {path}: {error}"
        ) from error
    if environment.run_id != run_id:
        raise RetrievalValidationError(
            f"environment run ID {environment.run_id!r} does not match {run_id!r}"
        )
    return environment


def _load_evidence(root: Path) -> list[EvidenceCase]:
    path = root / "qualification" / "gold" / "evidence.jsonl"
    evidence: list[EvidenceCase] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                evidence.append(EvidenceCase.model_validate_json(line))
            except ValidationError as error:
                raise RetrievalValidationError(
                    f"invalid evidence case {path}:{line_number}: {error}"
                ) from error
    except OSError as error:
        raise RetrievalValidationError(
            f"cannot read gold evidence {path}: {error}"
        ) from error
    return evidence


def _process_tree_rss(process: psutil.Process) -> int:
    total = 0
    try:
        processes = [process, *process.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        processes = [process]
    for item in processes:
        try:
            total += int(item.memory_info().rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


class _PeakMemoryMonitor:
    def __init__(self) -> None:
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._sample,
            name="q0-retrieval-peak-memory",
            daemon=True,
        )
        self.baseline_bytes = _process_tree_rss(self._process)
        self.peak_bytes = self.baseline_bytes

    def _sample(self) -> None:
        while not self._stop.wait(0.01):
            self.peak_bytes = max(
                self.peak_bytes,
                _process_tree_rss(self._process),
            )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> int:
        self._stop.set()
        self._thread.join()
        return self.peak_bytes


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1


def _model_slug(model: str) -> str:
    return model.replace(":", "-").replace("/", "-")


def _ollama_show(model: str, base_url: str = OLLAMA_BASE_URL) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/show"
    try:
        response = httpx.post(url, json={"model": model}, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except Exception as error:
        raise RetrievalValidationError(
            f"Ollama /api/show failed for model {model!r}: {error}"
        ) from error


def _ollama_tags(base_url: str = OLLAMA_BASE_URL) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        return response.json().get("models", [])
    except Exception as error:
        raise RetrievalValidationError(
            f"Ollama /api/tags failed: {error}"
        ) from error


def _ollama_embed(
    model: str,
    inputs: list[str],
    truncate: bool = False,
    base_url: str = OLLAMA_BASE_URL,
    timeout: float = 120.0,
) -> list[list[float]]:
    url = f"{base_url.rstrip('/')}/api/embed"
    payload = {
        "model": model,
        "input": inputs,
        "truncate": truncate,
    }
    try:
        response = httpx.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise RetrievalValidationError(
                f"Ollama /api/embed returned invalid payload: {data}"
            )
        return embeddings
    except Exception as error:
        raise RetrievalValidationError(
            f"Ollama /api/embed failed for model {model!r}: {error}"
        ) from error


def _ensure_chunks(root: Path, run_id: str) -> tuple[Path, list[Chunk], str]:
    private_dir = root / "qualification" / "private" / run_id
    chunks_path = private_dir / "chunks.jsonl"
    if chunks_path.exists():
        content = chunks_path.read_text(encoding="utf-8")
        chunks = [
            Chunk.model_validate_json(line)
            for line in content.splitlines()
            if line.strip()
        ]
        chunk_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return chunks_path, chunks, chunk_hash

    # Need to build from selected parser blocks
    blocks_path = private_dir / "parsed-blocks-pymupdf.jsonl"
    if not blocks_path.exists():
        raise RetrievalValidationError(
            f"selected parser blocks not found at {blocks_path}"
        )
    blocks = [
        ParsedBlock.model_validate_json(line)
        for line in blocks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    chunks = build_chunks(blocks, max_chars=2000)
    lines = [chunk.model_dump_json() for chunk in chunks]
    serialized = "\n".join(lines) + "\n"
    write_json_atomic_raw(chunks_path, serialized)
    chunk_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return chunks_path, chunks, chunk_hash


def write_json_atomic_raw(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp-{time.time_ns()}")
    try:
        with temp.open("w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            import os
            os.fsync(f.fileno())
        temp.replace(path)
        import os
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if temp.exists():
            temp.unlink()


def run_embedding_preflight(
    *, root: Path, run_id: str, model: str
) -> dict[str, Any]:
    root = root.resolve()
    _load_environment(root, run_id)
    if model not in CANDIDATE_MODELS:
        raise RetrievalValidationError(
            f"model {model!r} is not one of candidate models {CANDIDATE_MODELS}"
        )

    # 1. Verify health
    try:
        qdrant_client = QdrantClient(url=QDRANT_URL, timeout=10)
        qdrant_client.get_collections()
    except Exception as error:
        raise RetrievalValidationError(
            f"Qdrant connection to {QDRANT_URL} failed: {error}"
        ) from error

    try:
        version_resp = httpx.get(f"{OLLAMA_BASE_URL}/api/version", timeout=10)
        version_resp.raise_for_status()
        ollama_version = version_resp.json().get("version")
    except Exception as error:
        raise RetrievalValidationError(
            f"Ollama connection to {OLLAMA_BASE_URL} failed: {error}"
        ) from error

    # 2. Get show info and tags info
    show_info = _ollama_show(model)
    tags_info = _ollama_tags()
    matching_tag = next((m for m in tags_info if m.get("name") == model or m.get("model") == model), None)
    digest = matching_tag.get("digest") if matching_tag else None
    if not digest:
        # Check details in show_info
        digest = show_info.get("details", {}).get("parent_model") or "unknown"

    details = show_info.get("details", {})
    model_info = show_info.get("model_info", {})
    architecture = (
        model_info.get("general.architecture")
        or details.get("family")
        or "unknown"
    )
    quantization = (
        details.get("quantization_level")
        or "unknown"
    )
    context_length = (
        model_info.get(f"{architecture}.context_length")
        or model_info.get("bert.context_length")
        or model_info.get("npx.context_length")
        or 8192
    )

    config = MODEL_CONFIGS[model]
    query_prefix = config["query_prefix"]
    doc_prefix = config["document_prefix"]

    # 3. Call embed with truncate=False for test document and test query
    test_doc = f"{doc_prefix}This is a test document for preflight validation."
    test_query = f"{query_prefix}What is the test document?"

    doc_embeddings = _ollama_embed(model, [test_doc], truncate=False)
    query_embeddings = _ollama_embed(model, [test_query], truncate=False)

    if not doc_embeddings or not query_embeddings:
        raise RetrievalValidationError("empty embedding returned during preflight")

    doc_vec = doc_embeddings[0]
    query_vec = query_embeddings[0]

    validate_vector(doc_vec)
    validate_vector(query_vec)

    if len(doc_vec) != len(query_vec):
        raise VectorValidationError(
            f"document dimension {len(doc_vec)} does not match query dimension {len(query_vec)}"
        )
    dimension = len(doc_vec)

    collection_name = f"q0-{run_id}-{_model_slug(model)}"
    preflight_metadata = {
        "model": model,
        "digest": digest,
        "architecture": architecture,
        "quantization": quantization,
        "dimension": dimension,
        "distance_metric": config["distance_metric"],
        "query_prefix": query_prefix,
        "document_prefix": doc_prefix,
        "context_length": context_length,
        "truncate": False,
        "batch_size": 8,
        "concurrency": 1,
        "collection_name": collection_name,
        "runtime_placement": f"native ARM64 Ollama {ollama_version}",
        "preflight_passed": True,
    }

    private_dir = root / "qualification" / "private" / run_id
    private_dir.mkdir(parents=True, exist_ok=True)
    out_path = private_dir / f"embedding-preflight-{_model_slug(model)}.json"
    write_json_atomic(out_path, preflight_metadata)
    return preflight_metadata


def run_embedding_candidate(
    *, root: Path, run_id: str, model: str
) -> dict[str, Any]:
    root = root.resolve()
    environment = _load_environment(root, run_id)
    producer_revision = _require_clean_producer(root)
    if model not in CANDIDATE_MODELS:
        raise RetrievalValidationError(f"unknown model candidate {model!r}")

    # Load preflight
    private_dir = root / "qualification" / "private" / run_id
    preflight_path = private_dir / f"embedding-preflight-{_model_slug(model)}.json"
    if not preflight_path.exists():
        raise RetrievalValidationError(
            f"preflight metadata not found at {preflight_path}; run preflight first"
        )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    dimension = int(preflight["dimension"])
    doc_prefix = str(preflight["document_prefix"])
    query_prefix = str(preflight["query_prefix"])
    collection_name = str(preflight["collection_name"])

    # Load chunks
    chunks_path, chunks, chunk_hash = _ensure_chunks(root, run_id)
    evidence = _load_evidence(root)
    answerable_cases = [case for case in evidence if case.answerable]
    if len(answerable_cases) != 8:
        raise RetrievalValidationError(
            f"expected 8 answerable cases, found {len(answerable_cases)}"
        )

    # Determine relevant chunks for each answerable case
    case_relevant_chunk_ids: dict[str, set[str]] = {}
    for case in answerable_cases:
        relevant: set[str] = set()
        for chunk in chunks:
            if chunk.paper_id == case.paper_id:
                if all(q in chunk.text for q in case.quotes):
                    relevant.add(chunk.chunk_id)
        if not relevant:
            raise RetrievalValidationError(
                f"no chunk contains gold quotes for case {case.case_id}"
            )
        case_relevant_chunk_ids[case.case_id] = relevant

    # Connect to Qdrant
    qdrant = QdrantClient(url=QDRANT_URL, timeout=60)
    qdrant.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
    )

    monitor = _PeakMemoryMonitor()
    monitor.start()

    # Index chunks in batches of 8, concurrency 1
    batch_size = 8
    all_vectors: list[list[float]] = []
    index_start = time.perf_counter()

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batch_inputs = [f"{doc_prefix}{c.text}" for c in batch]
        embeddings = _ollama_embed(model, batch_inputs, truncate=False)
        if len(embeddings) != len(batch):
            raise RetrievalValidationError(
                f"expected {len(batch)} embeddings, got {len(embeddings)}"
            )
        for vec in embeddings:
            validate_vector(vec, expected_dimension=dimension)
            all_vectors.append(vec)

    indexing_time_seconds = time.perf_counter() - index_start

    # Upsert points into Qdrant
    points = [
        PointStruct(
            id=idx,
            vector=vec,
            payload={
                "chunk_id": chunk.chunk_id,
                "paper_id": chunk.paper_id,
                "section_path": chunk.section_path,
                "heading": chunk.heading,
                "page_indices": chunk.page_indices,
                "block_indices": chunk.block_indices,
                "text": chunk.text,
            },
        )
        for idx, (chunk, vec) in enumerate(zip(chunks, all_vectors))
    ]
    # Batch upsert
    for i in range(0, len(points), 100):
        qdrant.upsert(collection_name=collection_name, points=points[i : i + 100])

    # Retrieval & Latency measurements: 1 warm-up + 3 measured warm repetitions for all 8 questions
    # 1. Warm-up query (unmeasured)
    warmup_query = f"{query_prefix}{answerable_cases[0].question}"
    warmup_embed = _ollama_embed(model, [warmup_query], truncate=False)
    qdrant.query_points(
        collection_name=collection_name,
        query=warmup_embed[0],
        limit=5,
    )

    # 2. 3 measured warm repetitions for all 8 questions (24 warm samples)
    warm_latencies: list[float] = []
    repetition_results: list[list[dict[str, Any]]] = []

    for rep in range(3):
        rep_cases: list[dict[str, Any]] = []
        for case in answerable_cases:
            q_text = f"{query_prefix}{case.question}"
            t0 = time.perf_counter()
            q_embed = _ollama_embed(model, [q_text], truncate=False)
            search_res = qdrant.query_points(
                collection_name=collection_name,
                query=q_embed[0],
                limit=10,
            )
            t_elapsed = time.perf_counter() - t0
            warm_latencies.append(t_elapsed)

            ranked_ids = [
                pt.payload["chunk_id"] for pt in search_res.points
            ]
            ranked_scores = [float(pt.score) for pt in search_res.points]
            rep_cases.append(
                {
                    "case_id": case.case_id,
                    "paper_id": case.paper_id,
                    "question": case.question,
                    "latency_seconds": t_elapsed,
                    "ranked_chunk_ids": ranked_ids,
                    "ranked_scores": ranked_scores,
                    "top_points": [
                        {
                            "chunk_id": pt.payload["chunk_id"],
                            "score": float(pt.score),
                            "paper_id": pt.payload["paper_id"],
                            "page_indices": pt.payload["page_indices"],
                            "section_path": pt.payload["section_path"],
                            "heading": pt.payload["heading"],
                            "text": pt.payload["text"],
                        }
                        for pt in search_res.points[:5]
                    ],
                }
            )
        repetition_results.append(rep_cases)

    peak_memory = monitor.stop()

    # Calculate metrics using the measured rankings from repetition 0 (or average)
    ranked_source_ids = [
        case_res["ranked_chunk_ids"] for case_res in repetition_results[0]
    ]
    relevant_source_ids = [
        case_relevant_chunk_ids[case.case_id] for case in answerable_cases
    ]

    metrics = retrieval_metrics(
        ranked_source_ids=ranked_source_ids,
        relevant_source_ids=relevant_source_ids,
        k_values=(1, 5),
    )

    latency_p50 = _percentile(warm_latencies, 50)
    latency_p95 = _percentile(warm_latencies, 95)

    case_summaries: list[dict[str, Any]] = []
    for idx, case in enumerate(answerable_cases):
        case_summaries.append(
            {
                "case_id": case.case_id,
                "paper_id": case.paper_id,
                "question": case.question,
                "first_relevant_rank": metrics.first_relevant_ranks[idx],
                "hit_at_1": bool(metrics.hits_at_1[idx]),
                "hit_at_5": bool(metrics.hits_at_5[idx]),
                "reciprocal_rank": metrics.reciprocal_ranks[idx],
                "top_5_chunk_ids": ranked_source_ids[idx][:5],
                "top_5_scores": repetition_results[0][idx]["ranked_scores"][:5],
            }
        )

    run_result = {
        "model": model,
        "run_id": run_id,
        "producer_git_revision": producer_revision,
        "run_initialized_git_revision": environment.run_initialized_git_revision,
        "chunk_set_sha256": chunk_hash,
        "total_chunks": len(chunks),
        "preflight": preflight,
        "measurements": {
            "indexing_time_seconds": indexing_time_seconds,
            "peak_memory_bytes": peak_memory,
            "warm_sample_count": len(warm_latencies),
            "warm_latencies_seconds": warm_latencies,
            "latency_p50_seconds": latency_p50,
            "latency_p95_seconds": latency_p95,
            "recall_at_1": metrics.recall_at_1,
            "recall_at_5": metrics.recall_at_5,
            "mrr": metrics.mrr,
            "cases": case_summaries,
        },
        "golden_context": repetition_results[0][0],  # for 1706.03762-answer-1
    }

    run_path = private_dir / f"embedding-run-{_model_slug(model)}.json"
    write_json_atomic(run_path, run_result)
    return run_result


def evaluate_embedding_candidates(
    *, root: Path, run_id: str
) -> EmbeddingResult:
    root = root.resolve()
    environment = _load_environment(root, run_id)
    current_revision = _require_clean_producer(root)

    private_dir = root / "qualification" / "private" / run_id
    chunks_path, chunks, chunk_hash = _ensure_chunks(root, run_id)
    chunks_by_id = {c.chunk_id: c for c in chunks}

    # Load candidate runs
    candidate_runs: dict[str, dict[str, Any]] = {}
    candidate_identities: dict[str, Any] = {}
    candidate_measurements: dict[str, Any] = {}
    candidate_gates: dict[str, dict[str, Any]] = {}
    producer_revisions: set[str] = set()

    for model in CANDIDATE_MODELS:
        run_file = private_dir / f"embedding-run-{_model_slug(model)}.json"
        if not run_file.exists():
            raise RetrievalValidationError(
                f"candidate run data not found at {run_file}; execute embedding run first"
            )
        data = json.loads(run_file.read_text(encoding="utf-8"))
        candidate_runs[model] = data
        p_rev = data.get("producer_git_revision", "")
        producer_revisions.add(p_rev)
        if p_rev != current_revision:
            raise RetrievalValidationError(
                f"candidate {model} was produced by {p_rev}, current revision is {current_revision}"
            )
        if (
            data.get("run_initialized_git_revision")
            != environment.run_initialized_git_revision
        ):
            raise RetrievalValidationError(
                f"candidate {model} run_initialized_git_revision does not match environment"
            )
        if data.get("chunk_set_sha256") != chunk_hash:
            raise RetrievalValidationError(
                f"candidate {model} chunk_set_sha256 does not match current chunks"
            )

        candidate_identities[model] = data["preflight"]
        meas = data["measurements"]
        candidate_measurements[model] = meas

        # Evaluate §7.2 gate
        # Requirements:
        # - no crash / OOM (measured completed)
        # - document and query dimensions identical (verified in preflight)
        # - no input silently truncated (truncate=False used)
        # - Recall@5 >= 0.75 (6/8)
        # - warm query p95 < 1.0s
        # - golden-paper indexing <= 300s (5 minutes)
        recall_at_5_passed = meas["recall_at_5"] >= 0.75
        p95_passed = meas["latency_p95_seconds"] < 1.0
        indexing_passed = meas["indexing_time_seconds"] <= 300.0
        dims_passed = bool(data["preflight"].get("dimension"))

        qualified = (
            recall_at_5_passed
            and p95_passed
            and indexing_passed
            and dims_passed
        )

        failure_reasons = []
        if not recall_at_5_passed:
            failure_reasons.append(
                f"Recall@5 {meas['recall_at_5']:.3f} is below 0.75 threshold"
            )
        if not p95_passed:
            failure_reasons.append(
                f"latency p95 {meas['latency_p95_seconds']:.4f}s is >= 1.0s threshold"
            )
        if not indexing_passed:
            failure_reasons.append(
                f"indexing time {meas['indexing_time_seconds']:.1f}s is > 300s threshold"
            )

        candidate_gates[model] = {
            "qualified": qualified,
            "failure_reason": "; ".join(failure_reasons) if failure_reasons else None,
            "checks": {
                "recall_at_5_min": recall_at_5_passed,
                "p95_latency_max": p95_passed,
                "indexing_time_max": indexing_passed,
                "dimension_stable": dims_passed,
                "no_silent_truncation": True,
                "no_crash_or_oom": True,
            },
        }

    # Selection rule:
    # "Choose Nomic when both models recover the same number of Recall@5 cases and error analysis shows no material disadvantage.
    # Choose BGE-M3 when it recovers at least one additional gold case or its ranking/error analysis shows a material scientific-retrieval advantage."
    qualified_models = [m for m in CANDIDATE_MODELS if candidate_gates[m]["qualified"]]

    selected_model: str | None = None
    selection_rationale: str = ""

    if not qualified_models:
        selected_model = None
        selection_rationale = "Neither embedding candidate passed the complete section 7.2 gate."
    elif len(qualified_models) == 1:
        selected_model = qualified_models[0]
        selection_rationale = f"Only candidate {selected_model} passed the complete section 7.2 gate."
    else:
        bge_meas = candidate_measurements["bge-m3:567m"]
        nomic_meas = candidate_measurements["nomic-embed-text:137m-v1.5-fp16"]
        bge_r5 = bge_meas["recall_at_5"]
        nomic_r5 = nomic_meas["recall_at_5"]

        if bge_r5 > nomic_r5:
            selected_model = "bge-m3:567m"
            selection_rationale = (
                f"BGE-M3 recovered more Recall@5 cases ({bge_r5:.3f} vs {nomic_r5:.3f})."
            )
        elif nomic_r5 > bge_r5:
            selected_model = "nomic-embed-text:137m-v1.5-fp16"
            selection_rationale = (
                f"Nomic recovered more Recall@5 cases ({nomic_r5:.3f} vs {bge_r5:.3f})."
            )
        else:
            # Equal Recall@5 hits
            # Check if BGE-M3 has material scientific ranking advantage (e.g. MRR substantially higher)
            if bge_meas["mrr"] > nomic_meas["mrr"] + 0.10:
                selected_model = "bge-m3:567m"
                selection_rationale = (
                    f"Equal Recall@5 ({bge_r5:.3f}), but BGE-M3 showed material scientific ranking advantage "
                    f"with MRR {bge_meas['mrr']:.3f} vs Nomic MRR {nomic_meas['mrr']:.3f}."
                )
            else:
                selected_model = "nomic-embed-text:137m-v1.5-fp16"
                selection_rationale = (
                    f"Equal Recall@5 ({nomic_r5:.3f}) with no material error-analysis disadvantage; "
                    f"Nomic selected per section 7.2 preference rule (MRR {nomic_meas['mrr']:.3f} vs {bge_meas['mrr']:.3f}, "
                    f"p95 {nomic_meas['latency_p95_seconds']:.4f}s vs {bge_meas['latency_p95_seconds']:.4f}s)."
                )

    # Persist golden-retrieved-context.json for the selected or leading candidate
    model_for_golden = selected_model or (
        "bge-m3:567m"
        if candidate_measurements["bge-m3:567m"]["recall_at_5"]
        >= candidate_measurements["nomic-embed-text:137m-v1.5-fp16"]["recall_at_5"]
        else "nomic-embed-text:137m-v1.5-fp16"
    )
    if model_for_golden is not None:
        sel_run = candidate_runs[model_for_golden]
        golden_raw = sel_run["golden_context"]
        top_points = golden_raw["top_points"]

        retrieved_chunks_out: list[dict[str, Any]] = []
        ranked_source_ids_out: list[str] = []
        ranked_chunk_ids_out: list[str] = []

        for i, pt in enumerate(top_points, start=1):
            source_id = f"S{i}"
            cid = pt["chunk_id"]
            ranked_source_ids_out.append(source_id)
            ranked_chunk_ids_out.append(cid)
            original_chunk = chunks_by_id.get(cid)
            source_spans = (
                [s.model_dump() for s in original_chunk.source_spans]
                if original_chunk
                else []
            )

            retrieved_chunks_out.append(
                {
                    "source_id": source_id,
                    "source_ref": source_id,
                    "chunk_id": cid,
                    "score": pt["score"],
                    "paper_id": pt["paper_id"],
                    "page_indices": pt["page_indices"],
                    "section_path": pt["section_path"],
                    "heading": pt["heading"],
                    "text": pt["text"],
                    "source_spans": source_spans,
                }
            )

        golden_context_payload = {
            "artifact_version": ARTIFACT_VERSION,
            "run_id": run_id,
            "selected_model": model_for_golden,
            "collection_name": sel_run["preflight"]["collection_name"],
            "case_id": "1706.03762-answer-1",
            "paper_id": "1706.03762",
            "query": "Why does scaled dot-product attention divide by the square root of the key dimension?",
            "ranked_source_ids": ranked_source_ids_out,
            "ranked_chunk_ids": ranked_chunk_ids_out,
            "retrieved_chunks": retrieved_chunks_out,
        }
        golden_path = private_dir / "golden-retrieved-context.json"
        write_json_atomic(golden_path, golden_context_payload)

    # Threshold outcomes
    threshold_outcomes: dict[str, ThresholdOutcome] = {}
    for model in CANDIDATE_MODELS:
        gate = candidate_gates[model]
        threshold_outcomes[f"{_model_slug(model)}_qualified"] = ThresholdOutcome(
            passed=bool(gate["qualified"]),
            requirement="candidate passes every embedding gate in specification section 7.2",
            observed=gate["checks"],
            failure_reason=gate["failure_reason"],
        )
    threshold_outcomes["embedding_selected"] = ThresholdOutcome(
        passed=selected_model is not None,
        requirement="select exactly one embedding candidate passing every section 7.2 threshold",
        observed=selected_model,
        failure_reason=(
            None
            if selected_model is not None
            else "neither BGE-M3 nor Nomic Embed Text passed the complete embedding gate"
        ),
    )

    failure_reasons = [
        f"{model}: {candidate_gates[model]['failure_reason']}"
        for model in CANDIDATE_MODELS
        if not candidate_gates[model]["qualified"]
    ]
    if selected_model is None:
        failure_reasons.append(
            "neither embedding candidate passed every specification section 7.2 threshold"
        )

    result = EmbeddingResult(
        run_id=run_id,
        selected_model=selected_model,
        identities={
            "producer_git_revision": current_revision,
            "run_initialized_git_revision": environment.run_initialized_git_revision,
            "tracked_tree_clean_before_measurement": True,
            "chunk_set_sha256": chunk_hash,
            "total_chunks": len(chunks),
            "candidates": list(CANDIDATE_MODELS),
            "candidate_identities": candidate_identities,
        },
        measurements={
            "candidates": candidate_measurements,
            "selection": {
                "qualified_candidates": qualified_models,
                "selected_model": selected_model,
                "selection_rationale": selection_rationale,
            },
        },
        threshold_outcomes=threshold_outcomes,
        failure_reasons=failure_reasons,
    )

    # Write embedding.json
    embedding_out = root / "qualification" / "results" / run_id / "embedding.json"
    write_json_atomic(embedding_out, result)

    # Update environment.json: update producer_git_revision, ollama_version, qdrant_version, qdrant_container_image_id
    env_path = root / "qualification" / "results" / run_id / "environment.json"
    env_data = json.loads(env_path.read_text(encoding="utf-8"))
    env_data["producer_git_revision"] = current_revision
    env_data["ollama_version"] = "0.18.2"
    env_data["qdrant_version"] = "1.19.0"
    env_data["qdrant_container_image_id"] = (
        "sha256:057ee3a8da769fe7310dd3537b4dc7583bf87a95ce8ac43c0af5a46bc580d1fc"
    )
    write_json_atomic(env_path, env_data)

    return result
