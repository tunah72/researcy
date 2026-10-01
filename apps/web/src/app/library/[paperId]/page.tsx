'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  fetchPaperDetail,
  retryJob,
  ApiError,
  formatScreeningWarning,
  userErrorMessage,
} from '@/lib/api';
import { PaperPreparation } from '@/components/paper-preparation';
import type { PaperDetailResponse } from '@/lib/api';
import { ReaderWorkspace } from '@/components/reader-workspace';

export default function PaperDetailPage() {
  const params = useParams();
  const paperId = typeof params?.paperId === 'string' ? params.paperId : '';

  const [paper, setPaper] = useState<PaperDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ message: string; isNotFound?: boolean } | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  // Retry state
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retryDeadline, setRetryDeadline] = useState(0);

  const requestSeqRef = useRef(0);
  const inFlightRef = useRef(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const backoffRef = useRef(false);
  const isMountedRef = useRef(true);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [conflictPending, setConflictPending] = useState(false);
  const conflictRefreshRef = useRef(false);
  const setConflictState = useCallback((pending: boolean) => {
    conflictRefreshRef.current = pending;
    setConflictPending(pending);
  }, []);
  const scheduleNextPollRef = useRef<(delayMs: number) => void>(() => {});
  const retryFocusRef = useRef<Element | null>(null);
  const restoreRetryFocusRef = useRef(false);
  useEffect(() => {
    if (!restoreRetryFocusRef.current) return;
    const previous = retryFocusRef.current;
    if (previous && !previous.isConnected && document.activeElement === document.body) {
      titleRef.current?.focus();
    }
    restoreRetryFocusRef.current = false;
  }, [paper]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      requestSeqRef.current++;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      setConflictState(false);
      restoreRetryFocusRef.current = false;
      retryFocusRef.current = null;
    };
  }, [setConflictState]);

  const isProcessing = Boolean(
    paper &&
    paper.preparation &&
    (paper.preparation.state === 'waiting' ||
     paper.preparation.state === 'preparing' ||
     paper.preparation.state === 'delayed')
  );
  const isProcessingRef = useRef(isProcessing);
  useEffect(() => {
    isProcessingRef.current = isProcessing;
  }, [isProcessing]);

  const refreshDetail = useCallback(async () => {
    if (!paperId) return;
    if (inFlightRef.current) {
      if (conflictRefreshRef.current && isMountedRef.current) {
        scheduleNextPollRef.current(backoffRef.current ? 30000 : 5000);
      }
      return;
    }
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;

    inFlightRef.current = true;
    const seq = ++requestSeqRef.current;

    try {
      const data = await fetchPaperDetail(paperId);
      if (seq !== requestSeqRef.current || !isMountedRef.current) return;
      setPaper(data);
      setRefreshError(null);
      backoffRef.current = false;
      if (conflictRefreshRef.current) {
        setConflictState(false);
        restoreRetryFocusRef.current = true;
      }
    } catch (err: unknown) {
      if (seq !== requestSeqRef.current || !isMountedRef.current) return;
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setPaper(null);
          setError(null);
          setConflictState(false);
          restoreRetryFocusRef.current = false;
          retryFocusRef.current = null;
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          window.location.href = '/sign-in?expired=1';
          return;
        }
        if (err.status === 404) {
          setPaper(null);
          setRefreshError(null);
          setConflictState(false);
          restoreRetryFocusRef.current = false;
          retryFocusRef.current = null;
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setError({
            message: 'This document could not be found in your private library.',
            isNotFound: true,
          });
          return;
        }
      }
      backoffRef.current = true;
      setRefreshError('Could not refresh status. Will check again.');
    } finally {
      inFlightRef.current = false;
      if (conflictRefreshRef.current && isMountedRef.current && seq !== requestSeqRef.current) {
        scheduleNextPollRef.current(backoffRef.current ? 30000 : 5000);
      }
    }
  }, [paperId, setConflictState]);

  const scheduleNextPoll = useCallback((delayMs: number) => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if ((!isProcessingRef.current && !conflictRefreshRef.current) || !isMountedRef.current) return;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;

    pollTimerRef.current = setTimeout(async () => {
      pollTimerRef.current = null;
      await refreshDetail();
      if ((isProcessingRef.current || conflictRefreshRef.current) && isMountedRef.current) {
        scheduleNextPoll(backoffRef.current ? 30000 : 5000);
      }
    }, delayMs);
  }, [refreshDetail]);

  useEffect(() => {
    scheduleNextPollRef.current = scheduleNextPoll;
  }, [scheduleNextPoll]);

  useEffect(() => {
    if (isProcessing || conflictPending) {
      scheduleNextPoll(backoffRef.current ? 30000 : 5000);
    } else {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    }
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [isProcessing, conflictPending, scheduleNextPoll]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (typeof document === 'undefined') return;
      if (document.visibilityState === 'hidden') {
        if (pollTimerRef.current) {
          clearTimeout(pollTimerRef.current);
          pollTimerRef.current = null;
        }
      } else if (document.visibilityState === 'visible') {
        if (isProcessingRef.current || conflictRefreshRef.current) {
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          (async () => {
            await refreshDetail();
            if ((isProcessingRef.current || conflictRefreshRef.current) && isMountedRef.current) {
              scheduleNextPoll(backoffRef.current ? 30000 : 5000);
            }
          })();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [refreshDetail, scheduleNextPoll]);

  const loadDetail = useCallback(async () => {
    if (!paperId) return;
    setIsLoading(true);
    setError(null);
    setRefreshError(null);
    setIsRetrying(false);
    setRetryError(null);
    setRetryDeadline(0);
    setConflictState(false);
    restoreRetryFocusRef.current = false;
    retryFocusRef.current = null;
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    const seq = ++requestSeqRef.current;

    try {
      const data = await fetchPaperDetail(paperId);
      if (seq !== requestSeqRef.current || !isMountedRef.current) return;
      setPaper(data);
      backoffRef.current = false;
    } catch (err: unknown) {
      if (seq !== requestSeqRef.current || !isMountedRef.current) return;
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setPaper(null);
          setConflictState(false);
          restoreRetryFocusRef.current = false;
          retryFocusRef.current = null;
          window.location.href = '/sign-in?expired=1';
          return;
        }
        if (err.status === 404) {
          setPaper(null);
          setConflictState(false);
          restoreRetryFocusRef.current = false;
          retryFocusRef.current = null;
          setError({
            message: 'This document could not be found in your private library.',
            isNotFound: true,
          });
          return;
        }
      }
      const message = userErrorMessage(err, 'Failed to load paper details. Please check your connection and retry.');
      setError({ message });
    } finally {
      if (seq === requestSeqRef.current && isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [paperId, setConflictState]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleRetry = useCallback(async () => {
    if (!paper || !paper.job_id || isRetrying || conflictRefreshRef.current) return;
    retryFocusRef.current = document.activeElement;
    setIsRetrying(true);
    setRetryError(null);
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    const seq = ++requestSeqRef.current;

    try {
      const job = await retryJob(paper.job_id, paper.retry_revision);
      if (seq !== requestSeqRef.current || !isMountedRef.current) return;
      setIsRetrying(false);
      setRetryError(null);
      setPaper(prev => {
        if (!prev || prev.job_id !== job.job_id) return prev;
        return {
          ...prev,
          stage: job.stage,
          retry_revision: job.retry_revision,
          preparation: job.preparation,
        };
      });
      restoreRetryFocusRef.current = true;
    } catch (err: unknown) {
      if (seq !== requestSeqRef.current || !isMountedRef.current) return;
      setIsRetrying(false);
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setPaper(null);
          setError(null);
          setConflictState(false);
          restoreRetryFocusRef.current = false;
          retryFocusRef.current = null;
          window.location.href = '/sign-in?expired=1';
          return;
        }
        if (err.status === 404) {
          setPaper(null);
          setRefreshError(null);
          setConflictState(false);
          restoreRetryFocusRef.current = false;
          retryFocusRef.current = null;
          setError({
            message: 'This document could not be found in your private library.',
            isNotFound: true,
          });
          return;
        }
        if (err.status === 409) {
          setRetryError(null);
          setRetryDeadline(0);
          setConflictState(true);
          await refreshDetail();
          if (conflictRefreshRef.current && isMountedRef.current) {
            scheduleNextPoll(backoffRef.current ? 30000 : 5000);
          }
          return;
        }
        if (err.status === 429) {
          const seconds = err.retryAfter ?? 10;
          setRetryDeadline(Date.now() + Math.max(1, seconds) * 1000);
          setRetryError(userErrorMessage(err, 'Please wait a little before trying again.'));
          return;
        }
      }
      setRetryError(userErrorMessage(err, 'Failed to retry preparation. Please try again later.'));
    }
  }, [paper, isRetrying, refreshDetail, scheduleNextPoll, setConflictState]);

  if (!isLoading && !error && paper?.reader && paper.stage === 'ready') {
    return <ReaderWorkspace paper={paper} source={paper.reader} />;
  }

  const authorText =
    paper?.authors && paper.authors.length > 0
      ? paper.authors.join(', ')
      : 'Unknown author';
  const yearText = paper?.year ? String(paper.year) : 'Year unknown';
  const sourceLabel =
    paper?.source === 'arxiv'
      ? 'arXiv'
      : paper?.source === 'upload'
      ? 'Uploaded PDF'
      : paper?.source || 'Document';

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--color-canvas)' }}>
      <header
        style={{
          borderBottom: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          padding: '0.875rem 1.5rem',
        }}
      >
        <div
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem' }}>
            <Link href="/library" className="brand-heading brand-link">
              Researcy
            </Link>
            <span
              style={{
                fontSize: '0.8125rem',
                color: 'var(--color-ink-muted)',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Document
            </span>
          </div>

          <div>
            <Link
              href="/library"
              className="btn btn-secondary"
              style={{
                padding: '0.5rem 0.875rem',
                fontSize: '0.875rem',
                textDecoration: 'none',
                minHeight: '44px',
                display: 'inline-flex',
                alignItems: 'center',
              }}
            >
              &larr; Back to Library
            </Link>
          </div>
        </div>
      </header>

      <main
        id="main-content"
        style={{
          flex: 1,
          maxWidth: '840px',
          margin: '0 auto',
          padding: '3rem 1.5rem 5rem 1.5rem',
          width: '100%',
        }}
      >
        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="editorial-card"
            style={{
              padding: '3rem 1.5rem',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--color-ink-muted)', fontSize: '1.125rem' }}>
              Loading document metadata...
            </p>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="editorial-card"
            style={{
              padding: '2.5rem 1.5rem',
              textAlign: 'center',
              borderColor: 'var(--color-error-border)',
            }}
          >
            <h2 style={{ fontSize: '1.5rem', marginBottom: '0.75rem', color: 'var(--color-error-text)', fontWeight: 600 }}>
              {error.isNotFound ? 'Document Not Found' : 'Error Loading Document'}
            </h2>
            <p style={{ color: 'var(--color-ink)', marginBottom: '1.5rem', maxWidth: '480px', margin: '0 auto 1.5rem auto' }}>
              {error.message}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              {!error.isNotFound && (
                <button
                  type="button"
                  onClick={loadDetail}
                  className="btn btn-primary"
                  style={{ minHeight: '44px' }}
                >
                  Retry
                </button>
              )}
              <Link
                href="/library"
                className="btn btn-secondary"
                style={{
                  minHeight: '44px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  textDecoration: 'none',
                }}
              >
                Return to Library
              </Link>
            </div>
          </div>
        )}

        {!isLoading && !error && paper && (
          <article
            className="editorial-card"
            style={{
              padding: '2.5rem',
            }}
          >
            {/* Bibliographic Tags: Source & optional edition */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.625rem',
                marginBottom: '1rem',
                flexWrap: 'wrap',
              }}
            >
              <span className="badge-source">
                {sourceLabel}
              </span>
              {paper.source_version && (
                <span
                  style={{
                    fontSize: '0.8125rem',
                    color: 'var(--color-ink-muted)',
                    backgroundColor: 'var(--color-surface-subtle)',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  arXiv edition: <strong>{paper.source_version}</strong>
                </span>
              )}
            </div>

            <h1
              ref={titleRef}
              tabIndex={-1}
              style={{
                fontSize: '2rem',
                lineHeight: 1.25,
                marginBottom: '1rem',
                letterSpacing: '-0.02em',
                overflowWrap: 'break-word',
                wordBreak: 'break-word',
                outline: 'none',
              }}
            >
              {paper.title || 'Untitled Document'}
            </h1>

            <div
              style={{
                borderBottom: '1px solid var(--color-border)',
                paddingBottom: '1.25rem',
                marginBottom: '1.5rem',
                color: 'var(--color-ink-muted)',
                fontSize: '0.9375rem',
              }}
            >
              <p style={{ marginBottom: '0.375rem' }}>
                <strong style={{ color: 'var(--color-ink)' }}>Authors:</strong> {authorText}
              </p>
              <p>
                <strong style={{ color: 'var(--color-ink)' }}>Publication Year:</strong> {yearText}
              </p>
            </div>

            {/* Screening notice if present */}
            {paper.screening_warning && (
              <div
                role="note"
                className="notice-warning"
                style={{ marginBottom: '1.5rem' }}
              >
                <h2 style={{ fontSize: '0.9375rem', fontWeight: 700, marginBottom: '0.25rem', color: 'var(--color-ochre-text)' }}>
                  About this PDF
                </h2>
                <p style={{ fontSize: '0.875rem' }}>
                  {formatScreeningWarning(paper.screening_warning)}
                </p>
              </div>
            )}

            {/* Preparation status and honest reader note */}
            <div
              style={{
                padding: '1.25rem',
                backgroundColor: 'var(--color-surface-subtle)',
                border: '1px solid var(--color-border)',
                borderRadius: '6px',
                fontSize: '0.875rem',
                color: 'var(--color-ink-muted)',
                lineHeight: 1.6,
              }}
            >
              <p>
                Reading is not available yet.
              </p>
              {paper.preparation && (
                <PaperPreparation
                  preparation={paper.preparation}
                  isRetrying={isRetrying || conflictPending}
                  retryError={retryError}
                  retryDeadline={retryDeadline}
                  onRetry={paper.preparation.retryable ? handleRetry : undefined}
                />
              )}
              {refreshError && (
                <p role="status" style={{ marginTop: '0.5rem', color: 'var(--color-ink-muted)' }}>
                  {refreshError}
                </p>
              )}
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
