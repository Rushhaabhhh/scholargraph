import type { ReactNode } from 'react';

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <div className="app-main app-main-full">
        <div className="page-content">{children}</div>
      </div>
    </div>
  );
}
