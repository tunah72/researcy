export default function Loading() {
  return (
    <main
      id="main-content"
      className="container-editorial"
      style={{
        padding: '4rem 1.5rem',
      }}
    >
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
          Loading library...
        </p>
      </div>
    </main>
  );
}
