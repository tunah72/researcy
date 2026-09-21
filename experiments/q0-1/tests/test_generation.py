from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import json
import shutil
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest


RUN_ID = "q0-1-20260921T030640Z-36f32ae"
PINNED_BASE_URL = "http://127.0.0.1:20128/v1"
PINNED_MODEL = "ag/gemini-3.8-flash-low"
PINNED_VERSION = "0.5.81"
PINNED_CONNECTION_ID = "ag/gemini-3.8-flash-low"
MODEL_OWNER = "ag"
UPSTREAM_IDENTITY = "ag/gemini-3.8-flash-low"
RETIRED_MODEL = "gc/gemini-2.5-flash"
RETIRED_CONNECTION_ID = "2386766d-a7c1-4839-953c-deaeaa10e719"
GOLDEN_QUESTION = (
    "Why does scaled dot-product attention divide by the square root of the key "
    "dimension?"
)
FOLLOW_UP_QUESTION = "What failure mode would occur without that scaling?"
UNANSWERABLE_QUESTION = (
    "What carbon footprint did the authors report for training the Transformer?"
)
SOURCE_TEXT = (
    "Synthetic fixture context states that unscaled attention scores become large, "
    "causing softmax gradients to become small."
)
EVIDENCE_QUOTE = (
    "unscaled attention scores become large, causing softmax gradients to become small"
)
SUPPORTED_ANSWER = (
    "Unscaled attention scores can produce small softmax gradients [1]."
)
FOLLOW_UP_ANSWER = (
    "Without the divisor, scaled dot-product attention would produce large scores "
    "and small softmax gradients [1]."
)
SYSTEM_INSTRUCTIONS = """You answer questions about one scientific paper using only the supplied paper context.
Return exactly one JSON object matching the provided GroundedAnswer schema; do not add prose outside it.
For each substantive claim, include a unique positive citation marker such as [1] in the answer and one matching citation object.
Each citation must use a supplied source_ref and an evidence_quote copied verbatim from that source after whitespace normalization.
If the supplied context is insufficient, state that the supplied paper context is insufficient and return no citations.
For a follow-up, use only the bounded prior turn and explicitly name the scientific referent in the answer.
Never use outside knowledge, invent a source, or repair an invalid answer with a second response."""


def generation_module():
    spec = importlib.util.find_spec("q0.generation")
    assert spec is not None, "q0.generation must exist before generation fixtures can pass"
    return importlib.import_module("q0.generation")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def grounded_payload(
    *,
    answer: str = SUPPORTED_ANSWER,
    marker: int = 1,
    source_ref: str = "S1",
    evidence_quote: str = EVIDENCE_QUOTE,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "citations": [
            {
                "marker": marker,
                "source_ref": source_ref,
                "evidence_quote": evidence_quote,
            }
        ],
    }


def completion_sse(
    payload: dict[str, Any],
    *,
    model: str = PINNED_MODEL,
    upstream_identity: str | None = UPSTREAM_IDENTITY,
    include_finish: bool = True,
    include_usage: bool = True,
) -> bytes:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    cut_one = max(1, len(encoded) // 3)
    cut_two = max(cut_one + 1, 2 * len(encoded) // 3)
    fragments = (encoded[:cut_one], encoded[cut_one:cut_two], encoded[cut_two:])
    messages: list[dict[str, Any]] = []
    for fragment in fragments:
        chunk: dict[str, Any] = {
            "id": "chatcmpl-fixture",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": fragment},
                    "finish_reason": None,
                }
            ],
        }
        if upstream_identity is not None:
            chunk["upstream_identity"] = upstream_identity
        messages.append(chunk)
    if include_finish:
        finish: dict[str, Any] = {
            "id": "chatcmpl-fixture",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": "stop"}
            ],
        }
        if upstream_identity is not None:
            finish["upstream_identity"] = upstream_identity
        messages.append(finish)
    if include_usage:
        usage: dict[str, Any] = {
            "id": "chatcmpl-fixture",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [],
            "usage": {
                "prompt_tokens": 91,
                "completion_tokens": 37,
                "total_tokens": 128,
            },
        }
        if upstream_identity is not None:
            usage["upstream_identity"] = upstream_identity
        messages.append(usage)
    lines = [f"data: {json.dumps(message, separators=(',', ':'))}\n\n" for message in messages]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


