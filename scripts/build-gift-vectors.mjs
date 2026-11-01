import fs from 'node:fs/promises';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { chromium } from 'playwright';

const source = process.argv[2];
if (!source) throw new Error('Pass the directory containing approved 1.tgs..30.tgs and report.json');
const read = async file => JSON.parse(await fs.readFile(file, 'utf8'));
const cards = [...await read('backend/data/catalog-sample.json'), ...await read('backend/data/catalog-showcase-extra.json')];
const report = await read(path.join(source, 'report.json'));
const target = 'public/gifts/vector';
await fs.mkdir(`${target}/posters`, { recursive: true });
await fs.mkdir(`${target}/animations`, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.GIFT_BROWSER_EXECUTABLE ? { executablePath: process.env.GIFT_BROWSER_EXECUTABLE } : {}) });
const entries = [];
try {
  const page = await browser.newPage({ viewport: { width: 512, height: 512 } });
  await page.route('**/*', route => route.abort());
  await page.setContent('<!doctype html><div id="art" style="width:512px;height:512px"></div>');
  await page.addScriptTag({ path: 'node_modules/lottie-web/build/player/lottie_light.min.js' });
  for (const [index, card] of cards.entries()) {
    const metadata = report[index];
    if (metadata.gift !== card.name || metadata.model !== card.modelName || !/^[1-9]\d+$/.test(metadata.documentId)) throw new Error('Source model mismatch');
    const raw = await fs.readFile(path.join(source, `${index + 1}.tgs`));
    const data = JSON.parse(gunzipSync(raw, { maxOutputLength: 4_000_000 }));
    if (data.w !== 512 || data.h !== 512 || data.assets?.some(asset => 'p' in asset)) throw new Error('Pure vector model required');
    const stem = `${metadata.documentId}-${createHash('sha256').update(raw).digest('hex').slice(0, 12)}`;
    await page.evaluate(data => new Promise((resolve, reject) => {
      window.animation?.destroy();
      const animation = window.lottie.loadAnimation({ container: document.getElementById('art'), renderer: 'svg', animationData: data, autoplay: false, loop: false });
      window.animation = animation;
      const timeout = setTimeout(() => reject(new Error('Vector rendering timeout')), 5000);
      const done = () => { clearTimeout(timeout); animation.goToAndStop(Math.max(0, animation.totalFrames - 1), true); resolve(); };
      if (animation.isLoaded) done(); else animation.addEventListener('DOMLoaded', done);
    }), data);
    const svg = await page.locator('#art svg').evaluate(node => {
      node.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      node.setAttribute('width', '512'); node.setAttribute('height', '512');
      return node.outerHTML;
    });
    if (!svg.includes('<path') || /<image\b|<script\b|<foreignObject\b/i.test(svg)) throw new Error('Unexpected SVG content');
    await fs.writeFile(`${target}/posters/${stem}.svg`, svg);
    await fs.writeFile(`${target}/animations/${stem}.tgs`, raw);
    entries.push({ collectionId: card.collectionId, modelName: card.modelName, originalImage: card.image,
      poster: `/gifts/vector/posters/${stem}.svg`, animation: `/gifts/vector/animations/${stem}.tgs` });
  }
} finally { await browser.close(); }
const manifest = JSON.stringify({ schema: 1, source: 'telegram-model-documents', entries }, null, 2) + '\n';
await fs.writeFile(`${target}/manifest.json`, manifest);
await fs.writeFile('src/services/gift-media.json', manifest);
console.log(`Exported ${entries.length} pure SVG posters and original TGS animations.`);
