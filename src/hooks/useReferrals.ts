import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { useWallet } from '../wallet/WalletProvider';
import { MAX_BALANCE, parseWallet } from '../wallet/wallet';

type Summary = { asset: 'DEMO_TON'; invited_count: number; turnover_nano: string; earned_nano: string; available_nano: string; held_nano: string; rate_bps: number; invite_url: string | null };
const apiUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

export function parseReferralSummary(raw: unknown): Summary {
  if (!raw || typeof raw !== 'object') throw new Error('Invalid referrals');
  const value = raw as Summary;
  if (value.asset !== 'DEMO_TON' || !Number.isSafeInteger(value.invited_count) || value.invited_count < 0
    || !Number.isInteger(value.rate_bps) || value.rate_bps < 0 || value.rate_bps > 10000
    || !['turnover_nano', 'earned_nano', 'available_nano', 'held_nano'].every(key => {
      const amount = (raw as Record<string, unknown>)[key];
      return typeof amount === 'string' && /^(0|[1-9]\d{0,29})$/.test(amount)
        && (key !== 'available_nano' || BigInt(amount) <= MAX_BALANCE);
    }) || (value.invite_url !== null && (typeof value.invite_url !== 'string'
      || !/^https:\/\/t\.me\/[A-Za-z][A-Za-z0-9_]{4,31}\?startapp=ref_[A-Za-z0-9_-]{1,60}$/.test(value.invite_url)))) throw new Error('Invalid referrals');
  return value;
}

export function readReferralClaimKey(storageKey: string): string {
  const stored = localStorage.getItem(storageKey);
  if (stored && stored.length <= 128 && /^[!-~]+$/.test(stored)) return stored;
  const key = crypto.randomUUID();
  localStorage.setItem(storageKey, key);
  return key;
}

export function useReferrals() {
  const { state } = useAuth();
  const { applySnapshot } = useWallet();
  const session = state.status === 'ready' && state.mode !== 'demo' && state.accessToken
    ? { id: state.user.id, token: state.accessToken } : null;
  const identity = session ? `${session.id}:${session.token}` : '';
  const current = useRef(identity);
  useLayoutEffect(() => { current.current = identity; }, [identity]);
  const alive = useRef(false);
  const busy = useRef(false);
  const sequence = useRef(0);
  const [data, setData] = useState<{ identity: string; summary: Summary } | null>(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const token = session?.token;
  const userId = session?.id;
  const refresh = useCallback(async () => {
    if (!token) return;
    const version = ++sequence.current;
    try {
      const response = await fetch(`${apiUrl}/api/referrals`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(20000), cache: 'no-store' });
      if (!response.ok) throw new Error('Referrals unavailable');
      const summary = parseReferralSummary(await response.json());
      if (alive.current && current.current === identity && version === sequence.current) { setData({ identity, summary }); setError(''); }
    } catch {
      if (alive.current && current.current === identity && version === sequence.current) { setData(null); setError('Не удалось обновить реферальные данные.'); }
    }
  }, [identity, token]);
  useEffect(() => {
    alive.current = true;
    busy.current = false; setPending(false); setData(null); setError('');
    const visibleRefresh = () => { if (document.visibilityState === 'visible') void refresh(); };
    void refresh();
    const timer = window.setInterval(visibleRefresh, 60000);
    window.addEventListener('focus', visibleRefresh);
    document.addEventListener('visibilitychange', visibleRefresh);
    return () => { alive.current = false; sequence.current++; clearInterval(timer); window.removeEventListener('focus', visibleRefresh); document.removeEventListener('visibilitychange', visibleRefresh); };
  }, [refresh]);
  const claim = useCallback(async () => {
    if (!token || userId === undefined || busy.current) return;
    busy.current = true; setPending(true); setError('');
    const storageKey = `referral-claim-v1:${userId}`;
    try {
      // Persist before sending: timeouts, malformed responses and reloads reuse this key.
      const key = readReferralClaimKey(storageKey);
      sequence.current++;
      const response = await fetch(`${apiUrl}/api/referrals/claim`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: '{}', signal: AbortSignal.timeout(20000) });
      if (!response.ok) throw new Error('Claim unavailable');
      const raw: unknown = await response.json();
      if (!raw || typeof raw !== 'object') throw new Error('Invalid claim');
      const result = raw as Record<string, unknown>;
      const wallet = parseWallet(result.wallet);
      const summary = parseReferralSummary(result.referral);
      if (!alive.current || current.current !== identity) return;
      sequence.current++;
      applySnapshot(wallet);
      setData({ identity, summary });
      localStorage.removeItem(storageKey);
      void refresh();
    } catch {
      if (alive.current && current.current === identity) setError('Не удалось подтвердить награду. Повторите попытку.');
    } finally {
      if (alive.current && current.current === identity) { busy.current = false; setPending(false); }
    }
  }, [applySnapshot, identity, refresh, token, userId]);
  return { summary: data?.identity === identity ? data.summary : null, pending, error, refresh, claim, demo: state.status === 'ready' && state.mode === 'demo' };
}
