'use client';

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, PDFDocumentLoadingTask } from 'pdfjs-dist';
import type * as PdfRuntime from 'pdfjs-dist';
import type { ReaderDocument, ResolvedCitation } from '@/lib/api';
import { PdfPage } from './pdf-page';

type Runtime = typeof PdfRuntime;
interface OpenPdf { document: PDFDocumentProxy; runtime: Runtime }
interface OutlineItem { title: string; page: number; depth: number }
interface NativeOutline { title: string; dest: string | unknown[] | null; items?: NativeOutline[] }

async function outlinePages(document: PDFDocumentProxy, entries: NativeOutline[], depth = 0): Promise<OutlineItem[]> {
  const result: OutlineItem[] = [];
  for (const entry of entries) {
    const destination = typeof entry.dest === 'string' ? await document.getDestination(entry.dest) : entry.dest;
    if (Array.isArray(destination) && destination.length > 0) {
      const reference = destination[0];
      const index = typeof reference === 'number' ? reference :
        reference && typeof reference === 'object' && 'num' in reference && 'gen' in reference ?
          await document.getPageIndex({ num: Number(reference.num), gen: Number(reference.gen) }) : -1;
      if (Number.isInteger(index) && index >= 0 && index < document.numPages) {
        result.push({ title: entry.title, page: index + 1, depth });
      }
    }
    if (entry.items?.length) result.push(...await outlinePages(document, entry.items, depth + 1));
  }
  return result;
}

