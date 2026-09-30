import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

from researcy.ingestion.models import LostLease

from .models import SandboxLimits


_CHILD = Path(__file__).with_name("parser_child.py")
_RUNTIME = Path(sys.prefix)
_READY = b"RESEARCY_PDF_CHILD_READY\n"
# Limits precede importing the parser or opening untrusted input.
_BOOTSTRAP = '''import os,resource,runpy,sys
cpu,memory,files,processes,output=map(int,sys.argv[1:6])
if os.geteuid()==0: raise RuntimeError("unprivileged parser required")
for kind,value in ((resource.RLIMIT_CPU,cpu),(resource.RLIMIT_AS,memory),(resource.RLIMIT_NOFILE,files),(resource.RLIMIT_NPROC,processes),(resource.RLIMIT_FSIZE,output),(resource.RLIMIT_CORE,0)):
    resource.setrlimit(kind,(value,value))
os.write(1,b"RESEARCY_PDF_CHILD_READY\\n")
sys.argv=sys.argv[6:]
runpy.run_path('/parser_child.py',run_name='__main__')
'''


class SandboxError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def run_pdf_child(mode: str, source: Path, output: Path, limits: SandboxLimits, *, cancel: Event | None=None, deadline: float | None=None) -> None:
    """Only publish complete bounded output; namespace failure is fail-closed."""
    if mode not in ("screen","parse"):
        raise ValueError("unsupported parser mode")
    if sys.platform != "linux" or os.geteuid() == 0:
        raise SandboxError("PDF_SANDBOX_UNAVAILABLE")
    prefix = "PDF_SCREEN" if mode=="screen" else "PDF_PARSE"
    process = None
    succeeded = False
    output_created = False
    deadline = min(deadline if deadline is not None else float('inf'),time.monotonic()+limits.wall_seconds)
    if cancel is not None and cancel.is_set():
        raise LostLease()
    try:
        with source.open("rb") as original:
            fd = original.fileno()
            if os.fstat(fd).st_size > limits.input_bytes:
                raise SandboxError("PDF_TOO_LARGE")
            command = [
                "bwrap", "--unshare-user", "--unshare-pid", "--unshare-net",
                "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                "--ro-bind", "/usr/local", "/usr/local",
                "--ro-bind", "/usr/lib", "/usr/lib", "--symlink", "usr/lib", "/lib",
                "--ro-bind", str(_RUNTIME), "/runtime",
                "--ro-bind", str(_CHILD), "/parser_child.py",
                "--ro-bind", f"/proc/self/fd/{fd}", "/input/document.pdf",
                "--size", str(limits.memory_bytes), "--tmpfs", "/tmp",
                "--dir", "/dev", "--ro-bind", "/dev/null", "/dev/null",
                "--ro-bind", "/dev/urandom", "/dev/urandom",
                "--chdir", "/tmp", "--clearenv",
                "--setenv", "PATH", "/runtime/bin",
                "--setenv", "LD_LIBRARY_PATH", "/usr/local/lib",
                "/runtime/bin/python", "-I", "-c", _BOOTSTRAP,
                str(limits.cpu_seconds), str(limits.memory_bytes),
                str(limits.open_files), str(limits.processes), str(limits.output_bytes),
                "/parser_child.py", mode, str(limits.pages), str(limits.input_bytes), str(limits.characters),
            ]
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, pass_fds=(fd,), close_fds=True,
                env={"PATH": "/usr/bin:/bin"}, start_new_session=True,
            )
            assert process.stdout is not None
            os.set_blocking(process.stdout.fileno(), False)
            with selectors.DefaultSelector() as selector, output.open("xb") as target:
                output_created = True
                selector.register(process.stdout, selectors.EVENT_READ)
                count = 0
                preamble = b""
                while selector.get_map():
                    if cancel is not None and cancel.is_set():
                        raise LostLease()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SandboxError(f"{prefix}_TIMEOUT")
                    for key, _ in selector.select(min(remaining,.1)):
                        data = os.read(key.fd, 64 * 1024)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        if preamble != _READY:
                            needed = len(_READY) - len(preamble)
                            preamble += data[:needed]
                            data = data[needed:]
                            if not _READY.startswith(preamble):
                                raise SandboxError("PDF_SANDBOX_UNAVAILABLE")
                            if preamble != _READY:
                                continue
                        count += len(data)
                        if count > limits.output_bytes:
                            raise SandboxError(f"{prefix}_RESOURCE_LIMIT")
                        target.write(data)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SandboxError(f"{prefix}_TIMEOUT")
                if preamble != _READY:
                    raise SandboxError("PDF_SANDBOX_UNAVAILABLE")
                while process.poll() is None:
                    if cancel is not None and cancel.is_set():
                        raise LostLease()
                    remaining=deadline-time.monotonic()
                    if remaining<=0:
                        raise SandboxError(f"{prefix}_TIMEOUT")
                    try:
                        process.wait(timeout=min(remaining,.1))
                    except subprocess.TimeoutExpired:
                        continue
                if cancel is not None and cancel.is_set():
                    raise LostLease()
                if process.returncode != 0 or count == 0:
                    raise SandboxError(f"{prefix}_RESOURCE_LIMIT")
            succeeded = True
    except subprocess.TimeoutExpired:
        raise SandboxError(f"{prefix}_TIMEOUT") from None
    except OSError:
        raise SandboxError("PDF_SANDBOX_UNAVAILABLE") from None
    finally:
        if process is not None:
            # Reap the launcher; killing PID namespace init also kills descendants.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
        if output_created and not succeeded:
            output.unlink(missing_ok=True)
