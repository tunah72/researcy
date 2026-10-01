from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterator, Literal

from researcy.ingestion.models import IntegrityFailure


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
    characters: int = 2_000_000

    @classmethod
    def full_parser(cls) -> "SandboxLimits":
        from researcy.config import get_settings

        settings = get_settings()
        return cls(cpu_seconds=settings.parser_cpu_seconds,wall_seconds=settings.parser_wall_seconds,
            memory_bytes=settings.parser_memory_bytes,output_bytes=settings.parser_output_bytes,
            input_bytes=settings.max_upload_bytes,pages=settings.max_pdf_pages,
            characters=settings.parser_max_characters)

    def __post_init__(self) -> None:
        integers = (self.cpu_seconds,self.memory_bytes,self.output_bytes,self.input_bytes,
            self.pages,self.open_files,self.processes,self.characters)
        if (any(type(value) is not int or value<=0 for value in integers)
            or type(self.wall_seconds) not in (int,float)
            or not math.isfinite(self.wall_seconds) or self.wall_seconds<=0):
            raise ValueError("sandbox limits must be finite and positive")


Box = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PageRecord:
    page_index: int
    media_box: Box
    crop_box: Box
    rotation: int
    width: float
    height: float
    transform: tuple[float, ...]
    kind: Literal["page"] = "page"


@dataclass(frozen=True, slots=True)
class BlockRecord:
    page_index: int
    ordinal: int
    box: Box
    block_type: str
    font_size: float
    bold: bool
    source_group: int
    kind: Literal["block"] = "block"


@dataclass(frozen=True, slots=True)
class SpanRecord:
    page_index: int
    ordinal: int
    block_ordinal: int
    raw_text: str
    character_boxes: tuple[Box, ...]
    kind: Literal["span"] = "span"


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    page_count: int
    block_count: int
    span_count: int
    character_count: int
    sha256: bytes
    byte_count: int
    schema_version: int = 1


ParserRecord = PageRecord | BlockRecord | SpanRecord


def decode_parser_record(line: bytes) -> dict[str, object]:
    def unique_fields(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise IntegrityFailure("PARSER_OUTPUT_INVALID")
            result[key]=value
        return result

    try:
        value=json.loads(line,object_pairs_hook=unique_fields)
    except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):
        raise IntegrityFailure("PARSER_OUTPUT_INVALID") from None
    if type(value) is not dict:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    return value


def _number(value) -> float:
    if type(value) not in (int,float) or not math.isfinite(value):
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    return float(value)


