import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { gifts, inventoryGifts, type Gift } from '../pages/ExchangePage/data/gifts';
import { pledgeStore } from '../pages/DepositPage/services/pledgeStore';

type Snapshot = { inventory: Gift[]; pledged: Gift[]; catalog: Gift[] };
type Action = 'deposit' | 'withdraw' | 'exchange' | 'pledge' | 'release';
type Value = Snapshot & { loading: boolean; error: boolean; reload: () => Promise<void>; mutate: (action: Action, body?: Record<string, unknown>) => Promise<void> };
const Context = createContext<Value | null>(null);
const empty: Snapshot = { inventory: [], pledged: [], catalog: [] };
const localKey = 'demo-inventory-v1';
const apiUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

function parseSnapshot(value: unknown): Snapshot {
  const snapshot = value as Snapshot;
  if (!snapshot || !['inventory', 'pledged', 'catalog'].every((key) =>
    Array.isArray(snapshot[key as keyof Snapshot]) && snapshot[key as keyof Snapshot].every((gift) =>
      typeof gift.id === 'number' && typeof gift.name === 'string' && typeof gift.model === 'string' && Number.isFinite(Number(gift.price))))) throw new Error('Invalid inventory snapshot');
  const owned = new Set<number>();
  for (const gift of [...snapshot.inventory, ...snapshot.pledged]) {
    if (owned.has(gift.id)) throw new Error('Duplicate inventory gift');
    owned.add(gift.id);
  }
  return snapshot;
}
function readLocal(): Snapshot {
  const saved = localStorage.getItem(localKey);
  return saved ? parseSnapshot(JSON.parse(saved)) : { inventory: inventoryGifts.slice(0, 5), pledged: [], catalog: gifts };
}
function localMutation(snapshot: Snapshot, action: Action, body: Record<string, unknown>): Snapshot {
  let nextId = Math.max(Date.now() * 1000, ...snapshot.inventory.map((gift) => gift.id), ...snapshot.pledged.map((gift) => gift.id)) + 1;
  const offered = new Set(body.offered_ids as number[]); const received = new Set(body.received_ids as number[]); const withdrawn = new Set(body.ids as number[]);
  const find = (list: Gift[], id: unknown) => { const gift = list.find((item) => item.id === id); if (!gift) throw new Error('Gift unavailable'); return gift; };
  if (action === 'deposit') {
    return { ...snapshot, inventory: [...snapshot.inventory, { ...gifts[1], id: nextId++, pledgeSupported: true, blockTradeGift: false }] };
  }
  if (action === 'withdraw') {
    withdrawn.forEach((id) => find(snapshot.inventory, id));
    return { ...snapshot, inventory: snapshot.inventory.filter((gift) => !withdrawn.has(gift.id)) };
  }
  if (action === 'exchange') {
    const offer = [...offered].map((id) => find(snapshot.inventory, id)); const receive = [...received].map((id) => find(snapshot.catalog, id));
    if (!offer.length || !receive.length || receive.some((gift) => gift.blockTradeGift) || offer.reduce((sum, gift) => sum + Number(gift.price), 0) + 0.000001 < receive.reduce((sum, gift) => sum + Number(gift.price), 0)) throw new Error('Invalid exchange');
    return { ...snapshot, inventory: [...snapshot.inventory.filter((gift) => !offered.has(gift.id)), ...receive.map((gift) => ({ ...gift, id: nextId++, pledgeSupported: true, blockTradeGift: false }))] };
  }
  const reserving = action === 'pledge'; const gift = find(reserving ? snapshot.inventory : snapshot.pledged, body.id);
  if (reserving && gift.pledgeSupported === false) throw new Error('Gift unsupported');
  return { ...snapshot, inventory: reserving ? snapshot.inventory.filter((item) => item.id !== gift.id) : [...snapshot.inventory, gift], pledged: reserving ? [...snapshot.pledged, gift] : snapshot.pledged.filter((item) => item.id !== gift.id) };
}

export function InventoryProvider({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const token = state.status === 'ready' ? state.accessToken : null;
  const demo = state.status === 'ready' && state.mode === 'demo';
  const [snapshot, setSnapshot] = useState(empty); const [loading, setLoading] = useState(true); const [error, setError] = useState(false);
  const queue = useRef<Promise<unknown>>(Promise.resolve()); const alive = useRef(false);
  const uncertainActions = useRef(new Map<string, string>());
  const enqueue = useCallback((operation: () => Promise<void>) => { const next = queue.current.then(operation); queue.current = next.catch(() => {}); return next; }, []);
  const commit = useCallback((next: Snapshot) => { if (!alive.current) return; pledgeStore.syncInventory(next.inventory, next.pledged); setSnapshot(next); setError(false); }, []);
  const reload = useCallback(() => enqueue(async () => {
    try {
      if (demo) commit(readLocal());
      else {
        const response = await fetch(`${apiUrl}/api/inventory`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(20000) });
        if (!response.ok) throw new Error('Inventory unavailable');
        commit(parseSnapshot(await response.json()));
      }
    } catch (cause) { if (alive.current) setError(true); throw cause; }
    finally { if (alive.current) setLoading(false); }
  }), [commit, demo, enqueue, token]);
  const mutate = useCallback((action: Action, body: Record<string, unknown> = {}) => {
    const payload = JSON.stringify(body, Object.keys(body).sort());
    const signature = `${action}:${payload}`;
    return enqueue(async () => {
      if (demo) {
        const next = parseSnapshot(localMutation(readLocal(), action, body)); localStorage.setItem(localKey, JSON.stringify(next)); commit(next);
      } else {
        const key = uncertainActions.current.get(signature) ?? crypto.randomUUID();
        uncertainActions.current.set(signature, key);
        try {
          const response = await fetch(`${apiUrl}/api/inventory/demo-${action}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: payload, signal: AbortSignal.timeout(20000) });
          if (!response.ok) {
            if (response.status < 500 && response.status !== 408) uncertainActions.current.delete(signature);
            throw new Error('Inventory action failed');
          }
          commit(parseSnapshot(await response.json()));
          uncertainActions.current.delete(signature);
        } catch (cause) {
          // Reconcile after uncertainty; only an explicit user action resends the mutation.
          void reload().catch(() => {});
          throw cause;
        }
      }
    });
  }, [commit, demo, enqueue, reload, token]);
  useEffect(() => {
    alive.current = true;
    const refresh = () => { void reload().catch(() => {}); }; refresh();
    window.addEventListener('focus', refresh); window.addEventListener('storage', refresh);
    const disconnect = pledgeStore.connectInventory((id) => mutate('pledge', { id }), (id) => mutate('release', { id }));
    return () => { alive.current = false; window.removeEventListener('focus', refresh); window.removeEventListener('storage', refresh); disconnect(); };
  }, [mutate, reload]);
  const value = useMemo(() => ({ ...snapshot, loading, error, reload, mutate }), [snapshot, loading, error, reload, mutate]);
  return <Context.Provider value={value}>{loading ? <p role="status">Загрузка подарков...</p> : error && snapshot === empty ? <div role="alert">Не удалось загрузить подарки. <button onClick={() => void reload().catch(() => {})}>Повторить</button></div> : children}</Context.Provider>;
}
export function useInventory() { const value = useContext(Context); if (!value) throw new Error('InventoryProvider is required'); return value; }
