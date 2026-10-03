import asyncio
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import json
from typing import Any

import pytest

from researcy.citations.models import ProposedCitation
from researcy.config import Settings
from researcy.generation.client import GenerationClient
from researcy.generation.models import (
    AnswerAction,
    Claim,
    GenerationEvent,
    GenerationFailure,
    InvalidModelOutput,
    SearchAction,
    validate_action,
)


def test_model_cannot_supply_scope_filters():
    raw = b'{"next_action":"search_same_paper","query":"attention","owner_id":"forged"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_follow_up_cannot_request_a_third_generation_branch():
    raw = b'{"next_action":"search_same_paper","query":"attention"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=True)


# --- Strict Model & Validation Tests ---


def test_validate_action_valid_answer():
    raw = (
        b'{"next_action":"answer","claims":['
        b'{"text":"Self-attention models sequences.","citations":['
        b'{"source_ref":"source_1","evidence_quote":"self-attention connects all positions"}'
        b']}'
        b'],"refusal":null}'
    )
    action = validate_action(raw, follow_up=False)
    assert isinstance(action, AnswerAction)
    assert action.next_action == "answer"
    assert len(action.claims) == 1
    assert action.claims[0].text == "Self-attention models sequences."
    assert len(action.claims[0].citations) == 1
    assert action.claims[0].citations[0].source_ref == "source_1"
    assert action.refusal is None


def test_validate_action_valid_refusal():
    raw = b'{"next_action":"answer","claims":[],"refusal":"The paper does not mention training costs."}'
    action = validate_action(raw, follow_up=False)
    assert isinstance(action, AnswerAction)
    assert len(action.claims) == 0
    assert action.refusal == "The paper does not mention training costs."


def test_validate_action_valid_search():
    raw = b'{"next_action":"search_same_paper","query":"multi-head attention layers"}'
    action = validate_action(raw, follow_up=False)
    assert isinstance(action, SearchAction)
    assert action.next_action == "search_same_paper"
    assert action.query == "multi-head attention layers"


def test_validate_action_refusal_with_claims_rejected():
    raw = (
        b'{"next_action":"answer","claims":['
        b'{"text":"Some text.","citations":[{"source_ref":"s1","evidence_quote":"q1"}]}'
        b'],"refusal":"Contradictory refusal"}'
    )
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_empty_claims_without_refusal_rejected():
    raw = b'{"next_action":"answer","claims":[],"refusal":null}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_more_than_twelve_claims_rejected():
    claims_json = ",".join(
        f'{{"text":"Claim {i}","citations":[{{"source_ref":"s1","evidence_quote":"q1"}}]}}'
        for i in range(13)
    )
    raw = f'{{"next_action":"answer","claims":[{claims_json}],"refusal":null}}'.encode("utf-8")
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_more_than_twenty_four_total_citations_rejected():
    # 7 claims with 4 citations each = 28 citations > 24
    claims_json = ",".join(
        f'{{"text":"Claim {i}","citations":['
        + ",".join(f'{{"source_ref":"s{j}","evidence_quote":"q{j}"}}' for j in range(4))
        + f']}}'
        for i in range(7)
    )
    raw = f'{{"next_action":"answer","claims":[{claims_json}],"refusal":null}}'.encode("utf-8")
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_claim_without_citations_rejected():
    raw = b'{"next_action":"answer","claims":[{"text":"Uncited claim.","citations":[]}],"refusal":null}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_claim_more_than_four_citations_rejected():
    cits = ",".join(f'{{"source_ref":"s{i}","evidence_quote":"q{i}"}}' for i in range(5))
    raw = f'{{"next_action":"answer","claims":[{{"text":"Overcited.","citations":[{cits}]}}],"refusal":null}}'.encode("utf-8")
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_whitespace_only_text_rejected():
    raw = b'{"next_action":"answer","claims":[{"text":"   ","citations":[{"source_ref":"s1","evidence_quote":"q1"}]}],"refusal":null}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_whitespace_only_refusal_rejected():
    raw = b'{"next_action":"answer","claims":[],"refusal":"   \n  "}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_whitespace_only_query_rejected():
    raw = b'{"next_action":"search_same_paper","query":"   "}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_oversized_query_rejected():
    raw = f'{{"next_action":"search_same_paper","query":"{"q" * 2401}"}}'.encode("utf-8")
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_oversized_claim_text_rejected():
    raw = (
        f'{{"next_action":"answer","claims":['
        f'{{"text":"{"a" * 2001}","citations":[{{"source_ref":"s1","evidence_quote":"q1"}}]}}'
        f'],"refusal":null}}'
    ).encode("utf-8")
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_duplicate_json_keys_rejected():
    raw = b'{"next_action":"answer","next_action":"answer","claims":[],"refusal":"Refused"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_trailing_data_rejected():
    raw = b'{"next_action":"search_same_paper","query":"attention"} trailing garbage'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_nan_constant_rejected():
    raw = b'{"next_action":"answer","claims":[],"refusal":NaN}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_unsupported_action_rejected():
    raw = b'{"next_action":"execute_code","code":"import os; os.system(\'ls\')"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_non_object_json_rejected():
    raw = b'["next_action", "answer"]'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_validate_action_malformed_utf8_rejected():
    raw = b'{"next_action":"search_same_paper","query":"\xff\xfe invalid"}'
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)




