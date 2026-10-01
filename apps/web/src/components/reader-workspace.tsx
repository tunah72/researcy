'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import type { PaperDetailResponse, ReaderDocument } from '@/lib/api';
import { PdfReader } from './pdf-reader';
import './reader.css';

export function ReaderWorkspace({ paper, source }: { paper: PaperDetailResponse; source: ReaderDocument }) {
  const [supported, setSupported] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const resize = () => setSupported(window.innerWidth >= 1024);
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  return <div className="reader-workspace">
    <header className="reader-header">
      <Link href="/library" className="btn btn-secondary">Back to Library</Link>
      <div className="reader-title"><span className="reader-eyebrow">Original document</span>
        <h1>{paper.title || 'Untitled Document'}</h1>
      </div>
      <a className="btn btn-primary" href={source.pdf_url + '?download=1'}>Download PDF</a>
    </header>
    <main id="main-content" className="reader-main">
      {!supported ? <section className="reader-small-boundary" aria-labelledby="reader-size-heading">
        <span className="reader-eyebrow">A little more room to read</span>
        <h2 id="reader-size-heading">Open Reader on a larger screen.</h2>
        <p>The PDF and Discussion workspace needs a viewport at least 1024 pixels wide. You can still download the original PDF or return to Library.</p>
      </section> : <div className="reader-panes">
        <PdfReader source={source} page={page} onPageChange={setPage} />
        <aside className="reader-discussion" aria-labelledby="reader-discussion-heading">
          <div className="reader-discussion-heading"><span className="reader-eyebrow">Read with evidence</span>
            <h2 id="reader-discussion-heading">Discussion</h2>
          </div>
          <div className="reader-discussion-scroll">
            <p className="reader-discussion-intro">The original is open on the left. Discussion will stay scoped to this paper and its immutable document version.</p>
          </div>
        </aside>
      </div>}
    </main>
  </div>;
}
