import json
from pathlib import Path

import pymupdf
import pytest

from researcy.documents.models import SandboxLimits, read_parser_records
from researcy.documents.parser import parse_pdf
from researcy.ingestion.models import StageFailure


@pytest.mark.parametrize('rotation', [0,90,180,270])
def test_parser_retains_nonzero_crop_rotation_and_exact_character_geometry(tmp_path, rotation):
    source = tmp_path/'source.pdf'
    document = pymupdf.open()
    page = document.new_page(width=300,height=400)
    page.insert_text((60,100),'Exact geometry')
    baseline = page.get_text('rawdict')['blocks'][0]['lines'][0]['spans'][0]['chars']
    expected = [(char['bbox'][0],400-char['bbox'][3],char['bbox'][2],400-char['bbox'][1]) for char in baseline]
    page.set_cropbox(pymupdf.Rect(20,30,280,350));page.set_rotation(rotation)
    document.save(source);document.close()
    output = tmp_path/'records.jsonl'
    summary = parse_pdf(source,output,SandboxLimits.full_parser())
    records = list(read_parser_records(output))
    page_record = next(record for record in records if record.kind=='page')
    span = next(record for record in records if record.kind=='span')
    assert page_record.rotation == rotation
    assert page_record.media_box == (0,0,300,400)
    assert page_record.crop_box == (20,50,280,370)
    assert span.raw_text == 'Exact geometry'
    for actual, wanted in zip(span.character_boxes,expected,strict=True):
        assert actual == pytest.approx(wanted,abs=1e-4)
    assert summary.page_count == 1 and summary.character_count == len('Exact geometry')


def test_parser_orders_two_columns_before_lower_spanning_heading(tmp_path):
    source = tmp_path/'columns.pdf'
    document=pymupdf.open();page=document.new_page(width=600,height=700)
    for position,text in [((40,80),'1 Introduction'),((40,130),'Left first paragraph.'),
        ((330,130),'Right first paragraph.'),((40,200),'Left second paragraph.'),
        ((330,200),'Right second paragraph.'),((40,300),'2 A spanning section heading across the entire page')]:
        page.insert_text(position,text,fontsize=12)
    document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    text=[record.raw_text for record in read_parser_records(output) if record.kind=='span']
    assert text.index('Left second paragraph.') < text.index('Right first paragraph.')
    assert text.index('Right second paragraph.') < text.index('2 A spanning section heading across the entire page')


def test_malformed_child_output_is_rejected_without_publishing(tmp_path, monkeypatch):
    import researcy.documents.parser as parser

    source=tmp_path/'source.pdf';source.write_bytes(b'%PDF-untrusted')
    output=tmp_path/'records.jsonl'
    def malformed(mode,source,sink,limits,**kwargs):
        sink.write_text(json.dumps({'kind':'page','schema_version':1,'page_index':0,'media_box':[0,0,100,100],
            'crop_box':[0,0,100,100],'rotation':0,'width':100,'height':100,'transform':[1,0,0,1,0,0]})+'\n'+
            json.dumps({'kind':'span','schema_version':1,'page_index':0,'ordinal':0,'block_ordinal':0,
                'raw_text':'A','character_boxes':[[0,0,999,999]]})+'\n')
    monkeypatch.setattr(parser,'run_pdf_child',malformed)
    with pytest.raises(StageFailure):
        parse_pdf(source,output,SandboxLimits.full_parser())
    assert not output.exists()


def test_parser_does_not_truncate_extracted_text_at_character_cap(tmp_path):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'More than five characters');document.save(source);document.close()
    limits=SandboxLimits.full_parser()
    from dataclasses import replace
    output=tmp_path/'records.jsonl'
    with pytest.raises(StageFailure) as exc:
        parse_pdf(source,output,replace(limits,characters=5))
    assert exc.value.failure_kind=='resource_limit'
    assert not output.exists()


def test_parser_preserves_nonzero_media_origin(tmp_path):
    source=tmp_path/'offset.pdf';document=pymupdf.open();page=document.new_page(width=300,height=400)
    page.set_mediabox(pymupdf.Rect(10,20,310,420))
    page.insert_text((60,100),'Offset source')
    matrix=~page.transformation_matrix
    original=page.get_text('rawdict')['blocks'][0]['lines'][0]['spans'][0]['chars']
    expected=[tuple(pymupdf.Rect(char['bbox'])*matrix) for char in original]
    document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    records=list(read_parser_records(output))
    page_record=next(record for record in records if record.kind=='page')
    span=next(record for record in records if record.kind=='span')
    assert page_record.media_box==(10,20,310,420)
    for actual,wanted in zip(span.character_boxes,expected,strict=True):
        assert actual==pytest.approx(wanted,abs=1e-4)


