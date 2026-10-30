export function parseRevision(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid snapshot revision');
  return value;
}

export function parseCombinedRevision(root: unknown, wallet: unknown, inventory: unknown): number {
  const revision = parseRevision(root);
  if (revision !== parseRevision(wallet) || revision !== parseRevision(inventory)) throw new Error('Mismatched combined snapshot revisions');
  return revision;
}

export function createRevisionGate() {
  let revision = -1;
  return {
    current: () => revision,
    accept(next: number) {
      parseRevision(next);
      if (next < revision) return false;
      revision = next;
      return true;
    },
  };
}
