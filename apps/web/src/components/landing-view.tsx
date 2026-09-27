'use client';

import React, { useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { SignInDialog } from './sign-in-dialog';

export interface LandingViewProps {
  initialSignInOpen?: boolean;
  signInError?: string | null;
  signInExpired?: boolean;
}

export function LandingView({
  initialSignInOpen = false,
  signInError = null,
  signInExpired = false,
}: LandingViewProps) {
  const router = useRouter();
  const [isSignInOpen, setIsSignInOpen] = useState(initialSignInOpen);
  const [signInTrigger, setSignInTrigger] = useState<HTMLElement | null>(null);

  const handleOpenSignIn = useCallback((trigger: HTMLElement | null) => {
    setSignInTrigger(trigger);
    setIsSignInOpen(true);
  }, []);

  const handleCloseSignIn = useCallback(() => {
    setIsSignInOpen(false);
    if (initialSignInOpen) {
      router.push('/');
    }
  }, [initialSignInOpen, router]);

  return (
    <div className="onboarding-page">
      <header className="onboarding-header">
        <div className="onboarding-nav">
          <Link href="/" className="onboarding-brand" aria-label="Researcy home">
            <span className="onboarding-brand-mark" aria-hidden="true">
              R
            </span>
            <span>Researcy</span>
          </Link>

          <nav aria-label="Main navigation" className="onboarding-nav-actions">
            <a href="#how-it-works" className="onboarding-anchor-link">
              How it works
            </a>
            <button
              type="button"
              onClick={(e) => handleOpenSignIn(e.currentTarget)}
              className="btn btn-secondary onboarding-header-signin"
            >
              Sign in
            </button>
          </nav>
        </div>
      </header>

      <main id="main-content" className="onboarding-main">
        {/* Benefit-led hero */}
        <section className="onboarding-hero" aria-labelledby="hero-heading">
          <div className="onboarding-kicker">Scholarly Workspace &bull; Private Library</div>
          <h1 id="hero-heading" className="onboarding-headline">
            A quieter home for your research.
          </h1>
          <p className="onboarding-lead">
            Keep papers from arXiv and your own PDFs together in a private library.
          </p>
          <div className="onboarding-hero-action">
            <button
              type="button"
              onClick={(e) => handleOpenSignIn(e.currentTarget)}
              className="btn btn-primary onboarding-btn-cta"
            >
              Get Started
            </button>
          </div>
        </section>

        {/* Tasteful Library Preview Illustration */}
        <div className="onboarding-illustration-wrap" data-testid="landing-illustration">
          <div className="onboarding-preview-label">A look inside your library</div>
          <div
            className="onboarding-library-preview"
            role="region"
            aria-label="Preview of saved papers in the Researcy library"
          >
            {/* Mock library toolbar */}
            <div className="onboarding-preview-toolbar">
              <div className="onboarding-preview-search">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <span>Search papers by title or author...</span>
              </div>
              <div className="onboarding-preview-add">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                <span>Add paper</span>
              </div>
            </div>

            {/* Mock table header */}
            <div className="onboarding-preview-table-head">
              <span>Paper</span>
              <span>Source</span>
              <span></span>
            </div>

            {/* Mock paper rows */}
            <div className="onboarding-preview-rows">
              <div className="onboarding-preview-row">
                <div className="onboarding-preview-paper-main">
                  <div className="onboarding-preview-cover">A</div>
                  <div className="onboarding-preview-meta-block">
                    <div className="onboarding-preview-title">Attention Is All You Need</div>
                    <div className="onboarding-preview-authors">
                      Ashish Vaswani, Noam Shazeer, Niki Parmar &bull; 2017
                    </div>
                  </div>
                </div>
                <div className="onboarding-preview-source">arXiv</div>
                <div className="onboarding-preview-action">View details</div>
              </div>

              <div className="onboarding-preview-row">
                <div className="onboarding-preview-paper-main">
                  <div className="onboarding-preview-cover">R</div>
                  <div className="onboarding-preview-meta-block">
                    <div className="onboarding-preview-title">
                      Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
                    </div>
                    <div className="onboarding-preview-authors">
                      Patrick Lewis, Ethan Perez, Aleksandra Piktus &bull; 2020
                    </div>
                  </div>
                </div>
                <div className="onboarding-preview-source">Uploaded PDF</div>
                <div className="onboarding-preview-action">View details</div>
              </div>

              <div className="onboarding-preview-row">
                <div className="onboarding-preview-paper-main">
                  <div className="onboarding-preview-cover">D</div>
                  <div className="onboarding-preview-meta-block">
                    <div className="onboarding-preview-title">
                      Dense Passage Retrieval for Open-Domain Question Answering
                    </div>
                    <div className="onboarding-preview-authors">
                      Vladimir Karpukhin, Barlas Oguz, Sewon Min &bull; 2020
                    </div>
                  </div>
                </div>
                <div className="onboarding-preview-source">arXiv</div>
                <div className="onboarding-preview-action">View details</div>
              </div>
            </div>
          </div>
        </div>

        {/* 3-Step Benefits Section */}
        <section
          id="how-it-works"
          className="onboarding-steps-section"
          aria-labelledby="steps-heading"
        >
          <div className="onboarding-steps-container">
            <div className="onboarding-steps-header">
              <h2 id="steps-heading" className="onboarding-steps-title">
                How it works
              </h2>
              <p className="onboarding-steps-lead">
                A calm, focused literature workflow built for rigorous study.
              </p>
            </div>

            <div className="onboarding-steps-grid">
              <div className="onboarding-step-card">
                <span className="onboarding-step-num">01</span>
                <h3 className="onboarding-step-heading">Import papers</h3>
                <p className="onboarding-step-copy">
                  Add papers directly by arXiv identifier or upload your own research PDFs.
                </p>
              </div>

              <div className="onboarding-step-card">
                <span className="onboarding-step-num">02</span>
                <h3 className="onboarding-step-heading">Organize your library</h3>
                <p className="onboarding-step-copy">
                  Keep your saved papers together in one place, with their available titles, authors, and publication years.
                </p>
              </div>

              <div className="onboarding-step-card">
                <span className="onboarding-step-num">03</span>
                <h3 className="onboarding-step-heading">Find what you need</h3>
                <p className="onboarding-step-copy">
                  Quickly search through your papers by title or author whenever you need to revisit them.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="onboarding-footer">
        <p>Researcy &bull; Private research library</p>
      </footer>

      {/* Centered native sign-in dialog */}
      <SignInDialog
        isOpen={isSignInOpen}
        onClose={handleCloseSignIn}
        error={signInError}
        isExpired={signInExpired}
        triggerElement={signInTrigger}
      />
    </div>
  );
}
