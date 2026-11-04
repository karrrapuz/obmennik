import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

await mkdir('backend/.local', { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.goto(process.env.GRAM_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
  await page.locator('.exchange-header').waitFor({ timeout: 30000 });
  await page.locator('.exchange-summary').screenshot({ path: 'backend/.local/gram-summary.png' });
  const nav = page.getByRole('navigation', { name: 'Разделы' });
  await nav.getByRole('button', { name: 'Залог', exact: true }).click();
  await page.getByRole('button', { name: 'Открыть Artisan Brick', exact: true }).click();
  const terms = page.locator('.pledge-terms > button');
  for (const term of await terms.all()) {
    assert.equal(await term.evaluate(e => getComputedStyle(e).clipPath), 'inset(0px round 20px)');
    const image = term.locator(':scope > img');
    await image.evaluate(e => e.decode());
    const src = await image.getAttribute('src');
    const comma = src.indexOf(',');
    const svg = src.startsWith('data:')
      ? src.slice(0, comma).endsWith(';base64') ? Buffer.from(src.slice(comma + 1), 'base64').toString() : decodeURIComponent(src.slice(comma + 1))
      : await (await page.request.get(new URL(src, page.url()).href)).text();
    assert(svg.includes('linearGradient') && svg.includes('M32'), `Gradient GRAM outline loaded: ${svg.slice(0, 200)}`);
  }
  await page.waitForTimeout(450);
  await page.locator('.pledge-terms').screenshot({ path: 'backend/.local/gram-terms.png' });
  await page.locator('.pledge-sheet header button').click();
  await page.waitForTimeout(450);
  await nav.getByRole('button', { name: 'Профиль', exact: true }).click();
  const stats = page.locator('.profile-referral__stat');
  for (const stat of await stats.all()) {
    assert.equal(await stat.evaluate(e => getComputedStyle(e).clipPath), 'inset(0px round 20px)');
  }
  await page.locator('.profile-referral').screenshot({ path: 'backend/.local/gram-referral.png' });
  console.log('GRAM outline backdrops load, rounded clips retained, summary/profile/pledge render: OK');
} finally { await browser.close(); }
