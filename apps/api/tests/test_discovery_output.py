import asyncio
from dataclasses import replace
import json
import threading
import time

import httpx2
import pytest

from researcy.config import Settings
from researcy.discovery.models import (
    DISCOVERY_INITIAL_OUTPUT,
    DISCOVERY_REASONS_OUTPUT,
    DiscoveryReasons,
    SearchArxivAction,
    StopDiscoveryAction,
)
from researcy.generation.client import GenerationClient
from researcy.generation import models
from researcy.generation.models import AnswerAction, GenerationFailure, InvalidModelOutput
from test_generation import gateway_settings, local_fault_server


@pytest.mark.parametrize('raw', [
    b'{"next_action":"search_arxiv_metadata","query":"attention"}',
    b'{"next_action":"search_arxiv_metadata","url":"https://hostile.example"}',
    b'{"next_action":"search_arxiv_metadata","owner_id":"forged"}',
    b'{"next_action":"search_arxiv_metadata","next_action":"stop"}',
    b'{"next_action":"import_paper"}',
    b'{"next_action":"answer","claims":[],"refusal":"No evidence."}',
    b'{"next_action":1}',
    b'{"next_action":"stop"} {"next_action":"search_arxiv_metadata"}',
    b'{"next_action":"stop"} trailing',
    b'{"next_action":NaN}',
    b'{"next_action":Infinity}',
    b'{"next_action":-Infinity}',
    b'{"next_action":"\xff"}',
    b'[ {"next_action":"stop"} ]',
    b'null',
    b' ',
])
def test_discovery_decoder_rejects_untrusted_action_envelopes(raw):
    with pytest.raises(InvalidModelOutput):
        models.decode_output(raw, DISCOVERY_INITIAL_OUTPUT)


@pytest.mark.parametrize('bidi_char', [
    '\u202a',  # LRE
    '\u202b',  # RLE
    '\u202d',  # LRO
    '\u202e',  # RLO
    '\u202c',  # PDF
    '\u2066',  # LRI
    '\u2067',  # RLI
    '\u2068',  # FSI
    '\u2069',  # PDI
])
def test_discovery_decoder_rejects_bidi_controls_in_reason(bidi_char):
    raw = json.dumps({'papers': [{'arxiv_id': '2005.11401', 'reason': f'Topic {bidi_char} explanation'}]}).encode()
    with pytest.raises(InvalidModelOutput):
        models.decode_output(raw, DISCOVERY_REASONS_OUTPUT)


def test_discovery_decoder_allows_safe_unicode_in_reason():
    # Legitimate non-bidi unicode (e.g. ZWJ, em-dash, accented characters) is preserved
    raw = json.dumps({'papers': [{'arxiv_id': '2005.11401', 'reason': 'Étude on attention — with \u200d ZWJ'}]}).encode()
    result = models.decode_output(raw, DISCOVERY_REASONS_OUTPUT)
    assert result.papers[0].reason == 'Étude on attention — with \u200d ZWJ'


@pytest.mark.parametrize('raw', [
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"   \\n\\t"}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"\\u0000"}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"\\ud800"}]}',
    b'{"papers":[{"arxiv_id":2005,"reason":"Shared topic."}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":7}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":null}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"Shared topic.","title":"Invented title"}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"Shared topic.","url":"https://hostile.example"}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"Shared topic.","reason":"Other reason."}]}',
    b'{"papers":[]}',
    b'{"papers":{},"next_action":"search_arxiv_metadata"}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"Shared topic."}],"owner_id":"forged"}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":NaN}]}',
    b'{"papers":[{"arxiv_id":"2005.11401","reason":"Shared topic."}]} null',
])
def test_discovery_decoder_rejects_invalid_reasons_as_a_whole(raw):
    with pytest.raises(InvalidModelOutput):
        models.decode_output(raw, DISCOVERY_REASONS_OUTPUT)


