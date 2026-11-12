const prefix = 'obmennik:pending-mutation:v1:';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function mutationPayload(body: Record<string, unknown>) {
  return JSON.stringify(Object.fromEntries(Object.keys(body).sort().map((key) => [key, body[key]])));
}

export function mutationKey(userId: number, operation: string, payload: string, storage = localStorage) {
  const slot = prefix + JSON.stringify([userId, operation, payload]);
  let key = storage.getItem(slot);
  // Fail closed if we cannot reliably recover or persist the receipt key.
  if (key !== null && !uuid.test(key)) throw new Error('Invalid pending operation key');
  if (key === null) {
    key = crypto.randomUUID();
    storage.setItem(slot, key);
  }
  const reserved = key;
  return {
    key: reserved,
    settle() {
      if (storage.getItem(slot) === reserved) storage.removeItem(slot);
    },
  };
}

export function isConfirmedMutationRejection(status: number) {
  // Wallet and loan business rules and input validation reject before commit.
  return status === 409 || status === 422;
}
