import fs from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import { chromium } from 'playwright';

const gift = JSON.parse(await fs.readFile('src/pages/ExchangePage/data/relayer-preview.json', 'utf8'));
const data = JSON.parse(gunzipSync(await fs.readFile('public/gifts/featured/relayer-model.tgs'), { maxOutputLength: 4_000_000 }));
if (data.assets?.some(asset => 'p' in asset)) throw new Error('Pure vector gift required');
const browser = await chromium.launch({ executablePath: process.env.GIFT_BROWSER_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 512, height: 512 } });
  await page.route('**/*', route => route.abort());
  await page.setContent('<div id="art" style="width:512px;height:512px"></div>');
  await page.addScriptTag({ path: 'node_modules/lottie-web/build/player/lottie_light.min.js' });
  await page.evaluate(data => new Promise(resolve => {
    const animation = window.lottie.loadAnimation({ container: document.getElementById('art'), renderer: 'svg', animationData: data, autoplay: false, loop: false });
    const done = () => { animation.goToAndStop(animation.totalFrames - 1, true); resolve(); };
    if (animation.isLoaded) done(); else animation.addEventListener('DOMLoaded', done);
  }), data);
  const svg = await page.locator('#art svg').evaluate(node => {
    node.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    return node.outerHTML;
  });
  if (/<image\b|<script\b|<foreignObject\b/i.test(svg)) throw new Error('Unexpected SVG content');
  await fs.writeFile('public/gifts/featured/relayer-poster.svg', svg);
  const pattern = JSON.parse(gunzipSync(await fs.readFile('public/gifts/featured/relayer-pattern.tgs'), { maxOutputLength: 4_000_000 }));
  if (pattern.assets?.some(asset => 'p' in asset)) throw new Error('Pure vector pattern required');
  await page.evaluate(data => new Promise(resolve => {
    document.getElementById('art').replaceChildren();
    const animation = window.lottie.loadAnimation({ container: document.getElementById('art'), renderer: 'svg', animationData: data, autoplay: false, loop: false });
    const done = () => { animation.goToAndStop(animation.totalFrames - 1, true); resolve(); };
    if (animation.isLoaded) done(); else animation.addEventListener('DOMLoaded', done);
  }), pattern);
  const patternSvg = await page.locator('#art svg').evaluate(node => { node.setAttribute('xmlns', 'http://www.w3.org/2000/svg'); return node.outerHTML; });
  if (/<image\b|<script\b|<foreignObject\b/i.test(patternSvg)) throw new Error('Unexpected SVG content');
  await fs.writeFile('public/gifts/featured/relayer-pattern.svg', patternSvg);
  await fs.writeFile('src/services/relayer-media.json', JSON.stringify({ collectionId: gift.collectionId, modelName: gift.modelName,
    originalImage: gift.image, poster: gift.image, animation: '/gifts/featured/relayer-model.tgs', posterFrame: Math.floor(data.op - data.ip) - 1 }, null, 2) + '\n');
} finally { await browser.close(); }
