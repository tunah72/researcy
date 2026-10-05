'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ApiError, fetchPaperDetail, getCitation, getResearchDirections, listMessages,
  type PaperDetailResponse, type ReaderDocument, type ResolvedCitation } from '@/lib/api';
import { Discussion } from './discussion';
import { PdfReader } from './pdf-reader';
import { RelatedPapers } from './related-papers';
import { ResearchDirections } from './research-directions';
import './reader.css';

export function ReaderWorkspace({ paper, source }: { paper: PaperDetailResponse; source: ReaderDocument }) {
  const [supported, setSupported] = useState(false);
  const [displayed, setDisplayed] = useState({ paper, source });
  const [page, setPage] = useState(1);
  const [citation, setCitation] = useState<ResolvedCitation | null>(null);
  const [evidenceState, setEvidenceState] = useState<'closed' | 'loading' | 'open' | 'unavailable'>('closed');
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const [researchRun, setResearchRun] = useState<string | null>(null);
  const [evidenceRun, setEvidenceRun] = useState<string | null>(null);
  const [readerBusy, setReaderBusy] = useState(false);
  const [relatedBusy, setRelatedBusy] = useState(false);
  const [researchBusy, setResearchBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const evidenceRef = useRef<HTMLElement | null>(null);
  const focusedCitation = useRef<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const focusAfterReturn = useRef(false);
  useEffect(() => {
    if (focusAfterReturn.current && displayed.paper.paper_id === paper.paper_id &&
        displayed.source.document_version === source.document_version) {
      focusAfterReturn.current = false;
      headingRef.current?.focus();
    }
  }, [displayed.paper.paper_id, displayed.source.document_version, paper.paper_id, source.document_version]);

  const clearPrivate = useCallback(() => {
    request.current?.abort();
    setCitation(null); setEvidenceState('closed');
    window.location.assign('/library');
  }, []);
  const resolveDocument = useCallback(async (paperId: string, version: string, controller: AbortController) => {
    if (paperId === paper.paper_id && version === source.document_version) return { paper, source };
    const detail = await fetchPaperDetail(paperId, version);
    if (controller.signal.aborted) return null;
    if (detail.paper_id !== paperId || !detail.reader || detail.reader.document_version !== version) {
      throw new Error('Requested immutable document is unavailable.');
    }
    return { paper: detail, source: detail.reader };
  }, [paper, source]);
  const loadCitation = useCallback(async (id: string, button: HTMLButtonElement | null, updateUrl: boolean, run: string | null) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller; trigger.current = button;
    setCitation(null); setSelectedCitationId(id); setEvidenceRun(run);
    focusedCitation.current = null; setEvidenceState('loading');
    try {
      const { citation: accepted } = await getCitation(id, controller.signal);
      if (controller.signal.aborted) return;
      const url = new URL(window.location.href);
      let researchMember = false;
      if (run) {
        const result = await getResearchDirections(paper.paper_id, run, controller.signal);
        if (controller.signal.aborted) return;
        researchMember = result.state === 'completed' && result.document_version === source.document_version &&
          result.ideas.some(idea => idea.premise_citations.some(item => item.citation_id === id &&
            item.paper_id === accepted.paper_id && item.document_version === accepted.document_version));
        if (!researchMember && updateUrl) throw new Error('Not an accepted premise of this run.');
      }
      if (!researchMember) {
        setEvidenceRun(null);
        if (accepted.paper_id !== paper.paper_id || accepted.document_version !== source.document_version) {
          throw new Error('Not evidence for the active Discussion.');
        }
        const conversation = url.searchParams.get('conversation');
        if (!conversation) throw new Error('Conversation unavailable.');
        let after: string | null = null, belongs = false;
        do {
          const result = await listMessages(conversation, after, controller.signal);
          if (controller.signal.aborted) return;
          belongs = result.messages.some(message => message.citations?.some(item => item.citation_id === id));
          after = result.next_after;
        } while (!belongs && after);
        if (!belongs) throw new Error('Not an accepted Discussion citation.');
      }
      const target = await resolveDocument(accepted.paper_id, accepted.document_version, controller);
      if (!target || controller.signal.aborted) return;
      if (!Number.isInteger(accepted.page) || accepted.page < 1 || accepted.page > target.source.pages.length) {
        throw new Error('Exact page unavailable.');
      }
      if (!updateUrl && ((url.searchParams.has('page') && Number(url.searchParams.get('page')) !== accepted.page) ||
          (url.searchParams.has('pdf_paper') && url.searchParams.get('pdf_paper') !== accepted.paper_id) ||
          (url.searchParams.has('pdf_version') && url.searchParams.get('pdf_version') !== accepted.document_version) ||
          (accepted.paper_id !== paper.paper_id && (!url.searchParams.has('pdf_paper') || !url.searchParams.has('pdf_version'))))) {
        throw new Error('URL evidence identity mismatch.');
      }
      if (updateUrl) {
        url.searchParams.set('document_version', source.document_version);
        url.searchParams.set('page', String(accepted.page)); url.searchParams.set('citation', id);
        if (run) url.searchParams.set('research_run', run);
        if (accepted.paper_id !== paper.paper_id || accepted.document_version !== source.document_version) {
          url.searchParams.set('pdf_paper', accepted.paper_id); url.searchParams.set('pdf_version', accepted.document_version);
        } else { url.searchParams.delete('pdf_paper'); url.searchParams.delete('pdf_version'); }
        window.history.pushState(null, '', url);
      }
      setDisplayed(target); setPage(accepted.page); setCitation(accepted); setEvidenceState('open');
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) { clearPrivate(); return; }
      setEvidenceState('unavailable');
    }
  }, [paper.paper_id, source.document_version, clearPrivate, resolveDocument]);

  const closeEvidence = useCallback(() => {
    request.current?.abort(); setCitation(null); setSelectedCitationId(null); setEvidenceState('closed');
    const url = new URL(window.location.href); url.searchParams.delete('citation');
    window.history.replaceState(null, '', url);
    const current = trigger.current?.isConnected ? trigger.current : citation ? document.getElementById(`citation-${citation.citation_id}`) : null;
    current?.focus();
  }, [citation]);
  useEffect(() => {
    const resize = () => {
      const allowed = window.innerWidth >= 1024;
      setSupported(allowed);
      if (!allowed) {
        request.current?.abort(); setCitation(null); setSelectedCitationId(null); setEvidenceState('closed');
      }
    };
    resize(); window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  useEffect(() => {
    if (!supported) return;
    const restore = () => {
      request.current?.abort(); setCitation(null); setSelectedCitationId(null); setEvidenceState('closed'); setEvidenceRun(null);
      if (window.innerWidth < 1024) return;
      const url = new URL(window.location.href), run = url.searchParams.get('research_run');
      setResearchRun(run);
      if (url.searchParams.get('document_version') && url.searchParams.get('document_version') !== source.document_version) {
        setEvidenceState('unavailable'); return;
      }
      const id = url.searchParams.get('citation');
      if (id) { void loadCitation(id, null, false, run); return; }
      const controller = new AbortController(); request.current = controller;
      const paperHint = url.searchParams.get('pdf_paper'), versionHint = url.searchParams.get('pdf_version');
      if (Boolean(paperHint) !== Boolean(versionHint)) { setEvidenceState('unavailable'); return; }
      void resolveDocument(paperHint || paper.paper_id, versionHint || source.document_version, controller).then(target => {
        if (!target || controller.signal.aborted) return;
        const next = Number(url.searchParams.get('page') || '1');
        if (!Number.isInteger(next) || next < 1 || next > target.source.pages.length) throw new Error('Page unavailable.');
        setDisplayed(target); setPage(next);
      }).catch(error => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) clearPrivate();
        else setEvidenceState('unavailable');
      });
    };
    restore(); window.addEventListener('popstate', restore);
    return () => { request.current?.abort(); window.removeEventListener('popstate', restore); };
  }, [paper, source, loadCitation, resolveDocument, clearPrivate, supported]);
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
    if (citation && value !== citation.page) {
      request.current?.abort();
      setCitation(null); setSelectedCitationId(null); setEvidenceState('closed'); setEvidenceRun(null);
      focusedCitation.current = null;
      url.searchParams.delete('citation');
    }
    url.searchParams.set('page', String(value)); url.searchParams.set('document_version', source.document_version);
    window.history.replaceState(null, '', url);
  };
  const focusEvidence = useCallback((id: string) => {
    if (id === citation?.citation_id && id !== focusedCitation.current && evidenceRef.current) {
      evidenceRef.current.focus(); focusedCitation.current = id;
    }
  }, [citation?.citation_id]);
  const changeRun = useCallback((run: string | null) => {
    setResearchRun(run);
    const url = new URL(window.location.href);
    if (run === null && evidenceRun) {
      request.current?.abort(); trigger.current = null;
      setCitation(null); setSelectedCitationId(null); setEvidenceState('closed'); setEvidenceRun(null);
      url.searchParams.delete('citation');
    }
    if (run) url.searchParams.set('research_run', run); else url.searchParams.delete('research_run');
    window.history.replaceState(null, '', url);
  }, [evidenceRun]);
  const returnActive = () => {
    focusAfterReturn.current = true;
    closeEvidence(); setDisplayed({ paper, source }); setPage(1);
    const url = new URL(window.location.href);
    url.searchParams.delete('pdf_paper'); url.searchParams.delete('pdf_version'); url.searchParams.set('page', '1');
    window.history.pushState(null, '', url);
  };
  const evidence = evidenceState !== 'closed' ? <section id="evidence-card" className="reader-evidence-card"
    ref={evidenceRef} tabIndex={-1} role="region" aria-labelledby="evidence-heading">
    <div className="reader-evidence-heading"><h2 id="evidence-heading">Evidence{citation ? ` · page ${citation.page}` : ''}</h2>
      <button type="button" className="btn btn-secondary" onClick={closeEvidence}>Close evidence</button></div>
    {evidenceState === 'loading' ? <p role="status">Opening accepted evidence…</p> : evidenceState === 'unavailable' ?
      <p role="alert">This evidence is unavailable for the requested document. No approximate location is shown.</p> : citation ?
        <><p>{displayed.paper.title || 'Untitled Document'}</p><blockquote>{citation.evidence_quote}</blockquote>
          {citation.section && <p>{citation.section}</p>}</> : null}
  </section> : null;
  const inactive = source.document_version !== paper.active_version_id || paper.stage !== 'ready';
  const nonActivePdf = displayed.paper.paper_id !== paper.paper_id || displayed.source.document_version !== source.document_version;
  return <div className="reader-workspace">
    <header className="reader-header">
      <Link href="/library" className="btn btn-secondary">Back to Library</Link>
      <div className="reader-title"><span className="reader-eyebrow">Original document{nonActivePdf ? ' · Selected evidence source' : ''}</span>
        <h1 ref={headingRef} tabIndex={-1}>{displayed.paper.title || 'Untitled Document'}</h1></div>
      {nonActivePdf && <button type="button" className="btn btn-secondary" onClick={returnActive}>Return to active paper</button>}
      <a className="btn btn-primary" href={displayed.source.pdf_url + '?download=1'}>Download PDF</a>
    </header>
    <main id="main-content" className="reader-main">
      {!supported ? <section className="reader-small-boundary" aria-labelledby="reader-size-heading">
        <span className="reader-eyebrow">A little more room to read</span><h2 id="reader-size-heading">Open Reader on a larger screen.</h2>
        <p>The PDF and Discussion workspace needs a viewport at least 1024 pixels wide. You can still download the original PDF or return to Library.</p>
      </section> : <div className="reader-panes">
        <div className="reader-document-pane"><PdfReader key={`${displayed.paper.paper_id}:${displayed.source.document_version}`}
          source={displayed.source} page={page} onPageChange={navigate}
          citation={citation} onCitationReady={focusEvidence} /></div>
        <Discussion paperId={paper.paper_id} title={paper.title} documentVersion={source.document_version}
          onCitation={(accepted, button) => { void loadCitation(accepted.citation_id, button, true, null); }}
          activeCitationId={selectedCitationId} evidence={evidenceRun ? null : evidence} onBusyChange={setReaderBusy}
          generationDisabled={researchBusy || relatedBusy ? 'Wait for the current research action to finish before asking a question.' : undefined}
          secondaryActions={<>
            <RelatedPapers key={`${paper.paper_id}:${source.document_version}:${paper.active_version_id}:${paper.stage}`}
              paperId={paper.paper_id} documentVersion={source.document_version} onUnauthorized={clearPrivate} onBusyChange={setRelatedBusy}
              disabledReason={inactive ? 'Related papers is available only after the active document is ready.' :
                researchBusy || readerBusy ? 'Wait for the current evidence-linked generation to finish.' : undefined} />
            <ResearchDirections key={`${paper.paper_id}:${source.document_version}`} paperId={paper.paper_id}
              documentVersion={source.document_version} runId={researchRun} onRunChange={changeRun} onBusyChange={setResearchBusy}
              onUnauthorized={clearPrivate} disabledReason={inactive ? 'Research directions is available only for the ready active document version.' :
                relatedBusy || readerBusy ? 'Wait for the current generation to finish before requesting directions.' : undefined}
              onCitation={(accepted, button, run) => { void loadCitation(accepted.citation_id, button, true, run); }}
              activeCitationId={selectedCitationId} evidence={evidenceRun ? evidence : null} />
          </>} canCreateConversation={source.document_version === paper.active_version_id} onUnauthorized={clearPrivate} />
      </div>}
    </main>
  </div>;
}
