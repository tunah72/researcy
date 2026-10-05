import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReaderWorkspace } from './reader-workspace';
import * as api from '@/lib/api';
import PaperDetailPage from '../app/library/[paperId]/page';

vi.mock('next/navigation', () => ({
  useParams: () => ({ paperId: 'paper-ready' }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('pdfjs-dist', () => ({
  version: 'test-runtime',
  GlobalWorkerOptions: {},
  AnnotationMode: { DISABLE: 0 },
  TextLayer: class { async render() {} cancel() {} },
  getDocument: ({ url }: { url: string }) => ({
    destroy: async () => {},
    promise: Promise.resolve({
      numPages: url === '/api/selected/versions/selected-pinned/pdf' ? 3 : 1,
      getOutline: async () => [],
      getPage: async () => ({
        rotate: 0, view: [0, 0, 612, 792], userUnit: 1,
        getViewport: ({ scale }: { scale: number }) => ({
          width: 612 * scale, height: 792 * scale, scale, transform: [scale, 0, 0, -scale, 0, 792 * scale],
        }),
        render: () => ({ promise: Promise.resolve(), cancel() {} }),
        streamTextContent: () => new ReadableStream({ start(controller) { controller.close(); } }),
        cleanup: () => {},
      }),
    }),
  }),
}));

const readyPaper = {
  paper_id: 'paper-ready', title: 'Attention Is All You Need', authors: null,
  year: null, source: 'upload' as const, stage: 'ready' as const, active_version_id: 'version-ready',
  source_version: null, screening_warning: null, job_id: 'job-ready', retry_revision: 0,
  preparation: { state: 'complete' as const, reason: null, retryable: false, retry_after_seconds: 0 },
  reader: {
    document_version: 'version-ready', source_sha256: 'a'.repeat(64),
    pdf_url: '/api/papers/paper-ready/versions/version-ready/pdf',
    pages: [{ page_index: 0, media_box: [0, 0, 612, 792], crop_box: [0, 0, 612, 792], rotation: 0 }],
    outline: [{ title: 'Introduction', page: 1 }],
  },
  request_id: 'reader-request',
};

const originalWidth = window.innerWidth;
const originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView');
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth });
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', originalScrollIntoView);
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
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

it.each(['previous page', 'page number', 'scroll'] as const)(
  'retains the accepted immutable cross-source PDF after %s browsing, reload and popstate without stale highlights',
  async navigation => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(644);
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() });
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0));
    vi.stubGlobal('cancelAnimationFrame', (frame: number) => window.clearTimeout(frame));
    const selectedSource: api.ReaderDocument = {
      document_version: 'selected-pinned', source_sha256: 'b'.repeat(64),
      pdf_url: '/api/selected/versions/selected-pinned/pdf', outline: [],
      pages: [0, 1, 2].map(page_index => ({
        page_index, media_box: [0, 0, 612, 792], crop_box: [0, 0, 612, 792], rotation: 0,
      })),
    };
    const selectedPaper: api.PaperDetailResponse = {
      ...readyPaper, paper_id: 'selected-paper', title: 'Selected immutable source',
      source: 'upload', stage: 'ready', active_version_id: 'selected-newer', reader: selectedSource,
    };
    const accepted: api.ResolvedCitation = {
      citation_id: 'accepted-premise', paper_id: 'selected-paper', document_version: 'selected-pinned',
      source_ref: 'P1:S1', evidence_quote: 'The exact selected-source premise.', page: 2,
      boxes: [[10, 20, 30, 40]], section: 'Limitations',
    };
    vi.spyOn(api, 'listConversations').mockResolvedValue({ conversations: [], next_before: null, request_id: 'request' });
    vi.spyOn(api, 'getCitation').mockResolvedValue({ citation: accepted, request_id: 'request' });
    vi.spyOn(api, 'getResearchDirections').mockResolvedValue({
      run_id: 'accepted-run', active_paper_id: readyPaper.paper_id, document_version: 'version-ready',
      sources: [{ paper_id: readyPaper.paper_id, document_version: 'version-ready' },
        { paper_id: 'selected-paper', document_version: 'selected-pinned' }],
      state: 'completed', ideas: [{ observed_gap: 'A supported limitation.', proposed_direction: 'Compare approaches.',
        possible_method: 'Run an experiment.', premise_citations: [accepted] }],
      draft_ideas: [], error: null, request_id: 'request',
    });
    vi.spyOn(api, 'fetchPaperDetail').mockImplementation(async (paperId, version) => {
      if (paperId !== 'selected-paper' || version !== 'selected-pinned') {
        throw new api.ApiError(404, 'RESOURCE_NOT_FOUND', 'Not found.');
      }
      return selectedPaper;
    });
    window.history.replaceState(null, '', '/library/paper-ready?document_version=version-ready&research_run=accepted-run');
    const user = userEvent.setup();
    const activePaper: api.PaperDetailResponse = { ...readyPaper, source: 'upload', stage: 'ready',
      reader: readyPaper.reader as api.ReaderDocument };
    const initial = render(<ReaderWorkspace paper={activePaper} source={activePaper.reader!} />);
    await user.click(await screen.findByRole('button', { name: 'Premise citation 1' }));
    await screen.findByRole('heading', { name: 'Selected immutable source' });
    await waitFor(() => expect(document.querySelectorAll('.pdf-evidence-box')).toHaveLength(1));
    expect(screen.getByRole('spinbutton', { name: 'Page number' })).toHaveValue(2);
    const citationUrl = window.location.href;
    const intendedPage = navigation === 'previous page' ? 1 : 3;
    if (navigation === 'previous page') {
      await user.click(screen.getByRole('button', { name: 'Previous page' }));
    } else if (navigation === 'page number') {
      fireEvent.change(screen.getByRole('spinbutton', { name: 'Page number' }), { target: { value: '3' } });
    } else {
      for (const index of [1, 2, 3]) {
        const sheet = screen.getByRole('region', { name: `PDF page ${index}` });
        Object.defineProperties(sheet, { offsetTop: { configurable: true, value: (index - 1) * 792 },
          offsetHeight: { configurable: true, value: 792 } });
      }
      const scroller = screen.getByLabelText('PDF pages');
      scroller.scrollTop = 1584;
      fireEvent.scroll(scroller);
    }
    await waitFor(() => expect(screen.getByRole('spinbutton', { name: 'Page number' })).toHaveValue(intendedPage));
    const browsingUrl = window.location.href;
    const assertBrowsing = async () => {
      expect(await screen.findByRole('heading', { name: 'Selected immutable source' })).toBeVisible();
      await waitFor(() => expect(screen.getByRole('spinbutton', { name: 'Page number' })).toBeEnabled());
      expect(screen.getByRole('spinbutton', { name: 'Page number' })).toHaveValue(intendedPage);
      expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute(
        'href', '/api/selected/versions/selected-pinned/pdf?download=1');
      expect(document.querySelectorAll('.pdf-evidence-box')).toHaveLength(0);
      expect(screen.queryByText(accepted.evidence_quote)).not.toBeInTheDocument();
      expect(screen.queryByRole('region', { name: /evidence/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Premise citation 1' })).toHaveAttribute('aria-expanded', 'false');
      const url = new URL(window.location.href);
      expect(url.searchParams.get('citation')).toBeNull();
      expect(url.searchParams.get('pdf_paper')).toBe('selected-paper');
      expect(url.searchParams.get('pdf_version')).toBe('selected-pinned');
      expect(url.searchParams.get('research_run')).toBe('accepted-run');
      expect(url.searchParams.get('document_version')).toBe('version-ready');
    };
    await assertBrowsing();
    initial.unmount();
    render(<ReaderWorkspace paper={activePaper} source={activePaper.reader!} />);
    await assertBrowsing();
    window.history.pushState(null, '', citationUrl);
    await act(async () => window.dispatchEvent(new PopStateEvent('popstate')));
    await waitFor(() => expect(document.querySelectorAll('.pdf-evidence-box')).toHaveLength(1));
    expect(screen.getByRole('spinbutton', { name: 'Page number' })).toHaveValue(2);
    window.history.pushState(null, '', browsingUrl);
    await act(async () => window.dispatchEvent(new PopStateEvent('popstate')));
    await assertBrowsing();
    await user.click(screen.getByRole('button', { name: 'Return to active paper' }));
    expect(await screen.findByRole('heading', { name: 'Attention Is All You Need' })).toHaveFocus();
    expect(screen.getByRole('spinbutton', { name: 'Page number' })).toHaveValue(1);
    expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute(
      'href', '/api/papers/paper-ready/versions/version-ready/pdf?download=1');
  },
);
