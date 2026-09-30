import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Event,Thread

import pytest

from researcy.ingestion.models import LostLease,ProcessingProfile
from researcy.retrieval.embedding import EmbeddingClient
from researcy.retrieval.index import QdrantClient
from researcy.config import get_settings
from researcy.documents.artifacts import verify_artifact
from researcy.ingestion.models import ArtifactRef


@pytest.mark.parametrize('dependency',['embedding','qdrant','storage'])
def test_lease_loss_cancels_active_silent_http_request(dependency,tmp_path):
    received=Event();release=Event();cancel=Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                if dependency=='storage':
                    self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
                    self.wfile.write(b'x');self.wfile.flush()
                received.set();release.wait(3)
                if dependency!='storage':
                    self.send_response(200);self.end_headers();self.wfile.write(b'{}')
            except (BrokenPipeError,ConnectionResetError):
                pass
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    service=Thread(target=server.serve_forever);service.start()
    endpoint=f'http://127.0.0.1:{server.server_port}'
    def cancel_after_request():
        received.wait(2)
        if dependency=='storage':
            time.sleep(.1)
        cancel.set()
    canceller=Thread(target=cancel_after_request);canceller.start()
    started=time.monotonic()
    try:
        with pytest.raises(LostLease):
            if dependency=='embedding':
                EmbeddingClient(ProcessingProfile(),endpoint=endpoint,cancel=cancel).preflight()
            elif dependency=='qdrant':
                QdrantClient(endpoint=endpoint,cancel=cancel).request('GET','/collections/probe')
            else:
                settings=replace(get_settings(),storage_minio_endpoint=f'127.0.0.1:{server.server_port}',
                    storage_access_key='probe-key',storage_secret_key='probe-secret',storage_bucket='probe',storage_secure=False)
                verify_artifact(ArtifactRef('probe/object',b'h'*32,100),tmp_path/'download',settings=settings,cancel=cancel)
        assert time.monotonic()-started<1
        assert received.is_set()
        if dependency=='storage':
            assert not (tmp_path/'download').exists()
            assert not list(tmp_path.glob('.tmp.*'))
    finally:
        release.set();cancel.set();canceller.join();server.shutdown();server.server_close();service.join()
