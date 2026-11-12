import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mock } from 'node:test';
import ts from 'typescript';

function moduleUrl(path, imports = {}) {
  let source = readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
  for (const [name, url] of Object.entries(imports)) source = source.replace(`'${name}'`, `'${url}'`);
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  return 'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64');
}

const storage = new Map();
Object.defineProperty(globalThis, 'localStorage', { value: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) } });
globalThis.window = new EventTarget();
mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 1700000000000 });
const walletUrl = moduleUrl('src/wallet/wallet.ts', { '../services/snapshotRevision': moduleUrl('src/services/snapshotRevision.ts') });
const { applyLocalWallet, localWalletKey, readLocalWallet } = await import(walletUrl);
const storeUrl = moduleUrl('src/pages/DepositPage/services/pledgeStore.ts', {
  '../../ExchangePage/data/gifts': 'data:text/javascript,export const isUnpricedGift = () => false;',
  '../../../wallet/wallet': walletUrl,
});
const gift = { id: 42, name: 'Test gift' };
let inventory = [gift];
let pledged = [];
let mount = 0;
async function loadStore() {
  const { pledgeStore: store } = await import(storeUrl + '#' + mount++);
  store.connectInventory(async (id, save) => {
    assert.equal(id, gift.id);
    if (!save()) return false;
    inventory = [];
    pledged = [gift];
    store.syncInventory(inventory, pledged);
    return true;
  }, async (id, save) => {
    assert.equal(id, gift.id);
    if (!save()) return false;
    inventory = [gift];
    pledged = [];
    store.syncInventory(inventory, pledged);
    return true;
  });
  store.syncInventory(inventory, pledged);
  return store;
}
function walletAction(action, body) {
  localStorage.setItem(localWalletKey, JSON.stringify(applyLocalWallet(readLocalWallet(), action, body)));
}

const week = 7 * 86400000;
let store = await loadStore();
walletAction('topup', { amount_nano: '1', source: 'wallet' });
assert.equal(await store.create(gift.id, 2), true);
assert.equal(readLocalWallet().balance_nano, '1200000001');
assert.equal(await store.repay(gift.id), false);
assert.deepEqual(pledged, [gift]);
const due = Date.now() + 2 * week;
assert.equal(store.getSnapshot().pledges[0].dueAt, due);
await store.toggleAutopay(gift.id);
mock.timers.tick(1000);
store = await loadStore();
assert.deepEqual(store.getSnapshot().pledges[0], { gift, weeks: 2, principal: 1.2, repayment: 1.28, interest: 0.08, dueAt: due, autopay: true, status: 'active' });
assert.equal(await store.payInterest(gift.id), true);
const extension = store.extend([gift.id, gift.id]);
mock.timers.tick(1800);
assert.equal(await extension, true);
store = await loadStore();
assert.equal(store.getSnapshot().pledges[0].dueAt, due + 4 * week);
assert.equal(readLocalWallet().balance_nano, '1030000001');
walletAction('topup', { amount_nano: '250000000', source: 'wallet' });
assert.equal(await store.repay(gift.id), true);
store = await loadStore();
assert.deepEqual(store.getSnapshot().pledges, []);
assert.deepEqual(store.getSnapshot().inventory, [gift]);
assert.equal(readLocalWallet().balance_nano, '1');
assert.deepEqual(readLocalWallet().transactions.filter(({ kind }) => kind.startsWith('loan_')).map(({ kind, amount_nano }) => [kind, amount_nano]), [
  ['loan_repay', '-1280000000'], ['loan_extend', '-90000000'], ['loan_interest', '-80000000'], ['loan_credit', '1200000000'],
]);
inventory = [];
pledged = [gift];
store = await loadStore();
const migratedDue = store.getSnapshot().pledges[0].dueAt;
mock.timers.tick(1000);
store = await loadStore();
assert.equal(store.getSnapshot().pledges[0].dueAt, migratedDue);
assert.equal(readLocalWallet().balance_nano, '1');
mock.timers.reset();
console.log('Guest pledge wallet, reload, extension, repayment and legacy terms: OK');