# --- Preconditions and Guard Tests ---


def test_client_fails_closed_when_unconfigured():
    settings = replace(
        Settings.from_env(),
        generation_endpoint="",
        generation_api_key="",
    )
    client = GenerationClient(settings)

    async def run():
        async for _ in client.stream([{"role": "user", "content": "test"}]):
            pass

    with pytest.raises(GenerationFailure) as exc:
        asyncio.run(run())
    assert exc.value.code == "GENERATION_UNCONFIGURED"


def test_client_rejects_unapproved_model_route():
    settings = replace(
        Settings.from_env(),
        generation_endpoint="http://127.0.0.1:8000/v1",
        generation_api_key="key",
        generation_model="gpt-4o-arbitrary",
    )
    client = GenerationClient(settings)

    async def run():
        async for _ in client.stream([{"role": "user", "content": "test"}]):
            pass

    with pytest.raises(GenerationFailure) as exc:
        asyncio.run(run())
    assert exc.value.code == "INVALID_MODEL"


def test_client_production_rejects_non_tls_endpoint():
    settings = replace(
        Settings.from_env(),
        app_env="production",
        generation_endpoint="http://remote.gateway/v1",
        generation_api_key="key",
    )
    client = GenerationClient(settings)

    async def run():
        async for _ in client.stream([{"role": "user", "content": "test"}]):
            pass

    with pytest.raises(GenerationFailure) as exc:
        asyncio.run(run())
    assert exc.value.code == "INVALID_ENDPOINT"


def test_client_pre_expired_deadline_fails_timeout():
    settings = replace(
        Settings.from_env(),
        generation_endpoint="http://127.0.0.1:8000/v1",
        generation_api_key="key",
    )
    client = GenerationClient(settings)

    async def run():
        async for _ in client.stream(
            [{"role": "user", "content": "test"}],
            deadline=time.monotonic() - 1.0,
        ):
            pass

    with pytest.raises(GenerationFailure) as exc:
        asyncio.run(run())
    assert exc.value.code == "GENERATION_TIMEOUT"


# --- Deterministic Local HTTP Fault Server Tests ---


@contextmanager
def local_fault_server(response_fn):
    class CustomHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            response_fn(self, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), CustomHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_stream_successful_answer_action():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        content_part = (
            '{"next_action":"answer","claims":['
            '{"text":"Self-attention calculates weights.","citations":['
            '{"source_ref":"source_1","evidence_quote":"attention connects positions"}'
            ']}'
            '],"refusal":null}'
        )
        chunk1 = ('data: '+json.dumps({"model":"ag/gemini-3.8-flash-low","choices":[
            {"delta":{"content":content_part},"finish_reason":None}]})+'\n\n').encode()
        chunk2 = b'data: {"model":"ag/gemini-3.8-flash-low","choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":120,"completion_tokens":45,"total_tokens":165}}\n\n'
        chunk3 = b"data: [DONE]\n\n"

        handler.wfile.write(chunk1)
        handler.wfile.flush()
        handler.wfile.write(chunk2)
        handler.wfile.flush()
        handler.wfile.write(chunk3)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-auth-key",
        )
        client = GenerationClient(settings)

        async def run():
            events = []
            async for ev in client.stream([{"role": "user", "content": "Explain attention."}]):
                events.append(ev)
            return events

        events = asyncio.run(run())
        assert events[0].kind == "content"
        assert "next_action" in events[0].text

        terminal = next(event for event in events if event.kind=='completed')
        assert terminal.kind == "completed"
        assert isinstance(terminal.action, AnswerAction)
        assert terminal.action.claims[0].text == "Self-attention calculates weights."
        metadata = next(event for event in events if event.kind=='metadata')
        assert metadata.echoed_model == "ag/gemini-3.8-flash-low"
        assert metadata.finish_reason == "stop"
        assert metadata.usage == {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165}


def test_stream_fragmented_utf8_multibyte_across_chunks():
    # '✨' is \xe2\x9c\xa8 in UTF-8
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        prefix = b'data: {"model":"ag/gemini-3.8-flash-low","choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"attention '
        suffix = b'\\"}"},"finish_reason":null}]}\n\n'

        # Slice 1 ends with \xe2
        slice1 = prefix + b"\xe2"
        # Slice 2 starts with \x9c\xa8
        slice2 = b"\x9c\xa8" + suffix
        done_chunk = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

        handler.wfile.write(slice1)
        handler.wfile.flush()
        time.sleep(0.01)
        handler.wfile.write(slice2)
        handler.wfile.flush()
        handler.wfile.write(done_chunk)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            events = []
            async for ev in client.stream([{"role": "user", "content": "Query"}]):
                events.append(ev)
            return events

        events = asyncio.run(run())
        terminal = events[-1]
        assert terminal.kind == "completed"
        assert isinstance(terminal.action, SearchAction)
        assert "attention ✨" in terminal.action.query


