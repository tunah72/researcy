import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Researcy - Scholarly Library',
  description: 'Private scholarly library and paper import workspace.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
