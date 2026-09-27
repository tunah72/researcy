'use client';

import React from 'react';
import Link from 'next/link';
import { Paper, formatScreeningWarning } from '@/lib/api';

interface LibraryListProps {
  papers: Paper[];
  isLoading?: boolean;
  error?: { message: string } | null;
  onRetry?: () => void;
  searchQuery?: string;
  onClearSearch?: () => void;
}

export function LibraryList({
  papers,
  isLoading,
  error,
  onRetry,
  searchQuery,
  onClearSearch,
}: LibraryListProps) {
  if (isLoading) {
    return (
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
          Loading papers...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="editorial-card"
        style={{
          padding: '2rem 1.5rem',
          borderColor: 'var(--color-error-border)',
          textAlign: 'center',
        }}
      >
        <h3 style={{ fontSize: '1.25rem', color: 'var(--color-error-text)', marginBottom: '0.5rem', fontWeight: 600 }}>
          Unable to Load Library
        </h3>
        <p style={{ color: 'var(--color-ink-muted)', marginBottom: '1.25rem' }}>
          {error.message}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="btn btn-primary"
            style={{ minHeight: '44px' }}
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  // Query empty state
  if (papers.length === 0 && searchQuery && searchQuery.trim().length > 0) {
    return (
      <div
        role="region"
        aria-label="Search results"
        className="editorial-card"
        style={{
          padding: '3rem 1.5rem',
          textAlign: 'center',
        }}
      >
        <h3 style={{ fontSize: '1.25rem', marginBottom: '0.5rem', fontWeight: 600 }}>
          No papers match &ldquo;{searchQuery}&rdquo;
        </h3>
        <p style={{ color: 'var(--color-ink-muted)', marginBottom: '1.5rem' }}>
          Try searching with different terms or check for typos.
        </p>
        {onClearSearch && (
          <button
            type="button"
            onClick={onClearSearch}
            className="btn btn-secondary"
            style={{ minHeight: '44px' }}
          >
            Clear Search
          </button>
        )}
      </div>
    );
  }

  // The persistent toolbar owns the sole Add Paper trigger.
  if (papers.length === 0) {
    return (
      <div
        role="region"
        aria-label="Empty library"
        className="editorial-card"
        style={{
          padding: '3.5rem 1.5rem',
          textAlign: 'center',
        }}
      >
        <h3 style={{ fontSize: '1.5rem', marginBottom: '0.75rem', fontWeight: 600 }}>Your Library is Empty</h3>
        <p
          style={{
            color: 'var(--color-ink-muted)',
            maxWidth: '480px',
            margin: '0 auto 1.5rem auto',
            lineHeight: 1.6,
          }}
        >
          Researcy keeps your scholarly literature organized in a private workspace. Add your first paper using
          its arXiv identifier or upload a PDF.
        </p>
      </div>
    );
  }

  return (
    <div className="paper-table">
      <div className="list-head" aria-hidden="true">
        <div>Paper</div>
        <div>Source</div>
        <div style={{ textAlign: 'right' }}>Action</div>
      </div>
      <ul
        role="list"
        aria-label="Library papers"
        style={{ listStyle: 'none', margin: 0, padding: 0 }}
      >
        {papers.map((paper) => {
          const authorText =
            paper.authors && paper.authors.length > 0
              ? paper.authors.join(', ')
              : 'Unknown author';
          const yearText = paper.year ? String(paper.year) : 'Year unknown';
          const sourceLabel =
            paper.source === 'arxiv'
              ? paper.source_version
                ? `arXiv ${paper.source_version}`
                : 'arXiv'
              : paper.source === 'upload'
              ? 'Uploaded PDF'
              : paper.source;
          const firstChar = (paper.title || 'U').trim().charAt(0).toUpperCase();

          return (
            <li key={paper.paper_id} className="paper-row">
              <div className="paper-main">
                <div className="paper-cover" aria-hidden="true">
                  {firstChar}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <h3 className="paper-name">
                    <Link
                      href={`/library/${paper.paper_id}`}
                      className="paper-title-link"
                      style={{
                        color: 'var(--color-navy)',
                        textDecoration: 'none',
                      }}
                    >
                      {paper.title || 'Untitled Document'}
                    </Link>
                  </h3>
                  <p className="paper-authors">
                    <span>{authorText}</span>
                    <span style={{ margin: '0 0.375rem' }}>&bull;</span>
                    <span>{yearText}</span>
                  </p>
                  {paper.screening_warning && (
                    <div
                      role="note"
                      className="notice-warning"
                      style={{
                        marginTop: '0.5rem',
                        padding: '0.4rem 0.625rem',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <strong>About this PDF:</strong>{' '}
                      {formatScreeningWarning(paper.screening_warning)}
                    </div>
                  )}
                </div>
              </div>

              <div>
                <span className="badge-source">
                  {sourceLabel}
                </span>
              </div>

              <div style={{ textAlign: 'right' }}>
                <Link
                  href={`/library/${paper.paper_id}`}
                  className="btn btn-secondary"
                  style={{
                    padding: '0.375rem 0.75rem',
                    fontSize: '0.8125rem',
                    textDecoration: 'none',
                    minHeight: '44px',
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
                >
                  View details
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
