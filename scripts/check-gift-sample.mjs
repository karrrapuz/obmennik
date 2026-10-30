import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
const data = JSON.parse(fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8'));
assert.deepEqual(JSON.parse(fs.readFileSync('backend/data/catalog-sample.json', 'utf8')), data, 'Frontend and backend demo catalogs must match');
assert.equal(data.length, 20);
for (const gift of data) {
  for (const path of [gift.image, gift.symbol.image]) assert.ok(fs.readFileSync('public' + path).length > 100);
  assert.match(gift.backdrop.centerColor, /^#[a-f0-9]{6}$/i);
}
const source = fs.readFileSync('src/pages/ExchangePage/data/gifts.ts', 'utf8').replace("import sample from './catalog-sample.json';", `const sample = ${JSON.stringify(data)};`);
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { matchesGiftAttributes, getFilterOptions } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
for (const gift of data) {
  assert.ok(matchesGiftAttributes(gift, { collection: [gift.name], models: [gift.modelName], symbols: [gift.symbol.name], backdrops: [gift.backdrop.name] }));
  assert.equal(matchesGiftAttributes(gift, { collection: ['not present'] }), false);
  assert.ok(matchesGiftAttributes(gift, { collection: ['not present', gift.name], models: [] }));
}
assert.equal(getFilterOptions(data).collection.length, 20);
console.log('20 gifts, 40 local media files, colors and combined filters: OK');
