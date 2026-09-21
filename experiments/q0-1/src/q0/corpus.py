from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import httpx

from pydantic import BaseModel, ConfigDict, ValidationError

from q0.models import (
    ARTIFACT_VERSION,
    EvidenceCase,
    ReadingOrderRelation,
    write_json_atomic,
)

CORPUS = {
    "1706.03762": "Attention Is All You Need",
    "2005.11401": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
}


class CorpusValidationError(ValueError):
    pass


class GoldValidationError(ValueError):
    pass


class ManifestPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    title: str
    source_url: str
    sha256: str
    page_count: int


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_version: str = ARTIFACT_VERSION
    papers: list[ManifestPaper]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_pdf_hash(expected: str, actual_bytes: bytes) -> None:
    actual = sha256_bytes(actual_bytes)
    if actual != expected:
        raise CorpusValidationError(
            f"PDF SHA-256 mismatch: expected {expected}, observed {actual}"
        )


def _inspect_pdf(pdf_bytes: bytes, *, source: str) -> int:
    import pymupdf
    if not pdf_bytes.startswith(b"%PDF-"):
        raise CorpusValidationError(f"non-PDF response from {source}: missing PDF header")
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            page_count = document.page_count
    except Exception as error:
        raise CorpusValidationError(f"invalid PDF from {source}: {error}") from error
    if page_count < 1:
        raise CorpusValidationError(f"invalid PDF from {source}: no pages")
    return page_count


def _manifest_path(root: Path) -> Path:
    return root / "qualification" / "corpus" / "manifest.json"


def _pdf_path(root: Path, paper_id: str) -> Path:
    return root / "qualification" / ".cache" / "pdfs" / f"{paper_id}.pdf"


