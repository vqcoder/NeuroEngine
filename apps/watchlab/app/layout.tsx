import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AlphaEngine — WatchLab',
  description: 'Study runner with optional webcam capture',
  icons: { icon: '/favicon.svg' }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <header style={{
          position: 'sticky',
          top: 0,
          zIndex: 100,
          background: '#08080a',
          borderBottom: '1px solid #26262f',
          padding: '10px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}>
          <a href="/" style={{ display: 'flex', alignItems: 'center', gap: '10px', textDecoration: 'none' }}>
            <span style={{
              width: 26,
              height: 26,
              background: '#c8f031',
              borderRadius: 5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: 14,
              color: '#08080a',
              flexShrink: 0
            }}>α</span>
            <span style={{
              fontFamily: 'var(--font-body)',
              fontWeight: 700,
              fontSize: '0.95rem',
              letterSpacing: '-0.02em',
              color: '#e8e6e3'
            }}>AlphaEngine</span>
          </a>
        </header>
        {children}
      </body>
    </html>
  );
}