ResponseFactory = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeSSEServer:
    responders: deque[ResponseFactory]
    requests: list[httpx.Request] = field(default_factory=list)

    @classmethod
    def streaming(cls, body: bytes, *, status_code: int = 200) -> FakeSSEServer:
        content_type = (
            "text/event-stream" if status_code == 200 else "application/json"
        )
        return cls(
            deque(
                [
                    lambda request: httpx.Response(
                        status_code,
                        headers={"content-type": content_type},
                        content=body,
                        request=request,
                    )
                ]
            )
        )

    @classmethod
    def raising(cls, error_factory: Callable[[httpx.Request], Exception]) -> FakeSSEServer:
        def responder(request: httpx.Request) -> httpx.Response:
            raise error_factory(request)

        return cls(deque([responder]))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert self.responders, "fixture received an unexpected retry"
        return self.responders.popleft()(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    @property
    def only_request(self) -> dict[str, Any]:
        assert len(self.requests) == 1
        return json.loads(self.requests[0].content)


@pytest.fixture
def successful_server() -> FakeSSEServer:
    return FakeSSEServer.streaming(completion_sse(grounded_payload()))


def source(g):
    return g.GenerationSource(
        source_ref="S1",
        chunk_id="1706.03762-chunk-fixture",
        paper_id="1706.03762",
        text=SOURCE_TEXT,
        text_sha256=hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest(),
    )


def golden_request(g, *, model: str = PINNED_MODEL):
    return g.GenerationRequest(
        case_id="1706.03762-answer-1",
        kind="answerable",
        question=GOLDEN_QUESTION,
        model=model,
        sources=(source(g),),
    )


def configured_client(g, server: FakeSSEServer, **changes):
    identity_values = {
        "base_url": PINNED_BASE_URL,
        "gateway_version": PINNED_VERSION,
        "connection_id": PINNED_CONNECTION_ID,
        "configured_model": PINNED_MODEL,
    }
    identity_values.update(changes.pop("identity", {}))
    return g.OpenAICompatibleGenerationClient(
        identity=g.GatewayIdentity(**identity_values),
        api_key="fixture-secret",
        transport=server.transport,
        expected_upstream_identity=changes.pop(
            "expected_upstream_identity", UPSTREAM_IDENTITY
        ),
        **changes,
    )


def collect(client, request):
    async def run():
        try:
            return [event async for event in client.stream_answer(request)]
        finally:
            await client.aclose()

    return asyncio.run(run())


def terminal(events):
    terminals = [
        event
        for event in events
        if event.type in {"answer.completed", "answer.failed"}
    ]
    assert len(terminals) == 1
    assert events[-1] is terminals[0]
    return terminals[0]


def test_frozen_inputs_match_the_passing_hybrid_context_and_exact_case_sequence():
    g = generation_module()
    root = Path(__file__).resolve().parents[3]

    frozen = g.load_frozen_generation_inputs(root=root, run_id=RUN_ID)

    assert frozen.hybrid_result_sha256 == (
        "216577d0c170824f361885ffc0c103b088a84dfc27bc1a4c6c7c63af49b33f54"
    )
    assert frozen.golden_context_sha256 == (
        "f7b392c5fcfadc6db7a83db8505acc62d5e9c2dda0f51261a80c133e95392013"
    )
    assert frozen.evidence_gold_sha256 == (
        "858d2547c8dd515eaaad35e8dd73a1597a0dfa9147658128f159d7dab2d820bd"
    )
    assert frozen.case_sequence == (
        "1706.03762-answer-1",
        FOLLOW_UP_QUESTION,
        "1706.03762-unanswerable",
    )
    assert frozen.golden_question == GOLDEN_QUESTION
    assert frozen.unanswerable_question == UNANSWERABLE_QUESTION
    assert [(item.source_ref, item.chunk_id, item.text_sha256) for item in frozen.sources] == [
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
    ]
    assert frozen.system_instructions_sha256 == hashlib.sha256(
        SYSTEM_INSTRUCTIONS.encode("utf-8")
    ).hexdigest()
    assert frozen.request_parameters == {
        "max_retries": 0,
        "max_tokens": 800,
        "model": PINNED_MODEL,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0,
        "timeout_seconds": 60,
        "top_p": 1,
    }
    assert hashlib.sha256(canonical_json(frozen.request_parameters)).hexdigest() == (
        "d5f350c28696bbc8c04c1630384d96f979ae690cc1baf7373ac6e58e136885be"
    )
    assert frozen.frozen_input_sha256 == (
        "79a4593f1d2bf07fdb37558f9124358d8958bf41073ce78011648caf74fed22c"
    )


def test_request_uses_exact_model_schema_stream_usage_and_selected_context(
    successful_server,
):
    g = generation_module()
    client = configured_client(g, successful_server)

    collect(client, golden_request(g))

    request = successful_server.only_request
    assert successful_server.requests[0].url == httpx.URL(
        f"{PINNED_BASE_URL}/chat/completions"
    )
    assert request["model"] == PINNED_MODEL
    assert request["temperature"] == 0
    assert request["top_p"] == 1
    assert request["max_tokens"] == 800
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert request["response_format"]["type"] == "json_schema"
    response_schema = request["response_format"]["json_schema"]
    assert response_schema["name"] == "grounded_answer"
    assert response_schema["strict"] is True
    assert response_schema["schema"]["additionalProperties"] is False
    assert set(response_schema["schema"]["required"]) == {"answer", "citations"}
    assert [message["role"] for message in request["messages"]] == [
        "system",
        "user",
    ]
    assert request["messages"][0]["content"] == SYSTEM_INSTRUCTIONS
    assert request["messages"][1]["content"].count(SOURCE_TEXT) == 1
    assert GOLDEN_QUESTION in request["messages"][1]["content"]


def test_follow_up_sends_exactly_one_bounded_prior_turn(successful_server):
    g = generation_module()
    frozen_answer = g.GroundedAnswer.model_validate(grounded_payload())
    request = g.GenerationRequest(
        case_id="1706.03762-answer-1-follow-up",
        kind="follow_up",
        question=FOLLOW_UP_QUESTION,
        model=PINNED_MODEL,
        sources=(source(g),),
        prior_turn=g.BoundedPriorTurn(
            question=GOLDEN_QUESTION,
            answer=frozen_answer,
        ),
    )
    client = configured_client(g, successful_server)

    collect(client, request)

    messages = successful_server.only_request["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == GOLDEN_QUESTION
    assert json.loads(messages[2]["content"]) == grounded_payload()
    assert FOLLOW_UP_QUESTION in messages[3]["content"]
    assert messages[3]["content"].count(SOURCE_TEXT) == 1


def test_stream_has_ordered_deltas_then_exactly_one_completed_terminal_event(
    successful_server,
):
    g = generation_module()
    events = collect(configured_client(g, successful_server), golden_request(g))

    assert [event.type for event in events] == [
        "answer.delta",
        "answer.delta",
        "answer.delta",
        "answer.completed",
    ]
    assert terminal(events).type == "answer.completed"
    assert "".join(event.delta for event in events[:-1]) == json.dumps(
        grounded_payload(), separators=(",", ":"), ensure_ascii=False
    )


def test_completed_event_preserves_provider_usage_and_stable_identities(
    successful_server,
):
    g = generation_module()
    event = terminal(
        collect(configured_client(g, successful_server), golden_request(g))
    )

    assert event.usage.model_dump() == {
        "input_tokens": 91,
        "output_tokens": 37,
        "total_tokens": 128,
    }
    assert event.identity.configured_model == PINNED_MODEL
    assert event.identity.requested_model == PINNED_MODEL
    assert event.identity.response_model == PINNED_MODEL
    assert event.identity.upstream_identity == UPSTREAM_IDENTITY


@pytest.mark.parametrize(
    ("answer", "match"),
    [
        (
            grounded_payload(source_ref="S9"),
            "unknown source_ref",
        ),
        (
            grounded_payload(evidence_quote="a quote absent from the source"),
            "evidence_quote",
        ),
        (
            {
                "answer": "Supported [1]. Also supported [1].",
                "citations": [
                    {
                        "marker": 1,
                        "source_ref": "S1",
                        "evidence_quote": EVIDENCE_QUOTE,
                    },
                    {
                        "marker": 1,
                        "source_ref": "S1",
                        "evidence_quote": EVIDENCE_QUOTE,
                    },
                ],
            },
            "duplicate citation marker",
        ),
        (
            grounded_payload(marker=0, answer="Unsupported marker [0]."),
            "greater than 0",
        ),
        (
            grounded_payload(answer="A claim with no answer marker."),
            "answer markers",
        ),
        (
            grounded_payload(
                answer=(
                    "Large dot products push softmax into low-gradient regions [1]. "
                    "This second substantive claim is unsupported."
                )
            ),
            "claim-marker coverage",
        ),
    ],
)
def test_grounding_validator_rejects_invalid_citations_and_markers(answer, match):
    g = generation_module()
    with pytest.raises(g.GenerationValidationError, match=match):
        g.validate_grounded_answer(answer, (source(g),), answerable=True)


def test_grounding_validator_accepts_allowed_whitespace_normalization():
    g = generation_module()
    answer = grounded_payload(
        evidence_quote=(
            "unscaled attention scores become large,\n"
            "causing softmax gradients to become small"
        )
    )

    validated = g.validate_grounded_answer(answer, (source(g),), answerable=True)

    assert validated.citations[0].source_ref == "S1"
    assert g.claim_marker_coverage(validated.answer) == 1.0


def test_answerable_and_follow_up_cannot_pass_as_empty_citation_refusals():
    g = generation_module()
    refusal = {
        "answer": "The supplied paper context is insufficient to answer this question.",
        "citations": [],
    }

    with pytest.raises(g.GenerationValidationError, match="requires citations"):
        g.validate_grounded_answer(refusal, (source(g),), answerable=True)
    with pytest.raises(g.GenerationValidationError, match="requires citations"):
        g.validate_follow_up(refusal, (source(g),))


def test_unanswerable_requires_insufficient_context_and_no_citations():
    g = generation_module()
    refusal = g.validate_refusal(
        {
            "answer": "The supplied paper context is insufficient to answer this question.",
            "citations": [],
        }
    )
    assert refusal.citations == []

    with pytest.raises(g.GenerationValidationError, match="empty citations"):
        g.validate_refusal(grounded_payload())
    with pytest.raises(g.GenerationValidationError, match="insufficient"):
        g.validate_refusal({"answer": "I do not know.", "citations": []})


def test_follow_up_must_explicitly_preserve_scaled_dot_product_attention_referent():
    g = generation_module()
    accepted = grounded_payload(answer=FOLLOW_UP_ANSWER)
    assert g.validate_follow_up(accepted, (source(g),)).answer == FOLLOW_UP_ANSWER

    with pytest.raises(g.GenerationValidationError, match="referent"):
        g.validate_follow_up(grounded_payload(), (source(g),))


@pytest.mark.parametrize(
    "mutation",
    [
        {"GENERATION_BASE_URL": "https://api.example.com/v1"},
        {"GENERATION_MODEL": "gc/gemini-2.5-pro"},
        {"Q0_9ROUTER_VERSION": "0.5.82"},
        {"Q0_9ROUTER_CONNECTION_ID": "other-connection"},
        {"GENERATION_API_KEY": ""},
    ],
)
def test_environment_configuration_fails_closed_on_missing_or_nonlocal_identities(
    mutation,
):
    g = generation_module()
    values = {
        "GENERATION_BASE_URL": PINNED_BASE_URL,
        "GENERATION_MODEL": PINNED_MODEL,
        "Q0_9ROUTER_VERSION": PINNED_VERSION,
        "Q0_9ROUTER_CONNECTION_ID": PINNED_CONNECTION_ID,
        "GENERATION_API_KEY": "fixture-secret",
    }
    values.update(mutation)

    with pytest.raises(g.GenerationConfigurationError):
        g.OpenAICompatibleGenerationClient.from_environment(
            values,
            transport=httpx.MockTransport(
                lambda request: pytest.fail("invalid configuration reached transport")
            ),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {
            "GENERATION_MODEL": RETIRED_MODEL,
            "Q0_9ROUTER_CONNECTION_ID": RETIRED_CONNECTION_ID,
        },
        {"GENERATION_MODEL": RETIRED_MODEL},
        {"Q0_9ROUTER_CONNECTION_ID": RETIRED_CONNECTION_ID},
    ],
)
def test_retired_generation_identity_is_rejected_before_transport(
    successful_server, mutation
):
    g = generation_module()
    values = {
        "GENERATION_BASE_URL": PINNED_BASE_URL,
        "GENERATION_MODEL": PINNED_MODEL,
        "Q0_9ROUTER_VERSION": PINNED_VERSION,
        "Q0_9ROUTER_CONNECTION_ID": PINNED_CONNECTION_ID,
        "GENERATION_API_KEY": "fixture-secret",
    }
    values.update(mutation)

    with pytest.raises(g.GenerationConfigurationError):
        g.OpenAICompatibleGenerationClient.from_environment(
            values,
            transport=successful_server.transport,
        )

    assert successful_server.requests == []

def test_environment_configuration_requires_every_pinned_value():
    g = generation_module()
    with pytest.raises(g.GenerationConfigurationError, match="GENERATION_MODEL"):
        g.OpenAICompatibleGenerationClient.from_environment(
            {
                "GENERATION_BASE_URL": PINNED_BASE_URL,
                "GENERATION_API_KEY": "fixture-secret",
                "Q0_9ROUTER_VERSION": PINNED_VERSION,
                "Q0_9ROUTER_CONNECTION_ID": PINNED_CONNECTION_ID,
            },
            transport=httpx.MockTransport(
                lambda request: pytest.fail("invalid configuration reached transport")
            ),
        )


def test_api_key_is_not_exposed_by_client_representation(successful_server):
    g = generation_module()
    client = configured_client(g, successful_server)
    try:
        assert "fixture-secret" not in repr(client)
    finally:
        asyncio.run(client.aclose())


def test_requested_model_mismatch_fails_before_transport(successful_server):
    g = generation_module()
    events = collect(
        configured_client(g, successful_server),
        golden_request(g, model=RETIRED_MODEL),
    )

    event = terminal(events)
    assert event.type == "answer.failed"
    assert event.error.category == "identity_mismatch"
    assert successful_server.requests == []


@pytest.mark.parametrize(
    ("model", "upstream", "expected"),
    [
        (RETIRED_MODEL, UPSTREAM_IDENTITY, "response model"),
        (PINNED_MODEL, "other-provider/other-model", "upstream identity"),
    ],
)
def test_response_or_upstream_identity_mismatch_is_a_typed_terminal_failure(
    model, upstream, expected
):
    g = generation_module()
    server = FakeSSEServer.streaming(
        completion_sse(
            grounded_payload(), model=model, upstream_identity=upstream
        )
    )

    event = terminal(collect(configured_client(g, server), golden_request(g)))

    assert event.type == "answer.failed"
    assert event.error.category == "identity_mismatch"
    assert expected in event.error.message


def test_missing_usage_prevents_completion_and_emits_interrupted_stream():
    g = generation_module()
    server = FakeSSEServer.streaming(
        completion_sse(grounded_payload(), include_usage=False)
    )

    event = terminal(collect(configured_client(g, server), golden_request(g)))

    assert event.type == "answer.failed"
    assert event.error.category == "interrupted_stream"


def test_interrupted_stream_after_delta_has_one_failed_terminal_event():
    g = generation_module()
    server = FakeSSEServer.streaming(
        completion_sse(
            grounded_payload(), include_finish=False, include_usage=False
        )
    )

    events = collect(configured_client(g, server), golden_request(g))

    assert any(event.type == "answer.delta" for event in events)
    event = terminal(events)
    assert event.type == "answer.failed"
    assert event.error.category == "interrupted_stream"


def test_malformed_schema_fails_once_without_format_or_citation_retry():
    g = generation_module()
    invalid = grounded_payload()
    invalid["unexpected"] = "not allowed"
    server = FakeSSEServer.streaming(completion_sse(invalid))

    event = terminal(collect(configured_client(g, server), golden_request(g)))

    assert event.type == "answer.failed"
    assert event.error.category == "malformed_output"
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("status_code", "category", "retryable"),
    [
        (401, "authentication", False),
        (429, "rate_limit", True),
        (503, "unavailable", True),
    ],
)
def test_http_failures_are_typed_and_never_retried(status_code, category, retryable):
    g = generation_module()
    error_body = canonical_json(
        {
            "error": {
                "message": "fixture provider detail must not escape",
                "type": "fixture_error",
                "code": "fixture",
            }
        }
    )
    server = FakeSSEServer.streaming(error_body, status_code=status_code)

    event = terminal(collect(configured_client(g, server), golden_request(g)))

    assert event.type == "answer.failed"
    assert event.error.category == category
    assert event.error.retryable is retryable
    assert "fixture provider detail" not in event.error.message
    assert len(server.requests) == 1


