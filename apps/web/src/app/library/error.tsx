'use client';

import React from 'react';
import Link from 'next/link';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      role="alert"
      style={{
        maxWidth: '600px',
        margin: '4rem auto',
        padding: '2.5rem',
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-error-border)',
        borderRadius: '8px',
        textAlign: 'center',
      }}
    >
      <h2 style={{ fontSize: '1.5rem', color: 'var(--color-error-text)', marginBottom: '1rem' }}>
        Unable to Load Library View
      </h2>
      <p style={{ color: 'var(--color-ink-muted)', marginBottom: '1.5rem' }}>
        {error.message || 'An unexpected error occurred while loading this view.'}
      </p>
      {error.digest && (
        <p style={{ fontSize: '0.8125rem', color: 'var(--color-ink-muted)', marginBottom: '1.5rem' }}>
          Error Digest: <code>{error.digest}</code>
        </p>
      )}
      <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
        <button type="button" onClick={() => reset()} className="btn btn-primary">
          Try Again
        </button>
        <Link href="/" className="btn btn-secondary">
          Return Home
        </Link>
      </div>
    </div>
  );
}
