import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const sample = JSON.parse(fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8'));
const extra = JSON.parse(fs.readFileSync('src/pages/ExchangePage/data/catalog-showcase-extra.json', 'utf8'));
assert.deepEqual(extra, JSON.parse(fs.readFileSync('backend/data/catalog-showcase-extra.json', 'utf8')));
const moduleUrl = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64');
const giftsUrl = moduleUrl(fs.readFileSync('src/pages/ExchangePage/data/gifts.ts', 'utf8')
  .replace("import sample from './catalog-sample.json';", `const sample = ${JSON.stringify(sample)};`));
const source = fs.readFileSync('src/inventory/showcase.ts', 'utf8')
  .replace("import extra from '../pages/ExchangePage/data/catalog-showcase-extra.json';", `const extra = ${JSON.stringify(extra)};`)
  .replace("'../pages/ExchangePage/data/gifts'", JSON.stringify(giftsUrl));
const active = await import(moduleUrl(source.replace('import.meta.env.VITE_SHOWCASE_MODE', "'true'")));
const disabled = await import(moduleUrl(source.replace('import.meta.env.VITE_SHOWCASE_MODE', "'false'")));
const cards = active.presentationCatalog([]);
assert.equal(cards.length, 30);
assert.equal(new Set(cards.map(card => card.id)).size, 30);
assert.deepEqual(cards.map(card => card.id), Array.from({ length: 30 }, (_, i) => i + 1));
for (const card of cards) {
  assert(Number(card.price) > 0);
  assert.match(card.price, /^\d+\.\d{3}$/);
  for (const image of [card.image, card.symbol.image]) assert(fs.statSync('public' + image).size > 100);
  assert(card.modelName && card.backdrop.name && card.symbol.name);
}
const old = { id: 100000, name: 'Old preview', model: '—', price: '0.000', telegramCatalog: true };
const owned = [cards[0], old];
assert.deepEqual(active.presentationOwned(owned), [cards[0]]);
assert.equal(owned.length, 2, 'Hidden owned previews must never be deleted');
assert.equal(disabled.presentationOwned(owned), owned);
assert.equal(disabled.presentationCatalog(owned), owned);
console.log('30 priced presentation gifts, local models/symbols/backgrounds, reversible selection and unchanged ownership: OK');
