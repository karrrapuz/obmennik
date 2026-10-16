import { mkdir, writeFile } from 'node:fs/promises';
const base = 'https://raw.githubusercontent.com/ssamy2/TelegramGiftsAssests/main/';
const cdn = 'https://cdn.changes.tg/gifts/';
async function get(url) { const r = await fetch(url, { signal: AbortSignal.timeout(30000) }); if (!r.ok) throw new Error(`${r.status}: ${url}`); return r; }
const catalog = await (await get(base + 'Gifts_Details.json')).json();
const colors = await (await get(cdn + 'backdrops.json')).json();
await mkdir('public/gifts/models', { recursive: true });
await mkdir('public/gifts/symbols', { recursive: true });
const result = [];
for (const collection of catalog.upgraded) {
  if (result.length === 20) break;
  try {
    const models = await (await get(base + `models/${collection.short_name}/config.json`)).json();
    const patterns = await (await get(base + `patterns/${collection.short_name}/config.json`)).json();
    const backs = await (await get(base + `backdrops/${collection.short_name}/config.json`)).json();
    const index = result.length;
    const model = models[index % models.length];
    const backdrop = backs.filter((b) => colors.some((c) => c.name === b.name))[index % Math.min(backs.length, 20)];
    if (!backdrop || !model.webp_path) continue;
    const color = colors.find((c) => c.name === backdrop.name);
    let symbol;
    for (const pattern of patterns.slice(index % 5, index % 5 + 8)) {
      try {
        const response = await get(cdn + `patterns/${encodeURIComponent(collection.full_name)}/png/${encodeURIComponent(pattern.name)}.png`);
        const file = `symbols/${index + 1}.png`;
        await writeFile('public/gifts/' + file, Buffer.from(await response.arrayBuffer()));
        symbol = { name: pattern.name, image: '/gifts/' + file, rarity: `${pattern.rarity_percent}%` }; break;
      } catch { /* Try another available symbol in this collection. */ }
    }
    if (!symbol) continue;
    const image = Buffer.from(await (await get(base + model.webp_path)).arrayBuffer());
    if (image.toString('ascii', 0, 4) !== 'RIFF') throw new Error('Invalid WebP');
    await writeFile(`public/gifts/models/${index + 1}.webp`, image);
    result.push({ id: index + 1, name: collection.full_name, collectionId: collection.regular_id, model: `#${1000 + index}`, modelName: model.name.split('_').map((s) => s[0].toUpperCase() + s.slice(1)).join(' '), image: `/gifts/models/${index + 1}.webp`, price: (2 + index * .75).toFixed(3), symbol, backdrop: { name: backdrop.name, rarity: `${backdrop.rarity_percent}%`, ...color.hex }, source: base + model.webp_path, demo: true });
    console.log(`${result.length}/20 ${collection.full_name}`);
  } catch (error) { console.warn(collection.full_name, error.message); }
}
if (result.length !== 20) throw new Error('Incomplete sample');
await writeFile('src/pages/ExchangePage/data/catalog-sample.json', JSON.stringify(result, null, 2) + '\n');
await writeFile('public/gifts/source.json', JSON.stringify({ sources: [base, cdn], importedAt: new Date().toISOString(), note: 'Demo combinations, numbers and prices; source attributes and media. Not actual owned gifts or live market listings.' }, null, 2));
