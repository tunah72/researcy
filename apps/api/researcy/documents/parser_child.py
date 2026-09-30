"""Executed only through the namespace launcher after hard limits are installed."""
import json
import os
import sys


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


if __name__ == "__main__":
    if sys.argv[1] != "screen":
        raise ValueError("unsupported parser mode")
    try:
        screen(int(sys.argv[2]), int(sys.argv[3]))
    except MemoryError:
        emit(error="PDF_SCREEN_RESOURCE_LIMIT")
