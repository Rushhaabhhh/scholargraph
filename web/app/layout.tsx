import type { Metadata } from 'next';
import './styles.css';
import './voice.css';
export const metadata: Metadata = { title: 'ScholarGraph | Research intelligence', description: 'Discover research expertise through ranked, publication-backed evidence.' };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }
