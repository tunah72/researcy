from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import statistics
import subprocess
import time
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import psutil
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from q0.baseline import (
    EXPECTED_CHUNK_COUNT,
    discover_q01_run_id,
    verify_inherited_artifacts,
)
from q0.models import (
    ARTIFACT_VERSION,
    BASELINE_RUN_ID,
    EXPECTED_CHUNK_SHA256,
    EnvironmentResult,
    EvidenceCase,
    HybridRetrievalResult,
    ThresholdOutcome,
    write_json_atomic,
    write_text_atomic,
)
from q0.retrieval import (
    Chunk,
    VectorValidationError,
    retrieval_metrics,
    validate_vector,
)

MODEL_TAG = "bge-m3:567m"
MODEL_DIGEST = "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
MODEL_DIMENSION = 1024
MODEL_CONTEXT_LENGTH = 8192
MODEL_QUANTIZATION = "F16"
OLLAMA_VERSION = "0.18.2"
QDRANT_VERSION = "1.19.0"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
QDRANT_BASE_URL = "http://127.0.0.1:6333"
BATCH_SIZE = 8
CONCURRENCY = 1
DENSE_LIMIT = 10
BM25_LIMIT = 10
FUSED_LIMIT = 10
FINAL_LIMIT = 5
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60
GOLDEN_CASE_ID = "1706.03762-answer-1"
SELECTED_CONFIGURATION = "bge-m3:567m + BM25(k1=1.5,b=0.75) + RRF(k=60)"
PRIOR_BGE_ARTIFACT = (
    Path("qualification") / "results" / BASELINE_RUN_ID / "embedding.json"
)


class HybridValidationError(ValueError):
    pass


class RankedHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    score: float
    rank: int = Field(ge=1)


class HybridCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    dense_top_10: list[RankedHit]
    bm25_top_10: list[RankedHit]
    fused_top_10: list[RankedHit]
    first_relevant_rank: int | None


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    case_id: str
    paper_id: str
    question: str


@dataclass(frozen=True, slots=True)
class HybridGateEvidence:
    chunk_sha256: str
    vector_checks_passed: bool
    rankings_valid: bool
    rankings_stable: bool
    dense_recall_at_5: float
    fused_recall_at_5: float
    warm_latencies_seconds: tuple[float, ...]
    total_indexing_seconds: float
    golden_case_in_top_5: bool
    golden_provenance_complete: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HybridGateDecision:
    passed: bool
    threshold_outcomes: dict[str, ThresholdOutcome]
    failure_reasons: tuple[str, ...]


