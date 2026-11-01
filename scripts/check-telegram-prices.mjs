import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cache = new Map();
function load(filename) {
  if (filename.endsWith('.json')) return JSON.parse(fs.readFileSync(filename, 'utf8'));
  if (cache.has(filename)) return cache.get(filename).exports;
  const module = { exports: {} }; cache.set(filename, module);
  const localRequire = createRequire(filename);
  const require = specifier => {
    if (!specifier.startsWith('.')) return localRequire(specifier);
    const target = path.resolve(path.dirname(filename), specifier);
    const resolved = [target, target + '.ts', target + '.json'].find(candidate => fs.existsSync(candidate));
    if (!resolved) throw new Error(`Missing test dependency: ${specifier}`);
    return load(resolved);
  };
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  new Function('require', 'module', 'exports', compiled)(require, module, module.exports);
  return module.exports;
}
const { parseTelegramPrices, hasMarketPrice, marketPriceLabel, mergeMarketPrices, browsingPriceNano, compareBrowsingPrices, comparePriceAvailability, matchesBrowsingPrice } = load(path.join(root, 'src/services/telegramPrices.ts'));
const { isUnpricedGift } = load(path.join(root, 'src/pages/ExchangePage/data/gifts.ts'));
const now = 1800000000;
const fixture = () => ({ schema: 1, source: 'telegram-resale', kind: 'lowest_observed_listing', capturedAt: now - 600, validUntil: now - 600 + 86400, complete: true, collections: [{ telegramId: '18446744073709551615', catalogId: 100001, checkedAt: now - 1, status: 'available', floorNano: '5140000000', sampleCount: 200, hasMore: true }] });
const identities = { collections: [{ telegramId: '18446744073709551615', catalogId: 100001 }] };
const imported = { id: 1793443491986001, collectionId: identities.collections[0].telegramId, name: 'Collection', model: '—', image: '/original.webp', symbol: { name: 'Original' }, price: '0.000', telegramCatalog: true, priceSource: 'unpriced', tradeSupported: false, pledgeSupported: false };
let count = 0;
function test(name, run) { run(); count++; console.log(`PASS ${name}`); }
test('batch-start timestamp precedes per-collection checks', () => assert.equal(parseTelegramPrices(fixture(), now).collections[0].checkedAt, now - 1));
const invalid = [
  ['schema', f => f.schema = 2], ['source is not Stars conversion', f => f.source = 'stars-converted'], ['kind', f => f.kind = 'global_floor'], ['complete boolean', f => f.complete = 'true'],
  ['capture int', f => f.capturedAt += .5], ['capture future', f => f.capturedAt = now + 61], ['check before batch', f => f.collections[0].checkedAt = f.capturedAt - 1], ['check future', f => f.collections[0].checkedAt = now + 61], ['check at expiry', f => f.collections[0].checkedAt = f.validUntil],
  ['expiry int', f => f.validUntil += .5], ['expiry before batch', f => f.validUntil = f.capturedAt], ['TTL over24h', f => f.validUntil++],
  ['Telegram ID number', f => f.collections[0].telegramId = Number('18446744073709551615')], ['Telegram ID overflow', f => f.collections[0].telegramId = '18446744073709551616'], ['Telegram ID malformed', f => f.collections[0].telegramId = '001'],
  ['catalog int', f => f.collections[0].catalogId += .5], ['catalog below imported range', f => f.collections[0].catalogId = 20], ['catalog unsafe int', f => f.collections[0].catalogId = Number.MAX_SAFE_INTEGER + 1],
  ['nano number', f => f.collections[0].floorNano = 5.14], ['nano zero', f => f.collections[0].floorNano = '0'], ['nano negative', f => f.collections[0].floorNano = '-1'], ['nano exponent', f => f.collections[0].floorNano = '1e9'], ['nano leading zero', f => f.collections[0].floorNano = '01'], ['nano over CAP', f => f.collections[0].floorNano = '100000000000001'],
  ['sample int', f => f.collections[0].sampleCount = 1.1], ['sample negative', f => f.collections[0].sampleCount = -1], ['available needs sample', f => f.collections[0].sampleCount = 0], ['hasMore boolean', f => f.collections[0].hasMore = 1], ['available needs amount', f => f.collections[0].floorNano = null],
  ['unavailable cannot carry amount', f => f.collections[0].status = 'not_collectible'], ['unknown status', f => f.collections[0].status = 'unknown'], ['duplicate collection', f => f.collections.push({ ...f.collections[0] })],
];
for (const [name, change] of invalid) test(`reject ${name}`, () => { const f = fixture(); change(f); assert.throws(() => parseTelegramPrices(f, now)); });
test('one nano and cap are accepted exactly', () => { for (const value of ['1', '100000000000000']) { const f = fixture(); f.collections[0].floorNano = value; assert.equal(parseTelegramPrices(f, now).collections[0].floorNano, value); } });
test('unavailable statuses and incomplete feed remain valid', () => { for (const status of ['no_ton_listings', 'not_collectible', 'error']) { const f = fixture(); f.complete = false; Object.assign(f.collections[0], { status, floorNano: null, sampleCount: 0 }); parseTelegramPrices(f, now); } });
const merged = mergeMarketPrices([imported], parseTelegramPrices(fixture(), now), identities)[0];
test('owned ID, media, original attributes and financial flags preserved', () => { const { marketPrice, ...original } = merged; assert.deepEqual(original, imported); assert.equal(imported.marketPrice, undefined); assert.equal(marketPrice.floorNano, '5140000000'); assert.equal(isUnpricedGift(merged), true); });
test('exact manifest pair required; owned ID not used for lookup', () => { assert.ok(merged.marketPrice); assert.equal(mergeMarketPrices([imported], fixture(), { collections: [{ ...identities.collections[0], catalogId: 100002 }] })[0].marketPrice, undefined); assert.equal(mergeMarketPrices([imported], fixture(), null)[0].marketPrice, undefined); assert.equal(mergeMarketPrices([{ ...imported, collectionId: '123' }], fixture(), identities)[0].marketPrice, undefined); });
test('unavailable or missing feed clears previous metadata', () => { assert.equal(mergeMarketPrices([merged], null, identities)[0].marketPrice, undefined); const f = fixture(); Object.assign(f.collections[0], { status: 'no_ton_listings', floorNano: null, sampleCount: 0 }); assert.equal(mergeMarketPrices([merged], f, identities)[0].marketPrice, undefined); });
test('5.14 and single nano labels never round to zero', () => { assert.equal(marketPriceLabel(merged, now), 'от 5.14 TON'); assert.equal(marketPriceLabel({ marketPrice: { ...merged.marketPrice, floorNano: '1' } }, now), 'от 0.000000001 TON'); });
test('expiry exact boundary and stale labels', () => { const end = merged.marketPrice.validUntil; assert.equal(hasMarketPrice(merged, end - 1), true); assert.equal(hasMarketPrice(merged, end), false); assert.equal(marketPriceLabel(merged, end), 'Цена устарела'); assert.equal(marketPriceLabel({}, now), 'Нет TON-цены'); assert.equal(browsingPriceNano(merged, end), null); });
test('stale feed parses for honest outdated reference display', () => { const old = fixture(); const end = old.validUntil; parseTelegramPrices(old, end + 100); });
test('unknown or malformed metadata does not produce fake zero/stale price', () => { assert.equal(marketPriceLabel({ marketPrice: { ...merged.marketPrice, source: 'fake' } }, now + 90000), 'Нет TON-цены'); assert.equal(marketPriceLabel({ marketPrice: { ...merged.marketPrice, floorNano: '0' } }, now), 'Нет TON-цены'); });
test('sample transaction prices stay unchanged despite market reference', () => { const sample = { ...merged, telegramCatalog: false, tradeSupported: true, priceSource: 'sample', price: '2.750' }; assert.equal(browsingPriceNano(sample, now), 2750000000n); assert.equal(sample.price, '2.750'); });
test('fresh reference range uses exact nanos; unknown and stale excluded', () => { assert.equal(matchesBrowsingPrice(merged, '5.14', '5.14', now), true); assert.equal(matchesBrowsingPrice(merged, '5.140000001', '', now), false); assert.equal(matchesBrowsingPrice(imported, '', '100', now), false); assert.equal(matchesBrowsingPrice(merged, '', '100', merged.marketPrice.validUntil), false); const tiny = { ...merged, marketPrice: { ...merged.marketPrice, floorNano: '1' } }; assert.equal(matchesBrowsingPrice(tiny, '.000000001', '.000000001', now), true); });
test('unknown prices sort last in both directions', () => { for (const direction of ['asc', 'desc']) assert.equal(compareBrowsingPrices(imported, merged, direction, now), 1); const cheaper = { ...merged, marketPrice: { ...merged.marketPrice, floorNano: '1' } }; assert.equal(compareBrowsingPrices(cheaper, merged, 'asc', now), -1); assert.equal(compareBrowsingPrices(cheaper, merged, 'desc', now), 1); });
test('default catalog puts known TON prices before unpriced entries without reshuffling peers', () => {
  assert.equal(comparePriceAvailability(imported, merged, now), 1);
  assert.equal(comparePriceAvailability(merged, imported, now), -1);
  assert.equal(comparePriceAvailability(merged, { ...merged, id: 42 }, now), 0);
  assert.equal(comparePriceAvailability(imported, { ...imported, id: 43 }, now), 0);
});
test('unavailable source status is honest and cleared when a price appears', () => {
  const feed = fixture(); Object.assign(feed.collections[0], { status: 'not_collectible', floorNano: null, sampleCount: 0 });
  const missing = mergeMarketPrices([merged], feed, identities)[0];
  assert.equal(missing.marketPrice, undefined);
  assert.equal(marketPriceLabel(missing, now), 'Нет предложений в TON');
  const recovered = mergeMarketPrices([missing], fixture(), identities)[0];
  assert.equal(recovered.marketStatus, undefined);
  assert.equal(marketPriceLabel(recovered, now), 'от 5.14 TON');
  assert.equal(mergeMarketPrices([missing], null, identities)[0].marketStatus, undefined);
});
const realFile = path.join(root, 'public/gifts/telegram/prices.json');
if (fs.existsSync(realFile)) {
  test('real public feed parses and all IDs match manifest pairs', () => {
    const feed = parseTelegramPrices(JSON.parse(fs.readFileSync(realFile, 'utf8')));
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'public/gifts/telegram/catalog.json'), 'utf8'));
    const pairs = new Map(manifest.collections.map(item => [item.telegramId, item.catalogId]));
    assert.ok(feed.collections.every(item => pairs.get(item.telegramId) === item.catalogId));
    console.log(`REAL FEED complete=${feed.complete} collections=${feed.collections.length} available=${feed.collections.filter(item => item.status === 'available').length}`);
    if (process.argv.includes('--require-complete')) assert.equal(feed.complete, true);
  });
} else if (process.argv.includes('--require-complete')) throw new Error('Real prices.json is not available yet');
console.log(`${count} Telegram price checks passed`);
