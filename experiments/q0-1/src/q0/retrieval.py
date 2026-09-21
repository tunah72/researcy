from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from pydantic import BaseModel, ConfigDict

from q0.models import ParsedBlock, SourceSpan



class VectorValidationError(ValueError):
    pass


class RetrievalValidationError(ValueError):
    pass


def validate_vector(
    vector: Sequence[float],
    expected_dimension: int | None = None,
) -> list[float]:
    if not isinstance(vector, (list, tuple)):
        raise VectorValidationError("vector must be a sequence of floats")
    if expected_dimension is not None and len(vector) != expected_dimension:
        raise VectorValidationError(
            f"vector dimension {len(vector)} does not match expected {expected_dimension}"
        )
    for x in vector:
        if math.isnan(x) or math.isinf(x):
            raise VectorValidationError("vector contains non-finite values (NaN or Inf)")
    if all(x == 0.0 for x in vector):
        raise VectorValidationError("vector cannot be all zeros")
    return list(vector)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    paper_id: str
    section_path: list[str]
    heading: str | None = None
    page_indices: list[int]
    block_indices: list[int]
    text: str
    source_spans: list[SourceSpan]


def build_chunks(
    blocks: Sequence[ParsedBlock],
    max_chars: int = 2000,
) -> list[Chunk]:
    if not blocks:
        return []

    chunks: list[Chunk] = []
    chunk_counts_by_paper: dict[str, int] = defaultdict(int)
    current_blocks: list[ParsedBlock] = []

    def flush() -> None:
        nonlocal current_blocks
        if not current_blocks:
            return
        paper_id = current_blocks[0].paper_id
        section_path = list(current_blocks[0].section_path)
        heading = section_path[-1] if section_path else None

        combined_text_parts: list[str] = []
        combined_spans: list[SourceSpan] = []
        page_indices_set: set[int] = set()
        block_indices: list[int] = []

        current_offset = 0
        for i, b in enumerate(current_blocks):
            if i > 0:
                combined_text_parts.append("\n\n")
                current_offset += 2
            combined_text_parts.append(b.normalized_text)
            for span in b.source_spans:
                combined_spans.append(
                    SourceSpan(
                        text_start=span.text_start + current_offset,
                        text_end=span.text_end + current_offset,
                        page_index=span.page_index,
                        bbox=span.bbox,
                    )
                )
            current_offset += len(b.normalized_text)
            page_indices_set.add(b.page_index)
            block_indices.append(b.reading_order)

        full_text = "".join(combined_text_parts)
        chunk_idx = chunk_counts_by_paper[paper_id]
        chunk_counts_by_paper[paper_id] += 1

        chunks.append(
            Chunk(
                chunk_id=f"{paper_id}-chunk-{chunk_idx:04d}",
                paper_id=paper_id,
                section_path=section_path,
                heading=heading,
                page_indices=sorted(page_indices_set),
                block_indices=block_indices,
                text=full_text,
                source_spans=combined_spans,
            )
        )
        current_blocks = []

    for b in blocks:
        if current_blocks and (
            current_blocks[0].paper_id != b.paper_id
            or current_blocks[0].section_path != b.section_path
        ):
            flush()

        if not current_blocks:
            current_len = 0
        else:
            current_len = sum(len(x.normalized_text) for x in current_blocks) + 2 * (
                len(current_blocks) - 1
            )

        needed = (2 if current_blocks else 0) + len(b.normalized_text)
        if current_blocks and (current_len + needed > max_chars):
            flush()

        if len(b.normalized_text) <= max_chars:
            current_blocks.append(b)
        else:
            # Single block exceeds max_chars; split into sub-chunks
            text = b.normalized_text
            start = 0
            while start < len(text):
                end = min(start + max_chars, len(text))
                slice_text = text[start:end]
                slice_spans = [
                    SourceSpan(
                        text_start=s.text_start - start,
                        text_end=s.text_end - start,
                        page_index=s.page_index,
                        bbox=s.bbox,
                    )
                    for s in b.source_spans
                    if s.text_start >= start and s.text_end <= end
                ]
                paper_id = b.paper_id
                section_path = list(b.section_path)
                heading = section_path[-1] if section_path else None
                chunk_idx = chunk_counts_by_paper[paper_id]
                chunk_counts_by_paper[paper_id] += 1
                chunks.append(
                    Chunk(
                        chunk_id=f"{paper_id}-chunk-{chunk_idx:04d}",
                        paper_id=paper_id,
                        section_path=section_path,
                        heading=heading,
                        page_indices=[b.page_index],
                        block_indices=[b.reading_order],
                        text=slice_text,
                        source_spans=slice_spans,
                    )
                )
                start = end

    flush()
    return chunks


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_1: float
    recall_at_5: float
    mrr: float
    first_relevant_ranks: list[int | None] = field(default_factory=list)
    hits_at_1: list[float] = field(default_factory=list)
    hits_at_5: list[float] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)


def retrieval_metrics(
    ranked_source_ids: Sequence[Sequence[str]],
    relevant_source_ids: Sequence[set[str]],
    k_values: Sequence[int] = (1, 5),
) -> RetrievalMetrics:
    if len(ranked_source_ids) != len(relevant_source_ids):
        raise ValueError(
            "ranked_source_ids and relevant_source_ids must have the same length"
        )
    if not ranked_source_ids:
        return RetrievalMetrics(
            recall_at_1=0.0,
            recall_at_5=0.0,
            mrr=0.0,
        )

    first_ranks: list[int | None] = []
    hits_1: list[float] = []
    hits_5: list[float] = []
    rrs: list[float] = []

    for ranked, relevant in zip(ranked_source_ids, relevant_source_ids):
        found_rank: int | None = None
        for rank, source_id in enumerate(ranked, start=1):
            if source_id in relevant:
                found_rank = rank
                break
        first_ranks.append(found_rank)
        if found_rank is not None:
            rrs.append(1.0 / found_rank)
            hits_1.append(1.0 if found_rank <= 1 else 0.0)
            hits_5.append(1.0 if found_rank <= 5 else 0.0)
        else:
            rrs.append(0.0)
            hits_1.append(0.0)
            hits_5.append(0.0)

    n = len(ranked_source_ids)
    return RetrievalMetrics(
        recall_at_1=sum(hits_1) / n,
        recall_at_5=sum(hits_5) / n,
        mrr=sum(rrs) / n,
        first_relevant_ranks=first_ranks,
        hits_at_1=hits_1,
        hits_at_5=hits_5,
        reciprocal_ranks=rrs,
    )


