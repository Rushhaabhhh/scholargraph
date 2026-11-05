import type { Metadata } from 'next';
import './styles.css';
export const metadata: Metadata = { title: 'HireSense | Expert discovery', description: 'Find research expertise with evidence from DBLP.' };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }
