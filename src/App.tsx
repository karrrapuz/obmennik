import AppShell from './components/layout/AppShell/AppShell';
import HomePage from './pages/HomePage/HomePage';
import './styles/app.css';
import { useEffect, useState } from 'react';
import LoadingPage from './pages/LoadingPage/LoadingPage';

function App() {
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => setLoading(false), 5000);
    return () => window.clearTimeout(timer);
  }, []);
  if (loading) return <LoadingPage />;
  return (
    <AppShell>
      <HomePage />
    </AppShell>
  );
}

export default App;
