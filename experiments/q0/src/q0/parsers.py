from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import psutil
from pydantic import ValidationError

from q0.corpus import load_manifest
from q0.models import (
    ARTIFACT_VERSION,
    BBox,
    EnvironmentResult,
    EvidenceCase,
    ParsedBlock,
    ParserResult,
    ReadingOrderRelation,
    SourceSpan,
    ThresholdOutcome,
    write_json_atomic,
)


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


def _docling_pipeline_options() -> Any:
    os.environ["OMP_NUM_THREADS"] = "4"
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    return PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(num_threads=4),
        allow_external_plugins=False,
        do_ocr=False,
        do_table_structure=True,
        enable_remote_services=False,
    )


def resolved_docling_configuration() -> dict[str, Any]:
    options = _docling_pipeline_options()
    return {
        "version": importlib.metadata.version("docling"),
        "options": {
            "allow_external_plugins": bool(options.allow_external_plugins),
            "do_ocr": bool(options.do_ocr),
            "do_table_structure": bool(options.do_table_structure),
            "enable_remote_services": bool(options.enable_remote_services),
            "num_threads": int(options.accelerator_options.num_threads),
        },
    }


def _docling_page_dimensions(document: Any, page_no: int) -> tuple[float, float]:
    try:
        page = document.pages[page_no]
    except KeyError as error:
        raise ParserValidationError(f"Docling provenance names missing page {page_no}") from error
    width = float(page.size.width)
    height = float(page.size.height)
    if width <= 0 or height <= 0:
        raise ParserValidationError(f"Docling page {page_no} has invalid dimensions")
    return width, height


def _docling_bbox(
    value: Any, *, page_width: float, page_height: float
) -> BBox:
    origin = getattr(value.coord_origin, "value", str(value.coord_origin)).upper()
    if origin == "TOPLEFT":
        return top_left_to_bottom_left_bbox(
            BBox(
                x0=float(value.l),
                y0=float(value.t),
                x1=float(value.r),
                y1=float(value.b),
            ),
            page_width=page_width,
            page_height=page_height,
        )
    if origin == "BOTTOMLEFT":
        box = BBox(
            x0=float(value.l),
            y0=float(value.b),
            x1=float(value.r),
            y1=float(value.t),
        )
        if (
            box.x0 < 0
            or box.y0 < 0
            or box.x1 > page_width
            or box.y1 > page_height
        ):
            raise ParserValidationError(
                f"Docling bottom-left box is outside page bounds {page_width}x{page_height}: {box}"
            )
        if box.x0 >= box.x1 or box.y0 >= box.y1:
            raise ParserValidationError("Docling boxes must have positive area")
        return box
    raise ParserValidationError(f"unsupported Docling coordinate origin: {origin}")


def _docling_text_run_groups(
    *,
    text: str,
    provenance: Sequence[Any],
    document: Any,
) -> list[tuple[int, float, float, list[SourceRun]]]:
    if not provenance:
        raise ParserValidationError("Docling text item has no provenance")
    ordered = sorted(provenance, key=lambda item: (item.charspan[0], item.charspan[1]))
    groups: list[tuple[int, float, float, list[SourceRun]]] = []
    current_page_no: int | None = None
    current_runs: list[SourceRun] | None = None
    previous_box: BBox | None = None
    cursor = 0

    for item in ordered:
        start, end = (int(item.charspan[0]), int(item.charspan[1]))
        if start < cursor or start < 0 or end <= start or end > len(text):
            raise ParserValidationError(
                f"invalid Docling character span {(start, end)} for text length {len(text)}"
            )
        page_no = int(item.page_no)
        page_width, page_height = _docling_page_dimensions(document, page_no)
        page_index = page_no - 1
        if page_index < 0:
            raise ParserValidationError("Docling page numbers must be one-based")
        source_box = _docling_bbox(
            item.bbox,
            page_width=page_width,
            page_height=page_height,
        )

        gap = text[cursor:start]
        if gap.strip():
            raise ParserValidationError(
                "Docling provenance leaves non-whitespace text unmapped"
            )
        if gap and current_runs is not None and previous_box is not None:
            current_runs.append(
                SourceRun(
                    text=gap,
                    page_index=current_page_no - 1,
                    bbox=previous_box,
                )
            )

        if page_no != current_page_no:
            current_page_no = page_no
            current_runs = []
            groups.append((page_index, page_width, page_height, current_runs))
        if gap and previous_box is None:
            current_runs.append(
                SourceRun(text=gap, page_index=page_index, bbox=source_box)
            )
        current_runs.append(
            SourceRun(
                text=text[start:end],
                page_index=page_index,
                bbox=source_box,
            )
        )
        cursor = end
        previous_box = source_box

    if cursor < len(text):
        tail = text[cursor:]
        if tail.strip():
            raise ParserValidationError(
                "Docling provenance leaves trailing non-whitespace text unmapped"
            )
        if current_runs is None or previous_box is None or current_page_no is None:
            raise ParserValidationError("Docling provenance did not map any text")
        current_runs.append(
            SourceRun(
                text=tail,
                page_index=current_page_no - 1,
                bbox=previous_box,
            )
        )
    return groups


