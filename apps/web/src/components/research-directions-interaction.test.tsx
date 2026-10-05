import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReaderWorkspace } from './reader-workspace';
import * as api from '@/lib/api';

vi.mock('./pdf-reader', () => ({ PdfReader: ({ source }: { source: api.ReaderDocument }) =>
  <section aria-label="PDF reader" data-version={source.document_version} /> }));
vi.mock('@/lib/api', async original => ({ ...await original<typeof api>(),
  listConversations: vi.fn(), listMessages: vi.fn(), fetchPapers: vi.fn(), fetchPaperDetail: vi.fn(),
  getCitation: vi.fn(), streamResearchDirections: vi.fn(), getResearchDirections: vi.fn(),
}));
const active = '11111111-1111-4111-8111-111111111111';
const selected = '22222222-2222-4222-8222-222222222222';
const activeVersion = '33333333-3333-4333-8333-333333333333';
const selectedVersion = '44444444-4444-4444-8444-444444444444';
const run = '55555555-5555-4555-8555-555555555555';
const request = '66666666-6666-4666-8666-666666666666';
const source: api.ReaderDocument = { document_version: activeVersion, source_sha256: 'a'.repeat(64),
  pdf_url: '/api/active/original.pdf', outline: [], pages: [0, 1].map(page_index => ({ page_index,
    media_box: [0, 0, 612, 792], crop_box: [0, 0, 612, 792], rotation: 0 })) };
const paper: api.PaperDetailResponse = { paper_id: active, title: 'Active research paper', authors: [], year: 2026,
  source: 'upload', stage: 'ready', active_version_id: activeVersion, source_version: null,
  screening_warning: null, job_id: 'job', retry_revision: 0, preparation: { state: 'complete', reason: null,
    retryable: false, retry_after_seconds: 0 }, request_id: request, reader: source };
const otherSource = { ...source, document_version: selectedVersion, pdf_url: '/api/selected/original.pdf' };
const otherPaper = { ...paper, paper_id: selected, title: 'Selected evidence paper', active_version_id: selectedVersion, reader: otherSource };
const citation: api.ResolvedCitation = { citation_id: '77777777-7777-4777-8777-777777777777', paper_id: selected,
  document_version: selectedVersion, source_ref: 'P1:S1', evidence_quote: 'A selected source limitation.', page: 2,
  boxes: [[10, 20, 30, 40]], section: 'Limitations' };
const idea = { observed_gap: 'A supported limitation.', proposed_direction: 'Compare the approaches.',
  possible_method: 'Run controlled experiments.', premise_citations: [citation] };
const snapshot = { run_id: run, active_paper_id: active, document_version: activeVersion,
  sources: [{ paper_id: active, document_version: activeVersion }, { paper_id: selected, document_version: selectedVersion }],
  state: 'completed' as const, ideas: [idea], draft_ideas: [], error: null, request_id: request };

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(null, '', '/library/' + active);
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [], next_before: null, request_id: request });
  vi.mocked(api.listMessages).mockResolvedValue({ messages: [], next_after: null, request_id: request });
  vi.mocked(api.fetchPapers).mockResolvedValue({ papers: [paper, otherPaper], request_id: request });
  vi.mocked(api.fetchPaperDetail).mockResolvedValue(otherPaper);
  vi.mocked(api.getCitation).mockResolvedValue({ citation, request_id: request });
  vi.mocked(api.getResearchDirections).mockResolvedValue(snapshot);
  vi.mocked(api.streamResearchDirections).mockImplementation(async (_paper, _selected, onEvent, onReserved) => {
    onReserved(run);
    onEvent({ event: 'direction.delta', data: { run_id: run, request_id: request, sequence: 1, idea_index: 0,
      idea: { observed_gap: idea.observed_gap, proposed_direction: idea.proposed_direction, possible_method: idea.possible_method } } });
    onEvent({ event: 'citation.resolved', data: { run_id: run, request_id: request, idea_index: 0, citation } });
    onEvent({ event: 'direction.completed', data: { run_id: run, request_id: request, ideas: [idea] } });
  });
});
afterEach(cleanup);

