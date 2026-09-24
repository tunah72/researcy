'use client';

import React, { useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

function SignInContent() {
  const searchParams = useSearchParams();
  const errorParam = searchParams.get('error');
  const isExpired = searchParams.get('expired') === '1' || errorParam === 'expired';
  const [isRedirecting, setIsRedirecting] = useState(false);

  function handleGoogleSignIn() {
    setIsRedirecting(true);
    window.location.href = '/auth/google/start';
  }

  return (
    <div
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: '8px',
        padding: '2.5rem',
        maxWidth: '440px',
        width: '100%',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <h1
          style={{
            fontSize: '2rem',
            color: 'var(--color-navy)',
            marginBottom: '0.5rem',
            letterSpacing: '-0.02em',
          }}
        >
          Researcy
        </h1>
        <p style={{ color: 'var(--color-ink-muted)', fontSize: '1rem' }}>
          Scholarly Library &amp; Document Ingestion
        </p>
      </div>

      {isExpired && (
        <div
          role="alert"
          style={{
            marginBottom: '1.5rem',
            padding: '0.875rem 1rem',
            backgroundColor: 'var(--color-gold-bg)',
            border: '1px solid var(--color-gold-border)',
            borderRadius: '4px',
            color: 'var(--color-gold-text)',
            fontSize: '0.9375rem',
          }}
        >
          <strong>Session expired.</strong> Please sign in again with your Google account to access your library.
        </div>
      )}

      {errorParam && !isExpired && (
        <div
          role="alert"
          style={{
            marginBottom: '1.5rem',
            padding: '0.875rem 1rem',
            backgroundColor: 'var(--color-error-bg)',
            border: '1px solid var(--color-error-border)',
            borderRadius: '4px',
            color: 'var(--color-error-text)',
            fontSize: '0.9375rem',
          }}
        >
          <strong>Authentication error.</strong> The sign-in attempt could not be completed. Please try again.
        </div>
      )}

      <div style={{ marginBottom: '1.5rem' }}>
        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={isRedirecting}
          className="btn btn-primary"
          style={{
            width: '100%',
            fontSize: '1.0625rem',
            padding: '0.75rem 1.25rem',
            gap: '0.5rem',
          }}
        >
          {isRedirecting ? (
            'Connecting to Google...'
          ) : (
            <>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                aria-hidden="true"
                fill="currentColor"
                style={{ flexShrink: 0 }}
              >
                <path d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.761H12.545z" />
              </svg>
              <span>Sign in with Google</span>
            </>
          )}
        </button>
      </div>

      <p
        style={{
          textAlign: 'center',
          fontSize: '0.8125rem',
          color: 'var(--color-ink-muted)',
          lineHeight: 1.5,
        }}
      >
        Access to Researcy is private and owner-isolated.
        <br />
        <Link href="/" style={{ color: 'var(--color-navy)', textDecoration: 'underline' }}>
          Back to overview
        </Link>
      </p>
    </div>
  );
}

export default function SignInPage() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <header
        style={{
          borderBottom: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          padding: '1rem 2rem',
        }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <Link
            href="/"
            className="brand-link"
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '1.25rem',
              fontWeight: 700,
              color: 'var(--color-navy)',
              textDecoration: 'none',
            }}
          >
            Researcy
          </Link>
        </div>
      </header>

      <main
        id="main-content"
        style={{
          flex: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '2rem 1.5rem',
        }}
      >
        <Suspense
          fallback={
            <div
              style={{
                backgroundColor: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: '8px',
                padding: '2.5rem',
                maxWidth: '440px',
                width: '100%',
                textAlign: 'center',
              }}
            >
              <p style={{ color: 'var(--color-ink-muted)' }}>Loading sign-in options...</p>
            </div>
          }
        >
          <SignInContent />
        </Suspense>
      </main>
    </div>
  );
}
