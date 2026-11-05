import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const sample = JSON.parse(fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8'));
const initial = { revision: 0, inventory: sample.slice(0, 5).map((gift, index) => ({ ...gift, id: 101 + index, pledgeSupported: true })), pledged: [], catalog: sample };
const browser = await chromium.launch({ headless: true, ...(process.env.GIFT_BROWSER_EXECUTABLE ? { executablePath: process.env.GIFT_BROWSER_EXECUTABLE } : {}) });
try {
  for (const error of [false, true]) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    page.setDefaultTimeout(15000);
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.addInitScript(snapshot => localStorage.setItem('demo-inventory-v1', JSON.stringify(snapshot)), initial);
    await page.goto(process.env.FEEDBACK_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Выбрать Astral Shard', exact: true }).click({ timeout: 30000 });
    await page.getByRole('tab', { name: 'Инвентарь', exact: true }).click();
    await page.getByRole('button', { name: 'Выбрать B-Day Candle', exact: true }).click();
    await page.getByRole('button', { name: 'Открыть обмен', exact: true }).click();
    if (error) await page.evaluate(() => {
      const snapshot = JSON.parse(localStorage.getItem('demo-inventory-v1'));
      snapshot.inventory = snapshot.inventory.filter(gift => gift.id !== 103);
      localStorage.setItem('demo-inventory-v1', JSON.stringify(snapshot));
    });
    await page.locator('.exchange-modal__submit').click();
    const result = page.locator(`.exchange-modal[data-result="${error ? 'error' : 'success'}"]`);
    await result.waitFor({ state: 'attached' });
    const frames = await result.evaluate(node => {
      const animation = node.getAnimations().find(item => item.animationName === 'modal-feedback-sheet-in');
      if (!animation) throw new Error('Result did not start an entrance animation');
      const running = animation.playState;
      animation.pause();
      const values = [0, 150, 400].map(time => { animation.currentTime = time; return new DOMMatrix(getComputedStyle(node).transform).m42; });
      animation.currentTime = 350; animation.play();
      return { running, values };
    });
    assert.equal(frames.running, 'running');
    assert(frames.values[0] > frames.values[1] && frames.values[1] > frames.values[2]);
    assert(Math.abs(frames.values[2]) < 1);
    await page.waitForTimeout(150);
    await result.getByRole('button', { name: error ? 'Выбрать другой' : 'Вернуться к обмену', exact: true }).click();
    await result.waitFor({ state: 'detached' });
    await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Залог', exact: true }).click();
    assert.equal(await page.locator('.pledge-banner__ton--front').evaluate(node => getComputedStyle(node).backgroundColor), 'rgb(88, 127, 254)');
    const back = await page.locator('.pledge-banner__ton--back').evaluate(node => getComputedStyle(node).backgroundImage);
    assert(back.includes('rgb(88, 127, 254)') && back.includes('rgb(44, 69, 151)'));
    await page.close();
  }
  console.log('Success/error sheets animate automatically through intermediate positions and close cleanly; pledge banner circles are blue: OK');
} finally { await browser.close(); }
