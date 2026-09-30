from collections import Counter
from dataclasses import asdict
import json
import math
import re
import tempfile
from typing import Iterable, Iterator

from researcy.ingestion.models import DocumentScope, ProcessingProfile, IntegrityFailure, deterministic_id
from .canonical import CanonicalRecord, CanonicalPage, CanonicalSection, CanonicalBlock, CanonicalSpan, SourceMapping
from .models import PageRecord, BlockRecord, SpanRecord, ParserRecord


LIGATURES={'ﬀ':'ff','ﬁ':'fi','ﬂ':'fl','ﬃ':'ffi','ﬄ':'ffl','ﬅ':'st','ﬆ':'st'}


def _margin_key(page,block,text):
    x0,y0,x1,y1=page['crop_box'];height=y1-y0
    band='top' if block['box'][1]>=y1-height*.08 else 'bottom' if block['box'][3]<=y0+height*.08 else None
    if band is None:
        return None
    normalized=' '.join(''.join(LIGATURES.get(char,char) for char in text).split())
    if re.fullmatch(r'\d+',normalized):
        normalized='#'
    return band,normalized


def _normalized(raw,span_id,section_id,remove_hyphen):
    parts=[];mappings=[];position=0;source=0
    while source<len(raw):
        end=source+1;char=raw[source]
        if remove_hyphen and source==len(raw)-1:
            text='';transformation='dehyphenation'
        elif char.isspace():
            while end<len(raw) and raw[end].isspace(): end+=1
            text=' ';transformation='whitespace'
        elif char in LIGATURES:
            text=LIGATURES[char];transformation='ligature'
        else:
            text=char;transformation='identity'
        mapping=SourceMapping(position,position+len(text),span_id,source,end,transformation,section_id)
        if mappings and transformation=='identity' and mappings[-1].transformation=='identity':
            old=mappings[-1]
            mappings[-1]=SourceMapping(old.start,mapping.end,span_id,old.source_start,end,transformation,section_id)
        else:
            mappings.append(mapping)
        parts.append(text);position+=len(text);source=end
    return ''.join(parts),tuple(mappings)


def _units(spool):
    page=block=None
    for line in spool:
        value=json.loads(line)
        if value['kind']=='page':
            page=value;yield 'page',page,None,None
        elif value['kind']=='block':
            block=value
            if block['block_type']=='image': yield 'image',page,block,None
        else:
            yield 'text',page,block,value


def _numbered_title(current,following):
    kind,page,block,span=current
    if (kind!='text' or following is None or following[0]!='text' or
        not re.fullmatch(r'\d+(?:\.\d+)*\.?',span['raw_text']) or len(span['raw_text'])>24 or
        page['page_index']!=following[1]['page_index'] or following[2]['block_type']!='heading'):
        return False
    first,second=block['box'],following[2]['box']
    height=min(first[3]-first[1],second[3]-second[1])
    return first[2]<=second[0] and height>0 and min(first[3],second[3])-max(first[1],second[1])>=height*.8


def normalize_records(records: Iterable[ParserRecord], profile: ProcessingProfile, *, scope: DocumentScope) -> Iterator[CanonicalRecord]:
    """Two bounded disk passes allow conservative document-wide margin detection."""
    counts=Counter();seen=set();page_count=byte_count=characters=0;page=block=None
    with tempfile.TemporaryFile(mode='w+b') as spool:
        for record in records:
            if not isinstance(record,(PageRecord,BlockRecord,SpanRecord)):
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            value=asdict(record)
            if record.kind=='page':
                counts.update(seen);seen.clear();page=value;page_count+=1
            elif record.kind=='block': block=value
            else:
                if page is None or block is None:
                    raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
                characters+=len(record.raw_text)
                key=_margin_key(page,block,record.raw_text)
                if key is not None: seen.add(key)
            encoded=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode()
            byte_count+=len(encoded)
            if byte_count>profile.parser_output_bytes or page_count>profile.max_pages or characters>profile.max_characters:
                raise IntegrityFailure('PDF_PARSE_RESOURCE_LIMIT')
            spool.write(encoded)
        counts.update(seen)
        if not page_count or not characters:
            raise IntegrityFailure('PDF_NO_TEXT')
        excluded={key for key,count in counts.items() if count>=max(3,math.ceil(page_count*.6))}
        spool.seek(0);units=iter(_units(spool));current=next(units,None)
        section_ordinal=0
        section=CanonicalSection(deterministic_id(scope,profile.profile_hash,'section','0'),scope,profile.profile_hash,0,None,None)
        yield section
        previous=None;previous_join=False;paired_title=None
        while current is not None:
            following=next(units,None);kind,page,block,span=current
            page_id=deterministic_id(scope,profile.profile_hash,'page',str(page['page_index']))
            if kind=='page':
                source=PageRecord(page['page_index'],tuple(page['media_box']),tuple(page['crop_box']),page['rotation'],page['width'],page['height'],tuple(page['transform']))
                yield CanonicalPage(page_id,scope,source)
            else:
                is_excluded=kind=='text' and _margin_key(page,block,span['raw_text']) in excluded
                paired=_numbered_title(current,following) and not is_excluded and _margin_key(following[1],following[2],following[3]['raw_text']) not in excluded
                already_paired=kind=='text' and span['ordinal']==paired_title
                if kind=='text' and not is_excluded and (paired or block['block_type']=='heading' and not already_paired):
                    section_ordinal+=1
                    title=span['raw_text']+' '+following[3]['raw_text'] if paired else span['raw_text']
                    paired_title=following[3]['ordinal'] if paired else None
                    section=CanonicalSection(deterministic_id(scope,profile.profile_hash,'section',str(section_ordinal)),scope,profile.profile_hash,section_ordinal,title,(page['page_index'],span['ordinal']))
                    yield section;previous=None;previous_join=False
                block_id=deterministic_id(scope,profile.profile_hash,'block',str(block['ordinal']))
                yield CanonicalBlock(block_id,scope,page_id,section.id,block['ordinal'],block['block_type'],tuple(block['box']),bool(is_excluded))
                if kind=='text':
                    span_id=deterministic_id(scope,profile.profile_hash,'span',str(span['ordinal']))
                    retrieval=not is_excluded
                    same_group=(previous is not None and previous[0]==page['page_index'] and previous[1]==block['source_group'])
                    join=(retrieval and following is not None and following[0]=='text' and following[1]['page_index']==page['page_index'] and
                        following[2]['source_group']==block['source_group'] and following[2]['block_type']!='heading' and
                        _margin_key(following[1],following[2],following[3]['raw_text']) not in excluded and
                        len(span['raw_text'])>=2 and span['raw_text'][-1]=='-' and span['raw_text'][-2].isalpha() and
                        following[3]['raw_text'][0].islower())
                    text,mappings=_normalized(span['raw_text'],span_id,section.id,join)
                    separator='' if previous is None or (same_group and previous_join) else ' ' if same_group else '\n\n'
                    yield CanonicalSpan(span_id,scope,profile.profile_hash,block_id,page_id,section.id,span['ordinal'],span['raw_text'],
                        tuple(tuple(box) for box in span['character_boxes']),text,mappings,separator,retrieval)
                    if retrieval: previous=(page['page_index'],block['source_group']);previous_join=join
            current=following
