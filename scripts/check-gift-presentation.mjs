import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const source = fs.readFileSync('src/services/giftPresentation.ts', 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { getGiftPresentation } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const catalog = JSON.parse(fs.readFileSync('public/gifts/telegram/catalog.json', 'utf8'));
const sample = JSON.parse(fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8'));
const freeze = value => {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) freeze(child);
  }
  return value;
};
const colors = new Set(catalog.collections.flatMap(collection => collection.attributes.backdrops.map(backdrop =>
  JSON.stringify([backdrop.centerColor, backdrop.edgeColor, backdrop.patternColor, backdrop.textColor]))));
const variants = new Set();
for (const collection of catalog.collections) {
  const gift = freeze({ id: collection.catalogId, telegramCatalog: true, collectionId: collection.telegramId });
  const before = JSON.stringify(gift);
  const result = getGiftPresentation(gift);
  assert.deepEqual(result, getGiftPresentation({ ...gift, id: 9999999 }));
  assert.equal(JSON.stringify(gift), before);
  assert.ok(result.backdrop);
  assert.equal(result.symbol, undefined);
  const colorKey = JSON.stringify(Object.values(result.backdrop));
  assert.ok(colors.has(colorKey), 'Decorative colors must come from the existing Telegram palette');
  variants.add(colorKey);
  assert.equal(gift.backdrop, undefined);
  assert.equal(gift.symbol, undefined);
  assert.equal(gift.presentation, undefined);
}
assert.equal(variants.size, 8);
for (const gift of sample) {
  const result = getGiftPresentation(freeze(gift));
  assert.equal(result.backdrop, gift.backdrop);
  assert.equal(result.symbol, gift.symbol);
}
const imported = { telegramCatalog: true, collectionId: '1234' };
const decorative = freeze({ kind: 'decorative', backdrop: { centerColor: '#112233', edgeColor: '#223344', patternColor: '#334455', textColor: '#445566' }, symbol: { image: '/gifts/telegram/media/example.webp' } });
assert.equal(getGiftPresentation({ ...imported, presentation: decorative }).backdrop, decorative.backdrop);
assert.equal(getGiftPresentation({ ...imported, presentation: decorative }).symbol, decorative.symbol);
const backdrop = freeze({ ...decorative.backdrop, name: 'Actual backdrop', rarity: '1%' });
const symbol = freeze({ image: '/actual.webp', name: 'Actual symbol', rarity: '2%' });
const actual = freeze({ ...imported, presentation: decorative, backdrop, symbol });
assert.equal(getGiftPresentation(actual).backdrop, backdrop);
assert.equal(getGiftPresentation(actual).symbol, symbol);
assert.equal(getGiftPresentation({ ...imported, backdrop, presentation: decorative }).symbol, decorative.symbol);
assert.equal(getGiftPresentation({ ...imported, symbol }).symbol, symbol);
for (const invalid of [null, {}, { kind: 'decorative' }, { ...decorative, backdrop: null }, { ...decorative, backdrop: { ...decorative.backdrop, centerColor: 'url(unsafe)' } }]) {
  assert.deepEqual(getGiftPresentation({ ...imported, presentation: invalid }), getGiftPresentation(imported));
}
for (const invalidSymbol of [null, {}, [], 123, 'symbol', { image: null }, { image: 42 }, { image: '' }, ...[
  'javascript:alert(1)', 'data:image/svg+xml,test', 'file:///private.svg', '//example.com/mask.svg',
  'http://example.com/mask.svg', 'relative.webp', '/mask".svg', '/mask).svg', '/mask\\test.svg', '/mask\n.svg',
  '/mask\u0000.svg', 'https://user:password@example.com/mask.svg', 'https://',
].map(image => ({ image }))]) {
  const presentation = freeze({ ...decorative, symbol: invalidSymbol });
  const gift = freeze({ ...imported, presentation });
  const before = JSON.stringify(gift);
  const result = getGiftPresentation(gift);
  assert.equal(result.backdrop, decorative.backdrop, 'An invalid decorative symbol must not discard the background');
  assert.equal(result.symbol, undefined);
  assert.equal(JSON.stringify(gift), before);
  assert.equal(getGiftPresentation({ ...gift, symbol }).symbol, symbol, 'Actual symbols always win');
}
for (const image of ['/assets/mask.svg', 'https://example.com/gifts/mask.webp']) {
  const presentation = freeze({ ...decorative, symbol: { image } });
  assert.equal(getGiftPresentation({ ...imported, presentation }).symbol, presentation.symbol);
}
assert.ok(getGiftPresentation({ collectionId: '1234', priceSource: 'unpriced' }).backdrop);
assert.equal(getGiftPresentation({ collectionId: '1234', presentation: decorative }).backdrop, undefined);
assert.equal(getGiftPresentation({ telegramCatalog: true }).backdrop, undefined);
assert.equal(getGiftPresentation({ collectionId: '1234', tradeSupported: false }).backdrop, undefined);
console.log(`Gift presentation checks passed: ${catalog.collections.length} imported gifts, ${sample.length} unchanged sample gifts, 8 existing palettes, real-trait priority, immutable inputs.`);
