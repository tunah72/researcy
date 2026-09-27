'use client';

import React from 'react';
import Link from 'next/link';

export default function ErrorBoundary({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main
      id="main-content"
      className="container-narrow"
      style={{
        padding: '4rem 1.5rem',
      }}
    >
      <div
        role="alert"
        className="editorial-card"
        style={{
          padding: '2.5rem',
          borderColor: 'var(--color-error-border)',
          textAlign: 'center',
        }}
      >
        <h2 style={{ fontSize: '1.5rem', color: 'var(--color-error-text)', marginBottom: '1rem', fontWeight: 600 }}>
          Unable to Load Library View
        </h2>
        <p style={{ color: 'var(--color-ink-muted)', marginBottom: '1.75rem', lineHeight: 1.6 }}>
          Something unexpected occurred while loading your library view. Please try again.
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => reset()}
            className="btn btn-primary"
            style={{ minHeight: '44px' }}
          >
            Try Again
          </button>
          <Link
            href="/"
            className="btn btn-secondary"
            style={{
              minHeight: '44px',
              display: 'inline-flex',
              alignItems: 'center',
              textDecoration: 'none',
            }}
          >
            Return Home
          </Link>
        </div>
      </div>
    </main>
  );
}
