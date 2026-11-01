import fs from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import { chromium } from 'playwright';

const manifest = JSON.parse(await fs.readFile('src/services/gift-media.json', 'utf8'));
const browser = await chromium.launch({ headless: true, ...(process.env.GIFT_BROWSER_EXECUTABLE ? { executablePath: process.env.GIFT_BROWSER_EXECUTABLE } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 512, height: 512 } });
  await page.route('**/*', route => route.abort());
  await page.setContent('<div id="art" style="width:512px;height:512px"></div>');
  await page.addScriptTag({ path: 'node_modules/lottie-web/build/player/lottie_light.min.js' });
  for (const entry of manifest.entries) {
    const data = JSON.parse(gunzipSync(await fs.readFile('public' + entry.animation), { maxOutputLength: 4_000_000 }));
    const result = await page.evaluate(data => new Promise((resolve, reject) => {
      window.animation?.destroy();
      const animation = window.lottie.loadAnimation({ container: document.getElementById('art'), renderer: 'svg', animationData: data, autoplay: false, loop: false });
      window.animation = animation;
      const timer = setTimeout(() => reject(new Error('Poster rendering timeout')), 5000);
      const done = () => {
        const frame = Math.max(0, animation.totalFrames - 1);
        animation.goToAndStop(frame, true);
        const svg = document.querySelector('#art svg');
        svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        svg.setAttribute('width', '512'); svg.setAttribute('height', '512');
        clearTimeout(timer); resolve({ svg: svg.outerHTML, frame });
      };
      if (animation.isLoaded) done(); else animation.addEventListener('DOMLoaded', done);
    }), data);
    if (!result.svg.includes('<path') || /<image\b|<script\b|<foreignObject\b/i.test(result.svg)) throw new Error('Unexpected poster content');
    entry.poster = entry.poster.replace(/(?:-last)?\.svg$/, '-last.svg');
    entry.posterFrame = result.frame;
    await fs.writeFile('public' + entry.poster, result.svg);
  }
} finally { await browser.close(); }
const json = JSON.stringify(manifest, null, 2) + '\n';
await fs.writeFile('src/services/gift-media.json', json);
await fs.writeFile('public/gifts/vector/manifest.json', json);
console.log('Regenerated 30 SVG posters from the actual final animation frames.');
