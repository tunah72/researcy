import React from 'react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import LibraryPage from '../app/library/page';

const paper = {
  paper_id: 'paper-a',
  title: 'Attention Is All You Need',
  authors: ['Author'],
  year: 2017,
  source: 'upload',
  stage: 'failed',
  active_version_id: 'version-a',
  source_version: null,
  screening_warning: null,
  job_id: 'job-a',
  retry_revision: 0,
  preparation: {
    state: 'failed',
    reason: 'temporary',
    retryable: true,
    retry_after_seconds: 0,
  },
};
const user = { id: 'owner-a', email: 'smoke@example.invalid', name: 'Smoke' };
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
const originalLocation = window.location;
async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  document.cookie = 'researcy_csrf=test-csrf';
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { href: '' },
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: originalLocation,
  });
});

it('does not let an automatic poll invalidate a slow foreground search or leave the UI stuck loading', async () => {
  const pending = {
    ...paper,
    stage: 'queued',
    preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
  };
  const searched = {
    ...paper,
    paper_id: 'paper-b',
    job_id: 'job-b',
    title: 'Transformer Search Result',
  };
  let resolvePoll!: (value: Response) => void;
  let resolveSearch!: (value: Response) => void;
  let pollCalls = 0;

  const fetcher = vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.includes('?search=Transformer')) {
      return new Promise<Response>((resolve) => {
        resolveSearch = resolve;
      });
    }
    pollCalls++;
    if (pollCalls === 2) {
      return new Promise<Response>((resolve) => {
        resolvePoll = resolve;
      });
    }
    return response({ papers: [pending] });
  });

  vi.stubGlobal('fetch', fetcher);
  render(<LibraryPage />);
  await settle();
  expect(screen.getByRole('link', { name: paper.title })).toBeVisible();

  // Advance 5s so background poll starts (pollCalls === 2)
  await advance(5000);
  expect(pollCalls).toBe(2);

  // While background poll is in flight, user submits a foreground search
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search papers' }), {
    target: { value: 'Transformer' },
  });
  fireEvent.submit(screen.getByRole('search'));
  await settle();
  expect(
    screen.getAllByRole('status').some((el) => /loading papers/i.test(el.textContent ?? ''))
  ).toBe(true);

  // Background poll completes, its finally block must not schedule a poll that overtakes foreground search
  await act(async () => {
    resolvePoll(response({ papers: [pending] }));
  });
  await settle();

  // Time advances > 5s while foreground search is still in flight
  await advance(6000);

  // Settle foreground search
  await act(async () => {
    resolveSearch(response({ papers: [searched] }));
  });
  await settle();

  // Loading indicator clears and search results are visible
  expect(screen.queryByText(/loading papers/i)).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Transformer Search Result' })).toBeVisible();
});

it('recovers from an invalidated foreground search when sign-out fails without remaining stuck loading', async () => {
  let resolveSearch!: (value: Response) => void;
  let resolveLogout!: (value: Response) => void;
  let searchAttempts = 0;

  const searched = {
    ...paper,
    paper_id: 'paper-b',
    job_id: 'job-b',
    title: 'Transformer Paper',
  };

  const fetcher = vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url === '/auth/logout') {
      return new Promise<Response>((resolve) => {
        resolveLogout = resolve;
      });
    }
    if (url.includes('?search=Transformer')) {
      searchAttempts++;
      if (searchAttempts === 1) {
        return new Promise<Response>((resolve) => {
          resolveSearch = resolve;
        });
      }
      return response({ papers: [searched] });
    }
    return response({ papers: [paper] });
  });

  vi.stubGlobal('fetch', fetcher);
  render(<LibraryPage />);
  await settle();

  // Start foreground search
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search papers' }), {
    target: { value: 'Transformer' },
  });
  fireEvent.submit(screen.getByRole('search'));
  await settle();
  expect(
    screen.getAllByRole('status').some((el) => /loading papers/i.test(el.textContent ?? ''))
  ).toBe(true);

  // Click Sign Out while search is in flight
  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));
  await settle();

  // Discarded search resolves
  await act(async () => {
    resolveSearch(response({ papers: [searched] }));
  });
  await settle();

  // Sign out fails (e.g. 503)
  await act(async () => {
    resolveLogout(response({ code: 'LOGOUT_FAILED', message: 'Failed' }, 503));
  });
  await settle();

  // The invalidated foreground search should be recovered / settled, not stuck loading
  expect(screen.queryByText(/loading papers/i)).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Transformer Paper' })).toBeVisible();
});

