from dataclasses import dataclass
import json
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from researcy.citations.models import ProposedCitation


class InvalidModelOutput(Exception):
    """Raised when model output violates JSON syntax, schema, bounds, or forbidden actions."""


@dataclass(slots=True)
class GenerationFailure(Exception):
    """Safe typed domain failure. Never exposes raw provider payload or secrets."""

    code: str

    def __str__(self) -> str:
        return self.code


def _validate_safe_string(value: str, name: str) -> str:
    if not value.strip():
        raise ValueError(f"{name} cannot be whitespace only")
    if "\x00" in value:
        raise ValueError(f"{name} contains invalid characters")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{name} contains invalid encoding") from exc
    return value


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=2000)
    citations: tuple[ProposedCitation, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_content(self) -> "Claim":
        _validate_safe_string(self.text, "Claim text")
        for cit in self.citations:
            _validate_safe_string(cit.evidence_quote, "Evidence quote")
            _validate_safe_string(cit.source_ref, "Source reference")
        return self


class AnswerAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    next_action: Literal["answer"]
    claims: tuple[Claim, ...]
    refusal: str | None

    @model_validator(mode="after")
    def validate_action(self) -> "AnswerAction":
        if self.refusal is not None:
            _validate_safe_string(self.refusal, "Refusal")
            if len(self.claims) > 0:
                raise ValueError("Refusal action cannot contain claims")
        else:
            if not (1 <= len(self.claims) <= 12):
                raise ValueError("Answer without refusal must have between 1 and 12 claims")
            total_citations = sum(len(c.citations) for c in self.claims)
            if total_citations > 24:
                raise ValueError(f"Total citations ({total_citations}) cannot exceed 24")
        return self


class SearchAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    next_action: Literal["search_same_paper"]
    query: str = Field(min_length=1, max_length=2400)

    @model_validator(mode="after")
    def validate_content(self) -> "SearchAction":
        _validate_safe_string(self.query, "Query")
        return self

READER_INITIAL_OUTPUT = TypeAdapter(AnswerAction | SearchAction)
READER_FINAL_OUTPUT = TypeAdapter(AnswerAction)


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    kind: Literal["content", "metadata", "completed"]
    text: str = ""
    output: BaseModel | None = None
    usage: dict[str, Any] | None = None
    echoed_model: str | None = None
    finish_reason: str | None = None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(val: str) -> None:
    raise ValueError(f"JSON constant not allowed: {val}")


def decode_output(raw: bytes, output: TypeAdapter) -> BaseModel:
    if not isinstance(raw, (bytes, bytearray)):
        raise InvalidModelOutput("Raw output must be bytes")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidModelOutput("Invalid model output encoding.") from None

    if not text.strip():
        raise InvalidModelOutput("Empty model output")

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (ValueError,RecursionError):
        raise InvalidModelOutput("Invalid model output JSON.") from None

    if not isinstance(parsed, dict):
        raise InvalidModelOutput("Model output must be a JSON object")

    try:
        # Respect each role's model strictness; Reader JSON arrays become immutable tuples.
        return output.validate_python(parsed)
    except (ValidationError, ValueError, RecursionError):
        raise InvalidModelOutput("Invalid model output schema.") from None
