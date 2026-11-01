import fs from 'node:fs';
import assert from 'node:assert/strict';
import { gunzipSync } from 'node:zlib';
import ts from 'typescript';

const manifest = JSON.parse(fs.readFileSync('src/services/gift-media.json', 'utf8'));
assert.deepEqual(manifest, JSON.parse(fs.readFileSync('public/gifts/vector/manifest.json', 'utf8')));
assert.equal(manifest.entries.length, 30);
const cards = [...JSON.parse(fs.readFileSync('backend/data/catalog-sample.json')), ...JSON.parse(fs.readFileSync('backend/data/catalog-showcase-extra.json'))];
const source = fs.readFileSync('src/services/giftMedia.ts', 'utf8').replace("import manifest from './gift-media.json';", `const manifest = ${JSON.stringify(manifest)};`);
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { getGiftMedia, giftPoster, upgradeGiftImage } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
for (const card of cards) {
  const media = getGiftMedia(card);
  assert(media && media.originalImage === card.image);
  assert.equal(getGiftMedia({ ...card, id: 999999 }), media);
  assert.equal(giftPoster(card), media.poster);
  assert.equal(upgradeGiftImage(card.image), media.poster);
  const svg = fs.readFileSync('public' + media.poster, 'utf8');
  assert.match(svg, /<svg/); assert.match(svg, /<path/);
  assert.doesNotMatch(svg, /<image\b|<script\b|<foreignObject\b|https?:\/\/(?!www\.w3\.org\/)/i);
  const raw = fs.readFileSync('public' + media.animation);
  assert(raw.length < 100000);
  const data = JSON.parse(gunzipSync(raw, { maxOutputLength: 4000000 }));
  assert.equal(data.w, 512); assert.equal(data.h, 512);
  assert(data.op > data.ip && data.fr > 0 && data.fr <= 60);
  assert.equal(media.posterFrame, Math.floor(data.op - data.ip) - 1, 'Poster must be the actual final frame');
  assert(data.assets.every(asset => !('p' in asset)));
}
assert.equal(giftPoster({ image: '/unknown.webp', collectionId: 'unknown', modelName: 'unknown' }), '/unknown.webp');
console.log('30 exact model mappings, pure SVG posters, bounded original TGS files, owned-ID independence and safe fallback: OK');
