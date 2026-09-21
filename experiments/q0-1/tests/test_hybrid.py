from __future__ import annotations

import pytest

from q0.hybrid import (
    Bm25Index,
    HybridGateEvidence,
    HybridValidationError,
    evaluate_hybrid_gate,
    evaluate_recall_gate,
    reciprocal_rank_fusion,
    tokenize_bm25,
    validate_bge_vectors,
    validate_unique_chunk_ids,
)
from q0.models import EXPECTED_CHUNK_SHA256


def test_tokenizer_is_nfkc_casefolded_unicode_alphanumeric():
    assert tokenize_bm25("Scaled DOT-product d_k café!") == [
        "scaled",
        "dot",
        "product",
        "d",
        "k",
        "café",
    ]


def test_repeated_query_terms_do_not_multiply_bm25_score():
    index = Bm25Index.from_documents({"A": "attention scaling", "B": "attention"})
    assert index.rank("attention attention") == index.rank("attention")


def test_bm25_prefers_exact_scientific_terms():
    index = Bm25Index.from_documents(
        {
            "A": "dot products grow large and softmax gradients become small",
            "B": "multi head attention representation subspaces",
        }
    )
    assert index.rank("large dot products softmax gradients")[0].chunk_id == "A"


def test_bm25_rejects_duplicate_document_ids():
    with pytest.raises(HybridValidationError, match="duplicate chunk ID"):
        Bm25Index.from_tokenized_documents([("A", ["one"]), ("A", ["two"])])


def test_rrf_uses_one_based_ranks_and_stable_tie_breaks():
    fused = reciprocal_rank_fusion(
        dense_ids=["B", "A", "C"],
        bm25_ids=["A", "B", "C"],
        k=60,
    )
    assert [hit.chunk_id for hit in fused] == ["B", "A", "C"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert [hit.rank for hit in fused] == [1, 2, 3]


def test_rrf_order_is_deterministic_when_scores_and_channel_ranks_tie():
    first = reciprocal_rank_fusion(
        dense_ids=["B", "A"],
        bm25_ids=["B", "A"],
        k=60,
    )
    second = reciprocal_rank_fusion(
        dense_ids=["B", "A"],
        bm25_ids=["B", "A"],
        k=60,
    )
    assert first == second


def test_rrf_rejects_duplicate_ids_within_a_channel():
    with pytest.raises(HybridValidationError, match="duplicate dense chunk ID"):
        reciprocal_rank_fusion(
            dense_ids=["A", "A"],
            bm25_ids=["A", "B"],
            k=60,
        )


def test_hybrid_gate_requires_six_of_eight_recall_at_five():
    assert evaluate_recall_gate(6, total=8).passed
    assert not evaluate_recall_gate(5, total=8).passed


def test_bge_vectors_are_finite_non_zero_dimension_stable_and_repeatable():
    dimension = validate_bge_vectors(
        document_vector=[0.25, -0.5, 0.75],
        query_vector=[0.5, 0.25, -0.25],
        repeated_query_vector=[0.5, 0.25, -0.25],
    )
    assert dimension == 3


@pytest.mark.parametrize(
    ("query", "repeated"),
    [
        ([0.0, 0.0], [0.0, 0.0]),
        ([float("nan"), 1.0], [float("nan"), 1.0]),
        ([0.5, 0.25], [0.5, 0.2500001]),
    ],
)
def test_bge_vector_validation_rejects_invalid_or_unstable_vectors(query, repeated):
    with pytest.raises(HybridValidationError):
        validate_bge_vectors(
            document_vector=[0.25, -0.5],
            query_vector=query,
            repeated_query_vector=repeated,
        )


def test_unique_chunk_ids_are_required():
    assert validate_unique_chunk_ids(["A", "B"]) == 2
    with pytest.raises(HybridValidationError, match="duplicate chunk ID"):
        validate_unique_chunk_ids(["A", "A"])


def passing_gate_evidence(**changes) -> HybridGateEvidence:
    values = {
        "chunk_sha256": EXPECTED_CHUNK_SHA256,
        "vector_checks_passed": True,
        "rankings_valid": True,
        "rankings_stable": True,
        "dense_recall_at_5": 0.625,
        "fused_recall_at_5": 0.75,
        "warm_latencies_seconds": tuple(0.2 + index / 1000 for index in range(24)),
        "total_indexing_seconds": 42.0,
        "golden_case_in_top_5": True,
        "golden_provenance_complete": True,
        "failure_reasons": (),
    }
    values.update(changes)
    return HybridGateEvidence(**values)


def test_hybrid_gate_accepts_complete_passing_evidence():
    decision = evaluate_hybrid_gate(passing_gate_evidence())
    assert decision.passed
    assert decision.failure_reasons == ()


def test_hybrid_gate_requires_exactly_twenty_four_warm_samples():
    decision = evaluate_hybrid_gate(
        passing_gate_evidence(warm_latencies_seconds=tuple(0.2 for _ in range(23)))
    )
    assert not decision.passed
    assert not decision.threshold_outcomes["warm_sample_count"].passed


def test_hybrid_gate_requires_golden_case_in_fused_top_five():
    decision = evaluate_hybrid_gate(passing_gate_evidence(golden_case_in_top_5=False))
    assert not decision.passed
    assert not decision.threshold_outcomes["golden_case"].passed


def test_hybrid_gate_rejects_changed_chunk_hash():
    decision = evaluate_hybrid_gate(passing_gate_evidence(chunk_sha256="f" * 64))
    assert not decision.passed
    assert not decision.threshold_outcomes["chunk_identity"].passed
