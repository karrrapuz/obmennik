import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const moduleUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const revisionUrl = moduleUrl(transpile(fs.readFileSync('src/services/snapshotRevision.ts', 'utf8')));
const walletUrl = moduleUrl(transpile(fs.readFileSync('src/wallet/wallet.ts', 'utf8')
  .replace('../services/snapshotRevision', revisionUrl)));
const stubsUrl = moduleUrl(`export const useCallback = () => {}, useEffect = () => {},
  useLayoutEffect = () => {}, useRef = () => {}, useState = () => {},
  useAuth = () => {}, useWallet = () => {};`);
const source = fs.readFileSync('src/hooks/useReferrals.ts', 'utf8')
  .replace("from 'react'", `from '${stubsUrl}'`)
  .replace('../auth/AuthProvider', stubsUrl)
  .replace('../wallet/WalletProvider', stubsUrl)
  .replace('../wallet/wallet', walletUrl)
  .replace('import.meta.env.VITE_API_URL', "''");
const { parseReferralSummary: parse, readReferralClaimKey } = await import(moduleUrl(transpile(source)));
const { MAX_BALANCE } = await import(walletUrl);
const valid = {
  asset: 'DEMO_TON', invited_count: 3, turnover_nano: '999999999999999999999999999999',
  earned_nano: (MAX_BALANCE + 1n).toString(), available_nano: MAX_BALANCE.toString(),
  held_nano: (MAX_BALANCE + 1n).toString(), rate_bps: 200,
  invite_url: 'https://t.me/example_bot?startapp=ref_abc-123',
};
assert.deepEqual(parse(valid), valid);
assert.equal(parse({ ...valid, invite_url: null }).invite_url, null);
assert.equal(parse({ ...valid, available_nano: '0', rate_bps: 0 }).available_nano, '0');
const url = (username, code) => `https://t.me/${username}?startapp=ref_${code}`;
for (const invite_url of [url('a1234', 'a'), url('a'.repeat(32), 'a'.repeat(60))]) {
  assert.equal(parse({ ...valid, invite_url }).invite_url, invite_url);
}
for (const invite_url of [
  url('12345', 'abc'), url('_abcd', 'abc'), url('abcd', 'abc'), url('a'.repeat(33), 'abc'),
  url('example_bot', ''), url('example_bot', 'a'.repeat(61)),
  'http://t.me/example_bot?startapp=ref_abc', 'https://evil.com/?startapp=ref_abc',
  'https://t.me.evil.com/example_bot?startapp=ref_abc',
  url('example_bot', 'abc') + '&x=1', url('example_bot', 'abc') + '#x',
  url('example_bot', '%61'), url('example_bot', 'abc') + '\n', undefined,
]) assert.throws(() => parse({ ...valid, invite_url }), `Unsafe invite URL: ${invite_url}`);
for (const field of ['turnover_nano', 'earned_nano', 'held_nano', 'available_nano']) {
  for (const amount of ['01', '-1', '1e9', '1.0', '', '1'.repeat(31), 1, null]) {
    assert.throws(() => parse({ ...valid, [field]: amount }), `${field}: ${amount}`);
  }
}
assert.throws(() => parse({ ...valid, available_nano: (MAX_BALANCE + 1n).toString() }));
for (const patch of [{ invited_count: -1 }, { invited_count: 1.1 }, { invited_count: 2 ** 53 },
  { rate_bps: 10001 }, { rate_bps: 1.5 }, { asset: 'TON' }]) assert.throws(() => parse({ ...valid, ...patch }));
for (const raw of [null, undefined, [], {}, 'bad']) assert.throws(() => parse(raw));

const storage = new Map();
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
const storageKey = 'referral-claim-v1:123';
for (const stored of [null, '', 'a'.repeat(129), 'bad key', 'bad\nkey', '\u007f', '\u0430', 'x'.repeat(100000)]) {
  storage.clear();
  if (stored !== null) storage.set(storageKey, stored);
  const key = readReferralClaimKey(storageKey);
  assert.match(key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(storage.get(storageKey), key);
  assert.equal(readReferralClaimKey(storageKey), key, 'Uncertain retries must reuse the persisted key');
}
for (const stored of ['valid-key', '!'.repeat(128)]) {
  storage.set(storageKey, stored);
  assert.equal(readReferralClaimKey(storageKey), stored);
}
console.log('Referral summary bounds, cumulative totals, trusted URLs and persisted claim keys: OK');