def _docling_table_cells(
    *, item: Any, document: Any
) -> list[tuple[int, float, float, SourceRun]]:
    provenance = list(getattr(item, "prov", []))
    if not provenance:
        raise ParserValidationError("Docling table item has no provenance")
    page_no = int(provenance[0].page_no)
    if any(int(value.page_no) != page_no for value in provenance):
        raise ParserValidationError("one Docling table spans multiple pages")
    page_width, page_height = _docling_page_dimensions(document, page_no)
    page_index = page_no - 1
    table_box = _docling_bbox(
        provenance[0].bbox,
        page_width=page_width,
        page_height=page_height,
    )
    cells: list[tuple[int, float, float, SourceRun]] = []
    ordered_cells = sorted(
        item.data.table_cells,
        key=lambda cell: (
            int(cell.start_row_offset_idx),
            int(cell.start_col_offset_idx),
            int(cell.end_row_offset_idx),
            int(cell.end_col_offset_idx),
        ),
    )
    for cell in ordered_cells:
        if not cell.text or not cell.text.strip():
            continue
        cell_box = (
            _docling_bbox(
                cell.bbox,
                page_width=page_width,
                page_height=page_height,
            )
            if cell.bbox is not None
            else table_box
        )
        cells.append(
            (
                page_index,
                page_width,
                page_height,
                SourceRun(text=cell.text, page_index=page_index, bbox=cell_box),
            )
        )
    return cells


def parse_docling(path: str | Path) -> list[ParsedBlock]:
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise ParserValidationError(f"PDF not found: {pdf_path}")

    os.environ["OMP_NUM_THREADS"] = "4"
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = _docling_pipeline_options()
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        },
    )
    result = converter.convert(pdf_path, raises_on_error=False)
    if result.status not in {
        ConversionStatus.SUCCESS,
        ConversionStatus.PARTIAL_SUCCESS,
    }:
        details = "; ".join(str(error) for error in result.errors) or result.status.value
        raise ParserValidationError(f"Docling conversion failed: {details}")
    if result.status == ConversionStatus.PARTIAL_SUCCESS:
        details = "; ".join(str(error) for error in result.errors) or "partial success"
        raise ParserValidationError(f"Docling conversion was incomplete: {details}")

    parsed: list[ParsedBlock] = []
    section_stack: dict[int, str] = {}
    reading_order = 0
    for item, hierarchy_level in result.document.iterate_items(
        with_groups=False,
        traverse_pictures=False,
    ):
        label_value = getattr(getattr(item, "label", None), "value", "")
        if label_value in {"page_header", "page_footer", "picture"}:
            continue

        entries: list[tuple[int, float, float, list[SourceRun], str]] = []
        if label_value == "table":
            for page_index, page_width, page_height, source_run in _docling_table_cells(
                item=item,
                document=result.document,
            ):
                entries.append(
                    (
                        page_index,
                        page_width,
                        page_height,
                        [source_run],
                        "table_cell",
                    )
                )
        else:
            text = str(getattr(item, "text", ""))
            provenance = list(getattr(item, "prov", []))
            if not text.strip() or not provenance:
                continue
            for page_index, page_width, page_height, runs in _docling_text_run_groups(
                text=text,
                provenance=provenance,
                document=result.document,
            ):
                entries.append(
                    (
                        page_index,
                        page_width,
                        page_height,
                        runs,
                        label_value or "text",
                    )
                )

        for page_index, page_width, page_height, runs, block_type in entries:
            normalized_text, source_spans = normalize_with_map(runs)
            if not normalized_text:
                continue
            heading_level = (
                _heading_level(normalized_text)
                if block_type in {"section_header", "title", "text"}
                else None
            )
            if block_type == "section_header" and heading_level is None:
                heading_level = max(1, int(hierarchy_level))
            if heading_level is not None:
                section_stack = {
                    level: value
                    for level, value in section_stack.items()
                    if level < heading_level
                }
                section_stack[heading_level] = normalized_text
            block = ParsedBlock(
                paper_id=pdf_path.stem,
                page_index=page_index,
                section_path=[
                    section_stack[level] for level in sorted(section_stack)
                ],
                block_type=block_type,
                reading_order=reading_order,
                normalized_text=normalized_text,
                source_spans=source_spans,
                page_width=page_width,
                page_height=page_height,
                coordinate_origin="bottom-left",
            )
            validate_block_provenance(block)
            parsed.append(block)
            reading_order += 1
    if not parsed:
        raise ParserValidationError(f"Docling produced no provenance blocks for {pdf_path}")
    return parsed


