import copy
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from researcy.evaluation import m5 as evaluator


@pytest.fixture
def frozen_campaign():
    sources = [
        {'id': 'A', 'kind': 'scientific', 'edition': 'v1', 'sha256': 'a' * 64, 'page_count': 2},
        {'id': 'B', 'kind': 'scientific', 'edition': 'v2', 'sha256': 'b' * 64, 'page_count': 1},
        {'id': 'C', 'kind': 'scientific', 'edition': 'v1', 'sha256': 'c' * 64, 'page_count': 1},
        {'id': 'D', 'kind': 'scientific', 'edition': 'v1', 'sha256': 'd' * 64, 'page_count': 1},
    ]
    bindings = {
        source['id']: {
            'paper_id': f'00000000-0000-0000-0000-{number:012d}',
            'document_version': f'00000000-0000-0000-0001-{number:012d}',
            'profile_hash': 'e' * 64,
        }
        for number, source in enumerate(sources, 1)
    }
    cases = []
    for number in range(1, 9):
        cases.append({
            'id': f'R{number}', 'role': 'research', 'allocation': 'research',
            'active_source': 'A', 'selected_sources': ['B'],
            'expectation': 'insufficient' if number == 5 else 'hypothesis' if number == 6 else 'supported',
            'requires_cross_source': number in (1, 8), 'hostile': number == 7,
        })
    manifest = {
        'schema_version': 1, 'campaign_id': 'test-frozen',
        'frozen_at': '2026-10-04T00:00:00Z', 'sources': sources, 'cases': cases,
        'attempt_budget': 36,
        'allocations': {'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4},
        'required_layers': ['research'],
    }
    regions = [
        {'id': 'A1', 'source_id': 'A', 'page_index': 0, 'raw_start': 0, 'raw_end': 1,
         'raw_quote_sha256': hashlib.sha256(b'x').hexdigest(), 'boxes': [[10.0, 20.0, 11.0, 21.0]],
         'section': 'Methods', 'used_as_gold': True},
        {'id': 'B1', 'source_id': 'B', 'page_index': 0, 'raw_start': 0, 'raw_end': 1,
         'raw_quote_sha256': hashlib.sha256(b'y').hexdigest(), 'boxes': [[12.0, 22.0, 13.0, 23.0]],
         'section': 'Results', 'used_as_gold': True},
    ]
    gold = {'schema_version': 1, 'regions': regions, 'reading_order': [], 'retrieval_sets': []}
    observations = []
    for case in cases:
        citations = [
            {'id': 'cA', 'source_id': 'A', **bindings['A'], 'page': 1, 'evidence_quote': 'x',
             'raw_start': 0, 'raw_end': 1, 'region_id': 'A1', 'unique_raw_mapping': True,
             'boxes': [[10.0, 20.0, 11.0, 21.0]]},
            {'id': 'cB', 'source_id': 'B', **bindings['B'], 'page': 1, 'evidence_quote': 'y',
             'raw_start': 0, 'raw_end': 1, 'region_id': 'B1', 'unique_raw_mapping': True,
             'boxes': [[12.0, 22.0, 13.0, 23.0]]},
        ]
        observations.append({
            'case_id': case['id'], 'evidence_class': 'fresh_application',
            'state': 'refused' if case['expectation'] == 'insufficient' else 'completed',
            'sources': [{**source, **bindings[source['id']]} for source in sources[:2]],
            'citations': [] if case['expectation'] == 'insufficient' else citations,
            'ideas': [] if case['expectation'] == 'insufficient' else [{
                'assertions': [{'support_score': 2, 'reviewer': 'independent-human',
                                'citation_ids': ['cA', 'cB']}],
                'citation_ids': ['cA', 'cB'], 'hypothesis_labelled': True,
                'motivation_score': 2, 'reviewer': 'independent-human',
                'claims_proven_novelty': False, 'claims_proven_feasibility': False,
            }],
            'unauthorized_actions': 0, 'scope_errors': 0,
        })
    return manifest, observations, gold, bindings


def score(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    return evaluator.score_campaign(manifest, observations, annotations=gold, bindings=bindings)


def test_missing_research_case_prevents_campaign_acceptance(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    observations = [item for item in observations if item['case_id'] != 'R4']
    result = evaluator.score_campaign(manifest, observations, annotations=gold, bindings=bindings)
    assert result['research']['expected_cases'] == 8
    assert result['research']['missing_case_ids'] == ['R4']
    assert result['research']['supported_cases']['denominator'] == 5
    assert result['research']['supported_cases']['numerator'] == 4
    assert result['accepted'] is False


@pytest.mark.parametrize('field,value', [('sha256', 'f' * 64), ('edition', 'v9'),
                                         ('document_version', '00000000-0000-0000-0002-000000000001')])
def test_changed_source_identity_refuses_scoring(frozen_campaign, field, value):
    frozen_campaign[1][0]['sources'][0][field] = value
    with pytest.raises(evaluator.EvaluationError, match='SOURCE_IDENTITY_MISMATCH'):
        score(frozen_campaign)


def test_right_page_wrong_character_box_is_not_exact(frozen_campaign):
    frozen_campaign[1][0]['citations'][0]['boxes'] = [[10.0, 20.0, 12.0, 21.0]]
    result = score(frozen_campaign)
    assert result['citation']['exact']['numerator'] == 13
    assert result['citation']['exact']['denominator'] == 14
    assert result['research']['supported_cases']['numerator'] == 4
    assert result['accepted'] is False


def test_known_but_unselected_source_is_scope_leakage(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    citation = observations[0]['citations'][0]
    citation.update(source_id='C', **bindings['C'])
    result = score(frozen_campaign)
    assert result['citation']['allowed']['numerator'] == 13
    assert result['citation']['scope_errors'] == 1
    assert result['accepted'] is False


def test_hypothesis_label_does_not_excuse_unsupported_factual_assertion(frozen_campaign):
    frozen_campaign[1][5]['ideas'][0]['assertions'][0]['support_score'] = 0
    result = score(frozen_campaign)
    assert result['research']['assertion_support']['numerator'] == 6
    assert result['research']['assertion_support']['denominator'] == 7
    assert result['research']['case_results']['R6']['passed'] is False
    assert result['accepted'] is False


def test_unreviewed_support_cannot_pass(frozen_campaign):
    del frozen_campaign[1][0]['ideas'][0]['assertions'][0]['reviewer']
    assert score(frozen_campaign)['research']['case_results']['R1']['passed'] is False


def test_partial_usage_never_becomes_complete_zero(frozen_campaign):
    frozen_campaign[1][0]['accounting'] = {
        'generation_attempts': 2, 'physical_generation_requests': None,
        'passes': [
            {'kind': 'initial', 'usage': {'prompt_tokens': 9}, 'physical_requests': 1},
            {'kind': 'repair', 'usage': None, 'physical_requests': None},
        ],
    }
    result = score(frozen_campaign)
    assert result['cost']['usage']['known_passes'] == 0
    assert result['cost']['usage']['partial_passes'] == 1
    assert result['cost']['usage']['unknown_passes'] == 1
    assert result['cost']['usage']['totals']['prompt_tokens'] is None
    assert result['cost']['usage']['known_subtotals']['prompt_tokens'] == 9
    assert result['cost']['estimated_cost'] is None
    assert result['cost']['physical_responses']['known'] == 1
    assert result['cost']['physical_responses']['unknown_attempts'] == 1


def test_rank_metrics_include_missing_frozen_sets(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    gold['retrieval_sets'] = [
        {'id': 'Q1', 'case_id': 'R1', 'source_id': 'A', 'region_ids': ['A1'], 'subset': 'q0'},
        {'id': 'Q2', 'case_id': 'R2', 'source_id': 'B', 'region_ids': ['B1'], 'subset': 'q0'},
        {'id': 'P1', 'case_id': 'R1', 'source_id': 'A', 'region_ids': ['A1'], 'subset': 'paired'},
        {'id': 'P2', 'case_id': 'R1', 'source_id': 'B', 'region_ids': ['B1'], 'subset': 'paired'},
    ]
    observations[0]['retrieval'] = [
        {'set_id': 'Q1', 'source_id': 'A', 'dense': ['not-relevant', 'A1'],
         'lexical': ['A1'], 'fused': ['A1'], 'packed': ['A1']},
        {'set_id': 'P1', 'source_id': 'A', 'dense': ['A1'], 'lexical': [], 'fused': ['A1'], 'packed': []},
        {'set_id': 'P2', 'source_id': 'B', 'dense': [], 'lexical': [], 'fused': [], 'packed': []},
    ]
    result = score(frozen_campaign)
    assert result['retrieval']['q0']['dense']['recall_at_5'] == {'numerator': 1, 'denominator': 2, 'value': 0.5}
    assert result['retrieval']['q0']['dense']['mrr']['value'] == 0.25
    assert result['retrieval']['paired']['fused']['recall_at_5']['value'] == 0.5
    assert result['retrieval']['paired']['packed']['recall']['value'] == 0.0
    assert result['retrieval']['missing_set_ids'] == ['Q2']


def test_parser_mapping_and_order_denominators_are_frozen(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    gold['reading_order'] = [{'id': 'O1', 'source_id': 'A'}, {'id': 'O2', 'source_id': 'B'}]
    observations[0]['parser'] = {
        'regions': [{'region_id': 'A1', 'covered_codepoints': 1, 'raw_quote_sha256': hashlib.sha256(b'x').hexdigest(),
                     'page_index': 0, 'boxes': [[10.0, 20.0, 11.0, 21.0]], 'section': 'Methods'}],
        'reading_order': [{'id': 'O1', 'correct': True}],
    }
    result = score(frozen_campaign)
    assert result['parser']['resolvable_regions']['denominator'] == 2
    assert result['parser']['resolvable_regions']['numerator'] == 1
    assert result['parser']['reading_order']['denominator'] == 2
    assert result['parser']['reading_order']['numerator'] == 1
    assert result['parser']['text_coverage']['value'] == 0.5


def test_safe_results_never_copy_private_text(frozen_campaign):
    frozen_campaign[1][0]['prompt'] = 'PRIVATE-PROMPT-NEVER-COPY'
    frozen_campaign[1][0]['ideas'][0]['observed_gap'] = 'PRIVATE-GAP-NEVER-COPY'
    result = json.dumps(score(frozen_campaign))
    assert 'PRIVATE-' not in result
    assert 'evidence_quote' not in result
    assert 'paper_id' not in result


def test_artifact_hash_mismatch_fails_before_scoring(tmp_path):
    artifact = tmp_path / 'gold.json'
    artifact.write_text('{"regions": []}\n')
    manifest = {'artifacts': [{'path': 'gold.json', 'sha256': 'f' * 64}]}
    with pytest.raises(evaluator.EvaluationError, match='ARTIFACT_HASH_MISMATCH'):
        evaluator.verify_artifacts(manifest, tmp_path)


def test_serial_ledger_reserves_two_and_retains_uncertain_dispatch(tmp_path):
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
                                     allocations={'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4},
                                     campaign_id='test-campaign')
    reservation = ledger.reserve('R1', 'research')
    with pytest.raises(evaluator.EvaluationError, match='CAMPAIGN_RUN_ACTIVE'):
        ledger.reserve('R2', 'research')
    ledger.dispatched(reservation)
    ledger.finish(reservation, attempts=None, terminal_cleanup=False)
    assert ledger.summary()['charged_attempts'] == 2
    assert ledger.summary()['remaining_attempts'] == 34
    assert ledger.summary()['uncertain_runs'] == 1
    reloaded = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
                                      allocations=ledger.allocations, campaign_id='test-campaign')
    assert reloaded.summary()['charged_attempts'] == 2
    with pytest.raises(evaluator.EvaluationError, match='CASE_ALREADY_DISPATCHED'):
        reloaded.reserve('R1', 'research')


def test_unused_slot_release_and_allocation_guard(tmp_path):
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
                                     allocations={'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4},
                                     campaign_id='test-campaign')
    for number in range(8):
        reservation = ledger.reserve(f'R{number + 1}', 'research')
        ledger.dispatched(reservation)
        ledger.finish(reservation, attempts=2, terminal_cleanup=True)
    with pytest.raises(evaluator.EvaluationError, match='ALLOCATION_EXHAUSTED'):
        ledger.reserve('R9', 'research')
    reader = ledger.reserve('E1', 'reader')
    ledger.dispatched(reader)
    ledger.finish(reader, attempts=1, terminal_cleanup=True)
    assert ledger.summary()['charged_attempts'] == 17
    assert ledger.summary()['remaining_attempts'] == 19


def test_run_mode_rejects_main_origin_and_nonprivate_observations_before_dispatch(tmp_path):
    with pytest.raises(evaluator.EvaluationError, match='ISOLATED_ENDPOINT_REQUIRED'):
        evaluator.validate_run_target('http://localhost:3000', 'http://localhost:3000', 'main')
    with pytest.raises(evaluator.EvaluationError, match='PRIVATE_PATH_REQUIRED'):
        evaluator.require_private_path(Path('qualification/m5/observations.json'), Path.cwd())


def test_application_campaign_serial_dispatch_and_no_transport_retry(frozen_campaign, tmp_path):
    manifest, observations, gold, bindings = frozen_campaign
    selected = copy.deepcopy(manifest)
    selected['cases'] = selected['cases'][:2]
    dispatched = []

    def endpoint_run(case):
        dispatched.append(case['id'])
        if case['id'] == 'R1':
            raise TimeoutError('uncertain endpoint dispatch')
        return {'case_id': case['id'], 'state': 'completed',
                'accounting': {'generation_attempts': 1}, 'terminal_cleanup': True}

    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
                                     allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
    result = evaluator.run_campaign(selected, endpoint_run, ledger,
                                    observation_path=tmp_path / 'observations.json')
    assert dispatched == ['R1']
    assert result[0]['state'] == 'failed'
    assert ledger.summary()['charged_attempts'] == 2
    assert ledger.summary()['uncertain_runs'] == 1
    assert json.loads((tmp_path / 'observations.json').read_text())['observations'][0]['case_id'] == 'R1'


def test_controlled_http_failure_does_not_qualify_actual_provider_route(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['required_layers'] = ['route']
    observations[0]['route'] = {
        'provider': 'gemini', 'model': 'gemini-3.8-flash',
        'endpoint': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'application_graph': True, 'supported': True,
    }
    observations[0]['evidence_class'] = 'controlled_http'
    result = score(frozen_campaign)
    assert result['route']['actual_research_paths']['numerator'] == 0
    assert result['route']['actual_research_paths']['denominator'] == 4
    assert result['accepted'] is False


def test_discovery_implicit_import_and_unreviewed_reasons_cannot_pass(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['cases'].append({
        'id': 'D1', 'role': 'discovery', 'allocation': 'discovery',
        'active_source': 'A', 'selected_sources': [], 'expectation': 'search',
    })
    observations.append({
        'case_id': 'D1', 'evidence_class': 'fresh_application', 'state': 'completed',
        'discovery': {'inspected_unique': 8, 'returned_ids': ['2105.02358'],
                      'active_excluded': True, 'implicit_imports': 1,
                      'metadata_rationale_scores': [2], 'reviewer': 'independent-human'},
    })
    result = score(frozen_campaign)
    assert result['discovery']['cases']['numerator'] == 0
    assert result['discovery']['implicit_imports'] == 1


def test_reader_abstention_confusion_keeps_missing_case(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['cases'].extend([
        {'id': 'E1', 'role': 'reader', 'allocation': 'reader', 'active_source': 'A',
         'selected_sources': [], 'expectation': 'supported'},
        {'id': 'E2', 'role': 'reader', 'allocation': 'reader', 'active_source': 'A',
         'selected_sources': [], 'expectation': 'insufficient'},
    ])
    observations.append({'case_id': 'E1', 'evidence_class': 'fresh_application', 'state': 'refused'})
    result = score(frozen_campaign)
    assert result['reader']['abstention']['false_refusals'] == 1
    assert result['reader']['missing_case_ids'] == ['E2']
    assert result['reader']['cases']['denominator'] == 2


def test_authoritative_billable_mapping_estimate_is_separate_from_billed_cost(frozen_campaign):
    for observation in frozen_campaign[1][1:]:
        observation['accounting'] = {'generation_attempts': 0, 'passes': []}
    frozen_campaign[1][0]['accounting'] = {
        'generation_attempts': 1,
        'passes': [{
            'kind': 'initial', 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 150},
            'physical_requests': 1,
            'billable_tokens': {'uncached_input': 80, 'cached_input': 20, 'output_including_thinking': 50},
            'billable_mapping': {'authoritative': True, 'source': 'https://example.org/official-mapping',
                                 'date': '2026-10-04'},
        }],
    }
    result = score(frozen_campaign)
    assert result['cost']['estimated_cost'] == pytest.approx(0.000249)
    assert result['cost']['billed_cost'] is None
    assert result['cost']['currency'] == 'USD'


def test_layout_metric_output_cannot_copy_untrusted_text(frozen_campaign):
    frozen_campaign[1][0]['parser'] = {'layout_region_counts': {'caption': 2, 'secret': 'PRIVATE-LAYOUT'}}
    result = score(frozen_campaign)
    assert result['parser']['layout_region_counts'] == {'caption': 2}
    assert 'PRIVATE-LAYOUT' not in json.dumps(result)


def test_missing_run_accounting_prevents_aggregate_cost_estimate(frozen_campaign):
    frozen_campaign[1][0]['accounting'] = {
        'generation_attempts': 1,
        'passes': [{
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
            'physical_requests': 1,
            'billable_tokens': {'uncached_input': 100, 'cached_input': 0, 'output_including_thinking': 20},
            'billable_mapping': {'authoritative': True, 'source': 'https://example.org/official-mapping',
                                 'date': '2026-10-04'},
        }],
    }
    result = score(frozen_campaign)
    assert result['cost']['estimated_cost'] is None
    assert result['cost']['missing_accounting_cases'] == 7


def test_uncertain_cleanup_blocks_next_case_even_after_process_restart(tmp_path):
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
                                     allocations={'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4},
                                     campaign_id='test-campaign')
    reservation = ledger.reserve('R1', 'research')
    ledger.dispatched(reservation)
    ledger.finish(reservation, attempts=None, terminal_cleanup=False)
    with pytest.raises(evaluator.EvaluationError, match='CAMPAIGN_CLEANUP_UNPROVEN'):
        ledger.reserve('R2', 'research')


def test_decorative_citation_does_not_establish_cross_source_support(frozen_campaign):
    frozen_campaign[1][0]['ideas'][0]['assertions'][0]['citation_ids'] = ['cA']
    result = score(frozen_campaign)
    assert result['citation']['decorative_citations'] == 1
    assert result['research']['case_results']['R1']['passed'] is False


def test_historical_research_output_is_not_fresh_case_acceptance(frozen_campaign):
    frozen_campaign[1][0]['evidence_class'] = 'historical'
    assert score(frozen_campaign)['research']['case_results']['R1']['passed'] is False


def test_original_character_geometry_does_not_excuse_wrong_raw_offsets(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    gold['sources'] = {'A': {'page_count': 2, 'pages': [
        {'lines': [{'text': 'x', 'pdf_boxes': [[10.0, 20.0, 11.0, 21.0]]}]},
        {'lines': []},
    ]}}
    citation = observations[0]['citations'][0]
    del citation['region_id']
    citation['raw_fragments'] = [{'span_id': 's1', 'source_start': 1, 'source_end': 2, 'quote': 'x'}]
    assert score(frozen_campaign)['citation']['exact']['numerator'] == 13


def test_named_diagnostic_does_not_replace_original_failed_case(tmp_path):
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
                                     allocations={'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4},
                                     campaign_id='test-campaign')
    with pytest.raises(evaluator.EvaluationError, match='NAMED_FAILED_DIAGNOSTIC_REQUIRED'):
        ledger.reserve('X1-R1', 'diagnostic', diagnostic_of='R1')
    reservation = ledger.reserve('R1', 'research')
    ledger.dispatched(reservation)
    ledger.finish(reservation, attempts=1, terminal_cleanup=True, outcome='failed')
    diagnostic = ledger.reserve('X1-R1', 'diagnostic', diagnostic_of='R1')
    ledger.dispatched(diagnostic)
    ledger.finish(diagnostic, attempts=2, terminal_cleanup=True, outcome='completed')
    assert ledger.summary()['allocations_consumed']['research'] == 1
    assert ledger.summary()['allocations_consumed']['diagnostic'] == 2
    with pytest.raises(evaluator.EvaluationError, match='CASE_ALREADY_DISPATCHED'):
        ledger.reserve('R1', 'research')


def test_hypothesis_case_allows_real_research_safe_failure_refusal(frozen_campaign):
    observation = frozen_campaign[1][5]
    observation.update(state='failed', error_code='RESEARCH_INSUFFICIENT_EVIDENCE', ideas=[], citations=[])
    assert score(frozen_campaign)['research']['case_results']['R6']['passed'] is True


def test_negative_gold_requires_independent_preexecution_review(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['artifacts'] = [{'path': '.omp/runtime/m5-gold/annotations.json', 'sha256': 'f' * 64}]
    manifest['annotations_path'] = '.omp/runtime/m5-gold/annotations.json'
    with pytest.raises(evaluator.EvaluationError, match='INDEPENDENT_GOLD_REVIEW_REQUIRED'):
        evaluator.verify_gold_reviews(manifest, {}, [manifest['cases'][4]])
    reviews = {'gold_reviews': {
        'R5': {'reviewer': 'independent-controller', 'annotation_sha256': 'f' * 64,
               'verdict': 'insufficient', 'before_hosted_output': True},
        'R6': {'reviewer': 'independent-controller', 'annotation_sha256': 'f' * 64,
               'verdict': 'hypothesis', 'before_hosted_output': True},
    }}
    evaluator.verify_gold_reviews(manifest, reviews, manifest['cases'][4:6])
    reviews['gold_reviews']['R6']['before_hosted_output'] = False
    with pytest.raises(evaluator.EvaluationError, match='INDEPENDENT_GOLD_REVIEW_REQUIRED'):
        evaluator.verify_gold_reviews(manifest, reviews, manifest['cases'][4:6])


def test_optional_frozen_diagnostic_never_removes_primary_missing_case(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    diagnostic_case = copy.deepcopy(manifest['cases'][3])
    diagnostic_case.update(id='X1-R4', allocation='diagnostic', diagnostic_of='R4')
    manifest['diagnostic_cases'] = [diagnostic_case]
    observations = [item for item in observations if item['case_id'] != 'R4']
    diagnostic = copy.deepcopy(observations[0])
    diagnostic['case_id'] = 'X1-R4'
    observations.append(diagnostic)
    result = evaluator.score_campaign(manifest, observations, annotations=gold, bindings=bindings)
    assert result['research']['expected_cases'] == 8
    assert result['research']['missing_case_ids'] == ['R4']
    assert result['diagnostic']['observed_cases'] == 1
    assert 'X1-R4' not in result['missing_case_ids']
    assert result['accepted'] is False


def test_zero_discovery_candidates_cannot_pass_required_search_path(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['cases'].append({
        'id': 'D1', 'role': 'discovery', 'allocation': 'discovery',
        'active_source': 'A', 'selected_sources': [], 'expectation': 'search',
    })
    observations.append({
        'case_id': 'D1', 'evidence_class': 'fresh_application', 'state': 'completed',
        'discovery': {'action': 'stop', 'inspected_unique': 0, 'returned_ids': [],
                      'active_excluded': True, 'implicit_imports': 0,
                      'metadata_rationale_scores': [], 'reviewer': 'independent-human'},
    })
    assert score(frozen_campaign)['discovery']['cases']['numerator'] == 0


def test_page_only_fallback_count_is_not_every_geometry_failure(frozen_campaign):
    frozen_campaign[1][0]['citations'][0]['boxes'] = [[10.0, 20.0, 12.0, 21.0]]
    result = score(frozen_campaign)
    assert result['citation']['page_only_fallbacks'] == 0
    assert result['citation']['geometry_errors'] == 1


def test_failed_reader_run_is_not_a_true_answer(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['cases'].append({
        'id': 'E1', 'role': 'reader', 'allocation': 'reader', 'active_source': 'A',
        'selected_sources': [], 'expectation': 'supported',
    })
    observations.append({'case_id': 'E1', 'evidence_class': 'fresh_application', 'state': 'failed'})
    result = score(frozen_campaign)
    assert result['reader']['abstention']['true_answers'] == 0
    assert result['reader']['abstention']['failed_or_interrupted'] == 1


def test_missing_attempt_accounting_is_unknown_not_zero(frozen_campaign):
    result = score(frozen_campaign)
    assert result['cost']['generation_attempts'] is None
    assert result['cost']['known_attempts_subtotal'] == 0
    assert result['cost']['missing_accounting_cases'] == 8


def test_wrong_gold_crop_or_rotation_fails_parser_mapping(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    gold['regions'][0].update(media_box=[0, 0, 612, 792], crop_box=[20, 30, 590, 760], rotation=90)
    observations[0]['parser'] = {'regions': [{
        'region_id': 'A1', 'covered_codepoints': 1, 'raw_quote_sha256': hashlib.sha256(b'x').hexdigest(),
        'page_index': 0, 'boxes': [[10.0, 20.0, 11.0, 21.0]], 'section': 'Methods',
        'media_box': [0, 0, 612, 792], 'crop_box': [0, 0, 612, 792], 'rotation': 0,
    }]}
    assert score(frozen_campaign)['parser']['resolvable_regions']['numerator'] == 0


def test_missing_frozen_local_boundary_case_prevents_campaign_acceptance(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['cases'].append({'id': 'L-invalid-selection', 'role': 'route',
                              'local_only': True, 'expectation': 'rejected'})
    result = score(frozen_campaign)
    assert result['research']['accepted'] is True
    assert result['missing_case_ids'] == ['L-invalid-selection']
    assert result['accepted'] is False


def test_local_boundary_publication_is_not_safe_rejection(frozen_campaign):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['cases'].append({'id': 'L-invalid-selection', 'role': 'route',
                              'local_only': True, 'expectation': 'rejected'})
    observations.append({
        'case_id': 'L-invalid-selection', 'state': 'failed', 'evidence_class': 'controlled_http',
        'route': {'boundary_rejected': True}, 'accepted_publications': 1, 'unauthorized_actions': 0,
    })
    result = score(frozen_campaign)
    assert result['route']['local_boundary_rejections']['numerator'] == 0
    assert result['route']['local_boundary_rejections']['denominator'] == 1


def test_citation_version_mismatch_refuses_source_scoring(frozen_campaign):
    frozen_campaign[1][0]['citations'][0]['document_version'] = '00000000-0000-0000-0002-000000000001'
    with pytest.raises(evaluator.EvaluationError, match='SOURCE_IDENTITY_MISMATCH'):
        score(frozen_campaign)


def test_multi_response_pass_cannot_hide_extra_physical_requests(frozen_campaign):
    frozen_campaign[1][0]['accounting'] = {
        'generation_attempts': 1, 'passes': [{'usage': None, 'physical_requests': 2}],
    }
    with pytest.raises(evaluator.EvaluationError, match='INVALID_PHYSICAL_ACCOUNTING'):
        score(frozen_campaign)


def test_zero_call_refusal_does_not_qualify_actual_hosted_route(frozen_campaign):
    observation = frozen_campaign[1][4]
    observation['route'] = {
        'provider': 'gemini', 'model': 'gemini-3.8-flash',
        'endpoint': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'application_graph': True, 'insufficient': True,
    }
    observation['accounting'] = {'generation_attempts': 0, 'passes': []}
    result = score(frozen_campaign)
    assert result['route']['actual_research_paths']['numerator'] == 0


def test_wrong_actual_pass_identity_cannot_qualify_primary_route(frozen_campaign):
    observation = frozen_campaign[1][0]
    observation['route'] = {
        'provider': 'gemini', 'model': 'gemini-3.8-flash',
        'endpoint': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'application_graph': True, 'supported': True,
    }
    observation['accounting'] = {
        'generation_attempts': 1, 'passes': [{
            'kind': 'initial', 'provider': '9router', 'configured_model': 'ag/gemini-3.8-flash-low',
            'response_received': True, 'usage': None,
        }],
    }
    assert score(frozen_campaign)['route']['actual_research_paths']['numerator'] == 0


def test_dispatched_timeout_retains_uncertain_physical_attempt(frozen_campaign):
    for observation in frozen_campaign[1]:
        observation['accounting'] = {'generation_attempts': 0, 'passes': []}
    frozen_campaign[1][0]['accounting'] = {'generation_attempts': 1,
        'passes': [{'dispatched': True, 'response_received': False, 'usage': None}]}
    result = score(frozen_campaign)
    assert result['cost']['generation_attempts'] == 1
    assert result['cost']['physical_responses'] == {'known': 0, 'unknown_attempts': 1}
    assert result['cost']['usage']['totals']['total_tokens'] is None


@pytest.mark.parametrize('state', ['failed', 'running', 'completed'])
def test_primary_browser_journey_requires_successful_terminal_outcome(frozen_campaign, state):
    manifest, observations, gold, bindings = frozen_campaign
    manifest['required_layers'] = ['product']
    for number, role in enumerate(('research', 'reader', 'discovery'), 1):
        identity = f'B{number}'
        manifest['cases'].append({'id': identity, 'role': role, 'allocation': 'demo',
            'active_source': 'A', 'selected_sources': ['B'] if role == 'research' else [],
            'expectation': 'search' if role == 'discovery' else 'supported', 'product_journey': True})
        observations.append({'case_id': identity, 'state': state, 'evidence_class': 'manual_browser',
            'product': {'journey_complete': True, 'jump_attempts': 1, 'exact_jump_successes': 1,
                'cancel': True, 'reload': True, 'retry': True}})
    result = score(frozen_campaign)
    assert result['product']['journeys'] == {'numerator': 3 if state == 'completed' else 0,
        'denominator': 3, 'value': 1.0 if state == 'completed' else 0.0}
    assert result['accepted'] is (state == 'completed')


def test_endpoint_campaign_cannot_consume_browser_journey_reservation(frozen_campaign, tmp_path):
    manifest = frozen_campaign[0]
    manifest['cases'] = [{'id': 'B1', 'role': 'research', 'allocation': 'demo',
        'active_source': 'A', 'selected_sources': ['B'], 'expectation': 'supported', 'product_journey': True}]
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
        allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
    calls = []
    def endpoint(case):
        calls.append(case['id'])
        return {'case_id': case['id'], 'state': 'completed', 'terminal_cleanup': True,
            'accounting': {'generation_attempts': 1}}
    with pytest.raises(evaluator.EvaluationError, match='BROWSER_JOURNEY_REQUIRED'):
        evaluator.run_campaign(manifest, endpoint, ledger, observation_path=tmp_path / 'observations.json')
    assert calls == []
    assert ledger.summary()['charged_attempts'] == 0
    reservation = ledger.reserve('B1', 'demo')
    ledger.dispatched(reservation)
    ledger.finish(reservation, attempts=1, terminal_cleanup=True, outcome='completed')
    assert ledger.summary()['allocations_consumed']['demo'] == 1


def test_application_campaign_rejects_exact_origin_mismatch_before_dispatch(frozen_campaign, monkeypatch, tmp_path):
    from dataclasses import replace
    import httpx2
    from researcy import config
    manifest, observations, gold, bindings = frozen_campaign
    owner = '00000000-0000-4000-8000-000000000001'
    settings = replace(config.Settings.from_env(), generation_provider='gemini',
        generation_model=evaluator.PRIMARY_MODEL, generation_endpoint=evaluator.PRIMARY_ENDPOINT,
        generation_api_key='controlled-key', trusted_origins=('http://localhost:3305',))
    monkeypatch.setattr(config, 'get_settings', lambda: settings)
    monkeypatch.setenv('M5_SESSION', 'controlled-session')
    monkeypatch.setenv('M5_CSRF', 'controlled-csrf')
    monkeypatch.setattr(evaluator, '_check_application_bindings', lambda *args: bindings)
    client = httpx2.Client(transport=httpx2.MockTransport(
        lambda request: httpx2.Response(200, json={'id': owner})), base_url='http://127.0.0.1:3305')
    monkeypatch.setattr(httpx2, 'Client', lambda **kwargs: client)
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
        allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
    try:
        with pytest.raises(evaluator.EvaluationError, match='ISOLATED_ORIGIN_MISMATCH'):
            evaluator.ApplicationCampaign(manifest, gold, {'sources': bindings, 'owner_id': owner},
                base_url='http://127.0.0.1:3305', origin='http://127.0.0.1:3305', project='researcy-m5-acceptance')
        assert ledger.summary()['charged_attempts'] == 0
    finally:
        client.close()


@pytest.mark.parametrize('status,code,body_identity,run_header,extra,known', [
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, False, True),
    (429, 'RESEARCH_RATE_LIMITED', 'matching', False, False, True),
    (503, 'GENERATION_UNCONFIGURED', 'different', False, False, False),
    (503, 'GENERATION_UNCONFIGURED', 'missing', False, False, False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', True, False, False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, True, False),
    (429, 'GENERATION_UNCONFIGURED', 'matching', False, False, False),
    (503, 'GENERATION_UNAVAILABLE', 'matching', False, False, False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, 'duplicate', False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, 'array', False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, 'oversize', False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, 'malformed', False),
    (503, 'GENERATION_UNCONFIGURED', 'matching', False, 'plaintext', False),
])
def test_pre_reservation_rejection_preserves_budget_and_next_case(
        frozen_campaign, monkeypatch, tmp_path, status, code, body_identity, run_header, extra, known):
    from uuid import UUID
    import httpx2
    manifest, _, _, bindings = frozen_campaign
    selected = copy.deepcopy(manifest)
    selected['cases'] = selected['cases'][:2]
    dispatched = []
    request_id = '00000000-0000-4000-8000-000000000001'
    def rejected(request):
        dispatched.append(request.url.path)
        payload = {'code': code, 'message': 'The request could not proceed.', 'request_id': request_id}
        if body_identity == 'different':
            payload['request_id'] = '00000000-0000-4000-8000-000000000002'
        elif body_identity == 'missing':
            payload.pop('request_id')
        if extra is True:
            payload['run_id'] = request_id
        headers = {'x-request-id': request_id}
        if run_header:
            headers['x-research-run-id'] = request_id
        if extra == 'oversize':
            payload['message'] = 'x' * 4096
        if extra in ('duplicate', 'array', 'malformed', 'plaintext'):
            headers['content-type'] = 'text/plain' if extra == 'plaintext' else 'application/json'
            content = json.dumps(list(payload.items()) if extra == 'array' else payload)
            if extra == 'duplicate':
                content = '{"code":"GENERATION_UNCONFIGURED",' + content[1:]
            elif extra == 'malformed':
                content = content[:-1]
            return httpx2.Response(status, content=content, headers=headers)
        return httpx2.Response(status, json=payload, headers=headers)
    def missing_run(*args, **kwargs):
        raise evaluator.EvaluationError('APPLICATION_RUN_UNOBSERVED')
    monkeypatch.setattr(evaluator, '_export_application_run', missing_run)
    campaign = evaluator.ApplicationCampaign.__new__(evaluator.ApplicationCampaign)
    campaign.bindings = bindings
    campaign.owner = UUID(request_id)
    campaign.manifest = manifest
    campaign.client = httpx2.Client(transport=httpx2.MockTransport(rejected), base_url='http://127.0.0.1:3305')
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
        allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
    try:
        observed = evaluator.run_campaign(selected, campaign, ledger,
            observation_path=tmp_path / 'observations.json')
    finally:
        campaign.close()
    summary = ledger.summary()
    if known:
        assert len(dispatched) == len(observed) == 2
        assert summary['charged_attempts'] == summary['uncertain_runs'] == 0
        assert all(item['error_code'] == code and item['terminal_cleanup']
            and item['accounting']['generation_attempts'] == 0 for item in observed)
    else:
        assert len(dispatched) == len(observed) == 1
        assert summary['charged_attempts'] == 2 and summary['uncertain_runs'] == 1
        assert observed[0]['error_code'] == 'ENDPOINT_DISPATCH_UNCERTAIN'
        with pytest.raises(evaluator.EvaluationError, match='CAMPAIGN_CLEANUP_UNPROVEN'):
            ledger.reserve('R3', 'research')


@pytest.fixture
def cli_campaign(frozen_campaign, tmp_path, monkeypatch):
    root = tmp_path / 'repository'
    git = root / '.git'
    (git / 'objects').mkdir(parents=True)
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    (git / 'config').write_text('[core]\nrepositoryformatversion = 0\nbare = false\n')
    worktree = root / '.omp' / 'worktrees' / 'feature'
    worktree.mkdir(parents=True)
    metadata = git / 'worktrees' / 'feature'
    metadata.mkdir(parents=True)
    (metadata / 'HEAD').write_text('ref: refs/heads/feature\n')
    (metadata / 'commondir').write_text('../..\n')
    (metadata / 'gitdir').write_text(str(worktree / '.git') + '\n')
    (worktree / '.git').write_text('gitdir: ' + str(metadata) + '\n')

    manifest, observations, gold, bindings = copy.deepcopy(frozen_campaign)
    manifest['annotations_path'] = '.omp/runtime/test/annotations.json'
    gold_bytes = json.dumps(gold).encode()
    manifest['artifacts'] = [{'path': manifest['annotations_path'],
                              'sha256': hashlib.sha256(gold_bytes).hexdigest()}]
    canonical = root / '.omp/runtime/m5-campaigns/test-frozen/attempt-ledger.json'
    evaluator.AttemptLedger(canonical, budget=36, allocations=manifest['allocations'],
                            campaign_id=manifest['campaign_id'])
    clients, dispatched, uncertain = [], [], set()
    observed = {item['case_id']: item for item in observations}

    class ControlledApplication:
        def __init__(self, *args, **kwargs):
            clients.append(self)

        def __call__(self, case):
            dispatched.append(case['id'])
            if case['id'] in uncertain:
                raise TimeoutError('controlled uncertain dispatch')
            result = copy.deepcopy(observed[case['id']])
            result.update(terminal_cleanup=True,
                          accounting={'generation_attempts': 1, 'passes': []})
            return result

        def close(self):
            pass

    monkeypatch.setattr(evaluator, 'ApplicationCampaign', ControlledApplication)

    def invoke(checkout, ledger, case_id, name):
        private = checkout / '.omp/runtime/test'
        private.mkdir(parents=True, exist_ok=True)
        (private / 'annotations.json').write_bytes(gold_bytes)
        (private / 'bindings.json').write_text(json.dumps({'sources': bindings}))
        manifest_path = checkout / 'qualification/m5/manifest.json'
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest))
        return evaluator.main([
            '--run', '--root', str(checkout), '--manifest', 'qualification/m5/manifest.json',
            '--observations', f'.omp/runtime/test/{name}-observations.json',
            '--output', f'.omp/runtime/test/{name}-metrics.json',
            '--bindings', '.omp/runtime/test/bindings.json',
            '--attempt-budget', '36', '--ledger', str(ledger),
            '--base-url', 'http://127.0.0.1:3305', '--origin', 'http://localhost:3305',
            '--isolated-project', 'researcy-m5-test', '--case-id', case_id,
        ])

    return root, worktree, canonical, clients, dispatched, uncertain, invoke


@pytest.mark.parametrize('uncertain_dispatch', [False, True])
def test_cli_campaign_rejects_fresh_ledger_budget_reset(cli_campaign, uncertain_dispatch):
    root, _, canonical, clients, dispatched, uncertain, invoke = cli_campaign
    if uncertain_dispatch:
        uncertain.add('R1')
    assert invoke(root, canonical, 'R1', 'first') == 1
    original = canonical.read_bytes()
    alternate = root / '.omp/runtime/test/fresh-ledger.json'
    assert invoke(root, alternate, 'R1', 'reset') == 2
    assert dispatched == ['R1']
    assert len(clients) == 1
    assert not alternate.exists()
    assert canonical.read_bytes() == original


def test_cli_campaign_restart_across_checkouts_preserves_used_and_uncertain_budget(cli_campaign):
    root, worktree, canonical, _, dispatched, uncertain, invoke = cli_campaign
    assert invoke(root, canonical, 'R1', 'settled') == 1
    uncertain.add('R2')
    assert invoke(worktree, canonical, 'R2', 'uncertain') == 1
    reloaded = evaluator.AttemptLedger(canonical, budget=36,
        allocations=evaluator.ALLOCATIONS, campaign_id='test-frozen')
    summary = reloaded.summary()
    assert summary['charged_attempts'] == 3
    assert summary['remaining_attempts'] == 33
    assert summary['uncertain_runs'] == 1
    assert summary['allocations_consumed']['research'] == 3
    original = canonical.read_bytes()
    assert invoke(root, canonical, 'R3', 'blocked') == 2
    assert dispatched == ['R1', 'R2']
    assert canonical.read_bytes() == original


def test_cli_campaign_requires_explicit_adoption_before_client_creation(cli_campaign):
    root, worktree, canonical, clients, dispatched, _, invoke = cli_campaign
    legacy = worktree / '.omp/runtime/m5-gold/attempt-ledger.json'
    legacy.parent.mkdir(parents=True)
    original = canonical.read_bytes()
    legacy.write_bytes(original)
    canonical.unlink()
    assert invoke(root, canonical, 'R1', 'missing-adoption') == 2
    assert clients == dispatched == []
    assert not canonical.exists()
    assert legacy.read_bytes() == original


@pytest.mark.parametrize('nested_checkout', [False, True])
def test_cli_campaign_rejects_root_that_is_not_exact_git_checkout(cli_campaign, tmp_path, nested_checkout):
    root, _, _, clients, dispatched, _, invoke = cli_campaign
    invalid = root / 'nested' if nested_checkout else tmp_path / 'not-a-repository'
    ledger = invalid / '.omp/runtime/m5-campaigns/test-frozen/attempt-ledger.json'
    evaluator.AttemptLedger(ledger, budget=36, allocations=evaluator.ALLOCATIONS,
                            campaign_id='test-frozen')
    original = ledger.read_bytes()
    assert invoke(invalid, ledger, 'R1', 'invalid-root') == 2
    assert clients == dispatched == []
    assert ledger.read_bytes() == original


@pytest.mark.parametrize('failed_directory_sync', [2, 3])
def test_directory_sync_failure_prevents_endpoint_dispatch_and_retains_reservation(
        frozen_campaign, tmp_path, monkeypatch, failed_directory_sync):
    manifest = copy.deepcopy(frozen_campaign[0])
    manifest['cases'] = manifest['cases'][:1]
    ledger = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
        allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
    dispatched = []

    def endpoint(case):
        dispatched.append(case['id'])
        return {'case_id': case['id'], 'state': 'completed', 'terminal_cleanup': True,
                'accounting': {'generation_attempts': 1, 'passes': []}}

    fsync = os.fsync
    directory_syncs = 0

    def fail_directory_sync(descriptor):
        nonlocal directory_syncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_syncs += 1
            if directory_syncs == failed_directory_sync:
                raise OSError('controlled directory durability failure')
        fsync(descriptor)

    with monkeypatch.context() as fault:
        fault.setattr(os, 'fsync', fail_directory_sync)
        with pytest.raises(OSError, match='controlled directory durability failure'):
            evaluator.run_campaign(manifest, endpoint, ledger,
                observation_path=tmp_path / 'observations.json')
    assert dispatched == []
    reloaded = evaluator.AttemptLedger(tmp_path / 'ledger.json', budget=36,
        allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
    summary = reloaded.summary()
    assert summary['charged_attempts'] == 2
    assert summary['remaining_attempts'] == 34
    assert summary['reserved_runs'] == 1
    with pytest.raises(evaluator.EvaluationError, match='CAMPAIGN_RUN_ACTIVE'):
        evaluator.run_campaign(manifest, endpoint, reloaded,
            observation_path=tmp_path / 'restart-observations.json')
    assert dispatched == []


@pytest.mark.parametrize('diagnostic_attempts,accepted', [((2, 2, 2), False), ((2, 2, 0), True)])
def test_offline_cost_uses_frozen_diagnostic_allocation_not_research_role(
        frozen_campaign, diagnostic_attempts, accepted):
    manifest, observations, _, _ = frozen_campaign
    for observation in observations:
        observation['accounting'] = {'generation_attempts': 0, 'passes': []}
    manifest['diagnostic_cases'] = []
    for number, count in enumerate(diagnostic_attempts, 1):
        case = copy.deepcopy(manifest['cases'][number - 1])
        case.update(id=f'X1-R{number}', allocation='diagnostic', diagnostic_of=f'R{number}')
        manifest['diagnostic_cases'].append(case)
        observation = copy.deepcopy(observations[number - 1])
        observation.update(case_id=case['id'],
            accounting={'generation_attempts': count,
                        'passes': [{'usage': None, 'physical_requests': 1} for _ in range(count)]})
        observations.append(observation)
    cost = score(frozen_campaign)['cost']
    assert cost['accepted'] is accepted
    assert cost['generation_attempts'] == sum(diagnostic_attempts)
    assert cost['allocations']['diagnostic']['generation_attempts'] == sum(diagnostic_attempts)
    assert cost['allocations']['diagnostic']['limit'] == 4
    assert cost['allocations']['diagnostic']['accepted'] is accepted
    assert cost['allocations']['research']['generation_attempts'] == 0
    assert cost['physical_responses']['known'] == sum(diagnostic_attempts)
    assert cost['usage']['unknown_passes'] == sum(diagnostic_attempts)
    assert cost['estimated_cost'] is None
    assert cost['billed_cost'] is None
    assert cost['cost_source'] == 'unavailable'
    assert cost['unknown_is_free'] is False


@pytest.mark.parametrize('allocation,role,count', [
    ('research', 'research', 9), ('reader', 'reader', 4),
    ('discovery', 'discovery', 3), ('demo', 'research', 4),
])
def test_offline_cost_rejects_each_other_frozen_allocation_overrun(
        frozen_campaign, allocation, role, count):
    manifest, observations, _, _ = frozen_campaign
    for observation in observations:
        observation['accounting'] = {'generation_attempts': 0, 'passes': []}
    for number in range(count):
        identity = f'extra-{allocation}-{number}'
        manifest['cases'].append({'id': identity, 'role': role, 'allocation': allocation,
            'active_source': 'A', 'selected_sources': ['B'] if role == 'research' else [],
            'product_journey': allocation == 'demo'})
        observations.append({'case_id': identity, 'state': 'completed',
            'evidence_class': 'manual_browser' if allocation == 'demo' else 'fresh_application',
            'accounting': {'generation_attempts': 2, 'passes': []}})
    cost = score(frozen_campaign)['cost']
    assert cost['generation_attempts'] == count * 2 < 36
    assert cost['accepted'] is False
    assert cost['allocations'][allocation]['accepted'] is False


@pytest.mark.parametrize('accounting', [None, {}, {'passes': []}])
@pytest.mark.parametrize('evidence_class', ['fresh_application', 'manual_browser', 'owner_manual'])
def test_offline_cost_keeps_missing_attempt_counts_unknown_by_frozen_allocation(
        frozen_campaign, accounting, evidence_class):
    for observation in frozen_campaign[1]:
        observation['accounting'] = {'generation_attempts': 0, 'passes': []}
    frozen_campaign[1][0].update(evidence_class=evidence_class, accounting=accounting)
    frozen_campaign[1][1]['accounting'] = {'generation_attempts': 1, 'passes': []}
    cost = score(frozen_campaign)['cost']
    assert cost['accepted'] is False
    assert cost['generation_attempts'] is None
    assert cost['known_attempts_subtotal'] == 1
    assert cost['missing_accounting_cases'] == 1
    assert cost['allocations']['research']['generation_attempts'] is None
    assert cost['allocations']['research']['known_attempts_subtotal'] == 1
    assert cost['allocations']['research']['missing_accounting_cases'] == 1
    assert cost['estimated_cost'] is None


@pytest.mark.parametrize('case_update', [
    {'allocation': 'unapproved'}, {'allocation': None}, {'role': 'unapproved'},
    {'local_only': True},
])
def test_offline_cost_rejects_unsupported_frozen_case_accounting(frozen_campaign, case_update):
    for observation in frozen_campaign[1]:
        observation['accounting'] = {'generation_attempts': 1, 'passes': []}
    frozen_campaign[0]['cases'][0].update(case_update)
    with pytest.raises(evaluator.EvaluationError, match='INVALID_CASE_ACCOUNTING'):
        score(frozen_campaign)


def test_offline_cost_does_not_require_git_checkout_or_ledger(frozen_campaign, tmp_path):
    manifest, observations, gold, bindings = frozen_campaign
    for observation in observations:
        observation['accounting'] = {'generation_attempts': 1, 'passes': []}
    manifest['annotations_path'] = '.omp/runtime/annotations.json'
    private = tmp_path / '.omp/runtime'
    private.mkdir(parents=True)
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    (private / 'annotations.json').write_text(json.dumps(gold))
    (private / 'bindings.json').write_text(json.dumps({'sources': bindings}))
    (private / 'observations.json').write_text(json.dumps({
        'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'observations': observations,
    }))
    assert evaluator.main([
        '--root', str(tmp_path), '--manifest', 'manifest.json',
        '--observations', '.omp/runtime/observations.json',
        '--bindings', '.omp/runtime/bindings.json', '--output', 'metrics.json',
    ]) == 0
    cost = json.loads((tmp_path / 'metrics.json').read_text())['cost']
    assert cost['accepted'] is True
    assert cost['generation_attempts'] == 8
    assert cost['allocations']['research']['generation_attempts'] == 8
    assert not (tmp_path / '.git').exists()
    assert not (private / 'm5-campaigns').exists()


def test_offline_cost_accepts_full_bounded_allocations_and_zero_call_local_case(frozen_campaign):
    manifest, observations, _, _ = frozen_campaign
    for observation in observations:
        observation['accounting'] = {'generation_attempts': 2, 'passes': []}
    manifest['diagnostic_cases'] = []
    for allocation, role, count in [('reader', 'reader', 3), ('discovery', 'discovery', 2),
                                     ('demo', 'research', 3), ('diagnostic', 'research', 2)]:
        for number in range(count):
            identity = f'bounded-{allocation}-{number}'
            case = {'id': identity, 'role': role, 'allocation': allocation,
                'active_source': 'A', 'selected_sources': ['B'] if role == 'research' else [],
                'product_journey': allocation == 'demo'}
            if allocation == 'diagnostic':
                case['diagnostic_of'] = 'R1'
                manifest['diagnostic_cases'].append(case)
            else:
                manifest['cases'].append(case)
            observations.append({'case_id': identity, 'state': 'completed',
                'evidence_class': 'manual_browser' if allocation == 'demo' else 'fresh_application',
                'accounting': {'generation_attempts': 2, 'passes': []}})
    manifest['cases'].append({'id': 'local-rejection', 'role': 'route', 'local_only': True})
    observations.append({'case_id': 'local-rejection', 'state': 'failed',
                         'evidence_class': 'fresh_application'})
    cost = score(frozen_campaign)['cost']
    assert cost['accepted'] is True
    assert cost['generation_attempts'] == 36
    assert cost['missing_accounting_cases'] == 0
    assert {name: item['generation_attempts'] for name, item in cost['allocations'].items()} == {
        'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4}
    assert all(item['accepted'] for item in cost['allocations'].values())
    assert cost['usage']['unknown_passes'] == 36
    assert cost['physical_responses'] == {'known': 0, 'unknown_attempts': 36}
    assert cost['estimated_cost'] is None
    assert cost['cost_source'] == 'unavailable'
