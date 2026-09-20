import pytest

from q0.corpus import (
    CorpusValidationError,
    GoldValidationError,
    validate_evidence_case,
    validate_gold_counts,
    validate_pdf_hash,
)
from q0.models import EvidenceCase


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
