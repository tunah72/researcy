import Link from 'next/link';

export default function LandingPage() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          borderBottom: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          padding: '1.25rem 2rem',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '1.5rem',
                fontWeight: 700,
                color: 'var(--color-navy)',
                letterSpacing: '-0.02em',
              }}
            >
              Researcy
            </span>
            <span
              style={{
                fontSize: '0.75rem',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                fontWeight: 700,
                color: 'var(--color-gold)',
                padding: '0.125rem 0.375rem',
                backgroundColor: 'var(--color-gold-bg)',
                borderRadius: '3px',
              }}
            >
              Scholarly Workspace
            </span>
          </div>

          <nav aria-label="Main Navigation">
            <Link
              href="/library"
              className="btn btn-primary"
            >
              Go to Library
            </Link>
          </nav>
        </div>
      </header>

      <main
        id="main-content"
        style={{
          flex: 1,
          maxWidth: '960px',
          margin: '0 auto',
          padding: '4rem 1.5rem 6rem 1.5rem',
          width: '100%',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '4rem' }}>
          <h1
            style={{
              fontSize: '3rem',
              lineHeight: 1.15,
              fontWeight: 700,
              color: 'var(--color-ink)',
              marginBottom: '1.5rem',
              letterSpacing: '-0.03em',
            }}
          >
            A Private Workspace for Scholarly Literature
          </h1>
          <p
            style={{
              fontSize: '1.25rem',
              lineHeight: 1.6,
              color: 'var(--color-ink-muted)',
              maxWidth: '680px',
              margin: '0 auto 2.5rem auto',
            }}
          >
            Researcy provides owner-isolated paper intake, immutable document archiving, and
            transparent ingestion tracking for academic researchers.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            <Link
              href="/sign-in"
              className="btn btn-primary"
              style={{ fontSize: '1.125rem', padding: '0.75rem 2rem' }}
            >
              Sign in with Google
            </Link>
            <Link
              href="/library"
              className="btn btn-secondary"
              style={{ fontSize: '1.125rem', padding: '0.75rem 2rem' }}
            >
              Open Library
            </Link>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '1.5rem',
            marginTop: '2rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '6px',
              padding: '1.75rem',
            }}
          >
            <h2
              style={{
                fontSize: '1.25rem',
                color: 'var(--color-navy)',
                marginBottom: '0.75rem',
              }}
            >
              Owner Isolation
            </h2>
            <p style={{ color: 'var(--color-ink-muted)', fontSize: '0.9375rem', lineHeight: 1.6 }}>
              Every document, metadata record, and ingestion job is cryptographically scoped to your
              authenticated identity. Private objects are strictly protected against unauthorized access.
            </p>
          </div>

          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '6px',
              padding: '1.75rem',
            }}
          >
            <h2
              style={{
                fontSize: '1.25rem',
                color: 'var(--color-navy)',
                marginBottom: '0.75rem',
              }}
            >
              Verified Intake
            </h2>
            <p style={{ color: 'var(--color-ink-muted)', fontSize: '0.9375rem', lineHeight: 1.6 }}>
              Import directly from official arXiv records or upload verified born-digital PDF files.
              SHA-256 verification and pre-ingestion screening protect data integrity.
            </p>
          </div>

          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '6px',
              padding: '1.75rem',
            }}
          >
            <h2
              style={{
                fontSize: '1.25rem',
                color: 'var(--color-navy)',
                marginBottom: '0.75rem',
              }}
            >
              Editorial Restraint
            </h2>
            <p style={{ color: 'var(--color-ink-muted)', fontSize: '0.9375rem', lineHeight: 1.6 }}>
              Built with typography designed for reading clarity, high contrast ratios, and honest
              system states. No fabricated progress, no speculative completion claims.
            </p>
          </div>
        </div>
      </main>

      <footer
        style={{
          borderTop: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          padding: '1.5rem',
          textAlign: 'center',
          color: 'var(--color-ink-muted)',
          fontSize: '0.875rem',
        }}
      >
        <p>Researcy Scholarly Systems &bull; Licensed Typography &bull; Clean Ingestion Boundary</p>
      </footer>
    </div>
  );
}
