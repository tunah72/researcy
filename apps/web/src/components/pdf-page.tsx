'use client';

import React, { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, PDFPageProxy, RenderTask, TextLayer } from 'pdfjs-dist';
import type * as PdfRuntime from 'pdfjs-dist';
import type { ReaderPage, ResolvedCitation } from '@/lib/api';
import { pdfBoxToViewport } from '@/lib/pdf-geometry';

type Runtime = typeof PdfRuntime;

export function PdfPage({ document, runtime, metadata, pageNumber, width, zoom, onError, citation, onCitationReady }: {
  document: PDFDocumentProxy;
  runtime: Runtime;
  metadata: ReaderPage;
  pageNumber: number;
  width: number;
  zoom: number;
  onError: () => void;
  citation: ResolvedCitation | null;
  onCitationReady?: (citationId: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState<number[] | null>(null);

  useEffect(() => {
    let disposed = false;
    let rendering: RenderTask | undefined;
    let textLayer: TextLayer | undefined;
    let page: PDFPageProxy | undefined;
    const canvas = canvasRef.current;
    const text = textRef.current;
    if (!canvas || !text || width <= 0) return;
    setTransform(null);

    void (async () => {
      page = await document.getPage(pageNumber);
      if (disposed) { page.cleanup(); return; }
      if (page.rotate !== metadata.rotation ||
          page.view.some((value: number, index: number) => Math.abs(value - metadata.crop_box[index]) > 0.001)) {
        throw new Error('Unavailable original geometry.');
      }
      const original = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: width / original.width * zoom });
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.ceil(viewport.width * pixelRatio);
      canvas.height = Math.ceil(viewport.height * pixelRatio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      text.style.setProperty('--total-scale-factor', String(viewport.scale * page.userUnit));
      rendering = page.render({
        canvas, viewport,
        transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
        annotationMode: runtime.AnnotationMode.DISABLE,
      });
      textLayer = new runtime.TextLayer({
        textContentSource: page.streamTextContent(), container: text, viewport,
      });
      await Promise.all([rendering.promise, textLayer.render()]);
      if (!disposed) setTransform([...viewport.transform]);
    })().catch(() => { if (!disposed) onError(); });

    return () => {
      disposed = true;
      rendering?.cancel();
      textLayer?.cancel();
      // PDF.js cleanup must wait until a cancelled render has settled.
      void (rendering?.promise.catch(() => undefined) ?? Promise.resolve()).then(() => page?.cleanup());
      canvas.width = 0;
      canvas.height = 0;
      text.replaceChildren();
    };
  }, [document, runtime, metadata, pageNumber, width, zoom, onError]);

  useEffect(() => {
    if (transform && citation) onCitationReady?.(citation.citation_id);
  }, [transform, citation, onCitationReady]);

  return <>
    <canvas ref={canvasRef} aria-hidden="true" />
    <div ref={textRef} className="pdf-text-layer" />
    {transform && citation && <div className="pdf-evidence-overlay" aria-hidden="true">
      {citation.boxes.map((box, index) => {
        const geometry = pdfBoxToViewport(box, transform);
        return <span key={index} className="pdf-evidence-box" style={geometry} />;
      })}
    </div>}
  </>;
}
