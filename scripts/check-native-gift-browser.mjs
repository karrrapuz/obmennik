import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.addInitScript(() => {
    window.openedTelegramLinks = [];
    window.Telegram = { WebApp: { platform: 'unknown', initData: '', openTelegramLink: url => window.openedTelegramLinks.push(url) } };
  });
  const base = process.env.NATIVE_GIFT_TEST_URL || 'http://127.0.0.1:5190';
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.locator('.exchange-header').waitFor({ timeout: 30000 });
  assert((await page.locator('.gift-card').first().innerText()).includes('Voodoo Doll'));
  assert(await page.locator('.gift-card').first().locator('.gift-card__select').isDisabled(), 'Public profile display is not custody or a tradable asset');
  const poster = page.locator('.gift-card').first().locator('.catalog-artwork > img');
  await poster.evaluate(image => image.decode());
  assert(await poster.evaluate(image => image.naturalWidth > 0 && image.dataset.vector === 'true'));
  await page.locator('.gift-card').first().screenshot({ path: 'backend/.local/featured-relayer-gift.png' });
  await page.getByRole('button', { name: 'Открыть Voodoo Doll', exact: true }).click();
  const details = page.locator('.gift-details');
  assert((await details.innerText()).includes('Chromed Out'));
  await details.getByRole('button', { name: 'Посмотреть', exact: true }).click();
  assert.equal(await page.evaluate(() => window.openedTelegramLinks.at(-1)), 'https://t.me/nft/VoodooDoll-6565');
  await details.getByRole('button', { name: 'Поделиться', exact: true }).click();
  const share = new URL(await page.evaluate(() => window.openedTelegramLinks.at(-1)));
  assert.equal(share.pathname, '/share/url');
  assert.equal(share.searchParams.get('url'), 'https://t.me/obmen_huikin_bot?startapp=gift_90001');
  assert(share.searchParams.get('text').includes('Voodoo Doll #6565'));
  await page.goto(`${base}/?startapp=gift_90001`, { waitUntil: 'domcontentloaded' });
  await page.locator('.gift-details[open]').waitFor({ timeout: 30000 });
  assert((await page.locator('.gift-details').innerText()).includes('Voodoo Doll'));
  await page.locator('.gift-details__header .gift-details__close').click();
  await page.waitForTimeout(450);
  await page.getByRole('button', { name: 'Открыть Astral Shard', exact: true }).click();
  await details.getByRole('button', { name: 'Посмотреть', exact: true }).click();
  assert.equal(await page.evaluate(() => window.openedTelegramLinks.at(-1)), 'https://t.me/nft/VoodooDoll-6565');
  console.log('Featured real gift first; native NFT links, Telegram share selector URL and incoming gift link: OK (native calls mocked, nothing sent)');
} finally { await browser.close(); }