def test_timeout_is_a_typed_terminal_failure_without_retry():
    g = generation_module()
    server = FakeSSEServer.raising(
        lambda request: httpx.ReadTimeout("fixture timeout", request=request)
    )

    event = terminal(collect(configured_client(g, server), golden_request(g)))

    assert event.type == "answer.failed"
    assert event.error.category == "timeout"
    assert event.error.retryable is True
    assert len(server.requests) == 1


def test_sdk_types_do_not_cross_the_generation_boundary(successful_server):
    g = generation_module()
    events = collect(configured_client(g, successful_server), golden_request(g))

    for event in events:
        assert not event.__class__.__module__.startswith("openai")
        if event.type == "answer.completed":
            assert not event.answer.__class__.__module__.startswith("openai")
            assert not event.usage.__class__.__module__.startswith("openai")
            assert not event.identity.__class__.__module__.startswith("openai")
        if event.type == "answer.failed":
            assert not event.error.__class__.__module__.startswith("openai")


@dataclass
class LiveGatewayFixture:
    chat_bodies: deque[bytes]
    model_owned_by: str = MODEL_OWNER
    requests: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url == httpx.URL("http://127.0.0.1:20128/api/version"):
            return httpx.Response(
                200,
                json={"currentVersion": PINNED_VERSION},
                request=request,
            )
        if request.url == httpx.URL(f"{PINNED_BASE_URL}/models"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": PINNED_MODEL,
                            "object": "model",
                            "created": 1,
                            "owned_by": self.model_owned_by,
                        }
                    ],
                },
                request=request,
            )
        if request.url == httpx.URL(f"{PINNED_BASE_URL}/chat/completions"):
            assert self.chat_bodies, "fixture received an extra generation request"
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=self.chat_bodies.popleft(),
                request=request,
            )
        pytest.fail(f"unexpected gateway request: {request.method} {request.url}")

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    @property
    def chat_requests(self) -> list[dict[str, Any]]:
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url == httpx.URL(f"{PINNED_BASE_URL}/chat/completions")
        ]


