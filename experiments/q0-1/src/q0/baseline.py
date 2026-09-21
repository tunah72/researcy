from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import psutil
from pydantic import BaseModel, ValidationError

from q0.corpus import fetch_corpus, validate_gold
from q0.models import (
    BASELINE_RUN_ID,
    EXPECTED_CHUNK_SHA256,
    EnvironmentResult,
    ParsedBlock,
    ThresholdOutcome,
    write_json_atomic,
    write_text_atomic,
)
from q0.parsers import parse_pymupdf, validate_block_provenance
from q0.retrieval import Chunk, build_chunks

EXPECTED_CHUNK_COUNT = 93
EXPECTED_PYMUPDF_VERSION = "1.28.2"
Q01_RUN_ID_PATTERN = re.compile(r"q0-1-\d{8}T\d{6}Z-[0-9a-f]{7}")

INHERITED_ARTIFACT_SHA256: dict[str, str] = {
    "qualification/corpus/manifest.json": "50e221e0a441607306ba0a6eb9adf517793660c720ca2f5facb41bf5f442b8f9",
    "qualification/gold/evidence.jsonl": "858d2547c8dd515eaaad35e8dd73a1597a0dfa9147658128f159d7dab2d820bd",
    "qualification/gold/reading-order.jsonl": "d1346420ee29220ebc6cb308fbcfb36a6b6cb680d49a9e01639e642ca3d647bb",
    f"qualification/results/{BASELINE_RUN_ID}/environment.json": "fbb995829a87a7eb8172fd0899de6280b2f597fbd9aa2ea9fe2906856eb4b93f",
    f"qualification/results/{BASELINE_RUN_ID}/parser.json": "820fb2a71f075570bf89872cf468b4ac23e18c373009e06de109b8086c096c61",
    f"qualification/results/{BASELINE_RUN_ID}/embedding.json": "28536767095569d87f136fe848f9842a310deb649eb08b588ede156fd5c714c1",
}


class BaselineValidationError(ValueError):
    pass


def verify_file_hash(path: Path, expected: str) -> str:
    try:
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise BaselineValidationError(f"cannot read inherited artifact {path}: {error}") from error
    if observed != expected:
        raise BaselineValidationError(
            f"inherited artifact SHA-256 mismatch for {path}: expected {expected}, observed {observed}"
        )
    return observed


def verify_inherited_artifacts(root: Path) -> dict[str, str]:
    root = root.resolve()
    return {
        relative_path: verify_file_hash(root / relative_path, expected)
        for relative_path, expected in INHERITED_ARTIFACT_SHA256.items()
    }


def require_chunk_identity(*, observed: str) -> None:
    if observed != EXPECTED_CHUNK_SHA256:
        raise BaselineValidationError(
            "regenerated chunk-set SHA-256 mismatch: "
            f"expected {EXPECTED_CHUNK_SHA256}, observed {observed}"
        )


def _q01_environment_paths(root: Path) -> list[Path]:
    results = root.resolve() / "qualification" / "results"
    return sorted(results.glob("q0-1-*/environment.json")) if results.exists() else []


