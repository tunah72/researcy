import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReaderWorkspace } from './reader-workspace';
import type { PaperDetailResponse, ReaderDocument } from '@/lib/api';

const source: ReaderDocument = {
  document_version: 'version-a', source_sha256: 'a'.repeat(64), pdf_url: '/api/papers/paper-a/versions/version-a/pdf',
  pages: [{ page_index: 0, media_box: [0,0,612,792], crop_box: [0,0,612,792], rotation: 0 }], outline: [],
};
const paper: PaperDetailResponse = {
  paper_id: 'paper-a', title: 'Attention mechanisms', authors: null, year: null, source: 'upload', stage: 'ready',
  active_version_id: 'version-a', source_version: null, screening_warning: null, job_id: 'job-a', retry_revision: 0,
  preparation: { state: 'complete', reason: null, retryable: false, retry_after_seconds: 0 }, request_id: 'source-request',
};
const candidates = [
  { arxiv_id: '2005.11401', title: 'Retrieval augmented generation', authors: ['First author'], reason: 'A metadata-based sequence-modeling connection.', arxiv_url: 'https://arxiv.org/abs/2005.11401' },
  { arxiv_id: '1810.04805', title: 'Bidirectional representations', authors: [], reason: 'Attention appears in the supplied abstract.', arxiv_url: 'https://arxiv.org/abs/1810.04805' },
];
const accepted = { paper_id: 'saved-paper', document_version: 'saved-version', job_id: 'saved-job', stage: 'queued', screening_warning: null, source_version: 'v1', request_id: 'accepted-request' };
const json = (value: unknown, status = 200, headers: HeadersInit = {}) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const originalWidth = window.innerWidth;
let requests: { path: string; options?: RequestInit }[];
let related: (options?: RequestInit) => Promise<Response>;
let importing: (options?: RequestInit) => Promise<Response>;

beforeEach(() => {
  requests = [];
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  related = async () => json({ papers: candidates, request_id: 'related-request' });
  importing = async () => json(accepted, 202);
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, options?: RequestInit) => {
    const path = String(input);
    requests.push({ path, options });
    if (path.endsWith('/related:search')) return related(options);
    if (path === '/api/papers/arxiv') return importing(options);
    if (path.includes('/conversations')) return json({ conversations: [], next_before: null, request_id: 'conversation-request' });
    throw new Error('Unexpected browser request');
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth });
});
const searches = () => requests.filter(request => request.path.endsWith('/related:search'));
const imports = () => requests.filter(request => request.path === '/api/papers/arxiv');

it('requires explicit search and a separate canonical Add, and keeps accepted queued state honest', async () => {
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  const button = await screen.findByRole('button', { name: 'Related papers' });
  expect(searches()).toHaveLength(0);
  expect(imports()).toHaveLength(0);
  await user.click(button);
  const card = await screen.findByRole('article', { name: candidates[0].title });
  expect(within(card).getByText(candidates[0].reason)).toBeVisible();
  expect(within(card).getByRole('link', { name: /arxiv/i })).toHaveAttribute('href', candidates[0].arxiv_url);
  expect(imports()).toHaveLength(0);
  await user.click(within(card).getByRole('button', { name: 'Add to Library' }));
  expect(await within(card).findByRole('link', { name: 'View in Library' })).toHaveAttribute('href', '/library/saved-paper');
  expect(within(card).getByText(/waiting for processing/i)).toBeVisible();
  expect(within(card).queryByText(/ready to read/i)).not.toBeInTheDocument();
  expect(imports()).toHaveLength(1);
  expect(JSON.parse(String(imports()[0].options?.body))).toEqual({ arxiv_id_or_url: '2005.11401' });
  expect(searches()).toHaveLength(1);
  expect(screen.getAllByRole('main')).toHaveLength(1);
  expect(screen.getByRole('textbox', { name: /question/i })).toBeVisible();
});

