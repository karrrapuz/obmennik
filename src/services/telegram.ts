type TelegramWebApp = {
  initData: string;
  platform: string;
  ready: () => void;
  expand: () => void;
  isVersionAtLeast: (version: string) => boolean;
  disableVerticalSwipes: () => void;
  setHeaderColor: (color: string) => void;
  setBackgroundColor: (color: string) => void;
  setBottomBarColor: (color: string) => void;
  enableClosingConfirmation?: () => void;
  HapticFeedback?: { selectionChanged: () => void; notificationOccurred: (type: 'success' | 'error') => void };
};

let hapticsBound = false;
export function telegramHaptic(type: 'selection' | 'success' | 'error' = 'selection') {
  const feedback = (window as Window & { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp?.HapticFeedback;
  try {
    if (type === 'selection') feedback?.selectionChanged();
    else feedback?.notificationOccurred(type);
  } catch { /* Unsupported clients must not interrupt the action. */ }
}

export function getTelegramInitData(): string {
  return (window as Window & { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp?.initData ?? '';
}

export function isTelegramContext(): boolean {
  const app = (window as Window & { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp;
  return Boolean(app && (app.initData || (app.platform && app.platform !== 'unknown')));
}

export function initializeTelegram() {
  const app = (window as Window & { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp;
  if (!app || (!app.initData && app.platform === 'unknown')) return;

  app.ready();
  app.expand();
  if (!hapticsBound && typeof document !== 'undefined') {
    document.addEventListener('click', event => {
      const button = event.target instanceof Element ? event.target.closest('button') : null;
      if (button && !button.disabled && button.getAttribute('aria-disabled') !== 'true') telegramHaptic();
    });
    hapticsBound = true;
  }
  if (app.isVersionAtLeast('6.2')) app.enableClosingConfirmation?.();
  if (app.isVersionAtLeast('6.1')) app.setBackgroundColor('#0d0d0d');
  if (app.isVersionAtLeast('6.9')) app.setHeaderColor('#0d0d0d');
  if (app.isVersionAtLeast('7.7')) app.disableVerticalSwipes();
  if (app.isVersionAtLeast('7.10')) app.setBottomBarColor('#0d0d0d');
}
