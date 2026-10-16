import { inventoryGifts, type Gift } from '../../ExchangePage/data/gifts';

export type Pledge = {
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

// Demo source, isolated from presentation for a future API implementation.
let state: State = { inventory: inventoryGifts.map((gift) => ({ ...gift })), pledges: [], balance: 0 };
const listeners = new Set<() => void>();
const publish = (next: State) => { state = next; listeners.forEach((listener) => listener()); };
export const pledgeStore = {
  quote(ids: number[]) {
    const selected = state.pledges.filter((item) => ids.includes(item.gift.id) && item.status === 'active');
    const interest = Math.round(selected.reduce((sum, item) => sum + item.repayment - item.principal, 0) * 1000) / 1000;
    const fee = selected.length ? 0.01 : 0;
    return { interest, fee, total: Math.round((interest + fee) * 1000) / 1000 };
  },
  async extend(ids: number[]) {
    const unique = [...new Set(ids)];
    await new Promise((resolve) => setTimeout(resolve, 1800));
    const selected = state.pledges.filter((item) => unique.includes(item.gift.id) && item.status === 'active');
    const quote = this.quote(unique);
    if (!selected.length || selected.length !== unique.length || state.balance < quote.total) return false;
    publish({ ...state, balance: Math.round((state.balance - quote.total) * 1000) / 1000, pledges: state.pledges.map((item) => selected.includes(item) ? { ...item, dueAt: Math.max(Date.now(), item.dueAt) + 14 * 86400000 } : item) });
    return true;
  },
  getSnapshot: () => state,
  subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  create(giftId: number, weeks: 1 | 2) {
    const gift = state.inventory.find((item) => item.id === giftId);
    if (!gift || gift.pledgeSupported === false || state.pledges.some((item) => item.gift.id === giftId)) return;
    const term = pledgeTerms.find((item) => item.weeks === weeks)!;
    const pledge: Pledge = { gift, ...term, dueAt: Date.now() + weeks * 7 * 86400000, status: 'processing', autopay: false };
    publish({ ...state, inventory: state.inventory.filter((item) => item.id !== giftId), pledges: [...state.pledges, pledge] });
    setTimeout(() => publish({ ...state, balance: Math.round((state.balance + term.principal) * 1000) / 1000, pledges: state.pledges.map((item) => item.gift.id === giftId ? { ...item, status: 'active' } : item) }), 2200);
  },
  repay(giftId: number) {
    const pledge = state.pledges.find((item) => item.gift.id === giftId);
    if (!pledge || pledge.status !== 'active' || state.balance < pledge.repayment) return false;
    publish({ ...state, balance: Math.round((state.balance - pledge.repayment) * 1000) / 1000, inventory: [...state.inventory, pledge.gift], pledges: state.pledges.filter((item) => item !== pledge) });
    return true;
  },
  payInterest(giftId: number) {
    const pledge = state.pledges.find((item) => item.gift.id === giftId);
    if (!pledge || pledge.status !== 'active') return false;
    const interest = Math.round((pledge.repayment - pledge.principal) * 1000) / 1000;
    if (state.balance < interest) return false;
    publish({ ...state, balance: Math.round((state.balance - interest) * 1000) / 1000, pledges: state.pledges.map((item) => item === pledge ? { ...item, dueAt: item.dueAt + item.weeks * 7 * 86400000 } : item) });
    return true;
  },
  toggleAutopay(giftId: number) {
    publish({ ...state, pledges: state.pledges.map((item) => item.gift.id === giftId ? { ...item, autopay: !item.autopay } : item) });
  },
};
