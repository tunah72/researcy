'use client';

import React from 'react';
import Link from 'next/link';
import { Paper } from '@/lib/api';

interface LibraryListProps {
  papers: Paper[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  searchQuery?: string;
  onClearSearch?: () => void;
  onOpenAddPaper?: () => void;
}

export function LibraryList({
  papers,
  isLoading,
  error,
  onRetry,
  searchQuery,
  onClearSearch,
  onOpenAddPaper,
}: LibraryListProps) {
  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          padding: '3rem 1.5rem',
          textAlign: 'center',
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: '6px',
        }}
      >
        <p style={{ color: 'var(--color-ink-muted)', fontSize: '1.125rem' }}>
          Loading your library...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        style={{
          padding: '1.5rem',
          backgroundColor: 'var(--color-error-bg)',
          border: '1px solid var(--color-error-border)',
          borderRadius: '6px',
          marginBottom: '1.5rem',
        }}
      >
        <h3 style={{ color: 'var(--color-error-text)', marginBottom: '0.5rem', fontSize: '1.125rem' }}>
          Unable to Load Library
        </h3>
        <p style={{ color: 'var(--color-ink)', marginBottom: '0.5rem' }}>{error.message}</p>
        {error.requestId && (
          <p style={{ fontSize: '0.8125rem', color: 'var(--color-ink-muted)', marginBottom: '1rem' }}>
            Request ID: <code>{error.requestId}</code>
          </p>
        )}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="btn btn-primary"
            style={{ minHeight: '44px' }}
          >
            Retry Loading
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
        style={{
          padding: '3rem 1.5rem',
          textAlign: 'center',
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: '6px',
        }}
      >
        <h3 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
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
          >
            Clear Search
          </button>
        )}
      </div>
    );
  }

  // Truly empty library state
  if (papers.length === 0) {
    return (
      <div
        role="region"
        aria-label="Empty library"
        style={{
          padding: '3.5rem 1.5rem',
          textAlign: 'center',
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: '6px',
        }}
      >
        <h3 style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>Your Library is Empty</h3>
        <p
          style={{
            color: 'var(--color-ink-muted)',
            maxWidth: '480px',
            margin: '0 auto 1.5rem auto',
          }}
        >
          Researcy keeps your scholarly literature private and indexed. Add your first paper using
          its arXiv identifier or upload a born-digital PDF.
        </p>
        {onOpenAddPaper && (
          <button
            type="button"
            onClick={onOpenAddPaper}
            className="btn btn-primary"
          >
            Add Paper
          </button>
        )}
      </div>
    );
  }

  return (
    <ul
      role="list"
      aria-label="Library papers"
      style={{
        listStyle: 'none',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
    >
      {papers.map((paper) => {
        const stageLabel =
          paper.stage === 'queued' ? 'Waiting for processing' : paper.stage;
        const authorText =
          paper.authors && paper.authors.length > 0
            ? paper.authors.join(', ')
            : 'Unknown author';
        const yearText = paper.year ? String(paper.year) : 'Year unknown';

        return (
          <li
            key={paper.paper_id}
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '6px',
              padding: '1.25rem 1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
              transition: 'border-color 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 300px', minWidth: 0 }}>
                <h3
                  style={{
                    fontSize: '1.25rem',
                    lineHeight: 1.35,
                    marginBottom: '0.375rem',
                    overflowWrap: 'break-word',
                    wordBreak: 'break-word',
                  }}
                >
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
                <p
                  style={{
                    color: 'var(--color-ink-muted)',
                    fontSize: '0.9375rem',
                    marginBottom: '0.25rem',
                  }}
                >
                  <span>{authorText}</span>
                  <span style={{ margin: '0 0.5rem' }}>&bull;</span>
                  <span>{yearText}</span>
                </p>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    flexWrap: 'wrap',
                    fontSize: '0.875rem',
                    color: 'var(--color-ink-muted)',
                    marginTop: '0.5rem',
                  }}
                >
                  <span
                    style={{
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '0.125rem 0.5rem',
                      backgroundColor: 'var(--color-surface-subtle)',
                      borderRadius: '3px',
                      border: '1px solid var(--color-border)',
                    }}
                  >
                    {paper.source}
                  </span>
                  {paper.source_version && (
                    <span>arXiv version: <strong>{paper.source_version}</strong></span>
                  )}
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '0.125rem 0.5rem',
                      backgroundColor: 'var(--color-navy-subtle)',
                      color: 'var(--color-navy)',
                      borderRadius: '3px',
                      fontWeight: 600,
                      fontSize: '0.8125rem',
                    }}
                  >
                    {stageLabel}
                  </span>
                </div>
              </div>

              <div>
                <Link
                  href={`/library/${paper.paper_id}`}
                  className="btn btn-secondary"
                  style={{ whiteSpace: 'nowrap', fontSize: '0.875rem' }}
                >
                  View Details
                </Link>
              </div>
            </div>

            {paper.screening_warning && (
              <div
                role="note"
                style={{
                  marginTop: '0.25rem',
                  padding: '0.5rem 0.75rem',
                  backgroundColor: 'var(--color-gold-bg)',
                  border: '1px solid var(--color-gold-border)',
                  borderRadius: '4px',
                  color: 'var(--color-gold-text)',
                  fontSize: '0.875rem',
                }}
              >
                <strong>Screening notice:</strong> {paper.screening_warning}. M2 processing may fail.
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
