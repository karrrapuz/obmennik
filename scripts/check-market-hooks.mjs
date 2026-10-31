import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const nativeRequire = createRequire(import.meta.url);
let currentRunner;
let subscribe;
const react = {
  useState: initial => currentRunner.state(initial),
  useMemo: (fn, deps) => currentRunner.memo(fn, deps),
  useEffect: (fn, deps) => currentRunner?.effect(fn, deps),
  useSyncExternalStore: (sub, get) => { subscribe = sub; return get(); },
};
const cache = new Map();
function load(filename) {
  if (filename.endsWith('.json')) return JSON.parse(fs.readFileSync(filename, 'utf8'));
  if (cache.has(filename)) return cache.get(filename).exports;
  const module = { exports: {} }; cache.set(filename, module);
  const require = specifier => {
    if (specifier === 'react') return react;
    if (!specifier.startsWith('.')) return nativeRequire(specifier);
    const target = path.resolve(path.dirname(filename), specifier);
    const resolved = [target, target + '.ts', target + '.json'].find(candidate => fs.existsSync(candidate));
    if (!resolved) throw new Error(`Missing dependency: ${specifier}`);
    return load(resolved);
  };
  const source = fs.readFileSync(filename, 'utf8').replace('import.meta.env.VITE_API_URL', "'https://api.example'");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  new Function('require', 'module', 'exports', compiled)(require, module, module.exports);
  return module.exports;
}
const same = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
class HookRunner {
  slots = []; cursor = 0; pending = [];
  state(initial) {
    const index = this.cursor++;
    this.slots[index] ??= { value: initial };
    return [this.slots[index].value, value => { this.slots[index].value = value; }];
  }
  memo(fn, deps) {
    const index = this.cursor++;
    if (!same(this.slots[index]?.deps, deps)) this.slots[index] = { value: fn(), deps };
    return this.slots[index].value;
  }
  effect(fn, deps) {
    const index = this.cursor++;
    if (!same(this.slots[index]?.deps, deps)) this.pending.push(() => {
      this.slots[index]?.cleanup?.(); this.slots[index] = { deps, cleanup: fn() };
    });
  }
  render(hook, argument) {
    this.cursor = 0; currentRunner = this;
    const result = hook(argument); currentRunner = undefined;
    this.pending.splice(0).forEach(run => run());
    return result;
  }
  unmount() { this.slots.forEach(slot => slot.cleanup?.()); }
}
let count = 0;
const pass = name => { count++; console.log(`PASS ${name}`); };
const flush = async () => { for (let index = 0; index < 8; index++) await Promise.resolve(); };
let now = 1800000000000;
const originalNow = Date.now;
Date.now = () => now;
const timers = new Map(); let timerId = 0;
const globals = Object.fromEntries(['fetch', 'window', 'document', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'].map(key => [key, globalThis[key]]));
globalThis.setTimeout = (fn, ms) => { timers.set(++timerId, { fn, ms, type: 'timeout' }); return timerId; };
globalThis.clearTimeout = id => timers.delete(id);
globalThis.setInterval = (fn, ms) => { timers.set(++timerId, { fn, ms, type: 'interval' }); return timerId; };
globalThis.clearInterval = id => timers.delete(id);
const windowTarget = new EventTarget(), documentTarget = new EventTarget();
documentTarget.visibilityState = 'visible'; globalThis.window = windowTarget; globalThis.document = documentTarget;
const seconds = now / 1000;
const feed = capturedAt => ({ schema: 1, source: 'telegram-resale', kind: 'lowest_observed_listing', capturedAt,
  validUntil: capturedAt + 86400, complete: true, collections: [{ telegramId: '12345', catalogId: 100001,
    checkedAt: capturedAt, status: 'available', floorNano: '1000000000', sampleCount: 1, hasMore: false }] });
const calls = []; let responses = [];
globalThis.fetch = async (url, options) => {
  calls.push({ url, options }); const value = responses.shift();
  if (value instanceof Error) throw value;
  return { ok: true, json: async () => value };
};
try {
  const prices = load(path.join(root, 'src/hooks/useTelegramPrices.ts'));
  responses = [feed(seconds - 10)];
  const first = prices.loadTelegramPrices(); assert.equal(first, prices.loadTelegramPrices()); await first;
  assert.equal(calls.length, 1); assert.equal(calls[0].url, 'https://api.example/api/market/prices');
  assert.equal(calls[0].options.cache, 'no-store');
  await prices.loadTelegramPrices(); assert.equal(calls.length, 1);
  pass('API first, shared single in-flight request and minimum 60-second throttle');
  now += 60000; responses = [new Error('offline'), feed(seconds - 100)]; await prices.loadTelegramPrices();
  assert.equal(calls.at(-1).url, '/gifts/telegram/prices.json');
  assert.equal(prices.useTelegramPrices().feed.capturedAt, seconds - 10);
  now += 60000; responses = [{ invalid: true }, feed(seconds + 60)]; await prices.loadTelegramPrices();
  assert.equal(prices.useTelegramPrices().feed.capturedAt, seconds + 60);
  now += 60000; responses = [new Error('offline'), new Error('offline')]; await prices.loadTelegramPrices();
  assert.equal(prices.useTelegramPrices().feed.capturedAt, seconds + 60);
  now += 60000; responses = [feed(seconds - 200)]; await prices.loadTelegramPrices();
  assert.equal(prices.useTelegramPrices().feed.capturedAt, seconds + 60);
  pass('invalid API falls back; older API/fallback never downgrade; total failure retains validated feed; finally resets request');
  const unsubscribe = subscribe(() => {}), unsubscribeSecond = subscribe(() => {});
  const polling = [...timers.values()].filter(timer => timer.type === 'interval');
  assert.equal(polling.length, 1); assert.equal(polling[0].ms, 300000);
  let previous = calls.length; windowTarget.dispatchEvent(new Event('focus')); assert.equal(calls.length, previous);
  now += 60000; documentTarget.visibilityState = 'hidden';
  windowTarget.dispatchEvent(new Event('focus')); polling[0].fn(); assert.equal(calls.length, previous);
  documentTarget.visibilityState = 'visible'; responses = [feed(seconds + 100)];
  documentTarget.dispatchEvent(new Event('visibilitychange')); await prices.loadTelegramPrices(); assert.equal(calls.length, previous + 1);
  now += 300000; responses = [feed(seconds + 300)]; polling[0].fn(); await prices.loadTelegramPrices();
  assert.equal(prices.useTelegramPrices().feed.capturedAt, seconds + 300);
  unsubscribe(); assert.equal([...timers.values()].filter(timer => timer.type === 'interval').length, 1);
  unsubscribeSecond(); assert.equal(timers.size, 0);
  previous = calls.length; now += 60000; windowTarget.dispatchEvent(new Event('focus')); assert.equal(calls.length, previous);
  pass('focus/visibility throttle, hidden polling skipped, five-minute refresh, last-listener timer/event cleanup');

  const { marketValuationQuery: query, parseMarketValuation: parse, applyMarketValuation: display, useMarketValuation: useValuation } = load(path.join(root, 'src/hooks/useMarketValuation.ts'));
  const collection = { telegramId: '12345', attributes: { models: [{ id: '67890', name: 'Model' }, { id: '67891', name: 'Other' }], symbols: [{ id: '777' }], backdrops: [{ id: -123 }] } };
  const gift = { collectionId: '12345', modelFilterId: 'tg:model:12345:67890', symbol: { id: '777' }, backdrop: { id: -123 }, price: '0', tradeSupported: false, pledgeSupported: false };
  const before = JSON.stringify(gift), a = query(gift, collection, {});
  const b = query(gift, collection, { models: ['tg:model:12345:67891'] });
  assert.equal(query({ ...gift, modelFilterId: 'tg:model:12345:67891' }, collection, {}), b);
  const collectionQuery = query({ collectionId: '12345' }, collection, {});
  assert.equal(new URLSearchParams(a).get('model_id'), gift.modelFilterId);
  assert.equal(new URLSearchParams(a).get('symbol_id'), 'tg:symbol:777');
  assert.equal(new URLSearchParams(a).get('backdrop_id'), 'tg:backdrop:-123');
  for (const models of [['Model'], ['tg:model:999:67890'], ['tg:model:12345:67890', 'tg:model:12345:67891']]) assert.equal(query(gift, collection, { models }), null);
  assert.equal(query({ ...gift, collectionId: '999' }, collection, {}), null);
  assert.equal(query(gift, { ...collection, telegramId: '9223372036854775808' }, {}), null);
  assert.equal(JSON.stringify(gift), before);
  pass('queries use selected/actual canonical member IDs only, preserve original attributes and flags');
  const result = (q, overrides = {}) => {
    const params = new URLSearchParams(q), timestamp = Math.floor(now / 1000);
    return { collectionId: params.get('collection_id'), modelId: params.get('model_id'), symbolId: params.get('symbol_id'), backdropId: params.get('backdrop_id'),
      source: 'telegram-resale', kind: 'lowest_observed_listing', readOnly: true, guaranteedValuation: false,
      tradeSupported: false, pledgeSupported: false, status: 'available', floorNano: '123', sampleCount: 2,
      checkedAt: timestamp, validUntil: timestamp + 86400, ageSeconds: 0, ...overrides };
  };
  const unknown = q => result(q, { status: 'unknown', floorNano: null, sampleCount: 0, checkedAt: null, ageSeconds: null });
  assert.equal(parse(result(a), a).floorNano, '123');
  assert.equal(parse(result(collectionQuery), collectionQuery).floorNano, '123');
  assert.equal(parse(unknown(a), a), null);
  for (const patch of [{ modelId: null }, { symbolId: 'other' }, { backdropId: 'other' }, { collectionId: '999' }, { floorNano: '01' },
    { floorNano: '100000000000001' }, { floorNano: 123 }, { sampleCount: 0 }, { checkedAt: now / 1000 + 61 },
    { validUntil: now / 1000 }, { validUntil: now / 1000 + 86401 }, { readOnly: false }, { guaranteedValuation: true }]) assert.throws(() => parse(result(a, patch), a));
  assert.throws(() => parse(result(collectionQuery, { modelId: undefined }), collectionQuery));
  assert.equal(parse(result(a, { status: 'stale', checkedAt: now / 1000 - 100, validUntil: now / 1000 - 1 }), a).floorNano, '123');
  pass('parser verifies nullable echoed filters, metadata, exact nano bounds and unknown/stale states');
  const floor = parse(result(collectionQuery), collectionQuery);
  const withFloor = { ...gift, marketPrice: { ...floor, checkedAt: floor.checkedAt + 1 } };
  assert.equal(display(withFloor, { price: floor }, false), withFloor);
  assert.equal(display(withFloor, { price: null }, false), withFloor);
  assert.equal(display(withFloor, null, true).marketPrice, undefined);
  assert.equal(display(withFloor, { price: null }, true).marketPrice, undefined);
  assert.equal(display(withFloor, { price: floor }, true).marketPrice, floor);
  assert.equal(withFloor.tradeSupported, false); assert.equal(JSON.stringify(gift), before);
  pass('newer collection feed wins; specific loading/unknown never falls back to collection floor');

  const pending = [];
  globalThis.fetch = (url, options) => new Promise(resolve => pending.push({ url, options, resolve }));
  const respond = async (index, body) => { pending[index].resolve({ ok: true, json: async () => body }); await flush(); };
  const runner = new HookRunner();
  assert.equal(runner.render(useValuation, a), null);
  assert.equal(runner.render(useValuation, b), null); assert.equal(pending[0].options.signal.aborted, true);
  await respond(1, unknown(b));
  let observed = runner.render(useValuation, b); assert.equal(observed.price, null);
  assert.equal(display(withFloor, observed, true).marketPrice, undefined);
  await respond(0, result(a)); assert.equal(runner.render(useValuation, b).price, null);
  assert.equal(runner.render(useValuation, a), null);
  await respond(2, result(a)); assert.equal(runner.render(useValuation, a).price.floorNano, '123');
  assert.equal(runner.render(useValuation, null), null);
  assert.equal(runner.render(useValuation, a), null, 'Reopen must not return cached same-query result');
  await respond(3, unknown(a)); assert.equal(runner.render(useValuation, a).price, null);
  assert.equal(display(withFloor, runner.render(useValuation, a), true).marketPrice, undefined);
  runner.render(useValuation, b); runner.unmount();
  assert.equal(pending[4].options.signal.aborted, true); await respond(4, result(b));
  assert.equal(timers.size, 0);
  pass('rapid A/B/A selection, late aborted responses, unknown no-fallback, same-query reopen and unmount cleanup');
  console.log(`${count} market hook regression groups passed`);
} finally {
  Date.now = originalNow;
  for (const [key, value] of Object.entries(globals)) {
    if (value === undefined) delete globalThis[key]; else globalThis[key] = value;
  }
}
