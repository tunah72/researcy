'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ApiError, getCitation, listMessages, type PaperDetailResponse, type ReaderDocument, type ResolvedCitation } from '@/lib/api';
import { Discussion } from './discussion';
import { PdfReader } from './pdf-reader';
import './reader.css';

export function ReaderWorkspace({ paper, source }: { paper: PaperDetailResponse; source: ReaderDocument }) {
  const [supported, setSupported] = useState(false);
  const [page, setPage] = useState(1);
  const [citation, setCitation] = useState<ResolvedCitation | null>(null);
  const [evidenceState, setEvidenceState] = useState<'closed' | 'loading' | 'open' | 'unavailable'>('closed');
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const evidenceRef = useRef<HTMLElement | null>(null);
  const focusedCitation = useRef<string | null>(null);

  const clearPrivate = useCallback(() => {
    request.current?.abort();
    setCitation(null);
    setEvidenceState('closed');
    window.location.assign('/library');
  }, []);

  const loadCitation = useCallback(async (id: string, button: HTMLButtonElement | null, updateUrl: boolean) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    trigger.current = button;
    setCitation(null);
    setSelectedCitationId(id);
    focusedCitation.current = null;
    setEvidenceState('loading');
    try {
      const result = await getCitation(id, controller.signal);
      if (controller.signal.aborted) return;
      const accepted = result.citation;
      if (accepted.paper_id !== paper.paper_id || accepted.document_version !== source.document_version ||
          !Number.isInteger(accepted.page) || accepted.page < 1 || accepted.page > source.pages.length) {
        setEvidenceState('unavailable');
        return;
      }
      if (!updateUrl) {
        const url = new URL(window.location.href);
        const selectedConversation = url.searchParams.get('conversation');
        const urlPage = url.searchParams.get('page');
        if (!selectedConversation || (urlPage !== null && Number(urlPage) !== accepted.page)) {
          setEvidenceState('unavailable');
          return;
        }
        let after: string | null = null;
        let belongs = false;
        do {
          const messages = await listMessages(selectedConversation, after, controller.signal);
          if (controller.signal.aborted) return;
          belongs = messages.messages.some(message => message.citations?.some(item => item.citation_id === id));
          after = messages.next_after;
        } while (!belongs && after);
        if (!belongs) { setEvidenceState('unavailable'); return; }
      }
      if (updateUrl) {
        const url = new URL(window.location.href);
        url.searchParams.set('document_version', accepted.document_version);
        url.searchParams.set('page', String(accepted.page));
        url.searchParams.set('citation', accepted.citation_id);
        window.history.pushState(null, '', url);
      }
      setPage(accepted.page);
      setCitation(accepted);
      setEvidenceState('open');
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 401) { clearPrivate(); return; }
      setEvidenceState('unavailable');
    }
  }, [paper.paper_id, source.document_version, source.pages.length, clearPrivate]);

  const closeEvidence = useCallback(() => {
    request.current?.abort();
    setCitation(null);
    setSelectedCitationId(null);
    setEvidenceState('closed');
    const url = new URL(window.location.href);
    url.searchParams.delete('citation');
    window.history.replaceState(null, '', url);
    const currentTrigger = trigger.current?.isConnected ? trigger.current :
      citation ? document.getElementById(`citation-${citation.citation_id}`) : null;
    currentTrigger?.focus();
  }, [citation]);

  useEffect(() => {
    const resize = () => setSupported(window.innerWidth >= 1024);
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  useEffect(() => {
    const restore = () => {
      request.current?.abort();
      setCitation(null);
      setSelectedCitationId(null);
      setEvidenceState('closed');
      const url = new URL(window.location.href);
      const version = url.searchParams.get('document_version');
      const id = url.searchParams.get('citation');
      if (version && version !== source.document_version) { setEvidenceState('unavailable'); return; }
      const next = Number(url.searchParams.get('page') || '1');
      if (!Number.isInteger(next) || next < 1 || next > source.pages.length) {
        setEvidenceState('unavailable');
        return;
      }
      setPage(next);
      if (id) void loadCitation(id, null, false);
    };
    restore();
    window.addEventListener('popstate', restore);
    return () => { request.current?.abort(); window.removeEventListener('popstate', restore); };
  }, [source.document_version, source.pages.length, loadCitation]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && evidenceState !== 'closed') { event.preventDefault(); closeEvidence(); }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [evidenceState, closeEvidence]);

  const navigate = (value: number) => {
    setPage(value);
    const url = new URL(window.location.href);
    url.searchParams.set('page', String(value));
    url.searchParams.set('document_version', source.document_version);
    window.history.replaceState(null, '', url);
  };

  const focusEvidence = useCallback((id: string) => {
    if (id === citation?.citation_id && id !== focusedCitation.current && evidenceRef.current) {
      evidenceRef.current.focus();
      focusedCitation.current = id;
    }
  }, [citation?.citation_id]);

  const evidence = evidenceState !== 'closed' ? <section id="evidence-card" className="reader-evidence-card"
    ref={evidenceRef} tabIndex={-1} role="region" aria-labelledby="evidence-heading">
    <div className="reader-evidence-heading"><h2 id="evidence-heading">Evidence{citation ? ` · page ${citation.page}` : ''}</h2>
      <button type="button" className="btn btn-secondary" onClick={closeEvidence}>Close evidence</button></div>
    {evidenceState === 'loading' ? <p role="status">Opening accepted evidence…</p> : evidenceState === 'unavailable' ?
      <p role="alert">This evidence is unavailable for the open document. No approximate location is shown.</p> : citation ?
        <><p>{paper.title || 'Untitled Document'}</p><blockquote>{citation.evidence_quote}</blockquote>
          {citation.section && <p>{citation.section}</p>}</> : null}
  </section> : null;

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
        <div className="reader-document-pane">
          <PdfReader source={source} page={page} onPageChange={navigate} citation={citation} onCitationReady={focusEvidence} />
        </div>
        <Discussion paperId={paper.paper_id} title={paper.title} documentVersion={source.document_version}
          onCitation={(accepted, button) => { void loadCitation(accepted.citation_id, button, true); }}
          activeCitationId={selectedCitationId} evidence={evidence}
          canCreateConversation={source.document_version === paper.active_version_id} onUnauthorized={clearPrivate} />
      </div>}
    </main>
  </div>;
}
