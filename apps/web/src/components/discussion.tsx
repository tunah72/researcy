'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  listConversations,
  createConversation,
  listMessages,
  streamMessage,
  ApiError,
  userErrorMessage,
  generateIdempotencyKey,
} from '@/lib/api';
import type {
  Conversation,
  Message,
  ResolvedCitation,
  ReaderStreamEvent,
} from '@/lib/api';
import './discussion.css';

export interface DiscussionProps {
  paperId: string;
  title: string | null;
  documentVersion: string;
  onCitation: (citation: ResolvedCitation, trigger: HTMLButtonElement) => void;
  onUnauthorized: () => void;
  activeCitationId?: string | null;
  evidence?: React.ReactNode;
  canCreateConversation?: boolean;
}

interface RetryState {
  question: string;
}

export function Discussion({
  paperId,
  title,
  documentVersion,
  onCitation,
  onUnauthorized,
  activeCitationId,
  evidence,
  canCreateConversation = true,
}: DiscussionProps): React.ReactElement {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [nextAfter, setNextAfter] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'streaming' | 'error'>('idle');
  const [errorNotice, setErrorNotice] = useState<string | null>(null);
  const [retryPayload, setRetryPayload] = useState<RetryState | null>(null);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);

  const activeConvIdRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamAbortControllerRef = useRef<AbortController | null>(null);

  const submitting = useRef(false);
  const handleUnauthorized = useCallback(() => {
    setIsUnauthorized(true);
    setMessages([]);
    setConversation(null);
    activeConvIdRef.current = null;
    onUnauthorized();
    abortControllerRef.current?.abort();
    streamAbortControllerRef.current?.abort();
  }, [onUnauthorized]);

  // Load conversation and messages on mount or paper/documentVersion change
  useEffect(() => {
    setIsUnauthorized(false);
    setErrorNotice(null);
    setRetryPayload(null);
    setMessages([]);
    setConversation(null);
    activeConvIdRef.current = null;
    setNextAfter(null);
    setInput('');
    setStatus('loading');
    submitting.current = false;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (streamAbortControllerRef.current) {
      streamAbortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    async function loadData() {
      try {
        const url = new URL(window.location.href);
        const requested = url.searchParams.get('conversation');
        let before: string | null = null;
        let matchingConv: Conversation | undefined;
        do {
          const convList = await listConversations(paperId, before, controller.signal);
          if (controller.signal.aborted) return;
          matchingConv = convList.conversations.find(c => c.document_version === documentVersion &&
            (!requested || c.id === requested));
          before = convList.next_before;
        } while (!matchingConv && before);
        if (requested && !matchingConv) {
          throw new ApiError(404, 'RESOURCE_NOT_FOUND', 'This discussion is unavailable for the open document.');
        }
        if (matchingConv) {
          let msgList = await listMessages(matchingConv.id, null, controller.signal);
          if (controller.signal.aborted) return;
          const loaded = [...msgList.messages];
          const selectedCitation = url.searchParams.get('citation');
          while (selectedCitation && msgList.next_after &&
              !loaded.some(message => message.citations?.some(citation => citation.citation_id === selectedCitation))) {
            msgList = await listMessages(matchingConv.id, msgList.next_after, controller.signal);
            if (controller.signal.aborted) return;
            loaded.push(...msgList.messages);
          }
          setConversation(matchingConv);
          activeConvIdRef.current = matchingConv.id;
          setMessages(loaded);
          setNextAfter(msgList.next_after);
          if (!requested) {
            url.searchParams.set('conversation', matchingConv.id);
            window.history.replaceState(null, '', url);
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          handleUnauthorized();
        } else {
          setErrorNotice(userErrorMessage(err, 'Could not load discussion history.'));
          setStatus('error');
        }
      } finally {
        if (!controller.signal.aborted) setStatus(current => current === 'error' ? current : 'idle');
      }
    }

    loadData();

    return () => {
      controller.abort();
      if (streamAbortControllerRef.current) {
        streamAbortControllerRef.current.abort();
      }
    };
  }, [paperId, documentVersion, handleUnauthorized, historyRevision]);

  useEffect(() => {
    const restore = () => setHistoryRevision(value => value + 1);
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);

  const hasRunningMessage = messages.some(message => message.role === 'assistant' && message.state === 'running');
  const composerBlocked = status === 'loading' || status === 'streaming' || hasRunningMessage ||
    (!conversation && (status === 'error' || !canCreateConversation));

  const handleLoadMore = async () => {
    if (!conversation || !nextAfter || status === 'loading' || submitting.current) return;
    const target = conversation.id;
    const controller = new AbortController();
    abortControllerRef.current?.abort();
    abortControllerRef.current = controller;
    setStatus('loading');
    try {
      const res = await listMessages(target, nextAfter, controller.signal);
      if (controller.signal.aborted || activeConvIdRef.current !== target) return;
      setMessages((prev) => [...prev, ...res.messages]);
      setNextAfter(res.next_after);
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        handleUnauthorized();
      } else {
        setErrorNotice(userErrorMessage(err, 'Could not load more messages.'));
      }
    } finally {
      if (!controller.signal.aborted) setStatus('idle');
    }
  };

  const executeSubmission = async (questionText: string) => {
    if (submitting.current || composerBlocked || !questionText.trim()) return;
    submitting.current = true;
    setErrorNotice(null);
    setStatus('streaming');

    if (streamAbortControllerRef.current) {
      streamAbortControllerRef.current.abort();
    }
    const streamController = new AbortController();
    streamAbortControllerRef.current = streamController;

    let targetConvId = activeConvIdRef.current;

    try {
      if (!targetConvId) {
        const convRes = await createConversation(paperId, streamController.signal);
        if (streamController.signal.aborted) return;
        if (convRes.conversation.document_version !== documentVersion) {
          throw new ApiError(409, 'PAPER_NOT_READY', 'A discussion requires the currently prepared document version.');
        }
        targetConvId = convRes.conversation.id;
        setConversation(convRes.conversation);
        const url = new URL(window.location.href);
        url.searchParams.set('conversation', targetConvId);
        window.history.replaceState(null, '', url);
        activeConvIdRef.current = targetConvId;
      }
    } catch (err) {
      if (streamController.signal.aborted) return;
      submitting.current = false;
      setStatus('error');
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        handleUnauthorized();
      } else {
        setErrorNotice(userErrorMessage(err, 'Could not start a new discussion.'));
      }
      return;
    }

    const clientMessageId = generateIdempotencyKey();

    const userMsgId = `user-${clientMessageId}`;
    const assistMsgId = `assist-${clientMessageId}`;

      setMessages((prev) => [
        ...prev,
        {
          id: userMsgId,
          sequence: prev.length + 1,
          role: 'user',
          text: questionText,
          state: 'completed',
          error_code: null,
          request_id: 'pending',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          citations: [],
        },
        {
          id: assistMsgId,
          sequence: prev.length + 2,
          role: 'assistant',
          text: '',
          state: 'running',
          error_code: null,
          request_id: 'pending',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          citations: [],
        },
      ]);
      setInput('');

    try {
      const replay = await streamMessage(
        targetConvId,
        {
          client_message_id: clientMessageId,
          question: questionText,
        },
        (event: ReaderStreamEvent) => {
          if (streamController.signal.aborted || streamAbortControllerRef.current !== streamController || activeConvIdRef.current !== targetConvId) return;

          if (event.event === 'answer.delta') {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...last, id:event.data.message_id, request_id:event.data.request_id,
                    text: last.text + event.data.text, state: 'running' },
                ];
              }
              return prev;
            });
          } else if (event.event === 'answer.completed') {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  {
                    ...last,
                    id:event.data.message_id, request_id:event.data.request_id,
                    state: event.data.state,
                    citations: event.data.citations ?? [],
                  },
                ];
              }
              return prev;
            });
            setStatus('idle');
            setRetryPayload(null);
          } else if (event.event === 'answer.failed') {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...last, id:event.data.message_id, request_id:event.data.request_id,
                    state: event.data.code === 'READER_INTERRUPTED' ? 'interrupted' : 'failed', error_code: event.data.code },
                ];
              }
              return prev;
            });
            setStatus('error');
            setErrorNotice(userErrorMessage(new ApiError(500,event.data.code,''),
              'The answer could not be completed. Please submit a new question to retry.'));
            setRetryPayload({ question: questionText });
          }
        },
        streamController.signal
      );
      if (streamController.signal.aborted) return;
      if (replay) {
        const restored = await listMessages(targetConvId, null, streamController.signal);
        if (streamController.signal.aborted) return;
        setMessages(restored.messages);
        setNextAfter(restored.next_after);
        setStatus(replay.state === 'running' ? 'streaming' : 'idle');
      }
    } catch (err) {
      if (streamController.signal.aborted || activeConvIdRef.current !== targetConvId) return;

      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        handleUnauthorized();
        return;
      }

      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && last.state === 'running') {
          return [
            ...prev.slice(0, -1),
            { ...last, state: err instanceof ApiError && err.code === 'READER_INTERRUPTED' ? 'interrupted' : 'failed',
              error_code: err instanceof ApiError ? err.code : 'READER_INTERRUPTED' },
          ];
        }
        return prev;
      });

      setStatus('error');
      setErrorNotice(
        userErrorMessage(err, 'The response was interrupted or disconnected. Please try again.')
      );
      setRetryPayload({ question: questionText });
    } finally {
      if (streamAbortControllerRef.current === streamController) submitting.current = false;
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || status === 'streaming') return;
    void executeSubmission(input);
  };

  const handleRetry = () => {
    if (!retryPayload || status === 'streaming') return;
    void executeSubmission(retryPayload.question);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && status !== 'streaming') {
        void executeSubmission(input);
      }
    }
  };

  if (isUnauthorized) {
    return (
      <div className="discussion-container" role="region" aria-label="Discussion">
        <div className="discussion-scroll">
          <p className="discussion-intro">Session expired. Please sign in again.</p>
        </div>
      </div>
    );
  }

  const suggestionPrompt = title && title.trim()
    ? `What are the key contributions of ${title.trim()}?`
    : 'What are the key contributions of this paper?';

  return (
    <div className="discussion-container" role="region" aria-label="Discussion">
      <div className="reader-discussion-heading">
        <span className="reader-eyebrow">Read with evidence</span><h2>Discussion</h2>
        <button type="button" className="btn btn-secondary" disabled={status === 'streaming' || status === 'loading'}
          onClick={() => setHistoryRevision(value => value + 1)}>Reload history</button>
      </div>
      <div className="discussion-scroll">
        <p className="discussion-intro">
          The original is open on the left. Discussion will stay scoped to this paper and its immutable document version.
        </p>

        {nextAfter && (
          <div className="discussion-pagination">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleLoadMore}
              disabled={status === 'loading'}
            >
              Load more messages
            </button>
          </div>
        )}

        {messages.length === 0 && (
          <div className="discussion-suggestion">
            <div className="discussion-suggestion-prompt">Suggested question</div>
            <button
              type="button"
              className="discussion-suggestion-btn"
              onClick={() => setInput(suggestionPrompt)}
            >
              {suggestionPrompt}
            </button>
          </div>
        )}

        <div className="discussion-messages" role="log" aria-label="Conversation history" aria-live="off">
          {messages.map((msg, index) => (
            <div
              key={msg.id || index}
              className={`discussion-message discussion-message-${msg.role}`}
              data-state={msg.state}
            >
              <div className="discussion-message-header">
                <span className="discussion-message-role">
                  {msg.role === 'user' ? 'You' : 'Researcy'}
                </span>
                {msg.state === 'running' && (
                  <span className="discussion-badge discussion-badge-running">Drafting...</span>
                )}
                {msg.state === 'refused' && (
                  <span className="discussion-badge discussion-badge-refusal">Refusal</span>
                )}
                {(msg.state === 'failed' || msg.state === 'interrupted') && (
                  <span className="discussion-badge discussion-badge-failed">{msg.state === 'failed' ? 'Failed' : 'Interrupted'}</span>
                )}
              </div>

              <div className="discussion-message-body">
                {msg.text.split('\n\n').map((paragraph, pIdx) => (
                  <p key={pIdx}>{paragraph}</p>
                ))}
              </div>

              {msg.state === 'completed' && msg.citations && msg.citations.length > 0 && (
                <div className="discussion-citations">
                  <span className="discussion-citations-label">Sources:</span>
                  {msg.citations.map((cit, cIdx) => (
                    <button
                      key={cit.citation_id || cIdx}
                      id={`citation-${cit.citation_id}`}
                      type="button"
                      className="btn btn-citation"
                      aria-controls="evidence-card"
                      aria-expanded={activeCitationId === cit.citation_id ? 'true' : 'false'}
                      onClick={(e) => onCitation(cit, e.currentTarget)}
                    >
                      Citation {cIdx + 1}
                    </button>
                  ))}
                </div>
              )}
              {msg.citations?.some(citation => citation.citation_id === activeCitationId) && evidence}
            </div>
          ))}
        </div>
        {evidence && !messages.some(message => message.citations?.some(citation => citation.citation_id === activeCitationId)) && evidence}

        {errorNotice && (
          <div className="discussion-error-banner" role="alert">
            <span>{errorNotice}</span>
            {retryPayload && (
              <div className="discussion-retry-action">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleRetry}
                  disabled={status === 'streaming'}
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <form className="discussion-composer" onSubmit={handleSubmit}>
        <label htmlFor="discussion-question-input">Ask a question about this paper</label>
        <span role="status" aria-live="polite">
          {status === 'streaming' ? 'Preparing an evidence-linked answer.' : hasRunningMessage ?
            'A saved run is still pending. Reload history to check its persisted state.' :
            !conversation && !canCreateConversation ? 'Discussion is unavailable for this historical document version.' : ''}
        </span>
        <textarea
          id="discussion-question-input"
          name="question"
          className="discussion-textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about this paper..."
          aria-label="Ask a question about this paper"
          rows={3}
          disabled={composerBlocked}
        />
        <div className="discussion-composer-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={composerBlocked || !input.trim()}
          >
            {status === 'streaming' ? 'Thinking...' : 'Ask'}
          </button>
        </div>
      </form>
    </div>
  );
}