def test_stream_fragmented_sse_and_multiline_data():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        # Split across two chunk writes within the same SSE line
        part1 = b'data: {"model":"ag/gemini-3.8-flash-low","choi'
        part2 = b'ces":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"transformer\\"}"},"finish_reason":null}]}\n\n'
        # Multiline data
        part3 = b'data: {"choices":[\ndata: {"delta":{},"finish_reason":"stop"}\ndata: ]}\n\n'
        part4 = b'data: [DONE]\n\n'

        handler.wfile.write(part1)
        handler.wfile.flush()
        handler.wfile.write(part2)
        handler.wfile.flush()
        handler.wfile.write(part3)
        handler.wfile.flush()
        handler.wfile.write(part4)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            events = []
            async for ev in client.stream([{"role": "user", "content": "Query"}]):
                events.append(ev)
            return events

        events = asyncio.run(run())
        assert events[-1].kind == "completed"
        assert isinstance(events[-1].action, SearchAction)
        assert events[-1].action.query == "transformer"


def test_stream_duplicate_keys_in_model_json_fails_invalid_model_output():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk1 = b'data: {"choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"test\\"}"},"finish_reason":null}]}\n\n'
        chunk2 = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        handler.wfile.write(chunk1 + chunk2)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(InvalidModelOutput):
            asyncio.run(run())


def test_stream_trailing_garbage_fails_invalid_model_output():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk1 = b'data: {"choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"test\\"} extra_garbage"},"finish_reason":null}]}\n\n'
        chunk2 = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        handler.wfile.write(chunk1 + chunk2)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(InvalidModelOutput):
            asyncio.run(run())


def test_stream_unknown_fields_in_model_json_fails_invalid_model_output():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk1 = b'data: {"choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"test\\",\\"unauthorized_scope\\":\\"paper_123\\"}"},"finish_reason":null}]}\n\n'
        chunk2 = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        handler.wfile.write(chunk1 + chunk2)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(InvalidModelOutput):
            asyncio.run(run())


def test_stream_bounds_exceeded_raises_payload_too_large():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        # Emit 2000 bytes when client limit is 1024
        large_content = "a" * 1500
        chunk1 = f'data: {{"choices":[{{"delta":{{"content":"{large_content}"}},"finish_reason":null}}]}}\n\n'.encode()
        handler.wfile.write(chunk1)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
            generation_max_output_bytes=1024,
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "PAYLOAD_TOO_LARGE"


def test_stream_http_429_rate_limited():
    def response_fn(handler, body):
        handler.send_response(429)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(b'{"error":{"message":"Rate limit exceeded"}}')

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "GENERATION_RATE_LIMITED"


def test_stream_http_5xx_unavailable():
    def response_fn(handler, body):
        handler.send_response(503)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(b'{"error":{"message":"Service Unavailable"}}')

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "GENERATION_UNAVAILABLE"


def test_stream_aborted_connection_unexpected_eof():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        handler.wfile.write(b'data: {"choices":[{"delta":{"content":"partial"}\n\n')
        handler.wfile.flush()
        # Abrupt close without finish_reason: "stop" or [DONE]
        handler.close_connection = True

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code in ("INVALID_RESPONSE", "GENERATION_UNAVAILABLE")


def test_stream_timeout_or_deadline_exceeded():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        time.sleep(1.0)

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
            generation_pass_seconds=1,
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream(
                [{"role": "user", "content": "Query"}],
                deadline=time.monotonic() + 0.15,
            ):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "GENERATION_TIMEOUT"


def test_stream_missing_usage_keeps_none_never_invents_zero():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk1 = b'data: {"choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"attention\\"}"},"finish_reason":null}]}\n\n'
        chunk2 = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        chunk3 = b"data: [DONE]\n\n"
        handler.wfile.write(chunk1 + chunk2 + chunk3)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            events = []
            async for ev in client.stream([{"role": "user", "content": "Query"}]):
                events.append(ev)
            return events

        events = asyncio.run(run())
        terminal = events[-1]
        assert terminal.kind == "completed"
        metadata = next(event for event in events if event.kind=='metadata')
        assert metadata.usage is None  # Never invented zeroes




def test_stream_done_without_finish_stop_rejected():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk1 = b'data: {"choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"attention\\"}"},"finish_reason":null}]}\n\n'
        chunk2 = b"data: [DONE]\n\n"
        # Omit finish_reason: "stop"
        handler.wfile.write(chunk1 + chunk2)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "INVALID_RESPONSE"


