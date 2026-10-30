import AppShell from './components/layout/AppShell/AppShell';
import HomePage from './pages/HomePage/HomePage';
import './styles/app.css';
import { useEffect, useState } from 'react';
import LoadingPage from './pages/LoadingPage/LoadingPage';
import { useAuth } from './auth/AuthProvider';
import { InventoryProvider } from './inventory/InventoryProvider';
import { WalletProvider } from './wallet/WalletProvider';

function App() {
  const { state, retry } = useAuth();
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => setLoading(false), 5000);
    return () => window.clearTimeout(timer);
  }, []);
  if (loading || state.status === 'loading') return <LoadingPage />;
  if (state.status === 'error') return <main className="auth-error"><p role="alert">Не удалось войти через Telegram.</p><button type="button" onClick={retry}>Повторить</button></main>;
  return (
    <AppShell>
      <InventoryProvider><WalletProvider><HomePage /></WalletProvider></InventoryProvider>
    </AppShell>
  );
}

export default App;
