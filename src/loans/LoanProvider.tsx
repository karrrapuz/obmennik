import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { useBootReport } from '../boot/BootProvider';
import { parseSnapshot, useInventory, type Snapshot } from '../inventory/InventoryProvider';
import { useWallet } from '../wallet/WalletProvider';
import { displayTon, parseWallet, type WalletSnapshot } from '../wallet/wallet';
import { pledgeStore, pledgeTerms, type Pledge, type Quote } from '../pages/DepositPage/services/pledgeStore';
import { createRevisionGate, parseCombinedRevision } from '../services/snapshotRevision';
import { presentationOwned } from '../inventory/showcase';

type Term = { weeks: 1 | 2; principal: number; repayment: number };
type Loan = { id: string; gift_id: number; weeks: 1 | 2; principal_nano: string; repayment_nano: string; due_at: number; autopay: boolean; legacy: boolean; status: 'active' | 'repaid' };
type Combined = { revision: number; loans: Loan[]; terms: { weeks: 1 | 2; principal_nano: string; repayment_nano: string }[]; wallet: WalletSnapshot; inventory: Snapshot };
const Terms = createContext<readonly Term[]>(pledgeTerms);
const base = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
const nano = (value: unknown): value is string => typeof value === 'string' && /^(0|[1-9]\d*)$/.test(value);
export function useLoanTerms() { return useContext(Terms); }

