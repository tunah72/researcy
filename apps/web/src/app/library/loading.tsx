export default function Loading() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        maxWidth: '1200px',
        margin: '3rem auto',
        padding: '3rem 1.5rem',
        textAlign: 'center',
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: '6px',
      }}
    >
      <p style={{ color: 'var(--color-ink-muted)', fontSize: '1.125rem' }}>
        Loading library...
      </p>
    </div>
  );
}
