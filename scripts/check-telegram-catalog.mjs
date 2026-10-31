import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const path = 'public/gifts/telegram/catalog.json';
const raw = fs.readFileSync(path, 'utf8');
assert.equal(raw, fs.readFileSync('backend/data/catalog-telegram.json', 'utf8'));
assert.doesNotMatch(raw, /"(?:access_hash|file_reference|api_hash|session|phone)"\s*:/);
const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64');
const sample = fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8');
const giftsUrl = dataUrl(fs.readFileSync('src/pages/ExchangePage/data/gifts.ts', 'utf8')
  .replace("import sample from './catalog-sample.json';", `const sample = ${sample};`));
const service = fs.readFileSync('src/services/telegramCatalog.ts', 'utf8')
  .replace(/^import .* from 'react';\r?\n/m, '')
  .replace(/from '\.\.\/pages\/ExchangePage\/data\/gifts'/, `from '${giftsUrl}'`);
const { parseTelegramManifest, collectionGift, previewTelegramGift, telegramFilterOptions } = await import(dataUrl(service));
const { matchesGiftAttributes, giftCollectionKey } = await import(giftsUrl);
const manifest = parseTelegramManifest(JSON.parse(raw));
assert.equal(manifest.stats.metadataComplete, true, 'All collections must finish metadata import before publishing');
let mediaCount = 0;
for (const collection of manifest.collections) {
  assert.ok(['complete', 'not_available'].includes(collection.attributeStatus));
  for (const item of [collection, ...collection.attributes.models, ...collection.attributes.symbols]) {
    if (!item.image) continue;
    assert.match(item.image, /^\/gifts\/telegram\/media\/\d+\.webp$/);
    assert.ok(fs.statSync('public' + item.image).size > 0);
    mediaCount++;
  }
  const gift = collectionGift(collection);
  assert.equal(gift.tradeSupported, false);
  assert.equal(gift.pledgeSupported, false);
  const selected = { collection: [giftCollectionKey(gift)] };
  for (const group of ['models', 'symbols', 'backdrops']) selected[group] = collection.attributes[group].slice(0, 1).map(item => item.name);
  const preview = previewTelegramGift(gift, collection, selected);
  assert.ok(preview && matchesGiftAttributes(preview, selected));
  assert.equal(preview.tradeSupported, false);
}
const cards = manifest.collections.map(collectionGift);
assert.equal(telegramFilterOptions(cards, manifest, []).collection.length, cards.length);
assert.equal(new Set(cards.map(giftCollectionKey)).size, cards.length);
const invalid = structuredClone(manifest);
invalid.collections.push(invalid.collections[0]);
assert.throws(() => parseTelegramManifest(invalid));
console.log(`${cards.length} Telegram collections, ${mediaCount} media references, combined filters and unpriced previews: OK`);
