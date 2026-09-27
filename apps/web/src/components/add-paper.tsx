'use client';

import React, { useState, useId, useRef, useEffect, useCallback } from 'react';
import {
  generateIdempotencyKey,
  importArxiv,
  uploadPdf,
  ApiError,
  IntakeResponse,
  formatScreeningWarning,
  userErrorMessage,
} from '@/lib/api';

interface AddPaperProps {
  onPaperAdded?: (paperId: string) => void;
  onClose?: () => void;
  onUnauthorized?: () => void;
  onBusyChange?: (isBusy: boolean) => void;
}

export function AddPaper({ onPaperAdded, onClose, onUnauthorized, onBusyChange }: AddPaperProps) {
  const [activeTab, setActiveTab] = useState<'arxiv' | 'upload'>('arxiv');

  // arXiv form state
  const [arxivInput, setArxivInput] = useState('');
  const [arxivKey, setArxivKey] = useState('');
  const [lastArxivPayload, setLastArxivPayload] = useState<string | null>(null);
  const [arxivSubmitting, setArxivSubmitting] = useState(false);
  const [arxivError, setArxivError] = useState<{ message: string } | null>(null);

  // PDF upload form state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadKey, setUploadKey] = useState('');
  const [lastUploadFile, setLastUploadFile] = useState<File | null>(null);
  const [uploadSubmitting, setUploadSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<{ message: string } | null>(null);

  // Independent cooldown deadlines (avoids background timer drift and does NOT cross-block)
  const [arxivCooldownDeadline, setArxivCooldownDeadline] = useState<number | null>(null);
  const [arxivCooldownSeconds, setArxivCooldownSeconds] = useState(0);

  const [uploadCooldownDeadline, setUploadCooldownDeadline] = useState<number | null>(null);
  const [uploadCooldownSeconds, setUploadCooldownSeconds] = useState(0);

  // Accepted intake result
  const [acceptedResult, setAcceptedResult] = useState<IntakeResponse | null>(null);

  const arxivTabRef = useRef<HTMLButtonElement>(null);
  const uploadTabRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  const isSubmitting = arxivSubmitting || uploadSubmitting;

  useEffect(() => {
    onBusyChange?.(isSubmitting);
  }, [isSubmitting, onBusyChange]);

  // Initial focus management
  useEffect(() => {
    arxivTabRef.current?.focus();
  }, []);

  // Escape key handler (respects isSubmitting)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isSubmitting && onClose) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSubmitting, onClose]);

  // arXiv Cooldown timer
  useEffect(() => {
    if (!arxivCooldownDeadline) return;
    const update = () => {
      const remaining = Math.max(0, Math.ceil((arxivCooldownDeadline - Date.now()) / 1000));
      setArxivCooldownSeconds(remaining);
      if (remaining <= 0) {
        setArxivCooldownDeadline(null);
      }
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [arxivCooldownDeadline]);

  // PDF Upload Cooldown timer
  useEffect(() => {
    if (!uploadCooldownDeadline) return;
    const update = () => {
      const remaining = Math.max(0, Math.ceil((uploadCooldownDeadline - Date.now()) / 1000));
      setUploadCooldownSeconds(remaining);
      if (remaining <= 0) {
        setUploadCooldownDeadline(null);
      }
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [uploadCooldownDeadline]);

  const arxivInputId = useId();
  const fileInputId = useId();

  const handleUnauthorized = useCallback(() => {
    if (onUnauthorized) {
      onUnauthorized();
      return;
    }
    window.location.href = '/sign-in?expired=1';
  }, [onUnauthorized]);

  async function handleArxivSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = arxivInput.trim();
    if (!payload || arxivSubmitting || arxivCooldownSeconds > 0) return;

    setArxivSubmitting(true);
    setArxivError(null);

    // Reuse idempotency key for identical payload; fresh key for changed payload
    let key = arxivKey;
    if (payload !== lastArxivPayload || !key) {
      key = generateIdempotencyKey();
      setArxivKey(key);
    }
    setLastArxivPayload(payload);

    try {
      const result = await importArxiv(payload, key);
      setAcceptedResult(result);
      if (onPaperAdded) {
        onPaperAdded(result.paper_id);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          handleUnauthorized();
          return;
        }
        if (err.retryAfter && err.retryAfter > 0) {
          const deadline = Date.now() + err.retryAfter * 1000;
          if (err.code === 'IMPORT_RATE_LIMITED') {
            setArxivCooldownDeadline(deadline);
            setArxivCooldownSeconds(err.retryAfter);
            setUploadCooldownDeadline(deadline);
            setUploadCooldownSeconds(err.retryAfter);
            setUploadError({ message: userErrorMessage(err, 'Please wait before adding another paper.') });
          } else {
            setArxivCooldownDeadline(deadline);
            setArxivCooldownSeconds(err.retryAfter);
          }
        }
      }
      const message = userErrorMessage(
        err,
        'We could not get this paper from arXiv right now. Please check your link or try again later.'
      );
      setArxivError({ message });
    } finally {
      setArxivSubmitting(false);
    }
  }

  function handleArxivChange(val: string) {
    setArxivInput(val);
    // Only clear error when not on active cooldown, keeping reason for disabled retry visible
    if (arxivCooldownSeconds <= 0 && !arxivCooldownDeadline) {
      setArxivError(null);
    }
  }

  async function handleUploadSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile || uploadSubmitting || uploadCooldownSeconds > 0) return;

    setUploadSubmitting(true);
    setUploadError(null);

    let key = uploadKey;
    if (selectedFile !== lastUploadFile || !key) {
      key = generateIdempotencyKey();
      setUploadKey(key);
    }
    setLastUploadFile(selectedFile);

    try {
      const result = await uploadPdf(selectedFile, key);
      setAcceptedResult(result);
      if (onPaperAdded) {
        onPaperAdded(result.paper_id);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          handleUnauthorized();
          return;
        }
        if (err.retryAfter && err.retryAfter > 0) {
          const deadline = Date.now() + err.retryAfter * 1000;
          if (err.code === 'IMPORT_RATE_LIMITED') {
            setArxivCooldownDeadline(deadline);
            setArxivCooldownSeconds(err.retryAfter);
            setUploadCooldownDeadline(deadline);
            setUploadCooldownSeconds(err.retryAfter);
            setArxivError({ message: userErrorMessage(err, 'Please wait before adding another paper.') });
          } else {
            setUploadCooldownDeadline(deadline);
            setUploadCooldownSeconds(err.retryAfter);
          }
        }
      }
      const message = userErrorMessage(
        err,
        'We could not confirm the upload. Check your connection and try again.'
      );
      setUploadError({ message });
    } finally {
      setUploadSubmitting(false);
    }
  }

  function handleFileChange(file: File | null) {
    setSelectedFile(file);
    if (uploadCooldownSeconds <= 0 && !uploadCooldownDeadline) {
      setUploadError(null);
    }
  }

  function handleTabKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      if (activeTab === 'arxiv') {
        setActiveTab('upload');
        uploadTabRef.current?.focus();
      } else {
        setActiveTab('arxiv');
        arxivTabRef.current?.focus();
      }
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (activeTab === 'upload') {
        setActiveTab('arxiv');
        arxivTabRef.current?.focus();
      } else {
        setActiveTab('upload');
        uploadTabRef.current?.focus();
      }
    } else if (e.key === 'Home') {
      e.preventDefault();
      setActiveTab('arxiv');
      arxivTabRef.current?.focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      setActiveTab('upload');
      uploadTabRef.current?.focus();
    }
  }

  return (
    <section
      id="add-paper-panel"
      ref={panelRef}
      aria-labelledby="add-paper-heading"
      className="add-paper-popover"
      tabIndex={-1}
    >
      <div aria-live="polite" aria-atomic="true" className="visually-hidden">
        {arxivSubmitting ? 'Importing paper from arXiv, please wait.' : uploadSubmitting ? 'Uploading PDF document, please wait.' : ''}
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '1.25rem',
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: '0.75rem',
        }}
      >
        <h2 id="add-paper-heading" style={{ fontSize: '1.375rem', fontWeight: 600 }}>
          Add Paper to Library
        </h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="btn btn-secondary"
            aria-label="Close add paper panel"
            style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', minHeight: '44px' }}
          >
            Close
          </button>
        )}
      </div>

      {acceptedResult ? (
        <div role="status" className="notice-status">
          <h3 style={{ fontSize: '1.25rem', color: 'var(--color-navy)', marginBottom: '0.5rem', fontWeight: 600 }}>
            Added to your library
          </h3>
          <p style={{ marginBottom: '0.5rem', color: 'var(--color-ink)' }}>
            This paper is saved in your library. Reading is not available yet.
          </p>
          {acceptedResult.arxiv_version && (
            <p style={{ marginBottom: '0.5rem', fontSize: '0.9375rem', color: 'var(--color-ink-muted)' }}>
              Source: <strong>arXiv {acceptedResult.arxiv_version}</strong>
            </p>
          )}
          {acceptedResult.screening_warning && (
            <div
              role="note"
              className="notice-warning"
              style={{ marginTop: '0.75rem', marginBottom: '0.75rem' }}
            >
              <strong>About this PDF:</strong>{' '}
              {formatScreeningWarning(acceptedResult.screening_warning)}
            </div>
          )}
          <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <a
              href={`/library/${acceptedResult.paper_id}`}
              className="btn btn-primary"
              style={{ minHeight: '44px' }}
            >
              View in Library
            </a>
            <button
              type="button"
              onClick={() => {
                setAcceptedResult(null);
                setArxivInput('');
                setSelectedFile(null);
                setArxivError(null);
                setUploadError(null);
              }}
              className="btn btn-secondary"
              style={{ minHeight: '44px' }}
            >
              Add Another Paper
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Exactly two import choices: accessible tabs */}
          <div role="tablist" aria-label="Import methods" className="tab-list">
            <button
              ref={arxivTabRef}
              id="tab-arxiv"
              role="tab"
              aria-selected={activeTab === 'arxiv'}
              aria-controls="panel-arxiv"
              tabIndex={activeTab === 'arxiv' ? 0 : -1}
              disabled={isSubmitting}
              onClick={() => setActiveTab('arxiv')}
              onKeyDown={handleTabKeyDown}
              className={`btn ${activeTab === 'arxiv' ? 'btn-primary' : 'btn-secondary'}`}
              type="button"
              style={{ minHeight: '44px' }}
            >
              Import from arXiv
            </button>
            <button
              ref={uploadTabRef}
              id="tab-upload"
              role="tab"
              aria-selected={activeTab === 'upload'}
              aria-controls="panel-upload"
              tabIndex={activeTab === 'upload' ? 0 : -1}
              disabled={isSubmitting}
              onClick={() => setActiveTab('upload')}
              onKeyDown={handleTabKeyDown}
              className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-secondary'}`}
              type="button"
              style={{ minHeight: '44px' }}
            >
              Upload paper
            </button>
          </div>

          {/* Tab 1: arXiv Form */}
          <form
            id="panel-arxiv"
            role="tabpanel"
            aria-labelledby="tab-arxiv"
            hidden={activeTab !== 'arxiv'}
            onSubmit={handleArxivSubmit}
            noValidate
          >
            <div style={{ marginBottom: '1rem' }}>
              <label
                htmlFor={arxivInputId}
                style={{
                  display: 'block',
                  marginBottom: '0.375rem',
                  fontWeight: 600,
                }}
              >
                arXiv ID or URL
              </label>
              <input
                id={arxivInputId}
                type="text"
                value={arxivInput}
                onChange={(e) => handleArxivChange(e.target.value)}
                placeholder="e.g. 1706.03762 or https://arxiv.org/abs/1706.03762"
                className="form-input"
                disabled={arxivSubmitting}
                aria-invalid={arxivError ? 'true' : 'false'}
                aria-describedby={
                  arxivError
                    ? `${arxivInputId}-error ${arxivInputId}-helper`
                    : `${arxivInputId}-helper`
                }
                required
              />
              <p
                id={`${arxivInputId}-helper`}
                style={{
                  fontSize: '0.875rem',
                  color: 'var(--color-ink-muted)',
                  marginTop: '0.375rem',
                }}
              >
                Paste a paper link from arxiv.org, or enter its ID.
              </p>
            </div>

            {arxivError && (
              <div
                id={`${arxivInputId}-error`}
                className="notice-error"
                style={{ marginBottom: '1rem' }}
              >
                <p role="alert" style={{ fontWeight: 600 }}>{arxivError.message}</p>
                {arxivCooldownSeconds > 0 && (
                  <p style={{ marginTop: '0.375rem', fontSize: '0.875rem' }}>
                    Please wait <strong>{arxivCooldownSeconds}s</strong> before retrying.
                  </p>
                )}
                <button
                  type="submit"
                  className="btn btn-secondary"
                  disabled={arxivSubmitting || !arxivInput.trim() || arxivCooldownSeconds > 0}
                  style={{
                    marginTop: '0.5rem',
                    padding: '0.5rem 0.75rem',
                    fontSize: '0.875rem',
                    borderColor: 'var(--color-error-border)',
                    minHeight: '44px',
                  }}
                >
                  {arxivCooldownSeconds > 0 ? `Retry in ${arxivCooldownSeconds}s` : 'Retry Submission'}
                </button>
              </div>
            )}

            <button
              type="submit"
              disabled={arxivSubmitting || !arxivInput.trim() || arxivCooldownSeconds > 0}
              className="btn btn-primary"
              style={{ minHeight: '44px' }}
            >
              {arxivSubmitting ? 'Importing from arXiv...' : 'Import Paper'}
            </button>
          </form>

          {/* Tab 2: PDF Upload Form */}
          <form
            id="panel-upload"
            role="tabpanel"
            aria-labelledby="tab-upload"
            hidden={activeTab !== 'upload'}
            onSubmit={handleUploadSubmit}
            noValidate
          >
            <div style={{ marginBottom: '1rem' }}>
              <label
                htmlFor={fileInputId}
                style={{
                  display: 'block',
                  marginBottom: '0.375rem',
                  fontWeight: 600,
                }}
              >
                Select PDF Document
              </label>
              <input
                id={fileInputId}
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  handleFileChange(file);
                }}
                className="form-input"
                disabled={uploadSubmitting}
                aria-invalid={uploadError ? 'true' : 'false'}
                aria-describedby={
                  uploadError
                    ? `${fileInputId}-error ${fileInputId}-helper`
                    : `${fileInputId}-helper`
                }
                required
              />
              {selectedFile && (
                <p className="editorial-meta" style={{ marginTop: '0.375rem' }}>
                  Selected file: <strong>{selectedFile.name}</strong> ({Math.round(selectedFile.size / 1024)} KB)
                </p>
              )}
              <p
                id={`${fileInputId}-helper`}
                style={{
                  fontSize: '0.875rem',
                  color: 'var(--color-ink-muted)',
                  marginTop: '0.375rem',
                }}
              >
                Supported PDF files up to 25 MiB and 100 pages.
              </p>
            </div>

            {uploadError && (
              <div
                id={`${fileInputId}-error`}
                className="notice-error"
                style={{ marginBottom: '1rem' }}
              >
                <p role="alert" style={{ fontWeight: 600 }}>{uploadError.message}</p>
                {uploadCooldownSeconds > 0 && (
                  <p style={{ marginTop: '0.375rem', fontSize: '0.875rem' }}>
                    Please wait <strong>{uploadCooldownSeconds}s</strong> before retrying.
                  </p>
                )}
                <button
                  type="submit"
                  className="btn btn-secondary"
                  disabled={uploadSubmitting || !selectedFile || uploadCooldownSeconds > 0}
                  style={{
                    marginTop: '0.5rem',
                    padding: '0.5rem 0.75rem',
                    fontSize: '0.875rem',
                    borderColor: 'var(--color-error-border)',
                    minHeight: '44px',
                  }}
                >
                  {uploadCooldownSeconds > 0 ? `Retry in ${uploadCooldownSeconds}s` : 'Retry Upload'}
                </button>
              </div>
            )}

            <button
              type="submit"
              disabled={uploadSubmitting || !selectedFile || uploadCooldownSeconds > 0}
              className="btn btn-primary"
              style={{ minHeight: '44px' }}
            >
              {uploadSubmitting ? 'Uploading PDF...' : 'Upload PDF'}
            </button>
          </form>
        </>
      )}
    </section>
  );
}
