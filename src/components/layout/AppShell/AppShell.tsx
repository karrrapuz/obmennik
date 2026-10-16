import type { ReactNode } from 'react';
import './AppShell.css';

type AppShellProps = {
  children: ReactNode;
};

function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <main className="app-shell__main">{children}</main>
    </div>
  );
}

export default AppShell;
