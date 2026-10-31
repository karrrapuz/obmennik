import { parseRevision } from '../services/snapshotRevision';

export const NANO = 1000000000n;
export const MAX_ACTION = 10000n * NANO;
export const MAX_BALANCE = 100000n * NANO;
export type WalletTransaction = { id: string; kind: 'seed' | 'topup' | 'withdraw' | 'referral' | 'loan_credit' | 'loan_repay' | 'loan_interest' | 'loan_extend' | 'trade_credit' | 'trade_debit'; amount_nano: string; created_at: number };
export type WalletSnapshot = { revision: number; asset: 'DEMO_TON'; balance_nano: string; referral_nano: string; transactions: WalletTransaction[] };
export type WalletAction = 'topup' | 'withdraw' | 'referral';

export function parseTon(value: string): bigint | null {
  if (!/^(?:\d+(?:\.\d{0,9})?|\.\d{1,9})$/.test(value) || value.length > 32) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole || '0') * NANO + BigInt(fraction.padEnd(9, '0'));
}

export function formatNano(value: string | bigint): string {
  const nano = BigInt(value);
  const absolute = nano < 0n ? -nano : nano;
  const fraction = (absolute % NANO).toString().padStart(9, '0').replace(/0+$/, '');
  return `${nano < 0n ? '-' : ''}${absolute / NANO}${fraction ? `.${fraction}` : ''}`;
}

export function displayTon(value: string): number { return Number(BigInt(value)) / Number(NANO); }

export function parseWallet(value: unknown): WalletSnapshot {
  if (!value || typeof value !== 'object') throw new Error('Invalid wallet');
  const wallet = value as WalletSnapshot;
  parseRevision(wallet.revision);
  const unsigned = (amount: unknown): amount is string => typeof amount === 'string' && /^(0|[1-9]\d{0,17})$/.test(amount);
  if (wallet.asset !== 'DEMO_TON' || !unsigned(wallet.balance_nano) || !unsigned(wallet.referral_nano)
    || BigInt(wallet.balance_nano) > MAX_BALANCE || !Array.isArray(wallet.transactions)
    || !wallet.transactions.every((item) => item && typeof item.id === 'string'
      && ['seed', 'topup', 'withdraw', 'referral', 'loan_credit', 'loan_repay', 'loan_interest', 'loan_extend', 'trade_credit', 'trade_debit'].includes(item.kind)
      && typeof item.amount_nano === 'string' && /^-?(0|[1-9]\d{0,17})$/.test(item.amount_nano)
      && typeof item.created_at === 'number' && Number.isFinite(item.created_at))) throw new Error('Invalid wallet snapshot');
  return wallet;
}

export const localWalletKey = 'demo-wallet-v1';
export function readLocalWallet(): WalletSnapshot {
  const saved = localStorage.getItem(localWalletKey);
  if (saved) { const value = JSON.parse(saved); return parseWallet({ ...value, revision: value.revision === undefined ? 0 : value.revision }); }
  const initial: WalletSnapshot = { revision: 0, asset: 'DEMO_TON', balance_nano: '0', referral_nano: (5n * NANO).toString(), transactions: [{ id: crypto.randomUUID(), kind: 'seed', amount_nano: '0', created_at: Date.now() / 1000 }] };
  localStorage.setItem(localWalletKey, JSON.stringify(initial));
  return initial;
}

export function applyLocalWallet(wallet: WalletSnapshot, action: WalletAction, body: Record<string, string>): WalletSnapshot {
  const balance = BigInt(wallet.balance_nano);
  const amount = action === 'referral' ? BigInt(wallet.referral_nano) : /^\d+$/.test(body.amount_nano ?? '') ? BigInt(body.amount_nano) : 0n;
  if (amount <= 0n || (action !== 'referral' && amount > MAX_ACTION)
    || (action === 'withdraw' && (!body.destination?.trim() || amount > balance))
    || (action === 'topup' && !['wallet', 'cryptobot'].includes(body.source))) throw new Error('Invalid wallet operation');
  const delta = action === 'withdraw' ? -amount : amount;
  const next = balance + delta;
  if (next > MAX_BALANCE) throw new Error('Wallet limit exceeded');
  return { ...wallet, revision: wallet.revision + 1, balance_nano: next.toString(), referral_nano: action === 'referral' ? '0' : wallet.referral_nano,
    transactions: [{ id: crypto.randomUUID(), kind: action, amount_nano: delta.toString(), created_at: Date.now() / 1000 }, ...wallet.transactions] };
}