def test_stream_truncation_finish_reason_length_rejected():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk1 = b'data: {"choices":[{"delta":{"content":"{\\"next_action\\":\\"search_same_paper\\",\\"query\\":\\"attention"},"finish_reason":"length"}]}\n\n'
        chunk2 = b"data: [DONE]\n\n"
        handler.wfile.write(chunk1 + chunk2)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "PAYLOAD_TOO_LARGE"


def test_stream_multiple_choices_rejected():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk = b'data: {"choices":[{"delta":{"content":"1"}},{"delta":{"content":"2"}}]}\n\n'
        handler.wfile.write(chunk)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "INVALID_RESPONSE"


def test_stream_tool_calls_rejected():
    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        chunk = b'data: {"choices":[{"delta":{"tool_calls":[{"id":"call_1"}]}}]}\n\n'
        handler.wfile.write(chunk)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            async for _ in client.stream([{"role": "user", "content": "Query"}]):
                pass

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "INVALID_RESPONSE"


def test_stream_cancellation_closes_connection():
    connection_closed = threading.Event()

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()

        try:
            handler.wfile.write(b'data: {"choices":[{"delta":{"content":"first delta"},"finish_reason":null}]}\n\n')
            handler.wfile.flush()
            # Stalling until cancellation closes socket
            for _ in range(50):
                time.sleep(0.05)
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            connection_closed.set()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
        )
        client = GenerationClient(settings)

        async def run():
            gen = client.stream([{"role": "user", "content": "Query"}])
            ev = await anext(gen)
            assert ev.kind == "content"
            # Cancel iteration by closing the generator early
            await gen.aclose()

        asyncio.run(run())
        assert connection_closed.wait(timeout=2)


@pytest.mark.parametrize('raw',[
    b'{"next_action":"private-provider-marker","claims":[]}',
    b'{"next_action":"answer","claims":[],"private-provider-marker":"secret"}',
    b'{"next_action":"answer","private-provider-marker":1,"private-provider-marker":2}',
])
def test_invalid_action_diagnostics_never_disclose_provider_output(raw):
    import traceback
    with pytest.raises(InvalidModelOutput) as caught:
        validate_action(raw,follow_up=False)
    diagnostic = ''.join(traceback.format_exception(caught.value))
    assert 'private-provider-marker' not in diagnostic


def test_provider_delta_is_delivered_before_provider_finishes():
    release = threading.Event()
    first = '{"next_action":"answer",'
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        data = json.dumps({'choices':[{'delta':{'content':first},'finish_reason':None}]})
        handler.wfile.write(('data: '+data+'\n\n').encode())
        handler.wfile.flush()
        release.wait(timeout=5)
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            stream = GenerationClient(settings).stream([{'role':'user','content':'Question'}])
            try:
                event = await asyncio.wait_for(anext(stream),timeout=2)
                assert event.kind=='content' and event.text==first
                assert not release.is_set()
            finally:
                release.set()
                await stream.aclose()
        asyncio.run(run())


def test_provider_cannot_append_content_after_stop_before_terminal_marker():
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        action = '{"next_action":"answer","claims":[],"refusal":"Insufficient evidence."}'
        data = json.dumps({'choices':[{'delta':{'content':action},'finish_reason':'stop'}]})
        tail = json.dumps({'choices':[{'delta':{'content':' '},'finish_reason':None}]})
        handler.wfile.write(('data: '+data+'\n\ndata: '+tail+'\n\ndata: [DONE]\n\n').encode())
        handler.wfile.flush()
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            async for event in GenerationClient(settings).stream([{'role':'user','content':'Question'}]):
                pass
        with pytest.raises(GenerationFailure) as caught:
            asyncio.run(run())
        assert caught.value.code=='INVALID_RESPONSE'


def _collect_fault_stream(body,content_type='text/event-stream',status=200):
    def response_fn(handler,request_body):
        handler.send_response(status)
        handler.send_header('Content-Type',content_type)
        handler.end_headers()
        handler.wfile.write(body)
        handler.wfile.flush()
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            return [event async for event in GenerationClient(settings).stream([{'role':'user','content':'Question'}])]
        return asyncio.run(run())


def _terminal_wire(usage=None):
    action = '{"next_action":"answer","claims":[],"refusal":"Insufficient evidence."}'
    value = {'choices':[{'delta':{'content':action},'finish_reason':'stop'}]}
    if usage is not None:
        value['usage'] = usage
    return ('data: '+json.dumps(value)+'\n\n').encode()


