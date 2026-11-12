import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';

const load = async file => import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64'));
const { openGiftRelayer, giftRelayerUrl } = await load('src/services/giftRelayer.ts');
const calls = [];
globalThis.window = { Telegram: { WebApp: { openTelegramLink: url => calls.push(['native', url]) } } };
openGiftRelayer();
globalThis.window = { open: (...args) => calls.push(['browser', ...args]) };
openGiftRelayer();
assert.equal(giftRelayerUrl, 'https://t.me/smekz');
assert.deepEqual(calls[0], ['native', giftRelayerUrl]);
assert.deepEqual(calls[1], ['browser', giftRelayerUrl, '_blank', 'noopener,noreferrer']);
const { telegramHaptic } = await load('src/services/telegram.ts');
globalThis.window = { Telegram: { WebApp: { HapticFeedback: {
  selectionChanged: () => calls.push('selection'), notificationOccurred: type => calls.push(type),
} } } };
telegramHaptic(); telegramHaptic('success'); telegramHaptic('error');
assert.deepEqual(calls.slice(2), ['selection', 'success', 'error']);
globalThis.window.Telegram.WebApp.HapticFeedback.impactOccurred = style => calls.push(style);
telegramHaptic();
assert.equal(calls.at(-1), 'light', 'Button presses prefer a perceptible light impact');
globalThis.window = {};
assert.doesNotThrow(() => telegramHaptic());
const modal = fs.readFileSync('src/pages/ProfilePage/components/ProfileModal/ProfileModal.tsx', 'utf8');
assert(!modal.includes("mutate('deposit')"), 'Opening the relayer must not grant a fake gift');
assert(modal.includes('profile-modal__content'));
assert(fs.readFileSync('src/wallet/wallet.ts', 'utf8').includes("asset: 'DEMO_TON'"), 'Display rename must preserve API identifiers');
assert.match(fs.readFileSync('src/assets/gram.svg', 'utf8'), /fill="#31A1F5"/i);
console.log('GRAM display preserves API units; relayer opens only smekz without granting gifts; haptics safe: OK');
