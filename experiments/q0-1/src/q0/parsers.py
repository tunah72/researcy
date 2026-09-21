from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from q0.models import BBox, ParsedBlock, SourceSpan


class ParserValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceRun:
    text: str
    page_index: int
    bbox: BBox


@dataclass(frozen=True, slots=True)
class QuoteResolution:
    page_index: int
    page_width: float
    page_height: float
    text_start: int
    text_end: int
    boxes: tuple[BBox, ...]
    section_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MappedCharacter:
    value: str
    page_index: int
    bbox: BBox


@dataclass(slots=True)
class _RawPdfBlock:
    page_index: int
    page_width: float
    page_height: float
    top_left_bbox: BBox
    source_runs: list[SourceRun]
    max_font_size: float
    flags: int
    original_number: int


@dataclass(frozen=True, slots=True)
class _PageCharacter:
    bbox: BBox | None
    block: ParsedBlock | None


def _union_boxes(boxes: Sequence[BBox]) -> BBox:
    if not boxes:
        raise ParserValidationError("cannot union an empty box sequence")
    return BBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )


def _same_box(left: BBox, right: BBox) -> bool:
    return left == right


def _source_characters(text_runs: Sequence[SourceRun]) -> list[_MappedCharacter]:
    source: list[_MappedCharacter] = []
    for run in text_runs:
        if run.page_index < 0:
            raise ParserValidationError("source page index must be non-negative")
        if run.bbox.x0 >= run.bbox.x1 or run.bbox.y0 >= run.bbox.y1:
            raise ParserValidationError("source boxes must have positive area")
        source.extend(
            _MappedCharacter(value=character, page_index=run.page_index, bbox=run.bbox)
            for character in run.text
        )
    return source


def _nfkc_with_map(source: Sequence[_MappedCharacter]) -> list[_MappedCharacter]:
    normalized: list[_MappedCharacter] = []
    index = 0
    while index < len(source):
        cluster = [source[index]]
        index += 1
        while index < len(source) and unicodedata.combining(source[index].value):
            cluster.append(source[index])
            index += 1

        cluster_text = "".join(character.value for character in cluster).replace("\u00ad", "")
        if not cluster_text:
            continue
        cluster_pages = {character.page_index for character in cluster}
        if len(cluster_pages) != 1:
            raise ParserValidationError("one Unicode cluster spans multiple pages")
        cluster_box = _union_boxes([character.bbox for character in cluster])
        cluster_page = cluster[0].page_index
        for character in unicodedata.normalize("NFKC", cluster_text):
            normalized.append(
                _MappedCharacter(
                    value=character,
                    page_index=cluster_page,
                    bbox=cluster_box,
                )
            )
    return normalized


def _collapse_layout_whitespace(
    source: Sequence[_MappedCharacter],
) -> list[_MappedCharacter]:
    output: list[_MappedCharacter] = []
    index = 0
    while index < len(source):
        character = source[index]
        if not character.value.isspace():
            output.append(character)
            index += 1
            continue

        whitespace: list[_MappedCharacter] = []
        while index < len(source) and source[index].value.isspace():
            whitespace.append(source[index])
            index += 1

        previous = output[-1].value if output else ""
        following = source[index].value if index < len(source) else ""
        line_break = any(item.value in "\r\n" for item in whitespace)
        if previous == "-" and line_break:
            before_hyphen = output[-2].value if len(output) >= 2 else ""
            if before_hyphen and following and before_hyphen.isalnum() and following.isalnum():
                continue

        if not output or index >= len(source):
            continue
        pages = {item.page_index for item in whitespace}
        if len(pages) != 1:
            raise ParserValidationError("collapsed whitespace spans multiple pages")
        output.append(
            _MappedCharacter(
                value=" ",
                page_index=whitespace[0].page_index,
                bbox=_union_boxes([item.bbox for item in whitespace]),
            )
        )
    return output


def normalize_with_map(text_runs: Sequence[SourceRun]) -> tuple[str, list[SourceSpan]]:
    """Apply the allowed normalization while retaining one source box per output character."""

    characters = _collapse_layout_whitespace(_nfkc_with_map(_source_characters(text_runs)))
    normalized = "".join(character.value for character in characters)
    spans: list[SourceSpan] = []
    for offset, character in enumerate(characters):
        if (
            spans
            and spans[-1].text_end == offset
            and spans[-1].page_index == character.page_index
            and _same_box(spans[-1].bbox, character.bbox)
        ):
            previous = spans[-1]
            spans[-1] = previous.model_copy(update={"text_end": offset + 1})
        else:
            spans.append(
                SourceSpan(
                    text_start=offset,
                    text_end=offset + 1,
                    page_index=character.page_index,
                    bbox=character.bbox,
                )
            )
    return normalized, spans