@pytest.mark.parametrize('usage',[
    {'prompt_tokens':-1,'completion_tokens':1,'total_tokens':0},
    {'prompt_tokens':1,'completion_tokens':True,'total_tokens':2},
    {'prompt_tokens':1,'completion_tokens':2,'total_tokens':'3'},
    {'prompt_tokens':1,'completion_tokens':2,'total_tokens':7},
])
def test_invalid_provider_accounting_is_not_accepted(usage):
    with pytest.raises(GenerationFailure) as caught:
        _collect_fault_stream(_terminal_wire(usage)+b'data: [DONE]\n\n')
    assert caught.value.code=='INVALID_RESPONSE'


def test_unterminated_stop_event_is_not_manufactured_at_eof():
    with pytest.raises(GenerationFailure) as caught:
        _collect_fault_stream(_terminal_wire()[:-1])
    assert caught.value.code=='INVALID_RESPONSE'


@pytest.mark.parametrize('content_type,accepted',[
    ('Text/Event-Stream; charset=utf-8',True),
    ('application/x-text/event-stream',False),
])
def test_sse_media_type_is_an_exact_case_insensitive_token(content_type,accepted):
    wire = _terminal_wire()+b'data: [DONE]\n\n'
    if accepted:
        events = _collect_fault_stream(wire,content_type=content_type)
        assert events[-1].kind=='completed' and events[-1].action.refusal is not None
    else:
        with pytest.raises(GenerationFailure) as caught:
            _collect_fault_stream(wire,content_type=content_type)
        assert caught.value.code=='INVALID_RESPONSE'


def test_all_upstream_server_errors_are_classified_as_dependency_failure():
    with pytest.raises(GenerationFailure) as caught:
        _collect_fault_stream(b'private provider error',status=501)
    assert caught.value.code=='GENERATION_UNAVAILABLE'


def test_pass_timeout_never_cancels_consumer_while_generator_is_suspended():
    release = threading.Event()
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(b'data: {"choices":[{"delta":{"content":"{"},"finish_reason":null}]}\n\n')
        handler.wfile.flush()
        release.wait(timeout=5)
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key',
            generation_pass_seconds=1)
        async def run():
            stream = GenerationClient(settings).stream([{'role':'user','content':'Question'}])
            try:
                assert (await anext(stream)).kind=='content'
                await asyncio.sleep(1.1)
                with pytest.raises(GenerationFailure) as caught:
                    await anext(stream)
                assert caught.value.code=='GENERATION_TIMEOUT'
            finally:
                release.set()
                await stream.aclose()
        asyncio.run(run())


def test_provider_done_closes_an_open_connection_without_waiting_for_eof():
    release = threading.Event()
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(_terminal_wire()+b'data: [DONE]\n\n')
        handler.wfile.flush()
        release.wait(timeout=5)
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            try:
                async def consume():
                    return [event async for event in GenerationClient(settings).stream([{'role':'user','content':'Question'}])]
                events = await asyncio.wait_for(consume(),timeout=2)
                assert events[-1].kind=='completed'
                assert not release.is_set()
            finally:
                release.set()
        asyncio.run(run())


def test_refusal_uses_overall_output_bound_not_the_claim_text_limit():
    refusal = 'Insufficient evidence. '+('The supplied sources do not establish this measurement. '*40)
    action = validate_action(json.dumps({'next_action':'answer','claims':[],'refusal':refusal}).encode(),follow_up=False)
    assert action.refusal==refusal and action.claims==()


