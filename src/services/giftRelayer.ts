export const giftRelayerUrl = 'https://t.me/smekz';

export function openGiftRelayer() {
  const app = (window as Window & { Telegram?: { WebApp?: { openTelegramLink?: (url: string) => void } } }).Telegram?.WebApp;
  if (app?.openTelegramLink) { app.openTelegramLink(giftRelayerUrl); return; }
  window.open(giftRelayerUrl, '_blank', 'noopener,noreferrer');
}
