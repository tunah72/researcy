from uuid import UUID,uuid4

import pytest

from test_conversations import reader_source


def test_rrf_overlap_outranks_single_branch_top_with_stable_tie():
    from researcy.retrieval.hybrid import fuse_ranks
    a,b,c = UUID(int=1),UUID(int=2),UUID(int=3)
    assert fuse_ranks([a,b],[c,b])==(b,a,c)
    assert fuse_ranks([c],[a])==(a,c)


def test_context_drops_whole_lower_ranked_chunks_and_retains_complete_provenance():
    from researcy.retrieval.hybrid import pack_evidence
    from researcy.retrieval.repository import EvidenceHit
    from researcy.ingestion.models import DocumentScope
    from researcy.documents.canonical import EvidenceLocation
    scope = DocumentScope(uuid4(),uuid4(),uuid4())
    def hit(index,length):
        raw = str(index)*length
        location = EvidenceLocation(uuid4(),0,0,length,raw,((1.,2.,3.,4.),)*length)
        return EvidenceHit(scope,UUID(int=index),uuid4(),raw,1.,(location,))
    first,second,third = hit(1,7000),hit(2,6000),hit(3,3000)
    packed = pack_evidence((first,second,third))
    assert tuple(item.chunk_id for item in packed)==(first.chunk_id,third.chunk_id)
    assert packed[0].locations==first.locations and packed[1].locations==third.locations
    ranked = (first,second,hit(4,6000),hit(5,6000),hit(6,6000),third)
    assert tuple(item.chunk_id for item in pack_evidence(ranked))==(first.chunk_id,)


def test_lexical_search_stays_in_pinned_owner_version_and_empty_lexemes_are_empty(reader_source,monkeypatch):
    from researcy.retrieval.repository import load_ready_document
    from researcy.retrieval.hybrid import search_lexical
    source = reader_source
    document = source['document']
    from researcy.retrieval import hybrid,repository
    monkeypatch.setattr(hybrid,'get_conn',source['get_conn'])
    monkeypatch.setattr(repository,'get_conn',source['get_conn'])
    hits = search_lexical(document,'Owned exact source')
    assert [hit.chunk_id for hit in hits]==[source['chunks'][0].id]
    assert all(hit.scope==source['scope'] for hit in hits)
    assert search_lexical(document,'--- !!!')==[]
    from test_owned_retrieval import DeterministicEmbeddingClient
    from researcy.retrieval.hybrid import retrieve_same_paper
    monkeypatch.setattr(repository,'EmbeddingClient',DeterministicEmbeddingClient)
    fused = retrieve_same_paper(document,'Owned exact source')
    assert fused[0].score==pytest.approx(2/61)
    from researcy.errors import APIError
    with pytest.raises(APIError) as caught:
        load_ready_document(source['conn'],uuid4(),source['scope'].paper_id,source['scope'].document_version_id)
    assert caught.value.status_code==404


def test_lexical_postgres_disconnect_is_a_safe_dependency_failure(reader_source,monkeypatch):
    from contextlib import contextmanager
    import socket
    import psycopg
    from researcy.retrieval import hybrid
    from researcy.errors import APIError
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1',0))
        port = unavailable.getsockname()[1]
        @contextmanager
        def failed_database():
            with psycopg.connect(host='127.0.0.1',port=port,dbname='unavailable',connect_timeout=1) as conn:
                yield conn
        monkeypatch.setattr(hybrid,'get_conn',failed_database)
        with pytest.raises(APIError) as caught:
            hybrid.search_lexical(reader_source['document'],'source')
    assert caught.value.status_code==503 and caught.value.code=='DEPENDENCY_UNAVAILABLE'
    assert '127.0.0.1' not in caught.value.message
