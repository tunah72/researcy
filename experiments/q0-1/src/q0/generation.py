from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, cast

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from q0.corpus import normalize_text
from q0.hybrid import SELECTED_CONFIGURATION
from q0.models import (
    Citation,
    EnvironmentResult,
    GenerationResult,
    GroundedAnswer,
    ThresholdOutcome,
    write_json_atomic,
)

PINNED_BASE_URL = "http://127.0.0.1:20128/v1"
PINNED_MODEL = "gc/gemini-2.5-flash"
PINNED_GATEWAY_VERSION = "0.5.81"
PINNED_CONNECTION_ID = "2386766d-a7c1-4839-953c-deaeaa10e719"
PINNED_UPSTREAM_IDENTITY = "gemini-cli/gemini-2.5-flash"
PRIVATE_ARTIFACT_VERSION = "q0.1-generation-private-1"
_GENERATION_ENVIRONMENT_NAMES = (
    "GENERATION_BASE_URL",
    "GENERATION_API_KEY",
    "GENERATION_MODEL",
    "Q0_9ROUTER_VERSION",
    "Q0_9ROUTER_CONNECTION_ID",
)
FROZEN_RUN_ID = "q0-1-20260921T030640Z-36f32ae"
FROZEN_HYBRID_RESULT_SHA256 = (
    "216577d0c170824f361885ffc0c103b088a84dfc27bc1a4c6c7c63af49b33f54"
)
FROZEN_GOLDEN_CONTEXT_SHA256 = (
    "f7b392c5fcfadc6db7a83db8505acc62d5e9c2dda0f51261a80c133e95392013"
)
FROZEN_EVIDENCE_GOLD_SHA256 = (
    "858d2547c8dd515eaaad35e8dd73a1597a0dfa9147658128f159d7dab2d820bd"
)
GOLDEN_CASE_ID = "1706.03762-answer-1"
GOLDEN_QUESTION = (
    "Why does scaled dot-product attention divide by the square root of the key "
    "dimension?"
)
FOLLOW_UP_CASE_ID = "1706.03762-answer-1-follow-up"
FOLLOW_UP_QUESTION = "What failure mode would occur without that scaling?"
UNANSWERABLE_CASE_ID = "1706.03762-unanswerable"
UNANSWERABLE_QUESTION = (
    "What carbon footprint did the authors report for training the Transformer?"
)
TEMPERATURE = 0
TOP_P = 1
MAX_TOKENS = 800
TIMEOUT_SECONDS = 60
MAX_RETRIES = 0
STREAM_OPTIONS = {"include_usage": True}
SYSTEM_INSTRUCTIONS = """You answer questions about one scientific paper using only the supplied paper context.
Return exactly one JSON object matching the provided GroundedAnswer schema; do not add prose outside it.
For each substantive claim, include a unique positive citation marker such as [1] in the answer and one matching citation object.
Each citation must use a supplied source_ref and an evidence_quote copied verbatim from that source after whitespace normalization.
If the supplied context is insufficient, state that the supplied paper context is insufficient and return no citations.
For a follow-up, use only the bounded prior turn and explicitly name the scientific referent in the answer.
Never use outside knowledge, invent a source, or repair an invalid answer with a second response."""

_FROZEN_SOURCE_IDENTITIES = (
    (
        "S1",
        "1706.03762-chunk-0007",
        "bd0c0a35d7f0b1c5a7a66fa76cb8686da82a086946b31053986877639682c551",
    ),
    (
        "S2",
        "1706.03762-chunk-0008",
        "175e301f73f997f10b821ea6f442455425787bf744b61ce468dc844708f49f28",
    ),
    (
        "S3",
        "1706.03762-chunk-0006",
        "bf2133b8c89e6c15185a8d927246a55403723f278dc3b54a536f51a8fb5a202f",
    ),
    (
        "S4",
        "1706.03762-chunk-0027",
        "6da4ef37edb81ea5f3fc2bbb13501c8d281f879d9b615f8362a3d0fac56ca683",
    ),
    (
        "S5",
        "1706.03762-chunk-0009",
        "d39dad9169f38604845557c9856c2255ef8a3c6229be105625f4e676d9d740c6",
    ),
)
_MARKER_PATTERN = re.compile(r"\[(\d+)\]")
_CLAIM_SPLIT_PATTERN = re.compile(r"(?<=[.!?])(?:\s+|$)|\n+")


class GenerationValidationError(ValueError):
    pass


class GenerationConfigurationError(GenerationValidationError):
    pass


class _IdentityMismatch(GenerationValidationError):
    pass


class _InterruptedStream(GenerationValidationError):
    pass


class GenerationSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_ref: str = Field(pattern=r"^S[1-9]\d*$")
    chunk_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_text_identity(self) -> GenerationSource:
        if not self.text.strip():
            raise ValueError("source text must not be blank")
        observed = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if observed != self.text_sha256:
            raise ValueError("source text SHA-256 does not match text")
        return self


class BoundedPriorTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    question: str = Field(min_length=1)
    answer: GroundedAnswer


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_id: str = Field(min_length=1)
    kind: Literal["answerable", "follow_up", "unanswerable"]
    question: str = Field(min_length=1)
    model: str = Field(min_length=1)
    sources: tuple[GenerationSource, ...]
    prior_turn: BoundedPriorTurn | None = None

    @model_validator(mode="after")
    def validate_request(self) -> GenerationRequest:
        if not self.case_id.strip() or not self.question.strip():
            raise ValueError("case ID and question must not be blank")
        if not self.sources:
            raise ValueError("generation request must contain selected sources")
        source_refs = [source.source_ref for source in self.sources]
        if len(source_refs) != len(set(source_refs)):
            raise ValueError("generation source_ref values must be unique")
        chunk_ids = [source.chunk_id for source in self.sources]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("generation chunk IDs must be unique")
        if self.kind == "follow_up" and self.prior_turn is None:
            raise ValueError("follow-up request requires one bounded prior turn")
        if self.kind != "follow_up" and self.prior_turn is not None:
            raise ValueError("only a follow-up request may include a prior turn")
        return self


class GenerationUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_tokens: int = Field(gt=0)
    output_tokens: int = Field(gt=0)
    total_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_total(self) -> GenerationUsage:
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total token usage is smaller than input plus output")
        return self


class GatewayIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    base_url: str = Field(min_length=1)
    gateway_version: str = Field(min_length=1)
    connection_id: str = Field(min_length=1)
    configured_model: str = Field(min_length=1)
    requested_model: str | None = None
    response_model: str | None = None
    upstream_identity: str | None = None


GenerationErrorCategory: TypeAlias = Literal[
    "authentication",
    "rate_limit",
    "timeout",
    "interrupted_stream",
    "malformed_output",
    "unavailable",
    "identity_mismatch",
]


class GenerationError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    category: GenerationErrorCategory
    message: str = Field(min_length=1)
    retryable: bool
    status_code: int | None = None


class AnswerDeltaEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["answer.delta"] = "answer.delta"
    sequence: int = Field(ge=0)
    delta: str = Field(min_length=1)


class AnswerCompletedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["answer.completed"] = "answer.completed"
    answer: GroundedAnswer
    usage: GenerationUsage
    identity: GatewayIdentity


class AnswerFailedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["answer.failed"] = "answer.failed"
    error: GenerationError


GenerationEvent: TypeAlias = AnswerDeltaEvent | AnswerCompletedEvent | AnswerFailedEvent


class GenerationClient(Protocol):
    def stream_answer(
        self, request: GenerationRequest
    ) -> AsyncIterator[GenerationEvent]: ...


class FrozenGenerationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str
    hybrid_result_sha256: str
    golden_context_sha256: str
    evidence_gold_sha256: str
    system_instructions_sha256: str
    response_schema_sha256: str
    source_set_sha256: str
    frozen_input_sha256: str
    case_sequence: tuple[str, str, str]
    golden_question: str
    unanswerable_question: str
    sources: tuple[GenerationSource, ...]
    request_parameters: dict[str, Any]


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_frozen_bytes(path: Path, expected_sha256: str, label: str) -> bytes:
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise GenerationConfigurationError(f"cannot read frozen {label}: {path}") from error
    observed = _sha256_bytes(encoded)
    if observed != expected_sha256:
        raise GenerationConfigurationError(
            f"frozen {label} SHA-256 changed: expected {expected_sha256}, observed {observed}"
        )
    return encoded


def _decode_json(encoded: bytes, label: str) -> Any:
    try:
        return json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GenerationConfigurationError(f"invalid frozen {label} JSON") from error


def _load_evidence_cases(encoded: bytes) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    try:
        lines = encoded.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise GenerationConfigurationError("invalid evidence gold encoding") from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise GenerationConfigurationError(
                f"invalid evidence gold JSONL at line {line_number}"
            ) from error
        if not isinstance(value, dict) or not isinstance(value.get("case_id"), str):
            raise GenerationConfigurationError(
                f"invalid evidence gold case at line {line_number}"
            )
        case_id = value["case_id"]
        if case_id in cases:
            raise GenerationConfigurationError(f"duplicate evidence case {case_id!r}")
        cases[case_id] = value
    return cases


def _grounded_answer_schema() -> dict[str, Any]:
    return GroundedAnswer.model_json_schema()


