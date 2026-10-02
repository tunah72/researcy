from dataclasses import dataclass
import json
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from researcy.citations.models import ProposedCitation


class InvalidModelOutput(Exception):
    """Raised when model output violates JSON syntax, schema, bounds, or forbidden actions."""


@dataclass(slots=True)
class GenerationFailure(Exception):
    """Safe typed domain failure. Never exposes raw provider payload or secrets."""

    code: str

    def __str__(self) -> str:
        return self.code



class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=2000)
    citations: tuple[ProposedCitation, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_content(self) -> "Claim":
        if not self.text.strip():
            raise ValueError("Claim text cannot be whitespace only")
        for cit in self.citations:
            if not cit.evidence_quote.strip():
                raise ValueError("Evidence quote cannot be whitespace only")
            if not cit.source_ref.strip():
                raise ValueError("Source reference cannot be whitespace only")
        return self


class AnswerAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    next_action: Literal["answer"]
    claims: tuple[Claim, ...]
    refusal: str | None

    @model_validator(mode="after")
    def validate_action(self) -> "AnswerAction":
        if self.refusal is not None:
            if not self.refusal.strip():
                raise ValueError("Refusal cannot be whitespace only")
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
        if not self.query.strip():
            raise ValueError("Query cannot be whitespace only")
        return self


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    kind: Literal["content", "metadata", "completed"]
    text: str = ""
    action: AnswerAction | SearchAction | None = None
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


def validate_action(raw: bytes, *, follow_up: bool) -> AnswerAction | SearchAction:
    if not isinstance(raw, (bytes, bytearray)):
        raise InvalidModelOutput("Raw action must be bytes")

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

    if "next_action" not in parsed:
        raise InvalidModelOutput("Missing 'next_action'")

    action_type = parsed["next_action"]
    if action_type == "search_same_paper":
        if follow_up:
            raise InvalidModelOutput("search_same_paper is not allowed in follow-up generation")
        try:
            return SearchAction.model_validate(parsed)
        except (ValidationError, ValueError):
            raise InvalidModelOutput("Invalid search action.") from None
    elif action_type == "answer":
        try:
            return AnswerAction.model_validate(parsed)
        except (ValidationError, ValueError):
            raise InvalidModelOutput("Invalid answer action.") from None
    else:
        raise InvalidModelOutput("Unsupported model action.")
