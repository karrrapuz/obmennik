import { gifts, inventoryGifts, type Gift } from '../data/gifts';

export type GiftLists = { catalog: Gift[]; inventory: Gift[] };

// Контракт загрузки: API-реализация заменяет только этот источник данных.
export interface GiftRepository {
  load(signal: AbortSignal): Promise<GiftLists>;
}

export class MockGiftRepository implements GiftRepository {
  async load(signal: AbortSignal): Promise<GiftLists> {
    signal.throwIfAborted();
    return {
      catalog: gifts.map((gift) => ({ ...gift })),
      inventory: inventoryGifts.map((gift) => ({ ...gift })),
    };
  }
}

export const giftRepository: GiftRepository = new MockGiftRepository();
