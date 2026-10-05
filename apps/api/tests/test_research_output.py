import json
import pytest
from researcy.generation.models import decode_output,InvalidModelOutput


def idea():
    return {'observed_gap':'The source reports a bounded experiment.','proposed_direction':'Hypothesis: compare baselines.',
        'possible_method':'Hypothesis: measure matched trials.','premise_citations':[{'source_ref':'P0:S1','evidence_quote':'Exact source.'}]}


@pytest.mark.parametrize('raw',[
    b'{"next_action":"search_arxiv_metadata","ideas":[],"refusal":null}',
    b'{"next_action":"directions","ideas":[],"refusal":null}',
    b'{"next_action":"directions","ideas":[],"refusal":"No evidence","owner_id":"x"}',
    b'{"next_action":"directions","next_action":"directions","ideas":[],"refusal":"No evidence"}',
    b'{"next_action":"directions","ideas":[],"refusal":NaN}',
    b'{"next_action":"directions","ideas":[],"refusal":"No evidence"} trailing',
    b'{"next_action":"directions","ideas":[],"refusal":"\\ud800"}',
    b'{"next_action":"directions","ideas":[],"refusal":"unsafe\\u0001"}',
])
def test_unsupported_coercible_unsafe_or_contradictory_output_rejected(raw):
    from researcy.research.models import RESEARCH_OUTPUT
    with pytest.raises(InvalidModelOutput):decode_output(raw,RESEARCH_OUTPUT)


@pytest.mark.parametrize('mutation',['four','blank','number','unsafe','scope','geometry','no_citations','seven_citations','refusal','long'])
def test_idea_bounds_and_citation_shape_are_enforced(mutation):
    from researcy.research.models import RESEARCH_OUTPUT
    entry=idea();output={'next_action':'directions','ideas':[entry],'refusal':None}
    if mutation=='four':output['ideas']=[entry]*4
    elif mutation=='blank':entry['observed_gap']='  '
    elif mutation=='number':entry['observed_gap']=123
    elif mutation=='unsafe':entry['premise_citations'][0]['evidence_quote']='unsafe\x7f'
    elif mutation=='scope':entry['premise_citations'][0]['paper_id']='forged'
    elif mutation=='geometry':entry['premise_citations'][0]['boxes']=[[0,0,1,1]]
    elif mutation=='no_citations':entry['premise_citations']=[]
    elif mutation=='seven_citations':entry['premise_citations']*=7
    elif mutation=='refusal':output['refusal']='No evidence'
    elif mutation=='long':entry['possible_method']='x'*1201
    with pytest.raises(InvalidModelOutput):decode_output(json.dumps(output).encode(),RESEARCH_OUTPUT)


def test_supported_ideas_or_exclusive_refusal_have_exact_envelope():
    from researcy.research.models import RESEARCH_OUTPUT
    accepted=decode_output(json.dumps({'next_action':'directions','ideas':[idea()],'refusal':None}).encode(),RESEARCH_OUTPUT)
    assert accepted.ideas[0].observed_gap=='The source reports a bounded experiment.'
    refusal=decode_output(b'{"next_action":"directions","ideas":[],"refusal":"No evidence"}',RESEARCH_OUTPUT)
    assert refusal.ideas==[] and refusal.refusal=='No evidence'
