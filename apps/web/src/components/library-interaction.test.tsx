import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LibraryList } from './library-list';
import { AddPaper } from './add-paper';
import LibraryPage from '../app/library/page';
import { Paper, parseResponse, ApiError } from '@/lib/api';

describe('Library UI Consumer Interaction Tests', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'researcy_csrf=valid-csrf-token';
    Object.defineProperty(window, 'location', {
      writable: true,
      configurable: true,
      value: {
        href: '',
        assign: vi.fn(),
        replace: vi.fn(),
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('queued response renders without fake progress or raw stage badge', () => {
    const queuedPaper: Paper = {
      paper_id: '11111111-1111-1111-1111-111111111111',
      title: 'Attention Is All You Need',
      authors: ['Ashish Vaswani', 'Noam Shazeer'],
      year: 2017,
      source: 'arxiv',
      stage: 'queued',
      active_version_id: '22222222-2222-2222-2222-222222222222',
      source_version: 'v7',
      screening_warning: null,
      job_id: '11111111-1111-1111-1111-111111111111',
      retry_revision: 0,
      preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
    };

    render(<LibraryList papers={[queuedPaper]} />);

    expect(screen.getByText('Attention Is All You Need')).toBeInTheDocument();
    expect(screen.queryByText(/ready/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.queryByText(/^queued$/i)).not.toBeInTheDocument();
  });

  it('warning survives refresh and renders screening note without raw technical codes', () => {
    const warnedPaper: Paper = {
      paper_id: '33333333-3333-3333-3333-333333333333',
      title: 'Low Text Document',
      authors: ['Jane Doe'],
      year: 2023,
      source: 'upload',
      stage: 'queued',
      active_version_id: '44444444-4444-4444-4444-444444444444',
      source_version: null,
      screening_warning: 'LOW_TEXT: Total extracted characters under 200 (libmagic err 0x88f2)',
      job_id: '33333333-3333-3333-3333-333333333333',
      retry_revision: 0,
      preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
    };

    render(<LibraryList papers={[warnedPaper]} />);

    expect(screen.getByText('Low Text Document')).toBeInTheDocument();
    const note = screen.getByRole('note');
    expect(note).toBeInTheDocument();
    expect(note.textContent?.trim().length).toBeGreaterThan(0);
    expect(note).not.toHaveTextContent(/0x88f2/i);
    expect(note).not.toHaveTextContent(/libmagic/i);
    expect(note).not.toHaveTextContent(/LOW_TEXT/i);
  });

  it('screening warning with unknown technical codes still renders note but no raw technical codes', () => {
    const warnedPaper: Paper = {
      paper_id: '44444444-4444-4444-4444-444444444444',
      title: 'Technical Warning Paper',
      authors: ['Jane Doe'],
      year: 2023,
      source: 'upload',
      stage: 'queued',
      active_version_id: '55555555-5555-5555-5555-555555555555',
      source_version: null,
      screening_warning: 'PDF_OCR_EXCEPTION: libtesseract failed at memory address 0x00ff41',
      job_id: '44444444-4444-4444-4444-444444444444',
      retry_revision: 0,
      preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
    };

    render(<LibraryList papers={[warnedPaper]} />);

    const note = screen.getByRole('note');
    expect(note).toBeInTheDocument();
    expect(note).not.toHaveTextContent(/0x00ff41/i);
    expect(note).not.toHaveTextContent(/libtesseract/i);
    expect(note).not.toHaveTextContent(/PDF_OCR_EXCEPTION/i);
  });

  it('unknown author and year display stays honest', () => {
    const honestPaper: Paper = {
      paper_id: '55555555-5555-5555-5555-555555555555',
      title: 'Monograph Without Metadata',
      authors: null,
      year: null,
      source: 'upload',
      stage: 'queued',
      active_version_id: '66666666-6666-6666-6666-666666666666',
      source_version: null,
      screening_warning: null,
      job_id: '55555555-5555-5555-5555-555555555555',
      retry_revision: 0,
      preparation: { state: 'waiting', reason: null, retryable: false, retry_after_seconds: 0 },
    };

    render(<LibraryList papers={[honestPaper]} />);

    expect(screen.getByText('Monograph Without Metadata')).toBeInTheDocument();
    expect(screen.getByText(/unknown author/i)).toBeInTheDocument();
    expect(screen.getByText(/year unknown/i)).toBeInTheDocument();
  });

  it('submission failure keeps field-associated error, does not leak raw backend message or request ID, and supports retry', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/papers/arxiv')) {
        return Promise.resolve({
          ok: false,
          status: 422,
          headers: new Headers({ 'x-request-id': 'req-arxiv-err-422' }),
          json: async () => ({
            code: 'INVALID_ARXIV_REFERENCE',
            message: 'Internal parsing error: regex failure at 0xdeadbeef in worker-pool',
            request_id: 'req-arxiv-err-422',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AddPaper />);

    const input = screen.getByLabelText(/arXiv (?:ID|identifier)/i);
    const submitBtn = screen.getByRole('button', { name: /import/i });

    await userEvent.type(input, 'invalid-id-xyz');
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    // Never leak raw backend technical message or request ID into UI
    expect(screen.queryByText(/0xdeadbeef/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/worker-pool/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/req-arxiv-err-422/i)).not.toBeInTheDocument();

    // Check that Retry button exists and is field-associated
    const retryBtn = screen.getByRole('button', { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();

    const firstInit = mockFetch.mock.calls[0]?.[1];
    const firstHeaders = new Headers(firstInit && typeof firstInit === 'object' && 'headers' in firstInit ? firstInit.headers : undefined);
    const firstKey = firstHeaders.get('Idempotency-Key');
    expect(firstKey).not.toBeNull();

    // Click retry with unchanged payload -> must reuse identical idempotency key
    await userEvent.click(retryBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    const secondInit = mockFetch.mock.calls[1]?.[1];
    const secondHeaders = new Headers(secondInit && typeof secondInit === 'object' && 'headers' in secondInit ? secondInit.headers : undefined);
    const secondKey = secondHeaders.get('Idempotency-Key');
    expect(secondKey).toBe(firstKey);
  });

  it('uses a fresh idempotency key when a replacement file has changed bytes', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      headers: new Headers({ 'x-request-id': 'req-upload-err' }),
      json: async () => ({
        code: 'PDF_INVALID',
        message: 'The PDF could not be accepted.',
        request_id: 'req-upload-err',
      }),
    });
    vi.stubGlobal('fetch', mockFetch);
    render(<AddPaper />);

    await userEvent.click(screen.getByRole('tab', { name: /upload/i }));
    const fileInput = screen.getByLabelText(/select pdf document/i);
    const firstFile = new File(['first'], 'paper.pdf', {
      type: 'application/pdf',
      lastModified: 1,
    });
    const replacementFile = new File(['other'], 'paper.pdf', {
      type: 'application/pdf',
      lastModified: 1,
    });

    await userEvent.upload(fileInput, firstFile);
    await userEvent.click(screen.getByRole('button', { name: /upload/i }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    fireEvent.change(fileInput, { target: { files: [replacementFile] } });
    await userEvent.click(screen.getByRole('button', { name: /upload/i }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));

    const firstHeaders = new Headers(mockFetch.mock.calls[0]?.[1]?.headers);
    const secondHeaders = new Headers(mockFetch.mock.calls[1]?.[1]?.headers);
    expect(secondHeaders.get('Idempotency-Key')).not.toBe(
      firstHeaders.get('Idempotency-Key')
    );
    expect(screen.queryByText(/req-upload-err/i)).not.toBeInTheDocument();
  });

  it('logout failure never claims signed-out and does not leak backend error or request ID', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-me-1' }),
          json: async () => ({
            id: 'owner-uuid-123',
            email: 'researcher@example.org',
            name: 'Dr. Researcher',
            request_id: 'req-me-1',
          }),
        });
      }
      if (url === '/api/papers') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-papers-1' }),
          json: async () => ({
            papers: [],
            request_id: 'req-papers-1',
          }),
        });
      }
      if (url === '/auth/logout') {
        return Promise.resolve({
          ok: false,
          status: 500,
          headers: new Headers({ 'x-request-id': 'req-logout-fail-500' }),
          json: async () => ({
            code: 'REVOCATION_FAILED',
            message: 'Server failed to revoke active session in database: pg_pool connection lost.',
            request_id: 'req-logout-fail-500',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);

    // Wait for user info to load
    await waitFor(() => {
      expect(screen.getByText('researcher@example.org')).toBeInTheDocument();
    });

    const logoutBtn = screen.getByRole('button', { name: /sign out/i });
    expect(logoutBtn).toBeInTheDocument();

    await userEvent.click(logoutBtn);

    // Logout failed: should display error alert, user identity stays visible, no redirect
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.queryByText(/pg_pool connection lost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/req-logout-fail-500/i)).not.toBeInTheDocument();
    expect(screen.getByText('researcher@example.org')).toBeInTheDocument();
    expect(window.location.href).not.toBe('/sign-in');
  });

  it('401 clears authenticated view and redirects to sign-in', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: false,
          status: 401,
          headers: new Headers({ 'x-request-id': 'req-401' }),
          json: async () => ({
            code: 'UNAUTHENTICATED',
            message: 'Authentication is required.',
            request_id: 'req-401',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);

    await waitFor(() => {
      expect(window.location.href).toContain('/sign-in');
    });

    // Stale user identity should not be displayed
    expect(screen.queryByText(/researcher@example.org/i)).not.toBeInTheDocument();
  });

  it('parses Retry-After header into ApiError.retryAfter seconds', async () => {
    const response = new Response(
      JSON.stringify({
        code: 'ARXIV_UPSTREAM_ERROR',
        message: 'arXiv rate limit exceeded. Please wait before requesting again.',
        request_id: 'req-rate-limit-1',
      }),
      {
        status: 503,
        headers: {
          'Content-Type': 'application/json',
          'Retry-After': '60',
          'x-request-id': 'req-rate-limit-1',
        },
      }
    );

    let thrownError: unknown;
    try {
      await parseResponse(response);
    } catch (err) {
      thrownError = err;
    }

    expect(thrownError).toBeInstanceOf(ApiError);
    const apiErr = thrownError as ApiError;
    expect(apiErr.status).toBe(503);
    expect(apiErr.code).toBe('ARXIV_UPSTREAM_ERROR');
    expect(apiErr.requestId).toBe('req-rate-limit-1');
    expect(apiErr.retryAfter).toBe(60);
  });

  it('honors Retry-After cooldown, disables retry during cooldown, and preserves idempotency key on same payload retry', async () => {
    vi.useFakeTimers();
    try {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/papers/arxiv')) {
          return Promise.resolve({
            ok: false,
            status: 503,
            headers: new Headers({
              'x-request-id': 'req-retry-after-503',
              'retry-after': '30',
            }),
            json: async () => ({
              code: 'ARXIV_UPSTREAM_ERROR',
              message: 'arXiv rate limit exceeded. Please wait before retrying.',
              request_id: 'req-retry-after-503',
            }),
          });
        }
        return Promise.reject(new Error(`Unexpected url: ${url}`));
      });
      vi.stubGlobal('fetch', mockFetch);

      render(<AddPaper />);

      const input = screen.getByLabelText(/arXiv ID or URL/i);
      fireEvent.change(input, { target: { value: '1706.03762' } });
      await act(async () => {
        fireEvent.submit(input.closest('form')!);
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.queryByText(/req-retry-after-503/i)).not.toBeInTheDocument();

      const retryBtn = screen.getByRole('button', { name: /retry in 30s/i });
      expect(retryBtn).toBeDisabled();

      const firstInit = mockFetch.mock.calls[0]?.[1];
      const firstHeaders = new Headers(firstInit && typeof firstInit === 'object' && 'headers' in firstInit ? firstInit.headers : undefined);
      const firstKey = firstHeaders.get('Idempotency-Key');

      // Advance time by 30 seconds to expire cooldown
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });

      expect(retryBtn).not.toBeDisabled();
      expect(retryBtn).toHaveTextContent(/retry submission/i);

      // Click retry after cooldown expiry
      await act(async () => {
        fireEvent.click(retryBtn);
      });

      expect(mockFetch).toHaveBeenCalledTimes(2);
      const secondInit = mockFetch.mock.calls[1]?.[1];
      const secondHeaders = new Headers(secondInit && typeof secondInit === 'object' && 'headers' in secondInit ? secondInit.headers : undefined);
      const secondKey = secondHeaders.get('Idempotency-Key');

      expect(secondKey).toBe(firstKey);
    } finally {
      vi.useRealTimers();
    }
  });

  it('changed arXiv input does NOT clear upstream global cooldown', async () => {
    vi.useFakeTimers();
    try {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/papers/arxiv')) {
          return Promise.resolve({
            ok: false,
            status: 503,
            headers: new Headers({
              'x-request-id': 'req-retry-after-503',
              'retry-after': '60',
            }),
            json: async () => ({
              code: 'ARXIV_UPSTREAM_ERROR',
              message: 'arXiv rate limit exceeded.',
              request_id: 'req-retry-after-503',
            }),
          });
        }
        return Promise.reject(new Error(`Unexpected url: ${url}`));
      });
      vi.stubGlobal('fetch', mockFetch);

      render(<AddPaper />);

      const input = screen.getByLabelText(/arXiv (?:ID|identifier)/i);
      fireEvent.change(input, { target: { value: '1706.03762' } });
      await act(async () => {
        fireEvent.submit(input.closest('form')!);
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();

      const firstInit = mockFetch.mock.calls[0]?.[1];
      const firstHeaders = new Headers(firstInit && typeof firstInit === 'object' && 'headers' in firstInit ? firstInit.headers : undefined);
      const firstKey = firstHeaders.get('Idempotency-Key');

      // User changes the input to a different paper during active cooldown
      fireEvent.change(input, { target: { value: '2301.00001' } });

      // Changing input must NOT bypass cooldown; submit button must remain disabled
      const submitBtn = screen.getByRole('button', { name: /import/i });
      expect(submitBtn).toBeDisabled();

      // Advance timers to expire cooldown
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60000);
      });

      // After cooldown expires, submit button is enabled
      expect(submitBtn).not.toBeDisabled();

      await act(async () => {
        fireEvent.submit(input.closest('form')!);
      });

      expect(mockFetch).toHaveBeenCalledTimes(2);

      const secondInit = mockFetch.mock.calls[1]?.[1];
      const secondHeaders = new Headers(secondInit && typeof secondInit === 'object' && 'headers' in secondInit ? secondInit.headers : undefined);
      const secondKey = secondHeaders.get('Idempotency-Key');

      // Changed payload gets fresh idempotency key
      expect(secondKey).not.toBe(firstKey);
    } finally {
      vi.useRealTimers();
    }
  });
  it('retains cooldown when trimming whitespace or undoing edits back to the rate-limited arXiv payload', async () => {
    vi.useFakeTimers();
    try {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/papers/arxiv')) {
          return Promise.resolve({
            ok: false,
            status: 429,
            headers: new Headers({
              'x-request-id': 'req-cooldown-429',
              'retry-after': '30',
            }),
            json: async () => ({
              code: 'ARXIV_UPSTREAM_ERROR',
              message: 'arXiv rate limit exceeded. Please wait before retrying.',
              request_id: 'req-cooldown-429',
            }),
          });
        }
        return Promise.reject(new Error(`Unexpected url: ${url}`));
      });
      vi.stubGlobal('fetch', mockFetch);

      render(<AddPaper />);

      const input = screen.getByLabelText(/arXiv ID or URL/i);
      const submitBtn = screen.getByRole('button', { name: /import paper/i });

      // 1. Initial submission
      fireEvent.change(input, { target: { value: '1706.03762' } });
      await act(async () => {
        fireEvent.submit(input.closest('form')!);
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      const retryBtn = screen.getByRole('button', { name: /retry in 30s/i });
      expect(retryBtn).toBeDisabled();
      expect(submitBtn).toBeDisabled();

      // Capture first idempotency key
      const firstInit = mockFetch.mock.calls[0]?.[1];
      const firstHeaders = new Headers(firstInit && typeof firstInit === 'object' && 'headers' in firstInit ? firstInit.headers : undefined);
      const firstKey = firstHeaders.get('Idempotency-Key');

      // 2. Whitespace edit (trim test): adding spaces retains normalized payload and cooldown
      fireEvent.change(input, { target: { value: '  1706.03762   ' } });
      expect(submitBtn).toBeDisabled();

      // 3. Different payload edit: cooldown still blocks submission
      fireEvent.change(input, { target: { value: '1706.03762-edited' } });
      expect(submitBtn).toBeDisabled();

      // 4. Undo edit: restoring original payload retains cooldown
      fireEvent.change(input, { target: { value: '1706.03762' } });
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry in 30s/i })).toBeDisabled();
      expect(submitBtn).toBeDisabled();

      // 5. Advance timers to expire cooldown
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });

      const enabledRetryBtn = screen.getByRole('button', { name: /retry submission/i });
      expect(enabledRetryBtn).not.toBeDisabled();
      expect(submitBtn).not.toBeDisabled();

      // 6. Retry submission reuses the same idempotency key
      await act(async () => {
        fireEvent.click(enabledRetryBtn);
      });

      expect(mockFetch).toHaveBeenCalledTimes(2);
      const secondInit = mockFetch.mock.calls[1]?.[1];
      const secondHeaders = new Headers(secondInit && typeof secondInit === 'object' && 'headers' in secondInit ? secondInit.headers : undefined);
      const secondKey = secondHeaders.get('Idempotency-Key');
      expect(secondKey).toBe(firstKey);
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps arXiv and PDF cooldowns completely independent', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/papers/arxiv')) {
        return Promise.resolve({
          ok: false,
          status: 429,
          headers: new Headers({
            'x-request-id': 'req-arxiv-429',
            'retry-after': '45',
          }),
          json: async () => ({
            code: 'ARXIV_UPSTREAM_ERROR',
            message: 'arXiv rate limit exceeded.',
            request_id: 'req-arxiv-429',
          }),
        });
      }
      if (url.includes('/api/papers/upload')) {
        return Promise.resolve({
          ok: true,
          status: 202,
          headers: new Headers({
            'x-request-id': 'req-pdf-success',
          }),
          json: async () => ({
            paper_id: 'paper-pdf-1',
            title: 'Uploaded Document',
            authors: null,
            publication_year: null,
            abstract: null,
            primary_category: null,
            stage: 'queued',
            screening_warning: null,
            source_version: null,
            request_id: 'req-pdf-success',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    const onPaperAdded = vi.fn();
    render(<AddPaper onPaperAdded={onPaperAdded} />);

    // 1. Submit arXiv and trigger 45s cooldown
    const arxivInput = screen.getByLabelText(/arXiv (?:ID|identifier)/i);
    fireEvent.change(arxivInput, { target: { value: '1706.03762' } });
    await act(async () => {
      fireEvent.submit(arxivInput.closest('form')!);
    });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry in 45s/i })).toBeDisabled();

    // 2. Switch to PDF upload tab
    const uploadTab = screen.getByRole('tab', { name: /upload/i });
    await userEvent.click(uploadTab);

    // 3. PDF form must NOT be disabled by arXiv cooldown
    const fileInput = screen.getByLabelText(/select pdf document/i);
    const testFile = new File(['%PDF-1.4 mock content'], 'test.pdf', { type: 'application/pdf' });
    await userEvent.upload(fileInput, testFile);

    const uploadBtn = screen.getByRole('button', { name: /upload/i });
    expect(uploadBtn).not.toBeDisabled();

    // 4. PDF upload succeeds independently
    await userEvent.click(uploadBtn);

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(onPaperAdded).toHaveBeenCalledWith('paper-pdf-1');
    });
    expect(screen.queryByText(/req-pdf-success/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^queued$/i)).not.toBeInTheDocument();
  });

  it.each(['arxiv', 'upload'] as const)('explains an account cooldown on both tabs after %s is limited', async (method) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({ 'retry-after': '30' }),
      json: async () => ({ code: 'IMPORT_RATE_LIMITED', message: 'private quota diagnostic' }),
    }));
    render(<AddPaper />);
    const arxivInput = screen.getByLabelText(/arXiv ID/i);
    fireEvent.change(arxivInput, { target: { value: '1706.03762' } });
    await userEvent.click(screen.getByRole('tab', { name: /upload/i }));
    await userEvent.upload(screen.getByLabelText(/select pdf/i), new File(['pdf'], 'paper.pdf', { type: 'application/pdf' }));
    if (method === 'arxiv') {
      await userEvent.click(screen.getByRole('tab', { name: /arxiv/i }));
    }
    await userEvent.click(screen.getByRole('button', { name: method === 'arxiv' ? 'Import Paper' : 'Upload PDF' }));
    await screen.findByRole('alert');
    await userEvent.click(screen.getByRole('tab', { name: method === 'arxiv' ? /upload/i : /arxiv/i }));
    expect(screen.getByRole('alert')).toBeVisible();
    expect(screen.getByRole('button', { name: /retry in/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: method === 'arxiv' ? 'Upload PDF' : 'Import Paper' })).toBeDisabled();
    expect(screen.queryByText('private quota diagnostic')).not.toBeInTheDocument();
  });

  it('supports keyboard navigation for tabs using arrow keys, Home, and End', async () => {
    render(<AddPaper />);

    const arxivTab = screen.getByRole('tab', { name: /arxiv/i });
    const uploadTab = screen.getByRole('tab', { name: /upload/i });

    arxivTab.focus();
    expect(document.activeElement).toBe(arxivTab);

    // ArrowRight moves focus and selection to next tab
    fireEvent.keyDown(arxivTab, { key: 'ArrowRight' });
    expect(uploadTab).toHaveFocus();
    expect(uploadTab).toHaveAttribute('aria-selected', 'true');

    // ArrowLeft moves back to previous tab
    fireEvent.keyDown(uploadTab, { key: 'ArrowLeft' });
    expect(arxivTab).toHaveFocus();
    expect(arxivTab).toHaveAttribute('aria-selected', 'true');

    // End key moves to last tab
    fireEvent.keyDown(arxivTab, { key: 'End' });
    expect(uploadTab).toHaveFocus();
    expect(uploadTab).toHaveAttribute('aria-selected', 'true');

    // Home key moves to first tab
    fireEvent.keyDown(uploadTab, { key: 'Home' });
    expect(arxivTab).toHaveFocus();
    expect(arxivTab).toHaveAttribute('aria-selected', 'true');
  });

  it('manages focus when opening and closing Add Paper panel', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-me' }),
          json: async () => ({ id: 'user-1', email: 'user@example.com', name: 'User', request_id: 'req-me' }),
        });
      }
      if (url.startsWith('/api/papers')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-p' }),
          json: async () => ({ papers: [], request_id: 'req-p' }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /^add paper$/i })[0]).toBeInTheDocument();
    });

    const addPaperBtn = screen.getAllByRole('button', { name: /^add paper$/i })[0];
    await userEvent.click(addPaperBtn);

    // Add paper panel should open and focus should move inside the panel
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /add paper to library/i })).toBeInTheDocument();
    });

    const panel = screen.getByRole('region', { name: /add paper to library/i });
    expect(panel.contains(document.activeElement)).toBe(true);

    // Close panel using the panel's close button
    const closeBtn = screen.getByRole('button', { name: /close add paper panel/i });
    await userEvent.click(closeBtn);
    // Focus should be restored to Add Paper toggle button
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: /add paper to library/i })).not.toBeInTheDocument();
    });
    expect(document.activeElement).toBe(addPaperBtn);
  });
  it('restores focus to sole Add paper CTA when panel is opened and closed in empty library', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-me' }),
          json: async () => ({ id: 'user-1', email: 'user@example.com', name: 'User', request_id: 'req-me' }),
        });
      }
      if (url.startsWith('/api/papers')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-p' }),
          json: async () => ({ papers: [], request_id: 'req-p' }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);

    // Wait for empty state to render
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /empty library/i })).toBeInTheDocument();
    });

    // Exactly one primary "Add Paper" button in the view
    const addPaperButtons = screen.getAllByRole('button', { name: /^add paper$/i });
    expect(addPaperButtons).toHaveLength(1);
    const soleTrigger = addPaperButtons[0];
    expect(soleTrigger).toHaveClass('btn-primary');

    // Click the sole trigger to open Add Paper
    await userEvent.click(soleTrigger);

    // Panel should open
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /add paper to library/i })).toBeInTheDocument();
    });

    // Close the panel
    const closeBtn = screen.getByRole('button', { name: /close add paper panel/i });
    await userEvent.click(closeBtn);

    // Panel closes and focus is restored to the sole trigger that opened it
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: /add paper to library/i })).not.toBeInTheDocument();
    });
    expect(document.activeElement).toBe(soleTrigger);
  });

  it('prevents stale search responses from overwriting current query results', async () => {
    let resolveSlowQuery!: (value: unknown) => void;
    const slowQueryPromise = new Promise((resolve) => {
      resolveSlowQuery = resolve;
    });
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-me' }),
          json: async () => ({ id: 'u1', email: 'u@example.com', name: 'User', request_id: 'req-me' }),
        });
      }
      if (url === '/api/papers') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-init' }),
          json: async () => ({ papers: [], request_id: 'req-init' }),
        });
      }
      if (url.includes('search=slow')) {
        return slowQueryPromise.then(() => ({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-slow' }),
          json: async () => ({
            papers: [
              {
                paper_id: 'slow-id',
                title: 'Stale Slow Result',
                authors: ['Old Author'],
                year: 2020,
                source: 'arxiv',
                stage: 'queued',
                active_version_id: 'v-slow',
                source_version: 'v1',
                screening_warning: null,
                job_id: 'job-slow',
                retry_revision: 0,
                preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 },
              },
            ],
            request_id: 'req-slow',
          }),
        }));
      }
      if (url.includes('search=fast')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-fast' }),
          json: async () => ({
            papers: [
              {
                paper_id: 'fast-id',
                title: 'Current Fast Result',
                authors: ['New Author'],
                year: 2024,
                source: 'upload',
                stage: 'queued',
                active_version_id: 'v-fast',
                source_version: null,
                screening_warning: null,
                job_id: 'job-fast',
                retry_revision: 0,
                preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 },
              },
            ],
            request_id: 'req-fast',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);

    await waitFor(() => {
      expect(screen.getByRole('searchbox', { name: /search papers/i })).toBeInTheDocument();
    });

    const searchInput = screen.getByRole('searchbox', { name: /search papers/i });
    const searchForm = searchInput.closest('form')!;

    // 1. Submit slow search
    await userEvent.type(searchInput, 'slow');
    fireEvent.submit(searchForm);

    // 2. Immediately submit fast search
    await userEvent.clear(searchInput);
    await userEvent.type(searchInput, 'fast');
    fireEvent.submit(searchForm);

    // Fast search completes first
    await waitFor(() => {
      expect(screen.getByText('Current Fast Result')).toBeInTheDocument();
    });

    // 3. Now slow search resolves late
    resolveSlowQuery!({ ok: true });

    // Stale slow result must NOT overwrite the current fast query result
    await waitFor(() => {
      expect(screen.getByText('Current Fast Result')).toBeInTheDocument();
    });
    expect(screen.queryByText('Stale Slow Result')).not.toBeInTheDocument();
  });


  it('preserves entered inputs across tab switches in Add Paper', async () => {
    render(<AddPaper />);

    const arxivInput = screen.getByLabelText(/arXiv ID or URL/i);
    await userEvent.type(arxivInput, '2301.00001');

    // Switch to PDF tab
    await userEvent.click(screen.getByRole('tab', { name: /upload/i }));
    expect(screen.getByLabelText(/select pdf document/i)).toBeInTheDocument();

    // Switch back to arXiv tab
    await userEvent.click(screen.getByRole('tab', { name: /arxiv/i }));
    expect(screen.getByLabelText(/arXiv ID or URL/i)).toHaveValue('2301.00001');
  });

  it('auth loading or error prevents active upload and logout controls', async () => {
    const { promise: mePromise, resolve: resolveMe } = Promise.withResolvers<unknown>();

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return mePromise;
      }
      if (url === '/api/papers') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-papers' }),
          json: async () => ({ papers: [], request_id: 'req-papers' }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);

    // While auth is unknown / loading:
    // Add Paper buttons and Sign out button should be disabled
    const addPaperBtns = screen.queryAllByRole('button', { name: /^add paper$/i });
    for (const btn of addPaperBtns) {
      expect(btn).toBeDisabled();
    }
    const logoutBtn = screen.queryByRole('button', { name: /sign out/i });
    if (logoutBtn) {
      expect(logoutBtn).toBeDisabled();
    }

    // Resolve auth with an error (500)
    resolveMe({
      ok: false,
      status: 500,
      headers: new Headers({ 'x-request-id': 'req-me-500' }),
      json: async () => ({ code: 'INTERNAL_ERROR', message: 'Failed to fetch user', request_id: 'req-me-500' }),
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    // Upload / logout controls must NOT be active when profile is invalid/errored
    const addBtnsAfterError = screen.queryAllByRole('button', { name: /^add paper$/i });
    for (const btn of addBtnsAfterError) {
      expect(btn).toBeDisabled();
    }
    const logoutBtnAfterError = screen.queryByRole('button', { name: /sign out/i });
    if (logoutBtnAfterError) {
      expect(logoutBtnAfterError).toBeDisabled();
    }
  });

  it('Add Paper panel close button is disabled while submission is pending and retains key on retry', async () => {
    const { promise: uploadPromise, resolve: resolveUpload } = Promise.withResolvers<unknown>();

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/papers/upload')) {
        return uploadPromise;
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    const onClose = vi.fn();
    render(<AddPaper onClose={onClose} />);

    // Switch to upload tab
    await userEvent.click(screen.getByRole('tab', { name: /upload/i }));
    const fileInput = screen.getByLabelText(/select pdf document/i);
    const testFile = new File(['%PDF-1.4 test'], 'paper.pdf', { type: 'application/pdf' });
    await userEvent.upload(fileInput, testFile);

    const uploadBtn = screen.getByRole('button', { name: /upload/i });
    const closeBtn = screen.getByRole('button', { name: /close/i });

    // Submit upload
    await userEvent.click(uploadBtn);

    // Pending: Close button MUST be disabled
    expect(closeBtn).toBeDisabled();
    expect(uploadBtn).toBeDisabled();

    // Attempting to click close must do nothing
    fireEvent.click(closeBtn);
    expect(onClose).not.toHaveBeenCalled();

    // Now resolve with error
    resolveUpload({
      ok: false,
      status: 422,
      headers: new Headers({ 'x-request-id': 'req-up-fail' }),
      json: async () => ({
        code: 'PDF_INVALID',
        message: 'Could not parse document structure',
        request_id: 'req-up-fail',
      }),
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    // Close button is re-enabled after submission completes
    expect(closeBtn).not.toBeDisabled();

    // Retry button is available
    const retryBtn = screen.getByRole('button', { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();

    const firstKey = new Headers(mockFetch.mock.calls[0]?.[1]?.headers).get('Idempotency-Key');

    // Click retry with same file -> same idempotency key
    await userEvent.click(retryBtn);

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const secondKey = new Headers(mockFetch.mock.calls[1]?.[1]?.headers).get('Idempotency-Key');
    expect(secondKey).toBe(firstKey);
  });

  it('retry 409 conflict triggers background refresh retaining paper metadata', async () => {
    const failedPaper: Paper = {
      paper_id: 'conflict-id',
      title: 'Conflict Paper',
      authors: ['Author'],
      year: 2021,
      source: 'upload',
      stage: 'failed',
      active_version_id: 'v-conflict',
      source_version: null,
      screening_warning: null,
      job_id: 'job-conflict',
      retry_revision: 0,
      preparation: { state: 'failed', reason: 'temporary', retryable: true, retry_after_seconds: 0 },
    };
    const refreshedPaper: Paper = {
      ...failedPaper,
      stage: 'validating',
      retry_revision: 1,
      preparation: { state: 'preparing', reason: null, retryable: false, retry_after_seconds: 0 },
    };
    let refreshCalls = 0;
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-me' }),
          json: async () => ({ id: 'u1', email: 'u@example.com', name: 'User', request_id: 'req-me' }),
        });
      }
      if (url === '/api/papers') {
        refreshCalls++;
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': `req-p-${refreshCalls}` }),
          json: async () => ({ papers: [refreshCalls === 1 ? failedPaper : refreshedPaper], request_id: `req-p-${refreshCalls}` }),
        });
      }
      if (url.endsWith('/retry')) {
        return Promise.resolve({
          ok: false,
          status: 409,
          headers: new Headers({ 'x-request-id': 'req-409' }),
          json: async () => ({ code: 'RETRY_REVISION_CONFLICT', message: 'Revision conflict', request_id: 'req-409' }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /try again/i }));

    await waitFor(() => {
      expect(refreshCalls).toBe(2);
      expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: 'Conflict Paper' })).toBeInTheDocument();
  });

  it('allows retrying independent failed papers concurrently without one blocking the other', async () => {
    const paper1: Paper = {
      paper_id: 'p1',
      title: 'Paper One',
      authors: ['A1'],
      year: 2020,
      source: 'upload',
      stage: 'failed',
      active_version_id: 'v1',
      source_version: null,
      screening_warning: null,
      job_id: 'j1',
      retry_revision: 0,
      preparation: { state: 'failed', reason: 'temporary', retryable: true, retry_after_seconds: 0 },
    };
    const paper2: Paper = {
      paper_id: 'p2',
      title: 'Paper Two',
      authors: ['A2'],
      year: 2021,
      source: 'upload',
      stage: 'failed',
      active_version_id: 'v2',
      source_version: null,
      screening_warning: null,
      job_id: 'j2',
      retry_revision: 0,
      preparation: { state: 'failed', reason: 'temporary', retryable: true, retry_after_seconds: 0 },
    };

    const { promise: retry1Promise, resolve: resolveRetry1 } = Promise.withResolvers<unknown>();

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-me' }),
          json: async () => ({ id: 'u1', email: 'u@example.com', name: 'User', request_id: 'req-me' }),
        });
      }
      if (url === '/api/papers') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'x-request-id': 'req-p' }),
          json: async () => ({ papers: [paper1, paper2], request_id: 'req-p' }),
        });
      }
      if (url.includes('/api/jobs/j1/retry')) {
        return retry1Promise;
      }
      if (url.includes('/api/jobs/j2/retry')) {
        return Promise.resolve({
          ok: true,
          status: 202,
          headers: new Headers({ 'x-request-id': 'req-ret-2' }),
          json: async () => ({
            job_id: 'j2',
            paper_id: 'p2',
            document_version: 'v2',
            stage: 'validating',
            status: 'pending',
            retry_revision: 1,
            preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 },
            request_id: 'req-ret-2',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<LibraryPage />);
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /try again/i })).toHaveLength(2);
    });

    const buttons = screen.getAllByRole('button', { name: /try again/i });
    await userEvent.click(buttons[0]);

    expect(buttons[0]).toBeDisabled();

    const remainingRetry = buttons[1];
    expect(remainingRetry).toBeEnabled();

    await userEvent.click(remainingRetry);

    await waitFor(() => {
      expect(remainingRetry).not.toBeInTheDocument();
    });

    resolveRetry1({
      ok: true,
      status: 202,
      headers: new Headers({ 'x-request-id': 'req-ret-1' }),
      json: async () => ({
        job_id: 'j1',
        paper_id: 'p1',
        document_version: 'v1',
        stage: 'validating',
        status: 'pending',
        retry_revision: 1,
        preparation: { state: 'delayed', reason: null, retryable: false, retry_after_seconds: 0 },
        request_id: 'req-ret-1',
      }),
    });

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /retrying/i })).not.toBeInTheDocument();
    });
  });
});
