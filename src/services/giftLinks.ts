import featured from '../pages/ExchangePage/data/relayer-preview.json';
import { gifts, type Gift } from '../pages/ExchangePage/data/gifts';
import extra from '../pages/ExchangePage/data/catalog-showcase-extra.json';

function openTelegram(url: string) {
  const app = (window as Window & { Telegram?: { WebApp?: { openTelegramLink?: (url: string) => void } } }).Telegram?.WebApp;
  if (app?.openTelegramLink) { app.openTelegramLink(url); return; }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function nativeGiftUrl(gift: Pick<Gift, 'telegramSlug'>) {
  const slug = gift.telegramSlug && /^[A-Za-z0-9]+-[1-9]\d*$/.test(gift.telegramSlug) ? gift.telegramSlug : featured.telegramSlug;
  return `https://t.me/nft/${slug}`;
}

export function viewNativeGift(gift: Gift) { openTelegram(nativeGiftUrl(gift)); }

export function sharedGiftPayload() {
  const app = (window as Window & { Telegram?: { WebApp?: { initDataUnsafe?: { start_param?: string } } } }).Telegram?.WebApp;
  const query = new URLSearchParams(window.location.search);
  const payload = app?.initDataUnsafe?.start_param ?? query.get('tgWebAppStartParam') ?? query.get('startapp');
  return payload ?? '';
}

export async function shareGift(gift: Gift, source: 'inventory' | 'exchange' = 'exchange', accessToken: string | null = null) {
  const bot = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || 'obmen_huikin_bot';
  if (!/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(bot)) throw new Error('Invalid bot username');
  let payload: string;
  if (gift.shareToken && /^[A-Za-z0-9_-]{32}$/.test(gift.shareToken)) payload = `sg_${gift.shareToken}`;
  else if (accessToken) {
    const api = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
    const response = await fetch(`${api}/api/gifts/share`, { method: 'POST', headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, gift_id: gift.id }), signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error('Gift link unavailable');
    const result = await response.json();
    if (!/^[A-Za-z0-9_-]{32}$/.test(result.share_ref)) throw new Error('Invalid share reference');
    payload = `sg_${result.share_ref}`;
  } else {
    const template = source === 'exchange' ? gift : [...gifts, ...extra, featured].find(item => item.id === gift.catalogId || item.collectionId === gift.collectionId && item.modelName === gift.modelName);
    if (!template) throw new Error('Exact gift link unavailable');
    const number = /^#([1-9]\d{0,9})$/.exec(gift.model)?.[1];
    payload = `gift_${template.id}${source === 'inventory' && number ? `_n${number}` : ''}`;
  }
  const url = `https://t.me/${bot}?startapp=${payload}`;
  const text = `Посмотрите этот красивый подарок для обмена в @${bot}\n${gift.name} ${gift.model}`;
  openTelegram(`https://t.me/share/url?${new URLSearchParams({ url, text })}`);
}