def load_frozen_generation_inputs(
    *, root: Path, run_id: str
) -> FrozenGenerationInputs:
    root = root.resolve()
    if run_id != FROZEN_RUN_ID:
        raise GenerationConfigurationError(
            f"generation is frozen to run {FROZEN_RUN_ID!r}, not {run_id!r}"
        )
    result_path = root / "qualification" / "results" / run_id / "hybrid-retrieval.json"
    context_path = (
        root
        / "qualification"
        / "private"
        / run_id
        / "golden-retrieved-context.json"
    )
    evidence_path = root / "qualification" / "gold" / "evidence.jsonl"
    result_encoded = _read_frozen_bytes(
        result_path, FROZEN_HYBRID_RESULT_SHA256, "hybrid result"
    )
    context_encoded = _read_frozen_bytes(
        context_path, FROZEN_GOLDEN_CONTEXT_SHA256, "golden context"
    )
    evidence_encoded = _read_frozen_bytes(
        evidence_path, FROZEN_EVIDENCE_GOLD_SHA256, "evidence gold"
    )
    result = _decode_json(result_encoded, "hybrid result")
    context = _decode_json(context_encoded, "golden context")
    if not isinstance(result, dict) or result.get("run_id") != run_id:
        raise GenerationConfigurationError("frozen hybrid result has the wrong run ID")
    if result.get("failure_reasons") != []:
        raise GenerationConfigurationError("hybrid gate did not pass cleanly")
    thresholds = result.get("threshold_outcomes")
    if not isinstance(thresholds, dict) or not thresholds or any(
        not isinstance(value, dict) or value.get("passed") is not True
        for value in thresholds.values()
    ):
        raise GenerationConfigurationError("hybrid result does not pass every threshold")
    if result.get("selected_configuration") != SELECTED_CONFIGURATION:
        raise GenerationConfigurationError("hybrid selected configuration changed")
    golden_measurement = result.get("measurements", {}).get("golden_context")
    if not isinstance(golden_measurement, dict) or golden_measurement.get(
        "sha256"
    ) != FROZEN_GOLDEN_CONTEXT_SHA256:
        raise GenerationConfigurationError("hybrid result does not name the frozen context")
    if not isinstance(context, dict) or context.get("run_id") != run_id:
        raise GenerationConfigurationError("frozen golden context has the wrong run ID")
    if context.get("case_id") != GOLDEN_CASE_ID:
        raise GenerationConfigurationError("frozen golden context has the wrong case")
    if context.get("question") != GOLDEN_QUESTION:
        raise GenerationConfigurationError("frozen golden question changed")
    if context.get("configuration") != SELECTED_CONFIGURATION:
        raise GenerationConfigurationError("frozen golden configuration changed")
    raw_sources = context.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) != len(
        _FROZEN_SOURCE_IDENTITIES
    ):
        raise GenerationConfigurationError("frozen golden context must contain five sources")
    sources: list[GenerationSource] = []
    for position, (raw, expected) in enumerate(
        zip(raw_sources, _FROZEN_SOURCE_IDENTITIES, strict=True), start=1
    ):
        if not isinstance(raw, dict):
            raise GenerationConfigurationError(
                f"frozen source {position} is not an object"
            )
        source_ref, chunk_id, text_sha256 = expected
        text = raw.get("text")
        if (
            raw.get("source_ref") != source_ref
            or raw.get("chunk_id") != chunk_id
            or raw.get("paper_id") != "1706.03762"
            or not isinstance(text, str)
            or _sha256_bytes(text.encode("utf-8")) != text_sha256
        ):
            raise GenerationConfigurationError(
                f"frozen source identity changed at position {position}"
            )
        sources.append(
            GenerationSource(
                source_ref=source_ref,
                chunk_id=chunk_id,
                paper_id="1706.03762",
                text=text,
                text_sha256=text_sha256,
            )
        )
    evidence_cases = _load_evidence_cases(evidence_encoded)
    golden_case = evidence_cases.get(GOLDEN_CASE_ID)
    unanswerable_case = evidence_cases.get(UNANSWERABLE_CASE_ID)
    if (
        not isinstance(golden_case, dict)
        or golden_case.get("answerable") is not True
        or golden_case.get("question") != GOLDEN_QUESTION
    ):
        raise GenerationConfigurationError("frozen golden evidence case changed")
    if (
        not isinstance(unanswerable_case, dict)
        or unanswerable_case.get("answerable") is not False
        or unanswerable_case.get("question") != UNANSWERABLE_QUESTION
    ):
        raise GenerationConfigurationError("frozen unanswerable evidence case changed")
    request_parameters = {
        "max_retries": MAX_RETRIES,
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": STREAM_OPTIONS,
        "temperature": TEMPERATURE,
        "timeout_seconds": TIMEOUT_SECONDS,
        "top_p": TOP_P,
    }
    source_identities = [
        {
            "source_ref": source.source_ref,
            "chunk_id": source.chunk_id,
            "paper_id": source.paper_id,
            "text_sha256": source.text_sha256,
        }
        for source in sources
    ]
    system_sha256 = _sha256_bytes(SYSTEM_INSTRUCTIONS.encode("utf-8"))
    schema_sha256 = _sha256_bytes(_canonical_json_bytes(_grounded_answer_schema()))
    source_set_sha256 = _sha256_bytes(_canonical_json_bytes(source_identities))
    frozen_identity = {
        "run_id": run_id,
        "hybrid_result_sha256": FROZEN_HYBRID_RESULT_SHA256,
        "golden_context_sha256": FROZEN_GOLDEN_CONTEXT_SHA256,
        "evidence_gold_sha256": FROZEN_EVIDENCE_GOLD_SHA256,
        "system_instructions_sha256": system_sha256,
        "response_schema_sha256": schema_sha256,
        "source_set_sha256": source_set_sha256,
        "case_sequence": [
            GOLDEN_CASE_ID,
            FOLLOW_UP_QUESTION,
            UNANSWERABLE_CASE_ID,
        ],
        "request_parameters": request_parameters,
    }
    return FrozenGenerationInputs(
        run_id=run_id,
        hybrid_result_sha256=FROZEN_HYBRID_RESULT_SHA256,
        golden_context_sha256=FROZEN_GOLDEN_CONTEXT_SHA256,
        evidence_gold_sha256=FROZEN_EVIDENCE_GOLD_SHA256,
        system_instructions_sha256=system_sha256,
        response_schema_sha256=schema_sha256,
        source_set_sha256=source_set_sha256,
        frozen_input_sha256=_sha256_bytes(_canonical_json_bytes(frozen_identity)),
        case_sequence=(GOLDEN_CASE_ID, FOLLOW_UP_QUESTION, UNANSWERABLE_CASE_ID),
        golden_question=GOLDEN_QUESTION,
        unanswerable_question=UNANSWERABLE_QUESTION,
        sources=tuple(sources),
        request_parameters=request_parameters,
    )


def build_golden_request(frozen: FrozenGenerationInputs) -> GenerationRequest:
    return GenerationRequest(
        case_id=GOLDEN_CASE_ID,
        kind="answerable",
        question=frozen.golden_question,
        model=PINNED_MODEL,
        sources=frozen.sources,
    )


def build_follow_up_request(
    frozen: FrozenGenerationInputs, prior_answer: GroundedAnswer | Mapping[str, Any]
) -> GenerationRequest:
    validated_prior = validate_grounded_answer(
        prior_answer, frozen.sources, answerable=True
    )
    return GenerationRequest(
        case_id=FOLLOW_UP_CASE_ID,
        kind="follow_up",
        question=FOLLOW_UP_QUESTION,
        model=PINNED_MODEL,
        sources=frozen.sources,
        prior_turn=BoundedPriorTurn(
            question=frozen.golden_question,
            answer=validated_prior,
        ),
    )


def build_unanswerable_request(frozen: FrozenGenerationInputs) -> GenerationRequest:
    return GenerationRequest(
        case_id=UNANSWERABLE_CASE_ID,
        kind="unanswerable",
        question=frozen.unanswerable_question,
        model=PINNED_MODEL,
        sources=frozen.sources,
    )


def _parse_grounded_answer(
    value: GroundedAnswer | Mapping[str, Any],
) -> GroundedAnswer:
    try:
        if isinstance(value, GroundedAnswer):
            answer = value
        else:
            answer = GroundedAnswer.model_validate(value)
    except ValidationError as error:
        raise GenerationValidationError(f"invalid GroundedAnswer: {error}") from error
    if not answer.answer.strip():
        raise GenerationValidationError("answer must not be blank")
    for citation in answer.citations:
        if not citation.evidence_quote.strip():
            raise GenerationValidationError("evidence_quote must not be blank")
    return answer


def _claim_segments(answer: str) -> list[str]:
    return [
        segment.strip()
        for segment in _CLAIM_SPLIT_PATTERN.split(answer.strip())
        if re.search(r"\w", _MARKER_PATTERN.sub("", segment))
    ]


def claim_marker_coverage(answer: str) -> float:
    claims = _claim_segments(answer)
    if not claims:
        return 0.0
    supported = sum(bool(_MARKER_PATTERN.search(claim)) for claim in claims)
    return supported / len(claims)


def validate_grounded_answer(
    value: GroundedAnswer | Mapping[str, Any],
    supplied_sources: Sequence[GenerationSource],
    *,
    answerable: bool,
) -> GroundedAnswer:
    answer = _parse_grounded_answer(value)
    sources_by_ref = {source.source_ref: source for source in supplied_sources}
    if len(sources_by_ref) != len(supplied_sources):
        raise GenerationValidationError("supplied source_ref values are not unique")
    citation_markers = [citation.marker for citation in answer.citations]
    if len(citation_markers) != len(set(citation_markers)):
        raise GenerationValidationError("duplicate citation marker")
    answer_markers = [int(value) for value in _MARKER_PATTERN.findall(answer.answer)]
    if len(answer_markers) != len(set(answer_markers)):
        raise GenerationValidationError("duplicate answer marker")
    if set(answer_markers) != set(citation_markers):
        raise GenerationValidationError(
            "answer markers must map one-to-one to citations"
        )
    for citation in answer.citations:
        source = sources_by_ref.get(citation.source_ref)
        if source is None:
            raise GenerationValidationError(
                f"unknown source_ref {citation.source_ref!r}"
            )
        normalized_quote = normalize_text(citation.evidence_quote)
        normalized_source = normalize_text(source.text)
        if not normalized_quote or normalized_quote not in normalized_source:
            raise GenerationValidationError(
                f"evidence_quote is not present in source {citation.source_ref}"
            )
    if answerable:
        if not answer.citations:
            raise GenerationValidationError("answerable output requires citations")
        coverage = claim_marker_coverage(answer.answer)
        if coverage != 1.0:
            raise GenerationValidationError(
                f"claim-marker coverage must be 1.0, observed {coverage:.3f}"
            )
    return answer


def validate_refusal(
    value: GroundedAnswer | Mapping[str, Any],
) -> GroundedAnswer:
    answer = _parse_grounded_answer(value)
    if answer.citations:
        raise GenerationValidationError("grounded refusal requires empty citations")
    if _MARKER_PATTERN.search(answer.answer):
        raise GenerationValidationError("grounded refusal must not contain markers")
    normalized = normalize_text(answer.answer).casefold()
    required_words = ("supplied", "context", "insufficient")
    if any(word not in normalized for word in required_words):
        raise GenerationValidationError(
            "grounded refusal must state that supplied context is insufficient"
        )
    return answer


