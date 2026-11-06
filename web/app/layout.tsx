import type { Metadata } from 'next';
import './styles.css';
import './voice.css';
import './editorial.css';
import '@fontsource/inter/400.css';
import '@fontsource/inter/700.css';
import '@fontsource/inter/900.css';
import '@fontsource/ibm-plex-mono/400.css';
export const metadata: Metadata = { title: 'ScholarGraph | Research intelligence', description: 'Discover research expertise through ranked, publication-backed evidence.' };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }
