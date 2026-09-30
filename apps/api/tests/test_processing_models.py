from dataclasses import replace

import pytest

from researcy.ingestion.models import ProcessingProfile, ArtifactRef, StageManifest


def test_resource_limits_do_not_assign_a_different_semantic_index():
    profile = ProcessingProfile()
    operational = replace(profile, parser_cpu_seconds=30, parser_wall_seconds=40,
        parser_memory_bytes=512*1024*1024, parser_output_bytes=64*1024*1024,
        max_input_bytes=10*1024*1024, max_pages=50, max_characters=1000000, max_chunks=5000)
    assert operational.index_version == profile.index_version
    assert replace(profile, chunk_target=1500).index_version != profile.index_version


@pytest.mark.parametrize('changes', [
    {'distance':'dot'}, {'dimension':1}, {'vector_serialization':'unknown'},
    {'parser_package':''}, {'model_digest':'0'*64}, {'quantization':'Q4'},
    {'chunk_target':True}, {'chunk_maximum':2400.0}, {'parser_wall_seconds':True},
])
def test_unsupported_profile_cannot_be_sealed(changes):
    with pytest.raises(ValueError):
        ProcessingProfile(**changes)


@pytest.mark.parametrize('hash_value', [bytearray(32), 'x'*32])
def test_mutable_or_nonbinary_manifest_identity_is_rejected(hash_value):
    with pytest.raises(ValueError):
        ArtifactRef('test/artifact', hash_value, 1)
    with pytest.raises(ValueError):
        StageManifest('validating', hash_value, b'c'*32, 1, ())


def test_manifest_cannot_hold_a_mutable_artifact_selection():
    with pytest.raises(ValueError):
        StageManifest('parsing', b'p'*32, b'c'*32, 1, [])
    with pytest.raises(ValueError):
        StageManifest('parsing', b'p'*32, b'c'*32, 1, ('not-an-artifact',))
