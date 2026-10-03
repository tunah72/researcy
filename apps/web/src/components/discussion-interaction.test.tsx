import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Discussion } from './discussion';
import * as api from '@/lib/api';
import type {
  ResolvedCitation,
  Conversation,
  Message,
  ReaderStreamEvent,
} from '@/lib/api';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    listMessages: vi.fn(),
    streamMessage: vi.fn(),
    getCitation: vi.fn(),
  };
});

const mockCitation1: ResolvedCitation = {
  citation_id: 'cit-0001-0000-0000-000000000001',
  paper_id: 'paper-1111-1111-1111-111111111111',
  document_version: 'ver-2222-2222-2222-222222222222',
  source_ref: 'sec-1-para-2',
  evidence_quote: 'The Transformer is the first transduction model relying entirely on self-attention.',
  page: 1,
  boxes: [[50, 100, 500, 150]],
  section: 'Introduction',
};

const mockCitation2: ResolvedCitation = {
  citation_id: 'cit-0002-0000-0000-000000000002',
  paper_id: 'paper-1111-1111-1111-111111111111',
  document_version: 'ver-2222-2222-2222-222222222222',
  source_ref: 'sec-3-para-1',
  evidence_quote: 'Multi-head attention allows the model to jointly attend to information from different representation subspaces.',
  page: 4,
  boxes: [[72, 200, 480, 240]],
  section: 'Model Architecture',
};

