import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { getTelegramInitData, isTelegramContext } from '../services/telegram';

export type User = {
  id: number;
  first_name: string;
  last_name: string | null;
  username: string | null;
  photo_url: string | null;
  referral_code: string;
};

type Session = { user: User; accessToken: string | null; mode: 'telegram' | 'demo' };
type AuthState = { status: 'loading' } | { status: 'error' } | ({ status: 'ready' } & Session);
const demoSession: Session = {
  mode: 'demo', accessToken: null,
  user: { id: 0, first_name: 'Гость', last_name: null, username: 'demo', photo_url: null, referral_code: 'demo' },
};
const apiUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
let initialSession: Promise<Session> | undefined;

async function request(path: string, options: RequestInit): Promise<unknown> {
  const response = await fetch(`${apiUrl}${path}`, { ...options, signal: AbortSignal.timeout(20000) });
  if (!response.ok) throw new Error('Authentication failed');
  return response.json();
}

function isUser(value: unknown): value is User {
  if (!value || typeof value !== 'object') return false;
  const user = value as Record<string, unknown>;
  return typeof user.id === 'number' && typeof user.first_name === 'string'
    && typeof user.referral_code === 'string'
    && ['last_name', 'username', 'photo_url'].every((key) => user[key] === null || typeof user[key] === 'string');
}

async function authenticate(): Promise<Session> {
  const initData = getTelegramInitData();
  if (!initData) {
    if (isTelegramContext()) throw new Error('Missing Telegram initialization data');
    return demoSession;
  }
  const health = await fetch(`${apiUrl}/api/health`, { signal: AbortSignal.timeout(90000) });
  if (!health.ok) throw new Error('Service unavailable');
  const result = await request('/api/auth/telegram', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  }) as { access_token?: unknown; token_type?: unknown; user?: unknown } | null;
  if (!result || typeof result.access_token !== 'string' || !result.access_token
    || result.token_type !== 'bearer' || !isUser(result.user)) throw new Error('Invalid authentication response');
  const user = await request('/api/me', { headers: { Authorization: `Bearer ${result.access_token}` } });
  if (!isUser(user)) throw new Error('Invalid user response');
  return { mode: 'telegram', accessToken: result.access_token, user };
}

const AuthContext = createContext<{ state: AuthState; retry: () => void } | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    // Share the same promise during StrictMode's effect replay, including failures.
    initialSession ??= authenticate();
    initialSession.then(
      (session) => { if (active) setState({ status: 'ready', ...session }); },
      () => { if (active) setState({ status: 'error' }); },
    );
    return () => { active = false; };
  }, [attempt]);
  const retry = useCallback(() => {
    initialSession = undefined;
    setState({ status: 'loading' });
    setAttempt((value) => value + 1);
  }, []);
  const value = useMemo(() => ({ state, retry }), [state, retry]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('AuthProvider is required');
  return context;
}

export function useUser() {
  const { state } = useAuth();
  if (state.status !== 'ready') throw new Error('User is not ready');
  return state.user;
}

export function displayName(user: User) {
  return [user.first_name, user.last_name].filter(Boolean).join(' ').trim() || user.username || 'Гость';
}