@pytest.mark.parametrize("mutation", ["nonfinite","wrong-summary","extra-field","missing-summary"])
def test_typed_stream_rejects_invalid_geometry_or_completeness(tmp_path, mutation):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'Bounded typed source');document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    values=[json.loads(line) for line in output.read_text().splitlines()]
    if mutation=='nonfinite':
        next(value for value in values if value['kind']=='span')['character_boxes'][0][0]=float('nan')
    elif mutation=='wrong-summary': values[-1]['character_count']+=1
    elif mutation=='extra-field': values[0]['object_key']='untrusted'
    else: values.pop()
    output.write_text(''.join(json.dumps(value)+'\n' for value in values))
    with pytest.raises(StageFailure):
        list(read_parser_records(output))


def test_figure_pixels_are_not_invented_as_evidence_but_bounds_are_retained(tmp_path):
    source=tmp_path/'figure.pdf';document=pymupdf.open();page=document.new_page(width=300,height=400)
    image=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,4,4))
    image.clear_with(200)
    page.insert_image(pymupdf.Rect(40,80,160,200),pixmap=image)
    page.insert_text((40,230),'Figure 1: Available caption text')
    document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    records=list(read_parser_records(output))
    figure=next(record for record in records if record.kind=='block' and record.block_type=='image')
    assert figure.box==pytest.approx((40,200,160,320),abs=1e-4)
    assert [record.raw_text for record in records if record.kind=='span']==['Figure 1: Available caption text']


def test_compact_three_column_panels_order_rows_before_next_row(tmp_path):
    source=tmp_path/'panels.pdf';document=pymupdf.open();page=document.new_page(width=600,height=700)
    for row,y in enumerate((100,180)):
        for column,x in enumerate((70,240,420)):
            page.insert_text((x,y),f'Panel {row}-{column}')
            page.insert_text((x,y+16),f'Affiliation {row}-{column}')
    document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    texts=[record.raw_text for record in read_parser_records(output) if record.kind=='span']
    assert texts.index('Affiliation 0-2')<texts.index('Panel 1-0')
    assert texts.index('Affiliation 0-0')<texts.index('Panel 0-1')


def test_parallel_text_regions_with_narrow_gutter_remain_column_major(tmp_path):
    source=tmp_path/'narrow-columns.pdf';document=pymupdf.open();page=document.new_page(width=612,height=792)
    left='Left column starts here. '+('An independent paragraph is retained. '*5)+'Left column ends here.'
    right='Right column starts here. '+('Another independent paragraph is retained. '*5)+'Right column ends here.'
    assert page.insert_textbox(pymupdf.Rect(108,72,304,220),left,fontsize=10)>0
    assert page.insert_textbox(pymupdf.Rect(310,72,506,220),right,fontsize=10)>0
    page.insert_text((108,230),'3 A full width following section in the paper',fontsize=14)
    document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    text=' '.join(record.raw_text for record in read_parser_records(output) if record.kind=='span')
    assert text.index('Left column ends here.')<text.index('Right column starts here.')


@pytest.mark.parametrize("mutation", ["group-jump","outside-block","orphan-block"])
def test_parser_relations_cannot_lose_text_or_move_geometry(tmp_path, mutation):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'First source run')
    page.insert_text((72,130),'Second source run')
    document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    values=[json.loads(line) for line in output.read_text().splitlines()]
    if mutation=='group-jump':
        next(value for value in values if value['kind']=='block')['source_group']=1000
    elif mutation=='outside-block':
        next(value for value in values if value['kind']=='block')['box']=[0,0,1,1]
    else:
        removed=next(value for value in values if value['kind']=='span')
        values.remove(removed)
        next(value for value in values if value['kind']=='span')['ordinal']=0
        values[-1]['span_count']-=1
        values[-1]['character_count']-=len(removed['raw_text'])
    output.write_text(''.join(json.dumps(value)+'\n' for value in values))
    with pytest.raises(StageFailure):
        list(read_parser_records(output))


@pytest.mark.parametrize("mutation", ["huge-integer","overflowed-determinant"])
def test_unrepresentable_page_numbers_fail_as_safe_parser_errors(tmp_path, mutation):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'Finite geometry');document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    values=[json.loads(line) for line in output.read_text().splitlines()]
    if mutation=="huge-integer": values[0]['width']=10**400
    else: values[0]['transform']=[1e308,1e308,1e308,1e308,0,0]
    output.write_text(''.join(json.dumps(value)+'\n' for value in values))
    with pytest.raises(StageFailure) as exc:
        list(read_parser_records(output))
    assert exc.value.code=='PARSER_OUTPUT_INVALID' and exc.value.retryable is False


