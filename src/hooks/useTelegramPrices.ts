import { useEffect, useSyncExternalStore } from 'react';
import { parseTelegramPrices, type TelegramPrices } from '../services/telegramPrices';

type State = { feed: TelegramPrices | null; now: number };
let state: State = { feed: null, now: Math.floor(Date.now() / 1000) };
let request: Promise<void> | undefined;
let expiryTimer: ReturnType<typeof setTimeout> | undefined;
let pollingTimer: ReturnType<typeof setInterval> | undefined;
let lastAttempt = -Infinity;
const apiUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
const listeners = new Set<() => void>();
const snapshot = () => state;
function refreshClock() {
  state = { ...state, now: Math.floor(Date.now() / 1000) };
  listeners.forEach(listener => listener());
  clearTimeout(expiryTimer);
  if (listeners.size) expiryTimer = setTimeout(refreshClock, Math.min(60000, state.feed && state.feed.validUntil > state.now ? state.feed.validUntil * 1000 - Date.now() + 1 : 60000));
}
function becameVisible() {
  if (document.visibilityState !== 'visible') return;
  refreshClock();
  void loadTelegramPrices();
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    window.addEventListener('focus', becameVisible); document.addEventListener('visibilitychange', becameVisible);
    pollingTimer = setInterval(becameVisible, 300000);
    refreshClock();
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      window.removeEventListener('focus', becameVisible); document.removeEventListener('visibilitychange', becameVisible);
      clearTimeout(expiryTimer); clearInterval(pollingTimer);
      expiryTimer = undefined; pollingTimer = undefined;
    }
  };
}
export function loadTelegramPrices(): Promise<void> {
  if (request) return request;
  if (Date.now() - lastAttempt < 60000) return Promise.resolve();
  lastAttempt = Date.now();
  request = (async () => {
    for (const url of [`${apiUrl}/api/market/prices`, '/gifts/telegram/prices.json']) {
      try {
        const response = await fetch(url, { signal: AbortSignal.timeout(12000), cache: 'no-store' });
        if (!response.ok) throw new Error('Price reference unavailable');
        const feed = parseTelegramPrices(await response.json());
        if (!state.feed || feed.capturedAt >= state.feed.capturedAt) state = { ...state, feed };
        break;
      } catch { /* Keep the last validated feed if both sources fail. */ }
    }
  })().finally(() => { request = undefined; refreshClock(); });
  return request;
}
export function useTelegramPrices() {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => { void loadTelegramPrices(); }, []);
  return current;
}
