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

def test_gold_reading_order_allows_reverse_text_flow_when_anchors_unique():
    from q0.corpus import validate_reading_order_anchors
    from q0.models import ReadingOrderRelation

    relation = ReadingOrderRelation(
        relation_id="test-reverse",
        paper_id="1706.03762",
        page_index=0,
        before_anchor="bottom text",
        after_anchor="top text",
    )
    # page_text contains "top text" then "bottom text", so stream order is after then before
    page_text = "Here is top text and later is bottom text."
    validate_reading_order_anchors(relation, page_text)




def test_fetch_corpus_rejects_download_hash_mismatch_when_manifest_exists(tmp_path, monkeypatch):
    from q0.corpus import CorpusManifest, ManifestPaper, fetch_corpus
    import q0.corpus

    manifest = CorpusManifest(
        papers=[
            ManifestPaper(
                paper_id="1706.03762",
                title="Attention Is All You Need",
                source_url="https://arxiv.org/pdf/1706.03762",
                sha256="1" * 64,
                page_count=15,
            )
        ]
    )
    manifest_path = tmp_path / "qualification" / "corpus" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    import fitz
    doc = fitz.open()
    doc.new_page()
    fake_pdf = doc.tobytes()

    class MockResponse:
        headers = {"content-type": "application/pdf"}
        content = fake_pdf
        def raise_for_status(self):
            pass

    class MockClient:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            return MockResponse()

    monkeypatch.setattr(q0.corpus.httpx, "Client", lambda **kwargs: MockClient())
    monkeypatch.setattr(q0.corpus, "CORPUS", {"1706.03762": "Attention Is All You Need"})

    with pytest.raises(CorpusValidationError, match="SHA-256"):
        fetch_corpus(tmp_path)
