import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.FOOTER_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
    const nav = page.getByRole('navigation', { name: 'Разделы' });
    await nav.waitFor({ timeout: 30000 });
    for (const name of ['Профиль', 'Залог', 'Обмен', 'Профиль']) {
      await nav.getByRole('button', { name, exact: true }).click();
      await page.waitForTimeout(80);
      const exchangeColor = await nav.locator('.page-footer__item--exchange .page-footer__icon').evaluate(e => getComputedStyle(e).backgroundColor);
      const channels = exchangeColor.match(/[\d.]+/g).map(Number);
      assert.equal(channels[0], channels[1], 'Exchange icon must not pass through green');
      assert.equal(channels[1], channels[2], 'Exchange icon stays neutral during transitions');
      await page.waitForTimeout(400);
      assert.equal(await nav.locator('[aria-current="page"]').count(), 1);
      const active = nav.locator('[aria-current="page"]');
      const light = active.locator('.page-footer__light');
      if (name !== 'Обмен') {
        assert.equal(await light.evaluate(e => getComputedStyle(e).opacity), '1');
        assert.equal(await light.evaluate(e => new DOMMatrix(getComputedStyle(e).transform).m41), 0);
      }
      const bounds = await nav.boundingBox();
      assert(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
    }
    await page.close();
  }
  console.log('Footer navigation and stationary active highlights: OK');
} finally { await browser.close(); }
