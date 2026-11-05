import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)('playwright');
const out = path.resolve('backend/.local/ui-regression', process.env.UI_QA_RUN || 'baseline');
fs.mkdirSync(out, { recursive: true });
const sample = JSON.parse(fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8'));
const fixture = { revision: 0, inventory: sample.slice(0, 5).map((gift, index) => ({ ...gift, id: 101 + index, pledgeSupported: true })), pledged: [], catalog: sample };
const browser = await chromium.launch({ headless: true, executablePath: process.env.GIFT_BROWSER_EXECUTABLE || 'C:/Users/79505/AppData/Local/ms-playwright/chromium-1169/chrome-win/chrome.exe' });
const results = [];
try {
  for (const width of [320, 390]) for (const height of [568, 460]) {
    const context = await browser.newContext({ viewport: { width, height } });
    const page = await context.newPage();
    page.setDefaultTimeout(8000);
    await page.route('**/*', route => {
      const request = route.request();
      const url = new URL(request.url());
      return url.hostname === '127.0.0.1' && ['GET', 'HEAD'].includes(request.method()) ? route.continue() : route.abort();
    });
    await page.addInitScript(value => localStorage.setItem('demo-inventory-v1', JSON.stringify(value)), fixture);
    await page.goto(process.env.UI_QA_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.getByRole('button', { name: 'Фильтры', exact: true }).waitFor();
    const capture = async name => {
      await page.waitForTimeout(450);
      const state = await page.evaluate(() => {
        const box = n => { const r = n.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom, right: r.right }; };
        const shown = n => !!n.getBoundingClientRect().width && !!n.getBoundingClientRect().height && getComputedStyle(n).visibility !== 'hidden';
        const dialogs = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"], dialog[open]')].filter(shown);
        const scope = dialogs.at(-1) || document;
        const controls = [...scope.querySelectorAll('button,input')].filter(shown).map(n => {
          const b = box(n); const x = b.x + b.width / 2, y = b.y + b.height / 2;
          const hit = document.elementFromPoint(x, y);
          return { name: n.getAttribute('aria-label') || n.textContent.trim() || n.placeholder, box: b, disabled: n.disabled, centerHit: !!hit && (n === hit || n.contains(hit)), fontSize: getComputedStyle(n).fontSize };
        });
        const clippedText = [...scope.querySelectorAll('p,small,strong,h2,label,span')].filter(shown).filter(n => n.scrollWidth > n.clientWidth + 2 && n.clientWidth > 0).map(n => ({ text: n.textContent.slice(0, 100), cls: n.className, client: n.clientWidth, scroll: n.scrollWidth }));
        const secondary = [...scope.querySelectorAll('p,small')].filter(shown).slice(0, 20).map(n => ({ text: n.textContent.slice(0, 100), color: getComputedStyle(n).color, font: getComputedStyle(n).fontSize, opacity: getComputedStyle(n).opacity }));
        return { documentWidth: document.documentElement.scrollWidth, viewport: { width: innerWidth, height: innerHeight }, dialogs: dialogs.map(n => ({ name: n.getAttribute('aria-label'), cls: n.className, box: box(n) })), controls, clippedText, secondary, active: document.activeElement?.outerHTML.slice(0, 250) };
      });
      await page.screenshot({ path: path.join(out, `${width}x${height}-${name}.png`) });
      if (state.dialogs.length) {
        state.tabOutside = [];
        for (let i = 0; i < 15; i++) {
          await page.keyboard.press('Tab');
          const focus = await page.evaluate(() => ({ outside: !document.activeElement?.closest('[role="dialog"], [role="alertdialog"], dialog[open]'), text: document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent?.slice(0, 60) }));
          if (focus.outside) state.tabOutside.push({ step: i + 1, ...focus });
        }
      }
      results.push({ width, height, name, ...state });
      assert(state.documentWidth <= width, `${width}x${height} ${name}: page overflows horizontally`);
      const customModal = state.dialogs.some(dialog => ['filter-modal', 'sort-modal', 'exchange-modal', 'profile-modal'].includes(dialog.cls));
      if (customModal) assert.equal(state.tabOutside.length, 0, `${width}x${height} ${name}: focus escaped modal`);
    };
    const close = async () => { await page.keyboard.press('Escape'); await page.waitForTimeout(450); };
    const nav = name => page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name, exact: true }).click();
    await capture('exchange');
    await page.getByRole('button', { name: 'Фильтры', exact: true }).click();
    await capture('filters');
    await page.locator('.filter-modal__row').filter({ hasText: 'Цена' }).click();
    await page.locator('.filter-modal input').first().fill('10000000');
    await capture('filters-price');
    await page.locator('.filter-modal__row').filter({ hasText: 'Коллекция' }).click();
    await page.getByRole('searchbox', { name: 'Коллекция: поиск' }).fill('Artisan');
    await capture('filters-search');
    await page.locator('.filter-modal__actions button').first().click();
    await close();
    await page.locator('.exchange-page .gift-card').filter({ hasText: 'Astral Shard' }).getByRole('button', { name: 'Выбрать Astral Shard', exact: true }).click();
    await page.getByRole('tab', { name: 'Инвентарь', exact: true }).click();
    await page.locator('.exchange-page .gift-card').filter({ hasText: 'B-Day Candle' }).getByRole('button', { name: 'Выбрать B-Day Candle', exact: true }).click();
    await capture('exchange-selected');
    await page.getByRole('button', { name: 'Открыть обмен', exact: true }).click();
    await capture('exchange-modal');
    await close();
    await nav('Профиль');
    await capture('profile');
    await page.getByRole('button', { name: 'Кошелёк', exact: true }).click();
    await capture('wallet-connect');
    await page.getByPlaceholder('Адрес кошелька').fill('QA_LOCAL_WALLET_ADDRESS');
    await page.getByRole('button', { name: 'Сохранить адрес', exact: true }).click();
    await close();
    await page.getByRole('button', { name: 'Пополнить', exact: true }).click();
    await capture('deposit-choice');
    await page.locator('.profile-modal__choices button').filter({ hasText: 'CryptoBot' }).click();
    await capture('crypto-amount');
    const amount = page.locator('.profile-modal input').first();
    await amount.fill('10000.123456789');
    await amount.focus();
    await capture('crypto-amount-focused');
    await close();
    await page.getByRole('button', { name: 'Вывести', exact: true }).click();
    await capture('withdraw-choice');
    await page.locator('.profile-modal__choices button').filter({ hasText: 'Баланс' }).click();
    await capture('withdraw-amount');
    await close();
    await page.getByRole('button', { name: 'Пополнить подарки', exact: true }).click();
    await capture('gift-deposit');
    await close();
    await page.getByRole('button', { name: 'Вывести', exact: true }).click();
    await page.locator('.profile-modal__choices button').filter({ hasText: 'Подарки' }).click();
    await capture('gift-withdraw');
    await close();
    await nav('Залог');
    await capture('pledge-page');
    await page.getByRole('button', { name: 'Открыть Artisan Brick', exact: true }).click();
    await capture('pledge-terms');
    await page.locator('.pledge-terms button').first().click();
    await page.locator('.pledge-dialog footer button').click();
    await capture('pledge-confirm');
    await page.getByRole('button', { name: 'Отменить', exact: true }).click();
    await close();
    await context.close();
    fs.writeFileSync(path.join(out, 'measurements.json'), JSON.stringify(results, null, 2));
    console.log(`${width}x${height}: complete`);
  }
} finally {
  fs.writeFileSync(path.join(out, 'measurements.json'), JSON.stringify(results, null, 2));
  await browser.close();
}
console.log(`Saved ${results.length} states to ${out}`);
