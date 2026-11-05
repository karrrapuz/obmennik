import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 320, height: 568 } });
  await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.goto(process.env.AMOUNT_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
  await page.locator('.exchange-header').waitFor({ timeout: 30000 });
  for (const width of [320, 360, 390, 1280]) {
    await page.setViewportSize({ width, height: 568 });
    for (const text of ['0.000', '288.440', '99999.999', '10000000.000']) {
      await page.evaluate(async text => {
        const reactModule = await import('/node_modules/.vite/deps/react.js');
        const React = reactModule.default ?? reactModule;
        const client = await import('/node_modules/.vite/deps/react-dom_client.js');
        const { createRoot } = client.default ?? client;
        const { default: AmountDigits } = await import('/src/components/gifts/AmountDigits.tsx');
        if (!window.amountRoot) {
          const host = document.createElement('div');
          host.id = 'amount-test';
          Object.assign(host.style, { position: 'fixed', top: '100px', left: '0', width: 'min(390px,100%)', zIndex: '1000', fontFamily: 'Onest,Arial,sans-serif' });
          document.body.append(host);
          window.amountRoot = createRoot(host);
        }
        const h = React.createElement;
        const icon = () => h('img', { src: '/src/assets/gram-outline.svg' });
        const digits = () => h(AmountDigits, { text });
        const offer = h('div', { className: 'exchange-summary__offer' },
          h('strong', { className: 'exchange-summary__value exchange-summary__value--offer' },
            h('span', { className: 'exchange-summary__offer-stage' },
              h('span', { className: 'exchange-summary__offer-state exchange-summary__offer-state--amount' }, icon(), digits()))));
        const receive = h('div', { className: 'exchange-summary__total' },
          h('strong', { className: 'exchange-summary__value exchange-summary__value--total' }, icon(), digits()));
        const summary = h('section', { className: 'exchange-summary', 'data-active': 'true' }, offer, receive);
        const totals = h('div', { className: 'exchange-modal__totals', style: { position: 'relative', top: '20px', left: '16px', width: 'calc(100% - 32px)' } },
          ...[1, 2].map(key => h('button', { key, className: 'exchange-modal__total', 'data-active': 'true' }, h('strong', null, icon(), digits()))));
        window.amountRoot.render(h('div', null, summary, totals));
      }, text);
      await page.waitForTimeout(40);
      const amounts = page.locator('#amount-test .amount-digits');
      assert.equal(await amounts.count(), 4);
      for (const amount of await amounts.all()) {
        const fit = await amount.evaluate(e => {
          const slot = e.closest('.exchange-summary__offer, .exchange-summary__total, .exchange-modal__total').getBoundingClientRect();
          const range = document.createRange(); range.selectNodeContents(e);
          const glyphs = range.getBoundingClientRect();
          return { text: e.textContent, fits: glyphs.left >= slot.left - 1 && glyphs.right <= slot.right + 1, width: glyphs.width, slot: slot.width };
        });
        assert.equal(fit.text, text);
        assert(fit.fits, `${width}px ${text}: ${JSON.stringify(fit)}`);
      }
    }
  }
  console.log('Exact long offer/receive amounts fit page and modal at 320/360/390/1280px: OK');
} finally { await browser.close(); }