def top_left_to_bottom_left_bbox(
    bbox: BBox, *, page_width: float, page_height: float
) -> BBox:
    if page_width <= 0 or page_height <= 0:
        raise ParserValidationError("page dimensions must be positive")
    if bbox.x0 < 0 or bbox.y0 < 0 or bbox.x1 > page_width or bbox.y1 > page_height:
        raise ParserValidationError(
            f"top-left box is outside page bounds {page_width}x{page_height}: {bbox}"
        )
    if bbox.x0 >= bbox.x1 or bbox.y0 >= bbox.y1:
        raise ParserValidationError("top-left boxes must have positive area")
    return BBox(
        x0=bbox.x0,
        y0=page_height - bbox.y1,
        x1=bbox.x1,
        y1=page_height - bbox.y0,
    )


def validate_block_provenance(block: ParsedBlock) -> None:
    if block.page_index < 0:
        raise ParserValidationError("block page index must be non-negative")
    if block.page_width <= 0 or block.page_height <= 0:
        raise ParserValidationError("block page dimensions must be positive")
    if block.coordinate_origin != "bottom-left":
        raise ParserValidationError("block coordinates must use bottom-left origin")
    if not block.normalized_text:
        raise ParserValidationError("parsed blocks must contain normalized text")

    expected_start = 0
    for span in block.source_spans:
        if span.page_index != block.page_index:
            raise ParserValidationError("source span page does not match its block")
        if span.text_start != expected_start or span.text_end <= span.text_start:
            raise ParserValidationError("source spans must partition normalized offsets")
        if span.text_end > len(block.normalized_text):
            raise ParserValidationError("source span exceeds normalized text")
        box = span.bbox
        if (
            box.x0 < 0
            or box.y0 < 0
            or box.x1 > block.page_width
            or box.y1 > block.page_height
        ):
            raise ParserValidationError("source box is outside page bounds")
        if box.x0 >= box.x1 or box.y0 >= box.y1:
            raise ParserValidationError("source boxes must have positive area")
        expected_start = span.text_end
    if expected_start != len(block.normalized_text):
        raise ParserValidationError("source spans do not cover every normalized offset")


def _top_left_box(value: Sequence[float]) -> BBox:
    return BBox(x0=float(value[0]), y0=float(value[1]), x1=float(value[2]), y1=float(value[3]))


def _raw_pdf_blocks(path: Path) -> dict[int, list[_RawPdfBlock]]:
    import pymupdf

    blocks_by_page: dict[int, list[_RawPdfBlock]] = defaultdict(list)
    with pymupdf.open(path) as document:
        for page_index, page in enumerate(document):
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            raw_page = page.get_text("rawdict", sort=False)
            for original_number, raw_block in enumerate(raw_page.get("blocks", [])):
                if raw_block.get("type") != 0:
                    continue
                source_runs: list[SourceRun] = []
                max_font_size = 0.0
                combined_flags = 0
                lines = raw_block.get("lines", [])
                for line_index, line in enumerate(lines):
                    line_box = top_left_to_bottom_left_bbox(
                        _top_left_box(line["bbox"]),
                        page_width=page_width,
                        page_height=page_height,
                    )
                    for span in line.get("spans", []):
                        max_font_size = max(max_font_size, float(span.get("size", 0.0)))
                        combined_flags |= int(span.get("flags", 0))
                        for character in span.get("chars", []):
                            value = str(character.get("c", ""))
                            if not value:
                                continue
                            source_runs.append(
                                SourceRun(
                                    text=value,
                                    page_index=page_index,
                                    bbox=top_left_to_bottom_left_bbox(
                                        _top_left_box(character["bbox"]),
                                        page_width=page_width,
                                        page_height=page_height,
                                    ),
                                )
                            )
                    if line_index + 1 < len(lines):
                        source_runs.append(
                            SourceRun(text="\n", page_index=page_index, bbox=line_box)
                        )
                if not source_runs:
                    continue
                blocks_by_page[page_index].append(
                    _RawPdfBlock(
                        page_index=page_index,
                        page_width=page_width,
                        page_height=page_height,
                        top_left_bbox=_top_left_box(raw_block["bbox"]),
                        source_runs=source_runs,
                        max_font_size=max_font_size,
                        flags=combined_flags,
                        original_number=int(raw_block.get("number", original_number)),
                    )
                )
    return blocks_by_page