def test_actual_usage_remains_observable_when_final_action_is_invalid():
    observed = []
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        value = {'choices':[{'delta':{'content':'{"next_action":"unsupported_action"}'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
        handler.wfile.write(('data: '+json.dumps(value)+'\n\n').encode())
        handler.wfile.flush()
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            async for event in GenerationClient(settings).stream([{'role':'user','content':'Question'}]):
                observed.append(event)
        with pytest.raises(InvalidModelOutput):
            asyncio.run(run())
    metadata = [event for event in observed if event.kind=='metadata']
    assert [event.usage for event in metadata]==[{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}]
    assert all(event.kind!='completed' for event in observed)


def test_leading_utf8_bom_does_not_discard_valid_sse_action():
    events = _collect_fault_stream(b'\xef\xbb\xbf'+_terminal_wire()+b'data: [DONE]\n\n')
    assert events[-1].kind=='completed' and events[-1].action.refusal=='Insufficient evidence.'


def test_provider_backend_identity_cannot_change_within_one_pass():
    first = json.dumps({'model':'backend-a','choices':[{'delta':{'role':'assistant'},'finish_reason':None}]})
    terminal = json.loads(_terminal_wire().decode()[6:])
    terminal['model'] = 'backend-b'
    with pytest.raises(GenerationFailure) as caught:
        _collect_fault_stream(('data: '+first+'\n\ndata: '+json.dumps(terminal)+'\n\n').encode())
    assert caught.value.code=='INVALID_RESPONSE'


@pytest.mark.parametrize('usage',[
    {'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,'prompt_tokens_details':{'cached_tokens':20}},
    {'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,'cached_tokens':2,'prompt_tokens_details':{'cached_tokens':3}},
])
def test_impossible_usage_details_never_become_accounting_metadata(usage):
    with pytest.raises(GenerationFailure) as caught:
        _collect_fault_stream(_terminal_wire(usage))
    assert caught.value.code=='INVALID_RESPONSE'


def test_invalid_provider_compression_has_only_safe_domain_diagnostics():
    import traceback
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.send_header('Content-Encoding','gzip')
        handler.end_headers()
        handler.wfile.write(b'private-invalid-provider-compression')
        handler.wfile.flush()
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            return [event async for event in GenerationClient(settings).stream([{'role':'user','content':'Question'}])]
        with pytest.raises(GenerationFailure) as caught:
            asyncio.run(run())
        assert caught.value.code=='INVALID_RESPONSE'
        assert 'zlib.error' not in ''.join(traceback.format_exception(caught.value))


@pytest.mark.parametrize('omitted',['next_action','claims','refusal'])
def test_required_answer_fields_cannot_be_synthesized(omitted):
    payload = {'next_action':'answer','claims':[],'refusal':'Insufficient evidence.'}
    if omitted=='refusal':
        payload['claims'] = [{'text':'Supported claim.','citations':[{'source_ref':'S1','evidence_quote':'exact quote'}]}]
        payload['refusal'] = None
    del payload[omitted]
    with pytest.raises(InvalidModelOutput):
        validate_action(json.dumps(payload).encode(),follow_up=False)


@pytest.mark.parametrize('limit,reported,accepted',[(8192,8193,False),(8,9,False),(8,8,True)])
def test_provider_usage_must_respect_the_configured_output_token_ceiling(limit,reported,accepted):
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(_terminal_wire({'prompt_tokens':10,'completion_tokens':reported,'total_tokens':10+reported}))
        handler.wfile.flush()
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key',
            generation_max_output_tokens=limit)
        async def run():
            return [event async for event in GenerationClient(settings).stream([{'role':'user','content':'Question'}])]
        if accepted:
            assert asyncio.run(run())[-1].kind=='completed'
        else:
            with pytest.raises(GenerationFailure) as caught:
                asyncio.run(run())
            assert caught.value.code=='INVALID_RESPONSE'


def test_fixed_gateway_reasoning_is_not_a_subset_of_candidate_tokens():
    usage = {'prompt_tokens':90,'completion_tokens':20,'total_tokens':110,
        'completion_tokens_details':{'reasoning_tokens':80}}
    events = _collect_fault_stream(_terminal_wire(usage))
    assert events[-1].kind=='completed'
    assert next(event for event in events if event.kind=='metadata').usage==usage


def test_pass_deadline_closes_provider_while_consumer_holds_a_delta():
    closed = threading.Event()
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(b'data: {"choices":[{"delta":{"content":"{"},"finish_reason":null}]}\n\n')
        handler.wfile.flush()
        handler.connection.settimeout(4)
        if handler.connection.recv(1)==b'':
            closed.set()
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key',
            generation_pass_seconds=1)
        async def run():
            stream = GenerationClient(settings).stream([{'role':'user','content':'Question'}])
            try:
                assert (await anext(stream)).kind=='content'
                assert await asyncio.to_thread(closed.wait,2)
                with pytest.raises(GenerationFailure) as caught:
                    await anext(stream)
                assert caught.value.code=='GENERATION_TIMEOUT'
            finally:
                await stream.aclose()
        asyncio.run(run())


def test_large_unicode_provider_frame_remains_bounded_in_the_pending_content_queue():
    refusal = 'Unsupported measurement. '+('物理学 '*6000)
    action = json.dumps({'next_action':'answer','claims':[],'refusal':refusal},ensure_ascii=False)
    frame = {'choices':[{'delta':{'content':action},'finish_reason':'stop'}]}
    events = _collect_fault_stream(('data: '+json.dumps(frame,ensure_ascii=False)+'\n\n').encode())
    pieces = [event.text for event in events if event.kind=='content']
    assert all(len(piece.encode('utf-8'))<=16384 for piece in pieces)
    assert ''.join(pieces)==action
    assert events[-1].action.refusal==refusal



@pytest.mark.parametrize('bad_val', [r'\u0000', r'\ud800'])
@pytest.mark.parametrize('template', [
    '{"next_action":"answer","claims":[{"text":"Claim with {val}","citations":[{"source_ref":"s1","evidence_quote":"q1"}]}],"refusal":null}',
    '{"next_action":"answer","claims":[{"text":"Valid claim","citations":[{"source_ref":"s1","evidence_quote":"Quote with {val}"}]}],"refusal":null}',
    '{"next_action":"answer","claims":[{"text":"Valid claim","citations":[{"source_ref":"s1{val}","evidence_quote":"q1"}]}],"refusal":null}',
    '{"next_action":"answer","claims":[],"refusal":"Refusal with {val}"}',
    '{"next_action":"search_same_paper","query":"Query with {val}"}',
])
def test_validate_action_rejects_nul_and_lone_surrogates(template, bad_val):
    raw = template.replace('{val}', bad_val).encode('utf-8')
    with pytest.raises(InvalidModelOutput):
        validate_action(raw, follow_up=False)


def test_stream_retains_queued_metadata_when_pass_times_out_after_stop(monkeypatch):
    import researcy.generation.client as client_mod

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    orig_validate_action = client_mod.validate_action
    def timing_out_validate_action(*args, **kwargs):
        clock["now"] = 1010.0
        return orig_validate_action(*args, **kwargs)

    monkeypatch.setattr(client_mod, "validate_action", timing_out_validate_action)

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        handler.wfile.write(_terminal_wire({"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}))
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
            generation_pass_seconds=5,
        )
        observed = []

        async def run():
            client = GenerationClient(settings)
            async for event in client.stream([{"role": "user", "content": "Question"}], deadline=1005.0):
                observed.append((event, clock["now"]))

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())

        assert exc.value.code == "GENERATION_TIMEOUT"
        metadata_events = [e for e, _ in observed if e.kind == "metadata"]
        assert len(metadata_events) == 1
        assert metadata_events[0].usage == {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        assert all(e.kind != "completed" for e, _ in observed)
        assert all(seen <= 1005.0 for e, seen in observed if e.kind == "content")


def test_stream_late_postdeadline_new_metadata_is_not_treated_as_on_time(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    step_provider = threading.Event()

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        handler.wfile.write(b'data: {"choices":[{"delta":{"content":"First "},"finish_reason":null}]}\n\n')
        handler.wfile.flush()
        step_provider.wait(timeout=5.0)
        handler.wfile.write(_terminal_wire({"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}))
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key="test-key",
            generation_pass_seconds=5,
        )
        observed = []

        async def run():
            client = GenerationClient(settings)
            stream = client.stream([{"role": "user", "content": "Question"}], deadline=1005.0)
            first = await anext(stream)
            observed.append(first)
            clock["now"] = 1010.0
            step_provider.set()
            async for event in stream:
                observed.append(event)

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())

        assert exc.value.code == "GENERATION_TIMEOUT"
        assert all(e.kind != "metadata" for e in observed)
        assert all(e.kind != "completed" for e in observed)


def test_stream_retains_on_time_metadata_when_full_queue_times_out(monkeypatch):
    from contextlib import aclosing

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    usage = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
    action = '{"next_action":"answer","claims":[],"refusal":"' + ("No evidence. " * 15) + '"}'

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        for index in range(17):
            text = action[index * len(action) // 17:(index + 1) * len(action) // 17]
            frame = {"choices": [{"delta": {"content": text}, "finish_reason": None}]}
            handler.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode())
        terminal = {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": usage}
        handler.wfile.write(("data: " + json.dumps(terminal) + "\n\ndata: [DONE]\n\n").encode())
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(), generation_endpoint=endpoint,
            generation_api_key="test-key", generation_pass_seconds=5)
        observed = []
        received_at = []

        async def run():
            client = GenerationClient(settings)
            source = client._stream_events
            received = asyncio.Event()

            async def record(*args, **kwargs):
                async with aclosing(source(*args, **kwargs)) as events:
                    async for event in events:
                        if event.kind == "metadata":
                            received_at.append(clock["now"])
                            received.set()
                        yield event

            client._stream_events = record
            stream = client.stream([{"role": "user", "content": "Question"}], deadline=1005.0)
            await anext(stream)
            await received.wait()
            clock["now"] = 1010.0
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            async for event in stream:
                observed.append(event)

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())
        assert exc.value.code == "GENERATION_TIMEOUT"
        assert received_at == [1000.0]
        assert [event.kind for event in observed] == ["metadata"]
        assert observed[0].usage == usage


def test_stream_finish_reason_length_yields_metadata_before_payload_too_large():
    usage = {'prompt_tokens': 50, 'completion_tokens': 100, 'total_tokens': 150}
    observed = []

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        handler.wfile.write(b'data: {"choices":[{"delta":{"content":"Truncated text"},"finish_reason":null}]}\n\n')
        frame = {
            'choices': [{'delta': {}, 'finish_reason': 'length'}],
            'usage': usage,
            'model': 'ag/gemini-3.8-flash-low',
        }
        handler.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
        handler.wfile.write(b'data: [DONE]\n\n')
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(), generation_endpoint=endpoint, generation_api_key='test-key')
        async def run():
            client = GenerationClient(settings)
            async for event in client.stream([{'role': 'user', 'content': 'Question'}]):
                observed.append(event)

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())

        assert exc.value.code == 'PAYLOAD_TOO_LARGE'
        metadata_events = [e for e in observed if e.kind == 'metadata']
        assert len(metadata_events) == 1
        assert metadata_events[0].usage == usage
        assert metadata_events[0].finish_reason == 'length'
        assert metadata_events[0].echoed_model == 'ag/gemini-3.8-flash-low'
        assert all(e.kind != 'completed' for e in observed)


@pytest.mark.parametrize('bad_model', ['ag/gemini\x00flash', 'ag/gemini\ud800flash'])
def test_stream_echoed_model_rejects_nul_and_surrogates(bad_model):
    observed = []

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        action = '{"next_action":"answer","claims":[],"refusal":"Insufficient evidence."}'
        frame = {
            'model': bad_model,
            'choices': [{'delta': {'content': action}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        }
        wire = ('data: ' + json.dumps(frame) + '\n\ndata: [DONE]\n\n').encode('utf-8')
        handler.wfile.write(wire)
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(), generation_endpoint=endpoint, generation_api_key='test-key')
        async def run():
            client = GenerationClient(settings)
            async for event in client.stream([{'role': 'user', 'content': 'Question'}]):
                observed.append(event)

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())

        assert exc.value.code == 'INVALID_RESPONSE'
        assert observed == []


def test_stream_terminal_frame_usage_preserved_when_connection_stalls_before_done():
    cleanup_event = threading.Event()
    usage = {'prompt_tokens': 40, 'completion_tokens': 20, 'total_tokens': 60}
    observed = []

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        action = '{"next_action":"answer","claims":[],"refusal":"Insufficient evidence."}'
        frame = {
            'model': 'ag/gemini-3.8-flash-low',
            'choices': [{'delta': {'content': action}, 'finish_reason': 'stop'}],
            'usage': usage,
        }
        handler.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode('utf-8'))
        handler.wfile.flush()
        cleanup_event.wait(timeout=5.0)

    with local_fault_server(response_fn) as endpoint:
        settings = replace(
            Settings.from_env(),
            generation_endpoint=endpoint,
            generation_api_key='test-key',
            generation_pass_seconds=1,
        )
        async def run():
            client = GenerationClient(settings)
            try:
                async for event in client.stream([{'role': 'user', 'content': 'Question'}], deadline=time.monotonic() + 0.25):
                    observed.append(event)
            finally:
                cleanup_event.set()

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())

        assert exc.value.code == 'GENERATION_TIMEOUT'
        metadata_events = [e for e in observed if e.kind == 'metadata']
        assert len(metadata_events) == 1
        assert metadata_events[0].usage == usage
        assert metadata_events[0].finish_reason == 'stop'
        assert metadata_events[0].echoed_model == 'ag/gemini-3.8-flash-low'
        assert all(e.kind != 'completed' for e in observed)


@pytest.mark.parametrize('conflict_kind', ['usage', 'model', 'negative_usage', 'inconsistent_total'])
def test_stream_conflicting_terminal_frame_invalidates_retained_metadata(conflict_kind):
    initial_usage = {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30}
    observed = []
    checkpoint_history = []

    def on_metadata(event):
        checkpoint_history.append(event)

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        action = '{"next_action":"answer","claims":[],"refusal":"Insufficient evidence."}'
        frame_a = {
            'model': 'ag/gemini-3.8-flash-low',
            'choices': [{'delta': {'content': action}, 'finish_reason': 'stop'}],
            'usage': initial_usage,
        }
        handler.wfile.write(('data: ' + json.dumps(frame_a) + '\n\n').encode('utf-8'))
        handler.wfile.flush()

        if conflict_kind == 'usage':
            conflicting_frame = {
                'choices': [],
                'usage': {'prompt_tokens': 99, 'completion_tokens': 10, 'total_tokens': 109},
            }
        elif conflict_kind in ('negative_usage', 'inconsistent_total'):
            conflicting_frame = {'choices': [], 'usage': {
                'prompt_tokens': -1 if conflict_kind == 'negative_usage' else 20,
                'completion_tokens': 10, 'total_tokens': 999,
            }}
        else:
            conflicting_frame = {
                'model': 'conflicting-backend-model',
                'choices': [],
                'usage': initial_usage,
            }
        handler.wfile.write(('data: ' + json.dumps(conflicting_frame) + '\n\n').encode('utf-8'))
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(), generation_endpoint=endpoint, generation_api_key='test-key')
        async def run():
            client = GenerationClient(settings)
            async for event in client.stream([{'role': 'user', 'content': 'Question'}], on_metadata=on_metadata):
                observed.append(event)

        with pytest.raises(GenerationFailure) as exc:
            asyncio.run(run())

        assert exc.value.code == 'INVALID_RESPONSE'
        metadata_events = [e for e in observed if e.kind == 'metadata']
        assert metadata_events == []
        assert len(checkpoint_history) >= 2
        assert checkpoint_history[0] is not None
        assert checkpoint_history[0].usage == initial_usage
        assert checkpoint_history[-1] is None
