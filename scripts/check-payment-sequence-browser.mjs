import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  for (const scenario of ['success', 'error', 'closed']) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.PAYMENT_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
    await page.locator('.exchange-header').waitFor({ timeout: 30000 });
    await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Профиль', exact: true }).click();
    await page.getByRole('button', { name: 'Пополнить', exact: true }).click();
    await page.locator('.profile-modal__choices button').filter({ hasText: 'CryptoBot' }).click();
    await page.getByRole('textbox', { name: 'Сумма пополнения GRAM', exact: true }).fill('1');
    await page.waitForTimeout(400);
    await page.evaluate(error => {
      window.paymentTimeline = [];
      const layer = document.querySelector('.profile-modal-layer');
      const record = () => {
        const modal = layer.querySelector('.profile-modal');
        window.paymentTimeline.push({ time: performance.now(), kind: modal?.dataset.kind, visible: layer.dataset.visible,
          animated: modal?.getAnimations().some(a => a.animationName === 'modal-feedback-sheet-in') });
      };
      record();
      new MutationObserver(record).observe(layer, { attributes: true, subtree: true, attributeFilter: ['data-kind', 'data-visible'] });
      if (error) {
        const write = Storage.prototype.setItem;
        let armed = true;
        Storage.prototype.setItem = function(key, value) {
          if (key === 'demo-wallet-v1' && armed) { armed = false; throw new Error('Local test failure'); }
          return write.call(this, key, value);
        };
      }
    }, scenario === 'error');
    await page.locator('.profile-modal button[type=submit]').click();
    await page.locator('.profile-modal-layer[data-visible="false"]').waitFor({ state: 'attached' });
    await page.locator('.profile-modal-layer[data-visible="true"] .profile-modal[data-kind="payment-processing"]').waitFor();
    if (scenario === 'closed') {
      await page.locator('.profile-modal__close').click();
      await page.waitForTimeout(2300);
      assert.equal(await page.locator('.profile-modal').count(), 0, 'Closing processing must not reopen a result');
      await page.close();
      continue;
    }
    const result = page.locator(`.profile-modal-layer[data-visible="true"] .profile-modal[data-kind="result-${scenario}"]`);
    await result.waitFor();
    const events = await page.evaluate(() => window.paymentTimeline);
    const formExit = events.find(e => e.kind === 'crypto-amount' && e.visible === 'false');
    const processing = events.find(e => e.kind === 'payment-processing' && e.visible === 'true');
    const processingExit = events.find(e => e.kind === 'payment-processing' && e.visible === 'false' && e.time > processing.time);
    const resultEnter = events.find(e => e.kind === `result-${scenario}` && e.visible === 'true');
    assert(processing.time - formExit.time >= 350, 'Form finishes closing before processing enters');
    assert(processingExit.time - processing.time >= 1350, 'Processing remains for one full second after entering');
    assert(resultEnter.time - processingExit.time >= 350, 'Processing finishes closing before result enters');
    assert(resultEnter.animated, `Result uses entrance animation: ${JSON.stringify(events)}`);
    const balance = await page.evaluate(() => JSON.parse(localStorage.getItem('demo-wallet-v1')).balance_nano);
    assert.equal(balance, scenario === 'success' ? '1000000000' : '0');
    await page.close();
  }
  console.log('Payment form exits fully; processing lasts >=1s; real success/error result enters separately; closed UI stays closed: OK');
} finally { await browser.close(); }
