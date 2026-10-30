import { type Gift } from '../../ExchangePage/data/gifts';

export type Pledge = {
  legacy?: boolean;
  id?: string;
  interest?: number;
  gift: Gift;
  weeks: 1 | 2;
  principal: number;
  repayment: number;
  dueAt: number;
  status: 'processing' | 'active';
  autopay: boolean;
};
type State = { inventory: Gift[]; pledges: Pledge[]; balance: number };
export const pledgeTerms = [
  { weeks: 1, principal: 1.2, repayment: 1.24 },
  { weeks: 2, principal: 1.2, repayment: 1.28 },
] as const;
export type Quote = { interest: number; fee: number; total: number };
type Bridge = { mutate: (action: string, body: Record<string, unknown>) => Promise<boolean>; quote: (ids: number[]) => Promise<Quote> };
let bridge: Bridge | undefined;
let serverMode = false;

// Financial terms are demo-only; gift ownership is supplied by InventoryProvider.
let state: State = { inventory: [], pledges: [], balance: 0 };
let reserve: ((id: number) => Promise<void>) | undefined;
let release: ((id: number) => Promise<void>) | undefined;
let mutationBusy = false;
const listeners = new Set<() => void>();
const publish = (next: State) => { state = next; listeners.forEach((listener) => listener()); };
export const pledgeStore = {
  connectServer(next: Bridge) { bridge = next; serverMode = true; return () => { if (bridge === next) bridge = undefined; }; },
  useDemo() { serverMode = false; bridge = undefined; },
  applyServer(next: State) { publish(next); },
  setBalance(balance: number) { publish({ ...state, balance }); },
  async requestQuote(ids: number[]): Promise<Quote> { if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.quote(ids); } return this.quote(ids); },
  connectInventory(onReserve: (id: number) => Promise<void>, onRelease: (id: number) => Promise<void>) {
    reserve = onReserve; release = onRelease;
    return () => { if (reserve === onReserve) { reserve = undefined; release = undefined; } };
  },
  syncInventory(inventory: Gift[], pledged: Gift[]) {
    if (serverMode) return;
    publish({ ...state, inventory, pledges: pledged.map((gift) => {
      const existing = state.pledges.find((item) => item.gift.id === gift.id);
      return existing ? { ...existing, gift } : { gift, ...pledgeTerms[0], dueAt: Date.now() + 7 * 86400000, status: 'active', autopay: false };
    }) });
  },
  quote(ids: number[]) {
    const selected = state.pledges.filter((item) => ids.includes(item.gift.id) && item.status === 'active');
    const interest = Math.round(selected.reduce((sum, item) => sum + item.repayment - item.principal, 0) * 1000) / 1000;
    const fee = selected.length ? 0.01 : 0;
    return { interest, fee, total: Math.round((interest + fee) * 1000) / 1000 };
  },
  async extend(ids: number[]) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('extend', { gift_ids: ids }); }
    const unique = [...new Set(ids)];
    await new Promise((resolve) => setTimeout(resolve, 1800));
    const selected = state.pledges.filter((item) => unique.includes(item.gift.id) && item.status === 'active');
    const quote = this.quote(unique);
    if (mutationBusy || !selected.length || selected.length !== unique.length || state.balance < quote.total) return false;
    publish({ ...state, balance: Math.round((state.balance - quote.total) * 1000) / 1000, pledges: state.pledges.map((item) => selected.includes(item) ? { ...item, dueAt: Math.max(Date.now(), item.dueAt) + 14 * 86400000 } : item) });
    return true;
  },
  getSnapshot: () => state,
  subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  async create(giftId: number, weeks: 1 | 2) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('create', { gift_id: giftId, weeks }); }
    const gift = state.inventory.find((item) => item.id === giftId);
    if (mutationBusy || !reserve || !gift || gift.pledgeSupported === false || state.pledges.some((item) => item.gift.id === giftId)) return false;
    const term = pledgeTerms.find((item) => item.weeks === weeks)!;
    const pledge: Pledge = { gift, ...term, dueAt: Date.now() + weeks * 7 * 86400000, status: 'processing', autopay: false };
    mutationBusy = true;
    try {
      await reserve(giftId);
      publish({ ...state, balance: Math.round((state.balance + term.principal) * 1000) / 1000, pledges: state.pledges.map((item) => item.gift.id === giftId ? { ...pledge, status: 'active' } : item) });
      return true;
    } finally { mutationBusy = false; }
  },
  async repay(giftId: number) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('repay', { gift_id: giftId }); }
    const pledge = state.pledges.find((item) => item.gift.id === giftId);
    if (mutationBusy || !release || !pledge || pledge.status !== 'active' || state.balance < pledge.repayment) return false;
    mutationBusy = true;
    try {
      await release(giftId);
      publish({ ...state, balance: Math.round((state.balance - pledge.repayment) * 1000) / 1000 });
      return true;
    } finally { mutationBusy = false; }
  },
  async payInterest(giftId: number) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('pay-interest', { gift_id: giftId }); }
    const pledge = state.pledges.find((item) => item.gift.id === giftId);
    if (mutationBusy || !pledge || pledge.status !== 'active') return false;
    const interest = Math.round((pledge.repayment - pledge.principal) * 1000) / 1000;
    if (state.balance < interest) return false;
    publish({ ...state, balance: Math.round((state.balance - interest) * 1000) / 1000, pledges: state.pledges.map((item) => item === pledge ? { ...item, dueAt: item.dueAt + item.weeks * 7 * 86400000 } : item) });
    return true;
  },
  async toggleAutopay(giftId: number) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); const loan = state.pledges.find((item) => item.gift.id === giftId); return bridge.mutate('autopay', { gift_id: giftId, enabled: !loan?.autopay }); }
    publish({ ...state, pledges: state.pledges.map((item) => item.gift.id === giftId ? { ...item, autopay: !item.autopay } : item) });
  },
};
