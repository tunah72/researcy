import hashlib
import os
from pathlib import Path
from threading import Event
import time
import tempfile

from researcy.ingestion.models import StageFailure, IntegrityFailure, LostLease
from .models import SandboxLimits, ArtifactSummary, read_parser_records, decode_parser_record
from .sandbox import run_pdf_child, SandboxError


_ERRORS = {
    'PDF_TOO_LARGE':'resource_limit','PDF_TOO_MANY_PAGES':'resource_limit',
    'PDF_ENCRYPTED':'unsupported','PDF_INVALID':'unsupported','PDF_NO_TEXT':'unsupported',
    'PDF_PARSE_RESOURCE_LIMIT':'resource_limit','PDF_PARSE_TIMEOUT':'resource_limit',
    'PDF_PARSE_GEOMETRY_INVALID':'unsupported','PDF_SANDBOX_UNAVAILABLE':'temporary',
}


def _failure(code: str) -> StageFailure:
    kind = _ERRORS.get(code,'integrity')
    return StageFailure(code if code in _ERRORS else 'PARSER_OUTPUT_INVALID',kind,kind=='temporary')


def parse_pdf(source: Path, output: Path, limits: SandboxLimits, *, cancel: Event | None=None, deadline: float | None=None) -> ArtifactSummary:
    """Publish only a complete validated geometry stream, never partial child output."""
    if output.exists():
        raise IntegrityFailure('PARSER_OUTPUT_CONFLICT')
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='parser-') as directory:
        candidate=Path(directory)/'records.jsonl'
        try:
            run_pdf_child('parse',source,candidate,limits,cancel=cancel,deadline=deadline)
        except SandboxError as error:
            raise _failure(error.code) from None
        # An error may follow streamed records, so inspect every bounded line before
        # decoding the typed stream. Never expose an arbitrary child error string.
        try:
            with candidate.open('rb') as data:
                total=0
                while True:
                    if cancel is not None and cancel.is_set():
                        raise LostLease()
                    if deadline is not None and time.monotonic()>=deadline:
                        raise _failure('PDF_PARSE_TIMEOUT')
                    line=data.readline(min(limits.output_bytes,2*1024*1024)+1)
                    if not line:
                        break
                    total+=len(line)
                    if total>limits.output_bytes or len(line)>2*1024*1024:
                        raise IntegrityFailure('PARSER_OUTPUT_INVALID')
                    record=decode_parser_record(line)
                    if type(record) is dict and 'error' in record:
                        if set(record)!={'error'} or type(record['error']) is not str:
                            raise IntegrityFailure('PARSER_OUTPUT_INVALID')
                        raise _failure(record['error'])
            pages=blocks=spans=characters=0
            for record in read_parser_records(candidate,limits):
                if cancel is not None and cancel.is_set():
                    raise LostLease()
                if deadline is not None and time.monotonic()>=deadline:
                    raise _failure('PDF_PARSE_TIMEOUT')
                if record.kind=='page': pages+=1
                elif record.kind=='block': blocks+=1
                else:
                    spans+=1;characters+=len(record.raw_text)
            digest=hashlib.sha256();size=0
            with candidate.open('rb') as data:
                while chunk:=data.read(64*1024):
                    if cancel is not None and cancel.is_set():
                        raise LostLease()
                    if deadline is not None and time.monotonic()>=deadline:
                        raise _failure('PDF_PARSE_TIMEOUT')
                    digest.update(chunk);size+=len(chunk)
            summary=ArtifactSummary(pages,blocks,spans,characters,digest.digest(),size)
            # The worker owns this private scratch path; child and client cannot
            # access it. Publish validated bytes by same-filesystem atomic rename.
            if cancel is not None and cancel.is_set():
                raise LostLease()
            os.rename(candidate,output)
            return summary
        except (ValueError,TypeError,UnicodeError,OSError,RecursionError,OverflowError):
            raise IntegrityFailure('PARSER_OUTPUT_INVALID') from None
