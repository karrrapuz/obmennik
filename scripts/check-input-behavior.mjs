import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const [home, styles, main, html] = await Promise.all([
  read('src/pages/HomePage/HomePage.tsx'),
  read('src/styles/input-behavior.css'),
  read('src/main.tsx'),
  read('index.html'),
]);

assert.doesNotMatch(home, /useLayoutEffect|entryDirection|pageView|\.animate\s*\(/);
for (const handler of ['onTouchStart', 'onTouchMove', 'onTouchEnd', 'onTouchCancel']) {
  assert.ok(home.includes(handler), `${handler} must remain available`);
}
assert.match(home, /if \(nextPage\) navigate\(nextPage\)/);
assert.match(home, /<PageFooter active=\{activePage\} onNavigate=\{navigate\}/);
assert.match(styles, /@media\s*\(hover:\s*none\)\s+and\s+\(pointer:\s*coarse\)/);
assert.match(styles, /input\s*,\s*textarea\s*,\s*select\s*\{/);
assert.match(styles, /font-size:\s*max\(16px,\s*1em\)\s*!important/);
assert.doesNotMatch(styles, /touch-action|transform|zoom\s*:|width\s*:|height\s*:/);
assert.match(main, /import ['"]\.\/styles\/input-behavior\.css['"]/);
const viewport = html.match(/<meta\s+name="viewport"\s+content="([^"]+)"/i)?.[1];
assert.ok(viewport, 'Viewport declaration must exist');
assert.doesNotMatch(viewport, /user-scalable\s*=\s*(no|0)|maximum-scale\s*=/i);
console.log('Input/navigation source regression checks passed.');
