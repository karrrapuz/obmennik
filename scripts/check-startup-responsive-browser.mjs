import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

await mkdir('backend/.local', { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 320, height: 844 } });
  await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.goto(process.env.RESPONSIVE_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
  await page.locator('.exchange-header').waitFor({ timeout: 30000 });
  for (const width of [320, 360, 390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    const summary = page.locator('.exchange-summary');
    for (const element of [summary, summary.locator('.exchange-summary__total'), summary.locator('.exchange-summary__active')]) {
      const box = await element.boundingBox();
      assert(box.x >= 0 && box.x + box.width <= width, `Summary fits ${width}px`);
    }
    await summary.screenshot({ path: `backend/.local/summary-readable-${width}.png` });
  }
  const header = page.locator('.exchange-ton-icon');
  assert.equal(await header.evaluate(e => getComputedStyle(e).backgroundColor), 'rgb(88, 127, 254)');
  await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Залог', exact: true }).click();
  for (const badge of await page.locator('.pledge-banner__ton').all()) {
    assert(await badge.evaluate(e => {
      const style = getComputedStyle(e);
      return style.backgroundColor === 'rgb(88, 127, 254)' || style.backgroundImage.includes('rgb(88, 127, 254)');
    }));
  }
  await page.locator('.pledge-banner').screenshot({ path: 'backend/.local/banner-blue-badges.png' });
  // Exercise the real boot gate independently of network timings.
  await page.evaluate(async () => {
    const reactModule = await import('/node_modules/.vite/deps/react.js');
    const React = reactModule.default ?? reactModule;
    const clientModule = await import('/node_modules/.vite/deps/react-dom_client.js');
    const { createRoot } = clientModule.default ?? clientModule;
    const { BootProvider, BootContent, useBootReport } = await import('/src/boot/BootProvider.tsx');
    const host = document.createElement('div');
    host.id = 'boot-test-host';
    document.body.append(host);
    window.bootTestRoot = createRoot(host);
    function Reports({ loading, error }) {
      useBootReport('auth', loading, error, () => {});
      useBootReport('inventory', loading, error, () => {});
      useBootReport('wallet', loading, error, () => {});
      useBootReport('loans', loading, error, () => {});
      return React.createElement(BootContent, null, React.createElement('div', { id: 'boot-ready-test' }, 'ready'));
    }
    window.renderBootTest = (loading, error = false, key = 'normal') => window.bootTestRoot.render(React.createElement(BootProvider, { key }, React.createElement(Reports, { loading, error })));
    window.renderBootTest(true);
  });
  await page.waitForTimeout(100);
  assert.equal(await page.locator('#boot-ready-test').count(), 0, 'Pending data keeps loading screen');
  await page.evaluate(() => window.renderBootTest(false));
  await page.locator('#boot-ready-test').waitFor({ timeout: 1000 });
  await page.evaluate(() => window.renderBootTest(false, true, 'error'));
  await page.locator('#boot-test-host [role=alert]').waitFor({ timeout: 1000 });
  await page.evaluate(() => { window.bootTestRoot.unmount(); document.querySelector('#boot-test-host').remove(); });
  console.log('Ready data opens immediately, loading/error gates preserved; summary fits 320/360/390/1280; GRAM badges blue: OK');
} finally { await browser.close(); }