def test_discovery_decoder_rejects_four_recommendations():
    raw = json.dumps({'papers':[
        {'arxiv_id':arxiv_id,'reason':'A shared metadata topic.'}
        for arxiv_id in ('2005.11401','1706.03762','1810.04805','1907.11692')
    ]}).encode()
    with pytest.raises(InvalidModelOutput):
        models.decode_output(raw, DISCOVERY_REASONS_OUTPUT)


def test_discovery_decoder_rejects_oversized_reason():
    raw = json.dumps({'papers':[{'arxiv_id':'2005.11401','reason':'x'*1001}]}).encode()
    with pytest.raises(InvalidModelOutput):
        models.decode_output(raw, DISCOVERY_REASONS_OUTPUT)


@pytest.mark.parametrize('raw', ['{"next_action":"stop"}', None])
def test_decoder_requires_raw_utf8_bytes(raw):
    with pytest.raises(InvalidModelOutput):
        models.decode_output(raw, DISCOVERY_INITIAL_OUTPUT)


def test_reader_json_arrays_still_decode_to_immutable_claims_and_citations():
    raw = b'{"next_action":"answer","claims":[{"text":"Attention connects positions.","citations":[{"source_ref":"S1","evidence_quote":"attention connects positions"}]}],"refusal":null}'
    answer = models.decode_output(raw, models.READER_INITIAL_OUTPUT)
    assert isinstance(answer, AnswerAction)
    assert isinstance(answer.claims, tuple)
    assert isinstance(answer.claims[0].citations, tuple)
    assert answer.claims[0].text == 'Attention connects positions.'
    assert answer.claims[0].citations[0].source_ref == 'S1'


def _wire(content, *, finish='stop', done=True):
    frame = {'model':'controlled-discovery-route',
        'choices':[{'delta':{'content':content},'finish_reason':finish}],
        'usage':{'prompt_tokens':23,'completion_tokens':7,'total_tokens':30}}
    return ('data: '+json.dumps(frame,ensure_ascii=False)+'\n\n'
        +('data: [DONE]\n\n' if done else '')).encode()


@pytest.mark.parametrize('content,output,schema_name,expected_type', [
    ('{"next_action":"search_arxiv_metadata"}', DISCOVERY_INITIAL_OUTPUT, 'discovery_action', SearchArxivAction),
    ('{"next_action":"stop"}', DISCOVERY_INITIAL_OUTPUT, 'discovery_action', StopDiscoveryAction),
    ('{"papers":[{"arxiv_id":"2005.11401","reason":"Shared attention metadata — not PDF evidence."}]}',
        DISCOVERY_REASONS_OUTPUT, 'discovery_reasons', DiscoveryReasons),
])
def test_local_http_stream_decodes_explicit_discovery_outputs(content,output,schema_name,expected_type):
    requests = []
    wire = _wire(content)
    def respond(handler, body):
        requests.append(json.loads(body))
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        for start in range(0,len(wire),7):
            handler.wfile.write(wire[start:start+7])
            handler.wfile.flush()
    with local_fault_server(respond) as endpoint:
        settings = gateway_settings(generation_endpoint=endpoint,generation_api_key='isolated-test-only')
        checkpoints = []
        async def run():
            return [event async for event in GenerationClient(settings).stream(
                [{'role':'user','content':'Use only the supplied public metadata.'}],
                output=output,schema_name=schema_name,on_metadata=checkpoints.append)]
        events = asyncio.run(run())
    completed = [event for event in events if event.kind=='completed']
    assert len(completed) == 1
    assert isinstance(completed[0].output,expected_type)
    if isinstance(completed[0].output,DiscoveryReasons):
        assert completed[0].output.papers[0].reason == 'Shared attention metadata — not PDF evidence.'
    else:
        assert completed[0].output.next_action == json.loads(content)['next_action']
    assert ''.join(event.text for event in events if event.kind=='content') == content
    metadata = [event for event in events if event.kind=='metadata']
    assert len(metadata) == 1
    assert metadata[0].usage == {'prompt_tokens':23,'completion_tokens':7,'total_tokens':30}
    assert checkpoints[-1].usage == metadata[0].usage
    assert len(requests) == 1
    assert 'response_format' not in requests[0]
    assert 'tools' not in requests[0]


