from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import AsyncIterator, Mapping, Sequence
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
from q0.models import Citation, GroundedAnswer

PINNED_BASE_URL = "http://127.0.0.1:20128/v1"
PINNED_MODEL = "gc/gemini-2.5-flash"
PINNED_GATEWAY_VERSION = "0.5.81"
PINNED_CONNECTION_ID = "2386766d-a7c1-4839-953c-deaeaa10e719"
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
    "validate_follow_up",
    "validate_grounded_answer",
    "validate_refusal",
]
