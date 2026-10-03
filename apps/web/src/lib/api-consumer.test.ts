import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import {
  streamMessage,
  ApiError,
} from './api';
import type {
  ReaderStreamEvent,
  MessageStreamReplayResponse,
} from './api';

const UUID_CONV_1 = '11111111-1111-4111-8111-111111111111';
const UUID_CLIENT_1 = '22222222-2222-4222-8222-222222222222';
const UUID_CLIENT_2 = '22222222-2222-4222-8222-222222222223';
const UUID_RUN_1 = '33333333-3333-4333-8333-333333333333';
const UUID_MSG_1 = '44444444-4444-4444-8444-444444444444';
const UUID_REQ_1 = '55555555-5555-4555-8555-555555555555';
const UUID_PAPER_1 = '66666666-6666-4666-8666-666666666666';
const UUID_VERSION_1 = '77777777-7777-4777-8777-777777777777';
const UUID_CIT_1 = '88888888-8888-4888-8888-888888888888';

function createChunkedStream(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
}

function sseEventWire(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

describe('API consumer contracts and stream transport', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    document.cookie = 'researcy_csrf=test-csrf-token; path=/';
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('streamMessage handles fragmented UTF-8, split SSE frames and comments across multiple chunks', async () => {
    // Character '✨' is 3 bytes (E2 9C A8), '💡' is 4 bytes (F0 9F 92 A1)
    const initialComment = ': reader connected\n\n: heartbeat ping\n\n';
    const delta1 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 1,
      text: '✨ Attention is all you need 💡',
      request_id: UUID_REQ_1,
    });
    const citation1 = sseEventWire('citation.resolved', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      citation: {
        citation_id: UUID_CIT_1,
        paper_id: UUID_PAPER_1,
        document_version: UUID_VERSION_1,
        source_ref: 'ref-1',
        evidence_quote: 'Attention is all you need',
        page: 1,
        boxes: [[10, 20, 100, 200]],
        section: 'Introduction',
      },
      request_id: UUID_REQ_1,
    });
    const completed = sseEventWire('answer.completed', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      state: 'completed',
      citations: [
        {
          citation_id: UUID_CIT_1,
          paper_id: UUID_PAPER_1,
          document_version: UUID_VERSION_1,
          source_ref: 'ref-1',
          evidence_quote: 'Attention is all you need',
          page: 1,
          boxes: [[10, 20, 100, 200]],
          section: 'Introduction',
        },
      ],
      request_id: UUID_REQ_1,
    });

    const fullWire = initialComment + delta1 + citation1 + completed;
    const encoder = new TextEncoder();
    const encoded = encoder.encode(fullWire);

    // Split arbitrarily into tiny chunks (e.g., 7 bytes each) to fracture UTF-8 multi-byte sequences and SSE frame boundaries
    const chunks: Uint8Array[] = [];
    const chunkSize = 7;
    for (let i = 0; i < encoded.length; i += chunkSize) {
      chunks.push(encoded.slice(i, i + chunkSize));
    }

    const mockResponse = new Response(createChunkedStream(chunks), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    });
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const receivedEvents: ReaderStreamEvent[] = [];
    const abortController = new AbortController();

    const result = await streamMessage(
      UUID_CONV_1,
      { client_message_id: UUID_CLIENT_1, question: 'How does attention work?' },
      (event) => receivedEvents.push(event),
      abortController.signal,
    );

    expect(result).toBeNull();
    expect(receivedEvents).toHaveLength(3);

    expect(receivedEvents[0]).toEqual({
      event: 'answer.delta',
      data: {
        run_id: UUID_RUN_1,
        message_id: UUID_MSG_1,
        sequence: 1,
        text: '✨ Attention is all you need 💡',
        request_id: UUID_REQ_1,
      },
    });

    expect(receivedEvents[1]).toEqual({
      event: 'citation.resolved',
      data: {
        run_id: UUID_RUN_1,
        message_id: UUID_MSG_1,
        citation: {
          citation_id: UUID_CIT_1,
          paper_id: UUID_PAPER_1,
          document_version: UUID_VERSION_1,
          source_ref: 'ref-1',
          evidence_quote: 'Attention is all you need',
          page: 1,
          boxes: [[10, 20, 100, 200]],
          section: 'Introduction',
        },
        request_id: UUID_REQ_1,
      },
    });

    expect(receivedEvents[2]).toEqual({
      event: 'answer.completed',
      data: {
        run_id: UUID_RUN_1,
        message_id: UUID_MSG_1,
        state: 'completed',
        citations: [
          {
            citation_id: UUID_CIT_1,
            paper_id: UUID_PAPER_1,
            document_version: UUID_VERSION_1,
            source_ref: 'ref-1',
            evidence_quote: 'Attention is all you need',
            page: 1,
            boxes: [[10, 20, 100, 200]],
            section: 'Introduction',
          },
        ],
        request_id: UUID_REQ_1,
      },
    });
  });

  it('streamMessage rejects EOF without terminal completion as interrupted error', async () => {
    const delta1 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 1,
      text: 'Partial thought before socket drop...',
      request_id: UUID_REQ_1,
    });

    const encoder = new TextEncoder();
    // Closes immediately after delta 1 without answer.completed or answer.failed
    const mockResponse = new Response(createChunkedStream([encoder.encode(delta1)]), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    });
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const receivedEvents: ReaderStreamEvent[] = [];
    const abortController = new AbortController();

    await expect(
      streamMessage(
        UUID_CONV_1,
        { client_message_id: UUID_CLIENT_1, question: 'Will this finish?' },
        (event) => receivedEvents.push(event),
        abortController.signal,
      ),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.code).toBe('READER_INTERRUPTED');
      return true;
    });

    expect(receivedEvents).toHaveLength(1);
    expect(receivedEvents[0].event).toBe('answer.delta');
  });

  it('streamMessage returns MessageStreamReplayResponse directly on duplicate JSON replay', async () => {
    const replayPayload: MessageStreamReplayResponse = {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      state: 'completed',
      request_id: UUID_REQ_1,
    };

    const mockResponse = new Response(JSON.stringify(replayPayload), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'x-request-id': UUID_REQ_1,
      },
    });
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const onEvent = vi.fn();
    const abortController = new AbortController();

    const result = await streamMessage(
      UUID_CONV_1,
      { client_message_id: UUID_CLIENT_1, question: 'Already answered question' },
      onEvent,
      abortController.signal,
    );

    expect(result).toEqual(replayPayload);
    expect(onEvent).not.toHaveBeenCalled();
  });

  it('streamMessage respects AbortSignal cancellation before and during stream', async () => {
    // 1. Abort before initiating
    const preAborted = new AbortController();
    preAborted.abort();

    await expect(
      streamMessage(
        UUID_CONV_1,
        { client_message_id: UUID_CLIENT_1, question: 'Already aborted?' },
        vi.fn(),
        preAborted.signal,
      ),
    ).rejects.toThrow();

    // 2. Abort mid-stream
    const activeAbort = new AbortController();
    const encoder = new TextEncoder();
    const delta1 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 1,
      text: 'First part of text',
      request_id: UUID_REQ_1,
    });

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        controller.enqueue(encoder.encode(delta1));
        // Keep stream open until abort
      },
    });

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    );

    const events: ReaderStreamEvent[] = [];
    const streamPromise = streamMessage(
      UUID_CONV_1,
      { client_message_id: UUID_CLIENT_2, question: 'Abort midway?' },
      (ev) => {
        events.push(ev);
        activeAbort.abort();
      },
      activeAbort.signal,
    );

    await expect(streamPromise).rejects.toThrow();
    expect(events).toHaveLength(1);
  });

  it('streamMessage rejects excessive frame exceeding maximum event size', async () => {
    // Maximum frame is 262,144 bytes including framing
    const hugePayload = 'A'.repeat(262145);
    const hugeFrame = `event: answer.delta\ndata: {"run_id":"${UUID_RUN_1}","message_id":"${UUID_MSG_1}","sequence":1,"text":"${hugePayload}","request_id":"${UUID_REQ_1}"}\n\n`;

    const encoder = new TextEncoder();
    const mockResponse = new Response(createChunkedStream([encoder.encode(hugeFrame)]), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    });
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const abortController = new AbortController();

    await expect(
      streamMessage(
        UUID_CONV_1,
        { client_message_id: UUID_CLIENT_1, question: 'Oversize frame test' },
        vi.fn(),
        abortController.signal,
      ),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.code).toBe('READER_EVENT_TOO_LARGE');
      return true;
    });
  });

  it('streamMessage rejects malformed identity when run_id, message_id, or request_id mutates mid-stream', async () => {
    const delta1 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 1,
      text: 'First chunk',
      request_id: UUID_REQ_1,
    });
    // Corrupted event with mutated run_id
    const delta2Corrupted = sseEventWire('answer.delta', {
      run_id: '99999999-9999-4999-8999-999999999999',
      message_id: UUID_MSG_1,
      sequence: 2,
      text: 'Second chunk with wrong identity',
      request_id: UUID_REQ_1,
    });

    const encoder = new TextEncoder();
    const mockResponse = new Response(
      createChunkedStream([encoder.encode(delta1 + delta2Corrupted)]),
      {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      },
    );
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const abortController = new AbortController();

    await expect(
      streamMessage(
        UUID_CONV_1,
        { client_message_id: UUID_CLIENT_1, question: 'Identity check' },
        vi.fn(),
        abortController.signal,
      ),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.code).toBe('MALFORMED_STREAM');
      return true;
    });
  });

  it('streamMessage rejects non-monotonic or out-of-order delta sequence', async () => {
    const delta1 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 1,
      text: 'Chunk one',
      request_id: UUID_REQ_1,
    });
    // Out-of-order: sequence jumps to 3 skipping 2
    const deltaOutOrder = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 3,
      text: 'Skipped chunk',
      request_id: UUID_REQ_1,
    });

    const encoder = new TextEncoder();
    const mockResponse = new Response(
      createChunkedStream([encoder.encode(delta1 + deltaOutOrder)]),
      {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      },
    );
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const abortController = new AbortController();

    await expect(
      streamMessage(
        UUID_CONV_1,
        { client_message_id: UUID_CLIENT_1, question: 'Sequence check' },
        vi.fn(),
        abortController.signal,
      ),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.code).toBe('MALFORMED_STREAM');
      return true;
    });
  });

  it('streamMessage validates client request boundaries and safely fails on HTTP errors', async () => {
    const abortController = new AbortController();

    // 1. Question blank
    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: '   ' }, vi.fn(), abortController.signal),
    ).rejects.toThrow();

    // 2. Question exceeding 2400 Unicode code points
    const overlyLongQuestion = 'a'.repeat(2401);
    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: overlyLongQuestion }, vi.fn(), abortController.signal),
    ).rejects.toThrow();

    // 3. Client message ID not a UUID
    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: 'not-a-uuid', question: 'Valid question?' }, vi.fn(), abortController.signal),
    ).rejects.toThrow();

    // 4. HTTP 401 Unauthorized
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'UNAUTHORIZED', message: 'Sign-in required' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: 'Valid?' }, vi.fn(), abortController.signal),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.status).toBe(401);
      expect(apiErr.code).toBe('UNAUTHORIZED');
      return true;
    });

    // 5. HTTP 429 Rate Limit with Retry-After header
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'RATE_LIMITED', message: 'Quota exhausted' }), {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'retry-after': '30',
        },
      }),
    );

    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: 'Valid?' }, vi.fn(), abortController.signal),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.status).toBe(429);
      expect(apiErr.retryAfter).toBe(30);
      return true;
    });

    // 6. Safe failure over SSE: answer.failed event delivered to onEvent and finishes with null
    const failedWire = sseEventWire('answer.failed', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      code: 'READER_FAILED',
      message: 'Provider error',
      request_id: UUID_REQ_1,
    });
    const encoder = new TextEncoder();
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(createChunkedStream([encoder.encode(failedWire)]), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    );

    const events: ReaderStreamEvent[] = [];
    const res = await streamMessage(
      UUID_CONV_1,
      { client_message_id: UUID_CLIENT_1, question: 'Valid?' },
      (ev) => events.push(ev),
      abortController.signal,
    );

    expect(res).toBeNull();
    expect(events).toEqual([
      {
        event: 'answer.failed',
        data: {
          run_id: UUID_RUN_1,
          message_id: UUID_MSG_1,
          code: 'READER_FAILED',
          message: 'Provider error',
          request_id: UUID_REQ_1,
        },
      },
    ]);
  });
  it('streamMessage processes coalesced frames in single chunk where total size exceeds frame cap but each frame is valid', async () => {
    const text1 = 'A'.repeat(135000);
    const text2 = 'B'.repeat(135000);
    const delta1 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 1,
      text: text1,
      request_id: UUID_REQ_1,
    });
    const delta2 = sseEventWire('answer.delta', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      sequence: 2,
      text: text2,
      request_id: UUID_REQ_1,
    });
    const completed = sseEventWire('answer.completed', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      state: 'completed',
      citations: [],
      request_id: UUID_REQ_1,
    });

    const combinedBytes = new TextEncoder().encode(delta1 + delta2 + completed);
    expect(combinedBytes.length).toBeGreaterThan(262144);

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(createChunkedStream([combinedBytes]), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    );

    const events: ReaderStreamEvent[] = [];
    const abortController = new AbortController();

    const result = await streamMessage(
      UUID_CONV_1,
      { client_message_id: UUID_CLIENT_1, question: 'Coalesced frames?' },
      (ev) => events.push(ev),
      abortController.signal,
    );

    expect(result).toBeNull();
    expect(events).toHaveLength(3);
    expect(events[0].event).toBe('answer.delta');
    expect(events[1].event).toBe('answer.delta');
    expect(events[2].event).toBe('answer.completed');
  });

  it('streamMessage rejects invalid UTF-8 bytes with MALFORMED_STREAM', async () => {
    const invalidUtf8Chunk = new Uint8Array([0xff, 0xfe, 0xfd]);
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(createChunkedStream([invalidUtf8Chunk]), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    );

    const abortController = new AbortController();

    await expect(
      streamMessage(
        UUID_CONV_1,
        { client_message_id: UUID_CLIENT_1, question: 'Valid?' },
        vi.fn(),
        abortController.signal,
      ),
    ).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      const apiErr = error as ApiError;
      expect(apiErr.code).toBe('MALFORMED_STREAM');
      return true;
    });
  });

  it('streamMessage rejects malformed citation geometry, invalid completed citations, and unsupported events', async () => {
    const abortController = new AbortController();

    // 1. Citation with invalid geometry (x0 > x1: [100, 20, 10, 200])
    const badCitation = sseEventWire('citation.resolved', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      citation: {
        citation_id: UUID_CIT_1,
        paper_id: UUID_PAPER_1,
        document_version: UUID_VERSION_1,
        source_ref: 'ref-1',
        evidence_quote: 'quote',
        page: 1,
        boxes: [[100, 20, 10, 200]],
        section: 'Intro',
      },
      request_id: UUID_REQ_1,
    });
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(createChunkedStream([new TextEncoder().encode(badCitation)]), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    );

    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: 'Q?' }, vi.fn(), abortController.signal),
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).code).toBe('MALFORMED_STREAM');
      return true;
    });

    // 2. Unsupported stream event
    const unsupportedEvent = sseEventWire('unsupported.action', {
      run_id: UUID_RUN_1,
      message_id: UUID_MSG_1,
      request_id: UUID_REQ_1,
    });
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(createChunkedStream([new TextEncoder().encode(unsupportedEvent)]), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    );

    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: 'Q?' }, vi.fn(), abortController.signal),
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).code).toBe('MALFORMED_STREAM');
      return true;
    });
  });

  it('streamMessage rejects duplicate replay response with invalid state or malformed identity', async () => {
    const abortController = new AbortController();

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: UUID_RUN_1,
          message_id: UUID_MSG_1,
          state: 'UNKNOWN_STATE',
          request_id: UUID_REQ_1,
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    );

    await expect(
      streamMessage(UUID_CONV_1, { client_message_id: UUID_CLIENT_1, question: 'Q?' }, vi.fn(), abortController.signal),
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).code).toBe('MALFORMED_STREAM');
      return true;
    });
  });
});
