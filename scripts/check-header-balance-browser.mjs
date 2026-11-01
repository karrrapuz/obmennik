import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true, ...(process.env.GIFT_BROWSER_EXECUTABLE ? { executablePath: process.env.GIFT_BROWSER_EXECUTABLE } : {}) });
try {
  for (const width of [320, 390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.HEADER_TEST_URL || 'http://127.0.0.1:5185', { waitUntil: 'domcontentloaded' });
    await page.locator('.exchange-header').waitFor({ timeout: 30000 });
    const measurements = await page.locator('.exchange-header').evaluate(header => {
      const amount = header.querySelector('.exchange-balance__amount');
      const original = amount.textContent;
      const result = ['0.00', '100000.00', '999999999.99', '0.00'].map(value => {
        amount.textContent = value;
        const badge = header.querySelector('.exchange-balance').getBoundingClientRect();
        const number = amount.getBoundingClientRect();
        const add = header.querySelector('.exchange-balance__add').getBoundingClientRect();
        const user = header.querySelector('.exchange-user').getBoundingClientRect();
        const bounds = header.getBoundingClientRect();
        return { value, width: badge.width, fits: number.right + 7 <= add.left + .1 && user.right + 12 <= badge.left + .1 && badge.right <= bounds.right + .1 };
      });
      amount.textContent = original;
      return result;
    });
    assert.equal(measurements[0].width, 140);
    assert.equal(measurements[3].width, 140, 'Badge returns to its original size after a withdrawal');
    assert(measurements[2].width > 140, 'Large amounts expand naturally');
    assert(measurements.every(result => result.fits), JSON.stringify({ width, measurements }));
    await page.close();
  }
  console.log('Header balance: 140px baseline, natural expansion and shrink, no overlap at 320/390/1280px: OK');
} finally { await browser.close(); }