def copy_frozen_generation_root(tmp_path: Path) -> Path:
    source_root = Path(__file__).resolve().parents[3]
    relative_paths = (
        Path("qualification") / "results" / RUN_ID / "environment.json",
        Path("qualification") / "results" / RUN_ID / "hybrid-retrieval.json",
        Path("qualification")
        / "private"
        / RUN_ID
        / "golden-retrieved-context.json",
        Path("qualification") / "gold" / "evidence.jsonl",
    )
    for relative_path in relative_paths:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative_path, destination)
    assertion = {
        "gateway_version": PINNED_VERSION,
        "connection_id": PINNED_CONNECTION_ID,
        "active_connection_ids": [PINNED_CONNECTION_ID],
        "selected_account_count": 1,
        "route": PINNED_MODEL,
        "route_kind": "direct",
        "fallback_candidates": [],
        "rtk_enabled": False,
        "caveman_enabled": False,
        "prompt_transforms_enabled": False,
        "cloud_sync_enabled": False,
        "tunnel_enabled": False,
        "body_logging_enabled": False,
        "existing_quota_confirmed": True,
        "upstream_identity": UPSTREAM_IDENTITY,
    }
    assertion_path = (
        tmp_path
        / "qualification"
        / "private"
        / RUN_ID
        / "generation-configuration-assertion.json"
    )
    assertion_path.write_text(
        json.dumps(assertion, sort_keys=True) + "\n", encoding="utf-8"
    )
    return tmp_path


