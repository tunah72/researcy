'use client';

import { useEffect, useState } from 'react';
import type { Preparation } from '@/lib/api';

interface PaperPreparationProps {
  preparation: Preparation;
  isRetrying?: boolean;
  disabled?: boolean;
  retryError?: string | null;
  retryDeadline?: number;
  onRetry?: () => void;
}

const failureCopy = {
  temporary: 'Preparation could not finish because a service is temporarily unavailable.',
  unsupported: 'This PDF cannot be prepared. Try a supported PDF with extractable text.',
  resource_limit: 'This PDF exceeds the available processing limits.',
  integrity: 'Preparation could not safely verify this PDF.',
};

export function PaperPreparation({ preparation, isRetrying, disabled = false, retryError, retryDeadline = 0, onRetry }: PaperPreparationProps) {
  const seconds = preparation?.retry_after_seconds ?? 0;
  const [deadline, setDeadline] = useState(() => Date.now() + Math.max(0, seconds) * 1000);
  const [now, setNow] = useState(Date.now);
  useEffect(() => { setDeadline(Date.now() + Math.max(0, seconds) * 1000); setNow(Date.now()); }, [preparation, seconds]);
  const effectiveDeadline = Math.max(deadline, retryDeadline);
  useEffect(() => {
    if (effectiveDeadline <= Date.now()) return;
    const timer = window.setInterval(() => {
      const tick = Date.now(); setNow(tick);
      if (tick >= effectiveDeadline) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [effectiveDeadline]);
  const remaining = Math.max(0, Math.ceil((effectiveDeadline - now) / 1000));
  if (preparation?.state === 'complete') return null;
  let copy = 'Preparation status is unavailable. Check again later.';
  switch (preparation?.state) {
    case 'waiting': copy = 'Waiting for preparation.'; break;
    case 'preparing': copy = 'Preparing this PDF.'; break;
    case 'delayed': copy = 'Preparation is waiting to resume.'; break;
    case 'failed':
      copy = preparation.reason && Object.hasOwn(failureCopy, preparation.reason)
        ? failureCopy[preparation.reason] : 'This PDF could not be prepared.';
      break;
  }
  const canRetry = preparation?.state === 'failed' && preparation.retryable && onRetry;
  return (
    <div style={{ marginTop: '0.75rem', fontSize: '0.875rem', color: 'var(--color-ink-muted)' }}>
      <p role="status" aria-live="polite">{copy}</p>
      {canRetry && <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
        <button type="button" className="btn btn-secondary" style={{ minHeight: '44px', minWidth: '44px' }} disabled={disabled || isRetrying || remaining > 0} onClick={onRetry} aria-label="Try again">
          {isRetrying ? 'Retrying…' : 'Try again'}
        </button>
        {remaining > 0 && <span aria-live="off">Available in {remaining}s</span>}
      </div>}
      {retryError && <p role="status" style={{ marginTop: '0.5rem' }}>{retryError}</p>}
    </div>
  );
}
