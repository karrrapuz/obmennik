import type { Gift } from '../data/gifts';

export type ExchangeRequest = {
  offeredGiftIds: number[];
  receivedGiftIds: number[];
};

// Черновик обмена хранит только идентификаторы. Цены подтверждает сервер.
export class ExchangeDraft {
  readonly ids: number[];

  constructor(ids: readonly number[] = []) {
    this.ids = [...new Set(ids)];
  }

  toggle(id: number): ExchangeDraft {
    return new ExchangeDraft(this.ids.includes(id)
      ? this.ids.filter((selectedId) => selectedId !== id)
      : [...this.ids, id]);
  }

  selectFrom(gifts: readonly Gift[]): Gift[] {
    const selected = new Set(this.ids);
    return gifts.filter((gift) => selected.has(gift.id));
  }

  toRequest(inventory: readonly Gift[], catalog: readonly Gift[]): ExchangeRequest {
    return {
      offeredGiftIds: this.selectFrom(inventory).map((gift) => gift.id),
      receivedGiftIds: this.selectFrom(catalog).map((gift) => gift.id),
    };
  }
}