it('retains the exact Add key on an unknown outcome, while another candidate gets a distinct key', async () => {
  const user = userEvent.setup();
  let attempt = 0;
  importing = async () => { if (++attempt === 1) throw new TypeError('Controlled network loss'); return json(accepted, 202); };
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  const first = await screen.findByRole('article', { name: candidates[0].title });
  await user.click(within(first).getByRole('button', { name: 'Add to Library' }));
  await within(first).findByRole('alert');
  await user.click(within(first).getByRole('button', { name: /retry add/i }));
  await within(first).findByRole('link', { name: 'View in Library' });
  const second = screen.getByRole('article', { name: candidates[1].title });
  await user.click(within(second).getByRole('button', { name: 'Add to Library' }));
  await within(second).findByRole('link', { name: 'View in Library' });
  const keys = imports().map(request => new Headers(request.options?.headers).get('Idempotency-Key'));
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  expect(keys[2]).not.toBe(keys[0]);
  expect(imports()[0].options?.body).toBe(imports()[1].options?.body);
  expect(JSON.parse(String(imports()[2].options?.body))).toEqual({ arxiv_id_or_url: '1810.04805' });
});

it('cancels the one browser search without retry, and discards its late response', async () => {
  const user = userEvent.setup();
  let resolve!: (value: Response) => void;
  related = () => new Promise<Response>(done => { resolve = done; });
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  await user.click(await screen.findByRole('button', { name: 'Cancel search' }));
  expect(searches()[0].options?.signal?.aborted).toBe(true);
  await act(async () => { resolve(json({ papers: candidates, request_id: 'late' })); });
  expect(screen.queryByRole('article', { name: candidates[0].title })).not.toBeInTheDocument();
  expect(searches()).toHaveLength(1);
  expect(imports()).toHaveLength(0);
});

it('aborts source A on navigation and never replaces source B with a stale result', async () => {
  const user = userEvent.setup();
  let resolve!: (value: Response) => void;
  related = () => new Promise<Response>(done => { resolve = done; });
  const { rerender } = render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  rerender(<ReaderWorkspace paper={{ ...paper, paper_id: 'paper-b', active_version_id: 'version-b' }} source={{ ...source, document_version: 'version-b' }} />);
  await waitFor(() => expect(searches()[0].options?.signal?.aborted).toBe(true));
  await act(async () => { resolve(json({ papers: candidates, request_id: 'late-a' })); });
  expect(screen.queryByRole('article', { name: candidates[0].title })).not.toBeInTheDocument();
  expect(searches()).toHaveLength(1);
  expect(await screen.findByRole('button', { name: 'Related papers' })).toBeEnabled();
});

it('keeps stop empty and missing metadata distinct and retries only after user intent', async () => {
  const user = userEvent.setup();
  let attempt = 0;
  related = async () => ++attempt === 1 ? json({ papers: [], request_id: 'empty' }) : json({ code: 'DISCOVERY_METADATA_MISSING', message: 'unsafe raw diagnostic', request_id: 'missing' }, 409);
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  expect(await screen.findByText(/no related papers/i)).toBeVisible();
  expect(searches()).toHaveLength(1);
  await user.click(screen.getByRole('button', { name: 'Search again' }));
  expect(await within(screen.getByRole('region', { name: 'Related papers' })).findByRole('alert')).toHaveTextContent(/usable title/i);
  expect(screen.queryByText('unsafe raw diagnostic')).not.toBeInTheDocument();
  expect(searches()).toHaveLength(2);
  expect(imports()).toHaveLength(0);
});