def validate_follow_up(
    value: GroundedAnswer | Mapping[str, Any],
    supplied_sources: Sequence[GenerationSource],
) -> GroundedAnswer:
    answer = validate_grounded_answer(value, supplied_sources, answerable=True)
    normalized = normalize_text(answer.answer).casefold()
    if "scaled dot-product attention" not in normalized:
        raise GenerationValidationError(
            "follow-up answer does not preserve the scaled dot-product attention referent"
        )
    return answer


def _validate_for_request(
    answer: GroundedAnswer,
    request: GenerationRequest,
) -> GroundedAnswer:
    if request.kind == "unanswerable":
        return validate_refusal(answer)
    if request.kind == "follow_up":
        return validate_follow_up(answer, request.sources)
    return validate_grounded_answer(answer, request.sources, answerable=True)


def _source_context(sources: Sequence[GenerationSource]) -> str:
    entries = []
    for source in sources:
        entries.append(
            f'<source source_ref="{source.source_ref}" chunk_id="{source.chunk_id}">\n'
            f"{source.text}\n"
            "</source>"
        )
    return "\n\n".join(entries)


def _current_user_message(request: GenerationRequest) -> str:
    return (
        f"Question:\n{request.question}\n\n"
        "Supplied paper context:\n"
        f"{_source_context(request.sources)}"
    )


def _messages(request: GenerationRequest) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]
    if request.prior_turn is not None:
        messages.extend(
            [
                {"role": "user", "content": request.prior_turn.question},
                {
                    "role": "assistant",
                    "content": json.dumps(
                        request.prior_turn.answer.model_dump(mode="json"),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ]
        )
    messages.append({"role": "user", "content": _current_user_message(request)})
    return messages


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "grounded_answer",
            "strict": True,
            "schema": _grounded_answer_schema(),
        },
    }


def _configuration_error(name: str, observed: str | None = None) -> None:
    suffix = " is missing" if observed is None or not observed else " is not pinned"
    raise GenerationConfigurationError(f"{name}{suffix}")


def _validate_configured_identity(identity: GatewayIdentity) -> None:
    expected = {
        "base_url": PINNED_BASE_URL,
        "gateway_version": PINNED_GATEWAY_VERSION,
        "connection_id": PINNED_CONNECTION_ID,
        "configured_model": PINNED_MODEL,
    }
    for field_name, expected_value in expected.items():
        observed = getattr(identity, field_name)
        if observed != expected_value:
            raise GenerationConfigurationError(
                f"configured {field_name.replace('_', ' ')} is not pinned"
            )
    if identity.requested_model is not None or identity.response_model is not None:
        raise GenerationConfigurationError(
            "configured gateway identity must not contain observed response fields"
        )


def _upstream_identity(chunk: Any) -> str | None:
    extra = getattr(chunk, "model_extra", None)
    if not isinstance(extra, dict):
        return None
    direct = extra.get("upstream_identity")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    provider = extra.get("provider")
    upstream_model = extra.get("upstream_model")
    if (
        isinstance(provider, str)
        and provider.strip()
        and isinstance(upstream_model, str)
        and upstream_model.strip()
    ):
        return f"{provider.strip()}/{upstream_model.strip()}"
    return None


def _failed(
    category: GenerationErrorCategory,
    message: str,
    *,
    retryable: bool,
    status_code: int | None = None,
) -> AnswerFailedEvent:
    return AnswerFailedEvent(
        error=GenerationError(
            category=category,
            message=message,
            retryable=retryable,
            status_code=status_code,
        )
    )


