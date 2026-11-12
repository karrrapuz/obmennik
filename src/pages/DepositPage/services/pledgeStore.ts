import { isUnpricedGift, type Gift } from '../../ExchangePage/data/gifts';
import { displayTon, localWalletKey, MAX_BALANCE, parseTon, readLocalWallet, type WalletSnapshot, type WalletTransaction } from '../../../wallet/wallet';

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

type GuestTerms = Pick<Pledge, 'weeks' | 'principal' | 'repayment' | 'dueAt' | 'autopay'>;
type GuestWallet = WalletSnapshot & { pledgeTerms?: Record<number, GuestTerms> };
type MoveGift = (id: number, saveLoan: () => boolean) => Promise<boolean>;
type LoanKind = Extract<WalletTransaction['kind'], `loan_${string}`>;
const week = 7 * 86400000;
const interestFor = ({ repayment, principal }: GuestTerms) => Math.round((repayment - principal) * 1000) / 1000;
const guestWallet = (): GuestWallet => readLocalWallet();
export const guestLoanWalletEvent = 'guest-loan-wallet';

let state: State = { inventory: [], pledges: [], balance: 0 };
let reserve: MoveGift | undefined;
let release: MoveGift | undefined;
let mutationBusy = false;
const listeners = new Set<() => void>();
const publish = (next: State) => { state = next; listeners.forEach((listener) => listener()); };
function changeGuestWallet(kind: LoanKind | null, amount: number, update: (terms: Record<number, GuestTerms>) => boolean | void) {
  const wallet = guestWallet();
  const magnitude = parseTon(Math.abs(amount).toString());
  if (magnitude === null) throw new Error('Invalid guest loan amount');
  const delta = magnitude * (amount < 0 ? -1n : 1n);
  const balance = BigInt(wallet.balance_nano) + delta;
  if (balance < 0n || balance > MAX_BALANCE) return false;
  const pledgeTerms = { ...wallet.pledgeTerms };
  if (update(pledgeTerms) === false) return false;
  const next: GuestWallet = { ...wallet, pledgeTerms, balance_nano: balance.toString(), revision: wallet.revision + 1,
    transactions: kind ? [{ id: crypto.randomUUID(), kind, amount_nano: delta.toString(), created_at: Date.now() / 1000 }, ...wallet.transactions] : wallet.transactions };
  localStorage.setItem(localWalletKey, JSON.stringify(next));
  window.dispatchEvent(new Event(guestLoanWalletEvent));
  return true;
}
const refreshGuest = () => pledgeStore.syncInventory(state.inventory, state.pledges.map(({ gift }) => gift));
export const pledgeStore = {
  connectServer(next: Bridge) { bridge = next; serverMode = true; return () => { if (bridge === next) bridge = undefined; }; },
  useDemo() { serverMode = false; bridge = undefined; },
  applyServer(next: State) { publish(next); },
  setBalance(balance: number) { publish({ ...state, balance }); },
  async requestQuote(ids: number[]): Promise<Quote> { if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.quote(ids); } return this.quote(ids); },
  connectInventory(onReserve: MoveGift, onRelease: MoveGift) {
    reserve = onReserve; release = onRelease;
    return () => { if (reserve === onReserve) { reserve = undefined; release = undefined; } };
  },
  syncInventory(inventory: Gift[], pledged: Gift[]) {
    if (serverMode) return;
    const wallet = guestWallet();
    const saved = { ...wallet.pledgeTerms };
    let migrated = false;
    const pledges: Pledge[] = pledged.map((gift) => {
      if (!saved[gift.id]) {
        saved[gift.id] = { ...pledgeTerms[0], dueAt: Date.now() + week, autopay: false };
        migrated = true;
      }
      return { ...saved[gift.id], gift, interest: interestFor(saved[gift.id]), status: 'active' };
    });
    if (migrated) localStorage.setItem(localWalletKey, JSON.stringify({ ...wallet, pledgeTerms: saved }));
    publish({ inventory, pledges, balance: displayTon(wallet.balance_nano) });
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
    const session = reserve;
    await new Promise((resolve) => setTimeout(resolve, 1800));
    if (serverMode || !session || reserve !== session) return false;
    const selected = state.pledges.filter((item) => unique.includes(item.gift.id) && item.status === 'active');
    const quote = this.quote(unique);
    if (mutationBusy || !selected.length || selected.length !== unique.length) return false;
    const ok = changeGuestWallet('loan_extend', -quote.total, (terms) => {
      if (selected.some(({ gift }) => !terms[gift.id])) return false;
      for (const { gift } of selected) terms[gift.id] = { ...terms[gift.id], dueAt: Math.max(Date.now(), terms[gift.id].dueAt) + 2 * week };
    });
    if (ok) refreshGuest();
    return ok;
  },
  getSnapshot: () => state,
  subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  async create(giftId: number, weeks: 1 | 2) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('create', { gift_id: giftId, weeks }); }
    const gift = state.inventory.find((item) => item.id === giftId);
    if (mutationBusy || !reserve || !gift || gift.pledgeSupported === false || isUnpricedGift(gift) || state.pledges.some((item) => item.gift.id === giftId)) return false;
    const term = pledgeTerms.find((item) => item.weeks === weeks);
    if (!term) return false;
    mutationBusy = true;
    try {
      return await reserve(giftId, () => changeGuestWallet('loan_credit', term.principal, (terms) => {
        terms[giftId] = { ...term, dueAt: Date.now() + weeks * week, autopay: false };
      }));
    } finally { mutationBusy = false; }
  },
  async repay(giftId: number) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('repay', { gift_id: giftId }); }
    const pledge = state.pledges.find((item) => item.gift.id === giftId);
    if (mutationBusy || !release || !pledge || pledge.status !== 'active') return false;
    mutationBusy = true;
    try {
      return await release(giftId, () => changeGuestWallet('loan_repay', -pledge.repayment, (terms) => { delete terms[giftId]; }));
    } finally { mutationBusy = false; }
  },
  async payInterest(giftId: number) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); return bridge.mutate('pay-interest', { gift_id: giftId }); }
    const pledge = state.pledges.find((item) => item.gift.id === giftId);
    if (mutationBusy || !pledge || pledge.status !== 'active') return false;
    const interest = interestFor(pledge);
    const ok = changeGuestWallet('loan_interest', -interest, (terms) => {
      if (!terms[giftId]) return false;
      terms[giftId] = { ...terms[giftId], dueAt: terms[giftId].dueAt + terms[giftId].weeks * week };
    });
    if (ok) refreshGuest();
    return ok;
  },
  async toggleAutopay(giftId: number) {
    if (serverMode) { if (!bridge) throw new Error('Loans unavailable'); const loan = state.pledges.find((item) => item.gift.id === giftId); return bridge.mutate('autopay', { gift_id: giftId, enabled: !loan?.autopay }); }
    if (mutationBusy || !state.pledges.some((item) => item.gift.id === giftId)) return false;
    const ok = changeGuestWallet(null, 0, (terms) => {
      if (!terms[giftId]) return false;
      terms[giftId] = { ...terms[giftId], autopay: !terms[giftId].autopay };
    });
    if (ok) refreshGuest();
    return ok;
  },
};
