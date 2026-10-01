import importlib
import json
import os
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux namespace containment is verified in the deployed test image")


def _sandbox():
    try:
        return importlib.import_module("researcy.documents.sandbox")
    except ModuleNotFoundError:
        pytest.fail("PDF sandbox is missing; untrusted children are not contained")


def _run_probe(tmp_path, monkeypatch, script, **limits):
    sandbox = _sandbox()
    child = tmp_path / "probe.py"
    child.write_text(script)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    output = tmp_path / "output.json"
    monkeypatch.setattr(sandbox, "_CHILD", child)
    sandbox.run_pdf_child("screen", source, output, sandbox.SandboxLimits(**limits))
    return output


def test_child_cannot_read_service_secret_or_parent_files(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_LOOKUP_KEY", "sandbox-test-secret")
    marker = tmp_path / "private-marker"
    marker.write_text("private-marker")
    script = f'''import os,json
try:
    open({str(marker)!r}).read()
    file_visible=True
except OSError:
    file_visible=False
print(json.dumps({{"secret":os.getenv("SESSION_LOOKUP_KEY"),"file_visible":file_visible,"proc_visible":os.path.exists("/proc"),"uid":os.getuid()}}))
'''
    result = json.loads(_run_probe(tmp_path, monkeypatch, script).read_text())
    assert result == {"secret": None, "file_visible": False, "proc_visible": False, "uid": 65534}


def test_child_writes_only_to_bounded_scratch_mount(tmp_path, monkeypatch):
    script = '''import json
results={}
for path in ("/escape", "/tmp/scratch"):
    try:
        with open(path,"w") as target:
            target.write("bounded-test-marker")
        results[path]=True
    except OSError:
        results[path]=False
print(json.dumps(results))
'''
    assert json.loads(_run_probe(tmp_path, monkeypatch, script).read_text()) == {"/escape": False, "/tmp/scratch": True}


def test_child_cannot_connect_to_parent_network(tmp_path, monkeypatch):
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        script = f'''import socket,json
s=socket.socket()
s.settimeout(0.2)
try:
    s.connect(("127.0.0.1",{port}))
    reachable=True
except OSError:
    reachable=False
print(json.dumps({{"reachable":reachable}}))
'''
        assert json.loads(_run_probe(tmp_path, monkeypatch, script).read_text()) == {"reachable": False}


@pytest.mark.parametrize("script,limits,code", [
    ("while True: pass", {"cpu_seconds": 1, "wall_seconds": 6}, "PDF_SCREEN_RESOURCE_LIMIT"),
    ("import time; time.sleep(30)", {"wall_seconds": 0.3}, "PDF_SCREEN_TIMEOUT"),
    ("import os\nwhile True: os.write(1,b'x'*65536)", {"output_bytes": 1024}, "PDF_SCREEN_RESOURCE_LIMIT"),
    ("data=bytearray(1024*1024*1024)", {"memory_bytes": 64*1024*1024}, "PDF_SCREEN_RESOURCE_LIMIT"),
])
def test_resource_exhaustion_removes_partial_output(tmp_path, monkeypatch, script, limits, code):
    import time

    sandbox = _sandbox()
    started = time.monotonic()
    with pytest.raises(sandbox.SandboxError) as error:
        _run_probe(tmp_path, monkeypatch, script, **limits)
    assert error.value.code == code
    assert time.monotonic() - started < limits.get("wall_seconds", 15) + 2
    assert not (tmp_path / "output.json").exists()


def test_process_limit_denies_fork_bomb(tmp_path, monkeypatch):
    script = '''import os,json,time
children=[]
try:
    for _ in range(40):
        pid=os.fork()
        if pid==0:
            time.sleep(10)
            os._exit(0)
        children.append(pid)
    denied=False
except OSError:
    denied=True
finally:
    for pid in children:
        os.kill(pid,9)
        os.waitpid(pid,0)
print(json.dumps({"denied":denied}))
'''
    assert json.loads(_run_probe(tmp_path, monkeypatch, script).read_text()) == {"denied": True}


@pytest.mark.parametrize("payload", [
    {"pages": True, "title": None, "warning": False},
    {"pages": 101, "title": None, "warning": False},
    {"pages": 1, "title": None, "warning": False, "object_key": "untrusted"},
    {"error": {"provider_message": "untrusted"}},
])
def test_screening_rejects_malformed_child_response(tmp_path, monkeypatch, payload):
    from researcy.papers.screening import screen_pdf
    from researcy.errors import APIError

    sandbox = _sandbox()
    child = tmp_path / "malformed.py"
    child.write_text(f"print({json.dumps(payload)!r})")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(sandbox, "_CHILD", child)
    with pytest.raises(APIError) as error:
        screen_pdf(source, "application/pdf")
    assert error.value.status_code == 422
    assert error.value.code == "PDF_SCREEN_RESOURCE_LIMIT"


def test_denied_namespace_setup_returns_safe_unavailable(tmp_path, monkeypatch):
    from researcy.papers.screening import screen_pdf
    from researcy.errors import APIError

    sandbox = _sandbox()
    real_popen = sandbox.subprocess.Popen

    def deny_namespace(command, **kwargs):
        # A real namespace request denied by the deployed clone-flags filter.
        return real_popen(command[:1] + ["--unshare-uts"] + command[1:], **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "Popen", deny_namespace)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    with pytest.raises(APIError) as error:
        screen_pdf(source, "application/pdf")
    assert error.value.status_code == 503
    assert error.value.code == "PDF_SANDBOX_UNAVAILABLE"


def test_wall_timeout_terminates_and_reaps_descendants(tmp_path, monkeypatch):
    import threading
    import time

    sandbox = _sandbox()
    real_popen = sandbox.subprocess.Popen
    descendants = set()
    observed = threading.Event()
    monitors = []

    def monitor(pid):
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            pending = [pid]
            current = set()
            while pending:
                parent = pending.pop()
                try:
                    children = (Path("/proc") / str(parent) / "task" / str(parent) / "children").read_text()
                except FileNotFoundError:
                    continue
                for child in map(int, children.split()):
                    if child not in current:
                        current.add(child)
                        pending.append(child)
            if len(current) >= 3:
                descendants.update(current)
                observed.set()
                return
            observed.wait(0.01)

    def launch(command, **kwargs):
        process = real_popen(command, **kwargs)
        thread = threading.Thread(target=monitor, args=(process.pid,))
        thread.start()
        monitors.append(thread)
        return process

    monkeypatch.setattr(sandbox.subprocess, "Popen", launch)
    started = time.monotonic()
    try:
        with pytest.raises(sandbox.SandboxError) as error:
            _run_probe(tmp_path, monkeypatch, "import os,time\nos.fork()\ntime.sleep(30)", wall_seconds=2)
    finally:
        for thread in monitors:
            thread.join(timeout=2)
    assert observed.is_set(), "probe must observe actual live descendants"
    assert error.value.code == "PDF_SCREEN_TIMEOUT"
    assert time.monotonic() - started < 5
    deadline = time.monotonic() + 1
    while any((Path("/proc") / str(pid)).exists() for pid in descendants) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert all(not (Path("/proc") / str(pid)).exists() for pid in descendants)


def test_memory_limit_denies_allocation_without_cgroup_oom(tmp_path, monkeypatch):
    script = '''import json
try:
    allocation=bytearray(128*1024*1024)
    denied=False
except MemoryError:
    denied=True
print(json.dumps({"allocation_denied":denied}))
'''
    assert json.loads(_run_probe(tmp_path, monkeypatch, script, memory_bytes=64*1024*1024).read_text()) == {"allocation_denied": True}


def test_file_and_descriptor_limits_are_enforced(tmp_path, monkeypatch):
    script = '''import os,json
handles=[]
try:
    for _ in range(100):
        handles.append(open('/dev/null','rb'))
    descriptors_denied=False
except OSError:
    descriptors_denied=True
finally:
    for handle in handles: handle.close()
try:
    with open('/tmp/flood','wb',buffering=0) as file:
        file.write(b'x'*2048)
        file.write(b'x'*2048)
    file_denied=False
except OSError:
    file_denied=True
print(json.dumps({"descriptors_denied":descriptors_denied,"file_denied":file_denied}))
'''
    assert json.loads(_run_probe(tmp_path, monkeypatch, script, output_bytes=1024).read_text()) == {"descriptors_denied": True, "file_denied": True}

def test_lease_cancellation_reaps_silent_child_and_removes_partial_output(tmp_path,monkeypatch):
    import time
    from threading import Event,Timer
    from researcy.ingestion.models import LostLease

    sandbox=_sandbox();child=tmp_path/'slow.py';child.write_text('import time; time.sleep(30)')
    source=tmp_path/'source.pdf';source.write_bytes(b'%PDF-1.7\n');output=tmp_path/'partial.json'
    monkeypatch.setattr(sandbox,'_CHILD',child)
    cancel=Event();timer=Timer(.2,cancel.set);timer.start();started=time.monotonic()
    try:
        with pytest.raises(LostLease):
            sandbox.run_pdf_child('screen',source,output,sandbox.SandboxLimits(),cancel=cancel)
    finally:
        timer.cancel();timer.join()
    assert time.monotonic()-started<2
    assert not output.exists()
