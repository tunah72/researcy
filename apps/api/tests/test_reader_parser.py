import pytest

from researcy.agents.reader_parser import ClaimParser
from researcy.generation.models import InvalidModelOutput


def test_action_late_holds_claims():
    """Claims arriving before next_action='answer' are held until discriminator is observed."""
    parser = ClaimParser()
    assert parser.action is None

    # First chunk has a complete claim, but next_action is not yet known
    chunk1 = b'{"claims":[{"text":"Valid claim 1.","citations":[{"source_ref":"S1","evidence_quote":"Quote 1."}]}],'
    emitted1 = parser.feed(chunk1)
    assert emitted1 == ()
    assert parser.action is None

    # Second chunk provides the next_action='answer' discriminator
    chunk2 = b'"next_action":"answer","refusal":null}'
    emitted2 = parser.feed(chunk2)
    assert len(emitted2) == 1
    assert emitted2[0].text == "Valid claim 1."
    assert parser.action == "answer"

    parser.finish()


def test_claim_arrives_before_eof():
    """When action is known early, claims arriving across streaming chunks are emitted before EOF."""
    parser = ClaimParser()

    # Early discriminator
    assert parser.feed(b'{"next_action":"answer","refusal":null,"claims":[') == ()
    assert parser.action == "answer"

    # Claim 1 completes in chunk 2
    chunk2 = b'{"text":"First claim.","citations":[{"source_ref":"S1","evidence_quote":"Quote 1."}]},'
    emitted2 = parser.feed(chunk2)
    assert len(emitted2) == 1
    assert emitted2[0].text == "First claim."

    # Claim 2 split across chunks 3 and 4
    chunk3 = b'{"text":"Second claim.","citations":[{"source_ref":"S2",'
    assert parser.feed(chunk3) == ()

    chunk4 = b'"evidence_quote":"Quote 2."}]}]}'
    emitted4 = parser.feed(chunk4)
    assert len(emitted4) == 1
    assert emitted4[0].text == "Second claim."

    parser.finish()


def test_nested_citation_complete_and_schema_validation():
    """Nested citations must be complete, correctly shaped, and whitespace-only quotes rejected."""
    parser = ClaimParser()
    parser.feed(b'{"next_action":"answer","refusal":null,"claims":[')

    # Claim with 2 citations
    valid_claim = (
        b'{"text":"Dual cited claim.",'
        b'"citations":['
        b'{"source_ref":"S1","evidence_quote":"Quote 1."},'
        b'{"source_ref":"S2","evidence_quote":"Quote 2."}'
        b']}'
    )
    emitted = parser.feed(valid_claim)
    assert len(emitted) == 1
    assert len(emitted[0].citations) == 2
    assert emitted[0].citations[0].source_ref == "S1"
    assert emitted[0].citations[1].evidence_quote == "Quote 2."

    # Whitespace-only quote in next claim must fail
    bad_quote = (
        b',{"text":"Bad quote claim.",'
        b'"citations":[{"source_ref":"S3","evidence_quote":"   "}]}]}'
    )
    with pytest.raises(InvalidModelOutput):
        parser.feed(bad_quote)


def test_no_search_delta_and_search_forbids_claims():
    """Search action must never emit claim deltas and rejects any claim payload."""
    parser = ClaimParser()
    emitted = parser.feed(b'{"next_action":"search_same_paper","query":"attention mechanism"}')
    assert emitted == ()
    assert parser.action == "search_same_paper"
    parser.finish()

    # Search action containing claims must fail immediately
    search_with_claims = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        search_with_claims.feed(b'{"next_action":"search_same_paper","query":"test","claims":[]}')

    # Claims arriving before search discriminator must also fail when search discriminator arrives
    claims_then_search = ClaimParser()
    claims_then_search.feed(
        b'{"claims":[{"text":"Claim.","citations":[{"source_ref":"S1","evidence_quote":"Q."}]}], '
    )
    with pytest.raises(InvalidModelOutput):
        claims_then_search.feed(b'"next_action":"search_same_paper","query":"test"}')


