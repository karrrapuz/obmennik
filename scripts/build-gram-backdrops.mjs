import { readFile, writeFile } from 'node:fs/promises';

const source = await readFile(new URL('../src/assets/gram-outline.svg', import.meta.url), 'utf8');
for (const [name, color] of [['green', '#AAFFE9'], ['blue', '#C7D4FF']]) {
  const gradient = `<defs><linearGradient id="ink" x1="0" y1="0" x2="0" y2="100" gradientUnits="userSpaceOnUse"><stop stop-color="${color}"/><stop offset=".5" stop-color="${color}" stop-opacity=".5"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>`;
  const svg = source.replaceAll('"white"', '"url(#ink)"').replace('</svg>', `${gradient}</svg>`);
  await writeFile(new URL(`../src/assets/gram-outline-${name}.svg`, import.meta.url), svg);
}
