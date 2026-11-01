import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const url = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64');
const revision = url(fs.readFileSync('src/services/snapshotRevision.ts', 'utf8'));
const wallet = url(fs.readFileSync('src/wallet/wallet.ts', 'utf8').replace('../services/snapshotRevision', revision));
const { tradeDisplayTotals: totals } = await import(url(fs.readFileSync('src/pages/ExchangePage/services/tradeDisplay.ts', 'utf8').replace('../../../wallet/wallet', wallet)));
const offer = [{ id: 101, price: '2.000' }];
const receive = [{ id: 2, price: '2.750' }, { id: 3, price: '3.500' }];
assert.deepEqual(totals([], [], null), { offeredNano: 0n, receivedNano: 0n, requiredNano: 0n });
assert.equal(totals([], receive, null).receivedNano, 6250000000n);
assert.equal(totals(offer, [], null).offeredNano, 2000000000n);
assert.equal(totals(offer, receive, null).requiredNano, 4250000000n);
const quote = { expires_at: Math.floor(Date.now() / 1000) + 60, offered: [{ gift_id: 101 }], received: [{ catalog_id: 2 }, { catalog_id: 3 }], offered_nano: '2000000000', received_nano: '6562500000' };
assert.equal(totals(offer, receive, quote).receivedNano, 6562500000n);
assert.equal(totals(offer, receive.slice(0, 1), quote).receivedNano, 2750000000n);
assert.equal(totals([], receive, quote).offeredNano, 0n);
assert.equal(totals(offer, receive, { ...quote, expires_at: 1 }).receivedNano, 6250000000n);
assert.equal(totals([], [{ id: 5, price: '0.000000001' }], null).receivedNano, 1n);
const modal = fs.readFileSync('src/pages/ExchangePage/components/ExchangeModal/ExchangeModal.tsx', 'utf8');
assert(!modal.includes('exchange-modal__quote'));
assert(!modal.includes('markup_bps'));
assert(modal.includes('!trade.canExecute'));
console.log('Immediate partial-selection totals, authoritative quotes, stale quote rejection and execution guard: OK');