def test_duplicate_quote_key_and_map_keys_rejected():
    """Duplicate keys at root, claim, and citation levels must be rejected immediately."""
    # Root duplicate next_action
    p_root = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p_root.feed(b'{"next_action":"answer","next_action":"answer"}')

    # Claim duplicate text key
    p_claim = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p_claim.feed(
            b'{"next_action":"answer","claims":[{"text":"A","text":"B",'
            b'"citations":[{"source_ref":"S1","evidence_quote":"Q."}]}]}'
        )

    # Citation duplicate evidence_quote key
    p_cit = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p_cit.feed(
            b'{"next_action":"answer","claims":[{"text":"A",'
            b'"citations":[{"source_ref":"S1","evidence_quote":"Q1.","evidence_quote":"Q2."}]}]}'
        )


def test_malformed_late_envelope_raises_after_emitted_claim():
    """A parser that already emitted valid claims raises InvalidModelOutput on subsequent envelope corruption."""
    parser = ClaimParser()
    emitted = parser.feed(
        b'{"next_action":"answer","claims":[{"text":"Claim 1.","citations":[{"source_ref":"S1","evidence_quote":"Q1."}]}], '
    )
    assert len(emitted) == 1
    assert parser.action == "answer"

    # Subsequent syntax error / invalid envelope
    with pytest.raises(InvalidModelOutput):
        parser.feed(b'"refusal": 12345}')


def test_truncated_json_rejected_at_finish():
    """Incomplete JSON streams must be rejected by finish()."""
    parser = ClaimParser()
    parser.feed(b'{"next_action":"answer","claims":[{"text":"Unclosed claim"')
    with pytest.raises(InvalidModelOutput):
        parser.finish()


def test_trailing_data_rejected_during_feed_and_finish():
    """Trailing non-whitespace characters after root JSON object must be rejected."""
    # Trailing garbage in single feed
    p1 = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p1.feed(b'{"next_action":"search_same_paper","query":"attention"} trailing garbage')

    # Trailing garbage in subsequent feed
    p2 = ClaimParser()
    p2.feed(b'{"next_action":"search_same_paper","query":"attention"}')
    with pytest.raises(InvalidModelOutput):
        p2.feed(b' extra')


def test_utf8_split_fragments_parsed_correctly():
    """UTF-8 multi-byte characters split across chunk boundaries must decode and parse without error."""
    parser = ClaimParser()
    # 'Schrödinger' where 'ö' is \xc3\xb6, split between \xc3 and \xb6
    chunk1 = b'{"claims":[{"text":"Schr\xc3'
    chunk2 = b'\xb6dinger equation.","citations":[{"source_ref":"S1","evidence_quote":"Exact citation."}]}], "next_action":"answer","refusal":null}'

    assert parser.feed(chunk1) == ()
    emitted = parser.feed(chunk2)
    assert len(emitted) == 1
    assert emitted[0].text == "Schrödinger equation."
    parser.finish()