class OpenAICompatibleGenerationClient:
    def __init__(
        self,
        *,
        identity: GatewayIdentity,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        expected_upstream_identity: str | None = None,
    ) -> None:
        _validate_configured_identity(identity)
        if not api_key.strip():
            raise GenerationConfigurationError("GENERATION_API_KEY is missing")
        if expected_upstream_identity is not None and not expected_upstream_identity.strip():
            raise GenerationConfigurationError(
                "expected upstream identity must be non-empty when provided"
            )
        self._identity = identity
        self._expected_upstream_identity = expected_upstream_identity
        http_client = (
            httpx.AsyncClient(transport=transport, timeout=TIMEOUT_SECONDS)
            if transport is not None
            else None
        )
        options: dict[str, Any] = {
            "api_key": api_key,
            "base_url": identity.base_url,
            "timeout": TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES,
        }
        if http_client is not None:
            options["http_client"] = http_client
        self._client = AsyncOpenAI(**options)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self._identity.base_url!r}, "
            f"model={self._identity.configured_model!r})"
        )

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        expected_upstream_identity: str | None = None,
    ) -> OpenAICompatibleGenerationClient:
        values = os.environ if environ is None else environ
        required = (
            "GENERATION_BASE_URL",
            "GENERATION_API_KEY",
            "GENERATION_MODEL",
            "Q0_9ROUTER_VERSION",
            "Q0_9ROUTER_CONNECTION_ID",
        )
        resolved: dict[str, str] = {}
        for name in required:
            value = values.get(name)
            if not isinstance(value, str) or not value.strip():
                _configuration_error(name)
            resolved[name] = value.strip()
        expected = {
            "GENERATION_BASE_URL": PINNED_BASE_URL,
            "GENERATION_MODEL": PINNED_MODEL,
            "Q0_9ROUTER_VERSION": PINNED_GATEWAY_VERSION,
            "Q0_9ROUTER_CONNECTION_ID": PINNED_CONNECTION_ID,
        }
        for name, expected_value in expected.items():
            if resolved[name] != expected_value:
                _configuration_error(name, resolved[name])
        return cls(
            identity=GatewayIdentity(
                base_url=resolved["GENERATION_BASE_URL"],
                gateway_version=resolved["Q0_9ROUTER_VERSION"],
                connection_id=resolved["Q0_9ROUTER_CONNECTION_ID"],
                configured_model=resolved["GENERATION_MODEL"],
            ),
            api_key=resolved["GENERATION_API_KEY"],
            transport=transport,
            expected_upstream_identity=expected_upstream_identity,
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def stream_answer(
        self, request: GenerationRequest
    ) -> AsyncIterator[GenerationEvent]:
        try:
            if request.model != self._identity.configured_model:
                raise _IdentityMismatch(
                    "requested model does not match configured model"
                )
            stream = await self._client.chat.completions.create(
                model=request.model,
                messages=cast(Any, _messages(request)),
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_tokens=MAX_TOKENS,
                response_format=cast(Any, _response_format()),
                stream=True,
                stream_options=STREAM_OPTIONS,
            )
            content_parts: list[str] = []
            sequence = 0
            saw_stop = False
            usage: GenerationUsage | None = None
            response_model: str | None = None
            observed_upstream: str | None = None
            async with stream:
                async for chunk in stream:
                    chunk_model = getattr(chunk, "model", None)
                    if chunk_model != request.model:
                        raise _IdentityMismatch(
                            "response model does not match requested model"
                        )
                    if response_model is None:
                        response_model = chunk_model
                    elif response_model != chunk_model:
                        raise _IdentityMismatch(
                            "response model changed during the stream"
                        )
                    chunk_upstream = _upstream_identity(chunk)
                    if chunk_upstream is not None:
                        if observed_upstream is None:
                            observed_upstream = chunk_upstream
                        elif observed_upstream != chunk_upstream:
                            raise _IdentityMismatch(
                                "upstream identity changed during the stream"
                            )
                        if (
                            self._expected_upstream_identity is not None
                            and chunk_upstream != self._expected_upstream_identity
                        ):
                            raise _IdentityMismatch(
                                "upstream identity does not match the pinned identity"
                            )
                    choices = getattr(chunk, "choices", None)
                    if choices:
                        if len(choices) != 1 or choices[0].index != 0:
                            raise GenerationValidationError(
                                "stream must contain only choice index zero"
                            )
                        choice = choices[0]
                        content = getattr(choice.delta, "content", None)
                        if content:
                            content_parts.append(content)
                            yield AnswerDeltaEvent(sequence=sequence, delta=content)
                            sequence += 1
                        finish_reason = getattr(choice, "finish_reason", None)
                        if finish_reason is not None:
                            if finish_reason != "stop":
                                raise _InterruptedStream(
                                    f"stream ended with finish reason {finish_reason!r}"
                                )
                            if saw_stop:
                                raise _InterruptedStream(
                                    "stream contained more than one stop signal"
                                )
                            saw_stop = True
                    raw_usage = getattr(chunk, "usage", None)
                    if raw_usage is not None:
                        if usage is not None:
                            raise _InterruptedStream(
                                "stream contained more than one usage record"
                            )
                        try:
                            usage = GenerationUsage(
                                input_tokens=raw_usage.prompt_tokens,
                                output_tokens=raw_usage.completion_tokens,
                                total_tokens=raw_usage.total_tokens,
                            )
                        except ValidationError as error:
                            raise _InterruptedStream(
                                "stream contained invalid provider usage"
                            ) from error
            if not content_parts:
                raise _InterruptedStream("stream contained no answer deltas")
            if not saw_stop:
                raise _InterruptedStream("stream ended without a stop signal")
            if usage is None:
                raise _InterruptedStream("stream ended without provider usage")
            if response_model is None:
                raise _InterruptedStream("stream ended without a response model")
            try:
                answer = GroundedAnswer.model_validate_json("".join(content_parts))
            except ValidationError as error:
                raise GenerationValidationError(
                    "first response does not match the strict GroundedAnswer schema"
                ) from error
            answer = _validate_for_request(answer, request)
            yield AnswerCompletedEvent(
                answer=answer,
                usage=usage,
                identity=GatewayIdentity(
                    base_url=self._identity.base_url,
                    gateway_version=self._identity.gateway_version,
                    connection_id=self._identity.connection_id,
                    configured_model=self._identity.configured_model,
                    requested_model=request.model,
                    response_model=response_model,
                    upstream_identity=observed_upstream,
                ),
            )
        except _IdentityMismatch as error:
            yield _failed(
                "identity_mismatch",
                str(error),
                retryable=False,
            )
        except _InterruptedStream as error:
            yield _failed(
                "interrupted_stream",
                str(error),
                retryable=True,
            )
        except AuthenticationError:
            yield _failed(
                "authentication",
                "generation authentication failed",
                retryable=False,
                status_code=401,
            )
        except RateLimitError:
            yield _failed(
                "rate_limit",
                "generation provider rate limit exceeded",
                retryable=True,
                status_code=429,
            )
        except (APITimeoutError, httpx.TimeoutException):
            yield _failed(
                "timeout",
                "generation request timed out",
                retryable=True,
            )
        except APIStatusError as error:
            status_code = error.status_code
            category: GenerationErrorCategory = (
                "authentication"
                if status_code in {401, 403}
                else "rate_limit"
                if status_code == 429
                else "unavailable"
            )
            yield _failed(
                category,
                f"generation gateway returned HTTP {status_code}",
                retryable=category in {"rate_limit", "unavailable"},
                status_code=status_code,
            )
        except (APIConnectionError, httpx.HTTPError):
            yield _failed(
                "unavailable",
                "generation gateway is unavailable",
                retryable=True,
            )
        except (GenerationValidationError, json.JSONDecodeError):
            yield _failed(
                "malformed_output",
                "first response failed GroundedAnswer validation",
                retryable=False,
            )
        except Exception:
            yield _failed(
                "unavailable",
                "generation failed with an unavailable transport",
                retryable=True,
            )


class GenerationConfigurationAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    gateway_version: str
    connection_id: str
    active_connection_ids: tuple[str, ...]
    selected_account_count: int
    route: str
    route_kind: Literal["direct"]
    fallback_candidates: tuple[str, ...]
    rtk_enabled: bool
    caveman_enabled: bool
    prompt_transforms_enabled: bool
    cloud_sync_enabled: bool
    tunnel_enabled: bool
    body_logging_enabled: bool
    existing_quota_confirmed: bool
    upstream_identity: str

    @model_validator(mode="after")
    def validate_pinned_gateway(self) -> GenerationConfigurationAssertion:
        if self.gateway_version != PINNED_GATEWAY_VERSION:
            raise ValueError("gateway version is not pinned")
        if self.connection_id != PINNED_CONNECTION_ID:
            raise ValueError("provider connection is not pinned")
        if self.active_connection_ids != (PINNED_CONNECTION_ID,):
            raise ValueError("exactly the pinned provider connection must be active")
        if self.selected_account_count != 1:
            raise ValueError("exactly one selected account is required")
        if self.route != PINNED_MODEL or self.route_kind != "direct":
            raise ValueError("generation route must be the pinned literal direct route")
        if self.fallback_candidates:
            raise ValueError("generation route must not have fallback candidates")
        feature_flags = (
            self.rtk_enabled,
            self.caveman_enabled,
            self.prompt_transforms_enabled,
            self.cloud_sync_enabled,
            self.tunnel_enabled,
            self.body_logging_enabled,
        )
        if any(feature_flags):
            raise ValueError("gateway transformations, tunneling, sync, and logging must be disabled")
        if self.existing_quota_confirmed is not True:
            raise ValueError("existing quota for exactly four requests is not confirmed")
        if self.upstream_identity != PINNED_UPSTREAM_IDENTITY:
            raise ValueError("upstream identity is not pinned")
        return self


RequestSlot: TypeAlias = Literal[
    "preflight",
    "golden",
    "follow-up",
    "unanswerable",
]
_REQUEST_SLOT_ORDINAL: dict[RequestSlot, int] = {
    "preflight": 1,
    "golden": 2,
    "follow-up": 3,
    "unanswerable": 4,
}


class _RequestTiming(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ttft_seconds: float | None = Field(default=None, gt=0)
    total_latency_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_ordering(self) -> _RequestTiming:
        if (
            self.ttft_seconds is not None
            and self.total_latency_seconds < self.ttft_seconds
        ):
            raise ValueError("total latency must not precede time to first token")
        return self


class _NormalizedEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["answer.delta", "answer.completed"]
    sequence: int | None = Field(default=None, ge=0)
    delta_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_shape(self) -> _NormalizedEventRecord:
        if self.type == "answer.delta":
            if self.sequence is None or self.delta_sha256 is None:
                raise ValueError("delta event record requires sequence and hash")
        elif self.sequence is not None or self.delta_sha256 is not None:
            raise ValueError("terminal event record must not contain delta fields")
        return self


class _CitationIdentityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    marker: int = Field(gt=0)
    source_ref: str
    chunk_id: str
    source_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _RequestAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    slot: RequestSlot
    ordinal: int = Field(ge=1, le=4)
    state: Literal["reserved", "completed", "failed"]
    terminal_type: Literal[
        "answer.completed",
        "answer.failed",
        "validation.failed",
    ] | None = None
    timing: _RequestTiming | None = None
    error: GenerationError | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> _RequestAttempt:
        if self.ordinal != _REQUEST_SLOT_ORDINAL[self.slot]:
            raise ValueError("request slot ordinal changed")
        if self.state == "reserved":
            if (
                self.terminal_type is not None
                or self.timing is not None
                or self.error is not None
            ):
                raise ValueError("reserved request slot contains terminal evidence")
        elif self.state == "completed":
            if (
                self.terminal_type != "answer.completed"
                or self.timing is None
                or self.timing.ttft_seconds is None
                or self.error is not None
            ):
                raise ValueError("completed request slot evidence is incomplete")
        elif (
            self.terminal_type not in {"answer.failed", "validation.failed"}
            or self.timing is None
            or self.error is None
        ):
            raise ValueError("failed request slot evidence is incomplete")
        return self


class _GenerationRequestLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_version: Literal["q0.1-generation-private-1"] = PRIVATE_ARTIFACT_VERSION
    run_id: str
    producer_git_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    frozen_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_assertion_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    slots: dict[str, _RequestAttempt]

    @model_validator(mode="after")
    def validate_slots(self) -> _GenerationRequestLedger:
        allowed = set(_REQUEST_SLOT_ORDINAL)
        if not set(self.slots).issubset(allowed):
            raise ValueError("request ledger contains an unknown slot")
        for name, attempt in self.slots.items():
            if name != attempt.slot:
                raise ValueError("request ledger slot key changed")
        for slot, prerequisites in (
            ("golden", ("preflight",)),
            ("follow-up", ("preflight", "golden")),
            ("unanswerable", ("preflight", "golden", "follow-up")),
        ):
            if slot in self.slots and any(
                prerequisite not in self.slots for prerequisite in prerequisites
            ):
                raise ValueError("request ledger slot sequence is incomplete")
        return self

    @property
    def attempted_count(self) -> int:
        return len(self.slots)


class _GenerationPreflightState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_version: Literal["q0.1-generation-private-1"] = PRIVATE_ARTIFACT_VERSION
    run_id: str
    stage: Literal["preflight"] = "preflight"
    producer_git_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    frozen_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_assertion_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gateway_version: str
    route_present: bool
    answer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_types: tuple[Literal["answer.delta", "answer.completed"], ...]
    delta_event_count: int = Field(gt=0)
    terminal_event_count: Literal[1] = 1
    timing: _RequestTiming
    usage: GenerationUsage
    identity: GatewayIdentity


class _ValidatedGenerationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_id: str
    kind: Literal["answerable", "follow_up", "unanswerable"]
    answer: GroundedAnswer
    answer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: tuple[_NormalizedEventRecord, ...]
    delta_event_count: int = Field(gt=0)
    terminal_event_count: Literal[1] = 1
    timing: _RequestTiming
    usage: GenerationUsage
    identity: GatewayIdentity
    citation_identities: tuple[_CitationIdentityRecord, ...]


class _PrivateGenerationFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    slot: RequestSlot
    case_id: str
    error: GenerationError
    timing: _RequestTiming


class _ValidatedGenerationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_version: Literal["q0.1-generation-private-1"] = PRIVATE_ARTIFACT_VERSION
    run_id: str
    producer_git_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[_ValidatedGenerationCase, ...]
    failure: _PrivateGenerationFailure | None


@dataclass(frozen=True)
class _CollectedGeneration:
    events: tuple[GenerationEvent, ...]
    request_started_ns: int
    first_delta_ns: int | None
    terminal_ns: int | None
    request_ended_ns: int

    def timing(self, *, require_first_delta: bool) -> _RequestTiming:
        terminal_ns = self.terminal_ns or self.request_ended_ns
        total_ns = terminal_ns - self.request_started_ns
        if total_ns <= 0:
            raise GenerationValidationError(
                "generation total latency is not positive"
            )
        ttft_seconds: float | None = None
        if self.first_delta_ns is not None:
            ttft_ns = self.first_delta_ns - self.request_started_ns
            if ttft_ns <= 0 or ttft_ns > total_ns:
                raise GenerationValidationError(
                    "generation time to first token is not ordered"
                )
            ttft_seconds = ttft_ns / 1_000_000_000
        elif require_first_delta:
            raise GenerationValidationError(
                "completed generation emitted no answer delta"
            )
        return _RequestTiming(
            ttft_seconds=ttft_seconds,
            total_latency_seconds=total_ns / 1_000_000_000,
        )


@dataclass(frozen=True)
class _MeasurementExecution:
    cases: tuple[_ValidatedGenerationCase, ...]
    failure: _PrivateGenerationFailure | None


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
        raise GenerationConfigurationError(
            f"git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout.strip()


def _require_clean_producer(root: Path) -> str:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if status:
        raise GenerationConfigurationError(
            f"tracked tree must be clean before generation traffic; status was:\n{status}"
        )
    revision = _git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise GenerationConfigurationError("generation producer revision is invalid")
    return revision


def _load_environment(root: Path, run_id: str) -> EnvironmentResult:
    path = root / "qualification" / "results" / run_id / "environment.json"
    try:
        environment = EnvironmentResult.model_validate_json(path.read_text("utf-8"))
    except FileNotFoundError as error:
        raise GenerationConfigurationError(f"Q0.1 environment not found: {path}") from error
    except (OSError, ValidationError) as error:
        raise GenerationConfigurationError(f"invalid Q0.1 environment: {path}") from error
    if environment.run_id != run_id:
        raise GenerationConfigurationError("environment run ID does not match requested run")
    hybrid = environment.measurements.get("hybrid_retrieval")
    if not isinstance(hybrid, dict) or hybrid.get("status") != "qualified":
        raise GenerationConfigurationError("hybrid retrieval gate is not qualified")
    return environment


def load_generation_environment(root: Path) -> dict[str, str]:
    path = root.resolve() / "experiments" / "q0-1" / ".env"
    try:
        lines = path.read_text("utf-8").splitlines()
    except FileNotFoundError as error:
        raise GenerationConfigurationError(f"generation environment file is missing: {path}") from error
    except (OSError, UnicodeDecodeError) as error:
        raise GenerationConfigurationError(f"cannot read generation environment file: {path}") from error
    values: dict[str, str] = {}
    allowed = set(_GENERATION_ENVIRONMENT_NAMES)
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise GenerationConfigurationError(
                f"invalid generation environment entry at line {line_number}"
            )
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in allowed:
            raise GenerationConfigurationError(
                f"unexpected generation environment name at line {line_number}"
            )
        if name in values:
            raise GenerationConfigurationError(
                f"duplicate generation environment name at line {line_number}"
            )
        if not value.strip():
            raise GenerationConfigurationError(f"{name} is missing")
        values[name] = value.strip()
    missing = [name for name in _GENERATION_ENVIRONMENT_NAMES if name not in values]
    if missing:
        raise GenerationConfigurationError(
            f"generation environment is missing {', '.join(missing)}"
        )
    return values


def _configuration_assertion_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "qualification"
        / "private"
        / run_id
        / "generation-configuration-assertion.json"
    )


def _preflight_path(root: Path, run_id: str) -> Path:
    return (
        root / "qualification" / "private" / run_id / "generation-preflight.json"
    )


def _validated_generation_path(root: Path, run_id: str) -> Path:
    return (
        root / "qualification" / "private" / run_id / "validated-generation.json"
    )


def _request_ledger_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "qualification"
        / "private"
        / run_id
        / "generation-request-ledger.json"
    )


@contextmanager
def _request_ledger_lock(root: Path, run_id: str) -> Iterator[None]:
    directory = root / "qualification" / "private" / run_id
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".generation-request-ledger.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_request_ledger_unlocked(
    path: Path,
) -> _GenerationRequestLedger | None:
    try:
        encoded = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise GenerationConfigurationError(
            "cannot read private generation request ledger"
        ) from error
    try:
        return _GenerationRequestLedger.model_validate_json(encoded)
    except ValidationError as error:
        raise GenerationConfigurationError(
            "private generation request ledger is invalid"
        ) from error