def _vertical_layout_bands(blocks: Sequence[_RawPdfBlock]) -> list[list[_RawPdfBlock]]:
    ordered = sorted(
        blocks,
        key=lambda block: (
            block.top_left_bbox.y0,
            block.top_left_bbox.x0,
            block.original_number,
        ),
    )
    bands: list[list[_RawPdfBlock]] = []
    current: list[_RawPdfBlock] = []
    current_bottom = 0.0
    for block in ordered:
        if current and block.top_left_bbox.y0 > current_bottom + 18.0:
            bands.append(current)
            current = []
        current.append(block)
        current_bottom = max(current_bottom, block.top_left_bbox.y1)
    if current:
        bands.append(current)
    return bands


def _order_pdf_blocks(blocks: Sequence[_RawPdfBlock]) -> list[_RawPdfBlock]:
    if not blocks:
        return []
    page_width = blocks[0].page_width
    page_middle = page_width / 2.0
    result: list[_RawPdfBlock] = []
    for band in _vertical_layout_bands(blocks):
        left = [block for block in band if block.top_left_bbox.x1 <= page_middle + 8]
        right = [block for block in band if block.top_left_bbox.x0 >= page_middle - 8]
        columnar = bool(left and right and len(left) + len(right) >= len(band) - 1)
        if columnar:
            central = [block for block in band if block not in left and block not in right]
            for group in (left, right, central):
                result.extend(
                    sorted(
                        group,
                        key=lambda block: (
                            block.top_left_bbox.y0,
                            block.top_left_bbox.x0,
                            block.original_number,
                        ),
                    )
                )
        else:
            result.extend(
                sorted(
                    band,
                    key=lambda block: (
                        block.top_left_bbox.y0,
                        block.top_left_bbox.x0,
                        block.original_number,
                    ),
                )
            )
    return result


def _plain_normalize(value: str) -> str:
    if not value:
        return ""
    placeholder = BBox(x0=0, y0=0, x1=1, y1=1)
    return normalize_with_map([SourceRun(text=value, page_index=0, bbox=placeholder)])[0]


def _heading_level(text: str) -> int | None:
    numbered = re.match(r"^(\d+(?:\.\d+)*)\s+\S", text)
    if numbered:
        return numbered.group(1).count(".") + 1
    appendix = re.match(r"^([A-Z](?:\.\d+)*)\s+\S", text)
    if appendix:
        return appendix.group(1).count(".") + 1
    return None


def _block_type(text: str, raw: _RawPdfBlock, heading_level: int | None) -> str:
    if heading_level is not None:
        return "heading"
    if re.match(r"^(Figure|Table)\s+\d+", text, flags=re.IGNORECASE):
        return "caption"
    if raw.max_font_size <= 8.5 and text[:1].isdigit():
        return "footnote"
    return "paragraph"


def _is_page_number(text: str, raw: _RawPdfBlock) -> bool:
    return bool(
        re.fullmatch(r"\d+", text)
        and raw.top_left_bbox.y0 >= raw.page_height * 0.90
    )


def parse_pymupdf(path: str | Path) -> list[ParsedBlock]:
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise ParserValidationError(f"PDF not found: {pdf_path}")

    raw_by_page = _raw_pdf_blocks(pdf_path)
    parsed: list[ParsedBlock] = []
    section_stack: dict[int, str] = {}
    reading_order = 0
    for page_index in sorted(raw_by_page):
        for raw in _order_pdf_blocks(raw_by_page[page_index]):
            normalized_text, source_spans = normalize_with_map(raw.source_runs)
            if not normalized_text or _is_page_number(normalized_text, raw):
                continue
            heading_level = _heading_level(normalized_text)
            if heading_level is not None:
                section_stack = {
                    level: value
                    for level, value in section_stack.items()
                    if level < heading_level
                }
                section_stack[heading_level] = normalized_text
            section_path = [section_stack[level] for level in sorted(section_stack)]
            block = ParsedBlock(
                paper_id=pdf_path.stem,
                page_index=page_index,
                section_path=section_path,
                block_type=_block_type(normalized_text, raw, heading_level),
                reading_order=reading_order,
                normalized_text=normalized_text,
                source_spans=source_spans,
                page_width=raw.page_width,
                page_height=raw.page_height,
                coordinate_origin="bottom-left",
            )
            validate_block_provenance(block)
            parsed.append(block)
            reading_order += 1
    if not parsed:
        raise ParserValidationError(f"PyMuPDF produced no text blocks for {pdf_path}")
    return parsed