it('preserves canonical refresh intent and backs off 30s when conflict GET fails, then converges', async () => {
  let listCalls = 0;
  let finishRetry!: (value: Response) => void;
  const preparing = {
    ...paper,
    stage: 'embedding',
    retry_revision: 1,
    preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  const fetcher = vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) {
      return new Promise<Response>((resolve) => {
        finishRetry = resolve;
      });
    }
    listCalls++;
    if (listCalls === 1) {
      return response({ papers: [paper] }); // initial: failed paper
    }
    if (listCalls === 2) {
      // First canonical refresh after 409 fails (network error)
      return Promise.reject(new TypeError('network error'));
    }
    // After 30s backoff, retry of canonical refresh succeeds
    return response({ papers: [preparing] });
  });

  vi.stubGlobal('fetch', fetcher);
  render(<LibraryPage />);
  await settle();

  const button = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(button);
  await settle();

  // 409 conflict arrives
  await act(async () => {
    finishRetry(response({ code: 'RETRY_REVISION_CONFLICT', message: 'Conflict' }, 409));
  });
  await settle();

  // Canonical refresh failed (listCalls === 2), notice shown, and button stays disabled/busy (not re-enabled)
  expect(listCalls).toBe(2);
  expect(screen.getByRole('button', { name: /try again/i })).toBeDisabled();
  expect(
    screen
      .getAllByRole('status')
      .some((el) => /could not refresh status|check again shortly/i.test(el.textContent ?? ''))
  ).toBe(true);

  // Advance 15s — no busy spin, still in 30s backoff
  await advance(15000);
  expect(listCalls).toBe(2);

  // Advance remaining 15s to complete 30s backoff — should retry canonical GET
  await advance(15000);
  expect(listCalls).toBe(3);

  // State converges to preparing!
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: paper.title })).toBeVisible();
});

it('keeps retry busy during conflict refresh so user cannot trigger overlapping stale retries', async () => {
  let finishRetry!: (value: Response) => void;
  let finishCanonicalGet!: (value: Response) => void;
  let retryCalls = 0;
  const preparing = {
    ...paper,
    stage: 'embedding',
    retry_revision: 1,
    preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  const fetcher = vi.fn(async (url: string) => {
    if (url === '/api/me') return response(user);
    if (url.endsWith('/retry')) {
      retryCalls++;
      return new Promise<Response>((resolve) => {
        finishRetry = resolve;
      });
    }
    if (url.startsWith('/api/papers')) {
      if (retryCalls === 1) {
        return new Promise<Response>((resolve) => {
          finishCanonicalGet = resolve;
        });
      }
      return response({ papers: [paper] });
    }
    return response({ papers: [paper] });
  });

  vi.stubGlobal('fetch', fetcher);
  render(<LibraryPage />);
  await settle();

  const button = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(button);
  await settle();
  expect(retryCalls).toBe(1);

  // 409 conflict arrives
  await act(async () => {
    finishRetry(response({ code: 'RETRY_REVISION_CONFLICT', message: 'Conflict' }, 409));
  });
  await settle();

  // Canonical GET is now in flight
  // The retry button MUST stay busy / disabled while canonical GET is settling
  expect(button).toBeDisabled();

  // Attempting another click while canonical GET is in flight must not dispatch another retry
  fireEvent.click(button);
  await settle();
  expect(retryCalls).toBe(1);

  // Canonical GET finishes with updated server state
  await act(async () => {
    finishCanonicalGet(response({ papers: [preparing] }));
  });
  await settle();

  // Button is removed because state updated to preparing
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});