export function LoanProvider({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const { applySnapshot: applyInventory, getRevision: inventoryRevision, revision: inventoryStateRevision, inventory, pledged } = useInventory();
  const { applySnapshot: applyWallet, getRevision: walletRevision, wallet } = useWallet();
  const demo = state.status === 'ready' && state.mode === 'demo';
  const token = state.status === 'ready' ? state.accessToken : null;
  const [terms, setTerms] = useState<readonly Term[]>(demo ? pledgeTerms : []);
  const [loading, setLoading] = useState(!demo);
  const [error, setError] = useState(false);
  const alive = useRef(false);
  const [revision] = useState(createRevisionGate);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const refreshPending = useRef<Promise<void> | null>(null);
  const keys = useRef(new Map<string, string>());
  const request = useCallback(async (path: string, body?: Record<string, unknown>, key?: string) => {
    if (!token || demo) throw new Error('Telegram session required');
    const response = await fetch(`${base}/api/loans${path}`, {
      method: body ? 'POST' : 'GET',
      headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}), ...(key ? { 'Idempotency-Key': key } : {}) },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(90000),
    });
    if (!response.ok) {
      if (key && response.status < 500 && response.status !== 408) keys.current.forEach((value, signature) => { if (value === key) keys.current.delete(signature); });
      throw new Error(response.status === 401 ? 'Сессия истекла. Повторите вход.' : 'Не удалось выполнить операцию. Повторите попытку.');
    }
    return response.json();
  }, [demo, token]);
  const apply = useCallback((raw: Combined) => {
    parseCombinedRevision(raw?.revision, raw?.wallet?.revision, raw?.inventory?.revision);
    const nextWallet = parseWallet(raw.wallet);
    const nextInventory = parseSnapshot(raw.inventory);
    if (!Array.isArray(raw.loans) || !Array.isArray(raw.terms)
      || raw.loans.some((loan) => typeof loan.id !== 'string' || !Number.isInteger(loan.gift_id) || ![1, 2].includes(loan.weeks) || !nano(loan.principal_nano) || !nano(loan.repayment_nano) || !Number.isFinite(loan.due_at) || typeof loan.legacy !== 'boolean' || typeof loan.autopay !== 'boolean' || !['active', 'repaid'].includes(loan.status))
      || raw.terms.some((term) => ![1, 2].includes(term.weeks) || !nano(term.principal_nano) || !nano(term.repayment_nano))) throw new Error('Invalid loans snapshot');
    const gifts = new Map([...nextInventory.inventory, ...nextInventory.pledged].map((gift) => [gift.id, gift]));
    const next: Pledge[] = raw.loans.filter((loan) => loan.status === 'active').map((loan) => {
      const gift = gifts.get(loan.gift_id);
      if (!gift) throw new Error('Loan gift missing');
      return { id: loan.id, legacy: loan.legacy, gift, weeks: loan.weeks, principal: displayTon(loan.principal_nano), repayment: displayTon(loan.repayment_nano), interest: displayTon((BigInt(loan.repayment_nano) - BigInt(loan.principal_nano)).toString()), dueAt: loan.due_at * 1000, autopay: loan.autopay, status: 'active' };
    });
    if (!alive.current || raw.revision < Math.max(revision.current(), walletRevision(), inventoryRevision())) return false;
    revision.accept(raw.revision);
    applyWallet(nextWallet); applyInventory(nextInventory);
    pledgeStore.applyServer({ inventory: presentationOwned(nextInventory.inventory), pledges: next, balance: displayTon(nextWallet.balance_nano) });
    setTerms(raw.terms.map((term) => ({ weeks: term.weeks, principal: displayTon(term.principal_nano), repayment: displayTon(term.repayment_nano) })));
    setLoading(false); setError(false);
    return true;
  }, [applyInventory, applyWallet, inventoryRevision, walletRevision, revision]);
  const reconcile = useCallback(async () => {
    // A replayed idempotency response can predate a newer read or operation.
    for (let attempt = 0; attempt < 3 && alive.current; attempt++) {
      if (apply(await request(''))) return;
    }
    if (alive.current) throw new Error('Unable to obtain current loans snapshot');
  }, [apply, request]);
  const enqueue = useCallback(<T,>(fn: () => Promise<T>) => { const next = queue.current.then(fn); queue.current = next.catch(() => {}); return next; }, []);
  const reload = useCallback(() => {
    if (refreshPending.current) return refreshPending.current;
    const work = enqueue(async () => {
      try { await reconcile(); } catch { if (alive.current) setError(true); } finally { if (alive.current) setLoading(false); }
    });
    refreshPending.current = work;
    void work.then(() => { if (refreshPending.current === work) refreshPending.current = null; }, () => { if (refreshPending.current === work) refreshPending.current = null; });
    return work;
  }, [enqueue, reconcile]);
  useEffect(() => {
    alive.current = true;
    if (demo) { pledgeStore.useDemo(); setLoading(false); return () => { alive.current = false; }; }
    const disconnect = pledgeStore.connectServer({
      mutate: (action, body) => enqueue(async () => {
        const signature = `${action}:${JSON.stringify(body)}`;
        const key = keys.current.get(signature) ?? crypto.randomUUID(); keys.current.set(signature, key);
        try { const result = await request(`/${action}`, body, key); if (!apply(result)) await reconcile(); keys.current.delete(signature); return true; }
        catch (cause) { try { await reconcile(); } catch { /* Keep the last confirmed snapshot on network failure. */ } throw cause; }
      }),
      quote: async (ids): Promise<Quote> => {
        const result = await request('/quote', { gift_ids: ids });
        if (![result.interest_nano, result.fee_nano, result.total_nano].every(nano)) throw new Error('Invalid quote');
        return { interest: displayTon(result.interest_nano), fee: displayTon(result.fee_nano), total: displayTon(result.total_nano) };
      },
    });
    void reload();
    const refresh = () => { void reload(); };
    window.addEventListener('focus', refresh);
    return () => { alive.current = false; disconnect(); window.removeEventListener('focus', refresh); };
  }, [demo, enqueue, apply, reload, request, reconcile]);
  useEffect(() => {
    if (!demo && !loading && Math.max(wallet.revision, inventoryStateRevision) > revision.current()) void reload();
  }, [demo, loading, wallet.revision, inventoryStateRevision, revision, reload]);
  useEffect(() => { if (!demo && !loading) pledgeStore.setBalance(displayTon(wallet.balance_nano)); }, [demo, loading, wallet.balance_nano]);
  useEffect(() => {
    if (demo || loading) return;
    // Inventory refreshes can update artwork, but never reconstruct server loan terms.
    const gifts = new Map([...inventory, ...pledged].map((gift) => [gift.id, gift]));
    const current = pledgeStore.getSnapshot();
    pledgeStore.applyServer({ ...current, inventory, pledges: current.pledges.map((loan) => ({ ...loan, gift: gifts.get(loan.gift.id) ?? loan.gift })) });
  }, [demo, loading, inventory, pledged]);
  useBootReport('loans', loading, error, reload);
  return <Terms.Provider value={terms}>{children}</Terms.Provider>;
}
