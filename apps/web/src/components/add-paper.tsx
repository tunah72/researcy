'use client';

import React, { useState, useId } from 'react';
import {
  generateIdempotencyKey,
  importArxiv,
  uploadPdf,
  ApiError,
  IntakeResponse,
} from '@/lib/api';

interface AddPaperProps {
  onPaperAdded?: (paperId: string) => void;
  onClose?: () => void;
}

export function AddPaper({ onPaperAdded, onClose }: AddPaperProps) {
  const [activeTab, setActiveTab] = useState<'arxiv' | 'upload'>('arxiv');

  // arXiv form state
  const [arxivInput, setArxivInput] = useState('');
  const [arxivKey, setArxivKey] = useState('');
  const [lastArxivPayload, setLastArxivPayload] = useState<string | null>(null);
  const [arxivSubmitting, setArxivSubmitting] = useState(false);
  const [arxivError, setArxivError] = useState<{
    code?: string;
    message: string;
    requestId?: string;
  } | null>(null);

  // PDF upload form state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadKey, setUploadKey] = useState('');
  const [lastUploadPayload, setLastUploadPayload] = useState<string | null>(null);
  const [uploadSubmitting, setUploadSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<{
    code?: string;
    message: string;
    requestId?: string;
  } | null>(null);

  // Accepted intake result
  const [acceptedResult, setAcceptedResult] = useState<IntakeResponse | null>(null);

  const arxivInputId = useId();
  const fileInputId = useId();

  async function handleArxivSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = arxivInput.trim();
    if (!payload || arxivSubmitting) return;

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
          window.location.href = '/sign-in';
          return;
        }
        setArxivError({
          code: err.code,
          message: err.message,
          requestId: err.requestId,
        });
      } else {
        setArxivError({
          message: 'Network request failed. Please check your connection and retry.',
        });
      }
    } finally {
      setArxivSubmitting(false);
    }
  }

  async function handleUploadSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile || uploadSubmitting) return;

    setUploadSubmitting(true);
    setUploadError(null);

    const payload = `${selectedFile.name}:${selectedFile.size}:${selectedFile.lastModified}`;
    let key = uploadKey;
    if (payload !== lastUploadPayload || !key) {
      key = generateIdempotencyKey();
      setUploadKey(key);
    }
    setLastUploadPayload(payload);

    try {
      const result = await uploadPdf(selectedFile, key);
      setAcceptedResult(result);
      if (onPaperAdded) {
        onPaperAdded(result.paper_id);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          window.location.href = '/sign-in';
          return;
        }
        setUploadError({
          code: err.code,
          message: err.message,
          requestId: err.requestId,
        });
      } else {
        setUploadError({
          message: 'Upload failed. Please check your connection and retry.',
        });
      }
    } finally {
      setUploadSubmitting(false);
    }
  }

  return (
    <section
      aria-labelledby="add-paper-heading"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: '6px',
        padding: '1.5rem',
        marginBottom: '2rem',
      }}
    >
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
            className="btn btn-secondary"
            aria-label="Close add paper panel"
            style={{ minHeight: '36px', padding: '0.25rem 0.75rem', fontSize: '0.875rem' }}
          >
            Close
          </button>
        )}
      </div>

      {acceptedResult ? (
        <div
          role="status"
          style={{
            padding: '1.25rem',
            backgroundColor: 'var(--color-navy-subtle)',
            border: '1px solid var(--color-navy)',
            borderRadius: '4px',
          }}
        >
          <h3 style={{ fontSize: '1.125rem', color: 'var(--color-navy)', marginBottom: '0.5rem' }}>
            Paper Accepted
          </h3>
          <p style={{ marginBottom: '0.5rem' }}>
            Status: <strong>Waiting for processing</strong>
          </p>
          {acceptedResult.arxiv_version && (
            <p style={{ marginBottom: '0.5rem', fontSize: '0.9375rem' }}>
              Stored arXiv version: <strong>{acceptedResult.arxiv_version}</strong>
            </p>
          )}
          {acceptedResult.screening_warning && (
            <div
              role="alert"
              style={{
                marginTop: '0.75rem',
                marginBottom: '0.75rem',
                padding: '0.75rem',
                backgroundColor: 'var(--color-gold-bg)',
                border: '1px solid var(--color-gold-border)',
                borderRadius: '4px',
                color: 'var(--color-gold-text)',
                fontSize: '0.9375rem',
              }}
            >
              <strong>Screening Notice:</strong> {acceptedResult.screening_warning}. M2 processing may fail.
            </div>
          )}
          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem' }}>
            <a
              href={`/library/${acceptedResult.paper_id}`}
              className="btn btn-primary"
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
            >
              Add Another Paper
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Exactly two import options: tab bar */}
          <div
            role="tablist"
            aria-label="Import methods"
            style={{
              display: 'flex',
              gap: '0.5rem',
              marginBottom: '1.5rem',
            }}
          >
            <button
              id="tab-arxiv"
              role="tab"
              aria-selected={activeTab === 'arxiv'}
              aria-controls="panel-arxiv"
              onClick={() => setActiveTab('arxiv')}
              className={`btn ${activeTab === 'arxiv' ? 'btn-primary' : 'btn-secondary'}`}
              type="button"
            >
              arXiv Import
            </button>
            <button
              id="tab-upload"
              role="tab"
              aria-selected={activeTab === 'upload'}
              aria-controls="panel-upload"
              onClick={() => setActiveTab('upload')}
              className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-secondary'}`}
              type="button"
            >
              PDF Upload
            </button>
          </div>

          {/* Option 1: arXiv Form */}
          {activeTab === 'arxiv' && (
            <form
              id="panel-arxiv"
              role="tabpanel"
              aria-labelledby="tab-arxiv"
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
                  onChange={(e) => setArxivInput(e.target.value)}
                  placeholder="e.g. 1706.03762 or https://arxiv.org/abs/1706.03762"
                  className="form-input"
                  disabled={arxivSubmitting}
                  aria-invalid={arxivError ? 'true' : 'false'}
                  aria-describedby={arxivError ? 'arxiv-error-msg' : 'arxiv-helper'}
                  required
                />
                <p
                  id="arxiv-helper"
                  style={{
                    fontSize: '0.875rem',
                    color: 'var(--color-ink-muted)',
                    marginTop: '0.375rem',
                  }}
                >
                  Accepts canonical arXiv identifiers or official arXiv abstract/PDF URLs.
                </p>
              </div>

              {arxivError && (
                <div
                  id="arxiv-error-msg"
                  role="alert"
                  style={{
                    marginBottom: '1rem',
                    padding: '0.75rem',
                    backgroundColor: 'var(--color-error-bg)',
                    border: '1px solid var(--color-error-border)',
                    borderRadius: '4px',
                    color: 'var(--color-error-text)',
                    fontSize: '0.9375rem',
                  }}
                >
                  <p style={{ fontWeight: 600 }}>{arxivError.message}</p>
                  {arxivError.requestId && (
                    <p style={{ fontSize: '0.8125rem', marginTop: '0.25rem', opacity: 0.85 }}>
                      Request ID: <code>{arxivError.requestId}</code>
                    </p>
                  )}
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    disabled={arxivSubmitting}
                    style={{
                      marginTop: '0.5rem',
                      minHeight: '36px',
                      padding: '0.25rem 0.75rem',
                      fontSize: '0.875rem',
                      borderColor: 'var(--color-error-border)',
                    }}
                  >
                    Retry Submission
                  </button>
                </div>
              )}

              <button
                type="submit"
                disabled={arxivSubmitting || !arxivInput.trim()}
                className="btn btn-primary"
              >
                {arxivSubmitting ? 'Importing from arXiv...' : 'Import Paper'}
              </button>
            </form>
          )}

          {/* Option 2: PDF Upload Form */}
          {activeTab === 'upload' && (
            <form
              id="panel-upload"
              role="tabpanel"
              aria-labelledby="tab-upload"
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
                    setSelectedFile(file);
                    setUploadError(null);
                  }}
                  className="form-input"
                  disabled={uploadSubmitting}
                  aria-invalid={uploadError ? 'true' : 'false'}
                  aria-describedby={uploadError ? 'upload-error-msg' : 'upload-helper'}
                  required
                />
                <p
                  id="upload-helper"
                  style={{
                    fontSize: '0.875rem',
                    color: 'var(--color-ink-muted)',
                    marginTop: '0.375rem',
                  }}
                >
                  Supported born-digital PDF files up to 25 MiB and 100 pages.
                </p>
              </div>

              {uploadError && (
                <div
                  id="upload-error-msg"
                  role="alert"
                  style={{
                    marginBottom: '1rem',
                    padding: '0.75rem',
                    backgroundColor: 'var(--color-error-bg)',
                    border: '1px solid var(--color-error-border)',
                    borderRadius: '4px',
                    color: 'var(--color-error-text)',
                    fontSize: '0.9375rem',
                  }}
                >
                  <p style={{ fontWeight: 600 }}>{uploadError.message}</p>
                  {uploadError.requestId && (
                    <p style={{ fontSize: '0.8125rem', marginTop: '0.25rem', opacity: 0.85 }}>
                      Request ID: <code>{uploadError.requestId}</code>
                    </p>
                  )}
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    disabled={uploadSubmitting}
                    style={{
                      marginTop: '0.5rem',
                      minHeight: '36px',
                      padding: '0.25rem 0.75rem',
                      fontSize: '0.875rem',
                      borderColor: 'var(--color-error-border)',
                    }}
                  >
                    Retry Upload
                  </button>
                </div>
              )}

              <button
                type="submit"
                disabled={uploadSubmitting || !selectedFile}
                className="btn btn-primary"
              >
                {uploadSubmitting ? 'Uploading PDF...' : 'Upload PDF'}
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
