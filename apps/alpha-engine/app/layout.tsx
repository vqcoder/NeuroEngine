import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AlphaEngine — The AI-Native Marketing Stack for Customer Growth',
  description:
    'AlphaEngine connects product, marketing, service, sales, research, and media into shared memory, contextual action, and measurable growth.',
  icons: {
    icon: '/favicon.svg',
  },
  openGraph: {
    title: 'AlphaEngine — Two Growth Problems. One System.',
    description:
      'The AI-native marketing stack that helps companies grow the customers they have and acquire the right new ones.',
    siteName: 'AlphaEngine',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="site-header-inner">
            <a href="/" className="site-logo">
              <span className="site-logo-mark">α</span>
              <span className="site-logo-text">AlphaEngine</span>
            </a>
            <nav className="site-nav">
              <a href="#how-it-works" className="site-nav-link">How It Works</a>
              <a href="#results" className="site-nav-link">Results</a>
              <a href="#pilot" className="site-nav-cta">Request a Pilot</a>
            </nav>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
