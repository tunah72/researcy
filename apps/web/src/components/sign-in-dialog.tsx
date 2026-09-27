'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';

export interface SignInDialogProps {
  isOpen: boolean;
  onClose: () => void;
  error?: string | null;
  isExpired?: boolean;
  triggerElement?: HTMLElement | null;
}

export function SignInDialog({
  isOpen,
  onClose,
  error,
  isExpired,
  triggerElement,
}: SignInDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const [isRedirecting, setIsRedirecting] = useState(false);

  // Sync open state with native <dialog>
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen) {
      if (!dialog.open) {
        previousActiveElement.current = triggerElement || (document.activeElement as HTMLElement | null);
        dialog.showModal();
      }
    } else {
      if (dialog.open) {
        dialog.close();
      }
      setIsRedirecting(false);
      if (previousActiveElement.current && typeof previousActiveElement.current.focus === 'function') {
        previousActiveElement.current.focus();
        previousActiveElement.current = null;
      }
    }
  }, [isOpen, triggerElement]);

  // Handle native cancel (Escape key)
  const handleCancel = useCallback(
    (e: React.SyntheticEvent<HTMLDialogElement, Event>) => {
      e.preventDefault();
      onClose();
    },
    [onClose]
  );

  // Handle backdrop clicks (clicking outside the card)
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDialogElement>) => {
      if (e.target === dialogRef.current) {
        onClose();
      }
    },
    [onClose]
  );

  // Handle Google authentication redirect
  const handleGoogleSignIn = useCallback(() => {
    setIsRedirecting(true);
    window.location.href = '/auth/google/start';
  }, []);

  // Handle bfcache restore to unstick redirecting state
  useEffect(() => {
    function handlePageShow(event: PageTransitionEvent) {
      if (event.persisted) {
        setIsRedirecting(false);
      }
    }

    window.addEventListener('pageshow', handlePageShow);
    return () => {
      window.removeEventListener('pageshow', handlePageShow);
    };
  }, []);

  // If dialog is not open in DOM, do not render or keep closed
  return (
    <dialog
      ref={dialogRef}
      onCancel={handleCancel}
      onClick={handleBackdropClick}
      aria-labelledby="sign-in-dialog-title"
      className="onboarding-dialog"
    >
      <div className="onboarding-dialog-card">
        <button
          type="button"
          onClick={onClose}
          className="onboarding-dialog-close"
          aria-label="Close"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className="onboarding-dialog-mark" aria-hidden="true">
          R
        </div>

        <h2 id="sign-in-dialog-title" className="onboarding-dialog-title">
          Continue to Researcy
        </h2>
        <p className="onboarding-dialog-desc">
          Save papers from arXiv or your device and keep your research organized in a private workspace.
        </p>

        {isExpired && (
          <div role="alert" className="onboarding-dialog-alert onboarding-dialog-alert-warning">
            <strong>Please sign in again.</strong> Your session has expired.
          </div>
        )}

        {error && !isExpired && (
          <div role="alert" className="onboarding-dialog-alert onboarding-dialog-alert-error">
            <strong>Could not sign in.</strong> Please try again.
          </div>
        )}

        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={isRedirecting}
          className="onboarding-btn-google"
        >
          {isRedirecting ? (
            <span>Connecting to Google...</span>
          ) : (
            <>
              <svg
                className="onboarding-google-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              <span>Continue with Google</span>
            </>
          )}
        </button>

        <p className="onboarding-dialog-footer">
          One Google account. Your own paper collection.
        </p>
      </div>
    </dialog>
  );
}
