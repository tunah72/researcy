from __future__ import annotations

import json

import pytest

from q0.baseline import (
    BaselineValidationError,
    discover_q01_run_id,
    require_chunk_identity,
    verify_file_hash,
)
from q0.models import BBox, ParsedBlock, SourceSpan
from q0.retrieval import build_chunks


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