class Bm25Index:
    __slots__ = (
        "_average_document_length",
        "_document_frequencies",
        "_documents",
        "_term_frequencies",
        "b",
        "k1",
    )

    def __init__(
        self,
        documents: Sequence[tuple[str, Sequence[str]]],
        *,
        k1: float,
        b: float,
    ) -> None:
        if not documents:
            raise HybridValidationError("BM25 needs at least one document")
        if k1 <= 0:
            raise HybridValidationError("BM25 k1 must be positive")
        if not 0 <= b <= 1:
            raise HybridValidationError("BM25 b must be between zero and one")

        seen: set[str] = set()
        normalized_documents: list[tuple[str, tuple[str, ...]]] = []
        for chunk_id, tokens in documents:
            if chunk_id in seen:
                raise HybridValidationError(f"duplicate chunk ID in BM25 input: {chunk_id}")
            if not chunk_id:
                raise HybridValidationError("BM25 chunk IDs cannot be empty")
            seen.add(chunk_id)
            token_tuple = tuple(tokens)
            if any(not isinstance(token, str) or not token for token in token_tuple):
                raise HybridValidationError(
                    f"BM25 document {chunk_id} contains an invalid token"
                )
            normalized_documents.append((chunk_id, token_tuple))

        normalized_documents.sort(key=lambda item: item[0])
        self._documents = tuple(normalized_documents)
        self.k1 = k1
        self.b = b
        self._term_frequencies = {
            chunk_id: Counter(tokens) for chunk_id, tokens in self._documents
        }
        document_frequencies: Counter[str] = Counter()
        for _, tokens in self._documents:
            document_frequencies.update(set(tokens))
        self._document_frequencies = document_frequencies
        self._average_document_length = sum(
            len(tokens) for _, tokens in self._documents
        ) / len(self._documents)
        if self._average_document_length == 0:
            raise HybridValidationError("BM25 documents cannot all be empty")

    @classmethod
    def from_documents(
        cls,
        documents: Mapping[str, str],
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> Bm25Index:
        tokenized = [
            (chunk_id, tokenize_bm25(text)) for chunk_id, text in documents.items()
        ]
        return cls(tokenized, k1=k1, b=b)

    @classmethod
    def from_tokenized_documents(
        cls,
        documents: Sequence[tuple[str, Sequence[str]]],
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> Bm25Index:
        return cls(documents, k1=k1, b=b)

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def serialized_documents(self) -> list[list[Any]]:
        return [[chunk_id, list(tokens)] for chunk_id, tokens in self._documents]

    def rank(self, query: str, *, limit: int = BM25_LIMIT) -> list[RankedHit]:
        if limit <= 0:
            raise HybridValidationError("BM25 rank limit must be positive")
        query_terms = list(dict.fromkeys(tokenize_bm25(query)))
        document_count = len(self._documents)
        scored: list[tuple[str, float]] = []
        for chunk_id, tokens in self._documents:
            frequencies = self._term_frequencies[chunk_id]
            document_length = len(tokens)
            score = 0.0
            for term in query_terms:
                term_frequency = frequencies.get(term, 0)
                if term_frequency == 0:
                    continue
                document_frequency = self._document_frequencies[term]
                idf = math.log(
                    1
                    + (document_count - document_frequency + 0.5)
                    / (document_frequency + 0.5)
                )
                score += idf * (term_frequency * (self.k1 + 1)) / (
                    term_frequency
                    + self.k1
                    * (
                        1
                        - self.b
                        + self.b
                        * document_length
                        / self._average_document_length
                    )
                )
            scored.append((chunk_id, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            RankedHit(chunk_id=chunk_id, score=score, rank=rank)
            for rank, (chunk_id, score) in enumerate(scored[:limit], start=1)
        ]


def tokenize_bm25(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def _reject_channel_duplicates(channel: str, chunk_ids: Sequence[str]) -> None:
    seen: set[str] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            raise HybridValidationError(f"duplicate {channel} chunk ID: {chunk_id}")
        seen.add(chunk_id)


def reciprocal_rank_fusion(
    *,
    dense_ids: Sequence[str],
    bm25_ids: Sequence[str],
    k: int = RRF_K,
) -> list[RankedHit]:
    if k <= 0:
        raise HybridValidationError("RRF k must be positive")
    _reject_channel_duplicates("dense", dense_ids)
    _reject_channel_duplicates("BM25", bm25_ids)

    dense_ranks = {
        chunk_id: rank
        for rank, chunk_id in enumerate(dense_ids[:DENSE_LIMIT], start=1)
    }
    bm25_ranks = {
        chunk_id: rank
        for rank, chunk_id in enumerate(bm25_ids[:BM25_LIMIT], start=1)
    }
    chunk_ids = set(dense_ranks) | set(bm25_ranks)
    fused_scores = {
        chunk_id: (1 / (k + dense_ranks[chunk_id]) if chunk_id in dense_ranks else 0)
        + (1 / (k + bm25_ranks[chunk_id]) if chunk_id in bm25_ranks else 0)
        for chunk_id in chunk_ids
    }
    missing_rank = DENSE_LIMIT + 1
    ordered = sorted(
        chunk_ids,
        key=lambda chunk_id: (
            -fused_scores[chunk_id],
            dense_ranks.get(chunk_id, missing_rank),
            bm25_ranks.get(chunk_id, missing_rank),
            chunk_id,
        ),
    )[:FUSED_LIMIT]
    return [
        RankedHit(chunk_id=chunk_id, score=fused_scores[chunk_id], rank=rank)
        for rank, chunk_id in enumerate(ordered, start=1)
    ]


def validate_unique_chunk_ids(chunk_ids: Sequence[str]) -> int:
    seen: set[str] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            raise HybridValidationError(f"duplicate chunk ID: {chunk_id}")
        seen.add(chunk_id)
    return len(seen)


def validate_bge_vectors(
    *,
    document_vector: Sequence[float],
    query_vector: Sequence[float],
    repeated_query_vector: Sequence[float],
) -> int:
    try:
        document = validate_vector(document_vector)
        query = validate_vector(query_vector, expected_dimension=len(document))
        repeated = validate_vector(
            repeated_query_vector, expected_dimension=len(document)
        )
    except (TypeError, VectorValidationError) as error:
        raise HybridValidationError(f"invalid BGE vector: {error}") from error
    if query != repeated:
        raise HybridValidationError("repeated BGE query vector is not stable")
    return len(document)


def evaluate_recall_gate(relevant_hits: int, *, total: int) -> ThresholdOutcome:
    if total <= 0:
        raise HybridValidationError("recall total must be positive")
    if not 0 <= relevant_hits <= total:
        raise HybridValidationError("recall hits must be between zero and total")
    recall = relevant_hits / total
    passed = recall >= 0.75
    return ThresholdOutcome(
        passed=passed,
        requirement="Recall@5 is at least 6/8 (0.75)",
        observed={"hits": relevant_hits, "total": total, "recall": recall},
        failure_reason=None if passed else f"observed {relevant_hits}/{total}",
    )


def _inclusive_percentile(values: Sequence[float], percentile: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def _outcome(
    *,
    passed: bool,
    requirement: str,
    observed: Any,
    failure_reason: str,
) -> ThresholdOutcome:
    return ThresholdOutcome(
        passed=passed,
        requirement=requirement,
        observed=observed,
        failure_reason=None if passed else failure_reason,
    )


def evaluate_hybrid_gate(evidence: HybridGateEvidence) -> HybridGateDecision:
    p95 = _inclusive_percentile(evidence.warm_latencies_seconds, 95)
    outcomes = {
        "chunk_identity": _outcome(
            passed=evidence.chunk_sha256 == EXPECTED_CHUNK_SHA256,
            requirement="regenerated 93-chunk SHA-256 matches the inherited identity",
            observed=evidence.chunk_sha256,
            failure_reason="chunk-set SHA-256 changed",
        ),
        "bge_vector_stability": _outcome(
            passed=evidence.vector_checks_passed,
            requirement="BGE vectors are finite, non-zero, stable, dimension-consistent, and untruncated",
            observed=evidence.vector_checks_passed,
            failure_reason="BGE vector validation failed",
        ),
        "ranking_integrity": _outcome(
            passed=evidence.rankings_valid,
            requirement="all eight cases have unique well-formed dense, BM25, and fused top-10 rankings",
            observed=evidence.rankings_valid,
            failure_reason="one or more rankings are malformed",
        ),
        "ranking_stability": _outcome(
            passed=evidence.rankings_stable,
            requirement="all three measured repetitions preserve deterministic channel ordering",
            observed=evidence.rankings_stable,
            failure_reason="retrieval ordering changed across repetitions",
        ),
        "fused_recall_at_5": _outcome(
            passed=evidence.fused_recall_at_5 >= 0.75,
            requirement="fused Recall@5 is at least 0.75 (6/8)",
            observed=evidence.fused_recall_at_5,
            failure_reason="fused Recall@5 is below 0.75",
        ),
        "no_dense_recall_regression": _outcome(
            passed=evidence.fused_recall_at_5 >= evidence.dense_recall_at_5,
            requirement="fused Recall@5 is not below same-run dense Recall@5",
            observed={
                "dense_recall_at_5": evidence.dense_recall_at_5,
                "fused_recall_at_5": evidence.fused_recall_at_5,
            },
            failure_reason="fusion lowered same-run dense Recall@5",
        ),
        "warm_sample_count": _outcome(
            passed=len(evidence.warm_latencies_seconds) == 24,
            requirement="exactly three measured fused repetitions for each of eight questions",
            observed=len(evidence.warm_latencies_seconds),
            failure_reason="warm latency sample count is not 24",
        ),
        "warm_p95_latency": _outcome(
            passed=p95 is not None and p95 < 1.0,
            requirement="fused end-to-end warm p95 latency is below one second",
            observed=p95,
            failure_reason="fused warm p95 is missing or at least one second",
        ),
        "total_indexing_time": _outcome(
            passed=evidence.total_indexing_seconds < 300,
            requirement="total dense plus lexical indexing completes within five minutes",
            observed=evidence.total_indexing_seconds,
            failure_reason="total indexing took at least five minutes",
        ),
        "golden_case": _outcome(
            passed=evidence.golden_case_in_top_5,
            requirement=f"{GOLDEN_CASE_ID} is present in the fused top-5",
            observed=evidence.golden_case_in_top_5,
            failure_reason="golden evidence chunk is absent from the fused top-5",
        ),
        "golden_provenance": _outcome(
            passed=evidence.golden_provenance_complete,
            requirement="every frozen golden top-5 source has complete source-span provenance",
            observed=evidence.golden_provenance_complete,
            failure_reason="golden fused top-5 provenance is incomplete",
        ),
        "no_runtime_failures": _outcome(
            passed=not evidence.failure_reasons,
            requirement="no crash, OOM, identity drift, corpus drift, or provenance loss occurs",
            observed=list(evidence.failure_reasons),
            failure_reason="runtime or identity failures were recorded",
        ),
    }
    reasons = tuple(
        outcome.failure_reason
        for outcome in outcomes.values()
        if not outcome.passed and outcome.failure_reason is not None
    )
    return HybridGateDecision(
        passed=not reasons,
        threshold_outcomes=outcomes,
        failure_reasons=reasons,
    )


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        raise HybridValidationError(
            f"git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout.strip()


def _require_clean_producer(root: Path) -> str:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if status:
        raise HybridValidationError(
            f"tracked tree must be clean before hybrid measurement; status was:\n{status}"
        )
    return _git(root, "rev-parse", "HEAD")


def _load_environment(root: Path, run_id: str) -> EnvironmentResult:
    path = root / "qualification" / "results" / run_id / "environment.json"
    try:
        environment = EnvironmentResult.model_validate_json(path.read_text("utf-8"))
    except FileNotFoundError as error:
        raise HybridValidationError(f"Q0.1 environment not found: {path}") from error
    except (OSError, ValidationError) as error:
        raise HybridValidationError(f"invalid Q0.1 environment {path}: {error}") from error
    if environment.run_id != run_id:
        raise HybridValidationError("environment run ID does not match requested run")
    return environment


def _validate_run(root: Path, run_id: str) -> EnvironmentResult:
    discovered_run_id = discover_q01_run_id(root)
    if run_id != discovered_run_id:
        raise HybridValidationError(
            f"requested run ID {run_id!r} does not match initialized run {discovered_run_id!r}"
        )
    environment = _load_environment(root, run_id)
    inherited_hashes = verify_inherited_artifacts(root)
    if environment.inherited_artifact_sha256 != inherited_hashes:
        raise HybridValidationError("environment inherited artifact identities changed")
    if environment.regenerated_chunk_set_sha256 != EXPECTED_CHUNK_SHA256:
        raise HybridValidationError("environment names the wrong regenerated chunk identity")
    baseline = environment.measurements.get("baseline")
    if not isinstance(baseline, dict) or baseline.get("status") != "prepared":
        raise HybridValidationError("Q0.1 baseline is not prepared")
    return environment


def _private_directory(root: Path, run_id: str) -> Path:
    return root / "qualification" / "private" / run_id


def _private_state_path(root: Path, run_id: str) -> Path:
    return _private_directory(root, run_id) / "hybrid-run.json"


def _load_chunks(root: Path, run_id: str) -> tuple[list[Chunk], str]:
    path = _private_directory(root, run_id) / "chunks.jsonl"
    try:
        encoded = path.read_bytes()
        lines = encoded.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise HybridValidationError(f"cannot read exact private chunks {path}: {error}") from error
    chunk_sha256 = hashlib.sha256(encoded).hexdigest()
    if chunk_sha256 != EXPECTED_CHUNK_SHA256:
        raise HybridValidationError(
            "private chunk-set SHA-256 changed: "
            f"expected {EXPECTED_CHUNK_SHA256}, observed {chunk_sha256}"
        )
    if len(lines) != EXPECTED_CHUNK_COUNT:
        raise HybridValidationError(
            f"expected {EXPECTED_CHUNK_COUNT} chunks, observed {len(lines)}"
        )
    chunks: list[Chunk] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            chunks.append(Chunk.model_validate_json(line))
        except ValidationError as error:
            raise HybridValidationError(
                f"invalid Chunk in {path}:{line_number}: {error}"
            ) from error
    validate_unique_chunk_ids([chunk.chunk_id for chunk in chunks])
    return chunks, chunk_sha256


def _load_question_specs(root: Path) -> list[QuestionSpec]:
    path = root / "qualification" / "gold" / "evidence.jsonl"
    try:
        lines = path.read_text("utf-8").splitlines()
    except OSError as error:
        raise HybridValidationError(f"cannot read frozen evidence cases: {error}") from error
    questions: list[QuestionSpec] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            case = EvidenceCase.model_validate_json(line)
        except ValidationError as error:
            raise HybridValidationError(
                f"invalid evidence case in {path}:{line_number}: {error}"
            ) from error
        if not case.answerable:
            continue
        if not case.question:
            raise HybridValidationError(f"{case.case_id} has no frozen question")
        questions.append(
            QuestionSpec(
                case_id=case.case_id,
                paper_id=case.paper_id,
                question=case.question,
            )
        )
    if len(questions) != 8:
        raise HybridValidationError(
            f"expected eight answerable questions, observed {len(questions)}"
        )
    validate_unique_chunk_ids([question.case_id for question in questions])
    return questions


def _request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    expected_statuses: tuple[int, ...] = (200,),
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        raise HybridValidationError(f"request failed for {url}: {error}") from error
    if response.status_code not in expected_statuses:
        detail = response.text[:500]
        raise HybridValidationError(
            f"{method} {url} returned HTTP {response.status_code}: {detail}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise HybridValidationError(f"{url} did not return JSON") from error
    if not isinstance(payload, dict):
        raise HybridValidationError(f"{url} returned a non-object JSON payload")
    return payload


def _ollama_tags(client: httpx.Client) -> dict[str, dict[str, Any]]:
    payload = _request_json(client, "GET", f"{OLLAMA_BASE_URL}/api/tags")
    models = payload.get("models")
    if not isinstance(models, list):
        raise HybridValidationError("Ollama /api/tags omitted models")
    tags: dict[str, dict[str, Any]] = {}
    for model in models:
        if isinstance(model, dict) and isinstance(model.get("name"), str):
            tags[model["name"]] = model
    return tags


def _embed(
    client: httpx.Client,
    inputs: str | Sequence[str],
    *,
    expected_dimension: int | None = None,
) -> list[list[float]]:
    expected_count = 1 if isinstance(inputs, str) else len(inputs)
    if expected_count == 0:
        raise HybridValidationError("embedding input batch cannot be empty")
    if expected_count > BATCH_SIZE:
        raise HybridValidationError(
            f"embedding batch exceeds fixed batch size {BATCH_SIZE}"
        )
    payload = _request_json(
        client,
        "POST",
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": MODEL_TAG, "input": inputs, "truncate": False},
    )
    vectors = payload.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != expected_count:
        raise HybridValidationError(
            f"Ollama returned {len(vectors) if isinstance(vectors, list) else 'invalid'} vectors for {expected_count} inputs"
        )
    validated: list[list[float]] = []
    for vector in vectors:
        try:
            validated.append(
                validate_vector(vector, expected_dimension=expected_dimension)
            )
        except (TypeError, VectorValidationError) as error:
            raise HybridValidationError(f"invalid Ollama embedding: {error}") from error
    return validated


def _qdrant_identity(client: httpx.Client) -> dict[str, str]:
    try:
        health = client.get(f"{QDRANT_BASE_URL}/healthz")
    except httpx.HTTPError as error:
        raise HybridValidationError(f"Qdrant health request failed: {error}") from error
    if health.status_code != 200 or health.text.strip() != "healthz check passed":
        raise HybridValidationError(
            f"Qdrant health check failed: HTTP {health.status_code} {health.text[:200]}"
        )
    root_payload = _request_json(client, "GET", f"{QDRANT_BASE_URL}/")
    version = root_payload.get("version")
    commit = root_payload.get("commit")
    if version != QDRANT_VERSION:
        raise HybridValidationError(
            f"Qdrant version mismatch: expected {QDRANT_VERSION}, observed {version!r}"
        )
    if not isinstance(commit, str) or not commit:
        raise HybridValidationError("Qdrant root response omitted its commit identity")
    return {"version": version, "commit": commit}


def _qdrant_image_identity(root: Path) -> dict[str, str]:
    compose_directory = root / "experiments" / "q0-1"
    try:
        container = subprocess.run(
            ["docker", "compose", "ps", "-q", "qdrant"],
            cwd=compose_directory,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not container:
            raise HybridValidationError("Qdrant Compose container is not running")
        image_id = subprocess.run(
            ["docker", "inspect", "--format={{.Image}}", container],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        raise HybridValidationError(f"cannot inspect Qdrant container: {detail}") from error
    if not image_id.startswith("sha256:"):
        raise HybridValidationError(
            f"Qdrant container returned an invalid image ID: {image_id!r}"
        )
    return {"container_id": container, "image_id": image_id}


def _collection_name(run_id: str) -> str:
    return f"q0-1-{run_id}-bge-m3-567m"


def _require_new_collection(client: httpx.Client, collection_name: str) -> None:
    try:
        response = client.get(f"{QDRANT_BASE_URL}/collections/{collection_name}")
    except httpx.HTTPError as error:
        raise HybridValidationError(f"Qdrant collection lookup failed: {error}") from error
    if response.status_code == 200:
        raise HybridValidationError(
            f"Qdrant collection already exists; measurement is not new: {collection_name}"
        )
    if response.status_code != 404:
        raise HybridValidationError(
            f"Qdrant collection lookup returned HTTP {response.status_code}: {response.text[:500]}"
        )


def _preflight_identity(
    root: Path,
    client: httpx.Client,
    *,
    collection_name: str,
) -> dict[str, Any]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise HybridValidationError(
            "BGE must run through native Ollama on Darwin arm64"
        )
    version_payload = _request_json(
        client, "GET", f"{OLLAMA_BASE_URL}/api/version"
    )
    ollama_version = version_payload.get("version")
    if ollama_version != OLLAMA_VERSION:
        raise HybridValidationError(
            f"Ollama version mismatch: expected {OLLAMA_VERSION}, observed {ollama_version!r}"
        )
    tags = _ollama_tags(client)
    if MODEL_TAG not in tags:
        raise HybridValidationError(
            f"required exact Ollama model tag is absent: {MODEL_TAG}"
        )
    tag = tags[MODEL_TAG]
    digest = tag.get("digest")
    if digest != MODEL_DIGEST:
        raise HybridValidationError(
            f"BGE digest mismatch: expected {MODEL_DIGEST}, observed {digest!r}"
        )
    show = _request_json(
        client,
        "POST",
        f"{OLLAMA_BASE_URL}/api/show",
        json={"model": MODEL_TAG},
    )
    details = show.get("details")
    model_info = show.get("model_info")
    if not isinstance(details, dict) or not isinstance(model_info, dict):
        raise HybridValidationError("Ollama /api/show omitted model metadata")
    dimension = model_info.get("bert.embedding_length")
    context_length = model_info.get("bert.context_length")
    architecture = model_info.get("general.architecture")
    quantization = details.get("quantization_level")
    if dimension != MODEL_DIMENSION:
        raise HybridValidationError(
            f"BGE dimension mismatch: expected {MODEL_DIMENSION}, observed {dimension!r}"
        )
    if context_length != MODEL_CONTEXT_LENGTH:
        raise HybridValidationError(
            f"BGE context length mismatch: expected {MODEL_CONTEXT_LENGTH}, observed {context_length!r}"
        )
    if architecture != "bert" or quantization != MODEL_QUANTIZATION:
        raise HybridValidationError(
            "BGE architecture or quantization identity changed"
        )

    document_vector = _embed(
        client, "BGE-M3 document vector preflight."
    )[0]
    query_vectors = _embed(
        client,
        [
            "BGE-M3 query vector preflight.",
            "BGE-M3 query vector preflight.",
        ],
        expected_dimension=len(document_vector),
    )
    observed_dimension = validate_bge_vectors(
        document_vector=document_vector,
        query_vector=query_vectors[0],
        repeated_query_vector=query_vectors[1],
    )
    if observed_dimension != MODEL_DIMENSION:
        raise HybridValidationError(
            f"BGE probe dimension changed: expected {MODEL_DIMENSION}, observed {observed_dimension}"
        )

    running_payload = _request_json(client, "GET", f"{OLLAMA_BASE_URL}/api/ps")
    running_models = running_payload.get("models")
    if not isinstance(running_models, list):
        raise HybridValidationError("Ollama /api/ps omitted models")
    running_tags = {
        model.get("name")
        for model in running_models
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    if running_tags != {MODEL_TAG}:
        raise HybridValidationError(
            f"only {MODEL_TAG} may be loaded for Q0.1; observed {sorted(running_tags)}"
        )

    qdrant = _qdrant_identity(client)
    image = _qdrant_image_identity(root)
    _require_new_collection(client, collection_name)
    return {
        "ollama": {
            "version": ollama_version,
            "runtime_placement": f"native ARM64 Ollama {ollama_version}",
            "loaded_models": sorted(running_tags),
        },
        "model": {
            "tag": MODEL_TAG,
            "digest": digest,
            "architecture": architecture,
            "parameter_size": details.get("parameter_size"),
            "quantization": quantization,
            "dimension": observed_dimension,
            "context_length": context_length,
            "document_prefix": "",
            "query_prefix": "",
            "distance_metric": "cosine",
            "truncate": False,
            "batch_size": BATCH_SIZE,
            "concurrency": CONCURRENCY,
        },
        "vector_checks": {
            "document_finite_non_zero": True,
            "query_finite_non_zero": True,
            "dimension_consistent": True,
            "repeated_query_exact_match": True,
            "untruncated": True,
            "passed": True,
        },
        "qdrant": {
            **qdrant,
            **image,
            "collection_name": collection_name,
            "collection_new_before_measurement": True,
            "distance_metric": "cosine",
        },
    }


def run_hybrid_preflight(*, root: Path, run_id: str) -> dict[str, Any]:
    root = root.resolve()
    environment = _validate_run(root, run_id)
    producer_revision = _require_clean_producer(root)
    chunks, chunk_sha256 = _load_chunks(root, run_id)
    collection_name = _collection_name(run_id)
    with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
        preflight = _preflight_identity(
            root, client, collection_name=collection_name
        )
    state = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "stage": "preflight",
        "producer_git_revision": producer_revision,
        "run_initialized_git_revision": environment.run_initialized_git_revision,
        "chunk_set": {
            "count": len(chunks),
            "sha256": chunk_sha256,
            "stream_relative_path": str(
                (_private_directory(root, run_id) / "chunks.jsonl").relative_to(root)
            ),
        },
        "preflight": preflight,
    }
    write_json_atomic(_private_state_path(root, run_id), state)
    return {
        "run_id": run_id,
        "model": MODEL_TAG,
        "model_digest": MODEL_DIGEST,
        "dimension": MODEL_DIMENSION,
        "chunk_count": len(chunks),
        "chunk_set_sha256": chunk_sha256,
        "qdrant_version": preflight["qdrant"]["version"],
        "ollama_version": preflight["ollama"]["version"],
        "collection_name": collection_name,
        "passed": True,
    }


def _load_private_state(root: Path, run_id: str) -> dict[str, Any]:
    path = _private_state_path(root, run_id)
    try:
        payload = json.loads(path.read_text("utf-8"))
    except FileNotFoundError as error:
        raise HybridValidationError(f"hybrid preflight state not found: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise HybridValidationError(f"invalid hybrid private state {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("run_id") != run_id:
        raise HybridValidationError("hybrid private state has the wrong run identity")
    return payload


def _create_collection(
    client: httpx.Client, collection_name: str, dimension: int
) -> None:
    _require_new_collection(client, collection_name)
    payload = _request_json(
        client,
        "PUT",
        f"{QDRANT_BASE_URL}/collections/{collection_name}",
        json={"vectors": {"size": dimension, "distance": "Cosine"}},
    )
    if payload.get("status") != "ok" or payload.get("result") is not True:
        raise HybridValidationError(
            f"Qdrant did not confirm collection creation: {payload}"
        )


def _upsert_batch(
    client: httpx.Client,
    *,
    collection_name: str,
    point_offset: int,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
) -> None:
    if len(chunks) != len(vectors):
        raise HybridValidationError("chunk/vector batch lengths differ")
    points = [
        {
            "id": point_offset + offset,
            "vector": list(vector),
            "payload": {
                "chunk_id": chunk.chunk_id,
                "paper_id": chunk.paper_id,
            },
        }
        for offset, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    payload = _request_json(
        client,
        "PUT",
        f"{QDRANT_BASE_URL}/collections/{collection_name}/points",
        params={"wait": "true"},
        json={"points": points},
    )
    result = payload.get("result")
    if payload.get("status") != "ok" or not isinstance(result, dict):
        raise HybridValidationError(f"Qdrant upsert failed: {payload}")
    if result.get("status") != "completed":
        raise HybridValidationError(f"Qdrant upsert did not complete: {payload}")


def _validate_collection(
    client: httpx.Client, *, collection_name: str, expected_points: int
) -> dict[str, Any]:
    payload = _request_json(
        client, "GET", f"{QDRANT_BASE_URL}/collections/{collection_name}"
    )
    result = payload.get("result")
    if payload.get("status") != "ok" or not isinstance(result, dict):
        raise HybridValidationError("Qdrant collection response is malformed")
    points_count = result.get("points_count")
    config = result.get("config")
    if points_count != expected_points:
        raise HybridValidationError(
            f"Qdrant point count mismatch: expected {expected_points}, observed {points_count!r}"
        )
    if not isinstance(config, dict):
        raise HybridValidationError("Qdrant collection omitted its configuration")
    params = config.get("params")
    vectors = params.get("vectors") if isinstance(params, dict) else None
    if not isinstance(vectors, dict):
        raise HybridValidationError("Qdrant collection omitted vector parameters")
    if vectors.get("size") != MODEL_DIMENSION or vectors.get("distance") != "Cosine":
        raise HybridValidationError("Qdrant collection vector identity changed")
    return {
        "status": result.get("status"),
        "points_count": points_count,
        "indexed_vectors_count": result.get("indexed_vectors_count"),
        "vector_size": vectors.get("size"),
        "distance": vectors.get("distance"),
    }


def _dense_rank(
    client: httpx.Client,
    *,
    collection_name: str,
    vector: Sequence[float],
    known_chunk_ids: set[str],
) -> list[RankedHit]:
    payload = _request_json(
        client,
        "POST",
        f"{QDRANT_BASE_URL}/collections/{collection_name}/points/query",
        json={
            "query": list(vector),
            "limit": DENSE_LIMIT,
            "with_payload": True,
            "with_vector": False,
        },
    )
    result = payload.get("result")
    points = result.get("points") if isinstance(result, dict) else None
    if not isinstance(points, list) or len(points) != DENSE_LIMIT:
        raise HybridValidationError(
            f"Qdrant query returned {len(points) if isinstance(points, list) else 'invalid'} points"
        )
    scored: list[tuple[str, float]] = []
    for point in points:
        if not isinstance(point, dict):
            raise HybridValidationError("Qdrant query returned a malformed point")
        point_payload = point.get("payload")
        chunk_id = point_payload.get("chunk_id") if isinstance(point_payload, dict) else None
        score = point.get("score")
        if (
            not isinstance(chunk_id, str)
            or chunk_id not in known_chunk_ids
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise HybridValidationError("Qdrant query returned an invalid ID or score")
        scored.append((chunk_id, float(score)))
    _reject_channel_duplicates("dense", [chunk_id for chunk_id, _ in scored])
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [
        RankedHit(chunk_id=chunk_id, score=score, rank=rank)
        for rank, (chunk_id, score) in enumerate(scored, start=1)
    ]


def _execute_hybrid_query(
    client: httpx.Client,
    *,
    collection_name: str,
    bm25_index: Bm25Index,
    question: str,
    known_chunk_ids: set[str],
) -> tuple[list[RankedHit], list[RankedHit], list[RankedHit], float]:
    started = time.perf_counter()
    query_vector = _embed(
        client, question, expected_dimension=MODEL_DIMENSION
    )[0]
    dense_hits = _dense_rank(
        client,
        collection_name=collection_name,
        vector=query_vector,
        known_chunk_ids=known_chunk_ids,
    )
    bm25_hits = bm25_index.rank(question, limit=BM25_LIMIT)
    fused_hits = reciprocal_rank_fusion(
        dense_ids=[hit.chunk_id for hit in dense_hits],
        bm25_ids=[hit.chunk_id for hit in bm25_hits],
        k=RRF_K,
    )
    latency = time.perf_counter() - started
    return dense_hits, bm25_hits, fused_hits, latency


def _normalized_relevance_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _relevant_chunks_by_case(
    root: Path, chunks: Sequence[Chunk]
) -> dict[str, set[str]]:
    path = root / "qualification" / "gold" / "evidence.jsonl"
    cases = [
        EvidenceCase.model_validate_json(line)
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    normalized_chunks = {
        chunk.chunk_id: _normalized_relevance_text(chunk.text) for chunk in chunks
    }
    relevant: dict[str, set[str]] = {}
    for case in cases:
        if not case.answerable:
            continue
        normalized_quotes = [
            _normalized_relevance_text(quote) for quote in case.quotes
        ]
        matches = {
            chunk.chunk_id
            for chunk in chunks
            if chunk.paper_id == case.paper_id
            and any(
                quote and quote in normalized_chunks[chunk.chunk_id]
                for quote in normalized_quotes
            )
        }
        if not matches:
            raise HybridValidationError(
                f"gold quote for {case.case_id} does not resolve to any frozen chunk"
            )
        relevant[case.case_id] = matches
    if len(relevant) != 8:
        raise HybridValidationError(
            f"expected relevance sets for eight cases, observed {len(relevant)}"
        )
    return relevant


def _first_relevant_rank(
    hits: Sequence[RankedHit], relevant_chunk_ids: set[str]
) -> int | None:
    return next(
        (hit.rank for hit in hits if hit.chunk_id in relevant_chunk_ids),
        None,
    )


def _ranking_ids(result: tuple[list[RankedHit], list[RankedHit], list[RankedHit], float]) -> tuple[tuple[str, ...], ...]:
    dense, bm25, fused, _ = result
    return (
        tuple(hit.chunk_id for hit in dense),
        tuple(hit.chunk_id for hit in bm25),
        tuple(hit.chunk_id for hit in fused),
    )


def _serialize_bm25_index(index: Bm25Index) -> str:
    return (
        json.dumps(
            index.serialized_documents(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def _metrics_payload(
    rankings: Sequence[Sequence[str]], relevant: Sequence[set[str]]
) -> dict[str, Any]:
    metrics = retrieval_metrics(rankings, relevant, k_values=(1, 5))
    return asdict(metrics)


def _prior_rank_six_cases(root: Path) -> set[str]:
    path = root / PRIOR_BGE_ARTIFACT
    try:
        payload = json.loads(path.read_text("utf-8"))
        candidates = payload["measurements"]["candidates"]
        cases = candidates[MODEL_TAG]["cases"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise HybridValidationError(
            f"cannot read inherited BGE rank-6 cases from {path}: {error}"
        ) from error
    rank_six = {
        case["case_id"]
        for case in cases
        if isinstance(case, dict) and case.get("first_relevant_rank") == 6
    }
    if len(rank_six) != 3:
        raise HybridValidationError(
            f"expected three inherited BGE rank-6 cases, observed {len(rank_six)}"
        )
    return rank_six


def _build_error_analysis(
    root: Path,
    cases: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    prior_rank_six = _prior_rank_six_cases(root)
    analysis: list[dict[str, Any]] = []
    for case in cases:
        fused_rank = case["first_relevant_rank"]
        missed = fused_rank is None or fused_rank > FINAL_LIMIT
        inherited_rank_six = case["case_id"] in prior_rank_six
        if not missed and not inherited_rank_six:
            continue
        analysis.append(
            {
                "case_id": case["case_id"],
                "inherited_bge_first_relevant_rank": 6 if inherited_rank_six else None,
                "same_run_dense_first_relevant_rank": case[
                    "dense_first_relevant_rank"
                ],
                "bm25_first_relevant_rank": case["bm25_first_relevant_rank"],
                "fused_first_relevant_rank": fused_rank,
                "fused_top_5_miss": missed,
                "relevant_chunk_ids": case["relevant_chunk_ids"],
                "observation": (
                    "relevant evidence remained outside the fused top-5"
                    if missed
                    else "fixed lexical fusion recovered the prior dense rank-6 case into the fused top-5"
                ),
            }
        )
    analyzed_prior = {
        item["case_id"] for item in analysis if item["inherited_bge_first_relevant_rank"] == 6
    }
    if analyzed_prior != prior_rank_six:
        raise HybridValidationError("error analysis omitted an inherited BGE rank-6 case")
    return analysis


def _write_golden_context(
    root: Path,
    run_id: str,
    *,
    chunks_by_id: Mapping[str, Chunk],
    golden_case: dict[str, Any],
    chunk_sha256: str,
    collection_name: str,
    producer_revision: str,
) -> tuple[dict[str, Any], str]:
    dense_by_id = {
        hit["chunk_id"]: hit for hit in golden_case["dense_top_10"]
    }
    bm25_by_id = {
        hit["chunk_id"]: hit for hit in golden_case["bm25_top_10"]
    }
    sources: list[dict[str, Any]] = []
    for fused in golden_case["fused_top_10"][:FINAL_LIMIT]:
        chunk = chunks_by_id[fused["chunk_id"]]
        dense = dense_by_id.get(chunk.chunk_id)
        bm25 = bm25_by_id.get(chunk.chunk_id)
        sources.append(
            {
                "source_ref": f"S{len(sources) + 1}",
                "chunk_id": chunk.chunk_id,
                "paper_id": chunk.paper_id,
                "section_path": chunk.section_path,
                "heading": chunk.heading,
                "page_indices": chunk.page_indices,
                "block_indices": chunk.block_indices,
                "text": chunk.text,
                "source_spans": [
                    span.model_dump(mode="json") for span in chunk.source_spans
                ],
                "dense_rank": dense["rank"] if dense is not None else None,
                "dense_score": dense["score"] if dense is not None else None,
                "bm25_rank": bm25["rank"] if bm25 is not None else None,
                "bm25_score": bm25["score"] if bm25 is not None else None,
                "fused_rank": fused["rank"],
                "fused_score": fused["score"],
            }
        )
    payload = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "producer_git_revision": producer_revision,
        "configuration": SELECTED_CONFIGURATION,
        "collection_name": collection_name,
        "chunk_set_sha256": chunk_sha256,
        "case_id": golden_case["case_id"],
        "paper_id": golden_case["paper_id"],
        "question": golden_case["question"],
        "sources": sources,
    }
    path = _private_directory(root, run_id) / "golden-retrieved-context.json"
    write_json_atomic(path, payload)
    return payload, hashlib.sha256(path.read_bytes()).hexdigest()


def run_hybrid_measurement(*, root: Path, run_id: str) -> dict[str, Any]:
    root = root.resolve()
    _validate_run(root, run_id)
    producer_revision = _require_clean_producer(root)
    state = _load_private_state(root, run_id)
    if state.get("stage") != "preflight":
        raise HybridValidationError("hybrid preflight must complete exactly before run")
    if state.get("producer_git_revision") != producer_revision:
        raise HybridValidationError("hybrid preflight producer revision changed")
    preflight = state.get("preflight")
    if not isinstance(preflight, dict):
        raise HybridValidationError("hybrid preflight evidence is missing")

    chunks, chunk_sha256 = _load_chunks(root, run_id)
    questions = _load_question_specs(root)
    known_chunk_ids = {chunk.chunk_id for chunk in chunks}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    process = psutil.Process()
    peak_memory_bytes = process.memory_info().rss

    lexical_started = time.perf_counter()
    bm25_index = Bm25Index.from_documents(
        {chunk.chunk_id: chunk.text for chunk in chunks},
        k1=BM25_K1,
        b=BM25_B,
    )
    bm25_text = _serialize_bm25_index(bm25_index)
    bm25_path = _private_directory(root, run_id) / "bm25-index.json"
    write_text_atomic(bm25_path, bm25_text)
    bm25_sha256 = hashlib.sha256(bm25_path.read_bytes()).hexdigest()
    lexical_indexing_seconds = time.perf_counter() - lexical_started
    peak_memory_bytes = max(peak_memory_bytes, process.memory_info().rss)

    collection_name = preflight.get("qdrant", {}).get("collection_name")
    if collection_name != _collection_name(run_id):
        raise HybridValidationError("preflight Qdrant collection identity changed")

    document_batch_sizes: list[int] = []
    dense_started = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
        current_identity = _preflight_runtime_without_vector_probe(client)
        if current_identity["ollama_version"] != preflight["ollama"]["version"]:
            raise HybridValidationError("Ollama identity drifted after preflight")
        if current_identity["qdrant_version"] != preflight["qdrant"]["version"]:
            raise HybridValidationError("Qdrant identity drifted after preflight")
        _create_collection(client, collection_name, MODEL_DIMENSION)
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            document_batch_sizes.append(len(batch))
            vectors = _embed(
                client,
                [chunk.text for chunk in batch],
                expected_dimension=MODEL_DIMENSION,
            )
            _upsert_batch(
                client,
                collection_name=collection_name,
                point_offset=start,
                chunks=batch,
                vectors=vectors,
            )
            peak_memory_bytes = max(peak_memory_bytes, process.memory_info().rss)
        collection = _validate_collection(
            client,
            collection_name=collection_name,
            expected_points=len(chunks),
        )
        dense_indexing_seconds = time.perf_counter() - dense_started

        _execute_hybrid_query(
            client,
            collection_name=collection_name,
            bm25_index=bm25_index,
            question=questions[0].question,
            known_chunk_ids=known_chunk_ids,
        )
        peak_memory_bytes = max(peak_memory_bytes, process.memory_info().rss)

        raw_rankings: dict[
            str, tuple[list[RankedHit], list[RankedHit], list[RankedHit], float]
        ] = {}
        latency_samples: list[dict[str, Any]] = []
        rankings_stable = True
        for question in questions:
            reference_ids: tuple[tuple[str, ...], ...] | None = None
            for repetition in range(1, 4):
                result = _execute_hybrid_query(
                    client,
                    collection_name=collection_name,
                    bm25_index=bm25_index,
                    question=question.question,
                    known_chunk_ids=known_chunk_ids,
                )
                current_ids = _ranking_ids(result)
                if reference_ids is None:
                    reference_ids = current_ids
                    raw_rankings[question.case_id] = result
                elif current_ids != reference_ids:
                    rankings_stable = False
                latency_samples.append(
                    {
                        "case_id": question.case_id,
                        "repetition": repetition,
                        "seconds": result[3],
                    }
                )
                peak_memory_bytes = max(
                    peak_memory_bytes, process.memory_info().rss
                )

    if len(latency_samples) != 24:
        raise HybridValidationError(
            f"expected exactly 24 measured queries, observed {len(latency_samples)}"
        )

    # Gold quotes enter only here, after all independent channel rankings are complete.
    relevant_by_case = _relevant_chunks_by_case(root, chunks)
    case_payloads: list[dict[str, Any]] = []
    for question in questions:
        dense_hits, bm25_hits, fused_hits, _ = raw_rankings[question.case_id]
        relevant = relevant_by_case[question.case_id]
        case_model = HybridCaseResult(
            case_id=question.case_id,
            dense_top_10=dense_hits,
            bm25_top_10=bm25_hits,
            fused_top_10=fused_hits,
            first_relevant_rank=_first_relevant_rank(fused_hits, relevant),
        )
        case_payloads.append(
            {
                **case_model.model_dump(mode="json"),
                "paper_id": question.paper_id,
                "question": question.question,
                "relevant_chunk_ids": sorted(relevant),
                "dense_first_relevant_rank": _first_relevant_rank(
                    dense_hits, relevant
                ),
                "bm25_first_relevant_rank": _first_relevant_rank(
                    bm25_hits, relevant
                ),
            }
        )

    relevant_sets = [relevant_by_case[question.case_id] for question in questions]
    dense_metrics = _metrics_payload(
        [
            [hit["chunk_id"] for hit in case["dense_top_10"]]
            for case in case_payloads
        ],
        relevant_sets,
    )
    bm25_metrics = _metrics_payload(
        [
            [hit["chunk_id"] for hit in case["bm25_top_10"]]
            for case in case_payloads
        ],
        relevant_sets,
    )
    fused_metrics = _metrics_payload(
        [
            [hit["chunk_id"] for hit in case["fused_top_10"]]
            for case in case_payloads
        ],
        relevant_sets,
    )
    error_analysis = _build_error_analysis(root, case_payloads)
    golden_case = next(
        case for case in case_payloads if case["case_id"] == GOLDEN_CASE_ID
    )
    golden_payload, golden_sha256 = _write_golden_context(
        root,
        run_id,
        chunks_by_id=chunks_by_id,
        golden_case=golden_case,
        chunk_sha256=chunk_sha256,
        collection_name=collection_name,
        producer_revision=producer_revision,
    )
    golden_source_ids = [source["chunk_id"] for source in golden_payload["sources"]]
    golden_provenance_complete = (
        len(golden_payload["sources"]) == FINAL_LIMIT
        and all(source["text"] for source in golden_payload["sources"])
        and all(source["source_spans"] for source in golden_payload["sources"])
        and len(set(golden_source_ids)) == FINAL_LIMIT
    )
    golden_relevant = set(golden_case["relevant_chunk_ids"])
    golden_case_in_top_5 = bool(golden_relevant.intersection(golden_source_ids))
    latencies = [sample["seconds"] for sample in latency_samples]
    total_indexing_seconds = dense_indexing_seconds + lexical_indexing_seconds
    failures = [] if rankings_stable else ["rankings changed across measured repetitions"]

    measurement = {
        "chunk_set": {
            "count": len(chunks),
            "sha256": chunk_sha256,
        },
        "bm25": {
            "tokenizer": "Unicode NFKC + casefold + maximal Unicode alphanumeric runs",
            "formula": "ln(1 + (N - df + 0.5) / (df + 0.5)) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))",
            "query_term_frequency": "deduplicated in first-occurrence order",
            "k1": BM25_K1,
            "b": BM25_B,
            "document_count": bm25_index.document_count,
            "index_relative_path": str(bm25_path.relative_to(root)),
            "index_sha256": bm25_sha256,
        },
        "rrf": {
            "k": RRF_K,
            "dense_limit": DENSE_LIMIT,
            "bm25_limit": BM25_LIMIT,
            "fused_limit": FUSED_LIMIT,
            "final_limit": FINAL_LIMIT,
            "one_based_ranks": True,
            "tie_break": [
                "fused_score_desc",
                "dense_rank_asc",
                "bm25_rank_asc",
                "chunk_id_asc",
            ],
        },
        "collection": collection,
        "document_embedding_batches": document_batch_sizes,
        "warm_up": {
            "measured": False,
            "case_id": questions[0].case_id,
            "completed": True,
        },
        "latency": {
            "scope": "query embedding + Qdrant dense top-10 + in-process BM25 top-10 + RRF",
            "percentile_method": "statistics.quantiles inclusive",
            "samples": latency_samples,
            "sample_count": len(latency_samples),
            "p50_seconds": statistics.median(latencies),
            "p95_seconds": _inclusive_percentile(latencies, 95),
        },
        "indexing": {
            "dense_seconds": dense_indexing_seconds,
            "lexical_seconds": lexical_indexing_seconds,
            "total_seconds": total_indexing_seconds,
        },
        "peak_memory": {
            "bytes": peak_memory_bytes,
            "scope": "probe process RSS sampled at each index/query batch boundary",
        },
        "channel_metrics": {
            "dense": dense_metrics,
            "bm25": bm25_metrics,
            "fused": fused_metrics,
        },
        "cases": case_payloads,
        "rankings_stable": rankings_stable,
        "error_analysis": error_analysis,
        "golden_context": {
            "case_id": GOLDEN_CASE_ID,
            "relative_path": str(
                (
                    _private_directory(root, run_id)
                    / "golden-retrieved-context.json"
                ).relative_to(root)
            ),
            "sha256": golden_sha256,
            "source_ids": golden_source_ids,
            "case_in_top_5": golden_case_in_top_5,
            "provenance_complete": golden_provenance_complete,
        },
        "failures": failures,
    }
    measured_state = {
        **state,
        "stage": "measured",
        "measurement": measurement,
    }
    write_json_atomic(_private_state_path(root, run_id), measured_state)
    return {
        "run_id": run_id,
        "chunk_set_sha256": chunk_sha256,
        "collection_name": collection_name,
        "case_count": len(case_payloads),
        "warm_sample_count": len(latency_samples),
        "dense_recall_at_5": dense_metrics["recall_at_5"],
        "bm25_recall_at_5": bm25_metrics["recall_at_5"],
        "fused_recall_at_5": fused_metrics["recall_at_5"],
        "p95_seconds": measurement["latency"]["p95_seconds"],
        "total_indexing_seconds": total_indexing_seconds,
        "peak_memory_bytes": peak_memory_bytes,
        "golden_case_in_top_5": golden_case_in_top_5,
    }


def _preflight_runtime_without_vector_probe(
    client: httpx.Client,
) -> dict[str, str]:
    ollama = _request_json(client, "GET", f"{OLLAMA_BASE_URL}/api/version")
    tags = _ollama_tags(client)
    model = tags.get(MODEL_TAG)
    if ollama.get("version") != OLLAMA_VERSION:
        raise HybridValidationError("Ollama identity drifted after preflight")
    if not isinstance(model, dict) or model.get("digest") != MODEL_DIGEST:
        raise HybridValidationError("BGE tag or digest drifted after preflight")
    qdrant = _qdrant_identity(client)
    return {
        "ollama_version": ollama["version"],
        "model_digest": model["digest"],
        "qdrant_version": qdrant["version"],
        "qdrant_commit": qdrant["commit"],
    }


def _validate_ranked_hits(value: Any, channel: str) -> bool:
    if not isinstance(value, list) or len(value) != 10:
        return False
    try:
        hits = [RankedHit.model_validate(hit) for hit in value]
    except ValidationError:
        return False
    if [hit.rank for hit in hits] != list(range(1, 11)):
        return False
    if len({hit.chunk_id for hit in hits}) != 10:
        return False
    if any(not math.isfinite(hit.score) for hit in hits):
        return False
    if channel == "fused" and any(hit.score <= 0 for hit in hits):
        return False
    return True


def _validate_measurement_artifacts(
    root: Path,
    run_id: str,
    measurement: dict[str, Any],
) -> tuple[bool, bool, bool, list[str]]:
    failures: list[str] = []
    cases = measurement.get("cases")
    rankings_valid = isinstance(cases, list) and len(cases) == 8
    if rankings_valid:
        case_ids: set[str] = set()
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
                rankings_valid = False
                break
            case_ids.add(case["case_id"])
            rankings_valid = rankings_valid and all(
                _validate_ranked_hits(case.get(key), channel)
                for key, channel in (
                    ("dense_top_10", "dense"),
                    ("bm25_top_10", "bm25"),
                    ("fused_top_10", "fused"),
                )
            )
        rankings_valid = rankings_valid and len(case_ids) == 8
    if not rankings_valid:
        failures.append("durable channel rankings are incomplete or malformed")

    bm25 = measurement.get("bm25")
    if not isinstance(bm25, dict):
        failures.append("BM25 measurement identity is missing")
    else:
        path = root / str(bm25.get("index_relative_path", ""))
        try:
            observed = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            observed = None
        if observed != bm25.get("index_sha256"):
            failures.append("BM25 private index hash changed")

    golden = measurement.get("golden_context")
    golden_case_in_top_5 = False
    golden_provenance_complete = False
    if isinstance(golden, dict):
        path = root / str(golden.get("relative_path", ""))
        try:
            encoded = path.read_bytes()
            payload = json.loads(encoded)
        except (OSError, json.JSONDecodeError):
            payload = None
            encoded = b""
        if hashlib.sha256(encoded).hexdigest() != golden.get("sha256"):
            failures.append("golden private context hash changed")
        elif isinstance(payload, dict):
            sources = payload.get("sources")
            if isinstance(sources, list) and len(sources) == FINAL_LIMIT:
                source_ids = [source.get("chunk_id") for source in sources]
                golden_provenance_complete = (
                    len(set(source_ids)) == FINAL_LIMIT
                    and all(source.get("text") for source in sources)
                    and all(source.get("source_spans") for source in sources)
                    and all(source.get("fused_rank") == index for index, source in enumerate(sources, start=1))
                )
                golden_case = next(
                    (
                        case
                        for case in cases or []
                        if isinstance(case, dict)
                        and case.get("case_id") == GOLDEN_CASE_ID
                    ),
                    None,
                )
                if isinstance(golden_case, dict):
                    relevant = set(golden_case.get("relevant_chunk_ids", []))
                    golden_case_in_top_5 = bool(relevant.intersection(source_ids))
    if not golden_provenance_complete:
        failures.append("golden private context provenance is incomplete")
    if not golden_case_in_top_5:
        failures.append("golden case evidence is absent from fused top-5")
    return (
        rankings_valid,
        golden_case_in_top_5,
        golden_provenance_complete,
        failures,
    )


def evaluate_hybrid_measurement(*, root: Path, run_id: str) -> dict[str, Any]:
    root = root.resolve()
    environment = _validate_run(root, run_id)
    producer_revision = _require_clean_producer(root)
    state = _load_private_state(root, run_id)
    if state.get("stage") != "measured":
        raise HybridValidationError("hybrid run must complete before evaluation")
    if state.get("producer_git_revision") != producer_revision:
        raise HybridValidationError("measurement producer revision changed")
    preflight = state.get("preflight")
    measurement = state.get("measurement")
    if not isinstance(preflight, dict) or not isinstance(measurement, dict):
        raise HybridValidationError("hybrid private measurement is incomplete")

    chunks_path = _private_directory(root, run_id) / "chunks.jsonl"
    try:
        current_chunk_sha256 = hashlib.sha256(chunks_path.read_bytes()).hexdigest()
    except OSError as error:
        raise HybridValidationError(f"cannot revalidate private chunks: {error}") from error
    stored_chunk = measurement.get("chunk_set")
    stored_chunk_sha256 = (
        stored_chunk.get("sha256") if isinstance(stored_chunk, dict) else None
    )
    artifact_failures: list[str] = []
    if current_chunk_sha256 != stored_chunk_sha256:
        artifact_failures.append("private chunk stream changed after measurement")

    (
        rankings_valid,
        golden_case_in_top_5,
        golden_provenance_complete,
        validation_failures,
    ) = _validate_measurement_artifacts(root, run_id, measurement)
    artifact_failures.extend(validation_failures)

    latency = measurement.get("latency")
    samples = latency.get("samples") if isinstance(latency, dict) else None
    warm_latencies: tuple[float, ...] = ()
    if isinstance(samples, list):
        try:
            warm_latencies = tuple(float(sample["seconds"]) for sample in samples)
        except (KeyError, TypeError, ValueError):
            artifact_failures.append("warm latency samples are malformed")
            warm_latencies = ()
    metrics = measurement.get("channel_metrics")
    if not isinstance(metrics, dict):
        raise HybridValidationError("channel metrics are missing")
    dense_metrics = metrics.get("dense")
    fused_metrics = metrics.get("fused")
    if not isinstance(dense_metrics, dict) or not isinstance(fused_metrics, dict):
        raise HybridValidationError("dense or fused metrics are missing")
    indexing = measurement.get("indexing")
    if not isinstance(indexing, dict):
        raise HybridValidationError("indexing metrics are missing")
    vector_checks = preflight.get("vector_checks")
    vector_checks_passed = (
        isinstance(vector_checks, dict)
        and vector_checks.get("passed") is True
        and preflight.get("model", {}).get("dimension") == MODEL_DIMENSION
        and preflight.get("model", {}).get("truncate") is False
    )
    runtime_failures = measurement.get("failures")
    failures = [
        *(
            runtime_failures
            if isinstance(runtime_failures, list)
            else ["measurement failures field is malformed"]
        ),
        *artifact_failures,
    ]
    evidence = HybridGateEvidence(
        chunk_sha256=current_chunk_sha256,
        vector_checks_passed=vector_checks_passed,
        rankings_valid=rankings_valid,
        rankings_stable=measurement.get("rankings_stable") is True,
        dense_recall_at_5=float(dense_metrics["recall_at_5"]),
        fused_recall_at_5=float(fused_metrics["recall_at_5"]),
        warm_latencies_seconds=warm_latencies,
        total_indexing_seconds=float(indexing["total_seconds"]),
        golden_case_in_top_5=golden_case_in_top_5,
        golden_provenance_complete=golden_provenance_complete,
        failure_reasons=tuple(failures),
    )
    decision = evaluate_hybrid_gate(evidence)

    result = HybridRetrievalResult(
        run_id=run_id,
        identities={
            "producer_git_revision": producer_revision,
            "run_initialized_git_revision": environment.run_initialized_git_revision,
            "baseline_run_id": environment.baseline_run_id,
            "inherited_artifact_sha256": environment.inherited_artifact_sha256,
            "regenerated_parser": environment.measurements["baseline"]["parser"],
            "regenerated_chunk_set_sha256": current_chunk_sha256,
            "total_chunks": EXPECTED_CHUNK_COUNT,
            "model": preflight["model"],
            "ollama": preflight["ollama"],
            "qdrant": preflight["qdrant"],
            "tracked_tree_clean_before_measurement": True,
        },
        measurements={
            "configuration_under_test": SELECTED_CONFIGURATION,
            "gold_used_only_after_ranking": True,
            **measurement,
        },
        threshold_outcomes=decision.threshold_outcomes,
        failure_reasons=list(decision.failure_reasons),
        selected_configuration=(
            SELECTED_CONFIGURATION if decision.passed else None
        ),
    )
    result_path = (
        root
        / "qualification"
        / "results"
        / run_id
        / "hybrid-retrieval.json"
    )
    write_json_atomic(result_path, result)

    environment_hybrid_summary = {
        "status": "qualified" if decision.passed else "failed",
        "result_relative_path": str(result_path.relative_to(root)),
        "selected_configuration": result.selected_configuration,
        "chunk_set_sha256": current_chunk_sha256,
        "collection_name": preflight["qdrant"]["collection_name"],
        "warm_sample_count": len(warm_latencies),
        "fused_recall_at_5": evidence.fused_recall_at_5,
        "p95_seconds": _inclusive_percentile(warm_latencies, 95),
    }
    updated_environment = environment.model_copy(
        update={
            "producer_git_revision": producer_revision,
            "ollama_version": preflight["ollama"]["version"],
            "qdrant_version": preflight["qdrant"]["version"],
            "qdrant_container_image_id": preflight["qdrant"]["image_id"],
            "identities": {
                **environment.identities,
                "producer_git_revision": producer_revision,
                "hybrid_retrieval": {
                    "model": MODEL_TAG,
                    "model_digest": MODEL_DIGEST,
                    "collection_name": preflight["qdrant"]["collection_name"],
                    "configuration": SELECTED_CONFIGURATION,
                },
            },
            "measurements": {
                **environment.measurements,
                "hybrid_retrieval": environment_hybrid_summary,
            },
            "threshold_outcomes": {
                **environment.threshold_outcomes,
                **{
                    f"hybrid_{name}": outcome
                    for name, outcome in decision.threshold_outcomes.items()
                },
            },
            "failure_reasons": [
                *environment.failure_reasons,
                *decision.failure_reasons,
            ],
        }
    )
    environment_path = (
        root / "qualification" / "results" / run_id / "environment.json"
    )
    write_json_atomic(environment_path, updated_environment)
    return {
        "run_id": run_id,
        "passed": decision.passed,
        "selected_configuration": result.selected_configuration,
        "failure_reasons": list(decision.failure_reasons),
        "dense_recall_at_5": evidence.dense_recall_at_5,
        "fused_recall_at_5": evidence.fused_recall_at_5,
        "warm_sample_count": len(warm_latencies),
        "p50_seconds": statistics.median(warm_latencies) if warm_latencies else None,
        "p95_seconds": _inclusive_percentile(warm_latencies, 95),
        "total_indexing_seconds": evidence.total_indexing_seconds,
    }