def _gate_outcome(
    passed: bool,
    *,
    requirement: str,
    observed: Any,
) -> dict[str, Any]:
    return {
        "passed": passed,
        "requirement": requirement,
        "observed": observed,
        "failure_reason": None if passed else f"observed {observed!r}",
    }


def parser_gate_outcomes(measurements: dict[str, Any]) -> dict[str, dict[str, Any]]:
    coverage = list(measurements.get("coverage", []))
    reading_order = dict(measurements.get("reading_order", {}))
    outcomes = {
        "successful_parsing": _gate_outcome(
            measurements.get("successful_papers") == 2,
            requirement="both fixed corpus PDFs parse successfully",
            observed=measurements.get("successful_papers"),
        ),
        "page_correctness": _gate_outcome(
            measurements.get("answerable_case_count") == 8
            and measurements.get("page_correct_case_count") == 8,
            requirement="all 8 answerable cases resolve to the expected page",
            observed={
                "answerable": measurements.get("answerable_case_count"),
                "page_correct": measurements.get("page_correct_case_count"),
            },
        ),
        "geometry": _gate_outcome(
            measurements.get("answerable_case_count") == 8
            and measurements.get("geometry_case_count") == 8,
            requirement="every answerable case resolves to non-empty source boxes",
            observed={
                "answerable": measurements.get("answerable_case_count"),
                "with_geometry": measurements.get("geometry_case_count"),
            },
        ),
        "coverage_each_fixed_page": _gate_outcome(
            len(coverage) == 2
            and all(float(item.get("score", 0.0)) >= 0.90 for item in coverage),
            requirement="normalized token LCS coverage is at least 0.90 on each of 2 fixed pages",
            observed=[item.get("score") for item in coverage],
        ),
        "reading_order": _gate_outcome(
            reading_order.get("total") == 12
            and int(reading_order.get("correct", 0)) >= 10,
            requirement="at least 10 of 12 frozen reading-order relations are correct",
            observed=reading_order,
        ),
        "golden_region": _gate_outcome(
            bool(dict(measurements.get("golden_region", {})).get("passed")),
            requirement="golden evidence overlaps every annotated region in the correct column",
            observed=measurements.get("golden_region"),
        ),
        "reversible_offsets": _gate_outcome(
            measurements.get("reversible_offsets") is True,
            requirement="every normalized character has reversible source provenance",
            observed=measurements.get("reversible_offsets"),
        ),
    }
    qualified = all(outcome["passed"] for outcome in outcomes.values())
    outcomes["qualified"] = _gate_outcome(
        qualified,
        requirement="candidate passes every parser provenance threshold",
        observed={name: outcome["passed"] for name, outcome in outcomes.items()},
    )
    return outcomes