describe('Discussion Component Interaction Tests', () => {
  const mockOnCitation = vi.fn();
  const mockOnUnauthorized = vi.fn();

  beforeEach(() => {
    vi.resetAllMocks();
    window.history.replaceState(null, '', '/library/paper-1111-1111-1111-111111111111');
    mockOnCitation.mockReset();
    mockOnUnauthorized.mockReset();
    vi.mocked(api.listConversations).mockResolvedValue({
      conversations: [],
      next_before: null,
      request_id: 'req-list-convs',
    });
    vi.mocked(api.listMessages).mockResolvedValue({
      messages: [],
      next_after: null,
      request_id: 'req-list-msgs',
    });
    vi.mocked(api.createConversation).mockResolvedValue({
      conversation: {
        id: 'conv-new-1',
        paper_id: 'paper-1111-1111-1111-111111111111',
        document_version: 'ver-2222-2222-2222-222222222222',
        created_at: '2026-10-01T12:00:00Z',
        updated_at: '2026-10-01T12:00:00Z',
        last_message: null,
      },
      request_id: 'req-create-conv',
    });
    vi.mocked(api.streamMessage).mockResolvedValue(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('persisted pagination/reload: loads existing conversation messages and supports pagination with next_after', async () => {
    const existingConv: Conversation = {
      id: 'conv-persisted-1',
      paper_id: 'paper-1111-1111-1111-111111111111',
      document_version: 'ver-2222-2222-2222-222222222222',
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-01T10:05:00Z',
      last_message: {
        id: 'msg-2',
        role: 'assistant',
        text: 'Self-attention calculates token interactions directly.',
        state: 'completed',
      },
    };

    const initialMessages: Message[] = [
      {
        id: 'msg-1',
        sequence: 1,
        role: 'user',
        text: 'What is self-attention?',
        state: 'completed',
        error_code: null,
        request_id: 'req-m1',
        created_at: '2026-10-01T10:01:00Z',
        updated_at: '2026-10-01T10:01:00Z',
        citations: [],
      },
      {
        id: 'msg-2',
        sequence: 2,
        role: 'assistant',
        text: 'Self-attention calculates token interactions directly.',
        state: 'completed',
        error_code: null,
        request_id: 'req-m2',
        created_at: '2026-10-01T10:02:00Z',
        updated_at: '2026-10-01T10:02:00Z',
        citations: [mockCitation1],
      },
    ];

    vi.mocked(api.listConversations).mockResolvedValueOnce({
      conversations: [existingConv],
      next_before: null,
      request_id: 'req-convs',
    });

    vi.mocked(api.listMessages).mockResolvedValueOnce({
      messages: initialMessages,
      next_after: 'cursor-after-msg-2',
      request_id: 'req-msgs-p1',
    });

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    expect(await screen.findByText('What is self-attention?')).toBeInTheDocument();
    expect(screen.getByText('Self-attention calculates token interactions directly.')).toBeInTheDocument();

    const loadMoreBtn = await screen.findByRole('button', { name: /load more messages|load earlier/i });
    expect(loadMoreBtn).toBeInTheDocument();

    const paginatedMessages: Message[] = [
      {
        id: 'msg-3',
        sequence: 3,
        role: 'user',
        text: 'Does it use recurrence?',
        state: 'completed',
        error_code: null,
        request_id: 'req-m3',
        created_at: '2026-10-01T10:03:00Z',
        updated_at: '2026-10-01T10:03:00Z',
        citations: [],
      },
    ];

    vi.mocked(api.listMessages).mockResolvedValueOnce({
      messages: paginatedMessages,
      next_after: null,
      request_id: 'req-msgs-p2',
    });

    fireEvent.click(loadMoreBtn);

    await waitFor(() => {
      expect(api.listMessages).toHaveBeenCalledWith('conv-persisted-1', 'cursor-after-msg-2', expect.any(AbortSignal));
    });

    expect(await screen.findByText('Does it use recurrence?')).toBeInTheDocument();
  });

  it('explicit one UUID submit: sends exactly one client message UUID for new user question', async () => {
    const user = userEvent.setup();

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'How does multi-head attention work?');

    const submitBtn = screen.getByRole('button', { name: /send|ask|submit/i });
    await user.click(submitBtn);


    await waitFor(() => {
      expect(api.streamMessage).toHaveBeenCalledTimes(1);
    });

    const [conversationId, submission] = vi.mocked(api.streamMessage).mock.calls[0];
    expect(conversationId).toBe('conv-new-1');
    expect(submission.question).toBe('How does multi-head attention work?');
    expect(submission.client_message_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    );
  });

  it('provisional claims not accepted until terminal: shows streaming draft text but citations remain unaccepted until terminal completion', async () => {
    const user = userEvent.setup();

    let streamHandler: ((event: ReaderStreamEvent) => void) | null = null;
    vi.mocked(api.streamMessage).mockImplementation(
      async (_convId, _sub, onEvent) => {
        streamHandler = onEvent;
        const { promise } = Promise.withResolvers<null>();
        return promise;
      }
    );

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'Explain multi-head attention.');
    const submitBtn = screen.getByRole('button', { name: /send|ask|submit/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(streamHandler).not.toBeNull();
    });

    act(() => {
      streamHandler!({
        event: 'answer.delta',
        data: {
          run_id: 'run-1',
          message_id: 'msg-assist-1',
          sequence: 1,
          text: 'Multi-head attention projects queries, keys, and values linearly.',
          request_id: 'req-1',
        },
      });
    });

    expect(await screen.findByText(/Multi-head attention projects queries, keys, and values linearly/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /citation/i })).not.toBeInTheDocument();

    act(() => {
      streamHandler!({
        event: 'citation.resolved',
        data: {
          run_id: 'run-1',
          message_id: 'msg-assist-1',
          citation: mockCitation2,
          request_id: 'req-1',
        },
      });
    });

    expect(screen.queryByRole('button', { name: /citation/i })).not.toBeInTheDocument();

    act(() => {
      streamHandler!({
        event: 'answer.completed',
        data: {
          run_id: 'run-1',
          message_id: 'msg-assist-1',
          state: 'completed',
          citations: [mockCitation2],
          request_id: 'req-1',
        },
      });
    });

    const citationButton = await screen.findByRole('button', { name: /citation/i });
    expect(citationButton).toBeInTheDocument();
    expect(citationButton).toHaveAttribute('aria-controls', 'evidence-card');
  });

  it('refusal: renders honest refusal message with no citations and refusal status', async () => {
    const user = userEvent.setup();

    vi.mocked(api.streamMessage).mockImplementation(
      async (_convId, _sub, onEvent) => {
        onEvent({
          event: 'answer.delta',
          data: {
            run_id: 'run-refuse',
            message_id: 'msg-refuse',
            sequence: 1,
            text: 'The paper does not report carbon footprint or energy consumption.',
            request_id: 'req-refuse-1',
          },
        });
        onEvent({
          event: 'answer.completed',
          data: {
            run_id: 'run-refuse',
            message_id: 'msg-refuse',
            state: 'refused',
            citations: [],
            request_id: 'req-refuse-2',
          },
        });
        return null;
      }
    );

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'What was the carbon footprint of training the model?');
    await user.click(screen.getByRole('button', { name: /send|ask|submit/i }));

    expect(await screen.findByText(/The paper does not report carbon footprint or energy consumption/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /citation/i })).not.toBeInTheDocument();
    expect(screen.getByText(/refusal|unsupported/i)).toBeInTheDocument();
  });

  it('no autoconnect/retry: stream failure does not automatically reconnect or retry', async () => {
    const user = userEvent.setup();

    vi.mocked(api.streamMessage).mockRejectedValueOnce(new Error('Network disconnected'));

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'Does it use recurrent layers?');
    await user.click(screen.getByRole('button', { name: /send|ask|submit/i }));

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(api.streamMessage).toHaveBeenCalledTimes(1);

    const { promise: delayPromise, resolve: delayResolve } = Promise.withResolvers<void>();
    setTimeout(delayResolve, 50);
    await delayPromise;
    expect(api.streamMessage).toHaveBeenCalledTimes(1);
  });

  it('EOF or 429 safe explicit retry: interrupted stream or 429 presents safe explicit retry without false completion', async () => {
    const user = userEvent.setup();

    const rateLimitError = new api.ApiError(429, 'RATE_LIMIT_EXCEEDED', 'Too many requests. Please retry later.');
    vi.mocked(api.streamMessage).mockRejectedValueOnce(rateLimitError);

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'Explain positional encodings.');
    await user.click(screen.getByRole('button', { name: /send|ask|submit/i }));

    const retryBtn = await screen.findByRole('button', { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();
    expect(screen.queryByText(/completed/i)).not.toBeInTheDocument();
  });

  it('new UUID on retry: clicking explicit retry submits with a new client message UUID', async () => {
    const user = userEvent.setup();

    vi.mocked(api.streamMessage)
      .mockRejectedValueOnce(new Error('Connection terminated unexpectedly'))
      .mockResolvedValueOnce(null);

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'Explain encoder-decoder attention.');
    await user.click(screen.getByRole('button', { name: /send|ask|submit/i }));

    const retryBtn = await screen.findByRole('button', { name: /retry/i });
    expect(api.streamMessage).toHaveBeenCalledTimes(1);
    const initialUuid = vi.mocked(api.streamMessage).mock.calls[0][1].client_message_id;

    await user.click(retryBtn);

    await waitFor(() => {
      expect(api.streamMessage).toHaveBeenCalledTimes(2);
    });

    const retryUuid = vi.mocked(api.streamMessage).mock.calls[1][1].client_message_id;
    expect(retryUuid).not.toBe(initialUuid);
    expect(retryUuid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
  });

  it('duplicate blocking: disables submission while a stream is in flight', async () => {
    const user = userEvent.setup();

    vi.mocked(api.streamMessage).mockImplementation(async () => {
      const { promise } = Promise.withResolvers<null>();
      return promise;
    });

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    await user.type(textarea, 'What are the main results?');
    const submitBtn = screen.getByRole('button', { name: /send|ask|submit/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.streamMessage).toHaveBeenCalledTimes(1);
    });

    expect(submitBtn).toBeDisabled();
    fireEvent.click(submitBtn);
    expect(api.streamMessage).toHaveBeenCalledTimes(1);
  });

  it('stale conversation events: ignores events from older in-flight stream when conversation changes', async () => {
    let staleStreamHandler: ((event: ReaderStreamEvent) => void) | null = null;
    vi.mocked(api.streamMessage).mockImplementation(
      async (_convId, _sub, onEvent) => {
        staleStreamHandler = onEvent;
        const { promise } = Promise.withResolvers<null>();
        return promise;
      }
    );

    const { rerender } = render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const textarea = await screen.findByRole('textbox', { name: /ask a question|discussion question|question/i });
    fireEvent.change(textarea, { target: { value: 'Old conversation question' } });
    fireEvent.click(screen.getByRole('button', { name: /send|ask|submit/i }));

    await waitFor(() => {
      expect(staleStreamHandler).not.toBeNull();
    });

    // Switch paper/document version
    window.history.replaceState(null, '', '/library/paper-9999-9999-9999-999999999999');
    rerender(
      <Discussion
        paperId="paper-9999-9999-9999-999999999999"
        title="BERT: Pre-training of Deep Bidirectional Transformers"
        documentVersion="ver-9999-9999-9999-999999999999"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    await act(async () => {
      staleStreamHandler!({
        event: 'answer.delta',
        data: {
          run_id: 'stale-run',
          message_id: 'stale-msg',
          sequence: 1,
          text: 'Stale text from old paper.',
          request_id: 'stale-req',
        },
      });
    });

    expect(screen.queryByText('Stale text from old paper.')).not.toBeInTheDocument();
  });

  it('401 private clear: on 401 response clears private discussion state and invokes onUnauthorized', async () => {
    const unauthorizedError = new api.ApiError(401, 'UNAUTHORIZED', 'Session expired.');
    vi.mocked(api.listConversations).mockRejectedValueOnce(unauthorizedError);

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    await waitFor(() => {
      expect(mockOnUnauthorized).toHaveBeenCalledTimes(1);
    });

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('known-title-derived suggestion: derives prompt suggestion from actual paper title on empty discussion', async () => {
    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    const suggestionBtn = await screen.findByRole('button', {
      name: /What are the key contributions of Attention Is All You Need\?/i,
    });
    expect(suggestionBtn).toBeInTheDocument();

    fireEvent.click(suggestionBtn);

    const textarea = screen.getByRole('textbox', { name: /ask a question|discussion question|question/i });
    expect(textarea).toHaveValue('What are the key contributions of Attention Is All You Need?');
  });

  it('citation button aria-controls evidence-card and expanded from activeCitationId', async () => {
    const existingConv: Conversation = {
      id: 'conv-cite-1',
      paper_id: 'paper-1111-1111-1111-111111111111',
      document_version: 'ver-2222-2222-2222-222222222222',
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-01T10:05:00Z',
      last_message: null,
    };

    const messagesWithCitations: Message[] = [
      {
        id: 'msg-assist-cite',
        sequence: 1,
        role: 'assistant',
        text: 'The model relies entirely on self-attention mechanisms.',
        state: 'completed',
        error_code: null,
        request_id: 'req-cite',
        created_at: '2026-10-01T10:02:00Z',
        updated_at: '2026-10-01T10:02:00Z',
        citations: [mockCitation1],
      },
    ];

    vi.mocked(api.listConversations).mockResolvedValueOnce({
      conversations: [existingConv],
      next_before: null,
      request_id: 'req-c',
    });
    vi.mocked(api.listMessages).mockResolvedValueOnce({
      messages: messagesWithCitations,
      next_after: null,
      request_id: 'req-m',
    });

    const { rerender } = render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
        activeCitationId={null}
      />
    );

    const citationBtn = await screen.findByRole('button', { name: /citation 1|citation/i });
    expect(citationBtn).toHaveAttribute('aria-controls', 'evidence-card');
    expect(citationBtn).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(citationBtn);
    expect(mockOnCitation).toHaveBeenCalledWith(mockCitation1, citationBtn);

    rerender(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
        activeCitationId={mockCitation1.citation_id}
      />
    );

    expect(citationBtn).toHaveAttribute('aria-expanded', 'true');
  });

  it('plain text safe React: renders claims text safely without HTML injection or unescaped HTML', async () => {
    const rawXssText = '<img src=x onerror=alert(1)> Some plain text';
    const existingConv: Conversation = {
      id: 'conv-xss-1',
      paper_id: 'paper-1111-1111-1111-111111111111',
      document_version: 'ver-2222-2222-2222-222222222222',
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-01T10:05:00Z',
      last_message: null,
    };

    vi.mocked(api.listConversations).mockResolvedValueOnce({
      conversations: [existingConv],
      next_before: null,
      request_id: 'req-xss-c',
    });
    vi.mocked(api.listMessages).mockResolvedValueOnce({
      messages: [
        {
          id: 'msg-xss',
          sequence: 1,
          role: 'assistant',
          text: rawXssText,
          state: 'completed',
          error_code: null,
          request_id: 'req-xss-m',
          created_at: '2026-10-01T10:02:00Z',
          updated_at: '2026-10-01T10:02:00Z',
          citations: [],
        },
      ],
      next_after: null,
      request_id: 'req-xss-l',
    });

    render(
      <Discussion
        paperId="paper-1111-1111-1111-111111111111"
        title="Attention Is All You Need"
        documentVersion="ver-2222-2222-2222-222222222222"
        onCitation={mockOnCitation}
        onUnauthorized={mockOnUnauthorized}
      />
    );

    expect(await screen.findByText(rawXssText)).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });
  it('never displays or submits a conversation pinned to a different open version', async () => {
    vi.mocked(api.listConversations).mockResolvedValueOnce({
      conversations: [{ id:'older-conversation',paper_id:'paper-ready',document_version:'older-version',
        created_at:'2026-10-01T10:00:00Z',updated_at:'2026-10-01T10:00:00Z',last_message:null }],
      next_before:null,request_id:'list-request',
    });
    vi.mocked(api.listMessages).mockResolvedValueOnce({
      messages:[{id:'old-message',sequence:1,role:'assistant',text:'Evidence from a different immutable version.',
        state:'completed',error_code:null,request_id:'old-request',created_at:'2026-10-01T10:00:00Z',
        updated_at:'2026-10-01T10:00:00Z',citations:[]}],next_after:null,request_id:'messages-request',
    });
    render(<Discussion paperId="paper-ready" title="Current paper" documentVersion="current-version"
      onCitation={mockOnCitation} onUnauthorized={mockOnUnauthorized} />);
    await waitFor(() => expect(api.listConversations).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByText('Evidence from a different immutable version.')).not.toBeInTheDocument();
    expect(api.listMessages).not.toHaveBeenCalled();
  });

  it('explicit retry preserves the failed draft instead of rewriting its history as a new run', async () => {
    const user = userEvent.setup();
    vi.mocked(api.streamMessage).mockImplementationOnce(async (_id,_submission,onEvent) => {
      onEvent({event:'answer.delta',data:{run_id:'run-old',message_id:'message-old',request_id:'request-old',
        sequence:1,text:'Earlier provisional text.'}});
      throw new api.ApiError(500,'READER_INTERRUPTED','Interrupted.');
    }).mockImplementationOnce(async (_id,_submission,onEvent) => {
      onEvent({event:'answer.delta',data:{run_id:'run-new',message_id:'message-new',request_id:'request-new',
        sequence:1,text:'New independent answer.'}});
      onEvent({event:'answer.completed',data:{run_id:'run-new',message_id:'message-new',request_id:'request-new',
        state:'completed',citations:[]}});
      return null;
    });
    render(<Discussion paperId="paper-1111-1111-1111-111111111111" title="Current paper"
      documentVersion="ver-2222-2222-2222-222222222222" onCitation={mockOnCitation} onUnauthorized={mockOnUnauthorized} />);
    await user.type(await screen.findByRole('textbox',{name:/question/i}),'Explain this result.');
    await user.click(screen.getByRole('button',{name:/^ask$/i}));
    await user.click(await screen.findByRole('button',{name:/retry/i}));
    expect(await screen.findByText('New independent answer.')).toBeInTheDocument();
    expect(screen.getByText('Earlier provisional text.')).toBeInTheDocument();
  });
});
