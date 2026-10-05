import json
import pytest
from researcy.generation.models import decode_output,InvalidModelOutput
from test_research_output import idea


@pytest.mark.parametrize('order',['first','last'])
def test_split_utf8_whole_units_wait_for_action_and_refusal(order):
    from researcy.agents.research_parser import IdeaParser
    from researcy.research.models import RESEARCH_OUTPUT
    entry=idea();entry['observed_gap']='A café reports experimental evidence.'
    output={'next_action':'directions','refusal':None,'ideas':[entry]} if order=='first' else {'ideas':[entry],'next_action':'directions','refusal':None}
    raw=json.dumps(output,ensure_ascii=False).encode();parser=IdeaParser();units=[]
    for byte in raw:units.extend(parser.feed(bytes([byte])))
    assert len(units)==1 and units[0].observed_gap=='A café reports experimental evidence.'
    parser.finish(decode_output(raw,RESEARCH_OUTPUT))
    with pytest.raises(InvalidModelOutput):parser.feed(b' ')


def test_nested_complete_citation_does_not_emit_until_entire_idea_closes():
    from researcy.agents.research_parser import IdeaParser
    parser=IdeaParser()
    prefix=b'{"next_action":"directions","refusal":null,"ideas":[{"premise_citations":[{"source_ref":"P0:S1","evidence_quote":"Exact source."}],'
    assert parser.feed(prefix)==()
    assert parser.feed(b'"observed_gap":"Evidence","proposed_direction":"Hypothesis","possible_method":"Method"}')
    parser.close()


def test_later_contradiction_and_final_unit_mismatch_reject_all_drafts():
    from researcy.agents.research_parser import IdeaParser
    from researcy.research.models import RESEARCH_OUTPUT
    raw=json.dumps({'next_action':'directions','refusal':None,'ideas':[idea()]}).encode()
    parser=IdeaParser();assert len(parser.feed(raw))==1
    altered=idea();altered['possible_method']='Different hypothesis'
    with pytest.raises(InvalidModelOutput):parser.finish(decode_output(json.dumps({'next_action':'directions','refusal':None,'ideas':[altered]}).encode(),RESEARCH_OUTPUT))
    parser=IdeaParser()
    with pytest.raises(InvalidModelOutput):parser.feed(raw[:-1]+b',"refusal":"No evidence"}')


@pytest.mark.parametrize('raw',[b'{"next_action":"import","ideas":[],"refusal":null}',
    b'{"next_action":"directions","refusal":null,"ideas":[{"page":1}]}',b'x'*262145])
def test_rejection_closes_parser_and_does_not_repair_unsupported_protocol(raw):
    from researcy.agents.research_parser import IdeaParser
    parser=IdeaParser()
    with pytest.raises(InvalidModelOutput):parser.feed(raw)
    with pytest.raises(InvalidModelOutput):parser.feed(b'{}')


def test_truncated_or_abandoned_parser_never_finishes_as_supported():
    from researcy.agents.research_parser import IdeaParser
    from researcy.research.models import RESEARCH_OUTPUT
    output=decode_output(b'{"next_action":"directions","ideas":[],"refusal":"No evidence"}',RESEARCH_OUTPUT)
    parser=IdeaParser();parser.feed(b'{"next_action":"directions"')
    with pytest.raises(InvalidModelOutput):parser.finish(output)
    parser=IdeaParser();parser.close()
    with pytest.raises(InvalidModelOutput):parser.finish(output)