def _validate_request_ledger_identity(
    ledger: _GenerationRequestLedger,
    *,
    run_id: str,
    producer_git_revision: str,
    frozen_input_sha256: str,
    configuration_assertion_sha256: str,
) -> None:
    if ledger.run_id != run_id:
        raise GenerationConfigurationError("request ledger run identity changed")
    if ledger.producer_git_revision != producer_git_revision:
        raise GenerationConfigurationError(
            "request ledger producer revision changed"
        )
    if ledger.frozen_input_sha256 != frozen_input_sha256:
        raise GenerationConfigurationError("request ledger frozen inputs changed")
    if (
        ledger.configuration_assertion_sha256
        != configuration_assertion_sha256
    ):
        raise GenerationConfigurationError(
            "request ledger gateway assertion changed"
        )


def _persist_request_ledger(
    path: Path,
    ledger: _GenerationRequestLedger,
) -> _GenerationRequestLedger:
    write_json_atomic(path, ledger)
    try:
        return _GenerationRequestLedger.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise GenerationValidationError(
            "persisted generation request ledger failed validation"
        ) from error


def _assert_request_slot_available(
    *,
    root: Path,
    run_id: str,
    producer_git_revision: str,
    frozen_input_sha256: str,
    configuration_assertion_sha256: str,
    slot: RequestSlot,
) -> None:
    path = _request_ledger_path(root, run_id)
    with _request_ledger_lock(root, run_id):
        ledger = _read_request_ledger_unlocked(path)
        if ledger is None:
            return
        _validate_request_ledger_identity(
            ledger,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
        )
        if slot in ledger.slots:
            raise GenerationConfigurationError(
                f"generation request slot {slot!r} was already attempted"
            )


def _reserve_request_slot(
    *,
    root: Path,
    run_id: str,
    producer_git_revision: str,
    frozen_input_sha256: str,
    configuration_assertion_sha256: str,
    slot: RequestSlot,
) -> _GenerationRequestLedger:
    path = _request_ledger_path(root, run_id)
    with _request_ledger_lock(root, run_id):
        ledger = _read_request_ledger_unlocked(path)
        if ledger is None:
            ledger = _GenerationRequestLedger(
                run_id=run_id,
                producer_git_revision=producer_git_revision,
                frozen_input_sha256=frozen_input_sha256,
                configuration_assertion_sha256=configuration_assertion_sha256,
                slots={},
            )
        else:
            _validate_request_ledger_identity(
                ledger,
                run_id=run_id,
                producer_git_revision=producer_git_revision,
                frozen_input_sha256=frozen_input_sha256,
                configuration_assertion_sha256=configuration_assertion_sha256,
            )
        if slot in ledger.slots:
            raise GenerationConfigurationError(
                f"generation request slot {slot!r} was already attempted"
            )
        slots = {
            **ledger.slots,
            slot: _RequestAttempt(
                slot=slot,
                ordinal=_REQUEST_SLOT_ORDINAL[slot],
                state="reserved",
            ),
        }
        return _persist_request_ledger(
            path,
            ledger.model_copy(update={"slots": slots}),
        )


def _finish_request_slot(
    *,
    root: Path,
    run_id: str,
    producer_git_revision: str,
    frozen_input_sha256: str,
    configuration_assertion_sha256: str,
    slot: RequestSlot,
    terminal_type: Literal[
        "answer.completed",
        "answer.failed",
        "validation.failed",
    ],
    timing: _RequestTiming,
    error: GenerationError | None,
) -> _GenerationRequestLedger:
    path = _request_ledger_path(root, run_id)
    with _request_ledger_lock(root, run_id):
        ledger = _read_request_ledger_unlocked(path)
        if ledger is None:
            raise GenerationConfigurationError(
                "generation request ledger disappeared after reservation"
            )
        _validate_request_ledger_identity(
            ledger,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
        )
        existing = ledger.slots.get(slot)
        if existing is None or existing.state != "reserved":
            raise GenerationConfigurationError(
                f"generation request slot {slot!r} is not reserved"
            )
        state: Literal["completed", "failed"] = (
            "completed" if terminal_type == "answer.completed" else "failed"
        )
        attempt = _RequestAttempt(
            slot=slot,
            ordinal=_REQUEST_SLOT_ORDINAL[slot],
            state=state,
            terminal_type=terminal_type,
            timing=timing,
            error=error,
        )
        return _persist_request_ledger(
            path,
            ledger.model_copy(
                update={"slots": {**ledger.slots, slot: attempt}}
            ),
        )


def _request_ledger_snapshot(
    *,
    root: Path,
    run_id: str,
    producer_git_revision: str,
    frozen_input_sha256: str,
    configuration_assertion_sha256: str,
) -> _GenerationRequestLedger:
    path = _request_ledger_path(root, run_id)
    with _request_ledger_lock(root, run_id):
        ledger = _read_request_ledger_unlocked(path)
        if ledger is None:
            raise GenerationConfigurationError(
                "generation request ledger does not exist"
            )
        _validate_request_ledger_identity(
            ledger,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
        )
        return ledger


def _load_configuration_assertion(
    root: Path, run_id: str
) -> tuple[GenerationConfigurationAssertion, str]:
    path = _configuration_assertion_path(root, run_id)
    try:
        encoded = path.read_bytes()
        assertion = GenerationConfigurationAssertion.model_validate_json(encoded)
    except FileNotFoundError as error:
        raise GenerationConfigurationError(
            f"private generation configuration assertion not found: {path}"
        ) from error
    except (OSError, ValidationError) as error:
        raise GenerationConfigurationError(
            f"invalid private generation configuration assertion: {error}"
        ) from error
    return assertion, _sha256_bytes(encoded)


