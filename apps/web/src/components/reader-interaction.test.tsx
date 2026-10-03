import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import PaperDetailPage from '../app/library/[paperId]/page';

vi.mock('next/navigation', () => ({
  useParams: () => ({ paperId: 'paper-ready' }),
  useSearchParams: () => new URLSearchParams(),
}));

const readyPaper = {
  paper_id: 'paper-ready', title: 'Attention Is All You Need', authors: null,
  year: null, source: 'upload', stage: 'ready', active_version_id: 'version-ready',
  source_version: null, screening_warning: null, job_id: 'job-ready', retry_revision: 0,
  preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 },
  reader: {
    document_version: 'version-ready', source_sha256: 'a'.repeat(64),
    pdf_url: '/api/papers/paper-ready/versions/version-ready/pdf',
    pages: [{ page_index: 0, media_box: [0, 0, 612, 792], crop_box: [0, 0, 612, 792], rotation: 0 }],
    outline: [{ title: 'Introduction', page: 1 }],
  },
  request_id: 'reader-request',
};

const originalWidth = window.innerWidth;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth });
});

it('opens a ready original with PDF navigation and an owner-scoped download', async () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(readyPaper))));
  render(<PaperDetailPage />);
  expect(await screen.findByRole('link', { name: /download pdf/i }))
    .toHaveAttribute('href', readyPaper.reader.pdf_url + '?download=1');
  expect(await screen.findByRole('region', { name: /pdf reader/i })).toBeVisible();
  expect(screen.getByRole('spinbutton', { name: /page number/i })).toBeVisible();
  expect(screen.getByRole('button', { name: /next page/i })).toBeVisible();
  expect(screen.getAllByRole('main')).toHaveLength(1);
});

it('keeps the original downloadable below the Reader boundary and opens panes at 1024px', async () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1023 });
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(readyPaper))));
  render(<PaperDetailPage />);
  expect(await screen.findByRole('link', { name: /download pdf/i })).toBeVisible();
  expect(screen.queryByRole('region', { name: /pdf reader/i })).not.toBeInTheDocument();
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
  fireEvent(window, new Event('resize'));
  expect(await screen.findByRole('region', { name: /pdf reader/i })).toBeVisible();
});
