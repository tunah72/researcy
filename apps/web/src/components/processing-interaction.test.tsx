import React from 'react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import LibraryPage from '../app/library/page';

const paper = { paper_id: 'paper-a', title: 'Attention Is All You Need', authors: ['Author'], year: 2017, source: 'upload', stage: 'failed', active_version_id: 'version-a', source_version: null, screening_warning: null, job_id: 'job-a', retry_revision: 0, preparation: { state: 'failed', reason: 'temporary', retryable: true, retry_after_seconds: 0 } };
const user = { id: 'owner-a', email: 'smoke@example.invalid', name: 'Smoke' };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const originalLocation = window.location;
async function settle() { await act(async () => { await Promise.resolve(); await Promise.resolve(); }); }
async function advance(ms: number) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }

beforeEach(() => {
  vi.useFakeTimers();
  document.cookie = 'researcy_csrf=test-csrf';
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  Object.defineProperty(window, 'location', { configurable: true, writable: true, value: { href: '' } });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); Object.defineProperty(window, 'location', { configurable: true, value: originalLocation }); });

it('retries a terminal failure using its persisted revision and displays the accepted delayed state', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) { expect(JSON.parse(String(init?.body))).toEqual({ retry_revision: 0 }); return response({ job_id: 'job-a', paper_id: 'paper-a', document_version: 'version-a', stage: 'validating', status: 'pending', retry_revision: 1, preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 } }, 202); }
    return response({ papers: [paper] });
  });
  vi.stubGlobal('fetch', fetcher); render(<LibraryPage />); await settle();
  fireEvent.click(screen.getByRole('button', { name: /try again/i })); await settle();
  expect(screen.getByRole('link', { name: paper.title })).toBeVisible();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url]) => url === '/api/jobs/job-a/retry')).toBe(true);
});

it('keeps metadata and focused control when background status refresh fails without polling identity', async () => {
  const preparing = { ...paper, stage: 'embedding', preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 } };
  let lists = 0;
  const fetcher = vi.fn(async (url: string) => url === '/api/me' ? response(user) : ++lists === 1 ? response({ papers: [preparing] }) : Promise.reject(new TypeError('offline')));
  vi.stubGlobal('fetch', fetcher); render(<LibraryPage />); await settle();
  const link = screen.getByRole('link', { name: paper.title }); link.focus();
  await advance(5000);
  expect(screen.getByRole('link', { name: paper.title })).toBe(link);
  expect(link).toHaveFocus();
  expect(screen.getAllByRole('status').some(el => /status|check/i.test(el.textContent ?? ''))).toBe(true);
  expect(fetcher.mock.calls.filter(([url]) => url === '/api/me')).toHaveLength(1);
  expect(lists).toBe(2);
  await advance(25000); expect(lists).toBe(2);
  await advance(5000); expect(lists).toBe(3);
});

it('pauses background requests while hidden and refreshes when visible', async () => {
  const pending = { ...paper, stage: 'queued', preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 } };
  const fetcher = vi.fn(async (url: string) => response(url === '/api/me' ? user : { papers: [pending] }));
  vi.stubGlobal('fetch', fetcher); render(<LibraryPage />); await settle();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' }); fireEvent(document, new Event('visibilitychange'));
  await advance(15000); expect(fetcher).toHaveBeenCalledTimes(2);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); fireEvent(document, new Event('visibilitychange')); await settle();
  expect(fetcher).toHaveBeenCalledTimes(3);
});

it('clears private metadata on a polling 401', async () => {
  const pending = { ...paper, stage: 'queued', preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 } };
  let lists = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url === '/api/me' ? response(user) : ++lists === 1 ? response({ papers: [pending] }) : response({ code: 'UNAUTHENTICATED', message: 'safe' }, 401)));
  render(<LibraryPage />); await settle(); await advance(5000);
  expect(screen.queryByRole('link', { name: paper.title })).not.toBeInTheDocument();
  expect(window.location.href).toBe('/sign-in?expired=1');
});

it('enforces the server cooldown only on the relevant failed paper', async () => {
  const cooling = { ...paper, preparation: { ...paper.preparation, retry_after_seconds: 10 } };
  const other = { ...paper, paper_id: 'paper-b', job_id: 'job-b', title: 'Other paper' };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => response(url === '/api/me' ? user : { papers: [cooling, other] })));
  render(<LibraryPage />); await settle();
  const retries = screen.getAllByRole('button', { name: /try again/i });
  expect(retries[0]).toBeDisabled(); expect(retries[1]).toBeEnabled();
  await advance(10000); expect(retries[0]).toBeEnabled();
});

