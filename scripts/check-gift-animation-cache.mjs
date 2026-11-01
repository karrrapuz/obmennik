import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
const code = ts.transpileModule(fs.readFileSync('src/services/giftAnimation.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { loadGiftAnimation, claimGiftPlayback } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const entries = JSON.parse(fs.readFileSync('src/services/gift-media.json')).entries;
const originalFetch = globalThis.fetch;
let calls = 0;
globalThis.fetch = async (url, options) => {
  calls++;
  options.signal.throwIfAborted();
  return new Response(fs.readFileSync('public' + url));
};
try {
  const signal = new AbortController().signal;
  const first = await loadGiftAnimation(entries[0].animation, signal);
  first.w = 1;
  assert.equal((await loadGiftAnimation(entries[0].animation, signal)).w, 512, 'Player mutations cannot poison cached data');
  assert.equal(calls, 1);
  for (const entry of entries.slice(1, 5)) await loadGiftAnimation(entry.animation, signal);
  assert.equal(calls, 5);
  await loadGiftAnimation(entries[0].animation, signal);
  assert.equal(calls, 6, 'Oldest decoded animation must be evicted at four entries');
  await assert.rejects(loadGiftAnimation('https://example.com/asset.tgs', signal));
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(loadGiftAnimation(entries[6].animation, aborted.signal));
  globalThis.fetch = async () => new Response(new Uint8Array(100001));
  await assert.rejects(loadGiftAnimation(entries[7].animation, signal), /size limit/);
  let stopped = 0;
  const releaseFirst = claimGiftPlayback(() => stopped++);
  const releaseSecond = claimGiftPlayback(() => stopped++);
  assert.equal(stopped, 1);
  releaseFirst();
  const releaseThird = claimGiftPlayback(() => stopped++);
  assert.equal(stopped, 2, 'Old cleanup cannot revoke a newer playback lease');
  releaseSecond();
  const releaseFourth = claimGiftPlayback(() => stopped++);
  assert.equal(stopped, 3);
  releaseThird(); releaseFourth();
  console.log('Animation cache cloning, four-entry LRU, URL/byte bounds, cancellation and single-player lease: OK');
} finally { globalThis.fetch = originalFetch; }
