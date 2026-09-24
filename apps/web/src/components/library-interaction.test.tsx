import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LibraryList } from './library-list';
import { AddPaper } from './add-paper';
import LibraryPage from '../app/library/page';
import { Paper } from '@/lib/api';

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
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('empty Library offers Add paper', async () => {
    const onOpenAddPaper = vi.fn();
    render(
      <LibraryList
        papers={[]}
        onOpenAddPaper={onOpenAddPaper}
      />
    );

    expect(screen.getByRole('region', { name: /empty library/i })).toBeInTheDocument();
    expect(screen.getByText(/your library is empty/i)).toBeInTheDocument();

    const addPaperBtn = screen.getByRole('button', { name: /add paper/i });
    expect(addPaperBtn).toBeInTheDocument();

    await userEvent.click(addPaperBtn);
    expect(onOpenAddPaper).toHaveBeenCalledTimes(1);
  });

  it('queued response renders "Waiting for processing"', () => {
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
    };

    render(<LibraryList papers={[queuedPaper]} />);

    expect(screen.getByText('Attention Is All You Need')).toBeInTheDocument();
    expect(screen.getByText('Waiting for processing')).toBeInTheDocument();
    expect(screen.queryByText(/ready/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('warning survives refresh and renders screening note', () => {
    const warnedPaper: Paper = {
      paper_id: '33333333-3333-3333-3333-333333333333',
      title: 'Low Text Document',
      authors: ['Jane Doe'],
      year: 2023,
      source: 'upload',
      stage: 'queued',
      active_version_id: '44444444-4444-4444-4444-444444444444',
      source_version: null,
      screening_warning: 'LOW_TEXT: Total extracted characters under 200',
    };

    render(<LibraryList papers={[warnedPaper]} />);

    expect(screen.getByText('Low Text Document')).toBeInTheDocument();
    expect(screen.getByRole('note')).toBeInTheDocument();
    expect(
      screen.getByText(/LOW_TEXT: Total extracted characters under 200/i)
    ).toBeInTheDocument();
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
    };

    render(<LibraryList papers={[honestPaper]} />);

    expect(screen.getByText('Monograph Without Metadata')).toBeInTheDocument();
    expect(screen.getByText(/unknown author/i)).toBeInTheDocument();
    expect(screen.getByText(/year unknown/i)).toBeInTheDocument();
  });

  it('submission failure keeps field-associated error, request ID, and supports retry', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/papers/arxiv')) {
        return Promise.resolve({
          ok: false,
          status: 422,
          headers: new Headers({ 'x-request-id': 'req-arxiv-err-422' }),
          json: async () => ({
            code: 'INVALID_ARXIV_ID',
            message: 'Malformed or unparseable arXiv identifier.',
            request_id: 'req-arxiv-err-422',
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AddPaper />);

    const input = screen.getByLabelText(/arXiv ID or URL/i);
    const submitBtn = screen.getByRole('button', { name: /import paper/i });

    await userEvent.type(input, 'invalid-id-xyz');
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText('Malformed or unparseable arXiv identifier.')).toBeInTheDocument();
    expect(screen.getByText(/req-arxiv-err-422/i)).toBeInTheDocument();

    // Check that Retry button exists and is field-associated
    const retryBtn = screen.getByRole('button', { name: /retry submission/i });
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

    await userEvent.click(screen.getByRole('tab', { name: /pdf upload/i }));
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
    await userEvent.click(screen.getByRole('button', { name: /^upload pdf$/i }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    fireEvent.change(fileInput, { target: { files: [replacementFile] } });
    await userEvent.click(screen.getByRole('button', { name: /^upload pdf$/i }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));

    const firstHeaders = new Headers(mockFetch.mock.calls[0]?.[1]?.headers);
    const secondHeaders = new Headers(mockFetch.mock.calls[1]?.[1]?.headers);
    expect(secondHeaders.get('Idempotency-Key')).not.toBe(
      firstHeaders.get('Idempotency-Key')
    );
  });

  it('logout failure never claims signed-out', async () => {
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
            message: 'Server failed to revoke active session in database.',
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

    expect(screen.getByText(/sign out failed/i)).toBeInTheDocument();
    expect(screen.getByText(/Server failed to revoke active session in database/i)).toBeInTheDocument();
    expect(screen.getByText(/req-logout-fail-500/i)).toBeInTheDocument();
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
});