@pytest.mark.parametrize('content,output,schema_name', [
    ('{"next_action":"search_arxiv_metadata","url":"https://hostile.example"}', DISCOVERY_INITIAL_OUTPUT, 'discovery_action'),
    ('{"next_action":"search_arxiv_metadata","next_action":"stop"}', DISCOVERY_INITIAL_OUTPUT, 'discovery_action'),
    ('{"next_action":"import_paper"}', DISCOVERY_INITIAL_OUTPUT, 'discovery_action'),
    ('{"papers":[{"arxiv_id":"2005.11401","reason":" "}]}', DISCOVERY_REASONS_OUTPUT, 'discovery_reasons'),
])
def test_local_http_invalid_output_never_reaches_tool_and_retains_terminal_usage(content,output,schema_name):
    requests,observed,checkpoints,tools = [],[],[],[]
    def respond(handler, body):
        requests.append(json.loads(body))
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(_wire(content))
        handler.wfile.flush()
    with local_fault_server(respond) as endpoint:
        settings = gateway_settings(generation_endpoint=endpoint,generation_api_key='isolated-test-only')
        async def run():
            async for event in GenerationClient(settings).stream(
                [{'role':'user','content':'Use only the supplied public metadata.'}],
                output=output,schema_name=schema_name,on_metadata=checkpoints.append):
                observed.append(event)
                if event.kind=='completed' and isinstance(event.output,SearchArxivAction):
                    tools.append(event.output.next_action)
        with pytest.raises(InvalidModelOutput):
            asyncio.run(run())
    assert tools == []
    assert not any(event.kind=='completed' for event in observed)
    metadata = [event for event in observed if event.kind=='metadata']
    assert len(metadata) == 1
    assert metadata[0].usage == {'prompt_tokens':23,'completion_tokens':7,'total_tokens':30}
    assert metadata[0].finish_reason == 'stop'
    assert checkpoints[-1].usage == metadata[0].usage
    assert len(requests) == 1


@pytest.mark.parametrize('finish',['length','max_tokens'])
def test_local_http_truncated_discovery_output_preserves_usage_without_retry(finish):
    requests,observed = [],[]
    def respond(handler, body):
        requests.append(json.loads(body))
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(_wire('{"next_action":"search_arxiv_',finish=finish))
        handler.wfile.flush()
    with local_fault_server(respond) as endpoint:
        settings = gateway_settings(generation_endpoint=endpoint,generation_api_key='isolated-test-only')
        async def run():
            async for event in GenerationClient(settings).stream(
                [{'role':'user','content':'Public metadata only.'}],
                output=DISCOVERY_INITIAL_OUTPUT,schema_name='discovery_action'):
                observed.append(event)
        with pytest.raises(GenerationFailure) as caught:
            asyncio.run(run())
    assert caught.value.code == 'PAYLOAD_TOO_LARGE'
    assert not any(event.kind=='completed' for event in observed)
    metadata = [event for event in observed if event.kind=='metadata']
    assert len(metadata) == 1
    assert metadata[0].finish_reason == finish
    assert metadata[0].usage == {'prompt_tokens':23,'completion_tokens':7,'total_tokens':30}
    assert len(requests) == 1


def test_local_http_discovery_deadline_retains_received_terminal_usage_without_retry():
    release = threading.Event()
    requests,observed,checkpoints = [],[],[]
    def respond(handler, body):
        requests.append(json.loads(body))
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        handler.wfile.write(_wire('{"next_action":"stop"}',done=False))
        handler.wfile.flush()
        release.wait(2)
    with local_fault_server(respond) as endpoint:
        settings = gateway_settings(generation_endpoint=endpoint,generation_api_key='isolated-test-only')
        async def run():
            async for event in GenerationClient(settings).stream(
                [{'role':'user','content':'Public metadata only.'}],
                output=DISCOVERY_INITIAL_OUTPUT,schema_name='discovery_action',
                deadline=time.monotonic()+0.3,on_metadata=checkpoints.append):
                observed.append(event)
        try:
            with pytest.raises(GenerationFailure) as caught:
                asyncio.run(run())
        finally:
            release.set()
    assert caught.value.code == 'GENERATION_TIMEOUT'
    assert not any(event.kind=='completed' for event in observed)
    metadata = [event for event in observed if event.kind=='metadata']
    assert len(metadata) == 1
    assert metadata[0].usage == {'prompt_tokens':23,'completion_tokens':7,'total_tokens':30}
    assert checkpoints[-1].usage == metadata[0].usage
    assert len(requests) == 1