def _page_view(blocks: Sequence[ParsedBlock]) -> tuple[str, list[_PageCharacter]]:
    text: list[str] = []
    mapping: list[_PageCharacter] = []
    for block in sorted(blocks, key=lambda item: item.reading_order):
        if text:
            text.append(" ")
            mapping.append(_PageCharacter(bbox=None, block=None))
        per_character: list[BBox | None] = [None] * len(block.normalized_text)
        for span in block.source_spans:
            for offset in range(span.text_start, span.text_end):
                per_character[offset] = span.bbox
        if any(box is None for box in per_character):
            raise ParserValidationError("block has an unmapped normalized character")
        text.extend(block.normalized_text)
        mapping.extend(
            _PageCharacter(bbox=box, block=block) for box in per_character
        )
    return "".join(text), mapping


def _merge_line_boxes(boxes: Sequence[BBox]) -> tuple[BBox, ...]:
    if not boxes:
        return ()
    merged: list[BBox] = []
    for box in boxes:
        if merged:
            previous = merged[-1]
            same_line = abs(previous.y0 - box.y0) <= 2.0 and abs(previous.y1 - box.y1) <= 2.0
            close = box.x0 <= previous.x1 + 3.0 and box.x1 >= previous.x0 - 3.0
            if same_line and close:
                merged[-1] = _union_boxes([previous, box])
                continue
        merged.append(box)
    return tuple(merged)


def resolve_exact_quote(
    blocks: Sequence[ParsedBlock], quote: str
) -> list[QuoteResolution]:
    normalized_quote = _plain_normalize(quote)
    if not normalized_quote:
        raise ParserValidationError("cannot resolve an empty quote")

    by_page: dict[int, list[ParsedBlock]] = defaultdict(list)
    for block in blocks:
        validate_block_provenance(block)
        by_page[block.page_index].append(block)

    resolutions: list[QuoteResolution] = []
    for page_index in sorted(by_page):
        page_text, mapping = _page_view(by_page[page_index])
        search_start = 0
        while True:
            start = page_text.find(normalized_quote, search_start)
            if start < 0:
                break
            end = start + len(normalized_quote)
            source_boxes: list[BBox] = []
            section_counts: Counter[tuple[str, ...]] = Counter()
            for relative_offset, source in enumerate(mapping[start:end]):
                if normalized_quote[relative_offset].isspace():
                    continue
                if source.bbox is not None:
                    source_boxes.append(source.bbox)
                if source.block is not None:
                    section_counts[tuple(source.block.section_path)] += 1
            representative = by_page[page_index][0]
            section_path = section_counts.most_common(1)[0][0] if section_counts else ()
            resolutions.append(
                QuoteResolution(
                    page_index=page_index,
                    page_width=representative.page_width,
                    page_height=representative.page_height,
                    text_start=start,
                    text_end=end,
                    boxes=_merge_line_boxes(source_boxes),
                    section_path=section_path,
                )
            )
            search_start = start + 1
    return resolutions


def ordered_token_lcs_coverage(*, reference: str, candidate: str) -> dict[str, int | float]:
    reference_tokens = _plain_normalize(reference).casefold().split()
    if not reference_tokens:
        raise ParserValidationError("empty coverage reference")
    candidate_tokens = _plain_normalize(candidate).casefold().split()

    previous = [0] * (len(candidate_tokens) + 1)
    for reference_token in reference_tokens:
        current = [0]
        for candidate_index, candidate_token in enumerate(candidate_tokens, start=1):
            if reference_token == candidate_token:
                current.append(previous[candidate_index - 1] + 1)
            else:
                current.append(max(previous[candidate_index], current[-1]))
        previous = current
    numerator = previous[-1]
    denominator = len(reference_tokens)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "score": numerator / denominator,
    }


