'use client';

import React, { useState, useEffect, useCallback, useId, useRef } from 'react';
import Link from 'next/link';
import {
  Paper,
  UserProfile,
  fetchCurrentUser,
  fetchPapers,
  logoutUser,
  ApiError,
  userErrorMessage,
} from '@/lib/api';
import { LibraryList } from '@/components/library-list';
import { AddPaper } from '@/components/add-paper';

export default function LibraryPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ message: string } | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearch, setActiveSearch] = useState('');

  const [showAddPaper, setShowAddPaper] = useState(false);
  const [isAddPaperBusy, setIsAddPaperBusy] = useState(false);

  // Logout state
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<{ message: string } | null>(null);

  const searchInputId = useId();
  const requestSeqRef = useRef(0);
  const addPaperBtnRef = useRef<HTMLButtonElement>(null);
  const wasAddPaperOpen = useRef(false);

  useEffect(() => {
    if (wasAddPaperOpen.current && !showAddPaper) {
      addPaperBtnRef.current?.focus();
    }
    wasAddPaperOpen.current = showAddPaper;
  }, [showAddPaper]);

  const handleUnauthorized = useCallback(() => {
    setUser(null);
    setPapers([]);
    window.location.href = '/sign-in?expired=1';
  }, []);

  const loadLibraryData = useCallback(async (queryParam?: string) => {
    const seq = ++requestSeqRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const profile = await fetchCurrentUser();
      if (seq !== requestSeqRef.current) return;
      setUser(profile);
      const data = await fetchPapers(queryParam);
      if (seq !== requestSeqRef.current) return;
      setPapers(data.papers);
    } catch (err: unknown) {
      if (seq !== requestSeqRef.current) return;
      if (err instanceof ApiError && err.status === 401) {
        handleUnauthorized();
        return;
      }
      const message = userErrorMessage(err, 'Failed to load your library. Please try again.');
      setError({ message });
    } finally {
      if (seq === requestSeqRef.current) {
        setIsLoading(false);
      }
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    loadLibraryData();
  }, [loadLibraryData]);

  async function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setActiveSearch(searchQuery);
    loadLibraryData(searchQuery);
  }

  function handleClearSearch() {
    setSearchQuery('');
    setActiveSearch('');
    loadLibraryData('');
  }

  async function handleLogout() {
    if (isLoggingOut || !user) return;
    setIsLoggingOut(true);
    setLogoutError(null);

    try {
      await logoutUser();
      setUser(null);
      setPapers([]);
      window.location.href = '/sign-in';
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) {
        handleUnauthorized();
        return;
      }
      const message = userErrorMessage(err, 'You are still signed in. Please try again.');
      setLogoutError({ message });
      setIsLoggingOut(false);
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

        {/* Papers List or Empty State (single error location via LibraryList) */}
        <LibraryList
          papers={papers}
          isLoading={isLoading}
          error={error}
          onRetry={() => loadLibraryData(activeSearch)}
          searchQuery={activeSearch}
          onClearSearch={handleClearSearch}
        />
      </main>
    </div>
  );
}
