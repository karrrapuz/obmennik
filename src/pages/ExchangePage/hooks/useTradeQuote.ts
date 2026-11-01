import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../../../auth/AuthProvider';
import { parseSnapshot, useInventory } from '../../../inventory/InventoryProvider';
import { useWallet } from '../../../wallet/WalletProvider';
import { MAX_BALANCE, parseWallet } from '../../../wallet/wallet';
import { parseCombinedRevision } from '../../../services/snapshotRevision';

export type TradeQuote = { id: string; status: 'open' | 'executed'; asset: 'DEMO_TON'; expires_at: number; source: 'sample'; source_version: string; markup_bps: number; offered_nano: string; received_nano: string; wallet_delta_nano: string; required_balance_nano: string; offered: { gift_id: number; catalog_id: number; unit_nano: string }[]; received: { catalog_id: number; unit_nano: string }[] };
const api = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
type Attempt = { key: string; quoteId: string; offered: number[]; received: number[] };
const positiveId = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const validIds = (ids: unknown): ids is number[] => Array.isArray(ids) && ids.length > 0 && ids.length <= 100 && ids.every(positiveId) && new Set(ids).size === ids.length;
const quoteId = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
const unsignedNano = (value: unknown): value is string => typeof value === 'string' && /^(0|[1-9]\d{0,14})$/.test(value) && BigInt(value) <= MAX_BALANCE;
export function readTradeAttempt(user: number | undefined): Attempt | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(`trade-attempt:${user}`) ?? 'null');
    return value && typeof value.key === 'string' && /^[!-~]{1,128}$/.test(value.key) && quoteId(value.quoteId)
      && validIds(value.offered) && validIds(value.received) ? value : null;
  } catch { return null; }
}
export function parseTradeQuote(value: unknown, expected?: { offered: number[]; received: number[] }): TradeQuote {
  const q = value as TradeQuote;
  if (!q || !quoteId(q.id) || !['open', 'executed'].includes(q.status) || q.asset !== 'DEMO_TON' || q.source !== 'sample'
    || typeof q.source_version !== 'string' || !q.source_version.length || q.source_version.length > 256
    || !Number.isSafeInteger(q.expires_at) || q.expires_at <= 0 || q.expires_at > Math.floor(Number.MAX_SAFE_INTEGER / 1000)
    || !Number.isSafeInteger(q.markup_bps) || q.markup_bps < 0 || q.markup_bps > 10000
    || ![q.offered_nano, q.received_nano, q.required_balance_nano].every(unsignedNano)
    || typeof q.wallet_delta_nano !== 'string' || !/^(0|-?[1-9]\d{0,14})$/.test(q.wallet_delta_nano)
    || !unsignedNano(q.wallet_delta_nano.replace(/^-/, ''))
    || ![q.offered, q.received].every(items => Array.isArray(items) && items.length > 0 && items.length <= 100
      && items.every(item => item && positiveId(item.catalog_id) && unsignedNano(item.unit_nano) && BigInt(item.unit_nano) > 0n))
    || !validIds(q.offered.map(item => item.gift_id)) || !validIds(q.received.map(item => item.catalog_id))) throw new Error('Invalid trade quote');
  const offeredTotal = q.offered.reduce((sum, item) => sum + BigInt(item.unit_nano), 0n);
  const receivedTotal = q.received.reduce((sum, item) => sum + BigInt(item.unit_nano), 0n);
  const delta = offeredTotal - receivedTotal;
  const sameIds = (actual: number[], wanted: number[]) => actual.length === wanted.length && actual.every(id => wanted.includes(id));
  if (offeredTotal !== BigInt(q.offered_nano) || receivedTotal !== BigInt(q.received_nano)
    || delta !== BigInt(q.wallet_delta_nano) || BigInt(q.required_balance_nano) !== (delta < 0n ? -delta : 0n)
    || (expected && (!sameIds(q.offered.map(item => item.gift_id), expected.offered) || !sameIds(q.received.map(item => item.catalog_id), expected.received)))) throw new Error('Inconsistent trade quote');
  return q;
}
export function useTradeQuote(offered: number[], received: number[]) {
  const { state } = useAuth();
  const inventory = useInventory();
  const wallet = useWallet();
  const server = state.status === 'ready' && state.mode !== 'demo';
  const token = state.status === 'ready' ? state.accessToken : null;
  const userId = state.status === 'ready' ? state.user.id : undefined;
  const storageKey = `trade-attempt:${userId}`;
  const [savedQuote, setQuote] = useState<TradeQuote | null>(null);
  const [quotedSignature, setQuotedSignature] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [uncertain, setUncertain] = useState(() => server && Boolean(readTradeAttempt(state.status === 'ready' ? state.user.id : undefined)));
  const [version, refresh] = useState(0);
  const refreshQuote = useCallback(() => refresh(value => value + 1), []);
  const retries = useRef({ signature: '', failures: 0 });
  const attempt = useRef<Attempt | null>(server ? readTradeAttempt(state.status === 'ready' ? state.user.id : undefined) : null);
  const busy = useRef(false);
  const session = useRef({ generation: 0, active: false, identity: '' });
  const sessionIdentity = state.status === 'ready' ? `${state.mode}:${state.user.id}:${token}` : state.status;
  useLayoutEffect(() => {
    if (session.current.identity && session.current.identity !== sessionIdentity) {
      attempt.current = server ? readTradeAttempt(userId) : null;
      busy.current = false;
      setQuote(null); setQuotedSignature(''); setError(''); setPending(false); setLoading(false); setUncertain(Boolean(attempt.current));
    }
    session.current = { generation: session.current.generation + 1, active: true, identity: sessionIdentity };
    return () => { session.current = { generation: session.current.generation + 1, active: false, identity: sessionIdentity }; };
  }, [sessionIdentity, server, userId]);
  const signature = JSON.stringify([offered, received]);
  const blocked = received.some(id => inventory.catalog.some(gift => gift.id === id && gift.blockTradeGift));
  const quote = quotedSignature === signature ? savedQuote : null;
  useEffect(() => {
    const saved = attempt.current;
    if (!server || !saved) return;
    let active = true;
    const generation = session.current.generation;
    void fetch(`${api}/api/trades/quotes/${encodeURIComponent(saved.quoteId)}`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(20000) })
      .then(async response => { if (!response.ok) return; const next = parseTradeQuote(await response.json(), saved); if (active && session.current.active && session.current.generation === generation) { setQuote(next); setQuotedSignature(JSON.stringify([saved.offered, saved.received])); } }).catch(() => {});
    return () => { active = false; };
  }, [server, token]);
  useEffect(() => {
    if (!server || attempt.current) return;
    setQuote(null); setError('');
    const [offer, receive] = JSON.parse(signature) as number[][];
    if (!validIds(offer) || !validIds(receive) || blocked) { setLoading(false); return; }
    if (retries.current.signature !== signature) retries.current = { signature, failures: 0 };
    let active = true;
    const generation = session.current.generation;
    const isCurrent = () => active && session.current.active && session.current.generation === generation;
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    setLoading(true);
    const timer = setTimeout(async () => {
      let retryable = true;
      try {
        const response = await fetch(`${api}/api/trades/quote`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ offered_ids: offer, received_ids: receive }), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) });
        retryable = response.status >= 500 || response.status === 408 || response.status === 429;
        if (!response.ok) throw new Error('Не удалось получить котировку.');
        const next = parseTradeQuote(await response.json(), { offered: offer, received: receive });
        if (isCurrent()) { setQuote(next); setQuotedSignature(signature); retries.current.failures = 0; }
      } catch {
        if (isCurrent()) {
          setError('Не удалось получить котировку. Повторите обновление.');
          if (retryable && !document.hidden && retries.current.failures < 2) {
            retries.current.failures++;
            retryTimer = setTimeout(refreshQuote, retries.current.failures * 1500);
          }
        }
      }
      finally { if (isCurrent()) setLoading(false); }
    }, 200);
    return () => { active = false; clearTimeout(timer); clearTimeout(retryTimer); controller.abort(); };
  }, [signature, server, token, version, blocked, refreshQuote]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { if (!server) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [server]);
  const expired = Boolean(quote && quote.expires_at * 1000 <= now);
  useEffect(() => {
    if (expired && !document.hidden && !attempt.current) refreshQuote();
  }, [expired, refreshQuote]);
  useEffect(() => {
    const resume = () => {
      if (!document.hidden && server && !attempt.current && quote && quote.expires_at * 1000 <= Date.now()) refreshQuote();
    };
    document.addEventListener('visibilitychange', resume);
    return () => document.removeEventListener('visibilitychange', resume);
  }, [server, quote, refreshQuote]);
  const execute = async () => {
    const generation = session.current.generation;
    const isCurrent = () => session.current.active && session.current.identity === sessionIdentity && session.current.generation === generation;
    if (!server || !isCurrent()) throw new Error('Trade session changed');
    if (busy.current) throw new Error('Trade pending');
    if (!attempt.current && (!quote || quote.expires_at * 1000 <= Date.now() || !wallet.available || BigInt(quote.required_balance_nano) > BigInt(wallet.wallet.balance_nano))) throw new Error('Quote unavailable');
    busy.current = true; setPending(true); setError('');
    let persistenceFailed = false;
    const clearAttempt = () => {
      attempt.current = null;
      // A leftover persisted ID is safe to replay; storage cleanup must not undo a known outcome.
      try { sessionStorage.removeItem(storageKey); } catch { /* Storage can be disabled during a request. */ }
      setUncertain(false);
    };
    try {
      if (!attempt.current) {
        const nextAttempt = { key: crypto.randomUUID(), quoteId: quote!.id, offered: [...offered], received: [...received] };
        try { sessionStorage.setItem(storageKey, JSON.stringify(nextAttempt)); }
        catch (cause) { persistenceFailed = true; throw cause; }
        attempt.current = nextAttempt;
      }
      const submitted = attempt.current;
      const response = await fetch(`${api}/api/trades/execute`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': submitted.key }, body: JSON.stringify({ quote_id: submitted.quoteId }), signal: AbortSignal.timeout(20000) });
      if (!isCurrent()) throw new Error('Trade session changed');
      if (!response.ok) {
        if (response.status < 500 && ![408, 429].includes(response.status)) {
          clearAttempt(); setQuote(null); refresh(v => v + 1);
          void inventory.reload().catch(() => {}); void wallet.reload().catch(() => {});
        }
        throw new Error('Trade failed');
      }
      const result = await response.json();
      if (!isCurrent()) throw new Error('Trade session changed');
      const nextInventory = parseSnapshot(result.inventory);
      const nextWallet = parseWallet(result.wallet);
      const revision = parseCombinedRevision(result.revision, nextWallet.revision, nextInventory.revision);
      const executed = parseTradeQuote(result.quote, submitted);
      if (executed.id !== submitted.quoteId || executed.status !== 'executed') throw new Error('Invalid execution');
      if (revision >= Math.max(wallet.getRevision(), inventory.getRevision())) { inventory.applySnapshot(nextInventory); wallet.applySnapshot(nextWallet); }
      else { void inventory.reload().catch(() => {}); void wallet.reload().catch(() => {}); }
      clearAttempt(); setQuote(null);
    } catch (cause) {
      if (isCurrent()) {
        setUncertain(Boolean(attempt.current));
        setError(persistenceFailed ? 'Не удалось сохранить попытку. Обмен не отправлен. Разрешите хранилище и повторите.' : attempt.current ? 'Ответ не подтверждён. Повторите тот же обмен; выбор сохранён.' : 'Обмен отклонён. Обновите котировку.');
      }
      throw cause;
    } finally { if (isCurrent()) { busy.current = false; setPending(false); } }
  };
  return { server, quote, loading, error, pending, uncertain, locked: pending || uncertain, expired, refresh: refreshQuote, execute,
    canExecute: Boolean(quote && !expired && !loading && wallet.available && BigInt(quote.required_balance_nano) <= BigInt(wallet.wallet.balance_nano)) };
}
