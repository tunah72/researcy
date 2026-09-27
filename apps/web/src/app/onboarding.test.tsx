import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LandingPage from './page';
import SignInPage from './sign-in/page';

let mockSearchParams = new URLSearchParams();
const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

describe('Onboarding and Sign-In Experience', () => {
  const originalLocation = window.location;

  beforeAll(() => {
    // jsdom does not implement native HTMLDialogElement showModal / close
    if (typeof HTMLDialogElement !== 'undefined') {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.open = true;
      };
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.open = false;
        this.dispatchEvent(new Event('close'));
      };
    }
  });

  beforeEach(() => {
    vi.restoreAllMocks();
    mockSearchParams = new URLSearchParams();
    mockPush.mockReset();

    Object.defineProperty(window, 'location', {
      writable: true,
      configurable: true,
      value: {
        href: 'http://localhost:3000/',
        assign: vi.fn(),
        replace: vi.fn(),
      },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  describe('Sign-In Modal Dialog Interaction', () => {
    it('dialog is not open initially on landing page', () => {
      render(<LandingPage />);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('opens native dialog when Get Started is clicked and restores focus on close', async () => {
      const user = userEvent.setup();
      render(<LandingPage />);

      const getStartedBtn = screen.getByRole('button', { name: /get started/i });
      getStartedBtn.focus();
      expect(document.activeElement).toBe(getStartedBtn);

      await user.click(getStartedBtn);

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveAttribute('aria-labelledby');

      const closeBtn = screen.getByRole('button', { name: /close|back/i });
      await user.click(closeBtn);

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(document.activeElement).toBe(getStartedBtn);
    });

    it('opens dialog from header Sign In button and closes via Escape with focus restored', async () => {
      render(<LandingPage />);

      const headerSignIn = screen.getByRole('button', { name: /sign in/i });
      headerSignIn.focus();
      expect(document.activeElement).toBe(headerSignIn);

      fireEvent.click(headerSignIn);

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();

      // Trigger cancel event on native dialog (Escape key behavior in browser)
      fireEvent(dialog, new Event('cancel', { cancelable: true }));

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(document.activeElement).toBe(headerSignIn);
    });

    it('does not navigate before explicit Google click, then directs same tab to /auth/google/start', async () => {
      const user = userEvent.setup();
      render(<LandingPage />);

      const getStartedBtn = screen.getByRole('button', { name: /get started/i });
      await user.click(getStartedBtn);

      expect(window.location.href).toBe('http://localhost:3000/');

      const googleBtn = screen.getByRole('button', { name: /continue with google/i });
      await user.click(googleBtn);

      expect(window.location.href).toBe('/auth/google/start');
      expect(screen.getByText(/connecting to google/i)).toBeInTheDocument();
    });

    it('resets redirecting state on bfcache pageshow restore', async () => {
      const user = userEvent.setup();
      render(<LandingPage />);

      const getStartedBtn = screen.getByRole('button', { name: /get started/i });
      await user.click(getStartedBtn);

      const googleBtn = screen.getByRole('button', { name: /continue with google/i });
      await user.click(googleBtn);
      expect(screen.getByText(/connecting to google/i)).toBeInTheDocument();

      // Simulate bfcache back navigation
      act(() => {
        const pageShowEvent = new PageTransitionEvent('pageshow', { persisted: true });
        window.dispatchEvent(pageShowEvent);
      });

      expect(screen.getByRole('button', { name: /continue with google/i })).toBeInTheDocument();
      expect(screen.queryByText(/connecting to google/i)).not.toBeInTheDocument();
    });
  });

  describe('Direct /sign-in Entry and Error Handling', () => {
    it('opens dialog automatically in landing context on /sign-in', () => {
      render(<SignInPage />);
      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
    });

    it('displays expired session alert when ?expired=1 or ?error=expired', () => {
      mockSearchParams = new URLSearchParams('expired=1');
      render(<SignInPage />);

      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert.textContent).toMatch(/please sign in again/i);
    });

    it('displays safe friendly authentication error without developer jargon when ?error=oauth_failed', () => {
      mockSearchParams = new URLSearchParams('error=oauth_failed');
      render(<SignInPage />);

      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert.textContent).toMatch(/could not sign in/i);
      // Must not contain developer jargon, stack traces, or raw error codes
      expect(alert.textContent).not.toMatch(/oauth_failed|uuid|job_id|trace/i);
    });
  });
});