export function PdfReader({ source, page, onPageChange, citation, onCitationReady }: {
  source: ReaderDocument;
  page: number;
  onPageChange: (page: number) => void;
  citation: ResolvedCitation | null;
  onCitationReady?: (citationId: string) => void;
}) {
  const [opened, setOpened] = useState<OpenPdf | null>(null);
  const [failure, setFailure] = useState(false);
  const [reload, setReload] = useState(0);
  const [width, setWidth] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [outline, setOutline] = useState<OutlineItem[]>([]);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const revealedCitation = useRef<string | null>(null);
  const frame = useRef<number | null>(null);
  const loadingRef = useRef<PDFDocumentLoadingTask | null>(null);
  const showFailure = useCallback(() => {
    setFailure(true);
    setOpened(null);
    const loading = loadingRef.current;
    loadingRef.current = null;
    void loading?.destroy().catch(() => undefined);
  }, []);

  useEffect(() => {
    let disposed = false;
    let loading: PDFDocumentLoadingTask | undefined;
    setOpened(null);
    setFailure(false);
    setOutline(source.outline.map(entry => ({ ...entry, depth: 0 })));
    void (async () => {
      // PDF.js initializes DOMMatrix; static import would execute during Next SSR.
      const runtime = await import('pdfjs-dist');
      if (disposed) return;
      const assets = `/pdfjs/${runtime.version}/`;
      runtime.GlobalWorkerOptions.workerSrc = assets + 'pdf.worker.min.mjs';
      loading = runtime.getDocument({
        url: source.pdf_url, withCredentials: true, disableStream: true,
        disableAutoFetch: true, enableXfa: false, stopAtErrors: true,
        cMapUrl: assets + 'cmaps/', standardFontDataUrl: assets + 'standard_fonts/',
        wasmUrl: assets + 'wasm/',
      });
      loadingRef.current = loading;
      const document = await loading.promise;
      if (disposed) return;
      if (document.numPages !== source.pages.length) throw new Error('Unavailable original geometry.');
      const originalPage = await document.getPage(page);
      const expected = source.pages[page - 1];
      if (!expected || originalPage.rotate !== expected.rotation ||
          originalPage.view.some((value: number, index: number) => Math.abs(value - expected.crop_box[index]) > 0.001)) {
        throw new Error('Unavailable original geometry.');
      }
      setOpened({ document, runtime });
      const native = await document.getOutline();
      if (native?.length) {
        const entries = await outlinePages(document, native);
        if (!disposed && entries.length) setOutline(entries);
      }
    })().catch(() => { if (!disposed) showFailure(); });
    return () => {
      disposed = true;
      if (loadingRef.current === loading) loadingRef.current = null;
      void loading?.destroy().catch(() => undefined);
    };
    // Page navigation must not reload the immutable original/worker.
  }, [source, reload, showFailure]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const resize = () => setWidth(Math.max(0, element.clientWidth - 32));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    if (!citation) revealedCitation.current = null;
    if (width > 0) pageRefs.current[page - 1]?.scrollIntoView({ block: 'start', behavior: 'auto' });
    // Resizing/remounting changes offsets; normal scroll must not snap back.
  }, [width, zoom, failure, citation?.citation_id]);

  const revealCitation = useCallback((id: string) => {
    if (!citation || id !== citation.citation_id) return;
    if (id !== revealedCitation.current) {
      const box = pageRefs.current[citation.page - 1]?.querySelector('.pdf-evidence-box');
      if (!box) return;
      box.scrollIntoView({ block: 'center', behavior: 'auto' });
      revealedCitation.current = id;
    }
    onCitationReady?.(id);
  }, [citation?.citation_id, citation?.page, onCitationReady]);

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
  }, []);

  const navigate = (value: number) => {
    const target = Math.max(1, Math.min(source.pages.length, Math.trunc(value)));
    if (!Number.isFinite(target)) return;
    onPageChange(target);
    pageRefs.current[target - 1]?.scrollIntoView({ block: 'start', behavior: 'auto' });
  };
  const observePage = () => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      // The narrow CSS layout can expand before React unmounts the unsupported reader.
      if (window.innerWidth < 1024) return;
      const element = scrollRef.current;
      if (!element) return;
      const reference = element.scrollTop + element.clientHeight / 3;
      const selected = pageRefs.current.findIndex(node => node && node.offsetTop + node.offsetHeight > reference);
      if (selected >= 0 && selected + 1 !== page) onPageChange(selected + 1);
    });
  };

  return <section className="pdf-reader" aria-label="PDF reader">
    <div className="pdf-toolbar" aria-label="PDF controls">
      <button className="btn btn-secondary" type="button" aria-expanded={outlineOpen}
        aria-controls="reader-outline" onClick={() => setOutlineOpen(value => !value)}>Outline</button>
      <button className="btn btn-secondary" type="button" aria-label="Previous page"
        disabled={page <= 1 || !opened || failure} onClick={() => navigate(page - 1)}>Previous</button>
      <label className="pdf-page-control">Page
        <input aria-label="Page number" type="number" min={1} max={source.pages.length}
          value={page} disabled={!opened || failure} onChange={event => navigate(Number(event.target.value))} />
        <span>of {source.pages.length}</span>
      </label>
      <button className="btn btn-secondary" type="button" aria-label="Next page"
        disabled={page >= source.pages.length || !opened || failure} onClick={() => navigate(page + 1)}>Next</button>
      <label className="pdf-zoom-control">Zoom
        <select aria-label="PDF zoom" value={zoom} onChange={event => setZoom(Number(event.target.value))}>
          <option value={1}>Fit width</option><option value={1.25}>125%</option>
          <option value={1.5}>150%</option><option value={2}>200%</option>
        </select>
      </label>
    </div>
    <div className="pdf-reader-body">
      {outlineOpen && <nav id="reader-outline" className="pdf-outline" aria-label="Document outline">
        <h2>Contents</h2>
        {outline.length ? <ol>{outline.map((entry, index) => <li key={index} style={{ paddingLeft: `${Math.min(entry.depth, 3) * 0.6}rem` }}>
          <button type="button" onClick={() => navigate(entry.page)}>{entry.title}<span>p. {entry.page}</span></button>
        </li>)}</ol> : <p>No outline available for this original.</p>}
      </nav>}
      <div ref={scrollRef} className="pdf-scroll" onScroll={observePage} tabIndex={0} aria-label="PDF pages">
        {failure ? <div className="pdf-load-notice" role="alert">
          <h2>The PDF could not be opened.</h2>
          <p>Reload the original. If access has expired, return to Library and sign in again.</p>
          <button className="btn btn-secondary" onClick={() => setReload(value => value + 1)}>Reload PDF</button>
        </div> : <>
          {!opened && <p className="pdf-load-notice" role="status">Opening original PDF…</p>}
          {source.pages.map((metadata, index) => {
            const box = metadata.crop_box;
            const rotated = metadata.rotation % 180 !== 0;
            const ratio = rotated ? (box[2] - box[0]) / (box[3] - box[1]) : (box[3] - box[1]) / (box[2] - box[0]);
            return <div key={metadata.page_index} ref={node => { pageRefs.current[index] = node; }}
              className="pdf-sheet" role="region" aria-label={`PDF page ${index + 1}`}
              style={{ width: width * zoom || '100%', height: width > 0 ? width * zoom * ratio : undefined }}>
              {opened && Math.abs(index + 1 - page) <= 1 && width > 0 && <PdfPage
                key={`${width}:${zoom}`} metadata={metadata}
                document={opened.document} runtime={opened.runtime} pageNumber={index + 1}
                width={width} zoom={zoom} onError={showFailure}
                citation={citation?.page === index + 1 ? citation : null} onCitationReady={revealCitation} />}
              <span className="pdf-sheet-number" aria-hidden="true">{index + 1}</span>
            </div>;
          })}
        </>}
      </div>
    </div>
  </section>;
}