def _environment_values(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


async def _gateway_checks(
    *,
    api_key: str,
    transport: httpx.AsyncBaseTransport | None,
) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(
        headers=headers,
        timeout=TIMEOUT_SECONDS,
        transport=transport,
    ) as client:
        try:
            version_response = await client.get(
                "http://127.0.0.1:20128/api/version"
            )
            models_response = await client.get(f"{PINNED_BASE_URL}/models")
        except httpx.HTTPError as error:
            raise GenerationConfigurationError(
                "cannot verify the pinned local generation gateway"
            ) from error
    if version_response.status_code != 200:
        raise GenerationConfigurationError(
            f"9Router version endpoint returned HTTP {version_response.status_code}"
        )
    if models_response.status_code != 200:
        raise GenerationConfigurationError(
            f"9Router models endpoint returned HTTP {models_response.status_code}"
        )
    try:
        version_payload = version_response.json()
        models_payload = models_response.json()
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GenerationConfigurationError(
            "9Router identity endpoint returned invalid JSON"
        ) from error
    if (
        not isinstance(version_payload, dict)
        or version_payload.get("currentVersion") != PINNED_GATEWAY_VERSION
    ):
        raise GenerationConfigurationError("9Router currentVersion is not pinned")
    models = models_payload.get("data") if isinstance(models_payload, dict) else None
    if not isinstance(models, list) or not any(
        isinstance(model, dict) and model.get("id") == PINNED_MODEL
        for model in models
    ):
        raise GenerationConfigurationError(
            "pinned literal generation route is absent from /v1/models"
        )


async def _collect_events(
    client: OpenAICompatibleGenerationClient,
    request: GenerationRequest,
) -> _CollectedGeneration:
    request_started_ns = time.monotonic_ns()
    first_delta_ns: int | None = None
    terminal_ns: int | None = None
    events: list[GenerationEvent] = []
    async for event in client.stream_answer(request):
        observed_ns = time.monotonic_ns()
        events.append(event)
        if isinstance(event, AnswerDeltaEvent) and first_delta_ns is None:
            first_delta_ns = observed_ns
        if isinstance(event, (AnswerCompletedEvent, AnswerFailedEvent)):
            terminal_ns = observed_ns
    return _CollectedGeneration(
        events=tuple(events),
        request_started_ns=request_started_ns,
        first_delta_ns=first_delta_ns,
        terminal_ns=terminal_ns,
        request_ended_ns=time.monotonic_ns(),
    )


def _completed_event(
    events: Sequence[GenerationEvent],
    *,
    label: str,
    expected_upstream_identity: str,
) -> AnswerCompletedEvent | AnswerFailedEvent:
    terminals = [
        event
        for event in events
        if event.type in {"answer.completed", "answer.failed"}
    ]
    if len(terminals) != 1 or not events or events[-1] is not terminals[0]:
        raise GenerationValidationError(
            f"{label} did not emit exactly one final terminal event"
        )
    terminal = terminals[0]
    if isinstance(terminal, AnswerFailedEvent):
        return terminal
    if not isinstance(terminal, AnswerCompletedEvent):
        raise GenerationValidationError(f"{label} emitted an invalid terminal event")
    if not any(event.type == "answer.delta" for event in events):
        raise GenerationValidationError(f"{label} emitted no answer delta")
    identity = terminal.identity
    if (
        identity.gateway_version != PINNED_GATEWAY_VERSION
        or identity.connection_id != PINNED_CONNECTION_ID
        or identity.configured_model != PINNED_MODEL
        or identity.requested_model != PINNED_MODEL
        or identity.response_model != PINNED_MODEL
        or (
            identity.upstream_identity is not None
            and identity.upstream_identity != expected_upstream_identity
        )
    ):
        raise GenerationValidationError(f"{label} generation identity drifted")
    return terminal


def _typed_validation_error(error: GenerationValidationError) -> GenerationError:
    identity_mismatch = "identity" in str(error).casefold()
    return GenerationError(
        category="identity_mismatch" if identity_mismatch else "interrupted_stream",
        message=(
            "generation identity validation failed"
            if identity_mismatch
            else "generation stream validation failed"
        ),
        retryable=not identity_mismatch,
    )


async def _run_preflight_request(
    *,
    root: Path,
    run_id: str,
    producer_git_revision: str,
    frozen: FrozenGenerationInputs,
    assertion: GenerationConfigurationAssertion,
    configuration_assertion_sha256: str,
    environ: Mapping[str, str],
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[_CollectedGeneration, AnswerCompletedEvent | AnswerFailedEvent]:
    client = OpenAICompatibleGenerationClient.from_environment(
        environ,
        transport=transport,
        expected_upstream_identity=assertion.upstream_identity,
    )
    try:
        await _gateway_checks(
            api_key=environ["GENERATION_API_KEY"],
            transport=transport,
        )
        _reserve_request_slot(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen.frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
            slot="preflight",
        )
        collected = await _collect_events(client, build_golden_request(frozen))
    finally:
        await client.aclose()
    timing = collected.timing(require_first_delta=False)
    try:
        terminal = _completed_event(
            collected.events,
            label="generation preflight",
            expected_upstream_identity=assertion.upstream_identity,
        )
    except GenerationValidationError as validation_error:
        typed_error = _typed_validation_error(validation_error)
        _finish_request_slot(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen.frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
            slot="preflight",
            terminal_type="validation.failed",
            timing=timing,
            error=typed_error,
        )
        raise
    if isinstance(terminal, AnswerFailedEvent):
        _finish_request_slot(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen.frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
            slot="preflight",
            terminal_type="answer.failed",
            timing=timing,
            error=terminal.error,
        )
        return collected, terminal
    completed_timing = collected.timing(require_first_delta=True)
    _finish_request_slot(
        root=root,
        run_id=run_id,
        producer_git_revision=producer_git_revision,
        frozen_input_sha256=frozen.frozen_input_sha256,
        configuration_assertion_sha256=configuration_assertion_sha256,
        slot="preflight",
        terminal_type="answer.completed",
        timing=completed_timing,
        error=None,
    )
    return collected, terminal


def _normalized_event_records(
    events: Sequence[GenerationEvent],
) -> tuple[_NormalizedEventRecord, ...]:
    records: list[_NormalizedEventRecord] = []
    for event in events:
        if isinstance(event, AnswerDeltaEvent):
            records.append(
                _NormalizedEventRecord(
                    type="answer.delta",
                    sequence=event.sequence,
                    delta_sha256=_sha256_bytes(event.delta.encode("utf-8")),
                )
            )
        elif isinstance(event, AnswerCompletedEvent):
            records.append(_NormalizedEventRecord(type="answer.completed"))
        else:
            raise GenerationValidationError(
                "failed generation event cannot enter validated output"
            )
    return tuple(records)


def _citation_identity_records(
    answer: GroundedAnswer,
    frozen: FrozenGenerationInputs,
) -> tuple[_CitationIdentityRecord, ...]:
    sources = {source.source_ref: source for source in frozen.sources}
    records: list[_CitationIdentityRecord] = []
    for citation in answer.citations:
        source = sources[citation.source_ref]
        records.append(
            _CitationIdentityRecord(
                marker=citation.marker,
                source_ref=citation.source_ref,
                chunk_id=source.chunk_id,
                source_text_sha256=source.text_sha256,
                evidence_quote_sha256=_sha256_bytes(
                    citation.evidence_quote.encode("utf-8")
                ),
            )
        )
    return tuple(records)


def _validated_case(
    request: GenerationRequest,
    collected: _CollectedGeneration,
    completed: AnswerCompletedEvent,
    frozen: FrozenGenerationInputs,
) -> _ValidatedGenerationCase:
    answer_payload = completed.answer.model_dump(mode="json")
    return _ValidatedGenerationCase(
        case_id=request.case_id,
        kind=request.kind,
        answer=completed.answer,
        answer_sha256=_sha256_bytes(_canonical_json_bytes(answer_payload)),
        events=_normalized_event_records(collected.events),
        delta_event_count=sum(
            event.type == "answer.delta" for event in collected.events
        ),
        timing=collected.timing(require_first_delta=True),
        usage=completed.usage,
        identity=completed.identity,
        citation_identities=_citation_identity_records(completed.answer, frozen),
    )


async def _run_measured_requests(
    *,
    root: Path,
    run_id: str,
    producer_git_revision: str,
    frozen: FrozenGenerationInputs,
    assertion: GenerationConfigurationAssertion,
    configuration_assertion_sha256: str,
    environ: Mapping[str, str],
    transport: httpx.AsyncBaseTransport | None,
) -> _MeasurementExecution:
    client = OpenAICompatibleGenerationClient.from_environment(
        environ,
        transport=transport,
        expected_upstream_identity=assertion.upstream_identity,
    )
    cases: list[_ValidatedGenerationCase] = []

    async def attempt(
        slot: RequestSlot,
        request: GenerationRequest,
    ) -> tuple[_ValidatedGenerationCase | None, _PrivateGenerationFailure | None]:
        _reserve_request_slot(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen.frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
            slot=slot,
        )
        dispatch_started_ns = time.monotonic_ns()
        try:
            collected = await _collect_events(client, request)
        except Exception:
            elapsed_ns = time.monotonic_ns() - dispatch_started_ns
            timing = _RequestTiming(
                total_latency_seconds=max(elapsed_ns, 1) / 1_000_000_000
            )
            error = GenerationError(
                category="unavailable",
                message="generation failed with an unavailable transport",
                retryable=True,
            )
            _finish_request_slot(
                root=root,
                run_id=run_id,
                producer_git_revision=producer_git_revision,
                frozen_input_sha256=frozen.frozen_input_sha256,
                configuration_assertion_sha256=configuration_assertion_sha256,
                slot=slot,
                terminal_type="validation.failed",
                timing=timing,
                error=error,
            )
            return None, _PrivateGenerationFailure(
                slot=slot,
                case_id=request.case_id,
                error=error,
                timing=timing,
            )
        timing = collected.timing(require_first_delta=False)
        try:
            terminal = _completed_event(
                collected.events,
                label=request.case_id,
                expected_upstream_identity=assertion.upstream_identity,
            )
        except GenerationValidationError as validation_error:
            error = _typed_validation_error(validation_error)
            _finish_request_slot(
                root=root,
                run_id=run_id,
                producer_git_revision=producer_git_revision,
                frozen_input_sha256=frozen.frozen_input_sha256,
                configuration_assertion_sha256=configuration_assertion_sha256,
                slot=slot,
                terminal_type="validation.failed",
                timing=timing,
                error=error,
            )
            return None, _PrivateGenerationFailure(
                slot=slot,
                case_id=request.case_id,
                error=error,
                timing=timing,
            )
        if isinstance(terminal, AnswerFailedEvent):
            _finish_request_slot(
                root=root,
                run_id=run_id,
                producer_git_revision=producer_git_revision,
                frozen_input_sha256=frozen.frozen_input_sha256,
                configuration_assertion_sha256=configuration_assertion_sha256,
                slot=slot,
                terminal_type="answer.failed",
                timing=timing,
                error=terminal.error,
            )
            return None, _PrivateGenerationFailure(
                slot=slot,
                case_id=request.case_id,
                error=terminal.error,
                timing=timing,
            )
        try:
            validated = _validated_case(request, collected, terminal, frozen)
        except (GenerationValidationError, ValidationError, KeyError) as validation_error:
            error = GenerationError(
                category="malformed_output",
                message="completed generation failed local evidence validation",
                retryable=False,
            )
            _finish_request_slot(
                root=root,
                run_id=run_id,
                producer_git_revision=producer_git_revision,
                frozen_input_sha256=frozen.frozen_input_sha256,
                configuration_assertion_sha256=configuration_assertion_sha256,
                slot=slot,
                terminal_type="validation.failed",
                timing=timing,
                error=error,
            )
            return None, _PrivateGenerationFailure(
                slot=slot,
                case_id=request.case_id,
                error=error,
                timing=timing,
            )
        _finish_request_slot(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_git_revision,
            frozen_input_sha256=frozen.frozen_input_sha256,
            configuration_assertion_sha256=configuration_assertion_sha256,
            slot=slot,
            terminal_type="answer.completed",
            timing=validated.timing,
            error=None,
        )
        return validated, None

    try:
        golden_request = build_golden_request(frozen)
        golden_case, failure = await attempt("golden", golden_request)
        if failure is not None or golden_case is None:
            return _MeasurementExecution(cases=tuple(cases), failure=failure)
        cases.append(golden_case)

        follow_up_request = build_follow_up_request(
            frozen, golden_case.answer
        )
        follow_up_case, failure = await attempt("follow-up", follow_up_request)
        if failure is not None or follow_up_case is None:
            return _MeasurementExecution(cases=tuple(cases), failure=failure)
        cases.append(follow_up_case)

        unanswerable_request = build_unanswerable_request(frozen)
        unanswerable_case, failure = await attempt(
            "unanswerable", unanswerable_request
        )
        if failure is not None or unanswerable_case is None:
            return _MeasurementExecution(cases=tuple(cases), failure=failure)
        cases.append(unanswerable_case)
        return _MeasurementExecution(cases=tuple(cases), failure=None)
    finally:
        await client.aclose()


def _assert_sanitized_durable_payload(
    payload: GenerationResult,
    *,
    frozen: FrozenGenerationInputs,
    api_key: str,
) -> None:
    serialized = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
    )
    forbidden_values = (
        api_key,
        SYSTEM_INSTRUCTIONS,
        GOLDEN_QUESTION,
        FOLLOW_UP_QUESTION,
        UNANSWERABLE_QUESTION,
        *(source.text for source in frozen.sources),
    )
    if any(value and value in serialized for value in forbidden_values):
        raise GenerationValidationError(
            "durable generation evidence contains forbidden request material"
        )
    if re.search(r"\bAIza[0-9A-Za-z_-]{20,}\b", serialized):
        raise GenerationValidationError(
            "durable generation evidence contains a Google credential signature"
        )
    if re.search(r"\bsk-[0-9A-Za-z_-]{16,}\b", serialized):
        raise GenerationValidationError(
            "durable generation evidence contains an API credential signature"
        )
    if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", serialized):
        raise GenerationValidationError(
            "durable generation evidence contains an email address"
        )


def run_generation_preflight(
    *,
    root: Path,
    run_id: str,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    producer_revision = _require_clean_producer(root)
    _load_environment(root, run_id)
    frozen = load_frozen_generation_inputs(root=root, run_id=run_id)
    assertion, assertion_sha256 = _load_configuration_assertion(root, run_id)
    values = _environment_values(environ)
    _assert_request_slot_available(
        root=root,
        run_id=run_id,
        producer_git_revision=producer_revision,
        frozen_input_sha256=frozen.frozen_input_sha256,
        configuration_assertion_sha256=assertion_sha256,
        slot="preflight",
    )
    collected, terminal = asyncio.run(
        _run_preflight_request(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_revision,
            frozen=frozen,
            assertion=assertion,
            configuration_assertion_sha256=assertion_sha256,
            environ=values,
            transport=transport,
        )
    )
    if isinstance(terminal, AnswerFailedEvent):
        raise GenerationValidationError(
            "generation preflight failed with typed category "
            f"{terminal.error.category}"
        )
    answer_payload = terminal.answer.model_dump(mode="json")
    timing = collected.timing(require_first_delta=True)
    state = _GenerationPreflightState(
        run_id=run_id,
        producer_git_revision=producer_revision,
        frozen_input_sha256=frozen.frozen_input_sha256,
        configuration_assertion_sha256=assertion_sha256,
        gateway_version=PINNED_GATEWAY_VERSION,
        route_present=True,
        answer_sha256=_sha256_bytes(_canonical_json_bytes(answer_payload)),
        event_types=tuple(event.type for event in collected.events),
        delta_event_count=sum(
            event.type == "answer.delta" for event in collected.events
        ),
        timing=timing,
        usage=terminal.usage,
        identity=terminal.identity,
    )
    path = _preflight_path(root, run_id)
    write_json_atomic(path, state)
    try:
        _GenerationPreflightState.model_validate_json(path.read_text("utf-8"))
    except (OSError, ValidationError) as error:
        raise GenerationValidationError(
            "persisted generation preflight state failed validation"
        ) from error
    serialized = path.read_text("utf-8")
    if (
        values["GENERATION_API_KEY"] in serialized
        or GOLDEN_QUESTION in serialized
        or any(source.text in serialized for source in frozen.sources)
    ):
        raise GenerationValidationError(
            "private generation preflight contains forbidden request material"
        )
    return {
        "run_id": run_id,
        "producer_git_revision": producer_revision,
        "gateway_version": PINNED_GATEWAY_VERSION,
        "requested_model": terminal.identity.requested_model,
        "response_model": terminal.identity.response_model,
        "upstream_identity": terminal.identity.upstream_identity,
        "completed": True,
    }


def _generation_outcome(
    *,
    passed: bool,
    requirement: str,
    observed: Any,
    failure_reason: str | None = None,
) -> ThresholdOutcome:
    return ThresholdOutcome(
        passed=passed,
        requirement=requirement,
        observed=observed,
        failure_reason=None if passed else failure_reason or "generation threshold failed",
    )


def run_generation_measurement(
    *,
    root: Path,
    run_id: str,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    producer_revision = _require_clean_producer(root)
    environment = _load_environment(root, run_id)
    frozen = load_frozen_generation_inputs(root=root, run_id=run_id)
    assertion, assertion_sha256 = _load_configuration_assertion(root, run_id)
    preflight_path = _preflight_path(root, run_id)
    try:
        preflight_encoded = preflight_path.read_bytes()
        preflight = _GenerationPreflightState.model_validate_json(preflight_encoded)
    except FileNotFoundError as error:
        raise GenerationConfigurationError(
            "generation preflight must complete before measurement"
        ) from error
    except (OSError, ValidationError) as error:
        raise GenerationConfigurationError(
            "generation preflight state is invalid"
        ) from error
    if preflight.run_id != run_id:
        raise GenerationConfigurationError("generation preflight run identity changed")
    if preflight.producer_git_revision != producer_revision:
        raise GenerationConfigurationError(
            "generation preflight producer revision changed"
        )
    if preflight.frozen_input_sha256 != frozen.frozen_input_sha256:
        raise GenerationConfigurationError(
            "generation frozen input identity changed after preflight"
        )
    if preflight.configuration_assertion_sha256 != assertion_sha256:
        raise GenerationConfigurationError(
            "gateway configuration assertion changed after preflight"
        )
    initial_ledger = _request_ledger_snapshot(
        root=root,
        run_id=run_id,
        producer_git_revision=producer_revision,
        frozen_input_sha256=frozen.frozen_input_sha256,
        configuration_assertion_sha256=assertion_sha256,
    )
    preflight_attempt = initial_ledger.slots.get("preflight")
    if preflight_attempt is None or preflight_attempt.state != "completed":
        raise GenerationConfigurationError(
            "generation preflight request did not complete successfully"
        )

    values = _environment_values(environ)
    execution = asyncio.run(
        _run_measured_requests(
            root=root,
            run_id=run_id,
            producer_git_revision=producer_revision,
            frozen=frozen,
            assertion=assertion,
            configuration_assertion_sha256=assertion_sha256,
            environ=values,
            transport=transport,
        )
    )
    cases = execution.cases
    expected_case_prefix = (
        GOLDEN_CASE_ID,
        FOLLOW_UP_CASE_ID,
        UNANSWERABLE_CASE_ID,
    )[: len(cases)]
    if tuple(case.case_id for case in cases) != expected_case_prefix:
        raise GenerationValidationError("measured generation case sequence changed")

    validated = _ValidatedGenerationArtifact(
        run_id=run_id,
        producer_git_revision=producer_revision,
        preflight_sha256=_sha256_bytes(preflight_encoded),
        frozen_input_sha256=frozen.frozen_input_sha256,
        source_set_sha256=frozen.source_set_sha256,
        cases=cases,
        failure=execution.failure,
    )
    private_path = _validated_generation_path(root, run_id)
    write_json_atomic(private_path, validated)
    try:
        _ValidatedGenerationArtifact.model_validate_json(
            private_path.read_text("utf-8")
        )
    except (OSError, ValidationError) as error:
        raise GenerationValidationError(
            "persisted validated generation output failed validation"
        ) from error
    private_sha256 = _sha256_bytes(private_path.read_bytes())

    ledger = _request_ledger_snapshot(
        root=root,
        run_id=run_id,
        producer_git_revision=producer_revision,
        frozen_input_sha256=frozen.frozen_input_sha256,
        configuration_assertion_sha256=assertion_sha256,
    )
    attempted_count = ledger.attempted_count
    durable_cases: list[dict[str, Any]] = []
    for case in cases:
        coverage = (
            None
            if case.kind == "unanswerable"
            else claim_marker_coverage(case.answer.answer)
        )
        durable_cases.append(
            {
                "case_id": case.case_id,
                "kind": case.kind,
                "answer_sha256": case.answer_sha256,
                "citation_count": len(case.answer.citations),
                "claim_marker_coverage": coverage,
                "event_types": [event.type for event in case.events],
                "delta_event_count": case.delta_event_count,
                "terminal_event_count": case.terminal_event_count,
                "timing": case.timing.model_dump(mode="json"),
                "usage": case.usage.model_dump(mode="json"),
                "identity": case.identity.model_dump(mode="json"),
                "citation_identities": [
                    record.model_dump(mode="json")
                    for record in case.citation_identities
                ],
            }
        )

    preflight_identity_stable = (
        preflight.identity.configured_model == PINNED_MODEL
        and preflight.identity.requested_model == PINNED_MODEL
        and preflight.identity.response_model == PINNED_MODEL
        and (
            preflight.identity.upstream_identity is None
            or preflight.identity.upstream_identity == assertion.upstream_identity
        )
    )
    all_identities_stable = (
        len(cases) == 3
        and preflight_identity_stable
        and all(
            case.identity.configured_model == PINNED_MODEL
            and case.identity.requested_model == PINNED_MODEL
            and case.identity.response_model == PINNED_MODEL
            and (
                case.identity.upstream_identity is None
                or case.identity.upstream_identity == assertion.upstream_identity
            )
            for case in cases
        )
    )
    all_usage_present = len(cases) == 3 and all(
        case.usage.input_tokens > 0
        and case.usage.output_tokens > 0
        and case.usage.total_tokens
        >= case.usage.input_tokens + case.usage.output_tokens
        for case in cases
    )
    all_streams_valid = len(cases) == 3 and all(
        case.delta_event_count >= 1 and case.terminal_event_count == 1
        for case in cases
    )
    all_latency_present = (
        preflight.timing.ttft_seconds is not None
        and preflight.timing.total_latency_seconds
        >= preflight.timing.ttft_seconds
        and len(cases) == 3
        and all(
            case.timing.ttft_seconds is not None
            and case.timing.total_latency_seconds >= case.timing.ttft_seconds
            for case in cases
        )
    )
    required_slots = {
        "preflight",
        "golden",
        "follow-up",
        "unanswerable",
    }
    exact_request_scope = (
        set(ledger.slots) == required_slots
        and attempted_count == 4
        and all(
            attempt.state == "completed" for attempt in ledger.slots.values()
        )
    )
    no_generation_failure = execution.failure is None
    thresholds = {
        "pinned_gateway_version": _generation_outcome(
            passed=preflight.gateway_version == PINNED_GATEWAY_VERSION,
            requirement="9Router currentVersion is exactly 0.5.81",
            observed=preflight.gateway_version,
            failure_reason="pinned gateway version changed",
        ),
        "direct_route": _generation_outcome(
            passed=assertion.route == PINNED_MODEL
            and assertion.route_kind == "direct"
            and not assertion.fallback_candidates,
            requirement="literal gc/gemini-2.5-flash route is direct with no alias, combo, or fallback",
            observed={
                "route": assertion.route,
                "route_kind": assertion.route_kind,
                "fallback_candidate_count": len(assertion.fallback_candidates),
            },
            failure_reason="generation route is not the pinned direct route",
        ),
        "single_connection_and_account": _generation_outcome(
            passed=assertion.active_connection_ids == (PINNED_CONNECTION_ID,)
            and assertion.selected_account_count == 1,
            requirement="exactly the pinned connection and one selected account are active",
            observed={
                "active_connection_ids": list(assertion.active_connection_ids),
                "selected_account_count": assertion.selected_account_count,
            },
            failure_reason="active connection or selected account count changed",
        ),
        "safe_gateway_features": _generation_outcome(
            passed=not any(
                (
                    assertion.rtk_enabled,
                    assertion.caveman_enabled,
                    assertion.prompt_transforms_enabled,
                    assertion.cloud_sync_enabled,
                    assertion.tunnel_enabled,
                    assertion.body_logging_enabled,
                )
            ),
            requirement="RTK, Caveman, prompt transforms, cloud sync, tunnel, and body logging are disabled",
            observed={
                "rtk_enabled": assertion.rtk_enabled,
                "caveman_enabled": assertion.caveman_enabled,
                "prompt_transforms_enabled": assertion.prompt_transforms_enabled,
                "cloud_sync_enabled": assertion.cloud_sync_enabled,
                "tunnel_enabled": assertion.tunnel_enabled,
                "body_logging_enabled": assertion.body_logging_enabled,
            },
            failure_reason="a disallowed gateway feature is enabled",
        ),
        "existing_quota": _generation_outcome(
            passed=assertion.existing_quota_confirmed,
            requirement="existing quota covers one preflight and exactly three cases without new paid spend",
            observed=assertion.existing_quota_confirmed,
            failure_reason="existing quota was not confirmed",
        ),
        "exact_request_scope": _generation_outcome(
            passed=exact_request_scope,
            requirement="exactly four atomically reserved slots are completed once",
            observed={
                "attempted_slots": list(ledger.slots),
                "slot_states": {
                    slot: attempt.state
                    for slot, attempt in ledger.slots.items()
                },
                "total_requests": attempted_count,
            },
            failure_reason="the four-call request ledger did not complete exactly once",
        ),
        "stream_integrity": _generation_outcome(
            passed=all_streams_valid,
            requirement="every measured call emits at least one delta and exactly one terminal event",
            observed=all_streams_valid,
            failure_reason="one or more measured streams failed integrity checks",
        ),
        "latency_evidence": _generation_outcome(
            passed=all_latency_present,
            requirement="preflight and every measured case have positive ordered TTFT and total latency",
            observed=all_latency_present,
            failure_reason="generation latency evidence is incomplete",
        ),
        "provider_usage": _generation_outcome(
            passed=all_usage_present,
            requirement="provider-reported positive input, output, and total token usage is present for every case",
            observed=all_usage_present,
            failure_reason="provider usage is missing or invalid",
        ),
        "identity_stability": _generation_outcome(
            passed=all_identities_stable,
            requirement="configured, requested, and response identities stay pinned; exposed upstream identity matches",
            observed=all_identities_stable,
            failure_reason="generation identity changed",
        ),
        "three_valid_cases": _generation_outcome(
            passed=len(cases) == 3,
            requirement="golden, bounded follow-up, and unanswerable outputs all pass strict validation on first attempt",
            observed=[case.case_id for case in cases],
            failure_reason="fewer than three generation cases validated",
        ),
        "no_generation_failure": _generation_outcome(
            passed=no_generation_failure,
            requirement="no typed provider or local validation failure occurs",
            observed=(
                None
                if execution.failure is None
                else execution.failure.error.model_dump(mode="json")
            ),
            failure_reason="a typed generation failure occurred",
        ),
        "source_hash_consistency": _generation_outcome(
            passed=True,
            requirement="generation uses the frozen hybrid context, source set, and evidence gold hashes",
            observed={
                "hybrid_result_sha256": frozen.hybrid_result_sha256,
                "golden_context_sha256": frozen.golden_context_sha256,
                "evidence_gold_sha256": frozen.evidence_gold_sha256,
                "source_set_sha256": frozen.source_set_sha256,
            },
        ),
    }
    failure_reasons = [
        outcome.failure_reason or f"{name} failed"
        for name, outcome in thresholds.items()
        if not outcome.passed
    ]
    if execution.failure is not None:
        failure_reasons.append(
            f"{execution.failure.case_id} failed with typed category "
            f"{execution.failure.error.category}"
        )

    result = GenerationResult(
        run_id=run_id,
        provider="gemini-cli",
        requested_model_id=PINNED_MODEL,
        response_model_id=PINNED_MODEL if all_identities_stable else None,
        identities={
            "producer_git_revision": producer_revision,
            "run_initialized_git_revision": environment.run_initialized_git_revision,
            "gateway_version": PINNED_GATEWAY_VERSION,
            "connection_id": PINNED_CONNECTION_ID,
            "active_connection_ids": list(assertion.active_connection_ids),
            "selected_account_count": assertion.selected_account_count,
            "route": assertion.route,
            "route_kind": assertion.route_kind,
            "fallback_candidates": list(assertion.fallback_candidates),
            "requested_model": PINNED_MODEL,
            "response_model": PINNED_MODEL if all_identities_stable else None,
            "configured_upstream_identity": assertion.upstream_identity,
            "preflight_upstream_identity": preflight.identity.upstream_identity,
            "tracked_tree_clean_before_traffic": True,
        },
        measurements={
            "frozen_inputs": {
                "hybrid_result_sha256": frozen.hybrid_result_sha256,
                "golden_context_sha256": frozen.golden_context_sha256,
                "evidence_gold_sha256": frozen.evidence_gold_sha256,
                "source_set_sha256": frozen.source_set_sha256,
                "frozen_input_sha256": frozen.frozen_input_sha256,
                "response_schema_sha256": frozen.response_schema_sha256,
                "system_instructions_sha256": frozen.system_instructions_sha256,
            },
            "preflight": {
                "state_sha256": _sha256_bytes(preflight_encoded),
                "event_types": list(preflight.event_types),
                "delta_event_count": preflight.delta_event_count,
                "terminal_event_count": preflight.terminal_event_count,
                "timing": preflight.timing.model_dump(mode="json"),
                "usage": preflight.usage.model_dump(mode="json"),
                "identity": preflight.identity.model_dump(mode="json"),
            },
            "cases": durable_cases,
            "failure": (
                None
                if execution.failure is None
                else execution.failure.model_dump(mode="json")
            ),
            "validated_generation": {
                "relative_path": str(private_path.relative_to(root)),
                "sha256": private_sha256,
                "case_count": len(cases),
            },
            "request_slots": {
                slot: {
                    "ordinal": attempt.ordinal,
                    "state": attempt.state,
                    "terminal_type": attempt.terminal_type,
                }
                for slot, attempt in ledger.slots.items()
            },
            "live_request_count": attempted_count,
        },
        threshold_outcomes=thresholds,
        failure_reasons=failure_reasons,
    )
    _assert_sanitized_durable_payload(
        result,
        frozen=frozen,
        api_key=values["GENERATION_API_KEY"],
    )
    result_path = (
        root / "qualification" / "results" / run_id / "generation.json"
    )
    write_json_atomic(result_path, result)
    try:
        GenerationResult.model_validate_json(result_path.read_text("utf-8"))
    except (OSError, ValidationError) as error:
        raise GenerationValidationError(
            "persisted durable generation result failed validation"
        ) from error

    summary = {
        "run_id": run_id,
        "passed": not failure_reasons,
        "case_count": len(cases),
        "producer_git_revision": producer_revision,
        "live_request_count": attempted_count,
        "failure_reasons": failure_reasons,
    }
    if failure_reasons:
        return summary

    generation_summary = {
        "status": "qualified",
        "result_relative_path": str(result_path.relative_to(root)),
        "live_request_count": attempted_count,
        "case_count": len(cases),
        "validated_generation_sha256": private_sha256,
    }
    updated_environment = environment.model_copy(
        update={
            "producer_git_revision": producer_revision,
            "identities": {
                **environment.identities,
                "producer_git_revision": producer_revision,
                "generation": {
                    "gateway_version": PINNED_GATEWAY_VERSION,
                    "connection_id": PINNED_CONNECTION_ID,
                    "route": PINNED_MODEL,
                    "requested_model": PINNED_MODEL,
                    "response_model": PINNED_MODEL,
                    "configured_upstream_identity": assertion.upstream_identity,
                    "preflight_upstream_identity": preflight.identity.upstream_identity,
                },
            },
            "measurements": {
                **environment.measurements,
                "generation": generation_summary,
            },
            "threshold_outcomes": {
                **environment.threshold_outcomes,
                **{
                    f"generation_{name}": outcome
                    for name, outcome in thresholds.items()
                },
            },
        }
    )
    environment_path = (
        root / "qualification" / "results" / run_id / "environment.json"
    )
    write_json_atomic(environment_path, updated_environment)
    try:
        EnvironmentResult.model_validate_json(environment_path.read_text("utf-8"))
    except (OSError, ValidationError) as error:
        raise GenerationValidationError(
            "persisted updated environment failed validation"
        ) from error
    return summary


__all__ = [
    "AnswerCompletedEvent",
    "AnswerDeltaEvent",
    "AnswerFailedEvent",
    "BoundedPriorTurn",
    "Citation",
    "FrozenGenerationInputs",
    "GatewayIdentity",
    "GenerationClient",
    "GenerationConfigurationError",
    "GenerationError",
    "GenerationEvent",
    "GenerationRequest",
    "GenerationSource",
    "GenerationUsage",
    "GenerationValidationError",
    "GroundedAnswer",
    "OpenAICompatibleGenerationClient",
    "build_follow_up_request",
    "build_golden_request",
    "build_unanswerable_request",
    "claim_marker_coverage",
    "load_frozen_generation_inputs",
    "load_generation_environment",
    "run_generation_measurement",
    "run_generation_preflight",
    "validate_follow_up",
    "validate_grounded_answer",
    "validate_refusal",
]
