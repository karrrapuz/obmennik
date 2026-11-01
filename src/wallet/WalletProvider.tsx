import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { useBootReport } from '../boot/BootProvider';
import { createRevisionGate } from '../services/snapshotRevision';
import { applyLocalWallet, localWalletKey, parseWallet, readLocalWallet, type WalletAction, type WalletSnapshot } from './wallet';

type Value = { getRevision: () => number; applySnapshot: (next: WalletSnapshot) => void; wallet: WalletSnapshot; pending: boolean; error: string | null; available: boolean; reload: () => Promise<void>; operate: (action: WalletAction, body?: Record<string, string>) => Promise<void> };
const Context = createContext<Value | null>(null);
const apiUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

export function WalletProvider({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status !== 'ready') return null;
  return <WalletSession key={`${state.mode}:${state.user.id}:${state.accessToken}`} token={state.accessToken} demo={state.mode === 'demo'}>{children}</WalletSession>;
}

function WalletSession({ token, demo, children }: { token: string | null; demo: boolean; children: ReactNode }) {
  const { retry } = useAuth();
  const [wallet, setWallet] = useState<WalletSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [pending, setPending] = useState(false);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const uncertain = useRef(new Map<string, string>());
  const generation = useRef(0);
  const alive = useRef(false);
  const controllers = useRef(new Set<AbortController>());
  const [revision] = useState(createRevisionGate);
  const applySnapshot = useCallback((raw: WalletSnapshot) => {
    const next = parseWallet(raw);
    if (!alive.current || !revision.accept(next.revision)) return;
    setWallet(next); setError(null);
  }, [revision]);
  const enqueue = useCallback((operation: () => Promise<void>) => {
    const version = generation.current;
    const next = queue.current.then(() => { if (!alive.current || version !== generation.current) throw new Error('Wallet session changed'); return operation(); });
    queue.current = next.catch(() => {});
    return next;
  }, []);
  const request = useCallback(async (path: string, options: RequestInit = {}) => {
    const controller = new AbortController();
    controllers.current.add(controller);
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`${apiUrl}/api/wallet${path}`, { ...options, headers: { Authorization: `Bearer ${token}`, ...options.headers }, signal: controller.signal });
      return { ok: response.ok, status: response.status, body: response.ok ? await response.json() as unknown : null };
    }
    finally { clearTimeout(timer); controllers.current.delete(controller); }
  }, [token]);
  const reload = useCallback(() => enqueue(async () => {
    const version = generation.current;
    try {
      let next: WalletSnapshot;
      if (demo) next = readLocalWallet();
      else {
        const response = await request('');
        if (response.status === 401) { if (alive.current && version === generation.current) setExpired(true); throw new Error('Сессия истекла. Войдите снова.'); }
        if (!response.ok) throw new Error('Не удалось обновить баланс.');
        next = parseWallet(response.body);
      }
      if (alive.current && version === generation.current) applySnapshot(next);
    } catch (cause) {
      if (alive.current && version === generation.current) setError(cause instanceof Error ? cause.message : 'Не удалось обновить баланс.');
      throw cause;
    }
  }), [applySnapshot, demo, enqueue, request]);
  const operate = useCallback((action: WalletAction, body: Record<string, string> = {}) => {
    const payload = JSON.stringify(body, Object.keys(body).sort());
    const signature = `${action}:${payload}`;
    return enqueue(async () => {
      if (expired) throw new Error('Сессия истекла. Войдите снова.');
      const version = generation.current;
      setPending(true);
      try {
        let next: WalletSnapshot;
        if (demo) {
          next = applyLocalWallet(readLocalWallet(), action, JSON.parse(payload));
          localStorage.setItem(localWalletKey, JSON.stringify(next));
        } else {
          const key = uncertain.current.get(signature) ?? crypto.randomUUID();
          uncertain.current.set(signature, key);
          const response = await request(`/demo-${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: payload });
          if (!response.ok) {
            if (response.status < 500 && response.status !== 408) uncertain.current.delete(signature);
            if (response.status === 401 && alive.current && version === generation.current) setExpired(true);
            throw new Error(response.status === 401 ? 'Сессия истекла. Войдите снова.' : 'Операция не выполнена. Обновите баланс и повторите.');
          }
          next = parseWallet(response.body);
          uncertain.current.delete(signature);
        }
        if (!alive.current || version !== generation.current) throw new Error('Wallet session changed');
        applySnapshot(next);
      } catch (cause) {
        if (alive.current && version === generation.current) {
          setError('Не удалось подтвердить операцию.');
          void reload().catch(() => {});
        }
        throw cause;
      } finally { if (alive.current && version === generation.current) setPending(false); }
    });
  }, [applySnapshot, demo, enqueue, expired, reload, request]);
  useEffect(() => {
    alive.current = true;
    const refresh = () => { void reload().catch(() => {}); };
    const storage = (event: StorageEvent) => { if (demo && (!event.key || event.key === localWalletKey)) refresh(); };
    refresh(); window.addEventListener('focus', refresh); window.addEventListener('storage', storage);
    return () => { alive.current = false; generation.current++; controllers.current.forEach((controller) => controller.abort()); controllers.current.clear(); window.removeEventListener('focus', refresh); window.removeEventListener('storage', storage); };
  }, [demo, reload]);
  const bootRetry = useCallback(() => { if (expired) retry(); else void reload().catch(() => {}); }, [expired, retry, reload]);
  useBootReport('wallet', !wallet, Boolean((!wallet && error) || expired), bootRetry);
  const value = useMemo(() => ({ getRevision: revision.current, applySnapshot, wallet: wallet ?? { revision: 0, asset: 'DEMO_TON' as const, balance_nano: '0', referral_nano: '0', transactions: [] }, pending, error, available: Boolean(wallet) && !expired && !error, reload, operate }), [revision, applySnapshot, wallet, pending, error, expired, reload, operate]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useWallet() { const value = useContext(Context); if (!value) throw new Error('WalletProvider is required'); return value; }
