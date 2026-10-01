"""Executed only through the namespace launcher after hard limits are installed."""
import json
import os
import sys
import math
import re


def emit(**result):
    print(json.dumps(result, separators=(",", ":")))


def screen(page_limit: int, byte_limit: int) -> None:
    import pymupdf

    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    if os.stat("/input/document.pdf").st_size > byte_limit:
        emit(error="PDF_TOO_LARGE")
        return
    try:
        document = pymupdf.open("/input/document.pdf")
    except Exception:
        emit(error="PDF_INVALID")
        return
    with document:
        if document.is_encrypted:
            emit(error="PDF_ENCRYPTED")
            return
        if document.is_repaired:
            emit(error="PDF_INVALID")
            return
        pages = len(document)
        if pages > page_limit:
            emit(error="PDF_TOO_MANY_PAGES")
            return
        chars = 0
        substantial = 0
        for page in document:
            count = sum(not char.isspace() for char in page.get_text("text"))
            chars += count
            substantial += count >= 40
        if chars == 0:
            emit(error="PDF_NO_TEXT")
            return
        metadata = document.metadata or {}
        title = metadata.get("title")
        emit(pages=pages, title=title[:2000] if isinstance(title, str) else None,
             warning=chars < 200 or substantial * 2 < pages)


def _reading_order(items, width, depth=0):
    """Deterministic whitespace cuts; keep source text runs/formula lines together."""
    if len(items)<2:
        return items
    spanning = [item for item in items if item["bbox"][0]<width/2<item["bbox"][2]
        and item["bbox"][2]-item["bbox"][0]>=width*.4]
    if spanning and len(spanning)<len(items):
        spanning_ids = {item["source_order"] for item in spanning}
        pending = [item for item in items if item["source_order"] not in spanning_ids]
        ordered = []
        for separator in sorted(spanning,key=lambda item:(item["bbox"][1],item["source_order"])):
            band = [item for item in pending if item["bbox"][1]<separator["bbox"][1]]
            band_ids = {item["source_order"] for item in band}
            pending = [item for item in pending if item["source_order"] not in band_ids]
            ordered.extend(_reading_order(band,width,depth+1))
            ordered.append(separator)
        ordered.extend(_reading_order(pending,width,depth+1))
        return ordered
    cuts = []
    for axis,minimum in ((0,4),(1,3)):
        intervals = sorted((item["bbox"][axis],item["bbox"][axis+2]) for item in items)
        start,end = intervals[0]
        extent = max(interval[1] for interval in intervals)-start
        for low,high in intervals[1:]:
            if low>end and low-end>=minimum:
                cuts.append(((low-end)/max(1,extent),axis,(low+end)/2))
            end=max(end,high)
    if not cuts or depth>=16:
        return sorted(items,key=lambda item:(item["bbox"][1],item["bbox"][0],item["source_order"]))
    def compact_columns(group):
        if not group or any(item["bbox"][2]-item["bbox"][0]>=width*.3 for item in group):
            return 0
        columns=0;previous=-width
        for start in sorted(item["bbox"][0] for item in group):
            if start-previous>=width*.08:
                columns+=1;previous=start
        return columns
    # Compact 3+ column panels/tables are row-major, unlike two body columns.
    panels = [cut for cut in cuts if cut[1]==1
        and compact_columns([item for item in items if item["bbox"][3]<=cut[2]])>=3
        and compact_columns([item for item in items if item["bbox"][1]>=cut[2]])>=3]
    _,axis,position = max(panels or cuts,key=lambda cut:(cut[1]==0,cut[0],-cut[2]))
    before=[item for item in items if item["bbox"][axis+2]<=position]
    after=[item for item in items if item["bbox"][axis]>=position]
    if not before or not after or len(before)+len(after)!=len(items):
        return sorted(items,key=lambda item:(item["bbox"][1],item["bbox"][0],item["source_order"]))
    return _reading_order(before,width,depth+1)+_reading_order(after,width,depth+1)


