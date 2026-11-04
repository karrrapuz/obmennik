import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  for (const height of [600, 844]) {
    const page = await browser.newPage({ viewport: { width: 390, height } });
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.LAYOUT_TEST_URL || 'http://127.0.0.1:5190', { waitUntil: 'domcontentloaded' });
    await page.locator('.exchange-header').waitFor({ timeout: 30000 });
    await page.getByRole('navigation', { name: 'Разделы' }).getByRole('button', { name: 'Профиль', exact: true }).click();
    await page.getByRole('button', { name: 'Пополнить', exact: true }).click();
    await page.locator('.profile-modal__choices button').first().click();
    await page.locator('.profile-modal[data-kind="wallet-warning"]').waitFor();
    await page.getByRole('button', { name: 'Выбрать', exact: true }).click();
    const sheet = page.locator('.profile-modal[data-kind="wallet-connect"]');
    await sheet.waitFor();
    await page.waitForTimeout(500);
    const bounds = await sheet.boundingBox();
    const button = await sheet.getByRole('button', { name: 'Сохранить адрес' }).boundingBox();
    assert(bounds.height < 280, `Wallet sheet should fit content: ${bounds.height}`);
    assert(bounds.y >= 24);
    assert(Math.abs(bounds.y + bounds.height - height) < 2);
    assert(height - button.y - button.height < 70, 'No large gap below wallet action');
    await page.close();
  }
  console.log('Wallet sheet fits content on short and tall mobile viewports: OK');
} finally { await browser.close(); }