it('does not let a stale poll overwrite a newer search and keeps that search on later polls', async () => {
  const pending = { ...paper, stage: 'queued', preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 } };
  const searched = { ...pending, paper_id: 'paper-b', job_id: 'job-b', title: 'Target paper' };
  let finishPoll!: (value: Response) => void;
  let lists = 0;
  const fetcher = vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.includes('?search=Target')) return response({ papers: [searched] });
    if (++lists === 2) return new Promise<Response>(resolve => { finishPoll = resolve; });
    return response({ papers: [pending] });
  });
  vi.stubGlobal('fetch', fetcher); render(<LibraryPage />); await settle(); await advance(5000);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search papers' }), { target: { value: 'Target' } });
  fireEvent.submit(screen.getByRole('search')); await settle();
  expect(screen.getByRole('link', { name: 'Target paper' })).toBeVisible();
  await act(async () => { finishPoll(response({ papers: [pending] })); }); await settle();
  expect(screen.queryByRole('link', { name: paper.title })).not.toBeInTheDocument();
  await advance(5000);
  expect(fetcher.mock.calls.at(-1)?.[0]).toBe('/api/papers?search=Target');
});

it('does not overlap a slow visible status poll', async () => {
  const pending = { ...paper, stage: 'queued', preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 } };
  let lists = 0;
  let finishPoll!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (++lists === 2) return new Promise<Response>(resolve => { finishPoll = resolve; });
    return response({ papers: [pending] });
  }));
  render(<LibraryPage />); await settle(); await advance(15000);
  expect(lists).toBe(2);
  await act(async () => { finishPoll(response({ papers: [pending] })); }); await settle();
  await advance(5000); expect(lists).toBe(3);
});

it('does not poll completed papers or offer a fabricated Reader action', async () => {
  const complete = { ...paper, stage: 'ready', preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } };
  const fetcher = vi.fn(async (url: string) => response(url === '/api/me' ? user : { papers: [complete] }));
  vi.stubGlobal('fetch', fetcher); render(<LibraryPage />); await settle(); await advance(15000);
  expect(screen.getByRole('link', { name: paper.title })).toBeVisible();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /read paper|open reader/i })).not.toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it('does not let an older list response undo an accepted revision retry on another row', async () => {
  const pending = { ...paper, paper_id: 'paper-b', job_id: 'job-b', title: 'Pending paper', stage: 'queued', preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 } };
  let lists = 0;
  let finishPoll!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return response({ job_id: paper.job_id, paper_id: paper.paper_id, document_version: paper.active_version_id, stage: 'validating', status: 'pending', retry_revision: 1, preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 } }, 202);
    if (++lists === 2) return new Promise<Response>(resolve => { finishPoll = resolve; });
    return response({ papers: [paper, pending] });
  }));
  render(<LibraryPage />); await settle(); await advance(5000);
  fireEvent.click(screen.getByRole('button', { name: /try again/i })); await settle();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  await act(async () => { finishPoll(response({ papers: [paper, pending] })); }); await settle();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: paper.title })).toBeVisible();
});

it('resumes status polling after the last polled job fails and a retry is accepted', async () => {
  const pending = { ...paper, stage: 'embedding', preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 } };
  let lists = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return response({ job_id: paper.job_id, paper_id: paper.paper_id, document_version: paper.active_version_id, stage: 'embedding', status: 'pending', retry_revision: 1, preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 } }, 202);
    return response({ papers: [++lists === 1 ? pending : paper] });
  }));
  render(<LibraryPage />); await settle(); await advance(5000);
  fireEvent.click(screen.getByRole('button', { name: /try again/i })); await settle(); await advance(5000);
  expect(lists).toBe(3);
});

it('defers a hidden conflict refresh, retains busy retry, then restores the removed control focus', async () => {
  let reads = 0; let finishRetry!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return new Promise<Response>(resolve => { finishRetry = resolve; });
    return response({ papers: [++reads === 1 ? paper : { ...paper, retry_revision: 1, stage: 'ready', preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } }] });
  }));
  render(<LibraryPage />); await settle();
  const button = screen.getByRole('button', { name: /try again/i }); button.focus(); fireEvent.click(button);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' }); fireEvent(document, new Event('visibilitychange'));
  await act(async () => { finishRetry(response({ code: 'RETRY_REVISION_CONFLICT', message: 'safe' }, 409)); }); await settle();
  expect(button).toBeDisabled(); expect(reads).toBe(1);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); fireEvent(document, new Event('visibilitychange')); await settle();
  expect(reads).toBe(2); expect(screen.getByRole('link', { name: paper.title })).toHaveFocus();
});