def real_context_quote(root: Path) -> str:
    context_path = (
        root
        / "qualification"
        / "private"
        / RUN_ID
        / "golden-retrieved-context.json"
    )
    context = json.loads(context_path.read_text("utf-8"))
    text = context["sources"][0]["text"]
    return text[: min(120, len(text))].strip()


def live_payloads(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    quote = real_context_quote(root)
    golden = {
        "answer": "Scaling prevents attention logits from producing small gradients [1].",
        "citations": [
            {"marker": 1, "source_ref": "S1", "evidence_quote": quote}
        ],
    }
    follow_up = {
        "answer": (
            "Without scaling, scaled dot-product attention would produce unstable "
            "softmax behavior and small gradients [1]."
        ),
        "citations": [
            {"marker": 1, "source_ref": "S1", "evidence_quote": quote}
        ],
    }
    refusal = {
        "answer": "The supplied paper context is insufficient to answer this question.",
        "citations": [],
    }
    return golden, follow_up, refusal


def pinned_environment() -> dict[str, str]:
    return {
        "GENERATION_BASE_URL": PINNED_BASE_URL,
        "GENERATION_MODEL": PINNED_MODEL,
        "Q0_9ROUTER_VERSION": PINNED_VERSION,
        "Q0_9ROUTER_CONNECTION_ID": PINNED_CONNECTION_ID,
        "GENERATION_API_KEY": "fixture-secret",
    }


def test_live_preflight_verifies_gateway_and_persists_only_sanitized_state(
    monkeypatch, tmp_path
):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, _, _ = live_payloads(root)
    gateway = LiveGatewayFixture(deque([completion_sse(golden)]))
    revision = "a" * 40
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: revision)

    summary = g.run_generation_preflight(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    assert summary == {
        "run_id": RUN_ID,
        "producer_git_revision": revision,
        "gateway_version": PINNED_VERSION,
        "requested_model": PINNED_MODEL,
        "response_model": PINNED_MODEL,
        "upstream_identity": UPSTREAM_IDENTITY,
        "completed": True,
    }
    assert [request.url.path for request in gateway.requests] == [
        "/api/version",
        "/v1/models",
        "/v1/chat/completions",
    ]
    assert all(
        request.headers["authorization"] == "Bearer fixture-secret"
        for request in gateway.requests
    )
    state_path = (
        root
        / "qualification"
        / "private"
        / RUN_ID
        / "generation-preflight.json"
    )
    serialized = state_path.read_text("utf-8")
    state = json.loads(serialized)
    assert state["answer_sha256"]
    assert state["event_types"][-1] == "answer.completed"
    assert "fixture-secret" not in serialized
    assert real_context_quote(root) not in serialized
    assert GOLDEN_QUESTION not in serialized


def test_live_preflight_rejects_wrong_model_owner_before_chat_request(
    monkeypatch, tmp_path
):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, _, _ = live_payloads(root)
    gateway = LiveGatewayFixture(
        deque([completion_sse(golden)]),
        model_owned_by="gc",
    )
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "a" * 40)

    with pytest.raises(g.GenerationConfigurationError, match="owner"):
        g.run_generation_preflight(
            root=root,
            run_id=RUN_ID,
            environ=pinned_environment(),
            transport=gateway.transport,
        )

    assert gateway.chat_requests == []

