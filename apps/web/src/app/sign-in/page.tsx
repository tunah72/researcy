'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import '../onboarding.css';
import { LandingView } from '@/components/landing-view';

function SignInContent() {
  const searchParams = useSearchParams();
  const errorParam = searchParams.get('error');
  const isExpired = searchParams.get('expired') === '1' || errorParam === 'expired';

  // Safe user-friendly error without raw error codes or developer jargon
  const safeError = errorParam && !isExpired ? 'Could not sign in' : null;

  return (
    <LandingView
      initialSignInOpen={true}
      signInError={safeError}
      signInExpired={isExpired}
    />
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={<LandingView initialSignInOpen={true} />}>
      <SignInContent />
    </Suspense>
  );
}