def test_deeply_nested_child_json_is_a_safe_failure_without_output(tmp_path, monkeypatch):
    import researcy.documents.parser as parser

    source=tmp_path/'source.pdf';source.write_bytes(b'%PDF-trusted-fixture')
    output=tmp_path/'records.jsonl'
    def nested(mode,source,sink,limits,**kwargs):
        sink.write_text('['*10000+'0'+']'*10000+'\n')
    monkeypatch.setattr(parser,'run_pdf_child',nested)
    with pytest.raises(StageFailure) as exc:
        parse_pdf(source,output,SandboxLimits.full_parser())
    assert exc.value.code=='PARSER_OUTPUT_INVALID' and exc.value.retryable is False
    assert not output.exists()


def test_duplicate_child_fields_are_rejected_without_publication(tmp_path, monkeypatch):
    import researcy.documents.parser as parser

    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'Unambiguous source');document.save(source);document.close()
    valid=tmp_path/'valid.jsonl';parse_pdf(source,valid,SandboxLimits.full_parser())
    lines=valid.read_bytes().splitlines(keepends=True)
    lines[0]=b'{"page_index":999,'+lines[0][1:]
    malformed=tmp_path/'malformed.jsonl';malformed.write_bytes(b''.join(lines))
    with pytest.raises(StageFailure) as exc:
        list(read_parser_records(malformed))
    assert exc.value.code=='PARSER_OUTPUT_INVALID'
    output=tmp_path/'published.jsonl'
    monkeypatch.setattr(parser,'run_pdf_child',lambda mode,source,sink,limits,**kwargs: sink.write_bytes(malformed.read_bytes()))
    with pytest.raises(StageFailure) as exc:
        parse_pdf(source,output,SandboxLimits.full_parser())
    assert exc.value.code=='PARSER_OUTPUT_INVALID' and not output.exists()


@pytest.mark.parametrize("text,font,expected", [
    ("2 Methods","helv","heading"),
    ("Figure 1: Architecture","hebo","caption"),
    ("Table 2: Results","hebo","caption"),
])
def test_numbered_headings_and_bold_captions_keep_their_roles(tmp_path,text,font,expected):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),text,fontname=font);document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    block=next(record for record in read_parser_records(output) if record.kind=='block')
    assert block.block_type==expected


@pytest.mark.parametrize("mutation",["transform-translation","page-width","expanded-block","reflected-transform"])
def test_declared_geometry_must_match_its_exact_source(tmp_path,mutation):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'Consistent geometry');document.save(source);document.close()
    output=tmp_path/'records.jsonl';parse_pdf(source,output,SandboxLimits.full_parser())
    values=[json.loads(line) for line in output.read_text().splitlines()]
    if mutation=='transform-translation': values[0]['transform'][4]+=2
    elif mutation=='page-width': values[0]['width']+=2
    elif mutation=='reflected-transform':
        crop=values[0]['crop_box']
        values[0]['transform']=[-1,0,0,1,crop[2],crop[1]]
    else:
        block=next(value for value in values if value['kind']=='block')
        block['box'][0]-=2
    output.write_text(''.join(json.dumps(value)+'\n' for value in values))
    with pytest.raises(StageFailure) as exc:
        list(read_parser_records(output))
    assert exc.value.code=='PARSER_OUTPUT_INVALID'


@pytest.mark.parametrize("mixed",[False,True])
def test_unknown_glyphs_are_preserved_but_not_a_usable_document(tmp_path,mixed):
    source=tmp_path/'source.pdf';document=pymupdf.open();page=document.new_page()
    page.insert_text((72,72),'A')
    document.xref_set_key(page.get_fonts()[0][0],'Encoding','<< /Type /Encoding /Differences [0 /.notdef] >>')
    content=b'0041' if mixed else b'00'
    document.update_stream(page.get_contents()[0],b'BT /helv 12 Tf 1 0 0 1 72 72 Tm <'+content+b'> Tj ET')
    document.save(source);document.close()
    output=tmp_path/'records.jsonl'
    if not mixed:
        with pytest.raises(StageFailure) as exc:
            parse_pdf(source,output,SandboxLimits.full_parser())
        assert exc.value.code=='PDF_NO_TEXT' and exc.value.retryable is False
        assert not output.exists()
    else:
        summary=parse_pdf(source,output,SandboxLimits.full_parser())
        span=next(record for record in read_parser_records(output) if record.kind=='span')
        assert span.raw_text=='\ufffdA' and summary.character_count==2
