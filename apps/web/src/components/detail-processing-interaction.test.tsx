import React from 'react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import PaperDetailPage from '../app/library/[paperId]/page';

const mockParams = { paperId: 'paper-a' };
vi.mock('next/navigation', () => ({
  useParams: () => mockParams,
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const paper = {
  paper_id: 'paper-a',
  title: 'Attention Is All You Need',
  authors: ['Vaswani', 'Shazeer'],
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
  request_id: 'req-detail-1',
};

const response = (body: unknown, status = 200, headers?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
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
  Object.defineProperty(window, 'location', { configurable: true, writable: true, value: { href: '' } });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

it('retries a terminal failure using its persisted revision and displays the accepted delayed state', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/retry')) {
      expect(JSON.parse(String(init?.body))).toEqual({ retry_revision: 0 });
      return response(
        {
          job_id: 'job-a',
          paper_id: 'paper-a',
          document_version: 'version-a',
          stage: 'validating',
          status: 'pending',
          failed_stage: null,
          error_code: null,
          retry_revision: 1,
          preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 },
          request_id: 'req-retry-1',
        },
        202
      );
    }
    return response(paper);
  });

  vi.stubGlobal('fetch', fetcher);
  render(<PaperDetailPage />);
  await settle();

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  const retryBtn = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(retryBtn);
  await settle();

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  expect(screen.getByText('Preparation is waiting to resume.')).toBeVisible();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  expect(screen.getByText('Reading is not available yet.')).toBeVisible();
  expect(fetcher.mock.calls.some(([url]) => url === '/api/jobs/job-a/retry')).toBe(true);
});

it('keeps confirmed metadata when background status refresh fails without polling identity and backs off', async () => {
  const preparing = {
    ...paper,
    stage: 'embedding',
    preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  let calls = 0;
  const fetcher = vi.fn(async (url: string) => {
    if (url.includes('/api/papers/paper-a')) {
      calls++;
      if (calls === 1) return response(preparing);
      return Promise.reject(new TypeError('offline'));
    }
    return response({ code: 'NOT_FOUND', message: 'Not found' }, 404);
  });

  vi.stubGlobal('fetch', fetcher);
  render(<PaperDetailPage />);
  await settle();

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  expect(calls).toBe(1);

  // Advance 5000ms: first background poll occurs and fails
  await advance(5000);
  expect(calls).toBe(2);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  expect(screen.getAllByRole('status').some(el => /status|check/i.test(el.textContent ?? ''))).toBe(true);
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();

  // Advance 25000ms: backoff 30s means no call at 25s
  await advance(25000);
  expect(calls).toBe(2);

  // Advance remaining 5000ms to hit 30s backoff: next attempt occurs
  await advance(5000);
  expect(calls).toBe(3);
});

it('pauses background requests while hidden and refreshes when visible', async () => {
  const pending = {
    ...paper,
    stage: 'queued',
    preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  const fetcher = vi.fn(async () => response(pending));
  vi.stubGlobal('fetch', fetcher);
  render(<PaperDetailPage />);
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(1);

  // Hide document
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
  fireEvent(document, new Event('visibilitychange'));

  // Advance 15s while hidden -> no background calls
  await advance(15000);
  expect(fetcher).toHaveBeenCalledTimes(1);

  // Unhide document -> immediate refresh
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  fireEvent(document, new Event('visibilitychange'));
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it('clears private metadata on a polling 401', async () => {
  const pending = {
    ...paper,
    stage: 'queued',
    preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  let calls = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      calls++;
      if (calls === 1) return response(pending);
      return response({ code: 'UNAUTHENTICATED', message: 'safe' }, 401);
    })
  );

  render(<PaperDetailPage />);
  await settle();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);

  await advance(5000);
  expect(screen.queryByText(paper.title)).not.toBeInTheDocument();
  expect(window.location.href).toBe('/sign-in?expired=1');
});

it('removes private stale detail on background 404', async () => {
  const pending = {
    ...paper,
    stage: 'queued',
    preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  let calls = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      calls++;
      if (calls === 1) return response(pending);
      return response({ code: 'PAPER_NOT_FOUND', message: 'Not found' }, 404);
    })
  );

  render(<PaperDetailPage />);
  await settle();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);

  await advance(5000);
  expect(screen.queryByText(paper.title)).not.toBeInTheDocument();
  expect(screen.getByText(/not found/i)).toBeVisible();
});

it('enforces server cooldown on 429 retry failure', async () => {
  const fetcher = vi.fn(async (url: string) => {
    if (url.endsWith('/retry')) {
      return response(
        { code: 'PROCESSING_RETRY_LIMITED', message: 'Rate limited' },
        429,
        { 'retry-after': '10' }
      );
    }
    return response(paper);
  });

  vi.stubGlobal('fetch', fetcher);
  render(<PaperDetailPage />);
  await settle();

  const retryBtn = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(retryBtn);
  await settle();

  // Button disabled and countdown active
  expect(screen.getByRole('button', { name: /try again/i })).toBeDisabled();
  expect(screen.getAllByRole('status').some(el => /wait/i.test(el.textContent ?? ''))).toBe(true);

  // Advance 10s cooldown
  await advance(10000);
  expect(screen.getByRole('button', { name: /try again/i })).toBeEnabled();
});

