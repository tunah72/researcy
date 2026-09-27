'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetchPaperDetail, PaperDetailResponse, ApiError, formatScreeningWarning, userErrorMessage } from '@/lib/api';

export default function PaperDetailPage() {
  const params = useParams();
  const paperId = typeof params?.paperId === 'string' ? params.paperId : '';

  const [paper, setPaper] = useState<PaperDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ message: string; isNotFound?: boolean } | null>(null);

  const loadDetail = useCallback(async () => {
    if (!paperId) return;
    setIsLoading(true);
    setError(null);

    try {
      const data = await fetchPaperDetail(paperId);
      setPaper(data);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          window.location.href = '/sign-in?expired=1';
          return;
        }
        if (err.status === 404) {
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
      setIsLoading(false);
    }
  }, [paperId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

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
              style={{
                fontSize: '2rem',
                lineHeight: 1.25,
                marginBottom: '1rem',
                letterSpacing: '-0.02em',
                overflowWrap: 'break-word',
                wordBreak: 'break-word',
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

            {/* Honest M1 Status Note — Reading is not available yet */}
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
                Saved in your library. Reading is not available yet.
              </p>
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
