'use client';

import React, { useState, useEffect, useCallback, useId } from 'react';
import Link from 'next/link';
import {
  Paper,
  UserProfile,
  fetchCurrentUser,
  fetchPapers,
  logoutUser,
  ApiError,
} from '@/lib/api';
import { LibraryList } from '@/components/library-list';
import { AddPaper } from '@/components/add-paper';

export default function LibraryPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ message: string; requestId?: string } | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearch, setActiveSearch] = useState('');

  const [showAddPaper, setShowAddPaper] = useState(false);

  // Logout state
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<{ message: string; requestId?: string } | null>(null);

  const searchInputId = useId();

  const handleUnauthorized = useCallback(() => {
    // Clear stale authenticated view immediately
    setUser(null);
    setPapers([]);
    window.location.href = '/sign-in?expired=1';
  }, []);

  const loadLibraryData = useCallback(async (queryParam?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      // 1. Ensure user is authenticated
      const profile = await fetchCurrentUser();
      setUser(profile);

      // 2. Fetch owner's papers
      const data = await fetchPapers(queryParam);
      setPapers(data.papers);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          handleUnauthorized();
          return;
        }
        setError({ message: err.message, requestId: err.requestId });
      } else {
        setError({ message: 'Failed to connect to the server. Please check your connection and retry.' });
      }
    } finally {
      setIsLoading(false);
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
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    setLogoutError(null);

    try {
      await logoutUser();
      // Server revocation succeeded: clear state and navigate
      setUser(null);
      setPapers([]);
      window.location.href = '/sign-in';
    } catch (err: unknown) {
      // Never claim logout succeeded when server request failed
      if (err instanceof ApiError) {
        if (err.status === 401) {
          // Already logged out or session invalid on server
          handleUnauthorized();
          return;
        }
        setLogoutError({ message: err.message, requestId: err.requestId });
      } else {
        setLogoutError({ message: 'Network error during sign-out. You remain signed in on the server.' });
      }
      setIsLoggingOut(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          borderBottom: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          padding: '1rem 1.5rem',
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
            <Link
              href="/library"
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '1.5rem',
                fontWeight: 700,
                color: 'var(--color-navy)',
                textDecoration: 'none',
                letterSpacing: '-0.02em',
              }}
            >
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
              disabled={isLoggingOut}
              className="btn btn-secondary"
              style={{ minHeight: '40px', padding: '0.375rem 0.875rem', fontSize: '0.875rem' }}
            >
              {isLoggingOut ? 'Signing out...' : 'Sign Out'}
            </button>
          </div>
        </div>
      </header>

      {logoutError && (
        <div
          role="alert"
          style={{
            maxWidth: '1200px',
            margin: '1rem auto 0 auto',
            padding: '0.75rem 1.25rem',
            backgroundColor: 'var(--color-error-bg)',
            border: '1px solid var(--color-error-border)',
            borderRadius: '4px',
            color: 'var(--color-error-text)',
            fontSize: '0.9375rem',
            width: 'calc(100% - 3rem)',
          }}
        >
          <strong>Sign out failed:</strong> {logoutError.message}
          {logoutError.requestId && (
            <span style={{ marginLeft: '0.5rem', opacity: 0.85 }}>
              (Request ID: <code>{logoutError.requestId}</code>)
            </span>
          )}
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
            marginBottom: '2rem',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <div>
            <h1 style={{ fontSize: '2rem', marginBottom: '0.25rem' }}>Library</h1>
            <p style={{ color: 'var(--color-ink-muted)', fontSize: '0.9375rem' }}>
              Your private collection of indexed research documents.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              onClick={() => setShowAddPaper((prev) => !prev)}
              className="btn btn-primary"
            >
              {showAddPaper ? 'Close Add Paper' : 'Add Paper'}
            </button>
          </div>
        </div>

        {/* Add Paper Panel */}
        {showAddPaper && (
          <AddPaper
            onPaperAdded={() => {
              loadLibraryData(activeSearch);
            }}
            onClose={() => setShowAddPaper(false)}
          />
        )}

        {/* Search bar */}
        <section
          aria-label="Filter library"
          style={{
            marginBottom: '1.5rem',
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: '6px',
            padding: '1rem',
          }}
        >
          <form
            onSubmit={handleSearchSubmit}
            style={{
              display: 'flex',
              gap: '0.75rem',
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ flex: '1 1 280px' }}>
              <label htmlFor={searchInputId} style={{ display: 'none' }}>
                Search papers by title or author
              </label>
              <input
                id={searchInputId}
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search library by title or author..."
                className="form-input"
              />
            </div>
            <button type="submit" className="btn btn-primary">
              Search
            </button>
            {activeSearch && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="btn btn-secondary"
              >
                Clear
              </button>
            )}
          </form>
        </section>

        {/* Papers List */}
        <LibraryList
          papers={papers}
          isLoading={isLoading}
          error={error}
          onRetry={() => loadLibraryData(activeSearch)}
          searchQuery={activeSearch}
          onClearSearch={handleClearSearch}
          onOpenAddPaper={() => setShowAddPaper(true)}
        />
      </main>

      <footer
        style={{
          borderTop: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          padding: '1.25rem 1.5rem',
          textAlign: 'center',
          color: 'var(--color-ink-muted)',
          fontSize: '0.8125rem',
        }}
      >
        <p>Researcy Scholarly Systems &bull; Owner-Isolated Library</p>
      </footer>
    </div>
  );
}
