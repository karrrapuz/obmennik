import assert from 'node:assert/strict';
import { isConfirmedMutationRejection, mutationKey, mutationPayload } from '../src/services/mutationKeys.ts';

const entries = new Map();
const storage = {
  getItem: (key) => entries.get(key) ?? null,
  setItem: (key, value) => entries.set(key, value),
  removeItem: (key) => entries.delete(key),
};
const payload = mutationPayload({ weeks: 1, gift_id: 42 });
const first = mutationKey(1, 'loans:create', payload, storage);
assert.equal(first.key, mutationKey(1, 'loans:create', mutationPayload({ gift_id: 42, weeks: 1 }), storage).key);
assert.notEqual(first.key, mutationKey(2, 'loans:create', payload, storage).key);
assert.notEqual(first.key, mutationKey(1, 'wallet:topup', payload, storage).key);
assert.notEqual(first.key, mutationKey(1, 'loans:create', mutationPayload({ weeks: 2, gift_id: 42 }), storage).key);
first.settle();
const next = mutationKey(1, 'loans:create', payload, storage);
assert.notEqual(first.key, next.key);
first.settle();
assert.equal(mutationKey(1, 'loans:create', payload, storage).key, next.key);
assert.throws(() => mutationKey(1, 'loans:create', payload, { ...storage, getItem: () => 'corrupt' }));
assert.throws(() => mutationKey(3, 'loans:create', payload, { ...storage, setItem: () => { throw new Error('quota'); } }), /quota/);
for (const status of [401, 408, 425, 429, 500, 502, 503, 504]) assert.equal(isConfirmedMutationRejection(status), false);
for (const status of [409, 422]) assert.equal(isConfirmedMutationRejection(status), true);
console.log('Mutation key persistence, isolation, settlement and storage failures: OK');
