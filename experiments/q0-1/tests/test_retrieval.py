from __future__ import annotations

import pytest

from q0.models import ParsedBlock
from q0.retrieval import (
    VectorValidationError,
    build_chunks,
    retrieval_metrics,
    validate_vector,
)


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