def load_manifest(root: Path) -> CorpusManifest:
    path = _manifest_path(root)
    try:
        manifest = CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CorpusValidationError(f"corpus manifest not found: {path}") from error
    except (OSError, ValidationError) as error:
        raise CorpusValidationError(f"invalid corpus manifest {path}: {error}") from error

    paper_ids = [paper.paper_id for paper in manifest.papers]
    if paper_ids != sorted(CORPUS):
        raise CorpusValidationError(
            f"manifest papers must be sorted and exactly {sorted(CORPUS)}, observed {paper_ids}"
        )
    for paper in manifest.papers:
        expected_url = f"https://arxiv.org/pdf/{paper.paper_id}"
        if paper.title != CORPUS[paper.paper_id] or paper.source_url != expected_url:
            raise CorpusValidationError(
                f"manifest identity mismatch for {paper.paper_id}"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", paper.sha256):
            raise CorpusValidationError(
                f"manifest SHA-256 is malformed for {paper.paper_id}"
            )
        if paper.page_count < 1:
            raise CorpusValidationError(
                f"manifest page count is invalid for {paper.paper_id}"
            )
    return manifest


def fetch_corpus(root: Path) -> CorpusManifest:
    root = root.resolve()
    manifest_path = _manifest_path(root)
    previous_by_id: dict[str, ManifestPaper] = {}
    if manifest_path.exists():
        previous_by_id = {
            paper.paper_id: paper for paper in load_manifest(root).papers
        }

    entries: list[ManifestPaper] = []
    with httpx.Client(
        follow_redirects=True,
        timeout=60.0,
        headers={"User-Agent": "researcy-q0-qualification/1.0"},
    ) as client:
        for paper_id, title in sorted(CORPUS.items()):
            url = f"https://arxiv.org/pdf/{paper_id}"
            cache_path = _pdf_path(root, paper_id)
            previous = previous_by_id.get(paper_id)
            pdf_bytes: bytes | None = None
            page_count: int | None = None

            if previous is not None and cache_path.is_file():
                cached_bytes = cache_path.read_bytes()
                try:
                    validate_pdf_hash(previous.sha256, cached_bytes)
                    cached_page_count = _inspect_pdf(
                        cached_bytes,
                        source=str(cache_path),
                    )
                except CorpusValidationError:
                    pass
                else:
                    if cached_page_count == previous.page_count:
                        pdf_bytes = cached_bytes
                        page_count = cached_page_count

            if pdf_bytes is None:
                response = client.get(url)
                try:
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise CorpusValidationError(
                        f"failed to download {paper_id}: {error}"
                    ) from error
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type != "application/pdf":
                    raise CorpusValidationError(
                        f"non-PDF response from {url}: content-type {content_type or '<missing>'}"
                    )
                downloaded_bytes = response.content
                downloaded_page_count = _inspect_pdf(downloaded_bytes, source=url)
                if previous is not None:
                    validate_pdf_hash(previous.sha256, downloaded_bytes)
                    if downloaded_page_count != previous.page_count:
                        raise CorpusValidationError(
                            f"downloaded page count {downloaded_page_count} does not match manifest {previous.page_count} for {paper_id}"
                        )
                pdf_bytes = downloaded_bytes
                page_count = downloaded_page_count
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(pdf_bytes)

            entries.append(
                ManifestPaper(
                    paper_id=paper_id,
                    title=title,
                    source_url=url,
                    sha256=sha256_bytes(pdf_bytes),
                    page_count=page_count,
                )
            )

    if not manifest_path.exists():
        manifest = CorpusManifest(papers=entries)
        write_json_atomic(manifest_path, manifest)
    else:
        manifest = load_manifest(root)
    return manifest


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\u00ad", "")
    normalized = re.sub(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def validate_evidence_case(case: EvidenceCase, page_text: str) -> None:
    if case.answerable:
        if case.page_index is None:
            raise GoldValidationError(f"{case.case_id}: answerable case needs a page")
        if not case.quotes:
            raise GoldValidationError(f"{case.case_id}: answerable case needs a quote")
        if not case.expected_section:
            raise GoldValidationError(
                f"{case.case_id}: answerable case needs an expected section"
            )
        normalized_page = normalize_text(page_text)
        for quote in case.quotes:
            normalized_quote = normalize_text(quote)
            if not normalized_quote or normalized_quote not in normalized_page:
                raise GoldValidationError(
                    f"{case.case_id}: quote not found on annotated page: {quote!r}"
                )
    elif case.quotes:
        raise GoldValidationError(f"{case.case_id}: unanswerable case must have no quotes")

def validate_reading_order_anchors(relation: ReadingOrderRelation, page_text: str) -> None:
    normalized_page = normalize_text(page_text)
    before = normalize_text(relation.before_anchor)
    after = normalize_text(relation.after_anchor)
    before_count = normalized_page.count(before) if before else 0
    after_count = normalized_page.count(after) if after else 0
    if before_count != 1 or after_count != 1:
        raise GoldValidationError(
            f"{relation.relation_id}: anchors must each resolve exactly once; "
            f"before={before_count}, after={after_count}"
        )


def validate_gold_counts(counts: dict[str, dict[str, int]]) -> None:
    if set(counts) != set(CORPUS):
        raise GoldValidationError(
            f"gold papers must be exactly {sorted(CORPUS)}, observed {sorted(counts)}"
        )
    for paper_id in sorted(CORPUS):
        observed = counts[paper_id]
        if observed.get("answerable") != 4 or observed.get("unanswerable") != 1:
            raise GoldValidationError(
                f"{paper_id} must have exactly 4 answerable and 1 unanswerable case; "
                f"observed {observed}"
            )


def _read_jsonl(path: Path, model_type: type[BaseModel]) -> list[BaseModel]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise GoldValidationError(f"gold file not found: {path}") from error
    values: list[BaseModel] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise GoldValidationError(f"{path}:{line_number}: blank JSONL record")
        try:
            values.append(model_type.model_validate_json(line))
        except ValidationError as error:
            raise GoldValidationError(
                f"{path}:{line_number}: invalid record: {error}"
            ) from error
    return values


def _load_verified_pdf(root: Path, paper: ManifestPaper) -> bytes:
    path = _pdf_path(root, paper.paper_id)
    try:
        pdf_bytes = path.read_bytes()
    except FileNotFoundError as error:
        raise CorpusValidationError(f"cached PDF not found: {path}") from error
    validate_pdf_hash(paper.sha256, pdf_bytes)
    page_count = _inspect_pdf(pdf_bytes, source=str(path))
    if page_count != paper.page_count:
        raise CorpusValidationError(
            f"page count mismatch for {paper.paper_id}: "
            f"expected {paper.page_count}, observed {page_count}"
        )
    return pdf_bytes


def _require_unique_ids(values: list[BaseModel], attribute: str, label: str) -> None:
    ids = [getattr(value, attribute) for value in values]
    duplicates = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise GoldValidationError(f"duplicate {label}: {duplicates}")


def validate_gold(root: Path) -> dict[str, int | bool | str]:
    import pymupdf
    root = root.resolve()
    manifest = load_manifest(root)
    manifest_by_id = {paper.paper_id: paper for paper in manifest.papers}
    pdf_bytes_by_id = {
        paper.paper_id: _load_verified_pdf(root, paper) for paper in manifest.papers
    }

    evidence_path = root / "qualification" / "gold" / "evidence.jsonl"
    relations_path = root / "qualification" / "gold" / "reading-order.jsonl"
    evidence = [
        value
        for value in _read_jsonl(evidence_path, EvidenceCase)
        if isinstance(value, EvidenceCase)
    ]
    relations = [
        value
        for value in _read_jsonl(relations_path, ReadingOrderRelation)
        if isinstance(value, ReadingOrderRelation)
    ]
    _require_unique_ids(evidence, "case_id", "case IDs")
    _require_unique_ids(relations, "relation_id", "relation IDs")

    expected_case_ids = {
        *(f"{paper_id}-answer-{index}" for paper_id in CORPUS for index in range(1, 5)),
        *(f"{paper_id}-unanswerable" for paper_id in CORPUS),
    }
    observed_case_ids = {case.case_id for case in evidence}
    if observed_case_ids != expected_case_ids:
        raise GoldValidationError(
            "gold case IDs differ from the fixed question identities: "
            f"missing={sorted(expected_case_ids - observed_case_ids)}, "
            f"extra={sorted(observed_case_ids - expected_case_ids)}"
        )

    counts = {
        paper_id: {"answerable": 0, "unanswerable": 0} for paper_id in CORPUS
    }
    coverage_counts = Counter[str]()
    page_cache: dict[tuple[str, int], tuple[str, float, float]] = {}

    def page_details(paper_id: str, page_index: int) -> tuple[str, float, float]:
        cache_key = (paper_id, page_index)
        if cache_key not in page_cache:
            paper = manifest_by_id[paper_id]
            if page_index < 0 or page_index >= paper.page_count:
                raise GoldValidationError(
                    f"{paper_id}: page index {page_index} is outside 0..{paper.page_count - 1}"
                )
            with pymupdf.open(
                stream=pdf_bytes_by_id[paper_id],
                filetype="pdf",
            ) as document:
                page = document[page_index]
                page_cache[cache_key] = (
                    page.get_text("text", sort=False),
                    float(page.rect.width),
                    float(page.rect.height),
                )
        return page_cache[cache_key]

    for case in evidence:
        if case.paper_id not in manifest_by_id:
            raise GoldValidationError(
                f"{case.case_id}: unknown paper {case.paper_id}"
            )
        if case.question is None or not case.question.strip():
            raise GoldValidationError(f"{case.case_id}: question is empty")
        counts[case.paper_id]["answerable" if case.answerable else "unanswerable"] += 1
        if case.answerable:
            if case.page_index is None:
                raise GoldValidationError(f"{case.case_id}: answerable case needs a page")
            page_text, _, _ = page_details(case.paper_id, case.page_index)
            validate_evidence_case(case, page_text)
        else:
            validate_evidence_case(case, page_text="")
            if case.page_index is not None or case.expected_section is not None:
                raise GoldValidationError(
                    f"{case.case_id}: unanswerable case must not identify a page or section"
                )

        if case.coverage_reference_text is not None:
            if not case.answerable or case.page_index is None:
                raise GoldValidationError(
                    f"{case.case_id}: coverage reference must be on an answerable case"
                )
            page_text, _, _ = page_details(case.paper_id, case.page_index)
            reference = normalize_text(case.coverage_reference_text)
            if not reference or reference not in normalize_text(page_text):
                raise GoldValidationError(
                    f"{case.case_id}: coverage reference text is not on the annotated page"
                )
            coverage_counts[case.paper_id] += 1

    validate_gold_counts(counts)
    for paper_id in sorted(CORPUS):
        if coverage_counts[paper_id] != 1:
            raise GoldValidationError(
                f"{paper_id} must have exactly one coverage reference; "
                f"observed {coverage_counts[paper_id]}"
            )

    golden = next(case for case in evidence if case.case_id == "1706.03762-answer-1")
    if golden.page_index is None:
        raise GoldValidationError("golden case has no page")
    _, actual_width, actual_height = page_details(golden.paper_id, golden.page_index)
    if (
        golden.coordinate_origin != "bottom-left"
        or golden.expected_page_width is None
        or golden.expected_page_height is None
        or not golden.expected_boxes
    ):
        raise GoldValidationError(
            "golden case requires bottom-left origin, page dimensions, and expected boxes"
        )
    if abs(golden.expected_page_width - actual_width) > 0.01 or abs(
        golden.expected_page_height - actual_height
    ) > 0.01:
        raise GoldValidationError(
            "golden case page dimensions do not match the cached PDF"
        )
    for box in golden.expected_boxes:
        if not (
            0 <= box.x0 < box.x1 <= golden.expected_page_width
            and 0 <= box.y0 < box.y1 <= golden.expected_page_height
        ):
            raise GoldValidationError(
                f"golden case has an out-of-page or empty box: {box.model_dump()}"
            )

    relation_counts = Counter[str]()
    relation_ids_by_paper: dict[str, set[str]] = {
        paper_id: set() for paper_id in CORPUS
    }
    for relation in relations:
        if relation.paper_id not in manifest_by_id:
            raise GoldValidationError(
                f"{relation.relation_id}: unknown paper {relation.paper_id}"
            )
        page_text, _, _ = page_details(relation.paper_id, relation.page_index)
        validate_reading_order_anchors(relation, page_text)
        relation_counts[relation.paper_id] += 1
        relation_ids_by_paper[relation.paper_id].add(relation.relation_id)

    for paper_id in sorted(CORPUS):
        if relation_counts[paper_id] < 6:
            raise GoldValidationError(
                f"{paper_id} needs at least 6 reading-order relations; "
                f"observed {relation_counts[paper_id]}"
            )
        if not any(
            "column-transition" in relation_id
            for relation_id in relation_ids_by_paper[paper_id]
        ):
            raise GoldValidationError(
                f"{paper_id} needs a manually checked column-transition relation"
            )
    if not any(
        "table-caption" in relation_id
        for relation_id in relation_ids_by_paper["2005.11401"]
    ):
        raise GoldValidationError(
            "2005.11401 needs a manually checked table/caption relation"
        )

    return {
        "papers": len(manifest.papers),
        "answerable_cases": sum(1 for case in evidence if case.answerable),
        "unanswerable_cases": sum(1 for case in evidence if not case.answerable),
        "coverage_references": sum(coverage_counts.values()),
        "reading_order_relations": len(relations),
        "independent_golden_boxes": len(golden.expected_boxes),
        "coordinate_origin": "bottom-left",
        "valid": True,
    }


def summary_json(summary: dict[str, int | bool | str]) -> str:
    return json.dumps(summary, sort_keys=True)
