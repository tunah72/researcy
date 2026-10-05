import { afterEach, expect, it, vi } from 'vitest';
import * as api from './api';

const active = '11111111-1111-4111-8111-111111111111';
const selected = '22222222-2222-4222-8222-222222222222';
const version = '33333333-3333-4333-8333-333333333333';
const run = '44444444-4444-4444-8444-444444444444';
const request = '55555555-5555-4555-8555-555555555555';
const citation = { citation_id: '66666666-6666-4666-8666-666666666666', paper_id: selected,
  document_version: version, source_ref: 'P1:S1', evidence_quote: 'Exact source evidence.',
  page: 1, boxes: [[10, 20, 30, 40]], section: null };
const draft = { observed_gap: 'A source limitation.', proposed_direction: 'Compare naïve approaches.',
  possible_method: 'Run a controlled experiment.' };
const identity = { run_id: run, request_id: request };
const delta = { ...identity, sequence: 1, idea_index: 0, idea: draft };
const resolved = { ...identity, idea_index: 0, citation };
const completed = { ...identity, ideas: [{ ...draft, premise_citations: [citation] }] };
const wire = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; vi.restoreAllMocks(); });

function respond(text: string, header = run) {
  const bytes = new TextEncoder().encode(text);
  const stream = new ReadableStream<Uint8Array>({ start(controller) {
    for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7));
    controller.close();
  } });
  globalThis.fetch = vi.fn().mockResolvedValue(new Response(stream, { headers: {
    'Content-Type': 'text/event-stream; charset=utf-8', 'X-Research-Run-ID': header, 'X-Request-ID': request,
  } }));
}

it('retains a reload pointer before fragmented Unicode ideas and accepted evidence arrive', async () => {
  respond(': connected\n\n' + wire('direction.delta', delta) + wire('citation.resolved', resolved) + wire('direction.completed', completed));
  const observed: string[] = [];
  await api.streamResearchDirections(active, [selected], event => observed.push(event.event),
    id => observed.push(id), new AbortController().signal);
  expect(observed).toEqual([run, 'direction.delta', 'citation.resolved', 'direction.completed']);
});

it.each([
  wire('direction.delta', { ...delta, sequence: 2 }),
  wire('direction.delta', { ...delta, run_id: selected }),
  wire('direction.delta', delta) + wire('citation.resolved', { ...resolved, citation: { ...citation, paper_id: version } }),
  wire('direction.delta', delta) + wire('citation.resolved', { ...resolved, citation: { ...citation, boxes: [[30, 20, 10, 40]] } }),
  wire('direction.delta', delta) + wire('citation.resolved', { ...resolved, citation: { ...citation, source_ref: 'P0:S1' } }) +
    wire('direction.completed', { ...completed, ideas: [{ ...draft, premise_citations: [{ ...citation, source_ref: 'P0:S1' }] }] }),
  wire('citation.resolved', resolved),
  wire('direction.delta', delta) + wire('direction.completed', completed),
  wire('direction.delta', delta) + wire('citation.resolved', resolved) + wire('direction.completed', {
    ...completed, ideas: [{ ...draft, observed_gap: 'A changed premise.', premise_citations: [citation] }],
  }),
])('does not accept inconsistent streamed identity, sequence, geometry or terminal evidence (%#)', async text => {
  respond(text);
  const completedIdeas: unknown[] = [];
  await expect(api.streamResearchDirections(active, [selected], event => {
    if (event.event === 'direction.completed') completedIdeas.push(event.data.ideas);
  }, () => {}, new AbortController().signal)).rejects.toMatchObject({ code: 'MALFORMED_STREAM' });
  expect(completedIdeas).toEqual([]);
});

it('keeps provisional ideas interrupted when EOF arrives without terminal commitment', async () => {
  respond(wire('direction.delta', delta));
  await expect(api.streamResearchDirections(active, [selected], () => {}, () => {}, new AbortController().signal))
    .rejects.toMatchObject({ code: 'RESEARCH_INTERRUPTED' });
});

it('abort immediately after reservation does not read or publish a streamed idea', async () => {
  respond(wire('direction.delta', delta));
  const controller = new AbortController();
  const ideas = vi.fn();
  await expect(api.streamResearchDirections(active, [selected], ideas, () => controller.abort(), controller.signal))
    .rejects.toMatchObject({ name: 'AbortError' });
  expect(ideas).not.toHaveBeenCalled();
});

it('does not install an aborted reservation into the current workspace', async () => {
  const controller = new AbortController();
  const reserved = vi.fn();
  globalThis.fetch = vi.fn().mockImplementation(async () => {
    controller.abort();
    return new Response(wire('direction.delta', delta), { headers: {
      'Content-Type': 'text/event-stream', 'X-Research-Run-ID': run, 'X-Request-ID': request,
    } });
  });
  await expect(api.streamResearchDirections(active, [selected], () => {}, reserved, controller.signal))
    .rejects.toMatchObject({ name: 'AbortError' });
  expect(reserved).not.toHaveBeenCalled();
});

it('rejects a saved citation whose source prefix identifies a different pinned paper', async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    run_id: run, active_paper_id: active, document_version: version,
    sources: [{ paper_id: active, document_version: version }, { paper_id: selected, document_version: version }],
    state: 'completed', ideas: [{ ...draft, premise_citations: [{ ...citation, source_ref: 'P0:S1' }] }],
    draft_ideas: [], error: null, request_id: request,
  }), { headers: { 'Content-Type': 'application/json' } }));
  await expect(api.getResearchDirections(active, run)).rejects.toMatchObject({ code: 'MALFORMED_RESPONSE' });
});
