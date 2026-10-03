import ijson.backends.python as backend
from ijson.common import JSONError,ObjectBuilder
from pydantic import ValidationError

from researcy.generation.models import AnswerAction,Claim,InvalidModelOutput,SearchAction


_MAP_KEYS = {
    '':frozenset(('next_action','claims','refusal','query')),
    'claims.item':frozenset(('text','citations')),
    'claims.item.citations.item':frozenset(('source_ref','evidence_quote')),
}
_ARRAYS = frozenset(('claims','claims.item.citations'))
_STRING_LIMITS = {'claims.item.text':2000,'claims.item.citations.item.source_ref':64,
    'claims.item.citations.item.evidence_quote':2000,'query':2400}


class ClaimParser:
    """Finite JSON grammar over the supported pure-Python incremental ijson API."""

    MAX_BYTES = 262144
    MAX_CLAIMS = 12
    MAX_TOTAL_CITATIONS = 24

    def __init__(self) -> None:
        self._action: str | None = None
        self._bytes = 0
        self._closed = False
        self._root_done = False
        self._root_keys: set[str] = set()
        self._maps: list[tuple[str,set[str]]] = []
        self._builder: ObjectBuilder | None = None
        self._claims: list[Claim] = []
        self._emitted = 0
        self._new: list[Claim] = []
        self._citations = 0
        self._claim_citations = 0
        self._refusal: str | None = None
        self._query: str | None = None
        self._coro = backend.parse_coro(self._sink())

    @property
    def action(self) -> str | None:
        return self._action

    @backend.utils.coroutine
    def _sink(self):
        while True:
            prefix,event,value = yield
            self._event(prefix,event,value)

    def _emit(self) -> None:
        if self._action=='answer':
            self._new.extend(self._claims[self._emitted:])
            self._emitted = len(self._claims)

    def _event(self,prefix: str,event: str,value: object) -> None:
        if self._root_done:
            raise InvalidModelOutput('Additional model output data.')
        if event=='start_map':
            if prefix not in _MAP_KEYS:
                raise InvalidModelOutput('Invalid model output shape.')
            keys = self._root_keys if prefix=='' else set()
            self._maps.append((prefix,keys))
        elif event=='map_key':
            if not self._maps or self._maps[-1][0]!=prefix or value not in _MAP_KEYS[prefix]:
                raise InvalidModelOutput('Invalid model output field.')
            keys = self._maps[-1][1]
            if value in keys:
                raise InvalidModelOutput('Duplicate model output field.')
            keys.add(value)
        elif event=='end_map':
            if not self._maps or self._maps[-1][0]!=prefix:
                raise InvalidModelOutput('Invalid model output shape.')
            self._maps.pop()
            if prefix=='':
                self._root_done = True
        elif event in ('start_array','end_array'):
            if prefix not in _ARRAYS:
                raise InvalidModelOutput('Invalid model output shape.')
        elif prefix=='next_action':
            if event!='string' or value not in ('answer','search_same_paper'):
                raise InvalidModelOutput('Unsupported model action.')
            self._action = value
            self._emit()
        elif prefix=='refusal':
            if event=='null':
                self._refusal = None
            elif event=='string' and value.strip() and not self._claims:
                self._refusal = value
            else:
                raise InvalidModelOutput('Invalid refusal.')
        elif prefix in _STRING_LIMITS:
            if event!='string' or not value.strip() or len(value)>_STRING_LIMITS[prefix]:
                raise InvalidModelOutput('Invalid model output content.')
            if prefix=='query':
                self._query = value
        else:
            raise InvalidModelOutput('Invalid model output shape.')

        if self._action=='search_same_paper' and self._root_keys & {'claims','refusal'}:
            raise InvalidModelOutput('Invalid search envelope.')
        if self._action=='answer' and 'query' in self._root_keys:
            raise InvalidModelOutput('Invalid answer envelope.')
        if prefix=='claims.item' and event=='start_map':
            if self._refusal is not None or len(self._claims)>=self.MAX_CLAIMS:
                raise InvalidModelOutput('Invalid claim count or refusal.')
            self._claim_citations = 0
            self._builder = ObjectBuilder()
        if prefix=='claims.item.citations.item' and event=='start_map':
            self._claim_citations += 1
            if self._claim_citations>4:
                raise InvalidModelOutput('Invalid claim citation count.')
        if self._builder is not None:
            self._builder.event(event,value)
            if prefix=='claims.item' and event=='end_map':
                try:
                    claim = Claim.model_validate(self._builder.value)
                except ValidationError:
                    raise InvalidModelOutput('Invalid claim.') from None
                self._builder = None
                self._citations += len(claim.citations)
                if self._citations>self.MAX_TOTAL_CITATIONS:
                    raise InvalidModelOutput('Invalid total citation count.')
                self._claims.append(claim)
                self._emit()

    def feed(self,raw: bytes) -> tuple[Claim,...]:
        if self._closed or not isinstance(raw,(bytes,bytearray)):
            raise InvalidModelOutput('Invalid parser input or lifecycle.')
        self._bytes += len(raw)
        if self._bytes>self.MAX_BYTES:
            self.close()
            raise InvalidModelOutput('Model output exceeds the size limit.')
        if self._root_done:
            if raw.strip():
                self.close()
                raise InvalidModelOutput('Additional model output data.')
            return ()
        self._new = []
        try:
            self._coro.send(raw)
        except InvalidModelOutput:
            self.close()
            raise
        except (JSONError,UnicodeError,ValueError,RecursionError):
            self.close()
            raise InvalidModelOutput('Invalid model output JSON.') from None
        return tuple(self._new)

    def finish(self) -> None:
        if self._closed:
            raise InvalidModelOutput('Invalid parser lifecycle.')
        self._closed = True
        try:
            self._coro.close()
            if not self._root_done or self._builder is not None:
                raise InvalidModelOutput('Incomplete model output.')
            if self._action=='answer' and self._root_keys=={'next_action','claims','refusal'}:
                AnswerAction(next_action='answer',claims=tuple(self._claims),refusal=self._refusal)
            elif self._action=='search_same_paper' and self._root_keys=={'next_action','query'}:
                SearchAction(next_action='search_same_paper',query=self._query)
            else:
                raise InvalidModelOutput('Invalid model output envelope.')
        except (JSONError,UnicodeError,ValueError,RecursionError,ValidationError):
            raise InvalidModelOutput('Invalid model output JSON or envelope.') from None

    def close(self) -> None:
        """Abandon a failed/interrupted stream without treating its partial JSON as complete."""
        if not self._closed:
            self._closed = True
            try:
                self._coro.close()
            except (JSONError,UnicodeError,ValueError,InvalidModelOutput):
                pass
        self._builder = None
