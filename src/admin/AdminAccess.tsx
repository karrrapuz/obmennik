import { lazy, Suspense, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import './admin.css';

const AdminPanel = lazy(() => import('./AdminPanel'));
const api = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

export default function AdminAccess() {
  const { state } = useAuth();
  const token = state.status === 'ready' && state.mode === 'telegram' ? state.accessToken : null;
  const [allowed, setAllowed] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setAllowed(false);
    setOpen(false);
    if (!token) return;
    let active = true, done = false, lastAttempt = 0;
    let controller: AbortController | undefined;
    let timeout: number | undefined;
    const check = () => {
      if (!active || done || controller || document.visibilityState !== 'visible' || Date.now() - lastAttempt < 60000) return;
      lastAttempt = Date.now();
      const request = new AbortController();
      controller = request;
      timeout = window.setTimeout(() => request.abort(), 20000);
      fetch(`${api}/api/admin/overview`, {
        headers: { Authorization: `Bearer ${token}` }, signal: request.signal,
        cache: 'no-store', credentials: 'omit', redirect: 'error',
      }).then(async response => {
        if (response.status === 401 || response.status === 403) done = true;
        if (response.ok) {
          const body: unknown = await response.json();
          if (active && !request.signal.aborted && body && typeof body === 'object' && 'read_only' in body && body.read_only === true) {
            setAllowed(true); done = true;
          }
        }
      }).catch(() => {}).finally(() => { window.clearTimeout(timeout); controller = undefined; });
    };
    check();
    const retry = window.setInterval(check, 60000);
    window.addEventListener('focus', check);
    document.addEventListener('visibilitychange', check);
    return () => {
      active = false; controller?.abort(); window.clearTimeout(timeout); window.clearInterval(retry);
      window.removeEventListener('focus', check); document.removeEventListener('visibilitychange', check);
    };
  }, [token]);
  if (!allowed || !token) return null;
  return <>
    <button className="admin-entry" type="button" onClick={() => setOpen(true)}>Администрирование</button>
    {open && <Suspense fallback={<div role="status">Загрузка...</div>}><AdminPanel token={token} onClose={() => setOpen(false)} /></Suspense>}
  </>;
}