def discover_q01_run_id(root: Path) -> str:
    root = root.resolve()
    environments = _q01_environment_paths(root)
    if len(environments) != 1:
        raise BaselineValidationError(
            f"expected exactly one Q0.1 environment, observed {len(environments)}"
        )

    environment_path = environments[0]
    candidate = environment_path.parent.name
    if Q01_RUN_ID_PATTERN.fullmatch(candidate) is None:
        raise BaselineValidationError(f"invalid Q0.1 run directory name: {candidate}")
    try:
        payload = json.loads(environment_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineValidationError(
            f"invalid Q0.1 environment {environment_path}: {error}"
        ) from error
    if not isinstance(payload, dict) or payload.get("run_id") != candidate:
        raise BaselineValidationError(
            f"Q0.1 environment run ID does not match directory {candidate}"
        )

    private_path = root / "qualification" / "private" / "q0-1-run-id.txt"
    if private_path.is_file():
        try:
            private_run_id = private_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise BaselineValidationError(
                f"cannot read private Q0.1 run ID {private_path}: {error}"
            ) from error
        if private_run_id != candidate:
            raise BaselineValidationError(
                f"private Q0.1 run ID {private_run_id!r} does not match environment run ID {candidate!r}"
            )
    return candidate


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
        raise BaselineValidationError(
            f"git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout.strip()


def _require_clean_producer(root: Path) -> str:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if status:
        raise BaselineValidationError(
            f"tracked tree must be clean before baseline work; status was:\n{status}"
        )
    return _git(root, "rev-parse", "HEAD")


def _os_version() -> str:
    macos_version = platform.mac_ver()[0]
    return f"macOS {macos_version}" if macos_version else platform.platform()


def initialize_run(root: Path) -> str:
    root = root.resolve()
    existing = _q01_environment_paths(root)
    if len(existing) > 1:
        raise BaselineValidationError(
            f"more than one Q0.1 environment exists: {', '.join(map(str, existing))}"
        )
    if existing:
        raise BaselineValidationError(f"a Q0.1 run is already initialized: {existing[0]}")

    revision = _require_clean_producer(root)
    inherited_hashes = verify_inherited_artifacts(root)
    initialized_at = datetime.now(timezone.utc)
    run_id = f"q0-1-{initialized_at.strftime('%Y%m%dT%H%M%SZ')}-{revision[:7]}"
    if Q01_RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise BaselineValidationError(f"generated invalid Q0.1 run ID: {run_id}")

    environment = EnvironmentResult(
        run_id=run_id,
        initialized_at_utc=initialized_at,
        run_initialized_git_revision=revision,
        producer_git_revision=revision,
        tracked_tree_clean=True,
        baseline_run_id=BASELINE_RUN_ID,
        inherited_artifact_sha256=inherited_hashes,
        os_version=_os_version(),
        architecture=platform.machine(),
        physical_memory_bytes=psutil.virtual_memory().total,
        python_version=platform.python_version(),
        identities={
            "baseline_run_id": BASELINE_RUN_ID,
            "producer_git_revision": revision,
        },
        measurements={
            "baseline": {
                "status": "pending",
            }
        },
        threshold_outcomes={
            "tracked_tree_clean": ThresholdOutcome(
                passed=True,
                requirement="tracked tree is clean at Q0.1 run initialization",
                observed=True,
            ),
            "inherited_artifacts_match": ThresholdOutcome(
                passed=True,
                requirement="all six approved Q0 artifact hashes match",
                observed=len(inherited_hashes),
            ),
        },
    )
    environment_path = root / "qualification" / "results" / run_id / "environment.json"
    if environment_path.exists():
        raise BaselineValidationError(f"Q0.1 environment already exists: {environment_path}")
    write_json_atomic(environment_path, environment)
    write_text_atomic(
        root / "qualification" / "private" / "q0-1-run-id.txt",
        f"{run_id}\n",
    )
    return run_id


def _load_environment(root: Path, run_id: str) -> EnvironmentResult:
    path = root / "qualification" / "results" / run_id / "environment.json"
    try:
        environment = EnvironmentResult.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BaselineValidationError(f"Q0.1 environment not found: {path}") from error
    except (OSError, ValidationError) as error:
        raise BaselineValidationError(f"invalid Q0.1 environment {path}: {error}") from error
    if environment.run_id != run_id:
        raise BaselineValidationError(
            f"environment run ID {environment.run_id!r} does not match {run_id!r}"
        )
    return environment


def _serialize_jsonl(values: Sequence[BaseModel]) -> str:
    return "".join(value.model_dump_json(exclude_none=False) + "\n" for value in values)


def _validate_parsed_stream(path: Path, expected_count: int) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise BaselineValidationError(f"cannot read parsed-block stream {path}: {error}") from error
    if len(lines) != expected_count:
        raise BaselineValidationError(
            f"parsed-block stream record count changed: expected {expected_count}, observed {len(lines)}"
        )
    for line_number, line in enumerate(lines, start=1):
        try:
            block = ParsedBlock.model_validate_json(line)
        except ValidationError as error:
            raise BaselineValidationError(
                f"invalid ParsedBlock in {path}:{line_number}: {error}"
            ) from error
        validate_block_provenance(block)


def _validate_chunk_stream(path: Path, expected_count: int) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise BaselineValidationError(f"cannot read chunk stream {path}: {error}") from error
    if len(lines) != expected_count:
        raise BaselineValidationError(
            f"chunk stream record count changed: expected {expected_count}, observed {len(lines)}"
        )
    for line_number, line in enumerate(lines, start=1):
        try:
            Chunk.model_validate_json(line)
        except ValidationError as error:
            raise BaselineValidationError(
                f"invalid Chunk in {path}:{line_number}: {error}"
            ) from error


def _verify_cached_pdfs(root: Path, manifest: Any) -> tuple[list[dict[str, Any]], list[Path]]:
    import pymupdf

    identities: list[dict[str, Any]] = []
    paths: list[Path] = []
    for paper in manifest.papers:
        path = root / "qualification" / ".cache" / "pdfs" / f"{paper.paper_id}.pdf"
        try:
            pdf_bytes = path.read_bytes()
        except OSError as error:
            raise BaselineValidationError(f"cannot read cached PDF {path}: {error}") from error
        observed_hash = hashlib.sha256(pdf_bytes).hexdigest()
        if observed_hash != paper.sha256:
            raise BaselineValidationError(
                f"cached PDF SHA-256 mismatch for {paper.paper_id}: expected {paper.sha256}, observed {observed_hash}"
            )
        if not pdf_bytes.startswith(b"%PDF-"):
            raise BaselineValidationError(f"cached file is not a PDF: {path}")
        try:
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
                page_count = document.page_count
        except Exception as error:
            raise BaselineValidationError(f"cannot parse cached PDF {path}: {error}") from error
        if page_count != paper.page_count:
            raise BaselineValidationError(
                f"cached PDF page-count mismatch for {paper.paper_id}: expected {paper.page_count}, observed {page_count}"
            )
        identities.append(
            {
                "paper_id": paper.paper_id,
                "sha256": observed_hash,
                "page_count": page_count,
            }
        )
        paths.append(path)
    if len(identities) != 2:
        raise BaselineValidationError(
            f"baseline requires exactly two PDFs, observed {len(identities)}"
        )
    return identities, paths


def prepare_baseline(*, root: Path, run_id: str) -> dict[str, Any]:
    root = root.resolve()

    # This gate intentionally precedes every network request and parser invocation.
    inherited_hashes = verify_inherited_artifacts(root)

    discovered_run_id = discover_q01_run_id(root)
    if run_id != discovered_run_id:
        raise BaselineValidationError(
            f"requested run ID {run_id!r} does not match initialized Q0.1 run {discovered_run_id!r}"
        )
    environment = _load_environment(root, run_id)
    if environment.baseline_run_id != BASELINE_RUN_ID:
        raise BaselineValidationError("Q0.1 environment names the wrong baseline run")
    if environment.inherited_artifact_sha256 != inherited_hashes:
        raise BaselineValidationError("Q0.1 environment inherited artifact identities changed")

    producer_revision = _require_clean_producer(root)
    if environment.run_initialized_git_revision != producer_revision:
        raise BaselineValidationError(
            "baseline must be regenerated from the clean run-initialized producer revision"
        )
    if environment.producer_git_revision != producer_revision:
        raise BaselineValidationError("Q0.1 environment producer revision changed")

    parser_version = importlib.metadata.version("pymupdf")
    if parser_version != EXPECTED_PYMUPDF_VERSION:
        raise BaselineValidationError(
            f"PyMuPDF version mismatch: expected {EXPECTED_PYMUPDF_VERSION}, observed {parser_version}"
        )

    manifest = fetch_corpus(root)
    pdf_identities, pdf_paths = _verify_cached_pdfs(root, manifest)
    gold_summary = validate_gold(root)

    blocks: list[ParsedBlock] = []
    block_counts: dict[str, int] = {}
    for paper, pdf_path in zip(manifest.papers, pdf_paths, strict=True):
        paper_blocks = parse_pymupdf(pdf_path)
        if any(block.paper_id != paper.paper_id for block in paper_blocks):
            raise BaselineValidationError(
                f"PyMuPDF emitted the wrong paper identity for {paper.paper_id}"
            )
        if any(block.page_index >= paper.page_count for block in paper_blocks):
            raise BaselineValidationError(
                f"PyMuPDF emitted an out-of-range page for {paper.paper_id}"
            )
        for block in paper_blocks:
            validate_block_provenance(block)
        block_counts[paper.paper_id] = len(paper_blocks)
        blocks.extend(paper_blocks)

    private_directory = root / "qualification" / "private" / run_id
    parsed_path = private_directory / "parsed-blocks-pymupdf.jsonl"
    write_text_atomic(parsed_path, _serialize_jsonl(blocks))
    _validate_parsed_stream(parsed_path, len(blocks))

    chunks = build_chunks(blocks, max_chars=2000)
    if len(chunks) != EXPECTED_CHUNK_COUNT:
        raise BaselineValidationError(
            f"regenerated chunk count mismatch: expected {EXPECTED_CHUNK_COUNT}, observed {len(chunks)}"
        )
    chunks_text = _serialize_jsonl(chunks)
    chunk_sha256 = hashlib.sha256(chunks_text.encode("utf-8")).hexdigest()
    require_chunk_identity(observed=chunk_sha256)
    chunks_path = private_directory / "chunks.jsonl"
    write_text_atomic(chunks_path, chunks_text)
    _validate_chunk_stream(chunks_path, EXPECTED_CHUNK_COUNT)

    baseline_measurements = {
        "status": "prepared",
        "pdf_count": len(pdf_identities),
        "pdfs": pdf_identities,
        "gold_validation": gold_summary,
        "parser": {
            "candidate": "pymupdf",
            "version": parser_version,
            "coordinate_origin": "bottom-left",
            "parsed_block_count": len(blocks),
            "parsed_block_counts_by_paper": block_counts,
            "stream_relative_path": str(parsed_path.relative_to(root)),
            "stream_sha256": hashlib.sha256(parsed_path.read_bytes()).hexdigest(),
            "validated_as_parsed_block": True,
        },
        "chunks": {
            "count": len(chunks),
            "sha256": chunk_sha256,
            "max_chars": 2000,
            "overlap_chars": 0,
            "paragraph_boundary_preference": True,
            "cross_section_chunks": 0,
            "stream_relative_path": str(chunks_path.relative_to(root)),
            "validated_as_chunk": True,
        },
    }
    updated_environment = environment.model_copy(
        update={
            "producer_git_revision": producer_revision,
            "regenerated_chunk_set_sha256": chunk_sha256,
            "identities": {
                **environment.identities,
                "parser": {
                    "candidate": "pymupdf",
                    "version": parser_version,
                    "coordinate_origin": "bottom-left",
                },
                "corpus_paper_ids": [paper.paper_id for paper in manifest.papers],
            },
            "measurements": {
                **environment.measurements,
                "baseline": baseline_measurements,
            },
            "threshold_outcomes": {
                **environment.threshold_outcomes,
                "exact_corpus": ThresholdOutcome(
                    passed=True,
                    requirement="two cached PDFs match manifest hashes and page counts",
                    observed=len(pdf_identities),
                ),
                "pymupdf_provenance": ThresholdOutcome(
                    passed=True,
                    requirement="every PyMuPDF block validates with bottom-left provenance",
                    observed=len(blocks),
                ),
                "chunk_identity": ThresholdOutcome(
                    passed=True,
                    requirement="exactly 93 chunks match the inherited chunk-set SHA-256",
                    observed=chunk_sha256,
                ),
            },
        }
    )
    environment_path = root / "qualification" / "results" / run_id / "environment.json"
    write_json_atomic(environment_path, updated_environment)

    return {
        "run_id": run_id,
        "inherited_artifact_count": len(inherited_hashes),
        "pdf_count": len(pdf_identities),
        "parsed_block_count": len(blocks),
        "chunk_count": len(chunks),
        "chunk_set_sha256": chunk_sha256,
        "parser": "pymupdf",
        "parser_version": parser_version,
        "coordinate_origin": "bottom-left",
    }
