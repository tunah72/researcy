'use client';

import React, { useState, useEffect, useCallback, useId, useRef } from 'react';
import Link from 'next/link';
import {
  Paper,
  UserProfile,
  fetchCurrentUser,
  fetchPapers,
  retryJob,
  logoutUser,
  ApiError,
  userErrorMessage,
} from '@/lib/api';
import { LibraryList, ProcessingRetryState } from '@/components/library-list';
import { AddPaper } from '@/components/add-paper';
export default function LibraryPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ message: string } | null>(null);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearch, setActiveSearch] = useState('');

  const [showAddPaper, setShowAddPaper] = useState(false);
  const [isAddPaperBusy, setIsAddPaperBusy] = useState(false);

  // Logout state
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<{ message: string } | null>(null);

  // Per-job retry state
  const [retryStates, setRetryStates] = useState<Record<string, ProcessingRetryState>>({});

  const searchInputId = useId();
  const requestSeqRef = useRef(0);
  const addPaperBtnRef = useRef<HTMLButtonElement>(null);
  const wasAddPaperOpen = useRef(false);

  // Synchronization refs for stable callbacks and preventing stale closures
  const userRef = useRef<UserProfile | null>(null);
  userRef.current = user;

  const papersRef = useRef<Paper[]>(papers);
  papersRef.current = papers;

  const activeSearchRef = useRef('');
  activeSearchRef.current = activeSearch;

  const isLoggingOutRef = useRef(false);
  isLoggingOutRef.current = isLoggingOut;

  const isPollingRef = useRef(false);
  const conflictRefreshRef = useRef(false);
  const conflictedJobsRef = useRef<Set<string>>(new Set());
  const activeForegroundSeqRef = useRef<number | null>(null);
  const retryFocusTargetRef = useRef<{ element: Element | null; paperId: string } | null>(null);
  const restoreRetryFocusRef = useRef(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isBackoffRef = useRef(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    if (!restoreRetryFocusRef.current) return;
    const target = retryFocusTargetRef.current;
    if (
      target?.element &&
      !target.element.isConnected &&
      (document.activeElement === document.body || !document.activeElement)
    ) {
      document
        .querySelector<HTMLAnchorElement>(`a[href="/library/${encodeURIComponent(target.paperId)}"]`)
        ?.focus();
    }
    restoreRetryFocusRef.current = false;
  }, [papers]);
  function hasProcessing(list: Paper[]): boolean {
    return list.some((p) => {
      const state = p.preparation?.state;
      return state === 'waiting' || state === 'preparing' || state === 'delayed';
    });
  }

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);
  useEffect(() => {
    if (wasAddPaperOpen.current && !showAddPaper) {
      addPaperBtnRef.current?.focus();
    }
    wasAddPaperOpen.current = showAddPaper;
  }, [showAddPaper]);

  const handleUnauthorized = useCallback(() => {
    clearPollTimer();
    requestSeqRef.current++;
    activeForegroundSeqRef.current = null;
    setUser(null);
    userRef.current = null;
    setPapers([]);
    papersRef.current = [];
    setRetryStates({});
    conflictedJobsRef.current.clear();
    conflictRefreshRef.current = false;
    setRefreshNotice(null);
    window.location.href = '/sign-in?expired=1';
  }, [clearPollTimer]);

  const schedulePollRef = useRef<(delayMs: number) => void>(() => {});

  const executePoll = useCallback(async (force = false) => {
    if (!isMountedRef.current || isLoggingOutRef.current || !userRef.current) return;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    if (activeForegroundSeqRef.current !== null) {
      if (force) conflictRefreshRef.current = true;
      return;
    }
    if (isPollingRef.current) {
      if (force) conflictRefreshRef.current = true;
      return;
    }
    if (!force && !conflictRefreshRef.current && !hasProcessing(papersRef.current)) return;

    isPollingRef.current = true;
    const seq = ++requestSeqRef.current;
    const currentQuery = activeSearchRef.current;

    try {
      const data = await fetchPapers(currentQuery);
      if (!isMountedRef.current || seq !== requestSeqRef.current) return;

      const mergedPapers = data.papers.map((incoming) => {
        const current = papersRef.current.find((p) => p.job_id === incoming.job_id);
        if (current && current.retry_revision > incoming.retry_revision) {
          return current;
        }
        return incoming;
      });

      setPapers(mergedPapers);
      papersRef.current = mergedPapers;
      setRefreshNotice(null);
      isBackoffRef.current = false;

      if (conflictRefreshRef.current) {
        conflictRefreshRef.current = false;
        restoreRetryFocusRef.current = true;
      }

      if (conflictedJobsRef.current.size > 0) {
        const clearedJobs = new Set(conflictedJobsRef.current);
        conflictedJobsRef.current.clear();
        setRetryStates((prev) => {
          const next = { ...prev };
          for (const jId of clearedJobs) {
            if (next[jId]) {
              next[jId] = { ...next[jId], isRetrying: false };
            }
          }
          return next;
        });
      }

      if (
        hasProcessing(mergedPapers) &&
        typeof document !== 'undefined' &&
        document.visibilityState === 'visible'
      ) {
        schedulePollRef.current(5000);
      }
    } catch (err: unknown) {
      if (!isMountedRef.current || seq !== requestSeqRef.current) return;

      if (err instanceof ApiError && err.status === 401) {
        handleUnauthorized();
        return;
      }

      setRefreshNotice('Could not refresh status. Will check again shortly.');
      isBackoffRef.current = true;

      if (
        (hasProcessing(papersRef.current) || conflictRefreshRef.current) &&
        typeof document !== 'undefined' &&
        document.visibilityState === 'visible'
      ) {
        schedulePollRef.current(30000);
      }
    } finally {
      isPollingRef.current = false;
      if (
        isMountedRef.current &&
        userRef.current &&
        !isLoggingOutRef.current &&
        typeof document !== 'undefined' &&
        document.visibilityState === 'visible' &&
        !pollTimerRef.current &&
        (conflictRefreshRef.current || hasProcessing(papersRef.current))
      ) {
        schedulePollRef.current(isBackoffRef.current ? 30000 : conflictRefreshRef.current ? 0 : 5000);
      }
    }
  }, [handleUnauthorized]);

  const schedulePoll = useCallback(
    (delayMs: number) => {
      clearPollTimer();
      pollTimerRef.current = setTimeout(() => {
        pollTimerRef.current = null;
        executePoll();
      }, delayMs);
    },
    [clearPollTimer, executePoll]
  );

  schedulePollRef.current = schedulePoll;

  const loadLibraryData = useCallback(
    async (queryParam?: string) => {
      const seq = ++requestSeqRef.current;
      activeForegroundSeqRef.current = seq;
      setIsLoading(true);
      setError(null);
      setRefreshNotice(null);
      clearPollTimer();

      try {
        let profile = userRef.current;
        if (!profile) {
          profile = await fetchCurrentUser();
          if (!isMountedRef.current || seq !== requestSeqRef.current) return;
          setUser(profile);
          userRef.current = profile;
        }

        const data = await fetchPapers(queryParam);
        if (!isMountedRef.current || seq !== requestSeqRef.current) return;

        const mergedPapers = data.papers.map((incoming) => {
          const current = papersRef.current.find((p) => p.job_id === incoming.job_id);
          if (current && current.retry_revision > incoming.retry_revision) {
            return current;
          }
          return incoming;
        });

        setPapers(mergedPapers);
        papersRef.current = mergedPapers;

        if (conflictRefreshRef.current) {
          conflictRefreshRef.current = false;
          restoreRetryFocusRef.current = true;
        }

        if (conflictedJobsRef.current.size > 0) {
          const clearedJobs = new Set(conflictedJobsRef.current);
          conflictedJobsRef.current.clear();
          setRetryStates((prev) => {
            const next = { ...prev };
            for (const jId of clearedJobs) {
              if (next[jId]) {
                next[jId] = { ...next[jId], isRetrying: false };
              }
            }
            return next;
          });
        }

        if (
          hasProcessing(mergedPapers) &&
          typeof document !== 'undefined' &&
          document.visibilityState === 'visible'
        ) {
          schedulePoll(5000);
        }
      } catch (err: unknown) {
        if (!isMountedRef.current || seq !== requestSeqRef.current) return;
        if (err instanceof ApiError && err.status === 401) {
          handleUnauthorized();
          return;
        }
        const message = userErrorMessage(err, 'Failed to load your library. Please try again.');
        setError({ message });
      } finally {
        if (activeForegroundSeqRef.current === seq) {
          activeForegroundSeqRef.current = null;
        }
        if (isMountedRef.current && seq === requestSeqRef.current) {
          setIsLoading(false);
        }
      }
    },
    [clearPollTimer, handleUnauthorized, schedulePoll]
  );

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        clearPollTimer();
      } else if (document.visibilityState === 'visible') {
        if (
          (hasProcessing(papersRef.current) || conflictRefreshRef.current) &&
          userRef.current &&
          !isLoggingOutRef.current
        ) {
          clearPollTimer();
          executePoll(conflictRefreshRef.current);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [clearPollTimer, executePoll]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      clearPollTimer();
    };
  }, [clearPollTimer]);

  useEffect(() => {
    loadLibraryData();
  }, [loadLibraryData]);

  const handleProcessingRetry = useCallback(
    async (paper: Paper) => {
      if (!isMountedRef.current || isLoggingOutRef.current || !userRef.current) return;

      const jobId = paper.job_id;
      const revision = paper.retry_revision;
      const versionId = paper.active_version_id;
      const paperId = paper.paper_id;

      // Retry start invalidates poll seq and results stale
      requestSeqRef.current++;
      clearPollTimer();

      conflictedJobsRef.current.delete(jobId);
      setRetryStates((prev) => ({
        ...prev,
        [jobId]: { isRetrying: true, retryError: null },
      }));

      retryFocusTargetRef.current = {
        element: typeof document !== 'undefined' ? document.activeElement : null,
        paperId,
      };

      try {
        const jobResponse = await retryJob(jobId, revision);

        if (!isMountedRef.current || !userRef.current) return;
        if (isLoggingOutRef.current) {
          conflictedJobsRef.current.add(jobId);
          conflictRefreshRef.current = true;
          return;
        }

        let didAdvance = false;
        setPapers((prevPapers) => {
          const updated = prevPapers.map((p) => {
            if (
              p.job_id === jobId &&
              p.active_version_id === versionId &&
              p.retry_revision < jobResponse.retry_revision
            ) {
              didAdvance = true;
              return {
                ...p,
                stage: jobResponse.stage,
                retry_revision: jobResponse.retry_revision,
                preparation: jobResponse.preparation,
              };
            }
            return p;
          });
          papersRef.current = updated;
          return updated;
        });

        if (didAdvance) {
          restoreRetryFocusRef.current = true;
        }

        setRetryStates((prev) => ({
          ...prev,
          [jobId]: {
            isRetrying: false,
            retryError: null,
            retryDeadline:
              jobResponse.preparation?.retry_after_seconds > 0
                ? Date.now() + jobResponse.preparation.retry_after_seconds * 1000
                : 0,
          },
        }));

        if (
          jobResponse.preparation &&
          ['waiting', 'preparing', 'delayed'].includes(jobResponse.preparation.state) &&
          typeof document !== 'undefined' &&
          document.visibilityState === 'visible' &&
          !pollTimerRef.current &&
          !isPollingRef.current
        ) {
          schedulePoll(5000);
        }
      } catch (err: unknown) {
        if (!isMountedRef.current || !userRef.current) return;
        if (err instanceof ApiError && err.status === 429) {
          const retryAfter = err.retryAfter;
          const deadline = retryAfter && retryAfter > 0 ? Date.now() + retryAfter * 1000 : 0;
          setRetryStates((prev) => ({
            ...prev,
            [jobId]: {
              isRetrying: false,
              retryError: userErrorMessage(err, 'Too many retry attempts. Please wait.'),
              retryDeadline: deadline,
            },
          }));
          return;
        }
        if (isLoggingOutRef.current) {
          conflictedJobsRef.current.add(jobId);
          conflictRefreshRef.current = true;
          return;
        }

        if (err instanceof ApiError && err.status === 401) {
          handleUnauthorized();
          return;
        }

        if (err instanceof ApiError && err.status === 409) {
          conflictRefreshRef.current = true;
          conflictedJobsRef.current.add(jobId);
          setRetryStates((prev) => ({
            ...prev,
            [jobId]: { isRetrying: true, retryError: null },
          }));
          if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
            executePoll(true);
          }
          return;
        }


        const message = userErrorMessage(err, 'Could not retry preparation. Please try again.');
        setRetryStates((prev) => ({
          ...prev,
          [jobId]: {
            isRetrying: false,
            retryError: message,
          },
        }));
      }
    },
    [clearPollTimer, executePoll, handleUnauthorized, schedulePoll]
  );

  async function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setActiveSearch(searchQuery);
    activeSearchRef.current = searchQuery;
    loadLibraryData(searchQuery);
  }

  function handleClearSearch() {
    setSearchQuery('');
    setActiveSearch('');
    activeSearchRef.current = '';
    loadLibraryData('');
  }

  async function handleLogout() {
    if (isLoggingOut || !user) return;
    setIsLoggingOut(true);
    isLoggingOutRef.current = true;
    setLogoutError(null);
    clearPollTimer();
    requestSeqRef.current++;

    try {
      await logoutUser();
      setUser(null);
      userRef.current = null;
      setPapers([]);
      papersRef.current = [];
      setRetryStates({});
      conflictedJobsRef.current.clear();
      conflictRefreshRef.current = false;
      window.location.href = '/sign-in';
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) {
        handleUnauthorized();
        return;
      }
      const message = userErrorMessage(err, 'You are still signed in. Please try again.');
      setLogoutError({ message });
      setIsLoggingOut(false);
      isLoggingOutRef.current = false;

      if (activeForegroundSeqRef.current !== null || isLoading) {
        loadLibraryData(activeSearchRef.current);
      } else if (conflictRefreshRef.current) {
        executePoll(true);
      } else if (hasProcessing(papersRef.current)) {
        schedulePoll(5000);
      }
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--color-canvas)' }}>
      {/* Slim, accessible header / workspace shell */}
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
              Library
            </span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              flexWrap: 'wrap',
            }}
          >
            {user && (
              <span
                style={{
                  fontSize: '0.875rem',
                  color: 'var(--color-ink-muted)',
                }}
              >
                {user.email || user.name || 'Signed In'}
              </span>
            )}
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut || !user}
              className="btn btn-secondary"
              style={{ padding: '0.5rem 0.875rem', fontSize: '0.875rem', minHeight: '44px' }}
            >
              {isLoggingOut ? 'Signing out...' : 'Sign Out'}
            </button>
          </div>
        </div>
      </header>

      {logoutError && (
        <div
          role="alert"
          className="notice-error"
          style={{
            maxWidth: '1200px',
            margin: '1rem auto 0 auto',
            width: 'calc(100% - 3rem)',
          }}
        >
          <strong>Sign out failed:</strong> {logoutError.message}
        </div>
      )}

      <main
        id="main-content"
        style={{
          flex: 1,
          maxWidth: '1200px',
          margin: '0 auto',
          padding: '2rem 1.5rem 4rem 1.5rem',
          width: '100%',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '1.75rem',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <div>
            <h1 style={{ fontSize: '2rem', marginBottom: '0.25rem', fontWeight: 600 }}>Library</h1>
            <p style={{ color: 'var(--color-ink-muted)', fontSize: '0.9375rem' }}>
              Your private collection of research papers and literature.
            </p>
          </div>

          {/* Always mounted sole toolbar Add Paper CTA with anchored popover */}
          <div className="add-paper-anchor">
            <button
              ref={addPaperBtnRef}
              type="button"
              aria-expanded={showAddPaper}
              aria-controls={showAddPaper ? 'add-paper-panel' : undefined}
              onClick={() => setShowAddPaper((prev) => !prev)}
              disabled={!user || showAddPaper || isAddPaperBusy || isLoggingOut}
              className="btn btn-primary"
              style={{ minHeight: '44px' }}
            >
              Add Paper
            </button>

            {showAddPaper && (
              <AddPaper
                onPaperAdded={() => {
                  loadLibraryData(activeSearch);
                }}
                onClose={() => setShowAddPaper(false)}
                onUnauthorized={handleUnauthorized}
                onBusyChange={setIsAddPaperBusy}
              />
            )}
          </div>
        </div>

        {/* Search bar */}
        <form
          role="search"
          onSubmit={handleSearchSubmit}
          style={{
            marginBottom: '1.75rem',
            display: 'flex',
            gap: '0.5rem',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: '1 1 300px', position: 'relative' }}>
            <label htmlFor={searchInputId} className="visually-hidden">
              Search papers
            </label>
            <input
              id={searchInputId}
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search papers by title or author..."
              className="form-input"
              aria-label="Search papers"
            />
          </div>
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={isLoading || isLoggingOut || !user}
            style={{ minHeight: '44px' }}
          >
            Search
          </button>
          {activeSearch && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="btn btn-secondary"
              disabled={isLoading || isLoggingOut}
              style={{ minHeight: '44px' }}
            >
              Clear
            </button>
          )}
        </form>

        {refreshNotice && (
          <div
            role="status"
            style={{
              marginBottom: '1rem',
              padding: '0.625rem 0.875rem',
              fontSize: '0.875rem',
              color: 'var(--color-ink-muted)',
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {refreshNotice}
          </div>
        )}

        {/* Papers List or Empty State (single error location via LibraryList) */}
        <LibraryList
          papers={papers}
          isLoading={isLoading}
          error={error}
          onRetry={() => loadLibraryData(activeSearch)}
          searchQuery={activeSearch}
          onClearSearch={handleClearSearch}
          onProcessingRetry={handleProcessingRetry}
          retryStates={retryStates}
          isLoggingOut={isLoggingOut}
        />
      </main>
    </div>
  );
}
