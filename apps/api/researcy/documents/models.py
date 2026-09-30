from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    cpu_seconds: int = 10
    wall_seconds: float = 15
    memory_bytes: int = 256 * 1024 * 1024
    output_bytes: int = 64 * 1024
    input_bytes: int = 25 * 1024 * 1024
    pages: int = 100
    open_files: int = 64
    processes: int = 16

    def __post_init__(self) -> None:
        if any(value <= 0 for value in (
            self.cpu_seconds, self.wall_seconds, self.memory_bytes,
            self.output_bytes, self.input_bytes, self.pages,
            self.open_files, self.processes,
        )):
            raise ValueError("sandbox limits must be positive")
