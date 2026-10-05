'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import Link from 'next/link';
import { ApiError, fetchPapers, getResearchDirections, streamResearchDirections, userErrorMessage,
  type Paper, type ResearchDraft, type ResearchIdea, type ResolvedCitation } from '@/lib/api';

interface ResearchDirectionsProps {
  paperId: string;
  documentVersion: string;
  runId: string | null;
  disabledReason?: string;
  onRunChange: (runId: string | null) => void;
  onBusyChange: (busy: boolean) => void;
  onUnauthorized: () => void;
  onCitation: (citation: ResolvedCitation, button: HTMLButtonElement, runId: string) => void;
  activeCitationId?: string | null;
  evidence?: React.ReactNode;
}
type State = 'idle' | 'restoring' | 'streaming' | 'completed' | 'refusal' | 'failed' | 'interrupted' | 'pending';

export function ResearchDirections({ paperId, documentVersion, runId, disabledReason, onRunChange,
  onBusyChange, onUnauthorized, onCitation, activeCitationId, evidence }: ResearchDirectionsProps) {
  const id = useId();
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState('');
  const [state, setState] = useState<State>('idle');
  const [drafts, setDrafts] = useState<ResearchDraft[]>([]);
  const [ideas, setIdeas] = useState<ResearchIdea[]>([]);
  const [notice, setNotice] = useState('');
  const [reloadRevision, setReloadRevision] = useState(0);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [now, setNow] = useState(Date.now);
  const alive = useRef(false);
  const librarySequence = useRef(0);
  const request = useRef<AbortController | null>(null);
  const knownRun = useRef<string | null>(null);
  const generateButton = useRef<HTMLButtonElement | null>(null);
  const focusAfterCancel = useRef(false);

  const unauthorized = (error: unknown) => {
    if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 403)) return false;
    request.current?.abort();
    setPapers([]); setSelected([]); setIdeas([]); setDrafts([]);
    onUnauthorized();
    return true;
  };
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; librarySequence.current++; request.current?.abort(); onBusyChange(false); };
  }, [onBusyChange]);
  useEffect(() => {
    if (cooldownUntil <= Date.now()) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= cooldownUntil) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownUntil]);
  useEffect(() => {
    if (focusAfterCancel.current && state !== 'streaming') {
      focusAfterCancel.current = false;
      generateButton.current?.focus();
    }
  }, [state]);
  useEffect(() => {
    if (knownRun.current === runId) return;
    request.current?.abort();
    request.current = null;
    onBusyChange(Boolean(runId));
    setIdeas([]); setDrafts([]); setNotice('');
    if (!runId) { setState('idle'); knownRun.current = null; return; }
    knownRun.current = runId;
    const controller = new AbortController();
    request.current = controller;
    setState('restoring');
    void getResearchDirections(paperId, runId, controller.signal).then(snapshot => {
      if (!alive.current || controller.signal.aborted || request.current !== controller) return;
      if (snapshot.document_version !== documentVersion) throw new Error('Saved directions have a different active version.');
      setSelected(snapshot.sources.slice(1).map(source => source.paper_id));
      setIdeas(snapshot.ideas); setDrafts(snapshot.draft_ideas);
      setState(snapshot.state === 'running' ? 'pending' : snapshot.error?.code === 'RESEARCH_INSUFFICIENT_EVIDENCE' ? 'refusal' : snapshot.state);
      onBusyChange(snapshot.state === 'running');
      if (snapshot.error) setNotice(userErrorMessage(new ApiError(500, snapshot.error.code, ''),
        'The saved directions could not be completed. Choose a new selection to try again.'));
    }).catch(error => {
      if (!alive.current || controller.signal.aborted || unauthorized(error)) return;
      setState('failed');
      onBusyChange(false);
      setNotice('These saved directions are unavailable for the active document. No citation is shown.');
    }).finally(() => { if (request.current === controller) request.current = null; });
    return () => { if (request.current === controller) controller.abort(); };
  }, [paperId, documentVersion, runId, reloadRevision, onBusyChange, onUnauthorized]);

  const loadLibrary = async () => {
    const sequence = ++librarySequence.current;
    setSelectorOpen(true); setLibraryLoading(true); setLibraryError('');
    try {
      const result = await fetchPapers();
      if (!alive.current || sequence !== librarySequence.current) return;
      const candidates = result.papers.filter(paper => paper.paper_id !== paperId);
      setPapers(candidates);
      setSelected(current => current.filter(paper => candidates.some(candidate => candidate.paper_id === paper && candidate.stage === 'ready')));
    } catch (error) {
      if (!alive.current || sequence !== librarySequence.current || unauthorized(error)) return;
      setLibraryError('Library could not be loaded. Refresh the selection to try again.');
    } finally { if (alive.current && sequence === librarySequence.current) setLibraryLoading(false); }
  };
  const generate = async () => {
    if (state === 'pending' || disabledReason || libraryError || request.current || selected.length < 1 || selected.length > 3 || Date.now() < cooldownUntil) return;
    const controller = new AbortController();
    request.current = controller;
    knownRun.current = null;
    onRunChange(null);
    setState('streaming'); setDrafts([]); setIdeas([]); setNotice('');
    onBusyChange(true);
    try {
      await streamResearchDirections(paperId, selected, event => {
        if (!alive.current || controller.signal.aborted || request.current !== controller) return;
        if (event.event === 'direction.delta') setDrafts(current => [...current, event.data.idea]);
        else if (event.event === 'direction.completed') {
          setDrafts([]); setIdeas(event.data.ideas); setState('completed');
        } else if (event.event === 'direction.failed') {
          setState(event.data.code === 'RESEARCH_INSUFFICIENT_EVIDENCE' ? 'refusal' : event.data.code === 'RESEARCH_INTERRUPTED' ? 'interrupted' : 'failed');
          setNotice(userErrorMessage(new ApiError(500, event.data.code, ''), 'Research directions could not be completed. Submit a new request to retry.'));
        }
        // Citation events remain provisional until the verified completed payload.
      }, reserved => {
        if (!alive.current || controller.signal.aborted || request.current !== controller) return;
        knownRun.current = reserved; onRunChange(reserved);
      }, controller.signal);
    } catch (error) {
      if (!alive.current || controller.signal.aborted || unauthorized(error)) return;
      setIdeas([]);
      setState(error instanceof ApiError && error.code === 'RESEARCH_INTERRUPTED' ? 'interrupted' : 'failed');
      setNotice(userErrorMessage(error, 'Research directions could not be completed. Reload their saved state or submit a new request.'));
      if (error instanceof ApiError && error.retryAfter) { setNow(Date.now()); setCooldownUntil(Date.now() + error.retryAfter * 1000); }
    } finally {
      if (request.current === controller) {
        request.current = null;
        if (alive.current) onBusyChange(false);
      }
    }
  };
  const cancel = () => {
    request.current?.abort(); request.current = null;
    setIdeas([]); setState('interrupted');
    setNotice('Cancelled. Displayed drafts are unaccepted. Reload the saved run to check its persisted outcome.');
    onBusyChange(false);
    focusAfterCancel.current = true;
  };
  const reload = () => { knownRun.current = null; setReloadRevision(revision => revision + 1); };
  const wait = Math.max(0, Math.ceil((cooldownUntil - now) / 1000));
  const busy = state === 'streaming' || state === 'restoring' || state === 'pending';
  const displayed = state === 'completed' ? ideas : drafts;
  return <section className="research-directions" aria-labelledby={`${id}-heading`}>
    <div className="research-heading"><h3 id={`${id}-heading`}>Research directions</h3>
      <button type="button" className="btn btn-secondary" disabled={Boolean(disabledReason) || busy}
        aria-expanded={selectorOpen} aria-controls={`${id}-selection`} onClick={() => { void loadLibrary(); }}>Select research papers</button></div>
    <p className="research-note">Choose one to three ready Library papers. Premises use PDF evidence; directions and methods are hypotheses, not paper claims.</p>
    {disabledReason && <p className="research-note">{disabledReason}</p>}
    {selectorOpen && <div id={`${id}-selection`} className="research-selection">
      {libraryLoading ? <p role="status">Loading eligible Library papers…</p> : <>
        {libraryError && <p role="alert">{libraryError}</p>}
        <fieldset disabled={busy || Boolean(disabledReason)} aria-describedby={`${id}-selection-limit`}><legend>Select related sources · {selected.length}/3</legend>
          {papers.map(paper => <label key={paper.paper_id} className="research-source">
            <input type="checkbox" checked={selected.includes(paper.paper_id)}
              disabled={paper.stage !== 'ready' || (selected.length >= 3 && !selected.includes(paper.paper_id))}
              onChange={event => setSelected(current => event.target.checked ? [...current, paper.paper_id] : current.filter(id => id !== paper.paper_id))} />
            <span>{paper.title || 'Untitled Document'}<span className="research-source-state">{paper.stage === 'ready' ? 'Ready' :
              paper.stage === 'queued' ? 'Waiting for processing' : paper.stage === 'failed' ? 'Processing needs attention · check Library' : 'Preparing for reading'}</span></span>
          </label>)}
        </fieldset>
        <p id={`${id}-selection-limit`} className="research-note">Select at most three related papers. Deselect one before choosing another. Check <Link href="/library">Library</Link> for preparation or recovery.</p>
        {!papers.some(paper => paper.stage === 'ready') && <p>Add another paper to <Link href="/library">Library</Link> and wait for processing, then refresh this selection.</p>}
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => { void loadLibrary(); }}>Refresh Library selection</button>
      </>}
      <button ref={generateButton} type="button" className="btn btn-primary"
        disabled={busy || Boolean(disabledReason) || Boolean(libraryError) || libraryLoading || selected.length < 1 || selected.length > 3 || wait > 0}
        onClick={() => { void generate(); }}>Generate directions</button>
    </div>}
    <p role="status" className="research-status">{state === 'streaming' ? 'Preparing evidence-linked research hypotheses. Drafts are not accepted yet.' :
      state === 'restoring' ? 'Loading the saved research run…' : state === 'pending' ? 'The saved run is still pending. Reload its saved state; no generation is resumed.' :
      state === 'completed' ? `${ideas.length} accepted research ${ideas.length === 1 ? 'direction' : 'directions'}. Hypotheses remain proposals.` : ''}</p>
    {state === 'streaming' && <button type="button" className="btn btn-secondary" onClick={cancel}>Cancel directions</button>}
    {notice && <p className="research-notice" role={state === 'refusal' || state === 'interrupted' ? 'status' : 'alert'}>{notice}</p>}
    {wait > 0 && <p className="research-note">Try again in {wait} seconds.</p>}
    {runId && state !== 'streaming' && state !== 'restoring' && state !== 'completed' && <button type="button" className="btn btn-secondary" onClick={reload}>Reload saved directions</button>}
    {displayed.map((idea, index) => <article key={index} className="research-idea" aria-labelledby={`${id}-idea-${index}`}>
      <h4 id={`${id}-idea-${index}`}>Direction {index + 1}{state !== 'completed' && <span className="research-draft"> · Unaccepted draft</span>}</h4>
      <dl><dt>{state === 'completed' ? 'Observed gap · evidence-backed premise' : 'Observed gap — unaccepted premise'}</dt><dd>{idea.observed_gap}</dd>
        <dt>Proposed direction — hypothesis</dt><dd>{idea.proposed_direction}</dd>
        <dt>Possible method — hypothesis</dt><dd>{idea.possible_method}</dd></dl>
      {state === 'completed' && runId && <div className="research-citations">{ideas[index].premise_citations.map((citation, citationIndex) =>
        <button type="button" key={citation.citation_id} id={`citation-${citation.citation_id}`} className="btn btn-citation"
          aria-label={`Premise citation ${citationIndex + 1}`} aria-describedby={`${id}-idea-${index}`}
          aria-expanded={activeCitationId === citation.citation_id} aria-controls={activeCitationId === citation.citation_id ? 'evidence-card' : undefined}
          onClick={event => onCitation(citation, event.currentTarget, runId)}>{citation.source_ref} · page {citation.page}</button>)}</div>}
      {state === 'completed' && ideas[index].premise_citations.some(citation => citation.citation_id === activeCitationId) && evidence}
    </article>)}
    {evidence && !ideas.some(idea => idea.premise_citations.some(citation => citation.citation_id === activeCitationId)) && evidence}
  </section>;
}
