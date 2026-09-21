from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ARTIFACT_VERSION = "q0.1-hybrid-1"
BASELINE_RUN_ID = "q0-20260920T124722Z-cd96df4"
EXPECTED_CHUNK_SHA256 = "0aa4bbf11729158948230963930520c2cb52b04e5a292f03ba97c64d7c572cde"


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
    question: str | None = None
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


class ThresholdOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    requirement: str
    observed: JsonValue = None
    failure_reason: str | None = None


class QualificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_version: Literal["q0.1-hybrid-1"] = ARTIFACT_VERSION
    run_id: str
    identities: dict[str, JsonValue] = Field(default_factory=dict)
    measurements: dict[str, JsonValue] = Field(default_factory=dict)
    threshold_outcomes: dict[str, ThresholdOutcome] = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)


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


class HybridRetrievalResult(QualificationResult):
    selected_configuration: str | None = None


class GenerationResult(QualificationResult):
    provider: str | None = None
    requested_model_id: str | None = None
    response_model_id: str | None = None


class IntegratedProofResult(QualificationResult):
    html_sha256: str | None = None


def write_bytes_atomic(path: Path, encoded: bytes) -> None:
    """Durably replace one file using a temporary sibling."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(temporary_fd, "wb") as temporary_file:
            temporary_file.write(encoded)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str) -> None:
    write_bytes_atomic(path, text.encode("utf-8"))


def write_json_atomic(path: Path, value: BaseModel | dict[str, JsonValue]) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    write_text_atomic(path, text)
