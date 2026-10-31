import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText).toString('base64');
const sample = fs.readFileSync('src/pages/ExchangePage/data/catalog-sample.json', 'utf8');
const giftsUrl = dataUrl(fs.readFileSync('src/pages/ExchangePage/data/gifts.ts', 'utf8').replace("import sample from './catalog-sample.json';", `const sample = ${sample};`));
const service = fs.readFileSync('src/services/telegramCatalog.ts', 'utf8').replace(/^import .* from 'react';\r?\n/m, '').replace(/from '\.\.\/pages\/ExchangePage\/data\/gifts'/, `from '${giftsUrl}'`);
const { collectionGift, previewTelegramGift, telegramFilterOptions, telegramAttributeKey, nameTelegramGifts, applyTelegramLabels } = await import(dataUrl(service));
const { matchesGiftAttributes, gifts } = await import(giftsUrl);
const manifest = JSON.parse(fs.readFileSync('public/gifts/telegram/catalog.json', 'utf8'));
const cards = manifest.collections.map(collectionGift);
const options = telegramFilterOptions(cards, manifest, []);
for (const kind of ['models', 'symbols', 'backdrops']) {
  const ids = new Set(manifest.collections.flatMap(c => c.attributes[kind].map(a => telegramAttributeKey(kind, c.telegramId, a.id))));
  assert.equal(options[kind].length, ids.size);
  assert.deepEqual(new Set(options[kind].map(o => o.value)), ids);
}
const seen = new Map();
let collisionChecked = false;
for (const c of manifest.collections) {
  const selected = { collection: [`telegram:${c.telegramId}`] };
  for (const kind of ['models', 'symbols', 'backdrops']) selected[kind] = c.attributes[kind].slice(-1).map(a => telegramAttributeKey(kind, c.telegramId, a.id));
  const preview = previewTelegramGift(collectionGift(c), c, selected);
  assert.ok(preview && matchesGiftAttributes(preview, selected));
  assert.equal(preview.tradeSupported, false);
  assert.equal(preview.pledgeSupported, false);
  for (const model of c.attributes.models) {
    const prior = seen.get(model.name);
    if (!collisionChecked && prior && prior.telegramId !== c.telegramId) {
      assert.equal(previewTelegramGift(collectionGift(c), c, { models: [telegramAttributeKey('models', prior.telegramId, prior.model.id)] }), null);
      const scoped = telegramFilterOptions(cards, manifest, [`telegram:${c.telegramId}`]);
      assert.ok(!scoped.models.some(o => o.value === telegramAttributeKey('models', prior.telegramId, prior.model.id)));
      collisionChecked = true;
    }
    seen.set(model.name, { telegramId: c.telegramId, model });
  }
}
assert.ok(collisionChecked);
const realCollection = manifest.collections.find(c => c.attributes.models.length > 1);
const ownedActual = { ...collectionGift(realCollection), id: 9999999, modelName: realCollection.attributes.models[0].name, modelFilterId: telegramAttributeKey('models', realCollection.telegramId, realCollection.attributes.models[0].id), image: realCollection.attributes.models[0].image };
const notOwnedModel = { models: [telegramAttributeKey('models', realCollection.telegramId, realCollection.attributes.models[1].id)] };
assert.equal(previewTelegramGift(ownedActual, realCollection, notOwnedModel, 'inventory'), ownedActual);
assert.equal(matchesGiftAttributes(ownedActual, notOwnedModel), false);
assert.ok(matchesGiftAttributes(ownedActual, { models: [ownedActual.modelFilterId] }));
assert.ok(matchesGiftAttributes(gifts[0], { models: [gifts[0].modelName] }));
const labels = JSON.parse(fs.readFileSync('public/gifts/telegram/labels.json', 'utf8'));
assert.equal(fs.readFileSync('public/gifts/telegram/labels.json', 'utf8'), fs.readFileSync('backend/data/catalog-labels.json', 'utf8'));
const labeled = applyTelegramLabels(manifest, labels);
assert.notEqual(labeled, manifest);
assert.throws(() => applyTelegramLabels(manifest, { ...labels, labels: [labels.labels[0], labels.labels[0]] }));
assert.throws(() => applyTelegramLabels(manifest, { schema: 1, labels: [{ ...labels.labels[0], displayTitle: 'bad\nname' }] }));
for (const collection of labeled.collections) if (collection.sourceTitle) assert.equal(collection.title, collection.sourceTitle);
for (const kind of ['symbols', 'backdrops']) {
  for (const option of options[kind]) {
    const rarities = new Set(manifest.collections.flatMap(c => c.attributes[kind].filter(a => telegramAttributeKey(kind, c.telegramId, a.id) === option.value).map(a => a.rarity)));
    if (rarities.size > 1) assert.equal(option.rarity, undefined);
  }
}
assert.equal(labels.labels.length, manifest.collections.filter(c => !c.sourceTitle).length);
for (const label of labels.labels) {
  const c = manifest.collections.find(c => c.telegramId === label.telegramId);
  assert.ok(c && !c.sourceTitle);
  assert.equal(label.kind, 'descriptive');
  assert.match(label.displayTitle, /^[\x20-\x7e]+$/, 'Descriptive gift names must be English');
  const named = { ...manifest, collections: [{ ...c, title: label.displayTitle }] };
  const owned = { ...collectionGift(c), id: 987654321 };
  assert.equal(nameTelegramGifts([owned], named)[0].name, label.displayTitle);
  assert.equal(nameTelegramGifts([owned], named)[0].id, owned.id);
  assert.equal(nameTelegramGifts([owned], labeled)[0].name, label.displayTitle);
  assert.equal(nameTelegramGifts([owned], labeled)[0].price, owned.price);
  assert.equal(nameTelegramGifts([owned], labeled)[0].tradeSupported, false);
}
console.log(`Verified ${cards.length} collections, ${options.models.length} models, ${options.symbols.length} symbols, ${options.backdrops.length} backdrops, ${labels.labels.length} descriptive names; collision/scoping/combined previews/owned IDs passed.`);