it('requires an explicit eligible Library selection before generation', async () => {
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  expect(api.fetchPapers).not.toHaveBeenCalled();
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Select research papers' }));
  const checkbox = await screen.findByRole('checkbox', { name: /Selected evidence paper/ });
  expect(checkbox).not.toBeChecked();
  expect(screen.queryByRole('checkbox', { name: /Active research paper/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Generate directions' })).toBeDisabled();
  await user.click(checkbox);
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Generate directions' }));
  expect(await screen.findByText('A supported limitation.')).toBeVisible();
  expect(screen.getByText('Proposed direction — hypothesis')).toBeVisible();
  expect(screen.getByText('Possible method — hypothesis')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Premise citation 1' })).toBeEnabled();
});

it('restores committed related evidence without repinning Discussion, and Escape retains the displayed PDF', async () => {
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}`);
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  const input = await screen.findByRole('textbox', { name: 'Ask a question about this paper' });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, 'My active-paper question');
  const button = await screen.findByRole('button', { name: 'Premise citation 1' });
  await user.click(button);
  expect(await screen.findByRole('heading', { name: 'Selected evidence paper' })).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Ask a question about this paper' })).toHaveValue('My active-paper question');
  expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/api/selected/original.pdf?download=1');
  expect(screen.getByRole('region', { name: 'PDF reader' })).toHaveAttribute('data-version', selectedVersion);
  const url = new URL(window.location.href);
  expect(url.searchParams.get('document_version')).toBe(activeVersion);
  expect(url.searchParams.get('pdf_paper')).toBe(selected);
  expect(url.searchParams.get('pdf_version')).toBe(selectedVersion);
  await user.keyboard('{Escape}');
  expect(button).toHaveFocus();
  expect(new URL(window.location.href).searchParams.get('page')).toBe('2');
  expect(screen.getByRole('heading', { name: 'Selected evidence paper' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Return to active paper' }));
  expect(await screen.findByRole('heading', { name: 'Active research paper' })).toBeVisible();
  expect(input).toHaveValue('My active-paper question');
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
});

it('rejects a tampered related document tuple on reload without generating or highlighting', async () => {
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}&citation=${citation.citation_id}&pdf_paper=${selected}&pdf_version=${activeVersion}&page=2`);
  render(<ReaderWorkspace paper={paper} source={source} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('No approximate location');
  expect(screen.getByRole('heading', { name: 'Active research paper' })).toBeVisible();
  expect(screen.getByRole('region', { name: 'PDF reader' })).toHaveAttribute('data-version', activeVersion);
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
});

it('cancels provisional directions, preserves the composer, and ignores a late terminal callback', async () => {
  let emit: Parameters<typeof api.streamResearchDirections>[2] | undefined;
  const deferred = Promise.withResolvers<void>();
  vi.mocked(api.streamResearchDirections).mockImplementation(async (_paper, _selected, onEvent, onReserved) => {
    emit = onEvent;
    onReserved(run);
    onEvent({ event: 'direction.delta', data: { run_id: run, request_id: request, sequence: 1, idea_index: 0,
      idea: { observed_gap: idea.observed_gap, proposed_direction: idea.proposed_direction, possible_method: idea.possible_method } } });
    await deferred.promise;
  });
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  const input = await screen.findByRole('textbox', { name: 'Ask a question about this paper' });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, 'Preserve this question');
  await user.click(screen.getByRole('button', { name: 'Select research papers' }));
  await user.click(await screen.findByRole('checkbox', { name: /Selected evidence paper/ }));
  await user.click(screen.getByRole('button', { name: 'Generate directions' }));
  expect(await screen.findByText(/Unaccepted draft/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Premise citation 1' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
  expect(input).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Cancel directions' }));
  expect(input).toHaveValue('Preserve this question');
  expect(screen.getByRole('button', { name: 'Generate directions' })).toHaveFocus();
  await act(async () => {
    emit?.({ event: 'direction.completed', data: { run_id: run, request_id: request, ideas: [idea] } });
    deferred.resolve();
  });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled());
  expect(screen.queryByRole('button', { name: 'Premise citation 1' })).not.toBeInTheDocument();
});

it('does not let a stale related-paper detail response override Escape cancellation', async () => {
  const deferred = Promise.withResolvers<api.PaperDetailResponse>();
  vi.mocked(api.fetchPaperDetail).mockImplementation(() => deferred.promise);
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}`);
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Premise citation 1' }));
  await waitFor(() => expect(api.fetchPaperDetail).toHaveBeenCalled());
  await user.keyboard('{Escape}');
  await act(async () => deferred.resolve(otherPaper));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Close evidence' })).not.toBeInTheDocument());
  expect(screen.getByRole('heading', { name: 'Active research paper' })).toBeVisible();
  expect(screen.getByRole('region', { name: 'PDF reader' })).toHaveAttribute('data-version', activeVersion);
});

it('prevents a fourth ready selection and keeps waiting papers ineligible', async () => {
  const third = { ...otherPaper, paper_id: '88888888-8888-4888-8888-888888888888', title: 'Third paper' };
  const fourth = { ...otherPaper, paper_id: '99999999-9999-4999-8999-999999999999', title: 'Fourth paper' };
  const fifth = { ...otherPaper, paper_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', title: 'Fifth paper' };
  const waiting = { ...otherPaper, paper_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', title: 'Waiting paper', stage: 'queued' as const };
  vi.mocked(api.fetchPapers).mockResolvedValue({ papers: [paper, otherPaper, third, fourth, fifth, waiting], request_id: request });
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(screen.getByRole('button', { name: 'Select research papers' }));
  const selectedCheckbox = await screen.findByRole('checkbox', { name: /Selected evidence paper/ });
  await user.click(selectedCheckbox);
  await user.click(screen.getByRole('checkbox', { name: /Third paper/ }));
  await user.click(screen.getByRole('checkbox', { name: /Fourth paper/ }));
  expect(screen.getByRole('checkbox', { name: /Fifth paper/ })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: /Waiting paper/ })).toBeDisabled();
  expect(screen.getByRole('group', { name: 'Select related sources · 3/3' })).toHaveAccessibleDescription(/at most three/);
  await user.click(selectedCheckbox);
  expect(screen.getByRole('checkbox', { name: /Fifth paper/ })).toBeEnabled();
  expect(screen.getByRole('checkbox', { name: /Waiting paper/ })).toBeDisabled();
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
});

it('shows unavailable evidence when an authenticated Research run no longer resolves', async () => {
  vi.mocked(api.getResearchDirections).mockRejectedValue(new api.ApiError(404, 'RESOURCE_NOT_FOUND', 'Not found.'));
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}&citation=${citation.citation_id}&pdf_paper=${selected}&pdf_version=${selectedVersion}&page=2`);
  render(<ReaderWorkspace paper={paper} source={source} />);
  const card = await screen.findByRole('region', { name: 'Evidence' });
  expect(card).toHaveTextContent('No approximate location');
  expect(screen.getByRole('region', { name: 'PDF reader' })).toHaveAttribute('data-version', activeVersion);
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
});

it('excludes all generation while a restored run is pending and permits a saved-state reload', async () => {
  vi.mocked(api.getResearchDirections).mockResolvedValueOnce({ ...snapshot, state: 'running', ideas: [] });
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}`);
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await screen.findByText(/The saved run is still pending/);
  await user.type(screen.getByRole('textbox', { name: 'Ask a question about this paper' }), 'An active question');
  expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Related papers' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Select research papers' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Reload saved directions' }));
  await screen.findByRole('button', { name: 'Premise citation 1' });
  expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Related papers' })).toBeEnabled();
  expect(api.streamResearchDirections).not.toHaveBeenCalled();
});

it('clears old run evidence and rejects its late source response when starting another run', async () => {
  const detail = Promise.withResolvers<api.PaperDetailResponse>();
  const generation = Promise.withResolvers<void>();
  const nextRun = '88888888-8888-4888-8888-888888888888';
  vi.mocked(api.fetchPaperDetail).mockImplementation(() => detail.promise);
  vi.mocked(api.streamResearchDirections).mockImplementation(async (_paper, _selected, _event, reserved) => {
    reserved(nextRun);
    await generation.promise;
    throw new api.ApiError(409, 'RESEARCH_INTERRUPTED', 'Interrupted.');
  });
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}`);
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Premise citation 1' }));
  await waitFor(() => expect(api.fetchPaperDetail).toHaveBeenCalled());
  expect(screen.getByRole('region', { name: 'Evidence' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Select research papers' }));
  await screen.findByRole('checkbox', { name: /Selected evidence paper/ });
  await user.click(screen.getByRole('button', { name: 'Generate directions' }));
  expect(screen.queryByRole('region', { name: 'Evidence' })).not.toBeInTheDocument();
  expect(new URL(window.location.href).searchParams.get('research_run')).toBe(nextRun);
  expect(new URL(window.location.href).searchParams.get('citation')).toBeNull();
  await act(async () => { detail.resolve(otherPaper); generation.resolve(); });
  expect(screen.getByRole('heading', { name: 'Active research paper' })).toBeVisible();
  expect(new URL(window.location.href).searchParams.get('citation')).toBeNull();
});

it('returns keyboard focus to the active document after a citation-free selected PDF reload', async () => {
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&research_run=${run}&pdf_paper=${selected}&pdf_version=${selectedVersion}&page=2`);
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Return to active paper' }));
  expect(await screen.findByRole('heading', { name: 'Active research paper' })).toHaveFocus();
  expect(screen.getByRole('region', { name: 'PDF reader' })).toHaveAttribute('data-version', activeVersion);
  expect(new URL(window.location.href).searchParams.get('pdf_paper')).toBeNull();
});

it('does not let delayed Research reservation headers close a newer Discussion citation', async () => {
  const discussionCitation = { ...citation, citation_id: '99999999-9999-4999-8999-999999999999',
    paper_id: active, document_version: activeVersion, source_ref: 'S1', evidence_quote: 'An active Discussion premise.' };
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [{ id: 'conversation', paper_id: active,
    document_version: activeVersion, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
    last_message: null }], next_before: null, request_id: request });
  vi.mocked(api.listMessages).mockResolvedValue({ messages: [{ id: 'message', sequence: 1, role: 'assistant',
    text: 'A supported answer.', state: 'completed', error_code: null, request_id: request,
    created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', citations: [discussionCitation] }],
    next_after: null, request_id: request });
  vi.mocked(api.getCitation).mockImplementation(async id => ({ citation: id === discussionCitation.citation_id ?
    discussionCitation : citation, request_id: request }));
  const generation = Promise.withResolvers<void>();
  let reserved: Parameters<typeof api.streamResearchDirections>[3] | undefined;
  const nextRun = '88888888-8888-4888-8888-888888888888';
  vi.mocked(api.streamResearchDirections).mockImplementation(async (_paper, _selected, _event, onReserved) => {
    reserved = onReserved;
    await generation.promise;
    throw new api.ApiError(409, 'RESEARCH_INTERRUPTED', 'Interrupted.');
  });
  window.history.replaceState(null, '', `/library/${active}?document_version=${activeVersion}&conversation=conversation&research_run=${run}`);
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Premise citation 1' }));
  await screen.findByRole('heading', { name: 'Selected evidence paper' });
  await user.click(screen.getByRole('button', { name: 'Select research papers' }));
  await screen.findByRole('checkbox', { name: /Selected evidence paper/ });
  await user.click(screen.getByRole('button', { name: 'Generate directions' }));
  await user.click(await screen.findByRole('button', { name: 'Citation 1' }));
  await screen.findByText(discussionCitation.evidence_quote);
  await act(async () => { reserved?.(nextRun); generation.resolve(); });
  expect(screen.getByText(discussionCitation.evidence_quote)).toBeVisible();
  expect(new URL(window.location.href).searchParams.get('citation')).toBe(discussionCitation.citation_id);
  expect(new URL(window.location.href).searchParams.get('research_run')).toBe(nextRun);
});