it('does not regress a newer canonical same-revision state when an older retry response arrives', async () => {
  let finishRetry!: (value: Response) => void;
  let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return new Promise<Response>(resolve => { finishRetry = resolve; });
    return response({ papers: [++reads === 1 ? paper : { ...paper, retry_revision: 1, stage: 'ready', preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } }] });
  }));
  render(<LibraryPage />); await settle();
  fireEvent.click(screen.getByRole('button', { name: /try again/i }));
  fireEvent.submit(screen.getByRole('search')); await settle();
  await act(async () => { finishRetry(response({ job_id: paper.job_id, paper_id: paper.paper_id, document_version: paper.active_version_id, stage: 'validating', status: 'pending', retry_revision: 1, preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 } }, 202)); }); await settle();
  expect(screen.queryAllByRole('status')).toHaveLength(0);
});

it('restores status polling when sign-out fails and blocks processing mutations while signing out', async () => {
  const pending = { ...paper, paper_id: 'paper-b', job_id: 'job-b', title: 'Pending paper', stage: 'queued', preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 } };
  let reads = 0; let failLogout!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url === '/auth/logout') return new Promise<Response>(resolve => { failLogout = resolve; });
    reads++; return response({ papers: [paper, pending] });
  }));
  render(<LibraryPage />); await settle();
  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' })); await settle();
  expect(screen.getByRole('button', { name: /try again/i })).toBeDisabled();
  await act(async () => { failLogout(response({ code: 'LOGOUT_FAILED', message: 'safe' }, 503)); }); await settle(); await advance(5000);
  expect(reads).toBe(2);
});

it('reconciles an accepted retry that settles during a failed sign-out without claiming unsent retries', async () => {
  let finishRetry!: (value: Response) => void; let finishLogout!: (value: Response) => void; let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return new Promise<Response>(resolve => { finishRetry = resolve; });
    if (url === '/auth/logout') return new Promise<Response>(resolve => { finishLogout = resolve; });
    return response({ papers: [++reads === 1 ? paper : { ...paper, retry_revision: 1, stage: 'ready', preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } }] });
  }));
  render(<LibraryPage />); await settle();
  const button = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(button); fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));
  await act(async () => { finishRetry(response({ job_id: paper.job_id, paper_id: paper.paper_id, document_version: paper.active_version_id, stage: 'ready', status: 'succeeded', retry_revision: 1, preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } }, 202)); }); await settle();
  await act(async () => { finishLogout(response({ code: 'LOGOUT_FAILED', message: 'safe' }, 503)); }); await settle();
  expect(screen.getByRole('link', { name: paper.title })).toBeVisible();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});

it('keeps retry copy honest when sign-out disables a failure without sending a retry', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url === '/api/me' ? response(user) : url === '/auth/logout' ? new Promise<Response>(() => {}) : response({ papers: [paper] })));
  render(<LibraryPage />); await settle();
  const retry = screen.getByRole('button', { name: /try again/i });
  const priorCopy = retry.textContent;
  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' })); await settle();
  expect(retry).toBeDisabled(); expect(retry.textContent).toBe(priorCopy);
});

it('retains owner quota cooldown when retry fails during a subsequently failed logout', async () => {
  let finishRetry!: (value: Response) => void; let finishLogout!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return new Promise<Response>(resolve => { finishRetry = resolve; });
    if (url === '/auth/logout') return new Promise<Response>(resolve => { finishLogout = resolve; });
    return response({ papers: [paper] });
  }));
  render(<LibraryPage />); await settle();
  const retry = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(retry); fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));
  const limited = response({ code: 'PROCESSING_RETRY_LIMITED', message: 'safe' }, 429);
  limited.headers.set('Retry-After', '60');
  await act(async () => { finishRetry(limited); }); await settle();
  await act(async () => { finishLogout(response({ code: 'LOGOUT_FAILED', message: 'safe' }, 503)); }); await settle();
  expect(retry).toBeDisabled();
  await advance(59000); expect(retry).toBeDisabled();
  await advance(1000); expect(retry).toBeEnabled();
});

it('does not let an older conflict refresh consume a newer independent job conflict', async () => {
  const other = { ...paper, paper_id: 'paper-b', job_id: 'job-b', title: 'Other failure' };
  let reads = 0; let finishFirstRead!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) return response({ code: 'RETRY_REVISION_CONFLICT', message: 'safe' }, 409);
    if (++reads === 2) return new Promise<Response>(resolve => { finishFirstRead = resolve; });
    return response({ papers: reads === 1 ? [paper, other] : [{ ...paper, retry_revision: 1, preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } }, { ...other, retry_revision: 1, preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 } }] });
  }));
  render(<LibraryPage />); await settle();
  const buttons = screen.getAllByRole('button', { name: /try again/i });
  fireEvent.click(buttons[0]); await settle();
  fireEvent.click(buttons[1]); await settle();
  await act(async () => { finishFirstRead(response({ papers: [paper, other] })); }); await settle();
  await advance(1);
  expect(reads).toBe(3);
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});
