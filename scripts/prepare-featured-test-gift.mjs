import { readFile, writeFile } from 'node:fs/promises';

const file = 'src/pages/ExchangePage/data/relayer-preview.json';
const gift = JSON.parse(await readFile(file, 'utf8'));
const template = { ...gift, price: '43.950', priceSource: 'sample', tradeSupported: true, pledgeSupported: false,
  previewOnly: false, demo: true, testGrant: true };
delete template.marketPrice;
const json = JSON.stringify(template, null, 2) + '\n';
await writeFile(file, json);
await writeFile('backend/data/catalog-featured.json', json);
