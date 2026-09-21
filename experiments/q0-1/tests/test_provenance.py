from __future__ import annotations

import json
from pathlib import Path

import pytest

from q0.models import BBox, EvidenceCase, ParsedBlock, SourceSpan
from q0.parsers import (
    ParserValidationError,
    SourceRun,
    normalize_with_map,
    ordered_token_lcs_coverage,
    parse_pymupdf,
    resolve_exact_quote,
    top_left_to_bottom_left_bbox,
    validate_block_provenance,
)


ROOT = Path(__file__).resolve().parents[3]


def _box(x0: float, y0: float, x1: float, y1: float) -> BBox:
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _overlap_area(left: BBox, right: BBox) -> float:
    return max(0.0, min(left.x1, right.x1) - max(left.x0, right.x0)) * max(
        0.0, min(left.y1, right.y1) - max(left.y0, right.y0)
    )


def test_normalize_with_map_collapses_whitespace_and_preserves_every_offset():
    first = _box(10, 10, 30, 20)
    second = _box(31, 10, 60, 20)

    normalized, spans = normalize_with_map(
        [
            SourceRun(text="  Alpha\t", page_index=0, bbox=first),
            SourceRun(text="\n  Beta  ", page_index=0, bbox=second),
        ]
    )

    assert normalized == "Alpha Beta"
    coverage = [0] * len(normalized)
    for span in spans:
        for offset in range(span.text_start, span.text_end):
            coverage[offset] += 1
    assert coverage == [1] * len(normalized)
    assert spans[0].text_start == 0
    assert spans[-1].text_end == len(normalized)


def test_two_run_dehyphenation_resolves_scaled_dot_product_to_both_boxes():
    first = _box(100, 500, 190, 512)
    second = _box(100, 486, 160, 498)

    normalized, spans = normalize_with_map(
        [
            SourceRun(text="scaled dot-\n", page_index=3, bbox=first),
            SourceRun(text="product", page_index=3, bbox=second),
        ]
    )

    assert normalized == "scaled dot-product"
    quote_start = normalized.index("scaled dot-product")
    quote_end = quote_start + len("scaled dot-product")
    resolved_boxes = {
        span.bbox.model_dump_json()
        for span in spans
        if span.text_start < quote_end and span.text_end > quote_start
    }
    assert resolved_boxes == {first.model_dump_json(), second.model_dump_json()}


def test_nfkc_expansion_maps_each_output_character_to_the_source_box():
    ligature_box = _box(10, 10, 20, 20)

    normalized, spans = normalize_with_map(
        [SourceRun(text="ﬁ", page_index=0, bbox=ligature_box)]
    )

    assert normalized == "fi"
    assert [(span.text_start, span.text_end, span.bbox) for span in spans] == [
        (0, 2, ligature_box)
    ]


def test_top_left_conversion_uses_the_exact_bottom_left_formula():
    converted = top_left_to_bottom_left_bbox(
        _box(11, 23, 47, 89), page_width=612, page_height=792
    )

    assert converted == _box(11, 792 - 89, 47, 792 - 23)


def test_provenance_rejects_an_out_of_page_box():
    block = ParsedBlock(
        paper_id="paper",
        page_index=0,
        section_path=[],
        block_type="paragraph",
        reading_order=0,
        normalized_text="text",
        source_spans=[
            SourceSpan(
                text_start=0,
                text_end=4,
                page_index=0,
                bbox=_box(0, 0, 101, 20),
            )
        ],
        page_width=100,
        page_height=100,
        coordinate_origin="bottom-left",
    )

    with pytest.raises(ParserValidationError, match="outside page bounds"):
        validate_block_provenance(block)


def test_ordered_token_lcs_coverage_is_reference_token_recall():
    measurement = ordered_token_lcs_coverage(
        reference="alpha beta gamma delta",
        candidate="noise alpha gamma beta delta noise",
    )

    assert measurement == {"numerator": 3, "denominator": 4, "score": 0.75}
    with pytest.raises(ParserValidationError, match="empty coverage reference"):
        ordered_token_lcs_coverage(reference=" \n\t", candidate="anything")




def test_real_pdf_golden_quote_resolves_to_annotated_page_and_regions():
    evidence_path = ROOT / "qualification" / "gold" / "evidence.jsonl"
    golden = next(
        EvidenceCase.model_validate(json.loads(line))
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["case_id"] == "1706.03762-answer-1"
    )
    pdf_path = ROOT / "qualification" / ".cache" / "pdfs" / "1706.03762.pdf"

    blocks = parse_pymupdf(pdf_path)
    resolutions = resolve_exact_quote(blocks, golden.quotes[0])

    assert len(resolutions) == 1
    resolution = resolutions[0]
    assert resolution.page_index == golden.page_index
    assert resolution.boxes
    assert all(
        0 <= box.x0 < box.x1 <= resolution.page_width
        and 0 <= box.y0 < box.y1 <= resolution.page_height
        for box in resolution.boxes
    )
    assert golden.expected_boxes
    assert all(
        any(_overlap_area(source, expected) > 0 for source in resolution.boxes)
        for expected in golden.expected_boxes
    )