def test_live_preflight_rejects_unsafe_configuration_before_any_request(
    monkeypatch, tmp_path
):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    assertion_path = (
        root
        / "qualification"
        / "private"
        / RUN_ID
        / "generation-configuration-assertion.json"
    )
    assertion = json.loads(assertion_path.read_text("utf-8"))
    assertion["selected_account_count"] = 2
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")
    gateway = LiveGatewayFixture(deque())
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "a" * 40)

    with pytest.raises(g.GenerationConfigurationError, match="selected account"):
        g.run_generation_preflight(
            root=root,
            run_id=RUN_ID,
            environ=pinned_environment(),
            transport=gateway.transport,
        )

    assert gateway.requests == []


def test_live_run_sends_exactly_three_cases_and_writes_sanitized_gate_result(
    monkeypatch, tmp_path
):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, follow_up, refusal = live_payloads(root)
    gateway = LiveGatewayFixture(
        deque(
            [
                completion_sse(golden),
                completion_sse(golden),
                completion_sse(follow_up),
                completion_sse(refusal),
            ]
        )
    )
    revision = "b" * 40
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: revision)
    g.run_generation_preflight(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    summary = g.run_generation_measurement(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    assert summary == {
        "run_id": RUN_ID,
        "passed": True,
        "case_count": 3,
        "producer_git_revision": revision,
        "live_request_count": 4,
        "failure_reasons": [],
    }
    assert len(gateway.chat_requests) == 4
    measured_requests = gateway.chat_requests[1:]
    assert GOLDEN_QUESTION in measured_requests[0]["messages"][-1]["content"]
    assert FOLLOW_UP_QUESTION in measured_requests[1]["messages"][-1]["content"]
    assert UNANSWERABLE_QUESTION in measured_requests[2]["messages"][-1]["content"]
    assert [message["role"] for message in measured_requests[1]["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    result_path = root / "qualification" / "results" / RUN_ID / "generation.json"
    serialized = result_path.read_text("utf-8")
    result = json.loads(serialized)
    assert result["failure_reasons"] == []
    assert result["provider"] == "antigravity"
    assert result["identities"]["model_owner"] == MODEL_OWNER
    assert all(
        outcome["passed"] for outcome in result["threshold_outcomes"].values()
    )
    assert all(
        outcome["failure_reason"] is None
        for outcome in result["threshold_outcomes"].values()
    )
    assert [case["case_id"] for case in result["measurements"]["cases"]] == [
        "1706.03762-answer-1",
        "1706.03762-answer-1-follow-up",
        "1706.03762-unanswerable",
    ]
    assert result["measurements"]["live_request_count"] == 4
    assert result["measurements"]["preflight"]["timing"]["ttft_seconds"] > 0
    assert (
        result["measurements"]["preflight"]["timing"]["total_latency_seconds"]
        >= result["measurements"]["preflight"]["timing"]["ttft_seconds"]
    )
    for case in result["measurements"]["cases"]:
        assert case["timing"]["ttft_seconds"] > 0
        assert case["timing"]["total_latency_seconds"] >= case["timing"]["ttft_seconds"]
    assert "fixture-secret" not in serialized
    assert real_context_quote(root) not in serialized
    assert GOLDEN_QUESTION not in serialized
    private_path = (
        root
        / "qualification"
        / "private"
        / RUN_ID
        / "validated-generation.json"
    )
    private = json.loads(private_path.read_text("utf-8"))
    assert len(private["cases"]) == 3
    assert private["cases"][0]["answer"] == golden
    assert private["failure"] is None
    assert all(case["timing"]["ttft_seconds"] > 0 for case in private["cases"])
    ledger = json.loads(
        (
            root
            / "qualification"
            / "private"
            / RUN_ID
            / "generation-request-ledger.json"
        ).read_text("utf-8")
    )
    assert set(ledger["slots"]) == {
        "preflight",
        "golden",
        "follow-up",
        "unanswerable",
    }
    assert all(attempt["state"] == "completed" for attempt in ledger["slots"].values())
    environment = json.loads(
        (
            root / "qualification" / "results" / RUN_ID / "environment.json"
        ).read_text("utf-8")
    )
    assert environment["producer_git_revision"] == revision
    assert environment["identities"]["generation"]["route"] == PINNED_MODEL
    assert environment["identities"]["generation"]["model_owner"] == MODEL_OWNER


def test_generation_run_cli_returns_nonzero_when_gate_fails(
    monkeypatch, capsys, tmp_path
):
    from q0.cli import main as cli_main

    def fail_gate(*, root, run_id, environ):
        return {
            "run_id": run_id,
            "passed": False,
            "failure_reasons": ["provider usage was missing"],
        }

    monkeypatch.setattr("q0.generation.run_generation_measurement", fail_gate)
    environment_path = tmp_path / "experiments" / "q0-1" / ".env"
    environment_path.parent.mkdir(parents=True)
    environment_path.write_text(
        "\n".join(f"{name}={value}" for name, value in pinned_environment().items())
        + "\n",
        encoding="utf-8",
    )

    exit_code = cli_main(
        [
            "generation",
            "run",
            "--run-id",
            RUN_ID,
            "--root",
            str(tmp_path),
        ]
    )

    assert exit_code == 2
    assert "generation gate failed: provider usage was missing" in capsys.readouterr().err


def test_preflight_slot_cannot_be_attempted_twice(monkeypatch, tmp_path):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, _, _ = live_payloads(root)
    gateway = LiveGatewayFixture(deque([completion_sse(golden)]))
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "a" * 40)

    g.run_generation_preflight(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    with pytest.raises(g.GenerationConfigurationError, match="already attempted"):
        g.run_generation_preflight(
            root=root,
            run_id=RUN_ID,
            environ=pinned_environment(),
            transport=gateway.transport,
        )
    assert len(gateway.chat_requests) == 1


def test_crash_after_atomic_reservation_cannot_reopen_preflight_slot(
    monkeypatch, tmp_path
):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    gateway = LiveGatewayFixture(deque())
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "a" * 40)

    class SimulatedCrash(BaseException):
        pass

    async def crash_after_reservation(client, request):
        raise SimulatedCrash

    monkeypatch.setattr(g, "_collect_events", crash_after_reservation)
    with pytest.raises(SimulatedCrash):
        g.run_generation_preflight(
            root=root,
            run_id=RUN_ID,
            environ=pinned_environment(),
            transport=gateway.transport,
        )

    ledger_path = (
        root
        / "qualification"
        / "private"
        / RUN_ID
        / "generation-request-ledger.json"
    )
    ledger = json.loads(ledger_path.read_text("utf-8"))
    assert ledger["slots"]["preflight"]["state"] == "reserved"
    request_count = len(gateway.requests)
    with pytest.raises(g.GenerationConfigurationError, match="already attempted"):
        g.run_generation_preflight(
            root=root,
            run_id=RUN_ID,
            environ=pinned_environment(),
            transport=gateway.transport,
        )
    assert len(gateway.requests) == request_count


def test_completed_event_preserves_zero_delta_typed_failure():
    g = generation_module()
    failure = g.AnswerFailedEvent(
        error=g.GenerationError(
            category="authentication",
            message="generation authentication failed",
            retryable=False,
            status_code=401,
        )
    )

    terminal_event = g._completed_event(
        [failure],
        label="fixture",
        expected_upstream_identity=UPSTREAM_IDENTITY,
    )

    assert terminal_event is failure
    assert terminal_event.error.category == "authentication"


def test_live_preflight_accepts_unexposed_upstream_identity(monkeypatch, tmp_path):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, _, _ = live_payloads(root)
    gateway = LiveGatewayFixture(
        deque([completion_sse(golden, upstream_identity=None)])
    )
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "a" * 40)

    summary = g.run_generation_preflight(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    assert summary["completed"] is True
    assert summary["upstream_identity"] is None


def test_failed_threshold_leaves_environment_byte_identical(monkeypatch, tmp_path):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, follow_up, refusal = live_payloads(root)
    gateway = LiveGatewayFixture(
        deque(
            [
                completion_sse(golden),
                completion_sse(golden),
                completion_sse(follow_up),
                completion_sse(refusal),
            ]
        )
    )
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "b" * 40)
    environment_path = (
        root / "qualification" / "results" / RUN_ID / "environment.json"
    )
    environment_before = environment_path.read_bytes()
    g.run_generation_preflight(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )
    preflight_path = (
        root
        / "qualification"
        / "private"
        / RUN_ID
        / "generation-preflight.json"
    )
    preflight = json.loads(preflight_path.read_text("utf-8"))
    preflight["gateway_version"] = "0.5.80"
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

    summary = g.run_generation_measurement(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    assert summary["passed"] is False
    assert summary["live_request_count"] == 4
    assert environment_path.read_bytes() == environment_before
    durable = json.loads(
        (
            root / "qualification" / "results" / RUN_ID / "generation.json"
        ).read_text("utf-8")
    )
    assert durable["threshold_outcomes"]["pinned_gateway_version"]["passed"] is False


def test_measurement_failure_is_typed_persisted_and_stops_later_cases(
    monkeypatch, tmp_path
):
    g = generation_module()
    root = copy_frozen_generation_root(tmp_path)
    golden, _, _ = live_payloads(root)
    gateway = LiveGatewayFixture(
        deque(
            [
                completion_sse(golden),
                b"data: [DONE]\n\n",
            ]
        )
    )
    monkeypatch.setattr(g, "_require_clean_producer", lambda root: "c" * 40)
    environment_path = (
        root / "qualification" / "results" / RUN_ID / "environment.json"
    )
    environment_before = environment_path.read_bytes()
    g.run_generation_preflight(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    summary = g.run_generation_measurement(
        root=root,
        run_id=RUN_ID,
        environ=pinned_environment(),
        transport=gateway.transport,
    )

    assert summary["passed"] is False
    assert summary["case_count"] == 0
    assert summary["live_request_count"] == 2
    assert len(gateway.chat_requests) == 2
    private = json.loads(
        (
            root
            / "qualification"
            / "private"
            / RUN_ID
            / "validated-generation.json"
        ).read_text("utf-8")
    )
    assert private["cases"] == []
    assert private["failure"]["slot"] == "golden"
    assert private["failure"]["case_id"] == "1706.03762-answer-1"
    assert private["failure"]["error"]["category"] == "interrupted_stream"
    ledger = json.loads(
        (
            root
            / "qualification"
            / "private"
            / RUN_ID
            / "generation-request-ledger.json"
        ).read_text("utf-8")
    )
    assert set(ledger["slots"]) == {"preflight", "golden"}
    assert ledger["slots"]["golden"]["state"] == "failed"
    durable = json.loads(
        (
            root / "qualification" / "results" / RUN_ID / "generation.json"
        ).read_text("utf-8")
    )
    assert durable["measurements"]["failure"]["case_id"] == "1706.03762-answer-1"
    assert durable["measurements"]["failure"]["error"]["category"] == "interrupted_stream"
    assert durable["measurements"]["live_request_count"] == 2
    assert environment_path.read_bytes() == environment_before
