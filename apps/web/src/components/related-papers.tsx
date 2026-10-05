'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import Link from 'next/link';
import { ApiError, generateIdempotencyKey, importArxiv, searchRelatedPapers, userErrorMessage,
  type IntakeResponse, type RelatedPaper } from '@/lib/api';
import './related-papers.css';

interface RelatedPapersProps {
  paperId: string;
  documentVersion: string;
  onUnauthorized: () => void;
  disabledReason?: string;
  onBusyChange?: (busy: boolean) => void;
}
type SearchState = 'idle' | 'loading' | 'results' | 'empty' | 'missing' | 'error' | 'cancelled';
type AddState = { result?: IntakeResponse; error?: string };

export function RelatedPapers({ paperId, documentVersion, onUnauthorized, disabledReason, onBusyChange }: RelatedPapersProps) {
  const id = useId();
  const [state, setState] = useState<SearchState>('idle');
  const [papers, setPapers] = useState<RelatedPaper[]>([]);
  const [notice, setNotice] = useState('');
  const [adds, setAdds] = useState<Record<string, AddState>>({});
  const [addingId, setAddingId] = useState<string | null>(null);
  const [searchCooldown, setSearchCooldown] = useState(0);
  const [addCooldown, setAddCooldown] = useState(0);
  const [now, setNow] = useState(Date.now);
  const alive = useRef(false);
  const request = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const adding = useRef(false);
  const keys = useRef(new Map<string, string>());
  const searchButton = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      sequence.current += 1;
      request.current?.abort();
    };
  }, [paperId, documentVersion]);
  useEffect(() => {
    onBusyChange?.(state === 'loading');
    return () => onBusyChange?.(false);
  }, [state, onBusyChange]);
  useEffect(() => {
    if (state === 'cancelled' || ((state === 'error' || state === 'missing') && document.activeElement === document.body)) {
      searchButton.current?.focus();
    }
  }, [state]);
  useEffect(() => {
    const until = Math.max(searchCooldown, addCooldown);
    if (until <= Date.now()) return;
    const timer = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= until) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [searchCooldown, addCooldown]);

  const searchWait = Math.max(0, Math.ceil((searchCooldown - now) / 1000));
  const addWait = Math.max(0, Math.ceil((addCooldown - now) / 1000));
  const expired = (error: unknown) => {
    if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 403)) return false;
    request.current?.abort();
    sequence.current += 1;
    keys.current.clear();
    setPapers([]);
    setAdds({});
    setState('error');
    setNotice('Please sign in again before continuing.');
    onUnauthorized();
    return true;
  };

  const search = async () => {
    if (disabledReason || request.current || adding.current || Date.now() < searchCooldown) return;
    const controller = new AbortController();
    const current = ++sequence.current;
    request.current = controller;
    setPapers([]);
    setNotice('');
    setState('loading');
    try {
      const response = await searchRelatedPapers(paperId, controller.signal);
      if (!alive.current || current !== sequence.current || controller.signal.aborted) return;
      setPapers(response.papers);
      setState(response.papers.length ? 'results' : 'empty');
    } catch (error) {
      if (!alive.current || current !== sequence.current || controller.signal.aborted) return;
      if (expired(error)) return;
      setNotice(userErrorMessage(error, 'Related papers could not be found. Please search again.'));
      setState(error instanceof ApiError && error.code === 'DISCOVERY_METADATA_MISSING' ? 'missing' : 'error');
      if (error instanceof ApiError && error.retryAfter) {
        setNow(Date.now());
        setSearchCooldown(Date.now() + error.retryAfter * 1000);
      }
    } finally {
      if (current === sequence.current) request.current = null;
    }
  };
  const cancelSearch = () => {
    sequence.current += 1;
    request.current?.abort();
    request.current = null;
    setState('cancelled');
  };
  const add = async (paper: RelatedPaper) => {
    if (adding.current || Date.now() < addCooldown || adds[paper.arxiv_id]?.result) return;
    let key = keys.current.get(paper.arxiv_id);
    if (!key) {
      key = generateIdempotencyKey();
      keys.current.set(paper.arxiv_id, key);
    }
    adding.current = true;
    setAddingId(paper.arxiv_id);
    setAdds(previous => ({ ...previous, [paper.arxiv_id]: {} }));
    try {
      const result = await importArxiv(paper.arxiv_id, key);
      if (!alive.current) return;
      setAdds(previous => ({ ...previous, [paper.arxiv_id]: { result } }));
    } catch (error) {
      if (!alive.current || expired(error)) return;
      setAdds(previous => ({ ...previous, [paper.arxiv_id]: { error: userErrorMessage(error,
        'The Add outcome could not be confirmed. Retry Add using the same request.') } }));
      if (error instanceof ApiError && error.retryAfter) {
        setNow(Date.now());
        setAddCooldown(Date.now() + error.retryAfter * 1000);
      }
    } finally {
      adding.current = false;
      if (alive.current) setAddingId(null);
    }
  };

  const status = state === 'loading' ? 'Finding related papers from metadata…' :
    state === 'results' ? `${papers.length} metadata-based recommendations. Nothing is added until you choose Add.` :
    state === 'empty' ? 'No related papers were returned.' :
    state === 'cancelled' ? 'Search cancelled. Nothing was added to Library.' : '';
  return <section className="related-papers" aria-labelledby={`${id}-heading`}>
    <div className="related-heading">
      <h3 id={`${id}-heading`}>Related papers</h3>
      <button ref={searchButton} type="button" className="btn btn-secondary"
        aria-describedby={`${id}-note`} disabled={Boolean(disabledReason) || state === 'loading' || addingId !== null || searchWait > 0}
        onClick={() => { void search(); }}>{state === 'idle' ? 'Related papers' : state === 'loading' ? 'Searching…' : 'Search again'}</button>
    </div>
    <p id={`${id}-note`} className="related-note">Based on titles and abstracts, not PDF evidence. Add to Library is a separate choice.</p>
    {disabledReason && <p className="related-note">{disabledReason}</p>}
    <p className="related-status" role="status">{status}</p>
    {state === 'loading' && <button type="button" className="btn btn-secondary" onClick={cancelSearch}>Cancel search</button>}
    {(state === 'error' || state === 'missing') && <p className="related-error" role="alert">{notice}</p>}
    {searchWait > 0 && <p className="related-note">Search again in {searchWait} seconds.</p>}
    {addWait > 0 && <p className="related-note">Retry Add in {addWait} seconds.</p>}
    {state === 'results' && <div className="related-results">{papers.map((paper, index) => {
      const saved = adds[paper.arxiv_id]?.result;
      const error = adds[paper.arxiv_id]?.error;
      const pending = addingId === paper.arxiv_id;
      return <article key={paper.arxiv_id} className="related-card" aria-labelledby={`${id}-paper-${index}`}>
        <h4 id={`${id}-paper-${index}`}>{paper.title}</h4>
        <p className="related-authors">{paper.authors.length ? paper.authors.join(', ') : 'Authors not available'}</p>
        <p className="related-reason">{paper.reason}</p>
        <div className="related-card-actions">
          <a href={paper.arxiv_url} target="_blank" rel="noopener noreferrer" className="related-arxiv">View on arXiv <span className="sr-only">(opens a new tab)</span></a>
          <button type="button" className="btn btn-secondary" disabled={addingId !== null || Boolean(saved) || addWait > 0}
            onClick={() => { void add(paper); }}>{pending ? 'Adding…' : saved ? 'In Library' : error ? 'Retry Add' : 'Add to Library'}</button>
        </div>
        {error && <p className="related-error" role="alert">{error}</p>}
        {saved && <div className="related-saved" role="status">
          <p>{saved.stage === 'ready' ? 'In Library · Ready to read' : saved.stage === 'failed' ?
            'In Library · Processing needs attention' : saved.stage === 'queued' ?
              'Saved to Library · Waiting for processing' : 'In Library · Preparation not complete'}</p>
          <Link href={`/library/${encodeURIComponent(saved.paper_id)}`}>View in Library</Link>
        </div>}
      </article>;
    })}</div>}
  </section>;
}