PARSER_CANDIDATES = ("pymupdf", "docling")


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
        raise ParserValidationError(
            f"git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout.strip()


def _load_environment(root: Path, run_id: str) -> EnvironmentResult:
    path = root / "qualification" / "results" / run_id / "environment.json"
    try:
        environment = EnvironmentResult.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except FileNotFoundError as error:
        raise ParserValidationError(f"run environment not found: {path}") from error
    except (OSError, ValidationError) as error:
        raise ParserValidationError(f"invalid run environment {path}: {error}") from error
    if environment.run_id != run_id:
        raise ParserValidationError(
            f"environment run ID {environment.run_id!r} does not match {run_id!r}"
        )
    return environment


def _require_clean_producer(root: Path) -> str:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if status:
        raise ParserValidationError(
            "tracked tree must be clean before parser measurement"
        )
    return _git(root, "rev-parse", "HEAD")


def _write_jsonl_atomic(path: Path, blocks: Sequence[ParsedBlock]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = "".join(
        block.model_dump_json(exclude_none=False) + "\n" for block in blocks
    ).encode("utf-8")
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
    return hashlib.sha256(encoded).hexdigest()


def load_parsed_blocks(path: Path) -> list[ParsedBlock]:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ParserValidationError(f"cannot read parsed-block stream {path}: {error}") from error
    blocks: list[ParsedBlock] = []
    for line_number, line in enumerate(contents.splitlines(), start=1):
        if not line.strip():
            raise ParserValidationError(
                f"blank record in parsed-block stream {path}:{line_number}"
            )
        try:
            block = ParsedBlock.model_validate_json(line)
        except ValidationError as error:
            raise ParserValidationError(
                f"invalid ParsedBlock in {path}:{line_number}: {error}"
            ) from error
        validate_block_provenance(block)
        blocks.append(block)
    return blocks


def _process_tree_rss(process: psutil.Process) -> int:
    total = 0
    try:
        processes = [process, *process.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        processes = [process]
    for item in processes:
        try:
            total += int(item.memory_info().rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


class _PeakMemoryMonitor:
    def __init__(self) -> None:
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._sample,
            name="q0-parser-peak-memory",
            daemon=True,
        )
        self.baseline_bytes = _process_tree_rss(self._process)
        self.peak_bytes = self.baseline_bytes

    def _sample(self) -> None:
        while not self._stop.wait(0.01):
            self.peak_bytes = max(
                self.peak_bytes,
                _process_tree_rss(self._process),
            )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.peak_bytes = max(self.peak_bytes, _process_tree_rss(self._process))
        self._stop.set()
        self._thread.join(timeout=1)


def _candidate_identity(candidate: str) -> dict[str, Any]:
    if candidate == "pymupdf":
        return {
            "candidate": candidate,
            "version": importlib.metadata.version("pymupdf"),
            "adapter": "TextPage raw spans and characters with explicit geometry ordering",
        }
    if candidate == "docling":
        configuration = resolved_docling_configuration()
        return {
            "candidate": candidate,
            "version": configuration["version"],
            "options": configuration["options"],
        }
    raise ParserValidationError(
        f"candidate must be one of {PARSER_CANDIDATES}, observed {candidate!r}"
    )


def _candidate_parser(candidate: str) -> Any:
    if candidate == "pymupdf":
        return parse_pymupdf
    if candidate == "docling":
        return parse_docling
    raise ParserValidationError(
        f"candidate must be one of {PARSER_CANDIDATES}, observed {candidate!r}"
    )


def run_parser_candidate(
    *, root: Path, run_id: str, candidate: str
) -> dict[str, Any]:
    root = root.resolve()
    environment = _load_environment(root, run_id)
    producer_revision = _require_clean_producer(root)
    manifest = load_manifest(root)
    parser = _candidate_parser(candidate)
    identity = _candidate_identity(candidate)
    private_directory = root / "qualification" / "private" / run_id
    stream_path = private_directory / f"parsed-blocks-{candidate}.jsonl"
    metadata_path = private_directory / f"parser-run-{candidate}.json"

    monitor = _PeakMemoryMonitor()
    all_blocks: list[ParsedBlock] = []
    paper_results: list[dict[str, Any]] = []
    candidate_started = time.perf_counter()
    monitor.start()
    try:
        for paper in manifest.papers:
            pdf_path = (
                root
                / "qualification"
                / ".cache"
                / "pdfs"
                / f"{paper.paper_id}.pdf"
            )
            paper_started = time.perf_counter()
            try:
                if not pdf_path.is_file():
                    raise ParserValidationError(f"cached PDF not found: {pdf_path}")
                pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
                if pdf_sha256 != paper.sha256:
                    raise ParserValidationError(
                        f"cached PDF hash mismatch for {paper.paper_id}"
                    )
                blocks = parser(pdf_path)
                if any(block.paper_id != paper.paper_id for block in blocks):
                    raise ParserValidationError(
                        f"{candidate} emitted the wrong paper identity for {paper.paper_id}"
                    )
                if any(
                    block.page_index < 0 or block.page_index >= paper.page_count
                    for block in blocks
                ):
                    raise ParserValidationError(
                        f"{candidate} emitted an out-of-range page for {paper.paper_id}"
                    )
                for block in blocks:
                    validate_block_provenance(block)
                all_blocks.extend(blocks)
                paper_results.append(
                    {
                        "paper_id": paper.paper_id,
                        "status": "success",
                        "block_count": len(blocks),
                        "normalized_character_count": sum(
                            len(block.normalized_text) for block in blocks
                        ),
                        "latency_seconds": time.perf_counter() - paper_started,
                        "failure_type": None,
                        "failure_message": None,
                    }
                )
            except Exception as error:
                paper_results.append(
                    {
                        "paper_id": paper.paper_id,
                        "status": "failed",
                        "block_count": 0,
                        "normalized_character_count": 0,
                        "latency_seconds": time.perf_counter() - paper_started,
                        "failure_type": type(error).__name__,
                        "failure_message": str(error)[:1000],
                    }
                )
    finally:
        monitor.stop()

    latency_seconds = time.perf_counter() - candidate_started
    stream_sha256 = _write_jsonl_atomic(stream_path, all_blocks)
    successful_papers = sum(
        result["status"] == "success" for result in paper_results
    )
    metadata: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "candidate": candidate,
        "producer_git_revision": producer_revision,
        "run_initialized_git_revision": environment.run_initialized_git_revision,
        "tracked_tree_clean": True,
        "identity": identity,
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "paper_results": paper_results,
        "successful_papers": successful_papers,
        "latency_seconds": latency_seconds,
        "peak_memory_bytes": monitor.peak_bytes,
        "peak_memory_delta_bytes": max(
            0, monitor.peak_bytes - monitor.baseline_bytes
        ),
        "stream_relative_path": str(stream_path.relative_to(root)),
        "stream_sha256": stream_sha256,
        "stream_record_count": len(all_blocks),
    }
    write_json_atomic(metadata_path, metadata)
    return metadata


def _load_candidate_run(
    *, root: Path, run_id: str, candidate: str
) -> tuple[dict[str, Any], list[ParsedBlock]]:
    private_directory = root / "qualification" / "private" / run_id
    metadata_path = private_directory / f"parser-run-{candidate}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ParserValidationError(
            f"candidate run metadata not found: {metadata_path}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ParserValidationError(
            f"invalid candidate run metadata {metadata_path}: {error}"
        ) from error
    if (
        metadata.get("run_id") != run_id
        or metadata.get("candidate") != candidate
    ):
        raise ParserValidationError(
            f"candidate run identity mismatch in {metadata_path}"
        )
    stream_path = root / str(metadata.get("stream_relative_path", ""))
    blocks = load_parsed_blocks(stream_path)
    actual_sha256 = hashlib.sha256(stream_path.read_bytes()).hexdigest()
    if actual_sha256 != metadata.get("stream_sha256"):
        raise ParserValidationError(
            f"candidate stream hash mismatch for {candidate}"
        )
    if len(blocks) != metadata.get("stream_record_count"):
        raise ParserValidationError(
            f"candidate stream record-count mismatch for {candidate}"
        )
    return metadata, blocks


def _load_evidence(root: Path) -> list[EvidenceCase]:
    path = root / "qualification" / "gold" / "evidence.jsonl"
    evidence: list[EvidenceCase] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            try:
                evidence.append(EvidenceCase.model_validate_json(line))
            except ValidationError as error:
                raise ParserValidationError(
                    f"invalid evidence case {path}:{line_number}: {error}"
                ) from error
    except OSError as error:
        raise ParserValidationError(f"cannot read evidence gold {path}: {error}") from error
    return evidence


def _load_relations(root: Path) -> list[ReadingOrderRelation]:
    path = root / "qualification" / "gold" / "reading-order.jsonl"
    relations: list[ReadingOrderRelation] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            try:
                relations.append(ReadingOrderRelation.model_validate_json(line))
            except ValidationError as error:
                raise ParserValidationError(
                    f"invalid reading-order relation {path}:{line_number}: {error}"
                ) from error
    except OSError as error:
        raise ParserValidationError(
            f"cannot read reading-order gold {path}: {error}"
        ) from error
    return relations


def _all_occurrences(text: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while needle:
        found = text.find(needle, start)
        if found < 0:
            break
        positions.append(found)
        start = found + 1
    return positions


def _bbox_values(box: BBox) -> dict[str, float]:
    return {
        "x0": box.x0,
        "y0": box.y0,
        "x1": box.x1,
        "y1": box.y1,
    }


def _quote_measurement(
    *,
    blocks: Sequence[ParsedBlock],
    quote: str,
    expected_page: int,
    expected_section: str,
) -> dict[str, Any]:
    resolutions = resolve_exact_quote(blocks, quote)
    expected = [
        resolution
        for resolution in resolutions
        if resolution.page_index == expected_page
    ]
    representative = expected[0] if expected else None
    section_correct = any(
        expected_section in resolution.section_path for resolution in expected
    )
    return {
        "quote_sha256": hashlib.sha256(
            _plain_normalize(quote).encode("utf-8")
        ).hexdigest(),
        "occurrence_count": len(resolutions),
        "resolved_pages": sorted({resolution.page_index for resolution in resolutions}),
        "expected_page": expected_page,
        "page_correct": bool(expected),
        "geometry_resolved": bool(
            expected and all(resolution.boxes for resolution in expected)
        ),
        "resolved_boxes": (
            [_bbox_values(box) for box in representative.boxes]
            if representative is not None
            else []
        ),
        "section_path": (
            list(representative.section_path)
            if representative is not None
            else []
        ),
        "expected_section": expected_section,
        "section_correct": section_correct,
    }


def _evidence_measurements(
    *,
    blocks: Sequence[ParsedBlock],
    evidence: Sequence[EvidenceCase],
) -> tuple[list[dict[str, Any]], int, int, int]:
    blocks_by_paper: dict[str, list[ParsedBlock]] = defaultdict(list)
    for block in blocks:
        blocks_by_paper[block.paper_id].append(block)

    case_results: list[dict[str, Any]] = []
    page_correct_count = 0
    geometry_count = 0
    section_count = 0
    for case in evidence:
        if not case.answerable:
            continue
        if case.page_index is None or case.expected_section is None:
            raise ParserValidationError(
                f"answerable case {case.case_id} lacks a page or section"
            )
        quote_results = [
            _quote_measurement(
                blocks=blocks_by_paper[case.paper_id],
                quote=quote,
                expected_page=case.page_index,
                expected_section=case.expected_section,
            )
            for quote in case.quotes
        ]
        page_correct = bool(quote_results) and all(
            result["page_correct"] for result in quote_results
        )
        geometry_resolved = bool(quote_results) and all(
            result["geometry_resolved"] for result in quote_results
        )
        section_correct = bool(quote_results) and all(
            result["section_correct"] for result in quote_results
        )
        page_correct_count += int(page_correct)
        geometry_count += int(geometry_resolved)
        section_count += int(section_correct)
        case_results.append(
            {
                "case_id": case.case_id,
                "paper_id": case.paper_id,
                "expected_page": case.page_index,
                "page_correct": page_correct,
                "geometry_resolved": geometry_resolved,
                "expected_section": case.expected_section,
                "section_correct": section_correct,
                "quotes": quote_results,
            }
        )
    return case_results, page_correct_count, geometry_count, section_count


def _coverage_measurements(
    *,
    blocks: Sequence[ParsedBlock],
    evidence: Sequence[EvidenceCase],
) -> list[dict[str, Any]]:
    page_blocks: dict[tuple[str, int], list[ParsedBlock]] = defaultdict(list)
    for block in blocks:
        page_blocks[(block.paper_id, block.page_index)].append(block)
    measurements: list[dict[str, Any]] = []
    for case in evidence:
        if case.coverage_reference_text is None:
            continue
        if case.page_index is None:
            raise ParserValidationError(
                f"coverage case {case.case_id} has no page"
            )
        candidate_text, _ = _page_view(
            page_blocks[(case.paper_id, case.page_index)]
        )
        score = ordered_token_lcs_coverage(
            reference=case.coverage_reference_text,
            candidate=candidate_text,
        )
        measurements.append(
            {
                "case_id": case.case_id,
                "paper_id": case.paper_id,
                "page_index": case.page_index,
                **score,
            }
        )
    return measurements


def _reading_order_measurements(
    *,
    blocks: Sequence[ParsedBlock],
    relations: Sequence[ReadingOrderRelation],
) -> dict[str, Any]:
    page_blocks: dict[tuple[str, int], list[ParsedBlock]] = defaultdict(list)
    for block in blocks:
        page_blocks[(block.paper_id, block.page_index)].append(block)
    outcomes: list[dict[str, Any]] = []
    for relation in relations:
        page_text, _ = _page_view(
            page_blocks[(relation.paper_id, relation.page_index)]
        )
        before = _plain_normalize(relation.before_anchor)
        after = _plain_normalize(relation.after_anchor)
        before_positions = _all_occurrences(page_text, before)
        after_positions = _all_occurrences(page_text, after)
        correct = (
            len(before_positions) == 1
            and len(after_positions) == 1
            and before_positions[0] < after_positions[0]
        )
        outcomes.append(
            {
                "relation_id": relation.relation_id,
                "paper_id": relation.paper_id,
                "page_index": relation.page_index,
                "before_occurrences": len(before_positions),
                "after_occurrences": len(after_positions),
                "before_start": (
                    before_positions[0] if len(before_positions) == 1 else None
                ),
                "after_start": (
                    after_positions[0] if len(after_positions) == 1 else None
                ),
                "correct": correct,
            }
        )
    return {
        "correct": sum(outcome["correct"] for outcome in outcomes),
        "total": len(outcomes),
        "relations": outcomes,
    }


def _intersection_area(left: BBox, right: BBox) -> float:
    return max(0.0, min(left.x1, right.x1) - max(left.x0, right.x0)) * max(
        0.0, min(left.y1, right.y1) - max(left.y0, right.y0)
    )


def _golden_region_measurement(
    *,
    blocks: Sequence[ParsedBlock],
    evidence: Sequence[EvidenceCase],
) -> dict[str, Any]:
    golden = next(
        case for case in evidence if case.case_id == "1706.03762-answer-1"
    )
    if golden.page_index is None or not golden.expected_boxes:
        raise ParserValidationError("golden evidence lacks page geometry")
    paper_blocks = [
        block for block in blocks if block.paper_id == golden.paper_id
    ]
    resolutions = [
        resolution
        for resolution in resolve_exact_quote(paper_blocks, golden.quotes[0])
        if resolution.page_index == golden.page_index
    ]
    if not resolutions:
        return {
            "case_id": golden.case_id,
            "expected_page": golden.page_index,
            "resolved": False,
            "resolved_box_count": 0,
            "expected_region_count": len(golden.expected_boxes),
            "regions_overlapped": 0,
            "inside_annotated_region": False,
            "correct_column": False,
            "passed": False,
        }
    source_boxes = list(resolutions[0].boxes)
    region_hits = [
        any(_intersection_area(source, expected) > 0 for source in source_boxes)
        for expected in golden.expected_boxes
    ]
    inside = bool(source_boxes) and all(
        any(
            _intersection_area(source, expected)
            >= 0.5 * (source.x1 - source.x0) * (source.y1 - source.y0)
            for expected in golden.expected_boxes
        )
        for source in source_boxes
    )
    region_x0 = min(box.x0 for box in golden.expected_boxes)
    region_x1 = max(box.x1 for box in golden.expected_boxes)
    correct_column = bool(source_boxes) and all(
        source.x0 >= region_x0 - 2.0 and source.x1 <= region_x1 + 2.0
        for source in source_boxes
    )
    passed = all(region_hits) and inside and correct_column
    return {
        "case_id": golden.case_id,
        "expected_page": golden.page_index,
        "resolved": True,
        "resolved_box_count": len(source_boxes),
        "resolved_boxes": [_bbox_values(box) for box in source_boxes],
        "expected_region_count": len(golden.expected_boxes),
        "regions_overlapped": sum(region_hits),
        "inside_annotated_region": inside,
        "correct_column": correct_column,
        "passed": passed,
    }


def _block_bbox(block: ParsedBlock) -> BBox:
    return _union_boxes([span.bbox for span in block.source_spans])


def _header_footer_leakage(blocks: Sequence[ParsedBlock]) -> dict[str, Any]:
    candidates: list[tuple[str, int, int, str]] = []
    for block in blocks:
        box = _block_bbox(block)
        in_margin = box.y0 <= block.page_height * 0.05 or box.y1 >= block.page_height * 0.95
        if not in_margin:
            continue
        fingerprint = re.sub(
            r"\d+",
            "#",
            block.normalized_text.casefold(),
        )
        candidates.append(
            (block.paper_id, block.page_index, block.reading_order, fingerprint)
        )
    pages_by_fingerprint: dict[tuple[str, str], set[int]] = defaultdict(set)
    for paper_id, page_index, _, fingerprint in candidates:
        pages_by_fingerprint[(paper_id, fingerprint)].add(page_index)
    leaked = [
        {
            "paper_id": paper_id,
            "page_index": page_index,
            "reading_order": reading_order,
            "fingerprint_sha256": hashlib.sha256(
                fingerprint.encode("utf-8")
            ).hexdigest(),
        }
        for paper_id, page_index, reading_order, fingerprint in candidates
        if len(pages_by_fingerprint[(paper_id, fingerprint)]) >= 2
    ]
    return {
        "count": len(leaked),
        "blocks": leaked,
    }


def _candidate_measurements(
    *,
    metadata: dict[str, Any],
    blocks: Sequence[ParsedBlock],
    evidence: Sequence[EvidenceCase],
    relations: Sequence[ReadingOrderRelation],
) -> dict[str, Any]:
    case_results, page_correct_count, geometry_count, section_count = (
        _evidence_measurements(blocks=blocks, evidence=evidence)
    )
    coverage = _coverage_measurements(blocks=blocks, evidence=evidence)
    reading_order = _reading_order_measurements(
        blocks=blocks,
        relations=relations,
    )
    golden_region = _golden_region_measurement(
        blocks=blocks,
        evidence=evidence,
    )
    leakage = _header_footer_leakage(blocks)
    successful_papers = int(metadata.get("successful_papers", 0))
    measurements: dict[str, Any] = {
        "successful_papers": successful_papers,
        "paper_results": metadata.get("paper_results", []),
        "stream_record_count": len(blocks),
        "stream_sha256": metadata.get("stream_sha256"),
        "stream_relative_path": metadata.get("stream_relative_path"),
        "stream_validated_as_parsed_block": True,
        "answerable_case_count": len(case_results),
        "page_correct_case_count": page_correct_count,
        "geometry_case_count": geometry_count,
        "expected_section_case_count": len(case_results),
        "section_correct_case_count": section_count,
        "cases": case_results,
        "coverage": coverage,
        "reading_order": reading_order,
        "golden_region": golden_region,
        "header_footer_leakage": leakage,
        "reversible_offsets": True,
        "latency_seconds": metadata.get("latency_seconds"),
        "peak_memory_bytes": metadata.get("peak_memory_bytes"),
        "peak_memory_delta_bytes": metadata.get("peak_memory_delta_bytes"),
    }
    measurements["gate"] = parser_gate_outcomes(measurements)
    return measurements


def _selection_key(candidate: str, measurement: dict[str, Any]) -> tuple[Any, ...]:
    coverage_scores = [
        float(item["score"]) for item in measurement.get("coverage", [])
    ]
    return (
        bool(measurement["gate"]["reversible_offsets"]["passed"]),
        bool(measurement["gate"]["golden_region"]["passed"]),
        min(coverage_scores, default=0.0),
        int(measurement["reading_order"]["correct"]),
        int(measurement["section_correct_case_count"]),
        -int(measurement["header_footer_leakage"]["count"]),
        1 if candidate == "pymupdf" else 0,
        -int(measurement.get("peak_memory_bytes") or 0),
        -float(measurement.get("latency_seconds") or 0.0),
    )


def evaluate_parser_candidates(*, root: Path, run_id: str) -> ParserResult:
    root = root.resolve()
    environment = _load_environment(root, run_id)
    current_revision = _require_clean_producer(root)
    evidence = _load_evidence(root)
    relations = _load_relations(root)
    if sum(case.answerable for case in evidence) != 8 or len(relations) != 12:
        raise ParserValidationError(
            "parser evaluation requires exactly 8 answerable cases and 12 relations"
        )

    measurements_by_candidate: dict[str, dict[str, Any]] = {}
    identities: dict[str, Any] = {}
    producer_revisions: set[str] = set()
    candidate_failures: list[str] = []
    for candidate in PARSER_CANDIDATES:
        metadata, blocks = _load_candidate_run(
            root=root,
            run_id=run_id,
            candidate=candidate,
        )
        producer_revision = str(metadata.get("producer_git_revision", ""))
        producer_revisions.add(producer_revision)
        if producer_revision != current_revision:
            raise ParserValidationError(
                f"{candidate} was produced by {producer_revision}, current revision is {current_revision}"
            )
        if (
            metadata.get("run_initialized_git_revision")
            != environment.run_initialized_git_revision
        ):
            raise ParserValidationError(
                f"{candidate} run-initialized revision does not match environment"
            )
        identities[candidate] = metadata.get("identity", {})
        measurements = _candidate_measurements(
            metadata=metadata,
            blocks=blocks,
            evidence=evidence,
            relations=relations,
        )
        measurements_by_candidate[candidate] = measurements
        for paper_result in metadata.get("paper_results", []):
            if paper_result.get("status") != "success":
                candidate_failures.append(
                    f"{candidate}/{paper_result.get('paper_id')}: "
                    f"{paper_result.get('failure_type')}: "
                    f"{paper_result.get('failure_message')}"
                )
    if producer_revisions != {current_revision}:
        raise ParserValidationError(
            f"candidate producer revisions differ: {sorted(producer_revisions)}"
        )

    qualified = [
        candidate
        for candidate in PARSER_CANDIDATES
        if measurements_by_candidate[candidate]["gate"]["qualified"]["passed"]
    ]
    selected_candidate = (
        max(
            qualified,
            key=lambda candidate: _selection_key(
                candidate,
                measurements_by_candidate[candidate],
            ),
        )
        if qualified
        else None
    )
    selection_ranking = sorted(
        qualified,
        key=lambda candidate: _selection_key(
            candidate,
            measurements_by_candidate[candidate],
        ),
        reverse=True,
    )

    threshold_outcomes: dict[str, ThresholdOutcome] = {}
    for candidate in PARSER_CANDIDATES:
        gate = measurements_by_candidate[candidate]["gate"]
        passed = bool(gate["qualified"]["passed"])
        threshold_outcomes[f"{candidate}_qualified"] = ThresholdOutcome(
            passed=passed,
            requirement="candidate passes every parser gate in specification section 6.3",
            observed={
                name: outcome["passed"]
                for name, outcome in gate.items()
                if name != "qualified"
            },
            failure_reason=None if passed else gate["qualified"]["failure_reason"],
        )
    threshold_outcomes["parser_selected"] = ThresholdOutcome(
        passed=selected_candidate is not None,
        requirement="select only a parser candidate passing every section 6.3 threshold",
        observed=selected_candidate,
        failure_reason=(
            None
            if selected_candidate is not None
            else "neither PyMuPDF geometry-first nor Docling passed the complete parser gate"
        ),
    )

    failure_reasons = list(candidate_failures)
    if selected_candidate is None:
        failure_reasons.append(
            "neither parser candidate passed every specification section 6.3 threshold"
        )
    result = ParserResult(
        run_id=run_id,
        selected_candidate=selected_candidate,
        identities={
            "producer_git_revision": current_revision,
            "run_initialized_git_revision": environment.run_initialized_git_revision,
            "tracked_tree_clean_before_measurement": True,
            "coordinate_origin": "bottom-left",
            "candidates": list(PARSER_CANDIDATES),
            "candidate_identities": identities,
        },
        measurements={
            "candidates": measurements_by_candidate,
            "selection": {
                "qualified_candidates": qualified,
                "ranking": selection_ranking,
                "selected_candidate": selected_candidate,
                "tie_break_order": [
                    "provenance correctness",
                    "fixed-page text coverage",
                    "reading order and sections",
                    "implementation simplicity",
                    "peak memory",
                    "latency",
                ],
            },
        },
        threshold_outcomes=threshold_outcomes,
        failure_reasons=failure_reasons,
    )
    output_path = (
        root
        / "qualification"
        / "results"
        / run_id
        / "parser.json"
    )
    write_json_atomic(output_path, result)
    return result
