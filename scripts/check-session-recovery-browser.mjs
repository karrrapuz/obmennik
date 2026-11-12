import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const server = await createServer({ server: { host: '127.0.0.1', port: 0 } });
try {
  await server.listen();
  const url = server.resolvedUrls.local[0];
  const executablePath = process.env.GIFT_BROWSER_EXECUTABLE;
  const browser = await chromium.launch({ executablePath });
  try {
    const page = await browser.newPage();
    const user = { id: 42, first_name: 'Tester', last_name: null, username: null, photo_url: null, referral_code: 'test' };
    const wallet = { revision: 1, asset: 'DEMO_TON', balance_nano: '0', referral_nano: '0', transactions: [] };
    const inventory = { revision: 1, inventory: [], pledged: [], catalog: [] };
    const loans = { revision: 1, loans: [], terms: [], wallet, inventory };
    const loanWrites = [];
    const walletWrites = [];
    let authCalls = 0;
    let loanStatus = 200;
    let walletStatus = 200;
    let malformedWallet = true;
    let expireReads = false;
    const ready = () => page.locator('.exchange-header').waitFor();
    await page.addInitScript(() => {
      window.Telegram = { WebApp: { initData: 'test', platform: 'tdesktop', ready() {}, expand() {}, isVersionAtLeast: () => false } };
    });
    await page.route('https://telegram.org/**', (route) => route.fulfill({ body: '' }));
    await page.route('https://fonts.googleapis.com/**', (route) => route.abort());
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const reply = (json, status = 200) => route.fulfill({ status, json });
      switch (path) {
        case '/api/health': return reply({});
        case '/api/auth/telegram': return reply({ access_token: `token-${++authCalls}`, token_type: 'bearer', user });
        case '/api/me': return reply(user);
        case '/api/inventory': return reply(inventory);
        case '/api/wallet': return reply(wallet, expireReads ? 401 : 200);
        case '/api/loans': return reply(loans, expireReads ? 401 : 200);
        case '/api/wallet/demo-topup':
          walletWrites.push(request.headers()['idempotency-key']);
          return reply(malformedWallet ? {} : wallet, walletStatus);
        case '/api/loans/create':
          loanWrites.push(request.headers()['idempotency-key']);
          if (loanStatus === 0) return route.abort();
          return reply(loans, loanStatus);
        default: return reply({}, 404);
      }
    });
    await page.goto(url);
    await ready();
    const createLoan = () => page.evaluate(async () => {
      const { pledgeStore } = await import('/src/pages/DepositPage/services/pledgeStore.ts');
      return pledgeStore.create(123, 1);
    });
    loanStatus = 0;
    await assert.rejects(createLoan());
    loanStatus = 401;
    const loanRefreshed = page.waitForResponse((response) => response.url().endsWith('/api/me') && response.request().headers().authorization === 'Bearer token-2');
    await assert.rejects(createLoan(), /401|Сессия/);
    await loanRefreshed;
    await ready();
    assert.equal(authCalls, 2);
    assert.ok(loanWrites[0]);
    assert.deepEqual(loanWrites, [loanWrites[0], loanWrites[0]], 'Recovery must not replay the loan');
    loanStatus = 200;
    assert.equal(await createLoan(), true);
    assert.equal(loanWrites[2], loanWrites[0]);
    loanStatus = 409;
    await assert.rejects(createLoan());
    assert.notEqual(loanWrites[3], loanWrites[2]);
    await assert.rejects(createLoan());
    assert.notEqual(loanWrites[4], loanWrites[3]);

    const submitTopup = async () => {
      await page.locator('.exchange-balance__add').click();
      await page.getByRole('button', { name: 'CryptoBot' }).click();
      await page.locator('.balance-withdraw input').fill('1');
      const posted = page.waitForResponse((response) => response.url().endsWith('/api/wallet/demo-topup'));
      await page.locator('.balance-withdraw button[type=submit]').click();
      await posted;
    };
    await submitTopup(); // HTTP 200, but the wallet snapshot is invalid.
    await page.reload();
    await ready();
    walletStatus = 401;
    const refreshed = page.waitForResponse((response) => response.url().endsWith('/api/me') && response.request().headers().authorization === 'Bearer token-4');
    await submitTopup();
    await refreshed;
    await ready();
    assert.equal(walletWrites.length, 2, 'Recovery must not replay the topup');
    assert.ok(walletWrites[0]);
    assert.equal(walletWrites[1], walletWrites[0], 'The key survives a malformed response and page reload');
    walletStatus = 200;
    malformedWallet = false;
    await submitTopup();
    assert.equal(walletWrites[2], walletWrites[0]);
    await page.waitForFunction(() => !Object.keys(localStorage).some((key) => key.startsWith('obmennik:pending-mutation:')));

    expireReads = true;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.locator('.auth-error [role=alert]').waitFor();
    assert.equal(authCalls, 5, 'Concurrent 401s and a rejected replacement session must not loop');
    expireReads = false;
    await page.locator('.auth-error button').click();
    await ready();
    assert.equal(authCalls, 6);
    console.log('Wallet and loan recovery, persistent retries, and bounded concurrent 401 handling: OK');
  } finally { await browser.close(); }
} finally { await server.close(); }
