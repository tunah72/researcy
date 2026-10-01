import hashlib
import json
from dataclasses import asdict, dataclass
from uuid import UUID, uuid5


ID_NAMESPACE = UUID("35d2b7b3-0636-5a91-9509-b798c526d8db")
QUALIFIED_MODEL_DIGEST = "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
STAGES = ("validating", "parsing", "normalizing", "chunking", "embedding", "indexing")


@dataclass(frozen=True, slots=True)
class DocumentScope:
    owner_id: UUID
    paper_id: UUID
    document_version_id: UUID


@dataclass(frozen=True, slots=True)
class Lease:
    scope: DocumentScope
    job_id: UUID
    locked_by: str
    generation: int
    stage: str


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    key: str
    sha256: bytes
    byte_count: int

    def __post_init__(self) -> None:
        if (type(self.key) is not str or not self.key or type(self.sha256) is not bytes
            or len(self.sha256) != 32 or type(self.byte_count) is not int or self.byte_count <= 0):
            raise ValueError("invalid artifact identity")


@dataclass(frozen=True, slots=True)
class StageManifest:
    stage: str
    profile_hash: bytes
    content_hash: bytes
    record_count: int
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if (self.stage not in STAGES or type(self.profile_hash) is not bytes or len(self.profile_hash) != 32
            or type(self.content_hash) is not bytes or len(self.content_hash) != 32
            or type(self.record_count) is not int or self.record_count < 0
            or type(self.artifacts) is not tuple or any(type(ref) is not ArtifactRef for ref in self.artifacts)):
            raise ValueError("invalid manifest")


@dataclass(frozen=True, slots=True)
class ProcessingProfile:
    schema_version: int = 1
    parser_package: str = "PyMuPDF"
    parser_version: str = "1.28.2"
    adapter_version: str = "geometry-v1"
    normalization_version: str = "mapped-v1"
    chunker_version: str = "section-v1"
    chunk_target: int = 1600
    chunk_maximum: int = 2400
    chunk_overlap: int = 200
    model_tag: str = "bge-m3:567m"
    model_digest: str = QUALIFIED_MODEL_DIGEST
    quantization: str = "F16"
    dimension: int = 1024
    distance: str = "cosine"
    document_prefix: str = ""
    query_prefix: str = ""
    runtime_contract: str = "ollama-api-embed-v1"
    vector_serialization: str = "float32-le-unit-v1"
    max_input_bytes: int = 25 * 1024 * 1024
    max_pages: int = 100
    max_characters: int = 2_000_000
    max_chunks: int = 10_000
    parser_cpu_seconds: int = 45
    parser_wall_seconds: int = 60
    parser_memory_bytes: int = 768 * 1024 * 1024
    parser_output_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        numbers = (self.schema_version, self.chunk_target, self.chunk_maximum, self.chunk_overlap,
            self.dimension, self.max_input_bytes, self.max_pages, self.max_characters, self.max_chunks,
            self.parser_cpu_seconds, self.parser_wall_seconds, self.parser_memory_bytes, self.parser_output_bytes)
        if any(type(value) is not int for value in numbers):
            raise ValueError("processing parameters must be integers")
        if self.schema_version != 1 or not 0 <= self.chunk_overlap <= 200 or not self.chunk_overlap < self.chunk_target <= self.chunk_maximum <= 2400:
            raise ValueError("invalid processing profile")
        if (self.parser_package, self.parser_version, self.adapter_version, self.normalization_version,
            self.chunker_version, self.model_tag, self.model_digest, self.quantization, self.dimension,
            self.distance, self.document_prefix, self.query_prefix, self.runtime_contract, self.vector_serialization) != (
            "PyMuPDF", "1.28.2", "geometry-v1", "mapped-v1", "section-v1", "bge-m3:567m",
            QUALIFIED_MODEL_DIGEST, "F16", 1024, "cosine", "", "", "ollama-api-embed-v1", "float32-le-unit-v1"):
            raise ValueError("unsupported processing contract")
        if any(value <= 0 for value in (self.max_input_bytes, self.max_pages, self.max_characters,
            self.max_chunks, self.parser_cpu_seconds, self.parser_wall_seconds,
            self.parser_memory_bytes, self.parser_output_bytes)):
            raise ValueError("invalid processing limits")

    def canonical_bytes(self) -> bytes:
        semantic = asdict(self)
        for name in ("max_input_bytes", "max_pages", "max_characters", "max_chunks",
            "parser_cpu_seconds", "parser_wall_seconds", "parser_memory_bytes", "parser_output_bytes"):
            del semantic[name]
        return json.dumps(semantic, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    @property
    def profile_hash(self) -> bytes:
        return hashlib.sha256(self.canonical_bytes()).digest()

    @property
    def index_version(self) -> bytes:
        return self.profile_hash


def deterministic_id(scope: DocumentScope, profile_hash: bytes, kind: str, position: str) -> UUID:
    return uuid5(ID_NAMESPACE, f"{scope.owner_id}/{scope.paper_id}/{scope.document_version_id}/{profile_hash.hex()}/{kind}/{position}")


class LostLease(Exception):
    pass


class StageFailure(Exception):
    def __init__(self, code: str, failure_kind: str, retryable: bool, retry_after_seconds: int = 0):
        self.code = code
        self.failure_kind = failure_kind
        self.retryable = retryable
        self.retry_after_seconds = max(0, retry_after_seconds)
        super().__init__(code)


class IntegrityFailure(StageFailure):
    def __init__(self, code: str = "PROCESSING_INTEGRITY_FAILURE"):
        super().__init__(code, "integrity", False)


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    scope: DocumentScope
    job_id: UUID
    stage: str
    status: str
    failed_stage: str | None
    error_code: str | None
    failure_kind: str | None
    retryable: bool
    retry_revision: int
    attempts: int
    cycle_attempts: int
    retry_after_seconds: int
    published: bool = False
    lease_generation: int = 0


@dataclass(frozen=True, slots=True)
class RetryResult:
    job: JobSnapshot
    accepted: bool
