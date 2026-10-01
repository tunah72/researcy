'use client';

import React, { useEffect, useRef } from 'react';
import type { PDFDocumentProxy, PDFPageProxy, RenderTask, TextLayer } from 'pdfjs-dist';
import type * as PdfRuntime from 'pdfjs-dist';
import type { ReaderPage } from '@/lib/api';

type Runtime = typeof PdfRuntime;

export function PdfPage({ document, runtime, metadata, pageNumber, width, zoom, onError }: {
  document: PDFDocumentProxy;
  runtime: Runtime;
  metadata: ReaderPage;
  pageNumber: number;
  width: number;
  zoom: number;
  onError: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    let rendering: RenderTask | undefined;
    let textLayer: TextLayer | undefined;
    let page: PDFPageProxy | undefined;
    const canvas = canvasRef.current;
    const text = textRef.current;
    if (!canvas || !text || width <= 0) return;

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

  return <>
    <canvas ref={canvasRef} aria-hidden="true" />
    <div ref={textRef} className="pdf-text-layer" />
  </>;
}
