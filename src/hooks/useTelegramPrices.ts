import { useEffect, useSyncExternalStore } from 'react';
import { parseTelegramPrices, type TelegramPrices } from '../services/telegramPrices';

type State = { feed: TelegramPrices | null; now: number };
let state: State = { feed: null, now: Math.floor(Date.now() / 1000) };
let request: Promise<void> | undefined;
let expiryTimer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();
const snapshot = () => state;
function refreshClock() {
  state = { ...state, now: Math.floor(Date.now() / 1000) };
  listeners.forEach(listener => listener());
  clearTimeout(expiryTimer);
  if (listeners.size) expiryTimer = setTimeout(refreshClock, Math.min(60000, state.feed && state.feed.validUntil > state.now ? state.feed.validUntil * 1000 - Date.now() + 1 : 60000));
}
function becameVisible() { if (document.visibilityState === 'visible') refreshClock(); }
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) { window.addEventListener('focus', refreshClock); document.addEventListener('visibilitychange', becameVisible); refreshClock(); }
  return () => { listeners.delete(listener); if (!listeners.size) { window.removeEventListener('focus', refreshClock); document.removeEventListener('visibilitychange', becameVisible); clearTimeout(expiryTimer); } };
}
export function loadTelegramPrices(): Promise<void> {
  request ??= (async () => {
    try {
      const response = await fetch('/gifts/telegram/prices.json', { signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error('Price reference unavailable');
      state = { feed: parseTelegramPrices(await response.json()), now: Math.floor(Date.now() / 1000) };
    } catch { state = { feed: null, now: Math.floor(Date.now() / 1000) }; }
    refreshClock();
  })();
  return request;
}
export function useTelegramPrices() {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => { void loadTelegramPrices(); }, []);
  return current;
}
