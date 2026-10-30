import AppShell from './components/layout/AppShell/AppShell';
import HomePage from './pages/HomePage/HomePage';
import './styles/app.css';
import { BootProvider, BootContent, useBootReport } from './boot/BootProvider';
import { LoanProvider } from './loans/LoanProvider';
import { useAuth } from './auth/AuthProvider';
import { InventoryProvider } from './inventory/InventoryProvider';
import { WalletProvider } from './wallet/WalletProvider';

function Session() {
  const { state, retry } = useAuth();
  useBootReport('auth', state.status === 'loading', state.status === 'error', retry);
  if (state.status !== 'ready') return null;
  return (
    <InventoryProvider><WalletProvider><LoanProvider><BootContent><AppShell><HomePage /></AppShell></BootContent></LoanProvider></WalletProvider></InventoryProvider>
  );
}

export default function App() {
  const { state } = useAuth();
  const sessionKey = state.status === 'ready' ? `${state.mode}:${state.user.id}:${state.accessToken}` : 'auth';
  return <BootProvider key={sessionKey}><Session /></BootProvider>;
}
