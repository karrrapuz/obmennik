import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.addInitScript(() => {
    const viewport = new EventTarget();
    Object.assign(viewport, { height: 844, offsetTop: 0, scale: 1 });
    Object.defineProperty(window, 'visualViewport', { value: viewport });
    window.qaViewport = viewport;
  });
  await page.goto(process.env.KEYBOARD_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
  await page.locator('.exchange-header').waitFor({ timeout: 30000 });
  await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Профиль', exact: true }).click();
  await page.getByRole('button', { name: 'Пополнить', exact: true }).click();
  await page.locator('.profile-modal__choices button').filter({ hasText: 'CryptoBot' }).click();
  await page.locator('.profile-modal input').fill('1');
  for (const height of [460, 320, 260]) {
    await page.evaluate(height => { Object.assign(window.qaViewport, { height, offsetTop: 35, scale: 1 }); window.qaViewport.dispatchEvent(new Event('resize')); }, height);
    await page.waitForTimeout(400);
    const modal = await page.locator('.profile-modal').boundingBox();
    assert(modal.y >= 35 && modal.y + modal.height <= 35 + height + 1, 'Sheet fits visible keyboard viewport');
    const action = page.locator('.profile-modal button[type="submit"]');
    await action.scrollIntoViewIfNeeded();
    assert(await action.evaluate(e => {
      const r = e.getBoundingClientRect(); const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return e === hit || e.contains(hit);
    }), 'Submit remains reachable above keyboard');
  }
  const before = await page.evaluate(() => document.documentElement.style.getPropertyValue('--visible-height'));
  await page.evaluate(() => { Object.assign(window.qaViewport, { height: 130, scale: 2 }); window.qaViewport.dispatchEvent(new Event('resize')); });
  await page.waitForTimeout(50);
  assert.equal(await page.evaluate(() => document.documentElement.style.getPropertyValue('--visible-height')), before, 'Pinch zoom does not rewrite modal geometry');
  console.log('Keyboard visual viewport 460/320/260px keeps sheet and submit accessible; pinch zoom preserved: OK');
} finally { await browser.close(); }
