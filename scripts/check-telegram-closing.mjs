import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

const source = fs.readFileSync('src/services/telegram.ts', 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { initializeTelegram } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
for (const version of [6.1, 6.2, 7.7, 7.10]) {
  const calls = [];
  globalThis.window = { Telegram: { WebApp: {
    initData: 'test-only', platform: 'tdesktop', isVersionAtLeast: v => version >= Number(v),
    ...Object.fromEntries(['ready', 'expand', 'enableClosingConfirmation', 'setBackgroundColor', 'setHeaderColor', 'disableVerticalSwipes', 'setBottomBarColor'].map(name => [name, () => calls.push(name)])),
  } } };
  initializeTelegram();
  assert.equal(calls.includes('enableClosingConfirmation'), version >= 6.2);
}
globalThis.window = {};
assert.doesNotThrow(initializeTelegram);
console.log('Telegram native closing confirmation enabled on supported clients; browser fallback safe: OK');