it('renders complete preparation honestly without fake reader or badge', async () => {
  const completePaper = {
    ...paper,
    stage: 'ready',
    preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  vi.stubGlobal('fetch', vi.fn(async () => response(completePaper)));
  render(<PaperDetailPage />);
  await settle();

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  expect(screen.getByText('Reading is not available yet.')).toBeVisible();
  expect(screen.queryByText(/waiting|preparing|delayed|could not be prepared/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});

it('refreshes stale terminal detail after a retry conflict without losing metadata', async () => {
  let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/retry')) return response({ code: 'RETRY_REVISION_CONFLICT', message: 'safe' }, 409);
    return response(++reads === 1 ? paper : { ...paper, retry_revision: 1, stage: 'validating', preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 } });
  }));
  render(<PaperDetailPage />); await settle();
  fireEvent.click(screen.getByRole('button', { name: /try again/i })); await settle();
  expect(reads).toBe(2);
  expect(screen.getByRole('heading', { name: paper.title })).toBeVisible();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});

it('announces persisted preparation transitions politely, not the cooldown ticks', async () => {
  const pending = { ...paper, stage: 'embedding', preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 } };
  let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async () => response(++reads === 1 ? pending : paper)));
  render(<PaperDetailPage />); await settle();
  const preparationStatus = screen.getByRole('status');
  expect(preparationStatus).toHaveAttribute('aria-live', 'polite');
  await advance(5000);
  expect(preparationStatus).toHaveTextContent(/could not|unavailable/i);
});

it('defers a hidden retry conflict until visible and restores focus if the retry control disappears', async () => {
  let reads = 0;
  let finishRetry!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/retry')) return new Promise<Response>(resolve => { finishRetry = resolve; });
    return response(++reads === 1 ? paper : { ...paper, retry_revision: 1, stage: 'validating', preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 } });
  }));
  render(<PaperDetailPage />); await settle();
  const retry = screen.getByRole('button', { name: /try again/i }); retry.focus(); fireEvent.click(retry);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' }); fireEvent(document, new Event('visibilitychange'));
  await act(async () => { finishRetry(response({ code: 'RETRY_REVISION_CONFLICT', message: 'safe' }, 409)); }); await settle();
  expect(reads).toBe(1);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); fireEvent(document, new Event('visibilitychange')); await settle();
  expect(reads).toBe(2);
  expect(screen.getByRole('heading', { name: paper.title })).toHaveFocus();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});

it('retains metadata and disables stale retry after a 409 GET network failure, then replaces with canonical delayed state on 30s backoff', async () => {
  let reads = 0;
  const delayedPaper = {
    ...paper,
    retry_revision: 1,
    stage: 'validating',
    preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 },
  };

  const fetcher = vi.fn(async (url: string) => {
    if (url.endsWith('/retry')) {
      return response({ code: 'RETRY_REVISION_CONFLICT', message: 'safe' }, 409);
    }
    if (url.includes('/api/papers/paper-a')) {
      reads++;
      if (reads === 1) return response(paper);
      if (reads === 2) return Promise.reject(new TypeError('offline'));
      return response(delayedPaper);
    }
    return response({ code: 'NOT_FOUND', message: 'Not found' }, 404);
  });

  vi.stubGlobal('fetch', fetcher);
  render(<PaperDetailPage />);
  await settle();

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  const retryBtn = screen.getByRole('button', { name: /try again/i });
  expect(retryBtn).toBeEnabled();

  fireEvent.click(retryBtn);
  await settle();

  expect(reads).toBe(2);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  const pendingRetryBtn = screen.getByRole('button', { name: /try again/i });
  expect(pendingRetryBtn).toBeDisabled();

  await advance(25000);
  expect(reads).toBe(2);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);

  await advance(5000);
  expect(reads).toBe(3);

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  expect(screen.getByText('Preparation is waiting to resume.')).toBeVisible();
  expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
});

it('removes detail when 409 canonical refresh returns 404 and ignores subsequent visibility events', async () => {
  let reads = 0;
  const fetcher = vi.fn(async (url: string) => {
    if (url.endsWith('/retry')) {
      return response({ code: 'RETRY_REVISION_CONFLICT', message: 'safe' }, 409);
    }
    if (url.includes('/api/papers/paper-a')) {
      reads++;
      if (reads === 1) return response(paper);
      return response({ code: 'PAPER_NOT_FOUND', message: 'Not found' }, 404);
    }
    return response({ code: 'NOT_FOUND', message: 'Not found' }, 404);
  });

  vi.stubGlobal('fetch', fetcher);
  render(<PaperDetailPage />);
  await settle();

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paper.title);
  const retryBtn = screen.getByRole('button', { name: /try again/i });
  fireEvent.click(retryBtn);
  await settle();

  expect(reads).toBe(2);
  expect(screen.queryByText(paper.title)).not.toBeInTheDocument();
  expect(screen.getByText(/not found/i)).toBeVisible();

  const totalCallsAfter404 = fetcher.mock.calls.length;

  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
  fireEvent(document, new Event('visibilitychange'));
  await settle();

  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  fireEvent(document, new Event('visibilitychange'));
  await settle();

  await advance(30000);
  expect(fetcher.mock.calls.length).toBe(totalCallsAfter404);
});