def _integer(value, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    return value


def _box(value, bounds: Box | None = None) -> Box:
    if type(value) is not list or len(value) != 4:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    result = tuple(_number(coord) for coord in value)
    if result[0] > result[2] or result[1] > result[3]:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    if bounds and (result[0]<bounds[0] or result[1]<bounds[1] or result[2]>bounds[2] or result[3]>bounds[3]):
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    return result


def read_parser_records(path: Path, limits: SandboxLimits | None = None) -> Iterator[ParserRecord]:
    """Validate one bounded page/block/span stream; source text is never logged."""
    limits = limits or SandboxLimits.full_parser()
    page = None
    block = None
    group_index = -1
    block_has_text = False
    pages = blocks = spans = characters = byte_count = 0
    complete = False
    fields = {
        "page": {"kind","schema_version","page_index","media_box","crop_box","rotation","width","height","transform"},
        "block": {"kind","schema_version","page_index","ordinal","box","block_type","font_size","bold","source_group"},
        "span": {"kind","schema_version","page_index","ordinal","block_ordinal","raw_text","character_boxes"},
        "summary": {"kind","schema_version","page_count","block_count","span_count","character_count"},
    }
    try:
        with path.open("rb") as source:
            while True:
                line = source.readline(min(limits.output_bytes,2*1024*1024)+1)
                if not line:
                    break
                byte_count += len(line)
                if byte_count > limits.output_bytes or len(line)>2*1024*1024 or not line.endswith(b"\n") or complete:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                value = decode_parser_record(line)
                if type(value) is not dict or value.get("kind") not in fields:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                kind = value["kind"]
                if set(value)!=fields[kind] or type(value.get("schema_version")) is not int or value["schema_version"]!=1:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                if kind in ("page","block","summary") and block is not None and block.block_type!="image" and not block_has_text:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                if kind == "summary":
                    actual = (pages,blocks,spans,characters)
                    supplied = tuple(_integer(value[name],max(limits.characters,limits.pages)) for name in
                        ("page_count","block_count","span_count","character_count"))
                    if supplied!=actual or pages==0 or characters==0:
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    complete=True
                    continue
                index = _integer(value["page_index"],limits.pages-1)
                if kind == "page":
                    if index!=pages:
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    media = _box(value["media_box"])
                    crop = _box(value["crop_box"],media)
                    rotation = _integer(value["rotation"],270)
                    transform = value["transform"]
                    width,height = _number(value["width"]),_number(value["height"])
                    if (rotation not in (0,90,180,270) or width<=0 or height<=0 or
                        type(transform) is not list or len(transform)!=6):
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    matrix = tuple(_number(coord) for coord in transform)
                    determinant=matrix[0]*matrix[3]-matrix[1]*matrix[2]
                    if not math.isfinite(determinant) or abs(determinant)<1e-12:
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    corners=tuple((x*matrix[0]+y*matrix[2]+matrix[4],
                        x*matrix[1]+y*matrix[3]+matrix[5]) for x,y in
                        ((0,0),(width,0),(0,height),(width,height)))
                    expected_corners=((crop[0],crop[3]),(crop[2],crop[3]),
                        (crop[0],crop[1]),(crop[2],crop[1]))
                    # Preserve corner orientation; an equal envelope can be reflected.
                    if any(not math.isclose(actual,expected,rel_tol=0,abs_tol=1e-4)
                        for corner,expected_corner in zip(corners,expected_corners)
                        for actual,expected in zip(corner,expected_corner)):
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    page = PageRecord(index,media,crop,rotation,width,height,matrix)
                    block=None;group_index=-1;block_has_text=False;pages+=1
                    yield page
                    continue
                if page is None or index!=page.page_index:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                if kind == "block":
                    ordinal = _integer(value["ordinal"],limits.characters)
                    if ordinal!=blocks or value["block_type"] not in ("text","heading","caption","table","equation","image") or type(value["bold"]) is not bool:
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    size = _number(value["font_size"])
                    if size<0:
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    group = _integer(value["source_group"],limits.characters)
                    if group not in (group_index,group_index+1) or group<0:
                        raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                    group_index=group;block_has_text=False
                    block = BlockRecord(index,ordinal,_box(value["box"],page.media_box),value["block_type"],size,
                        value["bold"],group)
                    blocks+=1
                    yield block
                    continue
                ordinal = _integer(value["ordinal"],limits.characters)
                raw = value["raw_text"]
                boxes = value["character_boxes"]
                if (block is None or block.block_type=="image" or block_has_text or ordinal!=spans or type(raw) is not str or not raw or
                    type(boxes) is not list or len(boxes)!=len(raw) or
                    type(value["block_ordinal"]) is not int or value["block_ordinal"]!=block.ordinal):
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                if any(char=="\0" or 0xD800<=ord(char)<=0xDFFF for char in raw):
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                characters+=len(raw)
                if characters>limits.characters:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                character_boxes = tuple(_box(box,block.box) for box in boxes)
                span_box=(min(box[0] for box in character_boxes),min(box[1] for box in character_boxes),
                    max(box[2] for box in character_boxes),max(box[3] for box in character_boxes))
                if any(not math.isclose(actual,expected,rel_tol=0,abs_tol=1e-4)
                    for actual,expected in zip(span_box,block.box)):
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                spans+=1;block_has_text=True
                yield SpanRecord(index,ordinal,block.ordinal,raw,character_boxes)
        if not complete:
            raise IntegrityFailure("PARSER_OUTPUT_INVALID")
    except (ValueError,TypeError,KeyError,UnicodeError,OSError,RecursionError,OverflowError):
        raise IntegrityFailure("PARSER_OUTPUT_INVALID") from None
