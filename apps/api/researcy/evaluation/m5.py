"""Frozen M5 scoring. Hosted execution is opt-in and uses application endpoints only.

Raw PDFs, annotations, generated output, human reviews, bindings and the ledger are
private inputs. Only the deliberately constructed aggregate result is publishable.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable, TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import UUID, uuid4

if TYPE_CHECKING:
    import httpx2


PRIMARY_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/openai'
PRIMARY_MODEL = 'gemini-3.8-flash'
ALLOCATIONS = {'research': 16, 'reader': 6, 'discovery': 4, 'demo': 6, 'diagnostic': 4}
TOKEN_FIELDS = ('prompt_tokens', 'completion_tokens', 'total_tokens')
CASE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')


class EvaluationError(ValueError):
    """A safe, stable error code; never provider text or credentials."""


def _json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvaluationError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(EvaluationError('INVALID_JSON_NUMBER')))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvaluationError('INVALID_JSON_ARTIFACT') from error


def _atomic_json(path: Path, value: dict, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600 if private else 0o644)
            json.dump(value, stream, ensure_ascii=True, allow_nan=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_artifacts(manifest: dict, root: Path) -> None:
    """Check both historical bytes and new frozen source/annotation artifacts."""
    root = root.resolve()
    for artifact in manifest.get('artifacts', []):
        path = (root / artifact['path']).resolve()
        if not path.is_relative_to(root):
            raise EvaluationError('ARTIFACT_PATH_ESCAPE')
        if not path.is_file():
            raise EvaluationError('ARTIFACT_NOT_FOUND')
        if _hash(path) != artifact['sha256']:
            raise EvaluationError('ARTIFACT_HASH_MISMATCH')


def _git_main_repository(root_path: Path) -> Path:
    dot_git = root_path / '.git'
    if not dot_git.exists():
        raise EvaluationError('ROOT_NOT_GIT_CHECKOUT')
    if dot_git.is_dir():
        if not (dot_git / 'HEAD').exists() or not (dot_git / 'objects').exists():
            raise EvaluationError('ROOT_NOT_GIT_CHECKOUT')
        return root_path.resolve()
    elif dot_git.is_file():
        content = dot_git.read_text(encoding='utf-8').strip()
        if not content.startswith('gitdir:'):
            raise EvaluationError('ROOT_NOT_GIT_CHECKOUT')
        gitdir_raw = content[len('gitdir:'):].strip()
        gitdir = Path(gitdir_raw)
        if not gitdir.is_absolute():
            gitdir = (root_path / gitdir).resolve()
        else:
            gitdir = gitdir.resolve()
        commondir_file = gitdir / 'commondir'
        if commondir_file.exists():
            common_raw = commondir_file.read_text(encoding='utf-8').strip()
            common_dir = (gitdir / common_raw).resolve()
            return common_dir.parent
        return gitdir.parent
    else:
        raise EvaluationError('ROOT_NOT_GIT_CHECKOUT')


def require_private_path(path: Path, root: Path) -> Path:
    root = root.resolve()
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    private_roots = ('.omp/runtime', 'qualification/private', 'apps/api/private', 'evidence/private')
    valid = any(resolved.is_relative_to((root / base).resolve()) for base in private_roots)
    if not valid:
        try:
            main_repo = _git_main_repository(root)
            valid = any(resolved.is_relative_to((main_repo / base).resolve()) for base in private_roots)
        except Exception:
            pass
    if not valid:
        raise EvaluationError('PRIVATE_PATH_REQUIRED')
    return resolved


def _metric(numerator: int | float, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def _nonnegative(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _reviewed(value: dict) -> bool:
    return isinstance(value.get('reviewer'), str) and bool(value['reviewer'].strip())


def _index(records: list[dict], field: str) -> dict:
    indexed = {}
    for record in records:
        key = record.get(field)
        if not isinstance(key, str) or not CASE_ID.fullmatch(key):
            raise EvaluationError('INVALID_RECORD_ID')
        if key in indexed:
            raise EvaluationError('DUPLICATE_RECORD_ID')
        indexed[key] = record
    return indexed


def _validate_manifest(manifest: dict) -> tuple[dict, dict]:
    if manifest.get('schema_version') != 1 or not manifest.get('frozen_at'):
        raise EvaluationError('INVALID_FROZEN_MANIFEST')
    sources = _index(manifest.get('sources', []), 'id')
    cases = _index(manifest.get('cases', []) + manifest.get('diagnostic_cases', []), 'id')
    scientific = [source for source in sources.values() if source.get('kind') == 'scientific']
    if len({source.get('sha256') for source in scientific}) < 4:
        raise EvaluationError('INSUFFICIENT_SCIENTIFIC_CORPUS')
    for source in sources.values():
        if (not DIGEST.fullmatch(source.get('sha256', '')) or not source.get('edition')
                or type(source.get('page_count')) is not int or source['page_count'] <= 0):
            raise EvaluationError('INVALID_SOURCE_MANIFEST')
    for case in cases.values():
        selected = case.get('selected_sources', [])
        active = case.get('active_source')
        if active is not None and active not in sources:
            raise EvaluationError('UNKNOWN_CASE_SOURCE')
        if len(selected) != len(set(selected)) or active in selected or any(source not in sources for source in selected):
            raise EvaluationError('INVALID_CASE_SELECTION')
        if case.get('role') == 'research' and not 1 <= len(selected) <= 3:
            raise EvaluationError('INVALID_CASE_SELECTION')
    return sources, cases


def _check_source_pins(observations: list[dict], sources: dict, bindings: dict) -> None:
    for observation in observations:
        seen = set()
        for pin in observation.get('sources', []):
            source_id = pin.get('id', pin.get('source_id'))
            source = sources.get(source_id)
            if source is None or source_id in seen:
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            seen.add(source_id)
            if any(pin.get(field) != source[field] for field in ('sha256', 'edition')):
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            expected = bindings.get(source_id)
            if expected and any(pin.get(field) != expected.get(field) for field in ('paper_id', 'document_version', 'profile_hash')):
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')


def _measurements(observations: list[dict], layer: str, field: str, key: str) -> dict:
    indexed = {}
    for observation in observations:
        for item in observation.get(layer, {}).get(field, []):
            identity = item[key]
            if identity in indexed and indexed[identity] != item:
                raise EvaluationError('CONFLICTING_MEASUREMENT')
            indexed[identity] = item
    return indexed


def _boxes_valid(boxes) -> bool:
    return isinstance(boxes, list) and bool(boxes) and all(
        isinstance(box, (list, tuple)) and len(box) == 4
        and all(type(value) in (int, float) and math.isfinite(value) for value in box)
        and box[0] < box[2] and box[1] < box[3] for box in boxes)


def _layout_counts(observations: list[dict]) -> dict:
    counts = {}
    for kind in ('heading', 'body', 'table', 'caption', 'figure', 'one_column', 'two_column', 'alternative'):
        values = [item.get('parser', {}).get('layout_region_counts', {}).get(kind) for item in observations]
        numeric = [value for value in values if type(value) is int and value >= 0]
        if numeric:
            counts[kind] = sum(numeric)
    return counts


def _score_parser(observations: list[dict], annotations: dict) -> dict:
    expected = [region for region in annotations.get('regions', []) if region.get('used_as_gold', True)]
    observed = _measurements(observations, 'parser', 'regions', 'region_id')
    orders = _measurements(observations, 'parser', 'reading_order', 'id')
    resolved = sections = covered = total = 0
    missing = []
    for region in expected:
        length = region['raw_end'] - region['raw_start']
        total += length
        item = observed.get(region['id'])
        if not item:
            missing.append(region['id'])
            continue
        count = item.get('covered_codepoints', 0)
        if type(count) is not int or not 0 <= count <= length:
            raise EvaluationError('INVALID_TEXT_COVERAGE')
        covered += count
        exact = (item.get('raw_quote_sha256') == region['raw_quote_sha256']
                 and item.get('page_index') == region['page_index']
                 and _boxes_valid(item.get('boxes')) and item['boxes'] == region['boxes']
                 and all(field not in region or item.get(field) == region[field]
                         for field in ('media_box', 'crop_box', 'rotation')))
        resolved += exact
        sections += bool(region.get('section') and item.get('section') == region['section'])
    relations = annotations.get('reading_order', [])
    correct_order = sum(orders.get(relation['id'], {}).get('correct') is True for relation in relations)
    section_total = sum(bool(region.get('section')) for region in expected)
    passed = bool(expected) and resolved == len(expected) and correct_order == len(relations)
    return {'resolvable_regions': _metric(resolved, len(expected)), 'text_coverage': _metric(covered, total),
            'sections': _metric(sections, section_total), 'reading_order': _metric(correct_order, len(relations)),
            'missing_region_ids': missing, 'missing_order_ids': [item['id'] for item in relations if item['id'] not in orders],
            'layout_region_counts': _layout_counts(observations),
            'scope': 'frozen_gold_regions_only', 'accepted': passed}


def _hit_regions(hit) -> set[str]:
    if isinstance(hit, str):
        return {hit}
    return set(hit.get('region_ids', []))


def _first_rank(hits: list, groups: list[list[str]], limit: int) -> int | None:
    for rank, hit in enumerate(hits[:limit], 1):
        if any(set(group).issubset(_hit_regions(hit)) for group in groups):
            return rank
    return None


def _score_retrieval(observations: list[dict], annotations: dict, cases: dict, bindings: dict) -> dict:
    expected = annotations.get('retrieval_sets', [])
    records = {}
    scope_errors = verified = hit_count = 0
    for observation in observations:
        case = cases[observation['case_id']]
        allowed = {case.get('active_source'), *case.get('selected_sources', [])}
        for record in observation.get('retrieval', []):
            set_id = record['set_id']
            if set_id in records:
                raise EvaluationError('DUPLICATE_RETRIEVAL_SET')
            records[set_id] = record
            source_id = record['source_id']
            if source_id not in allowed:
                scope_errors += 1
            for kind in ('dense', 'lexical', 'fused', 'packed'):
                hits = record.get(kind, [])
                if kind != 'packed' and len(hits) > 5:
                    raise EvaluationError('RETRIEVAL_LIMIT_EXCEEDED')
                for hit in hits:
                    hit_count += 1
                    if not isinstance(hit, dict):
                        continue
                    identity = hit.get('source_id', source_id)
                    if identity not in allowed or identity != source_id:
                        scope_errors += 1
                    pin = bindings.get(identity)
                    exact = bool(pin) and all(hit.get(field) == pin[field]
                        for field in ('paper_id', 'document_version', 'profile_hash'))
                    verified += exact
    result = {'scope_errors': scope_errors, 'tuple_identity': _metric(verified, hit_count),
              'missing_set_ids': [item['id'] for item in expected if item['id'] not in records],
              'historical_lexical': 'BM25', 'fresh_lexical': 'PostgreSQL FTS',
              'historical_comparability_claimed': False}
    for subset in ('q0', 'paired'):
        sets = [item for item in expected if item.get('subset') == subset]
        scored = {}
        for kind in ('dense', 'lexical', 'fused', 'packed'):
            recall2 = recall5 = packed = 0
            reciprocal = 0.0
            for item in sets:
                record = records.get(item['id'], {})
                groups = item.get('region_groups') or [[region] for region in item['region_ids']]
                hits = record.get(kind, []) if record.get('source_id', item['source_id']) == item['source_id'] else []
                rank = _first_rank(hits, groups, 5)
                recall5 += rank is not None
                recall2 += rank is not None and rank <= 2
                reciprocal += 1 / rank if rank else 0
                union = set().union(*(_hit_regions(hit) for hit in hits)) if hits else set()
                packed += any(set(group).issubset(union) for group in groups)
            scored[kind] = {'recall_at_2': _metric(recall2, len(sets)),
                            'recall_at_5': _metric(recall5, len(sets)), 'mrr': _metric(reciprocal, len(sets))}
            if kind == 'packed':
                scored[kind]['recall'] = _metric(packed, len(sets))
        result[subset] = scored
    q0 = result['q0']['fused']['recall_at_5']
    paired = result['paired']['fused']['recall_at_5']
    result['accepted'] = (q0['denominator'] == 8 and q0['numerator'] >= 6
        and paired['denominator'] > 0 and paired['value'] >= 0.75 and not scope_errors
        and bool(hit_count) and verified == hit_count and not result['missing_set_ids'])
    return result


def _citation_exact(citation: dict, annotations: dict, regions: dict) -> bool:
    if citation.get('unique_raw_mapping') is not True or not _boxes_valid(citation.get('boxes')):
        return False
    region = regions.get(citation.get('region_id'))
    if region:
        raw = citation.get('evidence_quote')
        digest = hashlib.sha256(raw.encode('utf-8')).hexdigest() if isinstance(raw, str) else citation.get('raw_quote_sha256')
        return (citation.get('source_id') == region['source_id'] and citation.get('page') == region['page_index'] + 1
                and digest == region['raw_quote_sha256'] and citation['boxes'] == region['boxes']
                and citation.get('raw_start') == region['raw_start'] and citation.get('raw_end') == region['raw_end'])
    source = annotations.get('sources', {}).get(citation.get('source_id'))
    page_number = citation.get('page')
    quote = citation.get('evidence_quote')
    if (not source or type(page_number) is not int or not 1 <= page_number <= source['page_count']
            or not isinstance(quote, str) or len(quote) != len(citation['boxes'])):
        return False
    page = source['pages'][page_number - 1]
    by_box = {}
    for line in page['lines']:
        for char, box in zip(line['text'], line['pdf_boxes'], strict=True):
            by_box.setdefault(tuple(box), []).append(char)
    # Compare every raw Unicode character, not rounded regions or approximate IoU.
    fragments = citation.get('raw_fragments', [])
    if not fragments:
        return False
    cursor = 0
    for fragment in fragments:
        start, end = fragment.get('source_start'), fragment.get('source_end')
        raw = fragment.get('quote')
        if type(start) is not int or type(end) is not int or not isinstance(raw, str) or end - start != len(raw):
            return False
        fragment_boxes = citation['boxes'][cursor:cursor + len(raw)]
        candidates = [line for line in page['lines'] if 0 <= start < end <= len(line['text'])
            and line['text'][start:end] == raw and line['pdf_boxes'][start:end] == fragment_boxes]
        if len(candidates) != 1:
            return False
        cursor += len(raw)
    if cursor != len(quote) or ''.join(fragment['quote'] for fragment in fragments) != quote:
        return False
    return all(by_box.get(tuple(box)) == [char] for char, box in zip(quote, citation['boxes'], strict=True))


def _score_citations(observations: list[dict], annotations: dict, cases: dict, bindings: dict) -> tuple[dict, dict]:
    regions = _index(annotations.get('regions', []), 'id')
    total = allowed_count = exact_count = mapped = complete = assertion_count = leakage = decorative = page_only = geometry_errors = 0
    accepted = {}
    for observation in observations:
        case = cases[observation['case_id']]
        allowed_sources = {case.get('active_source'), *case.get('selected_sources', [])}
        citations = {}
        for citation in observation.get('citations', []):
            identity = citation.get('id', citation.get('citation_id'))
            if not identity or identity in citations:
                raise EvaluationError('DUPLICATE_CITATION_ID')
            source_id = citation.get('source_id')
            allowed = source_id in allowed_sources
            pin = bindings.get(source_id)
            tuple_exact = bool(pin) and all(citation.get(field) == pin[field]
                for field in ('paper_id', 'document_version', 'profile_hash'))
            if allowed and pin and not tuple_exact:
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            exact = allowed and tuple_exact and _citation_exact(citation, annotations, regions)
            total += 1
            allowed_count += allowed
            exact_count += exact
            mapped += citation.get('unique_raw_mapping') is True and exact
            leakage += not allowed
            page_only += not citation.get('boxes')
            geometry_errors += allowed and tuple_exact and not exact
            citations[identity] = {'exact': exact, 'source_id': source_id, 'allowed': allowed, 'tuple_exact': tuple_exact}
        accepted[observation['case_id']] = citations
        assertions = [assertion for idea in observation.get('ideas', []) for assertion in idea.get('assertions', [])]
        assertions.extend(observation.get('reader', {}).get('assertions', []))
        used = set()
        for assertion in assertions:
            assertion_count += 1
            ids = assertion.get('citation_ids', [])
            used.update(ids)
            complete += bool(ids) and all(citations.get(identity, {}).get('exact') for identity in ids)
        decorative += len(set(citations) - used)
    result = {'allowed': _metric(allowed_count, total), 'exact': _metric(exact_count, total),
              'unique_raw_mapping': _metric(mapped, total), 'completeness': _metric(complete, assertion_count),
              'scope_errors': leakage, 'page_only_fallbacks': page_only, 'geometry_errors': geometry_errors,
              'decorative_citations': decorative,
              'accepted': bool(total) and allowed_count == exact_count == mapped == total
                  and complete == assertion_count and not decorative}
    return result, accepted


def _supported_idea(idea: dict, citations: dict) -> bool:
    assertions = idea.get('assertions', [])
    ids = idea.get('citation_ids', [])
    used = {identity for assertion in assertions for identity in assertion.get('citation_ids', [])}
    return (bool(assertions) and bool(ids) and set(ids) == used and _reviewed(idea)
        and idea.get('hypothesis_labelled') is True and idea.get('motivation_score') == 2
        and idea.get('claims_proven_novelty') is False and idea.get('claims_proven_feasibility') is False
        and all(citations.get(identity, {}).get('exact') for identity in ids)
        and all(_reviewed(assertion) and type(assertion.get('support_score')) is int
            and assertion['support_score'] == 2 and bool(assertion.get('citation_ids'))
            and all(identity in ids and citations.get(identity, {}).get('exact') for identity in assertion['citation_ids'])
            for assertion in assertions))


def _score_research(cases: dict, observed: dict, accepted_citations: dict) -> dict:
    expected = [case for case in cases.values() if case.get('role') == 'research'
                and case.get('allocation') not in ('demo', 'diagnostic')]
    positives = [case for case in expected if case['id'] in ('R1', 'R2', 'R3', 'R4', 'R8')]
    passed = positive_passes = full_assertions = assertions = labelled = idea_count = scope = cross = 0
    results = {}
    for case in expected:
        observation = observed.get(case['id'])
        if not observation:
            results[case['id']] = {'passed': False, 'state': 'missing', 'fully_supported_ideas': 0}
            continue
        ideas = observation.get('ideas', [])
        citations = accepted_citations.get(case['id'], {})
        fully_supported = sum(_supported_idea(idea, citations) for idea in ideas)
        for idea in ideas:
            idea_count += 1
            labelled += _reviewed(idea) and idea.get('hypothesis_labelled') is True
            for assertion in idea.get('assertions', []):
                assertions += 1
                full_assertions += _reviewed(assertion) and type(assertion.get('support_score')) is int and assertion['support_score'] == 2
        scope += observation.get('scope_errors', 0) + sum(not citation['allowed'] for citation in citations.values())
        safe = (observation.get('evidence_class') == 'fresh_application'
                and observation.get('scope_errors') == 0 and observation.get('unauthorized_actions') == 0)
        split_ideas = sum(_supported_idea(idea, citations) and len({citations[identity]['source_id']
            for identity in idea['citation_ids']}) >= 2 for idea in ideas)
        split = split_ideas > 0
        cross += split_ideas
        terminal_refusal = observation.get('state') == 'refused' or (observation.get('state') == 'failed'
            and observation.get('error_code') == 'RESEARCH_INSUFFICIENT_EVIDENCE')
        if case.get('expectation') == 'insufficient':
            good = safe and terminal_refusal and not ideas and not citations
        elif case.get('expectation') == 'hypothesis' and terminal_refusal:
            good = safe and not ideas and not citations
        else:
            good = (safe and observation.get('state') == 'completed' and 1 <= len(ideas) <= 3
                    and fully_supported == len(ideas) and all(item['exact'] for item in citations.values())
                    and (not case.get('requires_cross_source') or split))
        passed += good
        positive_passes += good and case in positives
        results[case['id']] = {'passed': bool(good), 'state': observation.get('state', 'unknown'),
            'fully_supported_ideas': fully_supported, 'source_coverage': [len({citations[identity]['source_id']
                for identity in idea.get('citation_ids', []) if identity in citations}) for idea in ideas],
            'split_source_support': split}
    missing = [case['id'] for case in expected if case['id'] not in observed]
    return {'expected_cases': len(expected), 'observed_cases': len(expected) - len(missing),
        'missing_case_ids': missing, 'cases': _metric(passed, len(expected)),
        'supported_cases': _metric(positive_passes, len(positives)),
        'assertion_support': _metric(full_assertions, assertions), 'hypothesis_labels': _metric(labelled, idea_count),
        'split_source_ideas': _metric(cross, idea_count), 'scope_errors': scope, 'case_results': results,
        'accepted': len(expected) == 8 and passed == 8 and not scope and not missing}


def _score_reader(cases: dict, observed: dict, citations: dict) -> dict:
    expected = [case for case in cases.values() if case.get('role') == 'reader'
                and case.get('allocation') not in ('demo', 'diagnostic')]
    confusion = {'true_refusals': 0, 'false_refusals': 0, 'false_answers': 0, 'true_answers': 0,
                 'failed_or_interrupted': 0, 'missing': 0}
    passed = supported = assertions = follow_up = 0
    for case in expected:
        observation = observed.get(case['id'])
        if not observation:
            confusion['missing'] += 1
            continue
        refusal = observation.get('state') == 'refused'
        insufficient = case.get('expectation') == 'insufficient'
        if observation.get('state') not in ('completed', 'refused'):
            confusion['failed_or_interrupted'] += 1
        else:
            confusion['true_refusals' if insufficient and refusal else 'false_answers' if insufficient
                      else 'false_refusals' if refusal else 'true_answers'] += 1
        claims = observation.get('reader', {}).get('assertions', [])
        exact = citations.get(case['id'], {})
        valid_claims = bool(claims) and all(_reviewed(claim) and claim.get('support_score') == 2
            and claim.get('correctness_score') == 2 and claim.get('citation_ids')
            and all(exact.get(identity, {}).get('exact') for identity in claim['citation_ids']) for claim in claims)
        assertions += len(claims)
        supported += sum(_reviewed(claim) and claim.get('support_score') == 2 for claim in claims)
        searched = observation.get('accounting', {}).get('same_paper_searches') == 1
        follow_up += searched
        good = (refusal and not exact) if insufficient else (observation.get('state') == 'completed' and valid_claims)
        if case.get('expectation') == 'follow_up':
            good = searched and (good or (refusal and not exact))
        good = good and observation.get('evidence_class') == 'fresh_application'
        passed += good
    missing = [case['id'] for case in expected if case['id'] not in observed]
    return {'cases': _metric(passed, len(expected)), 'factual_support': _metric(supported, assertions),
        'abstention': confusion, 'fresh_follow_up_cases': follow_up, 'missing_case_ids': missing,
        'historical_reference_cases': 10, 'historical_evidence_counts_as_fresh': False,
        'accepted': bool(expected) and passed == len(expected) and not missing}


def _score_discovery(cases: dict, observed: dict) -> dict:
    expected = [case for case in cases.values() if case.get('role') == 'discovery'
                and case.get('allocation') not in ('demo', 'diagnostic')]
    passed = implicit = returned_total = inspected_total = rationale_total = rationale_supported = 0
    for case in expected:
        observation = observed.get(case['id'], {})
        item = observation.get('discovery', {})
        ids = item.get('returned_ids', [])
        scores = item.get('metadata_rationale_scores', [])
        inspected = item.get('inspected_unique')
        imports = item.get('implicit_imports')
        implicit += imports if type(imports) is int and imports >= 0 else 0
        returned_total += len(ids)
        inspected_total += inspected if type(inspected) is int and inspected >= 0 else 0
        rationale_total += len(ids)
        reviewed = _reviewed(item) and len(scores) == len(ids)
        rationale_supported += sum(score == 2 for score in scores) if reviewed else 0
        passed += (observation.get('evidence_class') == 'fresh_application' and observation.get('state') == 'completed'
                   and type(inspected) is int and 0 <= inspected <= 10 and len(ids) == len(set(ids))
                   and len(ids) <= 3 and item.get('active_excluded') is True and imports == 0 and reviewed
                   and all(score == 2 for score in scores)
                   and (case.get('expectation') != 'search' or item.get('action') == 'search_arxiv_metadata' and bool(ids)))
    missing = [case['id'] for case in expected if case['id'] not in observed]
    return {'cases': _metric(passed, len(expected)), 'inspected_unique_total': inspected_total,
        'returned_total': returned_total, 'metadata_rationale': _metric(rationale_supported, rationale_total),
        'implicit_imports': implicit, 'missing_case_ids': missing,
        'accepted': bool(expected) and passed == len(expected) and not missing}


def _score_route(observed: dict, cases: dict) -> dict:
    paths = {'R1': 'supported', 'R5': 'insufficient', 'R7': 'hostile_contained', 'R8': 'subsequent_valid'}
    actual = 0
    missing = []
    for case_id, path in paths.items():
        observation = observed.get(case_id, {})
        route = observation.get('route', {})
        accounting = observation.get('accounting') or {}
        passes = accounting.get('passes', [])
        actual_transport = (type(accounting.get('generation_attempts')) is int
            and 1 <= accounting['generation_attempts'] <= 2 and len(passes) == accounting['generation_attempts']
            and all(entry.get('provider') == 'gemini' and entry.get('configured_model') == PRIMARY_MODEL
                and (entry.get('response_received') is True or entry.get('physical_requests') == 1) for entry in passes))
        good = (observation.get('evidence_class') == 'fresh_application'
            and route.get('application_graph') is True and route.get('provider') == 'gemini'
            and route.get('model') == PRIMARY_MODEL and route.get('endpoint') == PRIMARY_ENDPOINT
            and route.get(path) is True and observation.get('unauthorized_actions') == 0 and actual_transport)
        actual += good
        if not good:
            missing.append(case_id)
    controlled_ids = [case['id'] for case in cases.values()
        if case.get('role') == 'route' and case['id'] in ('L-malformed-output', 'L-unsupported-action')]
    controlled = sum(observed.get(identity, {}).get('evidence_class') == 'controlled_http'
        and observed[identity].get('route', {}).get('decoder_graph_rejected') is True
        and observed[identity].get('unauthorized_actions') == 0
        and observed[identity].get('accepted_publications') == 0 for identity in controlled_ids)
    boundary_ids = [case['id'] for case in cases.values() if case.get('role') == 'route'
        and case.get('local_only') and case['id'] not in controlled_ids]
    boundaries = sum(observed.get(identity, {}).get('state') in ('failed', 'interrupted')
        and observed[identity].get('route', {}).get('boundary_rejected') is True
        and observed[identity].get('unauthorized_actions') == 0
        and observed[identity].get('accepted_publications') == 0 for identity in boundary_ids)
    return {'actual_research_paths': _metric(actual, 4), 'unproven_actual_case_ids': missing,
        'controlled_http_rejections': _metric(controlled, len(controlled_ids)),
        'local_boundary_rejections': _metric(boundaries, len(boundary_ids)),
        'controlled_is_natural_provider_output': False,
        'accepted': actual == 4 and len(controlled_ids) == 2 and controlled == 2 and boundaries == len(boundary_ids)}


def _score_product(observations: list[dict], cases: dict) -> dict:
    expected = [case['id'] for case in cases.values() if case.get('product_journey')]
    observed = {item['case_id']: item for item in observations}
    latencies = {name: [] for name in ('import_to_ready_ms', 'header_ms', 'first_validated_delta_ms', 'terminal_ms')}
    jumps = attempts = journeys = 0
    states = {'cancel': False, 'reload': False, 'retry': False}
    for observation in observations:
        item = observation.get('product', {})
        for name in latencies:
            value = item.get(name)
            if _nonnegative(value):
                latencies[name].append(value)
        for state in states:
            states[state] |= item.get(state) is True
        count = item.get('jump_attempts', 0)
        success = item.get('exact_jump_successes', 0)
        if type(count) is not int or type(success) is not int or not 0 <= success <= count:
            raise EvaluationError('INVALID_JUMP_MEASUREMENT')
        attempts += count
        jumps += success
    for identity in expected:
        observation = observed.get(identity, {})
        item = observation.get('product', {})
        journeys += (observation.get('evidence_class') == 'manual_browser'
            and observation.get('state') == 'completed' and item.get('journey_complete') is True)
    return {'journeys': _metric(journeys, len(expected)), 'exact_jumps': _metric(jumps, attempts),
        'latency_ms': latencies, 'states_observed': states, 'latency_generalization_claimed': False,
        'accepted': bool(expected) and journeys == len(expected) and attempts > 0 and jumps == attempts and all(states.values())}


def _score_cost(observations: list[dict], cases: dict | None = None) -> dict:
    cases = cases or {}
    attempts = known = partial = unknown = physical_known = physical_unknown = missing_accounting = 0
    subtotals = {name: 0 for name in TOKEN_FIELDS}
    complete_fields = {name: True for name in TOKEN_FIELDS}
    estimate = 0.0
    estimate_complete = True
    mapping_count = 0
    per_pass_latency = []
    alloc_attempts = {name: 0 for name in ALLOCATIONS}
    alloc_known = {name: 0 for name in ALLOCATIONS}
    alloc_missing = {name: 0 for name in ALLOCATIONS}

    for observation in observations:
        case_id = observation.get('case_id')
        case = cases.get(case_id) if cases else None
        allocation = case.get('allocation') if case else None
        accounting = observation.get('accounting')
        evidence_class = observation.get('evidence_class')

        if accounting:
            if case is not None:
                if (allocation not in ALLOCATIONS
                        or case.get('role') not in ('research', 'reader', 'discovery', 'route')
                        or case.get('local_only')):
                    raise EvaluationError('INVALID_CASE_ACCOUNTING')

        count = accounting.get('generation_attempts') if accounting else None
        if count is None:
            if not (case and case.get('local_only')) and evidence_class in ('fresh_application', 'manual_browser', 'owner_manual'):
                missing_accounting += 1
                if allocation in ALLOCATIONS:
                    alloc_missing[allocation] += 1
            if not accounting:
                continue

        passes = accounting.get('passes', [])
        if count is None:
            count = len(passes)
        if type(count) is not int or not 0 <= count <= 2 or len(passes) > count:
            raise EvaluationError('INVALID_ATTEMPT_ACCOUNTING')

        attempts += count
        if allocation in ALLOCATIONS:
            alloc_attempts[allocation] += count
            alloc_known[allocation] += count

        for number in range(count):
            entry = passes[number] if number < len(passes) else {}
            usage = entry.get('usage')
            if usage is not None and (not isinstance(usage, dict) or any(
                    key in usage and (type(usage[key]) is not int or usage[key] < 0) for key in TOKEN_FIELDS)):
                raise EvaluationError('INVALID_USAGE_ACCOUNTING')
            available = [key for key in TOKEN_FIELDS if usage and key in usage]
            known += len(available) == 3
            partial += 0 < len(available) < 3
            unknown += not available
            for name in TOKEN_FIELDS:
                if name in available:
                    subtotals[name] += usage[name]
                else:
                    complete_fields[name] = False
            physical = entry.get('physical_requests')
            if physical is None:
                if entry.get('response_received') is True: physical = 1
                elif entry.get('dispatched') is False: physical = 0
            if physical is not None and not (type(physical) is bool or type(physical) is int and physical in (0, 1)):
                raise EvaluationError('INVALID_PHYSICAL_ACCOUNTING')
            if physical is True or physical == 1:
                physical_known += 1
            elif physical is False or physical == 0:
                pass
            else:
                physical_unknown += 1
            if _nonnegative(entry.get('latency_ms')):
                per_pass_latency.append(entry['latency_ms'])
            billable = entry.get('billable_tokens', {})
            mapping = entry.get('billable_mapping', {})
            authoritative = (mapping.get('authoritative') is True and mapping.get('source') and mapping.get('date')
                and all(type(billable.get(name)) is int and billable[name] >= 0
                    for name in ('uncached_input', 'cached_input', 'output_including_thinking')))
            if authoritative:
                estimate += (billable['uncached_input'] * 0.75 + billable['cached_input'] * 0.075
                             + billable['output_including_thinking'] * 3.75) / 1_000_000
                mapping_count += 1
            else:
                estimate_complete = False

    allocations_summary = {}
    for name, limit in ALLOCATIONS.items():
        is_missing = alloc_missing[name] > 0
        tot = alloc_attempts[name] if not is_missing else None
        alloc_accepted = (not is_missing and tot is not None and tot <= limit)
        allocations_summary[name] = {
            'limit': limit,
            'generation_attempts': tot,
            'known_attempts_subtotal': alloc_known[name],
            'missing_accounting_cases': alloc_missing[name],
            'accepted': alloc_accepted,
        }

    totals = {name: subtotals[name] if attempts and complete_fields[name] and not missing_accounting else None
              for name in TOKEN_FIELDS}
    monetary = estimate if attempts and estimate_complete and not missing_accounting else None
    cost_accepted = (attempts > 0 and not missing_accounting and attempts <= 36
                     and all(item['accepted'] for item in allocations_summary.values()))

    return {'generation_attempts': attempts if not missing_accounting else None,
        'known_attempts_subtotal': attempts, 'missing_accounting_cases': missing_accounting,
        'allocations': allocations_summary,
        'usage': {'known_passes': known, 'partial_passes': partial, 'unknown_passes': unknown,
                  'totals': totals, 'known_subtotals': subtotals},
        'physical_responses': {'known': physical_known, 'unknown_attempts': physical_unknown},
        'per_pass_latency_ms': per_pass_latency, 'estimated_cost': monetary, 'billed_cost': None,
        'currency': 'USD', 'cost_source': 'documented_tariff' if monetary is not None else 'unavailable',
        'authoritatively_mapped_passes': mapping_count,
        'cost_unavailable_reason': None if monetary is not None else 'account_tariff_or_billable_unit_attribution_unverified',
        'public_pricing': {'source': 'https://ai.google.dev/gemini-api/docs/pricing', 'date': '2026-10-04',
            'tier': 'Standard paid through 2026-12-31', 'input_per_million': 0.75,
            'cached_input_per_million': 0.075, 'output_including_thinking_per_million': 3.75},
        'unknown_is_free': False, 'accepted': cost_accepted}


def score_campaign(manifest: dict, observations: list[dict], *, annotations: dict | None = None,
                   bindings: dict | None = None) -> dict:
    """Score all frozen denominators; human support annotations are mandatory evidence."""
    sources, cases = _validate_manifest(manifest)
    annotations = annotations or {}
    bindings = bindings or {}
    observed = _index(observations, 'case_id')
    if any(identity not in cases for identity in observed):
        raise EvaluationError('UNKNOWN_OBSERVATION_CASE')
    if any(item.get('state') not in ('completed', 'refused', 'failed', 'interrupted', 'running') for item in observations):
        raise EvaluationError('INVALID_OBSERVATION_STATE')
    _check_source_pins(observations, sources, bindings)
    citation, accepted_citations = _score_citations(observations, annotations, cases, bindings)
    result = {'schema_version': 1, 'campaign_id': manifest['campaign_id'],
        'parser': _score_parser(observations, annotations),
        'retrieval': _score_retrieval(observations, annotations, cases, bindings),
        'citation': citation, 'research': _score_research(cases, observed, accepted_citations),
        'reader': _score_reader(cases, observed, accepted_citations),
        'discovery': _score_discovery(cases, observed), 'route': _score_route(observed, cases),
        'product': _score_product(observations, cases), 'cost': _score_cost(observations, cases),
        'evidence_class_counts': {kind: sum(item.get('evidence_class') == kind for item in observations)
            for kind in ('fresh_application', 'historical', 'controlled_http', 'local_parse',
                         'local_retrieval', 'manual_browser', 'owner_manual')},
        'missing_case_ids': [identity for identity, case in cases.items()
            if identity not in observed and case.get('allocation') != 'diagnostic'],
        'diagnostic': {'observed_cases': sum(cases[item['case_id']].get('allocation') == 'diagnostic'
            for item in observations), 'substitutes_primary_failures': False}}
    required = manifest.get('required_layers', list(result.keys())[2:11])
    if any(layer not in result or not isinstance(result[layer], dict) or 'accepted' not in result[layer] for layer in required):
        raise EvaluationError('INVALID_REQUIRED_LAYER')
    result['accepted'] = bool(required) and not result['missing_case_ids'] and all(result[layer]['accepted'] for layer in required)
    return result


class AttemptLedger:
    """A process-locked, durable serial reservation ledger, never an automatic retry."""

    def __init__(self, path: Path, *, budget: int, allocations: dict, campaign_id: str):
        if type(budget) is not int or not 0 < budget <= 36 or allocations != ALLOCATIONS:
            raise EvaluationError('INVALID_ATTEMPT_BUDGET')
        self.path = Path(path)
        self.budget = budget
        self.allocations = allocations.copy()
        self.campaign_id = campaign_id
        with self._locked() as data:
            self._check(data)

    def _check(self, data: dict) -> None:
        if (data.get('campaign_id') != self.campaign_id or data.get('budget') != self.budget
                or data.get('allocations') != self.allocations):
            raise EvaluationError('LEDGER_CONFIGURATION_MISMATCH')

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = _json(self.path) if self.path.exists() else {
                'schema_version': 1, 'campaign_id': self.campaign_id, 'budget': self.budget,
                'allocations': self.allocations, 'runs': []}
            self._check(data)
            yield data
            _atomic_json(self.path, data, private=True)

    def reserve(self, case_id: str, allocation: str, *, diagnostic_of: str | None = None) -> str:
        if not CASE_ID.fullmatch(case_id) or allocation not in self.allocations:
            raise EvaluationError('INVALID_CAMPAIGN_RESERVATION')
        with self._locked() as data:
            if any(run['status'] in ('reserved', 'dispatched') for run in data['runs']):
                raise EvaluationError('CAMPAIGN_RUN_ACTIVE')
            if any(run['case_id'] == case_id for run in data['runs']):
                raise EvaluationError('CASE_ALREADY_DISPATCHED')
            if any(run['status'] == 'uncertain' and not run.get('terminal_cleanup') for run in data['runs']):
                raise EvaluationError('CAMPAIGN_CLEANUP_UNPROVEN')
            if allocation == 'diagnostic' and not any(run['case_id'] == diagnostic_of
                    and run.get('outcome') in ('failed', 'interrupted', 'prerequisite_failed') for run in data['runs']):
                raise EvaluationError('NAMED_FAILED_DIAGNOSTIC_REQUIRED')
            charged = sum(run['charged_attempts'] for run in data['runs'])
            allocated = sum(run['charged_attempts'] for run in data['runs'] if run['allocation'] == allocation)
            if charged + 2 > self.budget:
                raise EvaluationError('ATTEMPT_BUDGET_EXHAUSTED')
            if allocated + 2 > self.allocations[allocation]:
                raise EvaluationError('ALLOCATION_EXHAUSTED')
            identity = str(uuid4())
            data['runs'].append({'reservation_id': identity, 'case_id': case_id, 'allocation': allocation,
                'diagnostic_of': diagnostic_of, 'status': 'reserved', 'charged_attempts': 2,
                'reserved_at': datetime.now(timezone.utc).isoformat(), 'terminal_cleanup': False})
            return identity

    def dispatched(self, reservation: str) -> None:
        with self._locked() as data:
            run = self._run(data, reservation)
            if run['status'] != 'reserved':
                raise EvaluationError('INVALID_LEDGER_TRANSITION')
            run.update(status='dispatched', dispatched_at=datetime.now(timezone.utc).isoformat())

    @staticmethod
    def _run(data: dict, identity: str) -> dict:
        for run in data['runs']:
            if run['reservation_id'] == identity:
                return run
        raise EvaluationError('UNKNOWN_LEDGER_RESERVATION')

    def finish(self, reservation: str, *, attempts: int | None, terminal_cleanup: bool,
               outcome: str = 'failed') -> None:
        if attempts is not None and (type(attempts) is not int or not 0 <= attempts <= 2):
            raise EvaluationError('INVALID_ATTEMPT_ACCOUNTING')
        with self._locked() as data:
            run = self._run(data, reservation)
            if run['status'] not in ('dispatched', 'uncertain'):
                raise EvaluationError('INVALID_LEDGER_TRANSITION')
            run.update(status='settled' if terminal_cleanup and attempts is not None else 'uncertain',
                charged_attempts=attempts if terminal_cleanup and attempts is not None else 2,
                terminal_cleanup=terminal_cleanup, outcome=outcome,
                finished_at=datetime.now(timezone.utc).isoformat())

    def summary(self) -> dict:
        with self._locked() as data:
            charged = sum(run['charged_attempts'] for run in data['runs'])
            return {'charged_attempts': charged, 'remaining_attempts': self.budget - charged,
                'uncertain_runs': sum(run['status'] == 'uncertain' for run in data['runs']),
                'reserved_runs': sum(run['status'] in ('reserved', 'dispatched') for run in data['runs']),
                'allocations_consumed': {name: sum(run['charged_attempts'] for run in data['runs']
                    if run['allocation'] == name) for name in self.allocations}}


def run_campaign(manifest: dict, endpoint_run: Callable[[dict], dict], ledger: AttemptLedger,
                 *, observation_path: Path, manifest_sha256: str | None = None) -> list[dict]:
    """Dispatch serially; uncertain transport stops the campaign and retains both slots."""
    if any(case.get('product_journey') for case in manifest['cases']):
        raise EvaluationError('BROWSER_JOURNEY_REQUIRED')
    if Path(observation_path).exists():
        raise EvaluationError('OBSERVATIONS_ALREADY_EXIST')
    observations = []
    envelope = {'schema_version': 1, 'manifest_sha256': manifest_sha256, 'observations': observations}
    _atomic_json(Path(observation_path), envelope, private=True)
    for case in manifest['cases']:
        if case.get('local_only'):
            continue
        reservation = ledger.reserve(case['id'], case['allocation'], diagnostic_of=case.get('diagnostic_of'))
        ledger.dispatched(reservation)
        try:
            observation = endpoint_run(case)
            if observation.get('case_id') != case['id']:
                raise EvaluationError('APPLICATION_CASE_ID_MISMATCH')
        except Exception:
            observation = {'case_id': case['id'], 'state': 'failed', 'error_code': 'ENDPOINT_DISPATCH_UNCERTAIN',
                           'evidence_class': 'fresh_application', 'terminal_cleanup': False}
        observations.append(observation)
        # Preserve the private observation before releasing any reservation.
        _atomic_json(Path(observation_path), envelope, private=True)
        cleanup = observation.get('terminal_cleanup') is True
        attempts = observation.get('accounting', {}).get('generation_attempts')
        ledger.finish(reservation, attempts=attempts, terminal_cleanup=cleanup,
                      outcome=observation.get('state', 'failed'))
        if not cleanup or attempts is None:
            break
    return observations


def validate_run_target(base_url: str, origin: str, project: str) -> None:
    for value in (base_url, origin):
        parsed = urlsplit(value)
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
                or parsed.port in (None, 3000, 8000) or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
            raise EvaluationError('ISOLATED_ENDPOINT_REQUIRED')
    if not re.fullmatch(r'researcy-m5-[a-z0-9-]+', project) or 'main' in project:
        raise EvaluationError('ISOLATED_ENDPOINT_REQUIRED')


def _bindings_document(document: dict) -> dict:
    bindings = document.get('sources', {})
    for identity, pin in bindings.items():
        if not CASE_ID.fullmatch(identity) or not DIGEST.fullmatch(pin.get('profile_hash', '')):
            raise EvaluationError('INVALID_PRIVATE_BINDINGS')
        try:
            UUID(pin['paper_id'])
            UUID(pin['document_version'])
        except (KeyError, ValueError, TypeError) as error:
            raise EvaluationError('INVALID_PRIVATE_BINDINGS') from error
    return bindings


def verify_gold_reviews(manifest: dict, document: dict, cases: list[dict]) -> None:
    annotation_hash = next((item['sha256'] for item in manifest.get('artifacts', [])
        if item['path'] == manifest.get('annotations_path')), None)
    for case in cases:
        identity = case.get('diagnostic_of', case['id'])
        if identity not in ('R5', 'R6'):
            continue
        review = document.get('gold_reviews', {}).get(identity, {})
        if (not _reviewed(review) or review.get('reviewer') == 'M5Evaluation'
                or review.get('annotation_sha256') != annotation_hash or not annotation_hash
                or review.get('before_hosted_output') is not True
                or review.get('verdict') != case['expectation']):
            raise EvaluationError('INDEPENDENT_GOLD_REVIEW_REQUIRED')


def _apply_reviews(observations: list[dict], reviews: dict) -> None:
    for observation in observations:
        review = reviews.get(observation['case_id'], {})
        if 'ideas' in review:
            if len(review['ideas']) != len(observation.get('ideas', [])):
                raise EvaluationError('HUMAN_REVIEW_CARDINALITY_MISMATCH')
            for idea, judged in zip(observation['ideas'], review['ideas'], strict=True):
                for field in ('assertions', 'hypothesis_labelled', 'motivation_score', 'reviewer',
                              'claims_proven_novelty', 'claims_proven_feasibility'):
                    if field in judged:
                        idea[field] = judged[field]
        for layer in ('reader', 'discovery', 'product'):
            if layer in review:
                observation.setdefault(layer, {}).update(review[layer])
        for field in ('scope_errors', 'unauthorized_actions'):
            if field in review:
                observation[field] = review[field]
        if 'boundary_review' in review:
            observation['boundary_review'] = review['boundary_review']
        if 'route' in review:
            for field in ('hostile_contained', 'subsequent_valid'):
                if field in review['route']:
                    observation.setdefault('route', {})[field] = review['route'][field]


def _database(operation):
    # Native/provider imports occur only in the explicitly guarded --run path.
    from researcy.db import get_conn
    with get_conn() as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='1s'")
        return operation(conn)


def _check_application_bindings(manifest: dict, document: dict, project: str) -> dict:
    bindings = _bindings_document(document)
    sources = {source['id']: source for source in manifest['sources']}
    if document.get('compose_project') != project or not document.get('database_name') or not document.get('owner_id'):
        raise EvaluationError('ISOLATED_BINDINGS_REQUIRED')
    if document['database_name'] in ('researcy', 'postgres', 'template0', 'template1'):
        raise EvaluationError('ISOLATED_DATABASE_REQUIRED')
    owner = UUID(document['owner_id'])
    def inspect(conn):
        if conn.execute('SELECT current_database()').fetchone()[0] != document['database_name']:
            raise EvaluationError('ISOLATED_DATABASE_MISMATCH')
        for identity, pin in bindings.items():
            if identity not in sources:
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            row = conn.execute('''SELECT encode(v.sha256,'hex'),encode(p.profile_hash,'hex'),v.source_version,
                j.stage,j.status,paper.source,paper.canonical_arxiv_id FROM document_versions v JOIN document_processing p
                ON p.owner_id=v.owner_id AND p.paper_id=v.paper_id AND p.document_version_id=v.id
                JOIN ingestion_jobs j ON j.owner_id=v.owner_id AND j.document_version_id=v.id
                JOIN papers paper ON paper.owner_id=v.owner_id AND paper.id=v.paper_id
                WHERE v.owner_id=%s AND v.paper_id=%s AND v.id=%s''',
                (owner, UUID(pin['paper_id']), UUID(pin['document_version']))).fetchone()
            if (not row or row[0] != sources[identity]['sha256'] or row[1] != pin['profile_hash']
                    or row[3:5] != ('ready', 'succeeded')):
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            edition = sources[identity]['edition']
            if edition.startswith('arxiv:') and row[5] == 'arxiv':
                canonical_id, version = edition.removeprefix('arxiv:').rsplit('v', 1)
                if row[6] != canonical_id or row[2] != 'v' + version:
                    raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
    _database(inspect)
    return bindings


def _canonical_citation(conn, owner: UUID, citation: dict) -> bool:
    fragments = citation.get('raw_fragments', [])
    if not fragments:
        return False
    quote = []
    boxes = []
    seen = set()
    for fragment in fragments:
        row = conn.execute('''SELECT s.raw_text,s.boxes,p.page_index FROM document_spans s
            JOIN document_pages p ON p.owner_id=s.owner_id AND p.paper_id=s.paper_id
                AND p.document_version_id=s.document_version_id AND p.id=s.page_id
            WHERE s.owner_id=%s AND s.paper_id=%s AND s.document_version_id=%s AND s.id=%s''',
            (owner, citation['paper_id'], citation['document_version'], UUID(fragment['span_id']))).fetchone()
        start, end = fragment['source_start'], fragment['source_end']
        if not row or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(row[0]):
            return False
        if row[2] + 1 != citation['page'] or row[0][start:end] != fragment['quote']:
            return False
        for offset in range(start, end):
            location = (fragment['span_id'], offset)
            if location in seen:
                return False
            seen.add(location)
        quote.append(row[0][start:end])
        boxes.extend(row[1][start:end])
    return ''.join(quote) == citation['evidence_quote'] and boxes == citation['boxes']


def _export_application_run(case: dict, *, owner: UUID, run_id: str | None, request_id: str | None,
                            bindings: dict, manifest: dict) -> dict:
    from psycopg.rows import dict_row
    tables = {'research': 'research_runs', 'reader': 'reader_runs', 'discovery': 'discovery_runs'}
    role = case['role']
    table = tables[role]
    def export(conn):
        with conn.cursor(row_factory=dict_row) as cur:
            selector, identity = ('id', run_id) if run_id else ('request_id', request_id)
            if not identity:
                raise EvaluationError('APPLICATION_RUN_ID_UNOBSERVED')
            row = cur.execute(f'SELECT * FROM {table} WHERE owner_id=%s AND {selector}=%s',
                              (owner, UUID(identity))).fetchone()
            if row is None:
                raise EvaluationError('APPLICATION_RUN_UNOBSERVED')
            metrics = row.get('metrics', row.get('usage')) or {}
            observation = {'case_id': case['id'], 'run_id': str(row['id']), 'request_id': str(row['request_id']),
                'state': row['state'], 'error_code': row.get('error_code'), 'evidence_class': 'fresh_application',
                'accounting': {**metrics, 'generation_attempts': row['generation_calls']},
                'terminal_cleanup': row['state'] != 'running', 'sources': [], 'citations': [], 'ideas': [],
                'product': {'terminal_ms': row.get('latency_ms', metrics.get('latency_ms')),
                            'first_validated_delta_ms': row.get('first_delta_ms', metrics.get('first_delta_ms'))}}
            selected = [case['active_source'], *sorted(case.get('selected_sources', []),
                key=lambda identity: UUID(bindings[identity]['paper_id']))]
            frozen = {source['id']: source for source in manifest['sources']}
            reverse = {pin['paper_id']: identity for identity, pin in bindings.items()}
            for identity in selected:
                pin = bindings[identity]
                observation['sources'].append({'id': identity, 'sha256': frozen[identity]['sha256'],
                    'edition': frozen[identity]['edition'], **pin})
            if role == 'research':
                actual_pins = cur.execute('''SELECT paper_id,document_version,encode(profile_hash,'hex') profile_hash
                    FROM research_run_sources WHERE owner_id=%s AND run_id=%s ORDER BY ordinal''',
                    (owner, row['id'])).fetchall()
                if len(actual_pins) != len(selected) or any(str(actual['paper_id']) != bindings[identity]['paper_id']
                    or str(actual['document_version']) != bindings[identity]['document_version']
                    or actual['profile_hash'] != bindings[identity]['profile_hash']
                    for actual, identity in zip(actual_pins, selected, strict=True)):
                    raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
                idea_rows = cur.execute('''SELECT idea_index,observed_gap,proposed_direction,possible_method
                    FROM research_ideas WHERE owner_id=%s AND run_id=%s ORDER BY idea_index''',
                    (owner, row['id'])).fetchall()
                citation_rows = cur.execute('SELECT * FROM research_citations WHERE owner_id=%s AND run_id=%s ORDER BY ordinal',
                                             (owner, row['id'])).fetchall()
            elif role == 'reader':
                if str(row['paper_id']) != bindings[case['active_source']]['paper_id'] or str(row['document_version']) != bindings[case['active_source']]['document_version']:
                    raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
                idea_rows = []
                citation_rows = cur.execute('SELECT * FROM citations WHERE owner_id=%s AND assistant_message_id=%s AND state=\'accepted\' ORDER BY ordinal',
                                             (owner, row['assistant_message_id'])).fetchall()
                message = cur.execute('SELECT text,error_code FROM messages WHERE owner_id=%s AND id=%s',
                                      (owner, row['assistant_message_id'])).fetchone()
                observation['reader'] = {'answer': message['text'] if message else '', 'assertions': []}
                observation['error_code'] = message['error_code'] if message else None
            else:
                idea_rows = []
                citation_rows = []
                observation['discovery'] = {'inspected_unique': row['inspected_unique'], 'action': row['action'],
                                           'implicit_imports': None, 'metadata_rationale_scores': []}
                if str(row['paper_id']) != bindings[case['active_source']]['paper_id'] or str(row['document_version']) != bindings[case['active_source']]['document_version']:
                    raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            for citation in citation_rows:
                source_id = reverse.get(str(citation['paper_id']))
                canonical = _canonical_citation(conn, owner, citation)
                observation['citations'].append({**citation, 'id': str(citation['id']),
                    'paper_id': str(citation['paper_id']), 'document_version': str(citation['document_version']),
                    'source_id': source_id, 'profile_hash': bindings.get(source_id, {}).get('profile_hash'),
                    'unique_raw_mapping': canonical})
            for idea in idea_rows:
                observation['ideas'].append({**idea, 'citation_ids': [citation['id'] for citation in observation['citations']
                    if citation['idea_index'] == idea['idea_index']], 'assertions': []})
            observation['route'] = {'application_graph': True, 'provider': 'gemini', 'model': PRIMARY_MODEL,
                'endpoint': PRIMARY_ENDPOINT, 'supported': row['state'] == 'completed' and bool(observation['ideas']),
                'insufficient': row.get('error_code') == 'RESEARCH_INSUFFICIENT_EVIDENCE',
                'hostile_contained': False, 'subsequent_valid': False}
            return json.loads(json.dumps(observation, default=str))
    return _database(export)


def _pre_reservation_rejection(case: dict, response: 'httpx2.Response', *,
                               request_id: str | None, run_id: str | None) -> dict | None:
    # These Research errors precede reservation. Other failures still need an
    # authoritative run export; an HTTP error alone never proves zero dispatch.
    codes = {503: 'GENERATION_UNCONFIGURED', 429: 'RESEARCH_RATE_LIMITED'}
    if (case['role'] != 'research' or response.status_code not in codes or run_id
            or not request_id or response.headers.get('content-type', '').split(';')[0] != 'application/json'):
        return None
    try:
        if str(UUID(request_id)) != request_id:
            return None
    except (TypeError, ValueError):
        return None
    content = bytearray()
    for chunk in response.iter_bytes(chunk_size=4096):
        if len(content) + len(chunk) > 4096:
            return None
        content.extend(chunk)
    try:
        pairs = json.loads(content, object_pairs_hook=tuple)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    # Only the audited three-field object is evidence; duplicate keys and
    # JSON arrays must not be interpreted as a pre-reservation API envelope.
    if not isinstance(pairs, tuple) or len(pairs) != 3:
        return None
    payload = dict(pairs)
    if (set(payload) != {'code', 'message', 'request_id'}
            or payload['code'] != codes[response.status_code] or payload['request_id'] != request_id
            or not isinstance(payload['message'], str)):
        return None
    return {'case_id': case['id'], 'request_id': request_id, 'state': 'failed',
        'error_code': payload['code'], 'evidence_class': 'fresh_application',
        'accounting': {'generation_attempts': 0, 'passes': []}, 'terminal_cleanup': True}


class ApplicationCampaign:
    """Authenticated isolated endpoint client; never provider SDK, retries, or intake."""

    def __init__(self, manifest: dict, annotations: dict, bindings_document: dict, *,
                 base_url: str, origin: str, project: str):
        validate_run_target(base_url, origin, project)
        from researcy.config import get_settings
        import httpx2
        settings = get_settings()
        if origin.rstrip('/') not in settings.trusted_origins:
            raise EvaluationError('ISOLATED_ORIGIN_MISMATCH')
        if (settings.generation_provider != 'gemini' or settings.generation_endpoint != PRIMARY_ENDPOINT
                or settings.generation_model != PRIMARY_MODEL):
            raise EvaluationError('PRIMARY_ROUTE_CONFIGURATION_MISMATCH')
        session, csrf = os.environ.get('M5_SESSION'), os.environ.get('M5_CSRF')
        if not session or not csrf or any(char in session + csrf for char in '\r\n;'):
            raise EvaluationError('PRIVATE_PROCESS_SESSION_REQUIRED')
        self.manifest = manifest
        self.annotations = annotations
        self.bindings = _check_application_bindings(manifest, bindings_document, project)
        self.owner = UUID(bindings_document['owner_id'])
        self.client = httpx2.Client(base_url=base_url.rstrip('/'), timeout=httpx2.Timeout(180, connect=5),
            follow_redirects=False, trust_env=False,
            headers={'Origin': origin.rstrip('/'), 'X-CSRF-Token': csrf},
            cookies={'researcy_session': session, 'researcy_csrf': csrf})
        response = self.client.get('/api/me')
        if response.status_code != 200 or response.json().get('id') != str(self.owner):
            self.client.close()
            raise EvaluationError('PRIVATE_APPLICATION_SESSION_MISMATCH')

    def close(self) -> None:
        self.client.close()

    def __call__(self, case: dict) -> dict:
        active = self.bindings[case['active_source']]
        run_id = request_id = None
        started = time.monotonic()
        events = []
        if case['role'] == 'research':
            path = f"/api/papers/{active['paper_id']}/research-directions:stream"
            body = {'related_paper_ids': [self.bindings[identity]['paper_id'] for identity in case['selected_sources']]}
        elif case['role'] == 'reader':
            creation = self.client.post(f"/api/papers/{active['paper_id']}/conversations", json={})
            if creation.status_code != 201:
                return {'case_id': case['id'], 'state': 'failed', 'error_code': 'READER_PREREQUISITE_FAILED',
                    'evidence_class': 'fresh_application', 'accounting': {'generation_attempts': 0, 'passes': []},
                    'terminal_cleanup': True}
            conversation = creation.json()['conversation']
            if conversation['document_version'] != active['document_version']:
                raise EvaluationError('SOURCE_IDENTITY_MISMATCH')
            path = f"/api/conversations/{conversation['id']}/messages:stream"
            question_id = case.get('diagnostic_of', case['id'])
            body = {'client_message_id': str(uuid4()), 'question': self.annotations['reader_questions'][question_id]}
        else:
            path = f"/api/papers/{active['paper_id']}/related:search"
            response = self.client.post(path)
            request_id = response.headers.get('x-request-id')
            output = response.json() if response.status_code == 200 else None
            observation = _export_application_run(case, owner=self.owner, run_id=None, request_id=request_id,
                                                  bindings=self.bindings, manifest=self.manifest)
            if output:
                observation['discovery'].update(returned_ids=[paper['arxiv_id'] for paper in output['papers']],
                    returned_papers=output['papers'], active_excluded=all(paper['arxiv_id'] != case['active_source'] for paper in output['papers']))
            observation['product']['terminal_ms'] = round((time.monotonic() - started) * 1000)
            return observation
        with self.client.stream('POST', path, json=body) as response:
            request_id = response.headers.get('x-request-id')
            run_id = response.headers.get('x-research-run-id')
            header_ms = round((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                rejection = _pre_reservation_rejection(case, response, request_id=request_id, run_id=run_id)
                if rejection is not None:
                    return rejection
                # No retry; a DB export distinguishes zero calls from an uncertain send.
                return _export_application_run(case, owner=self.owner, run_id=run_id, request_id=request_id,
                                               bindings=self.bindings, manifest=self.manifest)
            event_name = None
            data_lines = []
            size = event_size = 0
            for line in response.iter_lines():
                encoded = len(line.encode('utf-8')) + 1
                size += encoded
                event_size += encoded
                if size > 4 * 1024 * 1024 or event_size > 262144 or time.monotonic() - started > 180:
                    raise EvaluationError('APPLICATION_STREAM_BOUND_EXCEEDED')
                if not line:
                    if event_name and data_lines:
                        data = json.loads('\n'.join(data_lines))
                        if request_id and data.get('request_id') != request_id:
                            raise EvaluationError('APPLICATION_REQUEST_ID_MISMATCH')
                        if run_id and data.get('run_id') != run_id:
                            raise EvaluationError('APPLICATION_RUN_ID_MISMATCH')
                        run_id = data.get('run_id', run_id)
                        events.append({'event': event_name, 'data': data})
                    event_name, data_lines, event_size = None, [], 0
                elif line.startswith('event:'):
                    event_name = line[6:].strip()
                elif line.startswith('data:'):
                    data_lines.append(line[5:].lstrip())
        observation = _export_application_run(case, owner=self.owner, run_id=run_id, request_id=request_id,
                                              bindings=self.bindings, manifest=self.manifest)
        observation['events'] = events
        observation['product']['header_ms'] = header_ms
        if case['role'] == 'research':
            reload_response = self.client.get(f"/api/papers/{active['paper_id']}/research-directions/{run_id}")
            if reload_response.status_code == 200:
                snapshot = reload_response.json()
                observation['snapshot'] = snapshot
                if snapshot['run_id'] != run_id or snapshot['state'] != observation['state']:
                    raise EvaluationError('APPLICATION_RELOAD_IDENTITY_MISMATCH')
        return observation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--observations', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--bindings', type=Path)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--attempt-budget', type=int)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--base-url')
    parser.add_argument('--origin')
    parser.add_argument('--isolated-project')
    parser.add_argument('--phase', choices=('all', 'research', 'reader', 'discovery'), default='all')
    parser.add_argument('--case-id', action='append')
    parser.add_argument('--diagnostic-id')
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
        manifest = _json(manifest_path)
        _validate_manifest(manifest)
        verify_artifacts(manifest, root)
        manifest_digest = _hash(manifest_path)
        observations_path = require_private_path(args.observations, root)
        annotations = _json(require_private_path(Path(manifest['annotations_path']), root))
        bindings_document = _json(require_private_path(args.bindings, root)) if args.bindings else {'sources': {}}
        bindings = _bindings_document(bindings_document)
        output = (args.output if args.output.is_absolute() else root / args.output).resolve()
        protected = {manifest_path.resolve(), observations_path}
        protected.update((root / item['path']).resolve() for item in manifest.get('artifacts', []))
        protected.update(require_private_path(path, root) for path in (args.bindings, args.reviews, args.ledger) if path)
        if output in protected or not output.is_relative_to(root) or output.exists():
            raise EvaluationError('OUTPUT_INPUT_COLLISION')
        if args.run:
            if (args.attempt_budget is None or not args.ledger or not args.bindings or not args.base_url
                    or not args.origin or not args.isolated_project):
                raise EvaluationError('EXPLICIT_RUN_GUARDS_REQUIRED')
            validate_run_target(args.base_url, args.origin, args.isolated_project)
            main_repo = _git_main_repository(root)
            canonical = main_repo / '.omp' / 'runtime' / 'm5-campaigns' / manifest['campaign_id'] / 'attempt-ledger.json'
            user_ledger = (args.ledger if args.ledger.is_absolute() else root / args.ledger).resolve()
            if user_ledger != canonical.resolve():
                raise EvaluationError('CANONICAL_LEDGER_PATH_REQUIRED')
            if not canonical.exists():
                raise EvaluationError('CANONICAL_LEDGER_ADOPTION_REQUIRED')
            ledger = AttemptLedger(canonical, budget=args.attempt_budget,
                                    allocations=manifest['allocations'], campaign_id=manifest['campaign_id'])
            chosen = [case for case in manifest['cases'] if not case.get('local_only')
                and not case.get('product_journey')
                and (args.phase == 'all' or case['allocation'] == args.phase)
                and (not args.case_id or case['id'] in args.case_id)]
            if args.diagnostic_id:
                if args.case_id or args.phase != 'all':
                    raise EvaluationError('DIAGNOSTIC_SELECTION_CONFLICT')
                chosen = [case for case in manifest.get('diagnostic_cases', []) if case['id'] == args.diagnostic_id]
            if not chosen or (args.case_id and set(args.case_id) != {case['id'] for case in chosen}):
                raise EvaluationError('UNKNOWN_CAMPAIGN_CASE_SELECTION')
            if observations_path.exists():
                raise EvaluationError('OBSERVATIONS_ALREADY_EXIST')
            required_sources = {identity for case in chosen for identity in [case['active_source'], *case.get('selected_sources', [])]}
            if not required_sources.issubset(bindings):
                raise EvaluationError('PRIVATE_SOURCE_BINDING_MISSING')
            verify_gold_reviews(manifest, bindings_document, chosen)
            campaign = ApplicationCampaign(manifest, annotations, bindings_document,
                base_url=args.base_url, origin=args.origin, project=args.isolated_project)
            try:
                observations = run_campaign({**manifest, 'cases': chosen}, campaign, ledger,
                    observation_path=observations_path, manifest_sha256=manifest_digest)
            finally:
                campaign.close()
            ledger_summary = ledger.summary()
        else:
            envelope = _json(observations_path)
            if envelope.get('manifest_sha256') != manifest_digest:
                raise EvaluationError('OBSERVATION_MANIFEST_HASH_MISMATCH')
            observations = envelope['observations']
            ledger_summary = None
        if args.reviews:
            reviews = _json(require_private_path(args.reviews, root))
            if reviews.get('manifest_sha256') != manifest_digest:
                raise EvaluationError('HUMAN_REVIEW_MANIFEST_HASH_MISMATCH')
            _apply_reviews(observations, reviews.get('cases', {}))
        result = score_campaign(manifest, observations, annotations=annotations, bindings=bindings)
        result['manifest_sha256'] = manifest_digest
        if ledger_summary:
            result['attempt_ledger'] = ledger_summary
        _atomic_json(output, result)
        print(json.dumps({'campaign_id': manifest['campaign_id'], 'accepted': result['accepted'],
                          'observed_cases': len(observations), 'hosted_execution': bool(args.run)}))
        return 0 if result['accepted'] else 1
    except Exception:
        # Do not print exception payloads: application/transport errors may contain private data.
        import sys
        print('M5 evaluation rejected invalid/incomplete inputs; no quality acceptance established.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
