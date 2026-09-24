'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetchPaperDetail, PaperDetailResponse, ApiError } from '@/lib/api';

export default function PaperDetailPage() {
  const params = useParams();
  const paperId = typeof params?.paperId === 'string' ? params.paperId : '';

  const [paper, setPaper] = useState<PaperDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<{ code?: string; message: string; requestId?: string; isNotFound?: boolean } | null>(null);

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
            code: err.code,
            message: 'This document could not be found in your private library.',
            requestId: err.requestId,
            isNotFound: true,
          });
          return;
        }
        setError({
          code: err.code,
          message: err.message,
          requestId: err.requestId,
        });
      } else {
        setError({
          message: 'Failed to load paper details. Please check your network connection.',
        });
      }
    } finally {
      setIsLoading(false);
    }
  }, [paperId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const stageLabel =
    paper?.stage === 'queued' ? 'Waiting for processing' : paper?.stage || 'Unknown';
  const authorText =
    paper?.authors && paper.authors.length > 0
      ? paper.authors.join(', ')
      : 'Unknown author';
  const yearText = paper?.year ? String(paper.year) : 'Year unknown';

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
              Document Details
            </span>
          </div>

          <Link href="/library" className="btn btn-secondary">
            &larr; Back to Library
          </Link>
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
            style={{
              padding: '3rem 1.5rem',
              textAlign: 'center',
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '6px',
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
            style={{
              padding: '2rem',
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '6px',
              textAlign: 'center',
            }}
          >
            <h2 style={{ fontSize: '1.5rem', marginBottom: '0.75rem', color: 'var(--color-error-text)' }}>
              {error.isNotFound ? 'Document Not Found' : 'Error Loading Document'}
            </h2>
            <p style={{ color: 'var(--color-ink-muted)', marginBottom: '1.5rem', maxWidth: '480px', margin: '0 auto 1.5rem auto' }}>
              {error.message}
            </p>
            {error.requestId && (
              <p style={{ fontSize: '0.8125rem', color: 'var(--color-ink-muted)', marginBottom: '1.5rem' }}>
                Request ID: <code>{error.requestId}</code>
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
              {!error.isNotFound && (
                <button type="button" onClick={loadDetail} className="btn btn-primary">
                  Retry
                </button>
              )}
              <Link href="/library" className="btn btn-secondary">
                Return to Library
              </Link>
            </div>
          </div>
        )}

        {!isLoading && !error && paper && (
          <article
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '8px',
              padding: '2.5rem',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '1rem',
              }}
            >
              <span
                style={{
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '0.2rem 0.6rem',
                  backgroundColor: 'var(--color-surface-subtle)',
                  borderRadius: '3px',
                  border: '1px solid var(--color-border)',
                }}
              >
                {paper.source}
              </span>
              <span
                style={{
                  padding: '0.2rem 0.6rem',
                  backgroundColor: 'var(--color-navy-subtle)',
                  color: 'var(--color-navy)',
                  borderRadius: '3px',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                }}
              >
                {stageLabel}
              </span>
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
                paddingBottom: '1.5rem',
                marginBottom: '1.5rem',
                color: 'var(--color-ink-muted)',
                fontSize: '1rem',
              }}
            >
              <p style={{ marginBottom: '0.25rem' }}>
                <strong>Authors:</strong> {authorText}
              </p>
              <p>
                <strong>Publication Year:</strong> {yearText}
              </p>
            </div>

            {/* Screening warning if present */}
            {paper.screening_warning && (
              <div
                role="note"
                style={{
                  marginBottom: '1.5rem',
                  padding: '1rem 1.25rem',
                  backgroundColor: 'var(--color-gold-bg)',
                  border: '1px solid var(--color-gold-border)',
                  borderRadius: '4px',
                  color: 'var(--color-gold-text)',
                  fontSize: '0.9375rem',
                  lineHeight: 1.5,
                }}
              >
                <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.25rem', color: 'var(--color-gold-text)' }}>
                  Screening Notice
                </h2>
                <p>
                  {paper.screening_warning}. The uploaded document has low extractable text. Full parsing and semantic search in M2 may fail.
                </p>
              </div>
            )}

            {/* Metadata DL */}
            <dl
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr',
                gap: '0.75rem 1.5rem',
                fontSize: '0.9375rem',
                marginBottom: '2rem',
              }}
            >
              <dt style={{ fontWeight: 600, color: 'var(--color-ink-muted)' }}>Document ID:</dt>
              <dd><code>{paper.paper_id}</code></dd>

              <dt style={{ fontWeight: 600, color: 'var(--color-ink-muted)' }}>Active Version:</dt>
              <dd><code>{paper.active_version_id}</code></dd>

              {paper.source_version && (
                <>
                  <dt style={{ fontWeight: 600, color: 'var(--color-ink-muted)' }}>Source Version:</dt>
                  <dd><code>{paper.source_version}</code></dd>
                </>
              )}

              <dt style={{ fontWeight: 600, color: 'var(--color-ink-muted)' }}>Ingestion Stage:</dt>
              <dd>
                <span
                  style={{
                    backgroundColor: 'var(--color-navy-subtle)',
                    color: 'var(--color-navy)',
                    padding: '0.125rem 0.5rem',
                    borderRadius: '3px',
                    fontWeight: 600,
                  }}
                >
                  {stageLabel}
                </span>
              </dd>
            </dl>

            {/* Honest M1 Status Note — No functional Reader or fake retry */}
            <div
              style={{
                padding: '1.25rem',
                backgroundColor: 'var(--color-surface-subtle)',
                border: '1px solid var(--color-border)',
                borderRadius: '6px',
                fontSize: '0.875rem',
                color: 'var(--color-ink-muted)',
                lineHeight: 1.5,
              }}
            >
              <p>
                <strong>Ingestion Notice:</strong> This document is safely accepted in your private library and queued for downstream processing. Interactive reading, citation graphs, and grounded Q&amp;A will activate once M2 background extraction is deployed.
              </p>
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
