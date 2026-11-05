import featured from '../pages/ExchangePage/data/relayer-preview.json';
import { gifts, type Gift } from '../pages/ExchangePage/data/gifts';

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

export function sharedGiftId() {
  const app = (window as Window & { Telegram?: { WebApp?: { initDataUnsafe?: { start_param?: string } } } }).Telegram?.WebApp;
  const query = new URLSearchParams(window.location.search);
  const payload = app?.initDataUnsafe?.start_param ?? query.get('tgWebAppStartParam') ?? query.get('startapp');
  const match = /^gift_([1-9]\d{0,8})$/.exec(payload ?? '');
  return match ? Number(match[1]) : null;
}

export function shareGift(gift: Gift, source: 'inventory' | 'exchange' = 'exchange') {
  const template = gift.telegramSlug ? featured : source === 'exchange' ? gift : gifts.find(item => item.collectionId === gift.collectionId && item.modelName === gift.modelName);
  const id = template?.id ?? featured.id;
  const bot = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || 'obmen_huikin_bot';
  if (!/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(bot)) throw new Error('Invalid bot username');
  const url = `https://t.me/${bot}?startapp=gift_${id}`;
  const text = template ? `Посмотрите на ${gift.name} ${gift.model} в нашем приложении.` : `Посмотрите на ${featured.name} ${featured.model} в нашем приложении.`;
  openTelegram(`https://t.me/share/url?${new URLSearchParams({ url, text })}`);
}