def test_bounds_and_limit_enforcements():
    """Parser enforces limits: 256KiB payload, 12 claims, 24 total citations, and envelope invariants."""
    # 1. 256KiB limit
    p_bytes = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p_bytes.feed(b" " * (256 * 1024 + 1))

    # 2. Maximum 12 claims limit
    p_claims = ClaimParser()
    p_claims.feed(b'{"next_action":"answer","refusal":null,"claims":[')
    for i in range(12):
        p_claims.feed(
            f'{{"text":"Claim {i}.","citations":[{{"source_ref":"S1","evidence_quote":"Q."}}]}},'.encode()
        )
    with pytest.raises(InvalidModelOutput):
        p_claims.feed(b'{"text":"Claim 13.","citations":[{"source_ref":"S1","evidence_quote":"Q."}]}]}')

    # 3. Maximum 24 total citations limit
    p_cits = ClaimParser()
    p_cits.feed(b'{"next_action":"answer","refusal":null,"claims":[')
    # 6 claims with 4 citations = 24
    for i in range(6):
        cits = ",".join(f'{{"source_ref":"S{j}","evidence_quote":"Q{j}."}}' for j in range(4))
        p_cits.feed(f'{{"text":"Claim {i}.","citations":[{cits}]}},'.encode())
    # 7th claim with 1 citation exceeds 24
    with pytest.raises(InvalidModelOutput):
        p_cits.feed(b'{"text":"Claim 7.","citations":[{"source_ref":"S1","evidence_quote":"Q."}]}]}')

    # 4. Refusal cannot contain claims
    p_refusal = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p_refusal.feed(
            b'{"next_action":"answer","claims":[{"text":"C.","citations":[{"source_ref":"S","evidence_quote":"Q."}]}],"refusal":"Refusal."}'
        )

    # 5. Answer without refusal must have at least 1 claim
    p_zero = ClaimParser()
    p_zero.feed(b'{"next_action":"answer","claims":[],"refusal":null}')
    with pytest.raises(InvalidModelOutput):
        p_zero.finish()

    # 6. Missing required envelope keys at finish
    p_miss_act = ClaimParser()
    p_miss_act.feed(b'{"claims":[{"text":"C.","citations":[{"source_ref":"S","evidence_quote":"Q."}]}],"refusal":null}')
    with pytest.raises(InvalidModelOutput):
        p_miss_act.finish()

    p_miss_ref = ClaimParser()
    p_miss_ref.feed(b'{"next_action":"answer","claims":[{"text":"C.","citations":[{"source_ref":"S","evidence_quote":"Q."}]}]}')
    with pytest.raises(InvalidModelOutput):
        p_miss_ref.finish()

    p_miss_cla = ClaimParser()
    p_miss_cla.feed(b'{"next_action":"answer","refusal":null}')
    with pytest.raises(InvalidModelOutput):
        p_miss_cla.finish()

    p_miss_qry = ClaimParser()
    p_miss_qry.feed(b'{"next_action":"search_same_paper"}')
    with pytest.raises(InvalidModelOutput):
        p_miss_qry.finish()

    # 7. Lifecycle invariants: non-bytes feed, feed after finish, double finish
    p_life = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        p_life.feed("non-bytes string")
    p_life.close()

    p_life2 = ClaimParser()
    p_life2.feed(b'{"next_action":"search_same_paper","query":"attention"}')
    p_life2.finish()
    with pytest.raises(InvalidModelOutput):
        p_life2.finish()
    with pytest.raises(InvalidModelOutput):
        p_life2.feed(b" ")


@pytest.mark.parametrize('partial',[
    b'{"next_action":"answer","claims":[{"text":{"nested":',
    b'{"next_action":"answer","claims":[{"text":"Claim.","citations":[{"source_ref":["nested",',
    b'{"next_action":"answer","claims":[{"text":"Claim.","citations":[{"source_ref":"S1","evidence_quote":{"nested":',
])
def test_invalid_nested_shapes_are_rejected_without_waiting_for_object_completion(partial):
    parser = ClaimParser()
    with pytest.raises(InvalidModelOutput):
        parser.feed(partial)


def test_refusal_field_order_does_not_turn_empty_claims_into_a_contradiction():
    parser = ClaimParser()
    assert parser.feed(b'{"next_action":"answer","refusal":"Insufficient evidence.","claims":[]}')==()
    parser.finish()
    assert parser.action=='answer'


@pytest.mark.parametrize('bad_val', [r'\u0000', r'\ud800'])
@pytest.mark.parametrize('template', [
    '{{"next_action":"answer","refusal":null,"claims":[{{"text":"Claim {val}","citations":[{{"source_ref":"S1","evidence_quote":"Quote 1."}}]}}]}}',
    '{{"next_action":"answer","refusal":null,"claims":[{{"text":"Valid claim","citations":[{{"source_ref":"S1","evidence_quote":"Quote {val}"}}]}}]}}',
    '{{"next_action":"answer","refusal":null,"claims":[{{"text":"Valid claim","citations":[{{"source_ref":"S1{val}","evidence_quote":"Quote 1."}}]}}]}}',
])
def test_claim_parser_rejects_nul_and_surrogate_before_emitting_delta(template, bad_val):
    parser = ClaimParser()
    chunk = template.format(val=bad_val).encode()
    with pytest.raises(InvalidModelOutput):
        parser.feed(chunk)
