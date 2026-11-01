import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { createHash } from 'node:crypto';
import { mkdir } from 'node:fs/promises';
const url = process.env.GIFT_TEST_URL || 'http://127.0.0.1:5180';
const hash = buffer => createHash('sha256').update(buffer).digest('hex');
await mkdir('backend/.local', { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.GIFT_BROWSER_EXECUTABLE ? { executablePath: process.env.GIFT_BROWSER_EXECUTABLE } : {}) });
try {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: width === 390 ? 3 : 1, isMobile: width === 390, hasTouch: width === 390 });
    const animations = [], players = [];
    page.on('request', request => {
      if (request.url().includes('/gifts/vector/animations/')) animations.push(request.url());
      if (request.url().includes('lottie_light')) players.push(request.url());
    });
    await page.route('https://telegram.org/js/**', route => route.fulfill({ body: '' }));
    await page.addInitScript(() => {
      window.__entryAnimations = [];
      const animate = Element.prototype.animate;
      Element.prototype.animate = function(...args) {
        if (this.matches('.gift-card,.exchange-summary,.exchange-toolbar,.profile-balance,.profile-content > section,.pledge-card,.pledge-banner')) window.__entryAnimations.push(this.className);
        return animate.apply(this, args);
      };
    });
    await page.goto(url);
    await page.waitForFunction(() => document.querySelectorAll('.gift-card').length === 30, null, { timeout: 45000 });
    const card = page.locator('.gift-card').filter({ has: page.getByRole('button', { name: 'Выбрать Astral Shard', exact: true }) });
    const art = card.locator('.catalog-artwork');
    await page.waitForFunction(() => [...document.querySelectorAll('.gift-card .catalog-artwork > img')].slice(0, 2).every(img => img.complete && img.naturalWidth === 512 && img.src.endsWith('.svg')));
    assert.equal(animations.length, 0); assert.equal(players.length, 0);
    const select = card.getByRole('button', { name: 'Выбрать Astral Shard', exact: true });
    await select.click();
    await art.locator('.catalog-artwork__animation[data-playing="true"] svg').waitFor();
    assert((await art.locator('svg path').count()) > 0);
    const first = hash(await art.screenshot());
    await page.waitForTimeout(450);
    assert.notEqual(hash(await art.screenshot()), first, 'Actual rendered frames must change');
    await art.locator('svg').waitFor({ state: 'detached', timeout: 6000 });
    assert.equal(await art.locator('img').evaluate(img => getComputedStyle(img).visibility), 'visible');
    await select.click(); await select.click();
    await art.locator('.catalog-artwork__animation[data-playing="true"] svg').waitFor();
    assert.equal(animations.length, 1, 'Decoded animation must be reused');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await art.locator('svg').waitFor({ state: 'detached' });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await select.click(); await select.click();
    await art.locator('.catalog-artwork__animation[data-playing="true"] svg').waitFor();
    await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Профиль', exact: true }).click();
    await art.locator('svg').waitFor({ state: 'detached' });
    await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Обмен', exact: true }).click();
    await page.waitForTimeout(300);
    assert.equal(await art.locator('svg').count(), 0, 'Navigation must not replay a selection');
    assert.deepEqual(await page.evaluate(() => window.__entryAnimations), []);
    for (const name of ['B-Day Candle', 'Berry Box', 'Big Year']) await page.getByRole('button', { name: `Выбрать ${name}`, exact: true }).click();
    assert(await page.locator('.catalog-artwork__animation svg').count() <= 1, 'Only one player may exist');
    await page.locator('.gift-card').last().scrollIntoViewIfNeeded();
    await page.waitForFunction(() => document.querySelectorAll('.catalog-artwork__animation svg').length === 0);
    await card.scrollIntoViewIfNeeded();
    if (width === 390) {
      const input = page.locator('.exchange-search input');
      assert(await input.evaluate(node => parseFloat(getComputedStyle(node).fontSize)) >= 16);
      await input.fill('Astral');
      assert.equal(await page.evaluate(() => visualViewport.scale), 1);
      await input.fill(''); await input.blur();
      assert.equal(await page.evaluate(() => visualViewport.scale), 1);
    }
    await page.screenshot({ path: `backend/.local/vector-gifts-${width}.png` });
    await page.close();
  }
  const reduced = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  let requests = 0;
  reduced.on('request', request => { if (request.url().includes('/gifts/vector/animations/')) requests++; });
  await reduced.route('https://telegram.org/js/**', route => route.fulfill({ body: '' }));
  await reduced.goto(url);
  await reduced.getByRole('button', { name: 'Выбрать Astral Shard', exact: true }).click({ timeout: 45000 });
  await reduced.waitForTimeout(500);
  assert.equal(requests, 0);
  assert.equal(await reduced.locator('.catalog-artwork__animation svg').count(), 0);
  await reduced.close();
  const fallback = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await fallback.route('https://telegram.org/js/**', route => route.fulfill({ body: '' }));
  await fallback.route('**/gifts/vector/animations/**', route => route.fulfill({ status: 503, body: '' }));
  await fallback.goto(url);
  const fallbackSelect = fallback.getByRole('button', { name: 'Выбрать Astral Shard', exact: true });
  await fallbackSelect.click({ timeout: 45000 });
  await fallback.waitForTimeout(700);
  assert.equal(await fallbackSelect.getAttribute('aria-pressed'), 'true');
  assert.equal(await fallback.locator('.catalog-artwork__animation svg').count(), 0);
  const fallbackImage = fallback.locator('.gift-card').filter({ has: fallbackSelect }).locator('.catalog-artwork > img');
  assert((await fallbackImage.getAttribute('src')).endsWith('.svg'));
  assert.equal(await fallbackImage.evaluate(img => getComputedStyle(img).visibility), 'visible');
  await fallback.close();
  console.log('PASS mobile/desktop: SVG quality, no idle animation downloads, visible one-shot playback, cache reuse, hidden-page cleanup, no page entry motion, mobile input sizes and reduced-motion fallback.');
} finally { await browser.close(); }