def parse(page_limit: int, byte_limit: int, character_limit: int) -> None:
    import pymupdf

    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    if os.stat("/input/document.pdf").st_size>byte_limit:
        emit(error="PDF_TOO_LARGE")
        return
    try:
        document = pymupdf.open("/input/document.pdf")
    except Exception:
        emit(error="PDF_INVALID")
        return
    with document:
        if document.is_encrypted or document.is_repaired or not document.is_pdf:
            emit(error="PDF_ENCRYPTED" if document.is_encrypted else "PDF_INVALID")
            return
        if not 0<len(document)<=page_limit:
            emit(error="PDF_TOO_MANY_PAGES")
            return
        blocks = spans = characters = 0
        substantive = False
        for page_index,page in enumerate(document):
            rotation = page.rotation
            # PyMuPDF's rotated-page transform loses crop offsets. Raw extraction
            # uses unrotated coordinates, so obtain the actual unrotated transform.
            page.set_rotation(0)
            matrix = page.transformation_matrix
            inverse = ~matrix
            media = tuple(page.mediabox)
            crop = tuple(page.rect*inverse)
            width,height = page.rect.width,page.rect.height
            # Unknown font CIDs are not Unicode. Keep MuPDF's replacement marker
            # rather than emitting a CID as invented text (CID 0 is also invalid SQL text).
            raw = page.get_text("rawdict",flags=pymupdf.TEXTFLAGS_RAWDICT &
                ~pymupdf.TEXT_PRESERVE_IMAGES & ~pymupdf.TEXT_USE_CID_FOR_UNKNOWN_UNICODE)
            page.set_rotation(rotation)
            emit(kind="page",schema_version=1,page_index=page_index,media_box=media,crop_box=crop,
                rotation=rotation,width=width,height=height,transform=tuple(inverse))
            groups = []
            for source_block in raw["blocks"]:
                if source_block["type"]!=0:
                    continue
                lines = [line for line in source_block["lines"]
                    if any(span.get("chars") for span in line["spans"])]
                left = [line for line in lines if line["bbox"][2]<width/2]
                right = [line for line in lines if line["bbox"][0]>width/2]
                def body_run(line):
                    return sum(char["c"].isalpha() for span in line["spans"] for char in span.get("chars",()))>=10
                # MuPDF sometimes groups two independent column lines into one
                # block. Do not split short inline math/superscripts as columns.
                if left and right and len(left)+len(right)==len(lines) and all(body_run(line) for line in lines):
                    parts = (left,right)
                else:
                    parts = (lines,) if lines else ()
                for part in parts:
                    bounds = (min(line["bbox"][0] for line in part),min(line["bbox"][1] for line in part),
                        max(line["bbox"][2] for line in part),max(line["bbox"][3] for line in part))
                    groups.append({"bbox":bounds,"source_order":len(groups),"lines":part})
            # Metadata only: do not decode/buffer image pixels to retain figure bounds.
            for image in page.get_image_info():
                groups.append({"bbox":image["bbox"],"source_order":len(groups),"image":True})
            ordered_lines = []
            for group_index,group in enumerate(_reading_order(groups,width)):
                part = [group] if group.get("image") else group["lines"]
                for line in part:
                    line["source_group"]=group_index
                ordered_lines.extend(part)
            for line in ordered_lines:
                if line.get("image"):
                    box = tuple(pymupdf.Rect(line["bbox"])*inverse)
                    if (not all(math.isfinite(coord) for coord in box) or
                        box[0]<media[0] or box[1]<media[1] or box[2]>media[2] or box[3]>media[3]):
                        emit(error="PDF_PARSE_GEOMETRY_INVALID")
                        return
                    emit(kind="block",schema_version=1,page_index=page_index,ordinal=blocks,
                        box=box,block_type="image",font_size=0,bold=False,source_group=line["source_group"])
                    blocks+=1
                    continue
                all_chars = [char for span in line["spans"] for char in span.get("chars",())]
                if not all_chars:
                    continue
                text = "".join(char["c"] for char in all_chars)
                characters+=len(text)
                if characters>character_limit:
                    emit(error="PDF_PARSE_RESOURCE_LIMIT")
                    return
                substantive |= any(not char.isspace() and char!="\ufffd" for char in text)
                size = max(span["size"] for span in line["spans"])
                bold = any(span["flags"] & 16 for span in line["spans"])
                block_type = "caption" if re.match(r"^(Figure|Table)\s+\d",text) else "text"
                if block_type!="caption" and ((re.match(r"^\d+(?:\.\d+)*\s+\S",text) and len(text)<180) or (bold and len(text)<120)):
                    block_type = "heading"
                boxes = []
                for char in all_chars:
                    if len(char["c"])!=1:
                        emit(error="PDF_PARSE_GEOMETRY_INVALID")
                        return
                    box = tuple(pymupdf.Rect(char["bbox"])*inverse)
                    if (not all(math.isfinite(coord) for coord in box) or
                        box[0]<media[0] or box[1]<media[1] or box[2]>media[2] or box[3]>media[3]):
                        emit(error="PDF_PARSE_GEOMETRY_INVALID")
                        return
                    boxes.append(box)
                block_box = (min(box[0] for box in boxes),min(box[1] for box in boxes),
                    max(box[2] for box in boxes),max(box[3] for box in boxes))
                emit(kind="block",schema_version=1,page_index=page_index,ordinal=blocks,box=block_box,
                    block_type=block_type,font_size=size,bold=bold,source_group=line["source_group"])
                emit(kind="span",schema_version=1,page_index=page_index,ordinal=spans,
                    block_ordinal=blocks,raw_text=text,character_boxes=boxes)
                blocks+=1;spans+=1
        if not substantive:
            emit(error="PDF_NO_TEXT")
            return
        emit(kind="summary",schema_version=1,page_count=len(document),block_count=blocks,
            span_count=spans,character_count=characters)


if __name__ == "__main__":
    try:
        if sys.argv[1]=="screen":
            screen(int(sys.argv[2]),int(sys.argv[3]))
        elif sys.argv[1]=="parse":
            parse(int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]))
        else:
            raise ValueError("unsupported parser mode")
    except MemoryError:
        emit(error="PDF_PARSE_RESOURCE_LIMIT" if sys.argv[1]=="parse" else "PDF_SCREEN_RESOURCE_LIMIT")
