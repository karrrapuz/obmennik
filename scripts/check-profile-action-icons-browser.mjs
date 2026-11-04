import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

await mkdir('backend/.local', { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.GIFT_BROWSER_EXECUTABLE ? { executablePath: process.env.GIFT_BROWSER_EXECUTABLE } : {}) });
try {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.PROFILE_ICONS_TEST_URL || 'http://127.0.0.1:5188', { waitUntil: 'domcontentloaded' });
    await page.locator('.exchange-header').waitFor({ timeout: 30000 });
    await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Профиль', exact: true }).click();
    const actions = page.locator('.profile-actions');
    const icons = actions.locator('.profile-actions__arrow');
    assert.equal(await icons.count(), 2);
    for (const icon of await icons.all()) {
      await icon.evaluate(image => image.decode());
      assert.equal(await icon.evaluate(image => image.naturalWidth), 24);
      const url = await icon.getAttribute('src');
      const comma = url.indexOf(',');
      const source = url.startsWith('data:')
        ? url.slice(0, comma).endsWith(';base64') ? Buffer.from(url.slice(comma + 1), 'base64').toString('utf8') : decodeURIComponent(url.slice(comma + 1))
        : await (await page.request.get(new URL(url, page.url()).href)).text();
      assert(!source.includes('#666666'));
      assert(source.includes('#06D7A0'));
    }
    assert(!/[↙↗]/u.test(await actions.innerText()), 'No platform-dependent emoji arrows');
    await actions.screenshot({ path: `backend/.local/profile-actions-${width}.png` });
    await actions.getByRole('button', { name: 'Пополнить', exact: true }).click();
    await page.getByRole('dialog', { name: 'Пополнение', exact: true }).waitFor();
    await page.locator('.profile-modal').getByRole('button', { name: 'Закрыть окно', exact: true }).click();
    await page.waitForTimeout(400);
    await actions.getByRole('button', { name: 'Вывести', exact: true }).click();
    await page.getByRole('dialog', { name: 'Вывод', exact: true }).waitFor();
    await page.close();
  }
  console.log('Profile SVG action icons render without export background; deposit/withdraw actions intact: OK');
} finally { await browser.close(); }