@pytest.mark.parametrize('output,schema_name,content,expected_type', [
    (DISCOVERY_INITIAL_OUTPUT,'discovery_action','{"next_action":"stop"}',StopDiscoveryAction),
    (DISCOVERY_REASONS_OUTPUT,'discovery_reasons',
        '{"papers":[{"arxiv_id":"2005.11401","reason":"A shared attention topic."}]}',DiscoveryReasons),
])
def test_gemini_request_uses_caller_schema_and_contains_no_reader_branch(output,schema_name,content,expected_type):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200,headers={'Content-Type':'text/event-stream'},content=_wire(content))
    settings = replace(Settings.from_env(),generation_provider='gemini',
        generation_endpoint='https://generativelanguage.googleapis.com/v1beta/openai',
        generation_model='gemini-3.8-flash',generation_api_key='isolated-test-only')
    async def run():
        return [event async for event in GenerationClient(settings,transport=httpx2.MockTransport(respond)).stream(
            [{'role':'user','content':'Public metadata only.'}],output=output,schema_name=schema_name)]
    events = asyncio.run(run())
    assert isinstance(events[-1].output,expected_type)
    assert len(requests) == 1
    payload = requests[0]
    schema_contract = payload['response_format']['json_schema']
    assert schema_contract['name'] == schema_name
    assert schema_contract['strict'] is True
    assert payload['reasoning_effort'] == 'low'
    assert payload['stream_options']['include_usage'] is True
    schema = schema_contract['schema']
    if output is DISCOVERY_INITIAL_OUTPUT:
        branches = [schema['$defs'][branch['$ref'].rsplit('/',1)[-1]] for branch in schema['anyOf']]
        assert {branch['properties']['next_action']['const'] for branch in branches} == {'search_arxiv_metadata','stop'}
        assert all(branch['additionalProperties'] is False for branch in branches)
        assert all(set(branch['properties']) == {'next_action'} for branch in branches)
    else:
        assert schema['additionalProperties'] is False
        assert set(schema['properties']) == {'papers'}
        papers = schema['properties']['papers']
        assert papers['minItems'] == 1 and papers['maxItems'] == 3
        reason = schema['$defs'][papers['items']['$ref'].rsplit('/',1)[-1]]
        assert reason['additionalProperties'] is False
        assert set(reason['properties']) == {'arxiv_id','reason'}
        assert reason['properties']['reason']['maxLength'] == 1000


def test_gemini_unsupported_discovery_output_is_still_rejected_without_retry():
    requests,observed = [],[]
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200,headers={'Content-Type':'text/event-stream'},
            content=_wire('{"next_action":"import_paper"}'))
    settings = replace(Settings.from_env(),generation_provider='gemini',
        generation_endpoint='https://generativelanguage.googleapis.com/v1beta/openai',
        generation_model='gemini-3.8-flash',generation_api_key='isolated-test-only')
    async def run():
        async for event in GenerationClient(settings,transport=httpx2.MockTransport(respond)).stream(
            [{'role':'user','content':'Public metadata only.'}],
            output=DISCOVERY_INITIAL_OUTPUT,schema_name='discovery_action'):
            observed.append(event)
    with pytest.raises(InvalidModelOutput):
        asyncio.run(run())
    assert len(requests) == 1
    assert not any(event.kind=='completed' for event in observed)
    assert next(event for event in observed if event.kind=='metadata').usage == {
        'prompt_tokens':23,'completion_tokens':7,'total_tokens':30}