it('does not expose active discovery in a historical Reader or below its viewport boundary', async () => {
  const { rerender } = render(<ReaderWorkspace paper={paper} source={{ ...source, document_version: 'historical-version' }} />);
  expect(await screen.findByRole('button', { name: 'Related papers' })).toBeDisabled();
  expect(screen.getByText(/active document version/i)).toBeVisible();
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1023 });
  await act(async () => window.dispatchEvent(new Event('resize')));
  expect(screen.queryByRole('button', { name: 'Related papers' })).not.toBeInTheDocument();
  rerender(<ReaderWorkspace paper={paper} source={source} />);
  expect(searches()).toHaveLength(0);
  expect(imports()).toHaveLength(0);
});

it('blocks repeated search during a server cooldown without a hidden retry', async () => {
  const user = userEvent.setup();
  related = async () => json({ code: 'DISCOVERY_RATE_LIMITED', message: 'unsafe quota diagnostic', request_id: 'limited' }, 429, { 'Retry-After': '30' });
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  const region = screen.getByRole('region', { name: 'Related papers' });
  expect(await within(region).findByRole('alert')).toHaveTextContent(/wait before searching/i);
  expect(within(region).getByRole('button', { name: 'Search again' })).toBeDisabled();
  expect(within(region).getByText(/search again in 30 seconds/i)).toBeVisible();
  expect(searches()).toHaveLength(1);
  expect(imports()).toHaveLength(0);
});

it('discards a pending Add result when navigating away from its source', async () => {
  const user = userEvent.setup();
  let resolve!: (value: Response) => void;
  importing = () => new Promise<Response>(done => { resolve = done; });
  const { rerender } = render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  await user.click(within(await screen.findByRole('article', { name: candidates[0].title })).getByRole('button', { name: 'Add to Library' }));
  rerender(<ReaderWorkspace paper={{ ...paper, paper_id: 'paper-b', active_version_id: 'version-b' }} source={{ ...source, document_version: 'version-b' }} />);
  await act(async () => { resolve(json(accepted, 202)); });
  expect(screen.queryByRole('link', { name: 'View in Library' })).not.toBeInTheDocument();
  expect(await screen.findByRole('button', { name: 'Related papers' })).toBeEnabled();
  expect(imports()).toHaveLength(1);
});

it('does not permit discovery for an active version still preparing', async () => {
  render(<ReaderWorkspace paper={{ ...paper, stage: 'embedding' }} source={source} />);
  expect(await screen.findByRole('button', { name: 'Related papers' })).toBeDisabled();
  expect(screen.getByText(/after the active document finishes processing/i)).toBeVisible();
  expect(searches()).toHaveLength(0);
});

it('abandons an in-flight discovery when its displayed source becomes historical', async () => {
  const user = userEvent.setup();
  let resolve!: (value: Response) => void;
  related = () => new Promise<Response>(done => { resolve = done; });
  const { rerender } = render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  rerender(<ReaderWorkspace paper={{ ...paper, active_version_id: 'new-active-version' }} source={source} />);
  expect(searches()[0].options?.signal?.aborted).toBe(true);
  await act(async () => { resolve(json({ papers: candidates, request_id: 'stale-ready' })); });
  expect(screen.queryByRole('article', { name: candidates[0].title })).not.toBeInTheDocument();
  expect(await screen.findByRole('button', { name: 'Related papers' })).toBeDisabled();
});

it('restores keyboard focus after a pending search fails and gives honest not-ready guidance', async () => {
  const user = userEvent.setup();
  let resolve!: (value: Response) => void;
  related = () => new Promise<Response>(done => { resolve = done; });
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Related papers' }));
  screen.getByRole('button', { name: 'Cancel search' }).focus();
  await act(async () => { resolve(json({ code: 'PAPER_NOT_READY', message: 'unsafe processing diagnostic', request_id: 'stale-ready' }, 409)); });
  const region = screen.getByRole('region', { name: 'Related papers' });
  expect(within(region).getByRole('alert')).toHaveTextContent(/finish processing/i);
  expect(within(region).getByRole('button', { name: 'Search again' })).toHaveFocus();
  expect(screen.queryByText('unsafe processing diagnostic')).not.toBeInTheDocument();
});
