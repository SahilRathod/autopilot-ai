import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Autopilot AI | Creator Studio',
  description: 'Local-first multi-channel production management',
};

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
