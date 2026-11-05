import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.goto(process.env.EXTENSION_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
  await page.locator('.exchange-header').waitFor({ timeout: 30000 });
  const nav = page.getByRole('navigation', { name: 'Разделы' });
  await nav.getByRole('button', { name: 'Залог', exact: true }).click();
  await page.getByRole('button', { name: 'Открыть Artisan Brick', exact: true }).click();
  await page.locator('.pledge-terms button[data-weeks="2"]').click();
  await page.locator('.pledge-sheet footer button').click();
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await page.locator('.pledge-sheet[data-status=active]').waitFor();
  await page.locator('.pledge-sheet header button').click();
  await page.waitForTimeout(450);
  await page.locator('.pledge-tabs').getByRole('tab', { name: /Залог/ }).click();
  await page.getByRole('button', { name: 'Выбрать Artisan Brick', exact: true }).click();
  await page.getByRole('button', { name: 'Продлить', exact: true }).click();
  await page.locator('.pledge-pay[data-stage=review]').waitFor();
  await page.setViewportSize({ width: 320, height: 460 });
  await page.waitForTimeout(450);
  await page.getByRole('button', { name: 'Платеж по Artisan Brick', exact: true }).click();
  await page.locator('.pledge-pay__total > button').click();
  const pay = page.locator('.pledge-pay__action');
  await pay.scrollIntoViewIfNeeded();
  const box = await pay.boundingBox();
  assert(box.x >= 0 && box.x + box.width <= 320 && box.y >= 0 && box.y + box.height <= 460);
  await page.screenshot({ path: 'backend/.local/extension-small-expanded.png' });
  await pay.click();
  await page.locator('.pledge-pay[data-stage=success]').waitFor({ timeout: 15000 });
  await page.getByRole('button', { name: 'Вернуться назад', exact: true }).click();
  await page.locator('.pledge-pay-dialog').waitFor({ state: 'detached' });
  console.log('Expanded pledge extension at 320x460: payment reachable, local demo succeeds, dialog closes: OK');
} finally { await browser.close(); }
