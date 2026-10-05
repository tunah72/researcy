import json
import ijson.backends.python as backend
from ijson.common import JSONError,ObjectBuilder
from pydantic import ValidationError

from researcy.generation.models import GenerationFailure,InvalidModelOutput,_reject_constant,_reject_duplicate_keys
from researcy.research.models import ProposedIdea,ResearchOutput,safe_text

_MAP_KEYS={
    '':frozenset(('next_action','ideas','refusal')),
    'ideas.item':frozenset(('observed_gap','proposed_direction','possible_method','premise_citations')),
    'ideas.item.premise_citations.item':frozenset(('source_ref','evidence_quote')),
}
_ARRAYS=frozenset(('ideas','ideas.item.premise_citations'))
_STRING_LIMITS={'ideas.item.observed_gap':1200,'ideas.item.proposed_direction':1200,
    'ideas.item.possible_method':1200,'ideas.item.premise_citations.item.source_ref':64,
    'ideas.item.premise_citations.item.evidence_quote':2000}


def validate_repair_protocol(raw: bytearray) -> None:
    """A content error must not conceal a later forbidden field or action."""
    try:
        value=json.loads(raw,object_pairs_hook=_reject_duplicate_keys,parse_constant=_reject_constant)
    except (ValueError,UnicodeError,RecursionError):
        raise InvalidModelOutput('Unverifiable model protocol.') from None
    if not isinstance(value,dict):raise InvalidModelOutput('Invalid model output shape.')
    if value.get('next_action')!='directions':raise GenerationFailure('GENERATION_INVALID_ACTION')
    def check(item,prefix):
        if isinstance(item,dict):
            if prefix not in _MAP_KEYS or not item.keys()<=_MAP_KEYS[prefix]:
                raise GenerationFailure('GENERATION_INVALID_ACTION')
            for key,child in item.items():check(child,prefix+'.'+key if prefix else key)
        elif isinstance(item,list):
            if prefix not in _ARRAYS:raise InvalidModelOutput('Invalid model output shape.')
            for child in item:check(child,prefix+'.item')
    try:check(value,'')
    except RecursionError:raise InvalidModelOutput('Invalid model output shape.') from None


class IdeaParser:
    """Emit complete ideas only when both envelope discriminants permit supported output."""
    MAX_BYTES=262144

    def __init__(self) -> None:
        self.action: str | None=None
        self.unsupported=False
        self._bytes=0
        self._closed=False
        self._root_done=False
        self._root_keys: set[str]=set()
        self._maps: list[tuple[str,set[str]]]=[]
        self._builder: ObjectBuilder | None=None
        self._ideas: list[ProposedIdea]=[]
        self._emitted=0
        self._new: list[ProposedIdea]=[]
        self._refusal_known=False
        self._refusal: str | None=None
        self._citations=0
        self._coro=backend.parse_coro(self._sink())

    @backend.utils.coroutine
    def _sink(self):
        while True:
            prefix,event,value=yield
            self._event(prefix,event,value)

    def _emit(self) -> None:
        if self.action=='directions' and self._refusal_known and self._refusal is None:
            self._new.extend(self._ideas[self._emitted:])
            self._emitted=len(self._ideas)

    def _event(self,prefix: str,event: str,value: object) -> None:
        if self._root_done:raise InvalidModelOutput('Additional model output data.')
        if event=='start_map':
            if prefix not in _MAP_KEYS:raise InvalidModelOutput('Invalid model output shape.')
            self._maps.append((prefix,self._root_keys if prefix=='' else set()))
        elif event=='map_key':
            if not self._maps or self._maps[-1][0]!=prefix or value not in _MAP_KEYS[prefix]:
                self.unsupported=True
                raise InvalidModelOutput('Unsupported model protocol field.')
            keys=self._maps[-1][1]
            if value in keys:raise InvalidModelOutput('Duplicate model output field.')
            keys.add(value)
        elif event=='end_map':
            if not self._maps or self._maps[-1][0]!=prefix:raise InvalidModelOutput('Invalid model output shape.')
            self._maps.pop()
            if prefix=='':self._root_done=True
        elif event in ('start_array','end_array'):
            if prefix not in _ARRAYS:raise InvalidModelOutput('Invalid model output shape.')
        elif prefix=='next_action':
            if event!='string' or value!='directions':
                self.unsupported=True
                raise InvalidModelOutput('Unsupported model action.')
            self.action=value
            self._emit()
        elif prefix=='refusal':
            self._refusal_known=True
            if event=='null':self._refusal=None
            elif event=='string' and len(value)<=1200 and not self._ideas:
                try:self._refusal=safe_text(value)
                except (ValueError,UnicodeError):raise InvalidModelOutput('Invalid refusal.') from None
            else:raise InvalidModelOutput('Invalid refusal.')
            self._emit()
        elif prefix in _STRING_LIMITS:
            if event!='string' or len(value)>_STRING_LIMITS[prefix]:raise InvalidModelOutput('Invalid idea content.')
            try:safe_text(value)
            except (ValueError,UnicodeError):raise InvalidModelOutput('Invalid idea content.') from None
        else:raise InvalidModelOutput('Invalid model output shape.')
        if prefix=='ideas.item' and event=='start_map':
            if self._refusal is not None or len(self._ideas)>=3:raise InvalidModelOutput('Invalid idea count or refusal.')
            self._citations=0
            self._builder=ObjectBuilder()
        if prefix=='ideas.item.premise_citations.item' and event=='start_map':
            self._citations+=1
            if self._citations>6:raise InvalidModelOutput('Invalid premise citation count.')
        if self._builder is not None:
            self._builder.event(event,value)
            if prefix=='ideas.item' and event=='end_map':
                try:idea=ProposedIdea.model_validate(self._builder.value)
                except (ValidationError,ValueError,UnicodeError):raise InvalidModelOutput('Invalid idea.') from None
                self._builder=None
                self._ideas.append(idea)
                self._emit()

    def feed(self,fragment: bytes) -> tuple[ProposedIdea,...]:
        if self._closed or not isinstance(fragment,(bytes,bytearray)):raise InvalidModelOutput('Invalid parser lifecycle.')
        self._bytes+=len(fragment)
        if self._bytes>self.MAX_BYTES:
            self.close();raise InvalidModelOutput('Model output exceeds its size limit.')
        if self._root_done:
            if fragment.strip():
                self.close();raise InvalidModelOutput('Additional model output data.')
            return ()
        self._new=[]
        try:self._coro.send(fragment)
        except InvalidModelOutput:
            self.close();raise
        except (JSONError,UnicodeError,ValueError,RecursionError):
            self.close();raise InvalidModelOutput('Invalid model output JSON.') from None
        return tuple(self._new)

    def finish(self,output: ResearchOutput) -> None:
        if self._closed:raise InvalidModelOutput('Invalid parser lifecycle.')
        self._closed=True
        try:
            self._coro.close()
            if (not self._root_done or self._builder is not None or self._root_keys!=_MAP_KEYS['']
                or not isinstance(output,ResearchOutput) or output.next_action!=self.action
                or output.refusal!=self._refusal or output.ideas!=self._ideas):
                raise InvalidModelOutput('Incomplete or inconsistent idea envelope.')
        except (JSONError,UnicodeError,ValueError,RecursionError):
            raise InvalidModelOutput('Invalid model output JSON or envelope.') from None
        finally:self._builder=None

    def close(self) -> None:
        if not self._closed:
            self._closed=True
            try:self._coro.close()
            except (JSONError,UnicodeError,ValueError,InvalidModelOutput):pass
        self._builder=None
